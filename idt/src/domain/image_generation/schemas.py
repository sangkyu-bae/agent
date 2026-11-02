"""LLM 출력 전용 스키마 — image-generation-tool Design §3.1 (strict structured output).

워커 LLM이 사용자 요청·대화 문맥·첨부 목록에서 생성 요청을 구조화한다.
서버가 계산하는 값(file_id·비용 등)은 여기에 두지 않는다 (llm-output-trust-boundary).
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ImageRequestDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(
        description=(
            "생성 모델에 보낼 프롬프트. "
            "사용자 요청의 의도·스타일·포함할 텍스트를 구체적으로"
        )
    )
    size: Literal["1024x1024", "1536x1024", "1024x1536"] = Field(
        description="정사각형 1024x1024 / 가로 1536x1024 / 세로 1024x1536"
    )
    quality: Literal["standard", "hd"] = Field(
        description="표준 standard 또는 고품질 hd"
    )
    mode: Literal["generate", "edit"] = Field(
        description="새로 생성 generate / 첨부 이미지를 바탕으로 편집 edit"
    )
    source_image_index: int | None = Field(
        description="edit 일 때 사용할 첨부 이미지 순번(0부터). generate 면 null"
    )
    reason: str = Field(description="왜 이 모드·크기를 골랐는지 한 줄")
