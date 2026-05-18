"""WorkflowCompiler 멀티 에이전트 컴파일 테스트."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.application.agent_builder.workflow_compiler import WorkflowCompiler
from src.domain.agent_builder.policies import (
    CircularReferenceError,
    NestingDepthExceededError,
)
from src.domain.agent_builder.schemas import (
    AgentDefinition,
    WorkerDefinition,
    WorkflowDefinition,
)
from src.domain.llm.interfaces import LLMFactoryInterface
from src.domain.llm_model.entity import LlmModel


def _make_llm_model() -> LlmModel:
    now = datetime.now(timezone.utc)
    return LlmModel(
        id="model-1", provider="openai", model_name="gpt-4o-mini",
        display_name="gpt-4o-mini", description=None, api_key_env="OPENAI_API_KEY",
        max_tokens=128000, is_active=True, is_default=True,
        created_at=now, updated_at=now,
    )


def _make_agent(
    agent_id: str = "sub-1",
    workers: list[WorkerDefinition] | None = None,
) -> AgentDefinition:
    now = datetime.now(timezone.utc)
    return AgentDefinition(
        id=agent_id, user_id="user-1", name="서브 에이전트",
        description="테스트", system_prompt="테스트 프롬프트",
        flow_hint="test", llm_model_id="model-1", status="active",
        workers=workers or [
            WorkerDefinition(
                tool_id="tavily_search", worker_id="tavily_worker",
                description="웹검색", sort_order=0,
            )
        ],
        created_at=now, updated_at=now,
    )


def _make_compiler_with_repo(sub_agent=None):
    tool_factory = MagicMock()
    tool_factory.create = MagicMock(return_value=MagicMock())
    llm_factory = MagicMock(spec=LLMFactoryInterface)
    llm_factory.create.return_value = MagicMock()
    logger = MagicMock()
    repo = AsyncMock()
    repo.find_by_id = AsyncMock(return_value=sub_agent)

    compiler = WorkflowCompiler(
        tool_factory=tool_factory,
        llm_factory=llm_factory,
        logger=logger,
        agent_repository=repo,
    )
    return compiler, repo


def _workflow_with_sub_agent(ref_id: str = "sub-1") -> WorkflowDefinition:
    return WorkflowDefinition(
        supervisor_prompt="상위 에이전트",
        workers=[
            WorkerDefinition(
                tool_id=f"sub_agent_{ref_id[:8]}",
                worker_id="sub_agent_worker_0",
                description="서브 에이전트",
                sort_order=0,
                worker_type="sub_agent",
                ref_agent_id=ref_id,
            ),
        ],
        flow_hint="sub_agent",
    )


def _workflow_mixed() -> WorkflowDefinition:
    return WorkflowDefinition(
        supervisor_prompt="혼합 에이전트",
        workers=[
            WorkerDefinition(
                tool_id="tavily_search", worker_id="tool_worker_0",
                description="웹검색", sort_order=0, worker_type="tool",
            ),
            WorkerDefinition(
                tool_id="sub_agent_sub-1",
                worker_id="sub_agent_worker_1",
                description="서브 에이전트",
                sort_order=1,
                worker_type="sub_agent",
                ref_agent_id="sub-1",
            ),
        ],
        flow_hint="mixed",
    )


class TestCompileSubAgent:
    @pytest.mark.asyncio
    async def test_compile_sub_agent_produces_graph(self):
        sub_agent = _make_agent("sub-1")
        compiler, _ = _make_compiler_with_repo(sub_agent)
        workflow = _workflow_with_sub_agent("sub-1")
        with patch("src.application.agent_builder.workflow_compiler.create_react_agent",
                   return_value=MagicMock()):
            graph = await compiler.compile(
                workflow, _make_llm_model(), "req-1",
                visited={"parent-1"},
            )
        assert graph is not None

    @pytest.mark.asyncio
    async def test_compile_mixed_workers(self):
        sub_agent = _make_agent("sub-1")
        compiler, _ = _make_compiler_with_repo(sub_agent)
        workflow = _workflow_mixed()
        with patch("src.application.agent_builder.workflow_compiler.create_react_agent",
                   return_value=MagicMock()):
            graph = await compiler.compile(
                workflow, _make_llm_model(), "req-1",
                visited={"parent-1"},
            )
        node_names = set(graph.get_graph().nodes.keys())
        assert "tool_worker_0" in node_names
        assert "sub_agent_worker_1" in node_names

    @pytest.mark.asyncio
    async def test_compile_circular_ref_raises(self):
        sub_agent = _make_agent("sub-1")
        compiler, _ = _make_compiler_with_repo(sub_agent)
        workflow = _workflow_with_sub_agent("sub-1")
        with pytest.raises(CircularReferenceError, match="순환참조"):
            await compiler.compile(
                workflow, _make_llm_model(), "req-1",
                visited={"sub-1"},
            )

    @pytest.mark.asyncio
    async def test_compile_depth_exceeded_raises(self):
        compiler, _ = _make_compiler_with_repo()
        workflow = _workflow_with_sub_agent("sub-1")
        with pytest.raises(NestingDepthExceededError, match="중첩 깊이"):
            await compiler.compile(
                workflow, _make_llm_model(), "req-1",
                depth=3,
            )

    @pytest.mark.asyncio
    async def test_compile_sub_agent_not_found_raises(self):
        compiler, repo = _make_compiler_with_repo(sub_agent=None)
        workflow = _workflow_with_sub_agent("missing-id")
        with pytest.raises(ValueError, match="서브 에이전트를 찾을 수 없습니다"):
            await compiler.compile(
                workflow, _make_llm_model(), "req-1",
                visited={"parent-1"},
            )

    @pytest.mark.asyncio
    async def test_compile_no_repo_raises(self):
        tool_factory = MagicMock()
        tool_factory.create = MagicMock(return_value=MagicMock())
        llm_factory = MagicMock(spec=LLMFactoryInterface)
        llm_factory.create.return_value = MagicMock()
        compiler = WorkflowCompiler(
            tool_factory=tool_factory, llm_factory=llm_factory,
            logger=MagicMock(), agent_repository=None,
        )
        workflow = _workflow_with_sub_agent("sub-1")
        with pytest.raises(ValueError, match="agent_repository"):
            await compiler.compile(
                workflow, _make_llm_model(), "req-1",
                visited=set(),
            )


class TestWrapSubAgent:
    @pytest.mark.asyncio
    async def test_wrap_sub_agent_task_delegation(self):
        compiler, _ = _make_compiler_with_repo()
        mock_ai_msg = MagicMock()
        mock_ai_msg.content = "서브 에이전트 결과입니다."
        mock_ai_msg.type = "ai"
        mock_sub_graph = AsyncMock()
        mock_sub_graph.ainvoke.return_value = {
            "messages": [mock_ai_msg],
            "token_usage": 100,
        }

        wrapped = compiler._wrap_sub_agent("sub_worker_0", mock_sub_graph)

        user_msg = MagicMock()
        user_msg.content = "문서를 분석해주세요"
        state = {
            "messages": [user_msg],
            "token_usage": 50,
            "token_limit": 8000,
        }

        result = await wrapped(state)
        assert result["last_worker_id"] == "sub_worker_0"
        assert result["token_usage"] == 150
        assert len(result["messages"]) == 1
        assert result["messages"][0].content == "서브 에이전트 결과입니다."

        call_args = mock_sub_graph.ainvoke.call_args[0][0]
        assert call_args["messages"][0]["content"] == "문서를 분석해주세요"
