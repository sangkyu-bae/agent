## ✅ Completed

### LOG-001: 로깅 & 에러 추적 모듈

- **상태**: 완료
- **목적**: API 요청/응답 로깅, 에러 스택 트레이스, 구조화된 로그 시스템
- **기술 스택**: Python logging, FastAPI Middleware
- **의존성**: 없음 (모든 모듈에서 참조)

---

#### 📦 1. 로깅 추상화 (Domain Layer)

##### 1-1. LoggerInterface ✅
- **파일**: `src/domain/logging/interfaces/logger_interface.py`
- **메서드**:
  - [x] debug(message: str, **context) → None
  - [x] info(message: str, **context) → None
  - [x] warning(message: str, **context) → None
  - [x] error(message: str, exception: Optional[Exception], **context) → None
  - [x] critical(message: str, exception: Optional[Exception], **context) → None

```python
from abc import ABC, abstractmethod
from typing import Any, Optional


class LoggerInterface(ABC):
    """Logger interface for dependency injection."""

    @abstractmethod
    def debug(self, message: str, **kwargs: Any) -> None:
        """Log debug message."""
        pass

    @abstractmethod
    def info(self, message: str, **kwargs: Any) -> None:
        """Log info message."""
        pass

    @abstractmethod
    def warning(self, message: str, **kwargs: Any) -> None:
        """Log warning message."""
        pass

    @abstractmethod
    def error(
        self, message: str, exception: Optional[Exception] = None, **kwargs: Any
    ) -> None:
        """Log error message with optional exception."""
        pass

    @abstractmethod
    def critical(
        self, message: str, exception: Optional[Exception] = None, **kwargs: Any
    ) -> None:
        """Log critical message with optional exception."""
        pass
```

##### 1-2. LogContext Value Object ✅
- **파일**: `src/domain/logging/value_objects/log_context.py`
- **특징**: frozen=True로 불변성 보장, to_dict()에서 None 값 제외

```python
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
import uuid


@dataclass(frozen=True)
class LogContext:
    """Value object for logging context."""

    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    endpoint: Optional[str] = None
    method: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, excluding None values."""
        result: Dict[str, Any] = {"request_id": self.request_id}

        if self.user_id is not None:
            result["user_id"] = self.user_id
        if self.session_id is not None:
            result["session_id"] = self.session_id
        if self.endpoint is not None:
            result["endpoint"] = self.endpoint
        if self.method is not None:
            result["method"] = self.method

        result.update(self.extra)
        return result
```

##### 1-3. ErrorSchema ✅
- **파일**: `src/domain/logging/schemas/error_schema.py`

```python
from typing import Any, Dict, Optional
from pydantic import BaseModel


class ErrorDetail(BaseModel):
    """Error detail schema."""

    type: str
    message: str
    stacktrace: Optional[str] = None


class ErrorResponse(BaseModel):
    """Error response schema."""

    request_id: str
    error: ErrorDetail

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, excluding None stacktrace."""
        result: Dict[str, Any] = {
            "request_id": self.request_id,
            "error": {
                "type": self.error.type,
                "message": self.error.message,
            },
        }
        if self.error.stacktrace is not None:
            result["error"]["stacktrace"] = self.error.stacktrace
        return result
```

---

#### 🔧 2. 로거 구현체 (Infrastructure Layer)

##### 2-1. StructuredFormatter ✅
- **파일**: `src/infrastructure/logging/formatters/structured_formatter.py`
- **특징**:
  - JSON 메타데이터 + 스택트레이스 분리 출력 (가독성 향상)
  - location 필드 포함 (file:function:line)

```python
import json
import logging
import traceback
from datetime import datetime, timezone
from typing import Any


class StructuredFormatter(logging.Formatter):
    """Structured JSON log formatter with readable stacktrace."""

    _RESERVED_ATTRS = {
        "name", "msg", "args", "created", "filename", "funcName",
        "levelname", "levelno", "lineno", "module", "msecs",
        "pathname", "process", "processName", "relativeCreated",
        "stack_info", "exc_info", "exc_text", "thread", "threadName",
        "taskName", "message",
    }

    def format(self, record: logging.LogRecord) -> str:
        log_dict = self._build_log_dict(record)

        # Add extra fields from record
        for key, value in record.__dict__.items():
            if key not in self._RESERVED_ATTRS and not key.startswith("_"):
                log_dict[key] = value

        log_line = json.dumps(log_dict, ensure_ascii=False, default=str)

        # Stacktrace on separate lines for readability
        if record.exc_info:
            stacktrace = "".join(traceback.format_exception(*record.exc_info))
            return f"{log_line}\n{stacktrace}"

        return log_line

    def _build_log_dict(self, record: logging.LogRecord) -> dict[str, Any]:
        log_dict = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "location": f"{record.filename}:{record.funcName}:{record.lineno}",
        }

        if record.exc_info and record.exc_info[1]:
            exc_type, exc_value, _ = record.exc_info
            log_dict["error_type"] = exc_type.__name__ if exc_type else "Unknown"
            log_dict["error_message"] = str(exc_value) if exc_value else ""

        return log_dict
```

##### 2-2. StructuredLogger + get_logger() ✅
- **파일**: `src/infrastructure/logging/structured_logger.py`
- **특징**:
  - 의존성 주입 없이 `get_logger(__name__)` 패턴 사용
  - 싱글톤 캐싱으로 동일 이름 로거 재사용

```python
import logging
from typing import Any, Optional

from src.domain.logging.interfaces import LoggerInterface
from src.infrastructure.logging.formatters import StructuredFormatter


class StructuredLogger(LoggerInterface):
    """Structured JSON logger implementation."""

    def __init__(self, name: str = "app", level: int = logging.INFO):
        self._logger = logging.getLogger(name)
        self._logger.setLevel(level)
        self._logger.propagate = False

        if not self._logger.handlers:
            handler = logging.StreamHandler()
            handler.setLevel(level)
            handler.setFormatter(StructuredFormatter())
            self._logger.addHandler(handler)

    def debug(self, message: str, **kwargs: Any) -> None:
        self._logger.debug(message, extra=kwargs)

    def info(self, message: str, **kwargs: Any) -> None:
        self._logger.info(message, extra=kwargs)

    def warning(self, message: str, **kwargs: Any) -> None:
        self._logger.warning(message, extra=kwargs)

    def error(
        self, message: str, exception: Optional[Exception] = None, **kwargs: Any
    ) -> None:
        self._logger.error(message, exc_info=exception, extra=kwargs)

    def critical(
        self, message: str, exception: Optional[Exception] = None, **kwargs: Any
    ) -> None:
        self._logger.critical(message, exc_info=exception, extra=kwargs)


# Logger cache for singleton pattern
_loggers: dict[str, StructuredLogger] = {}


def get_logger(name: str = "app") -> StructuredLogger:
    """Get or create a StructuredLogger instance."""
    if name not in _loggers:
        _loggers[name] = StructuredLogger(name=name)
    return _loggers[name]
```

---

#### 🌐 3. FastAPI 미들웨어 (Infrastructure Layer)

##### 3-1. RequestLoggingMiddleware ✅
- **파일**: `src/infrastructure/logging/middleware/request_logging_middleware.py`
- **기능**:
  - [x] request_id 자동 생성 및 request.state 저장
  - [x] 요청 로그: method, endpoint, query_params
  - [x] 응답 로그: status_code, process_time_ms
  - [x] X-Request-ID 헤더 추가
  - [x] 민감 정보 마스킹 (password, token, api_key, secret)

```python
import time
import uuid
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from src.infrastructure.logging import get_logger

logger = get_logger("api.request")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for logging HTTP requests and responses."""

    SENSITIVE_KEYS = {"password", "token", "api_key", "secret"}

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        start_time = time.time()
        method = request.method
        endpoint = str(request.url.path)
        query_params = dict(request.query_params)

        logger.info(
            "Request received",
            request_id=request_id,
            method=method,
            endpoint=endpoint,
            query_params=self._mask_sensitive(query_params),
        )

        response = await call_next(request)

        process_time_ms = int((time.time() - start_time) * 1000)

        logger.info(
            "Response sent",
            request_id=request_id,
            method=method,
            endpoint=endpoint,
            status_code=response.status_code,
            process_time_ms=process_time_ms,
        )

        response.headers["X-Request-ID"] = request_id
        return response

    def _mask_sensitive(self, data: dict) -> dict:
        """Mask sensitive information in data."""
        if not data:
            return data

        masked = data.copy()
        for key in self.SENSITIVE_KEYS:
            if key in masked:
                masked[key] = "***MASKED***"
        return masked
```

##### 3-2. ExceptionHandlerMiddleware ✅
- **파일**: `src/infrastructure/logging/middleware/exception_handler_middleware.py`
- **기능**:
  - [x] 예외 발생 시 에러 로깅 (스택트레이스 포함)
  - [x] JSONResponse 500 반환
  - [x] DEBUG=true 시 응답에 스택트레이스 포함
  - [x] DEBUG=false 시 응답에 스택트레이스 미포함

```python
import os
import traceback

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from src.infrastructure.logging import get_logger

logger = get_logger("api.exception")


class ExceptionHandlerMiddleware(BaseHTTPMiddleware):
    """Middleware for handling unhandled exceptions."""

    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except Exception as e:
            request_id = getattr(request.state, "request_id", "unknown")

            logger.error(
                "Unhandled exception",
                exception=e,
                request_id=request_id,
                endpoint=str(request.url.path),
                method=request.method,
            )

            error_response = {
                "request_id": request_id,
                "error": {
                    "type": type(e).__name__,
                    "message": str(e),
                },
            }

            if self._is_debug():
                error_response["error"]["stacktrace"] = traceback.format_exc()

            return JSONResponse(
                status_code=500,
                content=error_response,
                headers={"X-Request-ID": request_id},
            )

    def _is_debug(self) -> bool:
        return os.getenv("DEBUG", "false").lower() == "true"
```

---

#### 🔗 4. FastAPI 설정

##### 4-1. 미들웨어 등록 ✅
- **파일**: `src/api/main.py`

```python
from fastapi import FastAPI

from src.infrastructure.logging.middleware.exception_handler_middleware import (
    ExceptionHandlerMiddleware,
)
from src.infrastructure.logging.middleware.request_logging_middleware import (
    RequestLoggingMiddleware,
)

app = FastAPI(title="IDT API", version="0.1.0")

# 미들웨어 등록 (순서 중요: 아래에서 위로 실행)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(ExceptionHandlerMiddleware)
```

##### 4-2. 모듈에서 로깅 사용 ✅
- **패턴**: 에러 발생 시에만 로깅 (메서드 시작/종료 로그 불필요)

```python
from src.infrastructure.logging import get_logger

logger = get_logger(__name__)


class SomeService:
    def process(self, data: dict):
        try:
            result = self._do_work(data)
            return result
        except Exception as e:
            logger.error(
                "Processing failed",
                exception=e,
                data_keys=list(data.keys()),
            )
            raise
```

---

#### 📄 5. 로그 출력 형식

##### 5-1. 일반 로그 (JSON 한 줄)
```json
{"timestamp": "2025-01-30T10:30:00.000000+00:00", "level": "INFO", "logger": "api.request", "message": "Request received", "location": "request_logging_middleware.py:dispatch:25", "request_id": "550e8400-e29b-41d4-a716-446655440000", "method": "POST", "endpoint": "/api/v1/documents/upload", "query_params": {"user_id": "user_123"}}
```

##### 5-2. 에러 로그 (JSON + 스택트레이스 분리)
```
{"timestamp": "2025-01-30T10:30:01.500000+00:00", "level": "ERROR", "logger": "src.infrastructure.parser.pymupdf_parser", "message": "PDF parsing failed", "location": "pymupdf_parser.py:parse:85", "error_type": "ValueError", "error_message": "Invalid PDF format", "file_name": "document.pdf"}
Traceback (most recent call last):
  File "src/infrastructure/parser/pymupdf_parser.py", line 80, in parse
    doc = fitz.open(stream=file_bytes, filetype="pdf")
  File "...", line xxx, in open
    ...
ValueError: Invalid PDF format
```

---

#### 📁 폴더 구조

```
src/
├── domain/
│   └── logging/
│       ├── __init__.py
│       ├── interfaces/
│       │   ├── __init__.py
│       │   └── logger_interface.py
│       ├── value_objects/
│       │   ├── __init__.py
│       │   └── log_context.py
│       └── schemas/
│           ├── __init__.py
│           └── error_schema.py
│
└── infrastructure/
    └── logging/
        ├── __init__.py              # exports: StructuredLogger, get_logger
        ├── structured_logger.py
        ├── formatters/
        │   ├── __init__.py
        │   └── structured_formatter.py
        └── middleware/
            ├── __init__.py
            ├── request_logging_middleware.py
            └── exception_handler_middleware.py

tests/
├── domain/
│   └── logging/
│       ├── __init__.py
│       ├── test_logger_interface.py
│       ├── test_log_context.py
│       └── test_error_schema.py
│
└── infrastructure/
    └── logging/
        ├── __init__.py
        ├── test_structured_formatter.py
        ├── test_structured_logger.py
        ├── test_request_logging_middleware.py
        └── test_exception_handler_middleware.py
```

---

#### ✅ 완료 조건

- [x] StructuredLogger JSON 포맷 로깅 테스트
- [x] 에러 발생 시 스택 트레이스 출력 테스트
- [x] RequestLoggingMiddleware 요청/응답 로깅 테스트
- [x] ExceptionHandlerMiddleware 전역 에러 처리 테스트
- [x] request_id 추적 (요청 → 에러 → 응답) 테스트
- [x] 민감 정보 마스킹 테스트 (password, token 등)
- [x] DEBUG 모드 스택 트레이스 노출 제어 테스트
- [x] 기존 모듈에 에러 로깅 적용 (parser, embedding, vectorstore, compressor)

---

#### 🧪 테스트 결과

```bash
# 로깅 모듈 테스트
pytest tests/domain/logging/ tests/infrastructure/logging/ -v
# 71 passed

# 전체 테스트
pytest
# 927 passed
```

---

#### 📝 설계 결정 사항

1. **의존성 주입 대신 `get_logger(__name__)` 사용**
   - 로거까지 DI하면 코드가 복잡해짐
   - 모듈 레벨에서 바로 로거 생성하여 사용

2. **메서드 시작/종료 로그 제거**
   - API 엔드포인트는 미들웨어에서 자동 로깅
   - 모듈 내부는 에러 발생 시에만 로깅

3. **스택트레이스 가독성 개선**
   - JSON 메타데이터는 첫 줄에 출력
   - 스택트레이스는 별도 줄에 원본 형태로 출력

4. **location 필드 추가**
   - `filename:function:lineno` 형식으로 에러 위치 추적 용이

---

#### 🔒 금지 사항

- ❌ print() 사용 금지 (logger 사용)
- ❌ 스택 트레이스 없는 에러 로그 금지
- ❌ 민감 정보 평문 로깅 금지 (password, token, api_key 마스킹)
- ❌ API 컨텍스트에서 request_id 없는 로그 금지
