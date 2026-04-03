"""SQLAlchemy ORM: middleware_agent, middleware_agent_tool, middleware_config."""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.persistence.models.base import Base


class MiddlewareAgentModel(Base):
    __tablename__ = "middleware_agent"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False, default="gpt-4o")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    tools: Mapped[list["MiddlewareAgentToolModel"]] = relationship(
        "MiddlewareAgentToolModel",
        back_populates="agent",
        cascade="all, delete-orphan",
        order_by="MiddlewareAgentToolModel.sort_order",
    )
    middleware_configs: Mapped[list["MiddlewareConfigModel"]] = relationship(
        "MiddlewareConfigModel",
        back_populates="agent",
        cascade="all, delete-orphan",
        order_by="MiddlewareConfigModel.sort_order",
    )


class MiddlewareAgentToolModel(Base):
    __tablename__ = "middleware_agent_tool"
    __table_args__ = (
        UniqueConstraint("agent_id", "tool_id", name="uq_mw_agent_tool"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("middleware_agent.id", ondelete="CASCADE"), nullable=False
    )
    tool_id: Mapped[str] = mapped_column(String(100), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    agent: Mapped["MiddlewareAgentModel"] = relationship(
        "MiddlewareAgentModel", back_populates="tools"
    )


class MiddlewareConfigModel(Base):
    __tablename__ = "middleware_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("middleware_agent.id", ondelete="CASCADE"), nullable=False
    )
    middleware_type: Mapped[str] = mapped_column(String(100), nullable=False)
    config_json: Mapped[dict | None] = mapped_column(JSON)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    agent: Mapped["MiddlewareAgentModel"] = relationship(
        "MiddlewareAgentModel", back_populates="middleware_configs"
    )
