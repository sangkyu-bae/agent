# Plan: log-enhance

> Feature: 로그 출력 가독성 개선 + DB 쿼리 로깅
> Created: 2026-04-11
> Status: Plan
> Task ID: LOG-002

---

## 1. 목적 (Why)

현재 로그가 JSON 한 줄로 압축 출력되어 터미널에서 즉시 파악하기 어렵다.
개발/디버깅 환경에서 로그 가독성을 높이고, DB 쿼리 실행 내용도 추적할 수 있게 한다.

**현재 문제**
```
{"timestamp": "2026-04-11T08:28:41.987906+00:00", "level": "INFO", "logger": "idt_api", "message": "Request received", "location": "request_logging_middleware.py:_log_request:102", "request_id": "47b1c48c-...", "method": "GET", "endpoint": "/api/v1/auth/me", "query_params": {}}
{"timestamp": "2026-04-11T08:28:41.990424+00:00", "level": "INFO", "logger": "idt_api", "message": "Response sent", ..., "status_code": 401, "process_time_ms": 2.54}
INFO:     127.0.0.1:50060 - "GET /api/v1/auth/me HTTP/1.1" 401 Unauthorized
```

**목표 출력 (개발 환경)**
```
────────────────────────────────────────────
[2026-04-11T08:28:41Z] INFO  Request received
  request_id : 47b1c48c-46d1-40e0-98f2-4d339b7e8e2b
  method     : GET
  endpoint   : /api/v1/auth/me
  query_params: {}
  location   : request_logging_middleware.py:_log_request:102
────────────────────────────────────────────
[2026-04-11T08:28:41Z] INFO  Response sent
  request_id   : 47b1c48c-46d1-40e0-98f2-4d339b7e8e2b
  status_code  : 401
  process_time_ms: 2.54
────────────────────────────────────────────
[2026-04-11T08:28:41Z] DEBUG DB Query
  request_id : 47b1c48c-...
  sql        : SELECT users.id, users.email FROM users WHERE users.email = :email_1
  params     : {"email_1": "user@example.com"}
  duration_ms: 1.2
────────────────────────────────────────────
```

---

## 2. 기능 범위 (Scope)

### In Scope

#### LOG-002-A: 로그 포맷 개선 (Pretty Formatter)
- `LOG_FORMAT=pretty` 환경변수로 pretty 모드 활성화
- pretty 모드: 구분선 + 들여쓰기 필드 출력 (사람이 읽기 좋은 형태)
- compact 모드: 기존 JSON 한 줄 유지 (CI/운영 환경 — 로그 수집기 파싱용)
- `LOG_FORMAT` 기본값: `pretty` (개발 편의 우선, 운영은 명시적으로 `compact` 설정)
- uvicorn access log 억제 (`INFO:     127.0.0.1...` 중복 제거)

#### LOG-002-B: DB 쿼리 로깅 (SQLAlchemy Event Listener)
- SQLAlchemy `before_cursor_execute` / `after_cursor_execute` 이벤트 리스너로 쿼리 캡처
- 로그 레벨: DEBUG (운영 환경에서는 자동 비활성화)
- 포함 정보: SQL 문, 바인딩 파라미터, 실행 시간(ms)
- 민감 파라미터 마스킹: password, token 계열 값 `***MASKED***` 처리
- `engine.echo`는 False 유지 (SQLAlchemy 기본 출력 사용 X → 커스텀 포매터로 통일)
- 위치: `src/infrastructure/persistence/database.py` 내 리스너 등록

### Out of Scope
- 운영 환경 로그 집계 (ELK, CloudWatch 등) 연동
- 슬로우 쿼리 알림 (추후 별도 Task로)
- 쿼리 플랜(EXPLAIN) 자동 수집

---

## 3. 기술 의존성

| 모듈 | Task ID | 상태 |
|------|---------|------|
| StructuredFormatter | LOG-001 | 구현됨 |
| database.py (AsyncEngine) | MYSQL-001 | 구현됨 |

외부 추가 라이브러리: 없음 (SQLAlchemy 이벤트 API 사용)

---

## 4. 아키텍처 설계

### 변경 파일 목록

```
src/
└── infrastructure/
    └── logging/
        ├── formatters/
        │   ├── structured_formatter.py     # 기존 (compact — 변경 없음)
        │   └── pretty_formatter.py         # 신규 — pretty 출력 포매터
        ├── __init__.py                     # get_formatter() 팩토리 추가
        └── db_query_listener.py            # 신규 — SQLAlchemy 쿼리 리스너
    └── persistence/
        └── database.py                     # db_query_listener 등록 추가
```

### LOG-002-A: PrettyFormatter 설계

```python
# src/infrastructure/logging/formatters/pretty_formatter.py
class PrettyFormatter(logging.Formatter):
    """사람이 읽기 좋은 멀티라인 포매터."""

    SEPARATOR = "─" * 60

    def format(self, record: logging.LogRecord) -> str:
        # 헤더 라인: [timestamp] LEVEL  message
        header = f"[{timestamp}] {level:<8} {message}"
        # 필드 라인: 들여쓰기 + key : value (정렬)
        fields = [f"  {k:<14}: {v}" for k, v in extra_fields.items()]
        # 스택트레이스 (에러 시)
        return "\n".join([self.SEPARATOR, header] + fields)
```

**포매터 선택 로직** (`__init__.py`)
```python
def get_formatter() -> logging.Formatter:
    if os.getenv("LOG_FORMAT", "pretty").lower() == "pretty":
        return PrettyFormatter()
    return StructuredFormatter()
```

### LOG-002-B: DBQueryListener 설계

```python
# src/infrastructure/logging/db_query_listener.py
class DBQueryListener:
    """SQLAlchemy 쿼리 실행 로깅 리스너."""

    SENSITIVE_KEYS = {"password", "token", "secret", "api_key"}

    def register(self, engine: AsyncEngine) -> None:
        event.listen(engine.sync_engine, "before_cursor_execute", self._before)
        event.listen(engine.sync_engine, "after_cursor_execute", self._after)

    def _before(self, conn, cursor, statement, parameters, context, executemany):
        conn.info["query_start"] = time.perf_counter()

    def _after(self, conn, cursor, statement, parameters, context, executemany):
        duration_ms = (time.perf_counter() - conn.info["query_start"]) * 1000
        logger.debug(
            "DB Query",
            sql=statement.strip(),
            params=self._mask_sensitive(parameters),
            duration_ms=round(duration_ms, 2),
        )
```

**등록 위치** (`database.py` `get_engine()` 내부)
```python
def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(...)
        DBQueryListener().register(_engine)   # ← 추가
    return _engine
```

### uvicorn access log 억제

```python
# src/api/main.py 또는 설정
logging.getLogger("uvicorn.access").handlers = []
logging.getLogger("uvicorn.access").propagate = False
```

---

## 5. 환경변수 설계

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `LOG_FORMAT` | `pretty` | `pretty` = 멀티라인 / `compact` = JSON 한 줄 |
| `LOG_LEVEL` | `INFO` | DEBUG 설정 시 DB 쿼리 로그 활성화 |

운영 환경 권장 설정:
```env
LOG_FORMAT=compact
LOG_LEVEL=INFO
```

개발 환경 권장 설정 (`.env` 기본값):
```env
LOG_FORMAT=pretty
LOG_LEVEL=DEBUG
```

---

## 6. 테스트 계획

| 테스트 | 검증 내용 |
|--------|-----------|
| `test_pretty_formatter.py` | 구분선, 들여쓰기, 타임스탬프 포함 여부 |
| `test_pretty_formatter.py` | 에러 시 스택트레이스 멀티라인 출력 |
| `test_db_query_listener.py` | before/after 이벤트 시 쿼리 + duration_ms 로깅 |
| `test_db_query_listener.py` | 민감 파라미터 마스킹 (`password=***MASKED***`) |
| `test_get_formatter.py` | `LOG_FORMAT=pretty` → PrettyFormatter 반환 |
| `test_get_formatter.py` | `LOG_FORMAT=compact` → StructuredFormatter 반환 |

---

## 7. 완료 조건 (Definition of Done)

- [ ] `LOG_FORMAT=pretty` 시 멀티라인 구분선 포맷으로 출력
- [ ] `LOG_FORMAT=compact` 시 기존 JSON 한 줄 포맷 유지
- [ ] `LOG_LEVEL=DEBUG` 시 SQL + 파라미터 + duration_ms 로깅
- [ ] `LOG_LEVEL=INFO` 시 DB 쿼리 로그 미출력
- [ ] 민감 파라미터 마스킹 동작
- [ ] uvicorn access log 중복 라인 미출력
- [ ] 기존 927개 테스트 통과 유지
- [ ] 신규 테스트 추가 (pretty formatter + db listener)

---

## 8. 작업 순서

1. `PrettyFormatter` 구현 + 테스트 (Red → Green)
2. `get_formatter()` 팩토리 + `LOG_FORMAT` 환경변수 연동
3. `StructuredLogger` 초기화 시 `get_formatter()` 사용하도록 수정
4. uvicorn access log 억제 설정
5. `DBQueryListener` 구현 + 테스트 (Red → Green)
6. `get_engine()` 에 `DBQueryListener` 등록
7. `.env` 예시 업데이트 (`LOG_FORMAT`, `LOG_LEVEL`)
8. task-logging.md 문서 업데이트 (LOG-002 섹션 추가)
