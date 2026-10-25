# Multi-stage build: frontend + backend
FROM node:20-alpine AS frontend-build
WORKDIR /frontend

# Public, build-time frontend configuration (Vite inlines VITE_* values into
# the static bundle). These are safe to expose; backend secrets must never be
# passed here. Supply them with:
#   docker compose --env-file frontend/.env build
ARG VITE_CLERK_PUBLISHABLE_KEY=""
ARG VITE_API_BASE_URL=""

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN set -e; \
    if [ -z "$VITE_CLERK_PUBLISHABLE_KEY" ]; then \
        echo "WARNING: VITE_CLERK_PUBLISHABLE_KEY is empty; the built frontend will show the authentication-not-configured screen." >&2; \
    fi; \
    if [ -n "$VITE_CLERK_PUBLISHABLE_KEY" ]; then export VITE_CLERK_PUBLISHABLE_KEY; fi; \
    if [ -n "$VITE_API_BASE_URL" ]; then export VITE_API_BASE_URL; fi; \
    npm run build

# Backend runtime (Python 3.12 slim)
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libgomp1 \
    libsm6 \
    libxext6 \
    libxrender1 \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/backend

COPY backend/requirements.lock.txt ./requirements.lock.txt
RUN pip install --no-cache-dir -r requirements.lock.txt

# Backend source
COPY backend/app ./app
COPY backend/src ./src
COPY backend/data ./data
COPY backend/models ./models
COPY backend/configs ./configs
COPY backend/scripts ./scripts
COPY backend/monitoring ./monitoring
COPY backend/.env.example ./.env.example

# Frontend build output served by backend
COPY --from=frontend-build /frontend/dist /app/frontend/dist

# Dedicated directory for the bind-mounted SQLite database. Keeping it outside
# /app/backend means SQLite journal/WAL files never need the application source
# directory to be writable, and no application files are hidden by a volume.
RUN mkdir -p uploads monitoring/logs /app/db

RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
