"""SQLAlchemy ORM 모델: middleware_catalog + agent_middleware (V056)."""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.persistence.models.base import Base


class MiddlewareCatalogModel(Base):
    __tablename__ = "middleware_catalog"
    __table_args__ = (
        UniqueConstraint("middleware_type", name="uq_middleware_catalog_type"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, comment="PK (UUID)"
    )
    middleware_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment=(
            "미들웨어 유형 식별자 "
            "(model_retry/tool_retry/model_fallback/model_call_limit)"
        ),
    )
    name: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="표시 이름 (폼·관리자 화면)"
    )
    description: Mapped[str] = mapped_column(
        String(500), nullable=False, comment="설명 — 폼 안내 문구"
    )
    is_builtin: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        comment=(
            "빌트인 여부 — 에이전트 생성 시 기본 적용(사용자 해제 가능) · "
            "관리자 토글"
        ),
    )
    is_enforced: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        comment=(
            "강제 여부 — 실행 시 에이전트 스냅샷과 무관하게 병합 적용"
            "(사용자 해제 불가) · 관리자 토글"
        ),
    )
    default_config: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        comment=(
            "기본 설정값 (관리자 편집) — 런타임 설정 단일 소스 · "
            "1차는 에이전트별 오버라이드 없음"
        ),
    )
    is_active: Mapped[bool] = mapped_column(
        default=True,
        nullable=False,
        comment="활성 여부 — 비활성 시 빌트인/강제 판정에서 제외",
    )
    sort_order: Mapped[int] = mapped_column(
        default=0, nullable=False, comment="적용 순서 (미들웨어 체인 순서)"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, comment="생성 시각"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, comment="수정 시각"
    )


class AgentMiddlewareModel(Base):
    __tablename__ = "agent_middleware"
    __table_args__ = (
        UniqueConstraint("agent_id", "middleware_type", name="uq_agent_middleware"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, comment="PK (UUID)"
    )
    agent_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("agent_definition.id", ondelete="CASCADE"),
        nullable=False,
        comment="에이전트 FK (agent_definition.id)",
    )
    middleware_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="적용 미들웨어 유형 (middleware_catalog.middleware_type 참조값)",
    )
    config: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="에이전트별 설정 오버라이드 — 1차 미사용(NULL) · 후속 확장 예약",
    )
    sort_order: Mapped[int] = mapped_column(
        default=0, nullable=False, comment="적용 순서 (스냅샷 시점 카탈로그 순서)"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, comment="생성 시각"
    )
