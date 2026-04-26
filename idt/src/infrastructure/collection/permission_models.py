from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.persistence.models.base import Base


class CollectionPermissionModel(Base):
    __tablename__ = "collection_permissions"
    __table_args__ = (
        Index("ix_perm_owner", "owner_id"),
        Index("ix_perm_department", "department_id"),
        Index("ix_perm_scope", "scope"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    collection_name: Mapped[str] = mapped_column(
        String(100), nullable=False, unique=True
    )
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    scope: Mapped[str] = mapped_column(
        Enum("PERSONAL", "DEPARTMENT", "PUBLIC", name="collection_scope"),
        nullable=False,
        default="PERSONAL",
    )
    department_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("departments.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )
