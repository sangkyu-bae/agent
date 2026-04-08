"""JWT adapter using python-jose."""
import hashlib
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from src.domain.auth.interfaces import JWTAdapterInterface
from src.domain.auth.value_objects import TokenPayload
from src.infrastructure.config.auth_config import AuthConfig


class JWTAdapter(JWTAdapterInterface):
    def __init__(self, config: AuthConfig) -> None:
        self._config = config

    def create_access_token(self, user_id: int, role: str) -> str:
        exp = datetime.now(timezone.utc) + timedelta(
            minutes=self._config.jwt_access_token_expire_minutes
        )
        payload = {
            "sub": str(user_id),
            "role": role,
            "token_type": "access",
            "exp": exp,
        }
        return jwt.encode(
            payload,
            self._config.jwt_secret_key,
            algorithm=self._config.jwt_algorithm,
        )

    def create_refresh_token(self, user_id: int, role: str) -> str:
        exp = datetime.now(timezone.utc) + timedelta(
            days=self._config.jwt_refresh_token_expire_days
        )
        payload = {
            "sub": str(user_id),
            "role": role,
            "token_type": "refresh",
            "exp": exp,
        }
        return jwt.encode(
            payload,
            self._config.jwt_secret_key,
            algorithm=self._config.jwt_algorithm,
        )

    def decode(self, token: str) -> TokenPayload:
        try:
            data = jwt.decode(
                token,
                self._config.jwt_secret_key,
                algorithms=[self._config.jwt_algorithm],
            )
            return TokenPayload(
                sub=data["sub"],
                role=data["role"],
                token_type=data["token_type"],
                exp=data["exp"],
            )
        except (JWTError, KeyError) as e:
            raise ValueError(f"Invalid token: {e}") from e

    @staticmethod
    def hash_token(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()
