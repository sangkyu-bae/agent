"""Error Schema for structured error responses.

에러 응답에 사용되는 Pydantic 스키마입니다.
"""

from pydantic import BaseModel


class ErrorDetail(BaseModel):
    """에러 상세 정보.

    Attributes:
        type: 예외 타입 (예: ValueError, TypeError)
        message: 에러 메시지
        stacktrace: 스택 트레이스 (DEBUG 모드에서만 포함)
    """

    type: str
    message: str
    stacktrace: str | None = None


class ErrorResponse(BaseModel):
    """에러 응답 스키마.

    API 에러 응답에 사용됩니다.

    Attributes:
        request_id: 요청 추적 ID
        error: 에러 상세 정보
    """

    request_id: str
    error: ErrorDetail
