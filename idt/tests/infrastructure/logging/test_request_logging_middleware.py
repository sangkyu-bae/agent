"""Tests for RequestLoggingMiddleware."""

import json
import logging
import pytest
from io import StringIO
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from src.infrastructure.logging.middleware import RequestLoggingMiddleware
from src.infrastructure.logging import StructuredLogger
from src.infrastructure.logging.formatters import StructuredFormatter


class TestRequestLoggingMiddleware:
    """RequestLoggingMiddleware 테스트."""

    @pytest.fixture
    def log_stream(self):
        """로그 출력 캡처 fixture."""
        return StringIO()

    @pytest.fixture
    def logger(self, log_stream):
        """테스트용 로거 fixture."""
        logger = StructuredLogger(name="test_request_middleware", level=logging.DEBUG)
        logger._logger.handlers.clear()
        handler = logging.StreamHandler(log_stream)
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(StructuredFormatter())
        logger._logger.addHandler(handler)
        return logger

    @pytest.fixture
    def app(self, logger):
        """테스트용 FastAPI 앱 fixture."""
        app = FastAPI()
        app.add_middleware(RequestLoggingMiddleware, logger=logger)

        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}

        @app.post("/submit")
        async def submit_endpoint():
            return {"submitted": True}

        return app

    @pytest.fixture
    def client(self, app):
        """테스트 클라이언트 fixture."""
        return TestClient(app)

    def test_request_id_is_generated(self, client, log_stream):
        """request_id가 생성된다."""
        response = client.get("/test")
        assert response.status_code == 200

        logs = log_stream.getvalue().strip().split("\n")
        assert len(logs) >= 1
        parsed = json.loads(logs[0])
        assert "request_id" in parsed

    def test_request_id_in_response_header(self, client):
        """응답 헤더에 X-Request-ID가 포함된다."""
        response = client.get("/test")
        assert "X-Request-ID" in response.headers

    def test_request_log_includes_method(self, client, log_stream):
        """요청 로그에 method가 포함된다."""
        client.get("/test")
        logs = log_stream.getvalue().strip().split("\n")
        parsed = json.loads(logs[0])
        assert parsed["method"] == "GET"

    def test_request_log_includes_endpoint(self, client, log_stream):
        """요청 로그에 endpoint가 포함된다."""
        client.get("/test")
        logs = log_stream.getvalue().strip().split("\n")
        parsed = json.loads(logs[0])
        assert parsed["endpoint"] == "/test"

    def test_request_log_includes_query_params(self, client, log_stream):
        """요청 로그에 query_params가 포함된다."""
        client.get("/test?foo=bar&baz=123")
        logs = log_stream.getvalue().strip().split("\n")
        parsed = json.loads(logs[0])
        assert "query_params" in parsed
        assert parsed["query_params"]["foo"] == "bar"
        assert parsed["query_params"]["baz"] == "123"

    def test_response_log_includes_status_code(self, client, log_stream):
        """응답 로그에 status_code가 포함된다."""
        client.get("/test")
        logs = log_stream.getvalue().strip().split("\n")
        # 응답 로그 찾기 (두 번째 로그)
        response_log = None
        for log in logs:
            parsed = json.loads(log)
            if "status_code" in parsed:
                response_log = parsed
                break
        assert response_log is not None
        assert response_log["status_code"] == 200

    def test_response_log_includes_process_time_ms(self, client, log_stream):
        """응답 로그에 process_time_ms가 포함된다."""
        client.get("/test")
        logs = log_stream.getvalue().strip().split("\n")
        response_log = None
        for log in logs:
            parsed = json.loads(log)
            if "process_time_ms" in parsed:
                response_log = parsed
                break
        assert response_log is not None
        assert "process_time_ms" in response_log
        assert isinstance(response_log["process_time_ms"], (int, float))

    def test_sensitive_data_is_masked_password(self, log_stream, logger):
        """password 필드가 마스킹된다."""
        app = FastAPI()
        app.add_middleware(RequestLoggingMiddleware, logger=logger)

        @app.post("/login")
        async def login(request: Request):
            return {"status": "ok"}

        client = TestClient(app)
        client.post(
            "/login",
            json={"username": "test", "password": "secret123"},
        )

        logs = log_stream.getvalue()
        assert "secret123" not in logs
        assert "***MASKED***" in logs or "password" not in logs.lower()

    def test_sensitive_data_is_masked_token(self, log_stream, logger):
        """token 필드가 마스킹된다."""
        app = FastAPI()
        app.add_middleware(RequestLoggingMiddleware, logger=logger)

        @app.post("/auth")
        async def auth(request: Request):
            return {"status": "ok"}

        client = TestClient(app)
        client.post(
            "/auth",
            json={"token": "abc123secret"},
        )

        logs = log_stream.getvalue()
        assert "abc123secret" not in logs

    def test_sensitive_data_is_masked_api_key(self, log_stream, logger):
        """api_key 필드가 마스킹된다."""
        app = FastAPI()
        app.add_middleware(RequestLoggingMiddleware, logger=logger)

        @app.post("/config")
        async def config(request: Request):
            return {"status": "ok"}

        client = TestClient(app)
        client.post(
            "/config",
            json={"api_key": "sk-secret-key-123"},
        )

        logs = log_stream.getvalue()
        assert "sk-secret-key-123" not in logs

    def test_post_method_is_logged(self, client, log_stream):
        """POST 메서드가 올바르게 로깅된다."""
        client.post("/submit")
        logs = log_stream.getvalue().strip().split("\n")
        parsed = json.loads(logs[0])
        assert parsed["method"] == "POST"

    def test_request_id_same_for_request_and_response(self, client, log_stream):
        """요청과 응답의 request_id가 동일하다."""
        client.get("/test")
        logs = log_stream.getvalue().strip().split("\n")
        request_ids = set()
        for log in logs:
            parsed = json.loads(log)
            if "request_id" in parsed:
                request_ids.add(parsed["request_id"])
        # 모든 로그의 request_id가 같아야 함
        assert len(request_ids) == 1


class TestRequestLoggingMiddlewareHttpErrorWarning:
    """4xx/5xx 응답에 대한 WARNING 로그 테스트."""

    @pytest.fixture
    def log_stream(self):
        return StringIO()

    @pytest.fixture
    def logger(self, log_stream):
        logger = StructuredLogger(name="test_http_error_warning", level=logging.DEBUG)
        logger._logger.handlers.clear()
        handler = logging.StreamHandler(log_stream)
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(StructuredFormatter())
        logger._logger.addHandler(handler)
        return logger

    def _make_app(self, logger, status_code: int):
        from fastapi import HTTPException as FastAPIHTTPException
        app = FastAPI()
        app.add_middleware(RequestLoggingMiddleware, logger=logger)

        @app.get("/error")
        async def error_endpoint():
            raise FastAPIHTTPException(status_code=status_code, detail="test error")

        return app

    def _get_warning_log(self, log_stream) -> dict | None:
        logs = log_stream.getvalue().strip().split("\n")
        for log in logs:
            if not log:
                continue
            parsed = json.loads(log)
            if parsed.get("level") == "WARNING":
                return parsed
        return None

    def test_401_response_logs_warning(self, logger, log_stream):
        """401 응답 시 WARNING 레벨 로그가 찍힌다."""
        app = self._make_app(logger, 401)
        client = TestClient(app, raise_server_exceptions=False)
        client.get("/error")
        warning = self._get_warning_log(log_stream)
        assert warning is not None

    def test_403_response_logs_warning(self, logger, log_stream):
        """403 응답 시 WARNING 레벨 로그가 찍힌다."""
        app = self._make_app(logger, 403)
        client = TestClient(app, raise_server_exceptions=False)
        client.get("/error")
        warning = self._get_warning_log(log_stream)
        assert warning is not None

    def test_404_response_logs_warning(self, logger, log_stream):
        """404 응답 시 WARNING 레벨 로그가 찍힌다."""
        app = self._make_app(logger, 404)
        client = TestClient(app, raise_server_exceptions=False)
        client.get("/error")
        warning = self._get_warning_log(log_stream)
        assert warning is not None

    def test_500_response_logs_warning(self, logger, log_stream):
        """500 응답 시 WARNING 레벨 로그가 찍힌다."""
        app = self._make_app(logger, 500)
        client = TestClient(app, raise_server_exceptions=False)
        client.get("/error")
        warning = self._get_warning_log(log_stream)
        assert warning is not None

    def test_warning_includes_status_code(self, logger, log_stream):
        """WARNING 로그에 status_code가 포함된다."""
        app = self._make_app(logger, 401)
        client = TestClient(app, raise_server_exceptions=False)
        client.get("/error")
        warning = self._get_warning_log(log_stream)
        assert warning is not None
        assert warning["status_code"] == 401

    def test_warning_includes_request_id(self, logger, log_stream):
        """WARNING 로그에 request_id가 포함된다."""
        app = self._make_app(logger, 401)
        client = TestClient(app, raise_server_exceptions=False)
        client.get("/error")
        warning = self._get_warning_log(log_stream)
        assert warning is not None
        assert "request_id" in warning

    def test_warning_includes_method_and_endpoint(self, logger, log_stream):
        """WARNING 로그에 method와 endpoint가 포함된다."""
        app = self._make_app(logger, 404)
        client = TestClient(app, raise_server_exceptions=False)
        client.get("/error")
        warning = self._get_warning_log(log_stream)
        assert warning is not None
        assert warning["method"] == "GET"
        assert warning["endpoint"] == "/error"

    def test_200_response_no_warning(self, logger, log_stream):
        """200 정상 응답 시 WARNING 로그가 찍히지 않는다."""
        app = FastAPI()
        app.add_middleware(RequestLoggingMiddleware, logger=logger)

        @app.get("/ok")
        async def ok():
            return {"status": "ok"}

        client = TestClient(app)
        client.get("/ok")
        warning = self._get_warning_log(log_stream)
        assert warning is None

    def test_warning_includes_response_body(self, logger, log_stream):
        """4xx WARNING 로그에 응답 바디(detail)가 포함된다."""
        from fastapi import HTTPException as FastAPIHTTPException
        app = FastAPI()
        app.add_middleware(RequestLoggingMiddleware, logger=logger)

        @app.get("/auth")
        async def auth_endpoint():
            raise FastAPIHTTPException(status_code=401, detail="Invalid credentials")

        client = TestClient(app, raise_server_exceptions=False)
        client.get("/auth")
        warning = self._get_warning_log(log_stream)
        assert warning is not None
        assert "response_body" in warning
        # detail 메시지가 response_body에 포함되어야 함
        body = warning["response_body"]
        assert "Invalid credentials" in str(body)


class TestRequestLoggingMiddlewareResponseBody:
    """응답 바디 로깅 테스트."""

    @pytest.fixture
    def log_stream(self):
        return StringIO()

    @pytest.fixture
    def logger(self, log_stream):
        logger = StructuredLogger(name="test_response_body", level=logging.DEBUG)
        logger._logger.handlers.clear()
        handler = logging.StreamHandler(log_stream)
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(StructuredFormatter())
        logger._logger.addHandler(handler)
        return logger

    def _get_response_log(self, log_stream) -> dict | None:
        """'Response sent' 로그 반환."""
        logs = log_stream.getvalue().strip().split("\n")
        for log in logs:
            if not log:
                continue
            parsed = json.loads(log)
            if parsed.get("message") == "Response sent":
                return parsed
        return None

    def test_json_response_body_logged_in_response_sent(self, logger, log_stream):
        """JSON 응답 바디가 'Response sent' 로그에 포함된다."""
        app = FastAPI()
        app.add_middleware(RequestLoggingMiddleware, logger=logger)

        @app.get("/data")
        async def data():
            return {"user_id": 1, "email": "test@example.com"}

        client = TestClient(app)
        client.get("/data")
        log = self._get_response_log(log_stream)
        assert log is not None
        assert "response_body" in log
        assert log["response_body"]["user_id"] == 1

    def test_non_json_response_body_not_logged(self, logger, log_stream):
        """non-JSON 응답(plain text 등)은 response_body가 로그에 없다."""
        from starlette.responses import PlainTextResponse
        app = FastAPI()
        app.add_middleware(RequestLoggingMiddleware, logger=logger)

        @app.get("/text")
        async def text():
            return PlainTextResponse("hello world")

        client = TestClient(app)
        client.get("/text")
        log = self._get_response_log(log_stream)
        assert log is not None
        assert "response_body" not in log

    def test_response_body_still_received_by_client(self, logger, log_stream):
        """바디를 미들웨어에서 읽어도 클라이언트는 정상적으로 응답을 받는다."""
        app = FastAPI()
        app.add_middleware(RequestLoggingMiddleware, logger=logger)

        @app.get("/check")
        async def check():
            return {"ok": True}

        client = TestClient(app)
        response = client.get("/check")
        assert response.status_code == 200
        assert response.json() == {"ok": True}

    def test_large_response_body_truncated(self, logger, log_stream):
        """응답 바디가 크면 잘려서 로깅된다 (클라이언트는 전체 수신)."""
        app = FastAPI()
        app.add_middleware(RequestLoggingMiddleware, logger=logger)

        big_data = {"items": ["x" * 100] * 200}  # ~20KB

        @app.get("/big")
        async def big():
            return big_data

        client = TestClient(app)
        response = client.get("/big")
        assert response.status_code == 200
        # 클라이언트는 전체 수신
        assert len(response.json()["items"]) == 200

        log = self._get_response_log(log_stream)
        assert log is not None
        # 로그 바디는 잘렸거나 없을 수 있음 (크기 제한)
        if "response_body" in log:
            body_str = str(log["response_body"])
            assert len(body_str) <= 5000  # 로그에는 제한된 크기만
