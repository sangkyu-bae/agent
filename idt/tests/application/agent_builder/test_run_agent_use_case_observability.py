"""RunAgentUseCase + RunTracker 통합 동작 검증.

- 정상 실행: start_run → graph → complete_run / ai_run.id가 응답에 포함됨
- 실패 실행: start_run → graph 예외 → fail_run / 본 예외는 그대로 전파
- callback이 graph.ainvoke()의 config에 등록되어 LLM 호출이 수집됨
- ContextVar이 graph 실행 동안 활성화됨
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_builder.run_agent_use_case import RunAgentUseCase
from src.application.agent_builder.schemas import RunAgentRequest
from src.application.agent_run.context import get_current_run_context
from src.application.agent_run.tracker import RunTracker
from src.domain.agent_builder.schemas import AgentDefinition, WorkerDefinition
from src.domain.conversation.policies import SummarizationPolicy
from src.domain.llm_model.entity import LlmModel
from src.infrastructure.llm.usage_callback import UsageCallback


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


def _make_use_case():
    repository = MagicMock()
    llm_model_repository = MagicMock()
    compiler = MagicMock()
    logger = MagicMock()
    message_repo = MagicMock()
    summary_repo = MagicMock()
    summarizer = MagicMock()
    policy = SummarizationPolicy()
    tracker = MagicMock(spec=RunTracker)
    tracker.start_run = AsyncMock()
    tracker.complete_run = AsyncMock()
    tracker.fail_run = AsyncMock()

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

    mock_graph = MagicMock()
    last_msg = MagicMock()
    last_msg.content = "응답입니다"
    last_msg.name = None
    mock_graph.ainvoke = AsyncMock(return_value={"messages": [last_msg]})

    # stream() 어댑터: astream_events가 내부적으로 ainvoke를 호출하여
    # 1) 기존 callback 발화 패턴(graph.ainvoke.side_effect = fire_xxx) 그대로 동작
    # 2) ainvoke의 결과를 top-level on_chain_end로 흘려보냄
    # 3) graph.ainvoke.call_args / side_effect 어설션 그대로 유효
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
        tracker=tracker,
    )
    return use_case, tracker, agent, mock_graph, message_repo


class TestRunLifecycle:
    @pytest.mark.asyncio
    async def test_success_path_calls_start_then_complete(self) -> None:
        use_case, tracker, agent, _graph, _ = _make_use_case()

        result = await use_case.execute(
            agent.id,
            RunAgentRequest(query="q", user_id="user-1"),
            "req-1",
        )

        tracker.start_run.assert_awaited_once()
        tracker.complete_run.assert_awaited_once()
        tracker.fail_run.assert_not_awaited()
        assert result.run_id is not None
        # run_id는 36자 UUID
        assert len(result.run_id) == 36

    @pytest.mark.asyncio
    async def test_user_message_id_is_passed_to_start_run(self) -> None:
        use_case, tracker, agent, _graph, message_repo = _make_use_case()

        await use_case.execute(
            agent.id,
            RunAgentRequest(query="q", user_id="user-1"),
            "req-1",
        )

        kwargs = tracker.start_run.await_args.kwargs
        assert kwargs["user_id"] == "user-1"
        assert kwargs["agent_id"] == agent.id
        assert kwargs["agent_llm_model_id"] == "model-1"
        assert kwargs["user_message_id"] == 42  # saved_msg.id.value

    @pytest.mark.asyncio
    async def test_graph_invoke_receives_callback_and_metadata(self) -> None:
        use_case, tracker, agent, graph, _ = _make_use_case()

        await use_case.execute(
            agent.id,
            RunAgentRequest(query="q", user_id="user-1"),
            "req-1",
        )

        # ainvoke(initial_state, config={...})
        call_kwargs = graph.ainvoke.call_args.kwargs
        config = call_kwargs["config"]
        assert "callbacks" in config
        assert len(config["callbacks"]) == 1
        assert isinstance(config["callbacks"][0], UsageCallback)
        assert "metadata" in config
        assert config["metadata"]["user_id"] == "user-1"
        assert config["metadata"]["agent_id"] == agent.id
        assert "run_id" in config["metadata"]

    @pytest.mark.asyncio
    async def test_failure_path_calls_fail_run_and_raises(self) -> None:
        use_case, tracker, agent, graph, _ = _make_use_case()
        graph.ainvoke.side_effect = RuntimeError("graph blew up")

        with pytest.raises(RuntimeError, match="graph blew up"):
            await use_case.execute(
                agent.id,
                RunAgentRequest(query="q", user_id="user-1"),
                "req-1",
            )

        tracker.start_run.assert_awaited_once()
        tracker.fail_run.assert_awaited_once()
        tracker.complete_run.assert_not_awaited()


class TestContextVarLifecycle:
    @pytest.mark.asyncio
    async def test_run_context_active_during_graph_invoke(self) -> None:
        """graph.ainvoke 내부에서 ContextVar이 활성화되고, 종료 후 reset."""
        use_case, tracker, agent, graph, _ = _make_use_case()
        observed: dict = {}

        async def capture_ctx(*a, **kw):
            ctx = get_current_run_context()
            observed["run_id"] = ctx.run_id.value if ctx else None
            observed["user_id"] = ctx.user_id if ctx else None
            msg = MagicMock()
            msg.content = "ok"
            msg.name = None  # name=None은 MagicMock 생성자 키워드와 충돌하므로 직접 할당
            return {"messages": [msg]}

        graph.ainvoke.side_effect = capture_ctx

        await use_case.execute(
            agent.id,
            RunAgentRequest(query="q", user_id="user-1"),
            "req-1",
        )

        assert observed["run_id"] is not None
        assert observed["user_id"] == "user-1"
        # graph 종료 후엔 context가 None
        assert get_current_run_context() is None


class TestStartRunFailureDegradesGracefully:
    @pytest.mark.asyncio
    async def test_start_run_failure_continues_without_tracker(self) -> None:
        """start_run이 RuntimeError 발생해도 본 흐름은 계속된다 (degraded mode)."""
        use_case, tracker, agent, graph, _ = _make_use_case()
        tracker.start_run.side_effect = RuntimeError("db unreachable")

        result = await use_case.execute(
            agent.id,
            RunAgentRequest(query="q", user_id="user-1"),
            "req-1",
        )

        # 응답은 정상, run_id는 None (관측성 없음)
        assert result.run_id is None
        # complete_run / fail_run도 호출되지 않음 (run_id가 None이므로)
        tracker.complete_run.assert_not_awaited()


# ─────────────────── M2: Tool Call Wiring 통합 검증 ────────────────────────
class TestToolCallWiringM2:
    """AGENT-OBS-002: graph 실행 중 발생하는 on_tool_* 콜백이
    tracker.record_tool_call / update_tool_call 로 정상 연결되는지 검증.
    """

    @pytest.mark.asyncio
    async def test_tool_callback_records_tool_call_via_tracker(self) -> None:
        use_case, tracker, agent, graph, _ = _make_use_case()
        tracker.record_tool_call = AsyncMock(return_value="tcid-T1")
        tracker.update_tool_call = AsyncMock(return_value=None)

        async def fire_tool_callback(*a, **kw):
            callback = kw["config"]["callbacks"][0]
            lc_id = uuid.uuid4()
            await callback.on_tool_start(
                serialized={"name": "internal_document_search"},
                input_str='{"query": "test"}',
                run_id=lc_id,
            )
            await callback.on_tool_end(output={"docs": []}, run_id=lc_id)
            msg = MagicMock()
            msg.content = "ok"
            msg.name = None
            return {"messages": [msg]}

        graph.ainvoke.side_effect = fire_tool_callback
        await use_case.execute(
            agent.id, RunAgentRequest(query="q", user_id="user-1"), "req-1"
        )

        tracker.record_tool_call.assert_awaited_once()
        rec_kwargs = tracker.record_tool_call.await_args.kwargs
        assert rec_kwargs["tool_name"] == "internal_document_search"
        assert rec_kwargs["status"] == "STARTED"

        tracker.update_tool_call.assert_awaited_once()
        upd_kwargs = tracker.update_tool_call.await_args.kwargs
        assert upd_kwargs["status"] == "SUCCESS"
        assert upd_kwargs["tool_call_id"] == "tcid-T1"

    @pytest.mark.asyncio
    async def test_tool_failure_callback_records_failed(self) -> None:
        use_case, tracker, agent, graph, _ = _make_use_case()
        tracker.record_tool_call = AsyncMock(return_value="tcid-F1")
        tracker.update_tool_call = AsyncMock(return_value=None)

        async def fire_tool_error(*a, **kw):
            callback = kw["config"]["callbacks"][0]
            lc_id = uuid.uuid4()
            await callback.on_tool_start(
                serialized={"name": "tavily_search"},
                input_str="",
                run_id=lc_id,
            )
            await callback.on_tool_error(
                error=RuntimeError("rate limited"), run_id=lc_id
            )
            msg = MagicMock()
            msg.content = "fallback"
            msg.name = None
            return {"messages": [msg]}

        graph.ainvoke.side_effect = fire_tool_error
        await use_case.execute(
            agent.id, RunAgentRequest(query="q", user_id="user-1"), "req-1"
        )

        upd_kwargs = tracker.update_tool_call.await_args.kwargs
        assert upd_kwargs["status"] == "FAILED"
        assert "rate limited" in (upd_kwargs["error_text"] or "")

    @pytest.mark.asyncio
    async def test_inner_llm_call_attaches_tool_call_id(self) -> None:
        """M2 핵심 회귀 가드: 툴 내부 LLM 호출의 tool_call_id 자동 채움."""
        from langchain_core.outputs import LLMResult

        use_case, tracker, agent, graph, _ = _make_use_case()
        tracker.record_tool_call = AsyncMock(return_value="tcid-INNER")
        tracker.update_tool_call = AsyncMock(return_value=None)
        tracker.record_llm_call = AsyncMock(return_value=None)

        async def fire_nested(*a, **kw):
            callback = kw["config"]["callbacks"][0]
            tool_lc = uuid.uuid4()
            llm_lc = uuid.uuid4()
            await callback.on_tool_start(
                serialized={"name": "rag_search"},
                input_str="",
                run_id=tool_lc,
            )
            # 툴 내부 LLM 호출 시뮬레이션
            await callback.on_chat_model_start(
                serialized={}, messages=[], run_id=llm_lc
            )
            await callback.on_llm_end(
                LLMResult(
                    generations=[[]],
                    llm_output={
                        "model_name": "gpt-4o-mini",
                        "token_usage": {
                            "prompt_tokens": 10,
                            "completion_tokens": 5,
                            "total_tokens": 15,
                        },
                    },
                ),
                run_id=llm_lc,
            )
            await callback.on_tool_end(output="ok", run_id=tool_lc)
            msg = MagicMock()
            msg.content = "done"
            msg.name = None
            return {"messages": [msg]}

        graph.ainvoke.side_effect = fire_nested
        await use_case.execute(
            agent.id, RunAgentRequest(query="q", user_id="user-1"), "req-1"
        )

        tracker.record_llm_call.assert_awaited_once()
        llm_kwargs = tracker.record_llm_call.await_args.kwargs
        assert llm_kwargs["tool_call_id"] == "tcid-INNER"

    @pytest.mark.asyncio
    async def test_observability_failure_does_not_block_response(self) -> None:
        """tracker.record_tool_call 실패해도 응답은 정상 반환된다."""
        use_case, tracker, agent, graph, _ = _make_use_case()
        tracker.record_tool_call = AsyncMock(side_effect=RuntimeError("db down"))
        tracker.update_tool_call = AsyncMock(return_value=None)

        async def fire_tool_with_failure(*a, **kw):
            callback = kw["config"]["callbacks"][0]
            lc_id = uuid.uuid4()
            await callback.on_tool_start(
                serialized={"name": "x"}, input_str="", run_id=lc_id
            )
            await callback.on_tool_end(output="ok", run_id=lc_id)
            msg = MagicMock()
            msg.content = "response"
            msg.name = None
            return {"messages": [msg]}

        graph.ainvoke.side_effect = fire_tool_with_failure
        result = await use_case.execute(
            agent.id, RunAgentRequest(query="q", user_id="user-1"), "req-1"
        )

        # record_tool_call 실패에도 응답 정상
        assert result.answer == "response"
        # update_tool_call은 sentinel skip 되어 호출 안됨
        tracker.update_tool_call.assert_not_called()
