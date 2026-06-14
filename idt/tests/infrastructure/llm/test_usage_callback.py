"""UsageCallback: LangChain LLM 호출 인터셉트 + provider별 usage 정규화."""
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.outputs import LLMResult

from src.application.agent_run.tracker import RunTracker
from src.domain.agent_run.value_objects import RunId, RunPurpose, TokenUsage
from src.infrastructure.llm.usage_callback import UsageCallback


RUN_ID = "11111111-1111-1111-1111-111111111111"


def _make_callback() -> tuple[UsageCallback, MagicMock]:
    tracker = MagicMock(spec=RunTracker)
    tracker.record_llm_call = AsyncMock(return_value=None)
    logger = MagicMock()
    callback = UsageCallback(
        tracker=tracker,
        run_id=RunId(RUN_ID),
        user_id="user-1",
        agent_id="agent-1",
        logger=logger,
    )
    return callback, tracker


def _result_with_llm_output(
    model_name: str, token_usage: dict[str, int]
) -> LLMResult:
    return LLMResult(
        generations=[[]],
        llm_output={"model_name": model_name, "token_usage": token_usage},
    )


class TestPurposeAndContextSetters:
    def test_set_purpose_changes_state(self) -> None:
        cb, _ = _make_callback()
        cb.set_purpose(RunPurpose.SUPERVISOR)
        assert cb._current_purpose is RunPurpose.SUPERVISOR

    def test_enter_exit_step(self) -> None:
        cb, _ = _make_callback()
        cb.enter_step("step-1")
        assert cb._current_step_id == "step-1"
        cb.exit_step()
        assert cb._current_step_id is None

    def test_enter_exit_tool(self) -> None:
        cb, _ = _make_callback()
        cb.enter_tool("tool-1")
        assert cb._current_tool_call_id == "tool-1"
        cb.exit_tool()
        assert cb._current_tool_call_id is None


class TestStepIndexMonotonicCounter:
    """M3: ai_run_step.step_index 발급용 monotonic 카운터."""

    def test_initial_step_index_is_zero(self) -> None:
        cb, _ = _make_callback()
        assert cb._step_index == 0

    def test_enter_step_increments_index(self) -> None:
        cb, _ = _make_callback()
        cb.enter_step("step-1")
        assert cb._step_index == 1
        cb.enter_step("step-2")
        assert cb._step_index == 2

    def test_exit_step_does_not_reset_index(self) -> None:
        """M3 §4.4: exit_step에서 reset 안 함 — retry 시 시퀀스 충돌 방지."""
        cb, _ = _make_callback()
        cb.enter_step("step-1")
        cb.exit_step()
        assert cb._step_index == 1  # 1 유지
        cb.enter_step("step-2")
        assert cb._step_index == 2

    def test_step_index_isolated_per_callback_instance(self) -> None:
        cb1, _ = _make_callback()
        cb2, _ = _make_callback()
        cb1.enter_step("a")
        cb2.enter_step("b")
        cb1.enter_step("c")
        assert cb1._step_index == 2
        assert cb2._step_index == 1


class TestOnLlmEndOpenAI:
    @pytest.mark.asyncio
    async def test_openai_tokens_parsed_correctly(self) -> None:
        cb, tracker = _make_callback()
        cb.set_purpose(RunPurpose.SUPERVISOR)
        cb.enter_step("step-1")
        lc_run_id = uuid.uuid4()
        await cb.on_llm_start({}, [], run_id=lc_run_id)

        result = _result_with_llm_output(
            "gpt-4o",
            {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        )
        await cb.on_llm_end(result, run_id=lc_run_id)

        tracker.record_llm_call.assert_awaited_once()
        kwargs = tracker.record_llm_call.await_args.kwargs
        assert kwargs["provider"] == "openai"
        assert kwargs["model_name"] == "gpt-4o"
        assert kwargs["purpose"] is RunPurpose.SUPERVISOR
        assert kwargs["step_id"] == "step-1"
        assert kwargs["status"] == "SUCCESS"
        usage: TokenUsage = kwargs["token_usage"]
        assert usage.prompt_tokens == 100
        assert usage.completion_tokens == 50
        assert usage.total_tokens == 150


class TestOnLlmEndAnthropic:
    @pytest.mark.asyncio
    async def test_anthropic_input_output_tokens_normalized(self) -> None:
        cb, tracker = _make_callback()
        lc_run_id = uuid.uuid4()
        await cb.on_chat_model_start({}, [], run_id=lc_run_id)

        result = LLMResult(
            generations=[[]],
            llm_output={
                "model_name": "claude-3-5-sonnet-20241022",
                "token_usage": {"input_tokens": 80, "output_tokens": 40},
            },
        )
        await cb.on_llm_end(result, run_id=lc_run_id)

        kwargs = tracker.record_llm_call.await_args.kwargs
        assert kwargs["provider"] == "anthropic"
        usage: TokenUsage = kwargs["token_usage"]
        assert usage.prompt_tokens == 80
        assert usage.completion_tokens == 40
        assert usage.total_tokens == 120


class TestOnLlmEndOllama:
    @pytest.mark.asyncio
    async def test_ollama_prompt_eval_count_normalized(self) -> None:
        cb, tracker = _make_callback()
        lc_run_id = uuid.uuid4()
        await cb.on_llm_start({}, [], run_id=lc_run_id)

        result = LLMResult(
            generations=[[]],
            llm_output={
                "model_name": "llama3",
                "token_usage": {"prompt_eval_count": 30, "eval_count": 60},
            },
        )
        await cb.on_llm_end(result, run_id=lc_run_id)

        kwargs = tracker.record_llm_call.await_args.kwargs
        assert kwargs["provider"] == "ollama"
        usage: TokenUsage = kwargs["token_usage"]
        assert usage.prompt_tokens == 30
        assert usage.completion_tokens == 60
        assert usage.total_tokens == 90


class TestOnLlmEndUnknownProvider:
    @pytest.mark.asyncio
    async def test_unknown_provider_falls_back_to_openai_keys(self) -> None:
        cb, tracker = _make_callback()
        lc_run_id = uuid.uuid4()
        await cb.on_llm_start({}, [], run_id=lc_run_id)

        result = LLMResult(
            generations=[[]],
            llm_output={
                "model_name": "mystery-7b",
                "token_usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15,
                },
            },
        )
        await cb.on_llm_end(result, run_id=lc_run_id)

        kwargs = tracker.record_llm_call.await_args.kwargs
        assert kwargs["provider"] == "unknown"
        assert kwargs["model_name"] == "mystery-7b"


class TestOnLlmError:
    @pytest.mark.asyncio
    async def test_on_llm_error_records_failed_status(self) -> None:
        cb, tracker = _make_callback()
        cb.set_purpose(RunPurpose.WORKER)
        lc_run_id = uuid.uuid4()
        await cb.on_llm_start({}, [], run_id=lc_run_id)

        await cb.on_llm_error(
            RuntimeError("rate limit"),
            run_id=lc_run_id,
            invocation_params={"model": "gpt-4o"},
        )

        kwargs = tracker.record_llm_call.await_args.kwargs
        assert kwargs["status"] == "FAILED"
        assert kwargs["error_text"] == "rate limit"
        assert kwargs["provider"] == "openai"
        assert kwargs["token_usage"] == TokenUsage()


class TestLatencyMs:
    @pytest.mark.asyncio
    async def test_latency_is_calculated_from_start_to_end(self) -> None:
        cb, tracker = _make_callback()
        lc_run_id = uuid.uuid4()
        await cb.on_llm_start({}, [], run_id=lc_run_id)

        # 단순히 호출됨을 검증 (실제 latency는 환경 의존)
        result = _result_with_llm_output(
            "gpt-4o", {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}
        )
        await cb.on_llm_end(result, run_id=lc_run_id)

        kwargs = tracker.record_llm_call.await_args.kwargs
        assert kwargs["latency_ms"] is not None
        assert kwargs["latency_ms"] >= 0


class TestRecordLlmCallFailureIsSwallowed:
    @pytest.mark.asyncio
    async def test_tracker_failure_does_not_propagate(self) -> None:
        cb, tracker = _make_callback()
        tracker.record_llm_call.side_effect = RuntimeError("tracker down")
        lc_run_id = uuid.uuid4()
        await cb.on_llm_start({}, [], run_id=lc_run_id)

        result = _result_with_llm_output(
            "gpt-4o", {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}
        )
        # 예외 전파 X
        await cb.on_llm_end(result, run_id=lc_run_id)
