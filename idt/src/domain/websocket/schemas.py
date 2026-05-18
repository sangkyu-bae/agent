"""WebSocket domain schemas — message types, envelope, connection VO, close codes."""
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class WSMessageType(str, Enum):
    PING = "ping"
    PONG = "pong"
    ERROR = "error"
    CONNECTED = "connected"

    AGENT_STEP = "agent_step"
    AGENT_DONE = "agent_done"
    CHAT_TOKEN = "chat_token"
    CHAT_DONE = "chat_done"
    INGEST_PROGRESS = "ingest_progress"
    INGEST_DONE = "ingest_done"


class WSMessage(BaseModel):
    type: str
    data: Any = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: Optional[dict[str, Any]] = None


class WSErrorData(BaseModel):
    code: str
    message: str


class WSErrorMessage(WSMessage):
    type: str = "error"
    data: WSErrorData


@dataclass(frozen=True)
class WSConnection:
    user_id: int
    room_id: Optional[str] = None
    connected_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class WSCloseCode:
    NORMAL = 1000
    AUTH_FAILED = 4001
    FORBIDDEN = 4002
    NOT_FOUND = 4003
    RATE_LIMITED = 4004
    INTERNAL_ERROR = 4500
