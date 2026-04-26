from typing import Optional

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.doc_browse.interfaces import DocumentMetadataRepositoryInterface
from src.domain.doc_browse.schemas import DocumentMetadata
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.mysql.schemas import MySQLPaginationParams, MySQLPageResult
from src.infrastructure.doc_browse.models import DocumentMetadataModel


class DocumentMetadataRepository(DocumentMetadataRepositoryInterface):

    def __init__(self, session: AsyncSession, logger: LoggerInterface) -> None:
        self._session = session
        self._logger = logger

    async def save(self, metadata: DocumentMetadata, request_id: str) -> None:
        self._logger.info(
            "Document metadata save started",
            request_id=request_id,
            document_id=metadata.document_id,
        )
        try:
            existing = await self._find_model_by_document_id(metadata.document_id)
            if existing:
                existing.filename = metadata.filename
                existing.category = metadata.category
                existing.user_id = metadata.user_id
                existing.chunk_count = metadata.chunk_count
                existing.chunk_strategy = metadata.chunk_strategy
            else:
                model = DocumentMetadataModel(
                    document_id=metadata.document_id,
                    collection_name=metadata.collection_name,
                    filename=metadata.filename,
                    category=metadata.category,
                    user_id=metadata.user_id,
                    chunk_count=metadata.chunk_count,
                    chunk_strategy=metadata.chunk_strategy,
                )
                self._session.add(model)
            await self._session.flush()
            self._logger.info(
                "Document metadata save completed",
                request_id=request_id,
                document_id=metadata.document_id,
            )
        except Exception as e:
            self._logger.error(
                "Document metadata save failed",
                exception=e,
                request_id=request_id,
                document_id=metadata.document_id,
            )
            raise

    async def find_by_collection(
        self,
        collection_name: str,
        request_id: str,
        pagination: Optional[MySQLPaginationParams] = None,
    ) -> MySQLPageResult[DocumentMetadata]:
        self._logger.info(
            "Document metadata find_by_collection started",
            request_id=request_id,
            collection_name=collection_name,
        )
        try:
            p = pagination or MySQLPaginationParams(limit=20, offset=0)

            count_stmt = (
                select(func.count())
                .select_from(DocumentMetadataModel)
                .where(DocumentMetadataModel.collection_name == collection_name)
            )
            total = (await self._session.execute(count_stmt)).scalar_one()

            query_stmt = (
                select(DocumentMetadataModel)
                .where(DocumentMetadataModel.collection_name == collection_name)
                .order_by(DocumentMetadataModel.created_at.desc())
                .limit(p.limit)
                .offset(p.offset)
            )
            rows = (await self._session.execute(query_stmt)).scalars().all()

            items = [self._to_domain(r) for r in rows]
            self._logger.info(
                "Document metadata find_by_collection completed",
                request_id=request_id,
                total=total,
                page_size=len(items),
            )
            return MySQLPageResult(
                items=items,
                total=total,
                limit=p.limit,
                offset=p.offset,
            )
        except Exception as e:
            self._logger.error(
                "Document metadata find_by_collection failed",
                exception=e,
                request_id=request_id,
            )
            raise

    async def delete_by_document_id(
        self,
        document_id: str,
        request_id: str,
    ) -> bool:
        self._logger.info(
            "Document metadata delete started",
            request_id=request_id,
            document_id=document_id,
        )
        try:
            stmt = delete(DocumentMetadataModel).where(
                DocumentMetadataModel.document_id == document_id
            )
            result = await self._session.execute(stmt)
            await self._session.flush()
            deleted = result.rowcount > 0
            self._logger.info(
                "Document metadata delete completed",
                request_id=request_id,
                deleted=deleted,
            )
            return deleted
        except Exception as e:
            self._logger.error(
                "Document metadata delete failed",
                exception=e,
                request_id=request_id,
                document_id=document_id,
            )
            raise

    async def find_by_document_id(
        self,
        document_id: str,
        request_id: str,
    ) -> Optional[DocumentMetadata]:
        model = await self._find_model_by_document_id(document_id)
        return self._to_domain(model) if model else None

    async def _find_model_by_document_id(
        self, document_id: str
    ) -> Optional[DocumentMetadataModel]:
        stmt = select(DocumentMetadataModel).where(
            DocumentMetadataModel.document_id == document_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    def _to_domain(model: DocumentMetadataModel) -> DocumentMetadata:
        return DocumentMetadata(
            document_id=model.document_id,
            collection_name=model.collection_name,
            filename=model.filename,
            category=model.category,
            user_id=model.user_id,
            chunk_count=model.chunk_count,
            chunk_strategy=model.chunk_strategy,
        )
