"""Morphological analysis domain schemas."""
from dataclasses import dataclass


@dataclass(frozen=True)
class MorphToken:
    """형태소 분석 결과의 단일 토큰.

    Attributes:
        surface: 표면형 (원문 그대로)
        pos: 품사 태그명 (예: "NNG", "VV", "VA")
        start: 원본 텍스트에서의 시작 문자 위치
        length: 문자 길이
    """

    surface: str
    pos: str
    start: int
    length: int


_NOUN_TAGS = frozenset({"NNG", "NNP", "NNB"})
_VERB_TAGS = frozenset({"VV"})
_ADJ_TAGS = frozenset({"VA"})


@dataclass(frozen=True)
class MorphAnalysisResult:
    """형태소 분석 결과.

    Attributes:
        tokens: 분석된 전체 토큰 시퀀스 (순서 보존)
        text: 원본 텍스트
    """

    tokens: tuple[MorphToken, ...]
    text: str

    @property
    def nouns(self) -> list[MorphToken]:
        """일반 명사(NNG), 고유 명사(NNP), 의존 명사(NNB) 토큰 목록."""
        return [t for t in self.tokens if t.pos in _NOUN_TAGS]

    @property
    def verbs(self) -> list[MorphToken]:
        """동사(VV) 토큰 목록."""
        return [t for t in self.tokens if t.pos in _VERB_TAGS]

    @property
    def adjectives(self) -> list[MorphToken]:
        """형용사(VA) 토큰 목록."""
        return [t for t in self.tokens if t.pos in _ADJ_TAGS]

    @property
    def noun_surfaces(self) -> list[str]:
        """명사 표면형 목록 — 키워드 추출 연결 포인트."""
        return [t.surface for t in self.nouns]
