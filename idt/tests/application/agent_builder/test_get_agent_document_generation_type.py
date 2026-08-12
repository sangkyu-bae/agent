"""GetAgentUseCase — document_generation_type 프리필 스냅샷 테스트 (FR-12)."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_builder.get_agent_use_case import GetAgentUseCase
from src.domain.agent_builder.schemas import AgentDefinition, WorkerDefinition
from src.domain.document_generator.schemas import (
    DocumentGenerationType,
    DocumentSection,
)


def _agent(workers) -> AgentDefinition:
    now = datetime.now(timezone.utc)
    return AgentDefinition(
        id="agent-1", user_id="7", name="보고서봇", description="d",
        system_prompt="p", flow_hint="f", workers=workers,
        llm_model_id="model-1", status="active",
        created_at=now, updated_at=now,
    )


def _gen_worker() -> WorkerDefinition:
    return WorkerDefinition(
        tool_id="document_generator", worker_id="document_generator_worker",
        description="문서생성기", sort_order=0,
        tool_config={
            "type_id": "t-1",
            "mcp_html_to_doc_tool_id": "mcp_h2d",
            "output_format": "pdf",
        },
    )


def _gen_type() -> DocumentGenerationType:
    now = datetime.now(timezone.utc)
    return DocumentGenerationType(
        id="t-1", agent_id="agent-1",
        worker_id="document_generator_worker", name="시장조사 보고서",
        description="설명", sections=[DocumentSection(title="개요", guidance="g")],
        output_format="pdf", status="active",
        created_at=now, updated_at=now,
    )


def _use_case(agent, type_repo=None) -> GetAgentUseCase:
    repository = MagicMock()
    repository.find_by_id = AsyncMock(return_value=agent)
    return GetAgentUseCase(
        repository=repository,
        dept_repository=MagicMock(),
        logger=MagicMock(),
        document_generation_type_repo=type_repo,
    )


class TestGetAgentGenerationTypePrefill:
    @pytest.mark.asyncio
    async def test_active_type_included_in_response(self):
        type_repo = MagicMock()
        type_repo.find_active_by_agent_worker = AsyncMock(return_value=_gen_type())
        use_case = _use_case(_agent([_gen_worker()]), type_repo)

        response = await use_case.execute("agent-1", "req")

        info = response.document_generation_type
        assert info is not None
        assert info.name == "시장조사 보고서"
        assert info.sections[0].title == "개요"
        assert info.sections[0].guidance == "g"
        assert info.output_format == "pdf"
        assert info.mcp_html_to_doc_tool_id == "mcp_h2d"

    @pytest.mark.asyncio
    async def test_no_generator_worker_returns_none(self):
        type_repo = MagicMock()
        type_repo.find_active_by_agent_worker = AsyncMock()
        worker = WorkerDefinition(
            tool_id="excel_export", worker_id="excel_export_worker",
            description="엑셀", sort_order=0,
        )
        use_case = _use_case(_agent([worker]), type_repo)
        response = await use_case.execute("agent-1", "req")
        assert response.document_generation_type is None
        type_repo.find_active_by_agent_worker.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_active_type_returns_none(self):
        type_repo = MagicMock()
        type_repo.find_active_by_agent_worker = AsyncMock(return_value=None)
        use_case = _use_case(_agent([_gen_worker()]), type_repo)
        response = await use_case.execute("agent-1", "req")
        assert response.document_generation_type is None

    @pytest.mark.asyncio
    async def test_unwired_repo_keeps_legacy_behavior(self):
        use_case = _use_case(_agent([_gen_worker()]), type_repo=None)
        response = await use_case.execute("agent-1", "req")
        assert response.document_generation_type is None
