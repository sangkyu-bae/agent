"""GeneralChatUseCase 차트 컨텍스트 연속성 테스트.

chart-context-continuity Design §3.2(캡션 주입)/§3.7(편집 분기/폴백).
"""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage

from src.application.general_chat.use_case import GeneralChatUseCase
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
from src.domain.visualization.chart_policy import ChartStylePolicy, ChartDraft, ChartSeriesDraft
from src.domain.visualization.chart_schemas import ChartType
from src.domain.visualization.interfaces import ChartTransformResult

_STORED_CHART = {
    "type": "bar",
    "data": {
        "labels": ["영업", "심사"],
        "datasets": [{"label": "건수", "data": [1.0, 2.0]}],
    },
    "options": {"plugins": {"title": {"display": True, "text": "부서별 대출 건수"}}},
}


def _make_llm_model() -> LlmModel:
    return LlmModel(
        id="test-id", provider="openai", model_name="gpt-4o",
        display_name="GPT-4o", description=None, api_key_env="OPENAI_API_KEY",
        max_tokens=128000, is_active=True, is_default=True,
        created_at=datetime(2026, 1, 1), updated_at=datetime(2026, 1, 1),
    )


def _make_msg(
    role: MessageRole, content: str, turn: int,
    charts: list[dict] | None = None,
) -> ConversationMessage:
    return ConversationMessage(
        id=None, user_id=UserId("u1"), session_id=SessionId("s1"),
        agent_id=AgentId.super(), role=role, content=content,
        turn_index=TurnIndex(turn), created_at=datetime.utcnow(), charts=charts,
    )


def _transformed_config():
    draft = ChartDraft(
        chart_type=ChartType.PIE, title="변환됨", labels=["영업", "심사"],
        series=[ChartSeriesDraft(name="건수", data=[1.0, 2.0])],
    )
    return ChartStylePolicy().to_config(draft)


def _make_use_case(
    history: list[ConversationMessage] | None = None,
    chart_transformer=None,
) -> tuple[GeneralChatUseCase, dict]:
    mock_tool_builder = AsyncMock()
    mock_tool_builder.build.return_value = []

    mock_msg_repo = AsyncMock()
    mock_msg_repo.find_by_session.return_value = history or []
    mock_msg_repo.save.return_value = MagicMock()

    mock_summarizer = AsyncMock()
    mock_summarizer.summarize.return_value = "요약 내용"

    mock_summary_repo = AsyncMock()
    mock_summary_repo.save.return_value = MagicMock()
    mock_summary_repo.find_latest.return_value = None

    mock_policy = MagicMock()
    mock_policy.needs_summarization = MagicMock(return_value=False)

    mock_llm_factory = MagicMock(spec=LLMFactoryInterface)
    mock_llm_factory.create.return_value = MagicMock()

    mock_agent = AsyncMock()
    mock_agent.ainvoke.return_value = {"messages": [AIMessage(content="에이전트 답변")]}

    async def _fake_astream_events(input_dict, version=None):
        result = await mock_agent.ainvoke(input_dict)
        yield {"event": "on_chain_end", "data": {"output": result}, "name": "agent"}

    mock_agent.astream_events = _fake_astream_events

    uc = GeneralChatUseCase(
        chat_tool_builder=mock_tool_builder,
        message_repo=mock_msg_repo,
        summary_repo=mock_summary_repo,
        summarizer=mock_summarizer,
        summarization_policy=mock_policy,
        logger=MagicMock(),
        llm_factory=mock_llm_factory,
        llm_model=_make_llm_model(),
        chart_transformer=chart_transformer,
    )
    uc._create_agent = MagicMock(return_value=mock_agent)
    return uc, {
        "msg_repo": mock_msg_repo, "agent": mock_agent, "policy": mock_policy,
        "summarizer": mock_summarizer,
    }


def _history_with_chart() -> list[ConversationMessage]:
    return [
        _make_msg(MessageRole.USER, "부서별 대출 건수 그래프 그려줘", 1),
        _make_msg(MessageRole.ASSISTANT, "그래프입니다", 2, charts=[_STORED_CHART]),
    ]


# ── 캡션 주입 (D7-rev1) ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_caption_injected_for_assistant_message_with_charts():
    """charts 부속 assistant 메시지 → 컨텍스트 AIMessage에 캡션 부착."""
    uc, mocks = _make_use_case(history=_history_with_chart())
    req = GeneralChatRequest(user_id="u1", session_id="s1", message="고마워")
    await uc.execute(req, request_id="req-1")

    input_messages = mocks["agent"].ainvoke.call_args.args[0]["messages"]
    ai_contents = [m.content for m in input_messages if isinstance(m, AIMessage)]
    assert any("[생성된 차트:" in c for c in ai_contents)
    assert any("부서별 대출 건수" in c for c in ai_contents)


@pytest.mark.asyncio
async def test_no_caption_for_chartless_history_regression():
    """charts 없는 히스토리 → 캡션 미부착 (기존 동작 회귀 없음)."""
    history = [
        _make_msg(MessageRole.USER, "질문", 1),
        _make_msg(MessageRole.ASSISTANT, "답변", 2),
    ]
    uc, mocks = _make_use_case(history=history)
    req = GeneralChatRequest(user_id="u1", session_id="s1", message="후속")
    await uc.execute(req, request_id="req-1")

    input_messages = mocks["agent"].ainvoke.call_args.args[0]["messages"]
    assert all("[생성된 차트:" not in str(m.content) for m in input_messages)


@pytest.mark.asyncio
async def test_caption_injected_in_summarized_recent_turns():
    """요약 경로 — 최근 턴의 charts 부속 메시지에도 캡션 부착."""
    history = _history_with_chart()
    uc, mocks = _make_use_case(history=history)
    mocks["policy"].needs_summarization = MagicMock(return_value=True)
    mocks["policy"].get_turns_to_summarize = MagicMock(return_value=history[:1])
    mocks["policy"].get_summary_range = MagicMock(
        return_value=(TurnIndex(1), TurnIndex(1))
    )
    mocks["policy"].get_recent_turns = MagicMock(return_value=history[1:])

    req = GeneralChatRequest(user_id="u1", session_id="s1", message="고마워")
    await uc.execute(req, request_id="req-1")

    input_messages = mocks["agent"].ainvoke.call_args.args[0]["messages"]
    ai_contents = [m.content for m in input_messages if isinstance(m, AIMessage)]
    assert any("[생성된 차트:" in c for c in ai_contents)


# ── 편집 분기 (D4) ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_edit_intent_uses_transformer_and_skips_agent():
    """편집 의도 + 저장 차트 → transformer 호출, ReAct 에이전트 미호출."""
    transformer = AsyncMock()
    transformer.transform.return_value = ChartTransformResult(
        charts=[_transformed_config()], message="파이 차트로 변경했습니다.",
    )
    uc, mocks = _make_use_case(
        history=_history_with_chart(), chart_transformer=transformer,
    )
    req = GeneralChatRequest(
        user_id="u1", session_id="s1", message="해당 그래프를 파이로 바꿔줘",
    )
    resp = await uc.execute(req, request_id="req-1")

    transformer.transform.assert_awaited_once()
    assert transformer.transform.call_args.args[0] == "해당 그래프를 파이로 바꿔줘"
    assert transformer.transform.call_args.args[1] == [_STORED_CHART]
    mocks["agent"].ainvoke.assert_not_called()
    assert resp.answer == "파이 차트로 변경했습니다."
    assert resp.tools_used == ["chart_transformer"]
    assert len(resp.charts) == 1
    assert resp.charts[0]["type"] == "pie"


@pytest.mark.asyncio
async def test_edit_branch_persists_messages_with_charts():
    """편집 분기도 user/assistant 메시지 저장 + charts 부속."""
    transformer = AsyncMock()
    transformer.transform.return_value = ChartTransformResult(
        charts=[_transformed_config()], message="변경했습니다.",
    )
    uc, mocks = _make_use_case(
        history=_history_with_chart(), chart_transformer=transformer,
    )
    req = GeneralChatRequest(
        user_id="u1", session_id="s1", message="그 차트 색 바꿔줘",
    )
    await uc.execute(req, request_id="req-1")

    saved = [c.args[0] for c in mocks["msg_repo"].save.call_args_list]
    assert len(saved) == 2
    assert saved[0].role == MessageRole.USER
    assert saved[1].role == MessageRole.ASSISTANT
    assert saved[1].charts is not None and saved[1].charts[0]["type"] == "pie"


@pytest.mark.asyncio
async def test_edit_intent_without_stored_charts_falls_back():
    """편집 의도지만 세션에 저장 차트 없음 → 일반 경로 (오분류 안전망)."""
    transformer = AsyncMock()
    history = [
        _make_msg(MessageRole.USER, "질문", 1),
        _make_msg(MessageRole.ASSISTANT, "답변", 2),
    ]
    uc, mocks = _make_use_case(history=history, chart_transformer=transformer)
    req = GeneralChatRequest(
        user_id="u1", session_id="s1", message="해당 그래프 색 바꿔줘",
    )
    resp = await uc.execute(req, request_id="req-1")

    transformer.transform.assert_not_called()
    mocks["agent"].ainvoke.assert_called_once()
    assert resp.answer == "에이전트 답변"


@pytest.mark.asyncio
async def test_transform_empty_result_falls_back_to_agent():
    """변환 실패(charts=[]) → 일반 경로 폴백."""
    transformer = AsyncMock()
    transformer.transform.return_value = ChartTransformResult(charts=[], message="")
    uc, mocks = _make_use_case(
        history=_history_with_chart(), chart_transformer=transformer,
    )
    req = GeneralChatRequest(
        user_id="u1", session_id="s1", message="해당 그래프 색 바꿔줘",
    )
    resp = await uc.execute(req, request_id="req-1")

    mocks["agent"].ainvoke.assert_called_once()
    assert resp.answer == "에이전트 답변"


@pytest.mark.asyncio
async def test_transform_exception_falls_back_to_agent():
    """transformer 예외 → 일반 경로 폴백 (graceful)."""
    transformer = AsyncMock()
    transformer.transform.side_effect = RuntimeError("boom")
    uc, mocks = _make_use_case(
        history=_history_with_chart(), chart_transformer=transformer,
    )
    req = GeneralChatRequest(
        user_id="u1", session_id="s1", message="해당 그래프 색 바꿔줘",
    )
    resp = await uc.execute(req, request_id="req-1")

    mocks["agent"].ainvoke.assert_called_once()
    assert resp.answer == "에이전트 답변"


@pytest.mark.asyncio
async def test_no_transformer_injected_keeps_legacy_behavior():
    """transformer 미주입(하위호환) → 편집 의도여도 일반 경로."""
    uc, mocks = _make_use_case(history=_history_with_chart())
    req = GeneralChatRequest(
        user_id="u1", session_id="s1", message="해당 그래프 색 바꿔줘",
    )
    resp = await uc.execute(req, request_id="req-1")

    mocks["agent"].ainvoke.assert_called_once()
    assert resp.answer == "에이전트 답변"


@pytest.mark.asyncio
async def test_new_chart_request_goes_normal_path():
    """신규 차트 생성 요청 → 편집 분기 미진입 (기존 빌더 경로)."""
    transformer = AsyncMock()
    uc, mocks = _make_use_case(
        history=_history_with_chart(), chart_transformer=transformer,
    )
    req = GeneralChatRequest(
        user_id="u1", session_id="s1", message="월별 매출 그래프 그려줘",
    )
    await uc.execute(req, request_id="req-1")

    transformer.transform.assert_not_called()
    mocks["agent"].ainvoke.assert_called_once()
