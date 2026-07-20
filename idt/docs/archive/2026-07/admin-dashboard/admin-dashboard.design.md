# admin-dashboard Design Document

> **Summary**: 관리자 운영 현황 대시보드 — 신규 백엔드는 `/admin/dashboard/*` 4개 엔드포인트(적재/사용자 현황 stats·KB별 현황·최근 업로드·헬스체크)로 한정하고, 기간 의존 지표(질문 수·성공률·토큰·비용·추이·최근 질문/에러)는 기존 `/admin/usage/*`·`/admin/runs` API와 프론트 훅·컴포넌트를 전면 재사용
>
> **Project**: sangplusbot (idt 백엔드 + idt_front 풀스택)
> **Author**: 배상규
> **Date**: 2026-07-18
> **Status**: Draft
> **Plan Reference**: `docs/01-plan/features/admin-dashboard.plan.md`

---

## 1. Overview

### 1.1 Design Goals

1. **수치 단일 소스**: 질문/비용 지표는 기존 usage API만 사용 — AdminAgentRunsPage와 대시보드 수치가 항상 일치
2. **최소 신설**: 신규 백엔드는 "기존 API가 못 주는 것"(적재량·사용자 수·KB별 분포·헬스)만 구현
3. **장애 내성**: 저장소 1개 다운이 대시보드 전체를 죽이지 않음 (부분 실패 격리)
4. **기존 관례 준수**: DI placeholder+override, `require_role("admin")`, PeriodFilter/훅 재사용, MSW 테스트 패턴

### 1.2 Design Principles

- 읽기 전용 기능 — DB 스키마 변경·마이그레이션 없음, 쓰기 경로 없음
- 집계는 SQL COUNT/SUM/GROUP BY로 수행 (전체 행 로딩 금지)
- domain에 신규 비즈니스 규칙 없음 — DTO/포트 정의만

### 1.3 Plan 리스크·이월 항목 검증 결과 (2026-07-18 실코드 확인)

| 항목 | 확인 결과 | 근거 |
|------|-----------|------|
| usage summary 커버 범위 | `total_runs/success_runs/failed_runs/success_rate/total_tokens/total_cost_usd` + from/to — **기간 지표 완전 커버**. stats 이중 구현 불필요 확정 | `src/interfaces/schemas/agent_run_response.py:328-343` |
| `/admin/runs` 필터 | `status`(RUNNING/SUCCESS/FAILED/CANCELLED)·user_id·agent_id·from/to·limit(1-100)/offset 지원 — 최근 질문/에러 목록 재사용 가능 | `src/api/routes/agent_run_router.py:259-299` |
| 기간 기본값 | `_resolve_period` 미지정 시 최근 30일 강제 | `agent_run_router.py:313` 사용부 |
| SummaryCards 재사용성 | props가 usage 4종(totalRuns/successRate/totalTokens/totalCostUsd)에 **하드코딩** — usage 섹션엔 그대로 재사용, 적재 KPI엔 내부 `Card`(generic, 미export) 추출 필요 | `AdminAgentRunsPage/components/SummaryCards.tsx:1-36` |
| TimeseriesChart 재사용성 | props `points`+`loading`만 — 그대로 재사용. UsageMePage가 이미 cross-page import 선례 | `TimeseriesChart.tsx:14-17`, `UsageMePage/index.tsx:8-10` |
| 날짜 범위 필터 | 공통 `PeriodFilter`(preset+from/to, `resolvePeriod`) 이미 존재 — 자유 범위 요구 충족, 신규 구현 불필요 | `AdminAgentRunsPage/index.tsx:4-7,43-46` |
| 기존 프론트 훅 | `useAdminUsageSummary/useAdminUsageTimeseries/useAdminRuns` 등 존재 — 대시보드 페이지에서 직접 호출 | `hooks/useAgentRunAdmin.ts` |
| admin DI 패턴 | 라우터에 placeholder 팩토리(`raise NotImplementedError`) 선언 → `create_app`에서 override | `agent_run_router.py:77-121` |
| 사용자 상태 | `users.status` Enum(pending/approved/rejected), `role` Enum(user/admin) | `src/infrastructure/auth/models.py:16-26` |
| 헬스 ping 어댑터 재료 | Qdrant `QdrantClientFactory.create()`, ES `ElasticsearchClient.from_config()`, MySQL `get_session` — 모두 기존 존재 | `infrastructure/vector/qdrant_client.py:34-38`, `elasticsearch/es_client.py` |
| admin 화면 배선 | `App.tsx` 라우트 + `constants/adminNav.ts` 메뉴 + `AdminLayout` | `App.tsx:77`, `constants/adminNav.ts:32` |

---

## 2. Design Decisions (D1–D9)

| ID | Decision | 선택 | 근거 |
|----|----------|------|------|
| D1 | stats API의 기간 파라미터 | **from/to 없음 (기간 무관 누적 현황만)** | 기간 지표는 usage API가 완전 커버(§1.3) — stats는 KB/문서/청크/사용자 누적만 담당. Plan 리스크 "수치 이중 구현" 원천 제거 |
| D2 | 신규 라우터 | `admin_dashboard_router.py`, prefix `/api/v1/admin/dashboard`, DI placeholder+`create_app` override | admin_router(사용자 승인 전용) 단일 책임 유지, agent_run_router 선례 준수 |
| D3 | 유스케이스/리포 배치 | `domain/admin_dashboard/`(DTO+포트) + `application/admin_dashboard/use_cases.py`(4개 경량 유스케이스) + `infrastructure/admin_dashboard/`(집계 리포+헬스 어댑터). 집계 리포는 `Depends(get_session)` 단일 세션 조립 | Thin DDD·DB-001 준수. 유스케이스가 얇아(각 위임 1회) 한 파일 4클래스 허용 |
| D4 | kb-breakdown 조인 | `knowledge_base` **LEFT JOIN** (document_metadata를 kb_id로 GROUP BY한 서브쿼리) — 문서 0건 KB도 행 노출. kb_id NULL 문서는 breakdown에서 제외하고 stats의 `documents.without_kb`로 별도 집계 | FR-04(빈 KB 식별) + V047 이전/일반 업로드 문서의 수치 누락 방지 |
| D5 | 헬스체크 실행 모델 | 컴포넌트별 ping을 `asyncio.gather` 병렬 + 개별 `asyncio.wait_for(timeout=3s)`. MySQL=`SELECT 1`, Qdrant=`get_collections()`, ES=`ping()`. 실패/타임아웃은 해당 컴포넌트만 `fail` — HTTP는 항상 200 | FR-07·가용성 NFR. 어댑터는 `create_app`에서 1회 생성해 주입(요청마다 클라이언트 생성 금지) |
| D6 | 적재 KPI 카드 컴포넌트 | `SummaryCards.tsx`의 내부 `Card`를 **named export로 추출**(기존 default export 무변경 — additive)하여 대시보드 적재 KPI에 재사용 | 스타일 일관성 + 중복 구현 방지. 기존 화면 회귀 없음 |
| D7 | 페이지 데이터 소스 구성 | 신규 훅 4종(`useAdminDashboard*`) + 기존 훅 3종(`useAdminUsageSummary/Timeseries/Runs`) 조합. 새로고침 버튼 = `queryClient.invalidateQueries`(대시보드 관련 쿼리키 전체) | 백엔드 재사용 극대화. 수동 새로고침 확정사항 반영 |
| D8 | 최근 질문/에러 목록 | 기존 `/admin/runs` 2회 호출: ① 최신 5건(필터 없음) ② `status=FAILED` 최신 5건 — 페이지의 기간 필터를 그대로 전달 | 백엔드 무변경. RunListTable 대신 경량 패널(행 클릭 시 `/admin/agent-runs/:runId` 이동) |
| D9 | recent-documents 파라미터 | `?limit=10`(default 10, ge=1 le=50). 정렬 `created_at DESC`, `idx_dm_created` 활용. kb_name은 knowledge_base LEFT JOIN으로 채움(NULL=일반 업로드) | FR-05. 단순 최신순 목록으로 한정 |

---

## 3. Architecture

### 3.1 Data Flow

```
AdminDashboardPage
 ├─ [신규] GET /admin/dashboard/stats            ──▶ DashboardStatsUseCase ──▶ AggregationRepository (MySQL COUNT/SUM)
 ├─ [신규] GET /admin/dashboard/kb-breakdown     ──▶ KbBreakdownUseCase   ──▶ AggregationRepository (LEFT JOIN GROUP BY)
 ├─ [신규] GET /admin/dashboard/recent-documents ──▶ RecentDocumentsUseCase ─▶ AggregationRepository (ORDER BY created_at DESC)
 ├─ [신규] GET /admin/dashboard/health           ──▶ HealthCheckUseCase   ──▶ HealthAdapter (MySQL/Qdrant/ES 병렬 ping, 3s timeout)
 ├─ [재사용] GET /admin/usage/summary            (기간) — useAdminUsageSummary
 ├─ [재사용] GET /admin/usage/timeseries         (기간) — useAdminUsageTimeseries
 └─ [재사용] GET /admin/runs (×2: 최신/FAILED)   (기간) — useAdminRuns
```

### 3.2 API 계약 (신규 4종 — 모두 `require_role("admin")`)

**`GET /api/v1/admin/dashboard/stats`** (파라미터 없음 — D1)

```json
{
  "kb": { "total": 12, "active": 11, "by_scope": { "PERSONAL": 5, "DEPARTMENT": 4, "PUBLIC": 3 } },
  "documents": { "total": 340, "with_kb": 310, "without_kb": 30 },
  "chunks": { "total": 15820 },
  "users": { "total": 25, "approved": 20, "pending": 4, "admins": 2 }
}
```

- `chunks.total` = `SUM(document_metadata.chunk_count)` — MySQL 메타 기준(저장소 실측 아님, 화면 툴팁 고지)
- `documents.without_kb` = `kb_id IS NULL` (일반 업로드 + V047 이전 문서)

**`GET /api/v1/admin/dashboard/kb-breakdown`**

```json
{
  "rows": [
    { "kb_id": "…", "name": "여신 규정집", "scope": "PUBLIC", "status": "active",
      "document_count": 42, "chunk_count": 1830, "last_uploaded_at": "2026-07-17T09:12:00" }
  ]
}
```

- `knowledge_base LEFT JOIN (SELECT kb_id, COUNT(*), SUM(chunk_count), MAX(created_at) FROM document_metadata GROUP BY kb_id)` — 문서 0건 KB는 count 0·`last_uploaded_at` null (D4)
- 정렬: `document_count DESC, name ASC`

**`GET /api/v1/admin/dashboard/recent-documents?limit=10`** (limit ge=1 le=50)

```json
{
  "rows": [
    { "document_id": "…", "filename": "규정개정.pdf", "kb_id": "…", "kb_name": "여신 규정집",
      "collection_name": "kb_main", "chunk_count": 45, "chunk_strategy": "clause_aware",
      "created_at": "2026-07-18T08:30:00" }
  ]
}
```

**`GET /api/v1/admin/dashboard/health`** (항상 HTTP 200 — D5)

```json
{
  "components": [
    { "name": "mysql",         "status": "ok",   "latency_ms": 4,    "error": null },
    { "name": "qdrant",        "status": "ok",   "latency_ms": 12,   "error": null },
    { "name": "elasticsearch", "status": "fail", "latency_ms": null, "error": "timeout(3s)" }
  ]
}
```

**재사용 (변경 없음)**: `GET /admin/usage/summary`, `GET /admin/usage/timeseries`, `GET /admin/runs?status=&limit=&from=&to=`

### 3.3 신규/변경 파일

**백엔드 (idt/)**

| 파일 | 신규/변경 | 내용 |
|------|-----------|------|
| `src/domain/admin_dashboard/schemas.py` | 신규 | DTO dataclass: `DashboardStats`, `KbBreakdownRow`, `RecentDocumentRow`, `HealthComponent` |
| `src/domain/admin_dashboard/interfaces.py` | 신규 | `DashboardAggregationRepositoryInterface`(get_stats/get_kb_breakdown/get_recent_documents), `StorageHealthPort`(check_all) |
| `src/application/admin_dashboard/use_cases.py` | 신규 | 4개 경량 유스케이스 (D3) — 로깅 포함 |
| `src/infrastructure/admin_dashboard/aggregation_repository.py` | 신규 | MySQL 집계 쿼리 구현 (session 주입, commit 금지) |
| `src/infrastructure/admin_dashboard/health_adapter.py` | 신규 | MySQL/Qdrant/ES 병렬 ping, wait_for 3s, 예외→fail 변환 (D5) |
| `src/interfaces/schemas/admin_dashboard_response.py` | 신규 | Pydantic 응답 4종 (`from_dto` classmethod 관례) |
| `src/api/routes/admin_dashboard_router.py` | 신규 | prefix `/api/v1/admin/dashboard`, DI placeholder 4종, `require_role("admin")` |
| `src/api/main.py` (또는 create_app 모듈) | 변경 | 라우터 등록 + DI override 배선 |
| `tests/application/admin_dashboard/test_use_cases.py` | 신규 | 유스케이스 단위 (선행) |
| `tests/infrastructure/admin_dashboard/test_health_adapter.py` | 신규 | ok/fail/timeout 격리 (선행) |
| `tests/api/test_admin_dashboard_router.py` | 신규 | 401/403/200 스키마 (선행) |

**프론트엔드 (idt_front/)**

| 파일 | 신규/변경 | 내용 |
|------|-----------|------|
| `src/constants/api.ts` | 변경 | `ADMIN_DASHBOARD_STATS/KB_BREAKDOWN/RECENT_DOCUMENTS/HEALTH` 4종 추가 |
| `src/types/adminDashboard.ts` | 신규 | 응답 타입 4종 (백엔드 계약 동기화 §4-1) |
| `src/services/adminDashboard.ts` | 신규 | fetch 함수 4종 |
| `src/hooks/useAdminDashboard.ts` | 신규 | TanStack Query 훅 4종 (staleTime 짧게, refetch 수동) |
| `src/pages/AdminDashboardPage/index.tsx` | 신규 | 페이지 조립 (§3.4 레이아웃) |
| `src/pages/AdminDashboardPage/components/HealthBadges.tsx` | 신규 | 컴포넌트별 ok/fail 배지 + 응답시간 |
| `src/pages/AdminDashboardPage/components/StatCardsRow.tsx` | 신규 | 적재 KPI 카드 (Card 재사용 — D6) |
| `src/pages/AdminDashboardPage/components/KbBreakdownTable.tsx` | 신규 | KB별 현황 테이블 |
| `src/pages/AdminDashboardPage/components/RecentDocumentsTable.tsx` | 신규 | 최근 업로드 목록 |
| `src/pages/AdminDashboardPage/components/RecentRunsPanel.tsx` | 신규 | 최근 질문 5건 + 실패 5건 (D8, 행 클릭 → run 상세) |
| `src/pages/AdminAgentRunsPage/components/SummaryCards.tsx` | 변경 | 내부 `Card` named export 추가 (additive — D6) |
| `src/App.tsx` | 변경 | `/admin/dashboard` 라우트 |
| `src/constants/adminNav.ts` | 변경 | 대시보드 메뉴 항목 (최상단) |
| 각 신규 모듈 `.test.tsx` | 신규 | Vitest+MSW 선행 (파일별 3종 훅, `--pool=threads`) |

### 3.4 페이지 레이아웃

```
┌ 헤더: "운영 대시보드" ── PeriodFilter(기간 지표용) ── [새로고침] ┐
├ HealthBadges: MySQL ●ok  Qdrant ●ok  ES ●fail(timeout)          │
├ 적재 KPI (기간 무관): [KB 수] [문서 수] [청크 수] [사용자 수]     │
├ 사용량 KPI (기간): SummaryCards 재사용 [총 질문][성공률][토큰][비용]│
├ TimeseriesChart 재사용 (일별 질문·토큰·비용)                      │
├ ┌ KbBreakdownTable ─────────┐ ┌ RecentDocumentsTable ─────────┐ │
│ └───────────────────────────┘ └───────────────────────────────┘ │
└ RecentRunsPanel (최근 질문 5 · 실패 5)                            ┘
```

- 적재 KPI에는 "MySQL 메타 기준" 툴팁(hint) 표기 (Plan 리스크 대응)
- 기간 무관/기간 의존 섹션을 시각적으로 구분 (기간 라벨은 사용량 KPI 위에 표시)

---

## 4. Error Handling

| 상황 | 처리 |
|------|------|
| 비인증 / 비admin | 401 / 403 (`require_role("admin")` — 기존 의존성) |
| 저장소 ping 실패·타임아웃 | 해당 컴포넌트만 `status="fail"` + error 문자열, HTTP 200 유지 (D5) |
| 집계 쿼리 실패 | 500 + `LoggerInterface` 구조화 로그(request_id, stack) — print 금지 |
| 프론트 개별 위젯 에러 | 위젯 단위 에러/빈 상태 UI — 다른 위젯 렌더링 계속 (쿼리 격리) |
| ai_run 데이터 없음 | TimeseriesChart 기존 빈 상태 문구 재사용, 카드 0 표시 |

---

## 5. Test Plan (TDD — 테스트 선행)

### 5.1 단위 (백엔드)

- [ ] stats: 빈 DB → 전부 0 / KB scope별·user status별 분리 집계 / without_kb(kb_id NULL) 분리
- [ ] kb-breakdown: 문서 0건 KB 행 포함(count 0, last_uploaded_at null) / SUM·MAX 정확성 / 정렬
- [ ] recent-documents: limit 경계(1/50/기본 10) / created_at DESC / kb_name NULL 허용
- [ ] health_adapter: 3종 ok / 1종 예외 → 해당만 fail / wait_for 타임아웃 → fail("timeout") / 병렬 실행(총 소요 ≈ max, not sum)

### 5.2 통합 (백엔드 라우터)

- [ ] 미인증 401, user 역할 403, admin 200 (4개 엔드포인트 공통)
- [ ] 응답 스키마 계약(§3.2) 검증, recent-documents limit=0/51 → 422

### 5.3 프론트 (Vitest + MSW, `--pool=threads`, 파일별 3종 훅)

- [ ] services/hooks: 4종 엔드포인트 호출·타입 매핑
- [ ] StatCardsRow/HealthBadges/KbBreakdownTable/RecentDocumentsTable/RecentRunsPanel: 정상·빈 상태·(헬스) fail 배지 렌더
- [ ] 페이지: 위젯 조립 렌더, 새로고침 버튼 → invalidate 호출, PeriodFilter 변경 시 기간 훅 파라미터 반영
- [ ] SummaryCards 기존 테스트 회귀 없음 (Card export additive 확인)

### 5.4 수동 E2E (Qdrant/ES 실기동 시 — 공통 이월 체크리스트 등재)

- [ ] 실데이터 적재 후 stats 수치 = DB 직접 쿼리 결과 일치
- [ ] ES 중지 상태에서 헬스 fail 표시 + 나머지 위젯 정상 로딩

---

## 6. Clean Architecture — Layer Assignment

| Layer | 모듈 | 책임 |
|-------|------|------|
| domain | `admin_dashboard/schemas.py`, `interfaces.py` | DTO·포트 정의만 (외부 의존 없음) |
| application | `admin_dashboard/use_cases.py` | 위임·로깅 (비즈니스 규칙 없음 — 읽기 집계) |
| infrastructure | `aggregation_repository.py`, `health_adapter.py` | SQL 집계·저장소 ping (commit/rollback 금지) |
| interfaces/api | `admin_dashboard_router.py`, `admin_dashboard_response.py` | 요청 검증·DTO→응답 변환·위임만 |

DB-001: 집계 리포는 `Depends(get_session)` 단일 세션. 헬스 어댑터의 Qdrant/ES 클라이언트는 `create_app`에서 1회 생성 주입(lifespan 세션 보유 아님 — AsyncSession은 요청 단위 유지).

---

## 7. Implementation Order

1. **백엔드 도메인/테스트**: domain DTO·포트 → 유스케이스 테스트(Red) → use_cases.py(Green)
2. **집계 리포**: 리포 테스트(Red) → aggregation_repository.py(Green)
3. **헬스 어댑터**: 타임아웃/격리 테스트(Red) → health_adapter.py(Green)
4. **라우터/배선**: 라우터 테스트(401/403/스키마, Red) → admin_dashboard_router.py + main.py 배선(Green)
5. **프론트 계약**: api.ts 상수 → types → services/hooks (MSW 테스트 선행)
6. **프론트 컴포넌트**: Card export → StatCardsRow/HealthBadges/테이블·패널 (컴포넌트 테스트 선행)
7. **페이지 조립**: AdminDashboardPage + App.tsx 라우트 + adminNav 항목
8. **검증**: `/verify-architecture`, `/verify-tdd`, `/verify-logging` → `/pdca analyze admin-dashboard`

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-07-18 | Initial draft — Plan 이월 항목 실코드 검증(usage API 커버 범위·runs 필터·PeriodFilter·컴포넌트 재사용성) 완료, D1~D9 확정 | 배상규 |
