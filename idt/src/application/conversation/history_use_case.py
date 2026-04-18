"""ConversationHistoryUseCase: 저장된 대화 세션/메시지 조회 UseCase (CHAT-HIST-001)."""
from src.application.repositories.conversation_repository import (
    ConversationMessageRepository,
)
from src.domain.conversation.history_schemas import (
    MessageItem,
    MessageListResponse,
    SessionListResponse,
)
from src.domain.conversation.value_objects import SessionId, UserId
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class ConversationHistoryUseCase:
    """사용자의 저장된 대화 세션 및 메시지를 조회하는 UseCase."""

    def __init__(
        self,
        repo: ConversationMessageRepository,
        logger: LoggerInterface,
    ) -> None:
        self._repo = repo
        self._logger = logger

    async def get_sessions(
        self, user_id: str, request_id: str
    ) -> SessionListResponse:
        """user_id의 세션 목록을 최신순으로 반환."""
        self._logger.info(
            "get_sessions started", request_id=request_id, user_id=user_id
        )
        try:
            sessions = await self._repo.find_sessions_by_user(UserId(user_id))
            self._logger.info(
                "get_sessions completed",
                request_id=request_id,
                session_count=len(sessions),
            )
            return SessionListResponse(user_id=user_id, sessions=list(sessions))
        except Exception as e:
            self._logger.error(
                "get_sessions failed", exception=e, request_id=request_id
            )
            raise

    async def get_messages(
        self, user_id: str, session_id: str, request_id: str
    ) -> MessageListResponse:
        """user_id + session_id의 전체 메시지를 turn_index 오름차순으로 반환."""
        self._logger.info(
            "get_messages started",
            request_id=request_id,
            user_id=user_id,
            session_id=session_id,
        )
        try:
            messages = await self._repo.find_by_session(
                UserId(user_id), SessionId(session_id)
            )
            items = [
                MessageItem(
                    id=m.id.value if m.id else 0,
                    role=m.role.value,
                    content=m.content,
                    turn_index=m.turn_index.value,
                    created_at=m.created_at,
                )
                for m in messages
            ]
            self._logger.info(
                "get_messages completed",
                request_id=request_id,
                message_count=len(items),
            )
            return MessageListResponse(
                user_id=user_id, session_id=session_id, messages=items
            )
        except Exception as e:
            self._logger.error(
                "get_messages failed", exception=e, request_id=request_id
            )
            raise
