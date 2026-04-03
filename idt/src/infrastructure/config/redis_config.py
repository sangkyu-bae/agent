"""Redis configuration from environment variables."""
from pydantic_settings import BaseSettings


class RedisConfig(BaseSettings):
    """Redis 연결 설정 (환경변수 기반)."""

    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = ""
    REDIS_DB: int = 0
    REDIS_MAX_CONNECTIONS: int = 20

    model_config = {"env_file": ".env", "extra": "ignore"}

    @property
    def url(self) -> str:
        """Redis 연결 URL 생성."""
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
