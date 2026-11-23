from abc import ABC, abstractmethod
from typing import Optional

from src.domain.doc_browse.schemas import DocumentMetadata, KbDocumentSummary
from src.domain.mysql.schemas import MySQLPaginationParams, MySQLPageResult


class DocumentMetadataRepositoryInterface(ABC):

    @abstractmethod
    async def save(self, metadata: DocumentMetadata, request_id: str) -> None:
        ...

    @abstractmethod
    async def find_by_collection(
        self,
        collection_name: str,
        request_id: str,
        pagination: Optional[MySQLPaginationParams] = None,
    ) -> MySQLPageResult[DocumentMetadata]:
        ...

    @abstractmethod
    async def find_by_kb_id(
        self,
        kb_id: str,
        request_id: str,
        pagination: Optional[MySQLPaginationParams] = None,
        active_only: bool = False,
    ) -> MySQLPageResult[KbDocumentSummary]:
        """active_only: document-revision — superseded 버전 제외 (KB 문서 목록)."""
        ...

    @abstractmethod
    async def delete_by_document_id(
        self,
        document_id: str,
        request_id: str,
    ) -> bool:
        ...

    @abstractmethod
    async def find_by_document_id(
        self,
        document_id: str,
        request_id: str,
    ) -> Optional[DocumentMetadata]:
        ...

    @abstractmethod
    async def find_filenames(
        self,
        document_ids: list[str],
        request_id: str,
    ) -> dict[str, str]:
        """document_id → filename 일괄 조회 (agent-run-source-citations §3.4)."""
        ...

    async def find_version_labels(
        self,
        document_ids: list[str],
        request_id: str,
    ) -> dict[str, str]:
        """document_id → 버전 라벨 ("v3" / "v3 (라벨)"). v1·라벨 없음은 제외.

        document-revision module-6 근거 칩 라벨용. 구현이 없으면 빈 결과(라벨 생략).
        """
        return {}
