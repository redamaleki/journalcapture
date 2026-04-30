from __future__ import annotations

import json
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from flask import current_app

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
)


class JournalStore:
    def __init__(self):
        self.journals_dir: Path = current_app.config['JOURNALS_DIR']
        self.thumbs_dir: Path = current_app.config['THUMBS_DIR']

    def list_journals(self) -> list[dict[str, Any]]:
        journals = []
        for journal_dir in sorted(self.journals_dir.iterdir() if self.journals_dir.exists() else [], key=lambda p: p.name):
            if journal_dir.is_dir():
                journals.append(self.get_journal(journal_dir.name, include_pages=True))
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
        }
        save_yaml_only(journal_dir / 'journal.md', meta)
        write_people(journal_dir / 'people.json', [])
        return journal_id

    def get_journal(self, journal_id: str, include_pages: bool = True) -> dict[str, Any]:
        journal_dir = self.journals_dir / journal_id
        meta, _ = load_frontmatter(journal_dir / 'journal.md')
        people = read_people(journal_dir / 'people.json')
        pages = self.list_pages(journal_id) if include_pages else []
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
        complete_flags = 0
        total_flags = 0
        for page in pages:
            checks = ['transcription_complete', 'tagged_complete']
            if meta.get('has_translation'):
                checks.append('translation_complete')
            total_flags += len(checks)
            complete_flags += sum(1 for flag in checks if page.get(flag))
        progress = round((complete_flags / total_flags) * 100, 1) if total_flags else 0
        return {
            'id': journal_id,
            'dir': journal_dir,
            **meta,
            'people': people,
            'pages': pages,
            'grouped_entries': grouped_entries,
            'page_count': len(pages),
            'thumbnail_url': first_thumb,
            'progress_percent': progress,
        }

    def save_journal_meta(self, journal_id: str, data: dict[str, Any]) -> None:
        journal_dir = self.journals_dir / journal_id
        current, _ = load_frontmatter(journal_dir / 'journal.md')
        current.update(data)
        save_yaml_only(journal_dir / 'journal.md', update_last_modified(current))

    def journal_paths(self, journal_id: str) -> tuple[Path, Path]:
        journal_dir = self.journals_dir / journal_id
        pages_dir = journal_dir / 'pages'
        pages_dir.mkdir(parents=True, exist_ok=True)
        return journal_dir, pages_dir

    def list_pages(self, journal_id: str) -> list[dict[str, Any]]:
        journal = self.get_journal_meta(journal_id)
        _, pages_dir = self.journal_paths(journal_id)
        pages = []
        for page_md in sorted(pages_dir.glob('page-*.md'), key=sort_key_page_name):
            page = self.get_page(journal_id, page_md.stem)
            pages.append(page)
        return pages

    def get_journal_meta(self, journal_id: str) -> dict[str, Any]:
        journal_dir, _ = self.journal_paths(journal_id)
        meta, _ = load_frontmatter(journal_dir / 'journal.md')
        return meta

    def get_page(self, journal_id: str, page_slug: str) -> dict[str, Any]:
        journal_dir, pages_dir = self.journal_paths(journal_id)
        meta, body = load_frontmatter(pages_dir / f'{page_slug}.md')
        main_image = pages_dir / f'{page_slug}.jpg'
        scrapbooks = meta.get('scrapbook_items', []) or []
        if main_image.exists():
            thumb = self.thumbnail_for(main_image, journal_id, main_image.name)
            image_url = f'/journals/{journal_id}/assets/{main_image.name}'
        else:
            thumb = None
            image_url = None
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
        return {
            'slug': page_slug,
            'page_number': meta.get('page_number'),
            'entry_date': primary_entry.get('entry_date', meta.get('entry_date', '')),
            'entry_id': '',
            'transcription_complete': bool(meta.get('transcription_complete', False)),
            'translation_complete': bool(meta.get('translation_complete', False)),
            'tagged_complete': bool(meta.get('tagged_complete', False)),
            'people': meta.get('people', []) or [],
            'scrapbook_items': scrapbooks,
            'transcription': primary_entry.get('transcription', meta.get('transcription', '')),
            'translation': primary_entry.get('translation', meta.get('translation', '')),
            'notes': primary_entry.get('notes', meta.get('notes', '')),
            'entries': entries,
            'body': body,
            'thumbnail_url': thumb,
            'image_url': image_url,
            'first_line': first_line(meta.get('transcription', '')),
            'status_done': sum(1 for flag in ['transcription_complete', 'translation_complete', 'tagged_complete'] if meta.get(flag)),
            'journal_has_translation': bool(self.get_journal_meta(journal_id).get('has_translation')),
            'scrapbook_urls': [f'/journals/{journal_id}/assets/{name}' for name in scrapbooks],
        }

    def create_page_from_upload(self, journal_id: str, uploaded_file) -> str:
        _, pages_dir = self.journal_paths(journal_id)
        page_number = self.next_page_number(journal_id)
        page_slug = f'page-{page_number:03d}'
        image_path = pages_dir / f'{page_slug}.jpg'
        meta_path = pages_dir / f'{page_slug}.md'
        meta = {
            'page_number': page_number,
            'entry_date': '',
            'entry_id': '',
            'transcription_complete': False,
            'translation_complete': False,
            'tagged_complete': False,
            'people': [],
            'scrapbook_items': [],
            'transcription': '',
            'translation': '',
            'notes': '',
        }
        try:
            save_uploaded_image_as_jpeg(uploaded_file.stream, image_path)
            save_frontmatter(meta_path, meta)
            self.thumbnail_for(image_path, journal_id, image_path.name)
        except Exception:
            if image_path.exists():
                image_path.unlink()
            if meta_path.exists():
                meta_path.unlink()
            raise
        self.touch_journal(journal_id)
        return page_slug

    def next_page_number(self, journal_id: str) -> int:
        pages = self.list_pages(journal_id)
        if not pages:
            return 1
        return max(int(page['page_number'] or 0) for page in pages) + 1

    def save_page(self, journal_id: str, page_slug: str, form: dict[str, Any]) -> tuple[list[str], str]:
        _, pages_dir = self.journal_paths(journal_id)
        journal_meta = self.get_journal_meta(journal_id)
        page_path = pages_dir / f'{page_slug}.md'
        current, _ = load_frontmatter(page_path)
        errors = []
        entries = []
        entry_dates = form.getlist('entry_date')
        entry_transcriptions = form.getlist('entry_transcription')
        entry_translations = form.getlist('entry_translation')
        entry_notes = form.getlist('entry_notes')
        total_entries = max(len(entry_dates), len(entry_transcriptions), len(entry_translations), len(entry_notes), 1)
        for idx in range(total_entries):
            item = {
                'entry_date': entry_dates[idx].strip() if idx < len(entry_dates) else '',
                'transcription': entry_transcriptions[idx] if idx < len(entry_transcriptions) else '',
                'translation': entry_translations[idx] if idx < len(entry_translations) else '',
                'notes': entry_notes[idx] if idx < len(entry_notes) else '',
            }
            has_content = any([
                item['entry_date'],
                item['transcription'].strip(),
                item['translation'].strip(),
                item['notes'].strip(),
            ])
            if has_content:
                if not valid_date(item['entry_date']):
                    errors.append(f"Entry {idx + 1} date must be YYYY-MM-DD.")
                entries.append(item)
        try:
            new_page_number = int(form.get('page_number') or current.get('page_number') or 1)
        except ValueError:
            errors.append('Page number must be a number.')
            new_page_number = current.get('page_number') or 1
        new_slug = f'page-{new_page_number:03d}'
        if new_slug != page_slug and (pages_dir / f'{new_slug}.md').exists():
            errors.append(f'Page {new_page_number} already exists.')
        if errors:
            return errors, page_slug
        if not journal_meta.get('has_translation'):
            for item in entries:
                item['translation'] = ''
        primary = entries[0] if entries else {'entry_date': '', 'transcription': '', 'translation': '', 'notes': ''}
        current.update({
            'page_number': new_page_number,
            'entry_date': primary.get('entry_date', ''),
            'entry_id': '',
            'people': form.getlist('people'),
            'scrapbook_items': current.get('scrapbook_items', []),
            'transcription': primary.get('transcription', ''),
            'translation': primary.get('translation', ''),
            'notes': primary.get('notes', ''),
            'entries': entries,
        })
        if new_slug != page_slug:
            self.rename_page_assets(pages_dir, page_slug, new_slug, current)
            page_slug = new_slug
            page_path = pages_dir / f'{page_slug}.md'
        save_frontmatter(page_path, current)
        self.touch_journal(journal_id)
        return [], page_slug

    def rename_page_assets(self, pages_dir: Path, old_slug: str, new_slug: str, meta: dict[str, Any]) -> None:
        old_md = pages_dir / f'{old_slug}.md'
        old_img = pages_dir / f'{old_slug}.jpg'
        new_md = pages_dir / f'{new_slug}.md'
        new_img = pages_dir / f'{new_slug}.jpg'
        if old_img.exists():
            old_img.rename(new_img)
        new_items = []
        for idx, filename in enumerate(meta.get('scrapbook_items', []) or [], start=1):
            old_item = pages_dir / filename
            new_name = f'{new_slug}-scrapbook-{idx}.jpg'
            new_item = pages_dir / new_name
            if old_item.exists():
                old_item.rename(new_item)
            new_items.append(new_name)
        meta['scrapbook_items'] = new_items
        if old_md.exists():
            old_md.rename(new_md)

    def delete_page(self, journal_id: str, page_slug: str) -> None:
        _, pages_dir = self.journal_paths(journal_id)
        meta, _ = load_frontmatter(pages_dir / f'{page_slug}.md')
        for scrapbook in meta.get('scrapbook_items', []) or []:
            item = pages_dir / scrapbook
            if item.exists():
                item.unlink()
            thumb = self.thumbs_dir / journal_id / scrapbook
            if thumb.exists():
                thumb.unlink()
        for filename in [f'{page_slug}.md', f'{page_slug}.jpg']:
            target = pages_dir / filename
            if target.exists():
                target.unlink()
            thumb = self.thumbs_dir / journal_id / filename
            if thumb.exists():
                thumb.unlink()
        self.touch_journal(journal_id)

    def page_navigation(self, journal_id: str, page_slug: str) -> dict[str, Any]:
        pages = self.list_pages(journal_id)
        slugs = [p['slug'] for p in pages]
        if page_slug not in slugs:
            return {'prev': None, 'next': None, 'is_last': True, 'suggested_entry_date': date.today().isoformat()}
        idx = slugs.index(page_slug)
        prev_page = pages[idx - 1] if idx > 0 else None
        suggested_entry_date = self.default_new_entry_date(journal_id, page_slug)
        return {
            'prev': prev_page,
            'next': pages[idx + 1] if idx < len(pages) - 1 else None,
            'is_last': idx == len(pages) - 1,
            'suggested_entry_date': suggested_entry_date,
        }

    def default_new_entry_date(self, journal_id: str, page_slug: str) -> str:
        pages = self.list_pages(journal_id)
        slugs = [p['slug'] for p in pages]
        if page_slug not in slugs:
            return date.today().isoformat()
        idx = slugs.index(page_slug)
        if idx == 0:
            return date.today().isoformat()
        prev_page = pages[idx - 1]
        prev_entries = prev_page.get('entries') or []
        for entry in reversed(prev_entries):
            entry_date = (entry.get('entry_date') or '').strip()
            if entry_date and valid_date(entry_date):
                return entry_date
        prev_entry_date = (prev_page.get('entry_date') or '').strip()
        if prev_entry_date and valid_date(prev_entry_date):
            return prev_entry_date
        return date.today().isoformat()

    def reorder_pages(self, journal_id: str, ordered_slugs: list[str]) -> None:
        _, pages_dir = self.journal_paths(journal_id)
        existing_pages = self.list_pages(journal_id)
        existing_slugs = [page['slug'] for page in existing_pages]
        if sorted(existing_slugs) != sorted(ordered_slugs):
            raise ValueError('Reorder request did not match current pages.')

        temp_pairs: list[tuple[str, str]] = []
        for index, old_slug in enumerate(ordered_slugs, start=1):
            temp_slug = f'__reorder_tmp_{index:03d}__'
            self.rename_page_family(journal_id, pages_dir, old_slug, temp_slug)
            temp_pairs.append((temp_slug, f'page-{index:03d}'))

        for temp_slug, final_slug in temp_pairs:
            self.rename_page_family(journal_id, pages_dir, temp_slug, final_slug)

        self.touch_journal(journal_id)

    def rename_page_family(self, journal_id: str, pages_dir: Path, old_slug: str, new_slug: str) -> None:
        old_md = pages_dir / f'{old_slug}.md'
        if not old_md.exists():
            return
        meta, body = load_frontmatter(old_md)
        old_img = pages_dir / f'{old_slug}.jpg'
        new_md = pages_dir / f'{new_slug}.md'
        new_img = pages_dir / f'{new_slug}.jpg'
        if old_img.exists():
            old_img.rename(new_img)
        new_items = []
        for idx, filename in enumerate(meta.get('scrapbook_items', []) or [], start=1):
            old_item = pages_dir / filename
            new_name = f'{new_slug}-scrapbook-{idx}.jpg'
            new_item = pages_dir / new_name
            if old_item.exists():
                old_item.rename(new_item)
            thumb_old = self.thumbs_dir / journal_id / filename
            thumb_new = self.thumbs_dir / journal_id / new_name
            if thumb_old.exists():
                thumb_old.rename(thumb_new)
            new_items.append(new_name)
        meta['scrapbook_items'] = new_items
        thumb_old_main = self.thumbs_dir / journal_id / f'{old_slug}.jpg'
        thumb_new_main = self.thumbs_dir / journal_id / f'{new_slug}.jpg'
        if thumb_old_main.exists():
            thumb_old_main.rename(thumb_new_main)
        if new_slug.startswith('page-'):
            meta['page_number'] = int(new_slug.split('-')[-1])
        save_frontmatter(new_md, meta, body)
        old_md.unlink()

    def add_scrapbook_item(self, journal_id: str, page_slug: str, uploaded_file) -> None:
        _, pages_dir = self.journal_paths(journal_id)
        meta, _ = load_frontmatter(pages_dir / f'{page_slug}.md')
        items = meta.get('scrapbook_items', []) or []
        next_idx = len(items) + 1
        filename = f'{page_slug}-scrapbook-{next_idx}.jpg'
        path = pages_dir / filename
        save_uploaded_image_as_jpeg(uploaded_file.stream, path)
        items.append(filename)
        meta['scrapbook_items'] = items
        save_frontmatter(pages_dir / f'{page_slug}.md', meta)
        self.thumbnail_for(path, journal_id, filename)
        self.touch_journal(journal_id)

    def remove_scrapbook_item(self, journal_id: str, page_slug: str, filename: str) -> None:
        _, pages_dir = self.journal_paths(journal_id)
        meta, _ = load_frontmatter(pages_dir / f'{page_slug}.md')
        items = meta.get('scrapbook_items', []) or []
        if filename in items:
            items.remove(filename)
        meta['scrapbook_items'] = items
        save_frontmatter(pages_dir / f'{page_slug}.md', meta)
        target = pages_dir / filename
        if target.exists():
            target.unlink()
        thumb = self.thumbs_dir / journal_id / filename
        if thumb.exists():
            thumb.unlink()
        self.touch_journal(journal_id)

    def thumbnail_for(self, image_path: Path, journal_id: str, image_name: str) -> str:
        thumb_path = self.thumbs_dir / journal_id / image_name
        if (not thumb_path.exists()) or image_path.stat().st_mtime > thumb_path.stat().st_mtime:
            make_thumbnail(image_path, thumb_path)
        return f'/thumbnails/{journal_id}/{image_name}'

    def save_cover_photo(self, journal_id: str, uploaded_file) -> None:
        journal_dir, _ = self.journal_paths(journal_id)
        filename = 'cover.jpg'
        cover_path = journal_dir / filename
        save_uploaded_image_as_jpeg(uploaded_file.stream, cover_path)
        meta = self.get_journal_meta(journal_id)
        meta['cover_photo'] = filename
        save_yaml_only(journal_dir / 'journal.md', update_last_modified(meta))
        self.thumbnail_for(cover_path, journal_id, filename)

    def replace_page_image(self, journal_id: str, page_slug: str, uploaded_file) -> None:
        _, pages_dir = self.journal_paths(journal_id)
        image_path = pages_dir / f'{page_slug}.jpg'
        save_uploaded_image_as_jpeg(uploaded_file.stream, image_path)
        self.thumbnail_for(image_path, journal_id, image_path.name)
        self.touch_journal(journal_id)

    def add_person(self, journal_id: str, name: str, relation: str, notes: str) -> None:
        journal_dir, _ = self.journal_paths(journal_id)
        people_path = journal_dir / 'people.json'
        people = read_people(people_path)
        if not any(p['name'] == name for p in people):
            people.append({'name': name, 'relation': relation, 'notes': notes})
        write_people(people_path, sorted(people, key=lambda p: p['name'].lower()))
        self.touch_journal(journal_id)

    def save_backup_config(self, config: dict[str, Any]) -> None:
        import yaml
        path = current_app.config['BACKUP_CONFIG_PATH']
        path.write_text(yaml.safe_dump(config, sort_keys=False), encoding='utf-8')

    def load_backup_config(self) -> dict[str, Any]:
        import yaml
        path = current_app.config['BACKUP_CONFIG_PATH']
        if not path.exists():
            return {'path': '', 'username': '', 'password': ''}
        return yaml.safe_load(path.read_text(encoding='utf-8')) or {'path': '', 'username': '', 'password': ''}

    def backup_journal(self, journal_id: str) -> str:
        config = self.load_backup_config()
        target_root = config.get('path', '').strip()
        if not target_root:
            raise ValueError('Backup path is not configured.')
        src = self.journals_dir / journal_id
        dst = Path(target_root) / journal_id
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        return str(dst)

    def backup_all(self) -> str:
        config = self.load_backup_config()
        target_root = config.get('path', '').strip()
        if not target_root:
            raise ValueError('Backup path is not configured.')
        root = Path(target_root)
        root.mkdir(parents=True, exist_ok=True)
        for journal in self.list_journals():
            self.backup_journal(journal['id'])
        return str(root)

    def rename_journal(self, journal_id: str, new_title: str, new_description: str) -> None:
        journal_dir = self.journals_dir / journal_id
        meta, _ = load_frontmatter(journal_dir / 'journal.md')
        meta['title'] = new_title.strip()
        meta['description'] = new_description.strip()
        save_yaml_only(journal_dir / 'journal.md', update_last_modified(meta))

    def touch_journal(self, journal_id: str) -> None:
        journal_dir, _ = self.journal_paths(journal_id)
        meta, _ = load_frontmatter(journal_dir / 'journal.md')
        save_yaml_only(journal_dir / 'journal.md', update_last_modified(meta))
