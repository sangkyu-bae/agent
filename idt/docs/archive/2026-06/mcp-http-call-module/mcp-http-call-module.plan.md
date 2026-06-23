# MCP HTTP Call 공통 모듈 — Planning Document

> **Summary**: 기존 `infrastructure/mcp`에 흩어진 MCP 호출(매 호출마다 세션을 새로 여는 `MCPToolAdapter._arun`, transport별로 박힌 타임아웃)을 대체할 **순수 호출 코어(`MCPCallClient`)**를 설계한다. Streamable HTTP transport를 신규 추가하고 기존 SSE도 동일 인터페이스로 흡수하며, **타임아웃(connect/read/total)·인증 헤더(Bearer)·재시도+백오프·LoggerInterface**를 주입받는다. LangChain에 비의존하여 추후 LangGraph 어댑터와 pytest 양쪽에서 재사용한다.
>
> **Project**: sangplusbot (idt)
> **Version**: 1.0
> **Author**: 배상규
> **Date**: 2026-06-14
> **Status**: Draft
> **Scope note**: 본 PDCA 사이클은 **공통 호출 모듈의 설계/구현까지만** 다룬다. LangGraph(`MCPToolAdapter`)·`mcp_registry`·ToolFactory 통합은 본 모듈을 소비하는 **후속 작업**으로 분리한다.

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | MCP 호출 로직이 재사용 가능한 단일 진입점 없이 흩어져 있다. ① `MCPToolAdapter._arun`/`MCPToolRegistry`가 각자 `MCPClientFactory.create_session()`을 직접 호출하고, ② 타임아웃은 `SSEServerConfig.timeout` 한 값으로만 존재(연결/읽기/전체 구분 없음), ③ 재시도·백오프·인증 헤더 주입 표준이 없으며, ④ **Streamable HTTP transport 미지원**(stdio/SSE/WebSocket만), ⑤ LangChain(`BaseTool`)에 얽혀 있어 호출 코어만 단독 테스트하기 어렵다. |
| **Solution** | `infrastructure/mcp`를 확장해 LangChain 비의존 **순수 호출 코어 `MCPCallClient`**를 신설한다. (1) `domain/mcp`에 `MCPTransport.STREAMABLE_HTTP` + `StreamableHTTPServerConfig` + 주입 설정 VO(`MCPTimeoutConfig`/`MCPAuthConfig`)와 `MCPRetryPolicy`를 추가, (2) `MCPClientFactory`에 streamable HTTP 세션과 타임아웃·헤더 주입 경로 추가(SSE도 동일하게 흡수), (3) `MCPCallClient`가 `list_tools()`/`call_tool()`을 제공하며 timeout·auth·retry·logger를 생성자 주입으로 받는다. |
| **Function/UX Effect** | 개발자는 `MCPCallClient(config, timeout=..., auth=..., retry=..., logger=...)` 한 줄로 Streamable HTTP 또는 SSE MCP 서버를 호출할 수 있고, 일시 실패 시 정책에 따라 자동 재시도되며 모든 호출이 `request_id` 기반 구조화 로그로 추적된다. 테스트는 LangChain 없이 클라이언트를 직접 검증한다. |
| **Core Value** | 흩어진 MCP 호출을 **단일 책임의 주입형 코어**로 수렴시켜, 추후 LangGraph 어댑터·`mcp_registry` 로더가 이 코어만 소비하도록 만드는 토대를 마련한다. transport(HTTP/SSE) 교체와 타임아웃/재시도 정책 변경이 호출부 변경 없이 주입만으로 가능해진다. |

---

## 1. Overview

### 1.1 Purpose

LangChain에 비의존하는 **재사용 가능한 MCP 호출 코어 모듈**을 설계·구현한다. HTTP(Streamable HTTP) 형태를 1차 대상으로 하고, 타임아웃·인증·재시도·로거를 외부에서 주입받아 LangGraph 도구·pytest 양쪽에서 동일하게 사용할 수 있게 한다.

### 1.2 Background — 현재 상태 (As-Is)

스택: `mcp==1.26.0` 설치 확인, `streamablehttp_client` 사용 가능, `langchain-mcp-adapters>=0.1.0` 존재.

#### 도메인 (`src/domain/mcp/`)
- `MCPTransport` enum: `STDIO / SSE / WEBSOCKET` — **`STREAMABLE_HTTP` 없음** (`value_objects.py:12-17`)
- `SSEServerConfig.timeout`: 단일 `float` 한 값. connect/read/total 구분 없음 (`value_objects.py:28-33`)
- `MCPConnectionPolicy`: 서버 수 상한·tool 이름 정규화만 존재. **재시도/백오프 정책 없음** (`policy.py`)
- `MCPToolResult` VO는 존재 (`value_objects.py:82-89`)

#### 인프라 (`src/infrastructure/mcp/`)
- `MCPClientFactory.create_session()`: stdio/sse/websocket 분기 (`client_factory.py:26-116`). 인증 헤더는 SSE의 `headers`로만, 타임아웃은 SSE만 적용.
- `MCPToolAdapter._arun()`: **매 호출마다** `create_session()`을 새로 열고 `call_tool()` 호출 후 결과 텍스트 추출 (`tool_adapter.py:51-88`) — 재시도/세분화 타임아웃 없음, LangChain `BaseTool`에 결합.
- `MCPToolRegistry`: 서버별 `list_tools()` → `MCPToolAdapter` 생성 (`tool_registry.py`).

#### 레지스트리 (`src/*/mcp_registry/`)
- `MCPToolLoader`: DB 등록 서버를 **SSE 고정**으로 `MCPServerConfig` 조립 (`mcp_tool_loader.py:32-37`).

### 1.3 Gap 요약

| Gap | 영향 |
|-----|------|
| Streamable HTTP transport 미지원 | 최신 MCP 서버(HTTP) 연결 불가. 요청의 "http 형태" 충족 안 됨 |
| 타임아웃이 단일 값(SSE only) | connect 지연과 tool 실행 지연을 구분 제어 불가 |
| 재시도/백오프 표준 부재 | 네트워크 일시 실패가 즉시 도구 실패로 전파 |
| 인증 헤더 주입 표준 부재 | Bearer 토큰 등 서버별 인증 일관 처리 불가 |
| 호출 코어가 LangChain에 결합 | 호출 로직 단독 단위테스트 어려움, 재사용 불가 |
| 호출 진입점이 분산 | adapter/registry/loader가 각자 세션 생성 → 정책 변경 시 다중 수정 |

### 1.4 결정 사항 (사용자 확정)

| 항목 | 결정 |
|------|------|
| 모듈 위치 | **기존 `infrastructure/mcp` 확장** (신규 독립 모듈 X) |
| 책임 범위 | **순수 호출 코어만** (LangChain `BaseTool` 비의존) |
| Transport | **Streamable HTTP 신규 + 기존 SSE 동일 인터페이스 흡수** |
| 주입 설정 | **타임아웃(connect/read/total 분리) · 인증 헤더(Bearer) · 재시도+백오프 · LoggerInterface** |

---

## 2. Scope

### 2.1 In Scope (이번 사이클)

- `domain/mcp`: `STREAMABLE_HTTP` transport, `StreamableHTTPServerConfig`, 주입 설정 VO(`MCPTimeoutConfig`, `MCPAuthConfig`), `MCPRetryPolicy`(도메인 정책).
- `infrastructure/mcp`: `MCPClientFactory` streamable HTTP 세션 + 타임아웃/헤더 주입 경로 추가.
- `infrastructure/mcp`: **신규 `MCPCallClient`** — `list_tools()` / `call_tool()` 순수 호출 코어, 생성자 주입(config/timeout/auth/retry/logger), 재시도 적용.
- 위 전부에 대한 pytest(TDD Red→Green) — 외부 네트워크 의존 없는 mock 세션 기반.

### 2.2 Out of Scope (후속 분리)

- `MCPToolAdapter`/`MCPToolRegistry`를 `MCPCallClient` 위로 리팩토링 (LangGraph 통합).
- `mcp_registry`(`MCPToolLoader`)가 transport를 DB에서 선택하도록 확장.
- `ToolFactory`/`WorkflowCompiler`의 `mcp_` 도구 경로 변경.
- 실제 외부 MCP 서버 연동 E2E, 커넥션 풀링/세션 재사용(현 설계는 호출당 세션 — stateless).
- WebSocket/stdio transport에 대한 신규 기능(기존 동작 보존만).

### 2.3 비파괴 원칙 (Non-breaking)

- `MCPServerConfig`에 필드 **추가만** (`streamable_http` Optional), 기존 stdio/sse/websocket 동작·시그니처 보존.
- `SSEServerConfig.timeout` 단일 필드는 호환 유지(신규 `MCPTimeoutConfig`로 매핑 가능). 기존 호출부 무수정 통과.
- 신규 코드 추가 중심 — `MCPToolAdapter` 등 기존 소비자는 이번 사이클에서 변경하지 않음.

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | 요구사항 | 수용 기준(요약) |
|----|----------|----------------|
| FR-1 | `MCPTransport.STREAMABLE_HTTP` 및 `StreamableHTTPServerConfig`(url, headers, 타임아웃) 추가 | `MCPServerConfig(transport=STREAMABLE_HTTP, streamable_http=...)` 생성·검증 통과 |
| FR-2 | `MCPClientFactory`가 streamable HTTP 세션 생성 지원 | `create_session()`이 STREAMABLE_HTTP에서 `streamablehttp_client` 경유 `ClientSession` yield |
| FR-3 | 주입형 `MCPTimeoutConfig`(connect/read/total) | 각 transport 세션 생성/호출에 분리된 타임아웃 반영 |
| FR-4 | 주입형 `MCPAuthConfig`(Bearer/커스텀 헤더) | 생성된 세션 요청 헤더에 `Authorization` 등 병합 |
| FR-5 | `MCPRetryPolicy`(max_retries, base/factor/max backoff) — 도메인 순수 함수 | `compute_backoff(attempt)` 단조 증가·상한 보장, 재시도성 분류 규칙 정의 |
| FR-6 | `MCPCallClient.list_tools(request_id)` | 설정된 서버의 tool 목록 VO 반환 |
| FR-7 | `MCPCallClient.call_tool(name, arguments, request_id)` | `MCPToolResult` 반환, 일시 실패 시 정책대로 재시도 후 최종 결과/예외 |
| FR-8 | SSE 서버를 `MCPCallClient`로 동일 호출 | SSE/HTTP가 동일 메서드 시그니처로 동작 |

### 3.2 Non-Functional Requirements

| ID | 요구사항 |
|----|----------|
| NFR-1 (Arch) | DDD 준수: 도메인(VO/Policy)은 외부 의존 0, 호출 코어는 infrastructure, LangChain import 금지. `verify-architecture` 통과 |
| NFR-2 (Log) | LOG-001 준수: 모든 호출에 `request_id` 포함 구조화 로그, 실패 시 스택 트레이스 포함. `verify-logging` 통과 |
| NFR-3 (TDD) | 구현 전 테스트 작성, mock 세션으로 네트워크 비의존. `verify-tdd` 통과 |
| NFR-4 (Config) | 하드코딩 금지 — 기본 타임아웃/재시도 값은 `src/config` 또는 정책 상수로 (CLAUDE.md §3) |
| NFR-5 (Quality) | 함수 40줄·if 중첩 2단계 이내, 명시적 타입(pydantic/typing) |

---

## 4. 제안 모듈 구조 (High-level, 상세는 Design 단계)

```
domain/mcp/
  value_objects.py   (+) MCPTransport.STREAMABLE_HTTP
                     (+) StreamableHTTPServerConfig
                     (+) MCPTimeoutConfig(connect, read, total)
                     (+) MCPAuthConfig(scheme="Bearer", token, extra_headers)
                     (~) MCPServerConfig.streamable_http: Optional 필드 추가
  policy.py          (+) MCPRetryPolicy(max_retries, base_backoff, factor,
                         max_backoff) + compute_backoff()/is_retryable()

infrastructure/mcp/
  client_factory.py  (~) _streamable_http_session() 추가,
                         타임아웃/auth 헤더 주입 경로 확장
  call_client.py     (+) MCPCallClient  ← 이번 사이클 핵심 산출물
                         __init__(config, *, timeout, auth, retry, logger)
                         async list_tools(request_id) -> list[MCPToolDescriptor]
                         async call_tool(name, arguments, request_id) -> MCPToolResult
```

> `MCPCallClient`는 호출당 `MCPClientFactory.create_session()`(stateless)을 사용하고, `MCPRetryPolicy`로 재시도 루프를 감싼다. 결과는 기존 `MCPToolResult` VO 재사용. `MCPToolDescriptor`(name/description/input_schema)는 신규 경량 VO 또는 기존 구조 재사용 여부를 Design에서 확정한다.

---

## 5. Test Strategy (TDD 개요)

- **도메인 단위테스트**: `MCPRetryPolicy.compute_backoff` 경계(attempt 0..n, 상한), `is_retryable` 분류, 설정 VO 검증(필수 필드/타임아웃 음수 거부), `MCPServerConfig.get_transport_config()`의 STREAMABLE_HTTP 분기.
- **인프라 단위테스트**: `MCPCallClient`를 mock `ClientSession`(또는 `MCPClientFactory.create_session` patch)로 검증 — list_tools/call_tool happy path, 타임아웃 주입 반영, auth 헤더 병합, 재시도(2회 실패 후 성공 / 한도 초과 시 예외), SSE·HTTP 동일 시그니처.
- **네트워크 비의존**: 실제 소켓 연결 금지, 전부 mock.
- **Windows 주의**: 교차 실행 시 이벤트 루프 teardown 산발 실패가 알려져 있어, 본 모듈 테스트는 **격리 실행**으로 회귀 판정한다(참조: 메모리 `backend-test-eventloop-flakiness`). `pytest.mark.asyncio` 사용 시 루프 스코프 확인.

---

## 6. Milestones

| # | 단계 | 산출물 |
|---|------|--------|
| M1 | 도메인 확장 | transport enum/VO/`MCPRetryPolicy` + 도메인 테스트 |
| M2 | Factory 확장 | streamable HTTP 세션 + 타임아웃/헤더 주입 + 테스트 |
| M3 | `MCPCallClient` | 호출 코어 + 재시도 루프 + 로깅 + 테스트 |
| M4 | 검증 | `verify-architecture`/`verify-logging`/`verify-tdd`, Gap analysis(`/pdca analyze`) |

---

## 7. Risks & Mitigations

| 리스크 | 영향 | 완화 |
|--------|------|------|
| `mcp` SDK의 streamablehttp 시그니처/반환 형태 가정 오류 | Factory 구현 재작업 | Design 단계에서 `streamablehttp_client` 실제 시그니처 확인 후 고정 |
| 동기 컨텍스트에서의 호출(기존 `_run`이 `run_until_complete` 사용) | 이벤트 루프 충돌 | 본 코어는 **async-first**로 설계, 동기 래핑은 out of scope(후속) |
| `SSEServerConfig.timeout` 단일값 ↔ 신규 `MCPTimeoutConfig` 매핑 모호 | 기존 SSE 동작 변경 위험 | 단일값→total로 매핑하는 호환 규칙을 Design에서 명문화, 기존 테스트 보존 |
| 재시도가 비멱등 tool에 부작용 | 중복 실행 | 기본 `max_retries`는 보수적(예: 연결 단계 한정), tool 실행 재시도는 옵트인 정책으로 분리 검토 |
| Windows 이벤트 루프 teardown flakiness | 테스트 오탐 | 격리 실행으로 회귀 판정(§5) |

---

## 8. 영향 범위 / 후속 작업

- **이번 사이클 변경 파일(예상)**: `domain/mcp/value_objects.py`, `domain/mcp/policy.py`, `infrastructure/mcp/client_factory.py`, 신규 `infrastructure/mcp/call_client.py`, 대응 `tests/`.
- **무변경 보장**: `MCPToolAdapter`, `MCPToolRegistry`, `MCPToolUseCase`, `mcp_registry/*`, `ToolFactory`.
- **후속(별도 PDCA)**: ① `MCPToolAdapter`를 `MCPCallClient` 소비로 리팩토링(LangGraph), ② `MCPToolLoader` transport 선택 확장, ③ 동기 호출 래퍼/세션 풀링.

---

## 9. Open Questions (Design 단계에서 확정)

1. `MCPToolDescriptor`를 신규 VO로 둘지, 기존 `mcp` 타입을 그대로 노출할지.
2. 재시도 대상 범위: **연결 단계만** vs **tool 실행 포함**(멱등성 플래그 도입 여부).
3. 기본 타임아웃/재시도 상수의 소재: `src/config.settings` vs `MCPConnectionPolicy` 상수.
4. auth 헤더와 `SSEServerConfig.headers`/HTTP headers의 병합 우선순위 규칙.
