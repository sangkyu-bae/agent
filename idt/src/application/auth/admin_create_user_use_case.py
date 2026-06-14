"""AdminCreateUserUseCase.

admin-user-registration Design §4.1:
관리자가 직원 계정을 즉시 활성(status=approved)으로 직접 생성한다.
User + UserProfile(전체 필드) + (선택) 부서 배정을 단일 세션에서 처리한다.
"""
from dataclasses import dataclass
from datetime import date, datetime, timezone

from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.auth.interfaces import PasswordHasherInterface, UserRepositoryInterface
from src.domain.auth.policies import PasswordPolicy
from src.domain.auth.value_objects import Email
from src.domain.department.entity import UserDepartment
from src.domain.department.interfaces import DepartmentRepositoryInterface
from src.domain.logging.interfaces import LoggerInterface
from src.domain.user_profile.entity import UserProfile
from src.domain.user_profile.interfaces import UserProfileRepositoryInterface


@dataclass
class AdminCreateUserCommand:
    email: str
    password: str
    display_name: str
    position: str | None = None
    employee_no: str | None = None
    joined_at: date | None = None
    role: str = "user"
    department_id: str | None = None


@dataclass
class AdminCreateUserResult:
    user_id: int
    email: str
    role: str
    status: str
    display_name: str
    position: str | None
    employee_no: str | None
    joined_at: date | None
    department_id: str | None


class AdminCreateUserUseCase:
    def __init__(
        self,
        user_repo: UserRepositoryInterface,
        user_profile_repo: UserProfileRepositoryInterface,
        department_repo: DepartmentRepositoryInterface,
        password_hasher: PasswordHasherInterface,
        logger: LoggerInterface,
    ) -> None:
        self._user_repo = user_repo
        self._profile_repo = user_profile_repo
        self._dept_repo = department_repo
        self._hasher = password_hasher
        self._logger = logger

    async def execute(
        self, cmd: AdminCreateUserCommand, request_id: str, created_by: int
    ) -> AdminCreateUserResult:
        self._logger.info(
            "AdminCreateUser start",
            request_id=request_id, email=cmd.email,
            role=cmd.role, created_by=created_by,
        )

        # 1) 검증
        Email(cmd.email)
        PasswordPolicy.validate(cmd.password)
        if not cmd.display_name or not cmd.display_name.strip():
            raise ValueError("display_name is required")
        role = UserRole(cmd.role)  # 잘못된 값이면 ValueError → 422

        # 2) 중복 체크
        if await self._user_repo.find_by_email(cmd.email):
            raise ValueError(f"Email already registered: {cmd.email}")

        # 3) User — 즉시 활성(approved)
        hashed = self._hasher.hash(cmd.password)
        saved = await self._user_repo.save(
            User(
                email=cmd.email, password_hash=hashed,
                role=role, status=UserStatus.APPROVED,
            )
        )

        # 4) UserProfile (전체 필드)
        now = datetime.now(timezone.utc)
        display_name = cmd.display_name.strip()
        await self._profile_repo.upsert(
            UserProfile(
                user_id=saved.id,
                display_name=display_name,
                position=(cmd.position or None),
                employee_no=(cmd.employee_no or None),
                joined_at=cmd.joined_at,
                created_at=now,
                updated_at=now,
            ),
            request_id,
        )

        # 5) 부서 배정 (선택) — 동일 세션, 실패 시 전체 롤백
        if cmd.department_id:
            dept = await self._dept_repo.find_by_id(cmd.department_id, request_id)
            if dept is None:
                raise ValueError(f"부서를 찾을 수 없습니다: {cmd.department_id}")
            await self._dept_repo.assign_user(
                UserDepartment(
                    user_id=saved.id,
                    department_id=cmd.department_id,
                    is_primary=True,
                    created_at=now,
                ),
                request_id,
            )

        self._logger.info(
            "AdminCreateUser done", request_id=request_id, user_id=saved.id
        )
        return AdminCreateUserResult(
            user_id=saved.id, email=saved.email,
            role=saved.role.value, status=saved.status.value,
            display_name=display_name,
            position=cmd.position, employee_no=cmd.employee_no,
            joined_at=cmd.joined_at, department_id=cmd.department_id,
        )
