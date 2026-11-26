"""원칙 켜고 끄기 — 운영자 명령 (module-7, HTTP 는 module-8 `PATCH /principles/{id}`).

Design Ref: stock-analysis-agents §5.1, DD9,
Plan FR-12 · FR-15(MANAGE 권한은 라우터가 확인).
"""

from __future__ import annotations

from src.application.market_analysis.ports import PrincipleStore
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.market_analysis.principle import PRIORITY_RANK


class PrincipleNotFoundError(LookupError):
    pass


class InvalidPriorityError(ValueError):
    pass


class SetPrincipleActiveUseCase:
    def __init__(self, *, principles: PrincipleStore, logger: LoggerInterface) -> None:
        self._principles = principles
        self._logger = logger

    async def execute(
        self,
        *,
        principle_id: int,
        is_active: bool,
        priority: str | None,
        updated_by: str,
        request_id: str,
    ) -> None:
        if priority is not None and priority not in PRIORITY_RANK:
            raise InvalidPriorityError(priority)
        found = await self._principles.set_active(
            principle_id=principle_id,
            is_active=is_active,
            priority=priority,
            updated_by=updated_by,
            request_id=request_id,
        )
        if not found:
            raise PrincipleNotFoundError(principle_id)
        self._logger.info(
            "market_analysis principle updated",
            request_id=request_id,
            principle_id=principle_id,
            is_active=is_active,
            priority=priority,
            updated_by=updated_by,
        )
