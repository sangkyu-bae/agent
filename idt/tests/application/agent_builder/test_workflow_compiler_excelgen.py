"""WorkflowCompiler — excel_export 전용 생성 노드 테스트 (excel-generator-node §2.1)."""
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from src.application.agent_builder.supervisor_hooks import DefaultHooks
from src.application.agent_builder.workflow_compiler import WorkflowCompiler
from src.domain.agent_builder.schemas import WorkerDefinition, WorkflowDefinition
from src.domain.excel_generator.exceptions import (
    ExcelGenerateError,
    NoExcelDataError,
)
from src.domain.excel_generator.schemas import ExcelGenerateResult
from src.domain.llm.interfaces import LLMFactoryInterface
from src.domain.llm_model.entity import LlmModel


def _llm_model() -> LlmModel:
    now = datetime.now(UTC)
    return LlmModel(
        id="model-1", provider="openai", model_name="gpt-4o-mini",
        display_name="m", description=None, api_key_env="OPENAI_API_KEY",
        max_tokens=None, is_active=True, is_default=True,
        created_at=now, updated_at=now,
    )


def _worker() -> WorkerDefinition:
    return WorkerDefinition(
        tool_id="excel_export",
        worker_id="excel_worker",
        description="엑셀 생성",
        sort_order=0,
        tool_config={},
    )


def _compiler(generator=None) -> WorkflowCompiler:
    tool_factory = MagicMock()
    llm_factory = MagicMock(spec=LLMFactoryInterface)
    llm_factory.create.return_value = MagicMock()
    return WorkflowCompiler(
        tool_factory=tool_factory,
        llm_factory=llm_factory,
        logger=MagicMock(),
        hooks=DefaultHooks(),
        excel_generator=generator,
    )


def _result(truncated=False) -> ExcelGenerateResult:
    return ExcelGenerateResult(
        file_id="e" * 32, filename="수집결과.xlsx",
        sheet_count=2, total_rows=120,
        truncated=truncated, used_raw_source=True,
    )


def _state(messages=None, analysis_source=None, attachments=None) -> dict:
    return {
        "messages": messages or [HumanMessage(content="데이터 수집해서 엑셀로")],
        "token_usage": 0,
        "token_limit": 8000,
        "analysis_source": analysis_source or [],
        "attachments": attachments or [],
    }


class TestCompile:
    @pytest.mark.asyncio
    async def test_excel_worker_is_function_node_not_react_agent(self):
        # Design §2.1: excel_export는 전용 합성 노드 — react agent·ToolFactory 미경유
        compiler = _compiler(generator=MagicMock())
        workflow = WorkflowDefinition(
            supervisor_prompt="p", workers=[_worker()], flow_hint="f",
        )
        with patch(
            "src.application.agent_builder.workflow_compiler.create_agent"
        ) as mock_react:
            graph = await compiler.compile(workflow, _llm_model(), "req")
        mock_react.assert_not_called()
        compiler._tool_factory.create.assert_not_called()
        node_names = set(graph.get_graph().nodes.keys())
        assert "excel_worker" in node_names


    @pytest.mark.asyncio
    async def test_excel_worker_bypasses_wrap_worker(self):
        # Design §2.1: function_node_ids 등록 → _wrap_worker(react 결과 정제) 미적용
        compiler = _compiler(generator=MagicMock())
        workflow = WorkflowDefinition(
            supervisor_prompt="p", workers=[_worker()], flow_hint="f",
        )
        with patch.object(
            compiler, "_wrap_worker", wraps=compiler._wrap_worker
        ) as wrap, patch(
            "src.application.agent_builder.workflow_compiler.create_agent"
        ):
            await compiler.compile(workflow, _llm_model(), "req")
        assert all(
            call.args[0] != "excel_worker" for call in wrap.call_args_list
        )


class TestNode:
    @pytest.mark.asyncio
    async def test_start_log_emitted_before_generate(self):
        # Design §6.2: 시작 로그 — LLM 대기 중 프로세스 사망 시 run 흔적 확보
        generator = MagicMock()
        generator.generate = AsyncMock(return_value=_result())
        compiler = _compiler(generator=generator)
        node = compiler._create_excel_generator_node(
            MagicMock(), _worker(), auth_ctx=None, request_id="req",
        )
        await node(_state())
        events = [c.args[0] for c in compiler._logger.info.call_args_list]
        assert "excel_generator_node start" in events
        assert events.index("excel_generator_node start") < events.index(
            "excel_generator_node done"
        )

    @pytest.mark.asyncio
    async def test_missing_wiring_returns_guidance(self):
        compiler = _compiler(generator=None)
        node = compiler._create_excel_generator_node(
            MagicMock(), _worker(), auth_ctx=None, request_id="req",
        )
        result = await node(_state())
        assert result["last_worker_id"] == "excel_worker"
        assert "구성되지 않았" in result["messages"][0].content

    @pytest.mark.asyncio
    async def test_happy_path_returns_download_link_and_sources(self):
        generator = MagicMock()
        generator.generate = AsyncMock(return_value=_result())
        compiler = _compiler(generator=generator)
        node = compiler._create_excel_generator_node(
            MagicMock(), _worker(), auth_ctx=None, request_id="req",
        )
        messages = [
            HumanMessage(content="상위 데이터 수집해서 엑셀로 만들어줘"),
            AIMessage(content="[검색결과]\n수집 데이터", name="search_worker"),
        ]
        analysis_source = [{"origin": "a", "kind": "raw_source", "excel": {"sheets": {}}}]
        attachments = [{"type": "excel", "file_path": "/tmp/x.xlsx"}]
        result = await node(_state(messages, analysis_source, attachments))

        content = result["messages"][0].content
        assert f"/api/v1/document-extractor/files/{'e' * 32}" in content
        assert "수집결과.xlsx" in content
        assert result["messages"][0].name == "excel_worker"
        assert result["last_worker_id"] == "excel_worker"
        assert result["token_usage"] > 0
        # 소스 채널·누적 컨텍스트가 generator로 전달 (Design §2.1)
        kwargs = generator.generate.call_args.kwargs
        assert kwargs["analysis_source"] == analysis_source
        assert kwargs["attachments"] == attachments
        assert "수집 데이터" in kwargs["evidence_block"]
        assert "엑셀로 만들어줘" in kwargs["conversation_block"]

    @pytest.mark.asyncio
    async def test_truncated_result_notes_row_cap(self):
        generator = MagicMock()
        generator.generate = AsyncMock(return_value=_result(truncated=True))
        compiler = _compiler(generator=generator)
        node = compiler._create_excel_generator_node(
            MagicMock(), _worker(), auth_ctx=None, request_id="req",
        )
        content = (await node(_state()))["messages"][0].content
        assert "행 상한" in content  # Design §4.3 truncated 안내

    @pytest.mark.asyncio
    async def test_no_data_returns_guidance_not_raise(self):
        generator = MagicMock()
        generator.generate = AsyncMock(side_effect=NoExcelDataError("데이터 없음"))
        compiler = _compiler(generator=generator)
        node = compiler._create_excel_generator_node(
            MagicMock(), _worker(), auth_ctx=None, request_id="req",
        )
        result = await node(_state())
        assert "찾지 못했습니다" in result["messages"][0].content

    @pytest.mark.asyncio
    async def test_generate_error_returns_error_message_not_raise(self):
        generator = MagicMock()
        generator.generate = AsyncMock(side_effect=ExcelGenerateError("계획 파싱 실패"))
        compiler = _compiler(generator=generator)
        node = compiler._create_excel_generator_node(
            MagicMock(), _worker(), auth_ctx=None, request_id="req",
        )
        result = await node(_state())
        assert "엑셀 생성 실패" in result["messages"][0].content
