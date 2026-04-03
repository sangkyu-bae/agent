"""Morphological analyzer interface for domain layer.

구현체는 infrastructure layer에 위치한다.
외부 NLP 라이브러리(kiwipiepy 등) 의존 금지.
"""
from abc import ABC, abstractmethod

from src.domain.morph.schemas import MorphAnalysisResult


class MorphAnalyzerInterface(ABC):
    """형태소 분석기 추상 인터페이스."""

    @abstractmethod
    def analyze(self, text: str) -> MorphAnalysisResult:
        """텍스트에 대해 형태소 분석을 수행한다.

        Args:
            text: 분석할 텍스트

        Returns:
            분석된 토큰과 원본 텍스트를 포함한 결과
        """

    def extract_nouns(self, text: str) -> list[str]:
        """명사 표면형 목록을 반환한다.

        analyze()를 기반으로 동작하는 편의 메서드.
        CHUNK-IDX-001의 KeywordExtractorInterface 연결 포인트.

        Args:
            text: 분석할 텍스트

        Returns:
            명사(NNG/NNP/NNB) 표면형 문자열 목록
        """
        return self.analyze(text).noun_surfaces
