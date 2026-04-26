from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, Integer, String, Index
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
    )
