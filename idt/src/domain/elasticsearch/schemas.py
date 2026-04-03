"""Elasticsearch domain Value Objects.

외부 의존성 없는 순수 데이터 구조 정의.
"""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ESDocument:
    """Elasticsearch에 저장할 단일 문서."""

    id: str
    body: dict[str, Any]
    index: str


@dataclass
class ESSearchQuery:
    """Elasticsearch 검색 요청 파라미터."""

    index: str
    query: dict[str, Any]
    size: int = 10
    from_: int = 0
    source_fields: list[str] = field(default_factory=list)


@dataclass
class ESSearchResult:
    """Elasticsearch 검색 결과 단일 히트."""

    id: str
    score: float
    source: dict[str, Any]
    index: str
