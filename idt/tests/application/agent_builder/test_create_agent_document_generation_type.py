"""CreateAgentUseCase — document_generation_type 동봉 생성 테스트 (doc-generator §4-3)."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_builder.create_agent_use_case import CreateAgentUseCase
from src.application.agent_builder.schemas import (
    CreateAgentRequest,
    DocumentGenerationTypeRequest,
    DocumentSectionRequest,
)
from src.domain.document_generator.exceptions import InvalidGenerationTypeError
from src.domain.llm_model.entity import LlmModel


def _default_model() -> LlmModel:
    now = datetime.now(timezone.utc)
    return LlmModel(
        id="model-default", provider="openai", model_name="gpt-4o",
        display_name="GPT-4o", description=None, api_key_env="OPENAI_API_KEY",
        max_tokens=None, is_active=True, is_default=True,
        created_at=now, updated_at=now,
    )


def _type_request(**kwargs) -> DocumentGenerationTypeRequest:
    base = dict(
        name="시장조사 보고서",
        description="시장 동향 조사",
        sections=[
            DocumentSectionRequest(title="개요"),
            DocumentSectionRequest(title="시장 현황"),
        ],
        output_format="docx",
        mcp_html_to_doc_tool_id="mcp_h2d",
    )
    base.update(kwargs)
    return DocumentGenerationTypeRequest(**base)


def _make_use_case():
    repository = MagicMock()
    repository.save = AsyncMock(side_effect=lambda agent, rid: agent)

    llm_repo = MagicMock()
    llm_repo.find_default = AsyncMock(return_value=_default_model())

    type_repo = MagicMock()
    type_repo.save = AsyncMock(side_effect=lambda t, rid: t)

    use_case = CreateAgentUseCase(
        repository=repository,
        llm_model_repository=llm_repo,
        perm_repo=MagicMock(find_by_collection_name=AsyncMock(return_value=None)),
        logger=MagicMock(),
        document_generation_type_repo=type_repo,
    )
    return use_case, repository, type_repo


def _request(tool_ids=None, document_generation_type=None) -> CreateAgentRequest:
    return CreateAgentRequest(
        user_request="시장조사 보고서 작성 에이전트",
        name="보고서봇",
        user_id="7",
        system_prompt="보고서 지침",
        tool_ids=tool_ids or ["document_generator"],
        document_generation_type=document_generation_type,
    )


class TestCreateWithDocumentGenerationType:
    @pytest.mark.asyncio
    async def test_type_saved_and_tool_config_linked(self):
        use_case, _, type_repo = _make_use_case()
        response = await use_case.execute(
            _request(document_generation_type=_type_request()), "req"
        )

        type_repo.save.assert_awaited_once()
        saved = type_repo.save.call_args.args[0]
        assert saved.agent_id == response.agent_id
        assert saved.worker_id == "document_generator_worker"
        assert saved.status == "active"
        assert [s.title for s in saved.sections] == ["개요", "시장 현황"]

        worker = next(
            w for w in response.workers if w.tool_id == "document_generator"
        )
        assert worker.tool_config["type_id"] == saved.id
        assert worker.tool_config["mcp_html_to_doc_tool_id"] == "mcp_h2d"
        assert worker.tool_config["output_format"] == "docx"

    @pytest.mark.asyncio
    async def test_no_generator_worker_rejected(self):
        use_case, _, type_repo = _make_use_case()
        with pytest.raises(ValueError, match="document_generator"):
            await use_case.execute(_request(
                tool_ids=["excel_export"],
                document_generation_type=_type_request(),
            ), "req")
        type_repo.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_invalid_sections_rejected_before_agent_save(self):
        use_case, repository, type_repo = _make_use_case()
        with pytest.raises(InvalidGenerationTypeError):
            await use_case.execute(_request(
                document_generation_type=_type_request(sections=[]),
            ), "req")
        repository.save.assert_not_awaited()
        type_repo.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_missing_wiring_rejected(self):
        use_case, _, _ = _make_use_case()
        use_case._document_generation_type_repo = None
        with pytest.raises(ValueError, match="문서 유형"):
            await use_case.execute(
                _request(document_generation_type=_type_request()), "req"
            )

    @pytest.mark.asyncio
    async def test_without_type_request_no_side_effect(self):
        """유형 미동봉 생성은 기존 경로 그대로 (무회귀)."""
        use_case, _, type_repo = _make_use_case()
        response = await use_case.execute(_request(), "req")
        type_repo.save.assert_not_awaited()
        worker = next(
            w for w in response.workers if w.tool_id == "document_generator"
        )
        assert not worker.tool_config
