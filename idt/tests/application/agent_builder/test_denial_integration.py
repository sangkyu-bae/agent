"""능력 부정 되물음 — 컴파일된 그래프 통합 검증.

Design Ref: worker-capability-denial-guard §8.5 (L3) / §2.2 (합산 1회 상한)
Plan SC: FR-05, FR-08, FR-09

재현 시나리오(런 031564e4): 미분류 react 워커가 정상 데이터와 함께
'어떤 도구로도 조회할 수 없도록 제한'을 반환하고 supervisor LLM이 계속
FINISH를 내도, 되물음이 정확히 1회 일어난 뒤 final_answer로 종료한다.
빈 결과 신호와 동시에 서도 합산 1회 — 무한 루프가 없다.
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

DENIAL_PATTERNS = ("어떤 도구로도", "권한/범위 밖")
EMPTY_PATTERNS = ("등록된 데이터가 없습니다",)

# 재현 케이스와 동형: 정상 데이터 48건 + task 밖 능력 질문에 대한 불가 선언.
_DENIAL_BODY = (
    "55089 | [엔카닷컴] 자동차 담보 대출 상품 업무 논의 요청의 건 | 기타\n" * 20
    + "문의 글의 상세 본문 내용은 어떤 도구로도 조회할 수 없도록 제한되어 있습니다."
)
_OK_BODY = "55089 | 자동차 담보 대출 문의 | 기타\n" * 20
# 빈 결과 + 능력 부정이 한 산출에 동시에 있는 경우.
_BOTH_BODY = (
    "메뉴 상품공시 경영공시\n" * 40
    + "상세 등록된 데이터가 없습니다.\n"
    + "이 데이터는 어떤 도구로도 조회할 수 없도록 제한되어 있습니다."
)


def _make_llm_model() -> LlmModel:
    now = datetime.now(timezone.utc)
    return LlmModel(
        id="model-1", provider="openai", model_name="gpt-4o-mini",
        display_name="gpt-4o-mini", description=None,
        api_key_env="OPENAI_API_KEY", max_tokens=128000,
        is_active=True, is_default=True, created_at=now, updated_at=now,
    )


def _make_compiler(denial=DENIAL_PATTERNS, empty=EMPTY_PATTERNS) -> WorkflowCompiler:
    tool_factory = MagicMock()
    tool_factory.create = MagicMock(return_value=MagicMock())
    llm_factory = MagicMock(spec=LLMFactoryInterface)
    llm_factory.create.return_value = MagicMock()
    return WorkflowCompiler(
        tool_factory=tool_factory,
        llm_factory=llm_factory,
        logger=MagicMock(),
        hooks=DefaultHooks(),
        empty_result_patterns=empty,
        capability_denial_patterns=denial,
    )


def _workflow() -> WorkflowDefinition:
    return WorkflowDefinition(
        supervisor_prompt="당신은 고객 문의 분석 에이전트입니다.",
        workers=[
            # 미분류(react) 워커 — 실측 결함 대상. tool_id는 TOOL_REGISTRY에
            # 없는 값이라 카테고리 None → _wrap_worker 경로를 탄다.
            WorkerDefinition(
                tool_id="list_inquiries", worker_id="lister",
                description="문의 목록 조회", sort_order=0,
            ),
            WorkerDefinition(
                tool_id="get_inquiry", worker_id="reader",
                description="문의 본문 조회", sort_order=1,
            ),
        ],
        flow_hint="test",
    )


class _StubReactAgent:
    def __init__(self, body: str):
        self._body = body

    async def ainvoke(self, _input):
        return {"messages": [AIMessage(content=self._body)]}


def _finish() -> SupervisorDecision:
    return SupervisorDecision(next="FINISH", reasoning="r", answer="", task="")


def _route(worker: str = "lister") -> SupervisorDecision:
    return SupervisorDecision(next=worker, reasoning="r", answer="", task="목록")


async def _run(body: str, decisions: list, compiler: WorkflowCompiler | None = None):
    compiler = compiler or _make_compiler()
    llm = compiler._llm_factory.create.return_value
    spy = AsyncMock(side_effect=decisions)
    llm.with_structured_output.return_value.ainvoke = spy
    llm.ainvoke = AsyncMock(return_value=AIMessage(content="최종 답변"))

    config = SupervisorConfig()
    with patch(
        "src.application.agent_builder.workflow_compiler.create_agent",
        return_value=_StubReactAgent(body),
    ):
        graph = await compiler.compile(
            _workflow(), _make_llm_model(), "req-1", supervisor_config=config,
        )
    result = await graph.ainvoke(build_initial_state(
        messages=[{"role": "user", "content": "미답변 문의 알려줘. 각각 본문 읽을 수 있나요?"}],
        config=config,
        available_workers=["lister", "reader"],
    ))
    return result, spy


class TestChallengeHappensExactlyOnce:

    @pytest.mark.asyncio
    async def test_denial_triggers_one_challenge_then_finishes(self):
        """1: 워커 선택 / 2: FINISH→되돌림 / 3: FINISH→통과. 무한 루프 없음."""
        result, spy = await _run(_DENIAL_BODY, [_route(), _finish(), _finish(), _finish()])
        assert spy.await_count == 3
        assert result["finish_challenge_pending"] is False
        assert result["last_worker_denial"] == ""

    @pytest.mark.asyncio
    async def test_challenge_prompt_carries_denial_block_once(self):
        """되물음 직전 결정(2회차)에만 블록이 있고, 재진입(3회차)에는 없다."""
        _, spy = await _run(_DENIAL_BODY, [_route(), _finish(), _finish(), _finish()])
        prompts = [call.args[0][0]["content"] for call in spy.await_args_list]
        assert "[워커 능력 부정 감지]" not in prompts[0]
        assert "[워커 능력 부정 감지]" in prompts[1]
        assert "[워커 능력 부정 감지]" not in prompts[2]

    @pytest.mark.asyncio
    async def test_challenge_lets_supervisor_route_to_another_worker(self):
        """되물음 후 다른 워커(본문 조회)를 고르면 그 워커가 실제로 실행된다."""
        result, spy = await _run(
            _DENIAL_BODY, [_route(), _finish(), _route("reader"), _finish(), _finish()],
        )
        names = [getattr(m, "name", "") for m in result["messages"]]
        assert "reader" in names

    @pytest.mark.asyncio
    async def test_normal_result_finishes_without_challenge(self):
        _, spy = await _run(_OK_BODY, [_route(), _finish(), _finish()])
        assert spy.await_count == 2


class TestCombinedSignalsShareOneChallenge:
    """§2.2 — 빈 결과와 능력 부정이 동시에 서도 되물음은 합산 1회."""

    @pytest.mark.asyncio
    async def test_both_signals_still_challenge_once(self):
        result, spy = await _run(_BOTH_BODY, [_route(), _finish(), _finish(), _finish()])
        assert spy.await_count == 3
        assert result["last_worker_empty"] == ""
        assert result["last_worker_denial"] == ""

    @pytest.mark.asyncio
    async def test_empty_block_wins_when_both_present(self):
        _, spy = await _run(_BOTH_BODY, [_route(), _finish(), _finish(), _finish()])
        second = spy.await_args_list[1].args[0][0]["content"]
        assert "[수집 결과 확인 필요]" in second
        assert "[워커 능력 부정 감지]" not in second


class TestWiringScope:

    @pytest.mark.asyncio
    async def test_no_patterns_disables_challenge(self):
        """설정 미주입이면 판정이 꺼진다 — 기존 픽스처 무회귀."""
        _, spy = await _run(
            _DENIAL_BODY, [_route(), _finish(), _finish()],
            compiler=_make_compiler(denial=None),
        )
        assert spy.await_count == 2

    @pytest.mark.asyncio
    async def test_react_worker_is_covered(self):
        """D-04 — 빈 결과 데코레이터가 덮지 않는 미분류 react 워커도 대상이다."""
        result, spy = await _run(_DENIAL_BODY, [_route(), _finish(), _finish(), _finish()])
        assert spy.await_count == 3


class TestAllWorkerNodesWrapped:
    """Act-1 Gap-11 (D-04): 등록 루프가 워커 노드 전부를 데코레이터로 덮는다."""

    @pytest.mark.asyncio
    async def test_decorator_applied_once_per_worker(self):
        import src.application.agent_builder.workflow_compiler as wc
        compiler = _make_compiler()
        llm = compiler._llm_factory.create.return_value
        llm.with_structured_output.return_value.ainvoke = AsyncMock(return_value=_finish())
        spy = MagicMock(side_effect=wc._with_denial_signal)
        with patch.object(wc, "_with_denial_signal", spy), patch(
            "src.application.agent_builder.workflow_compiler.create_agent",
            return_value=_StubReactAgent(_OK_BODY),
        ):
            await compiler.compile(
                _workflow(), _make_llm_model(), "req-1", supervisor_config=SupervisorConfig(),
            )
        assert spy.call_count == 2
        assert all(c.args[1] == DENIAL_PATTERNS for c in spy.call_args_list)
