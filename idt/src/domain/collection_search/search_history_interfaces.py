from abc import ABC, abstractmethod
from typing import Optional

from src.domain.collection_search.search_history_schemas import SearchHistoryEntry


class SearchHistoryRepositoryInterface(ABC):

    @abstractmethod
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
    ) -> None: ...

    @abstractmethod
    async def find_by_user_and_collection(
        self,
        user_id: str,
        collection_name: str,
        limit: int,
        offset: int,
        request_id: str,
    ) -> tuple[list[SearchHistoryEntry], int]: ...
