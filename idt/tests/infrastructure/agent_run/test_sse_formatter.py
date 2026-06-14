"""AgentRunEventSseFormatter tests — SSE wire bytes 직렬화 검증.

Design §3.4 / §5.3 (agent-run-streaming-sse).
mock 금지 — pure serializer.
"""
from datetime import datetime, timezone

from src.domain.agent_run.value_objects import (
    AgentRunEvent,
    AgentRunEventType,
)
from src.infrastructure.agent_run.sse_formatter import AgentRunEventSseFormatter


def _make_event(
    seq: int = 1,
    event_type: AgentRunEventType = AgentRunEventType.RUN_STARTED,
    payload: dict | None = None,
) -> AgentRunEvent:
    return AgentRunEvent(
        seq=seq,
        event_type=event_type,
        run_id="11111111-2222-3333-4444-555555555555",
        payload=payload if payload is not None else {"k": "v"},
        timestamp=datetime(2026, 5, 24, 12, 0, 0, tzinfo=timezone.utc),
    )


class TestFormat:
    def test_returns_bytes(self) -> None:
        out = AgentRunEventSseFormatter.format(_make_event())
        assert isinstance(out, bytes)

    def test_three_lines_event_id_data(self) -> None:
        ev = _make_event(
            seq=42,
            event_type=AgentRunEventType.NODE_STARTED,
            payload={"node_name": "supervisor", "node_type": "SUPERVISOR"},
        )
        out = AgentRunEventSseFormatter.format(ev).decode("utf-8")

        assert out.startswith("event: node_started\n")
        assert "id: 42\n" in out
        assert 'data: {"node_name": "supervisor", "node_type": "SUPERVISOR"}' in out

    def test_ends_with_double_newline(self) -> None:
        out = AgentRunEventSseFormatter.format(_make_event())
        assert out.endswith(b"\n\n")

    def test_korean_payload_not_escaped(self) -> None:
        ev = _make_event(
            event_type=AgentRunEventType.TOKEN,
            payload={"chunk": "안녕", "node_name": "final_answer"},
        )
        out = AgentRunEventSseFormatter.format(ev).decode("utf-8")
        assert "안녕" in out
        assert "\\u" not in out  # ensure_ascii=False

    def test_datetime_in_payload_serialized_as_str(self) -> None:
        ev = _make_event(
            payload={"started_at": datetime(2026, 5, 24, tzinfo=timezone.utc)},
        )
        out = AgentRunEventSseFormatter.format(ev).decode("utf-8")
        assert "2026-05-24" in out

    def test_payload_is_single_line(self) -> None:
        # SSE 멀티라인 data를 피하기 위해 payload JSON은 한 줄.
        ev = _make_event(payload={"a": 1, "b": [1, 2, 3]})
        out = AgentRunEventSseFormatter.format(ev).decode("utf-8")
        # 3 라인 + 마지막 빈 라인 = "event:", "id:", "data:", ""
        non_empty_lines = [ln for ln in out.split("\n") if ln]
        assert len(non_empty_lines) == 3

    def test_event_type_uses_enum_value(self) -> None:
        ev = _make_event(event_type=AgentRunEventType.RUN_COMPLETED)
        out = AgentRunEventSseFormatter.format(ev).decode("utf-8")
        # AgentRunEventType.RUN_COMPLETED 그 자체가 아니라 "run_completed"
        assert out.startswith("event: run_completed\n")


class TestFormatHeartbeat:
    def test_is_sse_comment(self) -> None:
        out = AgentRunEventSseFormatter.format_heartbeat()
        assert out == b": heartbeat\n\n"


class TestFormatError:
    def test_uses_run_failed_event_type(self) -> None:
        out = AgentRunEventSseFormatter.format_error(
            code="GRAPH_EXEC_FAILED", message="timeout", seq=99
        ).decode("utf-8")
        assert out.startswith("event: run_failed\n")
        assert "id: 99\n" in out
        assert '"code": "GRAPH_EXEC_FAILED"' in out
        assert '"message": "timeout"' in out

    def test_ends_with_double_newline(self) -> None:
        out = AgentRunEventSseFormatter.format_error("X", "msg", 1)
        assert out.endswith(b"\n\n")

    def test_korean_message_not_escaped(self) -> None:
        out = AgentRunEventSseFormatter.format_error(
            code="UNAUTHORIZED", message="권한 없음", seq=0
        ).decode("utf-8")
        assert "권한 없음" in out
