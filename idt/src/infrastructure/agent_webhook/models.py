"""SQLAlchemy ORM 모델: agent_webhook (V057), agent_webhook_delivery (V058)."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.persistence.models.base import Base


class AgentWebhookModel(Base):
    __tablename__ = "agent_webhook"
    __table_args__ = {
        "comment": (
            "에이전트 웹훅 채널 — 외부 시스템 inbound 호출 인증(시크릿)과 "
            "outbound 발송 설정 (소유자 opt-in)"
        ),
    }

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, comment="PK (UUID)"
    )
    agent_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("agent_definition.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        comment="에이전트 FK (agent_definition.id) — 에이전트당 1채널",
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="inbound 수신 활성 여부 — false면 호출 404",
    )
    secret: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="시크릿 원문 — HMAC 서명 재계산용 (D2). 조회 응답·로그 노출 금지, hint만 노출",
    )
    secret_hint: Mapped[str] = mapped_column(
        String(8), nullable=False, comment="시크릿 끝 4자 — UI 식별용 표시"
    )
    outbound_url: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="outbound 발송 대상 URL (M2, http/https만) — NULL이면 미등록",
    )
    outbound_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="outbound 발송 활성 여부 (M2)",
    )
    created_by: Mapped[str] = mapped_column(
        String(36), nullable=False, comment="채널 생성자 user_id (감사용)"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, comment="생성 시각"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, comment="수정 시각"
    )


class AgentWebhookDeliveryModel(Base):
    __tablename__ = "agent_webhook_delivery"
    __table_args__ = {
        "comment": (
            "웹훅 outbound 발송 이력 — 실패 진단·전송 상태 노출용 (불변 레코드)"
        ),
    }

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, comment="PK (UUID)"
    )
    agent_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("agent_definition.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="에이전트 FK (agent_definition.id)",
    )
    run_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        comment="연계 ai_run id — 실행 관측 조인용 (실행측 미발급 시 NULL)",
    )
    url: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="발송 대상 URL (발송 시점 스냅샷 — 이후 변경과 무관)",
    )
    trigger_source: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="발송 계기 (schedule | webhook)"
    )
    success: Mapped[bool] = mapped_column(
        Boolean, nullable=False, comment="최종 성공 여부 (재시도 소진 후 판정)"
    )
    status_code: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="마지막 응답 HTTP 상태코드 (연결 실패 시 NULL)",
    )
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="총 시도 횟수 (1~4)"
    )
    error: Mapped[str | None] = mapped_column(
        String(2000),
        nullable=True,
        comment="마지막 오류 메시지 (성공 시 NULL)",
    )
    duration_ms: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="총 소요 시간 ms (재시도·백오프 포함)"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, comment="기록 시각"
    )
