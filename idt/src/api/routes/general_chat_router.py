"""General Chat API: POST /api/v1/chat."""
import uuid

from fastapi import APIRouter, Depends

from src.application.general_chat.use_case import GeneralChatUseCase
from src.domain.agent_run.auth_context import AuthContext
from src.domain.general_chat.schemas import GeneralChatRequest, GeneralChatResponse
from src.interfaces.dependencies.auth import get_auth_context

router = APIRouter(prefix="/api/v1", tags=["chat"])


def get_general_chat_use_case() -> GeneralChatUseCase:
    """Dependency placeholder — overridden in create_app()."""
    raise NotImplementedError("GeneralChatUseCase not initialized")


@router.post("/chat", response_model=GeneralChatResponse)
async def general_chat(
    body: GeneralChatRequest,
    auth_ctx: AuthContext = Depends(get_auth_context),
    use_case: GeneralChatUseCase = Depends(get_general_chat_use_case),
) -> GeneralChatResponse:
    """LangGraph ReAct 에이전트 기반 범용 채팅 API.

    Tavily 웹 검색 / 내부 문서 BM25+Vector 검색 / MCP 도구를 에이전트가
    자율적으로 선택·조합하여 응답합니다.
    6턴 초과 시 대화 히스토리를 자동 요약합니다.

    Args:
        body: user_id, session_id(optional), message, top_k(optional).
        auth_ctx: JWT 인증 + AuthContext 조립 (agent-user-context Design §6.2).
        use_case: 주입된 GeneralChatUseCase.

    Returns:
        에이전트 답변 + 사용 도구 목록 + 출처 + 요약 여부.
    """
    request_id = str(uuid.uuid4())
    return await use_case.execute(body, request_id, auth_ctx=auth_ctx)
