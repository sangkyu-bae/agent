"""FeedbackWikiService — 이유 있는 👎를 위키 draft로 환류 (wiki-feedback-loop §3-4).

MemoryExtractionService 동형 launcher:
- kickoff_draft()는 sync 즉시 반환 — asyncio.create_task + _tasks 보관(GC 방지)
- 모든 실패는 warning 격리, 평가 저장·memory 환류에 전파 금지 (FR-06)
- dedup은 refs_key로 LLM 호출 전 스킵 (distill 멱등 선례, FR-04)
- 저장은 짧은 세션 + session.begin() 명시 트랜잭션 (쓰기 세션 교훈)
"""
import asyncio
import uuid
from datetime import datetime
from typing import Callable

from src.application.wiki.interfaces import FeedbackWikiDistillerInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.wiki.entity import WikiArticle, WikiSourceType, WikiStatus
from src.domain.wiki.policies import WikiPolicy

_FEEDBACK_PATH = "피드백"  # 결정 ④: 승인 큐 트리 노드 고정 분류
_MATCH_CANDIDATES_MAX = 20  # recurring-feedback-promotion 결정 ④: 후보 상한


class FeedbackWikiService:
    def __init__(
        self,
        session_factory,
        distiller: FeedbackWikiDistillerInterface,
        logger: LoggerInterface,
        *,
        enabled: bool,
        repo_builder: Callable | None = None,
        reinforce_enabled: bool = False,
    ) -> None:
        self._session_factory = session_factory
        self._distiller = distiller
        self._logger = logger
        self._enabled = enabled
        self._reinforce_enabled = reinforce_enabled
        self._repo_builder = repo_builder or self._default_repo_builder
        self._tasks: set[asyncio.Task] = set()

    @property
    def enabled(self) -> bool:
        """wiki 환류 opt-in — memory 환류(feedback_enabled)와 독립 (FR-05)."""
        return self._enabled

    def kickoff_draft(
        self,
        agent_id: str,
        message_id: int,
        question: str,
        answer: str,
        feedback_note: str,
        request_id: str,
    ) -> None:
        """fire-and-forget 초안 생성 — enabled=False면 no-op."""
        if not self._enabled:
            return
        task = asyncio.create_task(
            self._run_guarded(
                agent_id, message_id, question, answer, feedback_note, request_id
            )
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def drain(self) -> None:
        """잔여 태스크 대기 — 테스트·종료 훅 전용."""
        if self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    async def _run_guarded(
        self,
        agent_id: str,
        message_id: int,
        question: str,
        answer: str,
        feedback_note: str,
        request_id: str,
    ) -> None:
        try:
            await self._distill_and_save(
                agent_id, message_id, question, answer, feedback_note, request_id
            )
        except Exception as e:
            self._logger.warning(
                "feedback wiki draft failed (feedback unaffected)",
                request_id=request_id,
                message_id=message_id,
                exception=e,
            )  # FR-06

    async def _distill_and_save(
        self,
        agent_id: str,
        message_id: int,
        question: str,
        answer: str,
        feedback_note: str,
        request_id: str,
    ) -> None:
        refs = [f"feedback:{message_id}"]

        # 1) dedup — LLM 호출 전 스킵 (짧은 세션, FR-04)
        async with self._session_factory() as session:
            repo = self._repo_builder(session)
            existing = await repo.find_by_agent(agent_id, request_id)
        existing_keys = {WikiPolicy.refs_key(a.source_refs) for a in existing}
        if WikiPolicy.is_duplicate_group(refs, existing_keys):
            self._logger.debug(
                "feedback wiki draft skipped — duplicate refs",
                request_id=request_id,
                message_id=message_id,
            )
            return

        # 2) LLM 판정+정제 (세션 밖 — DB 점유 없음)
        # recurring-feedback-promotion: reinforce on이면 병합 후보 동봉
        draft = await self._distiller.distill_feedback(
            question, answer, feedback_note, request_id,
            candidates=self._match_candidates(existing),
        )
        if draft is None:
            return  # FR-02: 승격 가치 없음 — 강제 생성 금지

        # 2.5) 같은 주제 match → 기존 draft 강화 (성공 시 종료, 실패 시 신규 폴백)
        if draft.match_id is not None and await self._reinforce(
            existing, draft.match_id, message_id, request_id
        ):
            return

        # 3) 구성 + 불변식 검증 (자동 승인 금지 — DRAFT 고정)
        now = datetime.utcnow()
        article = WikiArticle(
            id=str(uuid.uuid4()),
            agent_id=agent_id,
            title=draft.title,
            content=draft.content,
            source_type=WikiSourceType.CONVERSATION,
            source_refs=refs,
            status=WikiStatus.DRAFT,
            confidence=draft.confidence,
            created_at=now,
            updated_at=now,
            path=_FEEDBACK_PATH,
        )
        try:
            WikiPolicy.validate_for_creation(article)
            WikiPolicy.validate_path(article.path)
        except ValueError as exc:
            self._logger.warning(
                "feedback wiki draft skipped (invariant)",
                request_id=request_id,
                message_id=message_id,
                reason=str(exc),
            )
            return

        # 4) 저장 — 짧은 세션 + 명시 트랜잭션
        async with self._session_factory() as session:
            async with session.begin():
                repo = self._repo_builder(session)
                await repo.save(article, request_id)

        self._logger.info(
            "feedback wiki draft created",
            request_id=request_id,
            message_id=message_id,
            article_id=article.id,
            trigger="feedback",
        )

    def _match_candidates(
        self, existing: list[WikiArticle],
    ) -> list[tuple[str, str]] | None:
        """병합 후보 (id, title) — CONVERSATION+DRAFT, updated_at desc 상위 N.

        reinforce off·후보 0이면 None (distiller 프롬프트 기존과 동일 — FR-05).
        """
        if not self._reinforce_enabled:
            return None
        drafts = [
            a for a in existing
            if a.source_type == WikiSourceType.CONVERSATION
            and a.status == WikiStatus.DRAFT
        ]
        drafts.sort(
            key=lambda a: a.updated_at or datetime.min, reverse=True
        )
        candidates = [(a.id, a.title) for a in drafts[:_MATCH_CANDIDATES_MAX]]
        return candidates or None

    async def _reinforce(
        self,
        existing: list[WikiArticle],
        match_id: str,
        message_id: int,
        request_id: str,
    ) -> bool:
        """대상 draft 강화 — 미실재·비DRAFT면 False(신규 draft 폴백, FR-04)."""
        target = next((a for a in existing if a.id == match_id), None)
        if target is None or target.status != WikiStatus.DRAFT:
            self._logger.warning(
                "feedback wiki reinforce fallback — match invalid",
                request_id=request_id,
                message_id=message_id,
                match_id=match_id,
            )
            return False
        target.add_support(
            f"feedback:{message_id}",
            WikiPolicy.reinforce_confidence(target.confidence),
            datetime.utcnow(),
        )
        async with self._session_factory() as session:
            async with session.begin():
                repo = self._repo_builder(session)
                await repo.update(target, request_id)
        self._logger.info(
            "feedback wiki draft reinforced",
            request_id=request_id,
            message_id=message_id,
            article_id=target.id,
            support=len(target.source_refs),
            reinforced=True,  # §3-4: 필드 기반 관측 파싱용
            trigger="feedback",
        )
        return True

    def _default_repo_builder(self, session):
        from src.infrastructure.wiki.wiki_repository import WikiArticleRepository

        return WikiArticleRepository(session, self._logger)
