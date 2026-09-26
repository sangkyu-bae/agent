"""서버·실행 주체별 신원 헤더 공급자.

Design Ref: mcp-identity-header §2.1, §2.2 — 공급자는 MCP 세션을 열기 직전에
불린다. 부를 때마다 users 행을 다시 읽고 토큰을 새로 서명한다 (5분 수명,
캐시 금지). 실패는 IdentityUnavailableError 로 올려 네트워크 전에 멈춘다.
"""
import time
from typing import Callable, Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.auth.entities import User
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.mcp_registry.identity import (
    IdentityClaimPolicy,
    IdentityHeaderConfig,
    IdentityUnavailableError,
)
from src.domain.mcp_registry.schemas import MCPServerRegistration
from src.infrastructure.auth.user_repository import UserRepository
from src.infrastructure.mcp.client_factory import HeaderProvider
from src.infrastructure.mcp_registry.identity_token import HmacIdentityTokenSigner


class IdentityConfigUnreadableError(RuntimeError):
    """저장된 신원 설정을 읽을 수 없다 — 헤더 없이 보내지 않는다 (Check G-3)."""


class UserReader(Protocol):
    async def find_by_id(self, user_id: int) -> User | None: ...


class SessionScopedUserReader:
    """매 호출마다 새 세션으로 users 를 읽는다 (읽기 전용).

    공급자는 앱 싱글톤 로더가 만든 도구 안에서 불리므로 요청 세션을 들 수
    없다 — SessionScopedMcpServerRepository 와 같은 패턴 (tool-and-mcp §3).
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        logger: LoggerInterface,
    ) -> None:
        self._session_factory = session_factory
        self._logger = logger

    async def find_by_id(self, user_id: int) -> User | None:
        async with self._session_factory() as session:
            return await UserRepository(session=session, logger=self._logger).find_by_id(
                user_id
            )


class IdentityHeaderProviderFactory:
    """등록 정보와 실행 주체로 호출 시점 헤더 공급자를 만든다."""

    def __init__(
        self,
        user_reader: UserReader,
        signer: HmacIdentityTokenSigner,
        logger: LoggerInterface,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._reader = user_reader
        self._signer = signer
        self._logger = logger
        self._clock = clock

    def for_registration(
        self,
        registration: MCPServerRegistration,
        subject_user_id: str | None,
        request_id: str = "",
    ) -> HeaderProvider | None:
        """신원 미설정 서버는 None — 헤더·세션이 기존과 같다 (FR-08)."""
        config = registration.identity_config
        if registration.identity_config_unreadable:
            return _unreadable_provider(registration.id)
        if config is None:
            return None

        async def provide() -> dict[str, str]:
            return await self._issue(config, registration.id, subject_user_id, request_id)

        return provide

    async def _issue(
        self,
        config: IdentityHeaderConfig,
        server_id: str,
        subject_user_id: str | None,
        request_id: str,
    ) -> dict[str, str]:
        try:
            subject = IdentityClaimPolicy.require_subject(subject_user_id)
            user = await self._find_user(subject)
            value = IdentityClaimPolicy.resolve_claim_value(user, config.claim_source)
        except IdentityUnavailableError as e:
            e.subject = subject_user_id  # Check G-4 — 차단 로그 추적용
            raise
        claims = IdentityClaimPolicy.build_claims(
            config, subject, value, now=int(self._clock())
        )
        token = self._signer.sign(claims, config.secret)
        # FR-10: 토큰·비밀·클레임 값(메일함)은 남기지 않는다.
        self._logger.info(
            "MCP identity header issued",
            request_id=request_id,
            server_id=server_id,
            identity_sub=subject,
            identity_source=config.claim_source.value,
            identity_header=config.header_name,
        )
        return {config.header_name: token}

    async def _find_user(self, subject: str) -> User | None:
        # 플랫폼 사용자 ID 는 정수 PK 다. 그 외 값(anonymous 등)은 사용자 없음.
        if not subject.isdigit():
            return None
        return await self._reader.find_by_id(int(subject))


def _unreadable_provider(server_id: str) -> HeaderProvider:
    async def provide() -> dict[str, str]:
        raise IdentityConfigUnreadableError(
            f"identity_config of MCP server {server_id!r} is unreadable — re-enter it"
        )

    return provide
