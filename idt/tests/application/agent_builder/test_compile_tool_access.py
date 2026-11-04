"""WorkflowCompiler 실행 시점 도구 권한 필터 — 실제 컴파일 그래프로 검증.

Design Ref: tool-access-control §2.1 ①~④, §8.3 R7·R8·R9·R10·R11
AsyncMock 단독 금지(위키 false-green): 도구 팩토리만 가짜, compile 은 실제로 돌려
컴파일된 그래프의 노드 목록으로 워커 제외를 확인한다.
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.application.agent_builder.workflow_compiler import WorkflowCompiler
from src.domain.agent_builder.schemas import WorkerDefinition, WorkflowDefinition
from src.domain.llm.interfaces import LLMFactoryInterface
from src.domain.llm_model.entity import LlmModel
from src.domain.tool_access.value_objects import ToolAccessSet

_CREATE_AGENT = "src.application.agent_builder.workflow_compiler.create_agent"
SRV = "7f3c0000-0000-0000-0000-000000000001"


def _model() -> LlmModel:
    now = datetime.now(timezone.utc)
    return LlmModel(
        id="model-1", provider="openai", model_name="gpt-4o-mini", display_name="m",
        description=None, api_key_env="OPENAI_API_KEY", max_tokens=1000,
        is_active=True, is_default=True, created_at=now, updated_at=now,
    )


def _w(tool_id: str, worker_id: str) -> WorkerDefinition:
    return WorkerDefinition(tool_id=tool_id, worker_id=worker_id, description=f"{worker_id} 설명")


def _wf(*workers: WorkerDefinition, prompt: str = "역할") -> WorkflowDefinition:
    return WorkflowDefinition(supervisor_prompt=prompt, workers=list(workers), flow_hint="")


def _mcp_tool(name: str):
    t = MagicMock()
    t.mcp_tool_name = name
    t.name = name
    return t


def _compiler(**extra):
    tool_factory = MagicMock()
    tool_factory.create = MagicMock(side_effect=lambda tid, rid="", **kw: _mcp_tool(tid))
    tool_factory.create_all_async = AsyncMock(return_value=[_mcp_tool("search")])
    llm_factory = MagicMock(spec=LLMFactoryInterface)
    llm_factory.create.return_value = MagicMock()
    return (
        WorkflowCompiler(tool_factory=tool_factory, llm_factory=llm_factory, logger=MagicMock(), **extra),
        tool_factory,
    )


def _nodes(graph) -> set[str]:
    return set(graph.get_graph().nodes)




@pytest.fixture(autouse=True)
def _patch_agent():
    with patch(_CREATE_AGENT, return_value=MagicMock()):
        yield


async def test_denied_worker_not_in_graph_and_reported():
    access = ToolAccessSet(is_admin=False, allowed=frozenset({"internal:tavily_search"}))
    compiler, factory = _compiler()
    sink: list = []
    graph = await compiler.compile(
        _wf(_w("tavily_search", "web"), _w("python_code_executor", "code")),
        _model(), "rid", tool_access=access, excluded_sink=sink,
    )
    nodes = _nodes(graph)
    assert "web" in nodes and "code" not in nodes
    assert [w.tool_id for w in sink] == ["python_code_executor"]
    created = [c.args[0] for c in factory.create.call_args_list]
    assert "python_code_executor" not in created


async def test_all_denied_compiles_as_tool_less_agent():
    # 권한 제외는 '도구 생성 실패'가 아니다 — 전부 빠져도 컴파일 예외 없이 대화형으로 실행
    compiler, _ = _compiler()
    graph = await compiler.compile(
        _wf(_w("python_code_executor", "code")), _model(), "rid",
        tool_access=ToolAccessSet.deny_all(),
    )
    assert "code" not in _nodes(graph)


async def test_dedicated_node_excluded():
    # R8: 전용 노드(문서생성기 등)는 ToolFactory 를 거치지 않으므로 워커 단계에서 빠져야 한다
    compiler, _ = _compiler()
    graph = await compiler.compile(
        _wf(_w("tavily_search", "web"), _w("document_generator", "docgen")),
        _model(), "rid",
        tool_access=ToolAccessSet(is_admin=False, allowed=frozenset({"internal:tavily_search"})),
    )
    assert "docgen" not in _nodes(graph)


async def test_notice_reaches_supervisor_prompt():
    compiler, _ = _compiler()
    with patch(
        "src.application.agent_builder.workflow_compiler.create_supervisor_node",
        wraps=__import__(
            "src.application.agent_builder.workflow_compiler", fromlist=["create_supervisor_node"]
        ).create_supervisor_node,
    ) as spy:
        await compiler.compile(
            _wf(_w("tavily_search", "web"), _w("python_code_executor", "code")),
            _model(), "rid",
            tool_access=ToolAccessSet(is_admin=False, allowed=frozenset({"internal:tavily_search"})),
        )
    prompt = spy.call_args.kwargs.get("supervisor_prompt") or spy.call_args.args[1]
    assert "사용할 수 없는 도구" in prompt and "Python 코드 실행" in prompt
    assert prompt.rstrip().endswith("역할")


async def test_no_tool_access_means_no_filter():
    compiler, _ = _compiler()
    graph = await compiler.compile(
        _wf(_w("tavily_search", "web"), _w("python_code_executor", "code")), _model(), "rid",
    )
    assert {"web", "code"} <= _nodes(graph)


async def test_server_level_mcp_passes_allowed_names():
    # R9: 레거시 서버 단위 참조는 허용된 도구명만 바인딩하도록 팩토리에 전달
    access = ToolAccessSet(is_admin=False, allowed=frozenset({f"mcp:{SRV}:search"}))
    compiler, factory = _compiler()
    await compiler.compile(_wf(_w(f"mcp_{SRV}", "mcp")), _model(), "rid", tool_access=access)
    assert factory.create_all_async.call_args.kwargs["allowed_tool_names"] == frozenset({"search"})


async def test_server_level_all_denied_excluded():
    # R10
    compiler, factory = _compiler()
    sink: list = []
    await compiler.compile(
        _wf(_w(f"mcp_{SRV}", "mcp")), _model(), "rid",
        tool_access=ToolAccessSet(is_admin=False, allowed=frozenset()), excluded_sink=sink,
    )
    factory.create_all_async.assert_not_awaited()
    assert [w.tool_id for w in sink] == [f"mcp_{SRV}"]


async def test_admin_server_level_no_name_filter():
    compiler, factory = _compiler()
    await compiler.compile(_wf(_w(f"mcp_{SRV}", "mcp")), _model(), "rid", tool_access=ToolAccessSet.admin())
    assert factory.create_all_async.call_args.kwargs["allowed_tool_names"] is None


async def test_sub_agent_inherits_tool_access():
    # R7: 서브에이전트 그래프에도 같은 허용 집합이 적용된다
    sub = MagicMock()
    sub.status = "active"
    sub.llm_model_id = "model-1"
    sub.temperature = 0.0
    sub.include_user_context = True
    sub.to_workflow_definition.return_value = _wf(
        _w("tavily_search", "sub_web"), _w("python_code_executor", "sub_code")
    )
    repo = MagicMock()
    repo.find_by_id = AsyncMock(return_value=sub)
    compiler, factory = _compiler(agent_repository=repo)
    sink: list = []
    await compiler.compile(
        _wf(WorkerDefinition(tool_id="", worker_id="child", description="d",
                             worker_type="sub_agent", ref_agent_id="sub-1")),
        _model(), "rid",
        tool_access=ToolAccessSet(is_admin=False, allowed=frozenset({"internal:tavily_search"})),
        excluded_sink=sink,
    )
    created = [c.args[0] for c in factory.create.call_args_list]
    assert "tavily_search" in created and "python_code_executor" not in created
    assert [w.tool_id for w in sink] == ["python_code_executor"]


class TestWikiListBundling:
    """R11: wiki_read 허용 + wiki_list 불허 -> wiki_read 단독 (폴더 지시도 쓰지 않음)."""

    async def _compile(self, access):
        from tests.application.agent_builder.test_workflow_compiler_wiki_toc import (
            FOLDER_BLOCK,
            _make_compiler,
            _workflow,
        )

        compiler, _ = _make_compiler(toc_block=FOLDER_BLOCK)

        async def _noop(state):
            return {}

        with patch(_CREATE_AGENT, MagicMock(side_effect=lambda *a, **k: _noop)) as react:
            await compiler.compile(
                _workflow(["wiki_read"]), _model(), "rid", agent_id="a1", tool_access=access,
            )
        created = [c.args[0] for c in compiler._tool_factory.create.call_args_list]
        return created, react.call_args.kwargs.get("system_prompt") or ""

    async def test_denied_wiki_list_not_bundled(self):
        created, prompt = await self._compile(
            ToolAccessSet(is_admin=False, allowed=frozenset({"internal:wiki_read"}))
        )
        assert "wiki_list" not in created
        assert "wiki_list" not in prompt

    async def test_allowed_wiki_list_bundled(self):
        created, _ = await self._compile(
            ToolAccessSet(is_admin=False, allowed=frozenset({"internal:wiki_read", "internal:wiki_list"}))
        )
        assert "wiki_list" in created
