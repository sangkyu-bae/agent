"""DocumentRevisionRepository · RevisionCheckLogRepository — SQLite 실세션 (Design §3.3)."""
from __future__ import annotations

import os
import tempfile
from datetime import date, datetime
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.domain.document_revision.value_objects import (
    CheckDecision,
    CheckSource,
    LlmStatus,
    LlmVerdict,
    RevisionCandidate,
    RevisionCheckLogEntry,
    RevisionStatus,
    SyncState,
)
from src.infrastructure.doc_browse.models import DocumentMetadataModel
from src.infrastructure.document_revision.check_log_repository import (
    RevisionCheckLogRepository,
)
from src.infrastructure.document_revision.models import DocumentRevisionCheckModel
from src.infrastructure.document_revision.revision_repository import (
    DocumentRevisionRepository,
)
from src.infrastructure.persistence.models.base import Base


@pytest.fixture
async def session():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp.name}", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[DocumentMetadataModel.__table__, DocumentRevisionCheckModel.__table__],
        )
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with factory() as s:
            yield s
    finally:
        await engine.dispose()
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


_ids = iter(range(1, 10_000))


def _row(doc_id, *, kb="kb-1", lineage=None, version=1, status="active",
         sync="synced", file_hash=None, filename=None) -> DocumentMetadataModel:
    # SQLite 는 BigInteger PK 자동 증가가 없어 테스트에서 직접 부여한다
    return DocumentMetadataModel(
        id=next(_ids), document_id=doc_id, collection_name="col", filename=filename or f"{doc_id}.pdf",
        category="c", user_id="7", chunk_count=1, chunk_strategy="x", kb_id=kb,
        lineage_id=lineage, version_no=version, revision_status=status,
        sync_state=sync, file_hash=file_hash,
    )


async def _seed(session, *rows) -> None:
    session.add_all(rows)
    await session.flush()


class TestRevisionRepositoryReads:
    async def test_find_version_maps_fields(self, session) -> None:
        await _seed(session, _row("d2", lineage="d1", version=2, file_hash="h"))
        v = await DocumentRevisionRepository(session, MagicMock()).find_version("d2", "r")
        assert (v.document_id, v.lineage_id, v.version_no) == ("d2", "d1", 2)
        assert v.revision_status is RevisionStatus.ACTIVE
        assert v.sync_state is SyncState.SYNCED
        assert v.effective_lineage_id == "d1"

    async def test_find_version_missing(self, session) -> None:
        repo = DocumentRevisionRepository(session, MagicMock())
        assert await repo.find_version("nope", "r") is None

    async def test_lineage_includes_root_and_members_ordered(self, session) -> None:
        await _seed(
            session,
            _row("d3", lineage="d1", version=3),
            _row("d1", version=1, status="superseded"),
            _row("d2", lineage="d1", version=2, status="superseded"),
            _row("other"),
        )
        repo = DocumentRevisionRepository(session, MagicMock())
        versions = await repo.find_lineage_versions("d1", "r")
        assert [v.document_id for v in versions] == ["d1", "d2", "d3"]

    async def test_active_by_kb_and_hash_and_pending(self, session) -> None:
        await _seed(
            session,
            _row("a", file_hash="h1"),
            _row("b", status="superseded", sync="pending", file_hash="h1"),
            _row("c", kb="kb-2", file_hash="h1"),
        )
        repo = DocumentRevisionRepository(session, MagicMock())
        assert [v.document_id for v in await repo.find_active_by_kb("kb-1", "r")] == ["a"]
        assert sorted(
            v.document_id for v in await repo.find_by_hash("kb-1", "h1", "r")
        ) == ["a", "b"]
        assert [v.document_id for v in await repo.find_pending_sync("kb-1", "r")] == ["b"]


class TestRevisionRepositoryWrites:
    async def test_set_status_and_sync(self, session) -> None:
        await _seed(session, _row("d1"))
        repo = DocumentRevisionRepository(session, MagicMock())
        at = datetime(2026, 11, 23, 10, 0)
        await repo.set_status(
            "d1", status=RevisionStatus.SUPERSEDED, sync_state=SyncState.PENDING,
            superseded_by="d2", superseded_at=at, revised_by="7", request_id="r",
        )
        v = await repo.find_version("d1", "r")
        assert v.revision_status is RevisionStatus.SUPERSEDED
        assert v.sync_state is SyncState.PENDING
        assert (v.superseded_by, v.superseded_at, v.revised_by) == ("d2", at, "7")

        await repo.set_sync_state("d1", SyncState.SYNCED, "r")
        assert (await repo.find_version("d1", "r")).sync_state is SyncState.SYNCED

    async def test_assign_lineage_and_detach(self, session) -> None:
        await _seed(session, _row("n1"))
        repo = DocumentRevisionRepository(session, MagicMock())
        await repo.assign_lineage("n1", lineage_id="o1", version_no=4, request_id="r")
        v = await repo.find_version("n1", "r")
        assert (v.lineage_id, v.version_no) == ("o1", 4)
        await repo.assign_lineage("n1", lineage_id=None, version_no=1, request_id="r")
        v = await repo.find_version("n1", "r")
        assert (v.lineage_id, v.version_no) == (None, 1)

    async def test_update_meta(self, session) -> None:
        await _seed(session, _row("d1"))
        repo = DocumentRevisionRepository(session, MagicMock())
        await repo.update_meta(
            "d1", version_label="2026-11 개정", effective_date=date(2026, 12, 1),
            request_id="r",
        )
        v = await repo.find_version("d1", "r")
        assert (v.version_label, v.effective_date) == ("2026-11 개정", date(2026, 12, 1))


class TestCheckLogRepository:
    async def test_save_and_record_decision(self, session) -> None:
        repo = RevisionCheckLogRepository(session, MagicMock())
        cand = RevisionCandidate(
            document_id="o1", filename="o1.pdf", version_no=1, version_label=None,
            filename_score=1.0, content_score=0.9, combined_score=0.94,
            llm_verdict=LlmVerdict.SAME, llm_reason="같은 규정",
        )
        await repo.save(
            RevisionCheckLogEntry(
                check_id="c1", kb_id="kb-1", user_id="7", source=CheckSource.PRECHECK,
                filename="new.pdf", normalized_name="new", file_hash="h",
                verdict="revision_candidate", suggested_document_id="o1",
                candidates=[cand], llm_status=LlmStatus.OK, elapsed_ms=120, parse_ms=80,
            ),
            "r",
        )
        await repo.record_decision(
            "c1", decision=CheckDecision.REVISION, target_document_id="o1",
            decided_document_id="n1", decided_by="7", request_id="r",
        )
        row = (
            await session.execute(
                select(DocumentRevisionCheckModel).where(DocumentRevisionCheckModel.id == "c1")
            )
        ).scalar_one()
        assert row.decision == "revision"
        assert (row.target_document_id, row.decided_document_id) == ("o1", "n1")
        assert row.decided_at is not None
        assert row.candidates_json[0]["document_id"] == "o1"
        assert row.candidates_json[0]["llm_verdict"] == "same_document_revision"
        assert row.llm_status == "ok" and row.parse_ms == 80

    async def test_record_decision_unknown_check_is_noop(self, session) -> None:
        repo = RevisionCheckLogRepository(session, MagicMock())
        await repo.record_decision(
            "missing", decision=CheckDecision.NEW, target_document_id=None,
            decided_document_id="n1", decided_by="7", request_id="r",
        )


class TestMetadataRepositoryRevisionReads:
    """DocumentMetadataRepository 개정 관련 조회 (Design §4.2 #3, module-6 라벨)."""

    async def test_find_by_kb_id_active_only(self, session) -> None:
        from src.infrastructure.doc_browse.document_metadata_repository import (
            DocumentMetadataRepository,
        )

        await _seed(
            session,
            _row("v1", status="superseded"),
            _row("v2", lineage="v1", version=2),
            _row("solo"),
        )
        repo = DocumentMetadataRepository(session, MagicMock())
        page = await repo.find_by_kb_id("kb-1", "r", active_only=True)
        assert page.total == 2
        by_id = {i.document_id: i for i in page.items}
        assert set(by_id) == {"v2", "solo"}
        assert (by_id["v2"].version_no, by_id["v2"].lineage_id) == (2, "v1")
        assert by_id["v2"].revision_status == "active"
        everything = await repo.find_by_kb_id("kb-1", "r")
        assert everything.total == 3  # 기본값은 기존 동작(전체)

    async def test_find_version_labels(self, session) -> None:
        from src.infrastructure.doc_browse.document_metadata_repository import (
            DocumentMetadataRepository,
        )

        labeled = _row("v3", lineage="v1", version=3)
        labeled.version_label = "2026-11 개정"
        await _seed(session, _row("v1"), _row("v2", lineage="v1", version=2), labeled)
        repo = DocumentMetadataRepository(session, MagicMock())
        labels = await repo.find_version_labels(["v1", "v2", "v3", "none"], "r")
        assert labels == {"v2": "v2", "v3": "v3 (2026-11 개정)"}
        assert await repo.find_version_labels([], "r") == {}
