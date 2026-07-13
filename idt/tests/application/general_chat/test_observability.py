"""retrieval-observability §6-7/8/9: GeneralChatUseCase ai_run 라이프사이클 배선.

Design §4.4 — D1(chart-edit 이후 run open) / D2(deferred attach) / D3(sentinel agent_id).
tracker 미주입 시 기존 동작 100% 동일 (하위호환 회귀 가드).
"""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage

from src.application.general_chat.use_case import (
    GENERAL_CHAT_AGENT_ID,
    GeneralChatUseCase,
)
from src.domain.conversation.entities import ConversationMessage
from src.domain.conversation.value_objects import (
    AgentId,
    MessageRole,
    SessionId,
    TurnIndex,
    UserId,
)
from src.domain.general_chat.schemas import GeneralChatRequest
from src.domain.llm.interfaces import LLMFactoryInterface
from src.domain.llm_model.entity import LlmModel


def _make_llm_model() -> LlmModel:
    return LlmModel(
        id="model-1", provider="openai", model_name="gpt-4o",
        display_name="GPT-4o", description=None, api_key_env="OPENAI_API_KEY",
        max_tokens=128000, is_active=True, is_default=True,
        created_at=datetime(2026, 1, 1), updated_at=datetime(2026, 1, 1),
    )


def _make_saved_msg(msg_id: int | None, role: MessageRole) -> ConversationMessage:
    from src.domain.conversation.entities import MessageId

    return ConversationMessage(
        id=MessageId(msg_id) if msg_id is not None else None,
        user_id=UserId("u1"),
        session_id=SessionId("s1"),
        agent_id=AgentId.super(),
        role=role,
        content="내용",
        turn_index=TurnIndex(1),
        created_at=datetime.utcnow(),
    )


def _make_tracker() -> MagicMock:
    tracker = MagicMock()
    tracker.start_run = AsyncMock()
    tracker.complete_run = AsyncMock()
    tracker.fail_run = AsyncMock()
    tracker.attach_user_message = AsyncMock()
    return tracker


def _make_use_case(tracker=None, agent_messages=None):
    mock_tool_builder = AsyncMock()
    mock_tool_builder.build.return_value = []

    mock_msg_repo = AsyncMock()
    mock_msg_repo.find_by_session.return_value = []
    # user 메시지 저장(id=101) → assistant 저장(id=102)
    mock_msg_repo.save.side_effect = [
        _make_saved_msg(101, MessageRole.USER),
        _make_saved_msg(102, MessageRole.ASSISTANT),
    ]

    mock_policy = MagicMock()
    mock_policy.needs_summarization = MagicMock(return_value=False)

    mock_llm_factory = MagicMock(spec=LLMFactoryInterface)
    mock_llm_factory.create.return_value = MagicMock()

    mock_agent = AsyncMock()
    mock_agent.ainvoke.return_value = {
        "messages": agent_messages or [AIMessage(content="답변")]
    }

    async def _fake_astream_events(input_dict, version=None, config=None):
        result = await mock_agent.ainvoke(input_dict)
        yield {"event": "on_chain_end", "data": {"output": result}, "name": "agent"}

    mock_agent.astream_events = _fake_astream_events

    uc = GeneralChatUseCase(
        chat_tool_builder=mock_tool_builder,
        message_repo=mock_msg_repo,
        summary_repo=AsyncMock(),
        summarizer=AsyncMock(),
        summarization_policy=mock_policy,
        logger=MagicMock(),
        llm_factory=mock_llm_factory,
        llm_model=_make_llm_model(),
        tracker=tracker,
    )
    uc._create_agent = MagicMock(return_value=mock_agent)
    return uc, mock_msg_repo, mock_agent


class TestRunLifecycle:
    """§6-7: start → attach → complete 시퀀스 + sentinel agent_id."""

    @pytest.mark.asyncio
    async def test_start_attach_complete_sequence(self) -> None:
        tracker = _make_tracker()
        uc, _, _ = _make_use_case(tracker=tracker)
        req = GeneralChatRequest(user_id="u1", session_id="s1", message="질문")

        await uc.execute(req, request_id="req-1")

        tracker.start_run.assert_awaited_once()
        kwargs = tracker.start_run.await_args.kwargs
        assert kwargs["agent_id"] == GENERAL_CHAT_AGENT_ID
        assert kwargs["user_id"] == "u1"
        assert kwargs["user_message_id"] is None  # D2: deferred
        assert kwargs["agent_llm_model_id"] == "model-1"

        # D2: _persist_messages 후 user 메시지 id(101)로 attach
        tracker.attach_user_message.assert_awaited_once()
        attach_args = tracker.attach_user_message.await_args.args
        assert attach_args[1] == 101

        tracker.complete_run.assert_awaited_once()
        tracker.fail_run.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_run_context_reset_after_stream(self) -> None:
        from src.application.agent_run.context import get_current_run_context

        tracker = _make_tracker()
        uc, _, _ = _make_use_case(tracker=tracker)
        req = GeneralChatRequest(user_id="u1", session_id="s1", message="질문")

        await uc.execute(req, request_id="req-1")

        assert get_current_run_context() is None


class TestBackwardCompat:
    """§6-8: tracker 미주입 시 기존 동작 100% 동일."""

    @pytest.mark.asyncio
    async def test_no_tracker_no_observability(self) -> None:
        uc, msg_repo, _ = _make_use_case(tracker=None)
        req = GeneralChatRequest(user_id="u1", session_id="s1", message="질문")

        resp = await uc.execute(req, request_id="req-1")

        assert resp.answer == "답변"
        assert msg_repo.save.await_count == 2

    @pytest.mark.asyncio
    async def test_chart_edit_path_opens_no_run(self) -> None:
        """D1: chart-edit 조기 반환 경로는 run을 열지 않음."""
        tracker = _make_tracker()
        uc, _, _ = _make_use_case(tracker=tracker)
        # chart-edit 분기 강제: _try_chart_edit가 (answer, charts) 반환
        uc._try_chart_edit = AsyncMock(return_value=("차트 수정 완료", [{"t": "bar"}]))
        req = GeneralChatRequest(user_id="u1", session_id="s1", message="차트 바꿔줘")

        resp = await uc.execute(req, request_id="req-1")

        assert resp.answer == "차트 수정 완료"
        tracker.start_run.assert_not_awaited()


class TestFailurePaths:
    """§6-9: 예외 시 fail_run, start_run 실패 시 degraded 진행."""

    @pytest.mark.asyncio
    async def test_agent_failure_calls_fail_run(self) -> None:
        tracker = _make_tracker()
        uc, _, mock_agent = _make_use_case(tracker=tracker)
        mock_agent.ainvoke.side_effect = RuntimeError("LLM down")
        req = GeneralChatRequest(user_id="u1", session_id="s1", message="질문")

        events = [ev async for ev in uc.stream(req, "req-1")]

        types = [ev.event_type.value for ev in events]
        assert "chat_failed" in types
        tracker.fail_run.assert_awaited_once()
        tracker.complete_run.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_start_run_failure_degrades_gracefully(self) -> None:
        """start_run RuntimeError → run 없이 채팅 정상 진행."""
        tracker = _make_tracker()
        tracker.start_run = AsyncMock(side_effect=RuntimeError("obs down"))
        uc, _, _ = _make_use_case(tracker=tracker)
        req = GeneralChatRequest(user_id="u1", session_id="s1", message="질문")

        resp = await uc.execute(req, request_id="req-1")

        assert resp.answer == "답변"
        tracker.attach_user_message.assert_not_awaited()
        tracker.complete_run.assert_not_awaited()
        tracker.fail_run.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_attach_skipped_when_user_message_id_missing(self) -> None:
        """저장된 user 메시지 id가 None이면 attach 미호출."""
        tracker = _make_tracker()
        uc, msg_repo, _ = _make_use_case(tracker=tracker)
        msg_repo.save.side_effect = [
            _make_saved_msg(None, MessageRole.USER),
            _make_saved_msg(102, MessageRole.ASSISTANT),
        ]
        req = GeneralChatRequest(user_id="u1", session_id="s1", message="질문")

        await uc.execute(req, request_id="req-1")

        tracker.attach_user_message.assert_not_awaited()
