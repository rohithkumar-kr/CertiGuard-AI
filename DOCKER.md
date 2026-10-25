# CertiGuard Docker Setup

## Architecture
- Two services on the Compose network:
  - `frontend`: React + Vite SPA built in a Node stage and served by Nginx
    (`frontend/Dockerfile`, `frontend/nginx.conf`). Nginx also reverse-proxies
    `/api/` to `http://backend:8000`, so the browser makes same-origin requests.
  - `backend`: FastAPI on Python 3.12 slim, non-root runtime user (`appuser`,
    uid 1000), no `--reload`. It no longer builds or serves the frontend.
- Ports: app `http://localhost:8080`; backend is still published at
  `http://localhost:8000` temporarily for migration and direct API checks.
  The SPA itself does not use port 8000.
- SQLite by default. The **active host database** `backend/certificates.db` is
  bind-mounted as a single file (see Persistence below). No PostgreSQL required.
- Model artifacts (`backend/models/`) are copied into the backend image and are
  never mounted over.
- Only `frontend/nginx.conf` refers to the Compose service name `backend`; the
  browser never resolves it.

## Prerequisites
- Docker Desktop (or Docker Engine + Compose)
- `backend/.env` configured from `backend/.env.example` (never commit it).
  Required for Clerk auth: `CLERK_SECRET_KEY` (or `CLERK_JWT_KEY`), `CLERK_ISSUER`
  (Frontend API URL, not the JWKS URL).
- `frontend/.env` configured from `frontend/.env.example` when a Clerk
  publishable key is needed. Its `VITE_*` values are public build-time
  configuration. Do not put secrets in `frontend/.env`.

Clerk origins: `CLERK_AUTHORIZED_PARTIES` is optional. When it is unset, the
backend does not restrict token `azp`, so moving the UI to `localhost:8080`
only requires that Clerk itself allows that origin (Clerk's test instance
normally allows localhost). Do not add production origins or credentials
without confirming them in the Clerk Dashboard.

## Build and start
From the repo root:

```bash
# --env-file supplies the public VITE_CLERK_PUBLISHABLE_KEY build arg.
docker compose --env-file frontend/.env build
docker compose up -d
```

The backend runtime secrets are read from `backend/.env` through Compose
`env_file`; they are never copied into the frontend image or passed as build
args. `VITE_API_BASE_URL` is intentionally not passed: the bundle uses relative
`/api/...` URLs.

App: http://localhost:8080  
Health (through Nginx): http://localhost:8080/api/health  
Model (through Nginx): http://localhost:8080/api/model/info  
Backend direct (migration/testing): http://localhost:8000/api/health  
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
  and `configs/` always come from the backend image.
- `backend/data/certify.db` is a separate, untouched host file. It is **not**
  interchangeable with `backend/certificates.db`.
- `backend/certificates.db` is intentionally **untracked and Git-ignored**
  (runtime data). Never `git add` it; keep any backups outside the repository.
- No startup step copies, resets, overwrites, or migrates a host database.
  The container opens the configured database directly.
- The old volume `certiguard_backend_db` (from an earlier configuration that
  mounted the whole of `/app/backend`) is preserved but no longer used.
- Never run `docker compose down -v`: it deletes named volumes.

## Logs / health / stop
```bash
docker compose logs -f frontend
docker compose logs -f backend
docker compose ps
docker compose down        # stops; named volumes and host DB are preserved
docker compose restart frontend
```

## Rebuild after changes
```bash
docker compose --env-file frontend/.env build
docker compose up -d
```

Use `--no-cache` only when you intentionally need a clean dependency/build
layer rebuild. Rebuilding only the backend recreates it with a new container
IP; Nginx re-resolves the `backend` service name via Docker DNS, so a frontend
restart is normally unnecessary.

## Troubleshooting
- **Frontend shows "Authentication is not configured"**: the image was built
  without `VITE_CLERK_PUBLISHABLE_KEY`. Set it in `frontend/.env` and rebuild
  with `docker compose --env-file frontend/.env build frontend`.
- **Sign-in fails / 401 after moving to port 8080**: confirm the Clerk instance
  allows `http://localhost:8080` and that `CLERK_ISSUER`/`CLERK_SECRET_KEY` in
  `backend/.env` belong to the same instance as the publishable key. If
  `CLERK_AUTHORIZED_PARTIES` is set, verify it includes the new origin/party.
- **502 from http://localhost:8080/api/...**: the backend is not up yet or its
  container name changed. Check `docker compose ps` and `docker compose logs
  backend`.
- **413 on upload**: files must stay under the backend's
  `MAX_UPLOAD_SIZE_MB` (10 MB default); Nginx allows 12 MB including multipart
  framing.
- **504 / timeout during verification**: OCR and inference can be slow; Nginx
  allows 300s. Check `docker compose logs backend` for the real failure.
- **CORS errors only when calling `:8000` directly**: the Nginx path is
  same-origin and needs no CORS. If you deliberately call the API cross-origin,
  add the exact frontend origin to `CORS_ORIGINS` and keep
  `APP_ENV=production` wildcard-free.
- **OCR missing/slow**: uses the maintained `rapidocr` package with ONNX
  Runtime (bundled models). No Tesseract binary is required. Set
  `OCR_ENABLED=false` to disable OCR.
- **Model load fails**: `random_forest_v3` lives at
  `/app/backend/models/artifacts/random_forest_v3` in the image. Check logs for
  feature-schema mismatches.
- **SQLite locked / permission denied**: do not run a local backend against
  `backend/certificates.db` at the same time as the container. The bind-mounted
  file must be writable by container uid 1000.
- **Dependency changes**: update `backend/requirements.lock.txt` (Python 3.12)
  or `frontend/package-lock.json` and rebuild.

## Dev vs Prod
- Prod: Nginx frontend container, no `--reload`, non-root containers,
  healthchecks, persisted data, production env.
- Dev: run the backend from `backend/` with
  `python -m uvicorn app.main:app --reload --port 8000`, and the frontend with
  `npm run dev` in `frontend/` (Vite proxies `/api`).
