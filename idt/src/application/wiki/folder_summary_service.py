"""WikiFolderSummaryService — 승인 이벤트 시 폴더 요약 재증류 팬아웃 (wiki-folder-summaries D2).

WikiFeedbackService 동형 launcher:
- kickoff_refresh()는 sync 즉시 반환 — asyncio.create_task + _tasks 보관(GC 방지)
- 모든 실패는 warning 격리 — 승인/편집 API에 전파 금지
- 정합성 계약: 요청 트랜잭션 커밋과 경합하면 1이벤트 늦은 요약 허용
  (eventually consistent — 요약은 힌트, 진실은 wiki_list 실시간 목록)
- 세션은 목적별 단기 사용: 읽기(문서/기존 요약)와 쓰기(upsert/delete)를 분리하고
  LLM 호출은 세션 밖에서 수행한다(트랜잭션 장기 점유 방지)
"""
import asyncio
import uuid
from datetime import datetime
from typing import Callable

from src.application.wiki.interfaces import FolderSummaryDistillerInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.wiki.entity import WikiArticle, WikiFolderSummary, WikiStatus
from src.domain.wiki.policies import WikiPolicy

_DOC_SNIPPET_CONTENT_MAX = 500  # 증류 입력 스니펫: "제목: 본문" 본문부 상한


class WikiFolderSummaryService:
    """위키 상태 전이 이벤트를 받아 폴더 요약 계층을 갱신한다."""

    def __init__(
        self,
        session_factory,
        article_repo_builder: Callable,   # (session) -> WikiArticleRepository
        folder_repo_builder: Callable,    # (session) -> WikiFolderSummaryRepository
        distiller: FolderSummaryDistillerInterface,
        logger: LoggerInterface,
        *,
        enabled: bool,
    ) -> None:
        self._session_factory = session_factory
        self._article_repo_builder = article_repo_builder
        self._folder_repo_builder = folder_repo_builder
        self._distiller = distiller
        self._logger = logger
        self._enabled = enabled
        self._tasks: set[asyncio.Task] = set()

    @property
    def enabled(self) -> bool:
        return self._enabled

    def kickoff_refresh(
        self, agent_id: str, paths: list[str | None], request_id: str
    ) -> None:
        """fire-and-forget 재증류 — enabled=False 또는 대상 없음이면 no-op."""
        if not self._enabled:
            return
        targets = self._expand_targets(paths)
        if not targets:
            return
        task = asyncio.create_task(self._run_guarded(agent_id, targets, request_id))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def drain(self) -> None:
        """잔여 태스크 대기 — 테스트·종료 훅 전용."""
        if self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    @staticmethod
    def _expand_targets(paths: list[str | None]) -> list[str]:
        """자기+조상 확장 후 깊은 순서 유지 dedup (bottom-up 재증류 순서)."""
        seen: set[str] = set()
        ordered: list[str] = []
        expanded: list[str] = []
        for p in paths:
            expanded.extend(WikiPolicy.expand_ancestors(p))
        # 깊이 내림차순 정렬 — 하위 폴더 요약이 상위 증류 입력이 되도록(D3)
        for path in sorted(expanded, key=lambda x: x.count("/"), reverse=True):
            if path not in seen:
                seen.add(path)
                ordered.append(path)
        return ordered

    async def _run_guarded(
        self, agent_id: str, targets: list[str], request_id: str
    ) -> None:
        try:
            await self._refresh(agent_id, targets, request_id)
        except Exception as e:
            self._logger.warning(
                "folder summary refresh failed (approval unaffected)",
                request_id=request_id, agent_id=agent_id, exception=e,
            )

    async def _refresh(
        self, agent_id: str, targets: list[str], request_id: str
    ) -> None:
        now = datetime.utcnow()
        live = await self._load_live_articles(agent_id, now, request_id)

        for path in targets:
            # 폴더 단위 실패 격리 — leaf 증류 실패가 조상 갱신을 막지 않는다.
            # 실패 폴더는 기존 요약 유지, 다음 전이에서 수렴(eventually consistent).
            try:
                await self._refresh_one(agent_id, path, live, now, request_id)
            except Exception as e:
                self._logger.warning(
                    "folder summary refresh failed for path (continuing)",
                    request_id=request_id, agent_id=agent_id, path=path,
                    exception=e,
                )

    async def _refresh_one(
        self, agent_id: str, path: str, live: list[WikiArticle],
        now: datetime, request_id: str,
    ) -> None:
        direct = [a for a in live if a.path == path]
        child_rows = await self._load_children(agent_id, path, request_id)

        if not direct and not child_rows:
            await self._write(
                lambda repo: repo.delete(agent_id, path, request_id)
            )
            return

        recursive_count = sum(
            1 for a in live
            if a.path is not None
            and (a.path == path or a.path.startswith(path + "/"))
        )
        summary_text = await self._distiller.summarize_folder(
            path,
            [
                f"{a.title}: {a.content[:_DOC_SNIPPET_CONTENT_MAX]}"
                for a in direct
            ],
            [c.summary for c in child_rows],
            request_id,
        )
        entity = WikiFolderSummary(
            id=str(uuid.uuid4()), agent_id=agent_id, path=path,
            summary=summary_text, article_count=recursive_count,
            updated_at=now,
        )
        await self._write(lambda repo: repo.upsert(entity, request_id))

    async def _load_live_articles(
        self, agent_id: str, now: datetime, request_id: str
    ) -> list[WikiArticle]:
        async with self._session_factory() as session:
            articles = await self._article_repo_builder(session).find_by_agent(
                agent_id, request_id, status=WikiStatus.APPROVED
            )
        return [a for a in articles if a.is_searchable(now)]

    async def _load_children(
        self, agent_id: str, path: str, request_id: str
    ) -> list[WikiFolderSummary]:
        """직속 하위 폴더 요약 — bottom-up 순서상 이미 이번 갱신이 반영된 상태."""
        prefix = path + "/"
        async with self._session_factory() as session:
            rows = await self._folder_repo_builder(session).list_by_agent(
                agent_id, request_id
            )
        return [
            r for r in rows
            if r.path.startswith(prefix) and "/" not in r.path[len(prefix):]
        ]

    async def _write(self, op: Callable) -> None:
        """짧은 쓰기 세션 + begin() 명시 트랜잭션 (쓰기 세션 교훈)."""
        async with self._session_factory() as session:
            async with session.begin():
                await op(self._folder_repo_builder(session))
