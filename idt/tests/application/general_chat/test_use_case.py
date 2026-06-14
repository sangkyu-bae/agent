"""GeneralChatUseCase tests (AsyncMock)."""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.application.general_chat.use_case import GeneralChatUseCase
from src.domain.conversation.entities import ConversationMessage
from src.domain.conversation.value_objects import AgentId, MessageRole, SessionId, TurnIndex, UserId
from src.domain.general_chat.schemas import DocumentSource, GeneralChatRequest
from src.domain.llm.interfaces import LLMFactoryInterface
from src.domain.llm_model.entity import LlmModel


def _make_llm_model() -> LlmModel:
    return LlmModel(
        id="test-id", provider="openai", model_name="gpt-4o",
        display_name="GPT-4o", description=None, api_key_env="OPENAI_API_KEY",
        max_tokens=128000, is_active=True, is_default=True,
        created_at=datetime(2026, 1, 1), updated_at=datetime(2026, 1, 1),
    )


# ── helpers ─────────────────────────────────────────────────────────────────

def _make_msg(role: MessageRole, content: str, turn: int) -> ConversationMessage:
    return ConversationMessage(
        id=None,
        user_id=UserId("u1"),
        session_id=SessionId("s1"),
        agent_id=AgentId.super(),
        role=role,
        content=content,
        turn_index=TurnIndex(turn),
        created_at=datetime.utcnow(),
    )


def _make_use_case(
    history: list[ConversationMessage] | None = None,
    summary_text: str | None = None,
    agent_messages: list | None = None,
) -> tuple[GeneralChatUseCase, dict]:
    """모든 의존성을 AsyncMock으로 구성한 UseCase 반환."""
    mock_tool_builder = AsyncMock()
    mock_tool_builder.build.return_value = []

    mock_msg_repo = AsyncMock()
    mock_msg_repo.find_by_session.return_value = history or []
    mock_msg_repo.save.return_value = MagicMock()

    mock_summarizer = AsyncMock()
    mock_summarizer.summarize.return_value = summary_text or "요약 내용"

    mock_summary_repo = AsyncMock()
    mock_summary_repo.save.return_value = MagicMock()
    mock_summary_repo.find_latest.return_value = None

    mock_policy = MagicMock()
    mock_policy.SUMMARIZATION_THRESHOLD = 6
    mock_policy.RECENT_TURNS_CONTEXT = 3
    mock_policy.needs_summarization = MagicMock(return_value=False)

    mock_logger = MagicMock()

    mock_llm_factory = MagicMock(spec=LLMFactoryInterface)
    mock_llm_factory.create.return_value = MagicMock()

    default_messages = agent_messages or [AIMessage(content="에이전트 답변")]

    mock_agent = AsyncMock()
    mock_agent.ainvoke.return_value = {"messages": default_messages}

    # ws-chat-streaming Design §4.1: stream() uses astream_events(version="v2").
    # 기존 ainvoke 기반 테스트 호환을 위해 astream_events가 내부적으로 ainvoke를
    # 호출(side_effect/return_value 모두 그대로 동작)하고 결과를 단일
    # on_chain_end 이벤트로 yield 하도록 헬퍼 fixture 패턴 적용.
    async def _fake_astream_events(input_dict, version=None):
        result = await mock_agent.ainvoke(input_dict)
        yield {"event": "on_chain_end", "data": {"output": result}, "name": "agent"}

    mock_agent.astream_events = _fake_astream_events

    mocks = {
        "tool_builder": mock_tool_builder,
        "msg_repo": mock_msg_repo,
        "summarizer": mock_summarizer,
        "summary_repo": mock_summary_repo,
        "policy": mock_policy,
        "logger": mock_logger,
        "agent": mock_agent,
        "llm_factory": mock_llm_factory,
    }

    uc = GeneralChatUseCase(
        chat_tool_builder=mock_tool_builder,
        message_repo=mock_msg_repo,
        summary_repo=mock_summary_repo,
        summarizer=mock_summarizer,
        summarization_policy=mock_policy,
        logger=mock_logger,
        llm_factory=mock_llm_factory,
        llm_model=_make_llm_model(),
    )
    # agent 주입을 위해 _create_agent 패치
    uc._create_agent = MagicMock(return_value=mock_agent)

    return uc, mocks


# ── TC 1-12 ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_none_session_id_generates_uuid():
    """TC-1: session_id=None → uuid4 신규 발급 (str 타입)."""
    uc, _ = _make_use_case()
    req = GeneralChatRequest(user_id="u1", session_id=None, message="안녕")
    resp = await uc.execute(req, request_id="req-1")
    assert isinstance(resp.session_id, str)
    assert len(resp.session_id) > 0


@pytest.mark.asyncio
async def test_history_retrieved_and_context_built():
    """TC-2: 히스토리 조회 후 컨텍스트 구성 — find_by_session 호출 확인."""
    history = [
        _make_msg(MessageRole.USER, "이전 질문", 1),
        _make_msg(MessageRole.ASSISTANT, "이전 답변", 2),
    ]
    uc, mocks = _make_use_case(history=history)
    req = GeneralChatRequest(user_id="u1", session_id="s1", message="새 질문")
    await uc.execute(req, request_id="req-1")
    mocks["msg_repo"].find_by_session.assert_called_once()


@pytest.mark.asyncio
async def test_no_summarization_below_threshold():
    """TC-3: 6턴 이하 → 요약 미실행."""
    history = [_make_msg(MessageRole.USER, f"메시지{i}", i) for i in range(1, 5)]
    uc, mocks = _make_use_case(history=history)
    mocks["policy"].needs_summarization = MagicMock(return_value=False)

    req = GeneralChatRequest(user_id="u1", session_id="s1", message="질문")
    await uc.execute(req, request_id="req-1")
    mocks["summarizer"].summarize.assert_not_called()


@pytest.mark.asyncio
async def test_summarization_triggered_above_threshold():
    """TC-4: 6턴 초과 → 요약 실행 + summary_repo.save 호출."""
    history = [_make_msg(MessageRole.USER, f"메시지{i}", i) for i in range(1, 8)]
    uc, mocks = _make_use_case(history=history)
    mocks["policy"].needs_summarization = MagicMock(return_value=True)
    mocks["policy"].get_turns_to_summarize = MagicMock(return_value=history[:4])
    mocks["policy"].get_summary_range = MagicMock(
        return_value=(TurnIndex(1), TurnIndex(4))
    )
    mocks["policy"].get_recent_turns = MagicMock(return_value=history[-3:])

    req = GeneralChatRequest(user_id="u1", session_id="s1", message="질문")
    await uc.execute(req, request_id="req-1")
    mocks["summarizer"].summarize.assert_called_once()
    mocks["summary_repo"].save.assert_called_once()


@pytest.mark.asyncio
async def test_summarized_context_has_system_message_and_recent_turns():
    """TC-5: 요약 후 컨텍스트 = SystemMessage(요약) + 최근 3턴 + 새 메시지."""
    history = [_make_msg(MessageRole.USER, f"메시지{i}", i) for i in range(1, 8)]
    recent = history[-3:]
    uc, mocks = _make_use_case(history=history, summary_text="이전 요약")
    mocks["policy"].needs_summarization = MagicMock(return_value=True)
    mocks["policy"].get_turns_to_summarize = MagicMock(return_value=history[:4])
    mocks["policy"].get_summary_range = MagicMock(
        return_value=(TurnIndex(1), TurnIndex(4))
    )
    mocks["policy"].get_recent_turns = MagicMock(return_value=recent)

    captured_messages = []

    async def capture_invoke(input_dict):
        captured_messages.extend(input_dict["messages"])
        return {"messages": [AIMessage(content="답변")]}

    mocks["agent"].ainvoke.side_effect = capture_invoke

    req = GeneralChatRequest(user_id="u1", session_id="s1", message="새 질문")
    await uc.execute(req, request_id="req-1")

    from langchain_core.messages import SystemMessage
    assert any(isinstance(m, SystemMessage) for m in captured_messages)
    # SystemMessage + 최근 3턴 + 새 HumanMessage = 5개
    assert len(captured_messages) == 5


@pytest.mark.asyncio
async def test_react_agent_ainvoke_called():
    """TC-6: ReAct 에이전트 ainvoke 호출 확인."""
    uc, mocks = _make_use_case()
    mocks["policy"].needs_summarization = MagicMock(return_value=False)
    req = GeneralChatRequest(user_id="u1", session_id="s1", message="질문")
    await uc.execute(req, request_id="req-1")
    mocks["agent"].ainvoke.assert_called_once()


@pytest.mark.asyncio
async def test_tools_used_parsed_from_tool_messages():
    """TC-7: tools_used = ToolMessage에서 도구명 목록 추출."""
    tool_msg = ToolMessage(content="검색 결과", tool_call_id="tc1", name="tavily_search")
    ai_msg = AIMessage(content="최종 답변")
    uc, mocks = _make_use_case(agent_messages=[tool_msg, ai_msg])
    mocks["policy"].needs_summarization = MagicMock(return_value=False)

    req = GeneralChatRequest(user_id="u1", session_id="s1", message="질문")
    resp = await uc.execute(req, request_id="req-1")
    assert "tavily_search" in resp.tools_used


@pytest.mark.asyncio
async def test_sources_parsed_from_internal_doc_tool():
    """TC-8: sources = InternalDocumentSearchTool.collected_sources."""
    source = DocumentSource(content="내용", source="doc.pdf", chunk_id="c1", score=0.9)
    mock_internal_tool = MagicMock()
    mock_internal_tool.name = "internal_document_search"
    mock_internal_tool.top_k = 5
    mock_internal_tool.collected_sources = [source]

    uc, mocks = _make_use_case()
    # builder가 internal tool을 반환하도록 설정
    mocks["tool_builder"].build.return_value = [mock_internal_tool]
    mocks["policy"].needs_summarization = MagicMock(return_value=False)

    req = GeneralChatRequest(user_id="u1", session_id="s1", message="질문")
    resp = await uc.execute(req, request_id="req-1")
    assert len(resp.sources) == 1
    assert resp.sources[0].source == "doc.pdf"


@pytest.mark.asyncio
async def test_user_message_saved_to_db():
    """TC-9: 사용자 메시지 DB 저장 확인 — message_repo.save 호출."""
    uc, mocks = _make_use_case()
    mocks["policy"].needs_summarization = MagicMock(return_value=False)
    req = GeneralChatRequest(user_id="u1", session_id="s1", message="질문")
    await uc.execute(req, request_id="req-1")
    # 사용자 메시지 + AI 응답 총 2번 save 호출
    assert mocks["msg_repo"].save.call_count == 2


@pytest.mark.asyncio
async def test_ai_response_saved_to_db():
    """TC-10: AI 응답 DB 저장 확인 — message_repo.save 두 번째 호출."""
    uc, mocks = _make_use_case()
    mocks["policy"].needs_summarization = MagicMock(return_value=False)
    req = GeneralChatRequest(user_id="u1", session_id="s1", message="질문")
    await uc.execute(req, request_id="req-1")
    calls = mocks["msg_repo"].save.call_args_list
    # 두 번째 호출의 인자에서 role 확인
    saved_ai_msg = calls[1][0][0]
    assert saved_ai_msg.role == MessageRole.ASSISTANT


@pytest.mark.asyncio
async def test_was_summarized_true_when_summary_occurred():
    """TC-11: 요약 발생 시 was_summarized=True 반환."""
    history = [_make_msg(MessageRole.USER, f"메시지{i}", i) for i in range(1, 8)]
    uc, mocks = _make_use_case(history=history)
    mocks["policy"].needs_summarization = MagicMock(return_value=True)
    mocks["policy"].get_turns_to_summarize = MagicMock(return_value=history[:4])
    mocks["policy"].get_summary_range = MagicMock(
        return_value=(TurnIndex(1), TurnIndex(4))
    )
    mocks["policy"].get_recent_turns = MagicMock(return_value=history[-3:])

    req = GeneralChatRequest(user_id="u1", session_id="s1", message="질문")
    resp = await uc.execute(req, request_id="req-1")
    assert resp.was_summarized is True


@pytest.mark.asyncio
async def test_agent_exception_logs_error_and_reraises():
    """TC-12: 에이전트 예외 시 ERROR 로그 + 재발생."""
    uc, mocks = _make_use_case()
    mocks["policy"].needs_summarization = MagicMock(return_value=False)
    mocks["agent"].ainvoke.side_effect = RuntimeError("에이전트 오류")

    req = GeneralChatRequest(user_id="u1", session_id="s1", message="질문")
    with pytest.raises(RuntimeError):
        await uc.execute(req, request_id="req-1")
    mocks["logger"].error.assert_called_once()


def test_system_prompt_contains_context_instruction():
    """TC-15: _SYSTEM_PROMPT에 '이전 대화' 지시가 포함된다."""
    from src.application.general_chat.use_case import _SYSTEM_PROMPT
    assert "이전 대화" in _SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_second_message_includes_history_in_context():
    """TC-14: 히스토리 2개(USER+ASSISTANT)가 있을 때 에이전트 입력에 포함된다."""
    history = [
        _make_msg(MessageRole.USER, "첫 질문", 1),
        _make_msg(MessageRole.ASSISTANT, "첫 답변", 2),
    ]
    uc, mocks = _make_use_case(history=history)
    mocks["policy"].needs_summarization = MagicMock(return_value=False)

    captured = []

    async def capture(input_dict):
        captured.extend(input_dict["messages"])
        return {"messages": [AIMessage(content="두 번째 답변")]}

    mocks["agent"].ainvoke.side_effect = capture

    req = GeneralChatRequest(user_id="u1", session_id="s1", message="두 번째 질문")
    await uc.execute(req, request_id="req-1")

    # HumanMessage("첫 질문") + AIMessage("첫 답변") + HumanMessage("두 번째 질문") = 3개
    assert len(captured) == 3
    assert isinstance(captured[0], HumanMessage)
    assert captured[0].content == "첫 질문"


# agent-chat-reasoning-display Design §4.1
class TestChatStepReasoning:
    """on_chat_model_end + tool_calls + content → STEP_REASONING 이벤트."""

    @staticmethod
    def _install_chat_astream(mock_agent, *, ai_message_with_tool_calls):
        async def _fake(input_dict, version=None):
            # on_chat_model_end (tool_calls 동반 AI 메시지)
            yield {
                "event": "on_chat_model_end",
                "name": "ChatOpenAI",
                "data": {"output": ai_message_with_tool_calls},
                "metadata": {},
                "run_id": "lm-1",
            }
            # 최종 chain_end (final messages)
            yield {
                "event": "on_chain_end",
                "name": "agent",
                "data": {"output": {"messages": [
                    AIMessage(content="최종 답변", tool_calls=[])
                ]}},
                "metadata": {},
            }
        mock_agent.astream_events = _fake

    @pytest.mark.asyncio
    async def test_reasoning_emitted_when_tool_calls_and_content(self):
        """T3 — tool_calls + content가 모두 있는 AI 메시지에서 STEP_REASONING 발행."""
        from src.domain.general_chat.value_objects import ChatEventType

        uc, mocks = _make_use_case()
        ai_msg = AIMessage(
            content="RAG 검색이 필요해서 호출합니다.",
            tool_calls=[{"name": "rag_search", "args": {"q": "x"}, "id": "t1"}],
        )
        self._install_chat_astream(mocks["agent"], ai_message_with_tool_calls=ai_msg)

        events = []
        req = GeneralChatRequest(user_id="u1", session_id="s1", message="질문")
        async for ev in uc.stream(req, request_id="req-1"):
            events.append(ev)

        types = [ev.event_type for ev in events]
        assert ChatEventType.STEP_REASONING in types

        reasoning_ev = next(
            e for e in events if e.event_type == ChatEventType.STEP_REASONING
        )
        assert reasoning_ev.payload["step_name"] == "chat_agent"
        assert reasoning_ev.payload["reasoning"] == "RAG 검색이 필요해서 호출합니다."
        assert reasoning_ev.payload["tool_calls"] == ["rag_search"]

    @pytest.mark.asyncio
    async def test_no_reasoning_when_no_tool_calls(self):
        """T4 — tool_calls가 비어있으면 STEP_REASONING 미발행."""
        from src.domain.general_chat.value_objects import ChatEventType

        uc, mocks = _make_use_case()
        ai_msg = AIMessage(content="그냥 일반 응답", tool_calls=[])
        self._install_chat_astream(mocks["agent"], ai_message_with_tool_calls=ai_msg)

        events = []
        req = GeneralChatRequest(user_id="u1", session_id="s1", message="질문")
        async for ev in uc.stream(req, request_id="req-1"):
            events.append(ev)

        types = [ev.event_type for ev in events]
        assert ChatEventType.STEP_REASONING not in types

    @pytest.mark.asyncio
    async def test_no_reasoning_when_content_empty(self):
        """T5 — tool_calls만 있고 content가 비어있으면 STEP_REASONING 미발행."""
        from src.domain.general_chat.value_objects import ChatEventType

        uc, mocks = _make_use_case()
        ai_msg = AIMessage(
            content="",
            tool_calls=[{"name": "rag_search", "args": {}, "id": "t1"}],
        )
        self._install_chat_astream(mocks["agent"], ai_message_with_tool_calls=ai_msg)

        events = []
        req = GeneralChatRequest(user_id="u1", session_id="s1", message="질문")
        async for ev in uc.stream(req, request_id="req-1"):
            events.append(ev)

        types = [ev.event_type for ev in events]
        assert ChatEventType.STEP_REASONING not in types


class TestChatTokenContentNormalization:
    """on_chat_model_stream chunk.content가 block 리스트일 때 평탄화 문자열로 발행.

    FIX-CHAT-REASONING-OBJECT-RENDER: list가 그대로 실리면 프론트에서 [object Object]가 됨.
    """

    @staticmethod
    def _install_token_astream(mock_agent, *, chunk_content):
        chunk = MagicMock()
        chunk.content = chunk_content

        async def _fake(input_dict, version=None):
            yield {
                "event": "on_chat_model_stream",
                "name": "ChatAnthropic",
                "data": {"chunk": chunk},
                "metadata": {},
                "run_id": "lm-1",
            }
            yield {
                "event": "on_chain_end",
                "name": "agent",
                "data": {"output": {"messages": [AIMessage(content="끝", tool_calls=[])]}},
                "metadata": {},
            }
        mock_agent.astream_events = _fake

    @pytest.mark.asyncio
    async def test_content_block_list_flattened(self):
        from src.domain.general_chat.value_objects import ChatEventType

        uc, mocks = _make_use_case()
        self._install_token_astream(
            mocks["agent"],
            chunk_content=[{"type": "text", "text": "안"}, {"type": "text", "text": "녕"}],
        )

        events = []
        req = GeneralChatRequest(user_id="u1", session_id="s1", message="질문")
        async for ev in uc.stream(req, request_id="req-1"):
            events.append(ev)

        tokens = [e for e in events if e.event_type == ChatEventType.TOKEN]
        assert len(tokens) == 1
        assert tokens[0].payload["chunk"] == "안녕"
        assert isinstance(tokens[0].payload["chunk"], str)

    @pytest.mark.asyncio
    async def test_content_block_list_without_text_skipped(self):
        from src.domain.general_chat.value_objects import ChatEventType

        uc, mocks = _make_use_case()
        self._install_token_astream(
            mocks["agent"],
            chunk_content=[{"type": "tool_use", "id": "t1", "name": "rag_search"}],
        )

        events = []
        req = GeneralChatRequest(user_id="u1", session_id="s1", message="질문")
        async for ev in uc.stream(req, request_id="req-1"):
            events.append(ev)

        tokens = [e for e in events if e.event_type == ChatEventType.TOKEN]
        assert len(tokens) == 0


# ── chat-chart-persistence: 차트 영속화 (Design §3-6 D4) ────────────────────


class TestChartsPersistence:
    """차트 생성 → 저장 순서 + assistant 메시지 charts 영속화."""

    @staticmethod
    def _enable_charts(uc, charts: list[dict] | None = None, build_raises: bool = False):
        """viz 의존성 주입: 항상 visualize 판정 + chart_builder mock."""
        uc._viz_policy = MagicMock()
        uc._viz_policy.decide = MagicMock(return_value="visualize")
        builder = AsyncMock()
        if build_raises:
            builder.build.side_effect = RuntimeError("chart build boom")
        else:
            cfgs = []
            for c in charts or []:
                cfg = MagicMock()
                cfg.model_dump = MagicMock(return_value=c)
                cfgs.append(cfg)
            builder.build.return_value = cfgs
        uc._chart_builder = builder

    @staticmethod
    def _saved_by_role(mocks, role: MessageRole):
        return [
            call[0][0]
            for call in mocks["msg_repo"].save.call_args_list
            if call[0][0].role == role
        ]

    @pytest.mark.asyncio
    async def test_assistant_message_saved_with_charts(self):
        """차트 생성 런 → 저장된 assistant 메시지에 charts 반영 (순서: 차트 → 저장)."""
        charts = [{"type": "bar"}, {"type": "line"}]
        uc, mocks = _make_use_case()
        self._enable_charts(uc, charts=charts)

        req = GeneralChatRequest(user_id="u1", session_id="s1", message="그래프 그려줘")
        await uc.execute(req, request_id="req-1")

        saved = self._saved_by_role(mocks, MessageRole.ASSISTANT)
        assert len(saved) == 1
        assert saved[0].charts == charts

    @pytest.mark.asyncio
    async def test_user_message_saved_without_charts(self):
        """user 메시지는 항상 charts=None (D8)."""
        uc, mocks = _make_use_case()
        self._enable_charts(uc, charts=[{"type": "bar"}])

        req = GeneralChatRequest(user_id="u1", session_id="s1", message="그래프 그려줘")
        await uc.execute(req, request_id="req-1")

        saved = self._saved_by_role(mocks, MessageRole.USER)
        assert len(saved) == 1
        assert saved[0].charts is None

    @pytest.mark.asyncio
    async def test_message_saved_with_none_when_no_charts(self):
        """차트 미생성(빌더 미주입) → charts=None 저장 (D2)."""
        uc, mocks = _make_use_case()

        req = GeneralChatRequest(user_id="u1", session_id="s1", message="질문")
        await uc.execute(req, request_id="req-1")

        saved = self._saved_by_role(mocks, MessageRole.ASSISTANT)
        assert len(saved) == 1
        assert saved[0].charts is None

    @pytest.mark.asyncio
    async def test_chart_build_failure_does_not_block_persist(self):
        """차트 빌드 실패 → graceful []: 메시지는 charts=None으로 정상 저장."""
        uc, mocks = _make_use_case()
        self._enable_charts(uc, build_raises=True)

        req = GeneralChatRequest(user_id="u1", session_id="s1", message="그래프 그려줘")
        resp = await uc.execute(req, request_id="req-1")

        assert resp.answer  # 본 흐름 정상 완료
        saved = self._saved_by_role(mocks, MessageRole.ASSISTANT)
        assert len(saved) == 1
        assert saved[0].charts is None

    @pytest.mark.asyncio
    async def test_charts_not_injected_into_llm_context(self):
        """D7-rev1: full config(JSON)는 미투입, 캡션 1줄만 투입.

        chart-context-continuity Design §3.2 — 기존 D7(전면 미투입)을
        "캡션 허용"으로 개정. raw JSON 키는 여전히 컨텍스트에 없어야 한다.
        """
        history_msg = ConversationMessage(
            id=None, user_id=UserId("u1"), session_id=SessionId("s1"),
            agent_id=AgentId.super(), role=MessageRole.ASSISTANT,
            content="차트 답변", turn_index=TurnIndex(2),
            created_at=datetime.utcnow(),
            charts=[{"type": "bar", "data": {"labels": ["a"]}}],
        )
        history = [_make_msg(MessageRole.USER, "차트 그려줘", 1), history_msg]
        uc, mocks = _make_use_case(history=history)

        captured = []

        async def capture(input_dict):
            captured.extend(input_dict["messages"])
            return {"messages": [AIMessage(content="후속 답변")]}

        mocks["agent"].ainvoke.side_effect = capture

        req = GeneralChatRequest(user_id="u1", session_id="s1", message="후속 질문")
        await uc.execute(req, request_id="req-1")

        joined = " ".join(str(getattr(m, "content", "")) for m in captured)
        assert '"type"' not in joined       # 차트 raw JSON 미투입 (D7-rev1 유지)
        assert "datasets" not in joined     # full config 미투입
        assert "[생성된 차트:" in joined     # 캡션 1줄은 투입 (D7-rev1)
        assert "차트 답변" in joined         # content는 정상 투입


def test_create_agent_passes_system_prompt():
    """TC-13: _create_agent()가 create_react_agent에 prompt=_SYSTEM_PROMPT를 전달한다."""
    from src.application.general_chat.use_case import _SYSTEM_PROMPT

    mock_factory = MagicMock(spec=LLMFactoryInterface)
    mock_factory.create.return_value = MagicMock()

    with patch("src.application.general_chat.use_case.create_react_agent") as mock_create:
        mock_create.return_value = MagicMock()
        uc = GeneralChatUseCase(
            chat_tool_builder=MagicMock(),
            message_repo=AsyncMock(),
            summary_repo=AsyncMock(),
            summarizer=AsyncMock(),
            summarization_policy=MagicMock(),
            logger=MagicMock(),
            llm_factory=mock_factory,
            llm_model=_make_llm_model(),
        )
        uc._create_agent(tools=[])
        mock_create.assert_called_once()
        _, kwargs = mock_create.call_args
        assert kwargs.get("prompt") == _SYSTEM_PROMPT
