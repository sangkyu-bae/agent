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
    응답 바디(JSON)를 캡처하여 로그에 포함합니다.
    """

    # 마스킹할 민감한 필드 목록
    SENSITIVE_FIELDS = {"password", "token", "api_key", "secret", "authorization"}

    # 응답 바디 로깅 크기 제한 (4KB) — 이 이상은 잘라서 로깅
    _MAX_RESPONSE_BODY_BYTES = 4096

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

        # JSON 응답 바디 캡처 (클라이언트에 전달할 Response 재구성 포함)
        response_body, response = await self._capture_response_body(response)

        # 응답 로깅
        self._log_response(
            request_id,
            response.status_code,
            process_time_ms,
            method=request.method,
            endpoint=str(request.url.path),
            response_body=response_body,
        )

        # X-Request-ID 헤더 추가
        response.headers["X-Request-ID"] = request_id

        return response

    async def _capture_response_body(
        self, response: Response
    ) -> tuple[Any, Response]:
        """JSON 응답 바디를 캡처하고 재구성된 Response를 반환한다.

        바디를 읽으면 소비되므로, 동일한 내용으로 Response를 재구성하여 반환한다.
        JSON이 아니거나 크기 초과 시 body는 None.

        Args:
            response: 원본 Response

        Returns:
            (parsed_body_or_None, reconstructed_response)
        """
        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type:
            return None, response

        # 바디 읽기 (크기 제한 적용)
        raw = b""
        truncated = False
        async for chunk in response.body_iterator:
            raw += chunk
            if len(raw) > self._MAX_RESPONSE_BODY_BYTES:
                truncated = True
                break

        # content-length는 재계산되므로 제외하고 헤더 복사
        headers = {
            k: v
            for k, v in response.headers.items()
            if k.lower() != "content-length"
        }

        from starlette.responses import Response as StarletteResponse

        rebuilt = StarletteResponse(
            content=raw,
            status_code=response.status_code,
            headers=headers,
            media_type=response.media_type,
        )

        if truncated:
            return {"_truncated": True, "_raw_prefix": raw[:200].decode("utf-8", errors="replace")}, rebuilt

        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = raw.decode("utf-8", errors="replace")

        return parsed, rebuilt

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
        self,
        request_id: str,
        status_code: int,
        process_time_ms: float,
        method: str = "",
        endpoint: str = "",
        response_body: Any = None,
    ) -> None:
        """응답 정보 로깅.

        - 모든 응답: INFO 레벨 (response_body 포함)
        - 4xx/5xx 응답: WARNING 레벨 추가 (에러 원인 즉시 확인 용도)

        Args:
            request_id: 요청 추적 ID
            status_code: HTTP 상태 코드
            process_time_ms: 처리 시간 (밀리초)
            method: HTTP 메서드
            endpoint: 요청 경로
            response_body: 파싱된 응답 바디 (JSON) 또는 None
        """
        info_data: dict[str, Any] = {
            "request_id": request_id,
            "status_code": status_code,
            "process_time_ms": round(process_time_ms, 2),
        }
        if response_body is not None:
            info_data["response_body"] = response_body

        self._logger.info("Response sent", **info_data)

        if status_code >= 400:
            warning_data: dict[str, Any] = {
                "request_id": request_id,
                "status_code": status_code,
                "method": method,
                "endpoint": endpoint,
            }
            if response_body is not None:
                warning_data["response_body"] = response_body

            self._logger.warning("HTTP error response", **warning_data)

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
