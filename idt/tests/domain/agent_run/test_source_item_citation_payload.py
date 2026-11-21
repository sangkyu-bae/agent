"""RunSourceItem.citation payload·재진입 DTO — answer-citation §4.2 (S10)."""

from src.domain.agent_run.source_policy import RunSourceItem, SourceKind
from src.interfaces.schemas.agent_run_response import SourceItemDto

CITATION = {
    "status": "verified",
    "entries": [{"no": 1, "chunk_id": "c", "page": 2, "evidence": "e"}],
}


def test_payload_omits_citation_when_none():
    item = RunSourceItem(kind=SourceKind.DOCUMENT, label="a.pdf", excerpt="x", key="d")
    assert "citation" not in item.to_payload()


def test_payload_includes_citation_and_dto_round_trips():
    item = RunSourceItem(
        kind=SourceKind.DOCUMENT, label="a.pdf", excerpt="x", key="d", citation=CITATION
    )
    payload = item.to_payload()
    assert payload["citation"] == CITATION
    assert SourceItemDto(**payload).citation == CITATION


def test_dto_citation_defaults_to_null():
    dto = SourceItemDto(kind="document", source="a.pdf", content="x", chunk_id="d")
    assert dto.model_dump()["citation"] is None
