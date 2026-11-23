"""검색 가드 상수·ES 절 — Design §9.5 (필드 부재 = active 로 통과)."""

from src.domain.document_revision.search_guard import (
    REVISION_STATUS_FIELD,
    SUPERSEDED_VALUE,
    es_revision_guard_clause,
)


def test_constants() -> None:
    assert REVISION_STATUS_FIELD == "revision_status"
    assert SUPERSEDED_VALUE == "superseded"


def test_es_clause_excludes_only_superseded() -> None:
    assert es_revision_guard_clause() == {
        "bool": {"must_not": [{"term": {"revision_status": "superseded"}}]}
    }


def test_es_clause_returns_fresh_dict() -> None:
    a = es_revision_guard_clause()
    a["bool"]["must_not"].append({"x": 1})
    assert len(es_revision_guard_clause()["bool"]["must_not"]) == 1
