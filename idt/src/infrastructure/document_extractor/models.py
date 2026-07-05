"""SQLAlchemy ORM 모델: document_template (Design §2-5, V037 매핑)."""
from datetime import datetime

from sqlalchemy import DateTime, Index, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.persistence.models.base import Base


class DocumentTemplateModel(Base):
    __tablename__ = "document_template"
    __table_args__ = (
        # D4: 유니크 아님 — soft-delete 재등록 허용, active 1개는 UseCase가 보장.
        Index("idx_document_template_agent_worker", "agent_id", "worker_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(36), nullable=False)
    worker_id: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # MySQL LONGTEXT — Text().with_variant 없이도 mysql dialect에서 LONGTEXT 필요 시
    # DDL은 V037이 관리하므로 ORM은 Text로 충분(읽기/쓰기 호환).
    html_skeleton: Mapped[str] = mapped_column(Text, nullable=False)
    slots: Mapped[list] = mapped_column(JSON, nullable=False)
    source_file_ref: Mapped[str] = mapped_column(String(500), nullable=False)
    source_format: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
