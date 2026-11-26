"""접근 판정 유스케이스 — stock-analysis-agents design DD10, §4 AccessPort."""

from unittest.mock import MagicMock

import pytest
from src.application.market_analysis.access import (
    GetAccessUseCase,
    MarketAnalysisForbiddenError,
)
from src.domain.market_analysis.access import MANAGE_CODE, VIEW_CODE, AccessDecision


class FakeCodes:
    def __init__(self, codes: frozenset[str] = frozenset(), fail: bool = False):
        self.codes = codes
        self.fail = fail
        self.calls: list[tuple[int, str]] = []

    async def codes_for(
        self, user_id: int, role: str, request_id: str
    ) -> frozenset[str]:
        self.calls.append((user_id, role))
        if self.fail:
            raise RuntimeError("db down")
        return self.codes


async def test_admin_skips_permission_lookup():
    reader = FakeCodes()
    uc = GetAccessUseCase(reader, MagicMock())
    assert await uc.execute(user_id=1, role="admin", request_id="r") == AccessDecision(
        True, True, True
    )
    assert reader.calls == []


async def test_user_with_view_code():
    uc = GetAccessUseCase(FakeCodes(frozenset({VIEW_CODE})), MagicMock())
    decision = await uc.execute(user_id=7, role="user", request_id="r")
    assert (decision.can_view, decision.can_manage) == (True, False)


async def test_lookup_failure_denies():
    # 권한 조회가 실패하면 열어 주지 않는다 (fail-closed)
    logger = MagicMock()
    uc = GetAccessUseCase(FakeCodes(fail=True), logger)
    decision = await uc.execute(user_id=7, role="user", request_id="r")
    assert (decision.can_view, decision.can_manage) == (False, False)
    logger.warning.assert_called_once()


async def test_require_view_and_manage():
    uc = GetAccessUseCase(FakeCodes(frozenset({VIEW_CODE})), MagicMock())
    await uc.require(user_id=7, role="user", level="view", request_id="r")
    with pytest.raises(MarketAnalysisForbiddenError):
        await uc.require(user_id=7, role="user", level="manage", request_id="r")

    manager = GetAccessUseCase(FakeCodes(frozenset({MANAGE_CODE})), MagicMock())
    await manager.require(user_id=7, role="user", level="manage", request_id="r")


async def test_require_rejects_unknown_level():
    uc = GetAccessUseCase(FakeCodes(), MagicMock())
    with pytest.raises(ValueError):
        await uc.require(user_id=1, role="admin", level="owner", request_id="r")
