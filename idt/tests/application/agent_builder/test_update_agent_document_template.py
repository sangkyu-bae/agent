"""Update/Delete 경로의 document_template 정합 테스트 (Design §3-4, D4)."""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_builder.delete_agent_use_case import DeleteAgentUseCase
from src.application.agent_builder.schemas import (
    DocumentTemplateRequest,
    UpdateAgentRequest,
)
from src.application.agent_builder.update_agent_use_case import UpdateAgentUseCase
from src.application.document_extractor.schemas import TemplateSlotDto
from src.domain.agent_builder.schemas import AgentDefinition, WorkerDefinition
from src.domain.document_extractor.schemas import DocumentTemplate, TemplateSlot


def _agent(workers=None) -> AgentDefinition:
    now = datetime.now(timezone.utc)
    return AgentDefinition(
        id="agent-1",
        user_id="7",
        name="심의서봇",
        description="설명",
        system_prompt="프롬프트",
        flow_hint="힌트",
        workers=workers if workers is not None else [
            WorkerDefinition(
                tool_id="document_extractor",
                worker_id="document_extractor_worker",
                description="문서추출기",
                sort_order=0,
                tool_config={
                    "template_id": "old-template",
                    "mcp_pdf_to_html_tool_id": "mcp_p2h",
                    "mcp_html_to_doc_tool_id": "mcp_h2d",
                    "output_format": "pdf",
                },
            )
        ],
        llm_model_id="model-1",
        status="active",
        created_at=now,
        updated_at=now,
    )


def _old_template() -> DocumentTemplate:
    now = datetime.now(timezone.utc)
    return DocumentTemplate(
        id="old-template", agent_id="agent-1",
        worker_id="document_extractor_worker", name="구양식",
        html_skeleton="<p>{{old}}</p>",
        slots=[TemplateSlot(key="old", label="구", slot_type="value")],
        source_file_ref="ref", source_format="pdf", status="active",
        created_at=now, updated_at=now,
    )


def _template_request() -> DocumentTemplateRequest:
    return DocumentTemplateRequest(
        name="신양식",
        html_skeleton="<p>{{new_key}}</p>",
        slots=[TemplateSlotDto(key="new_key", label="신규", slot_type="value")],
        source_file_id="f" * 32,
        source_format="docx",
        mcp_pdf_to_html_tool_id="mcp_p2h",
        mcp_html_to_doc_tool_id="mcp_h2d",
    )


def _update_use_case(agent):
    repository = MagicMock()
    repository.find_by_id = AsyncMock(return_value=agent)
    repository.update = AsyncMock(side_effect=lambda a, rid: a)

    template_repo = MagicMock()
    template_repo.find_active_by_agent_worker = AsyncMock(
        return_value=_old_template()
    )
    template_repo.save = AsyncMock(side_effect=lambda t, rid: t)
    template_repo.soft_delete = AsyncMock()

    archiver = MagicMock()
    archiver.promote = MagicMock(return_value="uploads/document_templates/new.docx")

    use_case = UpdateAgentUseCase(
        repository=repository,
        perm_repo=MagicMock(),
        logger=MagicMock(),
        document_template_repo=template_repo,
        source_archiver=archiver,
    )
    return use_case, repository, template_repo, archiver


class TestUpdateWithDocumentTemplate:
    @pytest.mark.asyncio
    async def test_replace_soft_deletes_old_and_saves_new(self):
        agent = _agent()
        use_case, repository, template_repo, _ = _update_use_case(agent)
        await use_case.execute(
            "agent-1",
            UpdateAgentRequest(document_template=_template_request()),
            "req",
        )
        template_repo.soft_delete.assert_awaited_once_with("old-template", "req")
        template_repo.save.assert_awaited_once()
        new_template = template_repo.save.call_args.args[0]
        assert new_template.id != "old-template"
        assert new_template.source_format == "docx"
        # worker tool_config 갱신 + repository.update로 영속
        worker = agent.workers[0]
        assert worker.tool_config["template_id"] == new_template.id
        assert worker.tool_config["output_format"] == "docx"
        repository.update.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_none_means_no_change(self):
        use_case, _, template_repo, archiver = _update_use_case(_agent())
        await use_case.execute("agent-1", UpdateAgentRequest(name="새이름"), "req")
        template_repo.save.assert_not_awaited()
        template_repo.soft_delete.assert_not_awaited()
        archiver.promote.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_extractor_worker_rejected(self):
        agent = _agent(workers=[
            WorkerDefinition(
                tool_id="excel_export", worker_id="excel_export_worker",
                description="엑셀", sort_order=0,
            )
        ])
        use_case, _, _, _ = _update_use_case(agent)
        with pytest.raises(ValueError, match="document_extractor"):
            await use_case.execute(
                "agent-1",
                UpdateAgentRequest(document_template=_template_request()),
                "req",
            )


class TestDeleteCascadesTemplates:
    @pytest.mark.asyncio
    async def test_delete_soft_deletes_templates(self):
        repository = MagicMock()
        repository.find_by_id = AsyncMock(return_value=_agent())
        repository.soft_delete = AsyncMock()
        template_repo = MagicMock()
        template_repo.soft_delete_by_agent = AsyncMock(return_value=1)

        use_case = DeleteAgentUseCase(
            repository=repository,
            logger=MagicMock(),
            document_template_repo=template_repo,
        )
        await use_case.execute("agent-1", "7", "user", "req")
        template_repo.soft_delete_by_agent.assert_awaited_once_with(
            "agent-1", "req"
        )
