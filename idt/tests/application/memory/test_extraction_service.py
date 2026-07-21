"""MemoryExtractionService 단위 테스트 (agent-memory-extraction Design §3-3).

launcher 가드 패턴 — 예외 격리(FR-01)·pending 상한(FR-08)·dedup(FR-04)·
enabled off no-op(FR-09). kickoff는 fire-and-forget이라 테스트는 러너를 직접 await.
"""
from unittest.mock import AsyncMock, MagicMock

from src.application.memory.extraction_service import MemoryExtractionService
from src.application.memory.interfaces import MemoryCandidate
from src.domain.memory.entity import Memory, MemoryScope, MemoryStatus, MemoryType


def _existing(memory_id=1, content="여신 심사팀 소속", status=MemoryStatus.ACTIVE) -> Memory:
    return Memory(
        id=memory_id, scope=MemoryScope.USER, user_id="u1", tier=0,
        mem_type=MemoryType.PROFILE, content=content, status=status,
    )


class _BeginCtx:
    async def __aenter__(self):
        return None

    async def __aexit__(self, *a):
        return False


class _SessionCtx:
    def __init__(self, counter):
        self._counter = counter

    async def __aenter__(self):
        self._counter["opened"] += 1
        session = MagicMock()
        session.begin = lambda: _BeginCtx()  # 쓰기 트랜잭션 (RunTracker 선례)
        return session

    async def __aexit__(self, *a):
        self._counter["closed"] += 1
        return False


def _make(
    candidates=None,
    active=None,
    pending=None,
    enabled=True,
    max_per_turn=3,
    pending_cap=20,
    extract_error=None,
    feedback_enabled=False,
):
    counter = {"opened": 0, "closed": 0}

    def session_factory():
        return _SessionCtx(counter)

    repo = MagicMock()
    repo.find_by_user_and_status = AsyncMock(
        side_effect=lambda user_id, status, request_id: (
            list(active or []) if status == MemoryStatus.ACTIVE else list(pending or [])
        )
    )
    repo.count_by_user_and_status = AsyncMock(return_value=len(pending or []))
    saved: list[Memory] = []

    async def _save(memory, request_id):
        saved.append(memory)
        return memory

    repo.save = AsyncMock(side_effect=_save)

    extractor = MagicMock()
    if extract_error is not None:
        extractor.extract = AsyncMock(side_effect=extract_error)
    else:
        extractor.extract = AsyncMock(return_value=candidates or [])

    logger = MagicMock()
    service = MemoryExtractionService(
        session_factory=session_factory,
        extractor=extractor,
        logger=logger,
        enabled=enabled,
        max_per_turn=max_per_turn,
        pending_cap=pending_cap,
        repo_builder=lambda session: repo,
        feedback_enabled=feedback_enabled,
    )
    return service, repo, extractor, logger, saved, counter


class TestKickoff:
    async def test_enabled_False면_태스크_미생성(self):
        service, _, extractor, _, _, counter = _make(enabled=False)

        service.kickoff("u1", "질문", "답변", "run-1", "req-1")
        await service.drain()  # 테스트 헬퍼 — 잔여 태스크 대기

        extractor.extract.assert_not_awaited()
        assert counter["opened"] == 0


class TestRun:
    async def test_후보는_PENDING과_run_id로_저장(self):
        service, _, _, _, saved, _ = _make(
            candidates=[MemoryCandidate("profile", "여신 기획팀으로 이동", 80)],
        )

        await service.run("u1", "질문", "답변", "run-1", "req-1")

        assert len(saved) == 1
        assert saved[0].status == MemoryStatus.PENDING
        assert saved[0].source_run_id == "run-1"
        assert saved[0].confidence == 80
        assert saved[0].mem_type == MemoryType.PROFILE
        assert saved[0].user_id == "u1"

    async def test_pending_상한_도달_시_추출_스킵(self):
        service, _, extractor, logger, saved, _ = _make(
            pending=[_existing(i, f"후보{i}", MemoryStatus.PENDING) for i in range(20)],
            pending_cap=20,
        )

        await service.run("u1", "질문", "답변", "run-1", "req-1")

        extractor.extract.assert_not_awaited()  # LLM 호출 자체를 안 함
        assert saved == []
        logger.debug.assert_called_once()  # FR-08

    async def test_기존_content와_중복_후보는_탈락(self):
        service, _, _, _, saved, _ = _make(
            candidates=[
                MemoryCandidate("profile", "여신 심사팀 소속", 80),  # active와 중복
                MemoryCandidate("preference", "새 선호", 70),
            ],
            active=[_existing(content="여신 심사팀 소속")],
        )

        await service.run("u1", "질문", "답변", "run-1", "req-1")

        assert [m.content for m in saved] == ["새 선호"]

    async def test_턴당_상한_초과분_절단(self):
        service, _, _, _, saved, _ = _make(
            candidates=[MemoryCandidate("profile", f"내용{i}", 80) for i in range(5)],
            max_per_turn=3,
        )

        await service.run("u1", "질문", "답변", "run-1", "req-1")

        assert len(saved) == 3

    async def test_불량_mem_type은_탈락(self):
        service, _, _, _, saved, _ = _make(
            candidates=[
                MemoryCandidate("unknown_type", "내용", 80),
                MemoryCandidate("episode", "정상", 70),
            ],
        )

        await service.run("u1", "질문", "답변", "run-1", "req-1")

        assert [m.mem_type for m in saved] == [MemoryType.EPISODE]

    async def test_길이_초과_후보는_탈락(self):
        service, _, _, _, saved, _ = _make(
            candidates=[MemoryCandidate("profile", "가" * 501, 80)],
        )
        await service.run("u1", "질문", "답변", "run-1", "req-1")
        assert saved == []

    async def test_추출_0건이면_저장_0건(self):
        service, repo, _, _, saved, _ = _make(candidates=[])
        await service.run("u1", "질문", "답변", "run-1", "req-1")
        assert saved == []
        repo.save.assert_not_awaited()

    async def test_LLM_예외는_warning으로_격리(self):
        service, _, _, logger, saved, _ = _make(extract_error=RuntimeError("llm down"))

        await service.run("u1", "질문", "답변", "run-1", "req-1")  # 예외 전파 없음

        assert saved == []
        logger.warning.assert_called_once()  # FR-01

    async def test_세션은_조회와_저장_2회_개폐(self):
        """§3-3: 조회/저장 분리 짧은 세션 — LLM 호출 중 DB 점유 없음."""
        service, _, _, _, _, counter = _make(
            candidates=[MemoryCandidate("profile", "새 내용", 80)],
        )

        await service.run("u1", "질문", "답변", "run-1", "req-1")

        assert counter["opened"] == 2
        assert counter["closed"] == 2

    async def test_기존_active와_pending이_추출_프롬프트에_전달(self):
        service, _, extractor, _, _, _ = _make(
            candidates=[],
            active=[_existing(content="활성 내용")],
            pending=[_existing(2, "대기 내용", MemoryStatus.PENDING)],
        )

        await service.run("u1", "질문", "답변", "run-1", "req-1")

        existing_arg = extractor.extract.await_args.args[2]
        assert "활성 내용" in existing_arg
        assert "대기 내용" in existing_arg


class TestKickoffFeedback:
    """eval-feedback-loop Design §3-3 — 부정 평가 트리거 추출."""

    async def test_feedback_enabled_False면_no_op(self):
        service, _, extractor, _, _, counter = _make(feedback_enabled=False)

        service.kickoff_feedback("u1", "질문", "답변", "근거 부족", "req-1")
        await service.drain()

        extractor.extract.assert_not_awaited()
        assert counter["opened"] == 0
        assert service.feedback_enabled is False

    async def test_on이면_extract에_feedback_note_전달_후_PENDING_저장(self):
        service, _, extractor, _, saved, _ = _make(
            feedback_enabled=True,
            candidates=[MemoryCandidate("preference", "조문 근거 포함 선호", 80)],
        )

        service.kickoff_feedback("u1", "질문", "답변", "근거 부족", "req-1")
        await service.drain()

        assert extractor.extract.await_args.kwargs["feedback_note"] == "근거 부족"
        assert len(saved) == 1
        assert saved[0].status == MemoryStatus.PENDING
        assert saved[0].source_run_id is None  # provenance 결정 ④
        assert service.feedback_enabled is True

    async def test_매_턴_추출_off여도_feedback은_독립_동작(self):
        service, _, extractor, _, saved, _ = _make(
            enabled=False,  # 매 턴 추출 off
            feedback_enabled=True,
            candidates=[MemoryCandidate("preference", "새 선호", 70)],
        )

        service.kickoff_feedback("u1", "질문", "답변", "이유", "req-1")
        await service.drain()

        assert len(saved) == 1  # 독립 opt-in (FR-05)

    async def test_pending_cap_도달_시_동일하게_skip(self):
        service, _, extractor, _, saved, _ = _make(
            feedback_enabled=True,
            pending=[_existing(i, f"후보{i}", MemoryStatus.PENDING) for i in range(20)],
            pending_cap=20,
        )

        service.kickoff_feedback("u1", "질문", "답변", "이유", "req-1")
        await service.drain()

        extractor.extract.assert_not_awaited()  # 결정 ③: cap 우회 없음
        assert saved == []

    async def test_기존_kickoff는_feedback_note_None(self):
        service, _, extractor, _, _, _ = _make(
            candidates=[MemoryCandidate("profile", "내용", 80)],
        )

        service.kickoff("u1", "질문", "답변", "run-1", "req-1")
        await service.drain()

        assert extractor.extract.await_args.kwargs.get("feedback_note") is None
