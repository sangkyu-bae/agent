"""접근 판정 유스케이스.

Design Ref: stock-analysis-agents DD10, §5.1 (GET /access, view/manage 의존성).
Plan SC: SC-6 — 권한 없는 사용자는 메뉴가 보이지 않고 API 가 403 이다.
"""

from __future__ import annotations

from src.application.market_analysis.ports import PermissionCodesReader
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.market_analysis.access import ADMIN_ROLE, AccessDecision, AccessPolicy

_LEVELS = ("view", "manage")


class MarketAnalysisForbiddenError(Exception):
    """view/manage 권한 없음 → 라우터가 403 MA_FORBIDDEN 으로 바꾼다."""


class GetAccessUseCase:
    def __init__(self, codes: PermissionCodesReader, logger: LoggerInterface) -> None:
        self._codes = codes
        self._logger = logger

    async def execute(
        self, *, user_id: int, role: str, request_id: str
    ) -> AccessDecision:
        if role == ADMIN_ROLE:
            return AccessPolicy.decide(role=role, codes=frozenset())
        try:
            codes = await self._codes.codes_for(user_id, role, request_id)
        except Exception as e:  # noqa: BLE001 — 조회 실패는 닫는다 (fail-closed)
            self._logger.warning(
                "market_analysis access lookup failed — denied",
                exception=e,
                request_id=request_id,
                user_id=user_id,
            )
            codes = frozenset()
        return AccessPolicy.decide(role=role, codes=codes)

    async def require(
        self, *, user_id: int, role: str, level: str, request_id: str
    ) -> None:
        if level not in _LEVELS:
            raise ValueError(f"unknown access level: {level}")
        decision = await self.execute(user_id=user_id, role=role, request_id=request_id)
        allowed = decision.can_manage if level == "manage" else decision.can_view
        if not allowed:
            raise MarketAnalysisForbiddenError(level)
