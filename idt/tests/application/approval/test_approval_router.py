"""approval_router 단위 테스트 — 라우터 단독 마운트.

Design Ref: §4 (API), §6.1 (에러 매핑), §8.2 L1.

앱 전체(main.py)를 띄우지 않고 APIRouter 만 마운트하는 이유: 이 저장소의
tests/api 는 앱 와이어링 의존성(AssembleAuthContextUseCase) 때문에 선행
실패가 24건 있다. 라우터 계약 검증에 그 배선까지 끌어올 이유가 없다.
"""
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes import approval_router as mod
from src.application.approval.errors import (
    ApprovalAgentChangedError,
    ApprovalConflictError,
    ApprovalExpiredError,
    ApprovalForbiddenError,
    ApprovalInvalidWindowError,
    ApprovalNotFoundError,
)
from src.application.approval.list_use_case import ApprovalPage

_NOW = datetime(2026, 9, 21, 9, 0, 0)


def _approval(**over):
    base = dict(
        id="ap1", agent_id="ag1", tool_id="email_send",
        draft="본문" * 200, status="pending", execute_after=None,
        expires_at=_NOW + timedelta(hours=24), seen_at=None, created_at=_NOW,
        tool_args={"to": "a@b.c"}, worker_id="w1", decided_by=None,
        decided_at=None, decision_reason=None, executed_at=None,
        error_message=None,
    )
    base.update(over)
    return MagicMock(**base)


def _client(*, decide=None, listing=None, tick=None):
    app = FastAPI()
    app.include_router(mod.router)
    app.include_router(mod.internal_router)

    app.dependency_overrides[mod.get_current_user] = lambda: MagicMock(id="u1")
    app.dependency_overrides[mod.get_decide_approval_use_case] = (
        lambda: decide or MagicMock()
    )
    app.dependency_overrides[mod.get_list_approvals_use_case] = (
        lambda: listing or MagicMock()
    )
    app.dependency_overrides[mod.get_execute_due_approvals_use_case] = (
        lambda: tick or MagicMock()
    )
    app.dependency_overrides[mod.verify_scheduler_token] = lambda: None
    return TestClient(app)


class TestList:
    def test_목록을_반환한다(self):
        uc = MagicMock()
        uc.list = AsyncMock(return_value=ApprovalPage(items=[_approval()], total=1))
        r = _client(listing=uc).get("/api/v1/approvals")
        assert r.status_code == 200
        assert r.json()["pagination"]["total"] == 1
        assert r.json()["data"][0]["id"] == "ap1"

    def test_초안은_미리보기로_잘린다(self):
        """목록 응답을 가볍게 — 전문은 상세에서."""
        uc = MagicMock()
        uc.list = AsyncMock(return_value=ApprovalPage(items=[_approval()], total=1))
        r = _client(listing=uc).get("/api/v1/approvals")
        assert len(r.json()["data"][0]["draft_preview"]) == 200

    def test_status_쿼리가_튜플로_전달된다(self):
        uc = MagicMock()
        uc.list = AsyncMock(return_value=ApprovalPage(items=[], total=0))
        _client(listing=uc).get("/api/v1/approvals?status=executed,failed")
        assert uc.list.await_args.kwargs["statuses"] == ("executed", "failed")

    def test_status_미지정이면_UseCase_기본값을_쓴다(self):
        uc = MagicMock()
        uc.list = AsyncMock(return_value=ApprovalPage(items=[], total=0))
        _client(listing=uc).get("/api/v1/approvals")
        assert "statuses" not in uc.list.await_args.kwargs

    def test_size_상한_초과는_422(self):
        assert _client().get("/api/v1/approvals?size=999").status_code == 422


class TestApprove:
    def test_즉시_집행되면_executed를_반환(self):
        uc = MagicMock()
        uc.approve = AsyncMock(return_value=_approval(status="executed"))
        r = _client(decide=uc).post("/api/v1/approvals/ap1/approve")
        assert r.status_code == 200
        assert r.json()["status"] == "executed"

    def test_예약되면_UTC_명시_시각과_안내문구를_반환(self):
        """Check G12 — 서버가 벽시계 문구를 만들면 타임존을 모른 채 UTC 로
        적게 된다('(UTC)에 집행 예정'). 시각은 tz 를 붙여 내려주고, 사람이
        읽는 문구의 시각 포맷은 사용자 로캘을 아는 프론트가 만든다."""
        uc = MagicMock()
        uc.approve = AsyncMock(return_value=_approval(
            status="scheduled", execute_after=datetime(2026, 9, 21, 15, 0)
        ))
        body = _client(decide=uc).post("/api/v1/approvals/ap1/approve").json()
        assert body["status"] == "scheduled"
        assert body["execute_after"].endswith(("Z", "+00:00"))
        assert "UTC" not in body["message"]
        assert "예약" in body["message"]

    def test_집행_실패는_사유를_문구에_담는다(self):
        uc = MagicMock()
        uc.approve = AsyncMock(return_value=_approval(
            status="failed", error_message="SMTP 연결 실패"
        ))
        body = _client(decide=uc).post("/api/v1/approvals/ap1/approve").json()
        assert "SMTP 연결 실패" in body["message"]

    def test_execute_only_쿼리가_전달된다(self):
        uc = MagicMock()
        uc.approve = AsyncMock(return_value=_approval(status="executed"))
        _client(decide=uc).post("/api/v1/approvals/ap1/approve?execute_only=true")
        assert uc.approve.await_args.kwargs["execute_only"] is True


class TestErrorMapping:
    """Design §6.1 — 오류가 소유한 code/status 를 라우터가 그대로 옮긴다."""

    @pytest.mark.parametrize(
        ("error", "status", "code"),
        [
            (ApprovalNotFoundError("x"), 404, "APPROVAL_NOT_FOUND"),
            (ApprovalForbiddenError("x"), 403, "APPROVAL_FORBIDDEN"),
            (ApprovalConflictError("x"), 409, "APPROVAL_NOT_PENDING"),
            (ApprovalExpiredError("x"), 410, "APPROVAL_EXPIRED"),
            (ApprovalInvalidWindowError("x"), 400, "APPROVAL_INVALID_WINDOW"),
            (ApprovalAgentChangedError("x"), 409, "APPROVAL_AGENT_CHANGED"),
        ],
    )
    def test_오류가_상태코드와_코드로_매핑된다(self, error, status, code):
        uc = MagicMock()
        uc.approve = AsyncMock(side_effect=error)
        r = _client(decide=uc).post("/api/v1/approvals/ap1/approve")
        assert r.status_code == status
        assert r.json()["detail"]["code"] == code

    def test_중복_클릭은_409로_정상_응답한다(self):
        """예외 스택이 아니라 프론트가 다룰 수 있는 응답이어야 한다."""
        uc = MagicMock()
        uc.approve = AsyncMock(side_effect=ApprovalConflictError("status=executed"))
        r = _client(decide=uc).post("/api/v1/approvals/ap1/approve")
        assert r.status_code == 409
        assert "executed" in r.json()["detail"]["message"]


class TestReject:
    def test_사유와_함께_거절한다(self):
        uc = MagicMock()
        uc.reject = AsyncMock(return_value=_approval(status="rejected"))
        r = _client(decide=uc).post(
            "/api/v1/approvals/ap1/reject", json={"reason": "한도 초과"}
        )
        assert r.status_code == 200
        assert uc.reject.await_args.kwargs["reason"] == "한도 초과"

    def test_사유_없으면_422(self):
        r = _client().post("/api/v1/approvals/ap1/reject", json={})
        assert r.status_code == 422

    def test_빈_사유는_422(self):
        r = _client().post("/api/v1/approvals/ap1/reject", json={"reason": ""})
        assert r.status_code == 422


class TestDetailAndSeen:
    def test_상세는_초안_전문과_인자를_준다(self):
        uc = MagicMock()
        uc.get = AsyncMock(return_value=(_approval(), None))
        body = _client(decide=uc).get("/api/v1/approvals/ap1").json()
        assert len(body["draft"]) == 400
        assert body["tool_args"] == {"to": "a@b.c"}

    def test_확인_처리는_204(self):
        uc = MagicMock()
        uc.mark_seen = AsyncMock()
        r = _client(listing=uc).post("/api/v1/approvals/ap1/seen")
        assert r.status_code == 204


class TestInternalTick:
    def test_tick_결과를_반환한다(self):
        from src.application.approval.execute_scheduler import TickResult

        uc = MagicMock()
        uc.run = AsyncMock(return_value=TickResult(
            claimed_count=2, executed_count=1, failed_count=1, expired_count=3
        ))
        r = _client(tick=uc).post("/api/v1/internal/approvals/tick")
        assert r.status_code == 200
        assert r.json() == {
            "claimed_count": 2, "executed_count": 1,
            "failed_count": 1, "expired_count": 3,
        }

    def test_스케줄러_토큰_검증이_걸려_있다(self):
        """인증 없이 집행을 트리거할 수 있으면 게이트가 무의미해진다."""
        app = FastAPI()
        app.include_router(mod.internal_router)
        app.dependency_overrides[mod.get_execute_due_approvals_use_case] = MagicMock
        # verify_scheduler_token 을 override 하지 않으면 NotImplementedError
        with pytest.raises(NotImplementedError):
            TestClient(app).post("/api/v1/internal/approvals/tick")


class TestGateSettingsRouter:
    """approval-gate Check G3 — 에이전트별 게이트 설정 입구."""

    def _client(self, uc):
        app = FastAPI()
        app.include_router(mod.agent_gate_router)
        app.dependency_overrides[mod.get_current_user] = lambda: MagicMock(id="u1")
        app.dependency_overrides[mod.get_gate_settings_use_case] = lambda: uc
        return TestClient(app)

    _SETTINGS = {"available": True, "enabled": True, "is_enforced": False,
                 "config": {"mode": "always", "execute_after": "0 0 * * *",
                            "expires_hours": 24}}

    def test_조회(self):
        uc = MagicMock()
        uc.get = AsyncMock(return_value=self._SETTINGS)
        r = self._client(uc).get("/api/v1/agents/ag1/approval-gate")
        assert r.status_code == 200
        assert r.json()["config"]["execute_after"] == "0 0 * * *"

    def test_저장은_검증된_config를_넘긴다(self):
        uc = MagicMock()
        uc.put = AsyncMock(return_value=self._SETTINGS)
        r = self._client(uc).put(
            "/api/v1/agents/ag1/approval-gate",
            json={"mode": "always", "execute_after": "0 0 * * *",
                  "expires_hours": 24},
        )
        assert r.status_code == 200
        cfg = uc.put.await_args.kwargs["config"]
        assert cfg["execute_after"] == "0 0 * * *"
        assert "timezone" not in cfg  # 미지정이면 도메인 기본(Asia/Seoul)

    def test_타임존을_지정하면_전달된다(self):
        uc = MagicMock()
        uc.put = AsyncMock(return_value=self._SETTINGS)
        self._client(uc).put(
            "/api/v1/agents/ag1/approval-gate",
            json={"timezone": "UTC"},
        )
        assert uc.put.await_args.kwargs["config"]["timezone"] == "UTC"

    def test_검증_실패는_400(self):
        uc = MagicMock()
        uc.put = AsyncMock(side_effect=ValueError("invalid cron"))
        r = self._client(uc).put(
            "/api/v1/agents/ag1/approval-gate", json={"execute_after": "x"}
        )
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "APPROVAL_GATE_INVALID_CONFIG"

    def test_비소유자는_403(self):
        uc = MagicMock()
        uc.get = AsyncMock(side_effect=ApprovalForbiddenError("ag1"))
        r = self._client(uc).get("/api/v1/agents/ag1/approval-gate")
        assert r.status_code == 403

    def test_카탈로그_비활성은_409(self):
        from src.application.approval.gate_settings_use_case import (
            GateUnavailableError,
        )

        uc = MagicMock()
        uc.put = AsyncMock(side_effect=GateUnavailableError("off"))
        r = self._client(uc).put("/api/v1/agents/ag1/approval-gate", json={})
        assert r.status_code == 409



class TestTimezoneSerialization:
    """Check G12 — naive datetime 이 Z 없이 나가면 프론트가 로컬 시각으로 읽는다."""

    def test_목록_시각에_UTC_표시가_붙는다(self):
        uc = MagicMock()
        uc.list = AsyncMock(return_value=ApprovalPage(items=[_approval()], total=1))
        item = _client(listing=uc).get("/api/v1/approvals").json()["data"][0]
        for key in ("expires_at", "created_at"):
            assert item[key].endswith(("Z", "+00:00")), key

    def test_상세_시각에도_UTC_표시가_붙는다(self):
        uc = MagicMock()
        uc.get = AsyncMock(return_value=(_approval(), "금리 에이전트"))
        body = _client(decide=uc).get("/api/v1/approvals/ap1").json()
        assert body["expires_at"].endswith(("Z", "+00:00"))


class TestAgentName:
    """Check G6 — 카드에 에이전트명이 나와야 무엇을 승인하는지 알 수 있다."""

    def test_목록에_에이전트명이_채워진다(self):
        uc = MagicMock()
        uc.list = AsyncMock(return_value=ApprovalPage(
            items=[_approval()], total=1, agent_names={"ag1": "금리 에이전트"},
        ))
        item = _client(listing=uc).get("/api/v1/approvals").json()["data"][0]
        assert item["agent_name"] == "금리 에이전트"

    def test_상세에_에이전트명이_채워진다(self):
        uc = MagicMock()
        uc.get = AsyncMock(return_value=(_approval(), "금리 에이전트"))
        body = _client(decide=uc).get("/api/v1/approvals/ap1").json()
        assert body["agent_name"] == "금리 에이전트"
