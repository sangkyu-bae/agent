"""SQLAlchemy ORM 모델: evaluation_sweep.

Design Ref: §3.3 — V067 마이그레이션과 1:1 매핑.
컬럼 comment는 DDL과 동일하게 유지한다 (idt/CLAUDE.md §3 DDL 규약).
"""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.persistence.models.base import Base


class EvaluationSweepModel(Base):
    __tablename__ = "evaluation_sweep"
    __table_args__ = (
        Index("idx_sweep_user_created", "user_id", "created_at"),
        Index("idx_sweep_agent", "agent_id"),
        Index("idx_sweep_status", "status"),
        {"comment": "모델 스윕 — 동일 에이전트를 여러 LLM 모델로 순차 평가한 실험 1건"},
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, comment="스윕 ID (UUID)"
    )
    name: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="스윕 표시 이름"
    )
    agent_id: Mapped[str] = mapped_column(
        String(36), nullable=False,
        comment="피평가 에이전트 ID — 스윕 내내 고정",
    )
    testset_id: Mapped[str] = mapped_column(
        String(36), nullable=False,
        comment="평가에 사용한 테스트셋 ID (evaluation_testset.id)",
    )
    # FK 제약은 DDL(V067)에만 둔다 — ai_run.llm_model_id(agent_run.py:25) 선례.
    judge_llm_model_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True,
        comment="RAGAS 채점 judge 모델 ID — 실행 시점 박제",
    )
    model_ids: Mapped[list] = mapped_column(
        JSON, nullable=False,
        comment="피평가 모델 ID 배열 스냅샷 (최대 5개)",
    )
    metrics: Mapped[list] = mapped_column(
        JSON, nullable=False,
        comment="선택된 RAGAS 메트릭 이름 배열 스냅샷",
    )
    temperature: Mapped[Decimal] = mapped_column(
        Numeric(3, 2), nullable=False, default=Decimal("0.00"),
        comment="실행 temperature — 재현성 위해 항상 0",
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending",
        comment="진행 상태: pending/running/completed/failed",
    )
    total_runs: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
        comment="생성된 하위 run 총 개수 (= 모델 수)",
    )
    completed_runs: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
        comment="완료된 하위 run 개수 (진행률 산출용)",
    )
    estimated_cost_usd: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 6), nullable=True,
        comment="실행 전 추정 비용(USD) — 실제 비용과 대조용",
    )
    user_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True,
        comment="스윕 소유자 — 미소유자에게는 404로 은닉",
    )
    error_message: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="스윕 수준 실패 사유 (개별 run 실패는 evaluation_run에 기록)",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, comment="생성 시각"
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="전체 완료 시각"
    )
