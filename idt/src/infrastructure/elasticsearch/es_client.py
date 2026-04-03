"""Elasticsearch async connection adapter."""
from elasticsearch import AsyncElasticsearch

from src.infrastructure.config.elasticsearch_config import ElasticsearchConfig


class ElasticsearchClient:
    """AsyncElasticsearch 연결 어댑터."""

    def __init__(self, es: AsyncElasticsearch) -> None:
        self._es = es

    @classmethod
    def from_config(cls, config: ElasticsearchConfig) -> "ElasticsearchClient":
        """설정으로부터 ElasticsearchClient 생성."""
        kwargs: dict = {
            "hosts": [
                {
                    "host": config.ES_HOST,
                    "port": config.ES_PORT,
                    "scheme": config.ES_SCHEME,
                }
            ],
            "max_retries": config.ES_MAX_RETRIES,
            "retry_on_timeout": config.ES_RETRY_ON_TIMEOUT,
            "request_timeout": config.ES_REQUEST_TIMEOUT,
        }
        if config.ES_USERNAME and config.ES_PASSWORD:
            kwargs["http_auth"] = (config.ES_USERNAME, config.ES_PASSWORD)
        if config.ES_CA_CERTS:
            kwargs["ca_certs"] = config.ES_CA_CERTS
        return cls(es=AsyncElasticsearch(**kwargs))

    def get_client(self) -> AsyncElasticsearch:
        """AsyncElasticsearch 인스턴스 반환."""
        return self._es

    async def close(self) -> None:
        """연결 종료."""
        await self._es.close()
