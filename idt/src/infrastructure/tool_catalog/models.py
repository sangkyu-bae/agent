"""SQLAlchemy ORM 모델: tool_catalog."""
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.persistence.models.base import Base


class ToolCatalogModel(Base):
    __tablename__ = "tool_catalog"
    __table_args__ = (
        UniqueConstraint("tool_id", name="uq_tool_id"),
        Index("ix_source_active", "source", "is_active"),
        Index("ix_mcp_server", "mcp_server_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tool_id: Mapped[str] = mapped_column(String(150), nullable=False)
    source: Mapped[str] = mapped_column(
        Enum("internal", "mcp", name="tool_source_enum"), nullable=False
    )
    mcp_server_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("mcp_server_registry.id", ondelete="CASCADE"),
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    requires_env: Mapped[dict | None] = mapped_column(JSON)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
