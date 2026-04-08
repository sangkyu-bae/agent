"""bcrypt password hasher implementation."""
from passlib.context import CryptContext

from src.domain.auth.interfaces import PasswordHasherInterface


class BcryptPasswordHasher(PasswordHasherInterface):
    _ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

    def hash(self, plain_password: str) -> str:
        return self._ctx.hash(plain_password)

    def verify(self, plain_password: str, hashed: str) -> bool:
        return self._ctx.verify(plain_password, hashed)
