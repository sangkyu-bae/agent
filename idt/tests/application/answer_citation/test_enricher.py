"""CitationEnricher — answer-citation-verification §4.2 칩 계약, D-12·D-13·D-14."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.application.answer_citation.enricher import CitationEnricher
from src.domain.agent_run.entities import RetrievalSource
from src.domain.agent_run.source_policy import RunEvidence, RunSourceItem, SourceKind
from src.domain.agent_run.value_objects import RunId
from src.domain.answer_citation.models import AnswerCitation
from src.domain.answer_citation.ports import StoredRunCitations

RUN = RunId("11111111-1111-1111-1111-111111111111")
T0 = datetime(2026, 11, 21, tzinfo=UTC)


def _retrieval(doc: str, chunk: str, page=None, filename=None) -> RetrievalSource:
    meta = {}
    if page is not None:
        meta["page"] = page
    if filename:
        meta["filename"] = filename
    return RetrievalSource(
        id=f"r-{chunk}",
        run_id=RUN,
        tool_call_id=None,
        collection_name="kb",
        document_id=doc,
        chunk_id=chunk,
        score=None,
        rank_index=1,
        content_preview="발췌",
        metadata_json=meta,
        created_at=T0,
    )


def _cite(no, chunk, doc, page=None, evidence="근거", sentence="문장."):
    return AnswerCitation(
        no=no,
        marker=no,
        chunk_id=chunk,
        document_id=doc,
        page=page,
        evidence=evidence,
        sentence=sentence,
    )


def _doc(key: str) -> RunSourceItem:
    return RunSourceItem(
        kind=SourceKind.DOCUMENT, label=f"{key}.pdf", excerpt="발췌", key=key
    )


WEB = RunSourceItem(
    kind=SourceKind.WEB, label="웹", excerpt="", key="w", url="https://x"
)
EVIDENCE = RunEvidence(
    retrievals=[
        _retrieval("doc-a", "ca", page=3, filename="a.pdf"),
        _retrieval("doc-b", "cb"),
        _retrieval("doc-c", "cc", filename="c.pdf"),
    ],
    tool_calls=[],
    filenames={"doc-b": "b.pdf"},
    mcp_tools={},
)


def _enricher():
    return CitationEnricher(MagicMock(), MagicMock())


def test_no_stored_row_leaves_items_unchanged():
    items = [_doc("doc-a"), WEB]
    assert _enricher().apply(items, None, EVIDENCE) == items


def test_verified_entries_go_to_their_document_and_unused_get_empty():
    stored = StoredRunCitations(
        str(RUN.value),
        "verified",
        citations=(
            _cite(2, "cb", "doc-b"),
            _cite(1, "ca", "doc-a", page=None, evidence="가"),
            _cite(1, "ca", "doc-a", sentence="다른 문장."),
        ),
    )
    out = _enricher().apply(
        [_doc("doc-a"), _doc("doc-b"), _doc("doc-x"), WEB], stored, EVIDENCE
    )
    a, b, x, web = out
    # 같은 번호·같은 청크는 한 번만, page 가 없으면 검색 기록 metadata 로 보충
    assert a.citation == {
        "status": "verified",
        "entries": [
            {"no": 1, "chunk_id": "ca", "page": 3, "evidence": "가"},
        ],
    }
    assert b.citation["entries"] == [
        {"no": 2, "chunk_id": "cb", "page": None, "evidence": "근거"}
    ]
    assert x.citation == {"status": "verified", "entries": []}
    assert web.citation is None


def test_none_status_marks_every_document_chip():
    stored = StoredRunCitations(
        str(RUN.value), "none", citations=(), none_reason="all_rejected"
    )
    a, web = _enricher().apply([_doc("doc-a"), WEB], stored, EVIDENCE)
    assert a.citation == {"status": "none", "entries": []}
    assert web.citation is None


def test_cited_document_missing_from_chips_is_added_after_documents():
    stored = StoredRunCitations(
        str(RUN.value),
        "verified",
        citations=(_cite(1, "cc", "doc-c", evidence="보충 근거"),),
    )
    out = _enricher().apply([_doc("doc-a"), WEB], stored, EVIDENCE)
    assert [i.key for i in out] == ["doc-a", "doc-c", "w"]
    added = out[1]
    assert (added.kind, added.label, added.excerpt) == (
        SourceKind.DOCUMENT,
        "c.pdf",
        "보충 근거",
    )
    assert added.citation["entries"][0]["no"] == 1


def test_citation_without_document_id_is_skipped():
    stored = StoredRunCitations(
        str(RUN.value), "verified", citations=(_cite(1, "zz", None),)
    )
    (a,) = _enricher().apply([_doc("doc-a")], stored, EVIDENCE)
    assert a.citation == {"status": "verified", "entries": []}


@pytest.mark.asyncio
async def test_load_reads_repository_by_run_ids():
    repo = MagicMock()
    repo.find_by_runs = AsyncMock(return_value={"r": "x"})
    assert await CitationEnricher(repo, MagicMock()).load(["r"], "req") == {"r": "x"}
    repo.find_by_runs.assert_awaited_once_with(["r"], "req")
