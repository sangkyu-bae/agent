"""AgentRunEvent / AgentRunEventType value object tests.

Design §3.1 / §3.2 (agent-run-streaming-sse) — transport-독립 이벤트 VO.
mock 금지 (domain 규칙).
"""
from datetime import datetime, timezone

import pytest

from src.domain.agent_run.value_objects import (
    AgentRunEvent,
    AgentRunEventType,
)


class TestAgentRunEventType:
    def test_all_event_types_exist(self) -> None:
        # 9 base types (agent-run-streaming-sse) + STEP_REASONING
        # (agent-chat-reasoning-display §3.1.1) = 10.
        assert AgentRunEventType.RUN_STARTED.value == "run_started"
        assert AgentRunEventType.NODE_STARTED.value == "node_started"
        assert AgentRunEventType.NODE_COMPLETED.value == "node_completed"
        assert AgentRunEventType.STEP_REASONING.value == "step_reasoning"
        assert AgentRunEventType.TOOL_STARTED.value == "tool_started"
        assert AgentRunEventType.TOOL_COMPLETED.value == "tool_completed"
        assert AgentRunEventType.TOKEN.value == "token"
        assert AgentRunEventType.ANSWER_COMPLETED.value == "answer_completed"
        assert AgentRunEventType.RUN_COMPLETED.value == "run_completed"
        assert AgentRunEventType.RUN_FAILED.value == "run_failed"

    def test_is_str_enum(self) -> None:
        # SSE wire format에서 직접 직렬화되므로 str enum이어야 한다.
        assert isinstance(AgentRunEventType.RUN_STARTED, str)


class TestAgentRunEvent:
    def _make_ts(self) -> datetime:
        return datetime(2026, 5, 24, 12, 0, 0, tzinfo=timezone.utc)

    def test_valid_construction(self) -> None:
        ev = AgentRunEvent(
            seq=1,
            event_type=AgentRunEventType.RUN_STARTED,
            run_id="11111111-2222-3333-4444-555555555555",
            payload={"agent_id": "ag1"},
            timestamp=self._make_ts(),
        )
        assert ev.seq == 1
        assert ev.event_type == AgentRunEventType.RUN_STARTED
        assert ev.run_id == "11111111-2222-3333-4444-555555555555"
        assert ev.payload == {"agent_id": "ag1"}
        assert ev.timestamp == self._make_ts()

    def test_run_id_can_be_none_before_run_started(self) -> None:
        ev = AgentRunEvent(
            seq=0,
            event_type=AgentRunEventType.RUN_STARTED,
            run_id=None,
            payload={},
            timestamp=self._make_ts(),
        )
        assert ev.run_id is None

    def test_negative_seq_raises(self) -> None:
        with pytest.raises(ValueError, match="seq"):
            AgentRunEvent(
                seq=-1,
                event_type=AgentRunEventType.TOKEN,
                run_id=None,
                payload={},
                timestamp=self._make_ts(),
            )

    def test_naive_timestamp_raises(self) -> None:
        naive = datetime(2026, 5, 24, 12, 0, 0)  # no tzinfo
        with pytest.raises(ValueError, match="timezone-aware"):
            AgentRunEvent(
                seq=0,
                event_type=AgentRunEventType.RUN_STARTED,
                run_id=None,
                payload={},
                timestamp=naive,
            )

    def test_is_frozen(self) -> None:
        ev = AgentRunEvent(
            seq=1,
            event_type=AgentRunEventType.TOKEN,
            run_id=None,
            payload={"chunk": "hi"},
            timestamp=self._make_ts(),
        )
        with pytest.raises(Exception):
            ev.seq = 2  # type: ignore[misc]

    def test_payload_accepts_arbitrary_mapping(self) -> None:
        payload = {
            "node_name": "supervisor",
            "duration_ms": 820,
            "nested": {"k": "v"},
            "list": [1, 2, 3],
        }
        ev = AgentRunEvent(
            seq=5,
            event_type=AgentRunEventType.NODE_COMPLETED,
            run_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            payload=payload,
            timestamp=self._make_ts(),
        )
        assert ev.payload["node_name"] == "supervisor"
        assert ev.payload["nested"]["k"] == "v"
        assert ev.payload["list"] == [1, 2, 3]
