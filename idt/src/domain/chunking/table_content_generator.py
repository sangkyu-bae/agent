"""표 콘텐츠를 검색 최적화 텍스트로 변환하는 인터페이스."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True)
class TableConversionResult:
    """표 변환 결과."""

    original_markdown: str
    search_optimized_text: str
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class TableSpan:
    """텍스트 내 표 위치."""

    start: int
    end: int


@dataclass(frozen=True)
class PreprocessResult:
    """전처리 결과."""

    parent_text: str
    child_text: str
    table_count: int
    metadata: dict = field(default_factory=dict)


class TableContentGenerator(ABC):
    """표 → 검색 최적화 텍스트 변환 인터페이스."""

    @abstractmethod
    def generate(
        self, table_markdown: str, section_title: str
    ) -> TableConversionResult:
        pass
