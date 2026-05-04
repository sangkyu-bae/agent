"""AgentDefinitionRepositoryInterface, SubscriptionRepositoryInterface: 에이전트 저장소 추상화."""
from abc import ABC, abstractmethod

from src.domain.agent_builder.schemas import AgentDefinition
from src.domain.agent_builder.subscription import Subscription


class AgentDefinitionRepositoryInterface(ABC):
    @abstractmethod
    async def save(self, agent: AgentDefinition, request_id: str) -> AgentDefinition:
        """agent_definition + agent_tool 동시 INSERT."""

    @abstractmethod
    async def find_by_id(
        self, agent_id: str, request_id: str
    ) -> AgentDefinition | None:
        """agent_definition LEFT JOIN agent_tool ORDER BY sort_order."""

    @abstractmethod
    async def find_by_id_with_status(
        self, agent_id: str, request_id: str
    ) -> AgentDefinition | None:
        """삭제된 에이전트 포함 조회 (자동 포크 시 마지막 상태 스냅샷용)."""

    @abstractmethod
    async def update(self, agent: AgentDefinition, request_id: str) -> AgentDefinition:
        """system_prompt, name, updated_at UPDATE."""

    @abstractmethod
    async def list_by_user(
        self, user_id: str, request_id: str
    ) -> list[AgentDefinition]:
        """user_id로 에이전트 목록 조회."""

    @abstractmethod
    async def list_accessible(
        self,
        viewer_user_id: str,
        viewer_department_ids: list[str],
        scope: str,
        search: str | None,
        page: int,
        size: int,
        request_id: str,
    ) -> tuple[list[AgentDefinition], int]:
        """가시성 기반 에이전트 목록 + 전체 건수."""

    @abstractmethod
    async def soft_delete(self, agent_id: str, request_id: str) -> None:
        """status='deleted'로 소프트 삭제."""

    @abstractmethod
    async def count_forks(self, source_agent_id: str, request_id: str) -> int:
        """특정 에이전트의 포크 수."""

    @abstractmethod
    async def count_subscribers(self, agent_id: str, request_id: str) -> int:
        """특정 에이전트의 구독자 수."""


class SubscriptionRepositoryInterface(ABC):
    @abstractmethod
    async def save(self, subscription: Subscription, request_id: str) -> Subscription:
        """구독 INSERT."""

    @abstractmethod
    async def find_by_user_and_agent(
        self, user_id: str, agent_id: str, request_id: str
    ) -> Subscription | None:
        """특정 사용자의 특정 에이전트 구독 조회."""

    @abstractmethod
    async def delete(self, user_id: str, agent_id: str, request_id: str) -> None:
        """구독 DELETE."""

    @abstractmethod
    async def update_pin(
        self, user_id: str, agent_id: str, is_pinned: bool, request_id: str
    ) -> Subscription:
        """즐겨찾기 토글."""

    @abstractmethod
    async def list_by_user(
        self, user_id: str, request_id: str
    ) -> list[Subscription]:
        """사용자의 전체 구독 목록."""

    @abstractmethod
    async def find_subscribers_by_agent(
        self, agent_id: str, request_id: str
    ) -> list[Subscription]:
        """특정 에이전트의 전체 구독자 목록 (자동 포크용)."""

    @abstractmethod
    async def delete_by_agent(self, agent_id: str, request_id: str) -> int:
        """에이전트 삭제 시 관련 구독 일괄 삭제. 삭제 건수 반환."""
