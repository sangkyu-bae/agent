"""Request Logging Middleware.

모든 API 요청/응답을 로깅하는 미들웨어입니다.
"""

import json
import time
import uuid
from typing import Any, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from src.domain.logging.interfaces import LoggerInterface


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """요청/응답 로깅 미들웨어.

    모든 HTTP 요청과 응답을 구조화된 형식으로 로깅합니다.
    """

    # 마스킹할 민감한 필드 목록
    SENSITIVE_FIELDS = {"password", "token", "api_key", "secret", "authorization"}

    def __init__(self, app, logger: LoggerInterface):
        """미들웨어 초기화.

        Args:
            app: FastAPI 앱
            logger: 로거 인스턴스
        """
        super().__init__(app)
        self._logger = logger

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """요청 처리 및 로깅.

        Args:
            request: HTTP 요청
            call_next: 다음 미들웨어/핸들러 호출 함수

        Returns:
            HTTP 응답
        """
        # request_id 생성
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        # 시작 시간 기록
        start_time = time.perf_counter()

        # 요청 로깅
        await self._log_request(request, request_id)

        # 다음 핸들러 호출
        response = await call_next(request)

        # 처리 시간 계산
        process_time_ms = (time.perf_counter() - start_time) * 1000

        # 응답 로깅
        self._log_response(request_id, response.status_code, process_time_ms)

        # X-Request-ID 헤더 추가
        response.headers["X-Request-ID"] = request_id

        return response

    async def _log_request(self, request: Request, request_id: str) -> None:
        """요청 정보 로깅.

        Args:
            request: HTTP 요청
            request_id: 요청 추적 ID
        """
        # 쿼리 파라미터 추출
        query_params = dict(request.query_params)

        # 요청 바디 추출 (POST/PUT/PATCH)
        body = None
        if request.method in ("POST", "PUT", "PATCH"):
            try:
                body_bytes = await request.body()
                if body_bytes:
                    body = json.loads(body_bytes)
                    body = self._mask_sensitive_data(body)
            except (json.JSONDecodeError, Exception):
                pass

        log_data = {
            "request_id": request_id,
            "method": request.method,
            "endpoint": request.url.path,
            "query_params": query_params,
        }

        if body:
            log_data["body"] = body

        self._logger.info("Request received", **log_data)

    def _log_response(
        self, request_id: str, status_code: int, process_time_ms: float
    ) -> None:
        """응답 정보 로깅.

        Args:
            request_id: 요청 추적 ID
            status_code: HTTP 상태 코드
            process_time_ms: 처리 시간 (밀리초)
        """
        self._logger.info(
            "Response sent",
            request_id=request_id,
            status_code=status_code,
            process_time_ms=round(process_time_ms, 2),
        )

    def _mask_sensitive_data(self, data: dict[str, Any]) -> dict[str, Any]:
        """민감한 데이터 마스킹.

        Args:
            data: 원본 데이터

        Returns:
            마스킹된 데이터
        """
        if not isinstance(data, dict):
            return data

        masked = {}
        for key, value in data.items():
            if key.lower() in self.SENSITIVE_FIELDS:
                masked[key] = "***MASKED***"
            elif isinstance(value, dict):
                masked[key] = self._mask_sensitive_data(value)
            else:
                masked[key] = value
        return masked
