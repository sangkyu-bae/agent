"""MemoryExtractionService — 대화 후 백그라운드 메모리 후보 추출 (agent-memory-extraction §3-3).

section_summary launcher와 동일한 가드 패턴:
- kickoff()는 sync 즉시 반환 — asyncio.create_task + _tasks 보관(GC 방지)
- 모든 실패는 warning 격리, 채팅에 전파 금지 (FR-01)
- 잡 테이블 없음 — best-effort (허용 손실, Plan 리스크 확정)
세션은 RunScoped 선례대로 호출마다 session_factory로 짧게 연다.
"""
import asyncio
from typing import Callable

from src.application.memory.interfaces import MemoryExtractorInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.memory.entity import Memory, MemoryScope, MemoryStatus, MemoryType
from src.domain.memory.policies import MemoryPolicy


class MemoryExtractionService:
    def __init__(
        self,
        session_factory,
        extractor: MemoryExtractorInterface,
        logger: LoggerInterface,
        *,
        enabled: bool,
        max_per_turn: int,
        pending_cap: int,
        repo_builder: Callable | None = None,
        feedback_enabled: bool = False,
    ) -> None:
        self._session_factory = session_factory
        self._extractor = extractor
        self._logger = logger
        self._enabled = enabled
        self._feedback_enabled = feedback_enabled
        self._max_per_turn = max_per_turn
        self._pending_cap = pending_cap
        self._repo_builder = repo_builder or self._default_repo_builder
        self._tasks: set[asyncio.Task] = set()

    @property
    def feedback_enabled(self) -> bool:
        """eval-feedback-loop: 부정 평가 트리거 추출 opt-in — 매 턴 추출과 독립."""
        return self._feedback_enabled

    def kickoff(
        self,
        user_id: str,
        question: str,
        answer: str,
        run_id: str | None,
        request_id: str,
    ) -> None:
        """fire-and-forget 추출 — enabled=False면 no-op (FR-09)."""
        if not self._enabled:
            return
        self._spawn(user_id, question, answer, run_id, request_id, None)

    def kickoff_feedback(
        self,
        user_id: str,
        question: str,
        answer: str,
        feedback_note: str,
        request_id: str,
    ) -> None:
        """부정 평가 트리거 추출 — feedback_enabled=False면 no-op.

        eval-feedback-loop 결정 ④: run_id 없음(source_run_id=None),
        결정 ③: pending cap은 매 턴 추출과 동일 적용.
        """
        if not self._feedback_enabled:
            return
        self._spawn(user_id, question, answer, None, request_id, feedback_note)

    def _spawn(
        self,
        user_id: str,
        question: str,
        answer: str,
        run_id: str | None,
        request_id: str,
        feedback_note: str | None,
    ) -> None:
        task = asyncio.create_task(
            self._run_guarded(
                user_id, question, answer, run_id, request_id, feedback_note
            )
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def drain(self) -> None:
        """잔여 태스크 대기 — 테스트·종료 훅 전용."""
        if self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    async def run(
        self,
        user_id: str,
        question: str,
        answer: str,
        run_id: str | None,
        request_id: str,
    ) -> None:
        """추출 본체 — kickoff의 가드 내부에서 실행되며 예외를 스스로 격리한다."""
        await self._run_guarded(user_id, question, answer, run_id, request_id)

    async def _run_guarded(
        self,
        user_id: str,
        question: str,
        answer: str,
        run_id: str | None,
        request_id: str,
        feedback_note: str | None = None,
    ) -> None:
        try:
            await self._extract_and_store(
                user_id, question, answer, run_id, request_id, feedback_note
            )
        except Exception as e:
            self._logger.warning(
                "memory extraction failed (chat unaffected)",
                request_id=request_id,
                user_id=user_id,
                exception=e,
            )  # FR-01

    async def _extract_and_store(
        self,
        user_id: str,
        question: str,
        answer: str,
        run_id: str | None,
        request_id: str,
        feedback_note: str | None = None,
    ) -> None:
        # 1) 기존 메모리 조회 + pending 상한 검사 (짧은 세션)
        async with self._session_factory() as session:
            repo = self._repo_builder(session)
            pending_count = await repo.count_by_user_and_status(
                user_id, MemoryStatus.PENDING, request_id
            )
            if pending_count >= self._pending_cap:
                self._logger.debug(
                    "memory extraction skipped — pending cap reached",
                    request_id=request_id,
                    user_id=user_id,
                    pending=pending_count,
                )  # FR-08
                return
            active = await repo.find_by_user_and_status(
                user_id, MemoryStatus.ACTIVE, request_id
            )
            pending = await repo.find_by_user_and_status(
                user_id, MemoryStatus.PENDING, request_id
            )

        existing_contents = [m.content for m in active + pending]

        # 2) LLM 추출 (세션 밖 — DB 점유 없이)
        candidates = await self._extractor.extract(
            question, answer, existing_contents, request_id,
            feedback_note=feedback_note,
        )

        # 3) 검증·중복 제거·절단
        valid = []
        for candidate in MemoryPolicy.dedup_candidates(
            candidates, set(existing_contents)
        ):
            try:
                mem_type = MemoryType(candidate.mem_type)
                MemoryPolicy.validate_content(candidate.content)
            except ValueError:
                continue
            valid.append((mem_type, candidate))
        valid = valid[: self._max_per_turn]

        if not valid:
            return  # FR-05: 빈 후보 강제 금지

        # 4) pending 저장 (짧은 세션 + 명시 트랜잭션 — RunTracker 선례)
        async with self._session_factory() as session:
            async with session.begin():
                repo = self._repo_builder(session)
                await self._save_all(repo, valid, user_id, run_id, request_id)

        self._logger.info(
            "memory candidates extracted",
            request_id=request_id,
            user_id=user_id,
            saved=len(valid),
            run_id=run_id,
            trigger="feedback" if feedback_note else "turn",  # 결정 ④ provenance
        )

    async def _save_all(
        self, repo, valid, user_id: str, run_id: str | None, request_id: str
    ) -> None:
        for mem_type, candidate in valid:
                await repo.save(
                    Memory(
                        id=None,
                        scope=MemoryScope.USER,
                        user_id=user_id,
                        tier=0,
                        mem_type=mem_type,
                        content=candidate.content,
                        source_run_id=run_id,
                        confidence=MemoryPolicy.clamp_confidence(
                            candidate.confidence
                        ),
                        status=MemoryStatus.PENDING,  # FR-02: active 직행 금지
                    ),
                    request_id,
                )

    def _default_repo_builder(self, session):
        from src.infrastructure.memory.repository import MemoryRepository

        return MemoryRepository(session, self._logger)
