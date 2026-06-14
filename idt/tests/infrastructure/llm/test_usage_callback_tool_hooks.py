"""UsageCallback on_tool_* hooks (M2) 단위 테스트.

AGENT-OBS-002 Design §4-1 ~ §4-5 검증.
"""
import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.outputs import LLMResult

from src.application.agent_run.context import (
    RunContext,
    get_current_run_context,
    reset_run_context,
    set_current_run_context,
)
from src.application.agent_run.tracker import RunTracker
from src.domain.agent_run.value_objects import RunId, RunPurpose
from src.infrastructure.llm.usage_callback import (
    UsageCallback,
    _sanitize_args,
    _summarize_tool_output,
)


RUN_ID = "11111111-1111-1111-1111-111111111111"


def _make_callback() -> tuple[UsageCallback, MagicMock]:
    tracker = MagicMock(spec=RunTracker)
    tracker.record_tool_call = AsyncMock(return_value="tcid-001")
    tracker.update_tool_call = AsyncMock(return_value=None)
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


# ─────────────────────────── _sanitize_args ──────────────────────────────
class TestSanitizeArgs:
    def test_dict_passthrough(self) -> None:
        assert _sanitize_args({"q": "abc"}) == {"q": "abc"}

    def test_str_wrapped_under_input_key(self) -> None:
        assert _sanitize_args("hello") == {"input": "hello"}

    def test_none_returns_none(self) -> None:
        assert _sanitize_args(None) is None

    def test_non_dict_non_str_wrapped_via_str(self) -> None:
        assert _sanitize_args(42) == {"input": "42"}

    def test_non_json_serializable_object_via_default_str(self) -> None:
        class NotSerializable:
            def __str__(self) -> str:
                return "NotSer-instance"

        out = _sanitize_args({"obj": NotSerializable()})
        assert "NotSer-instance" in json.dumps(out)

    def test_truncation_keeps_under_or_equal_byte_budget(self) -> None:
        big = {"q": "x" * 5000}
        out = _sanitize_args(big)
        # Truncation 표시가 어떤 형태든, 결과 JSON byte 크기가 1KB+여유 이내
        assert out is not None
        serialized = json.dumps(out, ensure_ascii=False)
        # 컷 마커 여유 32바이트 허용
        assert len(serialized.encode("utf-8")) <= 1024 + 64


# ─────────────────────────── _summarize_tool_output ───────────────────────
class TestSummarizeToolOutput:
    def test_none_returns_none(self) -> None:
        assert _summarize_tool_output(None) is None

    def test_str_truncated_at_1024(self) -> None:
        assert _summarize_tool_output("x" * 2000) == "x" * 1024

    def test_short_str_passthrough(self) -> None:
        assert _summarize_tool_output("hello") == "hello"

    def test_dict_serialized_as_json(self) -> None:
        out = _summarize_tool_output({"a": 1, "b": "two"})
        assert out is not None
        assert "two" in out
        assert len(out) <= 1024

    def test_list_serialized_as_json(self) -> None:
        out = _summarize_tool_output(["alpha", "beta"])
        assert out is not None and "alpha" in out

    def test_langchain_document_uses_page_content(self) -> None:
        class FakeDoc:
            page_content = "this is the doc content"
            metadata = {"src": "x"}

        assert _summarize_tool_output(FakeDoc()) == "this is the doc content"

    def test_pydantic_model_uses_model_dump(self) -> None:
        class FakeModel:
            def model_dump(self) -> dict:
                return {"k": "v"}

        out = _summarize_tool_output(FakeModel())
        assert out is not None and "v" in out


# ─────────────────────────── on_tool_start ────────────────────────────────
class TestOnToolStart:
    @pytest.mark.asyncio
    async def test_calls_record_tool_call_with_started_status(self) -> None:
        cb, tracker = _make_callback()
        await cb.on_tool_start(
            serialized={"name": "internal_document_search"},
            input_str='{"query": "test"}',
            run_id=uuid.uuid4(),
        )
        tracker.record_tool_call.assert_awaited_once()
        kwargs = tracker.record_tool_call.await_args.kwargs
        assert kwargs["tool_name"] == "internal_document_search"
        assert kwargs["status"] == "STARTED"
        assert kwargs["run_id"] == RunId(RUN_ID)

    @pytest.mark.asyncio
    async def test_extracts_tool_name_from_id_fallback(self) -> None:
        cb, tracker = _make_callback()
        await cb.on_tool_start(
            serialized={"id": ["langchain", "tools", "my_tool"]},
            input_str="",
            run_id=uuid.uuid4(),
        )
        kwargs = tracker.record_tool_call.await_args.kwargs
        assert kwargs["tool_name"] == "my_tool"

    @pytest.mark.asyncio
    async def test_sets_current_tool_call_id(self) -> None:
        cb, tracker = _make_callback()
        tracker.record_tool_call.return_value = "tcid-001"
        await cb.on_tool_start(
            serialized={"name": "rag_search"},
            input_str="",
            run_id=uuid.uuid4(),
        )
        assert cb._current_tool_call_id == "tcid-001"

    @pytest.mark.asyncio
    async def test_sets_purpose_by_inference(self) -> None:
        cb, tracker = _make_callback()
        await cb.on_tool_start(
            serialized={"name": "query_rewriter_v2"},
            input_str="",
            run_id=uuid.uuid4(),
        )
        assert cb._current_purpose is RunPurpose.QUERY_REWRITE

    @pytest.mark.asyncio
    async def test_prefers_inputs_over_input_str(self) -> None:
        cb, tracker = _make_callback()
        await cb.on_tool_start(
            serialized={"name": "rag_search"},
            input_str="ignored",
            run_id=uuid.uuid4(),
            inputs={"query": "real query"},
        )
        kwargs = tracker.record_tool_call.await_args.kwargs
        assert kwargs["arguments"] == {"query": "real query"}

    @pytest.mark.asyncio
    async def test_registers_in_tool_starts_dict(self) -> None:
        cb, tracker = _make_callback()
        lc_id = uuid.uuid4()
        await cb.on_tool_start(
            serialized={"name": "x"}, input_str="", run_id=lc_id
        )
        assert lc_id in cb._tool_starts

    @pytest.mark.asyncio
    async def test_record_tool_call_failure_degrades_gracefully(self) -> None:
        cb, tracker = _make_callback()
        tracker.record_tool_call.side_effect = RuntimeError("db down")
        lc_id = uuid.uuid4()
        await cb.on_tool_start(
            serialized={"name": "x"}, input_str="", run_id=lc_id
        )
        # _current_tool_call_id 는 갱신되지 않음
        assert cb._current_tool_call_id is None
        # _tool_starts 에는 sentinel 등록되어 매칭 미스 방지
        assert lc_id in cb._tool_starts
        # logger.warning 호출됨
        cb._logger.warning.assert_called()


# ─────────────────────────── on_tool_end ──────────────────────────────────
class TestOnToolEnd:
    @pytest.mark.asyncio
    async def test_calls_update_tool_call_with_success(self) -> None:
        cb, tracker = _make_callback()
        tracker.record_tool_call.return_value = "tcid-001"
        lc_id = uuid.uuid4()
        await cb.on_tool_start(
            serialized={"name": "rag_search"}, input_str="", run_id=lc_id
        )
        await cb.on_tool_end(output={"docs": []}, run_id=lc_id)

        tracker.update_tool_call.assert_awaited_once()
        kwargs = tracker.update_tool_call.await_args.kwargs
        assert kwargs["status"] == "SUCCESS"
        assert kwargs["tool_call_id"] == "tcid-001"
        assert kwargs["run_id"] == RunId(RUN_ID)

    @pytest.mark.asyncio
    async def test_computes_latency_ms(self, monkeypatch) -> None:
        cb, tracker = _make_callback()
        tracker.record_tool_call.return_value = "tcid-001"
        # perf_counter monkeypatch — 결정성 보장
        clock = iter([100.0, 100.123])
        monkeypatch.setattr(
            "src.infrastructure.llm.usage_callback.time.perf_counter",
            lambda: next(clock),
        )
        lc_id = uuid.uuid4()
        await cb.on_tool_start(
            serialized={"name": "x"}, input_str="", run_id=lc_id
        )
        await cb.on_tool_end(output="ok", run_id=lc_id)

        kwargs = tracker.update_tool_call.await_args.kwargs
        assert kwargs["latency_ms"] == 123

    @pytest.mark.asyncio
    async def test_summarizes_output(self) -> None:
        cb, tracker = _make_callback()
        tracker.record_tool_call.return_value = "tcid-001"
        lc_id = uuid.uuid4()
        await cb.on_tool_start(
            serialized={"name": "x"}, input_str="", run_id=lc_id
        )
        await cb.on_tool_end(output="x" * 3000, run_id=lc_id)

        kwargs = tracker.update_tool_call.await_args.kwargs
        assert kwargs["result_summary"] == "x" * 1024

    @pytest.mark.asyncio
    async def test_clears_current_tool_call_id(self) -> None:
        cb, tracker = _make_callback()
        tracker.record_tool_call.return_value = "tcid-001"
        lc_id = uuid.uuid4()
        await cb.on_tool_start(
            serialized={"name": "rag_search"}, input_str="", run_id=lc_id
        )
        assert cb._current_tool_call_id == "tcid-001"
        await cb.on_tool_end(output="ok", run_id=lc_id)
        assert cb._current_tool_call_id is None

    @pytest.mark.asyncio
    async def test_restores_previous_purpose(self) -> None:
        cb, tracker = _make_callback()
        cb.set_purpose(RunPurpose.WORKER)
        tracker.record_tool_call.return_value = "tcid-001"
        lc_id = uuid.uuid4()
        await cb.on_tool_start(
            serialized={"name": "query_rewriter"},
            input_str="",
            run_id=lc_id,
        )
        assert cb._current_purpose is RunPurpose.QUERY_REWRITE
        await cb.on_tool_end(output="ok", run_id=lc_id)
        assert cb._current_purpose is RunPurpose.WORKER

    @pytest.mark.asyncio
    async def test_unmatched_run_id_logs_warning_no_update(self) -> None:
        cb, tracker = _make_callback()
        await cb.on_tool_end(output="ok", run_id=uuid.uuid4())
        tracker.update_tool_call.assert_not_called()
        cb._logger.warning.assert_called()

    @pytest.mark.asyncio
    async def test_skip_update_when_start_was_failed(self) -> None:
        """record_tool_call 실패한 케이스의 end는 update_tool_call을 호출하지 않음."""
        cb, tracker = _make_callback()
        tracker.record_tool_call.side_effect = RuntimeError("boom")
        lc_id = uuid.uuid4()
        await cb.on_tool_start(
            serialized={"name": "x"}, input_str="", run_id=lc_id
        )
        await cb.on_tool_end(output="ok", run_id=lc_id)
        tracker.update_tool_call.assert_not_called()


# ─────────────────────────── on_tool_error ────────────────────────────────
class TestOnToolError:
    @pytest.mark.asyncio
    async def test_calls_update_tool_call_with_failed_status(self) -> None:
        cb, tracker = _make_callback()
        tracker.record_tool_call.return_value = "tcid-001"
        lc_id = uuid.uuid4()
        await cb.on_tool_start(
            serialized={"name": "tavily_search"},
            input_str="",
            run_id=lc_id,
        )
        await cb.on_tool_error(error=RuntimeError("boom"), run_id=lc_id)

        tracker.update_tool_call.assert_awaited_once()
        kwargs = tracker.update_tool_call.await_args.kwargs
        assert kwargs["status"] == "FAILED"
        assert "boom" in (kwargs["error_text"] or "")

    @pytest.mark.asyncio
    async def test_truncates_error_text(self) -> None:
        cb, tracker = _make_callback()
        tracker.record_tool_call.return_value = "tcid-001"
        lc_id = uuid.uuid4()
        await cb.on_tool_start(
            serialized={"name": "x"}, input_str="", run_id=lc_id
        )
        big_msg = "e" * 3000
        await cb.on_tool_error(error=RuntimeError(big_msg), run_id=lc_id)

        kwargs = tracker.update_tool_call.await_args.kwargs
        assert len(kwargs["error_text"]) == 1024

    @pytest.mark.asyncio
    async def test_unmatched_run_id_logs_warning(self) -> None:
        cb, tracker = _make_callback()
        await cb.on_tool_error(error=RuntimeError("x"), run_id=uuid.uuid4())
        tracker.update_tool_call.assert_not_called()
        cb._logger.warning.assert_called()


# ─────────────────────────── RunContext 동기화 ────────────────────────────
class TestRunContextSync:
    @pytest.mark.asyncio
    async def test_run_context_tool_call_id_set_and_reset(self) -> None:
        cb, tracker = _make_callback()
        tracker.record_tool_call.return_value = "tcid-001"
        # 활성 RunContext 세팅
        ctx = RunContext(
            run_id=RunId(RUN_ID),
            user_id="u1",
            agent_id="a1",
            callback=cb,
        )
        token = set_current_run_context(ctx)
        try:
            lc_id = uuid.uuid4()
            await cb.on_tool_start(
                serialized={"name": "rag_search"},
                input_str="",
                run_id=lc_id,
            )
            cur = get_current_run_context()
            assert cur is not None and cur.tool_call_id == "tcid-001"

            await cb.on_tool_end(output="ok", run_id=lc_id)
            cur = get_current_run_context()
            assert cur is not None and cur.tool_call_id is None
        finally:
            reset_run_context(token)

    @pytest.mark.asyncio
    async def test_no_context_active_does_not_raise(self) -> None:
        """RunContext 미세팅 상태에서 on_tool_start/end도 안전해야 한다."""
        cb, tracker = _make_callback()
        tracker.record_tool_call.return_value = "tcid-001"
        lc_id = uuid.uuid4()
        # set_current_run_context 호출 없이 진행
        await cb.on_tool_start(
            serialized={"name": "rag_search"}, input_str="", run_id=lc_id
        )
        await cb.on_tool_end(output="ok", run_id=lc_id)
        # 예외 발생 없이 완료


# ─────────────────────────── 핵심 회귀 가드 ────────────────────────────────
class TestInnerLlmCallAttachesToolCallId:
    """M2의 단 하나의 가치 보장: 툴 내부 LLM 호출의 tool_call_id 자동 채움."""

    @pytest.mark.asyncio
    async def test_llm_call_inside_tool_attaches_tool_call_id(self) -> None:
        cb, tracker = _make_callback()
        tracker.record_tool_call.return_value = "tcid-XYZ"

        # 1. 툴 진입
        tool_lc_id = uuid.uuid4()
        await cb.on_tool_start(
            serialized={"name": "rag_search"},
            input_str='{"query": "x"}',
            run_id=tool_lc_id,
        )

        # 2. 툴 내부 LLM 호출 (rerank 가정)
        inner_llm_id = uuid.uuid4()
        await cb.on_chat_model_start(
            serialized={}, messages=[], run_id=inner_llm_id
        )
        result = LLMResult(
            generations=[[]],
            llm_output={
                "model_name": "gpt-4o-mini",
                "token_usage": {
                    "prompt_tokens": 50,
                    "completion_tokens": 20,
                    "total_tokens": 70,
                },
            },
        )
        await cb.on_llm_end(result, run_id=inner_llm_id)

        # 3. 검증: record_llm_call의 tool_call_id 인자가 tcid-XYZ
        tracker.record_llm_call.assert_awaited_once()
        kwargs = tracker.record_llm_call.await_args.kwargs
        assert kwargs["tool_call_id"] == "tcid-XYZ"

        # 4. 툴 종료
        await cb.on_tool_end(output="ok", run_id=tool_lc_id)
