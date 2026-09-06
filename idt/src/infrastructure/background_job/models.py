"""SQLAlchemy ORM 모델: agent_background_job (V060, V070).

DDL COMMENT 규칙 (V054+): 테이블·전 컬럼 comment= 동반 필수.
"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.persistence.models.base import Base


class AgentBackgroundJobModel(Base):
    __tablename__ = "agent_background_job"
    # Design Ref: §3.3 — 목록·집계가 (user_id, deleted_at) 으로 좁힌 뒤
    # queued_at 으로 정렬하므로 같은 순서의 복합 인덱스 (V070)
    __table_args__ = (
        Index(
            "ix_agent_background_job_user_deleted_queued",
            "user_id",
            "deleted_at",
            "queued_at",
        ),
        {"comment": "ad-hoc 백그라운드 작업 큐·이력 (background-jobs)"},
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, comment="작업 ID (uuid4)"
    )
    user_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="등록 사용자 ID (실행 신원·조회 인가 기준)",
    )
    agent_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("agent_definition.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="실행 대상 에이전트 ID",
    )
    source: Mapped[str] = mapped_column(
        String(10), nullable=False, default="chat", comment="등록 경로 (chat|api)"
    )
    query: Mapped[str] = mapped_column(
        Text, nullable=False, comment="실행할 사용자 질문"
    )
    session_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        comment="대화 세션 ID (미지정 시 실행 시 생성 후 역기입)",
    )
    run_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, comment="ai_run 연결 (AGENT-OBS-001)"
    )
    status: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="queued",
        index=True,
        comment="상태 (queued|running|success|failed)",
    )
    error_message: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="실패 사유 (2000자 절단)"
    )
    seen_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        comment="사용자 결과 확인 시각 (NULL=미확인, 벨 배지 집계 기준)",
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        comment="소프트 삭제 시각 (UTC). NULL=활성, 값 있으면 목록·집계에서 제외",
    )
    queued_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, comment="등록 시각 (UTC, claim 순서 기준)"
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="실행 시작 시각 (UTC)"
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="실행 종료 시각 (UTC)"
    )
    request_id: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="등록 요청 추적 ID"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, comment="생성 시각 (UTC)"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, comment="수정 시각 (UTC)"
    )
