"""SectionSummaryJobRepository.delete_by_document — kb-document-management FR-06.

실제 SQL로 대상 행만 지워지는지 확인한다.
"""
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from unittest.mock import MagicMock

from src.domain.section_summary.entities import SectionSummaryJob
from src.infrastructure.persistence.models.base import Base
from src.infrastructure.persistence.models.section_summary_job import (
    SectionSummaryJobModel,
)
from src.infrastructure.section_summary.job_repository import (
    SectionSummaryJobRepository,
)


def _job(job_id: str, document_id: str) -> SectionSummaryJob:
    return SectionSummaryJob(
        id=job_id,
        document_id=document_id,
        kb_id="kb-1",
        collection_name="col",
        chunking_profile_id="p-1",
        llm_model_id="m-1",
        embedding_provider="openai",
        embedding_model="e-1",
        status="completed",
    )


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[SectionSummaryJobModel.__table__],
        )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db_session:
        yield db_session
    await engine.dispose()


@pytest.mark.asyncio
async def test_deletes_only_target_document(session):
    repo = SectionSummaryJobRepository(session, MagicMock())
    await repo.save(_job("job-1", "doc-1"), "req-1")
    await repo.save(_job("job-2", "doc-2"), "req-1")

    deleted = await repo.delete_by_document("doc-1", "req-1")

    assert deleted == 1
    rows = (await session.execute(select(SectionSummaryJobModel))).scalars().all()
    assert [row.document_id for row in rows] == ["doc-2"]


@pytest.mark.asyncio
async def test_missing_document_is_noop(session):
    repo = SectionSummaryJobRepository(session, MagicMock())

    assert await repo.delete_by_document("doc-x", "req-1") == 0
