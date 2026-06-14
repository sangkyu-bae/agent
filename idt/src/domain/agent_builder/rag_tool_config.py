"""RagToolConfig: RAG 도구 커스텀 설정 Value Object + 검증 정책."""
import re
from dataclasses import dataclass, field
from typing import Literal

SearchMode = Literal["hybrid", "vector_only", "bm25_only"]

_VALID_SEARCH_MODES = {"hybrid", "vector_only", "bm25_only"}
_TOOL_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


def sanitize_tool_name(name: str) -> str:
    """OpenAI tool name 패턴(^[a-zA-Z0-9_-]+$)에 맞도록 변환."""
    if _TOOL_NAME_PATTERN.match(name):
        return name
    sanitized = re.sub(r"[^a-zA-Z0-9_-]", "_", name)
    sanitized = re.sub(r"_+", "_", sanitized)
    return sanitized.strip("_") or "unnamed_tool"


@dataclass(frozen=True)
class RagToolConfig:
    """에이전트별 RAG 도구 설정 Value Object."""

    collection_name: str | None = None
    es_index: str | None = None
    metadata_filter: dict[str, str] = field(default_factory=dict)
    top_k: int = 5
    search_mode: SearchMode = "hybrid"
    rrf_k: int = 60
    tool_name: str = "internal_document_search"
    tool_description: str = (
        "내부 문서에서 관련 정보를 검색합니다. "
        "질문에 대한 내부 문서 정보가 필요할 때 사용하세요."
    )
    # 벡터 코사인 유사도 컷오프 임계값.
    #   None = 미설정 → ToolFactory가 전역 기본값(settings) 적용
    #   0.0  = 명시적 비활성 (모든 hit 통과, 기존 동작)
    #   0~1  = 코사인 유사도 하한
    score_threshold: float | None = None

    def __post_init__(self) -> None:
        if not 1 <= self.top_k <= 20:
            raise ValueError(f"top_k must be 1~20, got {self.top_k}")
        if self.search_mode not in _VALID_SEARCH_MODES:
            raise ValueError(f"Invalid search_mode: {self.search_mode}")
        if self.rrf_k < 1:
            raise ValueError(f"rrf_k must be >= 1, got {self.rrf_k}")
        if self.score_threshold is not None and not (
            0.0 <= self.score_threshold <= 1.0
        ):
            raise ValueError(
                f"score_threshold must be 0.0~1.0, got {self.score_threshold}"
            )


class RagToolConfigPolicy:
    MAX_METADATA_FILTERS = 10
    MAX_TOOL_NAME_LENGTH = 100
    MAX_TOOL_DESCRIPTION_LENGTH = 500

    @classmethod
    def validate(cls, config: RagToolConfig) -> None:
        if len(config.metadata_filter) > cls.MAX_METADATA_FILTERS:
            raise ValueError(
                f"metadata_filter max {cls.MAX_METADATA_FILTERS} entries"
            )
        if len(config.tool_name) > cls.MAX_TOOL_NAME_LENGTH:
            raise ValueError(
                f"tool_name max {cls.MAX_TOOL_NAME_LENGTH} chars"
            )
        if len(config.tool_description) > cls.MAX_TOOL_DESCRIPTION_LENGTH:
            raise ValueError(
                f"tool_description max {cls.MAX_TOOL_DESCRIPTION_LENGTH} chars"
            )
