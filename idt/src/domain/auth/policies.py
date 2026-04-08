"""Auth domain policies."""


class PasswordPolicy:
    MIN_LENGTH: int = 8
    MAX_LENGTH: int = 128

    @classmethod
    def validate(cls, password: str) -> None:
        if len(password) < cls.MIN_LENGTH:
            raise ValueError(f"Password must be at least {cls.MIN_LENGTH} characters")
        if len(password) > cls.MAX_LENGTH:
            raise ValueError(f"Password must be at most {cls.MAX_LENGTH} characters")
