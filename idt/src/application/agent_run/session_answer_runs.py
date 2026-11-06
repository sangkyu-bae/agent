"""세션의 assistant 메시지 ↔ 그 답을 만든 런 연결.

Design Ref: agent-run-tool-trace §9.4 — get_session_sources_use_case 의 짝짓기·소유
확인을 추출해 근거 칩과 도구 실행 내역이 같은 규칙으로 런을 고른다 (Plan FR-09).
Design Ref: agent-run-source-citations §4.2 — 메시지 조회 실패는 전파하고, 런 조회
실패는 빈 목록으로 낮춘다.
"""
from src.application.repositories.conversation_repository import (
    ConversationMessageRepository,
)
from src.domain.agent_run.entities import AgentRun
from src.domain.agent_run.interfaces import AgentRunRepositoryInterface
from src.domain.conversation.entities import (
    ConversationMessage,
    MessageRole,
    SessionId,
    UserId,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class SessionAnswerRunsResolver:
    def __init__(
        self,
        message_repo: ConversationMessageRepository,
        agent_run_repo: AgentRunRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._message_repo = message_repo
        self._agent_run_repo = agent_run_repo
        self._logger = logger

    async def resolve(
        self, *, user_id: str, agent_id: str, session_id: str, request_id: str,
    ) -> list[tuple[int, AgentRun]]:
        """(assistant 메시지 id, 런) 목록. 쿼리는 메시지 1 + 런 1 로 고정이다."""
        messages = await self._message_repo.find_by_session(
            UserId(user_id), SessionId(session_id),
        )
        pairs = answer_pairs(messages)
        if not pairs:
            return []
        try:
            runs = await self._agent_run_repo.find_latest_runs_by_user_messages(
                [user_message_id for _, user_message_id in pairs],
            )
        except Exception as e:
            self._logger.warning(
                "session answer run lookup failed",
                exception=e, request_id=request_id, session_id=session_id,
            )
            return []
        # 같은 세션에 다른 에이전트·사용자의 런이 섞이지 않게 한 번 더 거른다.
        return [
            (assistant_id, runs[user_message_id])
            for assistant_id, user_message_id in pairs
            if user_message_id in runs
            and runs[user_message_id].agent_id == agent_id
            and runs[user_message_id].user_id == user_id
        ]


def answer_pairs(messages: list[ConversationMessage]) -> list[tuple[int, int]]:
    """(assistant id, 직전 user id) — id 순서로 짝짓는다.

    turn index 수정 전 데이터는 user/assistant 가 같은 turn_index 라 쓸 수 없다.
    user 1건은 첫 답변 1건과만 짝짓는다.
    """
    pairs: list[tuple[int, int]] = []
    pending_user: int | None = None
    ordered = sorted((m for m in messages if m.id is not None), key=lambda m: m.id.value)
    for message in ordered:
        if message.role == MessageRole.USER:
            pending_user = message.id.value
        elif message.role == MessageRole.ASSISTANT and pending_user is not None:
            pairs.append((message.id.value, pending_user))
            pending_user = None
    return pairs
