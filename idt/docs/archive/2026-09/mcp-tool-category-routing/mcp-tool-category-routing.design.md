# mcp-tool-category-routing Design Document

> **Summary**: 도구 카테고리를 `tool_catalog` 데이터로 관리하고, 수집형(`collect`)은 react 루프 없는 단일샷 노드로, 미분류는 호출 상한이 걸린 기존 react로 라우팅한다.
>
> **Project**: sangplusbot (idt)
> **Version**: —
> **Author**: 배상규
> **Date**: 2026-09-03
> **Status**: Draft
> **Planning Doc**: [mcp-tool-category-routing.plan.md](../../01-plan/features/mcp-tool-category-routing.plan.md)

### Pipeline References

| Phase | Document | Status |
|-------|----------|--------|
| Phase 1 | Schema Definition | N/A (PDCA 단독 사이클) |
| Phase 2 | Coding Conventions | ✅ `idt/CLAUDE.md` + `idt/docs/rules/` |
| Phase 3 | Mockup | N/A |
| Phase 4 | API Spec | 본 문서 §4 |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | MCP 도구가 구조적으로 분류 불가 → 전부 react 루프 → 중복 호출 + 근거/분석 경계 붕괴 |
| **WHO** | P2 (KB 운영자 / 에이전트 소유자) — MCP 도구를 붙여 에이전트를 만드는 사람. 및 도구 카탈로그 관리자 |
| **RISK** | 기존 저장 에이전트의 동작 변화(회귀). → category NULL = 현행과 100% 동일 경로로 방어 |
| **SUCCESS** | 스크랩 MCP 워커 1회 실행당 MCP 호출 1회, 산출물이 `is_search_result()` 판정 통과, 기존 에이전트 회귀 0건 |
| **SCOPE** | M1 스키마·카탈로그 / M2 collect 노드 / M3 컴파일러 라우팅·상한 / M4 Admin UI |

---

## 1. Overview

### 1.1 Design Goals

1. **노드 선택을 데이터로 이동** — `if tool_id == "..."` 하드코딩이 아니라 `tool_catalog.category` 값으로 워커 노드 종류를 결정한다.
2. **수집과 분석의 경계 복원** — 수집형 워커의 산출은 도구 원본이어야 하고, 종합·분석은 하류 analysis / final_answer 노드의 책임이다.
3. **호출 폭주의 이중 봉쇄** — 워커 내부(react 루프)와 워커 외부(supervisor 재라우팅) 양쪽에 상한을 둔다.
4. **무회귀 우선** — `category` NULL은 이 사이클 이전과 바이트 단위로 동일한 경로를 탄다.

### 1.2 Design Principles

- **Additive opt-in** — 신규 의존은 전부 `None` 기본값. 미주입 시 기존 동작 유지 (`_middleware_provider`, `_wiki_toc_provider` 선례).
- **동형 계약(AD-1)** — collect 노드 팩토리는 `create_search_pipeline_node` / `create_deep_search_node`와 동일한 시그니처·반환 계약을 따른다.
- **메시지 규약 단일 출처(D2 계승)** — 근거 메시지는 `search_pipeline.format_search_result()` 하나만 생산한다. collect는 이를 import해 재사용하며 새 마커를 만들지 않는다.
- **바퀴 재발명 금지** — 호출 상한은 langchain v1 내장 `ToolCallLimitMiddleware`, 재라우팅 억제는 기존 `SupervisorHooks.skip_workers` 확장점을 쓴다.
- **레이어 경계** — langchain 클래스 참조는 `MiddlewareBuilder`(D8 격리 지점)에 가둔다.

---

## 2. Architecture Options

### 2.0 Architecture Comparison

| Criteria | Option A: Minimal | Option B: Clean | Option C: Pragmatic |
|----------|:-:|:-:|:-:|
| **Approach** | 신규 노드 없이 react + `run_limit=1` + 출력 후처리 | 카테고리→노드 팩토리 레지스트리로 generator 하드코딩 분기까지 흡수 | `collect_pipeline.py` 신설, generator 분기 무수정 |
| **New Files** | 2 | 7 | 5 |
| **Modified Files** | 8 | 15 | 10 |
| **Complexity** | Low | High | Medium |
| **Maintainability** | Low | High | High |
| **Effort** | Low | High | Medium |
| **Risk** | **High — 핵심 증상 미해결** | Medium (Plan Out of Scope 유입) | Low |
| **Recommendation** | — | 장기 리팩토링 사이클 | **Selected** |

**Selected**: **Option C — Pragmatic**

**Rationale**:
- **A 탈락** — react가 도는 한 산출은 LLM 종합문이다. 후처리로 `[… 검색결과]` 껍데기만 씌우면 "분석 혼입"이 해결되지 않을 뿐 아니라 분석문이 근거로 위장되어 하류 노드를 더 오염시킨다.
- **B 탈락** — generator 계열 tool_id 하드코딩 분기(`workflow_compiler.py:399-445`) 리팩토링은 Plan §2.2에서 명시적으로 Out of Scope다. `compile()`이 이미 300줄을 넘는 상태라 동시 변경 시 회귀 표면이 급증한다. `generate` 카테고리 도입과 함께 별도 사이클로 미룬다.
- **C 선택** — search / deep_search 두 팩토리가 이미 확립한 "카테고리 → 전용 노드" 패턴을 한 칸 확장할 뿐이다. 기존 확장점(`SupervisorHooks`, `MiddlewareBuilder`, optional ctor dep)을 그대로 쓰므로 코어 수정이 최소다.

### 2.1 Component Diagram

```
                        ┌──────────────────────────────┐
   AdminToolsPage ─────▶│ PATCH /tool-catalog/{id}     │
   (category, limit)    │  → UpdateToolCatalogMetaUC   │
                        └──────────────┬───────────────┘
                                       ▼
                        ┌──────────────────────────────┐
   SyncMcpToolsUC ─────▶│  tool_catalog                │
   (category 미포함 SET) │  + category                  │
                        │  + max_tool_calls            │
                        └──────────────┬───────────────┘
                                       │ compile()당 1회 배치 조회
                                       ▼
   ┌────────────────────────────────────────────────────────────┐
   │  WorkflowCompiler._resolve_category(worker_def)            │
   │    agent_tool.category → tool_catalog.category             │
   │      → TOOL_REGISTRY → "action"                            │
   └───────┬──────────────┬──────────────┬──────────────┬───────┘
           ▼              ▼              ▼              ▼
      "search"       "collect"      "analysis"       "action"
           │              │              │              │
   search_pipeline  collect_pipeline  analysis    create_agent(react)
   (rewrite→search   (args 1회→호출     _node       + ToolCallLimit
    →validate        1회→조건부 압축)               (run_limit=N,
    →compress)                                       continue)
           │              │                              │
           └──────────────┴──────────────┐               │ wiki 분기는
                                         ▼               │ 미들웨어 미주입
                    format_search_result(worker_id, ...) │ (기존 유지)
                                         │               │
                                         ▼               ▼
                    is_search_result() == True    AIMessage(name=...)
                                         │               │
                                         └───────┬───────┘
                                                 ▼
                      analysis_node / final_answer_node / quality_gate
```

### 2.2 Data Flow

**collect 노드 내부 (신규)**

```
state["messages"] + worker_task
   │
   ▼ ① 인자 생성 (LLM 1회, structured output)
   │    입력: datetime + user_context + worker_context 블록
   │          + 도구 args_schema(JSON Schema) + 대화 맥락
   │    출력: CollectArguments{ arguments: dict, grounded: bool, missing: str }
   │
   ▼ ② 도메인 검증 (LLM 호출 없음)
   │    ToolArgumentPolicy.find_placeholder(arguments)
   │    grounded=False 또는 placeholder 발견 → ④-b 로 분기
   │
   ▼ ③ 도구 호출 (정확히 1회)
   │    tool.ainvoke(arguments) — 예외는 잡아 실패 문자열로 전환(그래프 비중단)
   │
   ▼ ④-a 조건부 압축 (LLM 0~1회)
   │    len(result) > threshold 일 때만 compress
   │ ④-b 근거 부족 경로 — 도구 미호출, 안내 문구를 본문으로
   │
   ▼ ⑤ 규약 포장
        AIMessage(content=format_search_result(worker_id, body), name=worker_id)
```

**react 워커 (미분류) — 변경점만**

```
create_agent(model, tools, middleware=[*plan.instantiate(), ToolCallLimitMiddleware(...)])
                                                             └─ run_limit = 도구별 or 기본 2
                                                                exit_behavior = "continue"
   → 상한 도달 시: 초과 도구 호출만 차단된 ToolMessage 반환
   → 모델은 그때까지 수집한 내용으로 최종 답변 작성 (응답 유실 없음)
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `collect_pipeline` | `search_pipeline.format_search_result` | 근거 메시지 규약 재사용 (D2 단일 출처) |
| `collect_pipeline` | `ToolArgumentPolicy` (domain/mcp) | 플레이스홀더 인자 차단 — 기존 정책 재사용 |
| `collect_pipeline` | `CollectPipelinePolicy` (domain/agent_builder) | 압축 임계치 등 순수 규칙 |
| `WorkflowCompiler` | `ToolCatalogRepositoryInterface` (신규 optional dep) | 카테고리·상한 배치 조회 |
| `WorkflowCompiler` | `MiddlewareBuilder.build_tool_call_budget()` | langchain 클래스 격리 (D8) |
| `WorkerRunCapHooks` | `SupervisorHooks` Protocol | 기존 훅 확장점 |
| `ToolCategoryPolicy` (domain/tool_catalog) | 없음 | 허용값·collect 적격성 판정 |

---

## 3. Data Model

### 3.1 Entity Definition

```python
# src/domain/tool_catalog/entity.py
@dataclass
class ToolCatalogEntry:
    id: str
    tool_id: str
    source: str
    name: str
    description: str
    mcp_server_id: str | None = None
    requires_env: list[str] = field(default_factory=list)
    is_active: bool = True
    is_builtin: bool = False
    # mcp-tool-category-routing §3.1 (FR-01/FR-02):
    # 워커 노드 종류를 결정하는 분류. None = 미분류 → 기존 react 경로 (FR-14).
    category: str | None = None
    # 워커 1회 실행당 도구 호출 상한. None = 정책 기본값(2회).
    max_tool_calls: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
```

```python
# src/domain/tool_catalog/policies.py (추가)
class ToolCategoryPolicy:
    """도구 카테고리 도메인 규칙 (mcp-tool-category-routing §3.1)."""

    SEARCH = "search"
    COLLECT = "collect"
    ANALYSIS = "analysis"
    ACTION = "action"
    ALLOWED = frozenset({SEARCH, COLLECT, ANALYSIS, ACTION})

    @classmethod
    def validate(cls, category: str | None) -> None:
        """None(미분류)은 허용. 그 외 허용값 밖이면 ValueError."""

    @classmethod
    def assert_assignable(cls, category: str | None, tool_id: str) -> None:
        """§5 D-04: collect는 단일 도구 참조(mcp:{srv}:{tool} 또는 내부 도구)에만
        지정할 수 있다. 서버 단위 레거시(mcp_{srv})는 도구가 여럿이라 '1회 호출'이
        정의되지 않으므로 거부한다."""
```

```python
# src/domain/agent_builder/policies.py (추가)
class ToolCallBudgetPolicy:
    """react 워커의 도구 호출 예산 (mcp-tool-category-routing §5 D-05)."""

    DEFAULT_RUN_LIMIT = 2   # 1차 호출 + ToolArgumentPolicy 차단 후 자가교정 1회
    MIN_RUN_LIMIT = 1
    MAX_RUN_LIMIT = 20

    @classmethod
    def resolve(cls, max_tool_calls: int | None) -> int:
        """카탈로그 값이 없거나 범위 밖이면 기본값으로 클램프."""
```

```python
# src/domain/agent_builder/policies.py (추가)
class CollectPipelinePolicy:
    """collect 노드 도메인 규칙 — LLM/도구 호출 없는 순수 규칙."""

    DEFAULT_COMPRESS_THRESHOLD = 4000   # SearchPipelinePolicy와 동일 기준
    TOOL_CALLS_PER_RUN = 1              # 단일샷 계약 (불변)

    def needs_compression(self, text: str) -> bool: ...
```

### 3.2 Entity Relationships

```
[mcp_server_registry] 1 ──── N [tool_catalog] ────┐
                                    │ tool_id     │ category / max_tool_calls
                                    │             │  = 도구 단위 기본값
                                    ▼             │
                              [agent_tool] ───────┘
                                category         = 에이전트별 오버라이드 (V019, 우선)
```

우선순위: `agent_tool.category` **>** `tool_catalog.category` **>** `TOOL_REGISTRY.category` **>** `"action"`

### 3.3 Database Schema

```sql
-- db/migration/V069__add_category_to_tool_catalog.sql
ALTER TABLE tool_catalog
    ADD COLUMN category VARCHAR(20) NULL DEFAULT NULL
        COMMENT '워커 노드 분류(search/collect/analysis/action). NULL=미분류 → react 기본 경로',
    ADD COLUMN max_tool_calls INT NULL DEFAULT NULL
        COMMENT '워커 1회 실행당 도구 호출 상한. NULL=정책 기본값(2회)';

ALTER TABLE tool_catalog
    COMMENT = '시스템에 등록된 도구 카탈로그(내부 도구 + MCP 서버 도구)';
```

> **DDL 규칙**: `idt/CLAUDE.md` §3 — ALTER ADD 에도 컬럼 COMMENT 필수. `tests/db/test_migration_ddl_comments.py`가 V054 이후 파일을 검사한다. SQLAlchemy 모델에도 `comment=` 를 동일하게 반영한다.

**백필 없음** — 기존 행은 전부 NULL로 남는다 (Plan §2.2, FR-14).

---

## 4. API Specification

### 4.1 Endpoint List

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/tool-catalog` | 도구 목록 (응답에 `category`, `max_tool_calls` 추가) | Required |
| PATCH | `/tool-catalog/metadata` | 카테고리·호출 상한 수정 (신규, tool_id는 body — D-13) | Admin |

> 기존 `GET /tool-catalog`은 **필드 추가만** 하므로 기존 소비자(`ToolPickerModal`, `ToolsStep`, `AgentBuilderPage`)는 무영향이다.

### 4.2 Detailed Specification

#### `PATCH /tool-catalog/metadata`

> **module-4 개정 (D-13)**: 설계 원안은 `PATCH /tool-catalog/{tool_id}/metadata`였으나
> body 방식으로 바꿨다. 카탈로그 `tool_id`(`mcp:{uuid}:{tool}`)는 콜론과 임의
> 도구명을 포함해 path 세그먼트로 부적합하며, 기존 `PATCH /tool-catalog/builtin`이
> 같은 이유로 이미 body 방식을 쓴다(`tool_catalog_router.py:47` 주석). 한 리소스에
> 두 가지 주소 규약이 공존하는 것을 피한다.

**Request:**
```json
{
  "tool_id": "mcp:3f2a...:scrape",
  "category": "collect",
  "max_tool_calls": 2
}
```

- `category`: `"search" | "collect" | "analysis" | "action" | null` — `null`은 미분류로 되돌린다.
- `maxToolCalls`: `1 ~ 20` 정수 또는 `null`(기본값 사용).
- 두 필드 모두 선택적. 생략한 필드는 변경하지 않는다.

**Response (200 OK):**
```json
{
  "tool_id": "mcp:3f2a...:scrape",
  "category": "collect",
  "max_tool_calls": 2
}
```

> 응답 필드는 snake_case다 — 기존 `SetBuiltinResponse`와 동일 관례.
> 목록 조회(`GET /tool-catalog`)가 나머지 도구 정보를 이미 제공하므로
> 수정 응답은 변경된 필드만 돌려준다.

**Error Responses:**

| Code | 조건 | 응답 |
|------|------|------|
| 400 | `category`가 허용값 밖 | `ToolCategoryPolicy.validate` ValueError 메시지 |
| 400 | 서버 단위 레거시 `mcp_{srv}` 도구에 `collect` 지정 | "collect는 단일 도구에만 지정할 수 있습니다" |
| 400 | `max_tool_calls` 범위 밖 | 범위 안내 |
| 404 | `tool_id` 미존재 | `LookupError` → 404 (도메인 오류 `ValueError` → 400과 구분) |

---

## 5. Key Design Decisions

| ID | 결정 | 대안 | 근거 |
|----|------|------|------|
| **D-01** | 카테고리는 `tool_catalog` 컬럼에 저장, `agent_tool.category`는 에이전트별 오버라이드로 존치 | agent_tool만 사용 / 컴파일 시 휴리스틱 | 도구 단위로 한 번 정리하면 모든 에이전트에 적용. 기존 우선순위 계약(`_resolve_category:845`)을 깨지 않고 한 단계만 삽입 |
| **D-02** | sync는 `category`·`max_tool_calls`를 **SET 절에 넣지 않는다** | 별도 보존 플래그 | `tool_catalog_repository.py:50-61`이 이미 `is_builtin`에 대해 같은 계약을 쓴다. 코드 추가가 아니라 "추가하지 않음"으로 성립 |
| **D-03** | collect는 `collect_pipeline.py` 신규 노드. search 노드를 재사용하지 않는다 | search 노드 + 인자 매핑 어댑터 | `search_pipeline._safe_search:242`가 `{"query": ...}` 하드코딩. 더 근본적으로 rewrite 단계(질문→검색어)가 스크랩엔 무의미하며 URL 환각을 유발한다 |
| **D-04** | collect는 **단일 도구 워커에만** 허용. 서버 단위 `mcp_{srv}`는 지정 거부 → react 유지 | 서버 단위도 첫 도구로 collect | 서버 단위 워커는 `create_all_async`가 도구 전체를 바인딩(`tool_factory.py:225`)하므로 "도구 1회 호출"이 정의되지 않는다. 정책 레벨에서 거부해 조용한 오동작을 막는다 |
| **D-05** | react 상한은 langchain 내장 `ToolCallLimitMiddleware(run_limit=N, exit_behavior="continue")` | 커스텀 `wrap_tool_call` 미들웨어 | 동일 기능이 이미 존재. `continue`는 초과 도구만 차단하고 모델이 수집분으로 답변을 마무리해 응답 유실이 없다 |
| **D-06** | **wiki 분기(`workflow_compiler.py:556`)에는 상한 미들웨어를 주입하지 않는다** | 전 react 분기 일괄 적용 | 폴더 모드는 지도→`wiki_list`→`wiki_read`로 최소 2회 호출하는 확립된 워크플로우다(D6 계승). 기본 상한 2회에 정확히 걸쳐 회귀 위험이 크다. 사용자 결정: 기존 워크플로우 유지 |
| **D-07** | FR-11은 신규 `WorkerRunCapHooks`가 `skip_workers`로 구현. supervisor 코어 미수정 | supervisor에 카운터 직접 추가 | `visualization_done → skip_workers` 선례(`supervisor_hooks.py:110`)와 동형. `next_worker in skipped → __end__`(`supervisor_nodes.py:307`) 기존 동작을 그대로 둔다 — 종료해도 `route_to_worker_or_final`이 `final_answer`로 우회해 답변은 보장된다 |
| **D-12** (module-3 개정) | FR-11 상한 대상을 **collect 워커 한정**으로 좁힌다. search 워커는 제외 | 설계 원안대로 search+collect 모두 | search는 `TOOL_REGISTRY`가 이미 `category="search"`로 분류하므로 관리자가 아무것도 지정하지 않아도 상한이 걸린다 → category NULL 무변화 계약(FR-14)의 취지가 기존 검색 에이전트에서 깨진다. 관찰된 증상(스크랩 4~5회)은 collect만으로 해소되며, search 재라우팅은 `quality_gate` 재시도·다주제 질의와 얽혀 있어 건드리면 회귀 위험만 크다. 사용자 결정 |
| **D-08** | `ToolCatalogRepositoryInterface`는 `WorkflowCompiler`의 **optional** ctor dep. `None`이면 카탈로그 조회 생략 | 필수 의존 | `_middleware_provider` / `_wiki_toc_provider` 선례. 미주입 시 기존 동작 완전 보존 → 기존 테스트 무회귀 |
| **D-09** | 카탈로그는 `compile()`당 **1회 배치 조회**. 워커별 조회 금지 | 워커마다 `find_by_tool_id` | N+1 방지 (Plan §5 리스크) |
| **D-10** | collect 인자 생성 실패·차단은 예외가 아니라 **근거 부족 메시지**로 graceful degrade | 예외 전파 | search 파이프라인의 "모든 LLM 단계 graceful fallback — 그래프 비중단" 원칙(§3 실패 분기 매트릭스) 계승 |
| **D-11** | langchain 미들웨어 클래스 참조는 `MiddlewareBuilder`에 추가하는 팩토리 메서드에 가둔다 | compiler에서 직접 import | D8 격리 계약(langchain v1 클래스 참조는 본 모듈에만 존재) 유지 |

---

## 6. Error Handling

### 6.1 실패 분기 매트릭스 (collect 노드)

| # | 실패 지점 | 감지 | 처리 | 도구 호출 | 산출 |
|---|-----------|------|------|:--------:|------|
| 1 | 인자 생성 LLM 예외 | `except Exception` | warning 로그 → 근거 부족 경로 | 0회 | `format_search_result(worker_id, 근거부족안내)` |
| 2 | `grounded=False` (맥락에 대상 없음) | 구조화 출력 필드 | 근거 부족 경로 + `missing` 사유 본문에 포함 | 0회 | 동일 |
| 3 | 플레이스홀더 인자 (`example.com` 등) | `ToolArgumentPolicy.find_placeholder` | 차단. `build_blocked_message()` 본문 사용 | 0회 | 동일 |
| 4 | 도구 `args_schema` 부재 | `getattr(tool, "args_schema", None) is None` | warning + 근거 부족 경로 (추측 인자 금지) | 0회 | 동일 |
| 5 | 도구 호출 예외 | `except Exception` | error 로그(스택 포함) → 실패 문자열 | 1회(실패) | `format_search_result(worker_id, "수집 실패: ...")` |
| 6 | 압축 LLM 예외/빈 응답 | `except` / 빈 문자열 | 원본 유지 | 1회 | 원본 본문 |

**핵심 계약**: 어떤 분기에서도 예외를 그래프로 전파하지 않으며, 항상 `is_search_result()` 판정을 통과하는 AIMessage 1개를 반환한다.

### 6.2 상한 도달 처리

| 상황 | 감지 | 처리 |
|------|------|------|
| react 워커 tool-call 상한 도달 | `ToolCallLimitMiddleware` (`exit_behavior="continue"`) | 초과 도구 호출만 차단된 ToolMessage → 모델이 수집분으로 답변 완성 |
| supervisor가 상한 소진 워커 재선택 | `WorkerRunCapHooks.skip_workers` + 프롬프트 "스킵된 워커(사용 불가)" | `next_worker = "__end__"` → `route_to_worker_or_final`이 `final_answer`로 우회 |

### 6.3 관측 (FR-12)

| 이벤트 | 로그 키 | run step 반영 |
|--------|---------|---------------|
| collect 실행 | `collect_node executing` (worker_id, grounded, blocked, compressed, len) | `STEP_OUTPUT_SUMMARY_KEY` |
| 인자 차단 | `collect_node argument blocked` (worker_id, blocked_value) | summary에 `blocked=true` |
| 카테고리 해석 | `worker category resolved` (worker_id, category, source) | — |
| 상한 주입 | `tool call budget applied` (worker_id, run_limit) | — |

---

## 7. Security Considerations

- [x] **인자 환각 차단** — 기존 `ToolArgumentPolicy`를 collect 경로에도 적용. 워커가 지어낸 예시 URL이 MCP 서버로 나가지 않는다.
- [x] **호출 폭주 억제** — react 상한 + 워커 실행 상한으로 외부 MCP 서버에 대한 의도치 않은 반복 요청을 줄인다.
- [x] **권한 경계 불변** — 이 사이클은 도구 실행 권한/인증 경로를 건드리지 않는다. `auth_ctx` 전달 계약 그대로.
- [ ] **PATCH 엔드포인트 권한** — 카탈로그 메타 수정은 관리자 전용. 기존 `SetBuiltinUseCase` 라우터의 권한 데코레이터와 동일 수준으로 맞춘다.
- [x] **입력 검증** — `ToolCategoryPolicy.validate` / 범위 클램프로 임의 문자열·음수가 DB에 들어가지 않는다.

---

## 8. Test Plan

> Do 단계에서 코드와 테스트를 **1세트**로 작성한다. Check 단계는 실행만 한다.

### 8.1 Test Scope

| Type | Target | Tool | Phase |
|------|--------|------|-------|
| L0: Unit (domain) | `ToolCategoryPolicy`, `ToolCallBudgetPolicy`, `CollectPipelinePolicy` | pytest | Do |
| L0: Unit (application) | `collect_pipeline` 실패 분기 6종, `_resolve_category` 우선순위, `WorkerRunCapHooks` | pytest + fake LLM/tool | Do |
| L1: API | `GET /tool-catalog` 필드 추가, `PATCH .../metadata` 정상·400·404 | pytest + httpx | Do |
| L1: DB | V069 DDL COMMENT, sync 재실행 후 category 보존 | pytest | Do |
| L2: UI | AdminToolsPage 카테고리 셀렉트·상한 입력·저장 | Vitest + RTL + MSW | Do |
| L3: 통합 | 컴파일된 그래프에서 collect 워커 1회 호출 + 하류 인식 | pytest (fake tool 호출 카운터) | Do |
| **회귀** | category NULL 경로가 변경 전과 동일 | 기존 `tests/application/agent_builder/` 전량 | Do/Check |

### 8.2 L0/L1 핵심 시나리오

| # | 대상 | 시나리오 | 기대 |
|---|------|----------|------|
| 1 | `_resolve_category` | agent_tool.category="search", catalog="collect" | `"search"` (오버라이드 우선) |
| 2 | `_resolve_category` | agent_tool NULL, catalog="collect" | `"collect"` |
| 3 | `_resolve_category` | 둘 다 NULL, MCP tool_id | `"action"` (현행 동일) |
| 4 | `_resolve_category` | 카탈로그 repo 미주입(None) | 현행과 동일 결과 (FR-14) |
| 5 | `compile` | catalog category="collect" | 워커 노드가 `create_agent` 아닌 collect 노드 |
| 6 | collect 노드 | 정상 인자 생성 | `tool.ainvoke` **정확히 1회**, LLM 1회 |
| 7 | collect 노드 | 결과 길이 < 임계치 | 압축 LLM **호출 안 함**, 원본 보존 |
| 8 | collect 노드 | 결과 길이 > 임계치 | 압축 LLM 1회 |
| 9 | collect 노드 | `grounded=False` | 도구 호출 **0회**, 규약 메시지 반환 |
| 10 | collect 노드 | 인자에 `https://example.com/x` | 도구 호출 **0회**, `BLOCKED_PREFIX` 본문 |
| 11 | collect 노드 | `args_schema` 없는 도구 | 도구 호출 **0회**, warning |
| 12 | collect 노드 | `tool.ainvoke` 예외 | 예외 전파 없음, "수집 실패" 본문, `is_search_result()` True |
| 13 | collect 산출 | 모든 분기 | `is_search_result(msg) is True` |
| 14 | react 분기 | catalog max_tool_calls=3 | 미들웨어 `run_limit=3` |
| 15 | react 분기 | catalog 값 없음 | `run_limit=2` (기본) |
| 16 | **wiki 분기** | `wiki_read` + 폴더 모드 | 상한 미들웨어가 **주입되지 않음** (D-06) |
| 17 | `WorkerRunCapHooks` | collect 워커 결과 존재 | `skip_workers`에 해당 worker_id 포함 |
| 18 | `WorkerRunCapHooks` | 결과 없음 | 빈 리스트 (기존 훅과 동일) |
| 19 | `ToolCategoryPolicy` | `assert_assignable("collect", "mcp_srv1")` | ValueError (D-04) |
| 20 | `ToolCategoryPolicy` | `assert_assignable("collect", "mcp:uuid:scrape")` | 통과 |
| 21 | sync | category 지정 후 `SyncMcpToolsUseCase` 재실행 | category 보존 (FR-03) |
| 22 | DDL | V069 | 테이블·전 컬럼 COMMENT 존재 |

### 8.3 L2: UI 시나리오

| # | Page | Action | Expected Result |
|---|------|--------|-----------------|
| 1 | AdminToolsPage | 목록 로드 | 도구별 카테고리 배지 + 상한 값 표시, 미분류는 "미분류" |
| 2 | AdminToolsPage | 카테고리 셀렉트 변경 → 저장 | PATCH 호출, 성공 토스트, 목록 갱신 |
| 3 | AdminToolsPage | 서버 단위 도구에 collect 선택 | 400 응답 → 에러 메시지 노출 (D-04) |
| 4 | AdminToolsPage | 상한에 범위 밖 값 | 클라이언트 검증 메시지 |

### 8.4 L3: 통합 시나리오

| # | 시나리오 | 단계 | 성공 기준 |
|---|----------|------|-----------|
| 1 | collect 단일샷 | catalog에 collect 지정 → compile → 그래프 1회 실행 | fake tool 호출 카운터 == 1 |
| 2 | 하류 인식 | collect 산출 후 analysis 노드 진입 | analysis가 collect 산출을 근거 블록으로 소비 |
| 3 | 무회귀 | category 전부 NULL인 기존 워크플로우 | 변경 전 스냅샷과 동일한 노드 구성 |

### 8.5 Seed Data Requirements

| Entity | Minimum Count | Key Fields Required |
|--------|:------------:|---------------------|
| `tool_catalog` (mcp) | 3 | 단일 도구형 2 (category NULL 1 / collect 1), 서버 단위형 1 |
| `mcp_server_registry` | 1 | `is_active=true` |

---

## 9. Clean Architecture

### 9.1 Layer Structure

| Layer | 책임 | 이 사이클의 산출물 |
|-------|------|-------------------|
| **domain** | 순수 규칙 | `ToolCategoryPolicy`, `ToolCallBudgetPolicy`, `CollectPipelinePolicy`, `ToolCatalogEntry` 필드 |
| **application** | 흐름 제어 | `collect_pipeline.py`, `worker_run_cap_hooks.py`, `workflow_compiler` 배선, `UpdateToolCatalogMetadataUseCase` |
| **infrastructure** | 외부 연동 | `ToolCatalogModel` 컬럼, 리포지토리, `MiddlewareBuilder.build_tool_call_budget` |
| **interfaces** | HTTP 경계 | `ToolCatalogMetadataRequest/Response`, PATCH 라우터 |

### 9.2 Dependency Rules

```
interfaces ──→ application ──→ domain ←── infrastructure
                    │                          ▲
                    └──────────────────────────┘
   domain은 langchain·DB·HTTP를 절대 참조하지 않는다.
```

**검증 포인트**:
- `CollectPipelinePolicy` / `ToolCallBudgetPolicy` / `ToolCategoryPolicy` — import 문에 외부 패키지 0개
- `collect_pipeline.py`는 `langchain_core.messages`만 사용 (search_pipeline과 동일 수준)
- `ToolCallLimitMiddleware` 참조는 `infrastructure`가 아닌 `application/middleware/middleware_builder.py` — 기존 D8 격리 지점을 그대로 따른다(이 모듈이 langchain 유일 접점이라는 계약 유지)

### 9.3 File Import Rules

| From | Can Import | Cannot Import |
|------|-----------|---------------|
| `collect_pipeline` | domain policies, `search_pipeline.format_search_result`, `langchain_core.messages` | infrastructure, `langchain.agents` |
| `workflow_compiler` | application, domain, `ToolCatalogRepositoryInterface`(domain) | 리포지토리 구현체 직접 참조 |
| domain policies | 표준 라이브러리만 | 전부 |

### 9.4 This Feature's Layer Assignment

| Component | Layer | Location |
|-----------|-------|----------|
| `ToolCategoryPolicy` | domain | `src/domain/tool_catalog/policies.py` |
| `ToolCallBudgetPolicy`, `CollectPipelinePolicy` | domain | `src/domain/agent_builder/policies.py` |
| `ToolCatalogEntry` 필드 | domain | `src/domain/tool_catalog/entity.py` |
| `create_collect_node` | application | `src/application/agent_builder/collect_pipeline.py` |
| `WorkerRunCapHooks` | application | `src/application/agent_builder/worker_run_cap_hooks.py` |
| `UpdateToolCatalogMetadataUseCase` | application | `src/application/tool_catalog/update_metadata_use_case.py` |
| `build_tool_call_budget` | application | `src/application/middleware/middleware_builder.py` |
| `ToolCatalogModel` 컬럼 | infrastructure | `src/infrastructure/tool_catalog/models.py` |
| PATCH 라우터·스키마 | interfaces | `src/api/routes/tool_catalog_router.py` |
| `AdminToolsPage` 편집 UI | presentation (front) | `idt_front/src/pages/AdminToolsPage/` |

---

## 10. Coding Convention Reference

### 10.1 Naming Conventions

기존 프로젝트 규칙을 그대로 따른다.

| 대상 | 규칙 | 이 사이클 예시 |
|------|------|----------------|
| 노드 팩토리 | `create_{kind}_node` | `create_collect_node` |
| 도메인 정책 | `{Subject}Policy` | `ToolCategoryPolicy` |
| 훅 클래스 | `{Purpose}Hooks` | `WorkerRunCapHooks` |
| 유스케이스 | `{Verb}{Subject}UseCase` | `UpdateToolCatalogMetadataUseCase` |
| 마이그레이션 | `V{NNN}__{verb}_{subject}.sql` | `V069__add_category_to_tool_catalog.sql` |
| 프론트 타입 | `as const` 상수는 `src/types/*.ts` | 컴포넌트 파일에서 런타임 상수 export 금지 |

### 10.2 Import Order

Python: 표준 → 서드파티 → `src.domain` → `src.application` → `src.infrastructure` (기존 파일 관례 준수)

### 10.3 Environment Variables

**신규 없음.** 상한 기본값·압축 임계치는 도메인 정책 상수로 둔다 (config 하드코딩 금지 규칙은 "설정값"에 대한 것이며, 도메인 규칙 상수는 정책 클래스가 단일 출처 — `SearchPipelinePolicy.DEFAULT_COMPRESS_THRESHOLD` 선례).

### 10.4 This Feature's Conventions

| 항목 | 적용 |
|------|------|
| 주석 | `# Design Ref: mcp-tool-category-routing §{절} — {근거}` 형식으로 핵심 결정에 부착 |
| 에러 처리 | 예외 삼킴 금지. `logger.error(..., exception=e)`로 스택 보존 후 graceful 값 반환 |
| 함수 길이 | 40줄 이하. collect 노드는 단계별 헬퍼로 분해 (`_build_arguments` / `_invoke_once` / `_maybe_compress`) |
| 테스트 | Red → Green. 각 모듈 테스트 파일은 구현 파일과 1:1 |

---

## 11. Implementation Guide

### 11.1 File Structure

```
idt/
├── db/migration/
│   └── V069__add_category_to_tool_catalog.sql              [신규]
├── src/
│   ├── domain/
│   │   ├── tool_catalog/
│   │   │   ├── entity.py                                   [수정] +2 필드
│   │   │   ├── interfaces.py                               [수정] +update_metadata
│   │   │   └── policies.py                                 [수정] +ToolCategoryPolicy
│   │   └── agent_builder/
│   │       └── policies.py                                 [수정] +ToolCallBudgetPolicy
│   │                                                                +CollectPipelinePolicy
│   ├── application/
│   │   ├── agent_builder/
│   │   │   ├── collect_pipeline.py                         [신규]
│   │   │   ├── worker_run_cap_hooks.py                     [신규]
│   │   │   └── workflow_compiler.py                        [수정]
│   │   ├── middleware/
│   │   │   └── middleware_builder.py                       [수정] +build_tool_call_budget
│   │   └── tool_catalog/
│   │       ├── update_metadata_use_case.py                 [신규]
│   │       ├── schemas.py                                  [수정]
│   │       ├── sync_mcp_tools_use_case.py                  [수정] 보존 계약 명시 주석
│   │       └── sync_internal_tools_use_case.py             [수정] 동일
│   ├── infrastructure/tool_catalog/
│   │   ├── models.py                                       [수정] +2 컬럼(comment=)
│   │   └── tool_catalog_repository.py                      [수정] +update_metadata
│   └── api/
│       ├── routes/tool_catalog_router.py                   [수정] +PATCH
│       └── main.py                                         [수정] compiler에 repo 주입
└── tests/
    ├── domain/tool_catalog/test_tool_category_policy.py    [신규]
    ├── domain/agent_builder/test_tool_call_budget_policy.py[신규]
    ├── application/agent_builder/test_collect_pipeline.py  [신규]
    ├── application/agent_builder/test_worker_run_cap_hooks.py [신규]
    ├── application/agent_builder/test_workflow_compiler_collect.py [신규]
    ├── application/tool_catalog/test_update_metadata.py    [신규]
    ├── application/tool_catalog/test_sync_preserves_category.py [신규]
    └── db/test_migration_ddl_comments.py                   [기존 — V069 자동 검사]

idt_front/
├── src/types/toolCatalog.ts                                [수정] +category, maxToolCalls
├── src/services/toolCatalog.ts                             [수정] +updateMetadata
├── src/hooks/useToolCatalog.ts                             [수정] +useUpdateToolMetadata
├── src/constants/api.ts                                    [수정] +엔드포인트
└── src/pages/AdminToolsPage/                               [수정] 편집 UI + 테스트
```

### 11.2 Implementation Order

1. [ ] **M1** 도메인 정책 → 엔티티 → DDL → 모델 → 리포지토리 → sync 보존 테스트
2. [ ] **M2** `CollectPipelinePolicy` → `collect_pipeline.py` (실패 분기 6종 우선 테스트)
3. [ ] **M3** `_resolve_category` 확장 → collect 분기 → 상한 미들웨어(wiki 예외) → `WorkerRunCapHooks` → `main.py` 배선
4. [ ] **M4** API 스키마·라우터 → 프론트 타입·서비스·훅 → AdminToolsPage UI
5. [ ] 회귀 스위트 전량 실행 + `/verify-architecture` `/verify-logging` `/verify-tdd`

### 11.3 Session Guide

#### Module Map

| Module | Scope Key | Description | Estimated Turns |
|--------|-----------|-------------|:---------------:|
| 스키마·카탈로그 | `module-1` | V069 DDL, 엔티티/모델 2필드, `ToolCategoryPolicy`, 리포지토리 `update_metadata`, sync 보존 검증 | 25-30 |
| collect 노드 | `module-2` | `CollectPipelinePolicy` + `collect_pipeline.py` + 실패 분기 6종 테스트 | 35-40 |
| 컴파일러 배선 | `module-3` | `_resolve_category` 확장(배치 조회), collect 분기, `ToolCallBudgetPolicy` + 미들웨어 주입(wiki 예외), `WorkerRunCapHooks`, `main.py` 주입 | 40-45 |
| API·Admin UI | `module-4` | PATCH 엔드포인트 + 프론트 타입·서비스·훅·AdminToolsPage | 30-35 |

**의존 순서**: `module-1` → (`module-2` ∥ `module-3` 일부) → `module-3` → `module-4`
`module-3`의 collect 분기는 `module-2` 완료를 전제하지만, 카테고리 해석·상한 미들웨어 부분은 `module-1` 직후 착수 가능하다.

#### Recommended Session Plan

| Session | Phase | Scope | Turns |
|---------|-------|-------|:-----:|
| Session 1 | Plan + Design | 전체 | 완료 |
| Session 2 | Do | `--scope module-1` | 25-30 |
| Session 3 | Do | `--scope module-2` | 35-40 |
| Session 4 | Do | `--scope module-3` | 40-45 |
| Session 5 | Do | `--scope module-4` | 30-35 |
| Session 6 | Check + Report | 전체 | 30-40 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-09-03 | 최초 초안. Option C 선택, wiki 상한 예외(D-06)·서버단위 collect 거부(D-04) 반영 | 배상규 |
