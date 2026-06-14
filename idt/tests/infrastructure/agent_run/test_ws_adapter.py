"""AgentRunEventWsAdapter tests — AgentRunEvent → WSMessage 변환 검증.

Design fe-websocket-integration-guide §3.2.
mock 금지 — pure mapper.
"""
from datetime import datetime, timezone

import pytest

from src.domain.agent_run.value_objects import AgentRunEvent, AgentRunEventType
from src.domain.websocket.schemas import WSMessage
from src.infrastructure.agent_run.ws_adapter import AgentRunEventWsAdapter


def _make_event(
    seq: int = 1,
    event_type: AgentRunEventType = AgentRunEventType.RUN_STARTED,
    payload: dict | None = None,
    run_id: str | None = "11111111-2222-3333-4444-555555555555",
) -> AgentRunEvent:
    return AgentRunEvent(
        seq=seq,
        event_type=event_type,
        run_id=run_id,
        payload=payload if payload is not None else {"k": "v"},
        timestamp=datetime(2026, 5, 25, 12, 0, 0, tzinfo=timezone.utc),
    )


class TestToWsMessage:
    def test_returns_ws_message(self) -> None:
        result = AgentRunEventWsAdapter.to_ws_message(_make_event())
        assert isinstance(result, WSMessage)

    @pytest.mark.parametrize(
        "event_type, expected_type",
        [
            (AgentRunEventType.RUN_STARTED, "agent_run_started"),
            (AgentRunEventType.NODE_STARTED, "agent_node_started"),
            (AgentRunEventType.NODE_COMPLETED, "agent_node_completed"),
            (AgentRunEventType.STEP_REASONING, "agent_step_reasoning"),
            (AgentRunEventType.TOOL_STARTED, "agent_tool_started"),
            (AgentRunEventType.TOOL_COMPLETED, "agent_tool_completed"),
            (AgentRunEventType.TOKEN, "agent_token"),
            (AgentRunEventType.ANSWER_COMPLETED, "agent_answer_completed"),
            (AgentRunEventType.RUN_COMPLETED, "agent_run_completed"),
            (AgentRunEventType.RUN_FAILED, "agent_run_failed"),
        ],
    )
    def test_maps_all_event_types(
        self, event_type: AgentRunEventType, expected_type: str
    ) -> None:
        out = AgentRunEventWsAdapter.to_ws_message(_make_event(event_type=event_type))
        assert out.type == expected_type

    def test_payload_preserved_as_data(self) -> None:
        payload = {
            "node_name": "final_answer",
            "duration_ms": 1234,
            "nested": {"k": [1, 2]},
        }
        ev = _make_event(event_type=AgentRunEventType.NODE_COMPLETED, payload=payload)
        out = AgentRunEventWsAdapter.to_ws_message(ev)
        assert out.data == payload

    def test_metadata_contains_seq_and_ts(self) -> None:
        ev = _make_event(seq=42)
        out = AgentRunEventWsAdapter.to_ws_message(ev)
        assert out.metadata is not None
        assert out.metadata["seq"] == 42
        # ISO 8601 with tz
        assert out.metadata["ts"].startswith("2026-05-25T12:00:00")

    def test_serializable_to_json(self) -> None:
        ev = _make_event(
            event_type=AgentRunEventType.TOKEN,
            payload={"chunk": "안녕", "node_name": "final_answer"},
        )
        out = AgentRunEventWsAdapter.to_ws_message(ev)
        dumped = out.model_dump(mode="json")
        assert dumped["type"] == "agent_token"
        assert dumped["data"]["chunk"] == "안녕"
        assert dumped["metadata"]["seq"] == 1

    def test_run_failed_payload_pass_through(self) -> None:
        ev = _make_event(
            event_type=AgentRunEventType.RUN_FAILED,
            payload={"code": "GRAPH_EXEC_FAILED", "message": "boom"},
        )
        out = AgentRunEventWsAdapter.to_ws_message(ev)
        assert out.type == "agent_run_failed"
        assert out.data["code"] == "GRAPH_EXEC_FAILED"
        assert out.data["message"] == "boom"

    def test_run_id_none_does_not_break(self) -> None:
        # RUN_STARTED 이전 또는 관측성 비활성 시 run_id가 None일 수 있다.
        ev = _make_event(run_id=None)
        out = AgentRunEventWsAdapter.to_ws_message(ev)
        # adapter는 run_id를 message에 포함시키지 않는다(payload에 이미 들어있음).
        assert isinstance(out, WSMessage)

    def test_step_reasoning_payload_pass_through(self) -> None:
        # agent-chat-reasoning-display Design §4.1
        payload = {
            "step_name": "supervisor",
            "reasoning": "X 정보가 필요해서 search_agent를 호출합니다.",
            "next_worker": "search_agent",
        }
        ev = _make_event(
            event_type=AgentRunEventType.STEP_REASONING, payload=payload
        )
        out = AgentRunEventWsAdapter.to_ws_message(ev)
        assert out.type == "agent_step_reasoning"
        assert out.data == payload
