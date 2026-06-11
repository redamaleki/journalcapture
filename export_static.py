#!/usr/bin/env python3
"""
Export a static, self-contained reader for a subset of journal pages + attached images.

Usage (from journalapp dir, inside venv or with deps):
  python export_static.py --journal-id <uuid> --pages "1-10,15" --out-dir ~/Public/my-excerpt
  python export_static.py --journal-dir /path/to/copied/journal-uuid-dir --all --out-dir ./share

The output is a folder you can zip, upload to static hosting, or open directly via file://.
It reuses the exact parsing rules and the beautiful reader UI from the app.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import date
from pathlib import Path
from typing import Any

# --- Pure imports from the app (no Flask context required) ---
# These are deliberately the minimal stable pieces for loading + normalization.
try:
    from journal_web.utils import (
        load_frontmatter,
        read_people,
        sort_key_page_name,
        first_line,
    )
except Exception as e:  # pragma: no cover - helpful message when run outside tree
    print("ERROR: Could not import from journal_web.utils.")
    print("Run this from the journalapp directory (the one containing journal_web/ and data/).")
    print("Inside the project's venv is recommended so all packages (PyYAML etc) are present.")
    print(f"Import error: {e}")
    sys.exit(1)


def resolve_journals_root() -> Path:
    """Best-effort journals root, matching the app's env-driven defaults."""
    env = os.environ.get("JOURNAL_JOURNALS_DIR")
    if env:
        return Path(env).expanduser()
    env_data = os.environ.get("JOURNAL_DATA_DIR")
    if env_data:
        return Path(env_data).expanduser() / "journals"
    # Default relative to this script (works when run from project root)
    base = Path(__file__).resolve().parent
    return base / "data" / "journals"


def load_journal(journal_dir: Path) -> dict[str, Any]:
    """Load journal metadata (no pages). Returns a dict similar to storage.get_journal(..., include_pages=False)."""
    meta, _ = load_frontmatter(journal_dir / "journal.md")
    people = read_people(journal_dir / "people.json")
    cover = meta.get("cover_photo") or ""
    return {
        "id": journal_dir.name,
        "dir": journal_dir,
        "title": meta.get("title", "Untitled Journal"),
        "owner": meta.get("owner", ""),
        "description": meta.get("description", ""),
        "has_translation": bool(meta.get("has_translation", False)),
        "cover_photo": cover,
        "created": meta.get("created", ""),
        "last_modified": meta.get("last_modified", ""),
        "mode": (meta.get("mode") or "editing").strip().lower(),
        "people": people,
        "page_count": int(meta.get("page_count") or 0),
    }


def synthesize_entries(meta: dict[str, Any]) -> list[dict[str, str]]:
    """Handle legacy single-entry pages (pre-entries[] format) exactly like the app."""
    entries = meta.get("entries") or []
    if entries:
        return entries
    legacy_date = meta.get("entry_date", "") or ""
    legacy_trans = meta.get("transcription", "") or ""
    legacy_transl = meta.get("translation", "") or ""
    legacy_notes = meta.get("notes", "") or ""
    if legacy_date or legacy_trans.strip() or legacy_transl.strip() or legacy_notes.strip():
        return [{
            "entry_date": legacy_date,
            "transcription": legacy_trans,
            "translation": legacy_transl,
            "notes": legacy_notes,
        }]
    return []


def load_pages(journal_dir: Path) -> list[dict[str, Any]]:
    """Return pages in scan order (page-001 first). Each item has the keys the reader template expects."""
    pages_dir = journal_dir / "pages"
    if not pages_dir.exists():
        return []
    pages: list[dict[str, Any]] = []
    for md_path in sorted(pages_dir.glob("page-*.md"), key=sort_key_page_name):
        meta, body = load_frontmatter(md_path)
        slug = md_path.stem  # e.g. page-003
        entries = synthesize_entries(meta)
        primary = entries[0] if entries else {}
        main_img = pages_dir / f"{slug}.jpg"
        scraps = meta.get("scrapbook_items", []) or []
        pages.append({
            "slug": slug,
            "page_number": meta.get("page_number"),
            "entry_date": primary.get("entry_date", meta.get("entry_date", "")),
            "entries": entries,
            "people": meta.get("people", []) or [],
            "scrapbook_items": scraps,
            "transcription": primary.get("transcription", meta.get("transcription", "")),
            "translation": primary.get("translation", meta.get("translation", "")),
            "notes": primary.get("notes", meta.get("notes", "")),
            "body": body or "",
            # image/scrap urls are filled later by the exporter after we know the media dir
            "image_url": None,
            "scrapbook_urls": [],
        })
    return pages


def parse_page_spec(spec: str, all_pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Support '1-5,7,10-12' or 'all'. Matches against page_number (preferred) or slug."""
    if not spec or spec.lower() in {"all", "*"}:
        return list(all_pages)

    wanted: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            try:
                start, end = int(a), int(b)
                wanted.update(range(start, end + 1))
            except ValueError:
                pass
        else:
            try:
                wanted.add(int(part))
            except ValueError:
                pass

    if not wanted:
        return list(all_pages)

    selected = []
    for p in all_pages:
        pn = p.get("page_number")
        if isinstance(pn, int) and pn in wanted:
            selected.append(p)
        else:
            # fallback: allow matching by slug number if user passed 003 etc.
            try:
                if int(p["slug"].split("-")[-1]) in wanted:
                    selected.append(p)
            except Exception:
                pass
    return selected


def copy_media(journal_dir: Path, selected_pages: list[dict[str, Any]], media_dir: Path, include_cover: bool, journal_meta: dict[str, Any]) -> dict[str, str]:
    """Copy only the images we actually need. Returns mapping of logical name -> relative media path used in HTML."""
    media_dir.mkdir(parents=True, exist_ok=True)
    pages_dir = journal_dir / "pages"
    copied: dict[str, str] = {}

    # Cover (optional)
    cover_name = journal_meta.get("cover_photo") or ""
    if include_cover and cover_name:
        src = journal_dir / cover_name
        if src.exists():
            dst = media_dir / "cover.jpg"
            shutil.copy2(src, dst)
            copied["cover"] = "media/cover.jpg"

    # Per-page main + scrapbooks
    for p in selected_pages:
        slug = p["slug"]
        # main
        main_src = pages_dir / f"{slug}.jpg"
        if main_src.exists():
            dst = media_dir / f"{slug}.jpg"
            shutil.copy2(main_src, dst)
            copied[f"{slug}.jpg"] = f"media/{slug}.jpg"
            p["image_url"] = f"media/{slug}.jpg"
        # scraps
        scrap_urls = []
        for sname in p.get("scrapbook_items", []) or []:
            ssrc = pages_dir / sname
            if ssrc.exists():
                sdst = media_dir / sname
                shutil.copy2(ssrc, sdst)
                copied[sname] = f"media/{sname}"
                scrap_urls.append(f"media/{sname}")
        p["scrapbook_urls"] = scrap_urls

    return copied


def compute_date_range(pages: list[dict[str, Any]]) -> str:
    dated = []
    for p in pages:
        for e in (p.get("entries") or []):
            d = (e.get("entry_date") or "").strip()
            if d:
                dated.append(d)
    if not dated:
        return ""
    dated.sort()
    return dated[0] if dated[0] == dated[-1] else f"{dated[0]} – {dated[-1]}"


def main() -> None:
    ap = argparse.ArgumentParser(description="Export a static reader for a journal subset (pages + attached images).")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--journal-id", help="UUID of journal under the journals root (e.g. 6cd68ae1-...)")
    src.add_argument("--journal-dir", type=Path, help="Direct path to a journal directory (works on backups/copies)")

    ap.add_argument("--pages", default="all", help='Subset e.g. "1-5,12,20-22" (by page_number) or "all"')
    ap.add_argument("--out-dir", type=Path, help="Output directory for the static site (default: ./journal-static-<shortid>-<date>)")
    ap.add_argument("--include-cover", action="store_true", help="Include journal cover if present")
    ap.add_argument("--include-raw-md", action="store_true", help="Also copy the selected page-*.md files into out/raw/")
    ap.add_argument("--all", action="store_true", help="Force include every page (use with care on large journals)")
    ap.add_argument("--serve", action="store_true", help="After export, start a local static server for preview")
    args = ap.parse_args()

    # Resolve source
    if args.journal_dir:
        journal_dir = args.journal_dir.expanduser().resolve()
        if not (journal_dir / "journal.md").exists():
            print(f"ERROR: {journal_dir} does not look like a journal dir (missing journal.md)")
            sys.exit(2)
        journal_id = journal_dir.name
    else:
        root = resolve_journals_root()
        journal_dir = (root / args.journal_id).resolve()
        journal_id = args.journal_id
        if not journal_dir.exists():
            print(f"ERROR: Journal not found: {journal_dir}")
            print(f"   (journals root = {root})")
            sys.exit(2)

    print(f"Loading journal from: {journal_dir}")

    jmeta = load_journal(journal_dir)
    all_pages = load_pages(journal_dir)

    if not all_pages:
        print("No pages found. Nothing to export.")
        sys.exit(0)

    # Subset selection
    if args.all:
        selected = list(all_pages)
    else:
        selected = parse_page_spec(args.pages, all_pages)
    if not selected:
        print("No pages matched the --pages filter.")
        sys.exit(2)

    if len(selected) > 40 and not args.all:
        print(f"WARNING: exporting {len(selected)} pages. Use --all only if you really want the whole thing.")

    # Output location
    today = date.today().isoformat()
    short = journal_id.split("-")[0] if "-" in journal_id else journal_id[:8]
    default_out = Path.cwd() / f"journal-static-{short}-{today}"
    out = (args.out_dir or default_out).expanduser().resolve()
    if out.exists():
        # gentle safety: don't nuke random dirs
        if any(out.iterdir()):
            print(f"ERROR: --out-dir {out} already exists and is non-empty. Choose a different path or remove it first.")
            sys.exit(2)
    out.mkdir(parents=True, exist_ok=True)
    media_dir = out / "media"
    raw_dir = out / "raw" if args.include_raw_md else None

    # Copy images (mutates selected with the url fields)
    copied = copy_media(journal_dir, selected, media_dir, include_cover=args.include_cover, journal_meta=jmeta)

    # Prepare template context (shape compatible with the reader expectations)
    date_range = compute_date_range(selected)
    has_any_translation = jmeta.get("has_translation", False) or any(
        (e.get("translation") or "").strip() for p in selected for e in (p.get("entries") or [])
    )

    journal_ctx = {
        "id": journal_id,
        "title": jmeta.get("title", "Untitled Journal"),
        "owner": jmeta.get("owner", ""),
        "description": jmeta.get("description", ""),
        "page_count": len(selected),
        "has_translation": has_any_translation,
        "cover_url": copied.get("cover") if args.include_cover else "",
        "pages": selected,
    }

    # Optional raw .md copies for transparency / further parsing by recipient
    if raw_dir:
        raw_dir.mkdir(parents=True, exist_ok=True)
        pages_dir = journal_dir / "pages"
        for p in selected:
            md_src = pages_dir / f"{p['slug']}.md"
            if md_src.exists():
                shutil.copy2(md_src, raw_dir / md_src.name)
            # also the images are already in media; raw/ is just the sidecar mds
        # copy journal.md + people.json for the subset context
        for name in ("journal.md", "people.json"):
            src = journal_dir / name
            if src.exists():
                shutil.copy2(src, raw_dir / name)

    # Write data.json (full parsed text content, no images) — useful for "parse" use cases
    data_payload = {
        "journal": {
            "id": journal_ctx["id"],
            "title": journal_ctx["title"],
            "owner": journal_ctx["owner"],
            "description": journal_ctx["description"],
            "exported": today,
            "source_dir_name": journal_id,
            "page_count_in_excerpt": len(selected),
            "date_range": date_range,
        },
        "pages": [
            {
                "slug": p["slug"],
                "page_number": p["page_number"],
                "entry_date": p["entry_date"],
                "entries": p["entries"],
                "people": p["people"],
                "notes_body": p.get("body", ""),
            }
            for p in selected
        ],
    }
    (out / "data.json").write_text(json.dumps(data_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    # Render the static reader (requires jinja2, which is pulled by Flask in the project venv)
    try:
        from jinja2 import Environment, FileSystemLoader, select_autoescape
    except ImportError:
        print("ERROR: jinja2 is required for the exporter.")
        print("Inside the journalapp venv it should be present (transitive from Flask).")
        print("If running outside: pip install jinja2 pyyaml pillow")
        sys.exit(3)

    templates_dir = Path(__file__).resolve().parent / "templates"
    env = Environment(
        loader=FileSystemLoader(str(templates_dir)),
        autoescape=select_autoescape(["html", "htm"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    tmpl = env.get_template("static_reader.html")
    html = tmpl.render(
        journal=journal_ctx,
        date_range=date_range,
        export_date=today,
    )
    (out / "index.html").write_text(html, encoding="utf-8")

    # Tiny helpful readme for the recipient
    readme = f"""Static Journal Excerpt
======================

Title: {journal_ctx['title']}
Owner: {journal_ctx['owner'] or '—'}
Pages in this excerpt: {len(selected)} (of original ~{jmeta.get('page_count', '?')})
Date range: {date_range or '—'}
Exported: {today}
Source journal id: {journal_id}

How to view
-----------
- Open index.html in any modern browser (double-click or file://...).
- Works completely offline. All images are in the media/ folder next to it.
- You can also serve the whole folder with any static server:
    python -m http.server -d {out.name} 0
    (or npx serve, caddy file-server, etc.)

This was generated by the Journal Capture app's static exporter.
The original app can still edit the source journal (data is unchanged).
Raw page metadata (for parsing/auditing) is in data.json{ ' and raw/' if raw_dir else '' }.
"""
    (out / "README.txt").write_text(readme, encoding="utf-8")

    print(f"\n✓ Exported static reader to: {out}")
    print(f"  Pages: {len(selected)}")
    print(f"  Media files copied: {len(copied)}")
    print(f"  Open: {out / 'index.html'}")
    print(f"  (or: cd {out} && python -m http.server 0 )")

    if args.serve:
        print("\nStarting local preview server (Ctrl-C to stop)...")
        os.chdir(str(out))
        # Use the same python that ran us
        os.execv(sys.executable, [sys.executable, "-m", "http.server", "0"])


if __name__ == "__main__":
    main()
