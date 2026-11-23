"""grounding_judge_setting ORM 모델 (V094).

Design Ref: answer-citation-verification §3.3
comment= 는 마이그레이션 COMMENT 와 같은 문구.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.persistence.models.base import Base

# V094 시드 행 id — 단일 행 테이블의 고정 키
GROUNDING_JUDGE_SETTING_ID = "c0000000-0000-4000-8000-000000000094"


class GroundingJudgeSettingModel(Base):
    __tablename__ = "grounding_judge_setting"
    __table_args__ = {"comment": "근거 판정 모델 전역 설정 — 단일 행"}

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, comment="고정 단일 행 식별자"
    )
    judge_llm_model_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        comment="llm_model.id 소프트 참조 — NULL이면 env 설정 사용",
    )
    updated_by: Mapped[str | None] = mapped_column(
        String(36), nullable=True, comment="마지막으로 바꾼 관리자 user_id"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, comment="생성 시각"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, comment="수정 시각"
    )
