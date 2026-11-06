"""SQLAlchemy ORM: kb_default_setting (V084).

Design Ref: agent-kb-quick-setup §3.3 — 전역 단일 행, default_embedding_model_id 는
embedding_model.id 소프트 참조(FK 없음).
CLAUDE.md §3: comment= 는 마이그레이션 COMMENT 와 동일 문구.
"""
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.persistence.models.base import Base

# V084 시드 행 id — 단일 행 테이블의 고정 키
KB_DEFAULT_SETTING_ID = "c0000000-0000-4000-8000-000000000001"


class KbDefaultSettingModel(Base):
    __tablename__ = "kb_default_setting"
    __table_args__ = {"comment": "지식베이스 자동 구성 전역 기본값 — 단일 행"}

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, comment="고정 단일 행 식별자"
    )
    default_embedding_model_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="embedding_model.id 소프트 참조 — NULL이면 미설정",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), comment="생성 시각"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="수정 시각",
    )
