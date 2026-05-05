from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


TRANSCRIBE_PROMPT = """
You are processing a photographed or scanned journal page for family history research.

Return only valid JSON matching the requested schema. Do not wrap the result in an array.

Core rules:
- Do not hallucinate. Transcription should be as close to exact as possible.
- If text is unclear, mark it explicitly with `[unclear]` or a best guess followed by `[?]`.
- Preserve original spelling, punctuation, capitalization, abbreviations, and meaningful line breaks in the transcription.
- If a date is visibly written as an entry heading, include that written date line inside `transcription` exactly as written, and also copy it into `date_text`.
- Translate to the true meaning of the writing if translating, not mechanically word-for-word.
- Entries should be split by dates recorded on the page.
- Do not invent dates, names, places, relationships, or events.
- If the first entry on the page has no visible date and previous_date_text is provided, treat that first entry as a continuation: set date_source to carried_from_context and is_continuation_from_previous_page to true.
- If journal_year is provided, use it to normalize visible month/day dates and carried-forward dates when otherwise ambiguous.

Return exactly this JSON object shape:
{
  "status": "ok | needs_review | failed",
  "language_detected": "string or null",
  "image_assessment": {
    "readability": "good | fair | poor",
    "issues": ["string"],
    "adjustment_used": false,
    "adjustment_notes": "string"
  },
  "page_notes": ["string"],
  "context_used": {
    "previous_date_text": "string or null",
    "journal_year": "string or null",
    "notes": ["string"]
  },
  "entries": [
    {
      "date_text": "date as written, or null",
      "normalized_date": "YYYY-MM-DD if confidently inferable, otherwise null",
      "date_source": "visible_on_page | carried_from_context | inferred | unknown",
      "is_continuation_from_previous_page": false,
      "transcription": "exact transcription with useful line breaks; include the visible written date heading as the first line when present",
      "translation": "meaning-preserving English translation, or null if already English/not requested",
      "confidence": "high | medium | low",
      "review_notes": ["string"]
    }
  ],
  "review": {
    "summary": "brief human-readable summary",
    "warnings": ["string"],
    "unclear_words": ["string"],
    "suggested_next_steps": ["string"]
  }
}
""".strip()

IMAGE_ADJUST_PROMPT = (
    "De-skew the image and crop/shrink the canvas to the journal page only. "
    "Preserve original detail, handwriting texture, ink, paper color, shadows, and page markings. "
    "Do not redraw, clean up, reinterpret, or enhance the handwriting. "
    "Keep the result faithful to the original page while correcting only page angle and excess surrounding canvas."
)


@dataclass
class OpenRouterConfig:
    api_key: str
    model: str
    reasoning_max_tokens: int = 0
    image_model: str = ""
    app_name: str = "Journal Capture"
    site_url: str = "http://localhost:5000"


def enabled() -> bool:
    return bool(os.environ.get("OPENROUTER_API_KEY") and os.environ.get("OPENROUTER_MODEL"))


def load_config() -> OpenRouterConfig:
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    model = os.environ.get("OPENROUTER_MODEL", "").strip()
    if not api_key or not model:
        raise RuntimeError("Transcribe and Translate add-in is not configured. Set OPENROUTER_API_KEY and OPENROUTER_MODEL.")
    try:
        reasoning_max_tokens = int(os.environ.get("OPENROUTER_REASONING_MAX_TOKENS", "0") or 0)
    except ValueError:
        reasoning_max_tokens = 0
    return OpenRouterConfig(
        api_key=api_key,
        model=model,
        reasoning_max_tokens=reasoning_max_tokens,
        image_model=os.environ.get("OPENROUTER_IMAGE_MODEL", "").strip(),
        app_name=os.environ.get("OPENROUTER_APP_NAME", "Journal Capture"),
        site_url=os.environ.get("OPENROUTER_SITE_URL", "http://localhost:5000"),
    )


def _headers(config: OpenRouterConfig) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": config.site_url,
        "X-Title": config.app_name,
    }


def _post_openrouter(config: OpenRouterConfig, payload: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers=_headers(config),
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenRouter request failed ({exc.code}): {body}") from exc


def _data_url(path: Path) -> str:
    mime = "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _parse_json_object(content: str) -> dict[str, Any]:
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end <= start:
            raise
        parsed = json.loads(content[start : end + 1])
    if isinstance(parsed, list) and len(parsed) == 1 and isinstance(parsed[0], dict):
        parsed = parsed[0]
    if not isinstance(parsed, dict):
        raise ValueError("Model response was not a JSON object.")
    return parsed


def _normalize_entries(data: dict[str, Any]) -> list[dict[str, Any]]:
    entries = []
    for entry in data.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        entries.append({
            "date_text": entry.get("date_text") or "",
            "entry_date": entry.get("normalized_date") or "",
            "date_source": entry.get("date_source") or "unknown",
            "is_continuation_from_previous_page": bool(entry.get("is_continuation_from_previous_page")),
            "transcription": entry.get("transcription") or "",
            "translation": entry.get("translation") or "",
            "confidence": entry.get("confidence") or "",
            "review_notes": entry.get("review_notes") or [],
        })
    return entries


def transcribe_page(image_path: Path, previous_date_text: str = "", journal_year: str = "", include_translation: bool = True) -> dict[str, Any]:
    config = load_config()
    source_data_url = _data_url(image_path)
    context = (
        f"Translation requested: {'yes' if include_translation else 'no'}.\n"
        f"previous_date_text: {previous_date_text or 'not provided'}\n"
        f"journal_year: {journal_year or 'not provided'}\n"
        "Use the original uploaded image for transcription and translation."
    )
    payload: dict[str, Any] = {
        "model": config.model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": f"{TRANSCRIBE_PROMPT}\n\n{context}"},
                {"type": "image_url", "image_url": {"url": source_data_url}},
            ],
        }],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    if config.reasoning_max_tokens > 0:
        payload["reasoning"] = {"max_tokens": config.reasoning_max_tokens, "exclude": True}

    raw = _post_openrouter(config, payload)
    content = raw.get("choices", [{}])[0].get("message", {}).get("content", "")
    data = _parse_json_object(content)
    return {
        "model": config.model,
        "reasoning": {"enabled": config.reasoning_max_tokens > 0, "max_tokens": config.reasoning_max_tokens or None, "exclude": True},
        "usage": raw.get("usage"),
        "data": data,
        "entries": _normalize_entries(data),
    }


def create_adjusted_image(image_path: Path) -> dict[str, Any] | None:
    config = load_config()
    if not config.image_model:
        return None
    payload = {
        "model": config.image_model,
        "modalities": ["image", "text"],
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": IMAGE_ADJUST_PROMPT},
                {"type": "image_url", "image_url": {"url": _data_url(image_path)}},
            ],
        }],
    }
    raw = _post_openrouter(config, payload)
    message = raw.get("choices", [{}])[0].get("message", {})
    images = message.get("images") or []
    if not images:
        return {"error": "Image model did not return an image.", "usage": raw.get("usage"), "prompt": IMAGE_ADJUST_PROMPT}
    image_url = images[0].get("image_url", {}).get("url") or images[0].get("imageUrl", {}).get("url")
    return {
        "model": config.image_model,
        "prompt": IMAGE_ADJUST_PROMPT,
        "usage": raw.get("usage"),
        "data_url": image_url,
    }


def decode_data_url(data_url: str) -> bytes:
    prefix, encoded = data_url.split(",", 1)
    return base64.b64decode(encoded)
