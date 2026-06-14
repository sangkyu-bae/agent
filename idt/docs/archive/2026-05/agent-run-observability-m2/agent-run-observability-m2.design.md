# agent-run-observability-m2 Design Document

> **Summary**: M2 — `UsageCallback`에 LangChain `on_tool_*` 비동기 훅 3개를 추가하여 모든 BaseTool 호출을 자동 인터셉트. 신규 테이블/도메인 0건, callback-driven wiring 한 곳 변경.
>
> **Project**: sangplusbot (idt)
> **Version**: 0.1
> **Author**: 배상규
> **Date**: 2026-05-19
> **Status**: Draft
> **Planning Doc**: [agent-run-observability-m2.plan.md](../../01-plan/features/agent-run-observability-m2.plan.md)
> **Parent Design**: [agent-run-observability.design.md](./agent-run-observability.design.md) (M1)

---

## 1. Overview

### 1.1 Design Goals

- M1의 "**단일 진입점 인터셉트**" 패턴을 툴 호출로 확장 — 노드/워커/툴 어댑터 코드 변경 0
- 모든 LangChain `BaseTool.ainvoke()` 호출을 자동으로 `ai_tool_call` 테이블에 영속화
- 툴 내부 LLM 호출이 어느 툴에서 일어났는지 SQL JOIN 한 줄로 추적 (`ai_llm_call.tool_call_id` 자동 채움)
- MCP 툴 / 신규 등록 툴 wrapping 코드 불필요 (LangChain runnable 추상화 활용)
- best-effort 보장 — 관측성 실패가 사용자 응답 흐름을 차단하지 않음

### 1.2 Design Principles

- **단일 진입점 (Single Interception Point)**: 모든 툴 호출을 `UsageCallback` 한 곳에서 처리
- **CLAUDE.md Thin DDD**: domain 변경 0, application 헬퍼 1개 신규, infrastructure callback 1개 수정
- **LangChain 표준 활용**: `AsyncCallbackHandler.on_tool_start/end/error` 표준 hook 사용 (LangChain 0.3+)
- **best-effort isolation**: 관측성 코드의 어떤 실패도 LangGraph 실행을 막지 않음
- **Idempotent 매칭**: `_tool_starts: dict[lc_run_id, ...]` — start↔end 누락 시에도 leak 감지 가능

---

## 2. Architecture

### 2.1 Component Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│                     RunAgentUseCase.execute()                         │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │  graph.ainvoke(state, config={"callbacks": [usage_callback]}) │  │
│  └────────────────────────────────────────────────────────────────┘  │
└───────────────────────────────┬──────────────────────────────────────┘
                                │  LangChain Callback Manager 자동 전파
                                ▼
┌───────────────────────────────────────────────────────────────────────┐
│                       LangGraph StateGraph                             │
│                                                                       │
│  supervisor ──▶ worker(react_agent) ──▶ tool.ainvoke()                │
│       │              │                       │                        │
│  ┌────▼──────────────▼───────────────────────▼──────────────────┐    │
│  │            UsageCallback (M1 + M2 hooks)                      │    │
│  │  ┌──────────────────┐    ┌──────────────────┐                 │    │
│  │  │ on_llm_start/end │    │ on_tool_start    │  ★ M2 신규     │    │
│  │  │   (M1)           │    │ on_tool_end      │                 │    │
│  │  └────────┬─────────┘    │ on_tool_error    │                 │    │
│  │           │              └────────┬─────────┘                 │    │
│  │           │              ┌────────▼─────────┐                 │    │
│  │           │              │ purpose_inference│  ★ M2 신규     │    │
│  │           │              │ infer_tool_purpose                 │    │
│  │           │              └────────┬─────────┘                 │    │
│  │           ▼                       ▼                           │    │
│  │   tracker.record_llm_call    tracker.record_tool_call         │    │
│  │   (tool_call_id 자동주입)     tracker.update_tool_call         │    │
│  └────────────┬────────────────────────┬───────────────────────┘    │
│               ▼                        ▼                              │
│        ai_llm_call                 ai_tool_call                       │
│        (tool_call_id ★ NOT NULL)   (★ M2 채워짐)                     │
└───────────────────────────────────────────────────────────────────────┘
```

### 2.2 Data Flow (Tool Invocation)

```
1. LangChain Worker가 tool.ainvoke({...}) 호출
       │
       ▼
2. LangChain CallbackManager → UsageCallback.on_tool_start(serialized, inputs, run_id=lc_uuid)
       │
       ├─ tool_call_id = await tracker.record_tool_call(STARTED, args, ...)
       ├─ self._tool_starts[lc_uuid] = ToolStartInfo(tool_call_id, t0, prev_purpose)
       ├─ self._current_tool_call_id = tool_call_id
       ├─ self.set_purpose(infer_tool_purpose(tool_name))
       └─ RunContext: set_current_run_context(with_tool_call_id(ctx, tool_call_id))
       │
       ▼
3. Tool body 실행
       │
       ├─ (툴 내부 LLM 호출 시)
       │      └─ on_llm_end → tracker.record_llm_call(tool_call_id=self._current_tool_call_id)
       │
       ▼
4-success. on_tool_end(output, run_id=lc_uuid)
       │
       ├─ info = self._tool_starts.pop(lc_uuid, None)
       ├─ latency_ms = int((perf_counter() - info.t0) * 1000)
       ├─ await tracker.update_tool_call(info.tool_call_id, SUCCESS,
       │      result_summary=_summarize_tool_output(output), latency_ms=...)
       ├─ self._current_tool_call_id = None
       ├─ self.set_purpose(info.prev_purpose)
       └─ RunContext: set_current_run_context(with_tool_call_id(ctx, None))

4-error. on_tool_error(error, run_id=lc_uuid)
       │
       └─ 동일 흐름, status=FAILED, error_text=str(error)[:1024]
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `UsageCallback` (수정) | `RunTracker` (M1) | `record_tool_call` / `update_tool_call` 호출 |
| `UsageCallback` (수정) | `purpose_inference` (M2 신규) | tool_name → RunPurpose 매핑 |
| `UsageCallback` (수정) | `RunContext` (M1) | `set_current_run_context` / `with_tool_call_id` |
| `purpose_inference` | `RunPurpose` enum (M1 도메인) | 반환 타입 |
| (변경 없음) `WorkflowCompiler` | `UsageCallback` (M1) | callback이 graph.ainvoke 시 자동 전파 |
| (변경 없음) `ToolFactory` | LangChain `BaseTool` | runnable 추상화 활용 |

신규 외부 라이브러리: **없음** (LangChain 0.3+ 이미 사용).

---

## 3. Data Model

### 3.1 변경 없음

M1 `V021__create_agent_run_tables.sql`의 `ai_tool_call` 컬럼을 그대로 사용.

### 3.2 ai_tool_call 컬럼별 채움 정책 (M2)

| 컬럼 | 채움 시점 | 값 |
|------|----------|-----|
| `id` | `on_tool_start` | `record_tool_call` 내부 `uuid.uuid4()` 발급 |
| `run_id` | `on_tool_start` | `RunContext.run_id` (callback이 보유한 `self._run_id`) |
| `step_id` | `on_tool_start` | **NULL** (M2 범위) — M3에서 `self._current_step_id` 채움 |
| `tool_name` | `on_tool_start` | `serialized.get("name") or serialized.get("id", ["unknown"])[-1]` |
| `llm_model_id` | `on_tool_start` | **NULL** (툴 자체는 LLM 아님) |
| `arguments_json` | `on_tool_start` | `_sanitize_args(inputs or input_str)` — 1KB 컷 |
| `result_summary` | `on_tool_end` | `_summarize_tool_output(output)[:1024]` |
| `result_json` | (현 시점 미사용) | **NULL** — retention 정책 별도 PDCA |
| `prompt_tokens/completion_tokens/total_tokens` | (미사용) | **NULL** — `ai_llm_call.tool_call_id` GROUP BY 로 집계 |
| `total_cost_usd` | (미사용) | **NULL** — 위와 동일 |
| `latency_ms` | `on_tool_end/error` | `int((perf_counter() - t0) * 1000)` |
| `status` | `on_tool_start` → end/error | `STARTED` → `SUCCESS` / `FAILED` |
| `error_text` | `on_tool_error` | `str(error)[:1024]` |
| `created_at` | `on_tool_start` | `datetime.now(timezone.utc)` |

### 3.3 status enum (M1 G3 동기화)

M1 Plan §5-3은 `SUCCESS / FAILED`로 표기됐으나 실제 도메인·DB는 `STARTED / SUCCESS / FAILED` 3-state. M2는 3-state를 공식화하며, M1 Plan은 후속 archive 시 재정합 (별도 작업).

```
ai_tool_call.status:
  STARTED  (on_tool_start 시점 INSERT)
    │
    ├──▶ SUCCESS  (on_tool_end)
    │
    └──▶ FAILED   (on_tool_error)
```

### 3.4 Entity Relationships

```
ai_run (M1) 1 ─── N ai_tool_call (M2 채워짐)
                       │
                       │ 1
                       ▼
                       N
                    ai_llm_call (M2: tool_call_id 채워짐)
                       │
                       │
                ai_retrieval_source (M4 예정)
```

---

## 4. Interface Specification

### 4.1 `UsageCallback` (수정) — 신규 메서드 시그니처

```python
class UsageCallback(AsyncCallbackHandler):
    """M1 + M2: LLM + Tool 호출 단일 인터셉트."""

    def __init__(self, tracker, run_id, user_id, agent_id, logger):
        # ... M1 기존 필드 ...
        # M2 추가
        self._tool_starts: dict[UUID, _ToolStartInfo] = {}

    # ─────────────────────────── M2 신규 hooks ────────────────────────────

    async def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,                   # LangChain의 callback run_id (NOT 우리 RunId)
        parent_run_id: Optional[UUID] = None,
        tags: Optional[list[str]] = None,
        metadata: Optional[dict] = None,
        inputs: Optional[dict] = None,  # LangChain 신버전 — 구조화된 입력
        **kwargs: Any,
    ) -> None:
        """툴 호출 시작 인터셉트. record_tool_call → _current_tool_call_id 세팅."""

    async def on_tool_end(
        self,
        output: Any,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """툴 호출 성공 종료. update_tool_call(SUCCESS) + 컨텍스트 복원."""

    async def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """툴 호출 실패. update_tool_call(FAILED) + 컨텍스트 복원."""
```

### 4.2 내부 dataclass — `_ToolStartInfo`

```python
from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class _ToolStartInfo:
    """on_tool_start ↔ on_tool_end/error 매칭용 메타.

    LangChain callback run_id를 키로 _tool_starts에 보관.
    on_tool_end에서 pop하여 latency 계산 및 update_tool_call 호출.
    """
    tool_call_id: str
    t0: float                         # time.perf_counter() 시작 시각
    prev_purpose: Optional[RunPurpose] # 진입 직전 purpose (복원용)
    prev_tool_call_id: Optional[str]   # 진입 직전 _current_tool_call_id (중첩 안전)
```

### 4.3 `purpose_inference` (신규) — `src/application/agent_run/purpose_inference.py`

```python
"""Tool name → RunPurpose 매핑.

AGENT-OBS-002 §5-3 (M2 Plan §7) Design §5-3 매핑 표 코드화.
UsageCallback.on_tool_start에서 호출되어 set_purpose에 전달된다.
"""
import re
from typing import Final

from src.domain.agent_run.value_objects import RunPurpose

# 매핑 규칙 (우선순위 순서대로 첫 매칭이 적용됨)
_RULES: Final[list[tuple[re.Pattern[str], RunPurpose]]] = [
    (re.compile(r"^query_rewrit", re.IGNORECASE),    RunPurpose.QUERY_REWRITE),
    (re.compile(r"^(reranker|compressor)", re.IGNORECASE), RunPurpose.RERANK),
    (re.compile(r"^hallucination", re.IGNORECASE),   RunPurpose.HALLUCINATION_CHECK),
    (re.compile(r"(rag_search|retrieval_|hybrid_search|internal_document_search)",
                re.IGNORECASE), RunPurpose.WORKER),
    (re.compile(r"^(tavily_|web_search|perplexity)", re.IGNORECASE), RunPurpose.WORKER),
    (re.compile(r"^excel_export", re.IGNORECASE),    RunPurpose.WORKER),
    (re.compile(r"^python_code_executor", re.IGNORECASE), RunPurpose.WORKER),
    (re.compile(r"^mcp_", re.IGNORECASE),            RunPurpose.OTHER),
]


def infer_tool_purpose(tool_name: str) -> RunPurpose:
    """tool_name 문자열로부터 RunPurpose 추론.

    매칭 실패 시 RunPurpose.OTHER 반환 (절대 raise하지 않음 — best-effort).
    """
    if not tool_name:
        return RunPurpose.OTHER
    for pattern, purpose in _RULES:
        if pattern.search(tool_name):
            return purpose
    return RunPurpose.OTHER
```

**왜 `re.search` 가 아니라 `re.compile + search`?**: 매칭 호출 빈도가 높음 (툴 호출마다 1회). 모듈 로드 시 1회만 compile.

**WORKER 통합 정책**: rag/web_search/excel/code_executor 등 "사용자 의도 직접 처리" 툴은 모두 `WORKER`로 매핑. 툴 *내부* LLM 호출이 `query_rewrite/rerank/hallucination`이면 그 LLM 호출 시점에 callback이 이미 `set_purpose(WORKER)` 상태인데, 툴 내부에서 별도로 `set_purpose(QUERY_REWRITE)`를 호출해야 정확. M2에서는 이를 "툴 어댑터의 선택적 정밀화"로 두고, **기본 매핑만 자동화**. 정밀화는 M3/M4에서 RAG 어댑터 수정 시 함께 (Out of Scope).

### 4.4 헬퍼 함수 — `UsageCallback` 내부

```python
# src/infrastructure/llm/usage_callback.py 내부

_ARGS_MAX_BYTES: Final[int] = 1024     # arguments_json 직렬화 최대 크기
_RESULT_MAX_CHARS: Final[int] = 1024   # result_summary 최대 문자 수

def _sanitize_args(payload: Any) -> Optional[dict]:
    """LangChain on_tool_start의 inputs/input_str → JSON-safe dict.

    Rules:
      - dict 그대로 (단, 직렬화 시도 후 실패하면 repr fallback)
      - str → {"input": <str>}
      - 그 외 → {"input": str(value)}
    Truncation:
      - json.dumps 결과 1KB 초과 시 마지막 키 잘림 + 마커 추가
    """
    try:
        if isinstance(payload, dict):
            raw = payload
        elif isinstance(payload, str):
            raw = {"input": payload}
        elif payload is None:
            return None
        else:
            raw = {"input": str(payload)}
        # 직렬화 시도 (실패 시 repr fallback)
        try:
            serialized = json.dumps(raw, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            serialized = json.dumps({"input": repr(payload)}, ensure_ascii=False)
        if len(serialized.encode("utf-8")) <= _ARGS_MAX_BYTES:
            return json.loads(serialized)
        # 컷 처리: 키 보존 + 값만 자르기 (간단히 input 키로 통합)
        truncated = serialized[:_ARGS_MAX_BYTES - len('..."}}')] + '..."}'
        try:
            return json.loads(truncated)
        except json.JSONDecodeError:
            return {"input": serialized[:_ARGS_MAX_BYTES - 20], "_truncated": True}
    except Exception:  # 어떤 경우에도 raise 안함 (best-effort)
        return None


def _summarize_tool_output(value: Any) -> Optional[str]:
    """tool 반환값 → result_summary 문자열 (1KB 컷).

    Rules:
      - None → None
      - str → str[:1024]
      - dict/list → json.dumps(default=str)[:1024]
      - LangChain Document/BaseModel → 가능하면 .content/.model_dump() → 위 규칙 재적용
      - 그 외 → str(value)[:1024]
    """
    if value is None:
        return None
    try:
        # LangChain Document 호환
        if hasattr(value, "page_content"):
            text = str(value.page_content)
            return text[:_RESULT_MAX_CHARS]
        # Pydantic BaseModel
        if hasattr(value, "model_dump"):
            text = json.dumps(value.model_dump(), ensure_ascii=False, default=str)
            return text[:_RESULT_MAX_CHARS]
        if isinstance(value, str):
            return value[:_RESULT_MAX_CHARS]
        if isinstance(value, (dict, list, tuple)):
            text = json.dumps(value, ensure_ascii=False, default=str)
            return text[:_RESULT_MAX_CHARS]
        return str(value)[:_RESULT_MAX_CHARS]
    except Exception:
        return None
```

### 4.5 메서드 내부 흐름 의사코드

#### `on_tool_start`

```python
async def on_tool_start(self, serialized, input_str, *, run_id, parent_run_id=None,
                       tags=None, metadata=None, inputs=None, **kwargs) -> None:
    tool_name = (
        serialized.get("name")
        or (serialized.get("id") or ["unknown"])[-1]
        if isinstance(serialized, dict) else "unknown"
    )
    args_payload = inputs if inputs is not None else input_str
    args_json = _sanitize_args(args_payload)

    t0 = time.perf_counter()
    prev_purpose = self._current_purpose
    prev_tool_call_id = self._current_tool_call_id  # 중첩 안전 (현 시점 N/A지만 미래 대비)

    try:
        tool_call_id = await self._tracker.record_tool_call(
            run_id=self._run_id,
            step_id=self._current_step_id,
            tool_name=tool_name,
            arguments=args_json,
            status="STARTED",
        )
    except Exception as e:
        self._logger.warning(
            "UsageCallback on_tool_start record_tool_call failed (best-effort)",
            exception=e, run_id=self._run_id.value, tool_name=tool_name,
        )
        tool_call_id = None

    # tool_call_id가 None이어도 _tool_starts에는 등록 (on_tool_end의 매칭 일관성 위해)
    self._tool_starts[run_id] = _ToolStartInfo(
        tool_call_id=tool_call_id or "",   # "" sentinel: end 시점 skip 신호
        t0=t0,
        prev_purpose=prev_purpose,
        prev_tool_call_id=prev_tool_call_id,
    )

    if tool_call_id is not None:
        self._current_tool_call_id = tool_call_id
        self.set_purpose(infer_tool_purpose(tool_name))
        # RunContext 동기화 (M4의 record_retrieval 사전 작업)
        _update_run_context_tool_call_id(tool_call_id)


def _update_run_context_tool_call_id(tool_call_id: Optional[str]) -> None:
    """현재 RunContext에 tool_call_id 반영. ContextVar 작업은 helper로 분리."""
    from src.application.agent_run.context import (
        get_current_run_context, set_current_run_context, with_tool_call_id,
    )
    ctx = get_current_run_context()
    if ctx is None:
        return
    set_current_run_context(with_tool_call_id(ctx, tool_call_id))
```

#### `on_tool_end`

```python
async def on_tool_end(self, output, *, run_id, parent_run_id=None, **kwargs) -> None:
    info = self._tool_starts.pop(run_id, None)
    if info is None:
        self._logger.warning(
            "UsageCallback on_tool_end without matching start (lc_run_id leak?)",
            run_id=self._run_id.value, lc_run_id=str(run_id),
        )
        return
    latency_ms = int((time.perf_counter() - info.t0) * 1000)
    result_summary = _summarize_tool_output(output)

    if info.tool_call_id:  # 빈 문자열이면 start가 실패한 케이스 → update skip
        try:
            await self._tracker.update_tool_call(
                tool_call_id=info.tool_call_id,
                run_id=self._run_id,
                status="SUCCESS",
                result_summary=result_summary,
                latency_ms=latency_ms,
            )
        except Exception as e:
            self._logger.warning(
                "UsageCallback on_tool_end update_tool_call failed (best-effort)",
                exception=e, run_id=self._run_id.value,
                tool_call_id=info.tool_call_id,
            )

    # 컨텍스트 복원 (purpose / tool_call_id / RunContext)
    self._current_tool_call_id = info.prev_tool_call_id
    self.set_purpose(info.prev_purpose)
    _update_run_context_tool_call_id(info.prev_tool_call_id)
```

#### `on_tool_error`

```python
async def on_tool_error(self, error, *, run_id, parent_run_id=None, **kwargs) -> None:
    info = self._tool_starts.pop(run_id, None)
    if info is None:
        self._logger.warning(
            "UsageCallback on_tool_error without matching start",
            run_id=self._run_id.value, lc_run_id=str(run_id),
        )
        return
    latency_ms = int((time.perf_counter() - info.t0) * 1000)
    error_text = str(error)[:1024] if error else None

    if info.tool_call_id:
        try:
            await self._tracker.update_tool_call(
                tool_call_id=info.tool_call_id,
                run_id=self._run_id,
                status="FAILED",
                latency_ms=latency_ms,
                error_text=error_text,
            )
        except Exception as e:
            self._logger.warning(
                "UsageCallback on_tool_error update_tool_call failed (best-effort)",
                exception=e, run_id=self._run_id.value,
                tool_call_id=info.tool_call_id,
            )

    self._current_tool_call_id = info.prev_tool_call_id
    self.set_purpose(info.prev_purpose)
    _update_run_context_tool_call_id(info.prev_tool_call_id)
```

---

## 5. State Machine

### 5.1 ai_tool_call.status 전이

```
        [INSERT on_tool_start]
                │
                ▼
            ┌────────┐
            │STARTED │
            └────┬───┘
       ┌─────────┼─────────┐
       │         │         │
  [on_tool_end] [on_tool_error] [graph 비정상 종료]
       │         │         │
       ▼         ▼         ▼
   ┌────────┐ ┌────────┐  (orphan: STARTED 상태로 잔존)
   │SUCCESS │ │FAILED  │   └─ M4 운영 dashboard에서
   └────────┘ └────────┘     detection 예정
```

**Orphan STARTED 처리**: graph가 비정상 종료(프로세스 kill 등)되면 `on_tool_end/error`가 호출되지 않아 row가 `STARTED` 상태로 남는다.

- M2 범위: warning log만 (best-effort 일관성)
- M4 후속: `tracker.complete_run` / `fail_run`에서 해당 run의 `STARTED` row를 `FAILED` (orphan reason)로 일괄 정리하는 sweep 로직 검토 — 별도 PDCA 후보

### 5.2 UsageCallback 내부 상태 전이

```
초기:
  _current_tool_call_id = None
  _current_purpose = None (또는 SUPERVISOR/WORKER per node entry)
  _tool_starts = {}

on_tool_start(lc_uuid_A):
  _tool_starts[lc_uuid_A] = ToolStartInfo(tcid_1, t0, prev=None, prev_tcid=None)
  _current_tool_call_id = tcid_1
  _current_purpose = inferred

on_tool_end(lc_uuid_A):
  info = _tool_starts.pop(lc_uuid_A)
  _current_tool_call_id = info.prev_tool_call_id (= None)
  _current_purpose = info.prev_purpose

최종:
  _current_tool_call_id = None
  _current_purpose = prev (복원됨)
  _tool_starts = {} (모든 매칭 종료)
```

---

## 6. Error Handling

### 6.1 Failure Modes & Responses

| 시나리오 | 영향 | 처리 |
|---------|------|------|
| `record_tool_call` 실패 (DB 다운 등) | `tool_call_id=None`, `ai_tool_call` 행 없음 | `_tool_starts`에 sentinel(`""`)로 등록 → on_tool_end는 update skip하되 컨텍스트 복원은 정상 수행. warning log |
| `update_tool_call` 실패 | `STARTED` row 잔존 (orphan) | warning log. M4 sweep에서 정리 예정 |
| `on_tool_end` 매칭 미스 (`pop`이 None) | leak 가능성 | warning log + skip |
| `_sanitize_args` 직렬화 실패 | `arguments_json = None` | 내부 try/except (best-effort) — DB 컬럼이 nullable이므로 안전 |
| `_summarize_tool_output` 실패 | `result_summary = None` | 내부 try/except — nullable 컬럼 |
| `purpose_inference` 매칭 실패 | `RunPurpose.OTHER` | 정상 동작 (raise 없음) |
| LangChain `on_tool_start` 시그니처 mismatch (구버전 vs 신버전) | TypeError 가능 | `**kwargs`로 수용 + `inputs` / `input_str` 둘 다 핸들링 |
| 중첩 툴 호출 (현재 패턴 아님) | `_current_tool_call_id` 덮어쓰기 | `_ToolStartInfo.prev_tool_call_id`로 stack-like 복원 (안전) |

### 6.2 Logging Conventions

| Level | 시나리오 |
|-------|---------|
| `info` | (없음 — record_tool_call 자체는 RunTracker가 이미 로깅) |
| `warning` | record/update 실패, 매칭 미스, 직렬화 실패, orphan 감지 |
| `error` | (해당 없음 — M2는 best-effort) |

모든 warning은 `run_id` + `tool_name` 또는 `lc_run_id` context 포함.

---

## 7. Security Considerations

- [x] **PII / 민감정보**: `arguments_json` / `result_summary`에 사용자 입력이 그대로 저장될 수 있음 → 1KB 컷이 1차 방어선, anonymization은 별도 PDCA(`agent-pii-masking`)
- [x] **arguments_json SQL Injection**: SQLAlchemy ORM 사용으로 자동 escape (M1 정책 유지)
- [x] **로그 노출**: warning log에 `arguments`/`result` 원문 포함 금지 — `tool_name` + `run_id`만 노출
- [x] **권한**: M2는 데이터 영속화만 — 조회 API(M4)에서 admin/self 권한 분리 예정
- [x] **MCP 툴 신뢰성**: 부서 등록 MCP 툴의 인자/결과가 신뢰할 수 없을 수 있음 → `default=str` + `repr` fallback이 안전 직렬화 보장

---

## 8. Test Plan

### 8.1 Test Scope

| Type | Target | Tool |
|------|--------|------|
| Unit Test | `purpose_inference.infer_tool_purpose` | pytest |
| Unit Test | `_sanitize_args` / `_summarize_tool_output` | pytest |
| Unit Test | `UsageCallback.on_tool_*` (Tracker = AsyncMock) | pytest + AsyncMock |
| Integration Test | RunAgentUseCase + real MySQL + DummyLLM + DummyTool | pytest + testcontainers (M1 conftest 재활용) |
| Manual Test | 실 LLM + RAG/Tavily 1회씩 + SQL 조회 | psql / mycli |

### 8.2 Key Test Cases

#### `tests/application/agent_run/test_purpose_inference.py` (7 cases)

```python
@pytest.mark.parametrize("tool_name, expected", [
    ("internal_document_search", RunPurpose.WORKER),
    ("rag_search_finance",       RunPurpose.WORKER),
    ("hybrid_search",            RunPurpose.WORKER),
    ("tavily_search",            RunPurpose.WORKER),
    ("query_rewriter_v2",        RunPurpose.QUERY_REWRITE),
    ("reranker_cohere",          RunPurpose.RERANK),
    ("compressor_basic",         RunPurpose.RERANK),
    ("hallucination_check_v1",   RunPurpose.HALLUCINATION_CHECK),
    ("mcp_jira_create_issue",    RunPurpose.OTHER),
    ("python_code_executor",     RunPurpose.WORKER),
    ("excel_export",             RunPurpose.WORKER),
    ("unknown_tool_xyz",         RunPurpose.OTHER),
    ("",                         RunPurpose.OTHER),
    (None,                       RunPurpose.OTHER),
    ("RAG_SEARCH",               RunPurpose.WORKER),  # case insensitive
])
def test_infer_tool_purpose(tool_name, expected):
    assert infer_tool_purpose(tool_name) == expected
```

#### `tests/infrastructure/llm/test_usage_callback_tool_hooks.py` (20 cases)

Critical cases:

```python
@pytest.mark.asyncio
async def test_on_tool_start_calls_record_tool_call(callback, tracker_mock):
    await callback.on_tool_start(
        serialized={"name": "internal_document_search"},
        input_str='{"query": "test"}',
        run_id=uuid4(),
    )
    tracker_mock.record_tool_call.assert_awaited_once()
    args = tracker_mock.record_tool_call.await_args.kwargs
    assert args["tool_name"] == "internal_document_search"
    assert args["status"] == "STARTED"


@pytest.mark.asyncio
async def test_on_tool_start_sets_purpose_by_inference(callback, tracker_mock):
    tracker_mock.record_tool_call.return_value = "tcid-001"
    await callback.on_tool_start(
        serialized={"name": "query_rewriter_v2"},
        input_str="", run_id=uuid4(),
    )
    assert callback._current_purpose == RunPurpose.QUERY_REWRITE


@pytest.mark.asyncio
async def test_on_tool_start_sets_current_tool_call_id(callback, tracker_mock):
    tracker_mock.record_tool_call.return_value = "tcid-001"
    await callback.on_tool_start(
        serialized={"name": "rag_search"}, input_str="", run_id=uuid4(),
    )
    assert callback._current_tool_call_id == "tcid-001"


@pytest.mark.asyncio
async def test_on_tool_end_computes_latency_ms(callback, tracker_mock, monkeypatch):
    tracker_mock.record_tool_call.return_value = "tcid-001"
    lc_id = uuid4()
    # perf_counter monkeypatch로 latency 결정성 보장
    t = [100.0, 100.123]
    monkeypatch.setattr("time.perf_counter", lambda: t.pop(0))
    await callback.on_tool_start(serialized={"name": "x"}, input_str="", run_id=lc_id)
    await callback.on_tool_end(output="ok", run_id=lc_id)
    upd = tracker_mock.update_tool_call.await_args.kwargs
    assert upd["latency_ms"] == 123


@pytest.mark.asyncio
async def test_on_tool_error_records_failed_status(callback, tracker_mock):
    tracker_mock.record_tool_call.return_value = "tcid-001"
    lc_id = uuid4()
    await callback.on_tool_start(serialized={"name": "tavily_search"},
                                 input_str="", run_id=lc_id)
    await callback.on_tool_error(error=RuntimeError("boom"), run_id=lc_id)
    upd = tracker_mock.update_tool_call.await_args.kwargs
    assert upd["status"] == "FAILED"
    assert "boom" in (upd["error_text"] or "")


@pytest.mark.asyncio
async def test_record_tool_call_failure_degrades_gracefully(
    callback, tracker_mock, caplog
):
    tracker_mock.record_tool_call.side_effect = RuntimeError("db down")
    lc_id = uuid4()
    await callback.on_tool_start(serialized={"name": "x"}, input_str="", run_id=lc_id)
    # _current_tool_call_id는 갱신되지 않음 (None 유지)
    assert callback._current_tool_call_id is None
    # _tool_starts에는 sentinel 등록되어 end가 매칭 미스 안 일으킴
    assert lc_id in callback._tool_starts
    await callback.on_tool_end(output="ok", run_id=lc_id)
    # update_tool_call는 호출되지 않음 (sentinel skip)
    tracker_mock.update_tool_call.assert_not_called()


@pytest.mark.asyncio
async def test_unmatched_on_tool_end_logs_warning(callback, tracker_mock):
    await callback.on_tool_end(output="ok", run_id=uuid4())
    tracker_mock.update_tool_call.assert_not_called()
    # warning log 검증은 logger mock으로


@pytest.mark.asyncio
async def test_llm_call_inside_tool_attaches_tool_call_id(  # ★ 핵심 회귀 가드
    callback, tracker_mock,
):
    tracker_mock.record_tool_call.return_value = "tcid-001"
    lc_id = uuid4()
    await callback.on_tool_start(serialized={"name": "rag_search"},
                                 input_str="", run_id=lc_id)
    # 툴 내부 LLM 호출 시뮬레이션
    inner_llm_id = uuid4()
    await callback.on_chat_model_start(serialized={}, messages=[], run_id=inner_llm_id)
    fake_response = _make_fake_openai_llm_result(prompt=10, completion=20)
    await callback.on_llm_end(response=fake_response, run_id=inner_llm_id)
    # record_llm_call의 tool_call_id 인자가 tcid-001이어야 함
    args = tracker_mock.record_llm_call.await_args.kwargs
    assert args["tool_call_id"] == "tcid-001"


def test_sanitize_args_dict_passthrough():
    assert _sanitize_args({"q": "abc"}) == {"q": "abc"}

def test_sanitize_args_str_wrapped():
    assert _sanitize_args("hello") == {"input": "hello"}

def test_sanitize_args_truncation():
    big = {"q": "x" * 5000}
    out = _sanitize_args(big)
    assert len(json.dumps(out).encode("utf-8")) <= 1024 + 32  # 컷 마커 여유

def test_sanitize_args_non_json_serializable_fallback():
    class NotSerializable:
        def __repr__(self): return "NotSer()"
    out = _sanitize_args(NotSerializable())
    assert "NotSer" in json.dumps(out)

def test_summarize_tool_output_str_truncated():
    assert _summarize_tool_output("x" * 2000) == "x" * 1024

def test_summarize_tool_output_dict_as_json():
    out = _summarize_tool_output({"a": 1, "b": "two"})
    assert "two" in out and len(out) <= 1024

def test_summarize_tool_output_none_returns_none():
    assert _summarize_tool_output(None) is None
```

#### `tests/application/agent_builder/test_run_agent_use_case_observability.py` (M2 보강 4 cases)

```python
@pytest.mark.asyncio
async def test_one_run_with_tool_creates_ai_tool_call_row(
    use_case, conversation_with_rag_tool, db_session,
):
    """RAG 툴 사용 워크플로우 1회 실행 → ai_tool_call 1 row 검증."""
    resp = await use_case.execute(conversation_with_rag_tool)
    rows = await db_session.execute(
        select(ToolCallModel).where(ToolCallModel.run_id == resp.run_id)
    )
    rows = rows.scalars().all()
    assert len(rows) >= 1
    assert rows[0].status == "SUCCESS"
    assert rows[0].tool_name == "internal_document_search"
    assert rows[0].latency_ms is not None and rows[0].latency_ms > 0


@pytest.mark.asyncio
async def test_tool_internal_llm_call_links_via_tool_call_id(  # ★ JOIN 검증
    use_case, conversation_with_rag_tool_using_rerank, db_session,
):
    resp = await use_case.execute(conversation_with_rag_tool_using_rerank)
    # 동일 run의 ai_tool_call + ai_llm_call JOIN
    row = await db_session.execute(text("""
        SELECT t.tool_name, l.purpose, l.tool_call_id
          FROM ai_llm_call l JOIN ai_tool_call t ON t.id = l.tool_call_id
         WHERE l.run_id = :rid
    """), {"rid": resp.run_id})
    rows = row.all()
    # 적어도 한 건의 LLM 호출이 tool_call_id로 연결됨
    assert any(r.tool_call_id is not None for r in rows)


@pytest.mark.asyncio
async def test_tool_failure_records_failed_status(
    use_case, conversation_with_failing_tool, db_session,
):
    resp = await use_case.execute(conversation_with_failing_tool)
    row = await db_session.execute(
        select(ToolCallModel).where(ToolCallModel.run_id == resp.run_id)
    )
    rows = row.scalars().all()
    failed = [r for r in rows if r.status == "FAILED"]
    assert len(failed) >= 1
    assert failed[0].error_text is not None


@pytest.mark.asyncio
async def test_observability_failure_does_not_block_response(
    use_case_with_broken_tracker, conversation_simple,
):
    """tracker.record_tool_call 강제 예외 → 응답은 정상 반환."""
    resp = await use_case_with_broken_tracker.execute(conversation_simple)
    assert resp.answer  # 응답 정상
    assert resp.run_id  # run_id는 발급됨 (start_run은 별개)
```

### 8.3 테스트 우선순위

1. **핵심 회귀 가드**: `test_llm_call_inside_tool_attaches_tool_call_id` — M2의 단 하나의 가치 보장
2. **State machine**: `test_on_tool_start_sets_current_tool_call_id` + `test_on_tool_end_restores_context`
3. **Best-effort**: `test_record_tool_call_failure_degrades_gracefully` + `test_observability_failure_does_not_block_response`
4. 나머지 헬퍼·purpose 매핑 단위 테스트

---

## 9. Clean Architecture

### 9.1 Layer Structure (CLAUDE.md §2 준수)

| Layer | Responsibility | M2 변경 |
|-------|---------------|---------|
| **domain/agent_run/** | `RunPurpose` enum (M1 기존) | **변경 없음** |
| **application/agent_run/** | `purpose_inference.py` (신규) | infer_tool_purpose 함수 1개 |
| **infrastructure/llm/** | `usage_callback.py` (수정) | `on_tool_*` 3 메서드 + 2 헬퍼 |
| **infrastructure/persistence/** | M1 ORM/Repo | **변경 없음** |
| **interfaces/** (FastAPI router) | | **변경 없음** (M4 범위) |

### 9.2 Dependency Direction

```
infrastructure/llm/usage_callback.py
    ├──> application/agent_run/tracker.py    (M1, 변경 없음)
    ├──> application/agent_run/purpose_inference.py  ★ M2 신규
    ├──> application/agent_run/context.py    (M1, 변경 없음)
    └──> domain/agent_run/value_objects.py   (RunPurpose import)

application/agent_run/purpose_inference.py
    └──> domain/agent_run/value_objects.py   (RunPurpose only)
        (외부 의존성 없음 — re 모듈만)
```

**규칙 검증**:
- domain → 외부 의존 0 ✅
- application(`purpose_inference`) → domain만 ✅
- infrastructure(`usage_callback`) → application + domain ✅
- 역방향(domain → infra) 없음 ✅

### 9.3 Forbidden Action 체크 (CLAUDE.md §6)

- [x] domain → infrastructure 참조: **없음**
- [x] controller/router에 비즈니스 로직: **N/A** (M2 라우터 변경 없음)
- [x] 대화 기록을 vector db에 저장: **N/A**
- [x] `print()` 사용: **금지** — `self._logger.warning` 사용
- [x] 스택 트레이스 없는 에러 처리: warning log에 `exception=e` 전달하여 LoggerInterface가 스택 포함
- [x] Repository 내부 commit/rollback: M2에서 Repository 변경 없음 (M1 정책 유지)
- [x] 한 UseCase 안에서 repository 별 다른 세션: N/A (M2는 UseCase 변경 없음)

---

## 10. Coding Convention Reference

### 10.1 Naming Conventions (Python — CLAUDE.md §3)

| Target | Rule | 적용 예시 (M2) |
|--------|------|---------|
| Module | snake_case.py | `purpose_inference.py`, `usage_callback.py` |
| Class | PascalCase | `_ToolStartInfo` |
| Function | snake_case | `infer_tool_purpose`, `on_tool_start`, `_sanitize_args` |
| Constant | UPPER_SNAKE_CASE | `_ARGS_MAX_BYTES`, `_RESULT_MAX_CHARS`, `_RULES` |
| Private | `_` prefix | `_tool_starts`, `_summarize_tool_output` |
| Async fn | async def | `on_tool_start`, `on_tool_end` |

### 10.2 Import Order

```python
# 1. Standard library
import json
import re
import time
import uuid
from dataclasses import dataclass
from typing import Any, Final, Optional
from uuid import UUID

# 2. Third-party
from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.outputs import LLMResult

# 3. First-party (src)
from src.application.agent_run.context import (
    get_current_run_context, set_current_run_context, with_tool_call_id,
)
from src.application.agent_run.purpose_inference import infer_tool_purpose
from src.application.agent_run.tracker import RunTracker
from src.domain.agent_run.value_objects import RunId, RunPurpose, TokenUsage
from src.domain.logging.interfaces.logger_interface import LoggerInterface
```

### 10.3 함수 길이 / if 중첩 (CLAUDE.md §3)

- 함수 길이 40줄 초과 금지: `on_tool_start/end/error` 각각 ~25줄, `_sanitize_args` ~25줄, `_summarize_tool_output` ~20줄 ✅
- if 중첩 2단계 초과 금지: 모든 분기 1~2단계 ✅
- 명시적 타입: 모든 시그니처 `Optional[...]` / `dict[str, Any]` 등 명시 ✅
- config 하드코딩 금지: `_ARGS_MAX_BYTES` / `_RESULT_MAX_CHARS` 는 모듈 상수 (M2 범위 OK), 환경변수화는 별도 PDCA

### 10.4 LOG-001 Logger 사용 (CLAUDE.md §7)

```python
self._logger.warning(
    "UsageCallback on_tool_start record_tool_call failed (best-effort)",
    exception=e,           # 스택 트레이스 자동 포함
    run_id=self._run_id.value,
    tool_name=tool_name,
    lc_run_id=str(run_id),
)
```

- 메시지는 영문, context는 키-값으로 — `verify-logging` skill 검증 통과 목표

---

## 11. Implementation Guide

### 11.1 File Structure

```
idt/
├── src/
│   ├── application/
│   │   └── agent_run/
│   │       ├── tracker.py                  # M1 (변경 없음)
│   │       ├── context.py                  # M1 (변경 없음)
│   │       └── purpose_inference.py        ★ M2 신규
│   └── infrastructure/
│       └── llm/
│           └── usage_callback.py            ★ M2 수정 (on_tool_* 3 메서드 + 2 헬퍼)
└── tests/
    ├── application/
    │   └── agent_run/
    │       └── test_purpose_inference.py    ★ M2 신규
    ├── infrastructure/
    │   └── llm/
    │       └── test_usage_callback_tool_hooks.py  ★ M2 신규
    └── application/
        └── agent_builder/
            └── test_run_agent_use_case_observability.py  (보강 +4 cases)
```

### 11.2 Implementation Order (TDD)

```
Step 1: purpose_inference 모듈 (단순, 의존성 최소)
  1.1 test_purpose_inference.py 작성 (Red)
  1.2 purpose_inference.py 구현 (Green)
  1.3 ruff/mypy 통과 (Refactor)

Step 2: UsageCallback 헬퍼 함수 (순수 함수)
  2.1 test_usage_callback_tool_hooks.py 헬퍼 부분 (_sanitize_args, _summarize_tool_output) 작성 (Red)
  2.2 usage_callback.py에 헬퍼 추가 (Green)

Step 3: UsageCallback on_tool_* hooks
  3.1 test_usage_callback_tool_hooks.py hook 부분 작성 (Red)
  3.2 _ToolStartInfo dataclass + on_tool_start/end/error 구현 (Green)
  3.3 _update_run_context_tool_call_id 헬퍼 추가

Step 4: 통합 테스트
  4.1 test_run_agent_use_case_observability.py 4 cases 보강 (Red)
  4.2 (구현 변경 없음 — UsageCallback 이미 graph에 등록되어 있음)
  4.3 통합 테스트 통과 확인 (Green)

Step 5: 수동 검증
  5.1 RAG/Tavily 1회씩 실 호출
  5.2 SQL 조회로 ai_tool_call + ai_llm_call.tool_call_id 검증
  5.3 verify-logging skill 실행
  5.4 verify-architecture skill 실행

Step 6: 문서 동기화
  6.1 M1 Plan §5-3 status enum 표기 갱신 (G3 후속)
  6.2 docs/03-analysis/agent-run-observability-m2.analysis.md 준비 (Check phase)
```

### 11.3 Dependencies / Setup

신규 패키지 설치 **없음**. LangChain `AsyncCallbackHandler.on_tool_*` 는 langchain-core 0.3+ 표준 메서드.

검증:
```bash
python -c "from langchain_core.callbacks import AsyncCallbackHandler; \
    import inspect; print([m for m in dir(AsyncCallbackHandler) if 'tool' in m])"
# 출력: ['on_tool_end', 'on_tool_error', 'on_tool_start']
```

---

## 12. M1 Design Sync Notes

| 항목 | M1 상태 | M2 결정 |
|------|---------|---------|
| Manual `_wrapped_tool_call` (M1 Design §5-3) | 제안만 — 구현 안 됨 | **폐기.** Callback-driven으로 통일 (M2 Plan §4-1 결정표 참조) |
| `ai_tool_call.status` enum | M1 Plan: `SUCCESS/FAILED` 2-state 표기 | **공식: `STARTED/SUCCESS/FAILED` 3-state.** M1 Plan은 archive 시 후속 동기화 |
| `UsageCallback.enter_tool/exit_tool` API | 수동 호출 의무 (M1 §14-1) | **자동화.** `on_tool_start/end`가 내부적으로 호출 (수동 API는 보존 — backward compat) |
| RunContext.tool_call_id | M1: 항상 None | **M2: on_tool_start/end가 자동 set/reset.** M4 RAG 어댑터 사전 작업 완료 |
| `_infer_tool_purpose()` (M1 Design §5-3 매핑 표) | 표만 — 코드 없음 | **`purpose_inference.py` 신규 모듈로 코드화** |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-05-19 | M2 초안 — Callback-driven tool hook 설계, 데이터 모델 무변경, TDD 26 cases | 배상규 |
