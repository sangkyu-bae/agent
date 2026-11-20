"""source-passage-viewer module-3 — 재진입 API DTO 가 viewer 를 보존한다 (§11.2 #7, SC-8)."""
from src.domain.agent_run.source_policy import RunSourceItem, SourceKind
from src.interfaces.schemas.agent_run_response import SourceItemDto


def _item(viewer=None):
    return RunSourceItem(
        kind=SourceKind.DOCUMENT, label="규정.pdf", excerpt="발췌", key="doc-1", viewer=viewer,
    )


def test_viewer_round_trips_through_dto():
    viewer = {"document_id": "doc-1", "kb_id": "kb-1", "original": None, "passages": []}
    dto = SourceItemDto(**_item(viewer).to_payload())
    assert dto.model_dump()["viewer"] == viewer


def test_dto_without_viewer_defaults_to_none():
    dto = SourceItemDto(**_item().to_payload())
    assert dto.viewer is None
