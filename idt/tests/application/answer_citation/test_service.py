"""CitationService / CitationRun — answer-citation-verification §2.1 (D-10~D-12)."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from src.application.agent_run.context import (
    RunContext,
    reset_run_context,
    set_current_run_context,
)
from src.application.answer_citation.registry import CitationRegistry
from src.application.answer_citation.service import CitationService
from src.domain.agent_run.value_objects import RunId
from src.domain.hallucination.citation_check import CitationCheck
from src.domain.hallucination.grounding import GroundingVerdict

RUN = "11111111-1111-1111-1111-111111111111"


@pytest.fixture
def run_ctx():
    token = set_current_run_context(
        RunContext(run_id=RunId(RUN), user_id="u", agent_id="a", callback=MagicMock())
    )
    yield
    reset_run_context(token)


def _service(registry=None, store=None):
    registry = registry or CitationRegistry()
    store = store or AsyncMock()
    return CitationService(registry, store, MagicMock()), registry, store


def _register(registry, n_chunks=2):
    for i in range(1, n_chunks + 1):
        registry.assign(
            RUN,
            chunk_id=f"ch-{i}",
            document_id=f"d{i}",
            page=i,
            text=f"청크{i}: 근거 문장 {i}번입니다.",
        )


def test_begin_none_without_run_context():
    svc, registry, _ = _service()
    _register(registry)
    assert svc.begin() is None


def test_begin_none_when_no_numbered_chunks(run_ctx):
    svc, _, _ = _service()
    assert svc.begin() is None


def test_instruction_and_history_strip(run_ctx):
    svc, registry, _ = _service()
    _register(registry)
    run = svc.begin()
    assert "[인용 규칙]" in run.instruction
    assert run.strip_history("지난 답변[3]입니다.") == "지난 답변입니다."


def test_request_for_builds_pairs_and_cited_sources(run_ctx):
    svc, registry, _ = _service()
    _register(registry, 3)
    run = svc.begin()
    req = run.request_for("가는 맞습니다.[1] 나는[1, 2] 맞습니다.")
    assert [(p.marker, p.sentence) for p in req.pairs] == [
        (1, "가는 맞습니다."),
        (1, "나는 맞습니다."),
        (2, "나는 맞습니다."),
    ]
    assert set(req.cited_sources) == {1, 2}
    assert run.request_for("인용 없는 답") is None


@pytest.mark.asyncio
async def test_finalize_saves_outcome_and_discards_registry(run_ctx):
    svc, registry, store = _service()
    _register(registry)
    run = svc.begin()
    text = "가는 맞습니다[1]. 나는 틀립니다[2]."
    req = run.request_for(text)
    verdict = GroundingVerdict(
        unsupported_claims=(),
        citation_checks=(
            CitationCheck("c1", True, "근거 문장 1번"),
            CitationCheck("c2", False, ""),
        ),
    )
    out = await run.finalize(text, verdict, req, request_id="r")
    assert out == "가는 맞습니다[1]. 나는 틀립니다."
    saved = store.save.await_args
    assert saved.args[0] == RUN
    assert saved.args[1].status == "verified"
    assert [c.chunk_id for c in saved.args[1].citations] == ["ch-1"]
    assert registry.chunks(RUN) == {}


@pytest.mark.asyncio
async def test_finalize_without_verdict_is_judge_failed(run_ctx):
    svc, registry, store = _service()
    _register(registry)
    run = svc.begin()
    out = await run.finalize("가[1].", None, None, request_id="r")
    assert out == "가."
    outcome = store.save.await_args.args[1]
    assert (outcome.status, outcome.none_reason) == ("none", "judge_failed")


@pytest.mark.asyncio
async def test_store_failure_does_not_break_answer(run_ctx):
    store = AsyncMock()
    store.save.side_effect = RuntimeError("db down")
    svc, registry, _ = _service(store=store)
    _register(registry)
    run = svc.begin()
    out = await run.finalize("인용 없는 답.", None, None, request_id="r")
    assert out == "인용 없는 답."
