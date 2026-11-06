"""pii-masking-integration module-3 — WorkflowCompiler 배선 그래프 테스트.

Design Ref: §2.1, §4.3, §4.4 (FR-03, FR-05, FR-08)
compile된 supervisor 그래프를 실제로 돌려, supervisor(구조화 출력)·react 워커
(create_agent)·final_answer가 외부 LLM으로 보낸 요청 전체에 원본 PII가 없는지
확인한다. 도구와 그래프 상태는 원본이어야 한다.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from src.application.agent_builder.supervisor_hooks import DefaultHooks
from src.application.agent_builder.supervisor_nodes import (
    SupervisorDecision,
    build_initial_state,
)
from src.application.agent_builder.workflow_compiler import WorkflowCompiler
from src.application.pii_masking.guarded_llm import GuardedLlm
from src.domain.agent_builder.schemas import (
    SupervisorConfig,
    WorkerDefinition,
    WorkflowDefinition,
)
from src.domain.llm.interfaces import LLMFactoryInterface

from tests.application.agent_builder.test_workflow_compiler_category import (
    _make_llm_model,
)
from tests.application.pii_masking._scripted_model import ScriptedChatModel
from tests.application.pii_masking._support import make_masker

EMAIL = "kim@customer.co.kr"
PHONE = "010-1234-5678"


class _StructuredRecorder:
    def __init__(self, owner: "RunModel", schema) -> None:
        self._owner = owner
        self._schema = schema

    async def ainvoke(self, messages, config=None, **kwargs):
        self._owner.seen.append(list(messages))
        if self._schema is not SupervisorDecision:
            raise AssertionError(f"unexpected schema {self._schema}")
        return self._owner.decisions.pop(0)


class RunModel(ScriptedChatModel):
    """supervisor 구조화 출력 + 워커/final_answer 본문을 한 모델이 맡는다."""

    decisions: list = []

    def with_structured_output(self, schema, **kwargs):
        return _StructuredRecorder(self, schema)


def _run_model() -> RunModel:
    return RunModel(
        decisions=[
            SupervisorDecision(
                next="sender",
                reasoning="[EMAIL_1] 확인",
                task="[EMAIL_1] 에게 발송",
            ),
            SupervisorDecision(next="FINISH", reasoning="완료"),
        ],
        script=[
            AIMessage(
                content="",
                tool_calls=[{"name": "send", "args": {"to": "[EMAIL_1]"}, "id": "c1"}],
            ),
            AIMessage(content="[EMAIL_1] 로 보냈습니다"),
            AIMessage(content="[EMAIL_1] 로 안내 메일을 보냈습니다"),
        ],
    )


def _compiler(model: RunModel, pii_masker=None):
    sent: list = []

    @tool
    def send(to: str) -> str:
        """메일을 보낸다."""
        sent.append(to)
        return f"발송 완료: {to}, 담당 {PHONE}"

    tool_factory = MagicMock()
    tool_factory.create = MagicMock(return_value=send)
    tool_factory.create_all_async = AsyncMock(return_value=[send])
    llm_factory = MagicMock(spec=LLMFactoryInterface)
    llm_factory.create.return_value = model
    compiler = WorkflowCompiler(
        tool_factory=tool_factory,
        llm_factory=llm_factory,
        logger=MagicMock(),
        hooks=DefaultHooks(),
        pii_masker=pii_masker,
    )
    return compiler, sent


def _workflow() -> WorkflowDefinition:
    return WorkflowDefinition(
        supervisor_prompt=f"고객 응대 에이전트. 담당자 연락처 {PHONE}",
        workers=[
            WorkerDefinition(
                tool_id="send",
                worker_id="sender",
                description="메일 발송",
                sort_order=0,
            )
        ],
        flow_hint="t",
    )


async def _run(compiler, **compile_kwargs):
    config = SupervisorConfig()
    graph = await compiler.compile(
        _workflow(),
        _make_llm_model(),
        "req-1",
        supervisor_config=config,
        **compile_kwargs,
    )
    state = build_initial_state(
        messages=[{"role": "user", "content": f"{EMAIL} 에게 출고 안내 보내줘"}],
        config=config,
        available_workers=["sender"],
    )
    return await graph.ainvoke(state)


def _sent_text(model: RunModel) -> str:
    parts = []
    for messages in model.seen:
        for message in messages:
            # supervisor는 dict 메시지를 넘긴다. guarded 경로만 객체로 정규화된다.
            if isinstance(message, dict):
                parts.append(repr(message))
                continue
            parts.append(repr(message.content))
            parts.append(repr(getattr(message, "tool_calls", None)))
    return "\n".join(parts)


class TestCompiledGraph:
    async def test_every_llm_request_masked_tool_and_state_original(self):
        model = _run_model()
        masker = make_masker()
        compiler, sent = _compiler(model, pii_masker=masker)
        result = await _run(compiler, pii_scope=masker.new_scope())

        text = _sent_text(model)
        assert len(model.seen) >= 4  # supervisor 2 + 워커 2 + final_answer
        assert EMAIL not in text
        assert PHONE not in text
        assert "[EMAIL_1]" in text
        assert sent == [EMAIL]
        assert EMAIL in result["messages"][-1].content
        assert "[EMAIL_" not in repr(result["messages"])

    async def test_compile_without_scope_still_masks(self):
        # Design §6.1: scope 없이 compile이 불려도 경계는 유지된다(우회 방지).
        model = _run_model()
        compiler, _ = _compiler(model, pii_masker=make_masker())
        await _run(compiler)
        assert EMAIL not in _sent_text(model)

    async def test_without_masker_behavior_unchanged(self):
        # 해제(D-03) — 미주입이면 지금과 같은 원문 전송.
        model = RunModel(
            decisions=[SupervisorDecision(next="FINISH", reasoning="x")],
            script=[AIMessage(content="답")],
        )
        compiler, _ = _compiler(model)
        await _run(compiler)
        assert PHONE in _sent_text(model)

    async def test_shadow_mode_sends_original_and_counts(self):
        model = RunModel(
            decisions=[SupervisorDecision(next="FINISH", reasoning="x")],
            script=[AIMessage(content="답")],
        )
        masker = make_masker("shadow")
        scope = masker.new_scope()
        compiler, _ = _compiler(model, pii_masker=masker)
        await _run(compiler, pii_scope=scope)
        assert PHONE in _sent_text(model)
        assert scope.vault.counts()


class TestPipelineLlm:
    def test_resolve_pipeline_llm_cached_model_wrapped_with_run_scope(self):
        masker = make_masker()
        scope = masker.new_scope()
        compiler, _ = _compiler(_run_model(), pii_masker=masker)
        compiler._pipeline_llm_model = _make_llm_model()
        cached = MagicMock(name="pipeline-llm")
        compiler._pipeline_llm_cache = cached
        run_llm = GuardedLlm(MagicMock(), masker, scope)

        resolved = compiler._resolve_pipeline_llm(run_llm)
        assert isinstance(resolved, GuardedLlm)
        assert resolved.inner is cached
        assert resolved.scope is scope

    def test_resolve_pipeline_llm_without_masker_returns_raw_cache(self):
        compiler, _ = _compiler(_run_model())
        compiler._pipeline_llm_model = _make_llm_model()
        cached = MagicMock(name="pipeline-llm")
        compiler._pipeline_llm_cache = cached
        assert compiler._resolve_pipeline_llm(MagicMock()) is cached


class TestSubAgent:
    async def test_compile_sub_agent_passes_parent_scope(self):
        masker = make_masker()
        scope = masker.new_scope()
        compiler, _ = _compiler(_run_model(), pii_masker=masker)
        sub_agent = MagicMock(
            status="active",
            llm_model_id="model-1",
            temperature=0.0,
            include_user_context=True,
        )
        compiler._agent_repository = MagicMock()
        compiler._agent_repository.find_by_id = AsyncMock(return_value=sub_agent)
        compiler.compile = AsyncMock(return_value=MagicMock())
        worker = WorkerDefinition(
            tool_id="",
            worker_id="child",
            description="d",
            sort_order=0,
            worker_type="sub_agent",
            ref_agent_id="agent-child",
        )
        await compiler._compile_sub_agent(
            worker_def=worker,
            llm_model=_make_llm_model(),
            request_id="r",
            temperature=0.0,
            supervisor_config=SupervisorConfig(),
            depth=1,
            visited=set(),
            pii_scope=scope,
        )
        assert compiler.compile.call_args.kwargs["pii_scope"] is scope


def test_class_default_masker_is_none_for_new_fixtures():
    # __new__ 로 만든 픽스처(test_workflow_compiler_sub_agent 등)가 깨지지 않도록.
    assert WorkflowCompiler.__new__(WorkflowCompiler)._pii_masker is None


@pytest.fixture(autouse=True)
def _no_env(monkeypatch):
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
