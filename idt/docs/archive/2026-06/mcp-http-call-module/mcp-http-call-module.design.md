# MCP HTTP Call 공통 모듈 — Design Document

> **Summary**: LangChain 비의존 **순수 MCP 호출 코어 `MCPCallClient`** 를 설계한다. `domain/mcp`에 Streamable HTTP transport·세분화 타임아웃·인증·재시도 정책 VO를 추가하고, `MCPClientFactory`를 확장하며, 주입형(config/timeout/auth/retry/logger) 호출 코어를 신설한다. 모든 인터페이스/시그니처를 확정한다.
>
> **Project**: sangplusbot (idt)
> **Version**: 1.0
> **Author**: 배상규
> **Date**: 2026-06-16
> **Status**: Draft
> **Planning Doc**: [mcp-http-call-module.plan.md](../../01-plan/features/mcp-http-call-module.plan.md)

### Pipeline References

| Phase | Document | Status |
|-------|----------|--------|
| Phase 1 | Schema Definition | N/A (도메인 VO는 본 문서 §3에서 정의) |
| Phase 2 | Coding Conventions | ✅ `idt/CLAUDE.md` §3 준수 |
| Phase 3 | Mockup | N/A (UI 없음) |
| Phase 4 | API Spec | N/A (외부 HTTP 엔드포인트 미추가, MCP 클라이언트 코어) |

---

## 1. Overview

### 1.1 Design Goals

- LangChain(`BaseTool`)에 **비의존**하는 재사용 가능한 MCP 호출 코어를 만든다.
- **Streamable HTTP** transport를 신규 지원하고 기존 SSE를 동일 시그니처로 흡수한다.
- 타임아웃(connect/read/total)·인증(Bearer)·재시도+백오프·LoggerInterface를 **생성자 주입**으로 받는다.
- DDD 레이어 경계를 지킨다: 도메인은 외부 의존 0, 호출 코어는 infrastructure, mcp SDK 타입은 코어 경계에서 도메인 VO로 변환한다.
- TDD: mock 세션 기반 네트워크 비의존 테스트로 전부 검증한다.

### 1.2 Design Principles

- **단일 책임**: `MCPCallClient`는 "세션 생성 → 호출 → 결과 변환 → 재시도/로깅"만 담당. 도구 래핑·등록은 후속 책임.
- **의존성 역전**: 코어는 `LoggerInterface`(도메인)에 의존하고 `StructuredLogger`(infra) 구현을 주입받는다.
- **확장 개방·수정 폐쇄**: `MCPServerConfig`에 필드 **추가만**, 기존 stdio/sse/websocket 분기·시그니처 보존.
- **순수 도메인**: 재시도 백오프·재시도성 분류·타임아웃 검증은 외부 의존 없는 순수 함수/VO.
- **async-first**: 코어는 비동기 전용. 동기 래핑은 out of scope.

---

## 2. Architecture

### 2.1 Component Diagram

```
        ┌──────────────────────────────────────────────────────────┐
        │  소비자 (후속 PDCA): MCPToolAdapter / mcp_registry / pytest │
        └───────────────────────────┬──────────────────────────────┘
                                     │ (주입: config, timeout, auth, retry, logger)
                                     ▼
   infrastructure ┌──────────────────────────────────────────────┐
                  │            MCPCallClient  ★신규               │
                  │  list_tools(request_id) / call_tool(...)      │
                  │  └ MCPRetryPolicy로 재시도 루프 래핑           │
                  └───────────┬───────────────────┬──────────────┘
                              │ create_session()  │ uses
                              ▼                    ▼
        ┌─────────────────────────────┐   ┌─────────────────────┐
        │  MCPClientFactory (~확장)    │   │  LoggerInterface    │
        │  + _streamable_http_session │   │  (domain, 주입)      │
        │  + 타임아웃/auth 헤더 주입    │   └─────────────────────┘
        └───────────┬─────────────────┘
                    │ mcp SDK
                    ▼
        ┌─────────────────────────────────────────────────────┐
        │ streamablehttp_client / sse_client / stdio / ws      │
        └─────────────────────────────────────────────────────┘
                    ▲ reads VO
   domain ┌─────────────────────────────────────────────────────┐
          │ MCPTransport.STREAMABLE_HTTP · StreamableHTTPServerConfig │
          │ MCPTimeoutConfig · MCPAuthConfig · MCPToolDescriptor   │
          │ MCPRetryPolicy(compute_backoff/is_retryable)          │
          └─────────────────────────────────────────────────────┘
```

### 2.2 Data Flow (`call_tool`)

```
call_tool(name, args, request_id)
  → MCPRetryPolicy 루프 (attempt = 0..max_retries)
      → MCPClientFactory.create_session(config, timeout, auth, request_id)   # 호출당 stateless 세션
          → transport 분기 (STREAMABLE_HTTP / SSE / STDIO / WS)
          → ClientSession.initialize()
      → asyncio.wait_for(session.call_tool(name, args), timeout=total)        # total 타임아웃 강제
      → _to_tool_result(raw) → MCPToolResult VO
  → 성공 시 반환 / 재시도성 예외 시 compute_backoff(attempt) 대기 후 재시도
  → 한도 초과 시 마지막 예외 raise (스택 트레이스 로깅)
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `MCPCallClient` (infra) | `MCPClientFactory`, `MCPRetryPolicy`, `LoggerInterface`, 도메인 VO | 호출 오케스트레이션 |
| `MCPClientFactory` (infra) | mcp SDK, 도메인 VO | transport별 세션 생성 |
| 도메인 VO/Policy | **없음** (pydantic/typing만) | 설정·규칙 정의 |

> **레이어 검증**: 도메인 → infra/langchain import 0건, infra → domain 단방향. `verify-architecture` 통과 목표.

---

## 3. Data Model (Domain VO / Policy)

### 3.1 `MCPTransport` 확장 (`domain/mcp/value_objects.py`)

```python
class MCPTransport(str, Enum):
    STDIO = "stdio"
    SSE = "sse"
    WEBSOCKET = "websocket"
    STREAMABLE_HTTP = "streamable_http"   # (+) 신규
```

### 3.2 `StreamableHTTPServerConfig` (+신규)

```python
class StreamableHTTPServerConfig(BaseModel):
    """Streamable HTTP Transport 서버 설정."""
    url: str = Field(description="MCP 서버 Streamable HTTP 엔드포인트 URL")
    headers: dict[str, str] | None = Field(default=None, description="정적 HTTP 헤더")
    timeout: MCPTimeoutConfig | None = Field(
        default=None, description="세분화 타임아웃. None이면 기본값 사용"
    )
```

### 3.3 주입 설정 VO (+신규)

```python
class MCPTimeoutConfig(BaseModel):
    """세분화 타임아웃 (초). 모두 양수여야 한다."""
    connect: float = Field(default=30.0, gt=0, description="연결/HTTP 요청 타임아웃")
    read: float = Field(default=300.0, gt=0, description="SSE/스트림 읽기 타임아웃")
    total: float = Field(default=300.0, gt=0, description="단일 호출 전체 상한(wait_for)")

    @classmethod
    def from_legacy(cls, timeout: float) -> "MCPTimeoutConfig":
        """SSEServerConfig.timeout 단일값 → connect로 매핑(호환 규칙). read/total은 기본값."""
        return cls(connect=timeout)


class MCPAuthConfig(BaseModel):
    """인증 헤더 주입 설정."""
    scheme: str = Field(default="Bearer", description="Authorization 스킴")
    token: str | None = Field(default=None, description="토큰 값")
    extra_headers: dict[str, str] = Field(default_factory=dict, description="추가 인증 헤더")

    def to_headers(self) -> dict[str, str]:
        """주입할 헤더 dict 생성. token이 있으면 Authorization 구성."""
        headers = dict(self.extra_headers)
        if self.token:
            headers["Authorization"] = f"{self.scheme} {self.token}".strip()
        return headers
```

### 3.4 `MCPToolDescriptor` (+신규) — **Open Question #1 확정**

> **결정**: mcp SDK 타입을 외부로 노출하지 않고 경량 도메인 VO로 변환한다. 코어의 LangChain/SDK 비의존성과 테스트 용이성을 위해 신규 VO를 둔다.

```python
class MCPToolDescriptor(BaseModel):
    """list_tools 결과 1건 (transport-agnostic)."""
    name: str = Field(description="Tool 이름 (원본)")
    description: str = Field(default="", description="Tool 설명")
    input_schema: dict = Field(default_factory=dict, description="JSON Schema (inputSchema)")
```

### 3.5 `MCPServerConfig` 필드 추가 (~비파괴)

```python
class MCPServerConfig(BaseModel):
    name: str
    transport: MCPTransport
    stdio: StdioServerConfig | None = None
    sse: SSEServerConfig | None = None
    websocket: WebSocketServerConfig | None = None
    streamable_http: StreamableHTTPServerConfig | None = None   # (+) 추가

    def get_transport_config(self) -> StdioServerConfig | SSEServerConfig \
            | WebSocketServerConfig | StreamableHTTPServerConfig:
        # 기존 분기 보존 + STREAMABLE_HTTP 분기 추가
        if self.transport == MCPTransport.STREAMABLE_HTTP:
            if self.streamable_http is None:
                raise ValueError("streamable_http config is required for STREAMABLE_HTTP transport")
            return self.streamable_http
        # ... 기존 stdio/sse/websocket 분기 그대로 ...
```

> `get_transport_config`는 분기가 4개로 늘어 if 중첩/길이 규칙을 지키기 위해 **dict 매핑 디스패치**로 리팩토링한다(§10.4).

### 3.6 `MCPRetryPolicy` (+신규, `domain/mcp/policy.py`) — **Open Question #2, #3 확정**

> **결정 #2 (재시도 범위)**: 기본은 **연결 단계 한정**. tool 실행 재시도는 비멱등 부작용 위험이 있어 `retry_tool_execution=False` 기본 **옵트인**.
> **결정 #3 (기본 상수 소재)**: 도메인 순수 정책 상수로 둔다(외부 config 비의존, NFR-4의 "정책 상수" 경로). 호출부에서 주입으로 오버라이드 가능.

```python
class MCPRetryPolicy(BaseModel):
    """재시도 + 지수 백오프 정책 (도메인 순수)."""
    max_retries: int = Field(default=2, ge=0, description="최초 시도 외 추가 재시도 횟수")
    base_backoff: float = Field(default=0.5, gt=0, description="첫 재시도 대기(초)")
    factor: float = Field(default=2.0, ge=1.0, description="지수 증가 계수")
    max_backoff: float = Field(default=8.0, gt=0, description="대기 상한(초)")
    retry_tool_execution: bool = Field(
        default=False, description="True면 call_tool 실패도 재시도(멱등 도구 한정 옵트인)"
    )

    def compute_backoff(self, attempt: int) -> float:
        """attempt(0-base) → 대기 시간. 단조 증가 + 상한 보장."""
        delay = self.base_backoff * (self.factor ** attempt)
        return min(delay, self.max_backoff)

    @staticmethod
    def is_retryable(exc: BaseException) -> bool:
        """재시도성 분류. 연결/타임아웃/일시 네트워크 오류만 재시도."""
        return isinstance(exc, (ConnectionError, TimeoutError, asyncio.TimeoutError, OSError))
```

> `MCPConnectionPolicy`는 기존 그대로 보존(서버 수·tool 이름 정규화). 재시도는 별도 클래스로 분리(단일 책임).

---

## 4. API Specification (모듈 인터페이스)

외부 HTTP 엔드포인트를 추가하지 않는다. 본 절은 **`MCPCallClient` 공개 인터페이스**를 계약으로 정의한다.

### 4.1 `MCPCallClient` (`infrastructure/mcp/call_client.py`, +신규)

```python
class MCPCallClient:
    def __init__(
        self,
        config: MCPServerConfig,
        *,
        timeout: MCPTimeoutConfig | None = None,
        auth: MCPAuthConfig | None = None,
        retry: MCPRetryPolicy | None = None,
        logger: LoggerInterface | None = None,
    ) -> None: ...

    async def list_tools(self, request_id: str | None = None) -> list[MCPToolDescriptor]: ...

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        request_id: str | None = None,
    ) -> MCPToolResult: ...
```

| 항목 | 계약 |
|------|------|
| 기본값 | `timeout=MCPTimeoutConfig()`, `auth=None`, `retry=MCPRetryPolicy()`, `logger=get_logger()` 기본 주입 |
| `list_tools` | 세션 `list_tools()` → 각 SDK tool을 `MCPToolDescriptor`로 변환한 리스트 반환. 멱등 read이므로 operation 단계도 재시도 허용(`retry_operation=True`) |
| `call_tool` 성공 | `MCPToolResult(tool_name, server_name=config.name, content, is_error=False, raw_result)` |
| `call_tool` 도구 에러 | MCP 결과 `isError=True` → `MCPToolResult(is_error=True, content=에러텍스트)` 반환(예외 아님) |
| 재시도 | `is_retryable(exc) and attempt < max_retries`일 때 `compute_backoff` 후 재시도. tool 실행은 `retry_tool_execution=True`일 때만 |
| 최종 실패 | 한도 초과 시 마지막 예외 `raise` (스택 트레이스 로깅 후) |
| request_id | 미지정 시 `uuid4().hex`로 생성하여 전 구간 로그에 전파 |

### 4.2 `MCPClientFactory` 확장 (~)

```python
@staticmethod
@asynccontextmanager
async def create_session(
    config: MCPServerConfig,
    request_id: str | None = None,
    *,
    timeout: MCPTimeoutConfig | None = None,   # (+) 주입
    auth: MCPAuthConfig | None = None,          # (+) 주입
) -> AsyncIterator[ClientSession]: ...

@staticmethod
@asynccontextmanager
async def _streamable_http_session(                 # (+) 신규
    config: MCPServerConfig,
    timeout: MCPTimeoutConfig,
    headers: dict[str, str],
) -> AsyncIterator[ClientSession]: ...
```

**`_streamable_http_session` 구현 계약** (SDK 실측 시그니처 기준 — Risk #1 해소):

```python
# streamablehttp_client(url, headers, timeout, sse_read_timeout, ...) → (read, write, get_session_id)  ← 3-tuple!
async with streamablehttp_client(
    url=cfg.url,
    headers=headers,                # 정적 헤더 + auth 병합 결과
    timeout=timeout.connect,
    sse_read_timeout=timeout.read,
) as (read, write, _get_session_id):   # ★ SSE와 달리 3개를 yield
    async with ClientSession(read, write) as session:
        await session.initialize()
        yield session
```

> **SDK 검증 완료**: `mcp.client.streamable_http.streamablehttp_client` 시그니처 = `(url, headers=None, timeout=30, sse_read_timeout=300, terminate_on_close=True, httpx_client_factory, auth=None)`, **반환은 3-tuple** `(read_stream, write_stream, get_session_id_callback)`. SSE의 `_sse_session`은 2-tuple이므로 언패킹을 혼동하지 않도록 분리한다.

### 4.3 헤더 병합 규칙 — **Open Question #4 확정**

> **결정**: `transport 정적 headers`(기반) → `MCPAuthConfig.to_headers()`(오버레이) 순서로 병합하며, **키 충돌 시 auth 가 우선**한다. 주입된 인증이 서버 설정의 정적 헤더를 항상 이긴다.

```python
merged = {**(transport_cfg.headers or {}), **(auth.to_headers() if auth else {})}
```

### 4.4 타임아웃 매핑 표

| 주입 필드 | STREAMABLE_HTTP | SSE | STDIO/WS |
|-----------|-----------------|-----|----------|
| `connect` | `timeout=` | `timeout=` | N/A (해당 transport 미적용) |
| `read` | `sse_read_timeout=` | `sse_read_timeout=` | N/A |
| `total` | `asyncio.wait_for`로 `call_tool`/`list_tools` 전체 감쌈 | 동일 | 동일 |

> SSE 호환: `SSEServerConfig.timeout` 단일값은 `MCPTimeoutConfig.from_legacy()`로 `connect`에 매핑(Risk #3 명문화). 기존 SSE 호출부는 무수정 통과.
>
> **Timeout 우선순위(STREAMABLE_HTTP)**: `StreamableHTTPServerConfig.timeout`(config 자체 값)이 존재하면 주입 `timeout`보다 **우선**한다(`effective_timeout = http_cfg.timeout or injected`). 서버별 고정 타임아웃을 config에 둘 수 있게 하기 위함이며, config에 없으면 주입값을 사용한다.

---

## 5. UI/UX Design

해당 없음 — 백엔드 인프라 코어 모듈. UI/엔드포인트 변경 없음.

---

## 6. Error Handling

### 6.1 에러 분류 및 처리

| 상황 | 분류 | 처리 |
|------|------|------|
| 연결 실패 (`ConnectionError`/`OSError`) | retryable | `is_retryable=True` → 재시도, 한도 초과 시 raise |
| 연결/호출 타임아웃 (`TimeoutError`) | retryable | `wait_for` 초과 → 재시도 대상 |
| MCP 도구 논리 에러 (`result.isError`) | non-exception | `MCPToolResult(is_error=True)` 반환, 재시도 안 함(기본) |
| 설정 누락 (`streamable_http=None`) | fatal | `get_transport_config()`가 `ValueError` 즉시 raise(재시도 X) |
| 인증 거부 (HTTP 401 등 SDK 예외) | non-retryable (기본) | `is_retryable=False`로 분류 → 즉시 raise |
| 예상치 못한 예외 | non-retryable | 스택 트레이스 로깅 후 raise |

### 6.2 로깅 (LOG-001 준수)

| 시점 | 레벨 | 필수 필드 |
|------|------|----------|
| 호출 시작 | info | `request_id, server, transport, tool` |
| 재시도 발생 | warning | `request_id, attempt, backoff, error` |
| 도구 에러 결과 | warning | `request_id, server, tool, is_error=True` |
| 최종 실패 | error | `request_id, server, tool, exception=`(스택 트레이스) |
| 호출 완료 | info | `request_id, server, tool, elapsed_ms` |

> `logger.error(..., exception=e)` 형태로 스택 트레이스를 강제 포함(LOG-001). `print()` 금지.

---

## 7. Security Considerations

- [x] 인증 토큰은 `MCPAuthConfig`로 주입 — 코드 하드코딩 금지. 로그에 토큰/`Authorization` 값 **마스킹**(헤더 값 미출력, 키 존재 여부만 로깅).
- [x] HTTPS 권장: `url`은 호출부 책임이나, `http://` 사용 시 경고 로그(선택).
- [x] 재시도가 비멱등 도구에 부작용 → 기본 `retry_tool_execution=False`로 차단.
- [x] 타임아웃 상한(`total`)으로 무한 대기/리소스 고갈 방지.
- [ ] Rate limiting / 커넥션 풀링 — out of scope(후속).

---

## 8. Test Plan

### 8.1 Test Scope

| Type | Target | Tool |
|------|--------|------|
| Unit (domain) | VO 검증·`MCPRetryPolicy`·`get_transport_config` 분기 | pytest |
| Unit (infra) | `MCPCallClient` (mock 세션) | pytest + `unittest.mock`/AsyncMock |
| Integration | 실 네트워크 | **out of scope** (후속 E2E) |

### 8.2 Test Cases (Key)

**도메인** (`tests/domain/mcp/`)
- [ ] `MCPTimeoutConfig`: 음수/0 거부(`gt=0`), `from_legacy(10.0).connect == 10.0`, read/total 기본값.
- [ ] `MCPAuthConfig.to_headers()`: token 있을 때 `Authorization: Bearer X`, 없을 때 extra_headers만, scheme 커스텀.
- [ ] `MCPRetryPolicy.compute_backoff`: attempt 0..n 단조 증가, `max_backoff` 상한 도달, `factor=1.0` 경계.
- [ ] `MCPRetryPolicy.is_retryable`: ConnectionError/TimeoutError/OSError → True, ValueError → False.
- [ ] `MCPServerConfig.get_transport_config`: STREAMABLE_HTTP 정상 분기 / `streamable_http=None`일 때 ValueError / 기존 stdio·sse·ws 회귀.

**인프라** (`tests/infrastructure/mcp/`) — `MCPClientFactory.create_session` 또는 세션을 patch
- [ ] `call_tool` happy path: `MCPToolResult(content=..., is_error=False)` 반환, server_name=config.name.
- [ ] `list_tools`: SDK tool 목록 → `MCPToolDescriptor` 변환 정확성(name/description/input_schema).
- [ ] 타임아웃 주입 반영: factory에 전달된 `timeout.connect/read` 값 검증(mock 인자 캡처).
- [ ] auth 헤더 병합: 정적 headers + auth, 충돌 시 auth 우선(§4.3).
- [ ] 재시도 성공: 2회 `ConnectionError` 후 3번째 성공 → 결과 반환, backoff 호출 횟수 검증.
- [ ] 재시도 한도 초과: max_retries 초과 → 마지막 예외 raise, error 로그 1회.
- [ ] 도구 에러 결과: `result.isError=True` → `is_error=True` 반환(예외 아님), 재시도 안 함.
- [ ] `retry_tool_execution` 옵트인: False면 call_tool 예외 즉시 raise, True면 재시도.
- [ ] SSE·STREAMABLE_HTTP 동일 시그니처: 같은 `call_tool` 호출로 양 transport 동작.

### 8.3 환경 주의 (메모리 반영)

- **네트워크 비의존**: 실제 소켓 금지, 전부 mock(`AsyncMock` 세션).
- **Windows 이벤트 루프 flakiness**: 교차 실행 시 teardown 산발 실패 알려짐 → 본 모듈 테스트는 **격리 실행**으로 회귀 판정(참조 메모리: `backend-test-eventloop-flakiness`). `@pytest.mark.asyncio` 루프 스코프 확인.

---

## 9. Clean Architecture

### 9.1 Layer Structure

| Layer | Responsibility | Location |
|-------|---------------|----------|
| **Domain** | transport enum, 설정/결과 VO, 재시도·연결 정책 | `src/domain/mcp/` |
| **Infrastructure** | 세션 팩토리, 호출 코어, StructuredLogger | `src/infrastructure/mcp/`, `src/infrastructure/logging/` |
| **Application** | (후속) UseCase/LangGraph 통합 | 이번 사이클 변경 없음 |
| **Interfaces** | 변경 없음 | — |

### 9.2 Dependency Rules

```
Application ──→ Domain ←── Infrastructure
                  ↑
   Infrastructure(MCPCallClient) ──→ Domain(VO/Policy/LoggerInterface)
   Domain ──→ (외부 의존 0)  ※ mcp SDK / langchain import 금지
```

### 9.3 File Import Rules

| From | Can Import | Cannot Import |
|------|-----------|---------------|
| `domain/mcp/*` | pydantic, typing, stdlib(`asyncio` 타입 분류만) | mcp SDK, langchain, infra |
| `infrastructure/mcp/call_client.py` | domain/mcp, mcp SDK, logging | langchain, application |
| `infrastructure/mcp/client_factory.py` | domain/mcp, mcp SDK | langchain, application |

> ⚠️ `is_retryable`에서 `asyncio.TimeoutError` 분류를 위해 도메인이 `asyncio`를 import한다. 이는 stdlib 타입 참조이며 외부 I/O가 아니므로 도메인 순수성 위반이 아님(주석으로 명시).

### 9.4 This Feature's Layer Assignment

| Component | Layer | Location |
|-----------|-------|----------|
| `MCPTransport.STREAMABLE_HTTP`, `StreamableHTTPServerConfig`, `MCPTimeoutConfig`, `MCPAuthConfig`, `MCPToolDescriptor` | Domain | `src/domain/mcp/value_objects.py` |
| `MCPRetryPolicy` | Domain | `src/domain/mcp/policy.py` |
| `MCPClientFactory` 확장 | Infrastructure | `src/infrastructure/mcp/client_factory.py` |
| `MCPCallClient` | Infrastructure | `src/infrastructure/mcp/call_client.py` (신규) |

---

## 10. Coding Convention Reference

### 10.1 Naming Conventions

| Target | Rule | Example |
|--------|------|---------|
| 클래스 | PascalCase | `MCPCallClient`, `MCPTimeoutConfig` |
| 함수/메서드 | snake_case | `call_tool()`, `compute_backoff()` |
| 상수 | UPPER_SNAKE_CASE | `MAX_SERVERS` |
| 모듈 파일 | snake_case.py | `call_client.py` |

### 10.2 Import Order (Python)

```python
# 1. stdlib
import asyncio
from contextlib import asynccontextmanager
# 2. 외부 라이브러리
from mcp import ClientSession
from pydantic import BaseModel, Field
# 3. 내부 (domain → infrastructure)
from src.domain.mcp.value_objects import MCPServerConfig, MCPToolResult
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.mcp.client_factory import MCPClientFactory
```

### 10.3 Environment Variables

신규 env 없음. 기본 타임아웃/재시도 상수는 **도메인 정책 VO 기본값**으로 관리(하드코딩 금지, NFR-4).

### 10.4 This Feature's Conventions

| Item | Convention Applied |
|------|-------------------|
| 함수 길이 | 40줄 이내 — `create_session`은 transport 분기를 dict 디스패치로 축약 |
| if 중첩 | 2단계 이내 — `get_transport_config`/`create_session`은 `{transport: handler}` 매핑으로 평탄화 |
| 타입 | 전부 명시(pydantic VO + typing), `Any`는 SDK 경계에서만 |
| 에러 처리 | `logger.error(exception=e)` 후 raise, 스택 트레이스 필수 |

---

## 11. Implementation Guide

### 11.1 File Structure

```
src/
├── domain/mcp/
│   ├── value_objects.py   (~) STREAMABLE_HTTP, StreamableHTTPServerConfig,
│   │                          MCPTimeoutConfig, MCPAuthConfig, MCPToolDescriptor,
│   │                          MCPServerConfig.streamable_http
│   └── policy.py          (~) MCPRetryPolicy 추가 (MCPConnectionPolicy 보존)
├── infrastructure/mcp/
│   ├── client_factory.py  (~) _streamable_http_session, timeout/auth 주입, dict 디스패치
│   └── call_client.py     (+) MCPCallClient
└── tests/
    ├── domain/mcp/        (+) test_value_objects.py, test_retry_policy.py
    └── infrastructure/mcp/(+) test_call_client.py, test_client_factory_http.py
```

### 11.2 Implementation Order (TDD Red→Green, 마일스톤 매핑)

1. **[M1] 도메인** — Red: VO/`MCPRetryPolicy` 테스트 작성 → Green: `value_objects.py`/`policy.py` 구현 → `verify-architecture`/`verify-tdd`.
2. **[M2] Factory** — Red: `_streamable_http_session`·타임아웃/헤더 주입 테스트(mock SDK) → Green: `client_factory.py` 확장(3-tuple 언패킹, dict 디스패치) → 기존 SSE/stdio/ws 회귀 통과 확인.
3. **[M3] 호출 코어** — Red: `MCPCallClient` happy/재시도/도구에러/타임아웃 테스트 → Green: `call_client.py` 구현(재시도 루프 + 로깅) → `verify-logging`.
4. **[M4] 검증** — `verify-architecture`/`verify-logging`/`verify-tdd` 전체 + `/pdca analyze mcp-http-call-module` (Match Rate ≥ 90% 목표). Windows 격리 실행.

### 11.3 비파괴 체크리스트

- [ ] `MCPServerConfig` 기존 필드/시그니처 무변경(추가만).
- [ ] `MCPClientFactory.create_session` 기존 호출(`tool_adapter.py:72`) 무수정 통과 — 신규 인자는 keyword-only 기본값.
- [ ] `MCPToolAdapter`/`MCPToolRegistry`/`mcp_registry`/`ToolFactory` 변경 0.
- [ ] `SSEServerConfig.timeout` 단일값 동작 보존.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-06-16 | Initial draft — Plan의 Open Questions 4건 전부 확정, SDK 실측 시그니처 반영 | 배상규 |
