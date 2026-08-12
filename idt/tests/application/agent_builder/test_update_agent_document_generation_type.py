"""Update/Delete 경로의 document_generation_type 정합 테스트 (doc-generator §4-3)."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_builder.delete_agent_use_case import DeleteAgentUseCase
from src.application.agent_builder.schemas import (
    DocumentGenerationTypeRequest,
    DocumentSectionRequest,
    UpdateAgentRequest,
)
from src.application.agent_builder.update_agent_use_case import UpdateAgentUseCase
from src.domain.agent_builder.schemas import AgentDefinition, WorkerDefinition
from src.domain.document_generator.schemas import (
    DocumentGenerationType,
    DocumentSection,
)


def _agent(workers=None) -> AgentDefinition:
    now = datetime.now(timezone.utc)
    return AgentDefinition(
        id="agent-1",
        user_id="7",
        name="보고서봇",
        description="설명",
        system_prompt="프롬프트",
        flow_hint="힌트",
        workers=workers if workers is not None else [
            WorkerDefinition(
                tool_id="document_generator",
                worker_id="document_generator_worker",
                description="문서생성기",
                sort_order=0,
                tool_config={
                    "type_id": "old-type",
                    "mcp_html_to_doc_tool_id": "mcp_h2d",
                    "output_format": "docx",
                },
            )
        ],
        llm_model_id="model-1",
        status="active",
        created_at=now,
        updated_at=now,
    )


def _old_type() -> DocumentGenerationType:
    now = datetime.now(timezone.utc)
    return DocumentGenerationType(
        id="old-type", agent_id="agent-1",
        worker_id="document_generator_worker", name="구유형",
        description="", sections=[DocumentSection(title="개요")],
        output_format="docx", status="active",
        created_at=now, updated_at=now,
    )


def _type_request() -> DocumentGenerationTypeRequest:
    return DocumentGenerationTypeRequest(
        name="신유형",
        sections=[DocumentSectionRequest(title="요약"), DocumentSectionRequest(title="본문")],
        output_format="pdf",
        mcp_html_to_doc_tool_id="mcp_h2d",
    )


def _update_use_case(agent):
    repository = MagicMock()
    repository.find_by_id = AsyncMock(return_value=agent)
    repository.update = AsyncMock(side_effect=lambda a, rid: a)

    type_repo = MagicMock()
    type_repo.find_active_by_agent_worker = AsyncMock(return_value=_old_type())
    type_repo.save = AsyncMock(side_effect=lambda t, rid: t)
    type_repo.soft_delete = AsyncMock()

    use_case = UpdateAgentUseCase(
        repository=repository,
        perm_repo=MagicMock(),
        logger=MagicMock(),
        document_generation_type_repo=type_repo,
    )
    return use_case, repository, type_repo


class TestUpdateWithDocumentGenerationType:
    @pytest.mark.asyncio
    async def test_replace_soft_deletes_old_and_saves_new(self):
        agent = _agent()
        use_case, repository, type_repo = _update_use_case(agent)
        await use_case.execute(
            "agent-1",
            UpdateAgentRequest(document_generation_type=_type_request()),
            "req",
        )
        type_repo.soft_delete.assert_awaited_once_with("old-type", "req")
        type_repo.save.assert_awaited_once()
        new_type = type_repo.save.call_args.args[0]
        assert new_type.id != "old-type"
        assert new_type.output_format == "pdf"
        # worker tool_config 갱신 + repository.update로 영속
        worker = agent.workers[0]
        assert worker.tool_config["type_id"] == new_type.id
        assert worker.tool_config["output_format"] == "pdf"
        repository.update.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_none_means_no_change(self):
        use_case, _, type_repo = _update_use_case(_agent())
        await use_case.execute("agent-1", UpdateAgentRequest(name="새이름"), "req")
        type_repo.save.assert_not_awaited()
        type_repo.soft_delete.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_generator_worker_rejected(self):
        agent = _agent(workers=[
            WorkerDefinition(
                tool_id="excel_export", worker_id="excel_export_worker",
                description="엑셀", sort_order=0,
            )
        ])
        use_case, _, _ = _update_use_case(agent)
        with pytest.raises(ValueError, match="document_generator"):
            await use_case.execute(
                "agent-1",
                UpdateAgentRequest(document_generation_type=_type_request()),
                "req",
            )

    @pytest.mark.asyncio
    async def test_no_existing_active_type_skips_soft_delete(self):
        agent = _agent()
        use_case, _, type_repo = _update_use_case(agent)
        type_repo.find_active_by_agent_worker = AsyncMock(return_value=None)
        await use_case.execute(
            "agent-1",
            UpdateAgentRequest(document_generation_type=_type_request()),
            "req",
        )
        type_repo.soft_delete.assert_not_awaited()
        type_repo.save.assert_awaited_once()


class TestDeleteCascadesGenerationTypes:
    @pytest.mark.asyncio
    async def test_delete_soft_deletes_generation_types(self):
        repository = MagicMock()
        repository.find_by_id = AsyncMock(return_value=_agent())
        repository.soft_delete = AsyncMock()
        type_repo = MagicMock()
        type_repo.soft_delete_by_agent = AsyncMock(return_value=1)

        use_case = DeleteAgentUseCase(
            repository=repository,
            logger=MagicMock(),
            document_generation_type_repo=type_repo,
        )
        await use_case.execute("agent-1", "7", "user", "req")
        type_repo.soft_delete_by_agent.assert_awaited_once_with("agent-1", "req")
