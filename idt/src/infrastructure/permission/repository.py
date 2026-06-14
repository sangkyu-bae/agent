"""PermissionRepository — permissions/role_permissions/user_permissions MySQL CRUD.

agent-user-context Design §5.3.
- 권한 부여(grant_to_user): idempotent (이미 있으면 무시)
- 권한 회수(revoke_from_user): idempotent (없어도 에러 X)
- find_codes_for_user는 role 기본 권한 제외 — user 추가 grant만 반환
"""
from sqlalchemy import delete, select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.permission.interfaces import PermissionRepositoryInterface
from src.infrastructure.permission.models import (
    RolePermissionModel,
    UserPermissionModel,
)


class PermissionRepository(PermissionRepositoryInterface):
    def __init__(self, session: AsyncSession, logger: LoggerInterface) -> None:
        self._session = session
        self._logger = logger

    async def find_codes_for_role(
        self, role: str, request_id: str
    ) -> list[str]:
        self._logger.info(
            "Permission find_for_role", request_id=request_id, role=role,
        )
        try:
            stmt = select(RolePermissionModel.permission_code).where(
                RolePermissionModel.role == role
            )
            result = await self._session.execute(stmt)
            return [row[0] for row in result.all()]
        except Exception as e:
            self._logger.error(
                "Permission find_for_role failed",
                exception=e, request_id=request_id,
            )
            raise

    async def find_codes_for_user(
        self, user_id: int, request_id: str
    ) -> list[str]:
        self._logger.info(
            "Permission find_for_user", request_id=request_id, user_id=user_id,
        )
        try:
            stmt = select(UserPermissionModel.permission_code).where(
                UserPermissionModel.user_id == user_id
            )
            result = await self._session.execute(stmt)
            return [row[0] for row in result.all()]
        except Exception as e:
            self._logger.error(
                "Permission find_for_user failed",
                exception=e, request_id=request_id,
            )
            raise

    async def grant_to_user(
        self, user_id: int, code: str, granted_by: int, request_id: str
    ) -> None:
        """idempotent grant — 이미 있으면 무시. 이벤트 형태로 LOG."""
        self._logger.info(
            "Permission grant",
            request_id=request_id, user_id=user_id, code=code, granted_by=granted_by,
        )
        try:
            stmt = mysql_insert(UserPermissionModel).values(
                user_id=user_id,
                permission_code=code,
                granted_by=granted_by,
            )
            # idempotent: 같은 PK가 이미 있으면 granted_by만 갱신 (감사 trail 보존)
            stmt = stmt.on_duplicate_key_update(
                granted_by=stmt.inserted.granted_by,
            )
            await self._session.execute(stmt)
            await self._session.flush()
        except Exception as e:
            self._logger.error(
                "Permission grant failed",
                exception=e, request_id=request_id,
            )
            raise

    async def revoke_from_user(
        self, user_id: int, code: str, request_id: str
    ) -> None:
        """idempotent revoke — 없어도 에러 X."""
        self._logger.info(
            "Permission revoke",
            request_id=request_id, user_id=user_id, code=code,
        )
        try:
            stmt = delete(UserPermissionModel).where(
                UserPermissionModel.user_id == user_id,
                UserPermissionModel.permission_code == code,
            )
            await self._session.execute(stmt)
            await self._session.flush()
        except Exception as e:
            self._logger.error(
                "Permission revoke failed",
                exception=e, request_id=request_id,
            )
            raise
