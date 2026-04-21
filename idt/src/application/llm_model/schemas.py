"""LlmModel API Pydantic schemas.

LLM-MODEL-REG-001 §5-1.
"""
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


class LlmModelResponse(BaseModel):
    id: str
    provider: str
    model_name: str
    display_name: str
    description: str | None
    max_tokens: int | None
    is_active: bool
    is_default: bool

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
        )


class LlmModelListResponse(BaseModel):
    models: list[LlmModelResponse]
