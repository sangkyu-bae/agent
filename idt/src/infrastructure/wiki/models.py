"""SQLAlchemy ORM 모델: wiki_article (LLM-WIKI-001)."""
from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.persistence.models.base import Base


class WikiArticleModel(Base):
    __tablename__ = "wiki_article"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)
    source_refs: Mapped[list] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    confidence: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False, default=0.5)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    editor_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reviewer_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
