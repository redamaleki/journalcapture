# Project: Journal Capture

A lightweight, local-first, visual journal digitization app for archiving family history.

## Purpose
The Journal Capture app provides a simple interface to digitize physical journals using a camera-first mobile workflow. It organizes page scans, transcriptions, translations, and scrapbook items into a portable, flat-file structure suitable for long-term archiving and manual organization.

## Key Design Principles
*   **Local & Portable**: Flat-file storage (Markdown + YAML + JSON); no database, no cloud, no AI dependencies.
*   **Visual-First**: Prioritizes thumbnail-based browsing and manual drag-and-drop page reordering.
*   **Mobile-Ready**: Designed for mobile browser access, including direct camera integration.
*   **Simple & Reliable**: Easy to back up, edit, and keep offline.

## Core Data Model
The application stores data in hierarchical folders:
*   `journals/{journal-id}/`: Metadata stored in `journal.md`.
*   `pages/`: Individual scans and metadata stored as `{page-slug}.md` and `{page-slug}.jpg`.
*   `entries[]`: The canonical structure for multiple-entry pages.
*   `scrapbook_items`: Additional images attached to pages.

## Specs & History
- **Phase 1 (Core)**: Established the flat-file structure, mobile-friendly UI, and drag-and-drop page management.
- **Phase 2 (Deployment)**: Introduced Docker-based deployment, host-mount storage patterns, and proxy-aware configuration for secure HTTPS usage.

*For archived specification documents, see `docs/archived_specs/`.*
