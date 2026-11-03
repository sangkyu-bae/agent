"""GetSessionSourcesUseCase: 세션의 assistant 메시지별 근거 (재진입 복원).

Design Ref: agent-run-source-citations §4.2 — 기존 대화 이력 API 는 인증이 없어
발췌를 실을 수 없으므로 인증 전용 경로로 분리한다. 실시간과 같은 서비스를 지나
같은 칩 목록을 만든다 (Plan SC-1).
"""
from dataclasses import dataclass, field

from src.application.agent_run.run_sources import RunSourcesService
from src.application.repositories.conversation_repository import (
    ConversationMessageRepository,
)
from src.domain.agent_run.interfaces import AgentRunRepositoryInterface
from src.domain.agent_run.source_policy import RunSourceItem
from src.domain.conversation.entities import (
    ConversationMessage,
    MessageRole,
    SessionId,
    UserId,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface


@dataclass(frozen=True)
class MessageSources:
    message_id: int
    sources: list[RunSourceItem] = field(default_factory=list)


@dataclass(frozen=True)
class SessionSourcesDto:
    session_id: str
    items: list[MessageSources] = field(default_factory=list)


class GetSessionSourcesUseCase:
    def __init__(
        self,
        message_repo: ConversationMessageRepository,
        agent_run_repo: AgentRunRepositoryInterface,
        sources: RunSourcesService,
        logger: LoggerInterface,
    ) -> None:
        self._message_repo = message_repo
        self._agent_run_repo = agent_run_repo
        self._sources = sources
        self._logger = logger

    async def execute(
        self, *, user_id: str, agent_id: str, session_id: str, request_id: str,
    ) -> SessionSourcesDto:
        """메시지 조회 실패는 전파하고, 근거 조회 실패는 빈 목록으로 낮춘다 (§6.1)."""
        messages = await self._message_repo.find_by_session(
            UserId(user_id), SessionId(session_id),
        )
        pairs = _answer_pairs(messages)
        if not pairs:
            return SessionSourcesDto(session_id=session_id)
        try:
            runs = await self._agent_run_repo.find_latest_runs_by_user_messages(
                [user_message_id for _, user_message_id in pairs],
            )
        except Exception as e:
            self._logger.warning(
                "session sources run lookup failed",
                exception=e, request_id=request_id, session_id=session_id,
            )
            return SessionSourcesDto(session_id=session_id)
        # 같은 세션에 다른 에이전트·사용자의 런이 섞이지 않게 한 번 더 거른다.
        owned = {
            message_id: run for message_id, run in runs.items()
            if run.agent_id == agent_id and run.user_id == user_id
        }
        try:
            built = await self._sources.build_for_runs(
                [run.id for run in owned.values()], request_id,
            )
        except Exception as e:
            # 서비스가 저장소 실패를 흡수하지만 정책 단계의 예상 밖 예외까지 막는다 (§4.2).
            self._logger.warning(
                "session sources build failed",
                exception=e, request_id=request_id, session_id=session_id,
            )
            return SessionSourcesDto(session_id=session_id)
        items = [
            MessageSources(assistant_id, built[owned[user_message_id].id.value])
            for assistant_id, user_message_id in pairs
            if user_message_id in owned and owned[user_message_id].id.value in built
        ]
        return SessionSourcesDto(session_id=session_id, items=items)


def _answer_pairs(messages: list[ConversationMessage]) -> list[tuple[int, int]]:
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
