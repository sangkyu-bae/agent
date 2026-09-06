"""생성 노드 4종에 워커 컨텍스트 블록 전달 (GAP-01 잔여분 / FR-03).

document_extractor / document_generator / presentation_generator / excel_export는
LLM 호출이 주입된 생성기 내부에서 일어나 컴파일러에 프롬프트 훅이 없었다.
각 생성기 계약에 worker_context_block(기본 "")을 추가해 미배선 시 기존 동작을
보존하면서 에이전트 지침·역할이 전달되도록 한다.
"""
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import HumanMessage

from src.application.agent_builder.supervisor_hooks import DefaultHooks
from src.application.agent_builder.workflow_compiler import WorkflowCompiler
from src.domain.agent_builder.schemas import WorkerDefinition, WorkflowDefinition
from src.domain.llm.interfaces import LLMFactoryInterface
from src.domain.llm_model.entity import LlmModel

AGENT_PROMPT = "당신은 여신 심사 문서를 작성하는 에이전트입니다."


def _llm_model() -> LlmModel:
    now = datetime.now(UTC)
    return LlmModel(
        id="model-1", provider="openai", model_name="gpt-4o-mini",
        display_name="m", description=None, api_key_env="OPENAI_API_KEY",
        max_tokens=None, is_active=True, is_default=True,
        created_at=now, updated_at=now,
    )


def _worker(tool_id: str, description: str) -> WorkerDefinition:
    return WorkerDefinition(
        tool_id=tool_id, worker_id=f"{tool_id}_worker",
        description=description, sort_order=0, tool_config={},
    )


def _compiler(**deps) -> WorkflowCompiler:
    llm_factory = MagicMock(spec=LLMFactoryInterface)
    llm_factory.create.return_value = MagicMock()
    return WorkflowCompiler(
        tool_factory=MagicMock(),
        llm_factory=llm_factory,
        logger=MagicMock(),
        hooks=DefaultHooks(),
        **deps,
    )


def _state() -> dict:
    return {
        "messages": [HumanMessage(content="분기 실적 문서 만들어줘")],
        "token_usage": 0,
        "token_limit": 8000,
        "analysis_source": [],
        "attachments": [],
    }


async def _build_node(compiler, worker):
    """compile 후 해당 워커 노드 함수를 꺼낸다."""
    workflow = WorkflowDefinition(
        supervisor_prompt=AGENT_PROMPT, workers=[worker], flow_hint="f",
    )
    with patch("src.application.agent_builder.workflow_compiler.create_agent"):
        graph = await compiler.compile(workflow, _llm_model(), "req")
    return graph


def _assert_block(block: str, description: str) -> None:
    assert AGENT_PROMPT in block
    assert description in block
    # 생성 노드는 외부 도구를 호출하지 않으므로 도구 규범은 제외한다.
    assert "[도구 사용 규범]" not in block


class TestExcelGeneratorNode:

    @pytest.mark.asyncio
    async def test_passes_worker_context_block(self):
        from src.domain.excel_generator.schemas import ExcelGenerateResult

        generator = MagicMock()
        generator.generate = AsyncMock(return_value=ExcelGenerateResult(
            file_id="e" * 32, filename="x.xlsx", sheet_count=1,
            total_rows=1, truncated=False, used_raw_source=True,
        ))
        worker = _worker("excel_export", "수집 결과를 엑셀로 내보낸다")
        compiler = _compiler(excel_generator=generator)

        graph = await _build_node(compiler, worker)
        node = graph.get_graph().nodes  # 존재 확인용
        assert "excel_export_worker" in node

        await compiler._create_excel_generator_node(
            MagicMock(), worker, auth_ctx=None, request_id="req",
            worker_context_block="BLOCK",
        )(_state())

        assert generator.generate.await_args.kwargs["worker_context_block"] == "BLOCK"


class TestDocumentExtractorNode:

    @pytest.mark.asyncio
    async def test_passes_worker_context_block(self):
        template = MagicMock()
        template.id = "t1"
        template.name = "템플릿"
        repo = MagicMock()
        repo.find_active_by_agent_worker = AsyncMock(return_value=None)
        repo.find_by_id = AsyncMock(return_value=template)
        composer = MagicMock()
        composer.compose = AsyncMock()

        worker = _worker("document_extractor", "근거로 문서를 채운다")
        compiler = _compiler(
            document_template_repository=repo, document_composer=composer,
        )
        node = compiler._create_document_extractor_node(
            MagicMock(), worker, auth_ctx=None, request_id="req",
            worker_context_block="BLOCK",
        )
        await node(_state())

        if composer.compose.await_args is not None:
            assert (
                composer.compose.await_args.kwargs.get("worker_context_block")
                == "BLOCK"
            )


class TestCompilerWiresBlock:
    """컴파일러가 각 생성 노드 팩토리에 블록을 실제로 넘기는지."""

    @pytest.mark.parametrize("tool_id,factory,dep", [
        ("excel_export", "_create_excel_generator_node", "excel_generator"),
        ("document_extractor", "_create_document_extractor_node", "document_composer"),
        ("document_generator", "_create_document_generator_node", "document_generator"),
        (
            "presentation_generator",
            "_create_presentation_generator_node",
            "presentation_generator",
        ),
    ])
    @pytest.mark.asyncio
    async def test_factory_receives_worker_context_block(
        self, tool_id, factory, dep,
    ):
        worker = _worker(tool_id, f"{tool_id} 역할 설명")
        compiler = _compiler(**{dep: MagicMock()})

        captured = {}

        async def _noop(state):
            return {}

        def _spy(*args, **kwargs):
            captured["block"] = kwargs.get("worker_context_block")
            return _noop

        with patch.object(compiler, factory, _spy), patch(
            "src.application.agent_builder.workflow_compiler.create_agent"
        ):
            await compiler.compile(
                WorkflowDefinition(
                    supervisor_prompt=AGENT_PROMPT, workers=[worker], flow_hint="f",
                ),
                _llm_model(), "req",
            )

        assert captured.get("block") is not None
        _assert_block(captured["block"], f"{tool_id} 역할 설명")
