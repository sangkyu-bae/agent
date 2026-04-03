"""AutoBuildSessionRepositoryInterface."""
from abc import ABC, abstractmethod
from src.domain.auto_agent_builder.schemas import AutoBuildSession


class AutoBuildSessionRepositoryInterface(ABC):

    @abstractmethod
    async def save(self, session: AutoBuildSession) -> None:
        ...

    @abstractmethod
    async def find(self, session_id: str) -> AutoBuildSession | None:
        ...

    @abstractmethod
    async def delete(self, session_id: str) -> None:
        ...
