from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.doc_browse.interfaces import DocumentMetadataRepositoryInterface
from src.domain.doc_browse.schemas import DocumentMetadata
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.mysql.schemas import MySQLPaginationParams, MySQLPageResult
from src.infrastructure.doc_browse.document_metadata_repository import DocumentMetadataRepository


class SessionScopedDocumentMetadataRepository(DocumentMetadataRepositoryInterface):

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        logger: LoggerInterface,
    ) -> None:
        self._session_factory = session_factory
        self._logger = logger

    async def save(self, metadata: DocumentMetadata, request_id: str) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                repo = DocumentMetadataRepository(session, self._logger)
                await repo.save(metadata, request_id)

    async def find_by_collection(
        self,
        collection_name: str,
        request_id: str,
        pagination: Optional[MySQLPaginationParams] = None,
    ) -> MySQLPageResult[DocumentMetadata]:
        async with self._session_factory() as session:
            repo = DocumentMetadataRepository(session, self._logger)
            return await repo.find_by_collection(collection_name, request_id, pagination)

    async def delete_by_document_id(
        self,
        document_id: str,
        request_id: str,
    ) -> bool:
        async with self._session_factory() as session:
            async with session.begin():
                repo = DocumentMetadataRepository(session, self._logger)
                return await repo.delete_by_document_id(document_id, request_id)

    async def find_by_document_id(
        self,
        document_id: str,
        request_id: str,
    ) -> Optional[DocumentMetadata]:
        async with self._session_factory() as session:
            repo = DocumentMetadataRepository(session, self._logger)
            return await repo.find_by_document_id(document_id, request_id)
