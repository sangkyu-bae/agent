"""SQLAlchemy ORM 모델: agent_alert_receiver, agent_alert_receipt (V099).

Design Ref: firewall-agent design §3.3. 컬럼 COMMENT 는 마이그레이션과 같게 둔다.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

# FK 대상 테이블을 메타데이터에 등록한다 (단독 create_all·테스트에서 참조 해석).
from src.infrastructure.agent_builder.models import AgentDefinitionModel  # noqa: F401
from src.infrastructure.persistence.models.base import Base


class AgentAlertReceiverModel(Base):
    __tablename__ = "agent_alert_receiver"
    __table_args__ = {"comment": "에이전트별 알림(Alertmanager 웹훅) 수신 설정"}

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, comment="수신 설정 ID"
    )
    agent_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("agent_definition.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        comment="대상 에이전트 (에이전트당 1개)",
    )
    user_id: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="설정자 = 실행 신원"
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, comment="수신 켜짐 여부"
    )
    skip_when_busy: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="진행 중·승인 대기 건이 있으면 실행하지 않음",
    )
    token_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="Bearer 토큰 sha256 hex"
    )
    token_hint: Mapped[str] = mapped_column(
        String(8), nullable=False, comment="토큰 끝 4자 (식별용)"
    )
    instruction_prefix: Mapped[str] = mapped_column(
        String(300), nullable=False, default="", comment="지침문 맨 앞에 붙일 문구"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, comment="생성 시각 (UTC)"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, comment="수정 시각 (UTC)"
    )


class AgentAlertReceiptModel(Base):
    __tablename__ = "agent_alert_receipt"
    __table_args__ = (
        Index(
            "ix_agent_alert_receipt_dedupe",
            "receiver_id",
            "group_key_hash",
            "received_at",
        ),
        {"comment": "알림 수신 이력 (결과·중복 판정 근거)"},
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, comment="수신 ID")
    receiver_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("agent_alert_receiver.id", ondelete="CASCADE"),
        nullable=False,
        comment="수신 설정 ID",
    )
    agent_id: Mapped[str] = mapped_column(
        String(36), nullable=False, comment="대상 에이전트 (비정규화)"
    )
    group_key_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="groupKey sha256 hex"
    )
    fingerprints_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="발화 알림 fingerprint 집합 sha256 hex"
    )
    firing_count: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="발화 알림 수"
    )
    result: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        comment="enqueued|duplicate|resolved_only|disabled|skipped_busy|invalid_payload",
    )
    skip_reason: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="skipped_busy 사유"
    )
    job_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, comment="등록된 백그라운드 잡 ID"
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, comment="수신 시각 (UTC)"
    )
    request_id: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="요청 추적 ID"
    )
