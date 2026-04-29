from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.collection_search.search_history_interfaces import (
    SearchHistoryRepositoryInterface,
)
from src.domain.collection_search.search_history_schemas import SearchHistoryEntry
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.collection_search.models import SearchHistoryModel


class SearchHistoryRepository(SearchHistoryRepositoryInterface):
    def __init__(self, session: AsyncSession, logger: LoggerInterface) -> None:
        self._session = session
        self._logger = logger

    async def save(
        self,
        user_id: str,
        collection_name: str,
        query: str,
        bm25_weight: float,
        vector_weight: float,
        top_k: int,
        result_count: int,
        request_id: str,
        document_id: Optional[str] = None,
    ) -> None:
        model = SearchHistoryModel(
            user_id=user_id,
            collection_name=collection_name,
            document_id=document_id,
            query=query,
            bm25_weight=bm25_weight,
            vector_weight=vector_weight,
            top_k=top_k,
            result_count=result_count,
        )
        self._session.add(model)
        await self._session.flush()

    async def find_by_user_and_collection(
        self,
        user_id: str,
        collection_name: str,
        limit: int,
        offset: int,
        request_id: str,
    ) -> tuple[list[SearchHistoryEntry], int]:
        count_stmt = (
            select(func.count())
            .select_from(SearchHistoryModel)
            .where(
                SearchHistoryModel.user_id == user_id,
                SearchHistoryModel.collection_name == collection_name,
            )
        )
        total = (await self._session.execute(count_stmt)).scalar() or 0

        stmt = (
            select(SearchHistoryModel)
            .where(
                SearchHistoryModel.user_id == user_id,
                SearchHistoryModel.collection_name == collection_name,
            )
            .order_by(SearchHistoryModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = (await self._session.execute(stmt)).scalars().all()

        entries = [
            SearchHistoryEntry(
                id=row.id,
                user_id=row.user_id,
                collection_name=row.collection_name,
                query=row.query,
                bm25_weight=row.bm25_weight,
                vector_weight=row.vector_weight,
                top_k=row.top_k,
                result_count=row.result_count,
                created_at=row.created_at,
                document_id=row.document_id,
            )
            for row in rows
        ]
        return entries, total
