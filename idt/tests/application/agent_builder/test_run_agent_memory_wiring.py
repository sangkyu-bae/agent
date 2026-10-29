"""RunAgentUseCase 메모리 블록 조립·전달 — agent-memory-injection Design §6.2 (U1~U6).

Plan FR-04: auth_ctx 없는 경로(스케줄·웹훅·재개)는 조회 0회.
Plan FR-05: 런당 1회, dept_ids=auth_ctx.department_ids.
Plan FR-06: assembler 미주입이면 호출 0회 + 프롬프트 불변.
Plan FR-07: 조립기 밖 예외도 런을 죽이지 않는다.
Plan FR-09: include_user_context=False 면 조회 생략.
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.application.agent_builder.run_agent_use_case import RunAgentUseCase
from src.domain.llm_model.entity import LlmModel

_BIS = "src.application.agent_builder.run_agent_use_case.build_initial_state"


def _llm_model() -> LlmModel:
    now = datetime.now(timezone.utc)
    return LlmModel(
        id="model-1", provider="openai", model_name="gpt-4o-mini",
        display_name="m", description=None, api_key_env="OPENAI_API_KEY",
        max_tokens=128000, is_active=True, is_default=True,
        created_at=now, updated_at=now,
    )


def _uc(assembler=None) -> RunAgentUseCase:
    uc = RunAgentUseCase.__new__(RunAgentUseCase)
    uc._logger = MagicMock()
    uc._tracker = None
    uc._agent_skill_repo = None
    uc._memory_assembler = assembler
    uc._compiler = MagicMock()
    uc._compiler.compile = AsyncMock(return_value=MagicMock(
        ainvoke=AsyncMock(return_value={"messages": []})
    ))
    uc._llm_model_repository = MagicMock()
    uc._llm_model_repository.find_by_id = AsyncMock(return_value=_llm_model())
    uc._build_messages = AsyncMock(return_value=[])
    uc._build_graph_config = MagicMock(return_value={})
    return uc


def _agent(include_user_context: bool = True) -> MagicMock:
    agent = MagicMock(id="ag1", max_iterations=25, llm_model_id="model-1",
                      temperature=0.0, include_user_context=include_user_context)
    agent.to_workflow_definition.return_value = MagicMock(workers=[])
    return agent


def _request() -> MagicMock:
    return MagicMock(user_id="u-7", session_id=None, query="q", attachments=None,
                     llm_model_id_override=None, temperature_override=None)


def _auth_ctx(depts=("d1", "d2")) -> MagicMock:
    return MagicMock(user_id="u-7", department_ids=list(depts))


def _assembler(block: str = "[사용자 메모리]\n- (용어) ETC\n---\n\n") -> MagicMock:
    a = MagicMock()
    a.build_block = AsyncMock(return_value=block)
    return a


async def _prepare(uc, agent, auth_ctx, **extra):
    """기본은 대화 라우트와 같은 inject_memory=True. extra 로 덮어쓴다."""
    kwargs = {"inject_memory": True, **extra}
    with patch(_BIS, return_value={}):
        await uc._prepare_graph(
            agent=agent, request=_request(), session_id="s", callback=None,
            run_id=None, request_id="req-1", auth_ctx=auth_ctx, **kwargs,
        )
    return uc._compiler.compile.call_args.kwargs


class TestBuildMemoryBlock:
    @pytest.mark.asyncio
    async def test_U1_대화_경로는_1회_조립해_compile에_넘긴다(self):
        asm = _assembler()
        kwargs = await _prepare(_uc(asm), _agent(), _auth_ctx())
        asm.build_block.assert_awaited_once_with(
            "u-7", "req-1", dept_ids=["d1", "d2"],
        )
        assert kwargs["memory_block"] == "[사용자 메모리]\n- (용어) ETC\n---\n\n"

    @pytest.mark.asyncio
    async def test_U2_assembler_미주입이면_빈_블록(self):
        kwargs = await _prepare(_uc(None), _agent(), _auth_ctx())
        assert kwargs.get("memory_block", "") == ""

    @pytest.mark.asyncio
    async def test_U3_auth_ctx_없으면_조회_0회(self):
        asm = _assembler()
        kwargs = await _prepare(_uc(asm), _agent(), None)
        asm.build_block.assert_not_awaited()
        assert kwargs.get("memory_block", "") == ""

    @pytest.mark.asyncio
    async def test_U4_include_user_context_False면_조회_0회(self):
        asm = _assembler()
        kwargs = await _prepare(_uc(asm), _agent(include_user_context=False), _auth_ctx())
        asm.build_block.assert_not_awaited()
        assert kwargs.get("memory_block", "") == ""

    @pytest.mark.asyncio
    async def test_U5_조립_예외는_warning_후_빈_블록(self):
        asm = MagicMock()
        asm.build_block = AsyncMock(side_effect=RuntimeError("boom"))
        uc = _uc(asm)
        kwargs = await _prepare(uc, _agent(), _auth_ctx())
        assert kwargs["memory_block"] == ""
        uc._logger.warning.assert_called_once()
        assert "exception" in uc._logger.warning.call_args.kwargs

    @pytest.mark.asyncio
    async def test_U6_승인_재개_경로는_조회_0회(self):
        asm = _assembler()
        uc = _uc(asm)
        uc._parse_result = MagicMock(return_value=("답", None))
        await uc._resume_graph({}, _agent(), "req-1", subject_user_id="u-7")
        asm.build_block.assert_not_awaited()
        assert "memory_block" not in uc._compiler.compile.call_args.kwargs


class TestOptIn:
    """Act-1 (Analysis G1): 주입은 호출자 opt-in — 웹훅·백그라운드는 auth_ctx 가
    있어도 inject_memory 를 넘기지 않으므로 조회 0회 (fail-closed)."""

    @pytest.mark.asyncio
    async def test_U7_opt_in_없으면_auth_ctx_있어도_조회_0회(self):
        asm = _assembler()
        kwargs = await _prepare(_uc(asm), _agent(), _auth_ctx(), inject_memory=False)
        asm.build_block.assert_not_awaited()
        assert kwargs["memory_block"] == ""

    @pytest.mark.asyncio
    async def test_U8_prepare_graph_기본값은_미주입(self):
        """웹훅(execute, auth_ctx=owner_ctx)·백그라운드(execute, auth_ctx=ctx) 동형."""
        asm = _assembler()
        uc = _uc(asm)
        with patch(_BIS, return_value={}):
            await uc._prepare_graph(
                agent=_agent(), request=_request(), session_id="s", callback=None,
                run_id=None, request_id="req-1", auth_ctx=_auth_ctx(),
            )
        asm.build_block.assert_not_awaited()

    def test_U9_stream_execute_기본값은_False(self):
        import inspect

        for name in ("stream", "execute"):
            sig = inspect.signature(getattr(RunAgentUseCase, name))
            param = sig.parameters["inject_memory"]
            assert param.default is False
            assert param.kind is inspect.Parameter.KEYWORD_ONLY


class TestConstructor:
    def test_생성자_기본값은_None(self):
        import inspect

        sig = inspect.signature(RunAgentUseCase.__init__)
        assert sig.parameters["memory_assembler"].default is None
