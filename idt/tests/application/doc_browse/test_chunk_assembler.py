"""chunk_assembler 단위 테스트 — kb-content-browser Design §4.2 (구현 순서 1).

GetChunksUseCase에서 추출한 공용 조립 헬퍼가 기존 동작과 동등함을 검증한다.
입력은 payload dict 리스트 (Qdrant point / ES hit 공용 정규화 형태).
"""
from __future__ import annotations

from src.application.doc_browse.chunk_assembler import (
    assemble_chunks_result,
    build_flat_list,
    build_hierarchy,
    detect_strategy,
    exclude_summary_payloads,
)


def _payload(**overrides) -> dict:
    base = {
        "document_id": "doc-1",
        "filename": "a.pdf",
        "category": "policy",
        "user_id": "u1",
        "chunk_id": "c1",
        "chunk_index": 0,
        "chunk_type": "child",
        "content": "text",
        "total_chunks": 1,
    }
    base.update(overrides)
    return base


class TestDetectStrategy:
    def test_parent_child(self):
        payloads = [_payload(chunk_type="parent"), _payload(chunk_type="child")]
        assert detect_strategy(payloads) == "parent_child"

    def test_full_token(self):
        assert detect_strategy([_payload(chunk_type="full")]) == "full_token"

    def test_semantic(self):
        assert detect_strategy([_payload(chunk_type="semantic")]) == "semantic"

    def test_unknown(self):
        assert detect_strategy([_payload(chunk_type="other")]) == "unknown"


class TestExcludeSummaryPayloads:
    def test_removes_summary_layers(self):
        payloads = [
            _payload(chunk_id="c1", chunk_type="child"),
            _payload(chunk_id="s1", chunk_type="section_summary"),
            _payload(chunk_id="d1", chunk_type="document_summary"),
        ]
        remaining = exclude_summary_payloads(payloads)
        assert [p["chunk_id"] for p in remaining] == ["c1"]


class TestBuildFlatList:
    def test_excludes_parent_for_parent_child(self):
        payloads = [
            _payload(chunk_id="p1", chunk_type="parent", chunk_index=0),
            _payload(chunk_id="c1", chunk_type="child", chunk_index=0, parent_id="p1"),
            _payload(chunk_id="c2", chunk_type="child", chunk_index=1, parent_id="p1"),
        ]
        chunks = build_flat_list(payloads, "parent_child")
        assert len(chunks) == 2
        assert all(c.chunk_type == "child" for c in chunks)

    def test_sorts_by_chunk_index(self):
        payloads = [
            _payload(chunk_id="c3", chunk_index=2),
            _payload(chunk_id="c1", chunk_index=0),
            _payload(chunk_id="c2", chunk_index=1),
        ]
        chunks = build_flat_list(payloads, "full_token")
        assert [c.chunk_index for c in chunks] == [0, 1, 2]

    def test_str_chunk_index_cast(self):
        """Qdrant payload는 chunk_index가 str로 저장됨 — int 캐스팅."""
        payloads = [_payload(chunk_id="c1", chunk_index="3")]
        chunks = build_flat_list(payloads, "full_token")
        assert chunks[0].chunk_index == 3

    def test_invalid_chunk_index_defaults_zero(self):
        payloads = [_payload(chunk_id="c1", chunk_index="abc")]
        chunks = build_flat_list(payloads, "full_token")
        assert chunks[0].chunk_index == 0

    def test_metadata_excludes_internal_keys(self):
        payloads = [_payload(chunk_id="c1", custom_key="v", total_chunks=5)]
        meta = build_flat_list(payloads, "full_token")[0].metadata
        for excluded in ("content", "chunk_id", "chunk_index", "chunk_type", "total_chunks"):
            assert excluded not in meta
        assert meta["custom_key"] == "v"


class TestBuildHierarchy:
    def test_maps_children_to_correct_parent(self):
        payloads = [
            _payload(chunk_id="par1", chunk_type="parent", chunk_index=0),
            _payload(chunk_id="par2", chunk_type="parent", chunk_index=1),
            _payload(chunk_id="ch1", chunk_type="child", chunk_index=0, parent_id="par1"),
            _payload(chunk_id="ch2", chunk_type="child", chunk_index=0, parent_id="par2"),
            _payload(chunk_id="ch3", chunk_type="child", chunk_index=1, parent_id="par2"),
        ]
        groups = build_hierarchy(payloads)
        assert len(groups) == 2
        par1 = next(g for g in groups if g.chunk_id == "par1")
        par2 = next(g for g in groups if g.chunk_id == "par2")
        assert len(par1.children) == 1
        assert len(par2.children) == 2

    def test_parents_sorted_by_index(self):
        payloads = [
            _payload(chunk_id="par2", chunk_type="parent", chunk_index=1),
            _payload(chunk_id="par1", chunk_type="parent", chunk_index=0),
        ]
        groups = build_hierarchy(payloads)
        assert [g.chunk_id for g in groups] == ["par1", "par2"]


class TestAssembleChunksResult:
    def test_empty_returns_unknown(self):
        result = assemble_chunks_result("doc-x", [], include_parent=False)
        assert result.total_chunks == 0
        assert result.filename == "unknown"
        assert result.chunk_strategy == "unknown"

    def test_parent_child_with_hierarchy(self):
        payloads = [
            _payload(chunk_id="par1", chunk_type="parent", chunk_index=0),
            _payload(chunk_id="ch1", chunk_type="child", chunk_index=0, parent_id="par1"),
        ]
        result = assemble_chunks_result("doc-1", payloads, include_parent=True)
        assert result.chunk_strategy == "parent_child"
        assert result.parents is not None
        assert result.total_chunks == 2

    def test_include_parent_ignored_for_flat_strategy(self):
        payloads = [_payload(chunk_id="c1", chunk_type="full")]
        result = assemble_chunks_result("doc-1", payloads, include_parent=True)
        assert result.parents is None
        assert len(result.chunks) == 1

    def test_filename_override(self):
        """ES 소스 등 payload에 filename 없을 때 document_metadata 값으로 대체."""
        payloads = [{**_payload(chunk_id="c1", chunk_type="full")}]
        payloads[0].pop("filename")
        result = assemble_chunks_result(
            "doc-1", payloads, include_parent=False, filename="meta.pdf"
        )
        assert result.filename == "meta.pdf"

    def test_payload_filename_wins_over_override_absence(self):
        payloads = [_payload(chunk_id="c1", chunk_type="full", filename="p.pdf")]
        result = assemble_chunks_result("doc-1", payloads, include_parent=False)
        assert result.filename == "p.pdf"
