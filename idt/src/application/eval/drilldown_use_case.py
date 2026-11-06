"""GetNegativeDrilldownUseCase — 👎 답변의 질문·답변·런·근거 조회.

Design Ref: negative-feedback-drilldown §4.5.
평가 id는 assistant 메시지, ai_run.user_message_id는 user 메시지를 가리킨다.
그래서 질문을 복원한 뒤 그 id로 런을 조회한다. assistant id로 조회하면 200 빈
결과로 조용히 실패한다.
"""
from dataclasses import dataclass, field

from src.application.agent_run.use_cases.get_message_retrievals_use_case import (
    GetMessageRetrievalsUseCase,
    MessageRunRetrievals,
)
from src.application.repositories.conversation_repository import (
    ConversationMessageRepository,
)
from src.domain.conversation.entities import ConversationMessage, MessageId
from src.domain.conversation.value_objects import MessageRole
from src.domain.eval.interfaces import MessageFeedbackRepositoryInterface
from src.domain.eval.policies import EvalPolicy
from src.domain.logging.interfaces.logger_interface import LoggerInterface

_NOT_FOUND_MSG = "메시지를 찾을 수 없습니다."


@dataclass(frozen=True)
class NegativeDrilldownDto:
    message_id: int
    agent_id: str
    question: str | None  # 복원 실패 시 None
    answer: str
    runs: list[MessageRunRetrievals] = field(default_factory=list)


class GetNegativeDrilldownUseCase:
    def __init__(
        self,
        feedback_repo: MessageFeedbackRepositoryInterface,
        message_repo: ConversationMessageRepository,
        retrievals: GetMessageRetrievalsUseCase,
        logger: LoggerInterface,
    ) -> None:
        self._feedback_repo = feedback_repo
        self._message_repo = message_repo
        self._retrievals = retrievals
        self._logger = logger

    async def execute(
        self, message_id: int, admin_id: str, request_id: str,
    ) -> NegativeDrilldownDto:
        """Raises: ValueError("…찾을 수 없…") → router 404."""
        answer = await self._resolve_answer(message_id, request_id)
        question = await self._find_question(answer)
        runs = await self._find_runs(question, admin_id)
        # Plan FR-09: 조회 기록. 대화 본문은 로그에 쓰지 않는다.
        self._logger.info(
            "negative drilldown viewed", request_id=request_id, admin_id=admin_id,
            message_id=message_id, question_restored=question is not None,
            run_count=len(runs),
        )
        return NegativeDrilldownDto(
            message_id=message_id,
            agent_id=answer.agent_id.value,
            question=question.content if question is not None else None,
            answer=answer.content,
            runs=runs,
        )

    async def _resolve_answer(
        self, message_id: int, request_id: str,
    ) -> ConversationMessage:
        """Plan FR-02·FR-08: 👎가 달린 assistant 메시지만 열람을 허용한다."""
        if not await self._feedback_repo.has_negative(message_id, request_id):
            raise ValueError(_NOT_FOUND_MSG)
        message = await self._message_repo.find_by_id(MessageId(message_id))
        if message is None or message.role != MessageRole.ASSISTANT:
            raise ValueError(_NOT_FOUND_MSG)
        return message

    async def _find_question(
        self, answer: ConversationMessage,
    ) -> ConversationMessage | None:
        messages = await self._message_repo.find_by_session(
            answer.user_id, answer.session_id
        )
        return EvalPolicy.find_question(messages, answer)

    async def _find_runs(
        self, question: ConversationMessage | None, admin_id: str,
    ) -> list[MessageRunRetrievals]:
        if question is None:
            return []
        result = await self._retrievals.execute(
            message_id=question.id.value,
            requesting_user_id=admin_id,
            is_admin=True,
        )
        return result.runs
