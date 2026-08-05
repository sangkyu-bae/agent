"""세션 팩토리 기반 미들웨어 저장소 어댑터 (builtin-middleware D6).

WorkflowCompiler·GeneralChatUseCase(앱 싱글톤)의 MiddlewareProvider가
런타임에 카탈로그/스냅샷을 읽을 때 사용
(SessionScopedDocumentTemplateRepository 패턴 — 읽기 전용).
"""
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.middleware.entities import (
    AgentMiddlewareRecord,
    MiddlewareCatalogEntry,
)
from src.domain.middleware.interfaces import (
    AgentMiddlewareRepositoryInterface,
    MiddlewareCatalogRepositoryInterface,
)
from src.infrastructure.middleware.repository import (
    AgentMiddlewareRepository,
    MiddlewareCatalogRepository,
)


class SessionScopedMiddlewareCatalogRepository(
    MiddlewareCatalogRepositoryInterface
):
    """매 호출마다 새 세션을 열어 MiddlewareCatalogRepository에 위임 (읽기 전용).

    쓰기(update_flags)는 per-request 세션 경로(관리자 API) 전용 —
    본 어댑터에서 호출 시 NotImplementedError.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        logger: LoggerInterface,
    ) -> None:
        self._session_factory = session_factory
        self._logger = logger

    async def list_all(self, request_id: str) -> list[MiddlewareCatalogEntry]:
        async with self._session_factory() as session:
            return await MiddlewareCatalogRepository(
                session, self._logger
            ).list_all(request_id)

    async def find_by_type(
        self, middleware_type: str, request_id: str
    ) -> MiddlewareCatalogEntry | None:
        async with self._session_factory() as session:
            return await MiddlewareCatalogRepository(
                session, self._logger
            ).find_by_type(middleware_type, request_id)

    async def update_flags(self, *args, **kwargs):
        raise NotImplementedError(
            "쓰기는 per-request 세션 경로(관리자 API) 전용"
        )

    async def list_builtin(self, request_id: str) -> list[MiddlewareCatalogEntry]:
        async with self._session_factory() as session:
            return await MiddlewareCatalogRepository(
                session, self._logger
            ).list_builtin(request_id)


class SessionScopedAgentMiddlewareRepository(AgentMiddlewareRepositoryInterface):
    """매 호출마다 새 세션을 열어 AgentMiddlewareRepository에 위임 (읽기 전용)."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        logger: LoggerInterface,
    ) -> None:
        self._session_factory = session_factory
        self._logger = logger

    async def list_by_agent(
        self, agent_id: str, request_id: str
    ) -> list[AgentMiddlewareRecord]:
        async with self._session_factory() as session:
            return await AgentMiddlewareRepository(
                session, self._logger
            ).list_by_agent(agent_id, request_id)
