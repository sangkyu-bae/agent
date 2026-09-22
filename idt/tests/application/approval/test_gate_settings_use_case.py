"""ApprovalGateSettingsUseCase 단위 테스트 — 에이전트별 게이트 설정 입구.

approval-gate Check G3: 이전에는 agent_middleware.config 를 쓸 경로가 없어
MergePolicy 의 record 우선 오버라이드가 구현만 되고 데이터가 들어올 수 없었다.
그 결과 execute_after·expires_hours·timezone 이 관리자 default 로 전역 적용됐다.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.approval.errors import ApprovalForbiddenError
from src.application.approval.gate_settings_use_case import (
    ApprovalGateSettingsUseCase,
    GateUnavailableError,
)
from src.domain.middleware.entities import (
    AgentMiddlewareRecord,
    MiddlewareCatalogEntry,
    MiddlewareType,
)


def _catalog(*, is_enforced=False, is_active=True, default=None):
    return [MiddlewareCatalogEntry(
        id="c1", middleware_type=MiddlewareType.APPROVAL_GATE, name="승인 게이트",
        description="", is_enforced=is_enforced, is_active=is_active,
        default_config=default or {"mode": "always", "execute_after": None,
                                   "expires_hours": 168},
        sort_order=100,
    )]


def _uc(*, owner="u1", records=None, catalog=None):
    agent = MagicMock(user_id=owner)
    agent_repo = MagicMock()
    agent_repo.find_by_id = AsyncMock(return_value=agent)
    catalog_repo = MagicMock()
    catalog_repo.list_all = AsyncMock(return_value=catalog or _catalog())
    mw_repo = MagicMock()
    mw_repo.list_by_agent = AsyncMock(return_value=records or [])
    mw_repo.upsert_config = AsyncMock()
    uc = ApprovalGateSettingsUseCase(
        agent_repo=agent_repo, catalog_repo=catalog_repo,
        agent_middleware_repo=mw_repo, logger=MagicMock(),
    )
    return uc, mw_repo


class TestGet:
    @pytest.mark.asyncio
    async def test_설정이_없으면_카탈로그_기본값과_꺼짐(self):
        uc, _ = _uc()
        s = await uc.get("ag1", user_id="u1", request_id="r")
        assert s["enabled"] is False
        assert s["config"]["expires_hours"] == 168
        assert s["is_enforced"] is False

    @pytest.mark.asyncio
    async def test_저장된_오버라이드가_기본값을_덮는다(self):
        rec = AgentMiddlewareRecord(
            agent_id="ag1", middleware_type="approval_gate",
            config={"execute_after": "0 0 * * *", "expires_hours": 24},
        )
        uc, _ = _uc(records=[rec])
        s = await uc.get("ag1", user_id="u1", request_id="r")
        assert s["enabled"] is True
        assert s["config"]["execute_after"] == "0 0 * * *"
        assert s["config"]["expires_hours"] == 24
        assert s["config"]["mode"] == "always"  # default 에서 보존

    @pytest.mark.asyncio
    async def test_강제면_레코드가_없어도_켜짐(self):
        uc, _ = _uc(catalog=_catalog(is_enforced=True))
        s = await uc.get("ag1", user_id="u1", request_id="r")
        assert s["enabled"] is True and s["is_enforced"] is True

    @pytest.mark.asyncio
    async def test_비소유자는_Forbidden(self):
        uc, _ = _uc(owner="남")
        with pytest.raises(ApprovalForbiddenError):
            await uc.get("ag1", user_id="u1", request_id="r")

    @pytest.mark.asyncio
    async def test_카탈로그에서_비활성이면_사용_불가(self):
        uc, _ = _uc(catalog=_catalog(is_active=False))
        s = await uc.get("ag1", user_id="u1", request_id="r")
        assert s["available"] is False


class TestPut:
    @pytest.mark.asyncio
    async def test_검증_후_저장한다(self):
        uc, mw = _uc()
        await uc.put("ag1", user_id="u1", request_id="r",
                     config={"mode": "always", "execute_after": "0 0 * * *",
                             "expires_hours": 24})
        args = mw.upsert_config.await_args
        assert args.kwargs["middleware_type"] == "approval_gate"
        assert args.kwargs["config"]["execute_after"] == "0 0 * * *"

    @pytest.mark.asyncio
    async def test_잘못된_cron은_저장하지_않는다(self):
        """저장 시점 방어 — 통과시키면 승인 버튼에서 터진다."""
        uc, mw = _uc()
        with pytest.raises(ValueError):
            await uc.put("ag1", user_id="u1", request_id="r",
                         config={"execute_after": "매일 자정"})
        mw.upsert_config.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_잘못된_타임존은_저장하지_않는다(self):
        uc, mw = _uc()
        with pytest.raises(ValueError):
            await uc.put("ag1", user_id="u1", request_id="r",
                         config={"timezone": "KST"})
        mw.upsert_config.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_비소유자는_Forbidden(self):
        uc, mw = _uc(owner="남")
        with pytest.raises(ApprovalForbiddenError):
            await uc.put("ag1", user_id="u1", request_id="r", config={})
        mw.upsert_config.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_카탈로그_비활성이면_거부(self):
        uc, mw = _uc(catalog=_catalog(is_active=False))
        with pytest.raises(GateUnavailableError):
            await uc.put("ag1", user_id="u1", request_id="r", config={})
        mw.upsert_config.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_강제된_게이트는_끌_수_없다(self):
        """FR-20 — 소유자가 mode=off 를 저장해도 무시되지만, 저장 자체를
        막아 화면과 실제 동작이 어긋나지 않게 한다."""
        uc, mw = _uc(catalog=_catalog(is_enforced=True))
        with pytest.raises(ValueError):
            await uc.put("ag1", user_id="u1", request_id="r",
                         config={"mode": "off"})
        mw.upsert_config.assert_not_awaited()
