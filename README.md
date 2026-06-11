# Journal App

Local-first journal digitization web app built with Flask, using flat files only.

## Features
- Flat-file journal storage only (`journal.md`, `people.json`, `pages/page-XXX.md`, images)
- Visual-first journal browsing
- Multi-entry page editing
- Journal-specific people management
- Scrapbook image upload/remove per page
- Camera-friendly page upload on supported mobile browsers
- Thumbnail generation
- Backup settings and one-click journal/all backup to a mounted share path
- Docker-ready deployment with host-mounted storage support
- Optional OpenRouter-powered Transcribe and Translate add-in with review/accept workflow

## Local development
```bash
cd /home/geo/.openclaw/workspace/journalapp
source venv/bin/activate
python app.py
```

Then open:
- <http://127.0.0.1:5000>
- or from LAN, use the host IP on port 5000

## Configuration
Environment variables supported:
- `JOURNAL_DATA_DIR`
- `JOURNAL_JOURNALS_DIR`
- `JOURNAL_THUMBS_DIR`
- `JOURNAL_BACKUP_CONFIG_PATH`
- `JOURNAL_SECRET_KEY`
- `JOURNAL_HOST`
- `JOURNAL_PORT`
- `JOURNAL_DEBUG`
- `TRANSCRIBE_TRANSLATE_ENABLED`
- `OPENROUTER_API_KEY`
- `OPENROUTER_OCR_MODEL`
- `OPENROUTER_TRANSLATION_MODEL`
- `OPENROUTER_MODEL` (legacy alias for OCR)
- `OPENROUTER_REASONING_MAX_TOKENS`
- `OPENROUTER_IMAGE_MODEL`
- `OPENROUTER_APP_NAME`
- `OPENROUTER_SITE_URL`

Defaults still support local workspace use if env vars are not set.

## Optional Transcribe and Translate add-in

When enabled, page editor screens show a **Transcribe and Translate** button below the page image. The app now uses a two-step OpenRouter flow:

- OCR step: sends the original page image to the configured OCR model and returns only `date_text` plus verbatim `transcription`.
- Translation step: sends the OCR JSON plus previous-entry date/year context to the configured translation model and returns keyed enrichment with `translation`, `normalized_date`, and `review_notes`.

The app merges those two steps server-side, presents the combined entries for review/edit, and saves them only after the user accepts.

If `OPENROUTER_IMAGE_MODEL` is configured and the checkbox is enabled, the app also creates a de-skewed/cropped review image after transcription. That image is not used for transcription. On the review screen the user can optionally replace the stored page image with the adjusted image.

For Docker, set these under `environment:` in `docker-compose.yml` (placeholders are already there—edit `OPENROUTER_API_KEY` and models as needed).

Notes:
- `OPENROUTER_MODEL` remains accepted as a legacy alias for OCR, but new deploys should set `OPENROUTER_OCR_MODEL` explicitly.
- `OPENROUTER_REASONING_MAX_TOKENS` applies to the translation/enrichment step, not OCR.
- The review screen still exposes raw request/response details for both OCR and translation.

## Docker Deployment (Recommended)

This is the primary and recommended way to run Journal Capture. **All configuration lives in `docker-compose.yml`**—no `.env` file is required.

#### Using Docker Compose

1. Clone the repository:
   ```bash
   git clone https://github.com/redamaleki/journalcapture.git
   cd journalcapture
   ```

2. **Configure the application**

   Edit `docker-compose.yml` on the host before first start:

   - Set `JOURNAL_SECRET_KEY` to a long random string (required for production).
   - Confirm the `volumes` path points at your persistent data directory (default `/srv/journalcapture/data`).
   - If you use Transcribe & Translate, set `OPENROUTER_API_KEY` and adjust model names under `environment:`.
   - To disable AI features, set `TRANSCRIBE_TRANSLATE_ENABLED: "false"` or leave `OPENROUTER_API_KEY` empty.

   Compose injects the `environment:` block into the container. The app does not need a separate `.env` file for Docker.

3. Create the data directory (if using the default volume path):
   ```bash
   sudo mkdir -p /srv/journalcapture/data
   ```

4. Start the application:
   ```bash
   docker compose up -d --build
   ```

The app will be available on the port defined in `docker-compose.yml` (default is port 5000).

#### Changing the Port

The port mapping is defined in `docker-compose.yml`. To change the port the app is exposed on, edit the `ports` section:

```yaml
ports:
  - "5000:5000"   # Change the left number to use a different port on the host
```

For example, to run on port 8080 instead:
```yaml
ports:
  - "8080:5000"
```

After changing the port, restart the container:
```bash
docker compose up -d
```

#### Recommended Volume Mount (Persistent Storage)

For production use, it is strongly recommended to mount a host directory so your journal data survives container restarts and updates.

In `docker-compose.yml`, use a volume mount like this:

```yaml
volumes:
  - /srv/journalcapture/data:/data
```

Create the directory on the host first:
```bash
sudo mkdir -p /srv/journalcapture/data
```

The following subdirectories will be created inside the mounted volume:

- `/srv/journalcapture/data/journals` — Your journal data and pages
- `/srv/journalcapture/data/.thumbnails` — Generated thumbnails
- `/srv/journalcapture/data/config/backup_config.yml` — Backup settings

#### Configuration

For Docker, set environment variables in the `environment:` section of `docker-compose.yml`. That file is the single source of truth for production.

Key variables: `JOURNAL_SECRET_KEY`, volume-related `JOURNAL_*_DIR` paths, `TRANSCRIBE_TRANSLATE_ENABLED`, and the `OPENROUTER_*` variables when using AI transcription.

For **local development** with `python app.py`, you can optionally copy `.env.example` to `.env` instead of exporting variables in your shell. Docker deployments do not need `.env`.

## HTTPS / trusted mobile browser access
For best mobile browser behavior, especially camera flows, serve the app behind HTTPS.

Recommended model:
- Journal App container on local Docker network
- TLS reverse proxy in front, such as Caddy, nginx, Traefik, or Nginx Proxy Manager

The app is proxy-aware and supports forwarded headers.

## Exporting a static reader for sharing

You can turn any journal (or a small subset of its pages) into a fully static, self-contained website for easy sharing. The exported site includes the beautiful read-only reader UI (translation/original toggle, progress tracking with localStorage, lightbox for main scans + scrapbook attachments, keyboard nav, etc.) and only the images + parsed text you choose. No server, no Python, no database — just `index.html` + a `media/` folder next to it.

The exporter reuses the exact same flat-file parser and entry model as the live app (including legacy single-entry pages and multi-entry pages).

### Basic usage (recommended: inside the project venv)

```bash
cd /path/to/journalapp
source venv/bin/activate

# Export a small subset by physical page number
python export_static.py \
  --journal-id 6cd68ae1-1cb7-4f0a-a7fa-6ac270c5a855 \
  --pages "1-4,7" \
  --out-dir ~/Public/my-journal-excerpt

# Or point directly at a copied/backed-up journal directory (great when you just have the files)
python export_static.py \
  --journal-dir /path/to/some/journal-uuid-dir \
  --pages "all" \
  --include-cover \
  --include-raw-md \
  --out-dir ./journal-share-2026-06
```

- `--pages` accepts ranges and lists: `1-5,12,20-22`. Page numbers are the physical `page_number` values (or the numeric part of the slug).
- Use `--all` (or `--pages all`) to export everything — be careful with 100+ page journals.
- `--include-cover` and `--include-raw-md` are optional.
- Output is a relocatable folder. Zip it, rsync it, drop it on Netlify/GitHub Pages, put it on a USB, email it, etc.
- Open `index.html` directly (file:// works) or serve the folder with any static server.

After export you will see:
- `index.html` — the complete reader
- `media/` — only the page scans and scrapbook images referenced by the chosen pages (+ cover if requested)
- `icons/` — full favicon set, apple-touch-icon, android icons, logo.svg, customized site.webmanifest (journal title + matching theme color) and browserconfig. The share is now a proper bookmarkable / add-to-home-screen PWA.
- `data.json` — machine-readable parsed entries (for further processing or auditing)
- `raw/` (only if `--include-raw-md`) — the original `.md` sidecars for the subset
- `README.txt` — human instructions for the recipient

The live Journal App itself also ships with the same professional icon set (dashboard, editors, and the in-app Read Journal view all get proper favicons + manifest).

Preview locally right after export:
```bash
python export_static.py ... --serve
# or manually:
cd <out-dir> && python -m http.server 0
```

### Requirements for the exporter
Run it from the journalapp directory using the project's Python environment (the same venv you use for `python app.py`). It needs the packages already listed in `requirements.txt` (Flask brings in Jinja2 transitively; PyYAML and Pillow are used for loading). If you run it in a minimal environment:

```bash
pip install -r requirements.txt jinja2
```

The *generated static site* has **zero** runtime dependencies — pure HTML + CSS + JS + images.

## Run as a user service
```bash
systemctl --user daemon-reload
systemctl --user enable --now journal-app.service
systemctl --user status journal-app.service
```

## Notes
- Journal data can live outside the app folder via env config
- Backups copy journal folders to the configured path
- Backup config path is configurable
- See `docs/journal-modes-and-scan-order.md` for editing vs complete modes and scan order
- See `docs/archived_specs/journal-app-spec-phase1.md` for product behavior
- See `docs/archived_specs/journal-app-spec-phase2-deployment.md` for Docker/deployment requirements
