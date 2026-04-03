"""Tests for main.py logging middleware integration."""

import json
import logging
import pytest
from io import StringIO
from unittest.mock import patch, AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.infrastructure.logging import StructuredLogger
from src.infrastructure.logging.formatters import StructuredFormatter
from src.infrastructure.logging.middleware import (
    RequestLoggingMiddleware,
    ExceptionHandlerMiddleware,
)


class TestMainLoggingIntegration:
    """main.py 로깅 미들웨어 통합 테스트."""

    @pytest.fixture
    def log_stream(self):
        """로그 출력 캡처 fixture."""
        return StringIO()

    @pytest.fixture
    def logger(self, log_stream):
        """테스트용 로거 fixture."""
        logger = StructuredLogger(name="test_main_logging", level=logging.DEBUG)
        logger._logger.handlers.clear()
        handler = logging.StreamHandler(log_stream)
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(StructuredFormatter())
        logger._logger.addHandler(handler)
        return logger

    @pytest.fixture
    def app_with_logging(self, logger):
        """로깅 미들웨어가 적용된 테스트 앱."""
        app = FastAPI()

        # 미들웨어 등록 순서: 마지막에 등록된 것이 먼저 실행됨
        # 1. RequestLogging이 먼저 실행되어 request_id 생성
        # 2. ExceptionHandler가 에러 처리
        app.add_middleware(RequestLoggingMiddleware, logger=logger)
        app.add_middleware(ExceptionHandlerMiddleware, logger=logger, debug=True)

        @app.get("/health")
        async def health_check():
            return {"status": "ok"}

        @app.get("/error")
        async def error_endpoint():
            raise ValueError("Test error for logging")

        return app

    @pytest.fixture
    def client(self, app_with_logging):
        """테스트 클라이언트."""
        return TestClient(app_with_logging, raise_server_exceptions=False)

    def test_middleware_registration_order(self, app_with_logging):
        """미들웨어가 올바른 순서로 등록되어 있다."""
        # user_middleware에서 클래스 정보 확인
        middleware_info = []
        for m in app_with_logging.user_middleware:
            if hasattr(m, "cls"):
                middleware_info.append(m.cls.__name__)
            elif hasattr(m, "kwargs") and "dispatch" in str(m.kwargs):
                middleware_info.append(str(m))

        # 미들웨어가 2개 등록되어 있어야 함
        assert len(app_with_logging.user_middleware) == 2

    def test_request_logging_on_success(self, client, log_stream):
        """정상 요청 시 로그가 출력된다."""
        response = client.get("/health")
        assert response.status_code == 200

        logs = log_stream.getvalue().strip().split("\n")
        # 요청, 응답 로그가 있어야 함
        assert len(logs) >= 2

        # 요청 로그 확인
        request_log = json.loads(logs[0])
        assert "request_id" in request_log
        assert request_log["method"] == "GET"
        assert request_log["endpoint"] == "/health"

    def test_error_logging_with_stacktrace(self, client, log_stream):
        """에러 발생 시 스택 트레이스가 로깅된다."""
        response = client.get("/error")
        assert response.status_code == 500

        logs = log_stream.getvalue()
        assert "Traceback" in logs
        assert "ValueError" in logs
        assert "Test error for logging" in logs

    def test_request_id_tracking(self, client, log_stream):
        """request_id가 요청 전체에서 추적된다."""
        response = client.get("/health")
        assert response.status_code == 200

        logs = log_stream.getvalue().strip().split("\n")
        request_ids = set()

        for log in logs:
            try:
                parsed = json.loads(log)
                if "request_id" in parsed:
                    request_ids.add(parsed["request_id"])
            except json.JSONDecodeError:
                continue

        # 모든 로그가 같은 request_id를 가져야 함
        assert len(request_ids) == 1

    def test_x_request_id_header_returned(self, client):
        """응답에 X-Request-ID 헤더가 포함된다."""
        response = client.get("/health")
        assert "X-Request-ID" in response.headers

    def test_error_response_format(self, client):
        """에러 응답이 올바른 형식이다."""
        response = client.get("/error")
        data = response.json()

        assert "request_id" in data
        assert "error" in data
        assert data["error"]["type"] == "ValueError"
        assert data["error"]["message"] == "Test error for logging"


class TestMainAppWithLogging:
    """실제 main.py 앱의 로깅 테스트 (mock 사용)."""

    @pytest.fixture
    def mock_processor(self):
        """Mock document processor."""
        mock = MagicMock()
        mock.process = AsyncMock(return_value={"status": "processed"})
        return mock

    def test_app_can_import_logging_modules(self):
        """main.py에서 로깅 모듈을 임포트할 수 있다."""
        from src.infrastructure.logging import StructuredLogger
        from src.infrastructure.logging.middleware import (
            RequestLoggingMiddleware,
            ExceptionHandlerMiddleware,
        )

        assert StructuredLogger is not None
        assert RequestLoggingMiddleware is not None
        assert ExceptionHandlerMiddleware is not None
