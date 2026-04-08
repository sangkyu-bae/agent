"""Auth value objects."""
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Email:
    value: str

    def __post_init__(self) -> None:
        pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
        if not re.match(pattern, self.value):
            raise ValueError(f"Invalid email format: {self.value}")


@dataclass(frozen=True)
class HashedPassword:
    value: str  # bcrypt 해시 문자열


@dataclass(frozen=True)
class TokenPayload:
    sub: str
    role: str
    token_type: str  # "access" | "refresh"
    exp: int
