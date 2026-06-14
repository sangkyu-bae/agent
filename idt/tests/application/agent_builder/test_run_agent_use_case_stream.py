"""RunAgentUseCase.stream() 단위 테스트.

Design §5.2.2 (agent-run-streaming-sse). LangGraph astream_events(v2) 기반
transport-독립 이벤트 스트림.

Sub-step coverage (Design §11):
- 4-1 happy path (RUN_STARTED, ANSWER_COMPLETED, RUN_COMPLETED, seq)
- 4-2 NODE_STARTED/COMPLETED 매핑
- 4-3 TOOL_STARTED/COMPLETED 매핑
- 4-4 TOKEN 매핑 (on_chat_model_stream)
- 4-5 RUN_FAILED + tracker.fail_run
- 4-6 CancelledError 분기
"""
import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_builder.run_agent_use_case import RunAgentUseCase
from src.application.agent_builder.schemas import RunAgentRequest
from src.application.agent_run.tracker import RunTracker
from src.domain.agent_builder.schemas import AgentDefinition, WorkerDefinition
from src.domain.agent_run.value_objects import (
    AgentRunEvent,
    AgentRunEventType,
)
from src.domain.conversation.policies import SummarizationPolicy
from src.domain.llm_model.entity import LlmModel


# ── Fixtures ────────────────────────────────────────────────────────────


def _make_llm_model() -> LlmModel:
    now = datetime.now(timezone.utc)
    return LlmModel(
        id="model-1",
        provider="openai",
        model_name="gpt-4o-mini",
        display_name="GPT-4o Mini",
        description=None,
        api_key_env="OPENAI_API_KEY",
        max_tokens=128000,
        is_active=True,
        is_default=True,
        created_at=now,
        updated_at=now,
    )


def _make_agent() -> AgentDefinition:
    now = datetime.now(timezone.utc)
    return AgentDefinition(
        id=str(uuid.uuid4()),
        user_id="user-1",
        name="테스트 에이전트",
        description="설명",
        system_prompt="시스템 프롬프트",
        flow_hint="힌트",
        workers=[WorkerDefinition("tavily_search", "search_worker", "검색", 0)],
        llm_model_id="model-1",
        status="active",
        created_at=now,
        updated_at=now,
    )


def _ai_message(content: str, name: str | None = None):
    """Final messages는 _parse_result가 getattr(m, 'name', None)을 검사하므로
    real AIMessage 대신 단순 namespace 객체로도 충분하다.
    """
    m = MagicMock()
    m.content = content
    m.name = name
    return m


def _fake_astream(events: list[dict]):
    """async generator → graph.astream_events(...) 대체."""
    async def _gen(*args, **kwargs):
        for e in events:
            yield e
    return _gen


def _make_tracker():
    tracker = MagicMock(spec=RunTracker)
    tracker.start_run = AsyncMock()
    tracker.complete_run = AsyncMock()
    tracker.fail_run = AsyncMock()
    return tracker


def _make_stream_use_case(
    astream_event_list: list[dict] | None = None,
    astream_raises: Exception | None = None,
    final_messages: list | None = None,
    with_tracker: bool = True,
):
    """stream() 테스트용 RunAgentUseCase 팩토리.

    - astream_event_list: graph.astream_events가 yield할 이벤트 시퀀스
    - astream_raises: 지정 시 첫 anext에서 예외 발생
    - final_messages: 최종 graph state.messages — top-level on_chain_end로 흘려보냄
    """
    repository = MagicMock()
    llm_model_repository = MagicMock()
    compiler = MagicMock()
    logger = MagicMock()
    message_repo = MagicMock()
    summary_repo = MagicMock()
    summarizer = MagicMock()
    policy = SummarizationPolicy()
    tracker = _make_tracker() if with_tracker else None

    agent = _make_agent()
    repository.find_by_id = AsyncMock(return_value=agent)
    llm_model_repository.find_by_id = AsyncMock(return_value=_make_llm_model())

    message_repo.find_by_session = AsyncMock(return_value=[])
    saved_msg = MagicMock()
    saved_msg.id.value = 42
    message_repo.save = AsyncMock(return_value=saved_msg)
    summary_repo.find_latest_by_session = AsyncMock(return_value=None)
    summary_repo.save = AsyncMock()
    summarizer.summarize = AsyncMock(return_value="요약")

    # 이벤트 시퀀스 마지막에 top-level on_chain_end 자동 추가 (final state)
    base_events = list(astream_event_list) if astream_event_list else []
    fm = final_messages if final_messages is not None else [_ai_message("기본 답변")]
    base_events.append({
        "event": "on_chain_end",
        "name": "LangGraph",  # top-level chain name (not in node_names)
        "data": {"output": {"messages": fm}},
        "metadata": {},
        "run_id": "top-level",
    })

    mock_graph = MagicMock()
    if astream_raises is not None:
        def _raising(*args, **kwargs):
            async def _g():
                raise astream_raises
                yield  # unreachable, makes function a generator
            return _g()
        mock_graph.astream_events = _raising
    else:
        mock_graph.astream_events = _fake_astream(base_events)
    compiler.compile = AsyncMock(return_value=mock_graph)

    use_case = RunAgentUseCase(
        repository=repository,
        llm_model_repository=llm_model_repository,
        compiler=compiler,
        logger=logger,
        message_repo=message_repo,
        summary_repo=summary_repo,
        summarizer=summarizer,
        policy=policy,
        tracker=tracker,
    )
    return use_case, agent, tracker, mock_graph, compiler


async def _collect(stream) -> list[AgentRunEvent]:
    out: list[AgentRunEvent] = []
    async for ev in stream:
        out.append(ev)
    return out


# ── final-answer-node TC-O01: 노드명 수집 ────────────────────────────────


class TestCollectNodeNames:
    """final-answer-node Design §5-5 TC-O01: _collect_node_names가 final_answer 포함."""

    def test_includes_final_answer_excludes_answer_agent(self):
        from src.application.agent_builder.run_agent_use_case import (
            _collect_node_names,
        )

        names = _collect_node_names(_make_agent().to_workflow_definition())
        assert "final_answer" in names
        assert "answer_agent" not in names
        assert "supervisor" in names
        assert "quality_gate" in names
        assert "search_worker" in names


# ── 4-1 Happy Path ─────────────────────────────────────────────────────


class TestStreamHappyPath:
    @pytest.mark.asyncio
    async def test_first_event_is_run_started(self):
        use_case, agent, _, _, _ = _make_stream_use_case(astream_event_list=[])
        request = RunAgentRequest(query="안녕", user_id="user-1")

        events = await _collect(use_case.stream(agent.id, request, "req-1"))

        assert events[0].event_type == AgentRunEventType.RUN_STARTED
        assert events[0].payload["agent_id"] == agent.id
        assert events[0].payload["session_id"]  # auto-generated UUID

    @pytest.mark.asyncio
    async def test_last_event_is_run_completed(self):
        use_case, agent, _, _, _ = _make_stream_use_case(astream_event_list=[])
        request = RunAgentRequest(query="안녕", user_id="user-1")

        events = await _collect(use_case.stream(agent.id, request, "req-1"))

        assert events[-1].event_type == AgentRunEventType.RUN_COMPLETED

    @pytest.mark.asyncio
    async def test_answer_completed_precedes_run_completed(self):
        use_case, agent, _, _, _ = _make_stream_use_case(
            astream_event_list=[],
            final_messages=[_ai_message("최종 답변입니다")],
        )
        request = RunAgentRequest(query="안녕", user_id="user-1")

        events = await _collect(use_case.stream(agent.id, request, "req-1"))

        answer_idx = next(
            i for i, e in enumerate(events)
            if e.event_type == AgentRunEventType.ANSWER_COMPLETED
        )
        completed_idx = next(
            i for i, e in enumerate(events)
            if e.event_type == AgentRunEventType.RUN_COMPLETED
        )
        assert answer_idx < completed_idx
        assert events[answer_idx].payload["answer"] == "최종 답변입니다"

    @pytest.mark.asyncio
    async def test_seq_is_monotonic_starting_from_one(self):
        use_case, agent, _, _, _ = _make_stream_use_case(astream_event_list=[])
        request = RunAgentRequest(query="안녕", user_id="user-1")

        events = await _collect(use_case.stream(agent.id, request, "req-1"))

        seqs = [e.seq for e in events]
        assert seqs[0] == 1
        assert seqs == sorted(seqs)
        assert all(b - a == 1 for a, b in zip(seqs, seqs[1:]))

    @pytest.mark.asyncio
    async def test_tracker_start_run_called_before_first_yield(self):
        use_case, agent, tracker, _, _ = _make_stream_use_case(astream_event_list=[])
        request = RunAgentRequest(query="안녕", user_id="user-1")

        events = await _collect(use_case.stream(agent.id, request, "req-1"))

        tracker.start_run.assert_awaited_once()
        # RUN_STARTED payload의 run_id != None (tracker 활성)
        assert events[0].payload["run_id"] is not None

    @pytest.mark.asyncio
    async def test_tracker_complete_run_called_on_success(self):
        use_case, agent, tracker, _, _ = _make_stream_use_case(astream_event_list=[])
        request = RunAgentRequest(query="안녕", user_id="user-1")

        await _collect(use_case.stream(agent.id, request, "req-1"))

        tracker.complete_run.assert_awaited_once()
        tracker.fail_run.assert_not_called()

    @pytest.mark.asyncio
    async def test_session_id_auto_generated_when_none(self):
        use_case, agent, _, _, _ = _make_stream_use_case(astream_event_list=[])
        request = RunAgentRequest(query="x", user_id="user-1", session_id=None)

        events = await _collect(use_case.stream(agent.id, request, "req-1"))

        sid = events[0].payload["session_id"]
        uuid.UUID(sid)  # raises if not a valid UUID

    @pytest.mark.asyncio
    async def test_session_id_preserved_when_provided(self):
        use_case, agent, _, _, _ = _make_stream_use_case(astream_event_list=[])
        sid = str(uuid.uuid4())
        request = RunAgentRequest(query="x", user_id="user-1", session_id=sid)

        events = await _collect(use_case.stream(agent.id, request, "req-1"))

        assert events[0].payload["session_id"] == sid


# ── 4-2 Node Events ────────────────────────────────────────────────────


class TestStreamNodeEvents:
    @pytest.mark.asyncio
    async def test_on_chain_start_for_registered_node_yields_node_started(self):
        events_in = [
            {"event": "on_chain_start", "name": "supervisor",
             "data": {}, "metadata": {}, "run_id": "r1"},
        ]
        use_case, agent, _, _, _ = _make_stream_use_case(astream_event_list=events_in)
        request = RunAgentRequest(query="x", user_id="user-1")

        events = await _collect(use_case.stream(agent.id, request, "req-1"))

        node_started = [e for e in events if e.event_type == AgentRunEventType.NODE_STARTED]
        assert len(node_started) == 1
        assert node_started[0].payload["node_name"] == "supervisor"
        assert node_started[0].payload["node_type"] == "SUPERVISOR"

    @pytest.mark.asyncio
    async def test_on_chain_end_for_registered_node_yields_node_completed(self):
        events_in = [
            {"event": "on_chain_start", "name": "search_worker",
             "data": {}, "metadata": {}, "run_id": "r1"},
            {"event": "on_chain_end", "name": "search_worker",
             "data": {"output": {"messages": []}}, "metadata": {}, "run_id": "r1"},
        ]
        use_case, agent, _, _, _ = _make_stream_use_case(astream_event_list=events_in)
        request = RunAgentRequest(query="x", user_id="user-1")

        events = await _collect(use_case.stream(agent.id, request, "req-1"))

        node_completed = [
            e for e in events if e.event_type == AgentRunEventType.NODE_COMPLETED
        ]
        assert len(node_completed) == 1
        assert node_completed[0].payload["node_name"] == "search_worker"
        assert "duration_ms" in node_completed[0].payload

    @pytest.mark.asyncio
    async def test_unregistered_chain_events_are_ignored(self):
        # LangGraph 내부 chain들은 노드 등록 이름이 아니므로 NODE_STARTED 미발행
        events_in = [
            {"event": "on_chain_start", "name": "RunnableSequence",
             "data": {}, "metadata": {}, "run_id": "r9"},
            {"event": "on_chain_end", "name": "RunnableSequence",
             "data": {"output": {}}, "metadata": {}, "run_id": "r9"},
        ]
        use_case, agent, _, _, _ = _make_stream_use_case(astream_event_list=events_in)
        request = RunAgentRequest(query="x", user_id="user-1")

        events = await _collect(use_case.stream(agent.id, request, "req-1"))

        node_events = [e for e in events if e.event_type in (
            AgentRunEventType.NODE_STARTED, AgentRunEventType.NODE_COMPLETED
        )]
        assert len(node_events) == 0

    @pytest.mark.asyncio
    async def test_node_type_for_worker_is_worker(self):
        events_in = [
            {"event": "on_chain_start", "name": "search_worker",
             "data": {}, "metadata": {}, "run_id": "r1"},
        ]
        use_case, agent, _, _, _ = _make_stream_use_case(astream_event_list=events_in)
        request = RunAgentRequest(query="x", user_id="user-1")

        events = await _collect(use_case.stream(agent.id, request, "req-1"))

        ns = next(e for e in events if e.event_type == AgentRunEventType.NODE_STARTED)
        assert ns.payload["node_type"] == "WORKER"


# ── 4-3 Tool Events ────────────────────────────────────────────────────


class TestStreamToolEvents:
    @pytest.mark.asyncio
    async def test_on_tool_start_yields_tool_started(self):
        events_in = [
            {"event": "on_tool_start", "name": "tavily_search",
             "data": {"input": {"query": "AI 뉴스"}},
             "metadata": {}, "run_id": "tc-1"},
        ]
        use_case, agent, _, _, _ = _make_stream_use_case(astream_event_list=events_in)
        request = RunAgentRequest(query="x", user_id="user-1")

        events = await _collect(use_case.stream(agent.id, request, "req-1"))

        tool_started = [e for e in events if e.event_type == AgentRunEventType.TOOL_STARTED]
        assert len(tool_started) == 1
        assert tool_started[0].payload["tool_name"] == "tavily_search"
        assert tool_started[0].payload["tool_call_id"] == "tc-1"
        assert "input_preview" in tool_started[0].payload

    @pytest.mark.asyncio
    async def test_on_tool_end_yields_tool_completed(self):
        events_in = [
            {"event": "on_tool_start", "name": "tavily_search",
             "data": {"input": {}}, "metadata": {}, "run_id": "tc-1"},
            {"event": "on_tool_end", "name": "tavily_search",
             "data": {"output": "검색 결과"},
             "metadata": {}, "run_id": "tc-1"},
        ]
        use_case, agent, _, _, _ = _make_stream_use_case(astream_event_list=events_in)
        request = RunAgentRequest(query="x", user_id="user-1")

        events = await _collect(use_case.stream(agent.id, request, "req-1"))

        tc = [e for e in events if e.event_type == AgentRunEventType.TOOL_COMPLETED]
        assert len(tc) == 1
        assert tc[0].payload["tool_name"] == "tavily_search"
        assert tc[0].payload["tool_call_id"] == "tc-1"
        assert "output_preview" in tc[0].payload
        assert "duration_ms" in tc[0].payload

    @pytest.mark.asyncio
    async def test_input_preview_truncated_to_1024(self):
        big = "x" * 5000
        events_in = [
            {"event": "on_tool_start", "name": "t1",
             "data": {"input": {"q": big}}, "metadata": {}, "run_id": "tc-2"},
        ]
        use_case, agent, _, _, _ = _make_stream_use_case(astream_event_list=events_in)
        request = RunAgentRequest(query="x", user_id="user-1")

        events = await _collect(use_case.stream(agent.id, request, "req-1"))

        ts = next(e for e in events if e.event_type == AgentRunEventType.TOOL_STARTED)
        assert len(ts.payload["input_preview"]) <= 1024


# ── 4-4 Token Events ───────────────────────────────────────────────────


class TestStreamTokenEvents:
    def _chunk_msg(self, content: str):
        chunk = MagicMock()
        chunk.content = content
        return chunk

    @pytest.mark.asyncio
    async def test_chat_model_stream_yields_token(self):
        events_in = [
            {"event": "on_chat_model_stream", "name": "ChatOpenAI",
             "data": {"chunk": self._chunk_msg("안")},
             "metadata": {"langgraph_node": "final_answer"},
             "run_id": "llm-1"},
            {"event": "on_chat_model_stream", "name": "ChatOpenAI",
             "data": {"chunk": self._chunk_msg("녕")},
             "metadata": {"langgraph_node": "final_answer"},
             "run_id": "llm-1"},
        ]
        use_case, agent, _, _, _ = _make_stream_use_case(astream_event_list=events_in)
        request = RunAgentRequest(query="x", user_id="user-1")

        events = await _collect(use_case.stream(agent.id, request, "req-1"))

        tokens = [e for e in events if e.event_type == AgentRunEventType.TOKEN]
        assert len(tokens) == 2
        assert tokens[0].payload["chunk"] == "안"
        assert tokens[1].payload["chunk"] == "녕"
        assert tokens[0].payload["node_name"] == "final_answer"

    @pytest.mark.asyncio
    async def test_empty_chunk_is_skipped(self):
        events_in = [
            {"event": "on_chat_model_stream", "name": "ChatOpenAI",
             "data": {"chunk": self._chunk_msg("")},
             "metadata": {"langgraph_node": "final_answer"},
             "run_id": "llm-1"},
        ]
        use_case, agent, _, _, _ = _make_stream_use_case(astream_event_list=events_in)
        request = RunAgentRequest(query="x", user_id="user-1")

        events = await _collect(use_case.stream(agent.id, request, "req-1"))

        tokens = [e for e in events if e.event_type == AgentRunEventType.TOKEN]
        assert len(tokens) == 0

    @pytest.mark.asyncio
    async def test_content_block_list_is_flattened_to_str(self):
        """FIX-CHAT-REASONING-OBJECT-RENDER: content가 block 리스트면 평탄화 문자열로 발행.

        프론트가 chunk를 문자열 결합하므로 list가 실리면 [object Object]가 된다.
        """
        events_in = [
            {"event": "on_chat_model_stream", "name": "ChatAnthropic",
             "data": {"chunk": self._chunk_msg(
                 [{"type": "text", "text": "안"}, {"type": "text", "text": "녕"}]
             )},
             "metadata": {"langgraph_node": "final_answer"},
             "run_id": "llm-1"},
        ]
        use_case, agent, _, _, _ = _make_stream_use_case(astream_event_list=events_in)
        request = RunAgentRequest(query="x", user_id="user-1")

        events = await _collect(use_case.stream(agent.id, request, "req-1"))

        tokens = [e for e in events if e.event_type == AgentRunEventType.TOKEN]
        assert len(tokens) == 1
        assert tokens[0].payload["chunk"] == "안녕"
        assert isinstance(tokens[0].payload["chunk"], str)

    @pytest.mark.asyncio
    async def test_content_block_list_without_text_is_skipped(self):
        """text block이 없는 content list(tool_use 단독 등)는 토큰 미발행."""
        events_in = [
            {"event": "on_chat_model_stream", "name": "ChatAnthropic",
             "data": {"chunk": self._chunk_msg(
                 [{"type": "tool_use", "id": "t1", "name": "search"}]
             )},
             "metadata": {"langgraph_node": "final_answer"},
             "run_id": "llm-1"},
        ]
        use_case, agent, _, _, _ = _make_stream_use_case(astream_event_list=events_in)
        request = RunAgentRequest(query="x", user_id="user-1")

        events = await _collect(use_case.stream(agent.id, request, "req-1"))

        tokens = [e for e in events if e.event_type == AgentRunEventType.TOKEN]
        assert len(tokens) == 0


# ── 4-5 Failure ────────────────────────────────────────────────────────


class TestStreamFailure:
    @pytest.mark.asyncio
    async def test_graph_exception_yields_run_failed(self):
        use_case, agent, tracker, _, _ = _make_stream_use_case(
            astream_raises=RuntimeError("graph boom"),
        )
        request = RunAgentRequest(query="x", user_id="user-1")

        events = await _collect(use_case.stream(agent.id, request, "req-1"))

        assert events[-1].event_type == AgentRunEventType.RUN_FAILED
        assert events[-1].payload["code"] == "GRAPH_EXEC_FAILED"
        assert "boom" in events[-1].payload["message"]
        tracker.fail_run.assert_awaited_once()
        tracker.complete_run.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_failed_generator_terminates_normally(self):
        # 예외 발생 후에도 generator는 StopAsyncIteration로 정상 종료 (raise X)
        use_case, agent, _, _, _ = _make_stream_use_case(
            astream_raises=RuntimeError("oops"),
        )
        request = RunAgentRequest(query="x", user_id="user-1")

        # exception이 호출자에게 re-raise되지 않아야 함
        try:
            events = await _collect(use_case.stream(agent.id, request, "req-1"))
        except RuntimeError:
            pytest.fail("stream() should not re-raise generic exception; "
                        "should yield RUN_FAILED instead")
        assert events[-1].event_type == AgentRunEventType.RUN_FAILED

    @pytest.mark.asyncio
    async def test_agent_not_found_raises_value_error_before_stream(self):
        use_case, _, _, _, _ = _make_stream_use_case(astream_event_list=[])
        # repository.find_by_id가 None 반환하도록 변경
        use_case._repository.find_by_id = AsyncMock(return_value=None)
        request = RunAgentRequest(query="x", user_id="user-1")

        with pytest.raises(ValueError, match="찾을 수 없"):
            await _collect(use_case.stream("nonexistent", request, "req-1"))


# ── 4-6 Cancellation ───────────────────────────────────────────────────


class TestStreamCancellation:
    @pytest.mark.asyncio
    async def test_cancelled_error_calls_fail_run_and_reraises(self):
        use_case, agent, tracker, _, _ = _make_stream_use_case(
            astream_raises=asyncio.CancelledError(),
        )
        request = RunAgentRequest(query="x", user_id="user-1")

        with pytest.raises(asyncio.CancelledError):
            await _collect(use_case.stream(agent.id, request, "req-1"))

        tracker.fail_run.assert_awaited_once()


# ── 5. execute() compatibility ─────────────────────────────────────────


class TestExecuteCompatibility:
    @pytest.mark.asyncio
    async def test_execute_returns_response_with_answer(self):
        use_case, agent, _, _, _ = _make_stream_use_case(
            astream_event_list=[],
            final_messages=[_ai_message("응답입니다")],
        )
        request = RunAgentRequest(query="안녕", user_id="user-1")

        result = await use_case.execute(agent.id, request, "req-1")

        assert result.agent_id == agent.id
        assert result.query == "안녕"
        assert result.answer == "응답입니다"
        assert result.request_id == "req-1"

    @pytest.mark.asyncio
    async def test_execute_includes_run_id(self):
        use_case, agent, _, _, _ = _make_stream_use_case(astream_event_list=[])
        request = RunAgentRequest(query="x", user_id="user-1")

        result = await use_case.execute(agent.id, request, "req-1")

        assert result.run_id is not None  # tracker 활성

    @pytest.mark.asyncio
    async def test_execute_re_raises_value_error_on_agent_not_found(self):
        use_case, _, _, _, _ = _make_stream_use_case(astream_event_list=[])
        use_case._repository.find_by_id = AsyncMock(return_value=None)
        request = RunAgentRequest(query="x", user_id="user-1")

        with pytest.raises(ValueError, match="찾을 수 없"):
            await use_case.execute("ghost", request, "req-1")

    @pytest.mark.asyncio
    async def test_execute_re_raises_on_graph_failure(self):
        use_case, agent, _, _, _ = _make_stream_use_case(
            astream_raises=RuntimeError("graph boom"),
        )
        request = RunAgentRequest(query="x", user_id="user-1")

        with pytest.raises(RuntimeError, match="boom"):
            await use_case.execute(agent.id, request, "req-1")

    @pytest.mark.asyncio
    async def test_execute_extracts_tools_used_from_messages(self):
        # _parse_result는 messages에서 name 속성 있는 메시지의 name을 모음
        msgs = [
            _ai_message("부분", name="search_worker"),
            _ai_message("최종", name=None),
        ]
        use_case, agent, _, _, _ = _make_stream_use_case(
            astream_event_list=[],
            final_messages=msgs,
        )
        request = RunAgentRequest(query="x", user_id="user-1")

        result = await use_case.execute(agent.id, request, "req-1")

        assert "search_worker" in result.tools_used


# ── §11-4: ANSWER_COMPLETED charts payload (supervisor-chart-builder-node) ──


class TestAnswerCompletedCharts:
    @pytest.mark.asyncio
    async def test_charts_present_in_answer_completed_when_chart_builder_ran(self):
        """chart_builder on_chain_end output의 charts가 ANSWER_COMPLETED payload에 실린다."""
        chart = {
            "type": "bar",
            "data": {"labels": ["a"], "datasets": [{"label": "s", "data": [1.0]}]},
        }
        use_case, agent, _, _, _ = _make_stream_use_case(
            astream_event_list=[
                {
                    "event": "on_chain_end",
                    "name": "chart_builder",
                    "data": {"output": {"charts": [chart]}},
                    "metadata": {},
                    "run_id": "cb",
                },
            ],
            final_messages=[_ai_message("차트 답변")],
        )
        request = RunAgentRequest(query="그래프 그려줘", user_id="user-1")

        events = await _collect(use_case.stream(agent.id, request, "req-1"))

        answer = next(
            e for e in events
            if e.event_type == AgentRunEventType.ANSWER_COMPLETED
        )
        assert answer.payload["charts"] == [chart]

    @pytest.mark.asyncio
    async def test_charts_absent_when_no_chart_builder(self):
        """charts가 없으면 ANSWER_COMPLETED payload에 charts 키가 없다(하위호환)."""
        use_case, agent, _, _, _ = _make_stream_use_case(
            astream_event_list=[],
            final_messages=[_ai_message("일반 답변")],
        )
        request = RunAgentRequest(query="안녕", user_id="user-1")

        events = await _collect(use_case.stream(agent.id, request, "req-1"))

        answer = next(
            e for e in events
            if e.event_type == AgentRunEventType.ANSWER_COMPLETED
        )
        assert "charts" not in answer.payload


# ── chat-chart-persistence: assistant 메시지 charts 영속화 ────────────────


class TestAssistantMessageChartsPersistence:
    """chat-chart-persistence Design §3-5: _save_assistant_message charts 전달."""

    @staticmethod
    def _saved_assistant_messages(use_case):
        """message_repo.save 호출 중 assistant role 엔티티만 추출."""
        from src.domain.conversation.value_objects import MessageRole

        return [
            call.args[0]
            for call in use_case._message_repo.save.await_args_list
            if call.args[0].role == MessageRole.ASSISTANT
        ]

    @pytest.mark.asyncio
    async def test_assistant_message_saved_with_charts(self):
        """chart_builder 실행 런 → 저장된 assistant 메시지에 charts 반영."""
        charts = [
            {"type": "bar", "data": {"labels": ["a"], "datasets": []}},
            {"type": "line", "data": {"labels": ["b"], "datasets": []}},
        ]
        use_case, agent, _, _, _ = _make_stream_use_case(
            astream_event_list=[
                {
                    "event": "on_chain_end",
                    "name": "chart_builder",
                    "data": {"output": {"charts": charts}},
                    "metadata": {},
                    "run_id": "cb",
                },
            ],
            final_messages=[_ai_message("차트 답변")],
        )
        request = RunAgentRequest(query="그래프 그려줘", user_id="user-1")

        await _collect(use_case.stream(agent.id, request, "req-1"))

        saved = self._saved_assistant_messages(use_case)
        assert len(saved) == 1
        assert saved[0].charts == charts

    @pytest.mark.asyncio
    async def test_assistant_message_saved_with_none_when_no_charts(self):
        """비차트 런 → charts=None 저장 (D2: 빈 리스트 금지)."""
        use_case, agent, _, _, _ = _make_stream_use_case(
            astream_event_list=[],
            final_messages=[_ai_message("일반 답변")],
        )
        request = RunAgentRequest(query="안녕", user_id="user-1")

        await _collect(use_case.stream(agent.id, request, "req-1"))

        saved = self._saved_assistant_messages(use_case)
        assert len(saved) == 1
        assert saved[0].charts is None

    @pytest.mark.asyncio
    async def test_charts_not_injected_into_llm_context(self):
        """D7 고정: 이력에 charts가 있어도 _build_messages는 role/content만 구성."""
        from unittest.mock import AsyncMock

        from src.domain.conversation.entities import ConversationMessage
        from src.domain.conversation.value_objects import (
            AgentId, MessageRole, SessionId, TurnIndex, UserId,
        )

        use_case, _, _, _, _ = _make_stream_use_case(astream_event_list=[])
        chart_msg = ConversationMessage(
            id=None, user_id=UserId("user-1"), session_id=SessionId("s1"),
            agent_id=AgentId.super(), role=MessageRole.ASSISTANT,
            content="차트 답변", turn_index=TurnIndex(2),
            created_at=datetime.now(timezone.utc),
            charts=[{"type": "bar", "data": {"labels": ["a"]}}],
        )
        use_case._message_repo.find_by_session = AsyncMock(return_value=[chart_msg])

        messages = await use_case._build_messages("후속 질문", "user-1", "s1", True)

        assert all(set(m.keys()) == {"role", "content"} for m in messages)
        assert "bar" not in " ".join(str(m["content"]) for m in messages)
