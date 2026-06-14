# admin-ragas-dashboard Design Document

> **Summary**: 관리자 전용 RAGAS 평가 대시보드 — Admin API 4개 + 프론트엔드 대시보드 페이지
>
> **Project**: sangplusbot (idt + idt_front)
> **Author**: AI Assistant
> **Date**: 2026-05-18
> **Status**: Draft
> **Planning Doc**: [admin-ragas-dashboard.plan.md](../01-plan/features/admin-ragas-dashboard.plan.md)

---

## 1. Overview

### 1.1 Design Goals

- 기존 RAGAS 도메인 인터페이스를 확장하여 통계 집계 메서드를 추가한다
- Admin 전용 UseCase와 라우터를 분리하여 기존 평가 실행 API와 관심사를 분리한다
- 프론트엔드에서 대시보드 통계 → 실행 목록 → 상세 결과를 한 화면에서 확인 가능하게 한다

### 1.2 Design Principles

- Thin DDD 레이어 준수: domain(인터페이스) → application(UseCase) → infrastructure(Repository) → interfaces(Router)
- 기존 코드 최소 변경: 새 메서드 추가만, 기존 메서드 수정 없음
- Admin 권한 보호: `require_role("admin")` 일관 적용

---

## 2. Architecture

### 2.1 Component Diagram

```
┌──────────────────────┐     ┌──────────────────────────────┐     ┌────────────┐
│  AdminRagasPage      │────▶│  /api/v1/admin/ragas/*       │────▶│  MySQL     │
│  (React + TanStack)  │     │  admin_ragas_router.py       │     │            │
│  - Dashboard cards   │     │  ├── require_role("admin")   │     │ eval_run   │
│  - Runs table        │     │  └── AdminEvalUseCase         │     │ eval_result│
│  - Detail modal      │     │      └── EvaluationRepository │     │ eval_testset│
└──────────────────────┘     └──────────────────────────────┘     └────────────┘
```

### 2.2 Data Flow

```
Admin 로그인 → AdminRagasPage 진입 → useAdminRagasDashboard() 호출
  → GET /api/v1/admin/ragas/dashboard → AdminEvalUseCase.get_dashboard_stats()
    → EvaluationRepository.get_dashboard_stats() → SQL 집계 쿼리 → 응답

필터 변경 → useAdminRagasRuns() refetch
  → GET /api/v1/admin/ragas/runs?target_type=rag&status=completed
    → AdminEvalUseCase.list_runs_with_summary() → 페이지네이션 응답

행 클릭 → useAdminRagasRunDetail(runId) fetch
  → GET /api/v1/admin/ragas/runs/{run_id}
    → AdminEvalUseCase.get_run_with_results() → 상세 + 결과 목록 응답
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `admin_ragas_router.py` | `AdminEvalUseCase`, `require_role("admin")` | HTTP 요청 처리 + 권한 검증 |
| `AdminEvalUseCase` | `EvaluationRepositoryInterface`, `LoggerInterface` | 비즈니스 로직 오케스트레이션 |
| `EvaluationRepository` | `AsyncSession`, `EvaluationRunModel`, `EvaluationResultModel` | SQL 집계 쿼리 실행 |
| `AdminRagasPage` | `adminRagasService`, TanStack Query | UI 렌더링 + 데이터 페칭 |

---

## 3. Data Model

### 3.1 기존 테이블 (변경 없음)

DB 스키마 변경 없이 기존 3개 테이블을 집계 쿼리로만 활용한다.

```
evaluation_run (PK: id VARCHAR(36))
  ├── eval_type: VARCHAR(20)      -- "batch" | "realtime"
  ├── target_type: VARCHAR(20)    -- "rag" | "agent" | "retrieval"
  ├── status: VARCHAR(20)         -- "pending" | "running" | "completed" | "failed"
  ├── total_cases: INT
  ├── config: JSON
  ├── created_at: DATETIME
  └── completed_at: DATETIME

evaluation_result (PK: id VARCHAR(36), FK: run_id → evaluation_run.id)
  ├── question: TEXT
  ├── answer: TEXT
  ├── ground_truth: TEXT (nullable)
  ├── contexts: JSON
  ├── metrics: JSON               -- {"faithfulness": 0.85, "answer_relevancy": 0.78, ...}
  └── created_at: DATETIME

evaluation_testset (PK: id VARCHAR(36))
  ├── name: VARCHAR(200)
  ├── description: TEXT
  ├── cases: JSON
  ├── case_count: INT
  └── created_at: DATETIME
```

### 3.2 Application DTO (신규)

```python
# src/application/ragas/admin_schemas.py

@dataclass(frozen=True)
class DashboardStatsResponse:
    total_runs: int
    status_counts: dict[str, int]       # {"pending": 1, "completed": 38, ...}
    target_type_counts: dict[str, int]  # {"rag": 30, "agent": 10, ...}
    avg_metrics: dict[str, float]       # {"faithfulness": 0.82, ...}
    recent_runs: list[EvalRunDetailResponse]

@dataclass(frozen=True)
class RunWithResultsResponse:
    id: str
    eval_type: str
    target_type: str
    status: str
    total_cases: int
    config: dict
    created_at: datetime
    completed_at: datetime | None
    summary: dict[str, float]
    results: list[EvalResultItem]
    results_total: int
```

---

## 4. API Specification

### 4.1 Endpoint List

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/api/v1/admin/ragas/dashboard` | 대시보드 통계 요약 | admin |
| GET | `/api/v1/admin/ragas/runs` | 평가 실행 목록 (필터/페이지네이션) | admin |
| GET | `/api/v1/admin/ragas/runs/{run_id}` | 실행 상세 + 결과 포함 | admin |
| GET | `/api/v1/admin/ragas/testsets` | 테스트셋 목록 | admin |

### 4.2 Detailed Specification

#### `GET /api/v1/admin/ragas/dashboard`

**Query Parameters:** `recent_limit` (int, default=5, max=20)

**Response (200 OK):**
```json
{
  "total_runs": 42,
  "status_counts": {
    "pending": 1,
    "running": 0,
    "completed": 38,
    "failed": 3
  },
  "target_type_counts": {
    "rag": 30,
    "agent": 10,
    "retrieval": 2
  },
  "avg_metrics": {
    "faithfulness": 0.82,
    "answer_relevancy": 0.75,
    "context_precision": 0.68
  },
  "recent_runs": [
    {
      "id": "uuid-1",
      "eval_type": "batch",
      "target_type": "rag",
      "status": "completed",
      "total_cases": 50,
      "created_at": "2026-05-18T10:00:00",
      "completed_at": "2026-05-18T10:05:00",
      "summary": {"faithfulness": 0.85, "answer_relevancy": 0.78}
    }
  ]
}
```

**Error Responses:**
- `401 Unauthorized`: 토큰 없음/만료
- `403 Forbidden`: admin 권한 아님

---

#### `GET /api/v1/admin/ragas/runs`

**Query Parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `target_type` | string (optional) | null | `rag`, `agent`, `retrieval` 필터 |
| `eval_type` | string (optional) | null | `batch`, `realtime` 필터 |
| `status` | string (optional) | null | `pending`, `running`, `completed`, `failed` 필터 |
| `limit` | int | 20 | 페이지 크기 (1~100) |
| `offset` | int | 0 | 오프셋 |

**Response (200 OK):**
```json
{
  "items": [
    {
      "id": "uuid-1",
      "eval_type": "batch",
      "target_type": "rag",
      "status": "completed",
      "total_cases": 50,
      "created_at": "2026-05-18T10:00:00",
      "completed_at": "2026-05-18T10:05:00",
      "summary": {"faithfulness": 0.85, "answer_relevancy": 0.78}
    }
  ],
  "total": 42,
  "limit": 20,
  "offset": 0
}
```

---

#### `GET /api/v1/admin/ragas/runs/{run_id}`

**Response (200 OK):**
```json
{
  "id": "uuid-1",
  "eval_type": "batch",
  "target_type": "rag",
  "status": "completed",
  "total_cases": 50,
  "config": {"top_k": 5, "llm_model": "gpt-4o-mini"},
  "created_at": "2026-05-18T10:00:00",
  "completed_at": "2026-05-18T10:05:00",
  "summary": {"faithfulness": 0.85},
  "results": [
    {
      "id": "uuid-r1",
      "question": "RAG 시스템이란?",
      "answer": "검색 증강 생성 시스템입니다.",
      "ground_truth": "...",
      "contexts": ["context1", "context2"],
      "scores": {"faithfulness": 0.9, "answer_relevancy": 0.8},
      "created_at": "2026-05-18T10:01:00"
    }
  ],
  "results_total": 50
}
```

**Error Responses:**
- `404 Not Found`: run_id 없음

---

#### `GET /api/v1/admin/ragas/testsets`

**Query Parameters:** `limit` (int, default=20), `offset` (int, default=0)

**Response (200 OK):**
```json
{
  "items": [
    {
      "id": "uuid-t1",
      "name": "금융상품 테스트셋",
      "description": "금융 문서 기반 QA",
      "case_count": 30,
      "created_at": "2026-05-15T09:00:00"
    }
  ],
  "total": 5,
  "limit": 20,
  "offset": 0
}
```

---

## 5. UI/UX Design

### 5.1 Screen Layout — AdminRagasPage

```
┌──────────────────────────────────────────────────────────────────┐
│ TopNav                                                           │
├────────┬─────────────────────────────────────────────────────────┤
│        │ ┌─ 헤더 ─────────────────────────────────────────────┐ │
│ Admin  │ │  RAGAS 평가                                         │ │
│ Sidebar│ │  Admin > RAGAS 평가 대시보드                         │ │
│        │ └────────────────────────────────────────────────────┘ │
│ 사용자  │                                                       │
│ 부서    │ ┌─ 통계 카드 4개 ────────────────────────────────────┐ │
│ RAGAS  │ │ [총 실행 수] [완료율] [평균 Faithfulness] [평균 AR] │ │
│ 평가   │ └────────────────────────────────────────────────────┘ │
│        │                                                       │
│        │ ┌─ 필터 바 ──────────────────────────────────────────┐ │
│        │ │ [target_type ▼] [eval_type ▼] [status ▼]          │ │
│        │ └────────────────────────────────────────────────────┘ │
│        │                                                       │
│        │ ┌─ 실행 목록 테이블 ─────────────────────────────────┐ │
│        │ │ 유형 │ 대상 │ 상태 │ 케이스수│ 평균점수│ 실행일     │ │
│        │ │──────┼──────┼──────┼────────┼────────┼──────────── │ │
│        │ │batch │ rag  │ ✅   │ 50     │ 0.85   │ 2026-05-18 │ │
│        │ │...   │      │      │        │        │            │ │
│        │ ├────────────────────────────────────────────────────┤ │
│        │ │ ◀ 1 2 3 ▶  (페이지네이션)                          │ │
│        │ └────────────────────────────────────────────────────┘ │
│        │                                                       │
│ 메인    │ ┌─ 상세 (행 클릭 시 확장/모달) ────────────────────┐ │
│ 으로   │ │ Run: uuid-1 | batch | rag | completed             │ │
│ 돌아   │ │ Config: top_k=5, llm=gpt-4o-mini                  │ │
│ 가기   │ │ 평균: faith=0.85, AR=0.78                          │ │
│        │ │                                                    │ │
│        │ │ [개별 결과 테이블]                                  │ │
│        │ │ # │ 질문          │ 답변         │ Faith │ AR     │ │
│        │ │ 1 │ RAG란?       │ 검색증강...   │ 0.90  │ 0.80  │ │
│        │ │ 2 │ 청킹전략은?  │ 고정/의미...  │ 0.85  │ 0.75  │ │
│        │ └────────────────────────────────────────────────────┘ │
├────────┴─────────────────────────────────────────────────────────┤
```

### 5.2 User Flow

```
Admin 사이드바 → "RAGAS 평가" 클릭
  → 대시보드 통계 카드 로드 (dashboard API)
  → 실행 목록 테이블 로드 (runs API)
  → 필터 변경 시 refetch
  → 행 클릭 → 상세 패널 확장 (runs/{run_id} API)
  → 개별 Q&A 결과 확인 → 메트릭 점수 색상 확인
```

### 5.3 Component Structure

| Component | Location | Responsibility |
|-----------|----------|----------------|
| `AdminRagasPage` | `pages/AdminRagasPage/index.tsx` | 페이지 컨테이너. 통계 + 목록 + 상세를 조합 |
| `StatCard` | 페이지 내부 컴포넌트 | 개별 통계 카드 (값, 라벨, 색상) |
| `RunsFilter` | 페이지 내부 컴포넌트 | target_type, eval_type, status 셀렉트 필터 |
| `RunsTable` | 페이지 내부 컴포넌트 | 실행 목록 테이블 + 페이지네이션 |
| `RunDetailPanel` | 페이지 내부 컴포넌트 | 선택된 실행의 상세 정보 + 결과 목록 |

### 5.4 메트릭 점수 색상 기준

| 범위 | 색상 | 의미 |
|------|------|------|
| 0.8 ~ 1.0 | 녹색 (`text-emerald-600`) | 우수 |
| 0.5 ~ 0.79 | 노란색 (`text-amber-600`) | 보통 |
| 0.0 ~ 0.49 | 빨간색 (`text-red-600`) | 주의 |

---

## 6. Backend Layer Design

### 6.1 Domain Layer — Interface 확장

```python
# src/domain/ragas/interfaces.py (기존 EvaluationRepositoryInterface에 추가)

@abstractmethod
async def get_dashboard_stats(
    self, recent_limit: int, request_id: str
) -> dict:
    """대시보드 통계: 상태별 수, target_type별 수, 전체 평균 메트릭."""
    ...

@abstractmethod
async def list_runs_with_summary(
    self,
    target_type: str | None,
    eval_type: str | None,
    status: str | None,
    limit: int,
    offset: int,
    request_id: str,
) -> tuple[list[dict], int]:
    """평가 실행 목록 + 각 run의 메트릭 요약 포함."""
    ...
```

### 6.2 Application Layer — AdminEvalUseCase

```python
# src/application/ragas/admin_eval_use_case.py

class AdminEvalUseCase:
    def __init__(
        self,
        repository: EvaluationRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._repository = repository
        self._logger = logger

    async def get_dashboard_stats(
        self, recent_limit: int, request_id: str
    ) -> DashboardStatsResponse:
        stats = await self._repository.get_dashboard_stats(recent_limit, request_id)
        # 최근 runs에 summary 포함
        recent_runs = []
        for run in stats["recent_runs"]:
            summary = await self._repository.get_run_summary(run.id, request_id)
            recent_runs.append(EvalRunDetailResponse(
                id=run.id,
                eval_type=run.eval_type,
                target_type=run.target_type,
                status=run.status,
                total_cases=run.total_cases,
                created_at=run.created_at,
                completed_at=run.completed_at,
                summary=summary,
            ))
        return DashboardStatsResponse(
            total_runs=stats["total_runs"],
            status_counts=stats["status_counts"],
            target_type_counts=stats["target_type_counts"],
            avg_metrics=stats["avg_metrics"],
            recent_runs=recent_runs,
        )

    async def list_runs_with_summary(
        self, target_type, eval_type, status, limit, offset, request_id
    ) -> tuple[list[EvalRunDetailResponse], int]:
        items, total = await self._repository.list_runs_with_summary(
            target_type, eval_type, status, limit, offset, request_id
        )
        return [
            EvalRunDetailResponse(
                id=i["id"], eval_type=i["eval_type"],
                target_type=i["target_type"], status=i["status"],
                total_cases=i["total_cases"], created_at=i["created_at"],
                completed_at=i["completed_at"], summary=i.get("summary", {}),
            )
            for i in items
        ], total

    async def get_run_with_results(
        self, run_id: str, request_id: str
    ) -> RunWithResultsResponse | None:
        run = await self._repository.get_run(run_id, request_id)
        if run is None:
            return None
        summary = await self._repository.get_run_summary(run_id, request_id)
        results, results_total = await self._repository.get_results_by_run(
            run_id, limit=100, offset=0, request_id=request_id
        )
        return RunWithResultsResponse(
            id=run.id, eval_type=run.eval_type,
            target_type=run.target_type, status=run.status,
            total_cases=run.total_cases, config=run.config,
            created_at=run.created_at, completed_at=run.completed_at,
            summary=summary,
            results=[
                EvalResultItem(
                    id=r.id, question=r.question, answer=r.answer,
                    ground_truth=r.ground_truth, scores=r.metrics,
                    created_at=r.created_at,
                )
                for r in results
            ],
            results_total=results_total,
        )
```

### 6.3 Infrastructure Layer — Repository 확장

```python
# src/infrastructure/ragas/repository.py (기존 EvaluationRepository에 추가)

async def get_dashboard_stats(
    self, recent_limit: int, request_id: str
) -> dict:
    # 1. 총 실행 수
    total_stmt = select(func.count(EvaluationRunModel.id))
    total = (await self._session.execute(total_stmt)).scalar() or 0

    # 2. 상태별 수
    status_stmt = (
        select(EvaluationRunModel.status, func.count(EvaluationRunModel.id))
        .group_by(EvaluationRunModel.status)
    )
    status_rows = (await self._session.execute(status_stmt)).all()
    status_counts = {row[0]: row[1] for row in status_rows}

    # 3. target_type별 수
    tt_stmt = (
        select(EvaluationRunModel.target_type, func.count(EvaluationRunModel.id))
        .group_by(EvaluationRunModel.target_type)
    )
    tt_rows = (await self._session.execute(tt_stmt)).all()
    target_type_counts = {row[0]: row[1] for row in tt_rows}

    # 4. 전체 평균 메트릭 (completed runs만)
    completed_run_ids_stmt = (
        select(EvaluationRunModel.id)
        .where(EvaluationRunModel.status == "completed")
    )
    metrics_stmt = (
        select(EvaluationResultModel.metrics)
        .where(EvaluationResultModel.run_id.in_(completed_run_ids_stmt))
    )
    metrics_rows = (await self._session.execute(metrics_stmt)).scalars().all()
    avg_metrics = self._calculate_avg_metrics(metrics_rows)

    # 5. 최근 runs
    recent_stmt = (
        select(EvaluationRunModel)
        .order_by(EvaluationRunModel.created_at.desc())
        .limit(recent_limit)
    )
    recent_result = await self._session.execute(recent_stmt)
    recent_runs = [self._to_run_entity(m) for m in recent_result.scalars()]

    return {
        "total_runs": total,
        "status_counts": status_counts,
        "target_type_counts": target_type_counts,
        "avg_metrics": avg_metrics,
        "recent_runs": recent_runs,
    }

async def list_runs_with_summary(
    self, target_type, eval_type, status, limit, offset, request_id
) -> tuple[list[dict], int]:
    stmt = select(EvaluationRunModel)
    count_stmt = select(func.count(EvaluationRunModel.id))

    for col, val in [
        (EvaluationRunModel.target_type, target_type),
        (EvaluationRunModel.eval_type, eval_type),
        (EvaluationRunModel.status, status),
    ]:
        if val:
            stmt = stmt.where(col == val)
            count_stmt = count_stmt.where(col == val)

    stmt = stmt.order_by(EvaluationRunModel.created_at.desc()).offset(offset).limit(limit)
    result = await self._session.execute(stmt)
    total = (await self._session.execute(count_stmt)).scalar() or 0

    items = []
    for model in result.scalars():
        summary = await self.get_run_summary(model.id, request_id)
        items.append({
            "id": model.id, "eval_type": model.eval_type,
            "target_type": model.target_type, "status": model.status,
            "total_cases": model.total_cases, "created_at": model.created_at,
            "completed_at": model.completed_at, "summary": summary,
        })
    return items, total

@staticmethod
def _calculate_avg_metrics(metrics_rows: list[dict]) -> dict[str, float]:
    totals: dict[str, float] = {}
    counts: dict[str, int] = {}
    for metrics in metrics_rows:
        if not metrics:
            continue
        for key, value in metrics.items():
            if isinstance(value, (int, float)):
                totals[key] = totals.get(key, 0.0) + value
                counts[key] = counts.get(key, 0) + 1
    return {k: totals[k] / counts[k] for k in totals if counts[k] > 0}
```

### 6.4 Interfaces Layer — Admin RAGAS Router

```python
# src/api/routes/admin_ragas_router.py

router = APIRouter(prefix="/api/v1/admin/ragas", tags=["admin-ragas"])

# 모든 엔드포인트에 admin: User = Depends(require_role("admin")) 적용

@router.get("/dashboard")
async def get_dashboard(
    recent_limit: int = Query(5, ge=1, le=20),
    admin: User = Depends(require_role("admin")),
    use_case=Depends(get_admin_eval_use_case),
) -> AdminDashboardResponseBody: ...

@router.get("/runs")
async def list_runs(
    target_type: str | None = Query(None),
    eval_type: str | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    admin: User = Depends(require_role("admin")),
    use_case=Depends(get_admin_eval_use_case),
) -> PaginatedResponse: ...

@router.get("/runs/{run_id}")
async def get_run_detail(
    run_id: str,
    admin: User = Depends(require_role("admin")),
    use_case=Depends(get_admin_eval_use_case),
) -> AdminRunDetailResponseBody: ...

@router.get("/testsets")
async def list_testsets(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    admin: User = Depends(require_role("admin")),
    use_case=Depends(get_admin_eval_use_case),
) -> PaginatedResponse: ...
```

---

## 7. Frontend Layer Design

### 7.1 API 상수 추가 (`constants/api.ts`)

```typescript
// Admin — RAGAS Evaluation
ADMIN_RAGAS_DASHBOARD: '/api/v1/admin/ragas/dashboard',
ADMIN_RAGAS_RUNS: '/api/v1/admin/ragas/runs',
ADMIN_RAGAS_RUN_DETAIL: (runId: string) => `/api/v1/admin/ragas/runs/${runId}`,
ADMIN_RAGAS_TESTSETS: '/api/v1/admin/ragas/testsets',
```

### 7.2 타입 정의 (`types/adminRagas.ts`)

```typescript
export interface AdminRagasDashboard {
  total_runs: number;
  status_counts: Record<string, number>;
  target_type_counts: Record<string, number>;
  avg_metrics: Record<string, number>;
  recent_runs: EvalRunSummary[];
}

export interface EvalRunSummary {
  id: string;
  eval_type: string;
  target_type: string;
  status: string;
  total_cases: number;
  created_at: string;
  completed_at: string | null;
  summary: Record<string, number>;
}

export interface EvalRunDetail extends EvalRunSummary {
  config: Record<string, unknown>;
  results: EvalResultItem[];
  results_total: number;
}

export interface EvalResultItem {
  id: string;
  question: string;
  answer: string;
  ground_truth: string | null;
  contexts: string[];
  scores: Record<string, number>;
  created_at: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}
```

### 7.3 서비스 함수 (`services/adminRagasService.ts`)

```typescript
import authApiClient from './api/authClient';
import { API_ENDPOINTS } from '@/constants/api';
import type { AdminRagasDashboard, EvalRunSummary, EvalRunDetail, PaginatedResponse } from '@/types/adminRagas';

export const adminRagasService = {
  getDashboard: (recentLimit = 5) =>
    authApiClient
      .get<AdminRagasDashboard>(API_ENDPOINTS.ADMIN_RAGAS_DASHBOARD, { params: { recent_limit: recentLimit } })
      .then(r => r.data),

  getRuns: (params: { target_type?: string; eval_type?: string; status?: string; limit?: number; offset?: number }) =>
    authApiClient
      .get<PaginatedResponse<EvalRunSummary>>(API_ENDPOINTS.ADMIN_RAGAS_RUNS, { params })
      .then(r => r.data),

  getRunDetail: (runId: string) =>
    authApiClient
      .get<EvalRunDetail>(API_ENDPOINTS.ADMIN_RAGAS_RUN_DETAIL(runId))
      .then(r => r.data),

  getTestsets: (params: { limit?: number; offset?: number }) =>
    authApiClient
      .get<PaginatedResponse<{ id: string; name: string; description: string; case_count: number; created_at: string }>>(
        API_ENDPOINTS.ADMIN_RAGAS_TESTSETS, { params }
      )
      .then(r => r.data),
};
```

### 7.4 Query Keys 추가 (`lib/queryKeys.ts`)

```typescript
// admin 섹션에 추가
admin: {
  // ... 기존 키 ...
  ragasDashboard: () => [...queryKeys.admin.all, 'ragasDashboard'] as const,
  ragasRuns: (params?: { target_type?: string; eval_type?: string; status?: string; limit?: number; offset?: number }) =>
    [...queryKeys.admin.all, 'ragasRuns', params] as const,
  ragasRunDetail: (runId: string) =>
    [...queryKeys.admin.all, 'ragasRunDetail', runId] as const,
  ragasTestsets: (params?: { limit?: number; offset?: number }) =>
    [...queryKeys.admin.all, 'ragasTestsets', params] as const,
},
```

### 7.5 AdminLayout 사이드바 항목 추가

```typescript
// AdminLayout.tsx ADMIN_SIDEBAR_ITEMS에 추가
{
  label: 'RAGAS 평가',
  path: '/admin/ragas',
  icon: 'M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 0 1 3 19.875v-6.75ZM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 0 1-1.125-1.125V8.625ZM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 0 1-1.125-1.125V4.125Z',
},
```

### 7.6 App.tsx 라우트 추가

```tsx
// Admin 전용 라우트 내부에 추가
<Route path="/admin/ragas" element={<AdminRagasPage />} />
```

---

## 8. Error Handling

### 8.1 Error Code Definition

| Code | Endpoint | Cause | Handling |
|------|----------|-------|----------|
| 401 | 전체 | 토큰 없음/만료 | 프론트에서 로그인 페이지 리다이렉트 |
| 403 | 전체 | admin 권한 아님 | 프론트 `AdminRoute`에서 사전 차단 + 서버 이중 검증 |
| 404 | `runs/{run_id}` | 존재하지 않는 run_id | "평가 실행을 찾을 수 없습니다" 메시지 표시 |

### 8.2 Error Response Format (기존 FastAPI 패턴)

```json
{
  "detail": "Evaluation run not found"
}
```

---

## 9. Security Considerations

- [x] 모든 Admin RAGAS API에 `require_role("admin")` 적용
- [x] 프론트엔드 `AdminRoute` 컴포넌트로 라우트 보호
- [x] authApiClient 사용 (Bearer 토큰 자동 첨부)
- [ ] SQL Injection 방지: SQLAlchemy ORM 파라미터 바인딩 사용 (자동)
- [ ] Rate Limiting: 현재 미적용 (향후 고려)

---

## 10. Test Plan

### 10.1 Test Scope

| Type | Target | Tool |
|------|--------|------|
| Unit Test | `AdminEvalUseCase` 메서드 | pytest + AsyncMock |
| Unit Test | Repository 통계 쿼리 | pytest + test DB |
| Integration Test | Admin RAGAS Router 엔드포인트 | pytest + httpx.AsyncClient |
| Integration Test | admin 권한 없이 접근 시 403 | pytest |

### 10.2 Test Cases

- [ ] `test_get_dashboard_stats_returns_counts_and_avg_metrics` — 통계 정상 반환
- [ ] `test_get_dashboard_stats_empty_db` — 데이터 없을 때 0/빈 dict 반환
- [ ] `test_list_runs_with_filter` — target_type, status 필터링 정상 동작
- [ ] `test_list_runs_pagination` — offset/limit 페이지네이션 정상
- [ ] `test_get_run_detail_with_results` — 실행 상세 + 결과 목록 반환
- [ ] `test_get_run_detail_not_found` — 없는 run_id 시 404
- [ ] `test_admin_role_required` — 일반 사용자 접근 시 403
- [ ] `test_unauthenticated_access` — 토큰 없이 접근 시 401

---

## 11. Implementation Order

### Phase 1: Backend (TDD)

| Step | Task | File(s) | Test First |
|------|------|---------|:----------:|
| 1 | Application DTO 정의 | `src/application/ragas/admin_schemas.py` | - |
| 2 | Domain Interface에 메서드 추가 | `src/domain/ragas/interfaces.py` | - |
| 3 | AdminEvalUseCase 작성 | `src/application/ragas/admin_eval_use_case.py` | `tests/application/ragas/test_admin_eval_use_case.py` |
| 4 | Repository에 통계/목록 구현 | `src/infrastructure/ragas/repository.py` | `tests/infrastructure/ragas/test_repository_admin.py` |
| 5 | Admin RAGAS Router 작성 | `src/api/routes/admin_ragas_router.py` | `tests/api/test_admin_ragas_router.py` |
| 6 | main.py DI 연결 | `src/api/main.py` | - |

### Phase 2: Frontend

| Step | Task | File(s) |
|------|------|---------|
| 7 | API 상수 추가 | `idt_front/src/constants/api.ts` |
| 8 | 타입 정의 | `idt_front/src/types/adminRagas.ts` |
| 9 | 서비스 함수 | `idt_front/src/services/adminRagasService.ts` |
| 10 | Query Keys 추가 | `idt_front/src/lib/queryKeys.ts` |
| 11 | AdminRagasPage 구현 | `idt_front/src/pages/AdminRagasPage/index.tsx` |
| 12 | AdminLayout 사이드바 추가 | `idt_front/src/components/layout/AdminLayout.tsx` |
| 13 | App.tsx 라우트 추가 | `idt_front/src/App.tsx` |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-05-18 | Initial draft | AI Assistant |
