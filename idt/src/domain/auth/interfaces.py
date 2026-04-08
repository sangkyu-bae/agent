"""Auth domain interfaces (abstract)."""
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

from src.domain.auth.entities import User, UserStatus
from src.domain.auth.value_objects import TokenPayload


class UserRepositoryInterface(ABC):
    @abstractmethod
    async def save(self, user: User) -> User: ...

    @abstractmethod
    async def find_by_email(self, email: str) -> Optional[User]: ...

    @abstractmethod
    async def find_by_id(self, user_id: int) -> Optional[User]: ...

    @abstractmethod
    async def find_by_status(self, status: UserStatus) -> list[User]: ...

    @abstractmethod
    async def update_status(self, user_id: int, status: UserStatus) -> None: ...


class RefreshTokenRepositoryInterface(ABC):
    @abstractmethod
    async def save(self, user_id: int, token_hash: str, expires_at: datetime) -> None: ...

    @abstractmethod
    async def find_valid(self, token_hash: str) -> Optional[dict]: ...
    # dict keys: user_id (int), expires_at (datetime), revoked_at (datetime|None)

    @abstractmethod
    async def revoke(self, token_hash: str) -> None: ...


class PasswordHasherInterface(ABC):
    @abstractmethod
    def hash(self, plain_password: str) -> str: ...

    @abstractmethod
    def verify(self, plain_password: str, hashed: str) -> bool: ...


class JWTAdapterInterface(ABC):
    @abstractmethod
    def create_access_token(self, user_id: int, role: str) -> str: ...

    @abstractmethod
    def create_refresh_token(self, user_id: int, role: str) -> str: ...

    @abstractmethod
    def decode(self, token: str) -> TokenPayload: ...

    @staticmethod
    @abstractmethod
    def hash_token(token: str) -> str: ...
