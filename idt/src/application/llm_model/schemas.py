"""LlmModel API Pydantic schemas.

LLM-MODEL-REG-001 §5-1 + M4 (가격 필드 additive 노출 + UpdatePricingRequest).
"""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from src.domain.llm_model.entity import LlmModel


class CreateLlmModelRequest(BaseModel):
    provider: str = Field(..., max_length=50)
    model_name: str = Field(..., max_length=150)
    display_name: str = Field(..., max_length=150)
    description: str | None = None
    api_key_env: str = Field(..., max_length=100)
    max_tokens: int | None = None
    is_active: bool = True
    is_default: bool = False


class UpdateLlmModelRequest(BaseModel):
    display_name: str | None = Field(None, max_length=150)
    description: str | None = None
    max_tokens: int | None = None
    is_active: bool | None = None
    is_default: bool | None = None


class UpdatePricingRequest(BaseModel):
    """M4: PATCH /api/v1/llm-models/{id}/pricing body."""

    input_price_per_1k_usd: Decimal = Field(..., ge=0)
    output_price_per_1k_usd: Decimal = Field(..., ge=0)


class LlmModelResponse(BaseModel):
    id: str
    provider: str
    model_name: str
    display_name: str
    description: str | None
    max_tokens: int | None
    is_active: bool
    is_default: bool
    # ── M4 additive (옵셔널 — 기존 frontend 영향 0) ───────────────────
    input_price_per_1k_usd: Decimal | None = None
    output_price_per_1k_usd: Decimal | None = None
    pricing_updated_at: datetime | None = None

    @classmethod
    def from_domain(cls, model: LlmModel) -> "LlmModelResponse":
        return cls(
            id=model.id,
            provider=model.provider,
            model_name=model.model_name,
            display_name=model.display_name,
            description=model.description,
            max_tokens=model.max_tokens,
            is_active=model.is_active,
            is_default=model.is_default,
            input_price_per_1k_usd=model.input_price_per_1k_usd,
            output_price_per_1k_usd=model.output_price_per_1k_usd,
            pricing_updated_at=model.pricing_updated_at,
        )


class LlmModelListResponse(BaseModel):
    models: list[LlmModelResponse]
