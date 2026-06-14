"""ListUsersUseCase.

admin-user-registration Design §4.2:
전체 사용자 목록(프로필 + 부서명)을 필터/페이지네이션으로 조회한다.
부서명은 list_all로 id→name 맵을 1회 구성해 매핑한다.
"""
from dataclasses import dataclass, field
from datetime import datetime

from src.domain.auth.interfaces import UserListFilters, UserRepositoryInterface
from src.domain.department.interfaces import DepartmentRepositoryInterface
from src.domain.logging.interfaces import LoggerInterface
from src.domain.user_profile.interfaces import UserProfileRepositoryInterface


@dataclass
class UserListItem:
    id: int
    email: str
    role: str
    status: str
    display_name: str | None
    position: str | None
    department_names: list[str] = field(default_factory=list)
    created_at: datetime | None = None


@dataclass
class UserListResult:
    items: list[UserListItem]
    total: int


class ListUsersUseCase:
    def __init__(
        self,
        user_repo: UserRepositoryInterface,
        user_profile_repo: UserProfileRepositoryInterface,
        department_repo: DepartmentRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._user_repo = user_repo
        self._profile_repo = user_profile_repo
        self._dept_repo = department_repo
        self._logger = logger

    async def execute(
        self, filters: UserListFilters, request_id: str
    ) -> UserListResult:
        self._logger.info("ListUsers start", request_id=request_id)

        users, total = await self._user_repo.find_all(filters, request_id)

        # 부서 id→name 맵 1회 구성 (N+1 회피)
        dept_name_by_id = {
            d.id: d.name
            for d in await self._dept_repo.list_all(request_id)
        }

        items: list[UserListItem] = []
        for u in users:
            profile = await self._profile_repo.find_by_user_id(u.id, request_id)
            user_depts = await self._dept_repo.find_departments_by_user(
                u.id, request_id
            )
            dept_names = [
                dept_name_by_id[ud.department_id]
                for ud in user_depts
                if ud.department_id in dept_name_by_id
            ]
            items.append(
                UserListItem(
                    id=u.id,
                    email=u.email,
                    role=u.role.value,
                    status=u.status.value,
                    display_name=profile.display_name if profile else None,
                    position=profile.position if profile else None,
                    department_names=dept_names,
                    created_at=u.created_at,
                )
            )

        return UserListResult(items=items, total=total)
