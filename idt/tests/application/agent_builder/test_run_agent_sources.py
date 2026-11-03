"""ANSWER_COMPLETED.sources — agent-run-source-citations FR-01·FR-11·FR-12."""
import ast
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from langgraph.errors import GraphRecursionError

from src.application.agent_builder.run_agent_use_case import RunAgentUseCase
from src.application.agent_builder.schemas import RunAgentRequest
from src.domain.agent_run.source_policy import RunSourceItem, SourceKind
from src.domain.agent_run.value_objects import AgentRunEventType
from tests.application.agent_builder.test_run_agent_use_case_stream import (
    _ai_message,
    _collect,
    _make_stream_use_case,
)

SRC = Path(__file__).resolve().parents[3] / "src"
ITEM = RunSourceItem(SourceKind.DOCUMENT, "a.pdf", "발췌", "doc-1")
REQUEST = RunAgentRequest(query="안녕", user_id="user-1")


def _reader(items: list[RunSourceItem]) -> MagicMock:
    reader = MagicMock()
    reader.load_for_run = AsyncMock(return_value=items)
    return reader


def _answer(events: list) -> dict:
    return next(
        e.payload for e in events
        if e.event_type == AgentRunEventType.ANSWER_COMPLETED
    )


async def _run(use_case: RunAgentUseCase, agent_id: str, **kwargs) -> dict:
    return _answer(await _collect(use_case.stream(agent_id, REQUEST, "req-1", **kwargs)))


@pytest.mark.asyncio
class TestAnswerPayloadSources:
    async def test_opt_in_attaches_wire_format(self) -> None:
        use_case, agent, *_ = _make_stream_use_case(astream_event_list=[])
        reader = _reader([ITEM])
        use_case._run_sources = reader

        payload = await _run(use_case, agent.id, include_sources=True)

        assert payload["sources"] == [ITEM.to_payload()]
        assert reader.load_for_run.await_args.args[1] == "req-1"

    async def test_default_issues_no_read(self) -> None:
        use_case, agent, *_ = _make_stream_use_case(astream_event_list=[])
        reader = _reader([ITEM])
        use_case._run_sources = reader

        payload = await _run(use_case, agent.id)

        assert "sources" not in payload
        reader.load_for_run.assert_not_awaited()

    async def test_no_sources_means_no_key(self) -> None:
        use_case, agent, *_ = _make_stream_use_case(astream_event_list=[])
        use_case._run_sources = _reader([])
        assert "sources" not in await _run(use_case, agent.id, include_sources=True)

    async def test_reader_not_wired_keeps_existing_behaviour(self) -> None:
        use_case, agent, *_ = _make_stream_use_case(astream_event_list=[])
        assert "sources" not in await _run(use_case, agent.id, include_sources=True)

    async def test_no_tracker_means_no_run_id_and_no_read(self) -> None:
        use_case, agent, *_ = _make_stream_use_case(
            astream_event_list=[], with_tracker=False,
        )
        reader = _reader([ITEM])
        use_case._run_sources = reader
        assert "sources" not in await _run(use_case, agent.id, include_sources=True)
        reader.load_for_run.assert_not_awaited()

    async def test_answer_event_precedes_run_completed(self) -> None:
        use_case, agent, *_ = _make_stream_use_case(astream_event_list=[])
        use_case._run_sources = _reader([ITEM])
        events = await _collect(
            use_case.stream(agent.id, REQUEST, "req-1", include_sources=True),
        )
        types = [e.event_type for e in events]
        assert types.index(AgentRunEventType.ANSWER_COMPLETED) < types.index(
            AgentRunEventType.RUN_COMPLETED
        )

    async def test_approval_pending_turn_also_attaches(self) -> None:
        # Design §4.2 — 게이트 이전에 조회한 근거도 승인 대기 답변에 싣는다.
        use_case, agent, *_ = _make_stream_use_case(astream_event_list=[])
        use_case._run_sources = _reader([ITEM])
        use_case._persist_approval_if_pending = AsyncMock(return_value="ap-1")

        payload = await _run(use_case, agent.id, include_sources=True)

        assert payload["approval_pending"] is True
        assert payload["approval_id"] == "ap-1"
        assert payload["sources"] == [ITEM.to_payload()]

    async def test_degraded_completion_also_attaches(self) -> None:
        use_case, agent, _, mock_graph, _ = _make_stream_use_case(astream_event_list=[])
        use_case._run_sources = _reader([ITEM])
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

        payload = await _run(use_case, agent.id, include_sources=True)

        assert payload["limit_reached"] is True
        assert payload["sources"] == [ITEM.to_payload()]


class TestSourcesContract:
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
                for v in self._keyword_values(path, "include_sources")
            )
        )
        assert opted_in == ["api/routes/ws_router.py"]

    def test_app_wires_reader_into_use_case(self) -> None:
        assert self._keyword_values(SRC / "api" / "main.py", "run_sources")

    def test_guard_blocked_turn_does_not_read_sources(self) -> None:
        tree = ast.parse(
            (SRC / "application/agent_builder/run_agent_use_case.py")
            .read_text(encoding="utf-8")
        )
        guard = next(
            n for n in ast.walk(tree)
            if isinstance(n, ast.AsyncFunctionDef) and n.name == "_guard_blocked_events"
        )
        calls = {
            n.func.attr for n in ast.walk(guard)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        }
        assert "_attach_sources" not in calls
