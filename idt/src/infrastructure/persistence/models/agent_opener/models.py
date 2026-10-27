"""AgentOpenerModel: agent_opener 테이블 ORM 매핑 (V080).

FK 는 DDL 에만 선언한다 (agent_definition CASCADE) — erd-agent 위키 관례 "FK 진실은 SQL".
"""
from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.persistence.models.base import Base


class AgentOpenerModel(Base):
    __tablename__ = "agent_opener"
    __table_args__ = {"comment": "에이전트별 대화 시작 예시 질문(오프너)"}

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, comment="UUID PK"
    )
    agent_id: Mapped[str] = mapped_column(
        String(36), nullable=False, index=True,
        comment="agent_definition.id (DDL FK CASCADE)",
    )
    text: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="예시 질문 본문(strip 완료)"
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="표시 순서(작을수록 먼저)"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, comment="생성 시각(UTC)"
    )
