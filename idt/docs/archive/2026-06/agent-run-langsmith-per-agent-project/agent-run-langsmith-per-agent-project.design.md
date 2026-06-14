# agent-run-langsmith-per-agent-project Design Document

> **Summary**: 에이전트 실행(`RunAgentUseCase.stream()`, 전 transport 공통)의 LangSmith 추적을 **에이전트별 프로젝트(`agent-{에이전트명}`)** 로 분리하고 run_name·tags·metadata에 에이전트명을 보강한다. 전역 `os.environ["LANGSMITH_PROJECT"]` 변경(동시성 race)이 아니라, `graph_config["callbacks"]`에 **per-run `LangChainTracer(project_name=...)`** 를 주입하는 방식으로 구현한다. langchain_core가 명시적 tracer가 있으면 전역 auto-tracer를 추가하지 않으므로(중복/경합 없음) 안전하다.
>
> **Project**: sangplusbot (idt)
> **Author**: AI Assistant
> **Date**: 2026-06-03
> **Status**: Draft
> **Planning Doc**: [../../01-plan/features/agent-run-langsmith-per-agent-project.plan.md](../../01-plan/features/agent-run-langsmith-per-agent-project.plan.md)

---

## 1. Overview

### 1.1 Design Goals
- 에이전트 실행 trace가 LangSmith에서 **`agent-{에이전트명}` 프로젝트**로 분리 기록
- root run `run_name` = 에이전트명, `tags`·`metadata`에 `agent_name` 포함 → UI 식별 가능
- HTTP `/run` + SSE `/run/stream` + WS `/ws/agent` **일괄 적용**(공통 `stream()` 1곳 수정)
- **동시성 안전**: 서로 다른 에이전트의 동시 실행에도 프로젝트가 섞이지 않음
- 진단(Step 0)으로 WS 추적 도달을 사실 확인

### 1.2 Design Principles
- 최소·국소 변경 + 기존 자산 재사용(`graph_config["callbacks"]` 경로 활용)
- DDD 레이어 준수: `langchain_core` tracer 생성은 **infrastructure**(`infrastructure/langsmith`)에 캡슐화. application(`RunAgentUseCase`)은 infra 헬퍼만 호출
- CLAUDE.md: print 금지·logger 사용, 함수 40줄·if 2단계 준수, config 하드코딩 회피(프로젝트명 정규화 헬퍼)

---

## 2. 핵심 설계 결정 — 전역 env vs per-run tracer

### 2.1 결정: **per-run `LangChainTracer` 주입** (Option A 채택)

| 방식 | 동작 | 동시성 | 채택 |
|------|------|--------|------|
| **A. per-run tracer** (채택) | `graph_config["callbacks"]`에 `LangChainTracer(project_name=f"agent-{name}")` 추가 | **안전** (run별 인스턴스) | ✅ |
| B. 전역 env per agent | `langsmith(project_name=f"agent-{name}")`로 `os.environ["LANGSMITH_PROJECT"]` 변경 | **race** (await 경계서 타 코루틴이 덮어씀) | ❌ |

### 2.2 Option B를 버린 이유 (race 근거)
`stream()`은 `langsmith()` 호출 이후 `_save_user_message`/`_begin_observability`/`astream_events` 등 **await 지점**이 있다. 전역 `os.environ`를 코루틴 A가 `agent-A`로 설정한 뒤 await에서 양보하면, 코루틴 B가 `agent-B`로 덮어쓰고, A 재개 시 글로벌 tracer가 `agent-B` 프로젝트를 읽는다 → **trace가 엉뚱한 프로젝트로 기록**. (Plan §7 race 요구 해소)

### 2.3 중복 trace가 없는 근거 (검증됨)
langchain_core `1.2.9` callback manager는:
```python
if tracing_v2_enabled_ and not any(
    isinstance(handler, LangChainTracer)
    for handler in callback_manager.handlers
):
    callback_manager.add_handler(tracer_v2)   # 전역 auto-tracer 추가
```
즉 **callbacks에 LangChainTracer가 이미 있으면 전역 tracer를 추가하지 않는다** → 우리 per-run tracer만 동작(중복 없음, 프로젝트 1개로 정확).

### 2.4 부수 효과 (진단과의 관계)
명시적 tracer는 자체 `Client`(API 키 기반)로 전송하므로, `LANGSMITH_TRACING`/`LANGCHAIN_TRACING_V2` env 이름 호환 이슈와 **무관하게** 추적이 동작한다. 따라서 per-run tracer 도입은 "WS 추적 미작동" 의심까지 robust하게 덮는다. 다만 사실 확인을 위해 §6 진단 Step은 유지(추적 도달·프로젝트명 눈으로 확인).

> 기존 전역 `langsmith(project_name="agent-run")` 호출은 **그대로 유지**(전역 기본 활성화/기타 코드 경로용). 에이전트 실행은 per-run tracer가 프로젝트를 결정하므로 전역 `LANGSMITH_PROJECT` 값에 의존하지 않는다.

---

## 3. Detailed Design

### 3.1 File: `src/infrastructure/langsmith/langsmith.py` (헬퍼 추가)

`langchain_core` import를 infra에 가둔다. 키 없으면/실패 시 `None` 반환(best-effort).

```python
from typing import Optional

_PROJECT_NAME_MAX = 128


def normalize_agent_project_name(agent_name: Optional[str]) -> str:
    """에이전트명 → LangSmith 프로젝트명. 공백 정규화·길이 제한, 빈 값이면 fallback."""
    base = " ".join((agent_name or "").split())
    if not base:
        return "agent-run"
    return f"agent-{base}"[:_PROJECT_NAME_MAX]


def make_agent_run_tracer(
    agent_name: Optional[str],
    tags: Optional[list[str]] = None,
):
    """에이전트별 프로젝트로 보내는 per-run LangChainTracer 생성.

    - API 키 없으면 None (추적 비활성, 본 흐름 영향 없음).
    - 명시적 tracer는 전역 LANGSMITH_TRACING env 이름 이슈와 무관하게 동작.
    """
    key = os.environ.get("LANGCHAIN_API_KEY", "") or os.environ.get(
        "LANGSMITH_API_KEY", ""
    )
    if not key.strip():
        return None
    try:
        from langchain_core.tracers import LangChainTracer
        return LangChainTracer(
            project_name=normalize_agent_project_name(agent_name),
            tags=tags,
        )
    except Exception:
        return None
```

> `langsmith()` 기존 함수는 변경하지 않는다(전역 활성화 책임 유지). Client 인스턴스는 LangChainTracer 기본 생성에 위임(추후 모듈 캐시 최적화 여지 — 본 사이클 범위 밖).

### 3.2 File: `src/application/agent_builder/run_agent_use_case.py`

#### 3.2.1 import 추가
```python
from src.infrastructure.langsmith.langsmith import langsmith, make_agent_run_tracer
```

#### 3.2.2 `_prepare_graph` — graph_config 보강 (핵심 변경)

기존 `graph_config` 구성(`460-469`)을 다음으로 교체. **run_name·tags·metadata는 tracker 유무와 무관하게 항상** 설정하고, callbacks는 tracer/usage-callback을 합친다.

```python
        # per-run LangSmith tracer (에이전트별 프로젝트). 전역 env 미변경 → race 없음.
        tracer = make_agent_run_tracer(
            agent.name, tags=["agent-platform", agent.id, agent.name],
        )

        callbacks: list = []
        if tracer is not None:
            callbacks.append(tracer)          # 전역 auto-tracer 억제(중복 방지)
        if callback is not None:
            callbacks.append(callback)        # UsageCallback (관측성)

        graph_config: dict = {
            "configurable": {"thread_id": session_id},
            "run_name": agent.name,            # LangSmith root run 이름 = 에이전트명
            "tags": ["agent-platform", agent.id, agent.name],
            "metadata": {
                "agent_id": agent.id,
                "agent_name": agent.name,      # 신규
                "conversation_id": session_id,
                "user_id": request.user_id,
            },
        }
        if run_id is not None:
            graph_config["metadata"]["run_id"] = run_id.value
        if callbacks:
            graph_config["callbacks"] = callbacks
        return graph, initial_state, graph_config
```

변경 요지:
- `run_name`, `tags`(+에이전트명), `metadata.agent_name` **항상** 설정 (기존엔 tracker 있을 때만 metadata/tags 설정).
- `callbacks`에 per-run tracer 추가(있으면) → 에이전트별 프로젝트로 기록.
- `run_id`는 있을 때만 metadata에 포함(관측성 비활성 시 None 회피).

#### 3.2.3 `stream()` 의 전역 `langsmith()` 호출

`run_agent_use_case.py:180` `langsmith(project_name="agent-run")`는 **유지**(전역 활성화/기타 경로). 에이전트 실행 프로젝트는 §3.2.2 tracer가 결정. (Plan §4의 "호출 이동" 항목은 race 회피를 위해 per-run tracer로 대체 — Design 정제.)

### 3.3 TraceExtractor 영향
`TraceExtractor.extract()`(get_current_run_tree)는 명시적 tracer 사용 시에도 현재 run tree contextvar가 설정되므로 동일 동작. `complete_run`의 `langsmith_run_url`/`trace_id` 회수 로직 변경 없음.

---

## 4. Test Plan (TDD)

### 4.1 `tests/infrastructure/langsmith/test_langsmith_helpers.py` (신규)
| 테스트 | 검증 |
|--------|------|
| `test_normalize_basic` | `"여신심사봇"` → `"agent-여신심사봇"` |
| `test_normalize_collapses_ws_and_empty` | 공백 다중→단일, 빈/None → `"agent-run"` |
| `test_normalize_truncates_long` | 128자 초과 절단 |
| `test_make_tracer_none_without_key` | 키 env 제거 시 `None` |
| `test_make_tracer_returns_tracer_with_project` | 키 set(monkeypatch) → `LangChainTracer`, `project_name=="agent-X"` |

### 4.2 `tests/application/agent_builder/test_run_agent_graph_config.py` (신규 또는 기존 보강)
`_prepare_graph`를 직접 호출(또는 compile/repo mock)하여 `graph_config` 검증:
| 테스트 | 검증 |
|--------|------|
| `test_graph_config_has_run_name_and_agent_name` | `run_name==agent.name`, `tags`에 `agent.name` 포함, `metadata["agent_name"]==agent.name` |
| `test_callbacks_include_tracer_when_key_set` | `make_agent_run_tracer` patch로 더미 tracer 반환 시 `graph_config["callbacks"]`에 포함 |
| `test_metadata_run_id_only_when_present` | tracker/run_id None이면 metadata에 `run_id` 키 없음 |

> Windows event-loop flakiness(메모리) → 신규 테스트는 **격리 실행**으로 검증.

### 4.3 회귀
- `tests/api/test_ws_agent_router.py`, `test_agent_builder_router_stream.py`, `test_agent_builder_router.py` 등 기존 stream/run 경로 GREEN 유지.

---

## 5. Implementation Order

```
Step 0: 진단 (코드 변경 전, 선택적이나 권장)
  └─ dev 서버 → 화면에서 WS(/ws/agent) 채팅 1회 → LangSmith run 도달/프로젝트명 기록(문서화)

Step 1: 테스트 작성 (RED, 격리 실행)
  ├─ tests/infrastructure/langsmith/test_langsmith_helpers.py
  └─ tests/application/agent_builder/test_run_agent_graph_config.py

Step 2: infrastructure — 헬퍼
  └─ src/infrastructure/langsmith/langsmith.py
       (normalize_agent_project_name, make_agent_run_tracer)

Step 3: application — _prepare_graph graph_config 보강
  └─ src/application/agent_builder/run_agent_use_case.py
       (import 추가, callbacks/run_name/tags/metadata 구성)

Step 4: 테스트 GREEN (격리 실행)

Step 5: dev 수동 검증 — WS/SSE/HTTP 각 1회 → LangSmith에
        agent-{이름} 프로젝트 + run_name=에이전트명 확인
```

---

## 6. 진단 절차 (Step 0 상세)
1. `uvicorn src.api.main:app --reload --port 8000`
2. 화면에서 에이전트 선택 → WS 채팅 1회
3. LangSmith: `agent-run`(또는 변경 후 `agent-{이름}`) 프로젝트에 run 도달 여부 + run 이름/태그 확인
4. 판정 → 정상이면 식별 보강만으로 종결, 미도달이면 env 이름 호환 이슈를 본 사이클로 승격 여부 사용자 재확인

---

## 7. Risk & Mitigation

| 리스크 | 심각도 | 대응 |
|--------|--------|------|
| 명시적 tracer + 전역 auto-tracer 중복 기록 | Low | langchain_core가 LangChainTracer 존재 시 전역 미추가(§2.3 검증). 중복 없음 |
| `agent.name` 비정상(빈/공백/초장문) | Low | `normalize_agent_project_name`에서 정규화·fallback·절단 |
| 프로젝트 수 급증 | Low | 사용자 명시 선택. 운영 수용 |
| LangChainTracer Client 생성 비용(매 run) | Low | best-effort, 예외 시 None. 추후 모듈 캐시 최적화 여지(범위 밖) |
| metadata/tags 항상 설정으로 인한 회귀 | Low | 추가 정보일 뿐 기존 키 유지. 테스트로 보장 |
| 진단에서 추적 미도달 판명 | Medium | env 이름 호환을 별도 결정으로 승격(Plan §2.2 Out of Scope 유지) |

---

## 8. Acceptance Criteria

- [ ] `make_agent_run_tracer`가 키 없을 때 `None`, 있을 때 `project_name="agent-{정규화}"` tracer 반환
- [ ] `normalize_agent_project_name` 정규화/fallback/절단 동작
- [ ] `_prepare_graph`의 `graph_config`에 `run_name=agent.name`, `tags`에 `agent.name`, `metadata["agent_name"]` 포함
- [ ] tracer 존재 시 `graph_config["callbacks"]`에 LangChainTracer 포함(전역 auto-tracer 억제로 중복 없음)
- [ ] 전역 `os.environ["LANGSMITH_PROJECT"]` 변경에 의존하지 않음(동시성 race 없음)
- [ ] HTTP `/run`, SSE `/run/stream`, WS `/ws/agent` 모두 동일 적용(공통 `stream()`)
- [ ] application이 `langchain_core` tracer를 직접 import하지 않음(infra 헬퍼 경유 — DDD)
- [ ] 신규/기존 테스트 통과(격리 실행)
- [ ] (수동) dev에서 `agent-{에이전트명}` 프로젝트 + run_name 확인
```
