"""Elasticsearch repository interface for domain layer.

구현체는 infrastructure layer에 위치한다.
외부 API 호출 금지 (elasticsearch-py 사용 금지).
"""
from abc import ABC, abstractmethod
from typing import Any, Optional

from src.domain.elasticsearch.schemas import ESDocument, ESSearchQuery, ESSearchResult


class ElasticsearchRepositoryInterface(ABC):
    """Elasticsearch 공통 repository 인터페이스."""

    @abstractmethod
    async def index(self, document: ESDocument, request_id: str) -> str:
        """문서 색인 (신규 또는 덮어쓰기).

        Args:
            document: 색인할 문서
            request_id: 요청 추적 ID

        Returns:
            저장된 document ID
        """

    @abstractmethod
    async def bulk_index(self, documents: list[ESDocument], request_id: str) -> int:
        """문서 대량 색인.

        Args:
            documents: 색인할 문서 목록
            request_id: 요청 추적 ID

        Returns:
            성공한 건수
        """

    @abstractmethod
    async def get(
        self, index: str, doc_id: str, request_id: str
    ) -> Optional[dict[str, Any]]:
        """ID로 문서 조회.

        Args:
            index: ES 인덱스 이름
            doc_id: 문서 ID
            request_id: 요청 추적 ID

        Returns:
            _source 딕셔너리, 없으면 None
        """

    @abstractmethod
    async def delete(self, index: str, doc_id: str, request_id: str) -> bool:
        """ID로 문서 삭제.

        Args:
            index: ES 인덱스 이름
            doc_id: 문서 ID
            request_id: 요청 추적 ID

        Returns:
            삭제 성공 여부
        """

    @abstractmethod
    async def search(
        self, query: ESSearchQuery, request_id: str
    ) -> list[ESSearchResult]:
        """Query DSL 기반 검색.

        Args:
            query: 검색 파라미터
            request_id: 요청 추적 ID

        Returns:
            ESSearchResult 목록
        """

    @abstractmethod
    async def exists(self, index: str, doc_id: str, request_id: str) -> bool:
        """문서 존재 여부 확인.

        Args:
            index: ES 인덱스 이름
            doc_id: 문서 ID
            request_id: 요청 추적 ID

        Returns:
            존재하면 True
        """

    @abstractmethod
    async def delete_by_query(
        self, index: str, query: dict[str, Any], request_id: str
    ) -> int:
        """쿼리 조건으로 문서 일괄 삭제.

        Args:
            index: ES 인덱스 이름
            query: Query DSL 조건
            request_id: 요청 추적 ID

        Returns:
            삭제된 건수
        """

    @abstractmethod
    async def ensure_index_exists(
        self, index: str, mappings: dict[str, Any]
    ) -> bool:
        """인덱스 존재 확인 후 없으면 생성.

        Args:
            index: ES 인덱스 이름
            mappings: 인덱스 매핑 정의

        Returns:
            True: 새로 생성됨, False: 이미 존재하거나 실패
        """
