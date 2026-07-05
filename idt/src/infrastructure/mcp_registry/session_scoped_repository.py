"""세션 팩토리 기반 MCP 레지스트리 조회 어댑터.

document_extractor의 DocumentConversionAdapter(앱 싱글톤)가 런타임에
MCPToolLoader.load_by_tool_id로 서버 등록 정보를 조회할 때 사용.
로더가 사용하는 find_by_id만 위임한다 (읽기 전용).
"""
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.mcp_registry.mcp_server_repository import (
    MCPServerRepository,
)


class SessionScopedMcpServerRepository:
    """매 호출마다 새 세션을 열어 MCPServerRepository.find_by_id에 위임."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        logger: LoggerInterface,
        cipher=None,
    ) -> None:
        self._session_factory = session_factory
        self._logger = logger
        self._cipher = cipher

    async def find_by_id(self, server_id: str, request_id: str):
        async with self._session_factory() as session:
            repo = MCPServerRepository(
                session=session, logger=self._logger, cipher=self._cipher
            )
            return await repo.find_by_id(server_id, request_id)
