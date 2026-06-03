# Journal modes and scan order

## Overview

Each journal has a **mode** that controls whether structure and media can change:

| Mode | Stored value | Purpose |
|------|----------------|---------|
| **Editing** | `editing` | Upload scans, fix upload order, edit entries, replace images, transcribe |
| **Complete** | `complete` | Browse and read; structure and images are locked |

Default for new journals: `editing`. Existing journals without a `mode` field are treated as `editing`.

Stored in `journal.md` frontmatter as `mode: editing` or `mode: complete`.

## Editing mode

- Upload new page images
- Organize scan order (dedicated screen)
- Edit transcriptions, translations, notes
- Replace page images, add scrapbook items
- Transcribe / translate via OpenRouter add-in
- Rename journal, delete pages, etc.

## Complete mode

- View journal overview and pages (read-only)
- Read-only page editor (no save, transcribe, or uploads)
- Organize scan order is **not** available in complete mode (reopen for editing first)
- Mode can be switched back to editing via "Reopen for editing"

## Scan order vs date sort

- **Default overview sort**: scan order (`page_number`)
- **Optional**: sort by entry date via `?sort=date`
- Drag-reorder on the overview was removed; use **Organize scan order** (`/journals/<id>/organize-scans`)

## Server-side guards

`journal_is_editing()` is checked on mutating routes and in `JournalStore` methods that change files.

## Key files

- `journal_web/storage.py` — mode constants, `set_journal_mode`, guards
- `journal_web/views.py` — `organize_scans`, `mark_journal_complete`, `reopen_journal_editing`, `redirect_if_not_editing`
- `templates/journal_view.html` — mode UI, sort, link to organize scans
- `templates/page_editor.html` — `read_only` when complete
- `templates/organize_scans.html` — reorder UI
