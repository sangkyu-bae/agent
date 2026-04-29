from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, Float, Integer, String, Text

from src.infrastructure.persistence.models.base import Base


class SearchHistoryModel(Base):
    __tablename__ = "search_history"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(String(100), nullable=False, index=True)
    collection_name = Column(String(100), nullable=False)
    document_id = Column(String(100), nullable=True)
    query = Column(Text, nullable=False)
    bm25_weight = Column(Float, nullable=False, default=0.5)
    vector_weight = Column(Float, nullable=False, default=0.5)
    top_k = Column(Integer, nullable=False, default=10)
    result_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
