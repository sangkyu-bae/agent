"""RAGAS 평가 SQLAlchemy ORM 모델."""
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.persistence.models.base import Base


class EvaluationRunModel(Base):
    __tablename__ = "evaluation_run"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    eval_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    target_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # agent-model-benchmark Design §3.3: 모델 차원. V068 매핑.
    # FK 제약은 DDL에만 둔다 — ai_run.llm_model_id(agent_run.py:25) 선례와 동일.
    # ORM에 교차 모듈 ForeignKey를 넣으면 부분 임포트 상태의 create_all 픽스처가
    # NoReferencedTableError로 깨진다.
    sweep_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True,
        comment="소속 스윕 ID — NULL이면 단독 실행(기존 배치 평가)",
    )
    llm_model_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True,
        comment="이 run에서 사용한 피평가 LLM 모델 ID — 모델 비교의 축",
    )
    user_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True,
        comment="실행자 사용자 ID (NULL=소유권 도입 이전 레거시, admin만 열람)",
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    total_cases: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    results: Mapped[list["EvaluationResultModel"]] = relationship(
        "EvaluationResultModel",
        back_populates="run",
        cascade="all, delete-orphan",
    )


class EvaluationResultModel(Base):
    __tablename__ = "evaluation_result"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("evaluation_run.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # agent-model-benchmark Design D11: ai_run 조인 키. FK를 걸지 않는다 —
    # 관측 데이터의 보존정책 삭제가 평가 결과를 지우면 안 되기 때문. V068 매핑.
    ai_run_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True,
        comment="이 케이스 실행의 ai_run.id — 토큰·비용·지연 회수 조인 키 (FK 없음)",
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    ground_truth: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    contexts: Mapped[list] = mapped_column(JSON, nullable=False)
    tools_used: Mapped[list | None] = mapped_column(
        JSON, nullable=True,
        comment="실제 호출된 도구 이름 배열 — expected_tools와 집합 비교(F1 산출)",
    )
    metrics: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    run: Mapped["EvaluationRunModel"] = relationship(back_populates="results")


class TestsetModel(Base):
    __tablename__ = "evaluation_testset"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True,
        comment="소유자 사용자 ID (NULL=소유권 도입 이전 레거시, admin만 열람)",
    )
    cases: Mapped[list] = mapped_column(JSON, nullable=False)
    case_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
