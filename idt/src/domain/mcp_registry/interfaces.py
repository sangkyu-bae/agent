"""MCPServerRegistryRepositoryInterface: MCP 서버 저장소 추상화."""
from abc import ABC, abstractmethod

from src.domain.mcp_registry.schemas import MCPServerRegistration


class MCPServerRegistryRepositoryInterface(ABC):

    @abstractmethod
    async def save(
        self, registration: MCPServerRegistration, request_id: str
    ) -> MCPServerRegistration:
        """INSERT."""

    @abstractmethod
    async def find_by_id(
        self, id: str, request_id: str
    ) -> MCPServerRegistration | None:
        """PK 단건 조회."""

    @abstractmethod
    async def find_all_active(
        self, request_id: str
    ) -> list[MCPServerRegistration]:
        """is_active=True 전체 조회."""

    @abstractmethod
    async def find_by_user(
        self, user_id: str, request_id: str
    ) -> list[MCPServerRegistration]:
        """user_id 기준 목록 조회."""

    @abstractmethod
    async def update(
        self, registration: MCPServerRegistration, request_id: str
    ) -> MCPServerRegistration:
        """UPDATE."""

    @abstractmethod
    async def delete(self, id: str, request_id: str) -> bool:
        """DELETE."""
