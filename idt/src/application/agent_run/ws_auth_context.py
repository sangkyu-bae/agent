"""WsAuthContextResolver — WebSocket 전용 AuthContext 조립기.

fix-ws-auth-context-missing Design §3.1:
- WS 연결은 스트리밍 동안 장시간 유지되므로, request-scoped 세션을 점유하지 않도록
  조립 시점에만 단기 세션을 연다 (CLAUDE.md §6: session_factory 주입, async with 사용).
- infrastructure repo를 직접 import하지 않고 session→UseCase 빌더를 주입받아 레이어 규칙 준수.
- execute()는 예외를 그대로 전파한다 (단일 책임). fail-closed degrade는 호출자(라우터)가 담당.
"""
from typing import Callable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.application.permission.assemble_auth_context import (
    AssembleAuthContextUseCase,
)
from src.domain.agent_run.auth_context import AuthContext
from src.domain.auth.entities import User


class WsAuthContextResolver:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        assemble_uc_builder: Callable[[AsyncSession], AssembleAuthContextUseCase],
    ) -> None:
        self._session_factory = session_factory
        self._assemble_uc_builder = assemble_uc_builder

    async def execute(self, user: User, request_id: str) -> AuthContext:
        """단기 세션으로 AuthContext 조립 (예외는 호출자가 fail-closed 처리)."""
        async with self._session_factory() as session:
            uc = self._assemble_uc_builder(session)
            return await uc.execute(user, request_id)
