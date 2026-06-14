---
template: design
version: 1.2
feature: agent-run-admin-dashboard
date: 2026-05-21
author: AI Assistant
project: sangplusbot (idt + idt_front)
status: Draft
---

# agent-run-admin-dashboard Design Document

> **Summary**: M4가 만든 6개 read API 위에 **신규 5개 엔드포인트**(admin/agents/runs 목록, admin/usage/summary, admin/usage/timeseries, usage/me/runs, usage/me/timeseries)를 얹고, FE는 **Admin 통합 대시보드 + 사용자 My Usage** 3개 페이지를 구현. DB 마이그레이션 0건, M4 컨벤션(UseCase per endpoint, Aggregator 래핑, 도메인 dataclass row) 100% 유지.
>
> **Project**: sangplusbot (idt + idt_front)
> **Version**: 1.0
> **Author**: AI Assistant
> **Date**: 2026-05-21
> **Status**: Draft
> **Planning Doc**: [agent-run-admin-dashboard.plan.md](../../01-plan/features/agent-run-admin-dashboard.plan.md)

### Pipeline References

| Phase | Document | Status |
|-------|----------|--------|
| Phase 1 | M1 Plan (스키마 정의: V021 마이그레이션) | ✅ (선행 archived) |
| Phase 2 | `idt/CLAUDE.md` + `idt_front/CLAUDE.md` | ✅ |
| Phase 4 | 본 문서 §4 | ✅ |
| Phase 5 | 본 문서 §5 (mockup) | ✅ |

---

## 1. Overview

### 1.1 Design Goals

- **무-마이그레이션 원칙**: M1 V021 스키마(`ai_run`, `ai_run_step`, `ai_tool_call`, `ai_llm_call`, `ai_retrieval_source`)와 기존 인덱스만 사용한다. SQL 신규 컬럼 0건.
- **M4 컨벤션 1:1 유지**: UseCase per endpoint, `Aggregator`가 Repository 호출, Repository는 domain dataclass row 반환, Route는 `_resolve_period` 헬퍼 재사용.
- **권한 계층 명확화**: admin 엔드포인트는 `require_role("admin")`, me 엔드포인트는 `get_current_user`만 — UseCase 시그니처에 `user_id`를 강제 주입.
- **풀스택 동기화**: Backend 응답 스키마 → FE 타입을 1:1 매핑 (수동 sync — `api-contract` skill로 검증).
- **재사용 가능한 FE 빌딩블록**: SummaryCards/TimeseriesChart/RunListTable을 페이지 독립 컴포넌트로 분리하여 admin/me 양쪽 페이지에서 재사용.

### 1.2 Design Principles

1. **DDD Thin Architecture** — domain(룰) ⟂ application(흐름) ⟂ infrastructure(IO) ⟂ interfaces(HTTP). Repository 시그니처는 domain interface가 소유.
2. **TDD Red→Green** — UseCase 단위 테스트 선작성, 라우트는 통합테스트(mock UseCase) 선작성.
3. **SQL-Side Aggregation** — 시계열·요약은 client 계산이 아닌 `GROUP BY DATE(...)` SQL.
4. **Offset Pagination** — 1만 row 이하 운영 가정에서 offset이 단순·예측 가능.
5. **Server-Enforced Self Filter** — `/usage/me/*`는 컨트롤러에서 `current_user.id` 주입, UseCase는 이를 인자로 받고 그 외 user_id 접근 불가.

---

## 2. Architecture

### 2.1 Component Diagram

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                              idt_front (React)                                │
│  ┌──────────────────────┐  ┌──────────────────────┐  ┌────────────────────┐ │
│  │ AdminAgentRunsPage   │  │ AgentRunDetailPage   │  │  UsageMePage       │ │
│  │  - SummaryCards      │  │  - StepTree          │  │  - SummaryCards    │ │
│  │  - TimeseriesChart   │  │  - LangSmith link    │  │  - TimeseriesChart │ │
│  │  - Tabs(4)           │  │                      │  │  - RunListTable    │ │
│  │  - RunListTable      │  │                      │  │  (my)              │ │
│  └──────────┬───────────┘  └──────────┬───────────┘  └─────────┬──────────┘ │
│             │                          │                        │             │
│             ▼                          ▼                        ▼             │
│   useAgentRunAdmin (hooks)   useAgentRunDetail            useUsageMe         │
│             │                          │                        │             │
│             ▼                          ▼                        ▼             │
│   agentRunAdminService           (M4 service reuse)        usageMeService   │
└──────────────┬──────────────────────────┬──────────────────────┬─────────────┘
               │                          │                      │
               │     HTTPS (Bearer JWT)   │                      │
               ▼                          ▼                      ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                              idt (FastAPI)                                    │
│                                                                              │
│   /api/v1/admin/agents/runs       ─┐                                        │
│   /api/v1/admin/usage/summary      │   require_role("admin")                │
│   /api/v1/admin/usage/timeseries   │                                        │
│                                    │                                        │
│   /api/v1/usage/me/runs            ─┐                                        │
│   /api/v1/usage/me/timeseries      │   get_current_user                      │
│                                    │                                        │
│   /api/v1/agents/runs/{id}         ─── self or admin (기존)                  │
│                                    │                                        │
│              ▼                                                              │
│   ┌─────────────────────────────────────────────────────────────┐           │
│   │  Application Layer (UseCase per endpoint)                    │           │
│   │   ListRunsUseCase / GetUsageSummaryUseCase /                 │           │
│   │   GetUsageTimeseriesUseCase / ListMyRunsUseCase /            │           │
│   │   GetMyUsageTimeseriesUseCase                                │           │
│   │   → UsageAggregator (M4 확장)                                 │           │
│   └─────────────────────┬───────────────────────────────────────┘           │
│                         ▼                                                    │
│   ┌─────────────────────────────────────────────────────────────┐           │
│   │  Domain Interfaces (확장)                                     │           │
│   │   AgentRunRepositoryInterface.list_runs(filter, page, size) │           │
│   │   LlmCallRepositoryInterface.aggregate_summary(...)         │           │
│   │   LlmCallRepositoryInterface.aggregate_timeseries(...)      │           │
│   └─────────────────────┬───────────────────────────────────────┘           │
│                         ▼                                                    │
│   ┌─────────────────────────────────────────────────────────────┐           │
│   │  Infrastructure (SQLAlchemy AsyncSession)                   │           │
│   │   AiRunRepository / LlmCallRepository                        │           │
│   └─────────────────────┬───────────────────────────────────────┘           │
│                         ▼                                                    │
│                  ┌──────────────┐                                            │
│                  │   MySQL      │  (V021 스키마 그대로)                       │
│                  └──────────────┘                                            │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Data Flow

```
[Admin Dashboard 로딩]
 ┌──────────────────────────────────────────────────────────────────┐
 │ 1. Page mount → 4 parallel queries:                              │
 │      GET /admin/usage/summary?from=...&to=...                    │
 │      GET /admin/usage/timeseries?from=...&to=...                 │
 │      GET /admin/usage/users?from=...&to=...   (M4 reuse)         │
 │      GET /admin/usage/llm-models?from=...&to=... (M4 reuse)      │
 │ 2. Tab switch → lazy query:                                      │
 │      GET /admin/usage/by-node   (M4 reuse)                       │
 │      GET /admin/agents/runs?user_id=&agent_id=&status=&page=&size= │
 │ 3. Run row click → router push → /admin/agent-runs/:runId        │
 │      GET /agents/runs/{runId}   (M4 reuse)                       │
 └──────────────────────────────────────────────────────────────────┘

[My Usage]
 ┌──────────────────────────────────────────────────────────────────┐
 │ 1. Page mount → 3 parallel queries:                              │
 │      GET /usage/me              (M4 reuse)                       │
 │      GET /usage/me/timeseries                                    │
 │      GET /usage/me/runs?page=1&size=20                           │
 │ 2. Run row click → /admin/agent-runs/:runId 와 동일 경로 진입     │
 │    백엔드 `/agents/runs/{id}`가 self/admin 분기 — 이미 구현됨    │
 └──────────────────────────────────────────────────────────────────┘
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `AdminAgentRunsPage` | `useAgentRunAdmin`, `agentRunAdminService`, `recharts` | 통합 대시보드 UI |
| `useAgentRunAdmin` | `agentRunAdminService`, TanStack Query | 서버 상태 fetch + cache |
| `agentRunAdminService` | `authApiClient`, `API_ENDPOINTS` | HTTP 호출 |
| `ListRunsUseCase` | `AgentRunRepositoryInterface` | run list 조회 |
| `GetUsageSummaryUseCase` | `UsageAggregator` (확장) | 카드 4종 집계 |
| `GetUsageTimeseriesUseCase` | `UsageAggregator` (확장) | 일자별 시계열 |
| `UsageAggregator` (확장) | `LlmCallRepositoryInterface`, `AgentRunRepositoryInterface` | SQL 집계 위임 |
| `AiRunRepository` | `AsyncSession`, `AgentRunModel` | M1 모델 read |
| `LlmCallRepository` | `AsyncSession`, `LlmCallModel` | M1 모델 read |

---

## 3. Data Model

### 3.1 Domain VOs/Rows (신규)

> M1 entities(`AgentRun`, `AgentRunStep`, `LlmCall` 등)는 그대로 사용한다.
> 본 PDCA는 **읽기 전용 dataclass row 4개**만 도메인에 추가한다.

```python
# src/domain/agent_run/interfaces.py 에 추가

@dataclass(frozen=True)
class RunListFilter:
    """Run 목록 조회 필터 VO."""
    from_dt: datetime
    to_dt: datetime
    user_id: Optional[str] = None      # admin이 특정 사용자로 좁힐 때
    agent_id: Optional[str] = None
    status: Optional[str] = None        # RUNNING/SUCCESS/FAILED/CANCELLED
    force_user_id: Optional[str] = None # me 라우트가 self 강제 필터링


@dataclass(frozen=True)
class RunListItem:
    """Run 목록 1행 (목록 카드/테이블용 — 상세 트리는 제외)."""
    id: str
    user_id: str
    agent_id: str
    status: str
    started_at: datetime
    ended_at: Optional[datetime]
    latency_ms: Optional[int]
    total_tokens: int
    total_cost_usd: Decimal
    llm_call_count: int
    langsmith_run_url: Optional[str]


@dataclass(frozen=True)
class UsageSummaryRow:
    """대시보드 카드 4종 단일 응답."""
    from_dt: datetime
    to_dt: datetime
    total_runs: int
    success_runs: int
    failed_runs: int
    total_tokens: int
    total_cost_usd: Decimal


@dataclass(frozen=True)
class UsageTimeseriesPoint:
    """일자별 시계열 1포인트 (bucket = 'day' 고정 v1)."""
    bucket: date          # YYYY-MM-DD
    run_count: int
    total_tokens: int
    total_cost_usd: Decimal
```

### 3.2 Repository Interface 확장

```python
# src/domain/agent_run/interfaces.py

class AgentRunRepositoryInterface(ABC):
    # ... 기존 메서드 ...

    @abstractmethod
    async def list_runs(
        self, filter_: RunListFilter, page: int, size: int
    ) -> tuple[List[RunListItem], int]:
        """Run 목록 + 총 개수. SQL: SELECT + COUNT(*) OVER() 또는 별도 COUNT."""


class LlmCallRepositoryInterface(ABC):
    # ... 기존 메서드 ...

    @abstractmethod
    async def aggregate_summary(
        self, from_dt: datetime, to_dt: datetime, user_id: Optional[str] = None
    ) -> UsageSummaryRow:
        """총 토큰·비용 (ai_llm_call) + run 수·성공/실패 수(ai_run) 통합 — 2 sub-queries."""

    @abstractmethod
    async def aggregate_timeseries(
        self,
        from_dt: datetime,
        to_dt: datetime,
        user_id: Optional[str] = None,
    ) -> List[UsageTimeseriesPoint]:
        """일자별 토큰/비용/run수 GROUP BY DATE(created_at)."""
```

> **선택 근거**: `aggregate_summary`와 `aggregate_timeseries`는 `ai_llm_call`과 `ai_run` 양쪽이 필요하지만, 호출 빈도·코드 응집을 위해 **`LlmCallRepository`에 집어넣고 내부에서 `ai_run` 테이블 모델을 함께 SELECT** 한다 (M4의 `aggregate_by_node`가 `ai_run_step` JOIN한 선례를 따른다). domain 인터페이스는 한쪽이 소유해도 무방.

### 3.3 Database Schema (확인용 — 변경 없음)

> V021 / V022 그대로 사용. 신규 인덱스/컬럼 0건.

활용할 인덱스:

| Table | Index | 활용처 |
|-------|-------|--------|
| `ai_run` | `idx_run_started_at (started_at DESC)` | summary, timeseries, list (정렬) |
| `ai_run` | `idx_run_user_started (user_id, started_at DESC)` | me/runs, admin/runs?user_id= |
| `ai_run` | `idx_run_agent (agent_id)` | admin/runs?agent_id= |
| `ai_run` | `idx_run_status (status)` | admin/runs?status= |
| `ai_llm_call` | `idx_llm_created_at (created_at DESC)` 추정 | summary tokens/cost |
| `ai_llm_call` | `idx_llm_user_created (user_id, created_at)` 추정 | me/timeseries |

> **검증 항목**: `ai_llm_call`의 user_id 기반 인덱스가 V021에 명시돼 있는지 Do 단계 첫 작업으로 확인. 없으면 V023으로 마이그레이션 1건 추가 — Plan §5 Risk에 명시됨(별도 승인 필요).

### 3.4 SQL Sketches (검증·튜닝 기준)

```sql
-- (A) GetUsageSummaryUseCase: 1회 호출, 30일 범위 가정
-- Part 1: tokens/cost from ai_llm_call
SELECT
    COALESCE(SUM(total_tokens), 0)     AS total_tokens,
    COALESCE(SUM(total_cost_usd), 0)   AS total_cost_usd
FROM ai_llm_call
WHERE created_at BETWEEN :from AND :to
  [AND user_id = :user_id];    -- me 라우트 전용

-- Part 2: run 수·성공/실패 from ai_run
SELECT
    COUNT(*)                                          AS total_runs,
    SUM(CASE WHEN status='SUCCESS' THEN 1 ELSE 0 END) AS success_runs,
    SUM(CASE WHEN status='FAILED'  THEN 1 ELSE 0 END) AS failed_runs
FROM ai_run
WHERE started_at BETWEEN :from AND :to
  [AND user_id = :user_id];


-- (B) GetUsageTimeseriesUseCase: 일자별 (UNION 으로 한 응답에 통합)
SELECT
    DATE(r.started_at)                                AS bucket,
    COUNT(DISTINCT r.id)                              AS run_count,
    COALESCE(SUM(c.total_tokens), 0)                  AS total_tokens,
    COALESCE(SUM(c.total_cost_usd), 0)                AS total_cost_usd
FROM ai_run r
LEFT JOIN ai_llm_call c
       ON c.run_id = r.id
      AND c.created_at BETWEEN :from AND :to
WHERE r.started_at BETWEEN :from AND :to
  [AND r.user_id = :user_id]
GROUP BY DATE(r.started_at)
ORDER BY bucket ASC;


-- (C) ListRunsUseCase: 페이지네이션
SELECT
    r.id, r.user_id, r.agent_id, r.status, r.started_at, r.ended_at,
    r.latency_ms, r.total_tokens, r.total_cost_usd,
    r.llm_call_count, r.langsmith_run_url
FROM ai_run r
WHERE r.started_at BETWEEN :from AND :to
  [AND r.user_id   = :user_id]
  [AND r.agent_id  = :agent_id]
  [AND r.status    = :status]
ORDER BY r.started_at DESC
LIMIT :size OFFSET :offset;

-- 동일 WHERE로 COUNT(*) 별도 쿼리 (인덱스 활용, 1만 row 이하 가정)
SELECT COUNT(*) FROM ai_run r WHERE ...;
```

---

## 4. API Specification

### 4.1 Endpoint List (신규 5건)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/v1/admin/agents/runs` | admin | Run 목록 (필터·페이지네이션) |
| GET | `/api/v1/admin/usage/summary` | admin | 카드 4종 단일 응답 |
| GET | `/api/v1/admin/usage/timeseries` | admin | 일자별 시계열 |
| GET | `/api/v1/usage/me/runs` | user (self) | 본인 Run 목록 |
| GET | `/api/v1/usage/me/timeseries` | user (self) | 본인 일자별 시계열 |

### 4.2 Detailed Specification

#### 4.2.1 `GET /api/v1/admin/agents/runs`

**Query Parameters**:

| Name | Type | Required | Default | Notes |
|------|------|:--------:|---------|-------|
| `from` | datetime (ISO) | No | `to - 30d` | _resolve_period 컨벤션 유지 |
| `to` | datetime (ISO) | No | `now` | |
| `user_id` | string | No | — | admin이 특정 사용자로 좁힐 때 |
| `agent_id` | string | No | — | |
| `status` | enum | No | — | RUNNING / SUCCESS / FAILED / CANCELLED |
| `page` | int | No | 1 | 1-based |
| `size` | int | No | 20 | 1..100 |

**Response 200**:

```json
{
  "from": "2026-04-21T00:00:00Z",
  "to":   "2026-05-21T00:00:00Z",
  "page": 1,
  "size": 20,
  "total": 137,
  "items": [
    {
      "id": "0e2a...",
      "user_id": "user-uuid-1",
      "agent_id": "agent-uuid-1",
      "status": "SUCCESS",
      "started_at": "2026-05-21T03:11:09Z",
      "ended_at":   "2026-05-21T03:11:21Z",
      "latency_ms": 12340,
      "total_tokens": 5421,
      "total_cost_usd": "0.012450",
      "llm_call_count": 3,
      "langsmith_run_url": "https://smith.langchain.com/..."
    }
  ]
}
```

**Error Responses**:

| Code | When |
|------|------|
| 401 | 미인증 |
| 403 | non-admin |
| 422 | period 잘못/365일 초과/size 범위 |

#### 4.2.2 `GET /api/v1/admin/usage/summary`

**Query**: `from`, `to` (둘 다 optional, 30일 기본)

**Response 200**:

```json
{
  "from": "2026-04-21T00:00:00Z",
  "to":   "2026-05-21T00:00:00Z",
  "total_runs": 421,
  "success_runs": 410,
  "failed_runs": 9,
  "success_rate": 0.9739,
  "total_tokens": 1284203,
  "total_cost_usd": "12.834201"
}
```

> `success_rate`는 서버에서 계산하여 응답 (FE에서 0으로 나눔 방지).

#### 4.2.3 `GET /api/v1/admin/usage/timeseries`

**Query**: `from`, `to`

**Response 200**:

```json
{
  "from": "2026-04-21T00:00:00Z",
  "to":   "2026-05-21T00:00:00Z",
  "bucket": "day",
  "points": [
    {
      "bucket": "2026-04-21",
      "run_count": 12,
      "total_tokens": 32104,
      "total_cost_usd": "0.421000"
    },
    {
      "bucket": "2026-04-22",
      "run_count": 18,
      "total_tokens": 48201,
      "total_cost_usd": "0.612900"
    }
  ]
}
```

> v1은 bucket=day 고정. v1.1에서 `bucket=hour|week` 지원 가능 (응답 스키마 그대로).

#### 4.2.4 `GET /api/v1/usage/me/runs`

`/admin/agents/runs`와 동일한 응답 스키마.

**Query**: `from`, `to`, `agent_id`, `status`, `page`, `size`.
**`user_id` 파라미터 미수용** — 항상 `current_user.id`로 강제.

#### 4.2.5 `GET /api/v1/usage/me/timeseries`

`/admin/usage/timeseries`와 동일 응답 스키마, `user_id`는 `current_user.id`로 강제.

### 4.3 Response Schemas (interfaces/schemas/agent_run_response.py 추가)

```python
class RunListItemDto(BaseModel):
    id: str
    user_id: str
    agent_id: str
    status: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    latency_ms: Optional[int] = None
    total_tokens: int
    total_cost_usd: Decimal
    llm_call_count: int
    langsmith_run_url: Optional[str] = None


class RunListResponse(BaseModel):
    from_dt: datetime = Field(alias="from")
    to_dt:   datetime = Field(alias="to")
    page:    int
    size:    int
    total:   int
    items:   List[RunListItemDto]

    model_config = ConfigDict(populate_by_name=True)


class UsageSummaryResponse(BaseModel):
    from_dt: datetime = Field(alias="from")
    to_dt:   datetime = Field(alias="to")
    total_runs:    int
    success_runs:  int
    failed_runs:   int
    success_rate:  float            # 0..1
    total_tokens:  int
    total_cost_usd: Decimal


class UsageTimeseriesPointDto(BaseModel):
    bucket: date
    run_count: int
    total_tokens: int
    total_cost_usd: Decimal


class UsageTimeseriesResponse(BaseModel):
    from_dt: datetime = Field(alias="from")
    to_dt:   datetime = Field(alias="to")
    bucket:  str  # "day" 고정 (v1)
    points:  List[UsageTimeseriesPointDto]
```

### 4.4 Route Skeletons

```python
# src/api/routes/agent_run_router.py (추가)

@router.get("/admin/agents/runs", response_model=RunListResponse)
async def list_admin_runs(
    from_: Optional[datetime] = Query(None, alias="from"),
    to: Optional[datetime] = Query(None),
    user_id: Optional[str] = Query(None),
    agent_id: Optional[str] = Query(None),
    status_: Optional[str] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    _: User = Depends(require_role("admin")),
    use_case: ListRunsUseCase = Depends(get_list_runs_use_case),
) -> RunListResponse:
    from_dt, to_dt = _resolve_period(from_, to)
    items, total = await use_case.execute(
        RunListFilter(
            from_dt=from_dt, to_dt=to_dt,
            user_id=user_id, agent_id=agent_id, status=status_,
        ),
        page=page, size=size,
    )
    return RunListResponse(
        **{"from": from_dt, "to": to_dt},
        page=page, size=size, total=total,
        items=[RunListItemDto.model_validate(i.__dict__) for i in items],
    )


@router.get("/admin/usage/summary", response_model=UsageSummaryResponse)
async def get_admin_usage_summary(
    from_: Optional[datetime] = Query(None, alias="from"),
    to: Optional[datetime] = Query(None),
    _: User = Depends(require_role("admin")),
    use_case: GetUsageSummaryUseCase = Depends(get_usage_summary_use_case),
) -> UsageSummaryResponse:
    from_dt, to_dt = _resolve_period(from_, to)
    row = await use_case.execute(from_dt, to_dt, user_id=None)
    return _summary_to_response(row)


@router.get("/admin/usage/timeseries", response_model=UsageTimeseriesResponse)
async def get_admin_usage_timeseries(
    from_: Optional[datetime] = Query(None, alias="from"),
    to: Optional[datetime] = Query(None),
    _: User = Depends(require_role("admin")),
    use_case: GetUsageTimeseriesUseCase = Depends(get_usage_timeseries_use_case),
) -> UsageTimeseriesResponse:
    from_dt, to_dt = _resolve_period(from_, to)
    points = await use_case.execute(from_dt, to_dt, user_id=None)
    return _timeseries_to_response(from_dt, to_dt, points)


@router.get("/usage/me/runs", response_model=RunListResponse)
async def list_my_runs(
    from_: Optional[datetime] = Query(None, alias="from"),
    to: Optional[datetime] = Query(None),
    agent_id: Optional[str] = Query(None),
    status_: Optional[str] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    use_case: ListMyRunsUseCase = Depends(get_list_my_runs_use_case),
) -> RunListResponse:
    from_dt, to_dt = _resolve_period(from_, to)
    items, total = await use_case.execute(
        user_id=str(current_user.id),
        filter_=RunListFilter(
            from_dt=from_dt, to_dt=to_dt,
            agent_id=agent_id, status=status_,
        ),
        page=page, size=size,
    )
    # ... 응답 매핑


@router.get("/usage/me/timeseries", response_model=UsageTimeseriesResponse)
async def get_my_usage_timeseries(
    from_: Optional[datetime] = Query(None, alias="from"),
    to: Optional[datetime] = Query(None),
    current_user: User = Depends(get_current_user),
    use_case: GetMyUsageTimeseriesUseCase = Depends(get_my_usage_timeseries_use_case),
) -> UsageTimeseriesResponse:
    from_dt, to_dt = _resolve_period(from_, to)
    points = await use_case.execute(str(current_user.id), from_dt, to_dt)
    return _timeseries_to_response(from_dt, to_dt, points)
```

### 4.5 UseCase Skeletons (5건)

```python
# src/application/agent_run/use_cases/list_runs_use_case.py
class ListRunsUseCase:
    def __init__(self, repo: AgentRunRepositoryInterface) -> None:
        self._repo = repo

    async def execute(
        self, filter_: RunListFilter, page: int, size: int
    ) -> tuple[List[RunListItem], int]:
        return await self._repo.list_runs(filter_, page=page, size=size)


# src/application/agent_run/use_cases/get_usage_summary_use_case.py
class GetUsageSummaryUseCase:
    def __init__(self, aggregator: UsageAggregator) -> None:
        self._aggregator = aggregator

    async def execute(
        self, from_dt: datetime, to_dt: datetime, user_id: Optional[str]
    ) -> UsageSummaryRow:
        return await self._aggregator.summary(from_dt, to_dt, user_id=user_id)


# src/application/agent_run/use_cases/get_usage_timeseries_use_case.py
class GetUsageTimeseriesUseCase:
    def __init__(self, aggregator: UsageAggregator) -> None:
        self._aggregator = aggregator

    async def execute(
        self, from_dt: datetime, to_dt: datetime, user_id: Optional[str]
    ) -> List[UsageTimeseriesPoint]:
        return await self._aggregator.timeseries(from_dt, to_dt, user_id=user_id)


# src/application/agent_run/use_cases/list_my_runs_use_case.py
class ListMyRunsUseCase:
    def __init__(self, repo: AgentRunRepositoryInterface) -> None:
        self._repo = repo

    async def execute(
        self, user_id: str, filter_: RunListFilter, page: int, size: int
    ) -> tuple[List[RunListItem], int]:
        # force_user_id 강제 — admin 라우트에서 우회 불가
        forced = replace(filter_, user_id=user_id, force_user_id=user_id)
        return await self._repo.list_runs(forced, page=page, size=size)


# src/application/agent_run/use_cases/get_my_usage_timeseries_use_case.py
class GetMyUsageTimeseriesUseCase:
    def __init__(self, aggregator: UsageAggregator) -> None:
        self._aggregator = aggregator

    async def execute(
        self, user_id: str, from_dt: datetime, to_dt: datetime
    ) -> List[UsageTimeseriesPoint]:
        return await self._aggregator.timeseries(from_dt, to_dt, user_id=user_id)
```

### 4.6 UsageAggregator 확장

```python
# src/application/agent_run/aggregator.py (추가)

class UsageAggregator:
    # ... 기존 메서드 ...

    async def summary(
        self, from_dt: datetime, to_dt: datetime, user_id: Optional[str] = None
    ) -> UsageSummaryRow:
        return await self._llm_repo.aggregate_summary(from_dt, to_dt, user_id=user_id)

    async def timeseries(
        self, from_dt: datetime, to_dt: datetime, user_id: Optional[str] = None
    ) -> List[UsageTimeseriesPoint]:
        return await self._llm_repo.aggregate_timeseries(from_dt, to_dt, user_id=user_id)
```

### 4.7 DI Wiring (src/api/main.py)

```python
# create_app() 안에서, 기존 M4 wiring 옆에 추가
def _wire_observability(...):
    # 기존: get_run_detail_use_case, get_usage_by_*_use_case 등 ...

    list_runs_uc = ListRunsUseCase(agent_run_repo_factory())
    get_summary_uc = GetUsageSummaryUseCase(aggregator_singleton)
    get_ts_uc = GetUsageTimeseriesUseCase(aggregator_singleton)
    list_my_runs_uc = ListMyRunsUseCase(agent_run_repo_factory())
    get_my_ts_uc = GetMyUsageTimeseriesUseCase(aggregator_singleton)

    app.dependency_overrides[get_list_runs_use_case]                   = lambda: list_runs_uc
    app.dependency_overrides[get_usage_summary_use_case]               = lambda: get_summary_uc
    app.dependency_overrides[get_usage_timeseries_use_case]            = lambda: get_ts_uc
    app.dependency_overrides[get_list_my_runs_use_case]                = lambda: list_my_runs_uc
    app.dependency_overrides[get_my_usage_timeseries_use_case]         = lambda: get_my_ts_uc
```

> ⚠ Repository는 요청당 새 세션이 필요 — `agent_run_repo_factory`는 `Depends`로 변경 가능. M4의 `aggregator_singleton`가 어떻게 wiring돼 있는지 Do 단계 첫 작업으로 확인 후 일관성 있게 처리.

---

## 5. UI/UX Design

### 5.1 Page Layouts

#### 5.1.1 `AdminAgentRunsPage` (`/admin/agent-runs`)

```
┌──────────────────────────── Admin Layout ────────────────────────────┐
│ TopNav                                                                │
├──────────┬───────────────────────────────────────────────────────────┤
│ Sidebar  │   📊 Agent Run 관측성                          [기간▼ 30d ▼] │
│ ─────────│   ┌──────────────────────────────────────────────────────┐ │
│ 사용자   │   │  Today    7 Days    30 Days    Custom: [from] [to]   │ │
│ 부서     │   └──────────────────────────────────────────────────────┘ │
│ RAGAS    │                                                            │
│ ▶Agent Run│   ┌──────────┬──────────┬──────────┬──────────┐           │
│           │   │ 총 Run   │ 성공률   │ 총 토큰  │ 총 비용  │           │
│           │   │   421    │  97.3%   │ 1.28M    │ $12.83   │           │
│           │   └──────────┴──────────┴──────────┴──────────┘           │
│           │                                                            │
│           │   ┌──────────────────────────────────────────────────────┐ │
│           │   │  📈 일자별 비용 + Run 수 (Line+Bar)                   │ │
│           │   │                                                      │ │
│           │   └──────────────────────────────────────────────────────┘ │
│           │                                                            │
│           │   [사용자별] [LLM별] [노드별] [Run 목록]                   │
│           │   ┌──────────────────────────────────────────────────────┐ │
│           │   │ (선택된 탭 콘텐츠)                                    │ │
│           │   │  ─ 테이블 (정렬·페이지네이션·행 클릭)                  │ │
│           │   └──────────────────────────────────────────────────────┘ │
└──────────┴───────────────────────────────────────────────────────────┘
```

#### 5.1.2 `AgentRunDetailPage` (`/admin/agent-runs/:runId`)

```
┌─────────────────────────────────────────────────────────────────────┐
│  ← 목록으로                                                          │
│                                                                     │
│  Run #0e2a... (SUCCESS)                       🔗 LangSmith Trace    │
│  ─────────────────────────────────────────────────────              │
│  user: user-uuid-1  /  agent: agent-uuid-1                         │
│  started: 2026-05-21 03:11:09  /  duration: 12.3s                  │
│  tokens: 5,421  /  cost: $0.012  /  llm calls: 3                   │
│                                                                     │
│  ▼ Steps                                                            │
│   1. supervisor [SUPERVISOR · SUCCESS · 320ms]                      │
│      └─ LLM: gpt-4o-mini, 1,210 tokens, $0.0012                    │
│   2. retriever  [WORKER · SUCCESS · 8,210ms]                        │
│      ├─ Tool: rag_search [SUCCESS · 7,890ms]                        │
│      │   └─ Retrievals (5):                                         │
│      │       1. doc-fin-001 #c2 (score 0.91)                        │
│      │       2. doc-fin-002 #c5 (score 0.88)                        │
│      └─ LLM: gpt-4o, 2,001 tokens, $0.0050                         │
│   3. answer     [WORKER · SUCCESS · 3,810ms]                        │
└─────────────────────────────────────────────────────────────────────┘
```

#### 5.1.3 `UsageMePage` (`/usage`)

```
┌─────────────────────────────────────────────────────────────────────┐
│  TopNav  ... [👤 내 사용량] [Logout]                                  │
├─────────────────────────────────────────────────────────────────────┤
│  내 사용량                                       [기간▼ 30d ▼]        │
│  ┌──────────┬──────────┬──────────┬──────────┐                       │
│  │ 내 Run   │ 성공률   │ 토큰     │ 비용     │                       │
│  └──────────┴──────────┴──────────┴──────────┘                       │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │ 📈 일자별 비용 (line)                                            │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│  최근 내 Run                                       [페이지네이션]    │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │ id    | agent | status | started_at  | tokens | cost | →       │ │
│  └─────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

### 5.2 User Flows

```
Admin
─────
Login → /admin/agent-runs → 기간 선택 → 카드/차트/탭 자동 새로고침
                          ↓
                          탭=Run 목록 → 필터(user/agent/status)+페이지네이션
                          ↓
                          행 클릭 → /admin/agent-runs/:runId (뒤로가기 가능)


User (일반)
──────────
Login → TopNav "내 사용량" → /usage → 카드/차트/내 Run 목록
                                    ↓
                                    행 클릭 → /admin/agent-runs/:runId
                                              (백엔드 self 분기로 403/허용)
```

### 5.3 Component List

| Component | Location | Responsibility |
|-----------|----------|----------------|
| `AdminAgentRunsPage` | `pages/AdminAgentRunsPage/index.tsx` | 페이지 컨테이너, 탭 라우팅, 기간 필터 보유 |
| `SummaryCards` | `pages/AdminAgentRunsPage/components/SummaryCards.tsx` | 카드 4개 (admin/me 공유) |
| `TimeseriesChart` | `pages/AdminAgentRunsPage/components/TimeseriesChart.tsx` | recharts ComposedChart (Line+Bar), admin/me 공유 |
| `RunListTable` | `pages/AdminAgentRunsPage/components/RunListTable.tsx` | 정렬·페이지네이션·행 클릭, admin/me 공유 |
| `UsageByUserTab` | `.../UsageByUserTab.tsx` | 사용자별 테이블 (M4 reuse) |
| `UsageByLlmTab` | `.../UsageByLlmTab.tsx` | LLM별 테이블 (M4 reuse) |
| `UsageByNodeTab` | `.../UsageByNodeTab.tsx` | 노드별 테이블 (M4 reuse) |
| `AgentRunDetailPage` | `pages/AgentRunDetailPage/index.tsx` | 상세 페이지 컨테이너 |
| `StepTree` | `pages/AgentRunDetailPage/components/StepTree.tsx` | 트리 렌더 |
| `UsageMePage` | `pages/UsageMePage/index.tsx` | 내 사용량 페이지 |
| `PeriodFilter` | `components/common/PeriodFilter.tsx` (신규 공용) | 기간 프리셋·커스텀 picker |

### 5.4 State Management

| State | Tool | Scope |
|-------|------|-------|
| 서버 데이터(쿼리/캐시) | TanStack Query | per-key (queryKeys) |
| 기간/필터 (URL synced) | Zustand + `searchParams` | per-page |
| 인증/세션 | 기존 auth store | 전역 |

### 5.5 queryKeys 확장

```typescript
// idt_front/src/lib/queryKeys.ts (추가)
agentRunAdmin: {
  all: ['agentRunAdmin'] as const,
  summary: (from: string, to: string) =>
    [...queryKeys.agentRunAdmin.all, 'summary', from, to] as const,
  timeseries: (from: string, to: string) =>
    [...queryKeys.agentRunAdmin.all, 'timeseries', from, to] as const,
  runs: (params: AdminRunsParams) =>
    [...queryKeys.agentRunAdmin.all, 'runs', params] as const,
  runDetail: (runId: string) =>
    [...queryKeys.agentRunAdmin.all, 'runDetail', runId] as const,
  byUser: (from: string, to: string) =>
    [...queryKeys.agentRunAdmin.all, 'byUser', from, to] as const,
  byLlm: (from: string, to: string) =>
    [...queryKeys.agentRunAdmin.all, 'byLlm', from, to] as const,
  byNode: (from: string, to: string) =>
    [...queryKeys.agentRunAdmin.all, 'byNode', from, to] as const,
},
usageMe: {
  all: ['usageMe'] as const,
  summary: (from: string, to: string) =>
    [...queryKeys.usageMe.all, 'summary', from, to] as const,
  timeseries: (from: string, to: string) =>
    [...queryKeys.usageMe.all, 'timeseries', from, to] as const,
  runs: (params: MyRunsParams) =>
    [...queryKeys.usageMe.all, 'runs', params] as const,
},
```

### 5.6 API Endpoint Constants 확장

```typescript
// idt_front/src/constants/api.ts (추가)

// Admin — Agent Run Observability
ADMIN_AGENT_RUNS:           '/api/v1/admin/agents/runs',
ADMIN_AGENT_RUN_DETAIL:     (runId: string) => `/api/v1/agents/runs/${runId}`,
ADMIN_USAGE_SUMMARY:        '/api/v1/admin/usage/summary',
ADMIN_USAGE_TIMESERIES:     '/api/v1/admin/usage/timeseries',
ADMIN_USAGE_BY_USER:        '/api/v1/admin/usage/users',          // M4
ADMIN_USAGE_BY_LLM:         '/api/v1/admin/usage/llm-models',     // M4
ADMIN_USAGE_BY_NODE:        '/api/v1/admin/usage/by-node',        // M4

// User My Usage
USAGE_ME:                   '/api/v1/usage/me',                    // M4
USAGE_ME_RUNS:              '/api/v1/usage/me/runs',
USAGE_ME_TIMESERIES:        '/api/v1/usage/me/timeseries',
```

### 5.7 Routes 추가 (`App.tsx`)

```tsx
{/* Admin 전용 */}
<Route element={<AdminRoute />}>
  <Route element={<AdminLayout />}>
    <Route path="/admin/users"        element={<AdminUsersPage />} />
    <Route path="/admin/departments"  element={<AdminDepartmentsPage />} />
    <Route path="/admin/ragas"        element={<AdminRagasPage />} />
    <Route path="/admin/agent-runs"             element={<AdminAgentRunsPage />} />
    <Route path="/admin/agent-runs/:runId"      element={<AgentRunDetailPage />} />
  </Route>
</Route>

{/* 일반 사용자 — 인증만 필요 */}
<Route element={<PrivateRoute />}>
  <Route path="/usage" element={<UsageMePage />} />
</Route>
```

### 5.8 AdminLayout 사이드바 추가

```ts
// idt_front/src/components/layout/AdminLayout.tsx
const ADMIN_SIDEBAR_ITEMS = [
  { label: '사용자 관리',   path: '/admin/users',        icon: ... },
  { label: '부서 관리',     path: '/admin/departments',  icon: ... },
  { label: 'RAGAS 평가',    path: '/admin/ragas',        icon: ... },
  { label: 'Agent Run 관측', path: '/admin/agent-runs',  icon: 'chart-bar' },  // 신규
];
```

---

## 6. Error Handling

### 6.1 Error Code Map

| Code | When | FE Handling |
|------|------|------------|
| 401 | 토큰 만료 / 미인증 | authApiClient interceptor → 로그인 페이지 |
| 403 | non-admin이 `/admin/*` 호출 / 사용자가 타인의 run 상세 조회 | toast "권한이 없습니다" + 이전 페이지로 |
| 404 | 존재하지 않는 run_id (상세 페이지) | "Run을 찾을 수 없습니다" 빈 상태 |
| 422 | 필터/페이지 파라미터 유효성 실패 | 에러 toast + 폼 리셋 |
| 500 | 서버 오류 | toast "잠시 후 다시 시도해 주세요" + Sentry 로그 |

### 6.2 Error Response Format

(FastAPI 기본 + project 컨벤션)

```json
{
  "detail": "Access denied"
}
```

### 6.3 Empty States

| Screen | When | UX |
|--------|------|----|
| Admin Dashboard | 기간 내 run 0건 | 카드 모두 0, 차트 자리에 "데이터가 없습니다" 일러스트 |
| Run List | 필터 결과 0건 | 테이블 자리에 "조건에 맞는 Run이 없습니다" + 필터 리셋 버튼 |
| My Usage | 본인 run 0건 | 카드 모두 0 + "아직 Agent를 실행하지 않으셨어요" CTA → `/agent` |

---

## 7. Security Considerations

| Item | Mitigation |
|------|------------|
| Admin 엔드포인트 우회 | `require_role("admin")` Depends 강제. pytest 401/403 케이스 명시. |
| `/usage/me/*` 타사용자 노출 | `user_id` 쿼리 파라미터 **미수용**, `current_user.id`만 서버에서 주입. UseCase 시그니처에 `user_id: str` 필수. |
| Run 상세 권한 우회 | 기존 M4 로직 그대로 유지 (`is_admin or run.user_id == requester`). |
| SQL Injection | SQLAlchemy parameterized query (raw SQL 사용 금지). |
| 시간 범위 폭주 | `_resolve_period`에서 366일 초과 거부 (M4 그대로). |
| 페이지네이션 abuse | `size` ≤ 100, `page` ≥ 1 — FastAPI Query 제약. |
| Mass scraping | (운영 단계) Nginx 레이트 리미트 (별도 인프라). 이번 PDCA 범위 밖. |

---

## 8. Test Plan

### 8.1 Test Scope

| Type | Target | Tool |
|------|--------|------|
| Unit | 5개 UseCase + Aggregator 신규 메서드 + Repository 신규 메서드 | pytest + AsyncMock |
| Integration | 5개 라우트 (401/403/422/200) | pytest + AsyncClient |
| Component | SummaryCards / TimeseriesChart / RunListTable / 페이지 컨테이너 | Vitest + RTL + MSW |
| E2E | (선택) 로그인 → admin → 필터 → 상세 진입 | Playwright (있을 때만, MVP 제외) |

### 8.2 Key Test Cases (Backend)

**`tests/application/agent_run/use_cases/test_list_runs_use_case.py`**:
- HP: filter 전부 지정 → repo.list_runs 정확히 호출, page/size 전달
- HP: 일부 필터만 → None 전달
- HP: total 반환 동작
- HP: 빈 리스트 반환

**`test_get_usage_summary_use_case.py`**:
- HP: aggregator.summary 호출 검증
- HP: user_id=None 전달

**`test_get_usage_timeseries_use_case.py`**:
- HP: aggregator.timeseries 호출 검증
- Edge: from > to → 422 (라우트 측 책임)

**`test_list_my_runs_use_case.py`**:
- HP: user_id 강제 주입 → filter.user_id가 인자와 일치
- Security: 호출자가 다른 user_id를 filter에 넣어도 force_user_id가 덮어쓰기

**`test_get_my_usage_timeseries_use_case.py`**:
- HP: user_id 전달

**Infrastructure (SQL 검증)**:
- `test_agent_run_repository_list_runs.py`: filter 조합 5종 + offset/limit + COUNT
- `test_llm_call_repository_summary.py`: 정상 / user_id 필터 / 빈 결과
- `test_llm_call_repository_timeseries.py`: 빈 결과 / 일자 정렬 / user_id 필터

**Route (API)**:
- `tests/api/test_agent_run_router.py` (M4 파일 확장):
  - `/admin/agents/runs`: 401/403/422/200 + 페이지네이션 + 필터
  - `/admin/usage/summary`: 401/403/200 + success_rate 계산
  - `/admin/usage/timeseries`: 401/403/200 + bucket=day
  - `/usage/me/runs`: 401/200, **user_id 쿼리 시도해도 무시** (보안 케이스)
  - `/usage/me/timeseries`: 401/200

### 8.3 Key Test Cases (Frontend)

**`AdminAgentRunsPage.test.tsx`**:
- HP: 마운트 시 5 queries 발사 (MSW)
- HP: 기간 변경 → 모든 queries invalidate
- HP: 탭 전환 → 해당 query만 발사
- Edge: run 0건일 때 empty state 표시

**`SummaryCards.test.tsx`**:
- HP: props로 받은 값 렌더
- Edge: undefined 시 "—" 표시
- Edge: success_rate 0..1 → 퍼센트 포맷

**`RunListTable.test.tsx`**:
- HP: 페이지 클릭 → onPageChange 호출
- HP: 행 클릭 → navigate(/admin/agent-runs/:id)
- HP: 정렬 인디케이터 (현재 started_at desc 고정 v1)

**`UsageMePage.test.tsx`**:
- HP: queries 3종 발사
- Security: `user_id` 파라미터를 추가하지 않음을 service spy로 검증

---

## 9. Clean Architecture

### 9.1 Layer Structure

| Layer | Responsibility | Location |
|-------|---------------|----------|
| **Interfaces (HTTP)** | FastAPI router, Pydantic schemas, period helper | `src/api/routes/`, `src/interfaces/schemas/` |
| **Application** | UseCases, Aggregator | `src/application/agent_run/use_cases/`, `aggregator.py` |
| **Domain** | Entities, VOs, Rows, Repository interfaces | `src/domain/agent_run/` |
| **Infrastructure** | SQLAlchemy Models, Repositories | `src/infrastructure/persistence/` |

### 9.2 Dependency Rules

```
Interfaces ──→ Application ──→ Domain ←── Infrastructure
```

- Domain은 **무의존**(SQLAlchemy/pydantic도 불가).
- Application은 Domain 인터페이스만 알면 됨 (Infra 구체 미참조).
- Infrastructure는 Domain의 인터페이스를 구현.
- Interfaces 레이어는 Application UseCase를 직접 호출 (라우트 그대로 적용 중인 M4 패턴).

### 9.3 File Import Rules

| From | Can Import | Cannot Import |
|------|-----------|---------------|
| `src/api/routes/agent_run_router.py` | application UseCase, interfaces schemas, domain VOs, dependencies/auth | infrastructure 구체 클래스 |
| `src/application/agent_run/use_cases/*` | `src.domain.agent_run.*`, `src.application.agent_run.aggregator` | `src.infrastructure.*`, `src.api.*` |
| `src/domain/agent_run/*` | stdlib only (dataclass, datetime, decimal) | SQLAlchemy, pydantic, fastapi |
| `src/infrastructure/persistence/repositories/*` | `src.domain.agent_run.*`, `src.infrastructure.persistence.models` | `src.application.*`, `src.api.*` |

### 9.4 This Feature's Layer Assignment

| Component | Layer | Location |
|-----------|-------|----------|
| `RunListFilter`, `RunListItem`, `UsageSummaryRow`, `UsageTimeseriesPoint` | Domain | `src/domain/agent_run/interfaces.py` |
| `ListRunsUseCase` 외 4종 | Application | `src/application/agent_run/use_cases/` |
| `UsageAggregator.summary / .timeseries` | Application | `src/application/agent_run/aggregator.py` |
| `AiRunRepository.list_runs` | Infrastructure | `src/infrastructure/persistence/repositories/agent_run_repository.py` |
| `LlmCallRepository.aggregate_summary / .aggregate_timeseries` | Infrastructure | `src/infrastructure/persistence/repositories/llm_call_repository.py` |
| `RunListResponse`, `UsageSummaryResponse`, `UsageTimeseriesResponse` | Interfaces | `src/interfaces/schemas/agent_run_response.py` |
| 5개 라우트 핸들러 | Interfaces | `src/api/routes/agent_run_router.py` |
| `AdminAgentRunsPage` 외 컴포넌트 | Presentation | `idt_front/src/pages/` |
| `useAgentRunAdmin` 외 훅 | Application (FE) | `idt_front/src/hooks/` |
| `agentRunAdminService` | Infrastructure (FE) | `idt_front/src/services/` |
| `agentRunAdmin.ts` 타입 | Domain (FE) | `idt_front/src/types/` |

---

## 10. Coding Convention Reference

### 10.1 Naming (Backend)

| Target | Rule | Example |
|--------|------|---------|
| UseCase | `*UseCase` PascalCase, single execute() | `ListRunsUseCase.execute(...)` |
| Repository method | `verb_noun`, async | `list_runs`, `aggregate_summary` |
| Dataclass row | `*Row` 또는 `*Item` 또는 `*Point` suffix | `UsageSummaryRow`, `RunListItem` |
| Pydantic schema | `*Dto`/`*Response`/`*Request` suffix | `RunListItemDto`, `UsageSummaryResponse` |
| Module | snake_case | `list_runs_use_case.py` |

### 10.2 Naming (Frontend)

| Target | Rule | Example |
|--------|------|---------|
| Page | `*Page` PascalCase, 폴더 + `index.tsx` | `AdminAgentRunsPage/index.tsx` |
| Component | PascalCase, 단일 책임 | `SummaryCards.tsx` |
| Hook | `use*` | `useAgentRunAdmin` |
| Service | `*Service` 또는 camelCase | `agentRunAdminService` |
| Type | PascalCase, file: camelCase | `AdminRunsParams` in `agentRunAdmin.ts` |

### 10.3 Import Order (TS)

```typescript
// 1. External
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
// 2. Internal absolute (@/)
import { API_ENDPOINTS } from '@/constants/api';
import { queryKeys } from '@/lib/queryKeys';
// 3. Relative
import { SummaryCards } from './components/SummaryCards';
// 4. Type-only
import type { AdminUsageSummary } from '@/types/agentRunAdmin';
```

### 10.4 Environment Variables

신규 없음 (Plan 그대로).

### 10.5 This Feature's Conventions

| Item | Convention Applied |
|------|-------------------|
| 함수 길이 | ≤ 40 line (CLAUDE.md §3) |
| 중첩 | ≤ 2 단 |
| 타입 | Backend pydantic+typing strict, FE TS strict |
| 로깅 | LOG-001 (StructuredLogger, no print) |
| DB 세션 | UseCase·Aggregator는 세션 직접 생성 금지, Repository 주입 |
| 응답 형식 | M4와 동일하게 `from`/`to` echo |

---

## 11. Implementation Guide

### 11.1 File Structure

```
idt/src/
 ├─ domain/agent_run/
 │   └─ interfaces.py                                     [M] +RunListFilter, RunListItem,
 │                                                            UsageSummaryRow, UsageTimeseriesPoint,
 │                                                            +list_runs / +aggregate_summary / +aggregate_timeseries
 ├─ application/agent_run/
 │   ├─ use_cases/
 │   │   ├─ list_runs_use_case.py                         [N]
 │   │   ├─ get_usage_summary_use_case.py                 [N]
 │   │   ├─ get_usage_timeseries_use_case.py              [N]
 │   │   ├─ list_my_runs_use_case.py                      [N]
 │   │   └─ get_my_usage_timeseries_use_case.py           [N]
 │   ├─ __init__.py                                       [M] export 추가
 │   └─ aggregator.py                                     [M] +summary, +timeseries
 ├─ infrastructure/persistence/repositories/
 │   ├─ agent_run_repository.py                           [M] +list_runs
 │   └─ llm_call_repository.py                            [M] +aggregate_summary, +aggregate_timeseries
 ├─ interfaces/schemas/
 │   └─ agent_run_response.py                             [M] +RunListItemDto, +RunListResponse,
 │                                                            +UsageSummaryResponse, +UsageTimeseriesResponse
 └─ api/
     ├─ main.py                                           [M] DI wiring 5건 추가
     └─ routes/agent_run_router.py                        [M] +5 endpoints + DI placeholders

idt/tests/
 ├─ application/agent_run/use_cases/
 │   ├─ test_list_runs_use_case.py                        [N]
 │   ├─ test_get_usage_summary_use_case.py                [N]
 │   ├─ test_get_usage_timeseries_use_case.py             [N]
 │   ├─ test_list_my_runs_use_case.py                     [N]
 │   └─ test_get_my_usage_timeseries_use_case.py          [N]
 ├─ infrastructure/agent_run/
 │   ├─ test_agent_run_repository_list_runs.py            [N]
 │   ├─ test_llm_call_repository_summary.py               [N]
 │   └─ test_llm_call_repository_timeseries.py            [N]
 └─ api/test_agent_run_router.py                          [M] +5 endpoint 케이스

idt_front/src/
 ├─ pages/
 │   ├─ AdminAgentRunsPage/                               [N]
 │   │   ├─ index.tsx
 │   │   ├─ components/
 │   │   │   ├─ SummaryCards.tsx
 │   │   │   ├─ TimeseriesChart.tsx
 │   │   │   ├─ RunListTable.tsx
 │   │   │   ├─ UsageByUserTab.tsx
 │   │   │   ├─ UsageByLlmTab.tsx
 │   │   │   └─ UsageByNodeTab.tsx
 │   │   └─ store.ts
 │   ├─ AgentRunDetailPage/                               [N]
 │   │   ├─ index.tsx
 │   │   └─ components/StepTree.tsx
 │   └─ UsageMePage/                                      [N]
 │       └─ index.tsx
 ├─ services/
 │   ├─ agentRunAdminService.ts                           [N]
 │   └─ usageMeService.ts                                 [N]
 ├─ hooks/
 │   ├─ useAgentRunAdmin.ts                               [N]
 │   ├─ useAgentRunDetail.ts                              [N]
 │   └─ useUsageMe.ts                                     [N]
 ├─ types/
 │   ├─ agentRunAdmin.ts                                  [N]
 │   └─ usageMe.ts                                        [N]
 ├─ components/
 │   ├─ common/PeriodFilter.tsx                           [N]
 │   └─ layout/
 │       ├─ AdminLayout.tsx                               [M] 사이드바 +1
 │       └─ TopNav.tsx                                    [M] +내 사용량
 ├─ constants/api.ts                                      [M] +엔드포인트
 ├─ lib/queryKeys.ts                                      [M] +agentRunAdmin, +usageMe
 └─ App.tsx                                               [M] +3 routes

idt_front/src/__tests__/  (또는 각 컴포넌트 옆 .test.tsx)
 └─ … (위 §8.3 참조)
```

> `[N]` = New, `[M]` = Modified.

### 11.2 Implementation Order (TDD 우선)

```
Phase A (Backend Admin 3종)
  A-1. Domain VOs 추가 + Repository interface 확장 (test 선)
  A-2. test_list_runs_use_case.py 작성 → ListRunsUseCase 구현
  A-3. test_agent_run_repository_list_runs.py 작성 → AgentRunRepository.list_runs 구현
  A-4. test_get_usage_summary_use_case.py / test_get_usage_timeseries_use_case.py
       → UseCase + Aggregator.summary/.timeseries 구현
  A-5. test_llm_call_repository_summary.py / _timeseries.py
       → LlmCallRepository.aggregate_summary / .aggregate_timeseries 구현
  A-6. interfaces/schemas/agent_run_response.py 신규 스키마 추가
  A-7. route 3건 추가 + test_agent_run_router.py 케이스 추가
  A-8. src/api/main.py DI wiring 3건

Phase B (Backend Me 2종)
  B-1. test_list_my_runs_use_case.py + ListMyRunsUseCase (force_user_id 보안)
  B-2. test_get_my_usage_timeseries_use_case.py + GetMyUsageTimeseriesUseCase
  B-3. route 2건 + 보안 케이스(user_id 파라미터 무시)
  B-4. DI wiring 2건

Phase C (Frontend 기반)
  C-1. types/agentRunAdmin.ts + types/usageMe.ts
  C-2. constants/api.ts + lib/queryKeys.ts 확장
  C-3. services/agentRunAdminService.ts + usageMeService.ts (Vitest 단위 테스트)
  C-4. hooks/useAgentRunAdmin.ts + useUsageMe.ts (MSW)

Phase D (Frontend Admin 페이지)
  D-1. components/common/PeriodFilter.tsx (공용)
  D-2. AdminAgentRunsPage/components/* 컴포넌트 (테스트 우선)
  D-3. AdminAgentRunsPage/index.tsx 컨테이너 조립
  D-4. AdminLayout 사이드바 +1
  D-5. App.tsx 라우트 +1

Phase E (Frontend Run 상세 + My Usage)
  E-1. AgentRunDetailPage (M4 응답 그대로 활용)
  E-2. App.tsx 라우트 +1
  E-3. UsageMePage 구현 (Admin 페이지 컴포넌트 재사용)
  E-4. TopNav 메뉴 +1
  E-5. App.tsx 라우트 +1

Phase F (검증)
  F-1. verify-tdd skill
  F-2. verify-architecture skill
  F-3. verify-logging skill
  F-4. api-contract skill
  F-5. /pdca analyze agent-run-admin-dashboard (gap-detector)
```

> 각 Phase는 PR 단위 가능. Phase A 완료 후 Backend 회귀 테스트 통과 확인이 게이트.

### 11.3 Performance Budget

| Endpoint | Target | 측정 |
|----------|--------|------|
| `/admin/usage/summary` | < 300ms (30d, 1만 run) | EXPLAIN + 로컬 부하 |
| `/admin/usage/timeseries` | < 500ms (30d daily) | EXPLAIN |
| `/admin/agents/runs?page=1&size=20` | < 400ms | EXPLAIN |
| `/usage/me/*` | < 300ms | EXPLAIN |
| FE 초기 로드 (Admin Dashboard) | < 1.5s TTI | LCP/INP 수동 측정 |

### 11.4 Open Questions (Do 단계에서 즉시 결정)

1. `ai_llm_call.user_id` 인덱스 존재 여부 — V021 SQL 확인.
   - 없으면 V023 마이그레이션 1건 (Plan §5 Risk).
2. `aggregator_singleton` 위치(M4 `src/api/main.py` 또는 DI 컨테이너) — 그대로 재사용.
3. 차트 라이브러리 — admin-ragas-dashboard에서 이미 쓰는 라이브러리 확인. 없으면 `recharts` 신규 추가.
4. `AgentRunDetailPage`를 별도 페이지로 두는 것이 admin 사이드바 메뉴 ‘Agent Run 관측’ 활성 표시와 충돌하지 않는지 — `useLocation.pathname.startsWith('/admin/agent-runs')`로 처리.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-05-21 | Initial draft. M4 패턴 mirror, 5 endpoints + 3 pages + TDD order | AI Assistant |
