"""승인 게이트 런 종료·안내·답변 템플릿.

Design Ref: approval-gate-run-termination §2.1, §4.2, §4.4 (B10, B16–B20).
실측(2026-09-29): 게이트 차단 후 supervisor 가 같은 워커를 5회 반복 호출했고,
워커 LLM 이 지어낸 성공 JSON 이 채팅 답변으로 저장됐다.
"""
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.application.agent_builder.run_agent_use_case import (
    RunAgentUseCase,
    _StreamState,
)
from src.application.agent_builder.supervisor_hooks import DefaultHooks
from src.application.agent_builder.supervisor_nodes import (
    SupervisorDecision,
    build_initial_state,
    create_supervisor_node,
    route_after_gated_worker,
)
from src.application.agent_builder.workflow_compiler import WorkflowCompiler
from src.domain.agent_builder.policies import GatedWorkerHintPolicy
from src.domain.agent_builder.schemas import SupervisorConfig, WorkerDefinition
from src.domain.approval.notice_policy import ApprovalPendingNoticePolicy
from tests.application.agent_builder.test_action_graph_integration import (
    FakeRunLLM,
    _compile_ready,
    _run,
)
from tests.application.agent_builder.test_workflow_compiler_category import (
    _make_llm_model,
)


class TestRouteAfterGatedWorker:
    def test_승인_대기면_종료(self):
        """B10"""
        assert route_after_gated_worker({"approval_pending": {"tool_id": "t"}}) == "end"

    def test_신호가_없으면_quality_gate(self):
        assert route_after_gated_worker({"approval_pending": {}}) == "quality_gate"
        assert route_after_gated_worker({}) == "quality_gate"


def _edges_from(graph, node: str) -> set[str]:
    return {e.target for e in graph.get_graph().edges if e.source == node}


class TestGraph:
    @pytest.mark.asyncio
    async def test_게이트_워커는_1회만_돌고_supervisor로_돌아가지_않는다(self):
        """B16 / SC-1 — 결정이 1개뿐이라 supervisor 재진입 시 IndexError."""
        llm = FakeRunLLM(decisions=["mailer"])
        compiler, workflow, tool = _compile_ready(llm, gated=True)
        with patch.object(WorkflowCompiler, "_should_gate_worker", return_value=True):
            result = await _run(compiler, workflow)
        assert tool.calls == []
        assert result["approval_pending"]["worker_id"] == "mailer"
        assert llm.decisions == []
        mailer_outputs = [m for m in result["messages"] if getattr(m, "name", None) == "mailer"]
        assert len(mailer_outputs) == 1

    @pytest.mark.asyncio
    async def test_게이트_워커만_조건부_간선을_갖는다(self):
        llm = FakeRunLLM(decisions=[])
        compiler, workflow, _ = _compile_ready(llm, gated=True)
        with patch.object(WorkflowCompiler, "_should_gate_worker", return_value=True):
            graph = await compiler.compile(
                workflow, _make_llm_model(), "req-1", supervisor_config=SupervisorConfig(),
            )
        assert _edges_from(graph, "mailer") == {"quality_gate", "__end__"}

    @pytest.mark.asyncio
    async def test_비게이트_워커_간선은_불변(self):
        """B17 — 게이트 없는 에이전트는 바이트 동일."""
        llm = FakeRunLLM(decisions=[])
        compiler, workflow, _ = _compile_ready(llm, gated=False)
        with patch.object(WorkflowCompiler, "_should_gate_worker", return_value=False):
            graph = await compiler.compile(
                workflow, _make_llm_model(), "req-1", supervisor_config=SupervisorConfig(),
            )
        assert _edges_from(graph, "mailer") == {"quality_gate"}


class _CapturingLLM:
    def __init__(self):
        self.prompts: list = []

    def with_structured_output(self, _schema):
        outer = self

        class _S:
            async def ainvoke(self, messages):
                outer.prompts.append(messages)
                return SupervisorDecision(next="FINISH", reasoning="r", answer="ok")

        return _S()


def _prompt_text(messages) -> str:
    return "\n".join(
        m["content"] if isinstance(m, dict) else str(getattr(m, "content", m))
        for m in messages
    )


class TestSupervisorHint:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("gated", [True, False])
    async def test_게이트_워커_설명에만_안내가_붙는다(self, gated):
        """B7 배선 — 비게이트는 바이트 동일."""
        llm = _CapturingLLM()
        workers = [WorkerDefinition(tool_id="t", worker_id="submit", description="답변 등록")]
        node = create_supervisor_node(
            llm=llm, workers=workers, supervisor_prompt="p", logger=MagicMock(),
            hooks=DefaultHooks(),
            gated_worker_ids=frozenset({"submit"}) if gated else frozenset(),
        )
        state = build_initial_state(
            messages=[{"role": "user", "content": "등록해줘"}],
            config=SupervisorConfig(), available_workers=["submit"],
        )
        await node(state)
        text = _prompt_text(llm.prompts[0])
        line = f"- submit: {GatedWorkerHintPolicy.PREFIX}답변 등록{GatedWorkerHintPolicy.SUFFIX}"
        assert (line in text) is gated
        assert (GatedWorkerHintPolicy.PREFIX in text) is gated
        assert "- submit: " in text and "답변 등록" in text
        # Act-1: 규칙 블록은 게이트 워커가 있을 때만 — 비게이트는 바이트 동일
        assert ("[승인 게이트 규칙]" in text) is gated


class TestResolveAnswer:
    def _uc(self):
        uc = RunAgentUseCase.__new__(RunAgentUseCase)
        uc._logger = MagicMock()
        return uc

    def test_승인_대기면_워커_텍스트_대신_템플릿(self):
        """B18 / SC-2 — 워커가 가짜 성공 JSON 을 출력해도."""
        state = _StreamState()
        state.final_messages = [
            HumanMessage(content="63116 등록해줘"),
            AIMessage(content='{"status": "ok", "was_answered": false}', name="submit"),
        ]
        state.approval_pending = {
            "tool_id": "mcp:s:submit_reply",
            "tool_args": {"arguments": {"reply_content": "안녕하세요"}},
            "draft": "안녕하세요",
            "worker_id": "submit",
        }
        answer, tools_used = self._uc()._resolve_answer(state)
        assert answer == ApprovalPendingNoticePolicy.render(
            tool_id="mcp:s:submit_reply",
            tool_args={"arguments": {"reply_content": "안녕하세요"}},
            draft="안녕하세요",
        )
        assert '"status": "ok"' not in answer
        assert tools_used == ["submit"]

    def test_승인_대기가_없으면_기존과_동일(self):
        """B19"""
        state = _StreamState()
        state.final_messages = [AIMessage(content="최종 답변", name="final_answer")]
        uc = self._uc()
        assert uc._resolve_answer(state) == uc._parse_result({"messages": state.final_messages})


class TestResumeUnaffected:
    def test_재개_상태는_승인_대기가_비어_새_간선에_걸리지_않는다(self):
        """B20"""
        from tests.application.approval.test_resume import _approval

        state = RunAgentUseCase._restore_state(_approval(), "결과")
        assert state["approval_pending"] == {}
        assert route_after_gated_worker(state) == "quality_gate"


class TestSubAgentGate:
    """Analysis G3 — 서브 에이전트 안의 게이트 신호가 부모 런을 끝내야 한다."""

    def _compiler(self):
        compiler = WorkflowCompiler.__new__(WorkflowCompiler)
        compiler._logger = MagicMock()
        return compiler

    @staticmethod
    def _parent_state():
        user = MagicMock()
        user.content = "등록해줘"
        return {"messages": [user], "token_usage": 0, "token_limit": 8000,
                "max_iterations": 100}

    @pytest.mark.asyncio
    async def test_서브_승인_대기를_부모로_올린다(self):
        from unittest.mock import AsyncMock

        sub_graph = MagicMock()
        sub_graph.ainvoke = AsyncMock(return_value={
            "messages": [AIMessage(content="승인 대기")], "token_usage": 3,
            "approval_pending": {"tool_id": "t", "worker_id": "inner_w", "draft": "d"},
        })
        out = await self._compiler()._wrap_sub_agent("sub_w", sub_graph)(self._parent_state())
        # 재개는 부모 그래프의 워커에 결과를 주입하므로 부모 워커 id 로 바꾼다
        assert out["approval_pending"]["worker_id"] == "sub_w"
        assert out["approval_pending"]["tool_id"] == "t"
        assert route_after_gated_worker(out) == "end"

    @pytest.mark.asyncio
    async def test_서브_승인_대기가_없으면_기존_출력과_동일(self):
        from unittest.mock import AsyncMock

        sub_graph = MagicMock()
        sub_graph.ainvoke = AsyncMock(return_value={
            "messages": [AIMessage(content="완료")], "token_usage": 3,
        })
        out = await self._compiler()._wrap_sub_agent("sub_w", sub_graph)(self._parent_state())
        assert "approval_pending" not in out

    @pytest.mark.asyncio
    async def test_서브_에이전트_워커는_조건부_종료_간선을_갖는다(self):
        from unittest.mock import AsyncMock

        from src.domain.agent_builder.schemas import WorkflowDefinition

        llm = FakeRunLLM(decisions=[])
        compiler, _, _ = _compile_ready(llm, gated=False)
        workflow = WorkflowDefinition(
            supervisor_prompt="p",
            workers=[WorkerDefinition(
                tool_id="", worker_id="sub_w", description="하위 에이전트",
                worker_type="sub_agent", ref_agent_id="ag-sub",
            )],
            flow_hint="t",
        )
        with patch.object(
            WorkflowCompiler, "_compile_sub_agent", AsyncMock(return_value=AsyncMock()),
        ):
            graph = await compiler.compile(
                workflow, _make_llm_model(), "req-1", supervisor_config=SupervisorConfig(),
            )
        assert _edges_from(graph, "sub_w") == {"quality_gate", "__end__"}
