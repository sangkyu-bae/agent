from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict
import uuid

from src.domain.mysql.schemas import MySQLPaginationParams

if TYPE_CHECKING:
    from src.domain.doc_browse.interfaces import DocumentMetadataRepositoryInterface
    from src.domain.logging.interfaces.logger_interface import LoggerInterface


class ListDocumentsUseCase:
    def __init__(
        self,
        document_metadata_repo: DocumentMetadataRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._repo = document_metadata_repo
        self._logger = logger

    async def execute(
        self,
        collection_name: str,
        offset: int = 0,
        limit: int = 20,
    ) -> Dict[str, Any]:
        request_id = str(uuid.uuid4())
        self._logger.info(
            "List documents started",
            request_id=request_id,
            collection=collection_name,
        )
        try:
            pagination = MySQLPaginationParams(limit=limit, offset=offset)
            page = await self._repo.find_by_collection(
                collection_name=collection_name,
                request_id=request_id,
                pagination=pagination,
            )

            documents = [
                {
                    "document_id": item.document_id,
                    "filename": item.filename,
                    "category": item.category,
                    "chunk_count": item.chunk_count,
                    "chunk_types": [],
                    "user_id": item.user_id,
                }
                for item in page.items
            ]

            self._logger.info(
                "List documents completed",
                request_id=request_id,
                collection=collection_name,
                total=page.total,
            )
            return {
                "collection_name": collection_name,
                "documents": documents,
                "total_documents": page.total,
                "offset": offset,
                "limit": limit,
            }
        except Exception as e:
            self._logger.error(
                "List documents failed",
                exception=e,
                collection=collection_name,
            )
            raise
