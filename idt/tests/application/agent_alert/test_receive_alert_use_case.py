"""ReceiveAlertUseCase — firewall-agent design §2.2 알림 경로 / §4.3."""

import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.application.agent_alert.receive_alert_use_case import (
    AlertAuthError,
    ReceiveAlertUseCase,
)
from src.domain.agent_alert.entity import AlertReceiver
from src.domain.agent_alert.policies import AlertTokenPolicy
from src.domain.agent_automation.busy import BusyVerdict

from .fakes import FakeJobRepo, FakeReceiptRepo, FakeReceiverRepo

FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "agent_alert"
    / "grafana_webhook_firing.json"
)
NOW = datetime(2026, 11, 24, 7, 30, 15)
TOKEN = "tok-abcdefghijklmnopqrstuvwxyz-0123456789"


def _body(**patch) -> bytes:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload.update(patch)
    return json.dumps(payload).encode()


def _receiver(**overrides) -> AlertReceiver:
    base = dict(
        id="rcv-1",
        agent_id="agent-1",
        user_id="7",
        enabled=True,
        skip_when_busy=True,
        token_hash=AlertTokenPolicy.hash(TOKEN),
        token_hint=TOKEN[-4:],
        instruction_prefix="정책대로 처리하라.",
        created_at=NOW,
        updated_at=NOW,
    )
    base.update(overrides)
    return AlertReceiver(**base)


def _uc(receiver=None, busy=BusyVerdict.idle(), *, now=NOW):
    receivers = FakeReceiverRepo(receiver if receiver is not None else _receiver())
    receipts = FakeReceiptRepo()
    jobs = FakeJobRepo()
    checker = MagicMock()
    checker.check = AsyncMock(return_value=busy)
    uc = ReceiveAlertUseCase(
        receiver_repo=receivers,
        receipt_repo=receipts,
        job_repo=jobs,
        busy_checker=checker,
        logger=MagicMock(),
        dedupe_seconds=600,
        now_fn=lambda: now,
    )
    return uc, receipts, jobs, checker


async def _call(uc, body=None, auth=f"Bearer {TOKEN}", agent="agent-1"):
    return await uc.execute(agent, auth, body if body is not None else _body(), "req-1")


# ── 인증 ────────────────────────────────────────────────────────────────


class TestAuth:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("auth", [None, "", "Bearer wrong", f"Basic {TOKEN}"])
    async def test_bad_token_is_rejected_without_receipt(self, auth):
        uc, receipts, jobs, _ = _uc()
        with pytest.raises(AlertAuthError):
            await _call(uc, auth=auth)
        assert receipts.items == [] and jobs.jobs == []

    @pytest.mark.asyncio
    async def test_unknown_agent_is_the_same_401(self):
        uc, *_ = _uc()
        with pytest.raises(AlertAuthError):
            await _call(uc, agent="agent-x")


# ── 결과 분기 ───────────────────────────────────────────────────────────


class TestResults:
    @pytest.mark.asyncio
    async def test_firing_alert_enqueues_a_background_job(self):
        uc, receipts, jobs, checker = _uc()
        result = await _call(uc)
        assert result.result == "enqueued" and result.job_id == jobs.jobs[0].id
        job = jobs.jobs[0]
        assert (job.agent_id, job.user_id, job.source, job.status) == (
            "agent-1",
            "7",
            "alert",
            "queued",
        )
        assert job.query.startswith("정책대로 처리하라.")
        assert "src_ip=172.28.10.66" in job.query and len(job.query) <= 2000
        (receipt,) = receipts.items
        assert receipt.result == "enqueued" and receipt.job_id == job.id
        assert receipt.firing_count == 1 and result.receipt_id == receipt.id
        checker.check.assert_awaited_once_with("agent-1", "req-1")

    @pytest.mark.asyncio
    async def test_same_payload_again_is_duplicate(self):
        uc, receipts, jobs, _ = _uc()
        await _call(uc)
        second = await _call(uc)
        assert second.result == "duplicate" and second.job_id is None
        assert len(jobs.jobs) == 1 and len(receipts.items) == 2

    @pytest.mark.asyncio
    async def test_duplicate_window_expires(self):
        uc, receipts, jobs, _ = _uc()
        await _call(uc)
        later, _, _, _ = _uc(now=NOW + timedelta(minutes=11))
        later._receipt_repo = receipts
        later._job_repo = jobs
        assert (await _call(later)).result == "enqueued"

    @pytest.mark.asyncio
    async def test_resolved_only_does_not_run(self):
        payload = json.loads(_body())
        payload["alerts"][0]["status"] = "resolved"
        uc, receipts, jobs, _ = _uc()
        result = await _call(uc, body=json.dumps(payload).encode())
        assert result.result == "resolved_only" and jobs.jobs == []
        assert receipts.items[0].firing_count == 0

    @pytest.mark.asyncio
    async def test_disabled_receiver_does_not_run(self):
        uc, receipts, jobs, checker = _uc(_receiver(enabled=False))
        result = await _call(uc)
        assert result.result == "disabled" and jobs.jobs == []
        checker.check.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_busy_agent_is_skipped_with_reason(self):
        uc, receipts, jobs, _ = _uc(
            busy=BusyVerdict(busy=True, reason="approval_pending")
        )
        result = await _call(uc)
        assert result.result == "skipped_busy" and jobs.jobs == []
        assert receipts.items[0].skip_reason == "approval_pending"

    @pytest.mark.asyncio
    async def test_skip_option_off_ignores_busy(self):
        uc, _, jobs, checker = _uc(
            _receiver(skip_when_busy=False),
            busy=BusyVerdict(busy=True, reason="approval_pending"),
        )
        assert (await _call(uc)).result == "enqueued"
        checker.check.assert_not_awaited()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("body", [b"not json", b"[]", b'{"alerts": "x"}'])
    async def test_invalid_payload_is_recorded_not_raised(self, body):
        uc, receipts, jobs, _ = _uc()
        result = await _call(uc, body=body)
        assert result.result == "invalid_payload" and jobs.jobs == []
        assert receipts.items[0].result == "invalid_payload"
