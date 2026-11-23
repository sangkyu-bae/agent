"""근거 칩 버전 라벨 — document-revision module-6 (Plan SC-5, FR-14)."""
from datetime import datetime, timezone

from src.domain.agent_run.entities import RetrievalSource
from src.domain.agent_run.source_policy import RunEvidence, RunSourcePolicy
from src.domain.agent_run.value_objects import RunId

RUN_ID = RunId("11111111-1111-1111-1111-111111111111")
T0 = datetime(2026, 11, 2, tzinfo=timezone.utc)


def _r(doc_id: str, id_: str, filename: str | None = None) -> RetrievalSource:
    return RetrievalSource(
        id=id_, run_id=RUN_ID, tool_call_id=None, collection_name="kb",
        document_id=doc_id, chunk_id=f"c-{id_}", score=None, rank_index=1,
        content_preview="발췌", metadata_json={"filename": filename} if filename else {},
        created_at=T0,
    )


def _build(retrievals, filenames=None, version_labels=None):
    return RunSourcePolicy.build(
        RunEvidence(
            retrievals=retrievals, tool_calls=[], filenames=filenames or {},
            mcp_tools={}, version_labels=version_labels or {},
        ),
        max_items=6,
    )


def test_label_appends_version() -> None:
    items = _build(
        [_r("d3", "1", "여신심사기준.pdf")], version_labels={"d3": "v3 (2026-11 개정)"}
    )
    assert items[0].label == "여신심사기준.pdf · v3 (2026-11 개정)"


def test_v1_without_label_is_unchanged() -> None:
    items = _build([_r("d1", "1", "규정.pdf")])
    assert items[0].label == "규정.pdf"


def test_filename_from_lookup_also_gets_version() -> None:
    items = _build(
        [_r("d2", "1")], filenames={"d2": "규정.pdf"}, version_labels={"d2": "v2"}
    )
    assert items[0].label == "규정.pdf · v2"


def test_different_versions_of_same_file_are_separate_chips() -> None:
    items = _build(
        [_r("d1", "1", "규정.pdf"), _r("d2", "2", "규정.pdf")],
        version_labels={"d2": "v2"},
    )
    assert [i.label for i in items] == ["규정.pdf", "규정.pdf · v2"]


def test_same_file_reuploaded_without_versions_still_dedups() -> None:
    items = _build([_r("a", "1", "규정.pdf"), _r("b", "2", "규정.pdf")])
    assert len(items) == 1
