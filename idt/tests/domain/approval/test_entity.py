"""approval-gate: ApprovalRequest / ResumeSnapshot 엔티티 단위 테스트."""
from datetime import datetime

import pytest

from src.domain.approval.entity import (
    ApprovalRequest,
    ResumeSnapshot,
    transition,
)

_NOW = datetime(2026, 9, 21, 9, 0, 0)


def _snapshot() -> ResumeSnapshot:
    return ResumeSnapshot(
        schema_version=1,
        agent_updated_at=_NOW,
        worker_id="w1",
        state_json='{"messages": []}',
    )


def _request(status: str = "pending") -> ApprovalRequest:
    return ApprovalRequest(
        id="ap1",
        run_id="r1",
        agent_id="ag1",
        requested_by="u1",
        worker_id="w1",
        tool_id="email_send",
        tool_args={"to": "a@b.c"},
        draft="본문",
        status=status,
        idempotency_key="r1:w1:tc1",
        snapshot=_snapshot(),
        expires_at=_NOW,
        request_id="req1",
        created_at=_NOW,
        updated_at=_NOW,
    )


class TestApprovalRequestDefaults:
    def test_선택_필드는_기본값으로_비어있다(self):
        req = _request()
        assert req.execute_after is None       # 즉시 집행
        assert req.decided_by is None
        assert req.decision_reason is None
        assert req.seen_at is None             # 미확인 = 벨 배지 대상
        assert req.tags == []

    def test_tags는_인스턴스마다_독립이다(self):
        """가변 기본값 공유 버그 방지."""
        a, b = _request(), _request()
        a.tags.append("x")
        assert b.tags == []


class TestIsTerminal:
    @pytest.mark.parametrize(
        "status", ["executed", "rejected", "expired", "failed"]
    )
    def test_종료_상태(self, status):
        assert _request(status).is_terminal is True

    @pytest.mark.parametrize("status", ["pending", "approved", "scheduled"])
    def test_진행_상태(self, status):
        assert _request(status).is_terminal is False


class TestTransitionTable:
    def test_전이표_직접_호출(self):
        assert transition("pending", "approve") == "approved"

    def test_금지_전이_메시지에_현재상태와_이벤트가_담긴다(self):
        with pytest.raises(ValueError, match="executed"):
            transition("executed", "approve")

    def test_모든_종료_상태에서_나가는_전이는_없다(self):
        """FR-25 — 특히 failed 에서 자동 재시도(execute)가 불가능해야 한다."""
        for status in ("executed", "rejected", "expired", "failed"):
            for event in ("approve", "reject", "schedule", "execute", "fail"):
                with pytest.raises(ValueError):
                    transition(status, event)


class TestResumeSnapshot:
    def test_스키마_버전을_보유한다(self):
        """포맷 변경 시 낡은 스냅샷을 식별해 재개를 거부하기 위한 필드."""
        assert _snapshot().schema_version == 1

    def test_에이전트_정의_시각을_보유한다(self):
        """FR-14 — 재개 직전 agent_definition.updated_at 과 대조한다."""
        assert _snapshot().agent_updated_at == _NOW

    def test_불변이다(self):
        with pytest.raises(Exception):
            _snapshot().worker_id = "다른워커"
