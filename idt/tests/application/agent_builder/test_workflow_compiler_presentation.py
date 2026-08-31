"""WorkflowCompiler — presentation_generator 생성 노드 (blueprint §8.2 #14~16)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from src.application.agent_builder.supervisor_hooks import DefaultHooks
from src.application.agent_builder.workflow_compiler import WorkflowCompiler
from src.domain.agent_builder.schemas import WorkerDefinition, WorkflowDefinition
from src.domain.blueprint.errors import PresentationGenerateError
from src.domain.blueprint.value_objects import (
    DocumentBlueprint,
    HeaderFooter,
    Narrative,
    NarrativeSection,
    PagePattern,
    PatternKind,
    PresentationResult,
    RelBox,
    Slot,
    SlotKind,
    StyleTokens,
    TableStyle,
)
from src.domain.llm.interfaces import LLMFactoryInterface
from src.domain.llm_model.entity import LlmModel


def _llm_model() -> LlmModel:
    now = datetime.now(UTC)
    return LlmModel(
        id="model-1",
        provider="openai",
        model_name="gpt-4o-mini",
        display_name="m",
        description=None,
        api_key_env="OPENAI_API_KEY",
        max_tokens=None,
        is_active=True,
        is_default=True,
        created_at=now,
        updated_at=now,
    )


def _worker(tool_config=None) -> WorkerDefinition:
    return WorkerDefinition(
        tool_id="presentation_generator",
        worker_id="ppt_worker",
        description="발표자료생성기",
        sort_order=0,
        tool_config=tool_config
        if tool_config is not None
        else {
            "blueprint_id": "bp-1",
            "output_format": "pptx",
            "mcp_pptx_to_pdf_tool_id": "",
            "max_slides": 10,
        },
    )


def _bp(status="active") -> DocumentBlueprint:
    now = datetime.now(UTC)
    slot = Slot(
        "title", SlotKind.TITLE, RelBox(0.1, 0.1, 0.8, 0.2), "t", 40, None, None
    )
    return DocumentBlueprint(
        id="bp-1",
        name="리스크보고",
        description="",
        schema_version=1,
        source_kind="pdf",
        page_count=1,
        style=StyleTokens(
            (13.333, 7.5),
            {"heading": "H", "body": "B"},
            {"h1": 28.0, "h2": 20.0, "body": 14.0, "caption": 10.0},
            {
                "primary": "#1F3A5F",
                "accent1": "#E07A1F",
                "text": "#222222",
                "bg": "#FFFFFF",
            },
            TableStyle("#1F3A5F", "#FFFFFF", "#CCCCCC", False),
            HeaderFooter(None, "", ""),
        ),
        patterns=(PagePattern("p1", PatternKind.COVER, (slot,), None, 1, ""),),
        narrative=Narrative((NarrativeSection("표지", ("p1",), ""),), "", "ko"),
        assets=(),
        font_mapping={},
        warnings=(),
        status=status,
        created_at=now,
        updated_at=now,
    )


def _compiler(repo=None, generator=None) -> WorkflowCompiler:
    llm_factory = MagicMock(spec=LLMFactoryInterface)
    llm_factory.create.return_value = MagicMock()
    return WorkflowCompiler(
        tool_factory=MagicMock(),
        llm_factory=llm_factory,
        logger=MagicMock(),
        hooks=DefaultHooks(),
        presentation_generator=generator,
        blueprint_repository=repo,
    )


def _state(messages=None) -> dict:
    return {
        "messages": messages or [HumanMessage(content="3분기 리스크 PPT 10장으로")],
        "token_usage": 0,
        "token_limit": 8000,
    }


def _result(**over) -> PresentationResult:
    base = dict(
        file_id="f" * 32,
        filename="리스크보고.pptx",
        pdf_file_id=None,
        slide_count=3,
        chart_count=1,
        warnings=(),
        usage={"total_tokens": 9},
    )
    base.update(over)
    return PresentationResult(**base)


@pytest.mark.asyncio
async def test_worker_is_function_node_not_react_agent():
    compiler = _compiler(repo=MagicMock(), generator=MagicMock())
    workflow = WorkflowDefinition(
        supervisor_prompt="p", workers=[_worker()], flow_hint="f"
    )
    with patch(
        "src.application.agent_builder.workflow_compiler.create_agent"
    ) as mock_react:
        graph = await compiler.compile(workflow, _llm_model(), "req")
    mock_react.assert_not_called()
    assert "ppt_worker" in set(graph.get_graph().nodes.keys())


@pytest.mark.asyncio
async def test_missing_wiring_and_missing_blueprint_id_return_guidance():
    node = _compiler(None, None)._create_presentation_generator_node(
        MagicMock(), _worker(), auth_ctx=None, request_id="req"
    )
    out = await node(_state())
    assert (
        out["last_worker_id"] == "ppt_worker"
        and "구성되지 않았" in out["messages"][0].content
    )
    node = _compiler(MagicMock(), MagicMock())._create_presentation_generator_node(
        MagicMock(), _worker(tool_config={}), auth_ctx=None, request_id="req"
    )
    assert "양식" in (await node(_state()))["messages"][0].content


@pytest.mark.asyncio
async def test_inactive_blueprint_returns_guidance_without_generate():
    repo = MagicMock()
    repo.find_by_id = AsyncMock(return_value=_bp(status="inactive"))
    generator = MagicMock()
    generator.generate = AsyncMock()
    node = _compiler(repo, generator)._create_presentation_generator_node(
        MagicMock(), _worker(), auth_ctx=None, request_id="req"
    )
    out = await node(_state())
    assert "비활성" in out["messages"][0].content
    generator.generate.assert_not_awaited()


@pytest.mark.asyncio
async def test_happy_path_splits_context_passes_config_and_renders_links():
    repo = MagicMock()
    repo.find_by_id = AsyncMock(return_value=_bp())
    repo.load_assets = AsyncMock(return_value={"a1": b"x"})
    generator = MagicMock()
    generator.generate = AsyncMock(
        return_value=_result(pdf_file_id="p" * 32, warnings=("w1",))
    )
    auth = MagicMock(user_id=42)
    node = _compiler(repo, generator)._create_presentation_generator_node(
        "LLM", _worker(), auth_ctx=auth, request_id="req"
    )
    messages = [
        HumanMessage(content="3분기 리스크 PPT"),
        AIMessage(content="[근거] 연체율 1.5%", name="search_worker"),
        HumanMessage(content="10장 이내로"),
    ]
    out = await node(_state(messages))
    kw = generator.generate.await_args.kwargs
    assert (
        kw["llm"] == "LLM"
        and kw["blueprint"].id == "bp-1"
        and kw["assets"] == {"a1": b"x"}
    )
    assert kw["tool_config"].max_slides == 10 and kw["owner_user_id"] == "42"
    assert (
        "연체율 1.5%" in kw["evidence_block"]
        and "search_worker" in kw["evidence_block"]
    )
    assert (
        "10장 이내로" in kw["conversation_block"]
        and kw["user_instruction"] == "10장 이내로"
    )
    text = out["messages"][0].content
    assert "리스크보고.pptx" in text and f"/files/{'f' * 32}" in text
    assert f"/files/{'p' * 32}" in text and "w1" in text and "3장" in text


@pytest.mark.asyncio
async def test_generate_error_returns_failure_message():
    repo = MagicMock()
    repo.find_by_id = AsyncMock(return_value=_bp())
    repo.load_assets = AsyncMock(return_value={})
    generator = MagicMock()
    generator.generate = AsyncMock(side_effect=PresentationGenerateError("계획 없음"))
    node = _compiler(repo, generator)._create_presentation_generator_node(
        MagicMock(), _worker(), auth_ctx=None, request_id="req"
    )
    out = await node(_state())
    assert (
        "발표자료 생성 실패" in out["messages"][0].content
        and "계획 없음" in out["messages"][0].content
    )


def test_guidance_block_mentions_presentation_worker():
    compiler = _compiler(MagicMock(), MagicMock())
    workers = [
        _worker(),
        WorkerDefinition(
            tool_id="tavily_search",
            worker_id="search_worker",
            description="s",
            sort_order=1,
        ),
    ]
    block = compiler._render_docgen_guidance_block(workers)
    assert "ppt_worker" in block


@pytest.mark.asyncio
async def test_usage_callback_is_forwarded_to_generator():
    """Act-1 G5 / Plan FR-17: 관측 콜백이 generate(callbacks=[...]) 로 전달된다."""
    repo = MagicMock()
    repo.find_by_id = AsyncMock(return_value=_bp())
    repo.load_assets = AsyncMock(return_value={})
    generator = MagicMock()
    generator.generate = AsyncMock(return_value=_result())
    cb = object()
    node = _compiler(repo, generator)._create_presentation_generator_node(
        MagicMock(), _worker(), auth_ctx=None, request_id="req", callback=cb
    )
    await node(_state())
    assert generator.generate.await_args.kwargs["callbacks"] == [cb]
    node = _compiler(repo, generator)._create_presentation_generator_node(
        MagicMock(), _worker(), auth_ctx=None, request_id="req"
    )
    await node(_state())
    assert generator.generate.await_args.kwargs["callbacks"] is None
