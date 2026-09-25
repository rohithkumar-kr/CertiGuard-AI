import sqlalchemy
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.database.base import Base
from app.core.logging import get_logger

logger = get_logger("database")

_connect_args = {}
if settings.database_url.startswith("sqlite"):
    _connect_args["check_same_thread"] = False

engine = create_engine(settings.database_url, connect_args=_connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


_LIGHTWEIGHT_MIGRATIONS = {
    "verifications": {
        # --- Phase 1: per-user ownership (Clerk auth) ---
        "user_id": "ALTER TABLE verifications ADD COLUMN user_id TEXT",
        "certificate_type": "ALTER TABLE verifications ADD COLUMN certificate_type TEXT",
        "review_status": "ALTER TABLE verifications ADD COLUMN review_status TEXT",
        "issuer": "ALTER TABLE verifications ADD COLUMN issuer TEXT",
        "issue_date": "ALTER TABLE verifications ADD COLUMN issue_date TEXT",
        "file_fingerprint": "ALTER TABLE verifications ADD COLUMN file_fingerprint TEXT",
        "cert_id_fingerprint": "ALTER TABLE verifications ADD COLUMN cert_id_fingerprint TEXT",
        "identity_fingerprint": "ALTER TABLE verifications ADD COLUMN identity_fingerprint TEXT",
        "duplicate_of": "ALTER TABLE verifications ADD COLUMN duplicate_of TEXT",
        "duplicate_type": "ALTER TABLE verifications ADD COLUMN duplicate_type TEXT",
        # --- Phase 9 advisory indicators ---
        "ood_status": "ALTER TABLE verifications ADD COLUMN ood_status TEXT",
        "review_priority": "ALTER TABLE verifications ADD COLUMN review_priority TEXT",
        "intelligence_json": "ALTER TABLE verifications ADD COLUMN intelligence_json TEXT",
        # --- Phase 10 extraction diagnostics ---
        "extraction_metadata": "ALTER TABLE verifications ADD COLUMN extraction_metadata TEXT",
        # --- Phase 12 evidence engine ---
        "evidence_json": "ALTER TABLE verifications ADD COLUMN evidence_json TEXT",
    },
    # --- Phase 1: per-user ownership (Clerk auth) ---
    # audit_events and certificates may not exist yet in legacy DBs; they are
    # created (with user_id) by create_all before these run.
    "audit_events": {
        "user_id": "ALTER TABLE audit_events ADD COLUMN user_id TEXT",
    },
    "certificates": {
        "user_id": "ALTER TABLE certificates ADD COLUMN user_id TEXT",
    },
    "verification_feedback": {
        # --- Phase 1: per-user ownership (Clerk auth) ---
        "user_id": "ALTER TABLE verification_feedback ADD COLUMN user_id TEXT",
        # --- Phase 12 evidence-engine snapshot on feedback rows ---
        "final_assessment": "ALTER TABLE verification_feedback ADD COLUMN final_assessment TEXT",
        "anomaly_score": "ALTER TABLE verification_feedback ADD COLUMN anomaly_score FLOAT",
        "anomaly_level": "ALTER TABLE verification_feedback ADD COLUMN anomaly_level TEXT",
    },
}

_INDEX_DDL = [
    "CREATE INDEX IF NOT EXISTS ix_verifications_created_at ON verifications (created_at)",
    "CREATE INDEX IF NOT EXISTS ix_verifications_prediction ON verifications (prediction)",
    "CREATE INDEX IF NOT EXISTS ix_verifications_filename ON verifications (filename)",
    "CREATE INDEX IF NOT EXISTS ix_verifications_review_status ON verifications (review_status)",
    "CREATE INDEX IF NOT EXISTS ix_verifications_issuer ON verifications (issuer)",
    "CREATE INDEX IF NOT EXISTS ix_verifications_issue_date ON verifications (issue_date)",
    "CREATE INDEX IF NOT EXISTS ix_verifications_risk_score ON verifications (risk_score)",
    # --- Phase 9 feedback indexes ---
    "CREATE INDEX IF NOT EXISTS ix_verification_feedback_reviewer_label ON verification_feedback (reviewer_label)",
    "CREATE INDEX IF NOT EXISTS ix_verification_feedback_reviewed_at ON verification_feedback (reviewed_at)",
    "CREATE INDEX IF NOT EXISTS ix_verification_feedback_certificate_type ON verification_feedback (certificate_type)",
    "CREATE INDEX IF NOT EXISTS ix_verification_feedback_issuer ON verification_feedback (issuer)",
    "CREATE INDEX IF NOT EXISTS ix_verification_feedback_file_fingerprint ON verification_feedback (file_fingerprint)",
    "CREATE INDEX IF NOT EXISTS ix_verification_feedback_cert_id_fingerprint ON verification_feedback (cert_id_fingerprint)",
    "CREATE INDEX IF NOT EXISTS ix_verification_feedback_split ON verification_feedback (split)",
    "CREATE INDEX IF NOT EXISTS ix_verification_feedback_dataset_batch ON verification_feedback (dataset_batch)",
    # --- Audit trail indexes ---
    "CREATE INDEX IF NOT EXISTS ix_audit_events_verification_id ON audit_events (verification_id)",
    "CREATE INDEX IF NOT EXISTS ix_audit_events_created_at ON audit_events (created_at)",
    "CREATE INDEX IF NOT EXISTS ix_audit_events_event_type ON audit_events (event_type)",
    # --- Phase 1: per-user ownership indexes ---
    "CREATE INDEX IF NOT EXISTS ix_verifications_user_id ON verifications (user_id)",
    "CREATE INDEX IF NOT EXISTS ix_verification_feedback_user_id ON verification_feedback (user_id)",
    "CREATE INDEX IF NOT EXISTS ix_audit_events_user_id ON audit_events (user_id)",
    "CREATE INDEX IF NOT EXISTS ix_certificates_user_id ON certificates (user_id)",
]


def _run_lightweight_migrations() -> None:
    """Apply schema additions to DB files that predate them.

    SQLite's create_all only creates missing tables, so schema additions on
    existing tables must be applied explicitly. Best-effort: logs a warning
    instead of raising so a stale dev DB never blocks startup.
    """
    if not settings.database_url.startswith("sqlite"):
        return
    with engine.connect() as conn:
        inspector = conn.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = {row[0] for row in inspector}
        for table, column_map in _LIGHTWEIGHT_MIGRATIONS.items():
            if table not in table_names:
                continue
            existing = {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")}
            for column, ddl in column_map.items():
                if column not in existing:
                    try:
                        conn.exec_driver_sql(ddl)
                        conn.commit()
                        logger.info("Applied migration: %s", ddl)
                    except Exception as exc:  # noqa: BLE001 - best-effort migration
                        conn.rollback()
                        logger.warning("Migration failed (%s): %s", ddl, exc)

        for ddl in _INDEX_DDL:
            try:
                conn.exec_driver_sql(ddl)
            except Exception as exc:  # noqa: BLE001 - best-effort index creation
                logger.warning("Index creation failed (%s): %s", ddl, exc)
        conn.commit()


def init_db() -> None:
    import app.models  # noqa: F401 - registers all ORM models
    Base.metadata.create_all(bind=engine)
    _run_lightweight_migrations()
    logger.info("Database ready: %s", settings.database_url)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()