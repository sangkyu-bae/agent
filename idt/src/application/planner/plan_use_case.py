"""PlanUseCase: Planner 실행 유즈케이스."""
from src.application.planner.schemas import PlanRequest, PlanResponse
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.planner.interfaces import PlannerInterface


class PlanUseCase:

    def __init__(self, planner: PlannerInterface, logger: LoggerInterface) -> None:
        self._planner = planner
        self._logger = logger

    async def execute(self, request: PlanRequest) -> PlanResponse:
        self._logger.info(
            "Planner started",
            request_id=request.request_id,
            query_len=len(request.query),
        )
        try:
            result = await self._planner.plan(
                query=request.query,
                context=request.context,
                request_id=request.request_id,
            )
            self._logger.info(
                "Planner completed",
                request_id=request.request_id,
                steps=len(result.steps),
                confidence=result.confidence,
            )
            return PlanResponse.from_domain(result, request.request_id)
        except Exception as e:
            self._logger.error(
                "Planner failed",
                exception=e,
                request_id=request.request_id,
            )
            raise
