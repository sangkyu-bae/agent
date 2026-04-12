# Design: log-enhance

> Feature: 로그 출력 가독성 개선 + DB 쿼리 로깅
> Created: 2026-04-11
> Status: Design
> Depends-On: log-enhance.plan.md
> Task ID: LOG-002

---

## 1. 레이어별 파일 구조

```
src/
└── infrastructure/
    └── logging/
        ├── __init__.py                          # 수정 — get_formatter() export 추가
        ├── structured_logger.py                 # 수정 — get_formatter() 사용
        ├── formatters/
        │   ├── __init__.py                      # 수정 — PrettyFormatter export 추가
        │   ├── structured_formatter.py          # 유지 (compact 모드, 변경 없음)
        │   └── pretty_formatter.py              # 신규 — 멀티라인 pretty 포매터
        ├── middleware/
        │   ├── __init__.py                      # 유지
        │   ├── request_logging_middleware.py    # 유지
        │   └── exception_handler_middleware.py  # 유지
        └── db_query_listener.py                 # 신규 — SQLAlchemy 쿼리 리스너

    └── persistence/
        └── database.py                          # 수정 — DBQueryListener 등록

tests/
└── infrastructure/
    └── logging/
        ├── test_pretty_formatter.py             # 신규
        ├── test_db_query_listener.py            # 신규
        └── test_get_formatter.py                # 신규
```

---

## 2. LOG-002-A: PrettyFormatter

### `src/infrastructure/logging/formatters/pretty_formatter.py` (신규)

```python
import logging
import os
import traceback
from datetime import datetime, timezone
from typing import Any

from src.infrastructure.logging.formatters.structured_formatter import (
    StructuredFormatter,
)


class PrettyFormatter(logging.Formatter):
    """사람이 읽기 좋은 멀티라인 로그 포매터.

    LOG_FORMAT=pretty 환경변수 설정 시 활성화된다.
    개발/디버깅 환경 전용. 운영 환경에서는 StructuredFormatter(compact) 사용.
    """

    SEPARATOR = "─" * 64

    LEVEL_COLORS = {
        "DEBUG": "\033[36m",   # cyan
        "INFO": "\033[32m",    # green
        "WARNING": "\033[33m", # yellow
        "ERROR": "\033[31m",   # red
        "CRITICAL": "\033[35m",# magenta
    }
    RESET = "\033[0m"

    # StructuredFormatter와 동일한 예약 속성 재사용
    _RESERVED_ATTRS = StructuredFormatter._RESERVED_ATTRS

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(
            record.created, tz=timezone.utc
        ).strftime("%Y-%m-%dT%H:%M:%SZ")

        level = record.levelname
        color = self.LEVEL_COLORS.get(level, "")
        location = f"{record.filename}:{record.funcName}:{record.lineno}"

        # 헤더
        header = (
            f"{color}[{timestamp}] {level:<8}{self.RESET} {record.getMessage()}"
        )

        # extra 필드 (예약 속성 제외)
        fields = {
            k: v
            for k, v in record.__dict__.items()
            if k not in self._RESERVED_ATTRS and not k.startswith("_")
        }
        # location 항상 마지막에 표시
        fields["location"] = location

        field_lines = self._format_fields(fields)

        lines = [self.SEPARATOR, header] + field_lines

        # 에러 스택트레이스
        if record.exc_info:
            stacktrace = "".join(traceback.format_exception(*record.exc_info))
            lines.append(stacktrace.rstrip())

        return "\n".join(lines)

    def _format_fields(self, fields: dict[str, Any]) -> list[str]:
        """key: value 형태로 들여쓰기 출력. 긴 값은 줄바꿈 처리."""
        if not fields:
            return []

        max_key_len = max(len(k) for k in fields)
        lines = []
        for key, value in fields.items():
            padding = " " * (max_key_len - len(key))
            lines.append(f"  {key}{padding} : {value}")
        return lines
```

**설계 결정:**
- 색상은 ANSI 코드 사용 (터미널에서만 의미 있음, 파일 저장 시 코드 그대로 출력되므로 운영 환경은 compact 사용)
- `_RESERVED_ATTRS`는 `StructuredFormatter`에서 재사용하여 중복 정의 방지
- location 필드는 always-last로 고정 (노이즈 줄임)
- 구분선은 요청/응답 경계를 시각적으로 분리

---

## 3. 포매터 팩토리

### `src/infrastructure/logging/formatters/__init__.py` (수정)

```python
import logging
import os

from .structured_formatter import StructuredFormatter
from .pretty_formatter import PrettyFormatter

__all__ = ["StructuredFormatter", "PrettyFormatter", "get_formatter"]


def get_formatter() -> logging.Formatter:
    """LOG_FORMAT 환경변수에 따라 포매터 반환.

    Returns:
        LOG_FORMAT=pretty  → PrettyFormatter (기본값)
        LOG_FORMAT=compact → StructuredFormatter
    """
    fmt = os.getenv("LOG_FORMAT", "pretty").strip().lower()
    if fmt == "compact":
        return StructuredFormatter()
    return PrettyFormatter()
```

### `src/infrastructure/logging/structured_logger.py` (수정)

`StructuredFormatter()` 직접 생성 부분을 `get_formatter()` 호출로 교체.

```python
# 변경 전
from src.infrastructure.logging.formatters import StructuredFormatter

handler.setFormatter(StructuredFormatter())

# 변경 후
from src.infrastructure.logging.formatters import get_formatter

handler.setFormatter(get_formatter())
```

---

## 4. uvicorn access log 억제

### `src/api/main.py` (수정)

미들웨어에서 이미 request/response 로깅을 하므로 uvicorn의 중복 출력을 억제한다.

```python
# lifespan 또는 앱 초기화 직후에 추가
uvicorn_access = logging.getLogger("uvicorn.access")
uvicorn_access.handlers.clear()
uvicorn_access.propagate = False
```

**위치**: `lifespan` 컨텍스트 매니저의 시작 부분, 또는 앱 생성 직후.

---

## 5. LOG-002-B: DBQueryListener

### `src/infrastructure/logging/db_query_listener.py` (신규)

```python
"""SQLAlchemy DB 쿼리 로깅 리스너.

before_cursor_execute / after_cursor_execute 이벤트로
SQL, 파라미터, 실행 시간을 DEBUG 레벨로 로깅한다.
"""

import time
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine

from src.infrastructure.logging import get_logger

logger = get_logger("db.query")

_SENSITIVE_PARAM_KEYS = {"password", "token", "secret", "api_key", "refresh_token"}


class DBQueryListener:
    """SQLAlchemy 쿼리 실행 로깅 리스너."""

    def register(self, engine: AsyncEngine) -> None:
        """엔진에 before/after 이벤트 리스너를 등록한다.

        Args:
            engine: AsyncEngine 인스턴스
        """
        event.listen(
            engine.sync_engine, "before_cursor_execute", self._before_execute
        )
        event.listen(
            engine.sync_engine, "after_cursor_execute", self._after_execute
        )

    def _before_execute(
        self,
        conn: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        """쿼리 시작 시각 기록."""
        conn.info["query_start_time"] = time.perf_counter()

    def _after_execute(
        self,
        conn: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        """쿼리 완료 후 SQL + 파라미터 + 실행 시간 로깅."""
        start = conn.info.get("query_start_time")
        duration_ms = round((time.perf_counter() - start) * 1000, 2) if start else None

        masked_params = _mask_sensitive_params(parameters)

        logger.debug(
            "DB Query",
            sql=statement.strip(),
            params=masked_params,
            duration_ms=duration_ms,
        )


def _mask_sensitive_params(parameters: Any) -> Any:
    """바인딩 파라미터에서 민감 키를 마스킹한다.

    Args:
        parameters: SQLAlchemy 바인딩 파라미터 (dict 또는 list[dict])

    Returns:
        마스킹된 파라미터
    """
    if isinstance(parameters, dict):
        return {
            k: "***MASKED***" if k.lower() in _SENSITIVE_PARAM_KEYS else v
            for k, v in parameters.items()
        }
    if isinstance(parameters, (list, tuple)):
        return [_mask_sensitive_params(p) for p in parameters]
    return parameters
```

### `src/infrastructure/persistence/database.py` (수정)

```python
# 변경 전
def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.database_url,
            echo=False,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )
    return _engine

# 변경 후
from src.infrastructure.logging.db_query_listener import DBQueryListener

_db_query_listener = DBQueryListener()

def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.database_url,
            echo=False,          # SQLAlchemy 기본 출력 비활성 유지
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )
        _db_query_listener.register(_engine)   # 커스텀 리스너 등록
    return _engine
```

**`echo=False` 유지 이유**: SQLAlchemy의 기본 echo 출력은 표준 logging 포매터를 따르지 않아 포맷이 불일치함. 커스텀 리스너로 동일한 `StructuredFormatter` / `PrettyFormatter` 포맷 적용.

---

## 6. 출력 예시

### pretty 모드 (LOG_FORMAT=pretty)

```
────────────────────────────────────────────────────────────────
[2026-04-11T08:28:41Z] INFO     Request received
  request_id  : 47b1c48c-46d1-40e0-98f2-4d339b7e8e2b
  method      : GET
  endpoint    : /api/v1/auth/me
  query_params: {}
  location    : request_logging_middleware.py:_log_request:102
────────────────────────────────────────────────────────────────
[2026-04-11T08:28:41Z] DEBUG    DB Query
  sql         : SELECT users.id, users.email, users.role
                FROM users WHERE users.email = :email_1
  params      : {"email_1": "user@example.com"}
  duration_ms : 1.24
  location    : db_query_listener.py:_after_execute:68
────────────────────────────────────────────────────────────────
[2026-04-11T08:28:41Z] INFO     Response sent
  request_id   : 47b1c48c-46d1-40e0-98f2-4d339b7e8e2b
  status_code  : 401
  process_time_ms: 2.54
  location     : request_logging_middleware.py:_log_response:114
```

### compact 모드 (LOG_FORMAT=compact) — 기존 동일

```
{"timestamp": "2026-04-11T08:28:41.987906+00:00", "level": "INFO", ...}
```

---

## 7. 환경변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `LOG_FORMAT` | `pretty` | `pretty` = 멀티라인 / `compact` = JSON 한 줄 |
| `LOG_LEVEL` | `INFO` | `DEBUG`로 설정 시 DB 쿼리 로그 출력 |

`.env` 예시 (개발):
```env
LOG_FORMAT=pretty
LOG_LEVEL=DEBUG
```

운영 환경 (`docker-compose.yml` 또는 서버 env):
```env
LOG_FORMAT=compact
LOG_LEVEL=INFO
```

---

## 8. 테스트 설계

### `tests/infrastructure/logging/test_pretty_formatter.py`

| 테스트명 | 검증 내용 |
|---------|-----------|
| `test_format_contains_separator` | 출력에 `─` 구분선 포함 |
| `test_format_header_line` | `[timestamp] LEVEL message` 형식 |
| `test_format_extra_fields_indented` | extra 필드가 `  key : value` 형태 |
| `test_format_error_with_stacktrace` | exc_info 있을 때 스택트레이스 포함 |
| `test_format_no_color_codes_in_plain_check` | 레벨별 ANSI 코드 포함 여부 |

### `tests/infrastructure/logging/test_db_query_listener.py`

| 테스트명 | 검증 내용 |
|---------|-----------|
| `test_logs_sql_statement` | SQL 문자열 로그에 포함 |
| `test_logs_duration_ms` | duration_ms 양수 값 포함 |
| `test_masks_password_param` | `password` 키 → `***MASKED***` |
| `test_masks_token_param` | `token` 키 → `***MASKED***` |
| `test_non_sensitive_param_not_masked` | `user_id` 등 일반 키는 마스킹 안 됨 |
| `test_list_params_masked` | executemany 형태(list of dict) 처리 |

### `tests/infrastructure/logging/test_get_formatter.py`

| 테스트명 | 검증 내용 |
|---------|-----------|
| `test_default_returns_pretty` | `LOG_FORMAT` 미설정 → `PrettyFormatter` |
| `test_pretty_returns_pretty` | `LOG_FORMAT=pretty` → `PrettyFormatter` |
| `test_compact_returns_structured` | `LOG_FORMAT=compact` → `StructuredFormatter` |
| `test_case_insensitive` | `LOG_FORMAT=COMPACT` 대소문자 무관 처리 |

---

## 9. 구현 순서

```
1. tests/infrastructure/logging/test_get_formatter.py    (Red)
2. src/infrastructure/logging/formatters/__init__.py     (get_formatter 추가 → Green)
3. tests/infrastructure/logging/test_pretty_formatter.py (Red)
4. src/infrastructure/logging/formatters/pretty_formatter.py (Green)
5. src/infrastructure/logging/structured_logger.py       (get_formatter() 교체)
6. src/api/main.py                                       (uvicorn access log 억제)
7. tests/infrastructure/logging/test_db_query_listener.py (Red)
8. src/infrastructure/logging/db_query_listener.py       (Green)
9. src/infrastructure/persistence/database.py            (리스너 등록)
10. 전체 테스트 실행 확인 (기존 927개 + 신규 테스트 통과)
```

---

## 10. 영향 범위

| 파일 | 변경 종류 | 영향 |
|------|----------|------|
| `structured_logger.py` | 수정 | 기존 모든 로거 포매터가 교체됨 (compact/pretty 선택) |
| `formatters/__init__.py` | 수정 | `get_formatter` export 추가 (하위 호환 유지) |
| `database.py` | 수정 | 엔진 생성 시 리스너 1회 등록 (사이드이펙트 최소) |
| `main.py` | 수정 | uvicorn.access 로거 핸들러 제거 |

**기존 코드 영향 없음:**
- `StructuredFormatter` 클래스 자체는 변경 없음 (compact 모드에서 그대로 사용)
- `RequestLoggingMiddleware`, `ExceptionHandlerMiddleware` 변경 없음
- 기존 927개 테스트에 영향 없음 (포매터 교체는 출력 형식만 변경)
