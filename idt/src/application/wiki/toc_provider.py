"""WikiTocProvider: compile 시점 위키 목차 블록 생성 (wiki-agentic-navigation FR-03).

WorkflowCompiler는 앱 싱글톤이므로 세션을 보유할 수 없다 — 호출마다
session_factory로 세션을 열고 닫는다(RunScopedWikiSearch와 동일 패턴).
목차 조회 실패는 빈 문자열 폴백(best-effort) — 위키 목차가 대화를 차단하지 않는다.

wiki-folder-summaries D5: 승인 문서 수가 임계를 넘고 폴더 요약이 존재하면
flat 목차 대신 폴더 지도를 렌더한다. 요약 부재/실패는 flat 폴백(무회귀).
"""
from datetime import datetime, timezone

from src.application.agent_run.prompt_rendering import (
    render_wiki_folder_block,
    render_wiki_toc_block,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class WikiTocProvider:
    """승인+미만료 위키 목차(또는 폴더 지도)를 프롬프트 블록으로 렌더링하는 공급자."""

    def __init__(
        self,
        session_factory,
        repo_builder,        # (session) -> WikiArticleRepository
        max_items: int,
        max_bytes: int,
        logger: LoggerInterface,
        folder_repo_builder=None,  # (session) -> WikiFolderSummaryRepository | None
        folder_enabled: bool = False,
        folder_threshold: int = 30,
    ) -> None:
        self._session_factory = session_factory
        self._repo_builder = repo_builder
        self._max_items = max_items
        self._max_bytes = max_bytes
        self._logger = logger
        self._folder_repo_builder = folder_repo_builder
        self._folder_enabled = folder_enabled
        self._folder_threshold = folder_threshold

    async def render_block(self, agent_id: str, request_id: str) -> str:
        try:
            async with self._session_factory() as session:
                items = await self._repo_builder(session).list_searchable_tree_items(
                    agent_id, datetime.now(timezone.utc), request_id
                )
                folder_block = await self._try_folder_block(
                    session, agent_id, items, request_id
                )
            if folder_block:
                return folder_block
            return render_wiki_toc_block(items, self._max_items, self._max_bytes)
        except Exception as e:
            self._logger.warning(
                "WikiTocProvider render failed (best-effort)",
                exception=e,
                agent_id=agent_id,
                request_id=request_id,
            )
            return ""

    async def _try_folder_block(
        self, session, agent_id: str, items, request_id: str
    ) -> str:
        """폴더 모드 조건 충족 시 지도 블록, 아니면 ''(flat 폴백)."""
        if (
            not self._folder_enabled
            or self._folder_repo_builder is None
            or len(items) <= self._folder_threshold
        ):
            return ""
        folders = await self._folder_repo_builder(session).list_by_agent(
            agent_id, request_id
        )
        top_folders = [f for f in folders if "/" not in f.path]
        if not top_folders:
            return ""
        uncategorized = sum(1 for i in items if i.path is None)
        return render_wiki_folder_block(top_folders, uncategorized, self._max_bytes)