"""AgentDefinitionRepositoryInterface: 에이전트 정의 저장소 추상화."""
from abc import ABC, abstractmethod

from src.domain.agent_builder.schemas import AgentDefinition


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
    async def update(self, agent: AgentDefinition, request_id: str) -> AgentDefinition:
        """system_prompt, name, updated_at UPDATE."""

    @abstractmethod
    async def list_by_user(
        self, user_id: str, request_id: str
    ) -> list[AgentDefinition]:
        """user_id로 에이전트 목록 조회."""
