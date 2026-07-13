"""SQLAlchemy ORM 모델: agent_definition, agent_tool."""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.persistence.models.base import Base


class AgentDefinitionModel(Base):
    __tablename__ = "agent_definition"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    flow_hint: Mapped[str | None] = mapped_column(Text)
    llm_model_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("llm_model.id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    visibility: Mapped[str] = mapped_column(
        String(20), nullable=False, default="private", index=True
    )
    department_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("departments.id", ondelete="SET NULL"),
        nullable=True,
    )
    temperature: Mapped[float] = mapped_column(nullable=False, default=0.70)
    # agent-recursion-limit V045: supervisor 반복 한도 (기본 25, 범위는 도메인 정책 검증).
    max_iterations: Mapped[int] = mapped_column(nullable=False, default=25)
    # agent-user-context V028: 향후 system bot이 user 컨텍스트 prepend를 거부하기 위한 슬롯.
    # 현재 PR은 전역 자동 prepend (DEFAULT TRUE).
    include_user_context: Mapped[bool] = mapped_column(
        nullable=False, default=True
    )
    forked_from: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True
    )
    forked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    tools: Mapped[list["AgentToolModel"]] = relationship(
        "AgentToolModel",
        back_populates="agent",
        cascade="all, delete-orphan",
        order_by="AgentToolModel.sort_order",
        foreign_keys="[AgentToolModel.agent_id]",
    )


class AgentToolModel(Base):
    __tablename__ = "agent_tool"
    __table_args__ = (
        UniqueConstraint("agent_id", "worker_id", name="uq_agent_worker"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    agent_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("agent_definition.id", ondelete="CASCADE"),
        nullable=False,
    )
    tool_id: Mapped[str] = mapped_column(String(100), nullable=False)
    worker_id: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tool_config: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    worker_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="tool"
    )
    ref_agent_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("agent_definition.id", ondelete="SET NULL"),
        nullable=True,
    )
    category: Mapped[str | None] = mapped_column(
        String(20), nullable=True, default=None,
    )

    agent: Mapped["AgentDefinitionModel"] = relationship(
        "AgentDefinitionModel", back_populates="tools",
        foreign_keys=[agent_id],
    )
