"""RunAgentUseCase 단위 테스트."""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.application.agent_builder.schemas import RunAgentRequest, RunAgentResponse
from src.application.agent_builder.run_agent_use_case import RunAgentUseCase
from src.domain.agent_builder.schemas import AgentDefinition, WorkerDefinition
from src.domain.conversation.entities import ConversationMessage
from src.domain.conversation.policies import SummarizationPolicy
from src.domain.conversation.value_objects import (
    AgentId, MessageRole, SessionId, TurnIndex, UserId,
)
from src.domain.llm_model.entity import LlmModel


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


def _make_use_case(existing_messages=None):
    repository = MagicMock()
    llm_model_repository = MagicMock()
    compiler = MagicMock()
    logger = MagicMock()
    message_repo = MagicMock()
    summary_repo = MagicMock()
    summarizer = MagicMock()
    policy = SummarizationPolicy()

    agent = _make_agent()
    repository.find_by_id = AsyncMock(return_value=agent)
    llm_model_repository.find_by_id = AsyncMock(return_value=_make_llm_model())

    message_repo.find_by_session = AsyncMock(return_value=existing_messages or [])
    message_repo.save = AsyncMock()
    summary_repo.find_latest_by_session = AsyncMock(return_value=None)
    summary_repo.save = AsyncMock()
    summarizer.summarize = AsyncMock(return_value="이전 대화 요약입니다.")

    mock_graph = MagicMock()
    last_msg = MagicMock()
    last_msg.content = "AI 뉴스를 수집했습니다."
    last_msg.name = None
    mock_graph.ainvoke = AsyncMock(return_value={
        "messages": [last_msg]
    })

    # stream() 어댑터: astream_events가 내부적으로 ainvoke를 호출
    # → graph.ainvoke.call_args / side_effect 어설션 그대로 유효
    def _astream_side_effect(*args, **kwargs):
        async def _gen():
            result = await mock_graph.ainvoke(*args, **kwargs)
            messages = result.get("messages", [])
            yield {
                "event": "on_chain_end",
                "name": "LangGraph",
                "data": {"output": {"messages": messages}},
                "metadata": {},
                "run_id": "top",
            }
        return _gen()
    mock_graph.astream_events = MagicMock(side_effect=_astream_side_effect)
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
    )
    return use_case, repository, compiler, agent, message_repo, summary_repo, summarizer, mock_graph


def _make_conversation_message(
    turn: int, role: str = "user", content: str = "msg",
    user_id: str = "user-1", session_id: str = "sess-1", agent_id: str = "agent-1",
) -> ConversationMessage:
    return ConversationMessage(
        id=None,
        user_id=UserId(user_id),
        session_id=SessionId(session_id),
        agent_id=AgentId(agent_id),
        role=MessageRole(role),
        content=content,
        turn_index=TurnIndex(turn),
        created_at=datetime.now(timezone.utc),
    )


class TestRunAgentUseCase:
    @pytest.mark.asyncio
    async def test_execute_returns_run_agent_response(self):
        use_case, _, _, agent, *_ = _make_use_case()
        request = RunAgentRequest(query="AI 뉴스 수집해줘", user_id="user-1")
        result = await use_case.execute(agent.id, request, "req-1")
        assert isinstance(result, RunAgentResponse)
        assert result.agent_id == agent.id
        assert result.query == "AI 뉴스 수집해줘"
        assert result.answer == "AI 뉴스를 수집했습니다."

    @pytest.mark.asyncio
    async def test_execute_raises_not_found_when_agent_missing(self):
        use_case, repository, _, _, *_ = _make_use_case()
        repository.find_by_id = AsyncMock(return_value=None)
        request = RunAgentRequest(query="쿼리", user_id="user-1")
        with pytest.raises(ValueError, match="찾을 수 없"):
            await use_case.execute("non-existent", request, "req-1")

    @pytest.mark.asyncio
    async def test_execute_calls_compiler_compile(self):
        use_case, _, compiler, agent, *_ = _make_use_case()
        request = RunAgentRequest(query="쿼리", user_id="user-1")
        await use_case.execute(agent.id, request, "req-1")
        compiler.compile.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_passes_llm_model_to_compiler(self):
        use_case, _, compiler, agent, *_ = _make_use_case()
        request = RunAgentRequest(query="쿼리", user_id="user-1")
        await use_case.execute(agent.id, request, "req-1")
        _, kwargs = compiler.compile.call_args
        assert kwargs["llm_model"].provider == "openai"
        assert kwargs["llm_model"].model_name == "gpt-4o-mini"

    @pytest.mark.asyncio
    async def test_execute_passes_supervisor_config(self):
        """SupervisorConfig가 compiler.compile()에 전달된다."""
        use_case, _, compiler, agent, *_ = _make_use_case()
        request = RunAgentRequest(query="쿼리", user_id="user-1")
        await use_case.execute(agent.id, request, "req-1")
        _, kwargs = compiler.compile.call_args
        from src.domain.agent_builder.schemas import SupervisorConfig
        assert isinstance(kwargs["supervisor_config"], SupervisorConfig)

    @pytest.mark.asyncio
    async def test_execute_passes_initial_state_with_supervisor_fields(self):
        """graph.ainvoke에 SupervisorState 형태의 initial_state가 전달된다."""
        use_case, _, _, agent, _, _, _, mock_graph = _make_use_case()
        request = RunAgentRequest(query="쿼리", user_id="user-1")
        await use_case.execute(agent.id, request, "req-1")
        call_args = mock_graph.ainvoke.call_args[0][0]
        assert "iteration_count" in call_args
        assert "max_iterations" in call_args
        assert "available_workers" in call_args
        assert call_args["iteration_count"] == 0

    @pytest.mark.asyncio
    async def test_execute_includes_request_id_in_response(self):
        use_case, _, _, agent, *_ = _make_use_case()
        request = RunAgentRequest(query="쿼리", user_id="user-1")
        result = await use_case.execute(agent.id, request, "req-xyz")
        assert result.request_id == "req-xyz"


class TestRunAgentMultiTurn:
    """Multi-turn 대화 기능 테스트."""

    @pytest.mark.asyncio
    async def test_session_id_auto_generated_when_none(self):
        """session_id 미전달 시 UUID 자동 생���."""
        use_case, _, _, agent, *_ = _make_use_case()
        request = RunAgentRequest(query="쿼리", user_id="user-1", session_id=None)
        result = await use_case.execute(agent.id, request, "req-1")
        assert result.session_id is not None
        uuid.UUID(result.session_id)

    @pytest.mark.asyncio
    async def test_session_id_preserved_when_provided(self):
        """session_id ���달 시 그대로 반환."""
        use_case, _, _, agent, *_ = _make_use_case()
        sid = str(uuid.uuid4())
        request = RunAgentRequest(query="쿼리", user_id="user-1", session_id=sid)
        result = await use_case.execute(agent.id, request, "req-1")
        assert result.session_id == sid

    @pytest.mark.asyncio
    async def test_history_loaded_when_session_id_provided(self):
        """session_id 전달 시 히스토리 로드 호출."""
        use_case, _, _, agent, message_repo, *_ = _make_use_case()
        sid = str(uuid.uuid4())
        request = RunAgentRequest(query="쿼리", user_id="user-1", session_id=sid)
        await use_case.execute(agent.id, request, "req-1")
        assert message_repo.find_by_session.call_count >= 1

    @pytest.mark.asyncio
    async def test_no_history_in_messages_when_no_session_id(self):
        """session_id 없을 시 graph에 현재 쿼리만 전달 (히스토리 미포함)."""
        use_case, _, _, agent, _, _, _, mock_graph = _make_use_case()
        request = RunAgentRequest(query="쿼리", user_id="user-1", session_id=None)
        await use_case.execute(agent.id, request, "req-1")
        call_args = mock_graph.ainvoke.call_args[0][0]
        messages = call_args["messages"]
        assert len(messages) == 1
        assert messages[0] == {"role": "user", "content": "쿼리"}

    @pytest.mark.asyncio
    async def test_history_injected_into_graph_messages(self):
        """히스토리가 있으면 graph.ainvoke 시 messages에 포함."""
        existing = [
            _make_conversation_message(1, "user", "안녕"),
            _make_conversation_message(2, "assistant", "안녕하세요!"),
        ]
        use_case, _, _, agent, _, _, _, mock_graph = _make_use_case(existing)
        sid = str(uuid.uuid4())
        request = RunAgentRequest(query="후속 질문", user_id="user-1", session_id=sid)
        await use_case.execute(agent.id, request, "req-1")

        call_args = mock_graph.ainvoke.call_args[0][0]
        messages = call_args["messages"]
        assert len(messages) == 3
        assert messages[0] == {"role": "user", "content": "안녕"}
        assert messages[1] == {"role": "assistant", "content": "안녕하세요!"}
        assert messages[2] == {"role": "user", "content": "후속 질문"}

    @pytest.mark.asyncio
    async def test_messages_saved_after_execution(self):
        """실행 후 user + assistant 메시지 저장."""
        use_case, _, _, agent, message_repo, *_ = _make_use_case()
        sid = str(uuid.uuid4())
        request = RunAgentRequest(query="쿼리", user_id="user-1", session_id=sid)
        await use_case.execute(agent.id, request, "req-1")
        assert message_repo.save.call_count == 2

    @pytest.mark.asyncio
    async def test_summarization_triggered_when_exceeds_threshold(self):
        """7턴 대화 시 요약 생성."""
        existing = [
            _make_conversation_message(i, "user" if i % 2 == 1 else "assistant", f"msg-{i}")
            for i in range(1, 8)
        ]
        use_case, _, _, agent, _, summary_repo, summarizer, _ = _make_use_case(existing)
        sid = str(uuid.uuid4())
        request = RunAgentRequest(query="8번째 질문", user_id="user-1", session_id=sid)
        await use_case.execute(agent.id, request, "req-1")
        summarizer.summarize.assert_called_once()
        summary_repo.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_summarization_within_threshold(self):
        """6턴 이하면 요약 안 함."""
        existing = [
            _make_conversation_message(i, "user" if i % 2 == 1 else "assistant", f"msg-{i}")
            for i in range(1, 5)
        ]
        use_case, _, _, agent, _, summary_repo, summarizer, _ = _make_use_case(existing)
        sid = str(uuid.uuid4())
        request = RunAgentRequest(query="5번째 질문", user_id="user-1", session_id=sid)
        await use_case.execute(agent.id, request, "req-1")
        summarizer.summarize.assert_not_called()
        summary_repo.save.assert_not_called()

    @pytest.mark.asyncio
    async def test_second_call_loads_first_turn_history(self):
        """2차 호출 시 1차 턴 메시지가 graph messages에 포함된다."""
        first_turn = [
            _make_conversation_message(1, "user", "첫 질문"),
            _make_conversation_message(2, "assistant", "첫 답변"),
        ]
        use_case, _, _, agent, _, _, _, mock_graph = _make_use_case(first_turn)
        sid = str(uuid.uuid4())
        request = RunAgentRequest(query="두 번째 질문", user_id="user-1", session_id=sid)
        await use_case.execute(agent.id, request, "req-2")

        call_args = mock_graph.ainvoke.call_args[0][0]
        messages = call_args["messages"]
        assert len(messages) == 3
        assert messages[0] == {"role": "user", "content": "첫 질문"}
        assert messages[1] == {"role": "assistant", "content": "첫 답변"}
        assert messages[2] == {"role": "user", "content": "두 번째 질문"}

    @pytest.mark.asyncio
    async def test_consecutive_calls_preserve_conversation(self):
        """1차(session_id=None)→2차 연속 호출 시 대화 문맥이 유지된다."""
        use_case, _, _, agent, message_repo, _, _, mock_graph = _make_use_case()

        # 1차 호출: session_id=None → 새 세션 생성 + 저장
        req1 = RunAgentRequest(query="첫 질문", user_id="user-1", session_id=None)
        result1 = await use_case.execute(agent.id, req1, "req-1")
        generated_sid = result1.session_id
        assert message_repo.save.call_count == 2

        # side_effect: 2차 호출의 find_by_session이 1차 턴 데이터 반환
        saved_messages = [
            _make_conversation_message(
                1, "user", "첫 질문",
                session_id=generated_sid, agent_id=agent.id,
            ),
            _make_conversation_message(
                2, "assistant", "AI 뉴스를 수집했습니다.",
                session_id=generated_sid, agent_id=agent.id,
            ),
        ]
        message_repo.find_by_session = AsyncMock(return_value=saved_messages)

        # 2차 호출: 반환된 session_id 사용
        req2 = RunAgentRequest(query="후속 질문", user_id="user-1", session_id=generated_sid)
        await use_case.execute(agent.id, req2, "req-2")

        call_args = mock_graph.ainvoke.call_args[0][0]
        messages = call_args["messages"]
        assert len(messages) == 3
        assert messages[0] == {"role": "user", "content": "첫 질문"}
        assert messages[1] == {"role": "assistant", "content": "AI 뉴스를 수집했습니다."}
        assert messages[2] == {"role": "user", "content": "후속 질문"}

    @pytest.mark.asyncio
    async def test_first_call_without_session_id_saves_turn(self):
        """session_id 없이 첫 호출해도 대화가 DB에 저장된다."""
        use_case, _, _, agent, message_repo, *_ = _make_use_case()
        request = RunAgentRequest(query="첫 질문", user_id="user-1", session_id=None)
        result = await use_case.execute(agent.id, request, "req-1")
        assert message_repo.save.call_count == 2  # user + assistant
        assert result.session_id is not None

    @pytest.mark.asyncio
    async def test_first_call_without_session_id_uses_only_current_query(self):
        """session_id 없이 호출하면 이전 히스토리 없이 현재 쿼리만 사용."""
        use_case, _, _, agent, _, _, _, mock_graph = _make_use_case()
        request = RunAgentRequest(query="단일 질문", user_id="user-1")
        result = await use_case.execute(agent.id, request, "req-1")

        call_args = mock_graph.ainvoke.call_args[0][0]
        messages = call_args["messages"]
        assert len(messages) == 1
        assert messages[0] == {"role": "user", "content": "단일 질문"}
        assert result.answer == "AI 뉴스를 수집했습니다."


# agent-chat-reasoning-display Design §4.1
class TestSupervisorStepReasoning:
    """Supervisor on_chain_end output._step_output_summary → STEP_REASONING 이벤트."""

    @staticmethod
    def _install_supervisor_astream(mock_graph, *, step_summary, next_worker="search_agent"):
        """supervisor on_chain_start → on_chain_end(with _step_output_summary) → top chain_end."""
        last_msg = MagicMock()
        last_msg.content = "최종 답변"
        last_msg.name = None

        def _side(*args, **kwargs):
            async def _gen():
                yield {
                    "event": "on_chain_start",
                    "name": "supervisor",
                    "data": {},
                    "metadata": {},
                    "run_id": "sv-1",
                }
                yield {
                    "event": "on_chain_end",
                    "name": "supervisor",
                    "data": {
                        "output": {
                            "next_worker": next_worker,
                            "_step_output_summary": step_summary,
                            "messages": [],
                        }
                    },
                    "metadata": {},
                    "run_id": "sv-1",
                }
                yield {
                    "event": "on_chain_end",
                    "name": "LangGraph",
                    "data": {"output": {"messages": [last_msg]}},
                    "metadata": {},
                    "run_id": "top",
                }
            return _gen()
        mock_graph.astream_events = MagicMock(side_effect=_side)

    @pytest.mark.asyncio
    async def test_reasoning_emitted_right_after_supervisor_node_completed(self):
        """T1 — _step_output_summary가 있으면 NODE_COMPLETED(supervisor) 직후 STEP_REASONING."""
        from src.domain.agent_run.value_objects import AgentRunEventType

        use_case, _, _, _agent, _, _, _, mock_graph = _make_use_case()
        self._install_supervisor_astream(
            mock_graph,
            step_summary="X 정보가 필요해 search_agent 호출",
            next_worker="search_agent",
        )

        events = []
        request = RunAgentRequest(query="질문", user_id="user-1")
        async for ev in use_case.stream("agent-1", request, "req-1"):
            events.append(ev)

        types = [ev.event_type for ev in events]
        assert AgentRunEventType.NODE_COMPLETED in types
        assert AgentRunEventType.STEP_REASONING in types

        idx_completed = types.index(AgentRunEventType.NODE_COMPLETED)
        assert types[idx_completed + 1] == AgentRunEventType.STEP_REASONING

        reasoning_ev = events[idx_completed + 1]
        assert reasoning_ev.payload["step_name"] == "supervisor"
        assert reasoning_ev.payload["reasoning"] == "X 정보가 필요해 search_agent 호출"
        assert reasoning_ev.payload["next_worker"] == "search_agent"
        # seq는 NODE_COMPLETED 직후 (단조 증가)
        assert reasoning_ev.seq == events[idx_completed].seq + 1

    @pytest.mark.asyncio
    async def test_no_reasoning_event_when_summary_missing(self):
        """T2 — _step_output_summary가 None/빈 문자열이면 STEP_REASONING 미발행."""
        from src.domain.agent_run.value_objects import AgentRunEventType

        use_case, _, _, _agent, _, _, _, mock_graph = _make_use_case()
        self._install_supervisor_astream(mock_graph, step_summary="")

        events = []
        request = RunAgentRequest(query="질문", user_id="user-1")
        async for ev in use_case.stream("agent-1", request, "req-1"):
            events.append(ev)

        types = [ev.event_type for ev in events]
        assert AgentRunEventType.NODE_COMPLETED in types
        assert AgentRunEventType.STEP_REASONING not in types


class TestRunAgentAuthCtx:
    """G-07: auth_ctx ContextVar set/reset coverage (agent-user-context Design §4.4.1)."""

    @pytest.mark.asyncio
    async def test_auth_ctx_contextvar_set_during_stream_and_reset_after(self):
        """auth_ctx 제공 시 stream 실행 중 ContextVar가 설정되고 완료 후 초기화된다."""
        from src.domain.agent_run.auth_context import AuthContext
        from src.application.agent_run.auth_context import get_current_auth_context

        auth_ctx = AuthContext(
            user_id=1,
            display_name="테스터",
            role="user",
            primary_department_id=None,
            primary_department_name=None,
            department_ids=(),
            department_names=(),
            permissions=frozenset({"USE_RAG_SEARCH"}),
        )

        use_case, _, _, agent, *_ = _make_use_case()

        ctx_during: list = []

        # Patch _execute_graph_stream to capture ContextVar value mid-execution
        original_stream = use_case.stream

        async def _capturing_stream(*args, **kwargs):
            async for event in original_stream(*args, **kwargs):
                ctx_during.append(get_current_auth_context())
                yield event

        request = RunAgentRequest(query="테스트", user_id="1")
        events = []
        async for ev in use_case.stream(agent.id, request, "req-auth-1", auth_ctx=auth_ctx):
            events.append(ev)
            # Capture once mid-stream (inside stream body ContextVar is set)
            ctx_during.append(get_current_auth_context())

        # After stream completes, ContextVar must be reset to None
        assert get_current_auth_context() is None
        # During stream, ContextVar was set to our auth_ctx
        assert any(c is auth_ctx for c in ctx_during), (
            "ContextVar was never set to auth_ctx during stream execution"
        )

    @pytest.mark.asyncio
    async def test_auth_ctx_contextvar_reset_on_exception(self):
        """stream 실행 중 예외 발생 시에도 ContextVar가 finally 블록에서 초기화된다."""
        from src.domain.agent_run.auth_context import AuthContext
        from src.application.agent_run.auth_context import get_current_auth_context

        auth_ctx = AuthContext(
            user_id=2,
            display_name="예외유저",
            role="user",
            primary_department_id=None,
            primary_department_name=None,
            department_ids=(),
            department_names=(),
            permissions=frozenset(),
        )

        use_case, repository, _, agent, *_ = _make_use_case()
        # Make the agent lookup raise after ContextVar is set
        repository.find_by_id = AsyncMock(side_effect=RuntimeError("DB 장애"))

        request = RunAgentRequest(query="테스트", user_id="2")
        events = []
        try:
            async for ev in use_case.stream(agent.id, request, "req-auth-2", auth_ctx=auth_ctx):
                events.append(ev)
        except Exception:
            pass  # RuntimeError propagates — expected

        # Regardless of exception, ContextVar must be cleared
        assert get_current_auth_context() is None
