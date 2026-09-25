from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import router as api_router
from app.core.config import settings
from app.core.errors import AppError
from app.core.logging import get_logger, setup_logging
from app.core.security import configure_cors
from app.database.database import init_db

import logging

setup_logging(level=getattr(logging, settings.log_level, logging.INFO))
logger = get_logger("main")

app = FastAPI(
    title=settings.app_name,
    description="AI-based preliminary verification and fraud-risk prediction for certificates.",
    version="1.0.0",
    docs_url="/docs" if settings.app_env == "development" else None,
    redoc_url=None,
)

configure_cors(app, settings.cors_origins)


@app.on_event("startup")
def on_startup() -> None:
    settings.ensure_dirs()
    init_db()
    if not settings.clerk_issuer:
        logger.warning(
            "CLERK_ISSUER is NOT configured: every protected API request will be "
            "rejected with HTTP 401 (\"Authentication unavailable\"). Set it in "
            "backend/.env to your Clerk instance's Frontend API URL, e.g. "
            "https://<your-instance>.clerk.accounts.dev."
        )
    elif settings.clerk_issuer_is_jwks_url:
        logger.warning(
            "CLERK_ISSUER is set to your Clerk JWKS URL (it ends in "
            ".well-known/jwks.json). The issuer check compares the token's `iss` "
            "claim against the Frontend API URL only, so the JWKS suffix is "
            "automatically stripped and auth will work — but please set "
            "CLERK_ISSUER to the plain Frontend API URL to avoid confusion: "
            "https://<your-instance>.clerk.accounts.dev"
        )
    if not settings.clerk_secret_key and not settings.clerk_jwt_key:
        logger.warning(
            "Neither CLERK_SECRET_KEY nor CLERK_JWT_KEY is configured: session "
            "tokens cannot be verified, so every protected API request will be "
            "rejected with HTTP 401."
        )


@app.get("/")
def home():
    return {
        "app": settings.app_name,
        "message": "AI-based preliminary verification for certificates",
        "docs": "/docs" if settings.app_env == "development" else None,
        "endpoints": [
            "GET /api/health",
            "GET /api/model/info",
            "POST /api/verify",
            "GET /api/verifications",
            "GET /api/verifications/summary",
            "GET /api/metrics",
            "GET /api/verifications/{id}",
            "POST /api/verifications/{id}/feedback",
            "GET /api/feedback/summary",
            "GET /api/feedback/analytics",
        ],
    }


@app.exception_handler(AppError)
async def app_error_handler(_: Request, exc: AppError):
    logger.warning("AppError (%s): %s", exc.status_code, exc.message)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    if request.headers.get("content-type", "").startswith("multipart/form-data"):
        # Keep the phase-8 file-upload message for multipart uploads.
        return JSONResponse(
            status_code=422,
            content={"detail": "Invalid request. A valid file upload is required."},
        )
    errors = _json_safe(exc.errors())
    return JSONResponse(
        status_code=422,
        content={"detail": errors},
    )


def _json_safe(value):
    """Recursively coerce non-JSON-serializable objects (e.g. pydantic ctx
    exceptions) into strings so validation details can be returned."""
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, Exception):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(_: Request, exc: StarletteHTTPException):
    # Preserve any response headers (e.g. WWW-Authenticate on 401) that the
    # exception carries.
    headers = dict(exc.headers) if exc.headers else None
    return JSONResponse(
        status_code=exc.status_code, content={"detail": str(exc.detail)}, headers=headers
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    # Never expose stack traces to clients; log them instead.
    logger.exception("Unhandled error on %s", request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected error occurred. Please try again later."},
    )


# Serve the built frontend (frontend/dist) when present, e.g. in production.
# Note: must be mounted AFTER API routes so /api/* is not shadowed.
app.include_router(api_router, prefix="/api")

_DIST = settings.base_dir.parent / "frontend" / "dist"
if _DIST.exists():
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=_DIST, html=True), name="frontend")