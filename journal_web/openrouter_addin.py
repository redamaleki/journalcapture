from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


OCR_PROMPT = """
Role: Pure Vision-to-Text Engine.

Task: Transcribe every glyph and character exactly as seen.

Language Rule: Do not assume a primary language. If a word looks like "calc" or "Bible Bounce", transcribe it exactly as such regardless of the surrounding context.

No Reasoning: Do not verify dates, check calendars, infer missing context, or validate whether the language is correct.

Verbatim Only: Transcribe exactly what is written. Do not correct spelling or grammar.

Ignore Context: Do not link entries, summarize content, or interpret ambiguous words.

Multiple Entry Detection: Scan the page for multiple distinct entries. If a page contains more than one entry, such as a new date header or a visual separator, return each as a separate object within the entries array. Do not merge text from different entries into a single transcription field.

Format: Valid JSON only. No prose. No explanations.

Minimal metadata: Provide only date_text and transcription.

If a visible written date heading starts an entry, copy it into date_text and also include that same written date line as the first line of the transcription for that entry.

Preserve useful line breaks in transcription when they exist on the page.

Return only valid JSON matching this exact shape:
{
  "entries": [
    {
      "date_text": "string or null",
      "transcription": "exact transcription, including the visible written date heading as the first line when present"
    }
  ]
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
    ocr_model: str
    translation_model: str
    reasoning_max_tokens: int = 0
    image_model: str = ""
    app_name: str = "Journal Capture"
    site_url: str = "http://localhost:5000"


def enabled() -> bool:
    return bool(os.environ.get("OPENROUTER_API_KEY") and (os.environ.get("OPENROUTER_OCR_MODEL") or os.environ.get("OPENROUTER_MODEL")))


def load_config() -> OpenRouterConfig:
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    ocr_model = (os.environ.get("OPENROUTER_OCR_MODEL") or os.environ.get("OPENROUTER_MODEL") or "google/gemini-3-flash-preview").strip()
    translation_model = os.environ.get("OPENROUTER_TRANSLATION_MODEL", "google/gemini-3.1-flash-lite").strip()
    if not api_key or not ocr_model or not translation_model:
        raise RuntimeError(
            "Transcribe and Translate add-in is not configured. "
            "Set OPENROUTER_API_KEY, OPENROUTER_OCR_MODEL (or OPENROUTER_MODEL), and OPENROUTER_TRANSLATION_MODEL."
        )
    try:
        reasoning_max_tokens = int(os.environ.get("OPENROUTER_REASONING_MAX_TOKENS", "0") or 0)
    except ValueError:
        reasoning_max_tokens = 0
    return OpenRouterConfig(
        api_key=api_key,
        ocr_model=ocr_model,
        translation_model=translation_model,
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


def _parse_json_object(content: str) -> Any:
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        fenced_start = content.find("```")
        if fenced_start != -1:
            fenced_end = content.find("```", fenced_start + 3)
            if fenced_end != -1:
                fenced_body = content[fenced_start + 3 : fenced_end]
                if fenced_body.lstrip().startswith("json"):
                    fenced_body = fenced_body.lstrip()[4:]
                try:
                    parsed = json.loads(fenced_body.strip())
                except json.JSONDecodeError:
                    parsed = None
                if parsed is not None:
                    if isinstance(parsed, list) and len(parsed) == 1 and isinstance(parsed[0], dict):
                        parsed = parsed[0]
                    if isinstance(parsed, (dict, list)):
                        return parsed
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end <= start:
            array_start = content.find("[")
            array_end = content.rfind("]")
            if array_start != -1 and array_end > array_start:
                parsed = json.loads(content[array_start : array_end + 1])
            else:
                raise ValueError(f"Model response was not parseable JSON. Response snippet: {content[:500]}")
        else:
            parsed = json.loads(content[start : end + 1])
    if isinstance(parsed, list) and len(parsed) == 1 and isinstance(parsed[0], dict):
        parsed = parsed[0]
    if not isinstance(parsed, (dict, list)):
        raise ValueError(f"Model response was not a JSON object or array. Response snippet: {content[:500]}")
    return parsed


def _normalize_ocr_result(parsed: Any) -> dict[str, Any]:
    entries = []
    if isinstance(parsed, list):
        raw_entries = parsed
    elif isinstance(parsed, dict):
        raw_entries = parsed.get("entries") or []
    else:
        raw_entries = []
    for entry in raw_entries:
        if not isinstance(entry, dict):
            continue
        entries.append(
            {
                "date_text": entry.get("date_text") or "",
                "transcription": entry.get("transcription") or "",
            }
        )
    return {"entries": entries}


def _normalize_translation_result(parsed: Any) -> dict[str, dict[str, Any]]:
    if isinstance(parsed, list):
        source = {str(index): value for index, value in enumerate(parsed)}
    elif isinstance(parsed, dict):
        source = parsed.get("entries") if isinstance(parsed.get("entries"), dict) else parsed
    else:
        return {}
    if not isinstance(source, dict):
        return {}
    normalized: dict[str, dict[str, Any]] = {}
    for key, value in source.items():
        if not isinstance(value, dict):
            continue
        raw_notes = value.get("review_notes")
        if isinstance(raw_notes, list):
            review_notes = [str(note) for note in raw_notes]
        elif isinstance(raw_notes, str):
            review_notes = [raw_notes] if raw_notes.strip() else []
        elif raw_notes is None:
            review_notes = []
        else:
            review_notes = [str(raw_notes)]
        normalized[str(key)] = {
            "translation": value.get("translation") or "",
            "normalized_date": value.get("normalized_date") or "",
            "review_notes": review_notes,
        }
    return normalized


def _infer_date_source(index: int, date_text: str, previous_date_text: str, normalized_date: str) -> str:
    if date_text:
        return "visible_on_page"
    if index == 0 and previous_date_text:
        return "carried_from_context"
    if normalized_date:
        return "inferred"
    return ""


def _merge_entries(
    ocr_entries: list[dict[str, Any]],
    translation_enrichment: dict[str, dict[str, Any]],
    *,
    previous_date_text: str = "",
) -> list[dict[str, Any]]:
    merged = []
    for index, entry in enumerate(ocr_entries):
        enrich = translation_enrichment.get(str(index), {})
        normalized_date = enrich.get("normalized_date") or ""
        merged.append(
            {
                "date_text": entry.get("date_text") or "",
                "entry_date": normalized_date,
                "date_source": _infer_date_source(index, entry.get("date_text") or "", previous_date_text, normalized_date),
                "is_continuation_from_previous_page": bool(index == 0 and not (entry.get("date_text") or "") and previous_date_text),
                "transcription": entry.get("transcription") or "",
                "translation": enrich.get("translation") or "",
                "confidence": "",
                "review_notes": enrich.get("review_notes") or [],
            }
        )
    return merged


def _combine_usage(*usages: Any) -> dict[str, Any]:
    prompt_tokens = 0
    completion_tokens = 0
    total_tokens = 0
    cost = 0.0
    saw_cost = False
    for usage in usages:
        if not isinstance(usage, dict):
            continue
        prompt_tokens += int(usage.get("prompt_tokens") or 0)
        completion_tokens += int(usage.get("completion_tokens") or 0)
        total_tokens += int(usage.get("total_tokens") or 0)
        if usage.get("cost") is not None:
            try:
                cost += float(usage.get("cost"))
                saw_cost = True
            except (TypeError, ValueError):
                pass
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "cost": cost if saw_cost else None,
    }


def _translation_prompt(previous_date_text: str = "", journal_year: str = "", extra_instructions: str = "") -> str:
    parts = [
        "You are translating already-transcribed journal entries for family history research.",
        "Return only valid JSON.",
        "Input JSON contains OCR/transcription results. Do not return transcription again.",
        "Return a JSON object where each key is the zero-based index of the entry.",
        "For each entry key, return only: translation, normalized_date, and review_notes.",
        "translation should be a meaning-preserving English translation. If the transcription is already English, set translation to null.",
        "Use journal_year to normalize visible month/day dates into YYYY-MM-DD when confident.",
        "If the first entry has date_text null or empty and previous_date_text is provided, treat it as continuation from the previous page and use previous_date_text plus journal_year to produce normalized_date when you can do so confidently.",
        "If you cannot confidently normalize a date, leave normalized_date null and explain briefly in review_notes.",
        "If a stray number at the top of the transcription appears to be a page number rather than a date or meaningful content marker, do not add a review note about it.",
        "Do not preserve source line breaks in translation unless the line break changes or clarifies meaning. Prefer natural prose paragraphs or sentences over line-for-line formatting.",
        "Do not include any fields other than translation, normalized_date, and review_notes.",
    ]
    if previous_date_text or journal_year:
        parts.append(
            f"Context:\n- previous_date_text: {previous_date_text or 'not provided'}\n- journal_year: {journal_year or 'not provided'}\n"
            "Use this only to understand ambiguous wording in the translation. Do not alter the transcription structure."
        )
    if extra_instructions:
        parts.append(f"Extra test instructions for translation only:\n{extra_instructions}")
    return "\n\n".join(parts)


def transcribe_page(
    image_path: Path,
    previous_date_text: str = "",
    journal_year: str = "",
    include_translation: bool = True,
) -> dict[str, Any]:
    config = load_config()
    source_data_url = _data_url(image_path)

    ocr_payload: dict[str, Any] = {
        "model": config.ocr_model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": OCR_PROMPT},
                    {"type": "image_url", "image_url": {"url": source_data_url}},
                ],
            }
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }

    ocr_raw = _post_openrouter(config, ocr_payload)
    ocr_content = ocr_raw.get("choices", [{}])[0].get("message", {}).get("content", "")
    ocr_result = _normalize_ocr_result(_parse_json_object(ocr_content))
    ocr_entries = ocr_result.get("entries") or []

    translation_payload: dict[str, Any] | None = None
    translation_raw: dict[str, Any] | None = None
    translation_result: dict[str, Any] | None = None
    translation_enrichment: dict[str, dict[str, Any]] = {}

    if include_translation:
        translation_payload = {
            "model": config.translation_model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": _translation_prompt(previous_date_text, journal_year)},
                        {"type": "text", "text": json.dumps(ocr_result)},
                    ],
                }
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        if config.reasoning_max_tokens > 0:
            translation_payload["reasoning"] = {"max_tokens": config.reasoning_max_tokens, "exclude": True}
        translation_raw = _post_openrouter(config, translation_payload)
        translation_content = translation_raw.get("choices", [{}])[0].get("message", {}).get("content", "")
        translation_result = _parse_json_object(translation_content)
        translation_enrichment = _normalize_translation_result(translation_result)

    merged_entries = _merge_entries(ocr_entries, translation_enrichment, previous_date_text=previous_date_text)

    return {
        "model": config.ocr_model,
        "models": {
            "ocr": config.ocr_model,
            "translation": config.translation_model if include_translation else "",
        },
        "reasoning": {
            "ocr": {"enabled": False},
            "translation": {
                "enabled": bool(include_translation and config.reasoning_max_tokens > 0),
                "max_tokens": config.reasoning_max_tokens or None,
                "exclude": True,
            },
        },
        "usage": {
            **_combine_usage(ocr_raw.get("usage"), (translation_raw or {}).get("usage")),
            "ocr": ocr_raw.get("usage"),
            "translation": (translation_raw or {}).get("usage"),
        },
        "steps": {
            "ocr": {
                "model": config.ocr_model,
                "request": ocr_payload,
                "result": ocr_result,
                "rawContent": ocr_content,
            },
            "translation": {
                "model": config.translation_model,
                "request": translation_payload,
                "result": translation_result,
                "rawContent": translation_raw.get("choices", [{}])[0].get("message", {}).get("content", "") if translation_raw else "",
            } if include_translation else None,
        },
        "data": {
            "entries": merged_entries,
        },
        "entries": merged_entries,
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
