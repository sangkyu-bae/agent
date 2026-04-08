"""Value object tests — mock 금지."""
import pytest
from src.domain.auth.value_objects import Email, TokenPayload


class TestEmail:
    def test_valid_email(self) -> None:
        e = Email("user@example.com")
        assert e.value == "user@example.com"

    def test_invalid_email_raises(self) -> None:
        with pytest.raises(ValueError):
            Email("not-an-email")

    def test_missing_domain_raises(self) -> None:
        with pytest.raises(ValueError):
            Email("user@")

    def test_frozen(self) -> None:
        e = Email("a@b.com")
        with pytest.raises(Exception):
            e.value = "x@y.com"  # type: ignore[misc]


class TestTokenPayload:
    def test_fields(self) -> None:
        p = TokenPayload(sub="1", role="user", token_type="access", exp=9999999999)
        assert p.sub == "1"
        assert p.role == "user"
        assert p.token_type == "access"

    def test_frozen(self) -> None:
        p = TokenPayload(sub="1", role="user", token_type="access", exp=9999999999)
        with pytest.raises(Exception):
            p.sub = "2"  # type: ignore[misc]
