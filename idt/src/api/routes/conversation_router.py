"""Conversation API: Multi-Turn 대화 메모리 관리 엔드포인트."""
import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from src.application.conversation.use_case import ConversationUseCase
from src.domain.conversation.schemas import ConversationChatRequest

router = APIRouter(prefix="/api/v1/conversation", tags=["conversation"])


class ConversationAPIRequest(BaseModel):
    """대화 질의 API 요청 스키마."""

    user_id: str = Field(..., description="사용자 ID")
    session_id: str = Field(..., description="세션 ID")
    message: str = Field(..., description="사용자 메시지")


class ConversationAPIResponse(BaseModel):
    """대화 질의 API 응답 스키마."""

    user_id: str
    session_id: str
    answer: str
    was_summarized: bool
    request_id: str


def get_conversation_use_case() -> ConversationUseCase:
    """Dependency placeholder — overridden in create_app()."""
    raise NotImplementedError("ConversationUseCase not initialized")


@router.post("/chat", response_model=ConversationAPIResponse)
async def conversation_chat(
    request: ConversationAPIRequest,
    use_case: ConversationUseCase = Depends(get_conversation_use_case),
) -> ConversationAPIResponse:
    """Multi-Turn 대화 메모리 관리 API.

    6턴 초과 시 오래된 히스토리를 LLM으로 요약하고,
    (요약본 + 최근 3턴)만 컨텍스트로 사용하여 LLM 답변을 생성합니다.

    Args:
        request: 사용자 ID, 세션 ID, 메시지.
        use_case: 주입된 ConversationUseCase.

    Returns:
        LLM 생성 답변 + 요약 발생 여부.
    """
    request_id = str(uuid.uuid4())
    domain_request = ConversationChatRequest(
        user_id=request.user_id,
        session_id=request.session_id,
        message=request.message,
    )
    result = await use_case.execute(domain_request, request_id)
    return ConversationAPIResponse(
        user_id=result.user_id,
        session_id=result.session_id,
        answer=result.answer,
        was_summarized=result.was_summarized,
        request_id=result.request_id,
    )
