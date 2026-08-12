"""WorkflowCompiler — document_generator 전용 생성 노드 테스트 (doc-generator §4-4)."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.application.agent_builder.supervisor_hooks import DefaultHooks
from src.application.agent_builder.workflow_compiler import WorkflowCompiler
from src.domain.agent_builder.schemas import WorkerDefinition, WorkflowDefinition
from src.domain.document_generator.exceptions import GenerateError
from src.domain.document_generator.schemas import (
    DocumentGenerationType,
    DocumentSection,
    GenerateResult,
)
from src.domain.llm.interfaces import LLMFactoryInterface
from src.domain.llm_model.entity import LlmModel


def _llm_model() -> LlmModel:
    now = datetime.now(timezone.utc)
    return LlmModel(
        id="model-1", provider="openai", model_name="gpt-4o-mini",
        display_name="m", description=None, api_key_env="OPENAI_API_KEY",
        max_tokens=None, is_active=True, is_default=True,
        created_at=now, updated_at=now,
    )


def _worker(tool_config=None) -> WorkerDefinition:
    return WorkerDefinition(
        tool_id="document_generator",
        worker_id="document_generator_worker",
        description="문서생성기",
        sort_order=0,
        tool_config=tool_config if tool_config is not None else {
            "type_id": "t-1",
            "mcp_html_to_doc_tool_id": "mcp_h2d",
            "output_format": "docx",
        },
    )


def _gen_type(status="active") -> DocumentGenerationType:
    now = datetime.now(timezone.utc)
    return DocumentGenerationType(
        id="t-1", agent_id="agent-1", worker_id="document_generator_worker",
        name="시장조사 보고서", description="",
        sections=[DocumentSection(title="개요"), DocumentSection(title="시장 현황")],
        output_format="docx", status=status,
        created_at=now, updated_at=now,
    )


def _compiler(type_repo=None, generator=None) -> WorkflowCompiler:
    tool_factory = MagicMock()
    llm_factory = MagicMock(spec=LLMFactoryInterface)
    llm_factory.create.return_value = MagicMock()
    return WorkflowCompiler(
        tool_factory=tool_factory,
        llm_factory=llm_factory,
        logger=MagicMock(),
        hooks=DefaultHooks(),
        document_generation_type_repository=type_repo,
        document_generator=generator,
    )


def _state(messages=None) -> dict:
    return {
        "messages": messages or [HumanMessage(content="AI 시장조사 보고서 만들어줘")],
        "token_usage": 0,
        "token_limit": 8000,
    }


class TestCompile:
    @pytest.mark.asyncio
    async def test_generator_worker_is_function_node_not_react_agent(self):
        compiler = _compiler(type_repo=MagicMock(), generator=MagicMock())
        workflow = WorkflowDefinition(
            supervisor_prompt="p", workers=[_worker()], flow_hint="f",
        )
        with patch(
            "src.application.agent_builder.workflow_compiler.create_agent"
        ) as mock_react:
            graph = await compiler.compile(workflow, _llm_model(), "req")
        mock_react.assert_not_called()
        node_names = set(graph.get_graph().nodes.keys())
        assert "document_generator_worker" in node_names


class TestNode:
    @pytest.mark.asyncio
    async def test_missing_wiring_returns_guidance(self):
        compiler = _compiler(type_repo=None, generator=None)
        node = compiler._create_document_generator_node(
            MagicMock(), _worker(), auth_ctx=None, request_id="req",
        )
        result = await node(_state())
        assert result["last_worker_id"] == "document_generator_worker"
        assert "구성되지 않았" in result["messages"][0].content

    @pytest.mark.asyncio
    async def test_no_type_config_returns_guidance(self):
        compiler = _compiler(type_repo=MagicMock(), generator=MagicMock())
        node = compiler._create_document_generator_node(
            MagicMock(), _worker(tool_config={}), auth_ctx=None, request_id="req",
        )
        result = await node(_state())
        assert "문서 유형" in result["messages"][0].content

    @pytest.mark.asyncio
    async def test_deleted_type_returns_guidance(self):
        repo = MagicMock()
        repo.find_by_id = AsyncMock(return_value=_gen_type(status="deleted"))
        compiler = _compiler(type_repo=repo, generator=MagicMock())
        node = compiler._create_document_generator_node(
            MagicMock(), _worker(), auth_ctx=None, request_id="req",
        )
        result = await node(_state())
        assert "찾을 수 없" in result["messages"][0].content

    @pytest.mark.asyncio
    async def test_happy_path_returns_download_link_and_context_split(self):
        repo = MagicMock()
        repo.find_by_id = AsyncMock(return_value=_gen_type())
        generator = MagicMock()
        generator.generate = AsyncMock(return_value=GenerateResult(
            file_id="g" * 32, filename="시장조사 보고서.docx",
            section_count=2, missing_sections=[], used_evidence=True,
        ))
        compiler = _compiler(type_repo=repo, generator=generator)
        node = compiler._create_document_generator_node(
            MagicMock(), _worker(), auth_ctx=None, request_id="req",
        )
        messages = [
            HumanMessage(content="AI 시장조사 보고서 만들어줘"),
            AIMessage(content="[검색결과]\nAI 시장 근거", name="search_worker"),
        ]
        result = await node(_state(messages))
        content = result["messages"][0].content
        assert f"/api/v1/document-extractor/files/{'g' * 32}" in content
        assert "시장조사 보고서.docx" in content
        assert result["messages"][0].name == "document_generator_worker"
        # 상류 워커 산출물 전체가 근거 블록으로 전달 (D1)
        kwargs = generator.generate.call_args.kwargs
        assert "AI 시장 근거" in kwargs["evidence_block"]
        assert "보고서 만들어줘" in kwargs["conversation_block"]

    @pytest.mark.asyncio
    async def test_missing_sections_and_no_evidence_noted_in_summary(self):
        repo = MagicMock()
        repo.find_by_id = AsyncMock(return_value=_gen_type())
        generator = MagicMock()
        generator.generate = AsyncMock(return_value=GenerateResult(
            file_id="g" * 32, filename="시장조사 보고서.docx",
            section_count=2, missing_sections=["시장 현황"], used_evidence=False,
        ))
        compiler = _compiler(type_repo=repo, generator=generator)
        node = compiler._create_document_generator_node(
            MagicMock(), _worker(), auth_ctx=None, request_id="req",
        )
        content = (await node(_state()))["messages"][0].content
        assert "시장 현황" in content        # 누락 섹션 안내 (D2)
        assert "대화 문맥" in content        # 근거 없음 명시 (D1)

    @pytest.mark.asyncio
    async def test_generate_error_returns_error_message_not_raise(self):
        repo = MagicMock()
        repo.find_by_id = AsyncMock(return_value=_gen_type())
        generator = MagicMock()
        generator.generate = AsyncMock(side_effect=GenerateError("응답 비어 있음"))
        compiler = _compiler(type_repo=repo, generator=generator)
        node = compiler._create_document_generator_node(
            MagicMock(), _worker(), auth_ctx=None, request_id="req",
        )
        result = await node(_state())
        assert "문서 생성 실패" in result["messages"][0].content
