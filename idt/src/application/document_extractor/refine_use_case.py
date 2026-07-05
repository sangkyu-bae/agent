"""RefineSlotsUseCase: 슬롯 재추천 (Design §3-2, GA3).

stateless — regen_count는 프론트가 전달(유휴 5분 재생성 포함), RegenPolicy로 상한(R5).
"""
from src.application.document_extractor.schemas import (
    RefineResponse,
    TemplateSlotDto,
)
from src.domain.document_extractor.policies import RegenPolicy
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class RefineSlotsUseCase:
    def __init__(
        self, slot_extractor, logger: LoggerInterface, max_regen: int
    ) -> None:
        self._extractor = slot_extractor
        self._logger = logger
        self._max_regen = max_regen

    async def execute(
        self,
        html: str,
        instruction: str,
        prev_slots: list[TemplateSlotDto],
        regen_count: int,
        request_id: str,
    ) -> RefineResponse:
        self._logger.info(
            "RefineSlotsUseCase start",
            request_id=request_id,
            regen_count=regen_count,
            prev_slot_count=len(prev_slots),
        )
        try:
            RegenPolicy.validate(regen_count, self._max_regen)
            suggested = await self._extractor.refine(
                html,
                instruction,
                [dto.to_domain() for dto in prev_slots],
                request_id,
            )
            self._logger.info(
                "RefineSlotsUseCase done",
                request_id=request_id,
                slot_count=len(suggested.slots),
            )
            return RefineResponse(
                suggested_slots=[
                    TemplateSlotDto.from_domain(s) for s in suggested.slots
                ]
            )
        except Exception as e:
            self._logger.error(
                "RefineSlotsUseCase failed", exception=e, request_id=request_id
            )
            raise
