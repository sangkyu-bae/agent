"""DispatchOutboundWebhookUseCase 단위 테스트 (M2 Design §6).

session_factory는 begin() 컨텍스트만 흉내내는 fake — repo builder가
세션 인자를 무시하고 고정 fake repo를 반환한다.
"""
import json
from contextlib import asynccontextmanager
from datetime import datetime

import pytest

from src.application.agent_webhook.dispatch_outbound_use_case import (
    DispatchOutboundWebhookUseCase,
)
from src.domain.agent_webhook.entity import AgentWebhook
from src.domain.agent_webhook.interfaces import OutboundResult
from src.domain.agent_webhook.policies import WebhookSignaturePolicy

AGENT_ID = "agent-1"
SECRET = "whsec_dispatch_secret"
URL = "http://receiver.local/hook"
REQ = "req-1"


class FakeRun:
    run_id = "run-1"
    session_id = "sess-1"
    query = "안녕"
    answer = "안녕하세요"
    tools_used = ["wiki_read"]


def _webhook(outbound_enabled=True, outbound_url=URL) -> AgentWebhook:
    now = datetime(2026, 8, 7)
    return AgentWebhook(
        id="wh-1",
        agent_id=AGENT_ID,
        enabled=True,
        secret=SECRET,
        secret_hint=SECRET[-4:],
        outbound_url=outbound_url,
        outbound_enabled=outbound_enabled,
        created_by="10",
        created_at=now,
        updated_at=now,
    )


class FakeSession:
    def begin(self):
        @asynccontextmanager
        async def _cm():
            yield

        return _cm()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


def fake_session_factory():
    return FakeSession()


class FakeWebhookRepo:
    def __init__(self, webhook):
        self._webhook = webhook

    async def find_by_agent_id(self, agent_id, request_id):
        return self._webhook


class FakeDeliveryRepo:
    def __init__(self, fail=False):
        self.rows = []
        self._fail = fail

    async def insert(self, delivery, request_id):
        if self._fail:
            raise RuntimeError("db down")
        self.rows.append(delivery)


class FakeSender:
    def __init__(self, result=None, fail=False):
        self.calls = []
        self._result = result or OutboundResult(
            success=True, status_code=200, attempts=1, error=None,
            duration_ms=12,
        )
        self._fail = fail

    async def send(self, url, body, headers, request_id):
        if self._fail:
            raise RuntimeError("sender crashed")
        self.calls.append((url, body, headers))
        return self._result


class FakeLogger:
    def __init__(self):
        self.errors = []

    def info(self, *a, **k): ...
    def warning(self, *a, **k): ...
    def debug(self, *a, **k): ...

    def error(self, *a, **k):
        self.errors.append((a, k))


def _uc(webhook, sender=None, delivery_repo=None, logger=None):
    return DispatchOutboundWebhookUseCase(
        session_factory=fake_session_factory,
        webhook_repo_builder=lambda s: FakeWebhookRepo(webhook),
        delivery_repo_builder=lambda s: delivery_repo or FakeDeliveryRepo(),
        sender=sender or FakeSender(),
        logger=logger or FakeLogger(),
    )


@pytest.mark.asyncio
class TestDispatchOutbound:
    async def test_disabled_or_missing_url_skips_silently(self):
        for wh in [None, _webhook(outbound_enabled=False), _webhook(outbound_url=None)]:
            sender = FakeSender()
            repo = FakeDeliveryRepo()
            await _uc(wh, sender, repo).dispatch(AGENT_ID, FakeRun(), "schedule", REQ)
            assert sender.calls == []
            assert repo.rows == []

    async def test_signed_payload_verifiable_with_m1_verify(self):
        sender = FakeSender()
        await _uc(_webhook(), sender).dispatch(AGENT_ID, FakeRun(), "webhook", REQ)

        url, body, headers = sender.calls[0]
        assert url == URL
        ts = int(headers[WebhookSignaturePolicy.HEADER_TIMESTAMP])
        sig = headers[WebhookSignaturePolicy.HEADER_SIGNATURE]
        # FR-15: 수신측이 M1 inbound 검증 코드로 동일하게 검증 가능
        assert WebhookSignaturePolicy.verify(SECRET, ts, body, sig)

    async def test_payload_schema(self):
        sender = FakeSender()
        await _uc(_webhook(), sender).dispatch(AGENT_ID, FakeRun(), "schedule", REQ)
        payload = json.loads(sender.calls[0][1])
        assert payload["event"] == "agent.run.completed"
        assert payload["agent_id"] == AGENT_ID
        assert payload["run_id"] == "run-1"
        assert payload["session_id"] == "sess-1"
        assert payload["query"] == "안녕"
        assert payload["answer"] == "안녕하세요"
        assert payload["tools_used"] == ["wiki_read"]
        assert payload["triggered_by"] == "schedule"
        assert isinstance(payload["timestamp"], int)

    async def test_delivery_recorded_with_result(self):
        repo = FakeDeliveryRepo()
        result = OutboundResult(
            success=False, status_code=503, attempts=4,
            error="HTTP 503", duration_ms=7100,
        )
        await _uc(_webhook(), FakeSender(result), repo).dispatch(
            AGENT_ID, FakeRun(), "webhook", REQ
        )
        row = repo.rows[0]
        assert row.agent_id == AGENT_ID
        assert row.run_id == "run-1"
        assert row.url == URL
        assert row.trigger_source == "webhook"
        assert row.success is False
        assert row.status_code == 503
        assert row.attempts == 4
        assert row.error == "HTTP 503"

    async def test_sender_exception_never_raises(self):
        logger = FakeLogger()
        uc = _uc(_webhook(), FakeSender(fail=True), logger=logger)
        await uc.dispatch(AGENT_ID, FakeRun(), "schedule", REQ)  # no raise
        assert len(logger.errors) == 1

    async def test_delivery_insert_exception_never_raises(self):
        logger = FakeLogger()
        uc = _uc(
            _webhook(),
            FakeSender(),
            delivery_repo=FakeDeliveryRepo(fail=True),
            logger=logger,
        )
        await uc.dispatch(AGENT_ID, FakeRun(), "webhook", REQ)  # no raise
        assert len(logger.errors) == 1
