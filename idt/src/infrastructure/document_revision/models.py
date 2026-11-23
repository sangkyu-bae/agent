"""document_revision_check 모델 (document-revision Design §3.3 V097)."""
from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, Index, Integer, String

from src.infrastructure.persistence.models.base import Base


class DocumentRevisionCheckModel(Base):
    __tablename__ = "document_revision_check"

    id = Column(String(36), primary_key=True)
    kb_id = Column(String(64), nullable=False)
    user_id = Column(String(128), nullable=False)
    source = Column(String(20), nullable=False)
    filename = Column(String(512), nullable=False)
    normalized_name = Column(String(512), nullable=True)
    file_hash = Column(String(64), nullable=True)
    verdict = Column(String(30), nullable=False)
    suggested_document_id = Column(String(64), nullable=True)
    candidates_json = Column(JSON, nullable=True)
    llm_status = Column(String(10), nullable=False, default="skipped")
    elapsed_ms = Column(Integer, nullable=False, default=0)
    parse_ms = Column(Integer, nullable=False, default=0)
    decision = Column(String(20), nullable=True)
    target_document_id = Column(String(64), nullable=True)
    decided_document_id = Column(String(64), nullable=True)
    decided_by = Column(String(128), nullable=True)
    decided_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (Index("idx_drc_kb_created", "kb_id", "created_at"),)
