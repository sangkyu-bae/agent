"""CreateAgentUseCase — document_template 동봉 생성 테스트 (Design §3-4)."""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_builder.create_agent_use_case import CreateAgentUseCase
from src.application.agent_builder.schemas import (
    CreateAgentRequest,
    DocumentTemplateRequest,
)
from src.application.document_extractor.schemas import TemplateSlotDto
from src.domain.document_extractor.exceptions import TemplateTokenMismatchError
from src.domain.llm_model.entity import LlmModel


def _default_model() -> LlmModel:
    now = datetime.now(timezone.utc)
    return LlmModel(
        id="model-default", provider="openai", model_name="gpt-4o",
        display_name="GPT-4o", description=None, api_key_env="OPENAI_API_KEY",
        max_tokens=None, is_active=True, is_default=True,
        created_at=now, updated_at=now,
    )


def _template_request(**kwargs) -> DocumentTemplateRequest:
    base = dict(
        name="여신심의서",
        html_skeleton="<p>금액: {{loan_amount}}</p>",
        slots=[TemplateSlotDto(key="loan_amount", label="여신금액", slot_type="value")],
        source_file_id="f" * 32,
        source_format="pdf",
        mcp_pdf_to_html_tool_id="mcp_p2h",
        mcp_html_to_doc_tool_id="mcp_h2d",
    )
    base.update(kwargs)
    return DocumentTemplateRequest(**base)


def _make_use_case():
    repository = MagicMock()
    repository.save = AsyncMock(side_effect=lambda agent, rid: agent)

    llm_repo = MagicMock()
    llm_repo.find_default = AsyncMock(return_value=_default_model())

    template_repo = MagicMock()
    template_repo.save = AsyncMock(side_effect=lambda t, rid: t)

    archiver = MagicMock()
    archiver.promote = MagicMock(
        return_value="uploads/document_templates/tpl.pdf"
    )

    use_case = CreateAgentUseCase(
        repository=repository,
        llm_model_repository=llm_repo,
        perm_repo=MagicMock(
            find_by_collection_name=AsyncMock(return_value=None)
        ),
        logger=MagicMock(),
        document_template_repo=template_repo,
        source_archiver=archiver,
    )
    return use_case, repository, template_repo, archiver


def _request(tool_ids=None, document_template=None) -> CreateAgentRequest:
    return CreateAgentRequest(
        user_request="여신심의서 자동 작성 에이전트",
        name="심의서봇",
        user_id="7",
        system_prompt="여신심의서 지침",
        tool_ids=tool_ids or ["document_extractor"],
        document_template=document_template,
    )


class TestCreateWithDocumentTemplate:
    @pytest.mark.asyncio
    async def test_template_saved_and_tool_config_linked(self):
        use_case, _, template_repo, archiver = _make_use_case()
        response = await use_case.execute(_request(
            document_template=_template_request()
        ), "req")

        template_repo.save.assert_awaited_once()
        saved_template = template_repo.save.call_args.args[0]
        assert saved_template.agent_id == response.agent_id
        assert saved_template.worker_id == "document_extractor_worker"
        assert saved_template.status == "active"
        assert saved_template.source_file_ref == "uploads/document_templates/tpl.pdf"

        # 원본 승격 (D3)
        archiver.promote.assert_called_once()
        assert archiver.promote.call_args.args[0] == "f" * 32

        # worker tool_config 연결 (같은 template_id)
        worker = next(
            w for w in response.workers if w.tool_id == "document_extractor"
        )
        assert worker.tool_config["template_id"] == saved_template.id
        assert worker.tool_config["mcp_html_to_doc_tool_id"] == "mcp_h2d"
        assert worker.tool_config["output_format"] == "pdf"

    @pytest.mark.asyncio
    async def test_no_extractor_worker_rejected(self):
        use_case, _, _, _ = _make_use_case()
        with pytest.raises(ValueError, match="document_extractor"):
            await use_case.execute(_request(
                tool_ids=["excel_export"],
                document_template=_template_request(),
            ), "req")

    @pytest.mark.asyncio
    async def test_token_mismatch_rejected(self):
        use_case, _, template_repo, _ = _make_use_case()
        bad = _template_request(html_skeleton="<p>토큰 없음</p>")
        with pytest.raises(TemplateTokenMismatchError):
            await use_case.execute(_request(document_template=bad), "req")
        template_repo.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_creation_without_template_still_allowed(self):
        use_case, _, template_repo, archiver = _make_use_case()
        response = await use_case.execute(_request(), "req")
        template_repo.save.assert_not_awaited()
        archiver.promote.assert_not_called()
        assert response.tool_ids == ["document_extractor"]

    @pytest.mark.asyncio
    async def test_expired_source_file_propagates(self):
        use_case, _, _, archiver = _make_use_case()
        archiver.promote.side_effect = ValueError("원본을 찾을 수 없습니다")
        with pytest.raises(ValueError, match="원본"):
            await use_case.execute(_request(
                document_template=_template_request()
            ), "req")
