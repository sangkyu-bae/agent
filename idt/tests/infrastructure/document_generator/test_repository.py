"""DocumentGenerationTypeRepository 단위 테스트 — AsyncMock 세션 (repo 테스트 관례)."""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.document_generator.schemas import (
    DocumentGenerationType,
    DocumentSection,
)
from src.infrastructure.document_generator.generation_type_repository import (
    DocumentGenerationTypeRepository,
)
from src.infrastructure.document_generator.models import DocumentGenerationTypeModel


def _gen_type(**kwargs) -> DocumentGenerationType:
    now = datetime.now(timezone.utc)
    base = dict(
        id=str(uuid.uuid4()),
        agent_id="agent-1",
        worker_id="document_generator_worker",
        name="시장조사 보고서",
        description="시장 동향 조사",
        sections=[
            DocumentSection(title="개요"),
            DocumentSection(title="시장 현황", guidance="웹서치 근거 위주"),
        ],
        output_format="docx",
        status="active",
        created_at=now,
        updated_at=now,
    )
    base.update(kwargs)
    return DocumentGenerationType(**base)


def _repo() -> tuple[DocumentGenerationTypeRepository, MagicMock]:
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock()
    return (
        DocumentGenerationTypeRepository(session=session, logger=MagicMock()),
        session,
    )


class TestSave:
    @pytest.mark.asyncio
    async def test_save_adds_and_flushes(self):
        repo, session = _repo()
        gen_type = _gen_type()
        result = await repo.save(gen_type, "req")
        session.add.assert_called_once()
        session.flush.assert_awaited_once()
        assert result.id == gen_type.id

    @pytest.mark.asyncio
    async def test_save_serializes_sections_to_json(self):
        repo, session = _repo()
        await repo.save(_gen_type(), "req")
        row: DocumentGenerationTypeModel = session.add.call_args.args[0]
        assert row.sections == [
            {"title": "개요", "guidance": ""},
            {"title": "시장 현황", "guidance": "웹서치 근거 위주"},
        ]


class TestFind:
    @pytest.mark.asyncio
    async def test_find_by_id_maps_to_domain(self):
        repo, session = _repo()
        row = DocumentGenerationTypeModel(
            id="t-1", agent_id="agent-1", worker_id="document_generator_worker",
            name="시장조사 보고서", description="",
            sections=[{"title": "개요", "guidance": ""}],
            output_format="docx", status="active",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        result_proxy = MagicMock()
        result_proxy.scalar_one_or_none.return_value = row
        session.execute.return_value = result_proxy

        found = await repo.find_by_id("t-1", "req")
        assert found is not None
        assert found.sections == [DocumentSection(title="개요", guidance="")]
        assert found.output_format == "docx"

    @pytest.mark.asyncio
    async def test_find_by_id_none(self):
        repo, session = _repo()
        result_proxy = MagicMock()
        result_proxy.scalar_one_or_none.return_value = None
        session.execute.return_value = result_proxy
        assert await repo.find_by_id("none", "req") is None


class TestSoftDelete:
    @pytest.mark.asyncio
    async def test_soft_delete_executes_update(self):
        repo, session = _repo()
        session.execute.return_value = MagicMock()
        await repo.soft_delete("t-1", "req")
        session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_soft_delete_by_agent_returns_rowcount(self):
        repo, session = _repo()
        result_proxy = MagicMock()
        result_proxy.rowcount = 2
        session.execute.return_value = result_proxy
        assert await repo.soft_delete_by_agent("agent-1", "req") == 2
