"""Repository Interface."""
from abc import ABC, abstractmethod

from src.domain.middleware_agent.schemas import MiddlewareAgentDefinition


class MiddlewareAgentRepositoryInterface(ABC):

    @abstractmethod
    async def save(self, agent: MiddlewareAgentDefinition) -> MiddlewareAgentDefinition:
        ...

    @abstractmethod
    async def find_by_id(self, agent_id: str) -> MiddlewareAgentDefinition | None:
        ...

    @abstractmethod
    async def update(self, agent: MiddlewareAgentDefinition) -> MiddlewareAgentDefinition:
        ...
