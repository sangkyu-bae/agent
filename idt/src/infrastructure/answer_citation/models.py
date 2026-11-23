"""ai_answer_citation ORM 모델 (V093).

Design Ref: answer-citation-verification §3.3
comment= 는 마이그레이션 COMMENT 와 같은 문구.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.persistence.models.base import Base


class AnswerCitationModel(Base):
    __tablename__ = "ai_answer_citation"
    __table_args__ = {"comment": "답변 인용 검증 결과 — 실행당 1행"}

    run_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, comment="ai_run.id 소프트 참조 — 실행당 1행"
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, comment="검증 결과 verified 또는 none"
    )
    none_reason: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        comment="none 사유 no_markers 또는 all_rejected 또는 judge_failed",
    )
    citations: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        comment="검증된 인용 목록 — no와 chunk_id와 page와 evidence와 sentence",
    )
    judge_model: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="판정에 쓴 모델 이름 — 감사용"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, comment="생성 시각"
    )
