"""SQLAlchemy ORM 모델: approval_request (V071).

DDL COMMENT 규칙 (V054+): 테이블·전 컬럼 comment= 동반 필수.
Design Ref: §3.3.
"""
from datetime import datetime

from sqlalchemy import JSON, DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.persistence.models.base import Base

# MySQL 에서는 LONGTEXT, 그 외 방언에서는 TEXT 로 컴파일된다.
# 이 모델이 공유 Base.metadata 에 등록되므로, MySQL 전용 타입을 그대로 쓰면
# sqlite 로 create_all 하는 통합 테스트가 전부 깨진다 (blueprint/models.py 선례).
_LONG_TEXT = Text().with_variant(LONGTEXT(), "mysql")


class ApprovalRequestModel(Base):
    __tablename__ = "approval_request"
    __table_args__ = (
        # Design Ref: §3.3 — claim_due 가 (status, execute_after) 로 좁히므로
        # 같은 순서의 복합 인덱스
        Index("ix_approval_request_due", "status", "execute_after"),
        Index("ix_approval_request_agent_status", "agent_id", "status"),
        {"comment": "에이전트 부작용 도구의 사람 승인 요청 및 런 재개 스냅샷 (approval-gate)"},
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, comment="승인 요청 ID (uuid4)"
    )
    run_id: Mapped[str] = mapped_column(
        String(36), nullable=False, index=True,
        comment="게이트가 발동한 에이전트 런 ID (ai_run 연결)",
    )
    # FK 제약은 DDL(V071)에만 두고 ORM 모델에는 선언하지 않는다.
    # ORM 에 두면 공유 Base.metadata 가 agent_definition Table 해석을 강제하고,
    # 그 테이블의 departments FK 까지 연쇄로 요구해 sqlite 로 create_all 하는
    # 통합 테스트들이 NoReferencedTableError 로 무너진다(측정: 91 errors).
    # 참조 무결성은 DB 제약이 보장하므로 ORM 선언은 불필요하다.
    agent_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        comment="대상 에이전트 ID (agent_definition.id)",
    )
    requested_by: Mapped[str] = mapped_column(
        String(100), nullable=False,
        comment="런 실행 신원. 스케줄·웹훅이면 시스템 식별자",
    )
    worker_id: Mapped[str] = mapped_column(
        String(100), nullable=False,
        comment="게이트가 걸린 워커 ID. 재개 시 결과 주입 대상",
    )
    tool_id: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="차단된 도구 ID (tool_catalog.tool_id)"
    )
    tool_args: Mapped[dict] = mapped_column(
        JSON, nullable=False, comment="차단 시점 도구 인자. 집행 시 그대로 사용"
    )
    draft: Mapped[str] = mapped_column(
        _LONG_TEXT, nullable=False,
        comment="사람이 검토할 초안 (이메일 본문·변경 내역 등)",
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False,
        comment="상태 (pending|approved|scheduled|executed|rejected|expired|failed)",
    )
    idempotency_key: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True,
        comment="이중 집행 차단 키 (run_id:worker_id:tool_call_id)",
    )
    snapshot_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1,
        comment="resume_snapshot 포맷 버전. 불일치 시 재개 거부",
    )
    agent_updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False,
        comment="적재 시점 agent_definition.updated_at. 재개 전 대조용",
    )
    resume_snapshot: Mapped[str] = mapped_column(
        _LONG_TEXT, nullable=False,
        comment="워커 진입 시점 SupervisorState 직렬화 JSON (상한 256KB)",
    )
    execute_after: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True,
        comment="집행 예정 시각(UTC). NULL 이면 승인 즉시 집행",
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False,
        comment="만료 시각(UTC). 경과 시 expired 로 전이되며 승인 불가",
    )
    decided_by: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="승인·거절한 사용자 ID"
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="승인·거절 시각(UTC)"
    )
    decision_reason: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="거절 사유. 재개 시 에이전트에 주입된다"
    )
    executed_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="집행 완료 시각(UTC)"
    )
    error_message: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="집행 실패 사유. 자동 재시도는 하지 않는다"
    )
    seen_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True,
        comment="NULL=미확인. 벨 배지 기준 (agent_background_job 동형)",
    )
    request_id: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="적재 요청의 추적 ID (로그 상관관계)"
    )
    # V074 (Check G1): DDL COMMENT 와 동일 문구 유지.
    session_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True,
        comment="재개 답변을 저장할 원래 대화 세션 ID. NULL 이면 재개 답변을 저장하지 않는다(구버전 행)",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, comment="생성 시각(UTC)"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, comment="수정 시각(UTC)"
    )
