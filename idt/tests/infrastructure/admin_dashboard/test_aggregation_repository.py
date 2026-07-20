"""SqlAlchemyDashboardAggregationRepository 테스트 — SQLite in-memory 실쿼리 검증.

document_metadata / knowledge_base / users 를 실제 생성해 집계 정확성을 확인한다
(Design §5.1 — 빈 DB 0, scope/status 분리, without_kb, LEFT JOIN 0건 KB 포함).
"""
from datetime import datetime
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.infrastructure.admin_dashboard.aggregation_repository import (
    SqlAlchemyDashboardAggregationRepository,
)
from src.infrastructure.auth.models import UserModel
from src.infrastructure.department.models import DepartmentModel
from src.infrastructure.doc_browse.models import DocumentMetadataModel
from src.infrastructure.persistence.models.chunking_profile import (
    ChunkingProfileModel,
)
from src.infrastructure.persistence.models.knowledge_base import KnowledgeBaseModel


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        # knowledge_base FK 참조 대상(users/departments/chunking_profile) 선행 생성
        for table in (
            UserModel.__table__,
            DepartmentModel.__table__,
            ChunkingProfileModel.__table__,
            KnowledgeBaseModel.__table__,
            DocumentMetadataModel.__table__,
        ):
            await conn.run_sync(table.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


def _repo(session) -> SqlAlchemyDashboardAggregationRepository:
    return SqlAlchemyDashboardAggregationRepository(
        session=session, logger=MagicMock()
    )


def _kb(kb_id: str, name: str, scope: str = "PERSONAL", status: str = "active"):
    return KnowledgeBaseModel(
        id=kb_id, name=name, owner_id=1, scope=scope,
        collection_name="col", status=status,
    )


_doc_seq = iter(range(1, 1000))


def _doc(document_id: str, kb_id: str | None, chunk_count: int, created: datetime):
    # SQLite는 BIGINT PK autoincrement 미지원 — id 명시
    return DocumentMetadataModel(
        id=next(_doc_seq),
        document_id=document_id, collection_name="col", filename=f"{document_id}.pdf",
        chunk_count=chunk_count, chunk_strategy="parent_child", kb_id=kb_id,
        created_at=created, updated_at=created,
    )


def _user(email: str, role: str = "user", status: str = "approved"):
    return UserModel(email=email, password_hash="h", role=role, status=status)


class TestGetStats:
    @pytest.mark.asyncio
    async def test_empty_db_returns_zeros(self, session):
        stats = await _repo(session).get_stats()
        assert stats.kb.total == 0
        assert stats.documents.total == 0
        assert stats.chunks.total == 0
        assert stats.users.total == 0

    @pytest.mark.asyncio
    async def test_aggregates_by_scope_status_and_kb_membership(self, session):
        session.add_all([
            _kb("kb-1", "A", scope="PERSONAL", status="active"),
            _kb("kb-2", "B", scope="PUBLIC", status="active"),
            _kb("kb-3", "C", scope="PUBLIC", status="archived"),
        ])
        session.add_all([
            _doc("d1", "kb-1", 10, datetime(2026, 7, 1)),
            _doc("d2", "kb-1", 20, datetime(2026, 7, 2)),
            _doc("d3", None, 5, datetime(2026, 7, 3)),
        ])
        session.add_all([
            _user("a@x.com", role="admin", status="approved"),
            _user("b@x.com", role="user", status="approved"),
            _user("c@x.com", role="user", status="pending"),
        ])
        await session.flush()

        stats = await _repo(session).get_stats()

        assert stats.kb.total == 3
        assert stats.kb.active == 2
        assert stats.kb.by_scope == {"PERSONAL": 1, "PUBLIC": 2}
        assert stats.documents.total == 3
        assert stats.documents.with_kb == 2
        assert stats.documents.without_kb == 1
        assert stats.chunks.total == 35
        assert stats.users.total == 3
        assert stats.users.approved == 2
        assert stats.users.pending == 1
        assert stats.users.admins == 1


class TestGetKbBreakdown:
    @pytest.mark.asyncio
    async def test_includes_kb_without_documents(self, session):
        session.add_all([
            _kb("kb-1", "문서있음"),
            _kb("kb-2", "빈KB"),
        ])
        session.add_all([
            _doc("d1", "kb-1", 10, datetime(2026, 7, 1, 9, 0)),
            _doc("d2", "kb-1", 20, datetime(2026, 7, 2, 9, 0)),
            _doc("d3", None, 5, datetime(2026, 7, 3)),  # 일반 업로드 — 제외
        ])
        await session.flush()

        rows = await _repo(session).get_kb_breakdown()

        assert len(rows) == 2
        by_id = {r.kb_id: r for r in rows}
        assert by_id["kb-1"].document_count == 2
        assert by_id["kb-1"].chunk_count == 30
        assert by_id["kb-1"].last_uploaded_at == datetime(2026, 7, 2, 9, 0)
        assert by_id["kb-2"].document_count == 0
        assert by_id["kb-2"].chunk_count == 0
        assert by_id["kb-2"].last_uploaded_at is None
        # 정렬: 문서 수 내림차순
        assert rows[0].kb_id == "kb-1"


class TestGetRecentDocuments:
    @pytest.mark.asyncio
    async def test_orders_desc_and_limits_with_kb_name(self, session):
        session.add(_kb("kb-1", "규정집"))
        session.add_all([
            _doc("d1", "kb-1", 1, datetime(2026, 7, 1)),
            _doc("d2", None, 2, datetime(2026, 7, 2)),
            _doc("d3", "kb-1", 3, datetime(2026, 7, 3)),
        ])
        await session.flush()

        rows = await _repo(session).get_recent_documents(limit=2)

        assert [r.document_id for r in rows] == ["d3", "d2"]
        assert rows[0].kb_name == "규정집"
        assert rows[1].kb_id is None
        assert rows[1].kb_name is None
