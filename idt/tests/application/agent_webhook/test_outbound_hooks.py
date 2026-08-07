"""outbound 발송 훅 2곳 테스트 (M2 Design §6 — FR-13·FR-16).

훅 ① 스케줄: TriggerDueSchedulesUseCase._run_one 성공 후 인라인 dispatch.
훅 ② invoke: InvokeWebhookAgentUseCase 실행 완료 후 spawn 비차단 dispatch.
"""
import time
from datetime import datetime

import pytest

from src.application.agent_schedule.trigger_due_schedules_use_case import (
    TriggerDueSchedulesUseCase,
)
from src.domain.agent_webhook.policies import WebhookSignaturePolicy

from tests.application.agent_webhook.test_invoke_webhook import (
    AGENT_ID,
    SECRET,
    REQ,
    FakeAgentRepo,
    FakeAssembleUc,
    FakeLogger,
    FakeRunUc,
    FakeUserRepo,
    FakeWebhookRepo,
    _webhook,
)
from src.application.agent_webhook.invoke_webhook_agent_use_case import (
    InvokeWebhookAgentUseCase,
)


class FakeDispatcher:
    def __init__(self, fail=False):
        self.calls = []
        self._fail = fail

    async def dispatch(self, agent_id, run, triggered_by, request_id):
        if self._fail:
            raise RuntimeError("dispatcher broke contract")
        self.calls.append((agent_id, run, triggered_by, request_id))


# ── 훅 ② invoke ──────────────────────────────────────────────


def _invoke_uc(dispatcher, spawn=None, run_uc=None):
    return InvokeWebhookAgentUseCase(
        webhook_repo=FakeWebhookRepo(_webhook()),
        agent_repo=FakeAgentRepo(),
        user_repo=FakeUserRepo(),
        assemble_auth_context_uc=FakeAssembleUc(),
        run_agent_uc=run_uc or FakeRunUc(),
        logger=FakeLogger(),
        outbound_dispatcher=dispatcher,
        spawn=spawn,
    )


def _signed_now(body: bytes):
    ts = int(time.time())
    return str(ts), WebhookSignaturePolicy.sign(SECRET, ts, body)


@pytest.mark.asyncio
class TestInvokeHook:
    async def test_dispatcher_called_with_webhook_source(self):
        dispatcher = FakeDispatcher()
        captured = []

        def capture_spawn(coro):
            captured.append(coro)
            return None

        uc = _invoke_uc(dispatcher, spawn=capture_spawn)
        body = b'{"query":"hi"}'
        ts, sig = _signed_now(body)
        result = await uc.execute(AGENT_ID, body, ts, sig, REQ)

        assert len(captured) == 1
        await captured[0]  # spawn된 코루틴 실행
        agent_id, run, triggered_by, request_id = dispatcher.calls[0]
        assert agent_id == AGENT_ID
        assert run is result
        assert triggered_by == "webhook"
        assert request_id == REQ

    async def test_no_dispatcher_no_op(self):
        uc = _invoke_uc(dispatcher=None)
        body = b'{"query":"hi"}'
        ts, sig = _signed_now(body)
        result = await uc.execute(AGENT_ID, body, ts, sig, REQ)  # no raise
        assert result == {"answer": "ok"}


# ── 훅 ① 스케줄 ──────────────────────────────────────────────


class _Schedule:
    id = "s1"
    agent_id = AGENT_ID
    user_id = "10"
    instruction = "요약해줘"
    timezone = "Asia/Seoul"


class _Claimed:
    schedule = _Schedule()
    scheduled_for = datetime(2026, 8, 7, 0, 0)


class _Response:
    session_id = "sess-1"
    run_id = "run-1"


class FakeSink:
    def __init__(self):
        self.finished = []

    async def on_started(self, schedule, scheduled_for, request_id):
        return "record-1"

    async def on_finished(self, record_id, status, request_id, **kwargs):
        self.finished.append((record_id, status, kwargs))


class _FakeSession:
    def begin(self):
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _cm():
            yield

        return _cm()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class FakeScheduleRepo:
    async def touch_last_run(self, schedule_id, now, request_id): ...


def _trigger_uc(dispatcher, run_response=None):
    class _RunUc:
        async def execute(self, agent_id, body, request_id, **kwargs):
            return run_response or _Response()

    return TriggerDueSchedulesUseCase(
        session_factory=lambda: _FakeSession(),
        schedule_repo_builder=lambda s: FakeScheduleRepo(),
        run_agent_uc_builder=lambda s: _RunUc(),
        sink=FakeSink(),
        logger=FakeLogger(),
        outbound_dispatcher=dispatcher,
    )


@pytest.mark.asyncio
class TestScheduleHook:
    async def test_dispatch_called_on_success(self):
        dispatcher = FakeDispatcher()
        uc = _trigger_uc(dispatcher)
        ok = await uc._run_one(_Claimed(), REQ)
        assert ok is True
        agent_id, _, triggered_by, _ = dispatcher.calls[0]
        assert agent_id == AGENT_ID
        assert triggered_by == "schedule"

    async def test_dispatch_failure_keeps_run_success(self):
        """FR-13: 계약 위반으로 dispatch가 raise해도 이력 success 유지."""
        uc = _trigger_uc(FakeDispatcher(fail=True))
        ok = await uc._run_one(_Claimed(), REQ)
        assert ok is True
        assert uc._sink.finished[0][1] == "success"

    async def test_no_dispatcher_no_op(self):
        uc = _trigger_uc(dispatcher=None)
        ok = await uc._run_one(_Claimed(), REQ)
        assert ok is True
