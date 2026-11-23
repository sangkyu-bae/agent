"""CitationLabeler — answer-citation-verification §10.2 라벨 형식."""

from unittest.mock import MagicMock

from src.application.agent_run.context import (
    RunContext,
    reset_run_context,
    set_current_run_context,
)
from src.application.answer_citation.labeler import CitationLabeler
from src.application.answer_citation.registry import CitationRegistry
from src.domain.agent_run.value_objects import RunId

RUN = "11111111-1111-1111-1111-111111111111"


def _with_run(fn):
    token = set_current_run_context(
        RunContext(run_id=RunId(RUN), user_id="u", agent_id="a", callback=MagicMock())
    )
    try:
        return fn()
    finally:
        reset_run_context(token)


def _label(labeler, chunk="c1", page=5, source="가계부채.pdf"):
    return labeler.label(
        source=source, chunk_id=chunk, document_id="d1", page=page, text="본문"
    )


def test_label_with_number_and_page_and_registers_chunk():
    reg = CitationRegistry()
    labeler = CitationLabeler(reg, MagicMock())
    assert _with_run(lambda: _label(labeler)) == "[출처 1: 가계부채.pdf · 5쪽]"
    assert (
        _with_run(lambda: _label(labeler, chunk="c2", page=None))
        == "[출처 2: 가계부채.pdf]"
    )
    assert reg.chunks(RUN)[1].chunk_id == "c1"


def test_string_page_and_invalid_page():
    labeler = CitationLabeler(CitationRegistry(), MagicMock())
    assert (
        _with_run(lambda: _label(labeler, page="7")) == "[출처 1: 가계부채.pdf · 7쪽]"
    )
    assert (
        _with_run(lambda: _label(labeler, chunk="c2", page="표지"))
        == "[출처 2: 가계부채.pdf]"
    )


def test_no_run_context_returns_none():
    labeler = CitationLabeler(CitationRegistry(), MagicMock())
    assert _label(labeler) is None


def test_registry_failure_returns_none_and_warns():
    reg = MagicMock()
    reg.assign.side_effect = RuntimeError("boom")
    logger = MagicMock()
    labeler = CitationLabeler(reg, logger)
    assert _with_run(lambda: _label(labeler)) is None
    logger.warning.assert_called_once()
