"""알림 수신 설정 관리 — firewall-agent design §4.1 (소유자 전용)."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.application.agent_alert.manage_use_cases import (
    GetAlertReceiverUseCase,
    ListAlertReceiptsUseCase,
    RotateAlertTokenUseCase,
    UpsertAlertReceiverUseCase,
)
from src.application.agent_alert.schemas import UpsertAlertReceiverRequest
from src.domain.agent_alert.entity import AlertReceipt
from src.domain.agent_alert.policies import AlertTokenPolicy

from .fakes import FakeReceiptRepo, FakeReceiverRepo

NOW = datetime(2026, 11, 24, 7, 30, 0)


def _agent_repo(owner: str | None = "7"):
    repo = MagicMock()
    agent = None if owner is None else MagicMock(user_id=owner)
    repo.find_by_id = AsyncMock(return_value=agent)
    return repo


def _upsert(receivers=None, owner="7"):
    receivers = receivers or FakeReceiverRepo()
    uc = UpsertAlertReceiverUseCase(
        receivers, _agent_repo(owner), MagicMock(), now_fn=lambda: NOW
    )
    return uc, receivers


class TestUpsert:
    @pytest.mark.asyncio
    async def test_first_call_creates_and_returns_token_once(self):
        uc, receivers = _upsert()
        resp = await uc.execute(
            "agent-1",
            "7",
            UpsertAlertReceiverRequest(enabled=True, instruction_prefix="정책대로"),
            "req",
        )
        (saved,) = receivers.saved
        assert resp.token and AlertTokenPolicy.verify(resp.token, saved.token_hash)
        assert resp.config.token_hint == resp.token[-4:]
        assert resp.config.enabled is True and resp.config.skip_when_busy is True
        assert resp.config.inbound_path == "/api/v1/alert-hooks/agents/agent-1"
        assert saved.user_id == "7"

    @pytest.mark.asyncio
    async def test_second_call_updates_without_new_token(self):
        uc, receivers = _upsert()
        first = await uc.execute("agent-1", "7", UpsertAlertReceiverRequest(), "req")
        resp = await uc.execute(
            "agent-1",
            "7",
            UpsertAlertReceiverRequest(enabled=False, skip_when_busy=False),
            "req",
        )
        assert resp.token is None
        stored = receivers.items["agent-1"]
        assert (stored.enabled, stored.skip_when_busy) == (False, False)
        assert AlertTokenPolicy.verify(first.token, stored.token_hash)

    @pytest.mark.asyncio
    async def test_default_is_disabled(self):
        uc, _ = _upsert()
        resp = await uc.execute("agent-1", "7", UpsertAlertReceiverRequest(), "req")
        assert resp.config.enabled is False

    @pytest.mark.asyncio
    async def test_non_owner_is_forbidden(self):
        uc, _ = _upsert(owner="8")
        with pytest.raises(PermissionError):
            await uc.execute("agent-1", "7", UpsertAlertReceiverRequest(), "req")

    @pytest.mark.asyncio
    async def test_missing_agent_is_value_error(self):
        uc, _ = _upsert(owner=None)
        with pytest.raises(ValueError):
            await uc.execute("agent-1", "7", UpsertAlertReceiverRequest(), "req")

    def test_prefix_is_capped(self):
        with pytest.raises(ValueError):
            UpsertAlertReceiverRequest(instruction_prefix="x" * 301)


class TestGetAndRotate:
    @pytest.mark.asyncio
    async def test_get_unconfigured(self):
        uc = GetAlertReceiverUseCase(FakeReceiverRepo(), _agent_repo(), MagicMock())
        resp = await uc.execute("agent-1", "7", "req")
        assert resp.configured is False and resp.token_hint is None

    @pytest.mark.asyncio
    async def test_rotate_replaces_hash(self):
        upsert, receivers = _upsert()
        first = await upsert.execute(
            "agent-1", "7", UpsertAlertReceiverRequest(), "req"
        )
        rotate = RotateAlertTokenUseCase(
            receivers, _agent_repo(), MagicMock(), now_fn=lambda: NOW
        )
        resp = await rotate.execute("agent-1", "7", "req")
        stored = receivers.items["agent-1"]
        assert resp.token != first.token
        assert AlertTokenPolicy.verify(resp.token, stored.token_hash)
        assert not AlertTokenPolicy.verify(first.token, stored.token_hash)

    @pytest.mark.asyncio
    async def test_rotate_without_receiver_is_lookup_error(self):
        rotate = RotateAlertTokenUseCase(
            FakeReceiverRepo(), _agent_repo(), MagicMock(), now_fn=lambda: NOW
        )
        with pytest.raises(LookupError):
            await rotate.execute("agent-1", "7", "req")


class TestListReceipts:
    @pytest.mark.asyncio
    async def test_lists_recent_receipts(self):
        upsert, receivers = _upsert()
        await upsert.execute("agent-1", "7", UpsertAlertReceiverRequest(), "req")
        receipts = FakeReceiptRepo()
        rid = receivers.items["agent-1"].id
        await receipts.add(
            AlertReceipt(
                id="rc-1",
                receiver_id=rid,
                agent_id="agent-1",
                group_key_hash="g",
                fingerprints_hash="f",
                firing_count=2,
                result="enqueued",
                skip_reason=None,
                job_id="job-1",
                received_at=NOW,
                request_id="r",
            ),
            "r",
        )
        uc = ListAlertReceiptsUseCase(receivers, receipts, _agent_repo(), MagicMock())
        items = await uc.execute("agent-1", "7", 20, "req")
        assert [(i.result, i.job_id, i.firing_count) for i in items] == [
            ("enqueued", "job-1", 2)
        ]


def test_timestamps_are_sent_as_explicit_utc():
    """저장값은 UTC naive — 응답에는 오프셋을 붙여 브라우저 오해석을 막는다."""
    from src.application.agent_alert.schemas import AlertReceiptResponse

    receipt = AlertReceipt(
        id="rc",
        receiver_id="r",
        agent_id="a",
        group_key_hash="g",
        fingerprints_hash="f",
        firing_count=1,
        result="disabled",
        skip_reason=None,
        job_id=None,
        received_at=NOW,
        request_id="q",
    )
    assert AlertReceiptResponse.of(receipt).received_at == "2026-11-24T07:30:00+00:00"
