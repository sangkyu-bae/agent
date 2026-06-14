"""WebSocket subscribe payload schemas.

Design fe-websocket-integration-guide §4.1.

WS 연결 직후 클라이언트가 보내는 첫 메시지(subscribe) 검증용.
잘못된 페이로드는 ValidationError → 라우터가 close하도록 한다.
"""
from typing import Literal, Optional

from pydantic import BaseModel, Field


class AttachmentRefPayload(BaseModel):
    """subscribe 메시지의 첨부 참조 (ws-agent-excel-attachment Design §4.3).

    실제 파일은 `POST /api/v1/agent/attachments`로 먼저 업로드해 file_id를 발급받는다.
    type은 표시/전달용이며 권위 있는 타입은 서버 저장 메타가 결정한다.
    """

    type: str = Field(min_length=1)  # 현재 "excel" (확장 가능)
    file_id: str = Field(min_length=1)


class SubscribeAgentRunPayload(BaseModel):
    """`/ws/agent/{run_id}` 의 첫 메시지 — 어떤 agent를 어떤 query로 실행할지."""

    type: Literal["subscribe"]
    agent_id: str = Field(min_length=1)
    query: str = Field(min_length=1)
    session_id: Optional[str] = None
    # ws-agent-excel-attachment: 엑셀 등 첨부 참조 (optional, 없으면 기존과 동일)
    attachments: Optional[list[AttachmentRefPayload]] = None


class SubscribeChatPayload(BaseModel):
    """`/ws/chat/{session_id}` 의 첫 메시지 — general chat 실행.

    ws-chat-streaming Design §3.5.
    """

    type: Literal["subscribe"]
    message: str = Field(min_length=1)
    top_k: Optional[int] = Field(default=5, ge=1, le=20)
    llm_model_id: Optional[str] = None  # 향후 모델 선택 확장
