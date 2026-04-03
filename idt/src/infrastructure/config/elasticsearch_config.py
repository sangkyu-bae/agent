"""Elasticsearch configuration from environment variables."""
from pydantic_settings import BaseSettings


class ElasticsearchConfig(BaseSettings):
    """Elasticsearch 연결 설정 (환경변수 기반)."""

    ES_HOST: str = "localhost"
    ES_PORT: int = 9200
    ES_SCHEME: str = "http"
    ES_USERNAME: str = ""
    ES_PASSWORD: str = ""
    ES_CA_CERTS: str = ""
    ES_MAX_RETRIES: int = 3
    ES_RETRY_ON_TIMEOUT: bool = True
    ES_REQUEST_TIMEOUT: int = 30

    model_config = {"env_file": ".env", "extra": "ignore"}
