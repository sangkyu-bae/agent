"""SQLAlchemy ORM 모델: llm_model.

LLM-MODEL-REG-001 §6-1.
"""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.persistence.models.base import Base


class LlmModelModel(Base):
    __tablename__ = "llm_model"
    __table_args__ = (
        UniqueConstraint("provider", "model_name", name="uq_provider_model"),
        Index("ix_is_active", "is_active"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model_name: Mapped[str] = mapped_column(String(150), nullable=False)
    display_name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    api_key_env: Mapped[str] = mapped_column(String(100), nullable=False)
    max_tokens: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    # AGENT-OBS-001 §5-0: 가격 컬럼 (V022 마이그레이션과 매핑)
    input_price_per_1k_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    output_price_per_1k_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    pricing_updated_at: Mapped[datetime | None] = mapped_column(DateTime)
