from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, Index, JSON, String

from src.infrastructure.persistence.models.base import Base


class CollectionActivityLogModel(Base):
    __tablename__ = "collection_activity_log"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    collection_name = Column(String(100), nullable=False, index=True)
    action = Column(String(30), nullable=False, index=True)
    user_id = Column(String(100), nullable=True, index=True)
    detail = Column(JSON, nullable=True)
    created_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, index=True
    )
