"""action 워커 그래프 통합 테스트 — 컴파일된 LangGraph를 실제로 돌린다.

Design Ref: action-category-compose-node §2.2 / §8.2 #25~#26 / D-07·D-11·D-13
  A. 게이트 대상: 도구 0회, approval_pending(draft == 초안), final_answer 미경유(END 직행)
     → 재개(_restore_state 동형): action 워커 재실행 0회, final_answer에 초안 + 집행 결과
  B. 게이트 비대상: 도구 정확히 1회, final_answer 프롬프트에 초안 원문·집행 결과

LLM·도구·카탈로그는 대역이고 supervisor 결정은 시나리오별로 고정한다.
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from src.application.agent_builder.collect_pipeline import CollectArguments
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
from tests.application.agent_builder.test_workflow_compiler_category import (
    FakeCatalogRepo,
    _entry,
    _make_llm_model,
)

TOOL_ID = "mcp:3f2a1b4c-0000-1111-2222-333344445555:send_mail"
DRAFT = "안녕하세요 고객님,\n문의하신 배송 건은 오늘 출고되었습니다."
OUTCOME = "메일 발송 성공 (id=42)"


class FakeTool:
    def __init__(self):
        self.name = "send_mail"
        self.description = "메일 발송"
        self.mcp_tool_name = "send_mail"
        self.mcp_input_schema = {"type": "object", "properties": {"to": {}, "body": {}}}
        self.calls: list = []

    async def ainvoke(self, payload):
        self.calls.append(payload)
        return OUTCOME


class _Structured:
    def __init__(self, fn):
        self._fn = fn

    async def ainvoke(self, _messages):
        return self._fn()


class FakeRunLLM:
    """supervisor(구조화)·compose·인자 조립·final_answer를 한 인스턴스가 맡는다."""

    def __init__(self, decisions: list[str]):
        self.decisions = list(decisions)
        self.ainvoke_calls: list = []

    def with_structured_output(self, schema):
        if schema is SupervisorDecision:
            return _Structured(self._next_decision)
        if schema is CollectArguments:
            out = MagicMock()
            out.arguments_json = json.dumps({"to": "kim@customer.co.kr"})
            out.grounded = True
            out.missing = ""
            return _Structured(lambda: out)
        raise AssertionError(f"unexpected schema {schema}")

    def _next_decision(self):
        nxt = self.decisions.pop(0)
        return SupervisorDecision(next=nxt, reasoning="t", task="회신 작성")

    async def ainvoke(self, messages):
        self.ainvoke_calls.append(messages)
        return AIMessage(content=DRAFT)

    def system_prompts(self) -> list[str]:
        return [m[0]["content"] for m in self.ainvoke_calls]


def _compile_ready(llm: FakeRunLLM, gated: bool):
    tool = FakeTool()
    tool_factory = MagicMock()
    tool_factory.create = MagicMock(return_value=tool)
    tool_factory.create_all_async = AsyncMock(return_value=[tool])
    llm_factory = MagicMock(spec=LLMFactoryInterface)
    llm_factory.create.return_value = llm
    compiler = WorkflowCompiler(
        tool_factory=tool_factory, llm_factory=llm_factory, logger=MagicMock(),
        hooks=DefaultHooks(),
        tool_catalog_repository=FakeCatalogRepo([_entry(TOOL_ID, category="action")]),
    )
    workflow = WorkflowDefinition(
        supervisor_prompt="당신은 고객 응대 에이전트입니다.",
        workers=[WorkerDefinition(
            tool_id=TOOL_ID, worker_id="mailer", description="회신 메일 발송",
            sort_order=0, category="action", tool_config={"draft_arg_key": "body"},
        )],
        flow_hint="t",
    )
    return compiler, workflow, tool


async def _run(compiler, workflow, state=None):
    config = SupervisorConfig()
    graph = await compiler.compile(
        workflow, _make_llm_model(), "req-1", supervisor_config=config,
    )
    if state is None:
        state = build_initial_state(
            messages=[{"role": "user", "content": "kim@customer.co.kr 에게 출고 안내 회신 보내줘"}],
            config=config, available_workers=["mailer"],
        )
    return await graph.ainvoke(state)


class TestGatedRunAndResume:
    @pytest.mark.asyncio
    async def test_gated_run_ends_with_pending_and_resume_skips_worker(self):
        llm = FakeRunLLM(decisions=["mailer", "FINISH"])
        compiler, workflow, tool = _compile_ready(llm, gated=True)

        with patch.object(WorkflowCompiler, "_should_gate_worker", return_value=True):
            result = await _run(compiler, workflow)

            # ── 1차 런: 게이트 → 도구 0회, 신호 승격, final_answer 미경유 ──
            assert tool.calls == []
            pending = result["approval_pending"]
            assert pending["draft"] == DRAFT
            assert pending["tool_args"] == {"to": "kim@customer.co.kr", "body": DRAFT}
            assert pending["worker_id"] == "mailer"
            assert len(llm.ainvoke_calls) == 1  # compose 1회 — final_answer 없음 (D-13)

            # ── 재개: _restore_state 동형 — outcome 주입 + 신호·종결 초기화 ──
            resumed = dict(result)
            resumed["messages"] = list(result["messages"]) + [
                AIMessage(content=OUTCOME, name="mailer"),
            ]
            resumed["approval_pending"] = {}
            resumed["next_worker"] = ""
            resumed["finish_challenge_pending"] = False
            llm.decisions = ["mailer", "FINISH"]  # supervisor가 같은 워커를 또 고르더라도

            final = await _run(compiler, workflow, state=resumed)

        assert tool.calls == []                      # 재실행 0회 (SC-8)
        assert len(llm.ainvoke_calls) == 2            # + final_answer 1회만
        assert "approval_pending" not in final or not final["approval_pending"]
        fa_prompt = llm.system_prompts()[-1]
        assert DRAFT in fa_prompt and OUTCOME in fa_prompt
        assert fa_prompt.count(DRAFT) == 1
        assert "재작성" in fa_prompt


class TestUngatedRun:
    @pytest.mark.asyncio
    async def test_dispatches_once_and_final_answer_keeps_draft(self):
        llm = FakeRunLLM(decisions=["mailer", "FINISH"])
        compiler, workflow, tool = _compile_ready(llm, gated=False)

        result = await _run(compiler, workflow)

        assert len(tool.calls) == 1
        assert tool.calls[0] == {"arguments": {"to": "kim@customer.co.kr", "body": DRAFT}}
        assert not result.get("approval_pending")
        assert len(llm.ainvoke_calls) == 2           # compose + final_answer
        fa_prompt = llm.system_prompts()[-1]
        assert DRAFT in fa_prompt and OUTCOME in fa_prompt
        assert result["messages"][-1].content == DRAFT  # final_answer 산출(대역은 초안 그대로 반환)
