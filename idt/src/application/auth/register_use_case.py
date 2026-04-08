"""Register UseCase."""
from dataclasses import dataclass

from src.domain.auth.entities import User
from src.domain.auth.interfaces import PasswordHasherInterface, UserRepositoryInterface
from src.domain.auth.policies import PasswordPolicy
from src.domain.auth.value_objects import Email
from src.domain.logging.interfaces import LoggerInterface


@dataclass
class RegisterRequest:
    email: str
    password: str


@dataclass
class RegisterResult:
    user_id: int
    email: str
    role: str
    status: str


class RegisterUseCase:
    def __init__(
        self,
        user_repo: UserRepositoryInterface,
        password_hasher: PasswordHasherInterface,
        logger: LoggerInterface,
    ) -> None:
        self._user_repo = user_repo
        self._hasher = password_hasher
        self._logger = logger

    async def execute(self, request: RegisterRequest, request_id: str) -> RegisterResult:
        self._logger.info("Register started", request_id=request_id, email=request.email)

        Email(request.email)
        PasswordPolicy.validate(request.password)

        existing = await self._user_repo.find_by_email(request.email)
        if existing:
            raise ValueError(f"Email already registered: {request.email}")

        hashed = self._hasher.hash(request.password)
        user = User(email=request.email, password_hash=hashed)
        saved = await self._user_repo.save(user)

        self._logger.info("Register completed", request_id=request_id, user_id=saved.id)
        return RegisterResult(
            user_id=saved.id,
            email=saved.email,
            role=saved.role.value,
            status=saved.status.value,
        )
