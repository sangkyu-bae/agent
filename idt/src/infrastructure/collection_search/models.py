from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, Float, Integer, String, Text

from src.infrastructure.persistence.models.base import Base


class SearchHistoryModel(Base):
    __tablename__ = "search_history"

    # SQLite(테스트)는 INTEGER PK만 autoincrement — MySQL은 BIGINT 유지
    id = Column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    user_id = Column(String(100), nullable=False, index=True)
    collection_name = Column(String(100), nullable=False)
    document_id = Column(String(100), nullable=True)
    # kb-retrieval-test D6: KB 단위 검색만 값 존재 (V049)
    kb_id = Column(String(64), nullable=True)
    query = Column(Text, nullable=False)
    bm25_weight = Column(Float, nullable=False, default=0.5)
    vector_weight = Column(Float, nullable=False, default=0.5)
    top_k = Column(Integer, nullable=False, default=10)
    result_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
