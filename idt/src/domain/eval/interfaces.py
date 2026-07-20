"""MessageFeedbackRepositoryInterface — 평가 저장소 추상화 (agent-eval-gate)."""
from abc import ABC, abstractmethod

from src.domain.eval.entity import MessageFeedback


class MessageFeedbackRepositoryInterface(ABC):
    @abstractmethod
    async def find_by_message_and_user(
        self, message_id: int, user_id: str, request_id: str
    ) -> MessageFeedback | None:
        """본인 평가 조회 — 없으면 None."""

    @abstractmethod
    async def upsert(self, feedback: MessageFeedback, request_id: str) -> MessageFeedback:
        """UNIQUE(message_id,user_id) 기준 삽입/갱신."""

    @abstractmethod
    async def delete(self, message_id: int, user_id: str, request_id: str) -> bool:
        """본인 평가 삭제 (취소) — 삭제됐으면 True."""

    @abstractmethod
    async def aggregate_by_agent(
        self, request_id: str
    ) -> list[tuple[str, int, int]]:
        """에이전트별 (agent_id, up_count, down_count)."""

    @abstractmethod
    async def recent_negative(
        self, limit: int, request_id: str
    ) -> list[MessageFeedback]:
        """최근 부정(down) 피드백 — created_at desc."""
