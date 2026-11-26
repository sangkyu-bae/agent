"""플랫폼 참조 확인 어댑터 (application.ports.ReferenceChecker, module-8).

Design Ref: stock-analysis-agents §5.2 검증 — 서버 id 는 등록된 활성 MCP,
run_as_user_id 는 활성 사용자, 역할 매핑 에이전트는 있고 삭제되지 않은 것.
플랫폼 조회는 main 이 넘긴 함수(MCP 조회·실행자 인증 조립)와 에이전트 저장소를 쓴다.
조회가 실패하면 False — 확인할 수 없는 값을 저장하지 않는다.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.agent_builder.agent_definition_repository import (
    AgentDefinitionRepository,
)


class PlatformReferenceChecker:
    def __init__(
        self,
        *,
        session_factory: Callable[[], Any],
        server_finder: Callable[[str, str], Awaitable[Any]],
        auth_ctx_assembler: Callable[[str, str], Awaitable[Any]],
        logger: LoggerInterface,
    ) -> None:
        self._sf = session_factory
        self._find_server = server_finder
        self._assemble = auth_ctx_assembler
        self._logger = logger

    async def mcp_server_active(self, server_id: str, request_id: str) -> bool:
        try:
            server = await self._find_server(server_id, request_id)
        except Exception as e:  # noqa: BLE001
            self._warn("mcp server lookup failed", e, request_id)
            return False
        return server is not None and bool(getattr(server, "is_active", False))

    async def user_active(self, user_id: str, request_id: str) -> bool:
        try:
            return await self._assemble(user_id, request_id) is not None
        except Exception as e:  # noqa: BLE001
            self._warn("user lookup failed", e, request_id)
            return False

    async def agent_usable(self, agent_id: str, request_id: str) -> bool:
        try:
            async with self._sf() as session:
                agent = await AgentDefinitionRepository(
                    session, self._logger
                ).find_by_id(agent_id, request_id)
        except Exception as e:  # noqa: BLE001
            self._warn("agent lookup failed", e, request_id)
            return False
        return agent is not None and getattr(agent, "status", "") != "deleted"

    def _warn(self, message: str, error: Exception, request_id: str) -> None:
        self._logger.warning(
            f"market_analysis {message}", exception=error, request_id=request_id
        )
