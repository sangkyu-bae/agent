"""관리자용 권한 부여/회수 UseCase.

agent-user-context Design §4.
- grant/revoke 모두 idempotent (Repository 단에서 보장)
- 권한 변경은 다음 요청부터 반영 (현재 진행 중인 stream은 시작 시점 스냅샷 유지)
"""
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.permission.interfaces import PermissionRepositoryInterface
from src.domain.permission.value_objects import PermissionCode


class GrantPermissionUseCase:
    def __init__(
        self,
        permission_repo: PermissionRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._permission_repo = permission_repo
        self._logger = logger

    async def execute(
        self, user_id: int, code: str, granted_by: int, request_id: str
    ) -> None:
        # 유효한 권한 코드인지 enum으로 검증 — 알 수 없는 코드 차단
        try:
            PermissionCode(code)
        except ValueError as e:
            raise ValueError(f"Unknown permission code: {code}") from e

        await self._permission_repo.grant_to_user(
            user_id=user_id, code=code, granted_by=granted_by, request_id=request_id,
        )


class RevokePermissionUseCase:
    def __init__(
        self,
        permission_repo: PermissionRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._permission_repo = permission_repo
        self._logger = logger

    async def execute(self, user_id: int, code: str, request_id: str) -> None:
        # 유효한 권한 코드인지 검증
        try:
            PermissionCode(code)
        except ValueError as e:
            raise ValueError(f"Unknown permission code: {code}") from e

        await self._permission_repo.revoke_from_user(
            user_id=user_id, code=code, request_id=request_id,
        )
