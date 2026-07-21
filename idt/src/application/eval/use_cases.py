"""Eval UseCases — 답변 평가 제출/조회 + 에이전트 통계 (agent-eval-gate Design §3-3).

세션·트랜잭션은 라우터 DI가 관리한다.
결정 ②: 같은 rating 재요청이면 삭제(취소). 타 메시지·미존재는 "찾을 수 없" → 404 은닉.
eval-feedback-loop §3-4: comment 있는 down 저장 시 부정 맥락 메모리 추출 트리거.
"""
from dataclasses import dataclass

from src.application.memory.extraction_service import MemoryExtractionService
from src.application.repositories.conversation_repository import (
    ConversationMessageRepository,
)
from src.application.wiki.feedback_service import FeedbackWikiService
from src.domain.conversation.entities import ConversationMessage, MessageId
from src.domain.conversation.value_objects import MessageRole
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
        extraction: MemoryExtractionService | None = None,
        wiki_feedback: FeedbackWikiService | None = None,
    ) -> None:
        self._repo = feedback_repo
        self._msg_repo = message_repo
        self._logger = logger
        self._extraction = extraction
        self._wiki_feedback = wiki_feedback

    async def execute(
        self, user_id: str, message_id: int, rating: str, comment: str | None,
        request_id: str,
    ) -> MessageFeedback | None:
        parsed = self._parse_rating(rating)
        EvalPolicy.validate_comment(comment)
        message = await self._resolve_message(message_id)

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
                agent_id=message.agent_id.value, rating=parsed, comment=comment,
            ),
            request_id,
        )
        self._logger.info(
            "feedback submitted", request_id=request_id, user_id=user_id,
            message_id=message_id, rating=parsed.value,
        )
        # eval-feedback-loop 결정 ⑤: comment 있는 down + 이전 상태와 다를 때만
        if self._is_actionable_negative(parsed, comment, existing):
            await self._kickoff_feedback_fanout(message, comment, request_id)
        return saved

    async def _resolve_message(self, message_id: int) -> ConversationMessage:
        message = await self._msg_repo.find_by_id(MessageId(message_id))
        if message is None:
            raise ValueError(_NOT_FOUND_MSG)
        return message

    def _is_actionable_negative(
        self, parsed: Rating, comment: str | None,
        existing: MessageFeedback | None,
    ) -> bool:
        """순수 트리거 조건 — 서비스별 enabled 판정은 팬아웃이 담당."""
        if parsed != Rating.DOWN or not (comment and comment.strip()):
            return False  # bare 👎는 통계만 — 추측 추출 금지 (rev1)
        return (
            existing is None
            or existing.rating != Rating.DOWN
            or existing.comment != comment
        )

    async def _kickoff_feedback_fanout(
        self, message: ConversationMessage, comment: str, request_id: str,
    ) -> None:
        """Q/A 복원 1회를 memory·wiki 환류가 공유 (wiki-feedback-loop §3-5)."""
        memory_on = (
            self._extraction is not None and self._extraction.feedback_enabled
        )
        wiki_on = (
            self._wiki_feedback is not None and self._wiki_feedback.enabled
        )
        if not (memory_on or wiki_on):
            return  # 복원 조회 0회 — off 경로 기존 동일 (FR-05)
        message_id = message.id.value if message.id is not None else None
        question = await self._find_question(message)
        if question is None:
            self._logger.warning(
                "feedback extraction skipped — question not found",
                request_id=request_id, message_id=message_id,
            )  # FR-02: 평가 저장은 유지
            return
        self._logger.info(
            "feedback extraction kickoff",
            request_id=request_id, message_id=message_id,
        )  # 결정 ④ provenance: 로그로만 추적
        if memory_on:
            self._extraction.kickoff_feedback(
                message.user_id.value, question.content, message.content,
                comment, request_id,
            )
        if wiki_on:
            self._wiki_feedback.kickoff_draft(
                message.agent_id.value, message_id, question.content,
                message.content, comment, request_id,
            )

    async def _find_question(
        self, message: ConversationMessage,
    ) -> ConversationMessage | None:
        """같은 세션에서 직전 turn의 user 메시지(질문) 복원 — 모호하면 None."""
        messages = await self._msg_repo.find_by_session(
            message.user_id, message.session_id
        )
        target_turn = message.turn_index.value - 1
        for m in messages:
            if m.turn_index.value == target_turn and m.role == MessageRole.USER:
                return m
        return None

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
