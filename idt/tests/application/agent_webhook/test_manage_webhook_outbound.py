"""UpdateWebhookUseCase M2 확장(D17) + ListWebhookDeliveries 단위 테스트."""
from datetime import datetime

import pytest

from src.application.agent_webhook.errors import WebhookValidationError
from src.application.agent_webhook.manage_webhook_use_cases import (
    EnableWebhookUseCase,
    ListWebhookDeliveriesUseCase,
    UpdateWebhookUseCase,
)
from src.application.agent_webhook.schemas import UpdateWebhookRequest
from src.domain.agent_webhook.entity import WebhookDelivery

from tests.application.agent_webhook.test_manage_webhook import (
    AGENT_ID,
    OWNER,
    REQ,
    FakeAgentRepo,
    FakeAgent,
    FakeLogger,
    FakeWebhookRepo,
)

URL = "https://intra.example.com/hook"


@pytest.fixture
def agent_repo():
    return FakeAgentRepo({AGENT_ID: FakeAgent(AGENT_ID, OWNER)})


@pytest.fixture
def webhook_repo():
    return FakeWebhookRepo()


@pytest.fixture
def logger():
    return FakeLogger()


async def _enable(webhook_repo, agent_repo, logger):
    await EnableWebhookUseCase(webhook_repo, agent_repo, logger).execute(
        AGENT_ID, OWNER, REQ
    )


def _update_uc(webhook_repo, agent_repo, logger):
    return UpdateWebhookUseCase(webhook_repo, agent_repo, logger)


@pytest.mark.asyncio
class TestUpdateWebhookOutbound:
    async def test_enabled_only_keeps_m1_behavior(
        self, webhook_repo, agent_repo, logger
    ):
        await _enable(webhook_repo, agent_repo, logger)
        res = await _update_uc(webhook_repo, agent_repo, logger).execute(
            AGENT_ID, UpdateWebhookRequest(enabled=False), OWNER, REQ
        )
        assert res.enabled is False
        # outbound 필드는 미변경 (미지정)
        assert res.outbound_url is None
        assert res.outbound_enabled is False

    async def test_register_valid_outbound_url(
        self, webhook_repo, agent_repo, logger
    ):
        await _enable(webhook_repo, agent_repo, logger)
        res = await _update_uc(webhook_repo, agent_repo, logger).execute(
            AGENT_ID, UpdateWebhookRequest(outbound_url=URL), OWNER, REQ
        )
        assert res.outbound_url == URL
        assert res.outbound_enabled is False  # 등록만으로 활성화되지 않음

    async def test_invalid_url_raises_validation_error(
        self, webhook_repo, agent_repo, logger
    ):
        await _enable(webhook_repo, agent_repo, logger)
        with pytest.raises(WebhookValidationError):
            await _update_uc(webhook_repo, agent_repo, logger).execute(
                AGENT_ID,
                UpdateWebhookRequest(outbound_url="ftp://x.com/a"),
                OWNER,
                REQ,
            )

    async def test_null_url_clears_and_forces_outbound_off(
        self, webhook_repo, agent_repo, logger
    ):
        await _enable(webhook_repo, agent_repo, logger)
        uc = _update_uc(webhook_repo, agent_repo, logger)
        await uc.execute(
            AGENT_ID,
            UpdateWebhookRequest(outbound_url=URL, outbound_enabled=True),
            OWNER,
            REQ,
        )
        res = await uc.execute(
            AGENT_ID, UpdateWebhookRequest(outbound_url=None), OWNER, REQ
        )
        assert res.outbound_url is None
        assert res.outbound_enabled is False

    async def test_enable_outbound_without_url_rejected(
        self, webhook_repo, agent_repo, logger
    ):
        await _enable(webhook_repo, agent_repo, logger)
        with pytest.raises(WebhookValidationError, match="먼저 등록"):
            await _update_uc(webhook_repo, agent_repo, logger).execute(
                AGENT_ID,
                UpdateWebhookRequest(outbound_enabled=True),
                OWNER,
                REQ,
            )

    async def test_empty_body_rejected_by_schema(self):
        with pytest.raises(ValueError, match="1개 이상"):
            UpdateWebhookRequest()


@pytest.mark.asyncio
class TestListWebhookDeliveries:
    async def test_returns_rows_without_url(self, agent_repo, logger):
        class FakeDeliveryRepo:
            async def list_by_agent(self, agent_id, limit, request_id):
                return [
                    WebhookDelivery(
                        id="d1", agent_id=agent_id, run_id="run-1",
                        url="http://x/hook", trigger_source="schedule",
                        success=True, status_code=200, attempts=1,
                        error=None, duration_ms=42,
                        created_at=datetime(2026, 8, 7),
                    )
                ]

        uc = ListWebhookDeliveriesUseCase(FakeDeliveryRepo(), agent_repo, logger)
        rows = await uc.execute(AGENT_ID, OWNER, 20, REQ)
        assert rows[0].trigger_source == "schedule"
        assert rows[0].success is True
        assert not hasattr(rows[0], "url")

    async def test_non_owner_forbidden(self, agent_repo, logger):
        class FakeDeliveryRepo:
            async def list_by_agent(self, *a):
                return []

        uc = ListWebhookDeliveriesUseCase(FakeDeliveryRepo(), agent_repo, logger)
        with pytest.raises(PermissionError):
            await uc.execute(AGENT_ID, "99", 20, REQ)
