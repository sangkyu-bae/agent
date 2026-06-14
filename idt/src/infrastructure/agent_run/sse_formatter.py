"""AgentRunEvent → SSE wire bytes formatter.

Design §3.4 / §5.3 (agent-run-streaming-sse).

EventSource API 호환 라인 포맷:

    event: <type>
    id: <seq>
    data: <json>
    <blank>

heartbeat는 SSE 주석 라인 (": ..."), payload는 single-line JSON.
멀티라인 data는 클라이언트가 라인별로 다시 합쳐야 하므로 회피한다.
"""
import json
from typing import Final

from src.domain.agent_run.value_objects import AgentRunEvent

_LINE_SEP: Final[bytes] = b"\n"
_BLOCK_SEP: Final[bytes] = b"\n\n"


class AgentRunEventSseFormatter:
    """transport-독립 AgentRunEvent를 SSE wire bytes로 직렬화."""

    @staticmethod
    def format(event: AgentRunEvent) -> bytes:
        """단일 이벤트 → SSE 라인 블록."""
        payload_json = json.dumps(
            dict(event.payload), ensure_ascii=False, default=str
        )
        lines = [
            f"event: {event.event_type.value}".encode("utf-8"),
            f"id: {event.seq}".encode("utf-8"),
            f"data: {payload_json}".encode("utf-8"),
        ]
        return _LINE_SEP.join(lines) + _BLOCK_SEP

    @staticmethod
    def format_error(code: str, message: str, seq: int) -> bytes:
        """스트림 중간 실패 → run_failed 이벤트로 송출."""
        body = json.dumps(
            {"code": code, "message": message},
            ensure_ascii=False,
        )
        lines = [
            b"event: run_failed",
            f"id: {seq}".encode("utf-8"),
            f"data: {body}".encode("utf-8"),
        ]
        return _LINE_SEP.join(lines) + _BLOCK_SEP

    @staticmethod
    def format_heartbeat() -> bytes:
        """idle keep-alive — SSE 주석 라인."""
        return b": heartbeat" + _BLOCK_SEP
