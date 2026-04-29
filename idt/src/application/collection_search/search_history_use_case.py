from src.domain.collection_search.search_history_interfaces import (
    SearchHistoryRepositoryInterface,
)
from src.domain.collection_search.search_history_schemas import (
    SearchHistoryListResult,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class SearchHistoryUseCase:
    def __init__(
        self,
        search_history_repo: SearchHistoryRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._repo = search_history_repo
        self._logger = logger

    async def execute(
        self,
        user_id: str,
        collection_name: str,
        limit: int,
        offset: int,
        request_id: str,
    ) -> SearchHistoryListResult:
        self._logger.info(
            "SearchHistory query",
            request_id=request_id,
            collection=collection_name,
        )
        histories, total = await self._repo.find_by_user_and_collection(
            user_id=user_id,
            collection_name=collection_name,
            limit=limit,
            offset=offset,
            request_id=request_id,
        )
        return SearchHistoryListResult(
            collection_name=collection_name,
            histories=histories,
            total=total,
            limit=limit,
            offset=offset,
        )
