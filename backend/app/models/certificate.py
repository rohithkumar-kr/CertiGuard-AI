from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime
from app.database.base import Base
from datetime import datetime, timezone


def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Certificate(Base):
    __tablename__ = "certificates"
    id = Column(Integer, primary_key=True)
    # Clerk user id of the user who uploaded/created this certificate. Null for
    # legacy records which remain hidden from all users.
    user_id = Column(String, index=True, nullable=True)
    original_filename = Column(String, nullable=False)
    stored_filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    candidate_name = Column(String, nullable=True)
    organization = Column(String, nullable=True)
    course = Column(String, nullable=True)
    status = Column(String, nullable=True)
    confidence = Column(Float, nullable=True)
    ocr_completed = Column(Boolean, default=False)
    uploaded_at = Column(DateTime, default=utc_now)