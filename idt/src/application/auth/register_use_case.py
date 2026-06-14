"""Register UseCase.

agent-user-context: display_name 필수 — 가입 시 UserProfile도 함께 생성.
"""
from dataclasses import dataclass
from datetime import datetime, timezone

from src.domain.auth.entities import User
from src.domain.auth.interfaces import PasswordHasherInterface, UserRepositoryInterface
from src.domain.auth.policies import PasswordPolicy
from src.domain.auth.value_objects import Email
from src.domain.logging.interfaces import LoggerInterface
from src.domain.user_profile.entity import UserProfile
from src.domain.user_profile.interfaces import UserProfileRepositoryInterface


@dataclass
class RegisterRequest:
    email: str
    password: str
    display_name: str


@dataclass
class RegisterResult:
    user_id: int
    email: str
    display_name: str
    role: str
    status: str


class RegisterUseCase:
    def __init__(
        self,
        user_repo: UserRepositoryInterface,
        password_hasher: PasswordHasherInterface,
        logger: LoggerInterface,
        user_profile_repo: UserProfileRepositoryInterface | None = None,
    ) -> None:
        self._user_repo = user_repo
        self._hasher = password_hasher
        self._logger = logger
        # user_profile_repo는 마이그레이션 직후 호환을 위해 Optional.
        # main.py wiring에서 반드시 주입해야 함.
        self._profile_repo = user_profile_repo

    async def execute(self, request: RegisterRequest, request_id: str) -> RegisterResult:
        self._logger.info("Register started", request_id=request_id, email=request.email)

        Email(request.email)
        PasswordPolicy.validate(request.password)
        if not request.display_name or not request.display_name.strip():
            raise ValueError("display_name is required")

        existing = await self._user_repo.find_by_email(request.email)
        if existing:
            raise ValueError(f"Email already registered: {request.email}")

        hashed = self._hasher.hash(request.password)
        user = User(email=request.email, password_hash=hashed)
        saved = await self._user_repo.save(user)

        # UserProfile 동시 생성 — V024 마이그레이션 이후 필수.
        if self._profile_repo is not None and saved.id is not None:
            now = datetime.now(timezone.utc)
            profile = UserProfile(
                user_id=saved.id,
                display_name=request.display_name.strip(),
                position=None,
                employee_no=None,
                joined_at=None,
                created_at=now,
                updated_at=now,
            )
            await self._profile_repo.upsert(profile, request_id)

        self._logger.info("Register completed", request_id=request_id, user_id=saved.id)
        return RegisterResult(
            user_id=saved.id,
            email=saved.email,
            display_name=request.display_name.strip(),
            role=saved.role.value,
            status=saved.status.value,
        )
