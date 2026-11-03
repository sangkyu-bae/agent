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
    ) -> MySQLPageResult[KbDocumentSummary]:
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
