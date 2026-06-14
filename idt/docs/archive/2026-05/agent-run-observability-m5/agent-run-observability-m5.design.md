# agent-run-observability-m5 Design Document

> **Summary**: M5 — Tavily web search retrieval 영속화 wiring + `GET /admin/runs` list/페이지네이션 API + V023 집계 인덱스 마이그레이션. internal_document_search(M4)와 tavily_search(M5)가 같은 `ai_retrieval_source` 테이블에 collection_name 분기로 통합되어 어드민이 web/RAG를 동등하게 분석 가능.
>
> **Project**: sangplusbot (idt)
> **Version**: 0.1
> **Author**: 배상규
> **Date**: 2026-05-21
> **Status**: Draft
> **Planning Doc**: [agent-run-observability-m5.plan.md](../../01-plan/features/agent-run-observability-m5.plan.md)
> **Parent (M1) Design**: [agent-run-observability.design.md](../../archive/2026-05/agent-run-observability/agent-run-observability.design.md)
> **Sibling Designs**: [M2](../../archive/2026-05/agent-run-observability-m2/agent-run-observability-m2.design.md) · [M3](../../archive/2026-05/agent-run-observability-m3/agent-run-observability-m3.design.md) · [M4](../../archive/2026-05/agent-run-observability-m4/agent-run-observability-m4.design.md)

---

## 1. Overview

### 1.1 Design Goals

- M4 §7.3에서 명시된 follow-up 3건 일괄 해소 — tavily retrieval / admin list API / aggregate index
- internal_document_search(M4) 패턴 100% 일관 — `TavilySearchTool`에 같은 형태 tracker DI + best-effort `record_retrieval`
- 화면 PDCA 의존성 0 — `GET /admin/runs?from=&to=&user_id=&agent_id=&status=&limit=&offset=` 구현으로 어드민 UI가 별도 backend 변경 없이 진행 가능
- 운영 안전 마진 — `ai_llm_call.created_at` 단독 인덱스 추가로 by-user/by-llm/by-node 집계 가속
- Repository 1 호출 → 2 query (list + count) 동시 처리 (asyncio.gather)
- 신규 테이블 / 도메인 entity 추가 0, 신규 마이그레이션 1건 (인덱스만)

### 1.2 Design Principles

- **Single Interception Point (Tool Body)** — M4와 동일: tavily는 `TavilySearchTool._arun` 한 곳에서 영속화. ToolFactory tavily case에 tracker 전달 1줄 추가.
- **Domain Closed for Web Schema** — `ai_retrieval_source` 컬럼 재사용, collection_name="tavily_web"으로 분기. 신규 테이블 없음 (Plan §4-2 옵션 B).
- **YAGNI** — Run list는 light keep (ai_run row만, steps/tool/retrieval/llm join 없음). chunk-by-chunk pagination·cursor·full-text search는 미포함.
- **Best-Effort Isolation** — Tavily record_retrieval 실패가 web search 답변 흐름 차단 안함 (M4 internal과 동일 try/except + warning + continue).
- **Capsule Validation** — `ListRunsUseCase`가 status enum / limit cap / 날짜 범위 검증 캡슐화 → router는 호출만.
- **Index without Code Change** — V023는 DDL only. Repository SQL 변경 0건 (created_at index가 기존 WHERE 절을 자동 가속).

### 1.3 Plan §11 Open Issues 결정

| # | Open Issue | 결정 | 근거 |
|---|------------|------|------|
| 1 | Tavily wiring method — `_arun` vs `search` | **`_arun`만 손댐**. `search`는 기존 sync 유지, `_arun`이 `search_as_value_object` → `SearchResult` → await record_retrieval → format → 반환 패턴 | M4 InternalDocumentSearchTool과 동일 정신: 도구 본체(`_arun`) 한 곳만 변경. `_run`/`search`는 backward-compat 유지 (외부에서 sync로 호출 가능) |
| 2 | `document_id VARCHAR(150)` URL 길이 부족 | **컬럼 확장 안 함**. `document_id`는 URL을 `[:150]`로 truncate하고, `metadata_json.url_full`에 원본 URL 보존 | DDL 변경 회피 (운영 ALTER 비용). 150자 미만 URL은 동일하게 저장, 초과만 truncate. metadata_json은 이미 JSON 타입이라 자유 형식 |
| 3 | `idx_llm_call_step` 추가 vs InnoDB FK 자동 인덱스 | **단독 추가**. `V021 fk_llm_call_step FOREIGN KEY (step_id)` 가 자동 인덱스 생성하지만 같은 컬럼에 명시 인덱스 추가는 멱등 (InnoDB가 이미 같은 인덱스 존재 시 중복 skip — 실제론 두 번째 인덱스는 다른 이름으로 생성될 수 있음) | 명시적 인덱스 추가는 의도 표현. 다만 V023에서는 `CREATE INDEX IF NOT EXISTS`를 쓸 수 없는 MySQL 5.7/8.0 호환을 위해 `ALTER TABLE ... ADD INDEX` 사용 — Flyway가 중복 INDEX 에러를 잡으면 V023에서 step_id 인덱스 줄 제외 가능. **Design 채택: created_at 단독만 추가, step_id는 운영 EXPLAIN으로 검증 후 별도** |
| 4 | Run list `total` 계산 방식 | **별도 COUNT 쿼리 + asyncio.gather 동시 실행** | total/rows 정합성 보장 + WHERE 조건 일치. WINDOW function COUNT(*) OVER()는 MySQL 8.0+ 한정 (호환성 회피) |
| 5 | Pagination 방식 | **limit/offset 단순** (limit ≤ 100, default 20) | M5 단계는 단순화 우선. Cursor 마이그레이션은 운영 데이터 1M row 초과 시 별도 PDCA |
| 6 | Status filter validation | **`RunStatus` enum 정확 일치만** (RUNNING/SUCCESS/FAILED/CANCELLED) | 값 외 → 422. router 또는 use case 검증 (use case 캡슐화 채택) |
| 7 | user_id / agent_id filter — 정확 일치 vs LIKE | **정확 일치 (equality)** | UUID4 / 정형 id이므로 부분 매칭 불필요. LIKE는 인덱스 회피 위험 |
| 8 | Run list 응답에 `agent_name` / `user_email` join | **미포함 (M5)** — id만 반환 | 어드민 UI가 별도 fetch (`/agents/{id}`, `/auth/users/{id}` 등) 가능. Run list는 light keep. join 비용 회피 |
| 9 | V023 마이그레이션의 운영 DB 적용 시점 | **본 PDCA는 dev/test 환경만** — 운영 적용은 유지보수 윈도우에서 별도 절차 | online DDL이 InnoDB 5.6+ 가능하나 락 위험 0 보장 어려움. 운영팀 관리 영역 |
| 10 | Tavily document_id 충돌 (같은 URL이 다른 run에 등장) | **id는 row uuid4 — document_id 중복 OK** | document_id는 PK 아님. 분석 시 GROUP BY document_id로 인기 URL 집계 가능 (free win) |

---

## 2. Architecture

### 2.1 Component Diagram (M5 추가)

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        HTTP Layer (FastAPI)                               │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │ agent_run_router.py  (M4 + M5 patch)                              │    │
│  │  ... 기존 5 endpoints (M4)                                        │    │
│  │  GET /api/v1/admin/runs?from=&to=&user_id=&agent_id=&status=     │    │
│  │                       &limit=20&offset=0           ★ M5 신규     │    │
│  └─────────────────────────┬────────────────────────────────────────┘    │
└────────────────────────────┼────────────────────────────────────────────┘
                             │ Depends(ListRunsUseCase)
                             ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                       Application Layer                                   │
│  application/agent_run/use_cases/list_runs_use_case.py  ★ NEW            │
│   execute(filters: RunListFilters) →                                      │
│     1. validate(filters) — status enum / limit ≤ 100                      │
│     2. asyncio.gather(                                                    │
│           agent_run_repo.list_runs(filters),                              │
│           agent_run_repo.count_runs(filters),                             │
│        ) → (rows, total)                                                  │
│     3. return RunListDto(rows, total, from_dt, to_dt, limit, offset)      │
│  ────────────────────────────────────────────────────────────────────    │
│  infrastructure/web_search/tavily_tool.py  ★ MODIFIED                    │
│   TavilySearchTool:                                                       │
│    - model_config + tracker / logger / config 필드 추가                   │
│    - _arun:                                                               │
│        result = self.search_as_value_object(...)                          │
│        await self._record_retrievals_best_effort(result)  ★ M5 신규       │
│        return format_search_result_to_xml(result, ...)                    │
└──────────────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                       Infrastructure / Domain                             │
│  domain/agent_run/interfaces.py  ★ MODIFIED                              │
│   + RunListFilters dataclass                                              │
│   + AgentRunRepositoryInterface.list_runs(filters) -> List[AgentRun]      │
│   + AgentRunRepositoryInterface.count_runs(filters) -> int                │
│                                                                           │
│  infrastructure/persistence/repositories/agent_run_repository.py          │
│   + list_runs SQL — WHERE 조건부 + ORDER BY started_at DESC + LIMIT/OFFSET│
│   + count_runs SQL — 같은 WHERE + COUNT(*)                                │
│                                                                           │
│  infrastructure/agent_builder/tool_factory.py  ★ MODIFIED                │
│   case "tavily_search":                                                   │
│     return TavilySearchTool(                                              │
│       api_key=self._tavily_api_key,                                       │
│       tracker=self._tracker,                          ★ M5                │
│       logger=self._logger,                            ★ M5                │
│       config=self._obs_config,                        ★ M5                │
│     )                                                                     │
│                                                                           │
│  db/migration/V023__add_agent_run_aggregate_indexes.sql  ★ NEW           │
│   ALTER TABLE ai_llm_call ADD INDEX idx_llm_call_created (created_at);    │
└──────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Tavily Retrieval Wiring Data Flow

```
[LangGraph worker_react node body]
  ↓ tool invocation (M2 wiring 기반)
[TavilySearchTool.ainvoke (BaseTool 표준)]
  ↓ M2: UsageCallback.on_tool_start → tracker.record_tool_call → tool_call_id 발급
  ↓ M2: RunContext.tool_call_id = tool_call_id  ★ M2가 set
  ↓ M3: RunContext.step_id = step_id            ★ M3가 set
  ↓
[TavilySearchTool._arun(query, ...)]   ★ M5 wiring 지점
  │
  ├─ result: SearchResult = self.search_as_value_object(query, request_id, ...)
  │
  ├─ if self.tracker is not None:
  │     ctx = get_current_run_context()
  │     if ctx is not None and ctx.run_id is not None:
  │         for rank_index, item in enumerate(result.items, start=1):
  │             try:
  │                 doc_id_truncated = (item.url or "")[:150]
  │                 await self.tracker.record_retrieval(
  │                     run_id=ctx.run_id,
  │                     tool_call_id=ctx.tool_call_id,     # M2 자동 set
  │                     collection_name="tavily_web",        # ★ 고정
  │                     document_id=doc_id_truncated or None,
  │                     chunk_id=None,                        # web 결과 chunk 없음
  │                     score=item.score,
  │                     rank_index=rank_index,
  │                     content_preview=item.content[:preview_max],
  │                     metadata={
  │                         "title": item.title,
  │                         "url_full": item.url,            # 잘림 대비
  │                         "raw_score": item.score,
  │                     },
  │                 )
  │             except Exception as e:
  │                 self.logger.warning("record_retrieval failed (best-effort)",
  │                                     exception=e, url=item.url[:50])
  │                 # continue
  │
  └─ return format_search_result_to_xml(result, include_raw_content=...)
  ↓
[UsageCallback.on_tool_end → tracker.update_tool_call(SUCCESS) — M2]
[ai_retrieval_source 테이블에 N row INSERT 완료 (collection='tavily_web')]
```

**핵심**: `_arun`이 sync `search_as_value_object`를 호출(블로킹 짧음 — Tavily API 1회) → async `record_retrieval` for-loop → 마지막에 XML 변환. M4 InternalDocumentSearchTool의 동기→비동기 승격 결정과 같은 정신.

### 2.3 Admin Run List Flow

```
GET /api/v1/admin/runs?from=2026-05-01&to=2026-05-22&status=FAILED&user_id=u-99&limit=20&offset=0
  ↓ require_role("admin")
[agent_run_router.get_admin_runs(filters, current_user)]
  ↓
[ListRunsUseCase.execute(filters: RunListFilters)]
  │
  ├─ # validation (capsule)
  │   if filters.status and filters.status not in RunStatus values  → raise ValueError
  │   if filters.limit > 100  → raise ValueError
  │   if filters.from_dt and filters.to_dt and filters.from_dt > filters.to_dt → raise ValueError
  │
  ├─ # parallel
  │   rows, total = await asyncio.gather(
  │       self._agent_run_repo.list_runs(filters),
  │       self._agent_run_repo.count_runs(filters),
  │   )
  │
  └─ return RunListDto(rows, total, from_dt, to_dt, limit, offset)
  ↓
return RunListResponse.from_dto(dto)
```

### 2.4 Repository SQL

```python
# SqlAlchemyAgentRunRepository.list_runs
async def list_runs(self, filters: RunListFilters) -> List[AgentRun]:
    stmt = select(AgentRunModel)
    stmt = self._apply_filters(stmt, filters)
    stmt = stmt.order_by(AgentRunModel.started_at.desc())
    stmt = stmt.limit(filters.limit).offset(filters.offset)
    rows = (await self._session.execute(stmt)).scalars().all()
    return [self._run_to_domain(r) for r in rows]


async def count_runs(self, filters: RunListFilters) -> int:
    stmt = select(func.count()).select_from(AgentRunModel)
    stmt = self._apply_filters(stmt, filters)
    return int((await self._session.execute(stmt)).scalar_one())


def _apply_filters(self, stmt, filters: RunListFilters):
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

**인덱스 활용 분석**:
- 단순 `from/to` 만 → `idx_run_started_at (started_at DESC)` 활용 ✅
- `user_id` 추가 → `idx_run_user_started (user_id, started_at DESC)` 활용 ✅
- `agent_id` 추가 → `idx_run_agent (agent_id)` 활용 후 started_at sort
- `status` 추가 → `idx_run_status (status)` 활용 후 started_at sort
- 모두 V021에 이미 존재. M5에서 추가 인덱스 불필요.

### 2.5 V023 Migration

```sql
-- db/migration/V023__add_agent_run_aggregate_indexes.sql
-- M5: M4 §7.3 follow-up — 집계 API (by-user/by-llm/by-node) 성능 마진

-- 1) ai_llm_call.created_at 단독 인덱스
--    by-user/by-llm/by-node 모두 WHERE created_at BETWEEN ? AND ? 으로 시작
--    기존 composite (user_id, created_at DESC) 등은 leading column 필터 없으면 무효
ALTER TABLE ai_llm_call
ADD INDEX idx_llm_call_created (created_at);

-- 2) (옵션) ai_llm_call.step_id 명시 인덱스
--    V021 fk_llm_call_step FOREIGN KEY (step_id)가 InnoDB 자동 인덱스 생성 — 명시 추가는 중복
--    Design §1.3 #3에 따라 본 V023에서는 step_id 인덱스 미추가
--    필요 시 운영 EXPLAIN 으로 by-node 쿼리 검증 후 V024로 별도

-- (참고) ai_run.started_at 단독 인덱스
--    V021 idx_run_started_at (started_at DESC)이 이미 존재 — list_runs ORDER BY 자동 가속
```

**효과 측정 SQL** (수동 검증용):
```sql
EXPLAIN
SELECT s.node_name,
       SUM(l.total_tokens), SUM(l.total_cost_usd), COUNT(*)
  FROM ai_llm_call l
  JOIN ai_run_step s ON s.id = l.step_id
 WHERE l.created_at BETWEEN '2026-05-01' AND '2026-05-22'
 GROUP BY s.node_name;
-- expected: key=idx_llm_call_created, type=range
```

---

## 3. Application Layer Design

### 3.1 `RunListFilters` Domain Dataclass

**파일**: `src/domain/agent_run/interfaces.py`

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass(frozen=True)
class RunListFilters:
    """Run list 조회 필터 + 페이지네이션 (M5)."""
    from_dt: Optional[datetime] = None
    to_dt: Optional[datetime] = None
    user_id: Optional[str] = None
    agent_id: Optional[str] = None
    status: Optional[str] = None   # RunStatus enum value (RUNNING/SUCCESS/FAILED/CANCELLED)
    limit: int = 20
    offset: int = 0
```

**불변성 — frozen=True**: filter는 use case 진입 후 변경 불가 (replace 패턴 사용 시 별도 instance).

### 3.2 abc Methods

```python
class AgentRunRepositoryInterface(ABC):
    ...
    @abstractmethod
    async def list_runs(self, filters: RunListFilters) -> List[AgentRun]:
        """필터 + ORDER BY started_at DESC + LIMIT/OFFSET."""

    @abstractmethod
    async def count_runs(self, filters: RunListFilters) -> int:
        """같은 필터로 total row count — list_runs와 정합 보장."""
```

### 3.3 `ListRunsUseCase`

**파일**: `src/application/agent_run/use_cases/list_runs_use_case.py`

```python
import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import List

from src.domain.agent_run.entities import AgentRun
from src.domain.agent_run.interfaces import (
    AgentRunRepositoryInterface,
    RunListFilters,
)
from src.domain.agent_run.value_objects import RunStatus
from src.domain.logging.interfaces.logger_interface import LoggerInterface


_MAX_LIMIT = 100
_VALID_STATUSES = {s.value for s in RunStatus}


@dataclass(frozen=True)
class RunListDto:
    rows: List[AgentRun]
    total: int
    from_dt: datetime
    to_dt: datetime
    limit: int
    offset: int


class ListRunsUseCase:
    def __init__(
        self,
        agent_run_repo: AgentRunRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._agent_run_repo = agent_run_repo
        self._logger = logger

    async def execute(self, filters: RunListFilters) -> RunListDto:
        self._validate(filters)
        rows, total = await asyncio.gather(
            self._agent_run_repo.list_runs(filters),
            self._agent_run_repo.count_runs(filters),
        )
        return RunListDto(
            rows=rows,
            total=total,
            from_dt=filters.from_dt,
            to_dt=filters.to_dt,
            limit=filters.limit,
            offset=filters.offset,
        )

    def _validate(self, filters: RunListFilters) -> None:
        if filters.limit < 1 or filters.limit > _MAX_LIMIT:
            raise ValueError(f"limit must be between 1 and {_MAX_LIMIT}")
        if filters.offset < 0:
            raise ValueError("offset must be >= 0")
        if filters.status is not None and filters.status not in _VALID_STATUSES:
            raise ValueError(
                f"status must be one of {sorted(_VALID_STATUSES)}"
            )
        if (
            filters.from_dt is not None
            and filters.to_dt is not None
            and filters.from_dt > filters.to_dt
        ):
            raise ValueError("from must be <= to")
```

### 3.4 `TavilySearchTool` 수정

**파일**: `src/infrastructure/web_search/tavily_tool.py`

핵심 변경:
1. `model_config = ConfigDict(arbitrary_types_allowed=True)` — Pydantic v2에서 임의 타입 필드 허용
2. `tracker / logger / config` 필드 (모두 Optional)
3. `_arun` 재구성 — sync `search_as_value_object` → async record_retrieval → format

```python
class TavilySearchTool(BaseTool):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str = "tavily_search"
    description: str = "..."
    args_schema: type = TavilySearchInput

    _api_key: str
    _client: TavilyClient
    _max_results: int

    # ── M5 추가 필드 (Optional — graph 외 단독 사용 시 None) ─────────
    tracker: Any = None
    logger: Any = None
    config: Any = None

    def __init__(self, api_key=None, max_results=None, **kwargs) -> None:
        # M5: tracker/logger/config는 super().__init__()에 그대로 흘러감
        super().__init__(**kwargs)
        ...

    async def _arun(
        self,
        query: str,
        search_depth="basic",
        topic="general",
        max_results=None,
        include_raw_content=False,
        days=None,
    ) -> str:
        """비동기 실행 — M5에서 retrieval 영속화 추가."""
        result = self.search_as_value_object(
            query=query,
            request_id="langchain-run",
            search_depth=search_depth,
            topic=topic,
            max_results=max_results,
            include_raw_content=include_raw_content,
            days=days,
        )

        if self.tracker is not None:
            await self._record_retrievals_best_effort(result)

        return format_search_result_to_xml(
            result, include_raw_content=include_raw_content
        )

    async def _record_retrievals_best_effort(self, result) -> None:
        ctx = get_current_run_context()
        if ctx is None or ctx.run_id is None:
            return
        preview_max = (self.config or _DEFAULT_OBS_CFG).retrieval_preview_max_bytes
        for rank_index, item in enumerate(result.items, start=1):
            try:
                doc_id = (item.url or "")[:150]
                await self.tracker.record_retrieval(
                    run_id=ctx.run_id,
                    tool_call_id=ctx.tool_call_id,
                    collection_name="tavily_web",
                    document_id=doc_id or None,
                    chunk_id=None,
                    score=item.score,
                    rank_index=rank_index,
                    content_preview=(item.content or "")[:preview_max] or None,
                    metadata={
                        "title": item.title,
                        "url_full": item.url,
                        "raw_score": item.score,
                    },
                )
            except Exception as e:
                if self.logger is not None:
                    self.logger.warning(
                        "tavily record_retrieval failed (best-effort)",
                        exception=e,
                        url=(item.url or "")[:80],
                    )
                # continue
```

**중요**: `_run` (sync)은 변경 없음. 외부에서 sync로 호출 시(드뭄) 기존 동작 그대로. async path만 영속화 추가.

---

## 4. Domain Layer Changes

### 4.1 `RunListFilters` dataclass (§3.1 참조)

### 4.2 `aggregate_by_node` / `list_runs` / `count_runs` abc 추가

```python
@abstractmethod
async def list_runs(self, filters: RunListFilters) -> List[AgentRun]: ...

@abstractmethod
async def count_runs(self, filters: RunListFilters) -> int: ...
```

### 4.3 Domain 변경 없음

- `AgentRun` 엔티티: 그대로
- `RunStatus` enum: 그대로
- `RetrievalSource` 엔티티: 그대로 (collection_name만 "tavily_web" 분기 — 도메인 정책상 자유 문자열)
- 새 `value_objects` / `policies` / `entities` 추가: 없음

---

## 5. Infrastructure Layer Design

### 5.1 `SqlAlchemyAgentRunRepository.list_runs / count_runs` (§2.4 참조)

### 5.2 V023 마이그레이션 (§2.5 참조)

### 5.3 `TavilySearchTool` 수정 (§3.4 참조)

### 5.4 ToolFactory tavily case 확장

```python
case "tavily_search":
    from src.infrastructure.web_search.tavily_tool import TavilySearchTool

    return TavilySearchTool(
        api_key=self._tavily_api_key,
        # ── M5: retrieval 영속화 wiring ──
        tracker=self._tracker,
        logger=self._logger,
        config=self._obs_config,
    )
```

**기존 변경 없음**:
- `excel_export` / `python_code_executor` / `mcp_*` 도구는 retrieval 개념 없음 → wiring 추가 안 함
- `internal_document_search` 케이스: M4가 이미 wiring → M5 변경 0

---

## 6. Interfaces (HTTP) Layer Design

### 6.1 `agent_run_router.py` — `GET /admin/runs` 추가

```python
from src.application.agent_run.use_cases.list_runs_use_case import ListRunsUseCase
from src.domain.agent_run.interfaces import RunListFilters
from src.interfaces.schemas.agent_run_response import RunListResponse, RunRowDto


def get_list_runs_use_case() -> ListRunsUseCase:
    raise NotImplementedError("ListRunsUseCase not initialized")


@router.get("/admin/runs", response_model=RunListResponse)
async def get_admin_runs(
    from_: Optional[datetime] = Query(None, alias="from"),
    to: Optional[datetime] = Query(None),
    user_id: Optional[str] = Query(None),
    agent_id: Optional[str] = Query(None),
    status_: Optional[str] = Query(None, alias="status"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    _: User = Depends(require_role("admin")),
    use_case: ListRunsUseCase = Depends(get_list_runs_use_case),
) -> RunListResponse:
    """관리자 Run 목록 (페이지네이션 + 필터)."""
    from_dt, to_dt = _resolve_period(from_, to)
    filters = RunListFilters(
        from_dt=from_dt,
        to_dt=to_dt,
        user_id=user_id,
        agent_id=agent_id,
        status=status_,
        limit=limit,
        offset=offset,
    )
    try:
        dto = await use_case.execute(filters)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )
    return RunListResponse.from_dto(dto)
```

**FastAPI Query 검증**: `Query(20, ge=1, le=100)` 으로 1차 검증 → use case _validate가 2차 (depth-in-defense).

### 6.2 Pydantic Schemas

**파일**: `src/interfaces/schemas/agent_run_response.py` (M4 schemas에 추가)

```python
class RunRowDto(BaseModel):
    """Run list 한 row (light — steps/tool_calls join 없음)."""
    id: str
    user_id: str
    agent_id: str
    conversation_id: str
    status: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    latency_ms: Optional[int] = None
    total_tokens: int = 0
    total_cost_usd: Decimal = Decimal("0")
    llm_call_count: int = 0
    error_message: Optional[str] = None


class RunListResponse(BaseModel):
    from_dt: datetime
    to_dt: datetime
    limit: int
    offset: int
    total: int
    rows: List[RunRowDto]

    @classmethod
    def from_dto(cls, dto) -> "RunListResponse":
        return cls(
            from_dt=dto.from_dt,
            to_dt=dto.to_dt,
            limit=dto.limit,
            offset=dto.offset,
            total=dto.total,
            rows=[
                RunRowDto(
                    id=r.id.value,
                    user_id=r.user_id,
                    agent_id=r.agent_id,
                    conversation_id=r.conversation_id,
                    status=r.status.value if hasattr(r.status, "value") else str(r.status),
                    started_at=r.started_at,
                    ended_at=r.ended_at,
                    latency_ms=r.latency_ms,
                    total_tokens=r.token_usage.total_tokens,
                    total_cost_usd=r.cost_usd.total_usd,
                    llm_call_count=r.llm_call_count,
                    error_message=r.error_message,
                )
                for r in dto.rows
            ],
        )
```

---

## 7. Wiring (api/main.py)

### 7.1 ListRunsUseCase Factory

```python
# import
from src.application.agent_run.use_cases.list_runs_use_case import ListRunsUseCase
from src.api.routes.agent_run_router import get_list_runs_use_case

# create_agent_run_factories() 확장
def list_runs_factory(
    session: AsyncSession = Depends(get_session),
) -> ListRunsUseCase:
    return ListRunsUseCase(
        agent_run_repo=SqlAlchemyAgentRunRepository(session),
        logger=app_logger,
    )

# return 튜플에 추가
return (
    run_detail_factory,
    by_user_factory,
    by_llm_factory,
    by_node_factory,
    me_factory,
    list_runs_factory,  # ★ M5
)

# call site (create_app)
(
    _run_detail_f, _usage_by_user_f, _usage_by_llm_f,
    _usage_by_node_f, _usage_me_f, _list_runs_f,
) = create_agent_run_factories()

app.dependency_overrides[get_list_runs_use_case] = _list_runs_f
```

### 7.2 ToolFactory 변경 (이미 §5.4)

`create_agent_builder_factories` 안 `tool_factory` 인스턴스가 이미 M4에서 `tracker / run_observability_config` 보유 → tavily case에 자동 전달. main.py 변경 0건.

---

## 8. Permission Matrix

| Endpoint | 인증 | 권한 | 추가 검증 |
|----------|------|------|-----------|
| `GET /api/v1/admin/runs` | Required | admin only | limit ≤ 100 (FastAPI Query) + status enum (use case) + from ≤ to (router `_resolve_period` 재사용) |

기존 M4 endpoints는 변경 없음.

---

## 9. Test Strategy

### 9.1 단위/통합 테스트 매트릭스

| 모듈 | 파일 | 케이스 수 | 핵심 검증 |
|------|------|----------|----------|
| TavilySearchTool retrieval | `tests/infrastructure/web_search/test_tavily_retrieval.py` ★ NEW | 4 | per-hit / ctx None skip / tool_call_id forward / best-effort 격리 |
| AgentRunRepository list/count | `tests/infrastructure/agent_run/test_agent_run_repository_list.py` ★ NEW | 4 | 필터 / pagination / ORDER BY / COUNT 정합 |
| ListRunsUseCase | `tests/application/agent_run/use_cases/test_list_runs_use_case.py` ★ NEW | 4 | filter forward (parallel) / status invalid / limit cap / from>to |
| agent_run_router /admin/runs | `tests/api/test_agent_run_router_list.py` ★ NEW | 5 | 200 admin / 403 non-admin / 422 invalid status / 422 limit>100 / pagination total |
| ToolFactory tavily | `tests/infrastructure/agent_builder/test_tool_factory_tavily.py` | 1 (확장) | tracker 주입 검증 |
| V023 migration | (수동/별도) | — | `SHOW INDEX FROM ai_llm_call` 결과 검증 |

**총 신규**: ~18 cases. M4 회귀 0건 보장.

### 9.2 핵심 회귀 가드 (3건)

1. **`test_record_retrieval_failure_does_not_break_tavily_output`** — Tavily 답변이 retrieval 실패로 차단 안됨 (M4 internal과 동일 패턴)
2. **`test_count_runs_returns_total_with_same_filters`** — list/count WHERE 절 정합성 (pagination 신뢰성)
3. **`test_get_admin_runs_requires_admin_role`** — 권한 안전성

### 9.3 통합 검증 (수동)

Plan §12.3 항목 11건. 핵심 SQL 3건:

```sql
-- (1) Tavily retrieval row 채워짐
SELECT rs.rank_index, rs.document_id, rs.score, LEFT(rs.content_preview, 80) AS preview
  FROM ai_retrieval_source rs
 WHERE rs.run_id = ? AND rs.collection_name = 'tavily_web'
 ORDER BY rs.rank_index;

-- (2) internal + tavily 통합 (한 run 안에 둘 다 있는 경우)
SELECT rs.collection_name, COUNT(*) AS hits, AVG(rs.score) AS avg_score
  FROM ai_retrieval_source rs
 WHERE rs.run_id = ?
 GROUP BY rs.collection_name;

-- (3) V023 인덱스 활용 확인
EXPLAIN
SELECT s.node_name, SUM(l.total_tokens) FROM ai_llm_call l
  JOIN ai_run_step s ON s.id = l.step_id
 WHERE l.created_at BETWEEN ? AND ?
 GROUP BY s.node_name;
-- expected: key=idx_llm_call_created, rows scanned 감소
```

---

## 10. Risk Mitigation

| 위험 | 영향 | 가능성 | M5 대응 |
|------|------|--------|---------|
| Tavily URL > 150자 truncation | `document_id` 잘림 | Medium | `metadata_json.url_full` 보존. 어드민 화면이 `url_full` 우선 사용 |
| `search_as_value_object` 가 sync — `_arun` 안 호출 시 event loop block | API latency 비례 (300-2000ms) | Low | Tavily API 1회만 호출 — 이미 LangChain 표준 패턴. 별도 thread pool 없이 acceptable. 운영 측정 후 `loop.run_in_executor` 검토 |
| `record_retrieval` 5회 commit → 트랜잭션 부하 | DB 부하 | Low | Tavily 평균 max_results=5 — 5 INSERT는 LLM 호출 대비 무시 가능 |
| `_arun` 안 sync `search` 호출이 일부 case에서 raise | 사용자에게 RuntimeError 전파 | Resolved | `search` 자체는 기존 코드 보존 — 예외 발생 시 raise가 정상 동작 (M4와 동일). 단 `_record_retrievals_best_effort`는 try/except |
| ALTER TABLE V023 운영 락 | 짧은 쓰기 잠금 | Medium | InnoDB online DDL (5.6+) — `LOCK=NONE` 옵션 가능. 운영 유지보수 윈도우에서 별도 실행. 본 PDCA는 dev/test 검증만 |
| Run list `count_runs` 비용 | 큰 데이터셋에서 full scan 위험 | Medium | 1차: from/to 좁힘 (default 30일) + `idx_run_started_at` 활용. 페이지네이션 cursor는 별도 PDCA |
| status 필터 잘못된 값으로 422 빈도 | 어드민 UX 혼선 | Low | 응답 detail에 `"status must be one of [...]"` — 정확한 enum 목록 노출. UI dropdown 권장 |
| `idx_llm_call_created` 추가가 INSERT 성능 영향 | LLM 호출 INSERT slow | Low | created_at 단일 컬럼 인덱스 — INSERT 비용 거의 0. 운영 LLM 호출은 단위 단조 시간 → 항상 끝 append |
| Tavily `item.url`이 None | `document_id` NULL OK | Low | `(item.url or "")[:150] or None` 패턴 — None 허용 (V021 컬럼 NULL) |
| metadata_json 안 `raw_content` 미포함 — 비밀 누설 우려 | None | Resolved | M5에서 raw_content는 절대 metadata에 넣지 않음. content_preview만 500자 컷 |
| `_arun` 변경이 LangGraph 워크플로우에 영향 | M3 wrapping과 충돌 | None | M3는 `_arun`을 호출하는 노드 함수를 wrap. M5는 `_arun` 본문만 변경 — 시그니처/반환 타입 동일 (str) |

---

## 11. Implementation Order

Plan §6 단계와 정합. M5-0 (Open Issue 결정)은 본 Design 완료로 해소.

1. **M5-1**: `TavilySearchTool` async _arun 재구성 + tracker/logger/config 필드 + best-effort 영속화 + 단위 4건 (test-first)
2. **M5-2**: ToolFactory tavily case에 tracker 전달 + 단위 1건 추가
3. **M5-3**: `RunListFilters` + `AgentRunRepositoryInterface.list_runs` / `count_runs` abc + 단위 1건
4. **M5-4**: `SqlAlchemyAgentRunRepository.list_runs` / `count_runs` SQL + 통합 4건
5. **M5-5**: `ListRunsUseCase` + 단위 4건 (★ asyncio.gather + validation)
6. **M5-6**: `agent_run_router.py` `GET /admin/runs` + Pydantic + 통합 5건
7. **M5-7**: `api/main.py` DI wiring (1 신규 factory)
8. **M5-8**: V023 마이그레이션 (`db/migration/V023__add_agent_run_aggregate_indexes.sql`)
9. **M5-9**: 수동 검증 (실 Tavily 검색 1회 + /admin/runs curl + EXPLAIN)

**핵심 의존성**:
- M5-1 → M5-2 (factory 주입은 tool 변경 이후)
- M5-3 → M5-4 → M5-5 → M5-6 → M5-7 (chain)
- M5-8 (V023)은 코드와 독립 — 마지막 또는 병렬

---

## 12. Open Issues (Design 종료 후 처리)

| Open Issue | 처리 시점 |
|-----------|----------|
| Tavily `_arun` 안 sync `search_as_value_object` 호출 비용 | 운영 환경 latency 측정 후 `run_in_executor` 검토 |
| `idx_llm_call_step` 명시 인덱스 추가 여부 | 운영 EXPLAIN by-node 결과로 별도 V024 PDCA |
| Run list response 확장 (agent_name / user_email join) | 어드민 UI PDCA에서 요구 시 별도 |
| Cursor-based pagination 마이그레이션 | 운영 데이터 1M run 초과 시 별도 PDCA |
| Tavily raw_content 영속화 | 보안/스토리지 비용 검토 후 별도 |
| Run list filter — full-text 검색 (error_message LIKE 등) | 어드민 UI 요구 시 별도 |

---

## 13. Design 변경 이력

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2026-05-21 | M5 초안 — Tavily retrieval wiring + admin run list API + V023 idx_llm_call_created. Open Issues 10건 모두 결정 완료 (§1.3) |

---

## 14. 참고 자료

- Plan: [agent-run-observability-m5.plan.md](../../01-plan/features/agent-run-observability-m5.plan.md)
- M1 Design (전체 데이터 모델): [agent-run-observability.design.md](../../archive/2026-05/agent-run-observability/agent-run-observability.design.md)
- M2 Design (tool_call_id ContextVar): [agent-run-observability-m2.design.md](../../archive/2026-05/agent-run-observability-m2/agent-run-observability-m2.design.md)
- M3 Design (step_id ContextVar): [agent-run-observability-m3.design.md](../../archive/2026-05/agent-run-observability-m3/agent-run-observability-m3.design.md)
- M4 Design (5 read API + invalidate capsule): [agent-run-observability-m4.design.md](../../archive/2026-05/agent-run-observability-m4/agent-run-observability-m4.design.md)
- M4 Report §7.3 (M5 scope 명시): [agent-run-observability-m4.report.md](../../archive/2026-05/agent-run-observability-m4/agent-run-observability-m4.report.md)
- V021 schema: `db/migration/V021__create_agent_run_tables.sql`
- V022 pricing: `db/migration/V022__add_llm_model_pricing.sql`
- Tavily tool: `src/infrastructure/web_search/tavily_tool.py`
- Tavily search result VO: `src/domain/web_search/value_objects.py` (`SearchResultItem.url/title/score/content/raw_content`)
