"""권한 코드 읽기 어댑터 (application.ports.PermissionCodesReader 구현).

Design Ref: stock-analysis-agents DD10. 플랫폼 PermissionRepository 의 role 기본 권한과
사용자 추가 권한을 PermissionResolver 로 합친다 — AuthContext 조립과 같은 규칙이다.
"""

from __future__ import annotations

from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.permission.interfaces import PermissionRepositoryInterface
from src.domain.permission.resolver import PermissionResolver


class PermissionCodesReader:
    def __init__(
        self, repo: PermissionRepositoryInterface, logger: LoggerInterface
    ) -> None:
        self._repo = repo
        self._logger = logger

    async def codes_for(
        self, user_id: int, role: str, request_id: str
    ) -> frozenset[str]:
        role_codes = await self._repo.find_codes_for_role(role, request_id)
        user_codes = await self._repo.find_codes_for_user(user_id, request_id)
        return PermissionResolver.resolve(role_codes, user_codes)
