"""SQLAlchemy ORM 모델: user_agent_subscription."""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.persistence.models.base import Base


class UserAgentSubscriptionModel(Base):
    __tablename__ = "user_agent_subscription"
    __table_args__ = (
        UniqueConstraint("user_id", "agent_id", name="uq_user_agent_sub"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )
    agent_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("agent_definition.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    is_pinned: Mapped[bool] = mapped_column(nullable=False, default=False)
    subscribed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
