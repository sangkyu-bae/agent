"""빈 결과 되물음 — 컴파일된 그래프 통합 + 배선 범위 검증.

Design Ref: supervisor-early-finish-fix §8.5 (L3) / §4.2 (D-06, Q-01)
Plan SC: FR-04, FR-06, FR-07, FR-08

재현 시나리오(트레이스 01a0a82b): 수집 워커가 '등록된 데이터가 없습니다'를
반환하고 supervisor LLM이 계속 FINISH를 내도, 되물음이 정확히 1회 일어난 뒤
final_answer로 종료한다 — 무한 루프가 없다.
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from src.application.agent_builder.supervisor_hooks import DefaultHooks
from src.application.agent_builder.supervisor_nodes import (
    SupervisorDecision,
    build_initial_state,
)
from src.application.agent_builder.workflow_compiler import WorkflowCompiler
from src.domain.agent_builder.schemas import (
    SupervisorConfig,
    WorkerDefinition,
    WorkflowDefinition,
)
from src.domain.llm.interfaces import LLMFactoryInterface
from src.domain.llm_model.entity import LlmModel

PATTERNS = ("등록된 데이터가 없습니다",)

# 재현 케이스와 동형: 본문은 길지만 데이터 영역만 비어 있다.
_EMPTY_BODY = "메뉴 상품공시 경영공시 소비자공시\n" * 40 + "상세 등록된 데이터가 없습니다."


def _make_llm_model() -> LlmModel:
    now = datetime.now(timezone.utc)
    return LlmModel(
        id="model-1", provider="openai", model_name="gpt-4o-mini",
        display_name="gpt-4o-mini", description=None,
        api_key_env="OPENAI_API_KEY", max_tokens=128000,
        is_active=True, is_default=True, created_at=now, updated_at=now,
    )


def _make_compiler(patterns=PATTERNS) -> WorkflowCompiler:
    tool_factory = MagicMock()
    tool_factory.create = MagicMock(return_value=MagicMock())
    llm_factory = MagicMock(spec=LLMFactoryInterface)
    llm_factory.create.return_value = MagicMock()
    return WorkflowCompiler(
        tool_factory=tool_factory,
        llm_factory=llm_factory,
        logger=MagicMock(),
        hooks=DefaultHooks(),
        empty_result_patterns=patterns,
    )


def _workflow(tool_id: str = "scrape_url") -> WorkflowDefinition:
    return WorkflowDefinition(
        supervisor_prompt="당신은 AI 에이전트입니다.",
        workers=[WorkerDefinition(
            tool_id=tool_id, worker_id="collector", description="수집", sort_order=0,
        )],
        flow_hint="test",
    )


class _StubReactAgent:
    """react 워커 스텁 — 항상 같은 본문을 최종 AIMessage로 돌려준다."""

    def __init__(self, body: str):
        self._body = body

    async def ainvoke(self, _input):
        return {"messages": [AIMessage(content=self._body)]}


async def _run(body: str, decisions: list, patterns=PATTERNS) -> dict:
    compiler = _make_compiler(patterns)
    llm = compiler._llm_factory.create.return_value
    llm.with_structured_output.return_value.ainvoke = AsyncMock(side_effect=decisions)
    # final_answer 노드의 직접 LLM 호출
    llm.ainvoke = AsyncMock(return_value=AIMessage(content="최종 답변"))

    config = SupervisorConfig()
    with patch(
        "src.application.agent_builder.workflow_compiler.create_agent",
        return_value=_StubReactAgent(body),
    ):
        graph = await compiler.compile(
            _workflow(), _make_llm_model(), "req-1", supervisor_config=config,
        )
    state = build_initial_state(
        messages=[{"role": "user", "content": "금리 전체 표"}],
        config=config,
        available_workers=["collector"],
    )
    return await graph.ainvoke(state)


def _finish(answer: str = "") -> SupervisorDecision:
    return SupervisorDecision(next="FINISH", reasoning="r", answer=answer, task="")


def _route() -> SupervisorDecision:
    return SupervisorDecision(next="collector", reasoning="r", answer="", task="수집")


class TestChallengeHappensExactlyOnce:

    @pytest.mark.asyncio
    async def test_empty_result_triggers_one_challenge_then_finishes(self):
        """수집 → FINISH(되돌림) → FINISH(통과). supervisor 3회, 무한 루프 없음."""
        decisions = [_route(), _finish(), _finish(), _finish()]
        result = await _run(_EMPTY_BODY, decisions)

        # 되물음 기회는 소진되고 신호도 리셋된 채 종료한다 (호출 횟수는 아래 테스트).
        assert result["finish_challenge_pending"] is False
        assert result["last_worker_empty"] == ""

    @pytest.mark.asyncio
    async def test_supervisor_called_three_times_on_empty(self):
        """1: 워커 선택 / 2: FINISH→되돌림 / 3: FINISH→통과."""
        compiler = _make_compiler()
        llm = compiler._llm_factory.create.return_value
        spy = AsyncMock(side_effect=[_route(), _finish(), _finish(), _finish()])
        llm.with_structured_output.return_value.ainvoke = spy
        llm.ainvoke = AsyncMock(return_value=AIMessage(content="최종 답변"))

        config = SupervisorConfig()
        with patch(
            "src.application.agent_builder.workflow_compiler.create_agent",
            return_value=_StubReactAgent(_EMPTY_BODY),
        ):
            graph = await compiler.compile(
                _workflow(), _make_llm_model(), "req-1", supervisor_config=config,
            )
        await graph.ainvoke(build_initial_state(
            messages=[{"role": "user", "content": "금리 표"}],
            config=config, available_workers=["collector"],
        ))
        assert spy.await_count == 3

    @pytest.mark.asyncio
    async def test_normal_result_finishes_without_challenge(self):
        """정상 수집이면 supervisor 2회 — 되물음이 일어나지 않는다."""
        compiler = _make_compiler()
        llm = compiler._llm_factory.create.return_value
        spy = AsyncMock(side_effect=[_route(), _finish(), _finish()])
        llm.with_structured_output.return_value.ainvoke = spy
        llm.ainvoke = AsyncMock(return_value=AIMessage(content="최종 답변"))

        config = SupervisorConfig()
        with patch(
            "src.application.agent_builder.workflow_compiler.create_agent",
            return_value=_StubReactAgent("저축은행A 12개월 3.50%\n" * 40),
        ):
            graph = await compiler.compile(
                _workflow(), _make_llm_model(), "req-1", supervisor_config=config,
            )
        await graph.ainvoke(build_initial_state(
            messages=[{"role": "user", "content": "금리 표"}],
            config=config, available_workers=["collector"],
        ))
        assert spy.await_count == 2


class TestWiringScope:
    """Q-01 확정 — 판정 대상 범위를 컴파일 레벨에서 고정한다."""

    @pytest.mark.asyncio
    async def test_wiki_worker_is_excluded_from_detection(self):
        """위키는 지식 열람이라 본문이 짧은 것이 정상 — 구조적 신호 오탐 방지."""
        compiler = _make_compiler()
        llm = compiler._llm_factory.create.return_value
        spy = AsyncMock(side_effect=[_route(), _finish(), _finish()])
        llm.with_structured_output.return_value.ainvoke = spy
        llm.ainvoke = AsyncMock(return_value=AIMessage(content="최종 답변"))

        workflow = WorkflowDefinition(
            supervisor_prompt="지침",
            workers=[WorkerDefinition(
                tool_id="wiki_read", worker_id="collector",
                description="위키", sort_order=0,
            )],
            flow_hint="test",
        )
        config = SupervisorConfig()
        with patch(
            "src.application.agent_builder.workflow_compiler.create_agent",
            return_value=_StubReactAgent("짧은 위키 본문"),  # 200자 미만
        ):
            graph = await compiler.compile(
                workflow, _make_llm_model(), "req-1", supervisor_config=config,
            )
        result = await graph.ainvoke(build_initial_state(
            messages=[{"role": "user", "content": "절차 알려줘"}],
            config=config, available_workers=["collector"],
        ))
        # 되물음 없이 2회로 끝난다 — 짧은 위키 본문이 빈 결과로 오탐되지 않음
        assert spy.await_count == 2
        assert result["last_worker_empty"] == ""

    @pytest.mark.asyncio
    async def test_no_patterns_falls_back_to_structural_only(self):
        """설정 미주입이어도 런이 깨지지 않는다."""
        compiler = _make_compiler(patterns=None)
        llm = compiler._llm_factory.create.return_value
        spy = AsyncMock(side_effect=[_route(), _finish(), _finish()])
        llm.with_structured_output.return_value.ainvoke = spy
        llm.ainvoke = AsyncMock(return_value=AIMessage(content="최종 답변"))

        config = SupervisorConfig()
        with patch(
            "src.application.agent_builder.workflow_compiler.create_agent",
            return_value=_StubReactAgent(_EMPTY_BODY),
        ):
            graph = await compiler.compile(
                _workflow(), _make_llm_model(), "req-1", supervisor_config=config,
            )
        await graph.ainvoke(build_initial_state(
            messages=[{"role": "user", "content": "금리 표"}],
            config=config, available_workers=["collector"],
        ))
        # 패턴이 없으니 긴 본문은 빈 결과로 잡히지 않는다 → 되물음 없음
        assert spy.await_count == 2


class TestGraphStructure:

    @pytest.mark.asyncio
    async def test_supervisor_self_loop_registered(self):
        """D-05 — 되물음 경로(route_map 자기순환)가 그래프에 등록돼 있다."""
        compiler = _make_compiler()
        with patch(
            "src.application.agent_builder.workflow_compiler.create_agent",
            return_value=_StubReactAgent("x"),
        ):
            graph = await compiler.compile(
                _workflow(), _make_llm_model(), "req-1",
                supervisor_config=SupervisorConfig(),
            )
        edges = graph.get_graph().edges
        assert any(
            e.source == "supervisor" and e.target == "supervisor" for e in edges
        )
