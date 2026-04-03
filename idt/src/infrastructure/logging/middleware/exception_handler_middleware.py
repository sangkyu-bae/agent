"""Exception Handler Middleware.

전역 예외 처리 및 로깅을 담당하는 미들웨어입니다.
"""

import traceback
import uuid
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from src.domain.logging.interfaces import LoggerInterface
from src.domain.logging.schemas import ErrorDetail, ErrorResponse


class ExceptionHandlerMiddleware(BaseHTTPMiddleware):
    """전역 예외 처리 미들웨어.

    모든 처리되지 않은 예외를 잡아 로깅하고 적절한 에러 응답을 반환합니다.
    """

    def __init__(self, app, logger: LoggerInterface, debug: bool = False):
        """미들웨어 초기화.

        Args:
            app: FastAPI 앱
            logger: 로거 인스턴스
            debug: 디버그 모드 (True면 응답에 스택 트레이스 포함)
        """
        super().__init__(app)
        self._logger = logger
        self._debug = debug

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """요청 처리 및 예외 핸들링.

        Args:
            request: HTTP 요청
            call_next: 다음 미들웨어/핸들러 호출 함수

        Returns:
            HTTP 응답
        """
        try:
            response = await call_next(request)
            return response
        except Exception as exc:
            return await self._handle_exception(request, exc)

    async def _handle_exception(
        self, request: Request, exc: Exception
    ) -> JSONResponse:
        """예외 처리 및 에러 응답 생성.

        Args:
            request: HTTP 요청
            exc: 발생한 예외

        Returns:
            에러 JSON 응답
        """
        # request_id 가져오기 (RequestLoggingMiddleware에서 설정)
        request_id = getattr(request.state, "request_id", str(uuid.uuid4()))

        # 스택 트레이스 생성
        stacktrace = "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)
        )

        # 에러 로깅 (스택 트레이스 포함)
        self._logger.error(
            "Unhandled exception",
            exception=exc,
            request_id=request_id,
            endpoint=request.url.path,
            method=request.method,
        )

        # 에러 응답 생성
        error_detail = ErrorDetail(
            type=type(exc).__name__,
            message=str(exc),
            stacktrace=stacktrace if self._debug else None,
        )

        error_response = ErrorResponse(
            request_id=request_id,
            error=error_detail,
        )

        return JSONResponse(
            status_code=500,
            content=error_response.model_dump(exclude_none=not self._debug),
            headers={"X-Request-ID": request_id},
        )
