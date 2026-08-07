"""WebhookOutboundPolicy 단위 테스트 (M2 Design §6)."""
from src.domain.agent_webhook.policies import WebhookOutboundPolicy


class TestIsValidUrl:
    def test_http_https_pass(self):
        assert WebhookOutboundPolicy.is_valid_url("http://intra.local/hook")
        assert WebhookOutboundPolicy.is_valid_url("https://example.com/wh")

    def test_other_scheme_rejected(self):
        assert not WebhookOutboundPolicy.is_valid_url("ftp://example.com/x")
        assert not WebhookOutboundPolicy.is_valid_url("file:///etc/passwd")

    def test_missing_scheme_or_host_rejected(self):
        assert not WebhookOutboundPolicy.is_valid_url("example.com/wh")
        assert not WebhookOutboundPolicy.is_valid_url("https://")
        assert not WebhookOutboundPolicy.is_valid_url("")


class TestShouldRetry:
    def test_connection_failure_retries(self):
        assert WebhookOutboundPolicy.should_retry(None)

    def test_5xx_retries(self):
        assert WebhookOutboundPolicy.should_retry(500)
        assert WebhookOutboundPolicy.should_retry(503)

    def test_2xx_4xx_no_retry(self):
        assert not WebhookOutboundPolicy.should_retry(200)
        assert not WebhookOutboundPolicy.should_retry(404)
        assert not WebhookOutboundPolicy.should_retry(422)


class TestConstants:
    def test_retry_and_backoff_shape(self):
        assert WebhookOutboundPolicy.MAX_RETRIES == 3
        assert len(WebhookOutboundPolicy.BACKOFF_SECONDS) == 3
        assert WebhookOutboundPolicy.EVENT_RUN_COMPLETED == "agent.run.completed"
