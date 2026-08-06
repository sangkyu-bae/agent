"""ComposeAgentUseCase × Planner 오케스트레이션 테스트 (fix-agent-planner-hitl).

분기 검증: needs_clarification / 답변 재호출 / 라운드 소진 강제 진행 /
Planner 예외 폴백 / planner 미주입 하위호환.
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_composer.composer import (
    _CapabilityOutput,
    _ComposeOutput,
    _WorkerOutput,
)
from src.application.agent_composer.compose_agent_use_case import ComposeAgentUseCase
from src.application.agent_composer.interfaces import PlanResult
from src.application.agent_composer.schemas import (
    ClarificationAnswerDto,
    ComposeAgentRequest,
)
from src.domain.agent_composer.schemas import (
    BuildPlan,
    ClarifyingQuestion,
    ToolDirectionHint,
)
from src.domain.llm_model.entity import LlmModel


def _make_default_llm_model() -> LlmModel:
    now = datetime.now(timezone.utc)
    return LlmModel(
        id="model-default",
        provider="openai",
        model_name="gpt-4o",
        display_name="GPT-4o",
        description=None,
        api_key_env="OPENAI_API_KEY",
        max_tokens=128000,
        is_active=True,
        is_default=True,
        created_at=now,
        updated_at=now,
    )


def _compose_output() -> _ComposeOutput:
    return _ComposeOutput(
        capabilities=[
            _CapabilityOutput(
                capability="검색",
                matched_tool_ids=["tavily_search"],
                reason="커버 가능",
            )
        ],
        workers=[
            _WorkerOutput(
                tool_id="tavily_search",
                worker_id="search_worker",
                description="검색",
                sort_order=0,
            )
        ],
        flow_hint="search_worker 단독",
        system_prompt="생성된 프롬프트",
        agent_name="제안된 이름",
        notes="",
    )


def _plan(confidence: float = 0.9) -> BuildPlan:
    return BuildPlan(
        requirement_summary="검색 에이전트 요구",
        tool_hints=[
            ToolDirectionHint(
                capability="검색", suggested_tool_ids=["tavily_search"]
            )
        ],
        plan_summary="검색 도구 하나로 구성한다.",
        confidence=confidence,
    )


def _questions(n: int = 2) -> list[ClarifyingQuestion]:
    return [
        ClarifyingQuestion(
            id=f"q{i + 1}",
            question=f"질문 {i + 1}?",
            options=["A", "B"],
        )
        for i in range(n)
    ]


def _make_use_case(planner=None):
    composer = MagicMock()
    composer.compose = AsyncMock(return_value=_compose_output())

    tool_catalog_repo = MagicMock()
    tool_catalog_repo.list_active = AsyncMock(return_value=[])
    mcp_server_repo = MagicMock()
    mcp_server_repo.find_all_active = AsyncMock(return_value=[])

    llm_model_repository = MagicMock()
    default_model = _make_default_llm_model()
    llm_model_repository.find_by_id = AsyncMock(return_value=default_model)
    llm_model_repository.find_default = AsyncMock(return_value=default_model)

    logger = MagicMock()
    use_case = ComposeAgentUseCase(
        composer=composer,
        tool_catalog_repo=tool_catalog_repo,
        mcp_server_repo=mcp_server_repo,
        llm_model_repository=llm_model_repository,
        logger=logger,
        planner=planner,
    )
    return use_case, composer, logger


def _mock_planner(result: PlanResult | Exception):
    planner = MagicMock()
    if isinstance(result, Exception):
        planner.plan = AsyncMock(side_effect=result)
    else:
        planner.plan = AsyncMock(return_value=result)
    return planner


class TestNeedsClarification:
    @pytest.mark.asyncio
    async def test_low_confidence_returns_questions_without_compose(self):
        """① 저신뢰+질문 → needs_clarification, composer 미호출, 초안 빈 값."""
        planner = _mock_planner(PlanResult(_plan(0.4), _questions(2)))
        use_case, composer, _ = _make_use_case(planner)
        result = await use_case.execute(
            ComposeAgentRequest(user_request="봇 만들어줘"), "req-1"
        )
        assert result.status == "needs_clarification"
        assert len(result.questions) == 2
        assert result.questions[0].id == "q0-1"  # q{round}-{i}
        assert result.questions[0].options == ["A", "B"]
        assert result.plan_summary == "검색 도구 하나로 구성한다."
        assert result.coverage == "none"
        assert result.tool_ids == []
        assert result.workers == []
        composer.compose.assert_not_called()

    @pytest.mark.asyncio
    async def test_questions_clamped_to_policy_max(self):
        planner = _mock_planner(PlanResult(_plan(0.4), _questions(5)))
        use_case, _, _ = _make_use_case(planner)
        result = await use_case.execute(
            ComposeAgentRequest(user_request="봇"), "req-1"
        )
        assert len(result.questions) == 3  # MAX_QUESTIONS_PER_ROUND

    @pytest.mark.asyncio
    async def test_round_exhausted_forces_compose(self):
        """③ 라운드 소진 → 질문 있어도 강제 진행 (best-effort)."""
        planner = _mock_planner(PlanResult(_plan(0.4), _questions(2)))
        use_case, composer, _ = _make_use_case(planner)
        result = await use_case.execute(
            ComposeAgentRequest(user_request="봇", clarification_round=2), "req-1"
        )
        assert result.status == "draft"
        composer.compose.assert_awaited_once()


class TestAnswersRoundTrip:
    @pytest.mark.asyncio
    async def test_answers_forwarded_to_planner_and_plan_injected(self):
        """② 답변 동봉 재호출 → planner에 답변 전달, 확신 시 plan 주입 compose."""
        planner = _mock_planner(PlanResult(_plan(0.9), []))
        use_case, composer, _ = _make_use_case(planner)
        result = await use_case.execute(
            ComposeAgentRequest(
                user_request="봇 만들어줘",
                clarification_answers=[
                    ClarificationAnswerDto(
                        question_id="q0-1", question="문서 범위는?", answer="여신"
                    ),
                    ClarificationAnswerDto(
                        question_id="q0-2", question="언어는?", answer=""
                    ),
                ],
                clarification_round=1,
            ),
            "req-1",
        )
        answers = planner.plan.call_args.kwargs["answers"]
        assert len(answers) == 2
        assert answers[0].answer == "여신"
        assert answers[1].answer == ""
        assert planner.plan.call_args.kwargs["round_"] == 1  # G1: 라운드 전달
        assert composer.compose.call_args.kwargs["plan"] is planner.plan.return_value.plan
        assert result.status == "draft"
        assert result.plan_summary == "검색 도구 하나로 구성한다."

    @pytest.mark.asyncio
    async def test_confident_plan_skips_questions_entirely(self):
        planner = _mock_planner(PlanResult(_plan(0.95), []))
        use_case, composer, _ = _make_use_case(planner)
        result = await use_case.execute(
            ComposeAgentRequest(user_request="tavily 검색 봇"), "req-1"
        )
        assert result.status == "draft"
        assert result.questions == []
        composer.compose.assert_awaited_once()


class TestFallback:
    @pytest.mark.asyncio
    async def test_planner_error_falls_back_to_direct_compose(self):
        """④ Planner 예외 → 경고 로그 + plan=None으로 기존 compose 수행."""
        planner = _mock_planner(RuntimeError("planner down"))
        use_case, composer, logger = _make_use_case(planner)
        result = await use_case.execute(
            ComposeAgentRequest(user_request="검색 봇"), "req-1"
        )
        assert result.status == "draft"
        assert result.plan_summary == ""
        assert composer.compose.call_args.kwargs["plan"] is None
        logger.warning.assert_called()

    @pytest.mark.asyncio
    async def test_no_planner_behaves_as_before(self):
        """⑤ planner 미주입(기존 생성 방식) → plan=None, 계약 동일."""
        use_case, composer, _ = _make_use_case(planner=None)
        result = await use_case.execute(
            ComposeAgentRequest(user_request="검색 봇"), "req-1"
        )
        assert result.status == "draft"
        assert result.questions == []
        assert result.plan_summary == ""
        assert composer.compose.call_args.kwargs["plan"] is None
        assert result.coverage == "full"
        assert result.tool_ids == ["tavily_search"]
