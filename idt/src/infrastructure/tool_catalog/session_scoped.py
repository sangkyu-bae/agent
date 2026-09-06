"""세션 팩토리 기반 도구 카탈로그 저장소 어댑터.

Design Ref: mcp-tool-category-routing §5 D-08/D-09

WorkflowCompiler는 앱 싱글톤이라 per-request 세션을 갖지 않는다. 런타임에
카테고리·호출 상한을 읽으려면 매 호출마다 세션을 여는 어댑터가 필요하다
(SessionScopedMiddlewareCatalogRepository 패턴 — 읽기 전용).

컴파일러가 실제로 쓰는 것은 list_active() 하나뿐이다(compile()당 1회 배치
조회). 나머지 연산은 per-request 세션 경로(관리자 API) 전용이므로 여기서
호출하면 NotImplementedError로 즉시 드러낸다 — 조용한 오용 방지.
"""
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.tool_catalog.entity import ToolCatalogEntry
from src.domain.tool_catalog.interfaces import ToolCatalogRepositoryInterface
from src.infrastructure.tool_catalog.tool_catalog_repository import (
    ToolCatalogRepository,
)


class SessionScopedToolCatalogRepository(ToolCatalogRepositoryInterface):
    """매 호출마다 새 세션을 열어 ToolCatalogRepository에 위임 (읽기 전용)."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        logger: LoggerInterface,
    ) -> None:
        self._session_factory = session_factory
        self._logger = logger

    async def list_active(self, request_id: str) -> list[ToolCatalogEntry]:
        async with self._session_factory() as session:
            return await ToolCatalogRepository(
                session, self._logger
            ).list_active(request_id)

    async def find_by_tool_id(
        self, tool_id: str, request_id: str
    ) -> ToolCatalogEntry | None:
        async with self._session_factory() as session:
            return await ToolCatalogRepository(
                session, self._logger
            ).find_by_tool_id(tool_id, request_id)

    async def list_builtin(self, request_id: str) -> list[ToolCatalogEntry]:
        async with self._session_factory() as session:
            return await ToolCatalogRepository(
                session, self._logger
            ).list_builtin(request_id)

    async def save(self, *args, **kwargs):
        raise NotImplementedError("쓰기는 per-request 세션 경로 전용")

    async def upsert_by_tool_id(self, *args, **kwargs):
        raise NotImplementedError("쓰기는 per-request 세션 경로 전용")

    async def deactivate_by_mcp_server(self, *args, **kwargs):
        raise NotImplementedError("쓰기는 per-request 세션 경로 전용")

    async def set_builtin(self, *args, **kwargs):
        raise NotImplementedError("쓰기는 per-request 세션 경로(관리자 API) 전용")

    async def update_metadata(self, *args, **kwargs):
        raise NotImplementedError("쓰기는 per-request 세션 경로(관리자 API) 전용")
