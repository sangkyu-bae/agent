"""source-passage-viewer module-3 — ViewerRef wire 형식·파일명 해석 (Design §3.3)."""
from datetime import datetime

from src.domain.agent_run.entities import RetrievalSource
from src.domain.agent_run.value_objects import RunId
from src.domain.source_viewer.models import OriginalKind, Passage, ViewerRef
from src.domain.source_viewer.policy import PassagePolicy

_DOC = "8f1c2d3e-0000-4000-8000-000000000001"


def _r(metadata: dict | None) -> RetrievalSource:
    return RetrievalSource(
        id="r1", run_id=RunId("00000000-0000-4000-8000-0000000000aa"),
        tool_call_id=None, collection_name="kb", document_id=_DOC, chunk_id="c1",
        score=None, rank_index=1, content_preview="발췌", metadata_json=metadata,
        created_at=datetime(2026, 11, 19),
    )


def test_viewer_ref_payload_shape():
    ref = ViewerRef(
        document_id=_DOC,
        kb_id="kb-1",
        original=OriginalKind.PDF,
        passages=(
            Passage(chunk_id="c-1", parent_id="p-1", page=12, rank=0, excerpt="가"),
            Passage(chunk_id="c-2", parent_id=None, page=None, rank=1, excerpt="나"),
        ),
    )
    assert ref.to_payload() == {
        "document_id": _DOC,
        "kb_id": "kb-1",
        "original": "pdf",
        "passages": [
            {"chunk_id": "c-1", "parent_id": "p-1", "page": 12, "excerpt": "가"},
            {"chunk_id": "c-2", "parent_id": None, "page": None, "excerpt": "나"},
        ],
    }


def test_viewer_ref_payload_without_original():
    ref = ViewerRef(document_id=_DOC, kb_id="kb-1", original=None, passages=())
    assert ref.to_payload()["original"] is None


def test_filename_prefers_retrieval_metadata():
    assert PassagePolicy.filename_of(_DOC, [_r({"filename": "규정.pdf"})], {_DOC: "x.docx"}) == "규정.pdf"


def test_filename_falls_back_to_lookup_then_empty():
    assert PassagePolicy.filename_of(_DOC, [_r(None)], {_DOC: "x.docx"}) == "x.docx"
    assert PassagePolicy.filename_of(_DOC, [_r(None)], {}) == ""
