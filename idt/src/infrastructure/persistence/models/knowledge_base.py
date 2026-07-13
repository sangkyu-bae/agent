from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.persistence.models.base import Base


class KnowledgeBaseModel(Base):
    __tablename__ = "knowledge_base"
    __table_args__ = (
        Index("idx_kb_owner_status", "owner_id", "status"),
        Index("idx_kb_scope_status", "scope", "status"),
        Index("idx_kb_department", "department_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    owner_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=False
    )
    scope: Mapped[str] = mapped_column(
        Enum("PERSONAL", "DEPARTMENT", "PUBLIC", name="knowledge_base_scope"),
        nullable=False,
        default="PERSONAL",
    )
    department_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("departments.id", ondelete="SET NULL"),
        nullable=True,
    )
    collection_name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active"
    )
    # clause-aware-chunking (Design D5): opt-in + late-binding 오버라이드
    use_clause_chunking: Mapped[bool] = mapped_column(
        Integer, nullable=False, default=0
    )
    chunking_profile_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("chunking_profile.id"),
        nullable=True,
    )
    chunk_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chunk_overlap: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )
