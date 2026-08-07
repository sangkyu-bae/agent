"""관리 UseCase 5종 단위 테스트 (Design §6) — fake repo 기반."""
import pytest

from src.application.agent_webhook.manage_webhook_use_cases import (
    DisableWebhookUseCase,
    EnableWebhookUseCase,
    GetWebhookUseCase,
    RotateWebhookSecretUseCase,
    UpdateWebhookUseCase,
)
from src.application.agent_webhook.schemas import UpdateWebhookRequest
from src.domain.agent_webhook.policies import WebhookSignaturePolicy

OWNER = "10"
OTHER = "99"
AGENT_ID = "agent-1"
REQ = "req-1"


class FakeAgent:
    def __init__(self, agent_id: str, user_id: str):
        self.id = agent_id
        self.user_id = user_id


class FakeAgentRepo:
    def __init__(self, agents: dict):
        self._agents = agents

    async def find_by_id(self, agent_id, request_id):
        return self._agents.get(agent_id)


class FakeWebhookRepo:
    def __init__(self):
        self.rows: dict = {}

    async def find_by_agent_id(self, agent_id, request_id):
        return self.rows.get(agent_id)

    async def insert(self, webhook, request_id):
        self.rows[webhook.agent_id] = webhook

    async def update(self, webhook, request_id):
        self.rows[webhook.agent_id] = webhook

    async def delete(self, agent_id, request_id):
        self.rows.pop(agent_id, None)


class FakeLogger:
    def info(self, *a, **k): ...
    def warning(self, *a, **k): ...
    def error(self, *a, **k): ...
    def debug(self, *a, **k): ...


@pytest.fixture
def agent_repo():
    return FakeAgentRepo({AGENT_ID: FakeAgent(AGENT_ID, OWNER)})


@pytest.fixture
def webhook_repo():
    return FakeWebhookRepo()


@pytest.fixture
def logger():
    return FakeLogger()


@pytest.mark.asyncio
class TestEnableWebhook:
    async def test_issues_secret_once_and_stores_hint(
        self, webhook_repo, agent_repo, logger
    ):
        uc = EnableWebhookUseCase(webhook_repo, agent_repo, logger)
        res = await uc.execute(AGENT_ID, OWNER, REQ)

        assert res.secret.startswith("whsec_")
        assert res.secret_hint == res.secret[-4:]
        assert res.enabled is True
        assert res.inbound_path == f"/api/v1/webhooks/agents/{AGENT_ID}"
        stored = webhook_repo.rows[AGENT_ID]
        assert stored.secret == res.secret
        assert stored.secret_hint == res.secret_hint
        assert stored.created_by == OWNER

    async def test_conflict_when_already_configured(
        self, webhook_repo, agent_repo, logger
    ):
        uc = EnableWebhookUseCase(webhook_repo, agent_repo, logger)
        await uc.execute(AGENT_ID, OWNER, REQ)
        with pytest.raises(ValueError, match="이미"):
            await uc.execute(AGENT_ID, OWNER, REQ)

    async def test_non_owner_forbidden(self, webhook_repo, agent_repo, logger):
        uc = EnableWebhookUseCase(webhook_repo, agent_repo, logger)
        with pytest.raises(PermissionError):
            await uc.execute(AGENT_ID, OTHER, REQ)

    async def test_missing_agent_not_found(
        self, webhook_repo, agent_repo, logger
    ):
        uc = EnableWebhookUseCase(webhook_repo, agent_repo, logger)
        with pytest.raises(ValueError, match="찾을 수 없"):
            await uc.execute("nope", OWNER, REQ)


@pytest.mark.asyncio
class TestGetWebhook:
    async def test_unconfigured_returns_configured_false(
        self, webhook_repo, agent_repo, logger
    ):
        uc = GetWebhookUseCase(webhook_repo, agent_repo, logger)
        res = await uc.execute(AGENT_ID, OWNER, REQ)
        assert res.configured is False
        assert res.secret_hint is None

    async def test_configured_exposes_hint_not_secret(
        self, webhook_repo, agent_repo, logger
    ):
        issued = await EnableWebhookUseCase(
            webhook_repo, agent_repo, logger
        ).execute(AGENT_ID, OWNER, REQ)
        res = await GetWebhookUseCase(
            webhook_repo, agent_repo, logger
        ).execute(AGENT_ID, OWNER, REQ)
        assert res.configured is True
        assert res.secret_hint == issued.secret_hint
        assert not hasattr(res, "secret")


@pytest.mark.asyncio
class TestRotateWebhook:
    async def test_rotate_replaces_secret_and_invalidates_old(
        self, webhook_repo, agent_repo, logger
    ):
        issued = await EnableWebhookUseCase(
            webhook_repo, agent_repo, logger
        ).execute(AGENT_ID, OWNER, REQ)
        rotated = await RotateWebhookSecretUseCase(
            webhook_repo, agent_repo, logger
        ).execute(AGENT_ID, OWNER, REQ)

        assert rotated.secret != issued.secret
        # 구키로 만든 서명은 새 저장 시크릿으로 검증 실패해야 한다
        ts, body = 1754500000, b'{"query":"x"}'
        old_sig = WebhookSignaturePolicy.sign(issued.secret, ts, body)
        stored = webhook_repo.rows[AGENT_ID]
        assert not WebhookSignaturePolicy.verify(
            stored.secret, ts, body, old_sig
        )

    async def test_rotate_unconfigured_not_found(
        self, webhook_repo, agent_repo, logger
    ):
        uc = RotateWebhookSecretUseCase(webhook_repo, agent_repo, logger)
        with pytest.raises(ValueError, match="찾을 수 없"):
            await uc.execute(AGENT_ID, OWNER, REQ)


@pytest.mark.asyncio
class TestUpdateWebhook:
    async def test_toggle_enabled(self, webhook_repo, agent_repo, logger):
        await EnableWebhookUseCase(webhook_repo, agent_repo, logger).execute(
            AGENT_ID, OWNER, REQ
        )
        res = await UpdateWebhookUseCase(
            webhook_repo, agent_repo, logger
        ).execute(AGENT_ID, UpdateWebhookRequest(enabled=False), OWNER, REQ)
        assert res.enabled is False
        assert webhook_repo.rows[AGENT_ID].enabled is False


@pytest.mark.asyncio
class TestDisableWebhook:
    async def test_delete_removes_row(self, webhook_repo, agent_repo, logger):
        await EnableWebhookUseCase(webhook_repo, agent_repo, logger).execute(
            AGENT_ID, OWNER, REQ
        )
        await DisableWebhookUseCase(webhook_repo, agent_repo, logger).execute(
            AGENT_ID, OWNER, REQ
        )
        assert AGENT_ID not in webhook_repo.rows

    async def test_delete_unconfigured_not_found(
        self, webhook_repo, agent_repo, logger
    ):
        uc = DisableWebhookUseCase(webhook_repo, agent_repo, logger)
        with pytest.raises(ValueError, match="찾을 수 없"):
            await uc.execute(AGENT_ID, OWNER, REQ)
