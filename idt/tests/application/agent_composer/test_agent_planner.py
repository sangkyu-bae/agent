"""AgentPlanner 단위 테스트 — Mock LLM structured output (fix-agent-planner-hitl)."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_composer.planner import (
    AgentPlanner,
    _PlanOutput,
    _QuestionOutput,
    _ToolHintOutput,
)
from src.application.agent_composer.interfaces import PlanResult
from src.application.agent_composer.schemas import ComposeCurrentConfig
from src.domain.agent_composer.schemas import (
    BuildPlan,
    CandidateTool,
    ClarificationAnswer,
)


def _make_output(
    confidence: float = 0.9,
    questions: list[_QuestionOutput] | None = None,
) -> _PlanOutput:
    return _PlanOutput(
        requirement_summary="여신 규정 질의응답 에이전트 요구",
        tool_hints=[
            _ToolHintOutput(
                capability="내부 문서 검색",
                suggested_tool_ids=["internal_document_search"],
                note="규정 문서 범위",
            )
        ],
        plan_summary="내부 문서 검색 도구로 규정 질의응답 에이전트를 구성한다.",
        confidence=confidence,
        clarifying_questions=questions or [],
    )


def _candidates() -> list[CandidateTool]:
    return [
        CandidateTool(
            tool_id="internal_document_search",
            name="내부 문서 검색",
            description="내부 하이브리드 검색",
            source="internal",
        ),
        CandidateTool(
            tool_id="tavily_search",
            name="Tavily 웹 검색",
            description="웹 검색 도구",
            source="internal",
        ),
    ]


def _make_planner(output: _PlanOutput | None = None, max_candidates: int = 100):
    mock_llm = MagicMock()
    mock_llm.with_structured_output = MagicMock(return_value=mock_llm)
    mock_llm.ainvoke = AsyncMock(return_value=output or _make_output())
    logger = MagicMock()
    planner = AgentPlanner(
        llm=mock_llm, logger=logger, max_candidates=max_candidates
    )
    return planner, mock_llm, logger


class TestAgentPlannerPlan:
    @pytest.mark.asyncio
    async def test_plan_returns_plan_result(self):
        planner, _, _ = _make_planner()
        result = await planner.plan("여신 규정 봇 만들어줘", _candidates(), "req-1")
        assert isinstance(result, PlanResult)
        assert isinstance(result.plan, BuildPlan)
        assert result.plan.confidence == 0.9
        assert result.plan.tool_hints[0].suggested_tool_ids == [
            "internal_document_search"
        ]
        assert result.questions == []

    @pytest.mark.asyncio
    async def test_candidates_injected_into_system_prompt(self):
        planner, mock_llm, _ = _make_planner()
        await planner.plan("봇 만들어줘", _candidates(), "req-1")
        messages = mock_llm.ainvoke.call_args[0][0]
        system_msg = next(m for m in messages if m["role"] == "system")
        assert "internal_document_search" in system_msg["content"]
        assert "tavily_search" in system_msg["content"]

    @pytest.mark.asyncio
    async def test_questions_clamped_by_planner_contract(self):
        """G3: 교체 구현체와 무관하게 Planner가 질문 상한(3)을 보장한다."""
        output = _make_output(
            confidence=0.4,
            questions=[
                _QuestionOutput(question=f"질문 {i}?", options=[])
                for i in range(5)
            ],
        )
        planner, _, _ = _make_planner(output)
        result = await planner.plan("봇 만들어줘", _candidates(), "req-1")
        assert len(result.questions) == 3

    @pytest.mark.asyncio
    async def test_question_ids_assigned_sequentially(self):
        output = _make_output(
            confidence=0.4,
            questions=[
                _QuestionOutput(question="문서 범위는?", options=["여신", "전체"]),
                _QuestionOutput(question="응답 언어는?", options=[]),
            ],
        )
        planner, _, _ = _make_planner(output)
        result = await planner.plan("봇 만들어줘", _candidates(), "req-1")
        assert [q.id for q in result.questions] == ["q1", "q2"]
        assert result.questions[0].options == ["여신", "전체"]
        assert result.questions[1].allow_free_text is True

    @pytest.mark.asyncio
    async def test_current_config_block_injected(self):
        planner, mock_llm, _ = _make_planner()
        current = ComposeCurrentConfig(
            name="재무 리포터",
            system_prompt="당신은 재무 에이전트입니다.",
            tool_ids=["excel_export"],
        )
        await planner.plan(
            "도구 추가해줘", _candidates(), "req-1", current_config=current
        )
        messages = mock_llm.ainvoke.call_args[0][0]
        system_msg = next(m for m in messages if m["role"] == "system")
        assert "[현재 에이전트 설정]" in system_msg["content"]
        assert "재무 리포터" in system_msg["content"]

    @pytest.mark.asyncio
    async def test_answers_block_with_no_answer_marker(self):
        """부분 답변 허용: answer==""는 '무응답'으로 표기되어 전달된다."""
        planner, mock_llm, _ = _make_planner()
        answers = [
            ClarificationAnswer(
                question_id="q1", question="문서 범위는?", answer="여신심사"
            ),
            ClarificationAnswer(question_id="q2", question="응답 언어는?", answer=""),
        ]
        await planner.plan(
            "봇 만들어줘", _candidates(), "req-1", answers=answers
        )
        messages = mock_llm.ainvoke.call_args[0][0]
        user_msg = messages[-1]["content"]
        assert "[이전 질문과 답변]" in user_msg
        assert "문서 범위는?" in user_msg
        assert "여신심사" in user_msg
        assert "무응답" in user_msg

    @pytest.mark.asyncio
    async def test_no_answers_no_block(self):
        planner, mock_llm, _ = _make_planner()
        await planner.plan("봇 만들어줘", _candidates(), "req-1")
        messages = mock_llm.ainvoke.call_args[0][0]
        assert "[이전 질문과 답변]" not in messages[-1]["content"]

    @pytest.mark.asyncio
    async def test_history_inserted_between_system_and_user(self):
        planner, mock_llm, _ = _make_planner()
        history = [
            {"role": "user", "content": "봇 만들어줘"},
            {"role": "assistant", "content": "초안: 규정 봇"},
        ]
        await planner.plan("도구 추가", _candidates(), "req-1", history=history)
        messages = mock_llm.ainvoke.call_args[0][0]
        assert messages[0]["role"] == "system"
        assert messages[1] == history[0]
        assert messages[2] == history[1]
        assert messages[-1]["role"] == "user"

    @pytest.mark.asyncio
    async def test_raises_and_logs_on_llm_error(self):
        planner, mock_llm, logger = _make_planner()
        mock_llm.ainvoke = AsyncMock(side_effect=RuntimeError("LLM down"))
        with pytest.raises(RuntimeError, match="LLM down"):
            await planner.plan("봇", _candidates(), "req-1")
        logger.error.assert_called_once()


class TestAgentPlannerTracing:
    @pytest.mark.asyncio
    async def test_config_has_plan_run_name_and_tags(self, monkeypatch):
        monkeypatch.setattr(
            "src.application.agent_composer.planner.make_composer_tracer",
            lambda tags=None: None,
        )
        planner, mock_llm, _ = _make_planner()
        await planner.plan("여신 규정 봇 만들어줘", _candidates(), "req-1")
        config = mock_llm.ainvoke.call_args.kwargs["config"]
        assert config["run_name"].startswith("plan:")
        assert "planner" in config["tags"]
        assert config["metadata"]["request_id"] == "req-1"
        assert config["metadata"]["round"] == 0

    @pytest.mark.asyncio
    async def test_round_recorded_in_trace_metadata(self, monkeypatch):
        """G1/FR-10: HITL 라운드가 LangSmith metadata에 기록된다."""
        monkeypatch.setattr(
            "src.application.agent_composer.planner.make_composer_tracer",
            lambda tags=None: None,
        )
        planner, mock_llm, _ = _make_planner()
        await planner.plan("봇", _candidates(), "req-1", round_=1)
        config = mock_llm.ainvoke.call_args.kwargs["config"]
        assert config["metadata"]["round"] == 1

    @pytest.mark.asyncio
    async def test_tracer_injected_into_callbacks(self, monkeypatch):
        sentinel = object()
        monkeypatch.setattr(
            "src.application.agent_composer.planner.make_composer_tracer",
            lambda tags=None: sentinel,
        )
        planner, mock_llm, _ = _make_planner()
        await planner.plan("봇", _candidates(), "req-1")
        config = mock_llm.ainvoke.call_args.kwargs["config"]
        assert config["callbacks"] == [sentinel]
