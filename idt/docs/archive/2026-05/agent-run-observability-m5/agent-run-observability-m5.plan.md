# Plan: agent-run-observability-m5

> Feature: Agent Run 운영 관측성 — **M5 (Tavily Retrieval + Admin Run List + Aggregate Index)**
> Created: 2026-05-21
> Status: Plan
> Task ID: AGENT-OBS-005
> Parent (M1): [agent-run-observability.plan.md](../../archive/2026-05/agent-run-observability/agent-run-observability.plan.md) (archived, 96%)
> Sibling (M2): [agent-run-observability-m2.plan.md](../../archive/2026-05/agent-run-observability-m2/agent-run-observability-m2.plan.md) (archived, 98%)
> Sibling (M3): [agent-run-observability-m3.plan.md](../../archive/2026-05/agent-run-observability-m3/agent-run-observability-m3.plan.md) (archived, 99%)
> Sibling (M4): [agent-run-observability-m4.plan.md](../../archive/2026-05/agent-run-observability-m4/agent-run-observability-m4.plan.md) (archived, 98%)

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | M4 완료로 5 read API + 1 PATCH + 5번째 테이블 `ai_retrieval_source` wiring(internal_document_search 전용)까지 채워졌지만, M4 §7.3에서 명시된 3건의 follow-up이 남아 있다: (1) `tavily_search` 호출은 여전히 `ai_retrieval_source`에 row 0건 — web 검색 근거를 사후 추적 불가, (2) 어드민이 run_id를 모르면 `GET /agents/runs/{run_id}` 호출 불가 — Run list/검색 API 부재, (3) `/admin/usage/by-node` 등 집계 API가 `ai_llm_call.created_at` 범위 스캔 시 적절한 인덱스 부재 — 데이터 누적 시 슬로우 우려. |
| **Solution** | **신규 마이그레이션 1건(V023) + 도메인 확장 1건 + 어드민 list API 1개 + Tavily adapter wiring 1건.** (a) `TavilySearchTool.search`에 best-effort `record_retrieval` 호출 추가 — `collection_name="tavily_web"` 고정 + `document_id`에 URL 저장(VARCHAR(150) → VARCHAR(2048) 확장은 Design에서 결정) + `metadata_json`에 `{title, raw_score}`. (b) `GET /api/v1/admin/runs?from=&to=&user_id=&status=&limit=&offset=` 신규 endpoint — `AgentRunRepository.list_runs(filters, pagination)` 추가 + `ListRunsUseCase`. (c) V023 마이그레이션 — `ai_llm_call.created_at` 단독 인덱스 추가 (`idx_llm_call_created`). step_id는 InnoDB FK 자동 인덱스로 이미 존재 가능성 ↑ — Design에서 `SHOW INDEX FROM ai_llm_call` 결과로 최종 확정. |
| **Function / UX Effect** | (1) **Tavily 답변 근거 추적**: 어드민이 한 run의 `ai_retrieval_source`에서 `collection_name='tavily_web'` 행을 골라 인용된 URL을 SQL JOIN 1줄로 확인. (2) **Run list 화면 PDCA 의존성 해소**: 어드민 대시보드가 별도 backend 변경 없이 `GET /admin/runs` 호출로 페이지네이션 + 필터(`status=FAILED`, `user_id=...`) 가능. (3) **집계 API 슬로우 사전 방지**: 데이터 누적 후 `/admin/usage/by-node` / `/users` / `/llm-models` latency 증가 시 인덱스 즉시 효과. (4) M4의 internal_document_search retrieval과 tavily retrieval이 같은 테이블에 누적되어 collection_name만 분기 — 어드민 화면이 통합 UI로 표시. |
| **Core Value** | **"외부 검색 = 동등 시민" 완성.** internal_document_search(RAG)와 tavily_search(web)가 영속화 측면에서 동등하게 취급되어 어드민이 "이 답변은 RAG 3 chunk + Web 2 URL 인용"같은 분석 가능. Run list API로 어드민 화면 PDCA의 backend 의존성 0 — 화면 PDCA가 100% 독립 진행 가능. 인덱스 사전 추가로 운영 안전 마진 확보. 1~2일 예상 (M4와 동일 패턴). |

---

## 1. 목적 (Why)

### 1-1. M1·M2·M3·M4 완료 후 남은 갭

| 영역 | M1~M4 상태 | M5에서 채울 것 |
|------|-----------|---------------|
| `ai_retrieval_source` (web search) | M4: internal_document_search 전용 wiring | Tavily web 검색 결과도 영속화 (collection_name 분기) |
| 어드민 Run list API | ❌ 미정의 (M4는 단건 detail만) | `GET /admin/runs?from=&to=&user_id=&status=&limit=&offset=` |
| `ai_llm_call.created_at` 단독 인덱스 | ❌ 부재 (composite index만 존재) | V023 — 단독 `created_at` 인덱스 추가 (집계 API 성능) |
| `ai_llm_call.step_id` 인덱스 | ⚠️ InnoDB FK 자동 인덱스 가능성 (확인 필요) | Design 단계 `SHOW INDEX` 결과로 결정 — 없으면 V023에 추가 |
| Run list 검색/필터링 화면 PDCA 의존성 | M4 단건 + UI 미존재 | Run list endpoint로 화면 PDCA 의존성 해소 |

### 1-2. 운영 니즈

- **Tavily 답변 책임 추적**: "이 web 검색 답변이 인용한 URL은?" → 현재는 답변 텍스트 안 `[출처: ...]` 외 DB 추적 길 없음. M5 후엔 SQL JOIN으로 즉시 확인
- **Failed run 디버깅**: 어드민이 "오늘 status=FAILED인 run 목록"을 한 화면에서 보고 각각 detail 클릭 → 현재는 run_id를 미리 알아야만 detail API 호출 가능
- **사용자별 운영 모니터링**: 특정 사용자의 최근 run 목록 — `user_id` 필터로 즉시 조회
- **집계 API 운영 마진**: `ai_llm_call` 데이터 누적 시 by-node/by-user 집계가 full scan으로 떨어지지 않게 사전 보장. 운영 1년 데이터(1M row 가정) 부담 회피
- **internal vs tavily 통합 분석**: 한 run 안에서 RAG 3건 + Tavily 2건 인용을 통합 트리로 표시 (M4 RunDetailResponse가 이미 retrievals[]로 받음 — M5는 데이터만 채우면 됨)

### 1-3. 비목표 (Non-Goals)

- 신규 `ai_*` 테이블 추가 (M1·M2·M3·M4 데이터 모델이 충분)
- Tavily 외 다른 web search 도구 (perplexity 등) 영속화 (별도 PDCA — `tool_factory`에 추가될 때마다 wiring 1줄씩)
- Run list 응답에 step/tool/retrieval/llm_call 트리 포함 (list는 light, detail은 heavy — 분리 유지)
- 부서별 집계 (`user → department` mapping) — 별도 PDCA
- PII redaction (별도 보안 검토 PDCA)
- 가격 history 테이블 (`ai_llm_pricing_history`) — 별도
- Retention/anonymization 정책 — 별도 컴플라이언스 PDCA
- 어드민 UI 화면 (`agent-run-admin-dashboard`) — M5 API 완료 후 별도 PDCA
- Tavily 결과의 chunk 단위 분할 (web 결과는 1 URL = 1 row 유지)
- 페이지네이션 cursor 방식 (M5는 limit/offset 단순 방식 — cursor는 후속 최적화 PDCA)
- 인덱스 hint / query plan 튜닝 (인덱스 추가만, 쿼리 재작성은 별도)

---

## 2. 기능 범위 (Scope)

### In Scope

| 영역 | 항목 |
|------|------|
| **Tavily retrieval wiring** | `TavilySearchTool.search` 또는 `search_as_value_object` 안에 best-effort `tracker.record_retrieval` 호출. `RunContext.tool_call_id` 자동 활용 (M2 wiring). `collection_name="tavily_web"` 고정, `document_id=hit.url[:N]`, `chunk_id=None`, `score=hit.score`, `rank_index=enumerate+1`, `content_preview=hit.content[:retrieval_preview_max_bytes]`, `metadata_json={"title": hit.title, "raw_score": ...}` |
| **TavilySearchTool tracker DI** | `tracker` / `logger` / `config` 필드 추가 (M4 InternalDocumentSearchTool 패턴 동일) |
| **ToolFactory tavily case 확장** | `tracker=self._tracker, logger=self._logger, config=self._obs_config` 전달 (M4-11과 동일 형태) |
| **Admin Run list API** | `GET /api/v1/admin/runs?from=&to=&user_id=&agent_id=&status=&limit=20&offset=0` → `{rows: [RunRowDto], total: int, from_dt, to_dt}`. status enum 필터, user_id 부분 일치 또는 정확 일치, default limit 20, max limit 100. admin only |
| **`AgentRunRepository.list_runs`** | 신규 메서드 — filter + ORDER BY started_at DESC + LIMIT/OFFSET. `count_runs(filters)` 별도 (total 계산용) |
| **`ListRunsUseCase` + DI** | `application/agent_run/use_cases/list_runs_use_case.py` + main.py factory + router dependency_override |
| **V023 마이그레이션** | `db/migration/V023__add_agent_run_aggregate_indexes.sql` — `ai_llm_call.created_at` 단독 인덱스 + 필요 시 `step_id` 단독 인덱스 (Design §3에서 SHOW INDEX 결과 확인 후 확정) |
| **Pydantic schemas** | `RunRowDto` (run + agent_name + user_id 등 light) + `RunListResponse` |
| **TDD** | router 단위 + use case 단위 + repository SQL 검증 + Tavily wiring 단위 + 인덱스 마이그레이션 회귀 0 검증 |

### Out of Scope (후속 PDCA)

- 다른 web search 도구 (perplexity, brave 등) — 추가 시 도구별로 1줄 wiring
- Run list에 LLM 비용/토큰 합계 컬럼 (별도 join 비용 — 어드민 화면이 요구 시 별도)
- Cursor-based pagination
- Full-text 검색 (run.error_message LIKE 등)
- LangSmith trace URL 표시 (M4 RunDetailResponse에 이미 포함, list는 light keep)
- `tavily_search` 외 도구의 retrieval (현재는 internal_document_search + tavily_web 2개 collection만)
- 부서별 집계
- 가격 history / retention / PII redaction (별도 PDCA)
- Index hint / query rewriter
- AGENT-OBS-005 이후 M6 명시 — 어드민 UI 화면 PDCA에서 발견되는 요구 사항 기반으로 결정

---

## 3. 기술 의존성

| 모듈 | Task ID / 상태 | M5 영향 |
|------|----------------|---------|
| `RunTracker.record_retrieval` | AGENT-OBS-001 (M1) ✅ | **호출자 추가만** |
| `RunContext.tool_call_id` | AGENT-OBS-002 (M2) ✅ | 활용 (이미 set/reset) |
| `RunContext.run_id` | M1 ✅ | 활용 |
| `AgentRunRepository.find_run / find_steps / ...` | M1 ✅ | 신규 `list_runs` / `count_runs` 추가 |
| `RunObservabilityConfig.retrieval_preview_max_bytes` | M1 ✅ | tavily content_preview 컷오프 재사용 |
| `ToolFactory.tracker / run_observability_config` | M4 ✅ | tavily case에도 전달 (M4 internal_document_search와 동일) |
| `get_current_user` / `require_role("admin")` | 기존 | 활용 |
| `TavilyClient` (tavily-python lib) | 기존 | 인터페이스 변경 없음 |
| 신규 외부 라이브러리 | — | **없음** |

---

## 4. 아키텍처 결정 (Strategy)

### 4-1. Tavily retrieval 영속화 진입점 선택

| 옵션 | 위치 | M4 일관성 | 영향도 |
|------|------|----------|--------|
| ❌ A: `TavilySearchTool._arun` 안에 직접 호출 | tool 함수 본문 | InternalDocumentSearchTool과 일관 | 가장 단순 — 채택 |
| ✅ **B: `TavilySearchTool.search` 안에 best-effort 호출** (M5 채택) | 내부 search 메서드 (실제 API 호출 직후) | 같은 instance — async 분기 / sync 분기 모두 커버 | (현재 `search`는 sync — async wrapping 필요) |
| ❌ C: callback-driven `on_tool_end` | UsageCallback | M2 패턴 — tool result 파싱 필요 (Tavily-specific 깨지기 쉬움) | M4와 동일 reasoning 적용해 거부 |

**결정**: 옵션 B — `_arun`이 `_run`을 호출하고 `_run`이 `search`를 호출하는 구조이므로 `search` 메서드 안에 record_retrieval을 두면 동기/비동기 모두 커버. 단, `record_retrieval`은 async이므로 `_arun` 안에서 `search` 호출 후 별도 `await`로 영속화 처리하거나, `search` 자체를 async로 승격. **M5 Design에서 최종 확정 — 본 Plan은 옵션 B 채택**.

### 4-2. `ai_retrieval_source` 컬럼 재사용 (vs 신규 테이블)

| 옵션 | 방법 | 장점 | 단점 |
|------|------|------|------|
| ❌ A: 신규 `ai_web_retrieval` 테이블 | URL/title 전용 schema | 의미 분리 명확 | DB 마이그레이션 비용 + RunDetailResponse 트리 조립 코드 복잡화 |
| ✅ **B: 기존 `ai_retrieval_source` 재사용 + collection_name 분기** (M5 채택) | `collection_name="tavily_web"` 고정 | M4 RunDetailResponse 자동 호환, 0 트리 변경 | `document_id VARCHAR(150)` 길이 부족 가능성 (긴 URL) |

**결정**: 옵션 B. URL 길이 문제는 (1) `document_id` 컬럼 확장 마이그레이션, 또는 (2) URL hash + raw URL을 `metadata_json`에 보존 — Design §3에서 확정.

### 4-3. Run list 응답 light keep

```jsonc
GET /api/v1/admin/runs?from=&to=&user_id=&status=&limit=20&offset=0
{
  "from_dt": "...",
  "to_dt": "...",
  "total": 137,
  "limit": 20,
  "offset": 0,
  "rows": [
    {
      "id": "run-uuid",
      "user_id": "...",
      "agent_id": "...",
      "status": "SUCCESS",
      "started_at": "...",
      "ended_at": "...",
      "latency_ms": 12340,
      "total_tokens": 234,           // ai_run.* (M1이 SUM 저장)
      "total_cost_usd": "0.0012",    // ai_run.* (M1이 SUM 저장)
      "llm_call_count": 4,           // ai_run.* (M1이 저장)
      "error_message": null
    }
  ]
}
```

**핵심**: ai_run row만으로 응답 구성 (steps/tool_calls/retrievals JOIN 없음) — light keep. 화면이 detail이 필요하면 별도 `GET /agents/runs/{id}` (M4) 호출.

### 4-4. V023 인덱스 마이그레이션 전략

Design §3에서 운영 DB의 `SHOW INDEX FROM ai_llm_call` 결과 확인 후 결정. 가설:

```sql
-- V023 candidate (Design 확정 전)
-- 1. created_at 단독 인덱스 (date-range scan 가속)
ALTER TABLE ai_llm_call ADD INDEX idx_llm_call_created (created_at);

-- 2. step_id 인덱스 (InnoDB FK 자동 인덱스 존재 시 skip)
-- ALTER TABLE ai_llm_call ADD INDEX idx_llm_call_step (step_id);
-- → SHOW INDEX 결과 fk_llm_call_step 인덱스가 step_id를 자동 cover 한다면 불필요
```

**중요**: 운영 환경에서 데이터 누적 후 ALTER TABLE은 lock 비용 발생. 본 PDCA에서는 dev/test 환경 마이그레이션만 다루고, 운영 환경 적용은 별도 운영 절차로 관리.

### 4-5. 레이어 배치 (Thin DDD 준수)

```
src/domain/agent_run/
└── interfaces.py            ★ 수정 — AgentRunRepositoryInterface.list_runs / count_runs + RunListFilters dataclass

src/application/agent_run/
└── use_cases/               (기존 — M4가 만듦)
    └── list_runs_use_case.py    ★ 신규 — filter validation + repo 위임

src/infrastructure/persistence/repositories/
└── agent_run_repository.py  ★ 수정 — list_runs (LIMIT/OFFSET + WHERE) + count_runs (단독 COUNT)

src/infrastructure/web_search/
└── tavily_tool.py           ★ 수정 — tracker / logger / config 필드 + record_retrieval best-effort 호출

src/infrastructure/agent_builder/
└── tool_factory.py          ★ 수정 — tavily_search case에 tracker / config 전달

src/api/routes/
└── agent_run_router.py      ★ 수정 — GET /admin/runs endpoint 추가 + RunListResponse 도입

src/interfaces/schemas/
└── agent_run_response.py    ★ 수정 — RunListResponse / RunRowDto 추가

src/api/main.py              ★ 수정 — ListRunsUseCase factory + dependency_override

db/migration/
└── V023__add_agent_run_aggregate_indexes.sql  ★ 신규

# 변경 없음
src/domain/agent_run/entities.py / value_objects.py / policies.py
src/application/agent_run/tracker.py / context.py / cost_calculator.py
src/application/rag_agent/tools.py    # M4가 만든 internal_document_search retrieval 그대로
src/application/agent_run/aggregator.py
```

**도메인 변경**: `RunListFilters` (frozen dataclass — from_dt/to_dt/user_id/agent_id/status/limit/offset) + abc method 2개 (list_runs, count_runs) 추가.

---

## 5. 데이터 모델

### 5-1. `ai_retrieval_source` Tavily row 컬럼 매핑

| 컬럼 | Tavily 값 |
|------|----------|
| `id` | uuid4 |
| `run_id` | `RunContext.run_id` |
| `tool_call_id` | `RunContext.tool_call_id` (M2 자동 set) |
| `collection_name` | `"tavily_web"` (상수) |
| `document_id` | `hit.url[:150]` (URL — Design에서 길이 확장 결정) |
| `chunk_id` | `None` (web 결과는 chunk 개념 없음) |
| `score` | `hit.score` (Tavily score, 0.0~1.0) |
| `rank_index` | enumerate(start=1) |
| `content_preview` | `hit.content[:retrieval_preview_max_bytes]` |
| `metadata_json` | `{"title": hit.title, "raw_score": ..., "url_full": hit.url}` (URL 잘림 대비) |
| `created_at` | `record_retrieval` 시점 |

### 5-2. V023 마이그레이션 (예시 — Design에서 확정)

```sql
-- V023__add_agent_run_aggregate_indexes.sql

-- 집계 API 성능 마진: by-user / by-llm / by-node 모두 created_at 범위 스캔
ALTER TABLE ai_llm_call ADD INDEX idx_llm_call_created (created_at);

-- step_id 단독 인덱스 (InnoDB FK 자동 인덱스 존재 여부 확인 후)
-- ALTER TABLE ai_llm_call ADD INDEX idx_llm_call_step (step_id);

-- ai_run.started_at 단독 인덱스도 점검 (V021 line 36이 이미 가지고 있음 — DESC composite)
-- list_runs ORDER BY started_at DESC + WHERE filters 결합 시 cardinality 확인
```

### 5-3. Run list 응답 데이터 (이미 ai_run에 모두 존재)

| 컬럼 | M1에서 이미 채움 |
|------|----------------|
| `id, user_id, agent_id, conversation_id` | ✅ |
| `status` | M1 + M3 (RUNNING/SUCCESS/FAILED/CANCELLED) ✅ |
| `started_at, ended_at, latency_ms` | M1 + complete_run ✅ |
| `total_tokens, total_cost_usd, llm_call_count` | M1 apply_completion_totals (SUM SUBQUERY) ✅ |
| `error_message` | M1 fail_run ✅ |

→ **신규 컬럼 0건. 모두 read.**

---

## 6. 마일스톤 (M5 내부 작업 분할)

| 단계 | 범위 | 산출물 | 예상 |
|------|------|--------|------|
| **M5-0** | Design — Tavily retrieval 옵션 B / 컬럼 길이 / V023 인덱스 후보 확정 | Design §1.3 Open Issue 정리 | 0.2일 |
| **M5-1** | Tavily retrieval wiring — `TavilySearchTool` tracker DI + best-effort record_retrieval + 단위 4건 | tavily_tool.py + tests/.../test_tavily_retrieval.py | 0.4일 |
| **M5-2** | ToolFactory tavily case 확장 — tracker 전달 | tool_factory.py 5줄 수정 + 단위 1건 | 0.1일 |
| **M5-3** | `AgentRunRepositoryInterface.list_runs / count_runs` + `RunListFilters` 도메인 | interfaces.py + 단위 1건 | 0.2일 |
| **M5-4** | `SqlAlchemyAgentRunRepository.list_runs / count_runs` SQL — WHERE + ORDER BY + LIMIT/OFFSET, separate COUNT | repository SQL + 통합 4건 | 0.3일 |
| **M5-5** | `ListRunsUseCase` + 단위 테스트 (필터 검증 / pagination 경계) | use case + 단위 4건 | 0.2일 |
| **M5-6** | `GET /admin/runs` router + Pydantic `RunListResponse` / `RunRowDto` + 통합 5건 | router 추가 + schemas 확장 + 통합 5건 | 0.3일 |
| **M5-7** | `api/main.py` DI wiring (1 신규 factory) | main.py 수정 | 0.1일 |
| **M5-8** | V023 마이그레이션 — `idx_llm_call_created` + (옵션) `idx_llm_call_step` | db/migration/V023*.sql + 회귀 통과 (테스트는 SQL syntax + 인덱스 존재 검증) | 0.2일 |
| **M5-9** | 수동 검증 (실 LLM + Tavily 1회 + admin list curl) | 검증 로그 캡처 | 0.3일 |

**총 예상**: 2.3일 (M4의 3.0일 대비 약간 작음 — wiring 1건 + endpoint 1개 + 마이그레이션 1건으로 축소).

---

## 7. 코드 통합 지점

| 파일 | 변경 내용 | 비고 |
|------|----------|------|
| `src/infrastructure/web_search/tavily_tool.py` | tracker / logger / config 필드 추가 (Pydantic BaseTool에 `model_config = ConfigDict(arbitrary_types_allowed=True)` 필요) + `_arun` 또는 `search` 안에 best-effort record_retrieval 루프 | M4 InternalDocumentSearchTool 패턴 동일. tavily-python sync client → async wrapping 검토 |
| `src/infrastructure/agent_builder/tool_factory.py` | `case "tavily_search"` 에 `tracker=self._tracker, logger=self._logger, config=self._obs_config` 전달 | 5줄 수정 |
| `src/domain/agent_run/interfaces.py` | `RunListFilters` frozen dataclass + `AgentRunRepositoryInterface.list_runs(filters) -> List[AgentRun]` + `count_runs(filters) -> int` abc method 2개 | ~20줄 |
| `src/infrastructure/persistence/repositories/agent_run_repository.py` | `list_runs` SQL (WHERE 조건부 + ORDER BY started_at DESC + LIMIT/OFFSET) + `count_runs` (단독 COUNT) | ~50줄 |
| `src/application/agent_run/use_cases/list_runs_use_case.py` ★ 신규 | filter validation (status enum, limit ≤ 100) + repo.list_runs + repo.count_runs 동시 호출 (asyncio.gather) | ~50줄 |
| `src/api/routes/agent_run_router.py` | `GET /admin/runs` endpoint 추가 + DI placeholder | ~35줄 |
| `src/interfaces/schemas/agent_run_response.py` | `RunRowDto` (light) + `RunListResponse` (rows + total + pagination meta) | ~40줄 |
| `src/api/main.py` | `ListRunsUseCase` factory + dependency_override 1건 추가 | 5줄 |
| `db/migration/V023__add_agent_run_aggregate_indexes.sql` ★ 신규 | `ALTER TABLE ai_llm_call ADD INDEX idx_llm_call_created (created_at);` + Design 확정 후 step_id 단독 인덱스 옵션 | ~10줄 |
| `tests/infrastructure/web_search/test_tavily_retrieval.py` ★ 신규 | 4건: per-hit / ctx None skip / tool_call_id / best-effort | |
| `tests/infrastructure/agent_run/test_agent_run_repository_list.py` ★ 신규 | 4건: 필터 / pagination / ORDER BY / COUNT 정합 | |
| `tests/application/agent_run/use_cases/test_list_runs_use_case.py` ★ 신규 | 4건: filter forward / status invalid / limit cap / 동시 list+count | |
| `tests/api/test_agent_run_router_list.py` ★ 신규 | 5건: 200 admin / 403 non-admin / 422 invalid status / 422 limit>100 / pagination total | |
| (보강) `tests/api/test_agent_run_router.py` | 회귀 0 검증 | 신규 0 |

---

## 8. TDD 계획

### 8-1. Tavily retrieval wiring (~4 cases)

```
test_search_records_retrieval_per_hit_with_rank_index
test_record_retrieval_uses_tool_call_id_from_runcontext
test_search_skips_record_retrieval_when_runcontext_none
test_record_retrieval_failure_does_not_break_tavily_output  ★ best-effort
```

### 8-2. AgentRunRepository list/count (~4 cases)

```
test_list_runs_returns_filtered_runs_ordered_by_started_desc
test_list_runs_respects_limit_offset
test_count_runs_returns_total_with_same_filters
test_list_runs_handles_optional_filters_none      # 필터 없음 → 전체
```

### 8-3. ListRunsUseCase (~4 cases)

```
test_executes_list_and_count_in_parallel
test_invalid_status_raises_value_error              # router → 422
test_caps_limit_at_100_max
test_default_pagination_limit_20_offset_0
```

### 8-4. Router 통합 (~5 cases)

```
test_get_admin_runs_returns_200_with_pagination_meta_for_admin
test_get_admin_runs_requires_admin_role             # non-admin → 403
test_get_admin_runs_rejects_invalid_status          # 422
test_get_admin_runs_caps_limit_at_100               # 422
test_get_admin_runs_filters_by_user_id              # ?user_id= 검증
```

**핵심 회귀 가드**:
- `test_record_retrieval_failure_does_not_break_tavily_output` (★ best-effort 격리, M4와 동일 정신)
- `test_get_admin_runs_requires_admin_role` (★ 권한 안전성)
- `test_count_runs_returns_total_with_same_filters` (★ total/rows 정합 — pagination 신뢰성)

---

## 9. CLAUDE.md 규칙 체크

- [x] domain 변경 — `RunListFilters` dataclass + abc method 2개 (infrastructure는 의존 가능)
- [x] application use case — repository만 import. Tracker / Tool 의존 없음
- [x] router는 비즈니스 로직 0 — use case 호출 + Pydantic 변환 + HTTPException 매핑만
- [x] `TavilySearchTool`이 `RunContext` (application) import — 도구는 RAG와 동일 — application 의존 허용
- [x] Repository 내부 commit 금지 (DB-001) — list/count 모두 SELECT only
- [x] LOG-001 LoggerInterface — Tavily record_retrieval 실패 시 warning (M4 internal과 동일)
- [x] TDD 순서 — 모든 4 suite 모두 테스트 먼저
- [x] 함수 ≤40줄 — `list_runs` SQL ~30줄, ListRunsUseCase.execute ~25줄 목표
- [x] if 중첩 ≤2 — filter 처리는 chain of `.where(condition)` 단순화
- [x] config 하드코딩 금지 — `retrieval_preview_max_bytes` M1 RunObservabilityConfig 재사용, max_limit=100은 router 상수
- [x] DTO와 Pydantic schema 분리 — domain RunListFilters ≠ Pydantic RunListResponse

---

## 10. 위험 요소 및 대응

| 위험 | 영향 | 가능성 | 대응 |
|------|------|--------|------|
| `document_id VARCHAR(150)`가 긴 URL을 잘라낼 가능성 | 데이터 손실 (full URL 미보존) | Medium | metadata_json에 `url_full` 키로 원본 보존. 추후 컬럼 확장 별도 마이그레이션 |
| Tavily 결과 `score`가 음수/거대 값 | DECIMAL(10,6) 범위 초과 | Very Low | tavily-python score는 0~1 normalized. 안전 — 다만 try/except로 record_retrieval 자체가 best-effort라 절대 안전 |
| `_arun`에서 `search` 호출 후 sync return → record_retrieval은 async 호출 | 동시 실행 처리 어색 | Low | M4 InternalDocumentSearchTool과 동일 패턴: `_arun`을 async로 두고 검색 결과 받은 직후 await record_retrieval. tavily-python sync client는 그대로 (executor wrap는 불필요 — 호출당 1회) |
| InnoDB FK 자동 인덱스 redundant — `idx_llm_call_step` 추가 시 중복 | 스토리지 낭비 | Low | Design §3에서 `SHOW INDEX FROM ai_llm_call` 결과로 결정. 중복 시 skip |
| ALTER TABLE이 운영 DB에서 lock 비용 | 운영 잠시 멈춤 | Medium | 본 PDCA는 마이그레이션 작성만. 운영 적용은 maintenance window에서 운영팀이 별도 실행 (online DDL 가능 검토 — InnoDB 5.6+ inplace ALTER) |
| Run list filter 조합이 인덱스 미적용 path 유발 | 슬로우 query | Medium | 1차: started_at DESC + (status / user_id 단일) 만 권장. 복합 필터는 cardinality 낮을 때 full scan acceptable. 후속 PDCA에서 composite index 검토 |
| `count_runs(filters)` 비용이 `list_runs`만큼 | 페이지 호출당 2 query | Low | 페이지네이션 신뢰성을 위해 필요 비용. 미래에 EXPLAIN으로 분리 cache 전략 검토 |
| Tavily 결과 `hit.url`이 None일 가능성 | document_id NULL | Low | `hit.url or "unknown"` fallback. metadata_json에 raw 보존 |
| Run list 응답 페이로드 크기 | limit=100 시 ~100×500B = 50KB | Low | gzip 압축 미들웨어 (기존) + light keep으로 충분 |
| Tavily retrieval 영속화가 RAG 답변 흐름 차단 | (M4와 동일 위험) | Resolved | try/except + warning log + continue 패턴 동일 적용 |
| Design 단계에서 confidential URL 노출 우려 | content_preview 안 비밀 URL | Low | retrieval_preview_max_bytes 500자 컷, 운영 모니터링 — PII redaction은 별도 PDCA |

---

## 11. 후속 PDCA (M5 이후)

- `agent-run-admin-dashboard` — 어드민 UI (Run list / detail / Usage 차트) — M5 list API + M4 detail API 활용
- `agent-usage-dashboard` — 사용자 셀프 화면
- M6 후보: 부서별 mapping + 집계
- `agent-run-pii-redaction` — step.input/output_summary 보안 검토
- `agent-run-retention-policy` — TTL / anonymization
- `agent-run-pricing-history` — `ai_llm_pricing_history` audit table
- `agent-run-cursor-pagination` — limit/offset → cursor 마이그레이션 (운영 데이터 누적 시)
- Run list response 확장 — agent_name / user_name 등 join을 통한 사람-읽기 가능 필드 (어드민 UI 요구 시)
- Perplexity / Brave web search 도구의 retrieval 영속화 (도구 추가 시점에 wiring)
- `idx_llm_call_user_node` 복합 인덱스 (by-node + by-user 결합 사용 패턴 발견 시)

---

## 12. 완료 기준 (DoD)

### 12.1 코드
- [ ] `TavilySearchTool` tracker / logger / config 필드 + best-effort record_retrieval
- [ ] `tool_factory.py` tavily case에 tracker 전달
- [ ] `RunListFilters` + `AgentRunRepositoryInterface.list_runs` / `count_runs` abc
- [ ] `SqlAlchemyAgentRunRepository.list_runs` / `count_runs` SQL
- [ ] `ListRunsUseCase` + filter validation
- [ ] `agent_run_router.py` `GET /admin/runs` endpoint
- [ ] `RunListResponse` / `RunRowDto` Pydantic
- [ ] `api/main.py` DI 와이어링
- [ ] `db/migration/V023__add_agent_run_aggregate_indexes.sql`

### 12.2 테스트
- [ ] Tavily retrieval wiring 4건 통과
- [ ] AgentRunRepository list/count 4건 통과
- [ ] ListRunsUseCase 4건 통과
- [ ] Router 통합 5건 통과
- [ ] M1·M2·M3·M4 기존 테스트 100% 유지 (163+ 회귀 0건)

### 12.3 수동 검증 (실 운영 환경)
- [ ] Tavily 검색이 포함된 한 사용자 질문 → `ai_retrieval_source`에 `collection_name='tavily_web'` row N건 + `document_id` URL 확인
  ```sql
  SELECT rs.rank_index, rs.document_id, rs.score, LEFT(rs.content_preview, 100)
    FROM ai_retrieval_source rs
   WHERE rs.run_id=? AND rs.collection_name='tavily_web' ORDER BY rs.rank_index;
  ```
- [ ] internal_document_search + tavily_search 둘 다 사용한 run → `ai_retrieval_source`에 두 collection 행 동시 존재
- [ ] `GET /api/v1/admin/runs?limit=20` 응답: rows[20] + total
- [ ] `GET /api/v1/admin/runs?status=FAILED&user_id=...` 필터 동작
- [ ] `GET /api/v1/admin/runs?limit=200` → 422 (limit cap)
- [ ] `GET /api/v1/admin/runs?status=INVALID` → 422
- [ ] 비-admin이 `/admin/runs` 호출 → 403
- [ ] V023 마이그레이션 실행 후 `SHOW INDEX FROM ai_llm_call` 결과 `idx_llm_call_created` 존재 확인
- [ ] V023 마이그레이션 직후 `/admin/usage/by-node` latency 변화 측정 (참고치)
- [ ] Tavily record_retrieval 강제 예외 주입 → 답변 정상 반환

### 12.4 문서 동기화
- [ ] M5 Design 문서 작성 (`docs/02-design/features/agent-run-observability-m5.design.md`)
- [ ] tavily retrieval 컬럼 매핑 표 Design §3에 명시
- [ ] V023 인덱스 후보 Design §3에서 `SHOW INDEX` 결과 기반 확정
- [ ] M4 §7.3 follow-up 3건 vs M5 In Scope 일치성 검증

---

## 13. 참고 자료

- 부모 Plan (M1): [agent-run-observability.plan.md](../../archive/2026-05/agent-run-observability/agent-run-observability.plan.md)
- M2 Plan: [agent-run-observability-m2.plan.md](../../archive/2026-05/agent-run-observability-m2/agent-run-observability-m2.plan.md)
- M3 Plan: [agent-run-observability-m3.plan.md](../../archive/2026-05/agent-run-observability-m3/agent-run-observability-m3.plan.md)
- M4 Plan: [agent-run-observability-m4.plan.md](../../archive/2026-05/agent-run-observability-m4/agent-run-observability-m4.plan.md)
- M4 §7.3 (M5 명시): [agent-run-observability-m4.report.md](../../archive/2026-05/agent-run-observability-m4/agent-run-observability-m4.report.md)
- M1 V021 schema: `db/migration/V021__create_agent_run_tables.sql`
- M1 V022 pricing: `db/migration/V022__add_llm_model_pricing.sql`
- 핵심 원칙: **"동등 시민화"** (internal_document_search와 tavily_search가 영속화 측면에서 동등) + **"화면 PDCA 의존성 해소"** (list API로 백엔드 의존성 0)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-05-21 | M5 초안 — Tavily retrieval wiring + GET /admin/runs list API + V023 인덱스 마이그레이션. 신규 도메인 entity 0건, 신규 마이그레이션 1건 (인덱스만) | 배상규 |
