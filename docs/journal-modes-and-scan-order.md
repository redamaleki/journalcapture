# Journal modes and scan order

## Overview

Each journal has a **mode** that controls whether structure and media can change:

| Mode | Stored value | Purpose |
|------|----------------|---------|
| **Editing** | `editing` | Upload scans, fix upload order, edit entries, replace images, transcribe |
| **Complete** | `complete` | Browse and read; structure and images are locked |

Default for new journals: `editing`. Existing journals without a `mode` field are treated as `editing`.

Stored in `journal.md` frontmatter:

```yaml
mode: editing
```

## Scan order vs entry data

- **Scan order** is the sequence files were captured (`page-001`, `page-002`, … on disk).
- **Entry dates and text** live in page frontmatter (`entries[]`) and are not changed when scan order is fixed.
- Reordering scans renames page files to stay sequential and updates `page_number` to match position (1…N).

**Organize scan order** is a dedicated screen (not the main journal overview). Use it after upload when sheets were added out of order (e.g. scan 10 before scan 9).

## What each mode allows

### Editing

- Add pages (upload / camera)
- **Organize scan order** (drag thumbnails, save)
- Page editor: save entries, people, physical page number field
- Replace main page image; scrapbook add/remove
- Transcribe & translate (if enabled)
- Cover photo, rename journal, people manager (write), prompt tuning, delete page
- Mark journal **Complete**
- Backup

### Complete

- Journal overview (list, sort by scan or date)
- **Read journal** (primary UX; opens by default from dashboard and journal URL)
- Journal overview (`?overview=1`) for page grid, entry navigator, reopen, backup
- Entry navigator
- Backup
- **Reopen for editing** (restores editing mode)

Blocked in complete: add pages, organize scans, save page, image/scrapbook/cover changes, transcribe accept, delete page, rename journal (optional—currently blocked), people POST.

## Mode transitions

**Mark complete** — confirmation explains that add/reorder/images are disabled until reopen.

**Reopen for editing** — confirmation explains scan order and images can change again.

## UI surfaces

- Dashboard: mode badge per journal card
- Journal overview: mode badge; editing actions vs complete actions in sidebar
- Main overview: **list view only** (no drag-reorder strip); sort by scan order or entry date
- `/journals/<id>/organize-scans`: thumbnail strip + Save order / Cancel

## Future

- Separate **journal page #** (printed folio) from scan index, display-only, no file rename
