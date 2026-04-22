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

Defaults still support local workspace use if env vars are not set.

## Docker
Build:
```bash
docker build -t journalapp .
```

Run:
```bash
docker run -d \
  --name journalapp \
  -p 5000:5000 \
  -e JOURNAL_SECRET_KEY=change-me \
  -v /srv/journalcapture/data:/data \
  journalapp
```

Compose:
```bash
docker compose up -d --build
```

Recommended host-mounted storage:
- `/srv/journalcapture/data/journals`
- `/srv/journalcapture/data/.thumbnails`
- `/srv/journalcapture/data/config/backup_config.yml`

## HTTPS / trusted mobile browser access
For best mobile browser behavior, especially camera flows, serve the app behind HTTPS.

Recommended model:
- Journal App container on local Docker network
- TLS reverse proxy in front, such as Caddy, nginx, Traefik, or Nginx Proxy Manager

The app is proxy-aware and supports forwarded headers.

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
- See `journal-app-spec-phase1.md` for product behavior
- See `journal-app-spec-phase2-deployment.md` for Docker/deployment requirements
