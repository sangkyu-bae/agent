"""agent_memory 테이블 SQLAlchemy 모델 (V050, agent-memory Design §3-1)."""
from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, Index, Integer, SmallInteger, String

from src.infrastructure.persistence.models.base import Base


class MemoryModel(Base):
    __tablename__ = "agent_memory"
    __table_args__ = (Index("idx_memory_user_status", "user_id", "status"),)

    # SQLite(테스트)는 INTEGER PK만 autoincrement — MySQL은 BIGINT 유지
    id = Column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    scope = Column(String(10), nullable=False, default="user")
    user_id = Column(String(255), nullable=True)
    tier = Column(SmallInteger, nullable=False, default=0)
    mem_type = Column(String(20), nullable=False)
    content = Column(String(500), nullable=False)
    source_run_id = Column(String(64), nullable=True)
    confidence = Column(SmallInteger, nullable=False, default=100)
    status = Column(String(10), nullable=False, default="active")
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
