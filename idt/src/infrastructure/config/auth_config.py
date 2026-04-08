"""Auth configuration via pydantic-settings."""
from pydantic_settings import BaseSettings


class AuthConfig(BaseSettings):
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 7

    model_config = {"env_file": ".env", "extra": "ignore"}
