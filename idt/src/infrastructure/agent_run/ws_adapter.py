"""AgentRunEvent → WSMessage adapter.

Design fe-websocket-integration-guide §3.2.

`AgentRunEventSseFormatter`(SSE)와 대칭되는 WebSocket transport용 어댑터.
UseCase는 변경하지 않고, transport별 어댑터만 추가한다(SSE 유지 + WS 병렬).

순수 함수 — 외부 의존 없음 (domain VO + Pydantic 메시지 스키마만 사용).
"""
from typing import Final

from src.domain.agent_run.value_objects import AgentRunEvent, AgentRunEventType
from src.domain.websocket.schemas import WSMessage

_TYPE_MAP: Final[dict[AgentRunEventType, str]] = {
    AgentRunEventType.RUN_STARTED: "agent_run_started",
    AgentRunEventType.NODE_STARTED: "agent_node_started",
    AgentRunEventType.NODE_COMPLETED: "agent_node_completed",
    AgentRunEventType.STEP_REASONING: "agent_step_reasoning",
    AgentRunEventType.TOOL_STARTED: "agent_tool_started",
    AgentRunEventType.TOOL_COMPLETED: "agent_tool_completed",
    AgentRunEventType.TOKEN: "agent_token",
    AgentRunEventType.ANSWER_COMPLETED: "agent_answer_completed",
    AgentRunEventType.RUN_COMPLETED: "agent_run_completed",
    AgentRunEventType.RUN_FAILED: "agent_run_failed",
}


class AgentRunEventWsAdapter:
    """transport-독립 AgentRunEvent를 WebSocket용 WSMessage로 변환."""

    @staticmethod
    def to_ws_message(event: AgentRunEvent) -> WSMessage:
        return WSMessage(
            type=_TYPE_MAP[event.event_type],
            data=dict(event.payload),
            metadata={"seq": event.seq, "ts": event.timestamp.isoformat()},
        )
