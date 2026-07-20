"""GeneralChatUseCase 메모리 주입 테스트 (agent-memory Design §3-3).

프롬프트 순서: render_user_context_block(auth_ctx) → memory_block → _SYSTEM_PROMPT.
assembler는 optional(None 기본) — 미주입 시 기존 동작 완전 불변(회귀 0).
"""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from src.application.agent_run.prompt_rendering import render_user_context_block
from src.application.general_chat.use_case import _SYSTEM_PROMPT, GeneralChatUseCase
from src.domain.agent_run.auth_context import AuthContext
from src.domain.general_chat.schemas import GeneralChatRequest
from src.domain.llm.interfaces import LLMFactoryInterface
from src.domain.llm_model.entity import LlmModel

_MEMORY_BLOCK = "[사용자 메모리]\n- (프로필) 여신 심사팀 소속\n---\n\n"


def _make_llm_model() -> LlmModel:
    return LlmModel(
        id="test-id", provider="openai", model_name="gpt-4o",
        display_name="GPT-4o", description=None, api_key_env="OPENAI_API_KEY",
        max_tokens=128000, is_active=True, is_default=True,
        created_at=datetime(2026, 1, 1), updated_at=datetime(2026, 1, 1),
    )


def _auth_ctx() -> AuthContext:
    return AuthContext(
        user_id=7, display_name="배상규", role="user",
        primary_department_id="d1", primary_department_name="여신심사팀",
        department_ids=("d1",), department_names=("여신심사팀",),
        permissions=frozenset(),
    )


def _make_uc(memory_assembler=None, memory_extractor=None) -> GeneralChatUseCase:
    mock_llm_factory = MagicMock(spec=LLMFactoryInterface)
    mock_llm_factory.create.return_value = MagicMock()
    return GeneralChatUseCase(
        chat_tool_builder=AsyncMock(),
        message_repo=AsyncMock(),
        summary_repo=AsyncMock(),
        summarizer=AsyncMock(),
        summarization_policy=MagicMock(),
        logger=MagicMock(),
        llm_factory=mock_llm_factory,
        llm_model=_make_llm_model(),
        memory_assembler=memory_assembler,
        memory_extractor=memory_extractor,
    )


class TestCreateAgentPrompt:
    def test_메모리_블록은_user_ctx와_system_사이(self):
        uc = _make_uc()
        ctx = _auth_ctx()
        with patch(
            "src.application.general_chat.use_case.create_react_agent"
        ) as mock_create:
            uc._create_agent(tools=[], auth_ctx=ctx, memory_block=_MEMORY_BLOCK)

        prompt = mock_create.call_args.kwargs["prompt"]
        assert prompt == render_user_context_block(ctx) + _MEMORY_BLOCK + _SYSTEM_PROMPT

    def test_블록_미전달이면_기존_프롬프트_불변(self):
        uc = _make_uc()
        with patch(
            "src.application.general_chat.use_case.create_react_agent"
        ) as mock_create:
            uc._create_agent(tools=[])

        assert mock_create.call_args.kwargs["prompt"] == _SYSTEM_PROMPT

    def test_auth_ctx_없이_블록만_전달(self):
        uc = _make_uc()
        with patch(
            "src.application.general_chat.use_case.create_react_agent"
        ) as mock_create:
            uc._create_agent(tools=[], memory_block=_MEMORY_BLOCK)

        assert mock_create.call_args.kwargs["prompt"] == _MEMORY_BLOCK + _SYSTEM_PROMPT


def _wire_stream_agent(uc: GeneralChatUseCase):
    """stream() 경로용 fake agent — 캡처한 memory_block을 돌려준다."""
    captured: dict = {}

    mock_agent = AsyncMock()
    mock_agent.ainvoke.return_value = {"messages": [AIMessage(content="답변")]}

    async def _fake_astream_events(input_dict, version=None):
        result = await mock_agent.ainvoke(input_dict)
        yield {"event": "on_chain_end", "data": {"output": result}, "name": "agent"}

    mock_agent.astream_events = _fake_astream_events

    def _fake_create_agent(tools, auth_ctx=None, memory_block=""):
        captured["memory_block"] = memory_block
        return mock_agent

    uc._create_agent = _fake_create_agent
    uc._msg_repo.find_by_session.return_value = []
    uc._policy.needs_summarization = MagicMock(return_value=False)
    uc._tool_builder.build.return_value = []
    return captured


class TestStreamIntegration:
    @pytest.mark.asyncio
    async def test_assembler_주입_시_블록이_agent_생성에_전달(self):
        assembler = MagicMock()
        assembler.build_block = AsyncMock(return_value=_MEMORY_BLOCK)
        uc = _make_uc(memory_assembler=assembler)
        captured = _wire_stream_agent(uc)

        req = GeneralChatRequest(user_id="u1", session_id="s1", message="질문")
        async for _ in uc.stream(req, request_id="req-1"):
            pass

        # agent-memory-org-scope: dept_ids 키워드 전달 (auth_ctx 없으면 None)
        assembler.build_block.assert_awaited_once_with("u1", "req-1", dept_ids=None)
        assert captured["memory_block"] == _MEMORY_BLOCK

    @pytest.mark.asyncio
    async def test_auth_ctx_부서가_dept_ids로_전달(self):
        assembler = MagicMock()
        assembler.build_block = AsyncMock(return_value=_MEMORY_BLOCK)
        uc = _make_uc(memory_assembler=assembler)
        _wire_stream_agent(uc)

        req = GeneralChatRequest(user_id="u1", session_id="s1", message="질문")
        async for _ in uc.stream(req, request_id="req-1", auth_ctx=_auth_ctx()):
            pass

        # _auth_ctx()의 department_ids=("d1",)가 리스트로 전달
        assert assembler.build_block.await_args.kwargs["dept_ids"] == ["d1"]

    @pytest.mark.asyncio
    async def test_assembler_미주입이면_빈_블록(self):
        uc = _make_uc(memory_assembler=None)
        captured = _wire_stream_agent(uc)

        req = GeneralChatRequest(user_id="u1", session_id="s1", message="질문")
        async for _ in uc.stream(req, request_id="req-1"):
            pass

        assert captured["memory_block"] == ""

    @pytest.mark.asyncio
    async def test_extractor_주입_시_답변_후_kickoff_호출(self):
        """agent-memory-extraction 결정 ⑤: 답변 완료 후 fire-and-forget 추출."""
        extractor = MagicMock()
        uc = _make_uc(memory_extractor=extractor)
        _wire_stream_agent(uc)

        req = GeneralChatRequest(user_id="u1", session_id="s1", message="질문")
        async for _ in uc.stream(req, request_id="req-1"):
            pass

        extractor.kickoff.assert_called_once()
        args = extractor.kickoff.call_args.args
        assert args[0] == "u1"       # user_id
        assert args[1] == "질문"      # question
        assert args[2] == "답변"      # answer (fake agent 응답)
        assert args[3] is None       # run_id — tracker 미주입이면 None (FR-03 계약)
        assert args[4] == "req-1"    # request_id

    @pytest.mark.asyncio
    async def test_chart_edit_조기_리턴_경로는_추출_제외(self):
        """결정 ⑤: 차트 편집 턴은 저장 가치가 낮아 kickoff 미호출."""
        extractor = MagicMock()
        uc = _make_uc(memory_extractor=extractor)
        _wire_stream_agent(uc)
        uc._try_chart_edit = AsyncMock(
            return_value=("차트 수정 완료", [{"type": "bar"}])
        )
        uc._persist_messages = AsyncMock(return_value=1)

        req = GeneralChatRequest(user_id="u1", session_id="s1", message="색 바꿔줘")
        async for _ in uc.stream(req, request_id="req-1"):
            pass

        extractor.kickoff.assert_not_called()

    @pytest.mark.asyncio
    async def test_extractor_미주입이면_기존_동작_불변(self):
        uc = _make_uc(memory_extractor=None)
        captured = _wire_stream_agent(uc)

        req = GeneralChatRequest(user_id="u1", session_id="s1", message="질문")
        events = []
        async for ev in uc.stream(req, request_id="req-1"):
            events.append(ev)

        assert captured["memory_block"] == ""
        assert len(events) >= 2  # 회귀 0

    @pytest.mark.asyncio
    async def test_assembler가_빈_문자열이어도_스트림_정상(self):
        """FR-07: 조립 실패는 assembler 내부에서 ""로 격리 — 스트림은 계속된다."""
        assembler = MagicMock()
        assembler.build_block = AsyncMock(return_value="")
        uc = _make_uc(memory_assembler=assembler)
        captured = _wire_stream_agent(uc)

        req = GeneralChatRequest(user_id="u1", session_id="s1", message="질문")
        events = []
        async for ev in uc.stream(req, request_id="req-1"):
            events.append(ev)

        assert captured["memory_block"] == ""
        assert len(events) >= 2  # CHAT_STARTED + ANSWER/DONE 계열
