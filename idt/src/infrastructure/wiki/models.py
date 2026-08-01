"""SQLAlchemy ORM 모델: wiki_article (LLM-WIKI-001)."""
from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.persistence.models.base import Base


class WikiArticleModel(Base):
    __tablename__ = "wiki_article"
    __table_args__ = (Index("idx_wiki_agent_path", "agent_id", "path"),)

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
    # wiki-user-facing(V051): 가상 폴더 경로. NULL=미분류
    path: Mapped[str | None] = mapped_column(String(255), nullable=True)


class WikiFolderSummaryModel(Base):
    """wiki-folder-summaries(V053): 폴더 요약 파생 캐시. DDL comment 규칙 — 전 컬럼 comment."""

    __tablename__ = "wiki_folder_summary"
    __table_args__ = (
        UniqueConstraint("agent_id", "path", name="uq_wiki_folder"),
        Index("idx_wiki_folder_agent", "agent_id"),
        {"comment": "에이전트 위키 폴더 요약 — 승인/편집/폐기 이벤트로 재증류되는 파생 캐시"},
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, comment="UUID PK")
    agent_id: Mapped[str] = mapped_column(
        String(36), nullable=False, comment="소속 에이전트 (agent_definition.id)"
    )
    path: Mapped[str] = mapped_column(
        String(255), nullable=False,
        comment='가상 폴더 경로("여신/한도"), 깊이<=3 — wiki_article.path와 동일 제약',
    )
    summary: Mapped[str] = mapped_column(
        Text, nullable=False,
        comment="LLM 증류 폴더 안내 설명 (탐색 힌트 — 진실은 wiki_list 실시간 목록)",
    )
    article_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="하위 전체(재귀) 승인+미만료 문서 수"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, comment="마지막 재증류 시각"
    )
