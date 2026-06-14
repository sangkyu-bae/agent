"""AssembleAuthContextUseCase — User → AuthContext 조립.

agent-user-context Design §4.2:
- 요청당 1회 실행 (FastAPI Dependency에서 호출)
- DB round-trip 3회 (profile, departments+department names, permissions)
- profile 미존재 시 email local-part로 display_name fallback
"""
from src.domain.agent_run.auth_context import AuthContext
from src.domain.auth.entities import User
from src.domain.department.interfaces import DepartmentRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.permission.interfaces import PermissionRepositoryInterface
from src.domain.permission.resolver import PermissionResolver
from src.domain.user_profile.interfaces import UserProfileRepositoryInterface


class AssembleAuthContextUseCase:
    def __init__(
        self,
        profile_repo: UserProfileRepositoryInterface,
        department_repo: DepartmentRepositoryInterface,
        permission_repo: PermissionRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._profile_repo = profile_repo
        self._department_repo = department_repo
        self._permission_repo = permission_repo
        self._logger = logger

    async def execute(self, user: User, request_id: str) -> AuthContext:
        if user.id is None:
            raise ValueError("Cannot assemble AuthContext for user without id")

        self._logger.info(
            "AssembleAuthContext start", request_id=request_id, user_id=user.id,
        )

        # 1) display_name — profile 없으면 email local-part로 fallback
        profile = await self._profile_repo.find_by_user_id(user.id, request_id)
        display_name = (
            profile.display_name if profile else user.email.split("@")[0]
        )

        # 2) 부서 정보 — UserDepartment + 각 Department 이름 조회
        user_depts = await self._department_repo.find_departments_by_user(
            user.id, request_id,
        )
        primary = next((d for d in user_depts if d.is_primary), None)

        dept_id_to_name: dict[str, str] = {}
        for ud in user_depts:
            dept = await self._department_repo.find_by_id(
                ud.department_id, request_id,
            )
            if dept is not None:
                dept_id_to_name[dept.id] = dept.name

        dept_ids = tuple(ud.department_id for ud in user_depts)
        dept_names = tuple(
            dept_id_to_name[did] for did in dept_ids if did in dept_id_to_name
        )

        primary_dept_id = primary.department_id if primary else None
        primary_dept_name = (
            dept_id_to_name.get(primary.department_id) if primary else None
        )

        # 3) 권한 — role 기본 + user 추가 grant
        role_codes = await self._permission_repo.find_codes_for_role(
            user.role.value, request_id,
        )
        user_codes = await self._permission_repo.find_codes_for_user(
            user.id, request_id,
        )
        permissions = PermissionResolver.resolve(role_codes, user_codes)

        ctx = AuthContext(
            user_id=user.id,
            display_name=display_name,
            role=user.role.value,
            primary_department_id=primary_dept_id,
            primary_department_name=primary_dept_name,
            department_ids=dept_ids,
            department_names=dept_names,
            permissions=permissions,
        )
        self._logger.info(
            "AssembleAuthContext done",
            request_id=request_id, user_id=user.id,
            permission_count=len(permissions),
            department_count=len(dept_ids),
        )
        return ctx
