"""실행 주체(subject_user_id) 배선 — 컴파일러·런 실행·승인 재개.

Design Ref: mcp-identity-header §1.1 (명시적 주체 전달), Appendix B (#1, #2).
주체는 인증 컨텍스트가 아니라 실행 요청의 사용자 ID 다 — 스케줄 런에는
인증 컨텍스트가 없다. 앱 싱글톤의 가변 필드를 쓰지 않고 인자로만 흐른다.
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.application.agent_builder.run_agent_use_case import RunAgentUseCase
from src.application.agent_builder.workflow_compiler import WorkflowCompiler
from src.domain.agent_builder.schemas import WorkerDefinition, WorkflowDefinition
from src.domain.llm.interfaces import LLMFactoryInterface
from src.domain.llm_model.entity import LlmModel

_CREATE_AGENT = "src.application.agent_builder.workflow_compiler.create_agent"


def _llm_model() -> LlmModel:
    now = datetime.now(timezone.utc)
    return LlmModel(
        id="model-1", provider="openai", model_name="gpt-4o-mini",
        display_name="m", description=None, api_key_env="OPENAI_API_KEY",
        max_tokens=128000, is_active=True, is_default=True,
        created_at=now, updated_at=now,
    )


def _mcp_workflow() -> WorkflowDefinition:
    return WorkflowDefinition(
        supervisor_prompt="p", flow_hint="t",
        workers=[WorkerDefinition(
            tool_id="mcp:srv-1:list_messages", worker_id="mail",
            description="메일", sort_order=0,
        )],
    )


def _compiler(**extra) -> tuple[WorkflowCompiler, MagicMock]:
    tool_factory = MagicMock()
    tool_factory.create = MagicMock(return_value=MagicMock())
    tool_factory.create_all_async = AsyncMock(return_value=[MagicMock()])
    llm_factory = MagicMock(spec=LLMFactoryInterface)
    llm_factory.create.return_value = MagicMock()
    compiler = WorkflowCompiler(
        tool_factory=tool_factory, llm_factory=llm_factory, logger=MagicMock(), **extra
    )
    return compiler, tool_factory


class TestCompiler:
    @pytest.mark.asyncio
    async def test_MCP_워커_생성에_주체를_넘긴다(self):
        compiler, tool_factory = _compiler()
        with patch(_CREATE_AGENT, return_value=MagicMock()):
            await compiler.compile(
                _mcp_workflow(), _llm_model(), "req-1", subject_user_id="7"
            )
        assert tool_factory.create_all_async.call_args.kwargs["subject_user_id"] == "7"

    @pytest.mark.asyncio
    async def test_주체를_주지_않으면_None(self):
        compiler, tool_factory = _compiler()
        with patch(_CREATE_AGENT, return_value=MagicMock()):
            await compiler.compile(_mcp_workflow(), _llm_model(), "req-1")
        assert tool_factory.create_all_async.call_args.kwargs["subject_user_id"] is None

    @pytest.mark.asyncio
    async def test_서브에이전트_재귀에도_주체가_전달된다(self):
        sub_agent = MagicMock()
        sub_agent.status = "active"
        sub_agent.llm_model_id = "model-1"
        sub_agent.temperature = 0.0
        sub_agent.include_user_context = True
        sub_agent.to_workflow_definition.return_value = _mcp_workflow()
        repo = MagicMock()
        repo.find_by_id = AsyncMock(return_value=sub_agent)
        compiler, tool_factory = _compiler(agent_repository=repo)
        parent = WorkflowDefinition(
            supervisor_prompt="부모", flow_hint="t",
            workers=[WorkerDefinition(
                tool_id="sub_agent", worker_id="child", description="서브",
                sort_order=0, worker_type="sub_agent", ref_agent_id="agent-child",
            )],
        )
        with patch(_CREATE_AGENT, return_value=MagicMock()):
            await compiler.compile(parent, _llm_model(), "req-1", subject_user_id="7")
        assert tool_factory.create_all_async.call_args.kwargs["subject_user_id"] == "7"


def _bare_run_uc() -> RunAgentUseCase:
    uc = RunAgentUseCase.__new__(RunAgentUseCase)
    uc._logger = MagicMock()
    uc._tracker = None
    uc._agent_skill_repo = None
    uc._compiler = MagicMock()
    uc._compiler.compile = AsyncMock(return_value=MagicMock(
        ainvoke=AsyncMock(return_value={"messages": []})
    ))
    uc._llm_model_repository = MagicMock()
    uc._llm_model_repository.find_by_id = AsyncMock(return_value=_llm_model())
    return uc


def _agent() -> MagicMock:
    agent = MagicMock(id="ag1", max_iterations=25, include_user_context=True,
                      llm_model_id="model-1", temperature=0.0)
    agent.to_workflow_definition.return_value = MagicMock(workers=[])
    return agent


class TestRunAgent:
    @pytest.mark.asyncio
    async def test_실행_요청의_user_id가_주체가_된다(self):
        """스케줄·웹훅·백그라운드도 모두 RunAgentRequest.user_id 를 채운다."""
        uc = _bare_run_uc()
        uc._build_messages = AsyncMock(return_value=[])
        uc._build_graph_config = MagicMock(return_value={})
        request = MagicMock(user_id="7", session_id=None, query="q", attachments=None,
                            llm_model_id=None, temperature=None)
        with patch("src.application.agent_builder.run_agent_use_case.build_initial_state",
                   return_value={}):
            await uc._prepare_graph(
                agent=_agent(), request=request, session_id="s", callback=None,
                run_id=None, request_id="req-1", auth_ctx=None,
            )
        assert uc._compiler.compile.call_args.kwargs["subject_user_id"] == "7"

    @pytest.mark.asyncio
    async def test_승인_재개_컴파일은_요청자를_주체로_쓴다(self):
        """승인자가 아니라 원래 실행을 요청한 사용자의 신원 (§7)."""
        uc = _bare_run_uc()
        uc._parse_result = MagicMock(return_value=("답", None))
        await uc._resume_graph({}, _agent(), "req-1", subject_user_id="requester-7")
        assert (
            uc._compiler.compile.call_args.kwargs["subject_user_id"] == "requester-7"
        )
