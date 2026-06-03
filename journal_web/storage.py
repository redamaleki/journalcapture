from __future__ import annotations

import json
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from flask import current_app

JOURNAL_MODE_EDITING = 'editing'
JOURNAL_MODE_COMPLETE = 'complete'
JOURNAL_MODES = {JOURNAL_MODE_EDITING, JOURNAL_MODE_COMPLETE}


def normalize_journal_mode(meta: dict[str, Any]) -> str:
    mode = (meta.get('mode') or JOURNAL_MODE_EDITING).strip().lower()
    return mode if mode in JOURNAL_MODES else JOURNAL_MODE_EDITING


def journal_is_editing(journal: dict[str, Any]) -> bool:
    return normalize_journal_mode(journal) == JOURNAL_MODE_EDITING


from .utils import (
    copy_file,
    ensure_people_file,
    first_line,
    journal_uuid,
    load_frontmatter,
    make_thumbnail,
    now_iso_date,
    read_people,
    save_frontmatter,
    save_uploaded_image_as_jpeg,
    save_yaml_only,
    sort_key_page_name,
    update_last_modified,
    valid_date,
    write_people,
    _normalize_for_yaml,
)


class JournalStore:
    def __init__(self):
        self.journals_dir: Path = current_app.config['JOURNALS_DIR']
        self.thumbs_dir: Path = current_app.config['THUMBS_DIR']

    def list_journals(self) -> list[dict[str, Any]]:
        journals = []
        for journal_dir in sorted(self.journals_dir.iterdir() if self.journals_dir.exists() else [], key=lambda p: p.name):
            if journal_dir.is_dir():
                journals.append(self.get_journal(journal_dir.name, include_pages=False))
        return journals

    def delete_journal(self, journal_id: str) -> None:
        journal_dir = self.journals_dir / journal_id
        thumb_dir = self.thumbs_dir / journal_id
        if journal_dir.exists():
            shutil.rmtree(journal_dir)
        if thumb_dir.exists():
            shutil.rmtree(thumb_dir)

    def create_journal(self, title: str, owner: str, description: str, has_translation: bool) -> str:
        journal_id = journal_uuid()
        journal_dir = self.journals_dir / journal_id
        pages_dir = journal_dir / 'pages'
        pages_dir.mkdir(parents=True, exist_ok=True)
        meta = {
            'title': title,
            'owner': owner,
            'has_translation': bool(has_translation),
            'description': description,
            'cover_photo': '',
            'created': now_iso_date(),
            'last_modified': now_iso_date(),
            # Prompt tuning (advanced feature)
            'advanced_prompt_tuning_enabled': False,
            'ocr_settings': {
                'custom_instructions': '',
                'date_and_structure_hints': '',
            },
            'translation_settings': {
                'custom_instructions': '',
                'terminology_and_style_notes': '',
            },
            'mode': JOURNAL_MODE_EDITING,
        }
        save_yaml_only(journal_dir / 'journal.md', meta)
        write_people(journal_dir / 'people.json', [])
        return journal_id

    def get_journal(self, journal_id: str, include_pages: bool = True) -> dict[str, Any]:
        journal_dir = self.journals_dir / journal_id
        meta, _ = load_frontmatter(journal_dir / 'journal.md')
        people = read_people(journal_dir / 'people.json')

        if include_pages:
            pages = self.list_pages(journal_id)
            grouped_entries = {}
            for page in pages:
                for entry in page.get('entries', []) or []:
                    entry_date = (entry.get('entry_date') or '').strip()
                    if entry_date:
                        grouped_entries.setdefault(entry_date, []).append(page)
                        break
            cover_photo = meta.get('cover_photo', '')
            cover_thumb = None
            if cover_photo:
                cover_path = journal_dir / cover_photo
                if cover_path.exists():
                    cover_thumb = self.thumbnail_for(cover_path, journal_id, cover_photo)
            first_thumb = cover_thumb or (pages[0]['thumbnail_url'] if pages else None)
            page_count = len(pages)
        else:
            pages = []
            grouped_entries = {}
            # Light path: still compute cover thumbnail + trust cached page_count
            cover_photo = meta.get('cover_photo', '')
            cover_thumb = None
            if cover_photo:
                cover_path = journal_dir / cover_photo
                if cover_path.exists():
                    cover_thumb = self.thumbnail_for(cover_path, journal_id, cover_photo)
            first_thumb = cover_thumb
            stored_count = meta.get('page_count')
            if stored_count is not None and stored_count > 0:
                page_count = stored_count
            else:
                _, pages_dir = self.journal_paths(journal_id)
     