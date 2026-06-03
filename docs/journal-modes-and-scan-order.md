# Journal modes and scan order

## Overview

Journals support two modes stored in `journal.md` frontmatter:

- **editing** (default): full authoring — uploads, reorder, image replace, save, transcribe.
- **complete**: read-only for content; scan order can still be organized on a dedicated screen.

## Mode persistence

- Field: `mode: editing | complete` in journal metadata (`journal.md`).
- `JournalStore.normalize_journal_mode()` and `journal_is_editing()` enforce valid values.
- `set_journal_mode(journal_id, mode)` updates metadata.

## UI behavior

### Journal overview (`journal_view.html`)

- Mode toggle (editing ↔ complete) when allowed.
- In **complete** mode: hide/disable upload, drag-reorder, and destructive actions.
- Default sort: **scan order** (`page_number`), not drag order.
- Link to **Organize scan order** screen.

### Page editor (`page_editor.html`)

- In **complete** mode: fields read-only; no save/transcribe/upload.

### Organize scans

- Dedicated route/screen to reorder pages by scan order without entering full edit mode.

## Server guards (`views.py` + `storage.py`)

- POST routes for upload, reorder, save, transcribe, image replace check `journal_is_editing()`.
- Flash or 403-style feedback when blocked in complete mode.

## Sorting

- Overview list uses scan order by default.
- Date sort remains available via query param where implemented.

## Related files

- `journal_web/storage.py` — mode helpers, guards in mutating methods.
- `journal_web/views.py` — route guards, organize-scans view.
- `templates/journal_view.html`, `page_editor.html`, `dashboard.html`.
