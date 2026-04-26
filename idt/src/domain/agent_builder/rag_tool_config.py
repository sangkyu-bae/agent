"""RagToolConfig: RAG 도구 커스텀 설정 Value Object + 검증 정책."""
from dataclasses import dataclass, field
from typing import Literal

SearchMode = Literal["hybrid", "vector_only", "bm25_only"]

_VALID_SEARCH_MODES = {"hybrid", "vector_only", "bm25_only"}


@dataclass(frozen=True)
class RagToolConfig:
    """에이전트별 RAG 도구 설정 Value Object."""

    collection_name: str | None = None
    es_index: str | None = None
    metadata_filter: dict[str, str] = field(default_factory=dict)
    top_k: int = 5
    search_mode: SearchMode = "hybrid"
    rrf_k: int = 60
    tool_name: str = "내부 문서 검색"
    tool_description: str = (
        "내부 문서에서 관련 정보를 검색합니다. "
        "질문에 대한 내부 문서 정보가 필요할 때 사용하세요."
    )

    def __post_init__(self) -> None:
        if not 1 <= self.top_k <= 20:
            raise ValueError(f"top_k must be 1~20, got {self.top_k}")
        if self.search_mode not in _VALID_SEARCH_MODES:
            raise ValueError(f"Invalid search_mode: {self.search_mode}")
        if self.rrf_k < 1:
            raise ValueError(f"rrf_k must be >= 1, got {self.rrf_k}")


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
