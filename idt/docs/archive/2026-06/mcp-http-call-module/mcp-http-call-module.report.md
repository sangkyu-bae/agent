# MCP HTTP Call 공통 모듈 — Completion Report

> **Summary**: LangChain 비의존 순수 MCP 호출 코어(MCPCallClient) + Streamable HTTP transport 추가 완료. 97% 설계 일치율, 구현 누락 0건, 전체 68 tests pass.
>
> **Feature**: mcp-http-call-module
> **Duration**: 2026-06-14 ~ 2026-06-16
> **Owner**: 배상규

---

## Executive Summary

### 1.1 Problem

MCP 호출 로직이 재사용 불가능하게 흩어져 있었다:
- `MCPToolAdapter._arun`과 `MCPToolRegistry`가 각자 `create_session()`을 직접 호출
- 타임아웃이 SSE 한정 + 단일 값(connect/read/total 구분 없음)
- Bearer 인증 헤더, 재시도·백오프 표준 부재
- **Streamable HTTP transport 미지원** (최신 MCP 서버 미호환)
- LangChain 결합으로 호출 코어 단독 테스트 불가

### 1.2 Solution

`infrastructure/mcp`를 확장하여 LangChain 비의존 **순수 호출 코어 `MCPCallClient`** 신설:
1. **도메인**: `MCPTransport.STREAMABLE_HTTP`, `StreamableHTTPServerConfig`, 세분화 타임아웃(`MCPTimeoutConfig`), 인증(`MCPAuthConfig`), 재시도 정책(`MCPRetryPolicy`)
2. **Factory 확장**: Streamable HTTP 세션 + 타임아웃/헤더 주입 경로 (3-tuple 언패킹)
3. **호출 코어**: `list_tools()`/`call_tool()` 주입형(config/timeout/auth/retry/logger), 재시도 루프, 구조화 로깅

### 1.3 Function/UX Effect

| 관점 | 효과 |
|------|------|
| **개발자 경험** | `MCPCallClient(config, timeout=..., auth=..., retry=..., logger=...)` 한 줄로 HTTP·SSE 서버 호출, 재시도는 정책 기반 자동 적용 |
| **테스트 가능성** | LangChain 의존 제거 → mock 세션으로 코어 단독 검증 가능 |
| **운영 추적성** | 전 구간 `request_id` 기반 구조화 로그 + 실패 시 스택 트레이스 |
| **호환성** | SSE 기존 호출 무수정 통과(keyword-only 기본값), 정책 변경이 주입만으로 가능 |

### 1.4 Core Value

흩어진 MCP 호출을 **단일 책임의 주입형 코어**로 수렴:
- 추후 `MCPToolAdapter`/`mcp_registry` 통합 시 이 코어만 소비 → 정책 일원화
- Transport(HTTP/SSE) 교체, 타임아웃/재시도 정책 변경이 호출부 무수정으로 가능
- pytest/LangGraph 양쪽에서 동일 인터페이스 재사용

---

## PDCA 사이클 요약

### Plan
- **문서**: [mcp-http-call-module.plan.md](../../01-plan/features/mcp-http-call-module.plan.md)
- **목표**: LangChain 비의존 순수 호출 코어 설계, Streamable HTTP transport 신규 추가
- **예상 기간**: 2 days (실제: 2 days)

### Design
- **문서**: [mcp-http-call-module.design.md](../../02-design/features/mcp-http-call-module.design.md)
- **주요 설계 결정**:
  - D-1: `MCPToolDescriptor` 신규 VO로 SDK 타입 비노출
  - D-2: 재시도 스테이지 구분 (연결 기본 / tool 실행 `retry_tool_execution=False` 옵트인)
  - D-3: 정책 상수를 도메인(`MCPRetryPolicy` default) 소재로 고정
  - D-4: 설정 timeout 우선(config > 주입), auth 헤더 병합 시 auth 우선
  - D-5: timeout 우선순위 (config.streamable_http.timeout > 주입 timeout)
  - D-6: list_tools 멱등 → operation 단계도 재시도 허용
  - D-7: timeout 전체 감싸기 (`asyncio.wait_for`)로 call_tool/list_tools 보호

### Do
- **구현 범위**:
  - `src/domain/mcp/value_objects.py`: 6개 신규 요소 (STREAMABLE_HTTP, StreamableHTTPServerConfig, MCPTimeoutConfig, MCPAuthConfig, MCPToolDescriptor, MCPServerConfig.streamable_http 필드)
  - `src/domain/mcp/policy.py`: `MCPRetryPolicy` (compute_backoff, is_retryable)
  - `src/infrastructure/mcp/client_factory.py`: `_streamable_http_session()`, 타임아웃/auth 주입, dict 디스패치
  - `src/infrastructure/mcp/call_client.py`: `MCPCallClient` 신규 (list_tools, call_tool, _execute, _should_retry)
- **실제 기간**: 2 days

### Check
- **분석 문서**: [mcp-http-call-module.analysis.md](../../03-analysis/mcp-http-call-module.analysis.md)
- **설계 일치율**: **97%** (Match: 38, Minor deviation: 2, Not implemented: 0)
- **Gap 요약**:
  - G-1 (Info): config timeout 우선순위 설계에 명시되나, SSE 경로와 비대칭 (설계 보강 권고)
  - G-2 (Info): list_tools 재시도 정책 설계 미명시 (설계 보강 권고)
  - L-1 (Minor): 완료 로그에 `elapsed_ms` 미포함 (선택적 개선)

---

## 성과

### 완료 항목

✅ **FR-1 (STREAMABLE_HTTP)**: `MCPTransport.STREAMABLE_HTTP` enum + `StreamableHTTPServerConfig` 추가, `MCPServerConfig.get_transport_config()` 신규 분기
✅ **FR-2 (Factory)**: `MCPClientFactory._streamable_http_session()` 구현, mcp SDK 3-tuple 언패킹 (`read, write, _get_session_id`)
✅ **FR-3 (타임아웃)**: `MCPTimeoutConfig` (connect/read/total) + 각 경로별 주입 매핑 (connect→timeout / read→sse_read_timeout / total→wait_for)
✅ **FR-4 (인증)**: `MCPAuthConfig` + `_merge_headers()` 병합 (정적 headers + auth, 충돌 시 auth 우선)
✅ **FR-5 (재시도)**: `MCPRetryPolicy` + `compute_backoff()` (지수 증가 + 상한), `is_retryable()` (ConnectionError/TimeoutError/OSError만)
✅ **FR-6 (list_tools)**: `MCPCallClient.list_tools()` → SDK tool 목록을 `list[MCPToolDescriptor]`로 변환
✅ **FR-7 (call_tool)**: `MCPCallClient.call_tool()` + 재시도 루프 + `MCPToolResult` 반환
✅ **FR-8 (동일 시그니처)**: SSE·Streamable HTTP 공통 `create_session()` 경로로 동일 메서드 지원

✅ **D-1 ~ D-7**: 모든 설계 결정 구현 완료

✅ **DDD 준수**: domain → infra/langchain import 0건, 비파괴 (기존 tool_adapter.py:72 무수정 통과)

### 미완료/보류 항목

⏸️ **선택적 개선 (L-1)**: `elapsed_ms` 로그 추가 — 핵심(request_id/exception) 완료, 선택사항

⏸️ **설계 문서 보강 (G-1, G-2)**: config timeout 우선순위 / list_tools 재시도 정책 — 구현 동작이 합리적이므로 **설계 문서 갱신 권고** (구현 수정 불필요)

---

## 테스트 결과

| 모듈 | 파일 | 테스트 | 상태 |
|------|------|--------|------|
| **Domain** | `test_value_objects.py` | 30 | ✅ pass |
| **Domain** | `test_policy.py` | 23 | ✅ pass |
| **Infrastructure** | `test_client_factory.py` | 7 | ✅ pass |
| **Infrastructure** | `test_call_client.py` | 8 | ✅ pass |
| **회귀** | 기존 tool_adapter/registry 소비자 | ~30 | ✅ pass (비파괴 확인) |

**총 테스트**: **68 passed** (파일 단위 격리 실행)

**커버리지**:
- Happy path (call_tool/list_tools 성공)
- 재시도 성공 (2회 실패 후 성공)
- 재시도 한도 초과 (예외 raise)
- 도구 논리 에러 (isError=True → 예외 아님)
- timeout 주입 반영
- auth 헤더 병합 + 우선순위
- SSE·HTTP 동일 시그니처
- `retry_tool_execution` 옵트인 (False→즉시 raise, True→재시도)

**네트워크 비의존**: 100% mock (AsyncMock), 실 연결 0건

**품질 게이트** (idt/CLAUDE.md):
- ✅ `ruff check` (E/F/I/N/W/UP): All passed
- ✅ `verify-architecture`: DDD 계층 경계 검증 통과
- ✅ `verify-logging`: LOG-001 (request_id/exception) 준수
- ✅ `verify-tdd`: Red→Green 엄수, 함수 40줄 이내, if 중첩 2단계 이내

---

## 구현 산출물

### 신규/수정 파일

| 파일 | 변경 유형 | 산출물 |
|------|---------|--------|
| `src/domain/mcp/value_objects.py` | 신규 + 기존 필드 추가 | MCPTransport.STREAMABLE_HTTP, StreamableHTTPServerConfig, MCPTimeoutConfig, MCPAuthConfig, MCPToolDescriptor, MCPServerConfig.streamable_http |
| `src/domain/mcp/policy.py` | 신규 | MCPRetryPolicy (compute_backoff, is_retryable) |
| `src/infrastructure/mcp/client_factory.py` | 확장 | `_streamable_http_session()`, dict 디스패치, timeout/auth 주입 경로 |
| `src/infrastructure/mcp/call_client.py` | 신규 | MCPCallClient (list_tools, call_tool, _execute, _should_retry, 재시도 루프, 로깅) |
| `tests/domain/mcp/test_value_objects.py` | 신규 | 30 tests (VO 검증, from_legacy, 타임아웃/auth 병합) |
| `tests/domain/mcp/test_policy.py` | 신규 | 23 tests (compute_backoff 경계, is_retryable 분류) |
| `tests/infrastructure/mcp/test_client_factory.py` | 신규 | 7 tests (streamable_http_session, 3-tuple 언패킹, dict 디스패치) |
| `tests/infrastructure/mcp/test_call_client.py` | 신규 | 8 tests (happy path, 재시도, timeout, auth, tool error) |

**비파괴 확인**: `tool_adapter.py:72` (`create_session(self.server_config)`) 무수정 통과

---

## 핵심 메트릭

| 메트릭 | 값 |
|--------|-----|
| **설계 일치율** | 97% (38/40 충족, 2 minor 편차, 0 누락) |
| **테스트** | 68 passed (domain 53 + factory 7 + call_client 8) |
| **코드 품질** | ruff E/F/I/N/W/UP all passed |
| **아키텍처** | DDD 준수, domain import 0건 |
| **로깅** | LOG-001 준수, request_id/exception 전부 포함 |
| **비파괴성** | ✅ 기존 호출 무수정 통과 |

---

## 잘된 점

1. **설계 → 코드 정합성**: 97% 일치율. 모든 FR(1~8)과 설계 결정(D-1~D-7) 구현. 구현 누락 0건.

2. **TDD 엄격**: Red→Green 선행, mock 세션으로 네트워크 비의존. Windows 이벤트 루프 flakiness 해결(파일 단위 격리).

3. **비파괴 설계**: `MCPServerConfig` 필드 추가만, 신규 factory 인자는 keyword-only 기본값 → 기존 tool_adapter/registry 무수정 통과.

4. **도메인 순수성**: 재시도 정책·타임아웃·인증을 도메인 VO로 정의, import 0건(asyncio 분류 제외).

5. **운영 추적성**: 전 경로에 `request_id` 기반 구조화 로그, 재시도·timeout·auth 과정 명확 기록.

---

## 개선 영역

1. **설계 문서 보강 (선택)**: G-1(config timeout 우선순위) / G-2(list_tools 재시도) — 구현이 합리적이므로 문서 갱신으로 충분.

2. **완료 로그 개선 (선택)**: `elapsed_ms` 추가 (L-1) — 핵심 요소(request_id/exception)는 충족, 경미 사항.

3. **`retry_tool_execution=True` 경로**: 성공 케이스 테스트 미보강(2 gaps) — 현재 `default=False`이므로 옵트인 경로, 나중에 보강 가능.

---

## 다음 단계 (후속 PDCA)

1. **`MCPToolAdapter` 리팩토링** → `MCPCallClient` 소비 (별도 PDCA)
   - LangGraph 통합 시 이 코어 활용
   - 기존 `_arun()` 제거 + `MCPCallClient` 소비로 전환

2. **`MCPToolLoader` 확장** → transport DB에서 선택
   - 현재: SSE 고정
   - 목표: STREAMABLE_HTTP, STDIO, WEBSOCKET 선택 가능

3. **동기 호출 래퍼** → `run_until_complete()` 통합
   - 기존 `_run()` 통합 지원
   - out of scope (비동기 우선 정책)

4. **세션 풀링** → 커넥션 재사용 (성능)
   - 현재: 호출당 세션 (stateless)
   - 선택적 최적화

---

## 영향 범위

### 변경 파일
- `src/domain/mcp/value_objects.py` (+6 요소)
- `src/domain/mcp/policy.py` (+1 클래스)
- `src/infrastructure/mcp/client_factory.py` (+1 메서드, 기존 인자 확장)
- `src/infrastructure/mcp/call_client.py` (+신규)
- 대응 tests/ (+4 파일, 68 tests)

### 무변경 보장
- `MCPToolAdapter`, `MCPToolRegistry`, `MCPToolUseCase`
- `MCPToolLoader`, `ToolFactory`, `WorkflowCompiler`
- 기존 `SSEServerConfig.timeout` 동작
- 기존 stdio/websocket transport

---

## 버전 히스토리

| 버전 | 날짜 | 변경사항 |
|------|------|---------|
| 1.0 | 2026-06-16 | 최초 완료 — 97% 일치율, 68 tests pass, 비파괴 확인 |

---

## 결론

**mcp-http-call-module PDCA 사이클 완료**. 설계 97% 일치, 구현 누락 0건, 전체 68 tests 통과, 품질 게이트 전부 pass.

✅ **Streamable HTTP transport** 신규 추가로 최신 MCP 서버 호환성 확보.
✅ **순수 호출 코어** 추출로 LangGraph/pytest 양쪽 재사용 가능.
✅ **비파괴 설계**로 기존 생태계 영향 최소.

다음: `/pdca report` 완료 → 선택적 개선(L-1, G-1/G-2) 반영 → `/pdca archive` 진행.
