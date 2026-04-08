"""PasswordHasher tests (Mock 불필요 — passlib 직접 사용)."""
import pytest
from src.infrastructure.auth.password_hasher import BcryptPasswordHasher


class TestBcryptPasswordHasher:
    def setup_method(self) -> None:
        self.hasher = BcryptPasswordHasher()

    def test_hash_returns_string(self) -> None:
        result = self.hasher.hash("secret1234")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_hash_is_not_plain(self) -> None:
        result = self.hasher.hash("secret1234")
        assert result != "secret1234"

    def test_verify_correct_password(self) -> None:
        hashed = self.hasher.hash("secret1234")
        assert self.hasher.verify("secret1234", hashed) is True

    def test_verify_wrong_password(self) -> None:
        hashed = self.hasher.hash("secret1234")
        assert self.hasher.verify("wrong", hashed) is False

    def test_same_password_different_hashes(self) -> None:
        h1 = self.hasher.hash("secret1234")
        h2 = self.hasher.hash("secret1234")
        assert h1 != h2  # bcrypt salt 랜덤
