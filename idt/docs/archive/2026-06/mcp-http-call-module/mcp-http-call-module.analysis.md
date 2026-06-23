# MCP HTTP Call 공통 모듈 — Gap Analysis (PDCA Check)

> **Feature**: mcp-http-call-module
> **Date**: 2026-06-16
> **Design Doc**: [mcp-http-call-module.design.md](../02-design/features/mcp-http-call-module.design.md)
> **Analyzer**: bkit:gap-detector
> **Match Rate**: **97%** (≥90% → Report 진행 가능, Act/iterate 불필요)

---

## 1. 요약

설계 문서와 구현 코드가 매우 잘 일치한다. FR-1~FR-8, 설계 결정 4건, DDD 레이어 규칙, LOG-001 핵심 요건이 모두 충족되었으며 **구현 누락(Not implemented) 0건**이다. 경미한 편차 2건(설계 미명세 동작을 구현이 합리적으로 보강)과 선택적 로깅 개선 1건만 존재한다.

```
Overall Match Rate: 97%
  ✅ Match:            38 items
  ⚠️ Minor deviation:   2 items (설계 미명세 — 구현 보강)
  ❌ Not implemented:    0 items
```

| 카테고리 | 점수 | 상태 |
|----------|:----:|:----:|
| Design Match (FR/결정/인터페이스/에러) | 97% | ✅ |
| Architecture Compliance (DDD §9) | 100% | ✅ |
| Convention Compliance (§3/§10) | 98% | ✅ |
| Test Coverage (§8) | 95% | ✅ |
| Logging (LOG-001 §6.2) | 90% | ⚠️ |

---

## 2. FR / 설계결정 검증 (전부 충족)

| 항목 | 위치 | 상태 |
|------|------|------|
| FR-1 STREAMABLE_HTTP + StreamableHTTPServerConfig | value_objects.py:18, 80-87 | ✅ |
| FR-2 streamablehttp_client 3-tuple 언패킹 | client_factory.py:156-161 `as (read, write, _get_session_id)` | ✅ |
| FR-3 timeout 매핑 connect→timeout / read→sse_read_timeout / total→wait_for | factory:159-160, call_client:146-148 | ✅ |
| FR-4 auth 헤더 병합, 충돌 시 auth 우선 | factory `_merge_headers`:27-35 (`.update`) | ✅ |
| FR-5 MCPRetryPolicy + compute_backoff/is_retryable | policy.py:70-111 | ✅ |
| FR-6 list_tools → list[MCPToolDescriptor] | call_client.py:69-81 | ✅ |
| FR-7 call_tool → MCPToolResult + 재시도 | call_client.py:83-101 | ✅ |
| FR-8 SSE/HTTP 동일 시그니처 | 공통 create_session 경로 | ✅ |
| 결정#1 MCPToolDescriptor 신규 VO | value_objects.py:134-141 | ✅ |
| 결정#2 재시도 스테이지 구분(연결 기본/tool 옵트인) | call_client.py:167-183 `_should_retry` | ✅ |
| 결정#3 정책 상수 도메인 소재 | policy.py:77-84 Field default | ✅ |
| 결정#4 isError → is_error 결과(예외 X) | call_client.py:103-117 | ✅ |

**DDD**: domain → infra/langchain import **0건**. `policy.py`의 `asyncio` import는 설계 §9.3이 명시 허용한 stdlib 타입 분류용(위반 아님).
**비파괴**: `tool_adapter.py:72`의 기존 `create_session(self.server_config)` 호출은 신규 keyword-only 기본값 덕에 무수정 통과 확인.

---

## 3. Gap 목록 (Missing 0 / Info 2 / Minor 1)

| ID | 심각도 | 위치 | 설계 기대 | 실제 | 권고 |
|----|--------|------|-----------|------|------|
| G-1 | 🟢 Info | client_factory.py:153 | §4.2는 주입 `timeout`만 사용. config 자체 `streamable_http.timeout`과의 우선순위 규칙 없음 | `effective_timeout = http_cfg.timeout or timeout` (config 우선) — SSE 경로와 비대칭 | 설계 §4.2/§4.4에 "config timeout 우선" 명문화 또는 SSE와 통일. 구현 수정 불필요 |
| G-2 | 🟢 Info | call_client.py:79-81 | 재시도 스테이지 구분을 call_tool 중심 기술, list_tools 정책 미명시 | list_tools는 멱등으로 보고 operation 단계도 재시도(`retry_operation=True`) | 설계 §4.1에 "list_tools 멱등 → operation 재시도 허용" 행 추가. 구현 수정 불필요 |
| L-1 | ⚠️ Minor | call_client.py:149 | §6.2 호출 완료 로그 필수 필드에 `elapsed_ms` | 완료 로그에 elapsed_ms 미포함(request_id/server/tool은 포함) | `time.perf_counter()`로 1줄 보강(선택). LOG-001 핵심(request_id/exception)은 충족 |

---

## 4. 테스트 커버리지 (§8)

설계 §8.2 핵심 케이스 전부 구현·네트워크 비의존(AsyncMock):
happy / 재시도 성공·한도초과 / 도구 isError / 비재시도 즉시 raise / tool 실행 재시도 옵트인 / timeout 주입 반영 / auth 병합 우선순위 / SSE·HTTP 동일 시그니처.
미커버 경미 항목: `retry_tool_execution=True` 성공 경로, G-1 config-timeout 우선 경로(설계에도 미명세).

> Windows `ProactorEventLoop` teardown flakiness로 다중 async 파일 동시 실행 시 teardown ERROR 산발 — 파일 단위 격리 실행으로 전부 통과 확인(메모리 `backend-test-eventloop-flakiness`).

---

## 5. 권고 액션

- **Immediate (24h)**: 없음 — 구현 누락/Critical 0건.
- **Short-term (선택)**: (1) 완료 로그 `elapsed_ms` 1줄 추가(L-1), (2) 설계 §4.2/§4.4에 timeout 우선순위 명문화(G-1), (3) 설계 §4.1에 list_tools 재시도 명시(G-2).
- **방향**: "Code is truth" — G-1/G-2는 구현 동작이 합리적이므로 **설계 문서를 구현에 맞춰 보강**하는 쪽 권고.
- **다음 단계**: Match Rate 97% ≥ 90% → `/pdca report mcp-http-call-module`.
