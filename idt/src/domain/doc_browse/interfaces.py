from abc import ABC, abstractmethod
from typing import Optional

from src.domain.doc_browse.schemas import DocumentMetadata
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
