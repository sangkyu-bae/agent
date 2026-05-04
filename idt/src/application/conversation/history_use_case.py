"""ConversationHistoryUseCase: 저장된 대화 세션/메시지 조회 UseCase (CHAT-HIST-001)."""
from src.application.repositories.conversation_repository import (
    ConversationMessageRepository,
)
from src.domain.conversation.history_schemas import (
    AgentChatSummary,
    AgentListResponse,
    AgentMessageListResponse,
    AgentSessionListResponse,
    MessageItem,
    MessageListResponse,
    SessionListResponse,
)
from src.domain.conversation.value_objects import AgentId, SessionId, UserId, SUPER_AGENT_ID
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class ConversationHistoryUseCase:
    """사용자의 저장된 대화 세션 및 메시지를 조회하는 UseCase."""

    def __init__(
        self,
        repo: ConversationMessageRepository,
        logger: LoggerInterface,
        agent_repo=None,
    ) -> None:
        self._repo = repo
        self._logger = logger
        self._agent_repo = agent_repo

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

    async def get_agents_with_history(
        self, user_id: str, request_id: str
    ) -> AgentListResponse:
        """대화 기록이 있는 에이전트 목록 반환."""
        self._logger.info(
            "get_agents_with_history started",
            request_id=request_id,
            user_id=user_id,
        )
        try:
            raw_agents = await self._repo.find_agents_by_user(UserId(user_id))

            agents = []
            for a in raw_agents:
                if a.agent_id == SUPER_AGENT_ID:
                    name = "일반 채팅"
                elif self._agent_repo:
                    agent_def = await self._agent_repo.find_by_id(a.agent_id)
                    name = agent_def.name if agent_def else f"삭제된 에이전트 ({a.agent_id[:8]})"
                else:
                    name = a.agent_id
                agents.append(AgentChatSummary(
                    agent_id=a.agent_id,
                    agent_name=name,
                    session_count=a.session_count,
                    last_chat_at=a.last_chat_at,
                ))

            self._logger.info(
                "get_agents_with_history completed",
                request_id=request_id,
                agent_count=len(agents),
            )
            return AgentListResponse(user_id=user_id, agents=agents)
        except Exception as e:
            self._logger.error(
                "get_agents_with_history failed",
                exception=e,
                request_id=request_id,
            )
            raise

    async def get_sessions_by_agent(
        self, user_id: str, agent_id: str, request_id: str
    ) -> AgentSessionListResponse:
        """에이전트별 세션 목록 반환."""
        self._logger.info(
            "get_sessions_by_agent started",
            request_id=request_id,
            user_id=user_id,
            agent_id=agent_id,
        )
        try:
            sessions = await self._repo.find_sessions_by_user_and_agent(
                UserId(user_id), AgentId(agent_id)
            )
            self._logger.info(
                "get_sessions_by_agent completed",
                request_id=request_id,
                session_count=len(sessions),
            )
            return AgentSessionListResponse(
                user_id=user_id,
                agent_id=agent_id,
                sessions=list(sessions),
            )
        except Exception as e:
            self._logger.error(
                "get_sessions_by_agent failed",
                exception=e,
                request_id=request_id,
            )
            raise

    async def get_messages_by_agent(
        self, user_id: str, agent_id: str, session_id: str, request_id: str
    ) -> AgentMessageListResponse:
        """에이전트 + 세션의 메시지 조회."""
        self._logger.info(
            "get_messages_by_agent started",
            request_id=request_id,
            user_id=user_id,
            agent_id=agent_id,
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
                "get_messages_by_agent completed",
                request_id=request_id,
                message_count=len(items),
            )
            return AgentMessageListResponse(
                user_id=user_id,
                agent_id=agent_id,
                session_id=session_id,
                messages=items,
            )
        except Exception as e:
            self._logger.error(
                "get_messages_by_agent failed",
                exception=e,
                request_id=request_id,
            )
            raise
