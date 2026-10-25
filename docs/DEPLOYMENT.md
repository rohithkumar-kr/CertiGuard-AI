# Deployment

This document covers running the system outside local development. The project
does **not** require Docker; a documented local deployment is used instead to
keep the Windows development workflow unchanged.

## Requirements

- Python 3.13+ (backend)
- Node.js 18+ (frontend build, only needed to produce `frontend/dist`)
- SQLite (default, zero setup) or PostgreSQL

## 1. Build the frontend (static assets)

For Docker deployments this step is done inside the `frontend` image; see
`DOCKER.md`. For a non-Docker deployment, build locally:

```bash
cd frontend
npm install
npm run build        # outputs frontend/dist
```

In a non-Docker deployment the FastAPI backend serves the built SPA from
`frontend/dist` when that folder exists. In Docker, Nginx serves it and
reverse-proxies `/api/` to the backend container.

The API base URL defaults to same-origin (`/api/...`), so no absolute
`VITE_API_BASE_URL` is needed. Only set it for an intentionally cross-origin
deployment, and then add that frontend origin to `CORS_ORIGINS`.

## 2. Configure the backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate          # Windows | source venv/bin/activate
pip install -r requirements.txt
copy .env.example .env         # Windows | cp .env.example .env
```

Edit `.env` for the target environment. Key settings:

| Variable | Default | Notes |
|---|---|---|
| `APP_ENV` | `development` | `production` hides `/docs` and refuses wildcard CORS |
| `BACKEND_HOST` / `BACKEND_PORT` | `0.0.0.0` / `8000` | Bind address and port |
| `CORS_ORIGINS` | local origins | Comma-separated allowed browser origins; `*` refused outside development |
| `DATABASE_URL` | `sqlite:///./certificates.db` | Or PostgreSQL `postgresql+psycopg2://user:pass@host:5432/db` |
| `MODEL_VERSION` | `random_forest_v3` | Production model; do NOT point at candidate versions |
| `DECISION_THRESHOLD` | `0.5` | Validated decision boundary; do not change without re-running frozen validation |
| `UPLOAD_RETENTION_MAX` | `200` | Max stored uploads; oldest pruned first |
| `MAX_CONCURRENT_VERIFICATIONS` | `8` | Burst-protection limit |
| `MAX_UPLOAD_SIZE_MB` | `10` | Upload size cap |
| `LOG_LEVEL` | `INFO` | `DEBUG` for development diagnostics |

The startup routine creates any missing directories, initializes the database
(idempotently, with lightweight migrations), and creates query indexes
automatically. No manual DB setup is required for SQLite.

## 3. Run the backend

Development:

```bash
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Production (Linux, multi-worker). Install the server worker:

```bash
pip install "uvicorn[standard]"
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

Notes for production:

- Terminate TLS at a reverse proxy (nginx/Caddy) and set
  `CORS_ORIGINS` to the exact HTTPS origin; keep `APP_ENV=production`.
- Serve the built SPA from that reverse proxy and forward `/api/` to the
  backend without stripping the prefix. In the Docker setup, the `frontend`
  Nginx container does this and proxies to `http://backend:8000` over the
  Compose network; the browser only talks to the frontend origin.
- Use a PostgreSQL `DATABASE_URL` for shared/concurrent access.
- Back up the database (SQLite: the `certificates.db` file) and the
  `backend/uploads` retention store as appropriate.

## 4. Health check

```bash
curl http://localhost:8000/api/health
```

The startup logs report model loading, DB migration status, and any failures.

## 5. Monitoring in production

```bash
curl http://localhost:8000/api/metrics
```

Drift detection is local-only by design (never automates deployment decisions):

```bash
python scripts/check_distribution_change.py --update-baseline   # snapshot baseline
python scripts/check_distribution_change.py                     # compare + report
```

## 6. Operational notes

- **No ML artifacts are written at runtime.** Prediction uses the loaded
  production model and is read-only; the training pipeline is an offline step.
- **The active model is `random_forest_v3`.** Candidate versions
  (`random_forest_v4*`) exist under `models/artifacts/` for evaluation only.
- **No secrets are committed.** `.env` is git-ignored; only `.env.example`
  is tracked.