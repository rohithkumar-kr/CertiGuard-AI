"""Tests for Phase 7 hardening: upload retention, DB migrations, concurrency."""

import json
import pathlib

from app.core.config import settings
from app.database import database
from app.services import file_service
from app.utils import file_utils


def test_upload_retention_prunes_oldest(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "upload_dir", pathlib.Path(tmp_path))
    monkeypatch.setattr(settings, "upload_retention_max", 3)

    for _ in range(5):
        file_service.save_upload(b"%PDF-1.4 test", "pdf")

    remaining = sorted(tmp_path.glob("*.pdf"), key=lambda p: p.stat().st_mtime)
    assert len(remaining) == 3
    assert all(f.exists() for f in remaining)


def test_delete_upload_removes_only_upload_dir_files(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "upload_dir", pathlib.Path(tmp_path))
    target = file_service.save_upload(b"%PDF-1.4 x", "pdf")
    assert target.exists()
    file_service.delete_upload(target)
    assert not target.exists()

    outside = tmp_path.parent / "outside.txt"
    outside.write_text("keep me", encoding="utf-8")
    file_service.delete_upload(outside)  # must not delete files outside upload dir
    assert outside.exists()


def test_init_db_is_idempotent():
    database.init_db()
    database.init_db()
    # Re-running migrations/index creation must not raise.
    database._run_lightweight_migrations()


def test_init_db_creates_history_indexes():
    database.init_db()
    with database.engine.connect() as conn:
        rows = conn.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
    index_names = {r[0] for r in rows}
    assert "ix_verifications_created_at" in index_names
    assert "ix_verifications_prediction" in index_names
    assert "ix_verifications_filename" in index_names