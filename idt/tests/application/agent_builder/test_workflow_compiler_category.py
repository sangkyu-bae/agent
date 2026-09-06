"""WorkflowCompiler 카테고리 라우팅·호출 상한 테스트.

Design Ref: mcp-tool-category-routing §5 D-01/D-05/D-06/D-08/D-09 (FR-04·05·10·14)

  이 파일이 고정하는 것
    ① 카테고리 해석 우선순위 (agent_tool → tool_catalog → REGISTRY → action)
    ② category="collect" → react가 아닌 collect 노드
    ③ react 분기에만 호출 상한 미들웨어 — wiki 분기는 예외 (D-06)
    ④ 카탈로그 미주입/NULL이면 이 사이클 이전과 동일 (FR-14)
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.application.agent_builder.supervisor_hooks import DefaultHooks
from src.application.agent_builder.workflow_compiler import WorkflowCompiler
from src.domain.agent_builder.schemas import WorkerDefinition, WorkflowDefinition
from src.domain.llm.interfaces import LLMFactoryInterface
from src.domain.llm_model.entity import LlmModel
from src.domain.tool_catalog.entity import ToolCatalogEntry


def _make_llm_model() -> LlmModel:
    now = datetime.now(timezone.utc)
    return LlmModel(
        id="model-1", provider="openai", model_name="gpt-4o-mini",
        display_name="gpt-4o-mini", description=None,
        api_key_env="OPENAI_API_KEY", max_tokens=128000,
        is_active=True, is_default=True, created_at=now, updated_at=now,
    )


def _entry(tool_id: str, category=None, max_tool_calls=None) -> ToolCatalogEntry:
    return ToolCatalogEntry(
        id=f"tc-{tool_id}", tool_id=tool_id, source="mcp",
        name=tool_id, description="d",
        category=category, max_tool_calls=max_tool_calls,
    )


class FakeCatalogRepo:
    def __init__(self, entries):
        self._entries = entries
        self.calls = 0

    async def list_active(self, request_id: str):
        self.calls += 1
        return list(self._entries)


def _make_compiler(catalog_entries=None, catalog_repo=None):
    mcp_tool = MagicMock()
    mcp_tool.name = "scrape"
    mcp_tool.description = "웹 수집"
    mcp_tool.mcp_tool_name = "scrape"
    mcp_tool.mcp_input_schema = {"type": "object", "properties": {}}

    tool_factory = MagicMock()
    tool_factory.create = MagicMock(return_value=mcp_tool)
    tool_factory.create_all_async = AsyncMock(return_value=[mcp_tool])
    llm_factory = MagicMock(spec=LLMFactoryInterface)
    llm_factory.create.return_value = MagicMock()

    if catalog_repo is None and catalog_entries is not None:
        catalog_repo = FakeCatalogRepo(catalog_entries)

    compiler = WorkflowCompiler(
        tool_factory=tool_factory,
        llm_factory=llm_factory,
        logger=MagicMock(),
        hooks=DefaultHooks(),
        tool_catalog_repository=catalog_repo,
    )
    return compiler, catalog_repo


def _workflow(tool_id: str, worker_id: str = "w1", category=None):
    return WorkflowDefinition(
        supervisor_prompt="당신은 AI 에이전트입니다.",
        workers=[WorkerDefinition(
            tool_id=tool_id, worker_id=worker_id,
            description="워커", sort_order=0, category=category,
        )],
        flow_hint="test",
    )


MCP_TOOL_ID = "mcp:3f2a1b4c-0000-1111-2222-333344445555:scrape"


class TestCategoryResolutionPriority:
    """FR-04: agent_tool → tool_catalog → TOOL_REGISTRY → action."""

    @pytest.mark.asyncio
    async def test_agent_tool_category_wins_over_catalog(self):
        compiler, _ = _make_compiler([_entry(MCP_TOOL_ID, category="collect")])
        worker = WorkerDefinition(
            tool_id=MCP_TOOL_ID, worker_id="w1", description="d",
            category="analysis",
        )
        meta = await compiler._load_catalog_metadata("req-1")

        assert compiler._resolve_category(worker, meta) == "analysis"

    @pytest.mark.asyncio
    async def test_catalog_category_used_when_agent_tool_null(self):
        compiler, _ = _make_compiler([_entry(MCP_TOOL_ID, category="collect")])
        worker = WorkerDefinition(
            tool_id=MCP_TOOL_ID, worker_id="w1", description="d",
        )
        meta = await compiler._load_catalog_metadata("req-1")

        assert compiler._resolve_category(worker, meta) == "collect"

    @pytest.mark.asyncio
    async def test_registry_used_when_catalog_has_no_category(self):
        """내부 도구는 카탈로그가 NULL이면 TOOL_REGISTRY가 계속 담당한다."""
        compiler, _ = _make_compiler([_entry("internal:tavily_search")])
        worker = WorkerDefinition(
            tool_id="tavily_search", worker_id="w1", description="d",
        )
        meta = await compiler._load_catalog_metadata("req-1")

        assert compiler._resolve_category(worker, meta) == "search"

    @pytest.mark.asyncio
    async def test_catalog_category_overrides_registry(self):
        """카탈로그 지정은 REGISTRY 기본값보다 우선한다."""
        compiler, _ = _make_compiler(
            [_entry("internal:tavily_search", category="collect")]
        )
        worker = WorkerDefinition(
            tool_id="tavily_search", worker_id="w1", description="d",
        )
        meta = await compiler._load_catalog_metadata("req-1")

        assert compiler._resolve_category(worker, meta) == "collect"

    @pytest.mark.asyncio
    async def test_unknown_mcp_tool_falls_back_to_action(self):
        compiler, _ = _make_compiler([])
        worker = WorkerDefinition(
            tool_id=MCP_TOOL_ID, worker_id="w1", description="d",
        )
        meta = await compiler._load_catalog_metadata("req-1")

        assert compiler._resolve_category(worker, meta) == "action"

    def test_no_catalog_repo_behaves_as_before(self):
        """D-08 / FR-14: 카탈로그 미주입이면 기존 2단계 해석 그대로."""
        compiler, _ = _make_compiler()
        worker = WorkerDefinition(
            tool_id=MCP_TOOL_ID, worker_id="w1", description="d",
        )

        assert compiler._resolve_category(worker) == "action"
        assert compiler._resolve_category(worker, None) == "action"

    @pytest.mark.asyncio
    async def test_catalog_not_queried_when_repo_absent(self):
        compiler, repo = _make_compiler()
        assert repo is None
        assert await compiler._load_catalog_metadata("req-1") == {}

    @pytest.mark.asyncio
    async def test_catalog_failure_degrades_to_empty(self):
        """카탈로그 조회 실패가 에이전트 컴파일을 죽이지 않는다."""
        class BoomRepo:
            async def list_active(self, request_id):
                raise RuntimeError("db down")

        compiler, _ = _make_compiler(catalog_repo=BoomRepo())

        assert await compiler._load_catalog_metadata("req-1") == {}


class TestCatalogBatchLoad:
    """D-09: compile()당 1회 조회 — 워커별 N+1 금지."""

    @pytest.mark.asyncio
    async def test_catalog_queried_once_per_compile(self):
        entries = [_entry(MCP_TOOL_ID, category="collect")]
        repo = FakeCatalogRepo(entries)
        compiler, _ = _make_compiler(catalog_repo=repo)
        workflow = WorkflowDefinition(
            supervisor_prompt="p",
            workers=[
                WorkerDefinition(
                    tool_id=MCP_TOOL_ID, worker_id=f"w{i}",
                    description="d", sort_order=i,
                )
                for i in range(3)
            ],
            flow_hint="t",
        )

        await compiler.compile(workflow, _make_llm_model(), "req-1")

        assert repo.calls == 1


class TestCollectBranch:
    """FR-05: category=collect → react가 아닌 collect 노드."""

    @pytest.mark.asyncio
    async def test_collect_category_builds_collect_node(self):
        compiler, _ = _make_compiler([_entry(MCP_TOOL_ID, category="collect")])
        graph = await compiler.compile(
            _workflow(MCP_TOOL_ID), _make_llm_model(), "req-1",
        )

        assert graph is not None
        assert "w1" in graph.nodes

    @pytest.mark.asyncio
    async def test_collect_worker_is_function_node_not_react_agent(self):
        """collect 노드는 create_agent 산출물이 아니다 (분석 혼입 방지의 근거)."""
        compiler, _ = _make_compiler([_entry(MCP_TOOL_ID, category="collect")])
        node = compiler._create_worker_node_for_category(
            category="collect",
            worker_id="w1",
            tool_id=MCP_TOOL_ID,
            tool=MagicMock(),
            llm=MagicMock(),
        )

        assert callable(node)
        assert not hasattr(node, "invoke")


class TestToolCallBudgetInjection:
    """FR-10 / D-05 / D-06."""

    def test_react_worker_gets_budget_middleware(self):
        compiler, _ = _make_compiler()
        extra = compiler._tool_call_budget_middleware(
            tool_id=MCP_TOOL_ID, catalog_meta={}, is_wiki_branch=False,
        )

        assert len(extra) == 1

    def test_wiki_branch_gets_no_budget_middleware(self):
        """D-06: 폴더 모드는 지도→wiki_list→wiki_read 최소 2회 — 기존 유지."""
        compiler, _ = _make_compiler()
        extra = compiler._tool_call_budget_middleware(
            tool_id="wiki_read", catalog_meta={}, is_wiki_branch=True,
        )

        assert extra == []

    def test_catalog_limit_overrides_default(self):
        compiler, _ = _make_compiler()
        meta = {MCP_TOOL_ID: _entry(MCP_TOOL_ID, max_tool_calls=5)}

        extra = compiler._tool_call_budget_middleware(
            tool_id=MCP_TOOL_ID, catalog_meta=meta, is_wiki_branch=False,
        )

        assert getattr(extra[0], "run_limit", None) == 5

    def test_default_limit_is_two(self):
        compiler, _ = _make_compiler()
        extra = compiler._tool_call_budget_middleware(
            tool_id=MCP_TOOL_ID, catalog_meta={}, is_wiki_branch=False,
        )

        assert getattr(extra[0], "run_limit", None) == 2


class TestBackwardCompatibility:
    """FR-14: 카탈로그가 없거나 category NULL이면 기존 경로 그대로."""

    @pytest.mark.asyncio
    async def test_compile_without_catalog_repo_succeeds(self):
        compiler, _ = _make_compiler()
        with patch(
            "src.application.agent_builder.workflow_compiler.create_agent",
            return_value=MagicMock(),
        ):
            graph = await compiler.compile(
                _workflow(MCP_TOOL_ID), _make_llm_model(), "req-1",
            )

        assert graph is not None

    @pytest.mark.asyncio
    async def test_null_category_takes_react_path(self):
        compiler, _ = _make_compiler([_entry(MCP_TOOL_ID, category=None)])
        with patch(
            "src.application.agent_builder.workflow_compiler.create_agent",
            return_value=MagicMock(),
        ) as mock_create:
            graph = await compiler.compile(
                _workflow(MCP_TOOL_ID), _make_llm_model(), "req-1",
            )

        assert graph is not None
        assert "w1" in graph.nodes
        mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_react_worker_receives_budget_middleware_in_compile(self):
        """FR-10 통합: 실제 compile 경로에서 상한 미들웨어가 실린다."""
        compiler, _ = _make_compiler([_entry(MCP_TOOL_ID, max_tool_calls=4)])
        with patch(
            "src.application.agent_builder.workflow_compiler.create_agent",
            return_value=MagicMock(),
        ) as mock_create:
            await compiler.compile(
                _workflow(MCP_TOOL_ID), _make_llm_model(), "req-1",
            )

        middleware = mock_create.call_args.kwargs["middleware"]
        limits = [getattr(m, "run_limit", None) for m in middleware]
        assert 4 in limits

    @pytest.mark.asyncio
    async def test_collect_worker_bypasses_create_agent(self):
        """FR-05 통합: collect 워커는 react agent를 만들지 않는다."""
        compiler, _ = _make_compiler([_entry(MCP_TOOL_ID, category="collect")])
        with patch(
            "src.application.agent_builder.workflow_compiler.create_agent",
            return_value=MagicMock(),
        ) as mock_create:
            await compiler.compile(
                _workflow(MCP_TOOL_ID), _make_llm_model(), "req-1",
            )

        mock_create.assert_not_called()
