"""InvokeWebhookAgentUseCase 단위 테스트 (Design §6) — 검증 순서·위임 인자."""
import time

import pytest

from src.application.agent_webhook.invoke_webhook_agent_use_case import (
    InvokeWebhookAgentUseCase,
    WebhookAuthError,
    WebhookBadRequestError,
    WebhookNotFoundError,
)
from src.domain.agent_run.auth_context import AuthContext
from src.domain.agent_webhook.entity import AgentWebhook
from src.domain.agent_webhook.policies import WebhookSignaturePolicy

AGENT_ID = "agent-1"
OWNER_ID = 10
SECRET = "whsec_unit_test_secret"
REQ = "req-1"


def _webhook(enabled: bool = True) -> AgentWebhook:
    from datetime import datetime

    now = datetime(2026, 8, 7)
    return AgentWebhook(
        id="wh-1",
        agent_id=AGENT_ID,
        enabled=enabled,
        secret=SECRET,
        secret_hint=SECRET[-4:],
        outbound_url=None,
        outbound_enabled=False,
        created_by=str(OWNER_ID),
        created_at=now,
        updated_at=now,
    )


def _owner_ctx() -> AuthContext:
    return AuthContext(
        user_id=OWNER_ID,
        display_name="owner",
        role="user",
        primary_department_id="d1",
        primary_department_name="여신",
        department_ids=("d1",),
        department_names=("여신",),
        permissions=frozenset({"USE_RAG_SEARCH"}),
    )


class FakeWebhookRepo:
    def __init__(self, webhook):
        self._webhook = webhook

    async def find_by_agent_id(self, agent_id, request_id):
        return self._webhook if agent_id == AGENT_ID else None


class FakeAgentRepo:
    async def find_by_id(self, agent_id, request_id):
        class _A:
            id = AGENT_ID
            user_id = str(OWNER_ID)

        return _A() if agent_id == AGENT_ID else None


class FakeUserRepo:
    async def find_by_id(self, user_id):
        class _U:
            id = OWNER_ID

        return _U() if user_id == OWNER_ID else None


class FakeAssembleUc:
    async def execute(self, user, request_id):
        return _owner_ctx()


class FakeRunUc:
    def __init__(self):
        self.calls = []

    async def execute(self, agent_id, body, request_id, **kwargs):
        self.calls.append((agent_id, body, request_id, kwargs))
        return {"answer": "ok"}


class FakeLogger:
    def info(self, *a, **k): ...
    def warning(self, *a, **k): ...
    def error(self, *a, **k): ...
    def debug(self, *a, **k): ...


def _make_uc(webhook=None, run_uc=None):
    return InvokeWebhookAgentUseCase(
        webhook_repo=FakeWebhookRepo(webhook),
        agent_repo=FakeAgentRepo(),
        user_repo=FakeUserRepo(),
        assemble_auth_context_uc=FakeAssembleUc(),
        run_agent_uc=run_uc or FakeRunUc(),
        logger=FakeLogger(),
    )


def _signed(body: bytes, secret: str = SECRET, ts: int | None = None):
    ts = ts if ts is not None else int(time.time())
    return str(ts), WebhookSignaturePolicy.sign(secret, ts, body)


@pytest.mark.asyncio
class TestInvokeWebhook:
    async def test_valid_request_delegates_to_run_uc_with_owner_identity(self):
        run_uc = FakeRunUc()
        uc = _make_uc(_webhook(), run_uc)
        body = b'{"query": "\xec\x95\x88\xeb\x85\x95", "session_id": "s-1"}'
        ts, sig = _signed(body)

        await uc.execute(AGENT_ID, body, ts, sig, REQ)

        agent_id, run_body, _, kwargs = run_uc.calls[0]
        assert agent_id == AGENT_ID
        assert run_body.query == "안녕"
        assert run_body.user_id == str(OWNER_ID)
        assert run_body.session_id == "s-1"
        assert kwargs["auth_ctx"].user_id == OWNER_ID
        assert kwargs["viewer_user_id"] == str(OWNER_ID)
        assert kwargs["viewer_department_ids"] == ["d1"]

    async def test_missing_headers_auth_error(self):
        uc = _make_uc(_webhook())
        with pytest.raises(WebhookAuthError):
            await uc.execute(AGENT_ID, b"{}", None, None, REQ)

    async def test_non_integer_timestamp_auth_error(self):
        uc = _make_uc(_webhook())
        with pytest.raises(WebhookAuthError):
            await uc.execute(AGENT_ID, b"{}", "abc", "sha256=x", REQ)

    async def test_expired_timestamp_auth_error(self):
        uc = _make_uc(_webhook())
        body = b'{"query":"hi"}'
        ts = int(time.time()) - 301
        _, sig = _signed(body, ts=ts)
        with pytest.raises(WebhookAuthError):
            await uc.execute(AGENT_ID, body, str(ts), sig, REQ)

    async def test_forged_signature_auth_error(self):
        uc = _make_uc(_webhook())
        body = b'{"query":"hi"}'
        ts, sig = _signed(body, secret="whsec_wrong")
        with pytest.raises(WebhookAuthError):
            await uc.execute(AGENT_ID, body, ts, sig, REQ)

    async def test_unconfigured_not_found(self):
        uc = _make_uc(webhook=None)
        body = b'{"query":"hi"}'
        ts, sig = _signed(body)
        with pytest.raises(WebhookNotFoundError):
            await uc.execute(AGENT_ID, body, ts, sig, REQ)

    async def test_disabled_not_found(self):
        uc = _make_uc(_webhook(enabled=False))
        body = b'{"query":"hi"}'
        ts, sig = _signed(body)
        with pytest.raises(WebhookNotFoundError):
            await uc.execute(AGENT_ID, body, ts, sig, REQ)

    async def test_invalid_body_bad_request_after_signature_pass(self):
        uc = _make_uc(_webhook())
        body = b'{"no_query": true}'
        ts, sig = _signed(body)
        with pytest.raises(WebhookBadRequestError):
            await uc.execute(AGENT_ID, body, ts, sig, REQ)
