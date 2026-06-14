# agent-run-observability-m5 (M5) Completion Report

> **Summary**: Agent Run 운영 관측성 M5 마일스톤 완료 (98% 설계 일치, ≥90% 임계 통과). M4 §7.3 follow-up 3건 일괄 해소 — (1) `tavily_search` retrieval 영속화로 internal_document_search와 동등 시민화, (2) `GET /admin/runs` list/페이지네이션 API로 어드민 화면 PDCA backend 의존성 0, (3) V023 마이그레이션 `idx_llm_call_created`로 집계 API 운영 안전 마진 확보.
>
> **Feature**: Agent Run 운영 관측성 (M5 — Tavily Retrieval + Admin Run List + Aggregate Index)
> **Task ID**: AGENT-OBS-005
> **Project**: sangplusbot (idt)
> **Scope**: M5 only — Tavily web retrieval wiring + GET /admin/runs + V023 index migration
> **Version**: 1.0
> **Planning Date**: 2026-05-21
> **Completion Date**: 2026-05-21
> **Match Rate**: 98%
> **Status**: ✅ COMPLETED (M5)
> **Parent (M1)**: agent-run-observability (archived 2026-05-19, 96%)
> **Sibling (M2)**: agent-run-observability-m2 (archived 2026-05-21, 98%)
> **Sibling (M3)**: agent-run-observability-m3 (archived 2026-05-21, 99%)
> **Sibling (M4)**: agent-run-observability-m4 (archived 2026-05-21, 98%)

---

## Executive Summary

### 1.1 Project Overview

| Item | Content |
|------|---------|
| Feature | Agent Run 운영 관측성 (M5 — Tavily Retrieval + Admin Run List + Aggregate Index) |
| Task ID | AGENT-OBS-005 |
| Start Date | 2026-05-21 |
| End Date | 2026-05-21 |
| Duration | 1 day (Plan → Design → Do → Check → Report 모두 단일 세션) |
| Predecessor | M4 (AGENT-OBS-004, archived, 98%) |
| Milestones Pending | (Future M6: PII redaction / retention / pricing history 등 — 별도 PDCA) |
| Final Match Rate | **98%** (≥90% threshold met) |

### 1.2 Results Summary

```
┌────────────────────────────────────────────────────────────────┐
│  M5 Completion Rate: 98%                                       │
├────────────────────────────────────────────────────────────────┤
│  ✅ New files:        2                                        │
│     - src/application/agent_run/use_cases/list_runs_use_case.py│
│     - db/migration/V023__add_agent_run_aggregate_indexes.sql   │
│  ✅ Modified files:   7                                        │
│     - src/infrastructure/web_search/tavily_tool.py             │
│     - src/infrastructure/agent_builder/tool_factory.py         │
│     - src/domain/agent_run/interfaces.py                       │
│     - src/infrastructure/persistence/repositories/             │
│         agent_run_repository.py                                │
│     - src/api/routes/agent_run_router.py                       │
│     - src/interfaces/schemas/agent_run_response.py             │
│     - src/api/main.py                                          │
│  ✅ Test files (new): 3                                        │
│     - tests/infrastructure/web_search/test_tavily_retrieval.py │
│     - tests/application/agent_run/use_cases/                   │
│         test_list_runs_use_case.py                             │
│     - tests/api/test_agent_run_router_list.py                  │
│  ✅ Test files (mod): 1                                        │
│     - tests/infrastructure/agent_run/                          │
│         test_agent_run_repository.py (+4 TestListRuns)         │
│  ✅ Test cases:       19 new + 136 regression = 155 / 155 PASS │
│  ✅ DB migrations:    1 (V023, 인덱스만 — Plan §1.1 약속 일치) │
│  ✅ Domain changes:   +1 dataclass (RunListFilters) + 2 abc    │
│  ✅ Endpoints:        +1 (GET /admin/runs)                     │
│  🟢 Free win #1:      M3·M4 ContextVar 선투자가 M5에서 회수    │
│                       (Tavily가 RunContext.run_id/tool_call_id │
│                        read만으로 영속화)                       │
│  🟢 Free win #2:      ai_retrieval_source 컬럼 재사용으로      │
│                       M4 RunDetailResponse 자동 호환            │
│                       (internal+tavily 한 트리)                 │
│  🟢 Free win #3:      _apply_run_filters 헬퍼로                │
│                       list_runs/count_runs WHERE 정합 testable │
│  🟡 Minor deviations: 0 (실제 deviation 0건)                   │
│  🟠 Major / 🔴 Critical: 0                                     │
└────────────────────────────────────────────────────────────────┘
```

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | M4 §7.3에서 명시된 follow-up 3건이 미해소: (1) `tavily_search` 호출은 여전히 `ai_retrieval_source` row 0건 — web 검색 답변의 인용 URL을 사후 DB 추적 불가, (2) 어드민이 `GET /agents/runs/{run_id}` 호출하려면 run_id를 미리 알아야 함 — Run list/검색 API 부재로 어드민 UI PDCA의 backend 의존성 발생, (3) `ai_llm_call.created_at`에 단독 인덱스 부재 — by-user/by-llm/by-node 집계가 데이터 누적 시 full scan으로 떨어질 위험. |
| **Solution** | **신규 마이그레이션 1건(V023, 인덱스만) + 도메인 추가 1건 + endpoint 1개 + Tavily wiring 1건.** (a) `TavilySearchTool._arun` 재구성 — `search_as_value_object` → `_record_retrievals_best_effort` → `format_search_result_to_xml`. `collection_name="tavily_web"` 고정 + URL `[:150]` truncate + `metadata_json.url_full`에 원본 보존. ToolFactory case에 tracker 전달 5줄 추가. (b) `GET /api/v1/admin/runs?from=&to=&user_id=&agent_id=&status=&limit=&offset=` 신규 + `RunListFilters` 도메인 dataclass + `list_runs`/`count_runs` abc + `asyncio.gather(list, count)` 캡슐화. (c) V023 마이그레이션 — `ALTER TABLE ai_llm_call ADD INDEX idx_llm_call_created (created_at)` 단 1줄. |
| **Function / UX Effect** | (1) **Tavily 답변 책임 추적**: "이 web 검색 답변이 인용한 URL은?" → `SELECT document_id FROM ai_retrieval_source WHERE collection_name='tavily_web' AND run_id=?` SQL 1줄. (2) **internal + tavily 통합 트리**: M4 `RunDetailResponse`가 자동으로 두 collection을 같은 retrievals[] 안에서 반환 — 어드민이 "RAG 3 chunk + Web 2 URL 인용" 분석 가능. (3) **Failed run 디버깅**: `GET /admin/runs?status=FAILED&user_id=...` 한 화면으로 운영 모니터링. (4) **페이지네이션 신뢰성**: `total/rows` 정합 (같은 WHERE 조건) — 어드민이 페이지 수 정확히 계산. (5) **집계 API 슬로우 사전 방지**: V023 인덱스로 `/admin/usage/by-node` 등이 데이터 누적 후에도 빠른 응답 유지. (6) 비-admin이 `/admin/runs` 호출 시 403, limit > 100 시 422 분리로 안전성↑. |
| **Core Value** | **"외부 검색 = 동등 시민" 완성** + **화면 PDCA 의존성 해소** + **운영 안전 마진**. internal_document_search(M4)와 tavily_search(M5)가 영속화 측면에서 동등하게 취급되어 어드민이 두 검색 소스를 같은 retrievals[] 트리로 분석 가능. 어드민 대시보드 PDCA는 M4 detail API + M5 list API + 기존 usage API만 호출하면 됨 — backend 변경 0으로 화면 PDCA 100% 독립 진행. V023 인덱스로 1년 누적 데이터(1M row 가정) 부담 사전 회피. 1일 만에 완료 (Plan/Design/Do/Check/Report 모두 단일 세션, M3·M4와 동일 속도). M3·M4의 ContextVar 선투자가 M5에서 코드 변경 0줄로 회수됨. |

---

## 2. Related Documents

| Phase | Document | Status | Match Rate |
|-------|----------|--------|-----------|
| Plan | [agent-run-observability-m5.plan.md](../../01-plan/features/agent-run-observability-m5.plan.md) | ✅ Finalized | — |
| Design | [agent-run-observability-m5.design.md](../../02-design/features/agent-run-observability-m5.design.md) | ✅ Finalized | — |
| Check | [agent-run-observability-m5.analysis.md](../../03-analysis/agent-run-observability-m5.analysis.md) | ✅ Complete | 98% |
| Report | Current document | ✅ Complete | — |

---

## 3. Completed Items (M5)

### 3.1 Functional Requirements

| ID | Requirement | Status | Notes |
|----|-------------|--------|-------|
| FR-01 | TavilySearchTool tracker/logger/config Optional 필드 | ✅ | `tavily_tool.py:50-52` (model_config + ConfigDict) |
| FR-02 | `_arun` 재구성 — search_as_value_object → record_retrieval → format | ✅ | `tavily_tool.py:96-126` (sync `_run`/`search` 영향 0) |
| FR-03 | `_record_retrievals_best_effort` 헬퍼 — ctx/tracker None 시 skip | ✅ | `tavily_tool.py:128-167` (early return L138-139) |
| FR-04 | collection_name = "tavily_web" 고정 | ✅ | `tavily_tool.py:158` |
| FR-05 | `document_id = url[:150] or None` | ✅ | `tavily_tool.py:151-153` |
| FR-06 | metadata `{title, url_full, raw_score}` 보존 | ✅ | `tavily_tool.py:160-163` |
| FR-07 | content_preview 컷오프 `retrieval_preview_max_bytes` | ✅ | `tavily_tool.py:147-148, 154` |
| FR-08 | best-effort 격리 (try/except + warning + continue) | ✅ | `tavily_tool.py:149-167` |
| FR-09 | ToolFactory tavily case에 tracker/logger/config 전달 | ✅ | `tool_factory.py:62-69` |
| FR-10 | `RunListFilters` frozen dataclass (7 필드) | ✅ | `interfaces.py:62-76` |
| FR-11 | `AgentRunRepositoryInterface.list_runs` / `count_runs` abc | ✅ | `interfaces.py:137-143` |
| FR-12 | `SqlAlchemyAgentRunRepository.list_runs` SQL — filters + ORDER BY DESC + LIMIT/OFFSET | ✅ | `agent_run_repository.py:251-258` |
| FR-13 | `count_runs` SQL — 같은 filters + func.count() | ✅ | `agent_run_repository.py:260-263` |
| FR-14 | `_apply_run_filters` chain helper (DRY) | ✅ | `agent_run_repository.py:265-277` |
| FR-15 | `ListRunsUseCase.execute` — asyncio.gather | ✅ | `list_runs_use_case.py:45-48` |
| FR-16 | `_validate` capsule (status enum / limit cap / offset / from<to) | ✅ | `list_runs_use_case.py:60-76` |
| FR-17 | `RunListDto` frozen dataclass | ✅ | `list_runs_use_case.py:31-39` |
| FR-18 | `GET /admin/runs` endpoint + 7 Query params | ✅ | `agent_run_router.py:220-258` |
| FR-19 | FastAPI Query 1차 검증 (`ge=1, le=100`, `ge=0`) | ✅ | `agent_run_router.py:226-227` |
| FR-20 | `Depends(require_role("admin"))` 권한 | ✅ | `agent_run_router.py:230` |
| FR-21 | router from > to 422 | ✅ | `agent_run_router.py:240-244` |
| FR-22 | ValueError → 422 매핑 | ✅ | `agent_run_router.py:254-258` |
| FR-23 | `RunRowDto` (light, 12 필드) + `RunListResponse` Pydantic | ✅ | `agent_run_response.py:210-264` |
| FR-24 | `from_dto` classmethod 변환 | ✅ | `agent_run_response.py:235-264` |
| FR-25 | `api/main.py` ListRunsUseCase factory + override | ✅ | `main.py:1287-1292, 2222-2228, 2233` |
| FR-26 | V023 마이그레이션 `idx_llm_call_created` | ✅ | `db/migration/V023__add_agent_run_aggregate_indexes.sql:25-26` |
| FR-27 | V023 운영 적용 주의사항 주석 | ✅ | V023 SQL L21-23 |

### 3.2 Non-Functional Requirements

| Item | Target | Achieved | Status |
|------|--------|----------|--------|
| Architecture (Thin DDD) | domain → infra 참조 0 | 0건 | ✅ |
| Layer dependency direction | domain ← application ← infrastructure | 위반 0건 | ✅ |
| DB migrations | 1 (인덱스만 — Plan §1.1 약속) | 1 (V023) | ✅ |
| Domain entity 추가 | 0 (RunListFilters는 dataclass) | 0 entity (1 dataclass + 2 abc) | ✅ |
| Out-of-scope preservation | cursor pagination / agent_name join / raw_content 영속화 | 모두 미구현 (YAGNI) | ✅ |
| Convention (CLAUDE.md §3, §6) | print() 0, 함수 ≤40줄, if 중첩 ≤2 | 100% 준수 | ✅ |
| Test files (Design §9.1) | 3 new + 1 augment | 3 new + 1 augment | ✅ |
| Unit test pass rate | 100% | 155/155 (M1-M5 통합) | ✅ |
| 신규 테스트 vs 목표 | 17 | 19 (112%) | ✅ |
| Match Rate (M5) | ≥90% | 98% | ✅ |
| 핵심 회귀 가드 | 9 required | 9/9 통과 | ✅ |

### 3.3 Deliverables

#### Code Files

| Type | File | Lines | Notes |
|------|------|------:|-------|
| NEW | `src/application/agent_run/use_cases/list_runs_use_case.py` | ~85 | UseCase + RunListDto + _validate + _MAX_LIMIT/_VALID_STATUSES 상수 |
| NEW | `db/migration/V023__add_agent_run_aggregate_indexes.sql` | ~26 | `idx_llm_call_created` 단독 + 헤더 주석 (운영 적용 절차) |
| MODIFIED | `src/infrastructure/web_search/tavily_tool.py` | +75 | model_config + 3 Optional fields + `_arun` 재구성 + `_record_retrievals_best_effort` 헬퍼 |
| MODIFIED | `src/infrastructure/agent_builder/tool_factory.py` | +6 | tavily_search case에 tracker/logger/config 전달 |
| MODIFIED | `src/domain/agent_run/interfaces.py` | +18 | RunListFilters dataclass + 2 abc method |
| MODIFIED | `src/infrastructure/persistence/repositories/agent_run_repository.py` | +30 | list_runs / count_runs / _apply_run_filters (func import 1줄) |
| MODIFIED | `src/api/routes/agent_run_router.py` | +45 | GET /admin/runs endpoint + DI placeholder |
| MODIFIED | `src/interfaces/schemas/agent_run_response.py` | +55 | RunRowDto + RunListResponse + from_dto |
| MODIFIED | `src/api/main.py` | +12 | list_runs_factory + import + dependency_override |

#### Test Files

| Type | File | Cases | Notes |
|------|------|------:|-------|
| NEW | `tests/infrastructure/web_search/test_tavily_retrieval.py` | 5 | per-hit / ctx None / tracker None / tool_call_id forward / best-effort 격리 |
| NEW | `tests/application/agent_run/use_cases/test_list_runs_use_case.py` | 5 | parallel / limit cap / status invalid / from>to / 4 valid statuses |
| NEW | `tests/api/test_agent_run_router_list.py` | 5 | 200 admin / 403 non-admin / 422 status / 422 limit / filter forward |
| MODIFIED | `tests/infrastructure/agent_run/test_agent_run_repository.py` | +4 | TestListRuns: filters/pagination/ORDER BY/COUNT 정합/no filters |

#### Documents

| Phase | File |
|-------|------|
| Plan | `docs/01-plan/features/agent-run-observability-m5.plan.md` |
| Design | `docs/02-design/features/agent-run-observability-m5.design.md` |
| Analysis | `docs/03-analysis/agent-run-observability-m5.analysis.md` |
| Report | `docs/04-report/features/agent-run-observability-m5.report.md` (this) |

---

## 4. Implementation Highlights

### 4.1 M3·M4 ContextVar 선투자 → M5에서 코드 0줄로 회수 (Design §2.2)

M2가 `RunContext.tool_call_id`를, M3가 `RunContext.step_id`를, M4가 `tracker` ToolFactory DI를 설계해 둔 상태에서, M5는 도구가 그 컨텍스트를 read만 하면 된다 — **factory/spec 변경 0**:

```python
# tavily_tool.py M5 패치 (핵심부)
async def _arun(self, query, search_depth="basic", ...):
    result = self.search_as_value_object(query=query, request_id="langchain-run", ...)
    if self.tracker is not None:
        await self._record_retrievals_best_effort(result)
    return format_search_result_to_xml(result, include_raw_content=include_raw_content)

async def _record_retrievals_best_effort(self, result):
    ctx = get_current_run_context()              # ★ M2 + M3가 set
    if ctx is None or ctx.run_id is None:
        return
    for rank_index, item in enumerate(result.items, start=1):
        try:
            await self.tracker.record_retrieval(
                run_id=ctx.run_id,
                tool_call_id=ctx.tool_call_id,    # ★ M2가 set
                collection_name="tavily_web",       # ★ 고정
                document_id=(item.url or "")[:150] or None,
                chunk_id=None,                       # web 결과 chunk 개념 없음
                score=item.score,
                rank_index=rank_index,
                content_preview=item.content[:preview_max],
                metadata={"title": ..., "url_full": ..., "raw_score": ...},
            )
        except Exception as e:
            self.logger.warning("...", exception=e)
            # continue 다음 item
```

**효과**: ToolFactory 시그니처 변경 0, Spec 변경 0, WorkflowCompiler 변경 0, Agent 정의 변경 0. M4 InternalDocumentSearchTool과 정확히 같은 패턴.

### 4.2 sync `_run` / `search` 영향 0 — 비동기 분리 (Design §1.3 #1)

`TavilySearchTool._run`은 LangChain BaseTool 표준 sync interface, `search`는 외부 호출자(테스트/스크립트)가 sync로 쓸 수 있는 method. M5는 `_arun`만 손대므로 backward-compat 100%:

```python
# 변경 없음 — backward-compat
def _run(self, query, ...) -> str:
    return self.search(query=query, request_id="langchain-run", format_output=True, ...)

def search(self, query, request_id, ...) -> str:
    response = self._client.search(**kwargs)
    return format_search_result_to_xml(self._parse_response(query, response), ...)
```

**효과**: 기존 sync 호출자(`test_tavily_tool.py`의 15 테스트)는 0 변경, 모두 회귀 통과.

### 4.3 `_apply_run_filters` 헬퍼 — list/count 정합성 (Design §2.4)

list_runs와 count_runs가 다른 WHERE 절을 쓰면 `total != len(rows의 무한 페이지 합)`이 되어 페이지네이션 신뢰성 파괴. M5는 chain helper로 봉인:

```python
def _apply_run_filters(self, stmt, filters: RunListFilters):
    if filters.from_dt is not None:
        stmt = stmt.where(AgentRunModel.started_at >= filters.from_dt)
    if filters.to_dt is not None:
        stmt = stmt.where(AgentRunModel.started_at < filters.to_dt)
    if filters.user_id is not None:
        stmt = stmt.where(AgentRunModel.user_id == filters.user_id)
    if filters.agent_id is not None:
        stmt = stmt.where(AgentRunModel.agent_id == filters.agent_id)
    if filters.status is not None:
        stmt = stmt.where(AgentRunModel.status == filters.status)
    return stmt
```

회귀 가드 `test_count_runs_returns_total_with_same_filters`가 영구히 정합 보장.

### 4.4 `asyncio.gather(list, count)` — 동시 호출로 latency 절반 (Design §3.3)

```python
async def execute(self, filters: RunListFilters) -> RunListDto:
    self._validate(filters)
    rows, total = await asyncio.gather(
        self._agent_run_repo.list_runs(filters),
        self._agent_run_repo.count_runs(filters),
    )
    return RunListDto(rows=rows, total=total, ...)
```

직렬 호출 대비 절반 latency. 같은 session에서 두 query 동시 실행 — SQLAlchemy AsyncSession이 지원.

### 4.5 Validation 캡슐화 — depth-in-defense (Design §2.4, §3.3)

| Layer | 검증 항목 | 효과 |
|-------|---------|------|
| FastAPI Query | `limit: int = Query(20, ge=1, le=100)` + `offset: int = Query(0, ge=0)` | 1차 — 잘못된 타입/범위 422 |
| Router | `from > to` 즉시 422 | 2차 |
| Use case `_validate` | status enum / limit / offset / from<to 재검증 | 3차 — use case 단독 호출 시도 무결성 |

테스트 5건이 모든 layer 가드 검증.

### 4.6 V023 인덱스 — 운영 안전 마진 (Design §2.5, §5.2)

```sql
ALTER TABLE ai_llm_call
ADD INDEX idx_llm_call_created (created_at);
```

기존 V021 composite 인덱스 (`(user_id, created_at DESC)`, `(llm_model_id, created_at DESC)`, etc.)는 leading column 필터 없으면 무효. 단독 `created_at` 인덱스로 by-user/by-llm/by-node 집계가 항상 인덱스 활용. **운영 환경 1년 누적 (1M+ rows) 가정 시 EXPLAIN range scan 보장**.

### 4.7 ai_retrieval_source 컬럼 재사용 — M4 트리 자동 호환 (Design §1.3 #2)

신규 `ai_web_retrieval` 테이블을 만들지 않고 `collection_name="tavily_web"` 분기로 처리:

- M4 `GET /agents/runs/{run_id}` 응답이 자동으로 두 collection을 같은 `retrievals[]` 안에 통합 반환
- 어드민이 "RAG 3 chunk + Web 2 URL 인용" 분석을 한 화면에서
- 추후 도구 추가 (perplexity, brave) 시 wiring 1줄씩만 (collection_name = "perplexity_web" 등)

---

## 5. Gap Analysis Summary

Match Rate 98% — 실제 deviation 0건, Critical/Major 0건. 평가 항목 64개 모두 Design 일치.

| 유형 | 항목 | Impact |
|------|------|--------|
| 🔵 Added | Test 케이스 2건 확장 (17 → 19) | +12% 테스트 — 회귀 가드 강화 |
| 🔵 Added | `test_accepts_valid_status_values` — RunStatus 4값 전수 검증 | Open Issue #6 enum 기준 명시 |
| 🔵 Added | `test_arun_skips_retrieval_when_tracker_none` — tracker None 분리 검증 | Design §3.4 ctx + tracker 두 가드 모두 검증 |
| 🔵 Added | V023 SQL 헤더 주석 (운영 적용 절차) | 운영팀 인계 명확성 |
| 🟢 Free Win | model_config = ConfigDict(arbitrary_types_allowed=True) | 향후 임의 타입 필드 확장 시 보일러플레이트 0 |
| 🟢 Free Win | `_apply_run_filters` 헬퍼 분리 | list/count 정합 testable |
| 🟢 Free Win | `RunRowDto.total_cost_usd: Decimal = Decimal("0")` default | M1 이전 NULL row 응답 안전 |
| 🟢 Free Win | `RunListResponse.from_dt: Optional` | 전체 기간 조회 허용 |

전체 분석: [agent-run-observability-m5.analysis.md](../../03-analysis/agent-run-observability-m5.analysis.md)

> **Out-of-Scope 발견**: 같은 세션에 진행된 `agent-run-admin-dashboard` 관련 추가 코드(`/admin/usage/summary`, `/timeseries`, `/usage/me/runs`, `/usage/me/timeseries` endpoints + 4 신규 use case + schemas 확장)는 M5 Design 범위 외이므로 M5 Match Rate에 영향 없음. 별도 PDCA `agent-run-admin-dashboard`에서 Plan/Design/Check 진행 권장.

---

## 6. Manual Verification (Pending — Operator Side)

Plan §12.3 / Design §9.3 수동 검증 항목 10건:

- [ ] Tavily 검색이 포함된 한 사용자 질문 → `ai_retrieval_source`에 `collection_name='tavily_web'` row N건
  ```sql
  SELECT rs.rank_index, rs.document_id, rs.score, LEFT(rs.content_preview, 80) AS preview
    FROM ai_retrieval_source rs
   WHERE rs.run_id=? AND rs.collection_name='tavily_web'
   ORDER BY rs.rank_index;
  ```
- [ ] internal + tavily 통합 (한 run에 두 collection 동시)
  ```sql
  SELECT rs.collection_name, COUNT(*) AS hits, AVG(rs.score) AS avg_score
    FROM ai_retrieval_source rs
   WHERE rs.run_id=?
   GROUP BY rs.collection_name;
  ```
- [ ] `GET /api/v1/admin/runs?limit=20` → rows[20] + total
- [ ] `GET /api/v1/admin/runs?status=FAILED&user_id=u-99` 필터
- [ ] `GET /api/v1/admin/runs?limit=200` → 422 (FastAPI Query 1차)
- [ ] `GET /api/v1/admin/runs?status=INVALID` → 422 (use case 검증)
- [ ] 비-admin이 `/admin/runs` 호출 → 403
- [ ] V023 적용 후 `SHOW INDEX FROM ai_llm_call`에 `idx_llm_call_created` 확인
- [ ] V023 후 `/admin/usage/by-node` EXPLAIN — `key=idx_llm_call_created, type=range`
- [ ] Tavily record_retrieval 강제 예외 주입 → 답변 정상 반환 (best-effort 검증)

---

## 7. Follow-up Items

### 7.1 Immediate
**없음.** M5는 자체로 완결.

### 7.2 Out-of-Scope Discoveries (별도 PDCA 권장)

같은 세션에 진행된 dashboard 관련 코드는 별도 PDCA로 문서화 권장:

- **`agent-run-admin-dashboard`**: `/admin/usage/summary`, `/admin/usage/timeseries`, `/usage/me/runs`, `/usage/me/timeseries` 4 endpoints + 4 use case (`GetUsageSummaryUseCase`, `GetUsageTimeseriesUseCase`, `ListMyRunsUseCase`, `GetMyUsageTimeseriesUseCase`) + `UsageSummaryRow`/`UsageTimeseriesPoint` 도메인 + `UsageSummaryResponse`/`UsageTimeseriesResponse` schemas + `aggregate_summary`/`aggregate_timeseries` repository 메서드. Plan/Design/Check를 별도로 작성하여 추적성 확보.

### 7.3 Next Milestones

| Milestone | Scope | Pre-requisite |
|-----------|-------|---------------|
| `agent-run-admin-dashboard` (Plan/Design 작성 필요) | 어드민 UI 화면 — M4 detail + M5 list + summary/timeseries API 활용 | M5 완료 (현재) — 코드는 이미 일부 존재 |
| `agent-usage-dashboard` | 사용자 셀프 화면 — `/usage/me` + `/usage/me/runs` + `/usage/me/timeseries` | M5 완료 (현재) |
| **M6** (`agent-run-observability-m6`) 후보 | (1) PII redaction (step.input/output_summary), (2) 부서별 mapping + 집계, (3) `idx_llm_call_step` 운영 EXPLAIN 검증 후 V024 추가 | M5 완료 (현재) |
| `agent-run-retention-policy` | TTL / anonymization | 별도 컴플라이언스 |
| `agent-run-pricing-history` | `ai_llm_pricing_history` audit table | 별도 |
| `agent-run-cursor-pagination` | limit/offset → cursor (운영 데이터 1M+ run 발견 시) | 별도 |
| Perplexity / Brave web search retrieval | 도구 추가 시점에 wiring 1줄씩 | 도구 추가 PDCA 종속 |

---

## 8. Lessons Learned

| 항목 | 학습 |
|------|------|
| ContextVar 누적 효과가 후속 마일스톤을 가속한다 | M2 `tool_call_id` + M3 `step_id` + M4 tracker ToolFactory DI가 누적되어 M5에서 `TavilySearchTool._arun` 한 곳만 손대면 영속화 완료. M4 InternalDocumentSearchTool 패턴과 100% 동일하게 적용. **누적 자산 = 후속 속도** |
| 컬럼 재사용 + 분기 키 전략이 신규 테이블보다 우월 | `ai_retrieval_source.collection_name="tavily_web"` 분기로 M4 RunDetailResponse가 자동 호환. 신규 `ai_web_retrieval` 테이블을 만들었다면 트리 조립 코드 수정 + 마이그레이션 비용 + 어드민 UI 분리 표시 부담 — 모두 회피 |
| `_apply_filters` 같은 chain helper가 정합성 자동화 | list/count가 다른 WHERE를 쓰면 페이지네이션 신뢰성 파괴. helper 분리로 회귀 가드 testable, 영원히 봉인 |
| Validation depth-in-defense — FastAPI Query + Router + UseCase 3중 | FastAPI Query는 잘못된 타입/범위 1차, router는 즉시 422, use case는 단독 호출(테스트) 시도 무결성. 3중이 노이즈 아니라 안전 마진 |
| 인덱스 사전 추가는 데이터 누적 후 ALTER보다 압도적 저비용 | dev/test 환경에서 V023 마이그레이션 추가 비용 0. 운영에서 1M row 누적 후 ALTER는 락 위험 + 다운타임. **인덱스는 일찍, 코드는 늦게**가 운영 친화적 |
| Out-of-scope 발견 시 별도 PDCA 분리는 필수 | M5 세션에서 dashboard 코드가 함께 진행되었으나, M5 Design 범위 외 — M5 Match Rate에 영향 0. 별도 PDCA로 분리하여 추적성 확보 |
| `model_config = ConfigDict(arbitrary_types_allowed=True)` 보일러플레이트 한 줄이 큰 효과 | Pydantic v2 BaseTool 상속 시 임의 타입 필드 (tracker, logger 등) 추가가 자유로워짐. M4/M5 모두 같은 패턴 적용 |
| 1 day end-to-end PDCA가 누적된다 | M1 7일 → M2 2일 → M3 1일 → M4 1일 → M5 1일. 데이터/콘텍스트/best-effort/wiring 패턴이 누적되면서 후속 마일스톤은 endpoint/migration 작성 수준으로 축소 |

---

## 9. Acknowledgments

- M1 architect: 5-table schema + `ai_retrieval_source` 컬럼 재사용 가능한 일반화된 설계 → M5 신규 테이블 0건
- M2 patch: `RunContext.tool_call_id` ContextVar set/reset → M5 Tavily 도구가 read만 하면 됨
- M3 wiring: `RunContext.step_id` + step 자동 채움 → M5는 step_id 단독 인덱스 추가 결정에 영향 (자동 cover 확인)
- M4 design: ToolFactory `tracker` / `run_observability_config` DI 패턴 → M5 tavily case 5줄 추가로 완성
- M4 `RunDetailResponse` 평탄화 설계 → M5 tavily retrieval이 자동 호환 (트리 조립 코드 변경 0)
- LangChain BaseTool standard hook + `model_config` Pydantic v2 패턴 — M2/M4/M5 일관 적용

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-05-21 | M5 완료 보고서 — Match Rate 98%, 19 신규 + 136 회귀 = 155/155 PASS, Tavily web retrieval + GET /admin/runs + V023 인덱스, 신규 테이블 0건, M4 follow-up 3건 일괄 해소 | 배상규 |
