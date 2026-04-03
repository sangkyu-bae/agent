"""LangGraphPlanner 인프라 테스트 (BaseChatModel Mock 사용)."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domain.planner.schemas import PlanResult, PlanStep
from src.infrastructure.planner.langgraph_planner import LangGraphPlanner


def _make_logger():
    logger = MagicMock()
    logger.info = MagicMock()
    logger.warning = MagicMock()
    logger.error = MagicMock()
    return logger


def _make_valid_llm_response(confidence: float = 0.9) -> str:
    return json.dumps({
        "steps": [
            {
                "step_index": 0,
                "description": "문서 검색",
                "tool_ids": [],
                "search_strategy": "hybrid",
                "expected_output": "관련 문서 목록",
            }
        ],
        "confidence": confidence,
        "reasoning": "하이브리드 검색이 적합",
        "requires_clarification": False,
        "clarifying_questions": [],
    })


class TestLangGraphPlanner:

    def _make_llm(self, response_content: str):
        llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = response_content
        llm.ainvoke = AsyncMock(return_value=mock_response)
        return llm

    @pytest.mark.asyncio
    async def test_plan_returns_plan_result(self):
        llm = self._make_llm(_make_valid_llm_response(confidence=0.9))
        planner = LangGraphPlanner(llm=llm, logger=_make_logger())

        result = await planner.plan(
            query="금리 인상 영향 분석",
            context={},
            request_id="req-1",
        )

        assert isinstance(result, PlanResult)
        assert len(result.steps) == 1
        assert result.confidence == 0.9

    @pytest.mark.asyncio
    async def test_plan_triggers_replan_on_low_confidence(self):
        """저신뢰 응답 후 재계획 시 LLM이 2회 호출된다."""
        low_conf = _make_valid_llm_response(confidence=0.3)
        high_conf = _make_valid_llm_response(confidence=0.9)

        llm = MagicMock()
        mock_low = MagicMock()
        mock_low.content = low_conf
        mock_high = MagicMock()
        mock_high.content = high_conf
        llm.ainvoke = AsyncMock(side_effect=[mock_low, mock_high])

        planner = LangGraphPlanner(llm=llm, logger=_make_logger())
        result = await planner.plan(query="질문", context={}, request_id="req-2")

        assert llm.ainvoke.call_count == 2
        assert result.confidence == 0.9

    @pytest.mark.asyncio
    async def test_plan_stops_at_max_attempts(self):
        """MAX_REPLAN_ATTEMPTS 이후 저신뢰 결과도 그대로 반환한다."""
        low_conf = _make_valid_llm_response(confidence=0.3)
        llm = self._make_llm(low_conf)
        # 계속 저신뢰만 반환
        llm.ainvoke = AsyncMock(return_value=MagicMock(content=low_conf))

        planner = LangGraphPlanner(llm=llm, logger=_make_logger())
        result = await planner.plan(query="질문", context={}, request_id="req-3")

        # 무한루프 없이 반환됨
        assert isinstance(result, PlanResult)
        assert result.confidence == 0.3

    @pytest.mark.asyncio
    async def test_plan_parse_failure_fallback(self):
        """JSON 파싱 실패 시 저신뢰 fallback PlanResult 반환."""
        llm = self._make_llm("invalid json response {{")
        planner = LangGraphPlanner(llm=llm, logger=_make_logger())

        result = await planner.plan(query="질문", context={}, request_id="req-4")

        assert isinstance(result, PlanResult)
        assert result.confidence == 0.0
        assert result.steps == []

    @pytest.mark.asyncio
    async def test_plan_logs_warning_on_parse_failure(self):
        """JSON 파싱 실패 시 WARNING 로그를 기록한다."""
        logger = _make_logger()
        llm = self._make_llm("bad json")
        planner = LangGraphPlanner(llm=llm, logger=logger)

        await planner.plan(query="질문", context={}, request_id="req-5")

        logger.warning.assert_called()
        all_warning_messages = [str(c) for c in logger.warning.call_args_list]
        assert any("parse" in msg.lower() for msg in all_warning_messages)
