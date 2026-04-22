# Journal Digitization Web App - Phase 1 Specification (Updated)

## Important Constraints
- Phase 1 only: purely manual, local-first, no AI features, no OCR, no transcription/translation inside the app.
- Storage must be 100% flat files (Markdown + YAML frontmatter plus a per-journal `people.json`). NO database.
- The app must be simple, lightweight, and easy to run locally on a LAN.
- Future Docker packaging and an optional later AI analysis step must be possible without changing the data format or folder structure.
- UX improvements are allowed, but Phase 1 should not add new product features outside manual journal organization and editing.
- No new YAML fields should be introduced for page ordering or view state.

## Folder Structure (Per Journal)
/data/journals/{journal-uuid}/
├── journal.md
├── people.json
├── cover.jpg                     # Optional journal cover image
└── pages/
    ├── page-001.jpg
    ├── page-001-scrapbook-1.jpg
    ├── page-001-scrapbook-2.jpg
    ├── page-001.md
    ├── page-002.jpg
    └── ...

## Journal File (journal.md)
YAML frontmatter only:

---
title: "Mom's 1978 Journal"
owner: "Mom"
has_translation: true
description: "Summer travels and family notes"
cover_photo: "cover.jpg"         # optional
created: "2026-04-01"
last_modified: "2026-04-18"
---

## Page File (pages/page-XXX.md)
YAML frontmatter + optional body for extra notes.

The app supports multiple dated entries on a single scanned page.
Legacy single-entry fields still exist for backward compatibility, but `entries` is the canonical structure going forward.

---
page_number: 35                   # optional/display-only physical page number
entry_date: "1978-06-15"         # legacy compatibility mirror of first entry
entry_id: ""                     # retained only for compatibility, not used logically
people:
  - "Mom"
  - "Dad"
scrapbook_items:
  - "page-035-scrapbook-1.jpg"
  - "page-035-scrapbook-2.jpg"
transcription: |
  [Legacy mirror of first entry transcription]
translation: |
  [Legacy mirror of first entry translation]
notes: |
  [Legacy mirror of first entry notes]
entries:
  - entry_date: "1978-06-15"
    transcription: |
      [Paste first entry transcription here]
    translation: |
      [Paste first entry translation here]
    notes: |
      Notes for first entry
  - entry_date: "1978-06-16"
    transcription: |
      [Paste second entry transcription here]
    translation: |
      [Paste second entry translation here]
    notes: |
      Notes for second entry
---

## People File (people.json)
Simple JSON array:

[
  {"name": "Mom", "relation": "mother", "notes": "Born 1945"},
  {"name": "Dad", "relation": "father", "notes": ""}
]

## Core Data Rules
- Journal storage remains flat-file only.
- Each page belongs to one markdown file and one main image file.
- Scrapbook items are additional image files tied to that page.
- People tags are stored at the page level.
- `entries` is the source of truth for multiple entry blocks on a page.
- The first entry is mirrored back into top-level legacy fields for compatibility with older page files and older UI assumptions.
- Separate entry IDs are no longer part of the active product design.
- Grouping across pages is date-based only.
- Physical scan order is represented by current file naming order (`page-001`, `page-002`, etc.), not by any extra sequence field.
- Reordering pages must never modify, merge, split, or reinterpret any `entries[]` data.

## Key Features

### Journals
- Create and delete journals.
- Journals may have an optional cover image.
- Dashboard and journal view prefer the cover image when present, otherwise they fall back to page thumbnails.
- Cover updates should be compact and mobile-friendly, including `capture="environment"` as a hint where supported.

### Pages
- Upload page images into an existing journal.
- Each upload creates a new page at the end of the current scan order.
- Pages can be visually reordered.
- Reordering automatically renames page markdown files, main image files, and scrapbook image filenames so file numbering remains sequential.
- Pages can be deleted, including all related assets and thumbnails.
- Physical page number is optional and display-only. It is not the source of page order.

### Scrapbook Items
- Support multiple scrapbook items per page.
- Files named `page-XXX-scrapbook-1.jpg`, `page-XXX-scrapbook-2.jpg`, etc.
- Page editor shows scrapbook items in a horizontal scrollable row.
- Scrapbook items can be added and removed individually.
- Reordering pages must keep scrapbook assets attached to the correct page while renaming filenames consistently.

### Date Handling and Multiple Entries
- A page may contain one or more dated entries.
- Each entry has its own `entry_date`.
- Same day on multiple pages = same grouped date.
- Multiple days on one scanned page = multiple entry blocks on that page.
- The page editor offers a helper to use the next day after the previous page's date.
- When adding a new entry block, default its date to the last entry date from the previous page in scan order, or today's date if this is the first page.
- Blank extra entries should not be created on save or refresh.

### People Management
- Each journal has its own reusable people list in `people.json`.
- People can be added from a dedicated journal-specific Manage People screen.
- Page editor links to Manage People rather than pretending it exists inside the page screen.
- Page editor only selects from the existing journal people list.

## User Interface (Phone-friendly)

### 1. Dashboard
- Show journals as cards with cover image or first page thumbnail, title, owner, page count, translation flag, and last modified date.
- Do not show progress percentages.
- "Add Journal" opens the creation form on demand instead of keeping it always visible.

### 2. Journal View
Primary journal browsing mode:
- The primary view is visual-first.
- Show pages as a horizontal scrollable strip on narrow screens, or a responsive thumbnail grid on wider screens.
- This visual index represents the exact scan and saved order.
- Large page thumbnails are the primary affordance for browsing and reordering.

Reordering:
- Add drag-and-drop reordering to the visual thumbnail strip/grid.
- Use lightweight client behavior such as SortableJS plus HTMX or equivalent simple request handling.
- When reorder is committed, the backend must rename files consistently to maintain sequential filenames.
- Reordering only changes physical sequence and filenames.
- Reordering must never alter the contents of `entries[]`, dates, people tags, scrapbook content membership, or other page metadata semantics.
- Date grouping in Journal View continues to derive only from `entry_date` values.

Secondary journal browsing mode:
- Keep the existing metadata-rich card/list view as an optional toggle named "List View".

Desktop / larger screens:
- Use a split layout.
- Left column is about one-third width and contains journal cover, title, metadata, and actions.
- Right column is about two-thirds width and contains the page browsing UI.
- On wider screens, the primary visual view may render as a dense responsive grid.

Mobile / smaller screens:
- Show a compact sticky journal summary above the page list.
- The journal summary includes title, owner, page count, cover image, and key actions like Add Pages and People.
- Once the user scrolls, the sticky journal summary should shrink significantly so it does not consume too much vertical space.
- The global app header should also compress on scroll.
- The goal is to keep the visual page strip in focus while preserving quick access to journal actions.

Journal view behavior:
- Page thumbnails should reflect scan order exactly.
- Add Pages opens in a modal, not as a bottom-page hidden form.
- Grouped Entries section groups pages by date when relevant.
- Journal-level actions include Manage People, Add Pages, Settings, Backup This Journal, Delete Journal, and compact cover-photo update.
- Do not show progress percentages.
- Do not require any separate order field or sequence index in stored data.

### 3. Page Editor
- Large main image for the scanned page.
- Main page controls live in the same sticky top app bar as Dashboard and Settings when editing a page.
- Sticky page controls include page context plus Save, Prev, Next, Back, and Add Page when on the last page.
- Main image remains easy to inspect on phone.
- Scrapbook items are shown in a clean horizontal scroll row.
- People tagging is kept in a separate compact section.
- Delete Page remains at the bottom.
- Unsaved changes warning appears before leaving the page.

Entry editing behavior:
- Multiple entries per page should feel lightweight, not overwhelming.
- The first entry is open by default.
- Additional entries are easy to add and remove.
- Entry blocks are visually compact and can collapse their detailed fields.
- Each entry block includes date, transcription, optional translation, and comments.
- Translation appears before transcription when translation is enabled.
- Physical page number should be labeled `Physical page number (optional)`.
- Physical page number is display-only and should not be required to preserve sequence.
- Keep backward compatibility for old single-entry pages.

### 4. Upload Flow
- Journal creation is separate from page upload.
- Page uploads happen from within a journal.
- On journal view, Add Pages opens a modal uploader.
- The uploader should support both normal file selection and a camera-friendly `Take Photo` input using `accept="image/*"` and `capture="environment"` where supported.
- On the last page in page editor, Add Page should route the user back into that journal upload flow.
- New pages start empty and editable.

### 5. Backup
- Settings page for one-time SMB share configuration (path, username, password).
- One-click Backup This Journal or Backup All Journals copies the entire journal folder.
- Current implementation assumes the SMB target path is already mounted or otherwise locally reachable.

### 6. Deletion
- Delete Page removes the page markdown, main image, scrapbook images, and thumbnails.
- Delete Journal removes the journal folder and thumbnails.

## UX Rules for Phase 1
- Prioritize smooth daily use over feature count.
- Prefer compact actions, modals, and on-demand forms over large always-open forms.
- Prefer mobile-first spacing and touch targets.
- Use lightweight JavaScript and HTMX-style partial behavior where helpful, but do not increase complexity beyond what a simple Flask app needs.
- Avoid full-page friction when a smaller interaction will do.
- Keep the interface understandable for non-technical family archiving work.
- Treat the visual page index as the primary organizing surface.

## Technical Requirements
- Use Python + Flask.
- Flat files only, no database.
- HTMX is optional. Standard Flask forms plus lightweight JavaScript are acceptable.
- Handle YAML with PyYAML.
- Generate thumbnails for fast loading.
- All data and images stored under a configurable `/data` directory.
- Run on a single port (default 5000).
- No external AI or cloud dependency.
- Make sure the entire journal folder is self-contained and portable.
- App should be able to run as a user systemd service for persistence on the local machine.

## Current Implementation Notes
- The live app is managed with a user systemd service: `journal-app.service`.
- The current implementation includes backward compatibility for older single-entry page files.
- Old progress-tracking checkbox concepts are no longer a meaningful part of the visible product UX and should not drive Phase 1 UI decisions.
- Separate entry IDs are deprecated in practice and should not be reintroduced into the UI.
