"""GeneralChatUseCase 분석 스냅샷 수집/복원 테스트 (analysis-data-continuity T7).

Design §3.7 (D7): ToolMessage 캡처(제외 목록) / system 블록 복원 /
chart_builder 컨텍스트 폴백 / 미주입 하위호환.
"""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage

from src.application.general_chat.use_case import GeneralChatUseCase
from src.domain.conversation.analysis_snapshot_policy import AnalysisSnapshotPolicy
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
from src.domain.visualization.schemas import VizDecision

_SNAPSHOT = {
    "version": 1,
    "question": "나의 휴가데이터",
    "items": [
        {"origin": "mcp_hr", "kind": "tool",
         "content": "배상규 휴가 15일 사용", "truncated": False}
    ],
}


def _make_llm_model() -> LlmModel:
    return LlmModel(
        id="test-id", provider="openai", model_name="gpt-4o",
        display_name="GPT-4o", description=None, api_key_env="OPENAI_API_KEY",
        max_tokens=128000, is_active=True, is_default=True,
        created_at=datetime(2026, 1, 1), updated_at=datetime(2026, 1, 1),
    )


def _make_msg(role: MessageRole, content: str, turn: int,
              analysis_data: dict | None = None) -> ConversationMessage:
    return ConversationMessage(
        id=None, user_id=UserId("u1"), session_id=SessionId("s1"),
        agent_id=AgentId.super(), role=role, content=content,
        turn_index=TurnIndex(turn), created_at=datetime.utcnow(),
        analysis_data=analysis_data,
    )


def _make_use_case(
    history=None, final_messages=None, snapshot_policy=...,
    viz_policy=None, chart_builder=None,
):
    mock_tool_builder = AsyncMock()
    mock_tool_builder.build.return_value = []

    mock_msg_repo = AsyncMock()
    mock_msg_repo.find_by_session.return_value = history or []
    mock_msg_repo.save.return_value = MagicMock()

    mock_summarizer = AsyncMock()
    mock_summarizer.summarize.return_value = "요약 내용"
    mock_summary_repo = AsyncMock()

    mock_policy = MagicMock()
    mock_policy.needs_summarization = MagicMock(return_value=False)

    mock_llm_factory = MagicMock(spec=LLMFactoryInterface)
    mock_llm_factory.create.return_value = MagicMock()

    final = final_messages if final_messages is not None else [
        AIMessage(content="에이전트 답변")
    ]
    mock_agent = AsyncMock()
    mock_agent.ainvoke.return_value = {"messages": final}

    async def _fake_astream_events(input_dict, version=None):
        result = await mock_agent.ainvoke(input_dict)
        yield {"event": "on_chain_end", "data": {"output": result}, "name": "agent"}

    mock_agent.astream_events = _fake_astream_events

    policy = AnalysisSnapshotPolicy() if snapshot_policy is ... else snapshot_policy
    uc = GeneralChatUseCase(
        chat_tool_builder=mock_tool_builder,
        message_repo=mock_msg_repo,
        summary_repo=mock_summary_repo,
        summarizer=mock_summarizer,
        summarization_policy=mock_policy,
        logger=MagicMock(),
        llm_factory=mock_llm_factory,
        llm_model=_make_llm_model(),
        viz_policy=viz_policy,
        chart_builder=chart_builder,
        snapshot_policy=policy,
    )
    uc._create_agent = MagicMock(return_value=mock_agent)
    return uc, {"msg_repo": mock_msg_repo, "agent": mock_agent}


def _saved_assistant_analysis_data(mock_msg_repo):
    saved = [c.args[0] for c in mock_msg_repo.save.call_args_list]
    assistants = [m for m in saved if m.role == MessageRole.ASSISTANT]
    assert len(assistants) == 1
    return assistants[0].analysis_data


# ── 수집 ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tool_message가_스냅샷으로_저장된다():
    final = [
        ToolMessage(content="배상규 휴가 15일", name="mcp_hr", tool_call_id="t1"),
        AIMessage(content="답변"),
    ]
    uc, mocks = _make_use_case(final_messages=final)
    req = GeneralChatRequest(user_id="u1", session_id="s1", message="나의 휴가데이터")
    await uc.execute(req, request_id="req-1")

    data = _saved_assistant_analysis_data(mocks["msg_repo"])
    assert data is not None
    assert data["items"][0] == {
        "origin": "mcp_hr", "kind": "tool",
        "content": "배상규 휴가 15일", "truncated": False,
    }


@pytest.mark.asyncio
async def test_제외_목록_도구는_캡처하지_않는다():
    final = [
        ToolMessage(content="웹 검색 스니펫", name="tavily_search", tool_call_id="t1"),
        AIMessage(content="답변"),
    ]
    uc, mocks = _make_use_case(final_messages=final)
    req = GeneralChatRequest(user_id="u1", session_id="s1", message="질문")
    await uc.execute(req, request_id="req-1")

    assert _saved_assistant_analysis_data(mocks["msg_repo"]) is None


@pytest.mark.asyncio
async def test_정책_미주입이면_수집하지_않는다():
    final = [
        ToolMessage(content="데이터", name="mcp_hr", tool_call_id="t1"),
        AIMessage(content="답변"),
    ]
    uc, mocks = _make_use_case(final_messages=final, snapshot_policy=None)
    req = GeneralChatRequest(user_id="u1", session_id="s1", message="질문")
    await uc.execute(req, request_id="req-1")

    assert _saved_assistant_analysis_data(mocks["msg_repo"]) is None


# ── 복원 ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_스냅샷이_system_블록으로_재주입된다():
    history = [
        _make_msg(MessageRole.USER, "나의 휴가데이터", 1),
        _make_msg(MessageRole.ASSISTANT, "차트입니다", 2, analysis_data=_SNAPSHOT),
    ]
    uc, mocks = _make_use_case(history=history)
    req = GeneralChatRequest(user_id="u1", session_id="s1", message="전체 사용자는?")
    await uc.execute(req, request_id="req-1")

    input_messages = mocks["agent"].ainvoke.call_args.args[0]["messages"]
    blocks = [
        m.content for m in input_messages if isinstance(m, SystemMessage)
    ]
    assert any("[이전 분석 데이터]" in b for b in blocks)
    assert any("배상규 휴가 15일 사용" in b for b in blocks)
    # 블록은 새 질문(HumanMessage) 직전
    assert input_messages[-1].content == "전체 사용자는?"


@pytest.mark.asyncio
async def test_스냅샷_없으면_system_블록_미주입():
    history = [
        _make_msg(MessageRole.USER, "질문", 1),
        _make_msg(MessageRole.ASSISTANT, "답변", 2),
    ]
    uc, mocks = _make_use_case(history=history)
    req = GeneralChatRequest(user_id="u1", session_id="s1", message="후속")
    await uc.execute(req, request_id="req-1")

    input_messages = mocks["agent"].ainvoke.call_args.args[0]["messages"]
    assert all(
        "[이전 분석 데이터]" not in str(m.content) for m in input_messages
    )


# ── chart_builder 컨텍스트 폴백 ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sources_없으면_스냅샷이_차트_컨텍스트로_사용된다():
    history = [
        _make_msg(MessageRole.USER, "나의 휴가데이터", 1),
        _make_msg(MessageRole.ASSISTANT, "답변", 2, analysis_data=_SNAPSHOT),
    ]
    viz_policy = MagicMock()
    viz_policy.decide.return_value = VizDecision.VISUALIZE.value
    chart_builder = AsyncMock()
    chart_builder.build.return_value = []

    uc, _ = _make_use_case(
        history=history, viz_policy=viz_policy, chart_builder=chart_builder,
    )
    req = GeneralChatRequest(
        user_id="u1", session_id="s1", message="휴가 그래프 다시 그려줘",
    )
    await uc.execute(req, request_id="req-1")

    chart_builder.build.assert_awaited_once()
    context = chart_builder.build.call_args.args[2]
    assert "배상규 휴가 15일 사용" in context
