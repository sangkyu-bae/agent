"""HttpxOutboundSender 단위 테스트 — httpx.MockTransport 기반 (M2 Design §6)."""
import httpx
import pytest

from src.infrastructure.webhook.outbound_sender import HttpxOutboundSender

URL = "http://receiver.local/hook"
REQ = "req-1"


class FakeLogger:
    def info(self, *a, **k): ...
    def warning(self, *a, **k): ...
    def error(self, *a, **k): ...
    def debug(self, *a, **k): ...


async def _no_sleep(_seconds):
    return None


def _sender(handler) -> HttpxOutboundSender:
    return HttpxOutboundSender(
        logger=FakeLogger(),
        transport=httpx.MockTransport(handler),
        sleep=_no_sleep,
    )


@pytest.mark.asyncio
class TestOutboundSender:
    async def test_2xx_first_try_success(self):
        calls = []

        def handler(request):
            calls.append(request)
            return httpx.Response(200)

        result = await _sender(handler).send(URL, b"{}", {"X-H": "v"}, REQ)
        assert result.success is True
        assert result.status_code == 200
        assert result.attempts == 1
        assert result.error is None
        assert calls[0].headers["X-H"] == "v"
        assert calls[0].headers["Content-Type"] == "application/json"

    async def test_5xx_then_success_retries(self):
        responses = iter([500, 500, 200])

        def handler(request):
            return httpx.Response(next(responses))

        result = await _sender(handler).send(URL, b"{}", {}, REQ)
        assert result.success is True
        assert result.attempts == 3
        assert result.status_code == 200

    async def test_exhausted_after_4_attempts(self):
        count = {"n": 0}

        def handler(request):
            count["n"] += 1
            return httpx.Response(503)

        result = await _sender(handler).send(URL, b"{}", {}, REQ)
        assert result.success is False
        assert result.attempts == 4
        assert count["n"] == 4
        assert result.error == "HTTP 503"

    async def test_4xx_stops_immediately(self):
        count = {"n": 0}

        def handler(request):
            count["n"] += 1
            return httpx.Response(404)

        result = await _sender(handler).send(URL, b"{}", {}, REQ)
        assert result.success is False
        assert result.attempts == 1
        assert count["n"] == 1
        assert result.status_code == 404

    async def test_connection_error_status_none_and_retries(self):
        def handler(request):
            raise httpx.ConnectError("connection refused")

        result = await _sender(handler).send(URL, b"{}", {}, REQ)
        assert result.success is False
        assert result.status_code is None
        assert result.attempts == 4
        assert "connection refused" in (result.error or "")

    async def test_duration_recorded(self):
        result = await _sender(lambda r: httpx.Response(200)).send(
            URL, b"{}", {}, REQ
        )
        assert result.duration_ms >= 0
