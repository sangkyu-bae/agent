"""Conversation History API: 저장된 대화 세션/메시지 조회 (CHAT-HIST-001)."""
import uuid
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from src.application.conversation.history_use_case import (
    ConversationHistoryUseCase,
)

router = APIRouter(prefix="/api/v1/conversations", tags=["conversation-history"])


class SessionSummaryAPI(BaseModel):
    """세션 요약 응답 항목."""

    session_id: str = Field(..., description="세션 ID")
    message_count: int = Field(..., description="세션 내 메시지 수")
    last_message: str = Field(..., description="마지막 user 메시지 (100자 truncate)")
    last_message_at: datetime = Field(..., description="마지막 메시지 시각")


class SessionListAPIResponse(BaseModel):
    """사용자 세션 목록 응답."""

    user_id: str
    sessions: List[SessionSummaryAPI]


class MessageItemAPI(BaseModel):
    """메시지 항목."""

    id: int
    role: str
    content: str
    turn_index: int
    created_at: datetime


class MessageListAPIResponse(BaseModel):
    """세션 메시지 목록 응답."""

    user_id: str
    session_id: str
    messages: List[MessageItemAPI]


class AgentChatSummaryAPI(BaseModel):
    """에이전트 채팅 요약 항목."""

    agent_id: str = Field(..., description="에이전트 ID ('super' = 일반 채팅)")
    agent_name: str = Field(..., description="에이전트 이름")
    session_count: int = Field(..., description="세션 수")
    last_chat_at: datetime = Field(..., description="마지막 대화 시각")


class AgentListAPIResponse(BaseModel):
    """에이전트 목록 응답."""

    user_id: str
    agents: List[AgentChatSummaryAPI]


class AgentSessionListAPIResponse(BaseModel):
    """에이전트별 세션 목록 응답."""

    user_id: str
    agent_id: str
    sessions: List[SessionSummaryAPI]


class AgentMessageListAPIResponse(BaseModel):
    """에이전트별 세션 메시지 응답."""

    user_id: str
    agent_id: str
    session_id: str
    messages: List[MessageItemAPI]


def get_history_use_case() -> ConversationHistoryUseCase:
    """Dependency placeholder — overridden in create_app()."""
    raise NotImplementedError("ConversationHistoryUseCase not initialized")


@router.get("/sessions", response_model=SessionListAPIResponse)
async def get_sessions(
    user_id: str = Query(..., description="사용자 ID"),
    use_case: ConversationHistoryUseCase = Depends(get_history_use_case),
) -> SessionListAPIResponse:
    """사용자의 전체 세션 목록을 최신순으로 반환."""
    request_id = str(uuid.uuid4())
    result = await use_case.get_sessions(user_id=user_id, request_id=request_id)
    return SessionListAPIResponse(
        user_id=result.user_id,
        sessions=[
            SessionSummaryAPI(
                session_id=s.session_id,
                message_count=s.message_count,
                last_message=s.last_message,
                last_message_at=s.last_message_at,
            )
            for s in result.sessions
        ],
    )


@router.get(
    "/sessions/{session_id}/messages",
    response_model=MessageListAPIResponse,
)
async def get_messages(
    session_id: str,
    user_id: str = Query(..., description="사용자 ID"),
    use_case: ConversationHistoryUseCase = Depends(get_history_use_case),
) -> MessageListAPIResponse:
    """특정 세션의 전체 메시지를 turn_index 오름차순으로 반환."""
    request_id = str(uuid.uuid4())
    result = await use_case.get_messages(
        user_id=user_id, session_id=session_id, request_id=request_id
    )
    return MessageListAPIResponse(
        user_id=result.user_id,
        session_id=result.session_id,
        messages=[
            MessageItemAPI(
                id=m.id,
                role=m.role,
                content=m.content,
                turn_index=m.turn_index,
                created_at=m.created_at,
            )
            for m in result.messages
        ],
    )


@router.get("/agents", response_model=AgentListAPIResponse)
async def get_agents(
    user_id: str = Query(..., description="사용자 ID"),
    use_case: ConversationHistoryUseCase = Depends(get_history_use_case),
) -> AgentListAPIResponse:
    """대화 기록이 있는 에이전트 목록."""
    request_id = str(uuid.uuid4())
    result = await use_case.get_agents_with_history(
        user_id=user_id, request_id=request_id
    )
    return AgentListAPIResponse(
        user_id=result.user_id,
        agents=[
            AgentChatSummaryAPI(
                agent_id=a.agent_id,
                agent_name=a.agent_name,
                session_count=a.session_count,
                last_chat_at=a.last_chat_at,
            )
            for a in result.agents
        ],
    )


@router.get(
    "/agents/{agent_id}/sessions",
    response_model=AgentSessionListAPIResponse,
)
async def get_agent_sessions(
    agent_id: str,
    user_id: str = Query(..., description="사용자 ID"),
    use_case: ConversationHistoryUseCase = Depends(get_history_use_case),
) -> AgentSessionListAPIResponse:
    """에이전트별 세션 목록."""
    request_id = str(uuid.uuid4())
    result = await use_case.get_sessions_by_agent(
        user_id=user_id, agent_id=agent_id, request_id=request_id
    )
    return AgentSessionListAPIResponse(
        user_id=result.user_id,
        agent_id=result.agent_id,
        sessions=[
            SessionSummaryAPI(
                session_id=s.session_id,
                message_count=s.message_count,
                last_message=s.last_message,
                last_message_at=s.last_message_at,
            )
            for s in result.sessions
        ],
    )


@router.get(
    "/agents/{agent_id}/sessions/{session_id}/messages",
    response_model=AgentMessageListAPIResponse,
)
async def get_agent_session_messages(
    agent_id: str,
    session_id: str,
    user_id: str = Query(..., description="사용자 ID"),
    use_case: ConversationHistoryUseCase = Depends(get_history_use_case),
) -> AgentMessageListAPIResponse:
    """에이전트 세션의 메시지 목록."""
    request_id = str(uuid.uuid4())
    result = await use_case.get_messages_by_agent(
        user_id=user_id,
        agent_id=agent_id,
        session_id=session_id,
        request_id=request_id,
    )
    return AgentMessageListAPIResponse(
        user_id=result.user_id,
        agent_id=result.agent_id,
        session_id=result.session_id,
        messages=[
            MessageItemAPI(
                id=m.id,
                role=m.role,
                content=m.content,
                turn_index=m.turn_index,
                created_at=m.created_at,
            )
            for m in result.messages
        ],
    )
