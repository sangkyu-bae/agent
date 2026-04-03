"""Tests for ElasticsearchClient connection management."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestElasticsearchClient:
    """ElasticsearchClient 연결 관리 테스트."""

    @patch("src.infrastructure.elasticsearch.es_client.AsyncElasticsearch")
    def test_from_config_creates_client_with_host_and_port(self, mock_es_cls):
        """from_config() 호출 시 AsyncElasticsearch가 host/port로 생성된다."""
        from src.infrastructure.elasticsearch.es_client import ElasticsearchClient
        from src.infrastructure.config.elasticsearch_config import ElasticsearchConfig

        config = ElasticsearchConfig(ES_HOST="localhost", ES_PORT=9200)
        ElasticsearchClient.from_config(config)

        mock_es_cls.assert_called_once()
        call_kwargs = mock_es_cls.call_args[1]
        hosts = call_kwargs["hosts"]
        assert any("localhost" in str(h) for h in hosts)

    @patch("src.infrastructure.elasticsearch.es_client.AsyncElasticsearch")
    def test_from_config_passes_auth_when_credentials_provided(self, mock_es_cls):
        """username/password가 있을 때 http_auth가 전달된다."""
        from src.infrastructure.elasticsearch.es_client import ElasticsearchClient
        from src.infrastructure.config.elasticsearch_config import ElasticsearchConfig

        config = ElasticsearchConfig(
            ES_HOST="localhost",
            ES_PORT=9200,
            ES_USERNAME="admin",
            ES_PASSWORD="secret",
        )
        ElasticsearchClient.from_config(config)

        call_kwargs = mock_es_cls.call_args[1]
        assert call_kwargs["http_auth"] == ("admin", "secret")

    @patch("src.infrastructure.elasticsearch.es_client.AsyncElasticsearch")
    def test_from_config_no_auth_when_credentials_empty(self, mock_es_cls):
        """username/password가 없을 때 http_auth가 전달되지 않는다."""
        from src.infrastructure.elasticsearch.es_client import ElasticsearchClient
        from src.infrastructure.config.elasticsearch_config import ElasticsearchConfig

        config = ElasticsearchConfig(ES_HOST="localhost", ES_PORT=9200)
        ElasticsearchClient.from_config(config)

        call_kwargs = mock_es_cls.call_args[1]
        assert "http_auth" not in call_kwargs

    @patch("src.infrastructure.elasticsearch.es_client.AsyncElasticsearch")
    def test_get_client_returns_async_elasticsearch_instance(self, mock_es_cls):
        """get_client()는 AsyncElasticsearch 인스턴스를 반환한다."""
        from src.infrastructure.elasticsearch.es_client import ElasticsearchClient
        from src.infrastructure.config.elasticsearch_config import ElasticsearchConfig

        mock_instance = MagicMock()
        mock_es_cls.return_value = mock_instance

        config = ElasticsearchConfig(ES_HOST="localhost", ES_PORT=9200)
        client = ElasticsearchClient.from_config(config)

        assert client.get_client() is mock_instance

    @pytest.mark.asyncio
    @patch("src.infrastructure.elasticsearch.es_client.AsyncElasticsearch")
    async def test_close_calls_es_close(self, mock_es_cls):
        """close() 호출 시 AsyncElasticsearch.close()가 호출된다."""
        from src.infrastructure.elasticsearch.es_client import ElasticsearchClient
        from src.infrastructure.config.elasticsearch_config import ElasticsearchConfig

        mock_instance = MagicMock()
        mock_instance.close = AsyncMock()
        mock_es_cls.return_value = mock_instance

        config = ElasticsearchConfig(ES_HOST="localhost", ES_PORT=9200)
        client = ElasticsearchClient.from_config(config)
        await client.close()

        mock_instance.close.assert_called_once()
