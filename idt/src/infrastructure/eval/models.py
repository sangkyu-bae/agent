"""message_feedback 테이블 SQLAlchemy 모델 (V052, agent-eval-gate)."""
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Index,
    Integer,
    String,
    UniqueConstraint,
)

from src.infrastructure.persistence.models.base import Base


class MessageFeedbackModel(Base):
    __tablename__ = "message_feedback"
    __table_args__ = (
        UniqueConstraint("message_id", "user_id", name="uq_feedback_msg_user"),
        Index("idx_feedback_agent_rating", "agent_id", "rating"),
    )

    id = Column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    message_id = Column(BigInteger, nullable=False)
    user_id = Column(String(255), nullable=False)
    agent_id = Column(String(64), nullable=False)
    rating = Column(String(4), nullable=False)
    comment = Column(String(500), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
