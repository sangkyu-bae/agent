"""JWTAdapter tests (Mock 사용)."""
import time
import pytest
from unittest.mock import MagicMock
from src.infrastructure.auth.jwt_adapter import JWTAdapter
from src.infrastructure.config.auth_config import AuthConfig


@pytest.fixture
def config() -> AuthConfig:
    return AuthConfig(
        jwt_secret_key="test-secret-key-for-testing-only",
        jwt_algorithm="HS256",
        jwt_access_token_expire_minutes=15,
        jwt_refresh_token_expire_days=7,
    )


@pytest.fixture
def adapter(config: AuthConfig) -> JWTAdapter:
    return JWTAdapter(config)


class TestJWTAdapter:
    def test_create_access_token_returns_string(self, adapter: JWTAdapter) -> None:
        token = adapter.create_access_token(user_id=1, role="user")
        assert isinstance(token, str)
        assert len(token) > 0

    def test_create_refresh_token_returns_string(self, adapter: JWTAdapter) -> None:
        token = adapter.create_refresh_token(user_id=1, role="user")
        assert isinstance(token, str)

    def test_decode_access_token(self, adapter: JWTAdapter) -> None:
        token = adapter.create_access_token(user_id=42, role="admin")
        payload = adapter.decode(token)
        assert payload.sub == "42"
        assert payload.role == "admin"
        assert payload.token_type == "access"

    def test_decode_refresh_token_type(self, adapter: JWTAdapter) -> None:
        token = adapter.create_refresh_token(user_id=1, role="user")
        payload = adapter.decode(token)
        assert payload.token_type == "refresh"

    def test_decode_invalid_token_raises(self, adapter: JWTAdapter) -> None:
        with pytest.raises(ValueError, match="Invalid token"):
            adapter.decode("not.a.valid.token")

    def test_hash_token_is_deterministic(self) -> None:
        h1 = JWTAdapter.hash_token("some-token")
        h2 = JWTAdapter.hash_token("some-token")
        assert h1 == h2

    def test_hash_token_different_inputs(self) -> None:
        h1 = JWTAdapter.hash_token("token-a")
        h2 = JWTAdapter.hash_token("token-b")
        assert h1 != h2

    def test_hash_token_length_64(self) -> None:
        # SHA-256 hex = 64 chars
        assert len(JWTAdapter.hash_token("any-token")) == 64
