"""ChatEvent → WSMessage adapter.

Design ws-chat-streaming §3.4.

`AgentRunEventWsAdapter`(SSE formatter mirror)와 동일 패턴.
순수 함수 — 외부 의존 0 (domain VO + Pydantic 스키마만 사용).
"""
from typing import Final

from src.domain.general_chat.value_objects import ChatEvent, ChatEventType
from src.domain.websocket.schemas import WSMessage

_TYPE_MAP: Final[dict[ChatEventType, str]] = {
    ChatEventType.CHAT_STARTED: "chat_started",
    ChatEventType.TOKEN: "chat_token",
    ChatEventType.STEP_REASONING: "chat_step_reasoning",
    ChatEventType.TOOL_STARTED: "chat_tool_started",
    ChatEventType.TOOL_COMPLETED: "chat_tool_completed",
    ChatEventType.ANSWER_COMPLETED: "chat_answer_completed",
    ChatEventType.CHAT_DONE: "chat_done",
    ChatEventType.CHAT_FAILED: "chat_failed",
}


class ChatEventWsAdapter:
    """transport-독립 ChatEvent를 WSMessage로 변환."""

    @staticmethod
    def to_ws_message(event: ChatEvent, *, cached: bool = False) -> WSMessage:
        meta: dict = {"seq": event.seq, "ts": event.timestamp.isoformat()}
        if cached:
            meta["cached"] = True
        return WSMessage(
            type=_TYPE_MAP[event.event_type],
            data=dict(event.payload),
            metadata=meta,
        )
