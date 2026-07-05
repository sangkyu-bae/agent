"""RunScopedWikiSearch: 에이전트 런타임 검색 어댑터 (LLM-WIKI-001, Step6 와이어링).

기존 hybrid search와 동일한 `execute(request, request_id)` 시그니처를 유지하여
InternalDocumentSearchTool을 수정하지 않고 끼워 넣을 수 있다.
- RunContext의 agent_id로 승인 위키를 우선 검색(WikiFirstSearchUseCase)
- agent 컨텍스트가 없으면 기존 hybrid search로 폴백
- WikiArticleRepository는 MySQL 세션이 필요하므로 매 호출마다 session_factory로
  세션을 열어 구성한다(ToolFactory 싱글톤 안전 — RunTracker와 동일 패턴).
"""
from datetime import datetime, timezone

from src.application.agent_run.context import get_current_run_context
from src.application.wiki.wiki_first_search_use_case import WikiFirstSearchUseCase
from src.domain.hybrid_search.schemas import HybridSearchRequest, HybridSearchResponse
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class RunScopedWikiSearch:
    """위키 우선 검색을 런타임 컨텍스트에 맞춰 수행하는 검색 어댑터."""

    def __init__(
        self,
        session_factory,
        repo_builder,        # (session) -> WikiArticleRepository
        inner_search_getter,  # () -> HybridSearchUseCase (lazy; .execute(request, request_id))
        logger: LoggerInterface,
    ) -> None:
        self._session_factory = session_factory
        self._repo_builder = repo_builder
        self._inner_getter = inner_search_getter
        self._logger = logger

    async def execute(
        self, request: HybridSearchRequest, request_id: str
    ) -> HybridSearchResponse:
        inner = self._inner_getter()
        ctx = get_current_run_context()
        agent_id = getattr(ctx, "agent_id", None) if ctx is not None else None
        if not agent_id:
            # 에이전트 컨텍스트 없음(graph 외부 호출 등) → 기존 검색으로 폴백
            return await inner.execute(request, request_id)
        async with self._session_factory() as session:
            repo = self._repo_builder(session)
            wiki_first = WikiFirstSearchUseCase(wiki_repo=repo, inner_search=inner)
            return await wiki_first.execute(
                request, agent_id, datetime.now(timezone.utc), request_id
            )
