# Backend runtime (Python 3.12 slim).
# The React frontend is built and served by the separate frontend/Nginx image;
# this image contains only the FastAPI application.
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
