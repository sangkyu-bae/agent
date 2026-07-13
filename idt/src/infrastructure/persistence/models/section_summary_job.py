"""SectionSummaryJob SQLAlchemy 모델 (card-section-summary Design §4.2)."""
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.persistence.models.base import Base


class SectionSummaryJobModel(Base):
    __tablename__ = "section_summary_job"
    __table_args__ = (
        UniqueConstraint("document_id", name="uq_section_summary_job_document"),
        Index("idx_section_summary_job_kb", "kb_id"),
        Index("idx_section_summary_job_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_id: Mapped[str] = mapped_column(String(36), nullable=False)
    kb_id: Mapped[str] = mapped_column(String(36), nullable=False)
    collection_name: Mapped[str] = mapped_column(String(255), nullable=False)
    chunking_profile_id: Mapped[str] = mapped_column(String(36), nullable=False)
    llm_model_id: Mapped[str] = mapped_column(String(36), nullable=False)
    embedding_provider: Mapped[str] = mapped_column(String(50), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )
    total_sections: Mapped[int | None] = mapped_column(Integer, nullable=True)
    done_sections: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_sections: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    error: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )
