"""final_answer 인용 결선 S8 — answer-citation-verification FR-04·FR-07·FR-15·D-10."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from src.application.agent_builder.workflow_compiler import WorkflowCompiler
from src.application.agent_run.context import (
    RunContext,
    reset_run_context,
    set_current_run_context,
)
from src.application.answer_citation.registry import CitationRegistry
from src.application.answer_citation.service import CitationService
from src.application.hallucination.grounded_generation import GroundedGenerator
from src.domain.agent_run.value_objects import RunId
from src.domain.hallucination.citation_check import CitationCheck
from src.domain.hallucination.grounding import GroundingJudgePort, GroundingVerdict
from src.infrastructure.agent_builder.tool_factory import ToolFactory

RUN = "22222222-2222-2222-2222-222222222222"
EVIDENCE = (
    "[출처 1: 가계부채.pdf · 2쪽]\n총량 목표를 경상성장률 이내로 관리\n\n"
    "[출처 2: 가계부채.pdf · 4쪽]\n주담대 한도 6억 원"
)
ANSWER = "총량 목표를 관리합니다[1]. 한도는 7억 원입니다[2]."


class FakeJudge(GroundingJudgePort):
    def __init__(self, checks=()):
        self.checks = tuple(checks)
        self.calls: list[dict] = []

    async def judge(self, **kwargs):
        self.calls.append(kwargs)
        return GroundingVerdict(unsupported_claims=(), citation_checks=self.checks)


class RecordingLLM:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls: list[list] = []
        self.configs: list = []

    async def ainvoke(self, messages, config=None):
        self.calls.append(messages)
        self.configs.append(config)
        return AIMessage(content=self.outputs.pop(0))


@pytest.fixture
def run_ctx():
    token = set_current_run_context(
        RunContext(run_id=RunId(RUN), user_id="u", agent_id="a", callback=MagicMock())
    )
    yield
    reset_run_context(token)


def _registry_with_chunks():
    reg = CitationRegistry()
    reg.assign(
        RUN,
        chunk_id="ch-1",
        document_id="d",
        page=2,
        text="총량 목표를 경상성장률 이내로 관리",
    )
    reg.assign(RUN, chunk_id="ch-2", document_id="d", page=4, text="주담대 한도 6억 원")
    return reg


def _node(llm, judge, *, enabled=True, registry=None, store=None):
    service = None
    if registry is not None:
        service = CitationService(registry, store or AsyncMock(), MagicMock())
    compiler = WorkflowCompiler(
        tool_factory=MagicMock(spec=ToolFactory),
        llm_factory=MagicMock(),
        logger=MagicMock(),
        grounded_generator=GroundedGenerator(
            judge, MagicMock(), enabled=enabled, corpus_max_chars=24000
        ),
        answer_grounding_max_retries=1,
        citation_service=service,
    )
    return compiler._create_final_answer_node(llm, "가계부채 안내 에이전트입니다.")


def _state(history=()):
    messages = [
        *history,
        HumanMessage(content="한도는?"),
        AIMessage(content=EVIDENCE, name="internal_document_search_worker"),
    ]
    return {"messages": messages, "token_usage": 0}


_CHECKS = (
    CitationCheck("c1", True, "경상성장률 이내로 관리"),
    CitationCheck("c2", False, ""),
)


@pytest.mark.asyncio
async def test_without_service_prompt_and_answer_unchanged(run_ctx):
    llm = RecordingLLM([ANSWER])
    judge = FakeJudge()
    out = await _node(llm, judge)(_state())
    assert "[인용 규칙]" not in llm.calls[0][0]["content"]
    assert "citations" not in judge.calls[0]
    assert out["messages"][0].content == ANSWER


@pytest.mark.asyncio
async def test_service_without_numbered_chunks_is_inactive(run_ctx):
    llm = RecordingLLM([ANSWER])
    out = await _node(llm, FakeJudge(), registry=CitationRegistry())(_state())
    assert "[인용 규칙]" not in llm.calls[0][0]["content"]
    assert out["messages"][0].content == ANSWER


@pytest.mark.asyncio
async def test_citations_verified_cleaned_and_saved(run_ctx):
    llm = RecordingLLM([ANSWER])
    judge = FakeJudge(_CHECKS)
    store = AsyncMock()
    out = await _node(llm, judge, registry=_registry_with_chunks(), store=store)(
        _state()
    )
    assert "[인용 규칙]" in llm.calls[0][0]["content"]
    assert [p.marker for p in judge.calls[0]["citations"].pairs] == [1, 2]
    assert (
        out["messages"][0].content == "총량 목표를 관리합니다[1]. 한도는 7억 원입니다."
    )
    outcome = store.save.await_args.args[1]
    assert outcome.status == "verified"
    assert outcome.citations[0].evidence == "경상성장률 이내로 관리"


@pytest.mark.asyncio
async def test_grounding_disabled_still_verifies_once(run_ctx):
    llm = RecordingLLM([ANSWER])
    judge = FakeJudge(_CHECKS)
    out = await _node(llm, judge, enabled=False, registry=_registry_with_chunks())(
        _state()
    )
    assert len(judge.calls) == 1
    assert (
        out["messages"][0].content == "총량 목표를 관리합니다[1]. 한도는 7억 원입니다."
    )


@pytest.mark.asyncio
async def test_previous_answer_markers_are_stripped_from_prompt(run_ctx):
    llm = RecordingLLM([ANSWER])
    history = (
        HumanMessage(content="이전 질문"),
        AIMessage(content="이전 답변[3]입니다."),
    )
    await _node(llm, FakeJudge(_CHECKS), registry=_registry_with_chunks())(
        _state(history)
    )
    contents = [getattr(m, "content", None) for m in llm.calls[0][1:]]
    assert "이전 답변입니다." in contents
    assert all("[3]" not in str(c) for c in contents)


@pytest.mark.asyncio
async def test_grounding_disabled_answer_call_is_not_streamed(run_ctx):
    """Analysis G-2 — 검증 전 번호가 채팅에 스트리밍되지 않도록 내부 태그를 단다."""
    from src.domain.hallucination.grounding import INTERNAL_LLM_TAG

    llm = RecordingLLM([ANSWER])
    await _node(
        llm, FakeJudge(_CHECKS), enabled=False, registry=_registry_with_chunks()
    )(_state())
    assert INTERNAL_LLM_TAG in (llm.configs[0] or {}).get("tags", [])
