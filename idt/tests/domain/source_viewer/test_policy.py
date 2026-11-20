"""source-passage-viewer module-1 — PassagePolicy · storage_key (Design §3.1, §8.2 #1~4)."""
from datetime import datetime, timedelta

import pytest

from src.domain.agent_run.entities import RetrievalSource
from src.domain.agent_run.value_objects import RunId
from src.domain.source_viewer.models import OriginalKind, Passage
from src.domain.source_viewer.policy import PassagePolicy, storage_key

_T0 = datetime(2026, 11, 19, 9, 0, 0)
_DOC = "8f1c2d3e-0000-4000-8000-000000000001"
_OTHER = "8f1c2d3e-0000-4000-8000-000000000002"


def _r(
    rid: str,
    *,
    document_id: str | None = _DOC,
    chunk_id: str | None = None,
    rank: int | None = 1,
    offset: int = 0,
    collection: str = "kb_col",
    metadata: dict | None = None,
    preview: str | None = "본문",
) -> RetrievalSource:
    return RetrievalSource(
        id=rid,
        run_id=RunId("00000000-0000-4000-8000-0000000000aa"),
        tool_call_id=None,
        collection_name=collection,
        document_id=document_id,
        chunk_id=chunk_id,
        score=0.9,
        rank_index=rank,
        content_preview=preview,
        metadata_json=metadata,
        created_at=_T0 + timedelta(seconds=offset),
    )


class TestCollect:
    def test_filters_document_dedups_and_orders(self):
        retrievals = [
            _r("r3", chunk_id="c-3", rank=2, offset=1),
            _r("r1", chunk_id="c-1", rank=2, offset=0),
            _r("r2", chunk_id="c-2", rank=1, offset=0),
            _r("r1b", chunk_id="c-1", rank=5, offset=2),  # 같은 청크 재검색
            _r("rx", document_id=_OTHER, chunk_id="c-9"),
            _r("rw", chunk_id="c-w", collection="tavily_web"),
        ]
        passages = PassagePolicy.collect(_DOC, retrievals)
        assert [p.chunk_id for p in passages] == ["c-2", "c-1", "c-3"]
        assert [p.rank for p in passages] == [0, 1, 2]

    def test_metadata_chunk_id_wins_over_record_chunk_id(self):
        r = _r("r1", chunk_id="point-uuid", metadata={"chunk_id": "meta-c", "parent_id": "p-1"})
        (p,) = PassagePolicy.collect(_DOC, [r])
        assert p == Passage(chunk_id="meta-c", parent_id="p-1", page=None, rank=0, excerpt="본문")

    @pytest.mark.parametrize(
        "raw, expected",
        [("12", 12), (12, 12), (None, None), ("x", None), (True, None), (0, None)],
    )
    def test_page_normalization(self, raw, expected):
        r = _r("r1", chunk_id="c-1", metadata={"page": raw})
        (p,) = PassagePolicy.collect(_DOC, [r])
        assert p.page == expected

    def test_falls_back_to_record_id_when_no_chunk_id(self):
        (p,) = PassagePolicy.collect(_DOC, [_r("r1", chunk_id=None)])
        assert p.chunk_id == "r1"

    def test_caps_at_max_passages(self):
        retrievals = [_r(f"r{i}", chunk_id=f"c-{i}", rank=i) for i in range(30)]
        assert len(PassagePolicy.collect(_DOC, retrievals)) == PassagePolicy.MAX_PASSAGES

    def test_missing_preview_becomes_empty_excerpt(self):
        (p,) = PassagePolicy.collect(_DOC, [_r("r1", chunk_id="c-1", preview=None)])
        assert p.excerpt == ""


class TestKbIdAndKind:
    def test_kb_id_first_non_empty(self):
        retrievals = [
            _r("r1", metadata={"kb_id": ""}),
            _r("r2", metadata={"kb_id": "kb-1"}),
            _r("r3", document_id=_OTHER, metadata={"kb_id": "kb-other"}),
        ]
        assert PassagePolicy.kb_id_of(_DOC, retrievals) == "kb-1"

    def test_kb_id_none_when_absent(self):
        assert PassagePolicy.kb_id_of(_DOC, [_r("r1", metadata=None)]) is None

    @pytest.mark.parametrize(
        "filename, expected",
        [
            ("여신규정.pdf", OriginalKind.PDF),
            ("A.PDF", OriginalKind.PDF),
            ("계약서.docx", OriginalKind.DOCX),
            ("규정.hwp", None),
            ("data.xlsx", None),
            ("noext", None),
            ("", None),
        ],
    )
    def test_original_kind(self, filename, expected):
        assert PassagePolicy.original_kind(filename) == expected


class TestStorageKey:
    def test_valid_uuid_shards_by_prefix(self):
        assert storage_key(_DOC) == f"8f/{_DOC}"

    def test_uppercase_uuid_is_normalized(self):
        assert storage_key(_DOC.upper()) == f"8f/{_DOC}"

    @pytest.mark.parametrize(
        "bad", ["", "../etc/passwd", "8f/../../x", "not-a-uuid", _DOC + "/x", "a" * 36]
    )
    def test_rejects_non_uuid(self, bad):
        with pytest.raises(ValueError):
            storage_key(bad)
