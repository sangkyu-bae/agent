"""Policy tests — mock 금지."""
import pytest
from src.domain.auth.policies import PasswordPolicy


class TestPasswordPolicy:
    def test_valid_password(self) -> None:
        PasswordPolicy.validate("secure1234")  # 통과 시 예외 없음

    def test_too_short_raises(self) -> None:
        with pytest.raises(ValueError, match="at least"):
            PasswordPolicy.validate("abc")

    def test_exactly_min_length(self) -> None:
        PasswordPolicy.validate("a" * PasswordPolicy.MIN_LENGTH)

    def test_too_long_raises(self) -> None:
        with pytest.raises(ValueError, match="at most"):
            PasswordPolicy.validate("a" * (PasswordPolicy.MAX_LENGTH + 1))
