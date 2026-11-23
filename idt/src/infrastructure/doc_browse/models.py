from datetime import datetime

from sqlalchemy import BigInteger, Column, Date, DateTime, Integer, String, Index
from src.infrastructure.persistence.models.base import Base


class DocumentMetadataModel(Base):
    __tablename__ = "document_metadata"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    document_id = Column(String(64), nullable=False, unique=True)
    collection_name = Column(String(128), nullable=False)
    filename = Column(String(512), nullable=False)
    category = Column(String(128), nullable=False, default="uncategorized")
    user_id = Column(String(128), nullable=False, default="")
    chunk_count = Column(Integer, nullable=False, default=0)
    chunk_strategy = Column(String(64), nullable=False, default="unknown")
    # kb-management-ui D1 (V047): 논리 KB 문서 목록 필터 키. NULL = 일반 업로드.
    kb_id = Column(String(64), nullable=True)
    # document-revision Design §3.3 (V095): 개정 계보·상태. 상태의 원본(MySQL 진실).
    #   lineage_id NULL = 자기 document_id 가 계보 ID. 기존 행은 v1·active (백필 없음).
    file_hash = Column(String(64), nullable=True)
    lineage_id = Column(String(64), nullable=True)
    version_no = Column(Integer, nullable=False, default=1)
    version_label = Column(String(100), nullable=True)
    effective_date = Column(Date, nullable=True)
    revision_status = Column(String(20), nullable=False, default="active")
    sync_state = Column(String(20), nullable=False, default="synced")
    superseded_by = Column(String(64), nullable=True)
    superseded_at = Column(DateTime, nullable=True)
    revised_by = Column(String(128), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        Index("idx_dm_collection", "collection_name"),
        Index("idx_dm_user", "user_id"),
        Index("idx_dm_created", "created_at"),
        Index("idx_dm_kb", "kb_id"),
        Index("idx_dm_kb_hash", "kb_id", "file_hash"),
        Index("idx_dm_lineage", "lineage_id", "version_no"),
        Index("idx_dm_kb_status", "kb_id", "revision_status"),
    )
