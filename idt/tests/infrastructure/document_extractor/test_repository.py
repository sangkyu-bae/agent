"""DocumentTemplateRepository 단위 테스트 — AsyncMock 세션 (기존 repo 테스트 관례)."""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.document_extractor.schemas import DocumentTemplate, TemplateSlot
from src.infrastructure.document_extractor.document_template_repository import (
    DocumentTemplateRepository,
)
from src.infrastructure.document_extractor.models import DocumentTemplateModel


def _template(**kwargs) -> DocumentTemplate:
    now = datetime.now(timezone.utc)
    base = dict(
        id=str(uuid.uuid4()),
        agent_id="agent-1",
        worker_id="document_extractor_worker",
        name="여신심의서",
        html_skeleton="<p>{{loan_amount}}</p>",
        slots=[TemplateSlot(key="loan_amount", label="여신금액", slot_type="value")],
        source_file_ref="uploads/document_templates/t1.pdf",
        source_format="pdf",
        status="active",
        created_at=now,
        updated_at=now,
    )
    base.update(kwargs)
    return DocumentTemplate(**base)


def _repo() -> tuple[DocumentTemplateRepository, MagicMock]:
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock()
    return DocumentTemplateRepository(session=session, logger=MagicMock()), session


class TestSave:
    @pytest.mark.asyncio
    async def test_save_adds_and_flushes(self):
        repo, session = _repo()
        template = _template()
        result = await repo.save(template, "req")
        session.add.assert_called_once()
        session.flush.assert_awaited_once()
        assert result.id == template.id

    @pytest.mark.asyncio
    async def test_save_serializes_slots_to_json(self):
        repo, session = _repo()
        await repo.save(_template(), "req")
        row: DocumentTemplateModel = session.add.call_args.args[0]
        assert row.slots == [
            {
                "key": "loan_amount", "label": "여신금액", "slot_type": "value",
                "description": "", "fill_hint": "", "sample_value": "",
            }
        ]


class TestFind:
    @pytest.mark.asyncio
    async def test_find_by_id_maps_to_domain(self):
        repo, session = _repo()
        row = DocumentTemplateModel(
            id="t-1", agent_id="agent-1", worker_id="document_extractor_worker",
            name="여신심의서", html_skeleton="<p>{{loan_amount}}</p>",
            slots=[{"key": "loan_amount", "label": "여신금액", "slot_type": "value"}],
            source_file_ref="ref", source_format="pdf", status="active",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        result_proxy = MagicMock()
        result_proxy.scalar_one_or_none.return_value = row
        session.execute.return_value = result_proxy

        found = await repo.find_by_id("t-1", "req")
        assert found.name == "여신심의서"
        assert found.slots[0].key == "loan_amount"
        assert found.slots[0].description == ""  # 누락 필드 graceful

    @pytest.mark.asyncio
    async def test_find_by_id_none(self):
        repo, session = _repo()
        result_proxy = MagicMock()
        result_proxy.scalar_one_or_none.return_value = None
        session.execute.return_value = result_proxy
        assert await repo.find_by_id("nope", "req") is None


class TestSoftDelete:
    @pytest.mark.asyncio
    async def test_soft_delete_executes_update(self):
        repo, session = _repo()
        await repo.soft_delete("t-1", "req")
        session.execute.assert_awaited_once()
        stmt = session.execute.call_args.args[0]
        assert "document_template" in str(stmt).lower()

    @pytest.mark.asyncio
    async def test_soft_delete_by_agent_returns_rowcount(self):
        repo, session = _repo()
        result_proxy = MagicMock()
        result_proxy.rowcount = 2
        session.execute.return_value = result_proxy
        assert await repo.soft_delete_by_agent("agent-1", "req") == 2
