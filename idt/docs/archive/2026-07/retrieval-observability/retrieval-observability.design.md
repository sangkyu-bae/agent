# Retrieval Observability Design Document

> **Summary**: 질문별 검색 근거 기록 — general_chat ai_run 배선 + 검색 실행 쿼리(rewrite 포함) 추적 + ai_retrieval_source 스키마 확장(V046) + 메시지 기준 조회 API
>
> **Project**: sangplusbot (idt)
> **Version**: 0.1
> **Author**: 배상규
> **Date**: 2026-07-09
> **Status**: Draft
> **Planning Doc**: [retrieval-observability.plan.md](../../01-plan/features/retrieval-observability.plan.md)

---

## 1. Overview

### 1.1 Design Goals

1. **general_chat 사각지대 제거**: 사용자 질문 대부분이 흐르는 general_chat 검색을 `ai_retrieval_source`에 영속화
2. **rewrite 쿼리 추적**: 검색 엔진에 실제 투입된 쿼리(재작성 포함)를 hit 단위로 기록 — "질문 → 재작성 쿼리 → 뽑힌 문서" 3단 연결
3. **분석 가능한 스키마**: BM25/벡터 개별 점수·검색 모드를 SQL로 필터/집계 가능하게 컬럼화
4. **기존 경로 무손상**: agent_run 경로의 기존 기록 동작·데이터·조회 API 하위호환 유지 (additive only)

### 1.2 Design Principles

- **기존 인프라 재사용**: `RunTracker` / `RunContext` / `ai_run` 라이프사이클을 그대로 사용 — 신규 테이블 없음
- **Best-effort**: 관측성 기록 실패는 WARNING 로그만, 채팅/검색 흐름을 절대 차단하지 않음 (AGENT-OBS-001 계약 유지)
- **Additive only**: 스키마·엔티티·시그니처 전부 nullable/optional 추가만. 기존 호출부 무변경으로 컴파일·동작
- **대화 메모리 정책 불변**: general_chat의 메시지 저장 시점·순서·요약 규칙을 바꾸지 않음 (deferred attach 방식, D2)

---

## 2. Architecture

### 2.1 전체 흐름 (general_chat 신규 배선)

```
GeneralChatUseCase.stream()
  ├─ CHAT_STARTED
  ├─ history 조회 / chart-edit 분기 (기존, run 없음)
  ├─ ★ _begin_observability()                        ← 신규 (D1)
  │    ├─ tracker.start_run(run_id, agent_id="general-chat",
  │    │                    user_message_id=None, ...)   ← D2/D3
  │    ├─ UsageCallback 생성                              ← D4
  │    └─ set_current_run_context(RunContext(...))
  ├─ tools = ChatToolBuilder.build(...)               ← tool에 tracker 주입됨 (§5)
  ├─ agent.astream_events(config={"callbacks":[callback]})  ← D4
  │    └─ InternalDocumentSearchTool._arun(query)
  │         ├─ single/multi_query/routed 검색
  │         └─ _format_results → tracker.record_retrieval(
  │              search_query, query_source, search_mode,
  │              bm25_score, vector_score, ...)        ← 신규 컬럼 (§3)
  ├─ _persist_messages() → user_message_id 반환        ← 반환값 추가
  ├─ ★ tracker.attach_user_message(run_id, user_message_id)  ← 신규 (D2)
  ├─ ★ tracker.complete_run(run_id, trace_id, run_url)
  ├─ ANSWER_COMPLETED / CHAT_DONE
  └─ (예외 시) ★ tracker.fail_run(run_id, e) → CHAT_FAILED
  └─ finally: reset_run_context(token)
```

조회:

```
GET /conversations/messages/{message_id}/retrievals
  → ai_run WHERE user_message_id = :id
  → ai_retrieval_source WHERE run_id IN (...)
  → search_query 기준 그룹핑 응답
```

### 2.2 Design Decisions

| ID | 결정 | 근거 |
|----|------|------|
| **D1** | run 시작 시점은 **chart-edit 분기 이후, tool build 직전** | chart-edit 경로는 검색이 없어 run이 무의미. 일반 경로만 관측. `start_run` 실패 시 degraded mode(기록 없이 진행) — agent 경로 `_begin_observability`와 동일 계약 |
| **D2** | user_message_id는 **deferred attach**: start_run 시 NULL → `_persist_messages` 후 `attach_user_message()` UPDATE | agent 경로의 "user message 선저장" 방식은 general_chat의 메시지 저장 시점을 바꿈(실패 시에도 user 메시지 영속화되는 동작 변화 = 대화 기록 정책 변경 소지). deferred attach는 기존 저장 시점·turn_index 계산을 그대로 보존. attach 시점엔 메시지 commit이 끝나 FK 락 이슈(Error 1205)도 없음 |
| **D3** | general_chat run의 `agent_id`는 sentinel 상수 **`"general-chat"`** | `ai_run.agent_id`는 NOT NULL이지만 FK 없음(V021 확인). 집계/필터에서 `agent_id='general-chat'`으로 구분 가능. 스키마 변경 불필요 |
| **D4** | `UsageCallback`을 생성해 RunContext에 넣고 **ReAct agent stream config에도 부착** | RunContext.callback이 필수 필드라 생성은 불가피. config 부착은 한 줄로 general_chat LLM 호출도 `ai_llm_call`에 기록되는 부수 이득(토큰/비용 SUM이 0이 아니게 됨). summarizer/chart LLM은 미부착(범위 밖) |
| **D5** | `search_query` = **검색 엔진에 실제 투입된 문자열** | 단일 검색: tool 입력 쿼리(ReAct LLM이 생성한 쿼리 — 사용자 원문과 다를 수 있으며 이것 자체가 1차 rewrite). 원문 질문은 `ai_run.user_message_id` 역참조로 확보(중복 저장 안 함) |
| **D6** | multi_query 귀속: **fused hit 단위 기록** + `search_query`=첫 기여 쿼리, `metadata_json.matched_queries`=전체 기여 쿼리 목록 | fused 결과가 실제로 LLM 컨텍스트에 들어간 것과 1:1. (query,hit) 쌍 단위 기록은 행 폭증 + rank 의미 이원화로 기각. 기여 쿼리 전체는 metadata에 보존되어 정보 손실 없음 |
| **D7** | 개별 점수는 `HybridSearchResult`의 기존 필드(`bm25_score/vector_score/bm25_rank/vector_rank/source`)를 **getattr best-effort**로 전달 | hybrid/multi_query 경로는 값 존재. `RoutedChunk`엔 없으므로 NULL — 기존 `_record_routed_retrieval`의 "RRF 점수 스케일 혼합 비교 금지" 원칙 유지 |
| **D8** | 조회 API는 **agent_run_router에 추가** (`/conversations/messages/{message_id}/retrievals`) | RunDetail 조회 인프라(repo/schemas/권한 패턴)와 같은 곳. 신규 라우터 파일 불필요 |
| **D9** | `search_mode` ∈ {hybrid, bm25_only, vector_only, routed} / `query_source` ∈ {original, multi_query} 직교 분리 | mode=엔진 실행 방식, source=쿼리 생성 방식. multi_query는 mode=hybrid + source=multi_query. routed는 mode=routed + source=original. 중복 의미 제거 |

---

## 3. Data Model — V046

### 3.1 Migration

```sql
-- V046__alter_ai_retrieval_source_add_query_context.sql
-- retrieval-observability D5~D7/D9: 검색 실행 쿼리·모드·개별 점수 기록.
-- 전 컬럼 nullable additive — 기존 데이터/기록 코드 하위호환.
ALTER TABLE ai_retrieval_source
    ADD COLUMN search_query  TEXT           NULL COMMENT '검색 엔진에 실제 투입된 쿼리(재작성 포함)',
    ADD COLUMN query_source  VARCHAR(20)    NULL COMMENT 'original | multi_query',
    ADD COLUMN search_mode   VARCHAR(20)    NULL COMMENT 'hybrid | bm25_only | vector_only | routed',
    ADD COLUMN bm25_score    DECIMAL(10, 6) NULL COMMENT 'RRF 병합 전 BM25 원점수',
    ADD COLUMN vector_score  DECIMAL(10, 6) NULL COMMENT 'RRF 병합 전 벡터 코사인 점수',
    ADD COLUMN bm25_rank     INT            NULL,
    ADD COLUMN vector_rank   INT            NULL,
    ADD COLUMN fusion_source VARCHAR(20)    NULL COMMENT 'both | bm25_only | vector_only';
```

- FK/인덱스 추가 없음 → collation(errno 3780) 이슈 해당 없음
- 조회는 기존 `idx_retrieval_run(run_id)` 경유(메시지 → run_id IN → retrieval)라 신규 인덱스 불필요

### 3.2 도메인 엔티티 (`src/domain/agent_run/entities.py`)

`RetrievalSource` dataclass에 동일 8필드를 `Optional[...] = None` 기본값으로 추가.
기존 생성 호출부(tracker, tavily_tool, 테스트)는 무변경으로 동작.

### 3.3 ORM 모델 & 매퍼

- `src/infrastructure/persistence/models/agent_run.py`: `AiRetrievalSourceModel`에 8컬럼 추가 (전부 nullable)
- `src/infrastructure/persistence/repositories/agent_run_repository.py`: `save_retrieval` / `find_retrievals` 매퍼에 필드 왕복 추가

---

## 4. Component Design

### 4.1 RunTracker 확장 (`src/application/agent_run/tracker.py`)

```python
async def record_retrieval(
    self,
    run_id: RunId,
    tool_call_id: Optional[str],
    collection_name: str,
    document_id: Optional[str] = None,
    chunk_id: Optional[str] = None,
    score: Optional[float] = None,
    rank_index: Optional[int] = None,
    content_preview: Optional[str] = None,
    metadata: Optional[dict] = None,
    # ── retrieval-observability 신규 (전부 optional — 하위호환) ──
    search_query: Optional[str] = None,
    query_source: Optional[str] = None,
    search_mode: Optional[str] = None,
    bm25_score: Optional[float] = None,
    vector_score: Optional[float] = None,
    bm25_rank: Optional[int] = None,
    vector_rank: Optional[int] = None,
    fusion_source: Optional[str] = None,
) -> None: ...

async def attach_user_message(self, run_id: RunId, user_message_id: int) -> None:
    """ai_run.user_message_id UPDATE — best-effort (D2).

    _persist_messages commit 이후 호출되므로 FK 락 경합 없음.
    실패는 warning 로그만 (질문-근거 연결만 끊길 뿐 근거 자체는 run_id로 남음).
    """
```

- `attach_user_message`용 repository 메서드 신설: `SqlAlchemyAgentRunRepository.attach_user_message(run_id, message_id)` — set-based UPDATE 1문
- 세션 정책: 기존 메서드와 동일하게 `session_factory`에서 자체 세션 open/commit (DB-001 §10.3)

### 4.2 InternalDocumentSearchTool (`src/application/rag_agent/tools.py`)

기록 지점 3곳에 신규 필드 전달. 검색 로직 자체는 무변경.

**(a) `_single_query_search` → `_format_results`**
`_format_results(results, search_query=query, query_source="original", search_mode=self.search_mode)`
— `search_mode`는 기존 필드값(hybrid/bm25_only/vector_only) 그대로.

**(b) `_multi_query_search` → `_format_results`** (D6)

```python
result = await self.multi_query_use_case.execute(...)
# chunk_id → 기여 쿼리 역맵 (additive 필드, §4.3)
hit_queries: dict[str, list[str]] = {}
for pq in (result.per_query_hits or []):
    for hid in pq.hit_ids:
        hit_queries.setdefault(hid, []).append(pq.query)
return await self._format_results(
    result.results,
    query_source="multi_query",
    search_mode="hybrid",
    hit_queries=hit_queries,          # hit별 search_query = matched[0]
    extra_metadata={"generated_queries": result.generated_queries},
)
```

**(c) `_format_results` 내부** — hit 루프에서:

```python
matched = hit_queries.get(hit.id, []) if hit_queries else []
await self.tracker.record_retrieval(
    ...,  # 기존 인자 유지
    search_query=(matched[0] if matched else search_query),
    query_source=query_source,
    search_mode=search_mode,
    bm25_score=getattr(hit, "bm25_score", None),      # D7
    vector_score=getattr(hit, "vector_score", None),
    bm25_rank=getattr(hit, "bm25_rank", None),
    vector_rank=getattr(hit, "vector_rank", None),
    fusion_source=getattr(hit, "source", None),
    metadata={**(dict(hit.metadata) if hit.metadata else {}),
              **({"matched_queries": matched} if matched else {}),
              **(extra_metadata or {})},
)
```

**(d) `_record_routed_retrieval`** — `search_query=query`(라우팅 입력), `query_source="original"`, `search_mode="routed"` 추가. 개별 점수는 NULL 유지(D7). 기존 metadata의 `"search": "routed"` 표기는 하위호환 위해 유지.

시그니처 변경은 `_format_results(self, results, *, search_query=None, query_source=None, search_mode=None, hit_queries=None, extra_metadata=None)` — 전부 keyword-optional이라 기존 테스트/호출 무손상.

### 4.3 MultiQueryResult additive 필드 (`src/domain/multi_query/schemas.py`)

```python
class PerQueryHits(BaseModel):
    query: str                 # 재작성 쿼리
    hit_ids: list[str]         # 이 쿼리가 반환한 hit id (병합 전)

class MultiQueryResult(BaseModel):
    ...                        # 기존 필드 무변경
    per_query_hits: list[PerQueryHits] | None = None   # 신규 (기본 None)
```

- `MultiQuerySearchUseCase.execute`: workflow state의 `generated_queries` × `per_query_results`(인덱스 정렬 — `asyncio.gather` 순서 보존)를 zip해 채움. workflow 자체는 무변경
- id만 담아 콘텐츠 중복 없음. 소비자는 tool 하나(하위호환: None이면 기존 동작)

### 4.4 GeneralChatUseCase (`src/application/general_chat/use_case.py`)

**생성자 추가 인자** (전부 optional — 미주입 시 관측성 완전 비활성, 기존 테스트 무변경):

```python
tracker: RunTracker | None = None,
```

**`_begin_observability(request, session_id_str)`** — agent 경로 `_begin_observability` 미러(D1):

```python
GENERAL_CHAT_AGENT_ID = "general-chat"   # D3 sentinel

run_id = RunId(str(uuid.uuid4()))
try:
    await self._tracker.start_run(
        run_id=run_id,
        conversation_id=session_id_str,
        user_id=request.user_id,
        agent_id=GENERAL_CHAT_AGENT_ID,
        agent_llm_model_id=self._llm_model.id,
        user_message_id=None,               # D2: deferred
        langgraph_thread_id=session_id_str,
    )
except RuntimeError:
    return None, None, None                 # degraded — 채팅은 계속
callback = UsageCallback(tracker=..., run_id=run_id,
                         user_id=request.user_id,
                         agent_id=GENERAL_CHAT_AGENT_ID, logger=...)
ctx_token = set_current_run_context(RunContext(run_id=run_id, ...))
return run_id, callback, ctx_token
```

**`stream()` 배선 지점**:

1. chart-edit 분기 이후(D1) `_begin_observability` 호출
2. `agent.astream_events({...}, version="v2", config={"callbacks": [callback]} if callback else None)` (D4)
3. `_persist_messages(...)` → **saved user message id 반환하도록 확장** (기존 반환 없음 → `int | None` 반환; 호출부 2곳)
4. 반환된 id로 `tracker.attach_user_message(run_id, user_message_id)` (run_id 있을 때만)
5. `TraceExtractor.extract()` → `tracker.complete_run(run_id, trace_id, run_url)` — 기존 `langsmith(project_name="general-chat")` 프로젝트에 trace가 남으므로 URL 연결됨
6. `except Exception` 블록에서 `tracker.fail_run(run_id, e)` / `CancelledError`에서도 동일
7. `finally`에서 `reset_run_context(ctx_token)` (auth_token reset 옆)

chart-edit 조기 반환 경로는 run을 열지 않음(D1) — user_message_id attach 대상 run이 없으므로 `_persist_messages` 반환값은 무시.

### 4.5 DI 배선 (`src/api/main.py`)

1. `RunTracker` 생성을 `create_agent_builder_factories()` 내부(L2097)에서 **모듈 수준 접근자 `get_run_tracker()`(lazy singleton)로 추출** — general_chat factory와 agent_builder factory가 동일 인스턴스 공유. RunTracker는 상태 없는 파사드(session_factory만 보유)라 공유 안전
2. `create_general_chat_use_case_factory()` (L1954):
   - `InternalDocumentSearchTool(...)` 생성 인자에 `tracker=get_run_tracker(), logger=app_logger, config=RunObservabilityConfig()` 추가 (L1978)
   - `GeneralChatUseCase(..., tracker=get_run_tracker())` 추가
3. **WS 경로 자동 커버**: `get_ws_general_chat_use_case` override도 동일 factory를 쓰므로(§main.py L3417 계열) HTTP SSE·WS 모두 배선됨 — override 지점이 분리돼 있으면 두 곳 모두 동일 factory 참조 확인

### 4.6 조회 API (D8)

**엔드포인트** (`src/api/routes/agent_run_router.py`):

```
GET /api/v1/conversations/messages/{message_id}/retrievals
```

**응답 스키마** (`src/interfaces/schemas/agent_run_response.py`):

```python
class RetrievalDto(BaseModel):
    ...  # 기존 필드 유지
    search_query: str | None = None      # 신규 8필드 반영 (RunDetail에도 동일 적용)
    query_source: str | None = None
    search_mode: str | None = None
    bm25_score: float | None = None
    vector_score: float | None = None
    bm25_rank: int | None = None
    vector_rank: int | None = None
    fusion_source: str | None = None

class QueryRetrievalGroup(BaseModel):
    search_query: str | None             # 재작성 쿼리 단위 그룹
    query_source: str | None
    search_mode: str | None
    sources: list[RetrievalDto]

class MessageRetrievalsResponse(BaseModel):
    message_id: int
    runs: list[MessageRunRetrievals]     # 보통 1개 (재시도 시 복수 가능)

class MessageRunRetrievals(BaseModel):
    run_id: str
    agent_id: str                        # "general-chat" | 실제 agent id
    langsmith_run_url: str | None
    groups: list[QueryRetrievalGroup]
```

**UseCase** (`src/application/agent_run/use_cases/get_message_retrievals_use_case.py` 신규):

1. `message_repo`(또는 직접 조회)로 `conversation_message.user_id` 확인 → 요청자 본인 아니고 admin 아니면 403 (기존 agent_run_router 권한 패턴 준수)
2. repo 신규 메서드 `find_runs_by_user_message(message_id) -> List[AgentRun]` (`idx` 없어도 user_message_id 조회는 저빈도 관리 조회라 풀스캔 아닌 FK 컬럼 조건 — 필요 시 후속 인덱스)
3. run별 `find_retrievals(run_id)` 재사용 → `search_query` 기준 그룹핑(순서: 그룹 내 rank_index)

**프론트 계약**: 신규 엔드포인트이므로 구현 시 `/api-contract-sync` 체크리스트 실행 (idt_front 타입 추가는 후속 UI 기능에서 소비)

---

## 5. Error Handling

| 상황 | 동작 |
|------|------|
| `start_run` 실패 | degraded mode — run_id/callback/ctx 없이 채팅 정상 진행 (agent 경로와 동일) |
| `record_retrieval` 실패 | hit별 WARNING 로그 후 다음 hit 진행 (기존 계약) |
| `attach_user_message` 실패 | WARNING만 — 근거는 run_id로 조회 가능, 질문 연결만 유실 |
| `complete_run`/`fail_run` 실패 | WARNING (기존 best-effort) |
| multi_query `per_query_hits` 미존재(None) | 귀속 없이 기존 방식 기록 (`search_query`=원 tool 입력) |
| 조회 API: 타인 메시지 | 403 / 존재하지 않는 메시지 404 / run 없음 → 빈 `runs: []` 200 |

로깅: 전 신규 로그에 `request_id` 전파, 예외는 `exception=` 포함 (LOG-001).

---

## 6. Test Plan (TDD — Red → Green)

| # | 테스트 파일 | 검증 |
|---|------------|------|
| 1 | `tests/application/agent_run/test_tracker_retrieval_context.py` | `record_retrieval` 신규 kwargs 저장 + 미전달 시 NULL(하위호환) |
| 2 | 〃 | `attach_user_message` UPDATE 성공 / 실패 시 WARNING·no-raise |
| 3 | `tests/application/multi_query/test_per_query_hits.py` | `MultiQueryResult.per_query_hits` — 쿼리↔hit_ids 정합(zip 순서) |
| 4 | `tests/application/rag_agent/test_tool_retrieval_context.py` | 단일 검색: search_query=tool 입력, query_source=original, 개별 점수 전달 |
| 5 | 〃 | multi_query: hit별 matched_queries·대표 쿼리 태깅(D6), generated_queries metadata |
| 6 | 〃 | routed: search_mode=routed, 개별 점수 NULL(D7) |
| 7 | `tests/application/general_chat/test_observability.py` | tracker 주입 시 start→attach→complete 시퀀스, ai_run.agent_id="general-chat" |
| 8 | 〃 | tracker 미주입 시 기존 동작 100% 동일(회귀), chart-edit 경로 run 미생성(D1) |
| 9 | 〃 | 예외 시 fail_run + CHAT_FAILED, start_run 실패 시 degraded 진행 |
| 10 | `tests/api/test_message_retrievals_api.py` | 응답 그룹핑·권한(본인/타인 403)·빈 결과 200 |
| 11 | 기존 스위트 | agent_run 경로 관측성 테스트 전체 통과 (회귀 없음) |

주의: Windows pytest 교차 실행 시 이벤트 루프 teardown 산발 실패 이력 — 모듈 격리 실행으로 검증.

---

## 7. Implementation Order

1. **V046 마이그레이션 + ORM 모델/매퍼** — 스키마 먼저 (테스트 1 Red)
2. **도메인 `RetrievalSource` 필드 + `RunTracker.record_retrieval` 확장 + `attach_user_message`** (테스트 1·2)
3. **`MultiQueryResult.per_query_hits`** (테스트 3)
4. **`InternalDocumentSearchTool` 기록 컨텍스트 전달** — single → multi_query → routed 순 (테스트 4~6)
5. **`GeneralChatUseCase` 관측성 배선** + `_persist_messages` 반환값 (테스트 7~9)
6. **main.py DI** — `get_run_tracker()` 추출 + general_chat factory 주입 (HTTP/WS 공용 확인)
7. **조회 API** — repo 메서드 → UseCase → router → 스키마 (테스트 10)
8. **RunDetail 응답에 신규 필드 반영** + 전체 회귀 (테스트 11) → `/pdca analyze retrieval-observability`

---

## 8. Impact & Risks

| 항목 | 영향 | 완화 |
|------|------|------|
| ai_retrieval_source 행 증가 (general_chat 유입) | 검색 1회당 top_k(기본 5)행 | 기존 run당 CASCADE 삭제 유지, 보존 정책은 후속 |
| `search_query` TEXT 중복 저장 (hit마다) | 스토리지 증가 | 쿼리는 짧음(수백 자). 정규화(쿼리 테이블 분리)는 과설계로 기각 |
| general_chat 응답 지연 | start_run INSERT 1회(≈수 ms) + hit별 best-effort INSERT | 기존 agent 경로에서 검증된 수준. record_retrieval은 스트리밍 완료 전 tool 실행 중 발생 |
| UsageCallback 부착(D4)으로 ai_llm_call에 general_chat 행 유입 | 사용량 집계 화면에 "general-chat" agent_id 등장 | 집계는 agent_id 비정규화 문자열 기반이라 오류 없음. 의도된 확장으로 문서화 |
| 기존 metadata_json 소비자 | matched_queries/generated_queries 키 추가 | JSON 키 추가는 소비자 무영향 (additive) |

**금지 준수**: 아키텍처/레이어 이동 없음, 대화 메모리 정책 불변(D2), Repository commit 금지 준수(tracker가 세션 소유), 하드코딩 없음(sentinel은 상수).
