"""Security helpers: CORS configuration.

CORS is restricted to explicitly allowed origins from the environment.
Wildcard origins are refused outside development; credentials are only
allowed with explicit origins.
"""

import logging

from app.core.config import settings

logger = logging.getLogger("certverify.security")


def configure_cors(app, origins: list[str]) -> None:
    from fastapi.middleware.cors import CORSMiddleware

    if not origins or ("*" in origins and settings.app_env != "development"):
        raise RuntimeError(
            "Refusing to start: wildcard CORS is not allowed outside development. "
            "Set CORS_ORIGINS to explicit origins."
        )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
    logger.info("CORS allowed origins: %s", origins)
