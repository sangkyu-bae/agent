"""Eval UseCases — 답변 평가 제출/조회 + 에이전트 통계 (agent-eval-gate Design §3-3).

세션·트랜잭션은 라우터 DI가 관리한다.
결정 ②: 같은 rating 재요청이면 삭제(취소). 타 메시지·미존재는 "찾을 수 없" → 404 은닉.
"""
from dataclasses import dataclass

from src.application.repositories.conversation_repository import (
    ConversationMessageRepository,
)
from src.domain.conversation.entities import MessageId
from src.domain.eval.entity import MessageFeedback, Rating
from src.domain.eval.interfaces import MessageFeedbackRepositoryInterface
from src.domain.eval.policies import EvalPolicy
from src.domain.logging.interfaces.logger_interface import LoggerInterface

_NOT_FOUND_MSG = "메시지를 찾을 수 없습니다."


@dataclass
class AgentEvalStat:
    agent_id: str
    up: int
    down: int
    satisfaction: float | None  # up/(up+down), 0건이면 None


class SubmitFeedbackUseCase:
    """답변 평가 제출 — 같은 rating 재요청은 취소(토글). 반환 None=취소됨."""

    def __init__(
        self,
        feedback_repo: MessageFeedbackRepositoryInterface,
        message_repo: ConversationMessageRepository,
        logger: LoggerInterface,
    ) -> None:
        self._repo = feedback_repo
        self._msg_repo = message_repo
        self._logger = logger

    async def execute(
        self, user_id: str, message_id: int, rating: str, comment: str | None,
        request_id: str,
    ) -> MessageFeedback | None:
        parsed = self._parse_rating(rating)
        EvalPolicy.validate_comment(comment)
        agent_id = await self._resolve_agent_id(message_id, request_id)

        existing = await self._repo.find_by_message_and_user(
            message_id, user_id, request_id
        )
        # 결정 ②: 같은 rating 재클릭 → 취소(삭제)
        if existing is not None and existing.rating == parsed and comment is None:
            await self._repo.delete(message_id, user_id, request_id)
            self._logger.info(
                "feedback cancelled", request_id=request_id, user_id=user_id,
                message_id=message_id,
            )
            return None

        saved = await self._repo.upsert(
            MessageFeedback(
                id=None, message_id=message_id, user_id=user_id,
                agent_id=agent_id, rating=parsed, comment=comment,
            ),
            request_id,
        )
        self._logger.info(
            "feedback submitted", request_id=request_id, user_id=user_id,
            message_id=message_id, rating=parsed.value,
        )
        return saved

    async def _resolve_agent_id(self, message_id: int, request_id: str) -> str:
        message = await self._msg_repo.find_by_id(MessageId(message_id))
        if message is None:
            raise ValueError(_NOT_FOUND_MSG)
        return message.agent_id.value

    @staticmethod
    def _parse_rating(rating: str) -> Rating:
        try:
            return Rating(rating)
        except ValueError:
            raise ValueError("지원하지 않는 평가입니다. (허용: up, down)")


class GetFeedbackUseCase:
    def __init__(self, feedback_repo: MessageFeedbackRepositoryInterface) -> None:
        self._repo = feedback_repo

    async def execute(
        self, user_id: str, message_id: int, request_id: str
    ) -> MessageFeedback | None:
        return await self._repo.find_by_message_and_user(
            message_id, user_id, request_id
        )


class DeleteFeedbackUseCase:
    def __init__(self, feedback_repo: MessageFeedbackRepositoryInterface) -> None:
        self._repo = feedback_repo

    async def execute(self, user_id: str, message_id: int, request_id: str) -> None:
        await self._repo.delete(message_id, user_id, request_id)


class AgentEvalStatsUseCase:
    def __init__(
        self,
        feedback_repo: MessageFeedbackRepositoryInterface,
        recent_negative_limit: int,
    ) -> None:
        self._repo = feedback_repo
        self._recent_limit = recent_negative_limit

    async def agents(self, request_id: str) -> list[AgentEvalStat]:
        rows = await self._repo.aggregate_by_agent(request_id)
        return [
            AgentEvalStat(
                agent_id=agent_id, up=up, down=down,
                satisfaction=EvalPolicy.satisfaction(up, down),
            )
            for agent_id, up, down in rows
        ]

    async def recent_negative(self, request_id: str) -> list[MessageFeedback]:
        return await self._repo.recent_negative(self._recent_limit, request_id)
