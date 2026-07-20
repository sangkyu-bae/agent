"""KbSearchHistoryUseCase — KB 단위 검색 히스토리 조회 (kb-retrieval-test D8)."""
from src.application.knowledge_base.use_case import KnowledgeBaseUseCase
from src.domain.auth.entities import User
from src.domain.collection_search.search_history_interfaces import (
    SearchHistoryRepositoryInterface,
)
from src.domain.collection_search.search_history_schemas import (
    KbSearchHistoryListResult,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class KbSearchHistoryUseCase:
    def __init__(
        self,
        kb_use_case: KnowledgeBaseUseCase,
        search_history_repo: SearchHistoryRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._kb_use_case = kb_use_case
        self._repo = search_history_repo
        self._logger = logger

    async def execute(
        self,
        kb_id: str,
        user: User,
        limit: int,
        offset: int,
        request_id: str,
    ) -> KbSearchHistoryListResult:
        # 존재 404 / KB 읽기 권한 403 — 검색과 동일 검증 (D3)
        await self._kb_use_case.get(kb_id, user, request_id)
        self._logger.info(
            "KbSearchHistory query",
            request_id=request_id,
            kb_id=kb_id,
        )
        histories, total = await self._repo.find_by_user_and_kb(
            user_id=str(user.id),
            kb_id=kb_id,
            limit=limit,
            offset=offset,
            request_id=request_id,
        )
        return KbSearchHistoryListResult(
            kb_id=kb_id,
            histories=histories,
            total=total,
            limit=limit,
            offset=offset,
        )
