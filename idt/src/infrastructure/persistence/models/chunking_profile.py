"""ChunkingProfile SQLAlchemy 모델 (clause-aware-chunking Design §4.1)."""
from datetime import datetime

from sqlalchemy import JSON, DateTime, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.persistence.models.base import Base


class ChunkingProfileModel(Base):
    __tablename__ = "chunking_profile"
    __table_args__ = (
        Index("idx_chunking_profile_status", "status"),
        Index("idx_chunking_profile_default", "is_default", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    boundary_rules: Mapped[list] = mapped_column(JSON, nullable=False)
    parent_chunk_size: Mapped[int] = mapped_column(
        Integer, nullable=False, default=2000
    )
    chunk_size: Mapped[int] = mapped_column(Integer, nullable=False, default=500)
    chunk_overlap: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    is_default: Mapped[bool] = mapped_column(Integer, nullable=False, default=0)
    # card-section-summary D2: 섹션 요약 LLM 소프트 참조 (FK 없음, NULL=비활성)
    summary_llm_model_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )
