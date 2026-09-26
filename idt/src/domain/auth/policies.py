"""Auth domain policies."""
import re
from typing import Optional

# local@domain.tld — 공백·중복 @ 불가, 도메인에 점 1개 이상.
_MAILBOX_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class MailboxPolicy:
    """사내 메일함 UPN 정규화 규칙 (Design Ref: mcp-identity-header §4.2)."""

    MAX_LENGTH: int = 255

    @classmethod
    def normalize(cls, value: Optional[str]) -> Optional[str]:
        """trim + 소문자. 빈 값은 해제를 뜻하는 None. 형식 위반은 ValueError."""
        normalized = (value or "").strip().lower()
        if not normalized:
            return None
        if len(normalized) > cls.MAX_LENGTH:
            raise ValueError(f"Mailbox must be at most {cls.MAX_LENGTH} characters")
        if not _MAILBOX_PATTERN.match(normalized):
            raise ValueError("Mailbox must be an email address")
        return normalized



class PasswordPolicy:
    MIN_LENGTH: int = 8
    MAX_LENGTH: int = 128

    @classmethod
    def validate(cls, password: str) -> None:
        if len(password) < cls.MIN_LENGTH:
            raise ValueError(f"Password must be at least {cls.MIN_LENGTH} characters")
        if len(password) > cls.MAX_LENGTH:
            raise ValueError(f"Password must be at most {cls.MAX_LENGTH} characters")
