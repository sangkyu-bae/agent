"""Keyword extractor interface for domain layer.

구현체는 infrastructure layer에 위치한다.
외부 API 호출 금지.
"""
from abc import ABC, abstractmethod

from src.domain.keyword.schemas import KeywordExtractionResult


class KeywordExtractorInterface(ABC):
    """텍스트에서 키워드를 추출하는 인터페이스."""

    @abstractmethod
    def extract(self, text: str, top_n: int = 10) -> KeywordExtractionResult:
        """텍스트에서 상위 top_n 키워드를 추출한다.

        Args:
            text: 분석할 텍스트
            top_n: 반환할 최대 키워드 수

        Returns:
            키워드 목록과 빈도수를 포함한 결과
        """
