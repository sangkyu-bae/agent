"""PlatformAgentRunner — 빌더 에이전트 1회 실행 어댑터 (design §4 ①).

백그라운드 워커(`_run_agent`)와 같은 방식: 회차마다 새 세션, 실행자 auth_ctx 재조립,
persist_conversation=False(대화 이력 안 남김,
ai_run 은 남음 — O4), 실행 후 ai_run 합계로 비용.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

from src.infrastructure.market_analysis.adapters.agent_runner import PlatformAgentRunner


class FakeSession:
    def __init__(self) -> None:
        self.began = 0

    @asynccontextmanager
    async def begin(self):
        self.began += 1
        yield self


class FakeUseCase:
    def __init__(self, *, fail: Exception | None = None, run_id: str | None = "run-1"):
        self.calls: list[dict] = []
        self.fail = fail
        self.run_id = run_id

    async def execute(
        self,
        agent_id,
        request,
        request_id,
        viewer_user_id=None,
        viewer_department_ids=None,
        *,
        auth_ctx=None,
        **_,
    ):
        self.calls.append(
            {
                "agent_id": agent_id,
                "request": request,
                "auth_ctx": auth_ctx,
                "viewer_user_id": viewer_user_id,
                "departments": viewer_department_ids,
            }
        )
        if self.fail:
            raise self.fail
        return SimpleNamespace(answer="## 기술적 분석\n본문", run_id=self.run_id)


def _runner(
    uc: FakeUseCase,
    *,
    ctx=SimpleNamespace(department_ids=["d1"]),
    usage=(1234, Decimal("0.012345")),
):
    session = FakeSession()

    @asynccontextmanager
    async def session_factory():
        yield session

    async def assemble(user_id: str, request_id: str):
        return ctx

    async def usage_reader(run_id: str):
        return usage

    return PlatformAgentRunner(
        session_factory=session_factory,
        run_uc_builder=lambda s: uc,
        auth_ctx_assembler=assemble,
        usage_reader=usage_reader,
        logger=MagicMock(),
    ), session


async def _run(runner, **kw):
    args = {
        "agent_id": "a1",
        "query": "섹션을 써라",
        "reference_context": "근거",
        "run_as_user_id": "7",
        "request_id": "r",
    }
    args.update(kw)
    return await runner.run(**args)


async def test_runs_like_the_background_worker_and_reads_cost():
    uc = FakeUseCase()
    runner, session = _runner(uc)
    out = await _run(runner)

    assert (out.answer, out.run_id, out.failed) == (
        "## 기술적 분석\n본문",
        "run-1",
        False,
    )
    assert (out.tokens, out.cost_usd) == (1234, Decimal("0.012345"))
    call = uc.calls[0]
    req = call["request"]
    assert (req.query, req.user_id, req.reference_context) == (
        "섹션을 써라",
        "7",
        "근거",
    )
    assert req.persist_conversation is False
    assert req.session_id is None  # 이전 대화를 불러오지 않는다
    assert call["auth_ctx"].department_ids == ["d1"]
    assert (call["viewer_user_id"], call["departments"]) == ("7", ["d1"])
    assert session.began == 1


async def test_unknown_or_inactive_run_as_user_fails_without_running():
    uc = FakeUseCase()
    runner, _ = _runner(uc, ctx=None)
    out = await _run(runner)
    assert out.failed and out.error == "RUN_AS_USER_INVALID"
    assert uc.calls == []


async def test_query_over_2000_chars_fails_without_running():
    uc = FakeUseCase()
    runner, _ = _runner(uc)
    out = await _run(runner, query="x" * 2001)
    assert out.failed and out.error == "QUERY_TOO_LONG"
    assert uc.calls == []


async def test_run_exception_becomes_failed_outcome():
    uc = FakeUseCase(fail=RuntimeError("graph exploded"))
    runner, _ = _runner(uc)
    out = await _run(runner)
    assert out.failed and out.error.startswith("RUN_FAILED: graph exploded")
    assert out.answer == ""


async def test_usage_read_failure_keeps_the_answer():
    uc = FakeUseCase()
    runner, _ = _runner(uc)

    async def broken(run_id):
        raise RuntimeError("db")

    runner._usage_reader = broken
    out = await _run(runner)
    assert (
        out.failed is False
        and out.answer
        and (out.tokens, out.cost_usd) == (0, Decimal("0"))
    )


async def test_assembler_exception_becomes_failed_outcome():
    """중간 점검 I2: 포트는 예외를 던지지 않는다 — 인증 조립 실패도 값으로."""
    uc = FakeUseCase()
    runner, _ = _runner(uc)

    async def boom(user_id, request_id):
        raise RuntimeError("db down")

    runner._assemble = boom
    out = await _run(runner)
    assert out.failed and out.error.startswith("AUTH_CONTEXT_FAILED")
    assert uc.calls == []


async def test_reference_context_over_limit_fails_without_running():
    uc = FakeUseCase()
    runner, _ = _runner(uc)
    out = await _run(runner, reference_context="x" * 40_001)
    assert out.failed and out.error == "CONTEXT_TOO_LONG"
    assert uc.calls == []
