"""WikiTocProvider: compile 시점 위키 목차 블록 생성 (wiki-agentic-navigation FR-03).

WorkflowCompiler는 앱 싱글톤이므로 세션을 보유할 수 없다 — 호출마다
session_factory로 세션을 열고 닫는다(RunScopedWikiSearch와 동일 패턴).
목차 조회 실패는 빈 문자열 폴백(best-effort) — 위키 목차가 대화를 차단하지 않는다.
"""
from datetime import datetime, timezone

from src.application.agent_run.prompt_rendering import render_wiki_toc_block
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class WikiTocProvider:
    """승인+미만료 위키 목차를 프롬프트 블록으로 렌더링하는 공급자."""

    def __init__(
        self,
        session_factory,
        repo_builder,        # (session) -> WikiArticleRepository
        max_items: int,
        max_bytes: int,
        logger: LoggerInterface,
    ) -> None:
        self._session_factory = session_factory
        self._repo_builder = repo_builder
        self._max_items = max_items
        self._max_bytes = max_bytes
        self._logger = logger

    async def render_block(self, agent_id: str, request_id: str) -> str:
        try:
            async with self._session_factory() as session:
                items = await self._repo_builder(session).list_searchable_tree_items(
                    agent_id, datetime.now(timezone.utc), request_id
                )
            return render_wiki_toc_block(items, self._max_items, self._max_bytes)
        except Exception as e:
            self._logger.warning(
                "WikiTocProvider render failed (best-effort)",
                exception=e,
                agent_id=agent_id,
                request_id=request_id,
            )
            return ""
