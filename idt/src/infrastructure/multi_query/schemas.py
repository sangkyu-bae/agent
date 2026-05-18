"""Structured output schemas for Multi-Query generation."""
from pydantic import BaseModel, Field


class MultiQueryGeneratorOutput(BaseModel):
    """LLM Multi-Query 생성 결과."""

    queries: list[str] = Field(
        ...,
        description="검색 최적화된 변형 쿼리 리스트",
    )
