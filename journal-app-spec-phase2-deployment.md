# Journal App - Phase 2 Deployment Specification

## Goal
Make Journal App deployable as a Docker container while preserving the Phase 1 flat-file data model and journal editing behavior.

Phase 2 is about deployment, configuration, portability, and trusted browser access. It does not redesign the journal data model.

## Non-Negotiables
- Keep storage 100% flat-file.
- No database.
- No cloud requirement.
- No AI requirement.
- No format change for journals, pages, scrapbook items, or people files.
- Docker deployment must work with host-mounted storage so the journal files and images remain directly accessible on the Docker host.

## Deployment Targets
- Local machine via Docker
- Home server / NAS / VPS via Docker
- Reverse proxy deployments behind HTTPS

## Containerization Requirements

### Docker Image
Provide:
- `Dockerfile`
- `.dockerignore`
- optional `docker-compose.yml` example

The image should:
- run the Flask app in a production-friendly way
- expose a configurable port
- avoid baking journal data into the image
- store application code separately from persistent data

### Host-Mounted Persistent Storage
The app must support environment-based configuration for storage paths.

At minimum support env vars for:
- `JOURNAL_DATA_DIR` - root data directory
- `JOURNAL_JOURNALS_DIR` - journal storage directory override
- `JOURNAL_THUMBS_DIR` - thumbnail directory override
- `JOURNAL_BACKUP_CONFIG_PATH` - backup config file location
- `JOURNAL_SECRET_KEY` - secret key override
- `JOURNAL_HOST`
- `JOURNAL_PORT`
- `JOURNAL_DEBUG`

Expected deployment pattern:
- container mounts host directory such as `/srv/journalcapture/data`
- app reads/writes journal data there
- files remain visible and editable from host backups/scripts if needed

### Trusted Mobile Browser Access
To be trusted by mobile browsers, deployment should support HTTPS-capable hosting.

Phase 2 requirements:
- App must work correctly behind a reverse proxy.
- Support proxy-aware behavior using standard forwarded headers.
- Document recommended deployment behind HTTPS via reverse proxy such as Caddy, Nginx Proxy Manager, Traefik, or nginx.
- Camera-friendly browser flows should continue to work when the site is served over HTTPS.

Clarification:
- The Flask app does not need to terminate TLS directly.
- The standard deployment model is containerized app behind a TLS reverse proxy.

## App Configuration Requirements
- Config must no longer assume local workspace-relative paths.
- All data/config paths must be configurable via environment variables with safe defaults.
- Defaults may still support local development when env vars are absent.
- Required directories should be created automatically on startup.

## Runtime Requirements
- App must bind to `0.0.0.0` in container environments.
- Port must be configurable.
- Debug mode must be configurable and off by default for production/container use.
- Use a production WSGI server in Docker, such as Gunicorn.

## Backup Compatibility
- Existing backup behavior must continue to work.
- Backup config file path must be configurable so it can live in a mounted persistent location.
- Backups still copy the entire journal folder structure.

## Documentation Requirements
Update README to include:
- local development run instructions
- Docker build instructions
- Docker run example
- Compose example
- host-mounted volume example
- environment variable reference
- reverse proxy / HTTPS deployment notes
- note explaining why HTTPS matters for mobile browser trust and camera behavior

## GitHub / Repo Readiness
The project should be ready to live in its own GitHub repository.

That means:
- app files live cleanly under the project directory
- Docker-related files are included
- README is accurate
- no private/local-only workspace clutter should be required for a normal clone

## Out of Scope for Phase 2
- User accounts
- Multi-user auth system
- Database migration
- OCR or AI processing
- Changing journal file formats
- Cloud SaaS deployment dependencies

## Deliverables
- Dockerfile
- .dockerignore
- optional docker-compose example
- environment-driven app config
- proxy-aware / HTTPS-friendly deployment notes
- updated README
- no changes to the Phase 1 journal data model
