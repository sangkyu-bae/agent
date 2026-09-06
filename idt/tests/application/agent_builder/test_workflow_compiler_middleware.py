"""builtin-middleware D6: WorkflowCompiler 미들웨어 배선 테스트.

- provider 미주입 → 워커 create_agent에 middleware=[] (무회귀)
- provider 주입 → prepare(agent_id, default_builtin=False) 1회 + 워커별 instantiate
- sub_agent 재귀(depth>0)에는 미전달
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.application.agent_builder.workflow_compiler import WorkflowCompiler
from src.domain.agent_builder.schemas import WorkerDefinition, WorkflowDefinition
from src.domain.llm_model.entity import LlmModel


def _make_llm_model() -> LlmModel:
    now = datetime.now(timezone.utc)
    return LlmModel(
        id="m-1", provider="openai", model_name="gpt-4o",
        display_name="GPT-4o", description=None, api_key_env="OPENAI_API_KEY",
        max_tokens=128000, is_active=True, is_default=True,
        created_at=now, updated_at=now,
    )


def _make_workflow(worker_count: int = 1) -> WorkflowDefinition:
    workers = [
        WorkerDefinition(
            tool_id="python_code_executor", worker_id=f"worker_{i}",
            description="코드 실행", sort_order=i,
        )
        for i in range(worker_count)
    ]
    return WorkflowDefinition(
        supervisor_prompt="프롬프트", workers=workers, flow_hint="test",
    )


def _make_compiler(middleware_provider=None) -> WorkflowCompiler:
    tool_factory = MagicMock()
    tool_factory.create = MagicMock(return_value=MagicMock())
    llm_factory = MagicMock()
    llm_factory.create = MagicMock(return_value=MagicMock())
    return WorkflowCompiler(
        tool_factory=tool_factory,
        llm_factory=llm_factory,
        logger=MagicMock(),
        middleware_provider=middleware_provider,
    )


def _make_provider(instances_factory):
    plan = MagicMock()
    plan.instantiate = MagicMock(side_effect=instances_factory)
    provider = MagicMock()
    provider.prepare = AsyncMock(return_value=plan)
    return provider, plan


class TestCompilerMiddlewareWiring:
    @pytest.mark.asyncio
    async def test_provider_미주입이면_plan_미들웨어_없음(self):
        """provider가 없으면 plan 유래 미들웨어는 0개다.

        mcp-tool-category-routing §5 D-05 (FR-10): react 워커에는 도구 호출
        예산 미들웨어가 항상 1개 실린다. plan 유래가 0개라는 성질은 그대로다.
        """
        from langchain.agents.middleware import ToolCallLimitMiddleware

        compiler = _make_compiler(middleware_provider=None)
        with patch(
            "src.application.agent_builder.workflow_compiler.create_agent",
            return_value=MagicMock(),
        ) as mock_create:
            await compiler.compile(_make_workflow(), _make_llm_model(), "req-1")
        middleware = mock_create.call_args.kwargs.get("middleware")
        assert all(isinstance(m, ToolCallLimitMiddleware) for m in middleware)
        assert len(middleware) == 1

    @pytest.mark.asyncio
    async def test_provider_주입시_prepare_1회_default_builtin_False(self):
        provider, _ = _make_provider(lambda: [])
        compiler = _make_compiler(middleware_provider=provider)
        with patch(
            "src.application.agent_builder.workflow_compiler.create_agent",
            return_value=MagicMock(),
        ):
            await compiler.compile(
                _make_workflow(worker_count=2), _make_llm_model(), "req-1",
                agent_id="agent-1",
            )
        provider.prepare.assert_awaited_once_with(
            "agent-1", "req-1", default_builtin=False
        )

    @pytest.mark.asyncio
    async def test_워커마다_instantiate_새_호출(self):
        """워커 간 미들웨어 인스턴스 공유 금지 — 워커 수만큼 instantiate."""
        provider, plan = _make_provider(lambda: [MagicMock()])
        compiler = _make_compiler(middleware_provider=provider)
        with patch(
            "src.application.agent_builder.workflow_compiler.create_agent",
            return_value=MagicMock(),
        ) as mock_create:
            await compiler.compile(
                _make_workflow(worker_count=3), _make_llm_model(), "req-1",
                agent_id="agent-1",
            )
        from langchain.agents.middleware import ToolCallLimitMiddleware

        assert plan.instantiate.call_count == 3
        for call in mock_create.call_args_list:
            middleware = call.kwargs["middleware"]
            plan_middleware = [
                m for m in middleware
                if not isinstance(m, ToolCallLimitMiddleware)
            ]
            # plan 유래는 워커당 정확히 1개 (인스턴스 공유 금지 — D6)
            assert len(plan_middleware) == 1
            # mcp-tool-category-routing §5 D-05: 예산 미들웨어도 워커마다 새로
            budgets = [
                m for m in middleware if isinstance(m, ToolCallLimitMiddleware)
            ]
            assert len(budgets) == 1
        budget_ids = {
            id(m)
            for call in mock_create.call_args_list
            for m in call.kwargs["middleware"]
            if isinstance(m, ToolCallLimitMiddleware)
        }
        assert len(budget_ids) == 3, "예산 미들웨어가 워커 간 공유되면 안 된다"

    @pytest.mark.asyncio
    async def test_sub_agent_재귀에는_미전달(self):
        """depth>0 재귀 컴파일은 plan을 준비하지 않는다."""
        provider, plan = _make_provider(lambda: [])
        compiler = _make_compiler(middleware_provider=provider)
        with patch(
            "src.application.agent_builder.workflow_compiler.create_agent",
            return_value=MagicMock(),
        ):
            await compiler.compile(
                _make_workflow(), _make_llm_model(), "req-1",
                depth=1, agent_id="agent-1",
            )
        provider.prepare.assert_not_awaited()
