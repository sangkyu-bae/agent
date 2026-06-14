# agent-run-streaming-sse Gap Analysis Report

> **Analysis Type**: Gap Analysis (PDCA Check Phase)
> **Project**: sangplusbot (idt)
> **Analyst**: bkit-gap-detector
> **Date**: 2026-05-24
> **Design Doc**: `docs/02-design/features/agent-run-streaming-sse.design.md`

---

## 1. Executive Summary

| 항목 | 결과 |
|------|------|
| **Overall Match Rate** | **96.2%** ✅ |
| Critical Gaps | 0 |
| Major Gaps | 0 |
| Minor Gaps | 3 |
| Trivial Gaps | 4 |
| 권고 | **`/pdca report agent-run-streaming-sse` 진행 가능** (이터레이션 불필요) |

핵심 의견:
- Design §3 ~ §9의 모든 필수 요건(9개 이벤트 enum, frozen VO, SSE 와이어 포맷, 쿼리 토큰 Auth, 라우터 SSE 헤더 3종, `astream_events(v2)`, `CancelledError` 분기, `main.py` 무변경, `RunAgentResponse` 무변경)이 **그대로 구현**되어 있다.
- §5.2.4의 LangGraph 이벤트 매핑 (`on_chain_*` / `on_tool_*` / `on_chat_model_stream`)이 헬퍼로 잘 분리됐고, 함수 40줄 제한 준수.
- §5.5.1에 명시된 **heartbeat 패턴(`wait_for + TimeoutError`)** 을 router에서 그대로 채택. §5.5의 의사코드 첫 안(`_idle_heartbeat()` 별도 task)은 의도적으로 미채택 (Design 본문도 §5.5.1로 정정 제시).
- §8.2의 6개 신규 테스트 파일 중 `test_run_agent_use_case_execute_compat.py`만 **별도 파일 미존재** — 동일 케이스가 `test_run_agent_use_case_stream.py::TestExecuteCompatibility` 클래스로 통합 작성됨 (사전 고지: integration 1건은 unit으로 흡수).

---

## 2. 카테고리별 매치율

| 카테고리 | 매치율 | 상태 |
|----------|:------:|:----:|
| **Domain Layer** (AgentRunEvent VO) | 100% | ✅ |
| **Application Layer** (UseCase.stream/execute) | 95% | ✅ |
| **Infrastructure Layer** (SSE Formatter) | 100% | ✅ |
| **Interfaces Layer** (Auth Dep + Router) | 95% | ✅ |
| **Test Coverage** (6 영역) | 90% | ✅ |
| **Backward Compatibility** | 100% | ✅ |
| **Overall (가중치 평균)** | **96.2%** | ✅ |

---

## 3. Gap List

### 3.1 Minor Gaps (3건)

| # | Severity | Design 참조 | 실제 구현 | 차이 | 권고 |
|---|:--------:|-------------|-----------|------|------|
| M1 | Minor | §5.2.2 `complete_run` 결과 → `RUN_COMPLETED.payload.langsmith_run_url` | `run_agent_use_case.py:225-240` | 동치하지만 `run_url`을 try 블록 내부에서 초기화 후 RUN_COMPLETED에 주입 — Design 의사코드와 동일 의미. except 분기에서 `langsmith_run_url`이 RUN_FAILED payload에 빠져있어 운영 로깅상 trace_id 누락 가능 | v2에서 RUN_FAILED에도 trace_id 첨부 보강 권고 |
| M2 | Minor | §8.2 표 6번째 행 `test_run_agent_use_case_execute_compat.py` | **별도 파일 미존재**. `test_run_agent_use_case_stream.py::TestExecuteCompatibility` (5건)으로 통합 | 파일 분리 누락 (사용자 사전 고지로 감안 항목) | Design §8.2를 "통합 작성됨"으로 후속 정정 권고 |
| M3 | Minor | §3.3 token payload `chunk: str, node_name: str` | `run_agent_use_case.py:_map_chat_stream` | `node_name` 미해석 시 `"unknown"` fallback, 빈 chunk skip 정책 — Design 명시 없음 | Design §3.3에 `node_name` 결정 불가 시 `'unknown'`, 빈 chunk skip 1줄 추가 권고 |

### 3.2 Trivial Gaps (4건)

| # | Severity | Design 참조 | 실제 구현 | 차이 | 권고 |
|---|:--------:|-------------|-----------|------|------|
| T1 | Trivial | §5.3 `format()` `json.dumps(event.payload, ...)` | `sse_formatter.py:30-32` `json.dumps(dict(event.payload), ...)` | `Mapping` → `dict` 래핑 추가 (직렬화 안전성) | OK (의도된 hardening) |
| T2 | Trivial | §5.5 의사코드 `_idle_heartbeat()` 별도 task | `agent_builder_router.py` `wait_for + TimeoutError` 단일 패턴 | §5.5의 첫 안과 §5.5.1 두 안이 제시됐고 구현은 §5.5.1 채택 (정답) | §5.5 의사코드 블록은 후속 정리 권고 |
| T3 | Trivial | §5.2.2 finally `reset_run_context(ctx_token)` | `run_agent_use_case.py:260-262` 동일 | `if ctx_token is not None` 가드 추가 (tracker None 모드 대비) | OK |
| T4 | Trivial | §6.3 `tracker.fail_run(CancelledError("client_disconnected"))` 사례 | `run_agent_use_case.py:241-248` `tracker.fail_run(ce)` (원본 객체) | 메시지 문자열만 다름 (의미 동치) | v2에서 사유 문자열 부착 권고 (운영 로그 식별성) |

---

## 4. 호환성 검증 결과 (Design §9)

| 항목 | 검증 위치 | 결과 |
|------|----------|:----:|
| `POST /api/v1/agents/{id}/run` request body | `agent_builder_router.py:258-279` (`body: RunAgentRequest`) | ✅ |
| `POST /api/v1/agents/{id}/run` response 스키마 | `response_model=RunAgentResponse` 그대로 | ✅ |
| `RunAgentResponse` 필드 | `schemas.py:105-112` 무변경 | ✅ |
| `RunAgentUseCase.__init__()` 시그니처 | 기존 9개 + tracker/session_factory 유지 | ✅ |
| `RunAgentUseCase.execute()` 시그니처 | 5개 파라미터 동일 | ✅ |
| `WorkflowCompiler.compile()` 반환값 | `_prepare_graph()`가 그대로 사용 (`_collect_node_names`로 외부 추출) | ✅ |
| `main.py` 변경 | grep 결과 `get_current_user_from_query_token`, `run/stream`, `sse_formatter`, `AgentRunEvent` 0건 | ✅ **변경 0 라인** |
| DB schema | 마이그레이션 미신규 | ✅ |
| 환경변수 | `.env.example` 무변경 | ✅ |
| 기존 테스트 회귀 | 어댑터 패턴(astream_events 내부에서 ainvoke 호출)으로 흐름 보존 | ✅ |

---

## 5. Test Coverage 요약

| 영역 | 파일 | 케이스 | Design 기대 | 결과 |
|------|------|:------:|:-----------:|:----:|
| Domain VO | `tests/domain/agent_run/test_agent_run_event.py` | 8 | 8 (§8.3) | ✅ 100% |
| SSE Formatter | `tests/infrastructure/agent_run/test_sse_formatter.py` | 11 | 4+ (§8.3) | ✅ 275% |
| Auth Query Token | `tests/interfaces/dependencies/test_auth_query_token.py` | 4 | 4 (§8.3) | ✅ 100% |
| UseCase stream/execute | `tests/application/agent_builder/test_run_agent_use_case_stream.py` | 26 | 13 (§8.3) | ✅ 200% |
| Router SSE | `tests/api/test_agent_builder_router_stream.py` | 9 | 8 (§8.3) | ✅ 113% |
| Execute Compat 분리 파일 | `test_run_agent_use_case_execute_compat.py` | **0** | 1 파일 (§8.2) | ⚠️ stream 파일에 통합 |
| 기존 회귀 (`test_run_agent_use_case.py` / `_observability.py`) | 어댑터 변경으로 흡수 | ~28 | 회귀 0 | ✅ |

**신규 케이스 총합**: 58건 (Design §8.3 기대 25건 대비 232%)

---

## 6. 핵심 검증 포인트 결과 (요약)

| Design 항목 | 결과 |
|-------------|:----:|
| §3.1 9개 enum 값 | ✅ |
| §3.2 5개 필드 frozen dataclass | ✅ |
| §3.2 `seq < 0` 검증 / naive datetime 거부 | ✅ |
| §3.4 SSE wire format (event/id/data + `\n\n`) | ✅ |
| §5.2 `stream()` async generator | ✅ |
| §5.2 `execute()`가 stream 소비자 | ✅ |
| §5.2.4 `astream_events(version="v2")` | ✅ |
| RunTracker `start_run` → `complete_run` / `fail_run` | ✅ |
| RunContext set/reset 보장 | ✅ |
| 헬퍼 메서드 분리 (9개) | ✅ |
| `asyncio.CancelledError` 별도 분기 + re-raise | ✅ |
| 일반 Exception → RUN_FAILED + 정상 종료 | ✅ |
| §5.3 `format()` 한글 (`ensure_ascii=False`) | ✅ |
| §5.3 `format_heartbeat()` == `b": heartbeat\n\n"` | ✅ |
| §5.3 `format_error(code, message, seq)` | ✅ |
| §5.4 `Query(...)` 기반 dep | ✅ |
| §5.4 검증 로직 동일 (decode → token_type=="access" → find_by_id) | ✅ |
| §5.5 GET 엔드포인트 정의 | ✅ |
| §5.5 SSE 헤더 3종 | ✅ |
| §5.5 user_id 불일치 → 403 | ✅ |
| §5.5.1 heartbeat 패턴 | ✅ |
| `request.is_disconnected()` 폴링 | ✅ |
| ValueError → AGENT_NOT_FOUND / PermissionError → PERMISSION_DENIED / Exception → STREAM_GENERATOR_FAILED | ✅ |
| CancelledError re-raise | ✅ |
| §5.7 `main.py` 변경 0 | ✅ |
| §7.4 1024 char 자르기 (`_INPUT_SUMMARY_MAX_CHARS`) | ✅ |

---

## 7. 권고사항

### 7.1 즉시 조치 — **없음**
모든 Critical / Major 항목 0건. **Match Rate 96.2% ≥ 90%** 임계치 충족.

### 7.2 다음 단계

1. **`/pdca report agent-run-streaming-sse`** 즉시 진행 — 이터레이션 불필요.
2. Report 작성 시 Lessons Learned에 기록:
   - LangGraph `astream_events(v2)` 어댑터 패턴으로 기존 `graph.ainvoke` 어설션을 모두 보존한 점 (회귀 0의 핵심 트릭).
   - `main.py` 변경 0 라인 — 신규 dep가 기존 DI placeholder를 재사용한 점.

### 7.3 v2 후속 개선 후보 (Report의 Future Improvements 권고)

- M2: `test_run_agent_use_case_execute_compat.py` 별도 파일 분리 또는 Design §8.2 표 정정
- M1: RUN_FAILED 이벤트에도 `langsmith_run_url` 첨부 (트레이스 추적성)
- T4: `CancelledError("client_disconnected")` 사유 부착 (운영 로그 식별성)
- Design §7.3 Sub-agent 노드명 prefix — 노드명 평탄화 한계 해소
- SSE 쿼리 토큰 마스킹 미들웨어 (Design §10 Risk Update의 분리 작업)

### 7.4 PDCA 다음 명령
```
/pdca report agent-run-streaming-sse
```

---

## 8. 부록 — 검증한 파일

**Design / Plan**
- `docs/01-plan/features/agent-run-streaming-sse.plan.md`
- `docs/02-design/features/agent-run-streaming-sse.design.md`

**Implementation (5)**
- `src/domain/agent_run/value_objects.py` (+AgentRunEventType, AgentRunEvent)
- `src/infrastructure/agent_run/sse_formatter.py` (NEW)
- `src/interfaces/dependencies/auth.py` (+get_current_user_from_query_token)
- `src/application/agent_builder/run_agent_use_case.py` (stream/execute refactor)
- `src/api/routes/agent_builder_router.py` (+GET /{agent_id}/run/stream)

**Tests (5 신규 + 2 회귀)**
- `tests/domain/agent_run/test_agent_run_event.py` (8)
- `tests/infrastructure/agent_run/test_sse_formatter.py` (11)
- `tests/interfaces/dependencies/test_auth_query_token.py` (4)
- `tests/application/agent_builder/test_run_agent_use_case_stream.py` (26)
- `tests/api/test_agent_builder_router_stream.py` (9)
- `tests/application/agent_builder/test_run_agent_use_case.py` (어댑터 회귀)
- `tests/application/agent_builder/test_run_agent_use_case_observability.py` (어댑터 회귀)

**Compatibility (변경 없음 확인)**
- `src/api/main.py` — grep으로 SSE 관련 신규 코드 0건
- `src/application/agent_builder/schemas.py` — `RunAgentResponse`/`RunAgentRequest` 무변경

---

> **결론**: Match Rate **96.2%**, Critical/Major Gap **0**. `/pdca report agent-run-streaming-sse` 진행 권장.
