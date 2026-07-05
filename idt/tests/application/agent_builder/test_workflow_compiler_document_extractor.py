"""WorkflowCompiler — document_extractor 전용 합성 노드 테스트 (Design §4-1/§4-2)."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.application.agent_builder.supervisor_hooks import DefaultHooks
from src.application.agent_builder.workflow_compiler import WorkflowCompiler
from src.domain.agent_builder.schemas import WorkerDefinition, WorkflowDefinition
from src.domain.document_extractor.exceptions import ComposeError
from src.domain.document_extractor.schemas import DocumentTemplate, TemplateSlot
from src.domain.llm.interfaces import LLMFactoryInterface
from src.domain.llm_model.entity import LlmModel
from src.infrastructure.document_extractor.composer import ComposeResult


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
        tool_id="document_extractor",
        worker_id="document_extractor_worker",
        description="문서추출기",
        sort_order=0,
        tool_config=tool_config if tool_config is not None else {
            "template_id": "t-1",
            "mcp_pdf_to_html_tool_id": "mcp_p2h",
            "mcp_html_to_doc_tool_id": "mcp_h2d",
            "output_format": "pdf",
        },
    )


def _template(status="active") -> DocumentTemplate:
    now = datetime.now(timezone.utc)
    return DocumentTemplate(
        id="t-1", agent_id="agent-1", worker_id="document_extractor_worker",
        name="여신심의서", html_skeleton="<p>{{loan_amount}}</p>",
        slots=[TemplateSlot(key="loan_amount", label="여신금액", slot_type="value")],
        source_file_ref="ref", source_format="pdf", status=status,
        created_at=now, updated_at=now,
    )


def _compiler(template_repo=None, composer=None) -> WorkflowCompiler:
    tool_factory = MagicMock()
    llm_factory = MagicMock(spec=LLMFactoryInterface)
    llm_factory.create.return_value = MagicMock()
    return WorkflowCompiler(
        tool_factory=tool_factory,
        llm_factory=llm_factory,
        logger=MagicMock(),
        hooks=DefaultHooks(),
        document_template_repository=template_repo,
        document_composer=composer,
    )


def _state(messages=None) -> dict:
    return {
        "messages": messages or [HumanMessage(content="여신금액 5억 심의서 작성")],
        "token_usage": 0,
        "token_limit": 8000,
    }


class TestCompile:
    @pytest.mark.asyncio
    async def test_extractor_worker_is_function_node_not_react_agent(self):
        compiler = _compiler(template_repo=MagicMock(), composer=MagicMock())
        workflow = WorkflowDefinition(
            supervisor_prompt="p", workers=[_worker()], flow_hint="f",
        )
        with patch(
            "src.application.agent_builder.workflow_compiler.create_react_agent"
        ) as mock_react:
            graph = await compiler.compile(workflow, _llm_model(), "req")
        mock_react.assert_not_called()
        node_names = set(graph.get_graph().nodes.keys())
        assert "document_extractor_worker" in node_names
        assert "quality_gate" in node_names


class TestNode:
    @pytest.mark.asyncio
    async def test_missing_wiring_returns_guidance(self):
        compiler = _compiler(template_repo=None, composer=None)
        node = compiler._create_document_extractor_node(
            MagicMock(), _worker(), auth_ctx=None, request_id="req",
        )
        result = await node(_state())
        assert result["last_worker_id"] == "document_extractor_worker"
        assert "구성되지 않았" in result["messages"][0].content

    @pytest.mark.asyncio
    async def test_no_template_config_returns_guidance(self):
        compiler = _compiler(template_repo=MagicMock(), composer=MagicMock())
        node = compiler._create_document_extractor_node(
            MagicMock(), _worker(tool_config={}), auth_ctx=None, request_id="req",
        )
        result = await node(_state())
        assert "템플릿" in result["messages"][0].content

    @pytest.mark.asyncio
    async def test_deleted_template_returns_guidance(self):
        repo = MagicMock()
        repo.find_by_id = AsyncMock(return_value=_template(status="deleted"))
        compiler = _compiler(template_repo=repo, composer=MagicMock())
        node = compiler._create_document_extractor_node(
            MagicMock(), _worker(), auth_ctx=None, request_id="req",
        )
        result = await node(_state())
        assert "찾을 수 없" in result["messages"][0].content

    @pytest.mark.asyncio
    async def test_happy_path_returns_download_link(self):
        repo = MagicMock()
        repo.find_by_id = AsyncMock(return_value=_template())
        composer = MagicMock()
        composer.compose = AsyncMock(return_value=ComposeResult(
            file_id="c" * 32, filename="여신심의서.pdf",
            filled_slots={"여신금액": "5억 원"}, unfilled_labels=["소견"],
        ))
        compiler = _compiler(template_repo=repo, composer=composer)
        node = compiler._create_document_extractor_node(
            MagicMock(), _worker(), auth_ctx=None, request_id="req",
        )
        messages = [
            HumanMessage(content="여신금액 5억 심의서 작성"),
            AIMessage(content="[내부 문서 검색결과]\n근거", name="rag_worker"),
        ]
        result = await node(_state(messages))
        content = result["messages"][0].content
        assert f"/api/v1/document-extractor/files/{'c' * 32}" in content
        assert "여신심의서.pdf" in content
        assert "여신금액" in content       # 채운 항목 병기 (R3)
        assert "소견" in content           # 공란 항목 안내 (GB6)
        assert result["messages"][0].name == "document_extractor_worker"
        # 상류 워커 산출물이 근거 블록으로 전달됐는지 (GB2)
        kwargs = composer.compose.call_args.kwargs
        assert "근거" in kwargs["evidence_block"]
        assert "심의서 작성" in kwargs["conversation_block"]

    @pytest.mark.asyncio
    async def test_compose_error_returns_error_message_not_raise(self):
        repo = MagicMock()
        repo.find_by_id = AsyncMock(return_value=_template())
        composer = MagicMock()
        composer.compose = AsyncMock(side_effect=ComposeError("LLM 계약 위반"))
        compiler = _compiler(template_repo=repo, composer=composer)
        node = compiler._create_document_extractor_node(
            MagicMock(), _worker(), auth_ctx=None, request_id="req",
        )
        result = await node(_state())
        assert "문서 생성 실패" in result["messages"][0].content
