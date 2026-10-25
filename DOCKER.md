# CertiGuard Docker Setup

## Architecture
- Single service: `backend` (FastAPI), built from `backend/Dockerfile` (multi-stage). Node builds the frontend into `/app/frontend/dist`; the Python 3.12 runtime serves those static assets when present.
- Python 3.12 slim, non-root runtime user (`appuser`, uid 1000), no `--reload`.
- SQLite by default. The **active host database** `backend/certificates.db` is bind-mounted as a single file (see Persistence below). No PostgreSQL required.
- Model artifacts (`backend/models/`) are copied into the image and are never mounted over.

## Prerequisites
- Docker Desktop (or Docker Engine + Compose)
- `backend/.env` configured from `backend/.env.example` (never commit it).
  Required for Clerk auth: `CLERK_SECRET_KEY` (or `CLERK_JWT_KEY`), `CLERK_ISSUER`
  (Frontend API URL, not the JWKS URL).
- `frontend/.env` configured from `frontend/.env.example`. Its `VITE_*` values
  are public build-time configuration. Do not put secrets in `frontend/.env`.

## Build and start
From the repo root:

```bash
# --env-file supplies the public VITE_* build args from frontend/.env.
docker compose --env-file frontend/.env build
docker compose up -d
```

The backend runtime secrets are read from `backend/.env` through Compose
`env_file`; they are never copied into the image or passed as build args.

App: http://localhost:8000  
Health: http://localhost:8000/api/health  
Model: http://localhost:8000/api/model/info  
API docs: `/docs` is intentionally disabled because `APP_ENV=production`
(404 is expected).

## Persistence and mounts
| Mount | Container path | Purpose |
|---|---|---|
| Bind: `./backend/certificates.db` | `/app/db/certificates.db` | Active SQLite database (single file). `/app/db` is writable by `appuser` so SQLite can create journal/WAL files. |
| Volume: `backend_uploads` | `/app/backend/uploads` | Uploaded documents (retained, outside the image). |
| Volume: `backend_monitoring_logs` | `/app/backend/monitoring/logs` | Rotating application logs. |

Important:
- Nothing is mounted over `/app/backend` as a directory, so code, `models/`,
  `configs/`, and static frontend assets always come from the image.
- `backend/data/certify.db` is a separate, untouched host file. It is **not**
  interchangeable with `backend/certificates.db`.
- No startup step copies, resets, overwrites, or migrates a host database.
  The container opens the configured database directly.
- The old volume `certiguard_backend_db` (from an earlier configuration that
  mounted the whole of `/app/backend`) is preserved but no longer used.
- Never run `docker compose down -v`: it deletes named volumes.

## Logs / health / stop
```bash
docker compose logs -f backend
docker compose ps
docker compose down        # stops; named volumes and host DB are preserved
docker compose restart backend
```

## Rebuild after changes
```bash
docker compose --env-file frontend/.env build
docker compose up -d
```

Use `--no-cache` only when you intentionally need a clean dependency/build
layer rebuild.

## Troubleshooting
- **Frontend shows "Authentication is not configured"**: the image was built
  without `VITE_CLERK_PUBLISHABLE_KEY`. Rebuild with
  `docker compose --env-file frontend/.env build`.
- **OCR missing/slow**: uses the maintained `rapidocr` package with ONNX
  Runtime (bundled models). No Tesseract binary is required. Set
  `OCR_ENABLED=false` to disable OCR.
- **Model load fails**: `random_forest_v3` lives at
  `/app/backend/models/artifacts/random_forest_v3` in the image. Check logs for
  feature-schema mismatches.
- **Auth 401**: verify `CLERK_ISSUER` is the Clerk Frontend API URL and that
  the secret key matches the same Clerk instance. Do not expose secrets.
- **SQLite locked / permission denied**: do not run a local backend against
  `backend/certificates.db` at the same time as the container. The bind-mounted
  file must be writable by container uid 1000.
- **Dependency changes**: update `backend/requirements.lock.txt` (Python 3.12)
  and rebuild.

## Dev vs Prod
- Prod: no `--reload`, non-root, healthcheck, persisted data, production env.
- Dev: from `backend/`, run
  `python -m uvicorn app.main:app --reload --port 8000`.
