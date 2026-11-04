"""ToolAccessResolver — 실행 주체 → ToolAccessSet 조립.

Design Ref: tool-access-control §2.1, §3.5, §0 F1
- for_auth_ctx: 채팅·웹훅·잡 (부서는 auth_ctx 값 사용, 쿼리 1회)
- for_user_id : auth_ctx 없이 user_id 만 있는 스케줄·승인 재개·RAGAS (쿼리 3회)
- for_user    : 라우터가 User 엔티티를 가진 카탈로그 조회 등

Fail-Closed: 주체를 특정할 수 없으면 deny_all. 저장소 예외는 올린다 —
실행 경로는 호출자가 deny_all 로 강등하고, 저장 경로는 저장을 막는다 (§6.2).
판정 규칙 자체는 ToolAccessPolicy 가 가진다.
"""
from src.domain.agent_run.auth_context import AuthContext
from src.domain.auth.entities import User, UserStatus
from src.domain.auth.interfaces import UserRepositoryInterface
from src.domain.department.interfaces import DepartmentRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.tool_access.interfaces import ToolAccessRepositoryInterface
from src.domain.tool_access.policy import ToolAccessPolicy
from src.domain.tool_access.value_objects import ToolAccessSet

_ADMIN = "admin"
_USER = "user"


class ToolAccessResolver:
    def __init__(
        self,
        grant_repo: ToolAccessRepositoryInterface,
        user_repo: UserRepositoryInterface,
        department_repo: DepartmentRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._grant_repo = grant_repo
        self._user_repo = user_repo
        self._department_repo = department_repo
        self._logger = logger

    async def for_auth_ctx(
        self, auth_ctx: AuthContext | None, request_id: str
    ) -> ToolAccessSet:
        if auth_ctx is None or auth_ctx.user_id <= 0:
            return self._deny("no_auth_ctx", request_id)
        return await self._build(
            role=auth_ctx.role,
            user_id=auth_ctx.user_id,
            department_ids=list(auth_ctx.department_ids),
            request_id=request_id,
        )

    async def for_user_id(
        self, user_id: str | int | None, request_id: str
    ) -> ToolAccessSet:
        uid = _parse_user_id(user_id)
        if uid is None:
            return self._deny("invalid_user_id", request_id)
        user = await self._user_repo.find_by_id(uid)
        if user is None:
            return self._deny("user_not_found", request_id)
        return await self.for_user(user, request_id)

    async def for_user(self, user: User, request_id: str) -> ToolAccessSet:
        if user.id is None:
            return self._deny("user_without_id", request_id)
        if user.status != UserStatus.APPROVED:
            return self._deny("user_not_approved", request_id)
        role = user.role.value
        if role == _ADMIN:
            return ToolAccessSet.admin()
        memberships = await self._department_repo.find_departments_by_user(
            user.id, request_id
        )
        return await self._build(
            role=role,
            user_id=user.id,
            department_ids=[m.department_id for m in memberships],
            request_id=request_id,
        )

    async def _build(
        self, *, role: str, user_id: int, department_ids: list[str], request_id: str
    ) -> ToolAccessSet:
        if role == _ADMIN:
            return ToolAccessSet.admin()
        if role != _USER:
            return self._deny(f"role:{role}", request_id)
        grants = await self._grant_repo.find_grants_for(
            user_id, department_ids, request_id
        )
        return ToolAccessPolicy.build(role=role, grants=grants)

    def _deny(self, reason: str, request_id: str) -> ToolAccessSet:
        self._logger.info(
            "ToolAccessResolver deny_all", request_id=request_id, reason=reason
        )
        return ToolAccessSet.deny_all()


def _parse_user_id(raw: str | int | None) -> int | None:
    if raw is None or isinstance(raw, bool):
        return None
    try:
        uid = int(str(raw).strip())
    except ValueError:
        return None
    return uid if uid > 0 else None
