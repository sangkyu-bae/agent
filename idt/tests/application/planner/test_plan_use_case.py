"""PlanUseCase 애플리케이션 테스트."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.planner.plan_use_case import PlanUseCase
from src.application.planner.schemas import PlanRequest, PlanResponse
from src.domain.planner.schemas import PlanResult, PlanStep


def _make_logger():
    logger = MagicMock()
    logger.info = MagicMock()
    logger.error = MagicMock()
    return logger


def _make_plan_result(confidence: float = 0.9) -> PlanResult:
    step = PlanStep(step_index=0, description="검색", expected_output="문서 목록")
    return PlanResult(
        query="금리 인상 영향",
        steps=[step],
        confidence=confidence,
        reasoning="검색 필요",
    )


class TestPlanUseCase:

    def _make_use_case(self, result: PlanResult):
        planner = MagicMock()
        planner.plan = AsyncMock(return_value=result)
        logger = _make_logger()
        return PlanUseCase(planner=planner, logger=logger), planner, logger

    @pytest.mark.asyncio
    async def test_execute_returns_plan_response(self):
        result = _make_plan_result()
        use_case, _, _ = self._make_use_case(result)
        request = PlanRequest(query="금리 인상 영향", request_id="req-1")

        response = await use_case.execute(request)

        assert isinstance(response, PlanResponse)
        assert response.query == "금리 인상 영향"
        assert response.confidence == 0.9
        assert response.request_id == "req-1"
        assert len(response.steps) == 1

    @pytest.mark.asyncio
    async def test_execute_logs_start_and_complete(self):
        result = _make_plan_result()
        use_case, _, logger = self._make_use_case(result)
        request = PlanRequest(query="질문", request_id="req-2")

        await use_case.execute(request)

        assert logger.info.call_count == 2
        first_call = logger.info.call_args_list[0][0][0]
        second_call = logger.info.call_args_list[1][0][0]
        assert "started" in first_call.lower()
        assert "completed" in second_call.lower()

    @pytest.mark.asyncio
    async def test_execute_logs_error_on_exception(self):
        planner = MagicMock()
        planner.plan = AsyncMock(side_effect=RuntimeError("LLM error"))
        logger = _make_logger()
        use_case = PlanUseCase(planner=planner, logger=logger)
        request = PlanRequest(query="질문", request_id="req-3")

        with pytest.raises(RuntimeError):
            await use_case.execute(request)

        logger.error.assert_called_once()
        call_kwargs = logger.error.call_args
        assert "exception" in call_kwargs[1]

    @pytest.mark.asyncio
    async def test_execute_propagates_request_id(self):
        result = _make_plan_result()
        use_case, planner, _ = self._make_use_case(result)
        request = PlanRequest(query="질문", request_id="req-xyz")

        await use_case.execute(request)

        planner.plan.assert_called_once_with(
            query="질문",
            context={},
            request_id="req-xyz",
        )

    @pytest.mark.asyncio
    async def test_execute_passes_context(self):
        result = _make_plan_result()
        use_case, planner, _ = self._make_use_case(result)
        ctx = {"user_id": "u1", "document_id": "d1"}
        request = PlanRequest(query="질문", context=ctx, request_id="req-4")

        await use_case.execute(request)

        planner.plan.assert_called_once_with(
            query="질문",
            context=ctx,
            request_id="req-4",
        )
