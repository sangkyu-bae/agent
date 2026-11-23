"""document_metadata 개정 컬럼 매핑 — document-revision Design §3.3.

삽입 시에는 계보 필드를 저장하고, 기존 행 갱신(save 재호출)은 개정 상태를 건드리지 않는다.
상태 전환은 개정 전용 리포지토리만 수행한다 (MySQL 진실 원칙, Design §1.2).
"""

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.domain.doc_browse.schemas import DocumentMetadata
from src.infrastructure.doc_browse.document_metadata_repository import (
    DocumentMetadataRepository,
)
from src.infrastructure.doc_browse.models import DocumentMetadataModel


def _metadata(**kwargs) -> DocumentMetadata:
    base = dict(
        document_id="doc-2",
        collection_name="col",
        filename="여신심사기준_2026.pdf",
        category="policy",
        user_id="7",
        chunk_count=3,
        chunk_strategy="parent_child",
        kb_id="kb-1",
    )
    base.update(kwargs)
    return DocumentMetadata(**base)


@pytest.fixture
def session() -> AsyncMock:
    s = AsyncMock()
    s.add = MagicMock()
    return s


def _no_existing(session: AsyncMock) -> None:
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=result)


def _existing(session: AsyncMock, model: DocumentMetadataModel) -> None:
    result = MagicMock()
    result.scalar_one_or_none.return_value = model
    session.execute = AsyncMock(return_value=result)


def test_domain_defaults_are_v1_without_lineage() -> None:
    m = _metadata()
    assert m.version_no == 1
    assert m.lineage_id is None
    assert m.file_hash is None
    assert m.version_label is None
    assert m.effective_date is None


async def test_insert_persists_revision_fields(session: AsyncMock) -> None:
    _no_existing(session)
    repo = DocumentMetadataRepository(session, MagicMock())
    await repo.save(
        _metadata(
            file_hash="a" * 64,
            lineage_id="doc-1",
            version_no=2,
            version_label="2026-11 개정",
            effective_date=date(2026, 12, 1),
        ),
        "req",
    )
    model = session.add.call_args.args[0]
    assert model.file_hash == "a" * 64
    assert model.lineage_id == "doc-1"
    assert model.version_no == 2
    assert model.version_label == "2026-11 개정"
    assert model.effective_date == date(2026, 12, 1)


async def test_update_does_not_touch_revision_state(session: AsyncMock) -> None:
    model = DocumentMetadataModel(
        document_id="doc-2",
        collection_name="col",
        filename="old.pdf",
        category="policy",
        user_id="7",
        chunk_count=1,
        chunk_strategy="x",
        kb_id="kb-1",
        lineage_id="doc-1",
        version_no=2,
        version_label="라벨",
        revision_status="superseded",
        sync_state="pending",
        file_hash="b" * 64,
    )
    _existing(session, model)
    repo = DocumentMetadataRepository(session, MagicMock())
    await repo.save(_metadata(chunk_count=9), "req")
    assert model.chunk_count == 9
    assert model.lineage_id == "doc-1"
    assert model.version_no == 2
    assert model.version_label == "라벨"
    assert model.revision_status == "superseded"
    assert model.sync_state == "pending"
    assert model.file_hash == "b" * 64


def test_to_domain_maps_revision_fields() -> None:
    model = DocumentMetadataModel(
        document_id="doc-2",
        collection_name="col",
        filename="a.pdf",
        category="c",
        user_id="7",
        chunk_count=1,
        chunk_strategy="x",
        kb_id="kb-1",
        lineage_id="doc-1",
        version_no=3,
        version_label="L",
        effective_date=date(2026, 1, 2),
        file_hash="c" * 64,
    )
    d = DocumentMetadataRepository._to_domain(model)
    assert (d.lineage_id, d.version_no, d.version_label) == ("doc-1", 3, "L")
    assert d.effective_date == date(2026, 1, 2)
    assert d.file_hash == "c" * 64


def test_model_declares_revision_columns_and_indexes() -> None:
    cols = DocumentMetadataModel.__table__.columns
    for name in (
        "file_hash",
        "lineage_id",
        "version_no",
        "version_label",
        "effective_date",
        "revision_status",
        "sync_state",
        "superseded_by",
        "superseded_at",
        "revised_by",
    ):
        assert name in cols, name
    assert cols["revision_status"].default.arg == "active"
    assert cols["sync_state"].default.arg == "synced"
    assert cols["version_no"].default.arg == 1
    index_names = {i.name for i in DocumentMetadataModel.__table__.indexes}
    assert {"idx_dm_kb_hash", "idx_dm_lineage", "idx_dm_kb_status"} <= index_names
