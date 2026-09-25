"""Application configuration loaded from environment variables (.env).

Never hardcode secrets. All runtime settings come from the environment,
with sensible defaults for local development.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # backend/
load_dotenv(BASE_DIR / ".env")


def _as_bool(value: str, default: bool = False) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"} if value is not None else default


class Settings:
    def __init__(self) -> None:
        self.base_dir = BASE_DIR
        self.app_name = os.getenv("APP_NAME", "CertiGuard AI")
        self.app_env = os.getenv("APP_ENV", "development")

        self.host = os.getenv("BACKEND_HOST", "0.0.0.0")
        self.port = int(os.getenv("BACKEND_PORT", "8000"))
        self.log_level = os.getenv("LOG_LEVEL", "INFO").upper()

        origins = os.getenv("CORS_ORIGINS",
                            "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000")
        self.cors_origins = [o.strip() for o in origins.split(",") if o.strip()]

        self.database_url = os.getenv(
            "DATABASE_URL",
            f"sqlite:///{(BASE_DIR / 'certificates.db').as_posix()}",
        )
        self.max_upload_size_mb = int(os.getenv("MAX_UPLOAD_SIZE_MB", "10"))
        self.allowed_upload_extensions = {
            e.strip().lower().lstrip(".")
            for e in os.getenv("ALLOWED_UPLOAD_EXTENSIONS", "pdf,png,jpg,jpeg").split(",")
            if e.strip()
        }
        self.upload_dir = (BASE_DIR / os.getenv("UPLOAD_DIR", "uploads")).resolve()
        self.upload_retention_max = int(os.getenv("UPLOAD_RETENTION_MAX", "200"))
        self.max_concurrent_verifications = int(os.getenv("MAX_CONCURRENT_VERIFICATIONS", "8"))

        self.model_version = os.getenv("MODEL_VERSION", "random_forest_v3")
        self.model_artifact_dir = (BASE_DIR / os.getenv("MODEL_ARTIFACT_DIR", "models/artifacts")).resolve()
        self.model_metadata_dir = (BASE_DIR / os.getenv("MODEL_METADATA_DIR", "models/metadata")).resolve()
        self.decision_threshold = float(os.getenv("DECISION_THRESHOLD", "0.5"))

        self.data_raw_dir = (BASE_DIR / os.getenv("DATA_RAW_DIR", "data/raw")).resolve()
        self.data_processed_dir = (BASE_DIR / os.getenv("DATA_PROCESSED_DIR", "data/processed")).resolve()
        self.training_seed = int(os.getenv("TRAINING_SEED", "42"))

        # --- Phase 10 OCR configuration (centralized) ---
        # ocr_enabled: master switch. When off, extraction never runs OCR.
        self.ocr_enabled = _as_bool(os.getenv("OCR_ENABLED"), True)
        # ocr_engine: auto (rapidocr then pytesseract) | rapidocr | pytesseract | none.
        self.ocr_engine = os.getenv("OCR_ENGINE", "auto").strip().lower()
        self.ocr_languages = os.getenv("OCR_LANGUAGES", "en").strip()
        # ocr_max_pages: maximum pages rendered for OCR (certificates are short).
        self.ocr_max_pages = int(os.getenv("OCR_MAX_PAGES", "4"))
        # ocr_dpi: render resolution used for OCR (higher = better, slower).
        self.ocr_dpi = int(os.getenv("OCR_DPI", "200"))
        # Below this text length the embedded text layer is treated as
        # insufficient and OCR is attempted.
        self.ocr_min_text_chars = int(os.getenv("OCR_MIN_TEXT_CHARS", "40"))
        # Below this length, even non-empty embedded text triggers OCR when
        # core fields are also missing (image-heavy certificates).
        self.ocr_hybrid_chars = int(os.getenv("OCR_HYBRID_CHARS", "150"))
        # Fraction of core identity fields that counts as "extraction good
        # enough to trust" without OCR.
        self.ocr_min_completeness = float(os.getenv("OCR_MIN_COMPLETENESS", "0.4"))

        self.debug = _as_bool(os.getenv("DEBUG"), self.app_env == "development")

        # --- Clerk authentication (backend verification) ---
        # Clerk Dashboard field mapping (copy the exact value shown):
        #   "Frontend API URL"        -> CLERK_ISSUER  (the token's `iss` claim)
        #   "Backend API URL"         -> used by the SDK to fetch JWKS when no
        #                               CLERK_JWT_KEY is set (default
        #                               https://api.clerk.com/v1/jwks)
        #   "JWKS URL" / "JWKS key"   -> NOT configuration inputs; the SDK
        #                               resolves keys itself. Do NOT paste the
        #                               JWKS URL into CLERK_ISSUER.
        # The secret key is used to fetch the signing JWKS from the Clerk
        # Backend API when jwt_key is not supplied. The jwt_key is the PEM
        # public key from the Clerk Dashboard (networkless verification).
        # Never ship the secret key to the frontend; it belongs only here.
        self.clerk_secret_key = os.getenv("CLERK_SECRET_KEY", "").strip() or None
        self.clerk_jwt_key = os.getenv("CLERK_JWT_KEY", "").strip() or None
        # Issuer URL: the Clerk Frontend API URL (e.g.
        # https://<your-clerk-domain>.clerk.accounts.dev). The token's `iss`
        # claim must equal this value EXACTLY and nothing else. Auth strips a
        # trailing "/.well-known/jwks.json" defensively, but set the plain value.
        self.clerk_issuer = os.getenv("CLERK_ISSUER", "").strip() or None
        # True when the configured issuer is actually the JWKS URL — a common
        # Dashboard copy-paste mistake worth flagging loudly at startup.
        self.clerk_issuer_is_jwks_url = bool(
            self.clerk_issuer
            and (
                self.clerk_issuer.lower().endswith("/.well-known/jwks.json")
                or self.clerk_issuer.lower().endswith("/jwks.json")
                or self.clerk_issuer.lower().endswith("/.well-known/jwks")
            )
        )
        # Developer diagnostics: when enabled, an issuer mismatch logs the
        # received token's `iss` claim (a public URL — never the JWT). Off by
        # default. Enable via CLERK_DEBUG_ISSUER=1.
        self.clerk_debug_issuer = _as_bool(os.getenv("CLERK_DEBUG_ISSUER"), False)
        # Allow-list of authorized parties validated against the token's `azp`
        # claim (comma-separated). Clerk's default azp is the publishable key;
        # after configuring authorized parties in the Dashboard use those.
        self.clerk_authorized_parties = [
            p.strip() for p in os.getenv("CLERK_AUTHORIZED_PARTIES", "").split(",")
            if p.strip()
        ] or None
        self.clerk_audience = os.getenv("CLERK_AUDIENCE", "").strip() or None
        self.clerk_clock_skew_ms = int(os.getenv("CLERK_CLOCK_SKEW_MS", "5000"))

        # --- Phase 12: external verification (off by default) ---
        # When enabled, QR/issuer URLs may be contacted. Never enabled in
        # environments that cannot perform outbound network calls safely.
        self.external_verify_enabled = _as_bool(os.getenv("EXTERNAL_VERIFY_ENABLED"), False)
        # Timeout (seconds) and maximum payload size for external checks.
        self.external_verify_timeout = float(os.getenv("EXTERNAL_VERIFY_TIMEOUT", "4.0"))
        self.external_verify_max_bytes = int(os.getenv("EXTERNAL_VERIFY_MAX_BYTES", "200000"))
        self.external_verify_schemes = {
            s.strip().lower()
            for s in os.getenv("EXTERNAL_VERIFY_SCHEMES", "https,http").split(",")
            if s.strip()
        }

    def ensure_dirs(self) -> None:
        for d in (self.upload_dir, self.model_artifact_dir, self.model_metadata_dir):
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()