"""module-3 도메인: 추출 단위 선택·근거 검증·이름 정규화·결정적 ID (Design §2.2·§3.4)."""
import pytest
from src.domain.graph_rag.extraction import (
    ChunkUnit,
    EvidencePolicy,
    ExtractionUnitPolicy,
    NameNormalizer,
    decision_id_for,
    relation_id_for,
)


def _doc(cid, ctype, idx=0, content="본문"):
    return {"chunk_id": cid, "chunk_type": ctype, "chunk_index": idx, "content": content}


def test_units_prefer_parents_and_skip_children_and_summaries():
    docs = [
        _doc("p1", "parent", 0), _doc("c1", "child", 1), _doc("c2", "child", 2),
        _doc("p2", "parent", 3), _doc("s1", "section_summary", 4),
    ]
    assert [d["chunk_id"] for d in ExtractionUnitPolicy.select(docs)] == ["p1", "p2"]


def test_units_without_parents_use_all_non_summary_in_order():
    docs = [_doc("b", "semantic", 2), _doc("a", "semantic", 1),
            _doc("s", "document_summary", 0)]
    assert [d["chunk_id"] for d in ExtractionUnitPolicy.select(docs)] == ["a", "b"]


def test_units_skip_empty_content():
    docs = [_doc("a", "full", 0, content="  "), _doc("b", "full", 1)]
    assert [d["chunk_id"] for d in ExtractionUnitPolicy.select(docs)] == ["b"]


@pytest.mark.parametrize("evidence, ok", [
    ("개인사업자는 한도의 50%까지", True),
    ("개인사업자는   한도의\n50%까지", True),   # 공백·줄바꿈 차이는 허용
    ("법인은 한도의 50%까지", False),           # 원문에 없는 문장
    ("", False),
    ("짧", False),                              # 너무 짧으면 근거로 인정하지 않음
])
def test_evidence_must_be_in_chunk(evidence, ok):
    chunk = "제5조(한도) ① 개인사업자는 한도의 50%까지 대출할 수 있다."
    assert EvidencePolicy.is_grounded(evidence, chunk) is ok


@pytest.mark.parametrize("raw, norm", [
    ("  여신  한도 ", "여신 한도"),
    ("ＡＢＣ상품", "abc상품"),          # NFKC + casefold
    ("「여신업무규정」", "여신업무규정"),  # 양끝 괄호류 제거
    ("한도.", "한도"),
])
def test_name_normalizer(raw, norm):
    assert NameNormalizer.normalize(raw) == norm


def test_deterministic_ids():
    a = decision_id_for("chunk-1", "여신 한도", "용어")
    assert a == decision_id_for("chunk-1", "여신 한도", "용어")
    assert a != decision_id_for("chunk-2", "여신 한도", "용어")
    r = relation_id_for("chunk-1", "a상품", "적용대상", "개인사업자")
    assert r == relation_id_for("chunk-1", "a상품", "적용대상", "개인사업자")
    assert r != relation_id_for("chunk-1", "개인사업자", "적용대상", "a상품")


@pytest.mark.parametrize("filename, ok", [
    ("여신업무규정.pdf", True), ("규정.HWP", True), ("지침.docx", True),
    ("거래처정보.xlsx", False), ("요율표.XLS", False), ("목록.csv", False),
])
def test_extractable_filename(filename, ok):
    from src.domain.graph_rag.extraction import DocumentEligibilityPolicy

    assert DocumentEligibilityPolicy.is_extractable(filename) is ok


def test_chunk_unit_is_frozen():
    u = ChunkUnit(chunk_id="p1", document_id="d", kb_id="kb", collection_name="c",
                  content="x", chunk_index=0)
    with pytest.raises(Exception):
        u.content = "y"  # type: ignore[misc]
