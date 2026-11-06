"""GetSessionSourcesUseCase: 세션의 assistant 메시지별 근거 (재진입 복원).

Design Ref: agent-run-source-citations §4.2 — 기존 대화 이력 API 는 인증이 없어
발췌를 실을 수 없으므로 인증 전용 경로로 분리한다. 실시간과 같은 서비스를 지나
같은 칩 목록을 만든다 (Plan SC-1).
Design Ref: agent-run-tool-trace §9.4 — 메시지↔런 연결은 SessionAnswerRunsResolver 로
옮겨 도구 실행 내역과 공유한다. 동작은 그대로다.
"""
from dataclasses import dataclass, field

from src.application.agent_run.run_sources import RunSourcesService
from src.application.agent_run.session_answer_runs import SessionAnswerRunsResolver
from src.application.repositories.conversation_repository import (
    ConversationMessageRepository,
)
from src.domain.agent_run.interfaces import AgentRunRepositoryInterface
from src.domain.agent_run.source_policy import RunSourceItem
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
        self._answer_runs = SessionAnswerRunsResolver(message_repo, agent_run_repo, logger)
        self._sources = sources
        self._logger = logger

    async def execute(
        self, *, user_id: str, agent_id: str, session_id: str, request_id: str,
    ) -> SessionSourcesDto:
        """메시지 조회 실패는 전파하고, 근거 조회 실패는 빈 목록으로 낮춘다 (§6.1)."""
        answers = await self._answer_runs.resolve(
            user_id=user_id, agent_id=agent_id, session_id=session_id,
            request_id=request_id,
        )
        # 빈 목록이어도 서비스가 쿼리 없이 즉시 반환하므로 분기를 두지 않는다.
        try:
            built = await self._sources.build_for_runs(
                [run.id for _, run in answers], request_id,
            )
        except Exception as e:
            # 서비스가 저장소 실패를 흡수하지만 정책 단계의 예상 밖 예외까지 막는다 (§4.2).
            self._logger.warning(
                "session sources build failed",
                exception=e, request_id=request_id, session_id=session_id,
            )
            return SessionSourcesDto(session_id=session_id)
        items = [
            MessageSources(assistant_id, built[run.id.value])
            for assistant_id, run in answers
            if run.id.value in built
        ]
        return SessionSourcesDto(session_id=session_id, items=items)
