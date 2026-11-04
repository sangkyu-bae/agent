"""GetSessionToolTracesUseCase: 세션의 assistant 메시지별 도구 실행 내역 (재진입 복원).

Design Ref: agent-run-tool-trace §4.2 — 근거 API 와 같은 규칙(토큰 사용자 세션만,
타인·없는 세션은 빈 결과)으로 런을 고르고, 실시간 경로와 같은 RunToolTraceService 를
지나 두 화면의 내역이 일치한다 (Plan R4).
"""
from dataclasses import dataclass, field

from src.application.agent_run.run_tool_trace import RunToolTraceService
from src.application.agent_run.session_answer_runs import SessionAnswerRunsResolver
from src.application.repositories.conversation_repository import (
    ConversationMessageRepository,
)
from src.domain.agent_run.interfaces import AgentRunRepositoryInterface
from src.domain.agent_run.tool_trace_policy import ToolTrace
from src.domain.logging.interfaces.logger_interface import LoggerInterface


@dataclass(frozen=True)
class MessageToolTrace:
    message_id: int
    tool_trace: ToolTrace


@dataclass(frozen=True)
class SessionToolTracesDto:
    session_id: str
    items: list[MessageToolTrace] = field(default_factory=list)


class GetSessionToolTracesUseCase:
    def __init__(
        self,
        message_repo: ConversationMessageRepository,
        agent_run_repo: AgentRunRepositoryInterface,
        traces: RunToolTraceService,
        logger: LoggerInterface,
    ) -> None:
        self._answer_runs = SessionAnswerRunsResolver(message_repo, agent_run_repo, logger)
        self._traces = traces
        self._logger = logger

    async def execute(
        self, *, user_id: str, agent_id: str, session_id: str, request_id: str,
    ) -> SessionToolTracesDto:
        """메시지 조회 실패는 전파하고, 내역 조회 실패는 빈 목록으로 낮춘다 (§6)."""
        answers = await self._answer_runs.resolve(
            user_id=user_id, agent_id=agent_id, session_id=session_id,
            request_id=request_id,
        )
        if not answers:
            return SessionToolTracesDto(session_id=session_id)
        try:
            built = await self._traces.build_for_runs(
                [run.id for _, run in answers], request_id,
            )
        except Exception as e:
            # 서비스가 저장소 실패를 흡수하지만 예상 밖 예외까지 히스토리를 막지 않게 한다.
            self._logger.warning(
                "session tool traces build failed",
                exception=e, request_id=request_id, session_id=session_id,
            )
            return SessionToolTracesDto(session_id=session_id)
        items = [
            MessageToolTrace(assistant_id, built[run.id.value])
            for assistant_id, run in answers
            if run.id.value in built
        ]
        return SessionToolTracesDto(session_id=session_id, items=items)
