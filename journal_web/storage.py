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
                actual_count = len(list(pages_dir.glob('page-*.md'))) if pages_dir.exists() else 0
                page_count = actual_count
                self.save_journal_meta(journal_id, {'page_count': page_count})

        result = {
            'id': journal_id,
            'dir': journal_dir,
            **meta,
            'mode': normalize_journal_mode(meta),
            'is_editing': journal_is_editing(meta),
            'people': people,
            'grouped_entries': grouped_entries,
            'page_count': page_count,
            'thumbnail_url': first_thumb,
        }
        if include_pages:
            result['pages'] = pages
        return result

    def save_journal_meta(self, journal_id: str, data: dict[str, Any]) -> None:
        journal_dir = self.journals_dir / journal_id
        current, _ = load_frontmatter(journal_dir / 'journal.md')
        current.update(data)
        save_yaml_only(journal_dir / 'journal.md', update_last_modified(current))

    def set_journal_mode(self, journal_id: str, mode: str) -> None:
        if mode not in JOURNAL_MODES:
            raise ValueError(f'Invalid journal mode: {mode}')
        self.save_journal_meta(journal_id, {'mode': mode})

    def save_prompt_tuning(self, journal_id: str, enabled: bool, ocr_settings: dict, translation_settings: dict, prompt_tuning_description: str = "") -> None:
        """Save the advanced prompt tuning settings for a journal (additive only)."""
        data = {
            'advanced_prompt_tuning_enabled': bool(enabled),
            'ocr_settings': {
                'custom_instructions': (ocr_settings or {}).get('custom_instructions', '').strip(),
                'date_and_structure_hints': (ocr_settings or {}).get('date_and_structure_hints', '').strip(),
            },
            'translation_settings': {
                'custom_instructions': (translation_settings or {}).get('custom_instructions', '').strip(),
                'terminology_and_style_notes': (translation_settings or {}).get('terminology_and_style_notes', '').strip(),
            },
            'prompt_tuning_description': (prompt_tuning_description or '').strip(),
        }
        self.save_journal_meta(journal_id, data)

    def journal_paths(self, journal_id: str) -> tuple[Path, Path]:
        journal_dir = self.journals_dir / journal_id
        pages_dir = journal_dir / 'pages'
        pages_dir.mkdir(parents=True, exist_ok=True)
        return journal_dir, pages_dir

    def list_pages(self, journal_id: str) -> list[dict[str, Any]]:
        journal_meta = self.get_journal_meta(journal_id)
        _, pages_dir = self.journal_paths(journal_id)
        pages = []
        for page_md in sorted(pages_dir.glob('page-*.md'), key=sort_key_page_name):
            meta, body = load_frontmatter(page_md)
            pages.append(self._build_page_dict(journal_id, page_md.stem, meta, body, journal_meta))
        return pages

    def list_pages_basic(self, journal_id: str) -> list[dict[str, Any]]:
        _, pages_dir = self.journal_paths(journal_id)
        pages = []
        for page_md in sorted(pages_dir.glob('page-*.md'), key=sort_key_page_name):
            meta, _ = load_frontmatter(page_md)
            entries = meta.get('entries') or []
            if not entries:
                legacy_entry_date = meta.get('entry_date', '')
                if legacy_entry_date or meta.get('transcription') or meta.get('translation') or meta.get('notes'):
                    entries = [{
                        'entry_date': legacy_entry_date,
                        'transcription': meta.get('transcription', ''),
                        'translation': meta.get('translation', ''),
                        'notes': meta.get('notes', ''),
                    }]
            primary_entry = entries[0] if entries else {}
            # Generate thumbnail so the template can render images
            main_image = pages_dir / f'{page_md.stem}.jpg'
            if main_image.exists():
                thumb_url = self.thumbnail_for(main_image, journal_id, main_image.name)
            else:
                thumb_url = None

            pages.append({
                'slug': page_md.stem,
                'page_number': meta.get('page_number'),
                'entry_date': primary_entry.get('entry_date', meta.get('entry_date', '')),
                'entries': entries,
                'thumbnail_url': thumb_url,
                'first_line': first_line(primary_entry.get('transcription', '')),
            })
        return pages

    def get_journal_meta(self, journal_id: str) -> dict[str, Any]:
        journal_dir, _ = self.journal_paths(journal_id)
        meta, _ = load_frontmatter(journal_dir / 'journal.md')
        return meta

    def get_page(self, journal_id: str, page_slug: str) -> dict[str, Any]:
        journal_meta = self.get_journal_meta(journal_id)
        _, pages_dir = self.journal_paths(journal_id)
        page_md = pages_dir / f'{page_slug}.md'
        meta, body = load_frontmatter(page_md)
        return self._build_page_dict(journal_id, page_slug, meta, body, journal_meta)

    def _build_page_dict(self, journal_id: str, page_slug: str, meta: dict, body: str, journal_meta: dict) -> dict[str, Any]:
        _, pages_dir = self.journal_paths(journal_id)
        entries = meta.get('entries') or []
        if not entries:
            legacy_entry_date = meta.get('entry_date', '')
            if legacy_entry_date or meta.get('transcription') or meta.get('translation') or meta.get('notes'):
                entries = [{
                    'entry_date': legacy_entry_date,
                    'transcription': meta.get('transcription', ''),
                    'translation': meta.get('translation', ''),
                    'notes': meta.get('notes', ''),
                }]
        primary_entry = entries[0] if entries else {}
        main_image = pages_dir / f'{page_slug}.jpg'
        image_url = url_for_page_asset(journal_id, main_image.name) if main_image.exists() else None
        thumb_url = self.thumbnail_for(main_image, journal_id, main_image.name) if main_image.exists() else None
        scrapbook_urls = []
        for item in meta.get('scrapbook', []) or []:
            if item:
                scrapbook_urls.append(url_for_page_asset(journal_id, item))
        return {
            'slug': page_slug,
            'page_number': meta.get('page_number'),
            'entry_date': primary_entry.get('entry_date', meta.get('entry_date', '')),
            'entries': entries,
            'body': body,
            'image_url': image_url,
            'thumbnail_url': thumb_url,
            'scrapbook': meta.get('scrapbook', []),
            'scrapbook_urls': scrapbook_urls,
            'has_translation': bool(journal_meta.get('has_translation')),
        }

    def page_navigation(self, journal_id: str, page_slug: str) -> dict[str, Any]:
        pages = self.list_pages_basic(journal_id)
        slugs = [p['slug'] for p in pages]
        if page_slug not in slugs:
            return {'prev': None, 'next': None, 'index': -1, 'total': len(slugs)}
        idx = slugs.index(page_slug)
        prev_page = pages[idx - 1] if idx > 0 else None
        next_page = pages[idx + 1] if idx + 1 < len(pages) else None
        return {'prev': prev_page, 'next': next_page, 'index': idx, 'total': len(pages)}

    def thumbnail_for(self, image_path: Path, journal_id: str, filename: str) -> str:
        thumb_dir = self.thumbs_dir / journal_id
        thumb_dir.mkdir(parents=True, exist_ok=True)
        thumb_path = thumb_dir / filename
        if not thumb_path.exists() or thumb_path.stat().st_mtime < image_path.stat().st_mtime:
            make_thumbnail(image_path, thumb_path)
        return f'/thumbnails/{journal_id}/{filename}'

    def page_image_path(self, journal_id: str, page_slug: str) -> Path:
        _, pages_dir = self.journal_paths(journal_id)
        return pages_dir / f'{page_slug}.jpg'

    def rename_journal(self, journal_id: str, title: str, description: str = '') -> None:
        self.save_journal_meta(journal_id, {'title': title, 'description': description})

    def add_person(self, journal_id: str, name: str, relation: str = '', notes: str = '') -> None:
        journal_dir, _ = self.journal_paths(journal_id)
        people_path = journal_dir / 'people.json'
        ensure_people_file(people_path)
        people = read_people(people_path)
        people.append({'name': name, 'relation': relation, 'notes': notes})
        write_people(people_path, people)

    def save_cover_photo(self, journal_id: str, uploaded_file) -> None:
        journal_dir, _ = self.journal_paths(journal_id)
        cover_name = f'cover-{journal_uuid()}.jpg'
        dest = journal_dir / cover_name
        save_uploaded_image_as_jpeg(uploaded_file, dest)
        self.save_journal_meta(journal_id, {'cover_photo': cover_name})

    def create_pages_from_uploads(self, journal_id: str, files: list) -> tuple[list[str], list[str]]:
        if not journal_is_editing(self.get_journal_meta(journal_id)):
            return [], ['Journal is in complete mode; uploads are disabled.']
        _, pages_dir = self.journal_paths(journal_id)
        created = []
        errors = []
        existing = sorted(pages_dir.glob('page-*.md'), key=sort_key_page_name)
        next_num = 1
        if existing:
            last = existing[-1].stem
            try:
                next_num = int(last.split('-', 1)[1]) + 1
            except (IndexError, ValueError):
                next_num = len(existing) + 1
        for uploaded in files:
            try:
                slug = f'page-{next_num:04d}'
                page_md = pages_dir / f'{slug}.md'
                image_path = pages_dir / f'{slug}.jpg'
                save_uploaded_image_as_jpeg(uploaded, image_path)
                meta = {
                    'page_number': next_num,
                    'entries': [{'entry_date': '', 'transcription': '', 'translation': '', 'notes': ''}],
                    'scrapbook': [],
                }
                save_yaml_only(page_md, meta)
                created.append(slug)
                next_num += 1
            except Exception as exc:
                errors.append(f'{getattr(uploaded, "filename", "file")}: {exc}')
        if created:
            self._refresh_page_count(journal_id)
        return created, errors

    def reorder_pages(self, journal_id: str, ordered_slugs: list[str]) -> None:
        if not journal_is_editing(self.get_journal_meta(journal_id)):
            raise ValueError('Journal is in complete mode; reorder is disabled.')
        _, pages_dir = self.journal_paths(journal_id)
        for idx, slug in enumerate(ordered_slugs, start=1):
            page_md = pages_dir / f'{slug}.md'
            if not page_md.exists():
                continue
            meta, body = load_frontmatter(page_md)
            meta['page_number'] = idx
            save_frontmatter(page_md, meta, body)

    def save_page(self, journal_id: str, page_slug: str, form_data) -> tuple[list[str], str]:
        if not journal_is_editing(self.get_journal_meta(journal_id)):
            return ['Journal is in complete mode; saving is disabled.'], page_slug
        _, pages_dir = self.journal_paths(journal_id)
        page_md = pages_dir / f'{page_slug}.md'
        meta, body = load_frontmatter(page_md)
        errors = []
        entries = []
        dates = form_data.getlist('entry_date')
        transcriptions = form_data.getlist('entry_transcription')
        translations = form_data.getlist('entry_translation')
        notes_list = form_data.getlist('entry_notes')
        total = max(len(dates), len(transcriptions), len(translations), len(notes_list), 0)
        for idx in range(total):
            entry_date = dates[idx] if idx < len(dates) else ''
            if entry_date and not valid_date(entry_date):
                errors.append(f'Invalid date: {entry_date}')
            entries.append({
                'entry_date': entry_date,
                'transcription': transcriptions[idx] if idx < len(transcriptions) else '',
                'translation': translations[idx] if idx < len(translations) else '',
                'notes': notes_list[idx] if idx < len(notes_list) else '',
            })
        if errors:
            return errors, page_slug
        meta['entries'] = entries
        new_slug = form_data.get('page_slug', page_slug).strip() or page_slug
        if new_slug != page_slug:
            new_md = pages_dir / f'{new_slug}.md'
            new_img = pages_dir / f'{new_slug}.jpg'
            old_img = pages_dir / f'{page_slug}.jpg'
            if new_md.exists():
                return [f'Page {new_slug} already exists.'], page_slug
            page_md.rename(new_md)
            if old_img.exists():
                old_img.rename(new_img)
            page_md = new_md
            page_slug = new_slug
        save_frontmatter(page_md, meta, form_data.get('body', body))
        return [], page_slug

    def delete_page(self, journal_id: str, page_slug: str) -> None:
        if not journal_is_editing(self.get_journal_meta(journal_id)):
            raise ValueError('Journal is in complete mode; delete is disabled.')
        _, pages_dir = self.journal_paths(journal_id)
        for path in [pages_dir / f'{page_slug}.md', pages_dir / f'{page_slug}.jpg']:
            if path.exists():
                path.unlink()
        self._refresh_page_count(journal_id)

    def replace_page_image(self, journal_id: str, page_slug: str, uploaded_file) -> None:
        if not journal_is_editing(self.get_journal_meta(journal_id)):
            raise ValueError('Journal is in complete mode; image replace is disabled.')
        image_path = self.page_image_path(journal_id, page_slug)
        save_uploaded_image_as_jpeg(uploaded_file, image_path)

    def add_scrapbook_item(self, journal_id: str, page_slug: str, uploaded_file) -> None:
        if not journal_is_editing(self.get_journal_meta(journal_id)):
            raise ValueError('Journal is in complete mode; scrapbook uploads are disabled.')
        _, pages_dir = self.journal_paths(journal_id)
        page_md = pages_dir / f'{page_slug}.md'
        meta, body = load_frontmatter(page_md)
        scrap_name = f'{page_slug}-scrap-{journal_uuid()}.jpg'
        dest = pages_dir / scrap_name
        save_uploaded_image_as_jpeg(uploaded_file, dest)
        scrapbook = list(meta.get('scrapbook') or [])
        scrapbook.append(scrap_name)
        meta['scrapbook'] = scrapbook
        save_frontmatter(page_md, meta, body)

    def remove_scrapbook_item(self, journal_id: str, page_slug: str, filename: str) -> None:
        if not journal_is_editing(self.get_journal_meta(journal_id)):
            raise ValueError('Journal is in complete mode; scrapbook edits are disabled.')
        _, pages_dir = self.journal_paths(journal_id)
        page_md = pages_dir / f'{page_slug}.md'
        meta, body = load_frontmatter(page_md)
        scrapbook = [s for s in (meta.get('scrapbook') or []) if s != filename]
        meta['scrapbook'] = scrapbook
        save_frontmatter(page_md, meta, body)
        scrap_path = pages_dir / filename
        if scrap_path.exists():
            scrap_path.unlink()

    def apply_transcribed_entries(self, journal_id: str, page_slug: str, entries: list[dict], adjusted_image_bytes: bytes | None = None) -> None:
        if not journal_is_editing(self.get_journal_meta(journal_id)):
            raise ValueError('Journal is in complete mode; transcribe accept is disabled.')
        _, pages_dir = self.journal_paths(journal_id)
        page_md = pages_dir / f'{page_slug}.md'
        meta, body = load_frontmatter(page_md)
        meta['entries'] = entries
        save_frontmatter(page_md, meta, body)
        if adjusted_image_bytes:
            image_path = pages_dir / f'{page_slug}.jpg'
            image_path.write_bytes(adjusted_image_bytes)

    def _refresh_page_count(self, journal_id: str) -> None:
        _, pages_dir = self.journal_paths(journal_id)
        count = len(list(pages_dir.glob('page-*.md')))
        self.save_journal_meta(journal_id, {'page_count': count})

    def load_backup_config(self) -> dict[str, Any]:
        config_path = current_app.config['DATA_DIR'] / 'backup_config.json'
        if config_path.exists():
            return json.loads(config_path.read_text())
        return {'path': '', 'username': '', 'password': ''}

    def save_backup_config(self, data: dict[str, Any]) -> None:
        config_path = current_app.config['DATA_DIR'] / 'backup_config.json'
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps(data, indent=2))

    def backup_journal(self, journal_id: str) -> str:
        config = self.load_backup_config()
        if not config.get('path'):
            raise ValueError('Backup path is not configured.')
        src = self.journals_dir / journal_id
        if not src.exists():
            raise ValueError(f'Journal {journal_id} not found.')
        dest_root = Path(config['path'])
        dest_root.mkdir(parents=True, exist_ok=True)
        dest = dest_root / f'{journal_id}-{now_iso_date()}'
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src, dest)
        return str(dest)

    def backup_all(self) -> str:
        config = self.load_backup_config()
        if not config.get('path'):
            raise ValueError('Backup path is not configured.')
        dest_root = Path(config['path']) / f'all-journals-{now_iso_date()}'
        dest_root.mkdir(parents=True, exist_ok=True)
        for journal_dir in self.journals_dir.iterdir() if self.journals_dir.exists() else []:
            if journal_dir.is_dir():
                shutil.copytree(journal_dir, dest_root / journal_dir.name, dirs_exist_ok=True)
        return str(dest_root)


def url_for_page_asset(journal_id: str, filename: str) -> str:
    from flask import url_for
    return url_for('journal.page_asset', journal_id=journal_id, filename=filename)
