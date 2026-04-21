"""ToolCatalogRepositoryInterface: 도구 카탈로그 저장소 추상화."""
from abc import ABC, abstractmethod

from src.domain.tool_catalog.entity import ToolCatalogEntry


class ToolCatalogRepositoryInterface(ABC):
    @abstractmethod
    async def save(self, entry: ToolCatalogEntry, request_id: str) -> ToolCatalogEntry: ...

    @abstractmethod
    async def upsert_by_tool_id(
        self, entry: ToolCatalogEntry, request_id: str
    ) -> ToolCatalogEntry: ...

    @abstractmethod
    async def find_by_tool_id(
        self, tool_id: str, request_id: str
    ) -> ToolCatalogEntry | None: ...

    @abstractmethod
    async def list_active(self, request_id: str) -> list[ToolCatalogEntry]: ...

    @abstractmethod
    async def deactivate_by_mcp_server(
        self, mcp_server_id: str, request_id: str
    ) -> int: ...
