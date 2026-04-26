from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.persistence.models.base import Base


class EmbeddingModelTable(Base):
    __tablename__ = "embedding_model"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model_name: Mapped[str] = mapped_column(
        String(100), nullable=False, unique=True
    )
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    vector_dimension: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
