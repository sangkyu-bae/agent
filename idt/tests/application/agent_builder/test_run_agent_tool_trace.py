"""ANSWER_COMPLETED.tool_trace — agent-run-tool-trace §4.3 (Plan FR-10·FR-11).

근거 칩(test_run_agent_sources.py)과 같은 구조로 고정한다: opt-in 기본 False,
WS 라우트만 켬, 일반·강등 완료 두 지점, 없으면 키 미포함.
"""
import ast
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from langgraph.errors import GraphRecursionError

from src.application.agent_builder.run_agent_use_case import RunAgentUseCase
from src.application.agent_builder.schemas import RunAgentRequest
from src.domain.agent_run.tool_trace_policy import ToolTrace, ToolTraceItem, ToolTraceKind
from src.domain.agent_run.value_objects import AgentRunEventType
from tests.application.agent_builder.test_run_agent_use_case_stream import (
    _ai_message,
    _collect,
    _make_stream_use_case,
)

SRC = Path(__file__).resolve().parents[3] / "src"
TRACE = ToolTrace(
    items=[ToolTraceItem(seq=1, kind=ToolTraceKind.TOOL, label="도구", output="결과")],
)
REQUEST = RunAgentRequest(query="안녕", user_id="user-1")


def _reader(trace) -> MagicMock:
    reader = MagicMock()
    reader.load_for_run = AsyncMock(return_value=trace)
    return reader


def _answer(events: list) -> dict:
    return next(
        e.payload for e in events
        if e.event_type == AgentRunEventType.ANSWER_COMPLETED
    )


async def _run(use_case: RunAgentUseCase, agent_id: str, **kwargs) -> dict:
    return _answer(await _collect(use_case.stream(agent_id, REQUEST, "req-1", **kwargs)))


@pytest.mark.asyncio
class TestAnswerPayloadToolTrace:
    async def test_opt_in_attaches_wire_format(self) -> None:
        use_case, agent, *_ = _make_stream_use_case(astream_event_list=[])
        reader = _reader(TRACE)
        use_case._run_tool_trace = reader

        payload = await _run(use_case, agent.id, include_tool_trace=True)

        assert payload["tool_trace"] == TRACE.to_payload()
        assert reader.load_for_run.await_args.args[1] == "req-1"

    async def test_default_issues_no_read(self) -> None:
        use_case, agent, *_ = _make_stream_use_case(astream_event_list=[])
        reader = _reader(TRACE)
        use_case._run_tool_trace = reader

        payload = await _run(use_case, agent.id)

        assert "tool_trace" not in payload
        reader.load_for_run.assert_not_awaited()

    async def test_no_trace_means_no_key(self) -> None:
        use_case, agent, *_ = _make_stream_use_case(astream_event_list=[])
        use_case._run_tool_trace = _reader(None)
        assert "tool_trace" not in await _run(use_case, agent.id, include_tool_trace=True)

    async def test_reader_not_wired_keeps_existing_behaviour(self) -> None:
        use_case, agent, *_ = _make_stream_use_case(astream_event_list=[])
        assert "tool_trace" not in await _run(use_case, agent.id, include_tool_trace=True)

    async def test_no_tracker_means_no_run_id_and_no_read(self) -> None:
        use_case, agent, *_ = _make_stream_use_case(
            astream_event_list=[], with_tracker=False,
        )
        reader = _reader(TRACE)
        use_case._run_tool_trace = reader
        assert "tool_trace" not in await _run(use_case, agent.id, include_tool_trace=True)
        reader.load_for_run.assert_not_awaited()

    async def test_sources_and_tool_trace_coexist(self) -> None:
        use_case, agent, *_ = _make_stream_use_case(astream_event_list=[])
        use_case._run_tool_trace = _reader(TRACE)
        sources = MagicMock()
        sources.load_for_run = AsyncMock(return_value=[])
        use_case._run_sources = sources

        payload = await _run(
            use_case, agent.id, include_sources=True, include_tool_trace=True,
        )

        assert payload["tool_trace"] == TRACE.to_payload()
        sources.load_for_run.assert_awaited_once()

    async def test_degraded_completion_also_attaches(self) -> None:
        use_case, agent, _, mock_graph, _ = _make_stream_use_case(astream_event_list=[])
        use_case._run_tool_trace = _reader(TRACE)
        partial = {
            "event": "on_chain_end", "name": "LangGraph",
            "data": {"output": {"messages": [_ai_message("부분 답변")]}},
            "metadata": {}, "run_id": "top",
        }

        def _raising(*args, **kwargs):
            async def _gen():
                yield partial
                raise GraphRecursionError("limit")
            return _gen()

        mock_graph.astream_events = _raising

        payload = await _run(use_case, agent.id, include_tool_trace=True)

        assert payload["limit_reached"] is True
        assert payload["tool_trace"] == TRACE.to_payload()


class TestToolTraceContract:
    """호출자 opt-in 은 소스로 고정한다 (run-agent-caller-optin-gating 선례)."""

    @staticmethod
    def _keyword_values(path: Path, keyword: str) -> list[ast.expr]:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        return [
            kw.value for node in ast.walk(tree) if isinstance(node, ast.Call)
            for kw in node.keywords if kw.arg == keyword
        ]

    def test_only_ws_route_opts_in(self) -> None:
        opted_in = sorted(
            str(path.relative_to(SRC)).replace("\\", "/")
            for path in SRC.rglob("*.py")
            if any(
                isinstance(v, ast.Constant) and v.value is True
                for v in self._keyword_values(path, "include_tool_trace")
            )
        )
        assert opted_in == ["api/routes/ws_router.py"]

    def test_app_wires_reader_into_use_case(self) -> None:
        assert self._keyword_values(SRC / "api" / "main.py", "run_tool_trace")

    def test_stream_default_is_off(self) -> None:
        import inspect
        default = inspect.signature(RunAgentUseCase.stream).parameters["include_tool_trace"].default
        assert default is False
