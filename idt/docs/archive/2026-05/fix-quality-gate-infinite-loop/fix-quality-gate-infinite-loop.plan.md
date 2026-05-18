# Plan: fix-quality-gate-infinite-loop

## Executive Summary

| 항목 | 내용 |
|------|------|
| Feature | Quality Gate 무한루프 및 LangSmith 추적 불가 수정 |
| 작성일 | 2026-05-18 |
| 예상 소요 | 1~2시간 |
| 영향 범위 | supervisor_nodes.py, supervisor_state.py, workflow_compiler.py, 관련 테스트 |

| 관점 | 설명 |
|------|------|
| Problem | quality_gate 통과 시 `next_worker`가 초기화되지 않아 동일 worker로 무한 재라우팅, LangSmith에서 gate 판정 결과 추적 불가 |
| Solution | quality_gate가 모든 경로에서 `next_worker: ""`를 명시 반환 + gate 판정 메타데이터를 state에 기록 |
| Function UX Effect | 에이전트 실행이 정상 종료되고, LangSmith에서 각 worker의 품질 판정 결과를 즉시 확인 가능 |
| Core Value | Agent Builder 에이전트의 안정적 실행 보장 + 운영 디버깅 가능성 확보 |

---

## 1. 문제 분석

### 1.1 무한루프 발생 메커니즘

```
supervisor (next_worker="worker_1")
  → worker_1 (실행, last_worker_id="worker_1")
    → quality_gate (통과 → return {})     ← next_worker 초기화 안됨!
      → route_after_quality (next_worker="worker_1" 읽음)
        → worker_1 (다시 실행!)
          → quality_gate → route_after_quality → worker_1 → ... ∞
```

### 1.2 근본 원인 3가지

**원인 1: `quality_gate_node`가 통과 시 빈 dict 반환** (`supervisor_nodes.py:116,128,143`)

```python
# 현재 코드 — 3곳 모두 동일
if not state["quality_gate_enabled"]:
    return {}          # next_worker 그대로 유지

if last_ai_msg is None:
    return {}          # next_worker 그대로 유지

if is_acceptable:
    return {}          # next_worker 그대로 유지 ← 핵심 버그
```

LangGraph StateGraph에서 노드가 `{}`를 반환하면 state 업데이트가 없으므로, supervisor가 설정한 `next_worker="worker_1"`이 그대로 남는다.

**원인 2: `route_after_quality`가 잔존하는 `next_worker`를 그대로 사용** (`supervisor_nodes.py:169-173`)

```python
def route_after_quality(state: SupervisorState) -> str:
    next_worker = state.get("next_worker", "")
    if next_worker and next_worker != "__end__":
        return next_worker    # ← stale next_worker="worker_1"로 재라우팅
    return "supervisor"
```

이 함수의 의도는 "quality_gate가 재시도를 요청했을 때만 해당 worker로 라우팅"인데, 통과 시에도 stale 값이 남아있어 무조건 worker로 돌아간다.

**원인 3: LangSmith 추적 불가**

`quality_gate_node`가 `{}`를 반환하면 LangSmith trace에 아무 데이터도 기록되지 않아:
- 품질 검증이 실행되었는지 여부 확인 불가
- pass/fail/skip 판정 결과 확인 불가
- 어떤 worker의 응답이 검증되었는지 파악 불가

### 1.3 영향 범위

| 파일 | 수정 내용 |
|------|----------|
| `src/application/agent_builder/supervisor_nodes.py` | quality_gate_node 반환값 수정, route_after_quality 로직 강화 |
| `src/application/agent_builder/supervisor_state.py` | (선택) `quality_gate_result` 필드 추가 |
| `src/application/agent_builder/workflow_compiler.py` | (수정 없을 가능성 높음, 그래프 구조는 유지) |
| `tests/` | quality_gate 통과/실패/비활성 시나리오 테스트 |

---

## 2. 수정 방안

### 2.1 핵심 수정: quality_gate_node 반환값

모든 return 경로에서 `next_worker: ""`를 명시 반환하여 stale 값 제거:

```python
# (A) 비활성 시
if not state["quality_gate_enabled"]:
    return {"next_worker": ""}

# (B) AI 메시지 없음
if last_ai_msg is None:
    return {"next_worker": ""}

# (C) 통과 시
if is_acceptable:
    return {"next_worker": ""}

# (D) 실패 + 재시도 한계 시
if current_retries >= state["max_retries_per_worker"]:
    return {"next_worker": ""}

# (E) 실패 + 재시도 — 기존대로 next_worker=last_worker 유지
return {
    "messages": [feedback_msg],
    "retry_counts": retry_counts,
    "next_worker": last_worker,
}
```

### 2.2 route_after_quality 방어 로직 강화

현재 로직은 수정 후에도 정상 작동하지만, 의도를 명확히 하기 위해 주석 및 로깅 추가:

```python
def route_after_quality(state: SupervisorState) -> str:
    next_worker = state.get("next_worker", "")
    if next_worker and next_worker != "__end__":
        return next_worker  # quality_gate가 재시도 요청한 경우만 여기 진입
    return "supervisor"
```

### 2.3 LangSmith 추적용 state 필드 추가 (선택)

`SupervisorState`에 `quality_gate_result` 필드를 추가하여 판정 메타데이터 기록:

```python
# supervisor_state.py
class SupervisorState(TypedDict):
    ...
    quality_gate_result: str  # "passed" | "failed" | "skipped" | "max_retries"
```

각 반환 경로에서 해당 필드 설정:

```python
return {"next_worker": "", "quality_gate_result": "passed"}
return {"next_worker": "", "quality_gate_result": "skipped"}
return {"next_worker": "", "quality_gate_result": "max_retries"}
return {"next_worker": last_worker, "quality_gate_result": "failed", ...}
```

---

## 3. 구현 순서

| # | 작업 | 파일 | 우선순위 |
|---|------|------|---------|
| 1 | quality_gate_node 빈 반환값을 `{"next_worker": ""}` 으로 수정 | supervisor_nodes.py | **P0 (필수)** |
| 2 | quality_gate_result state 필드 추가 | supervisor_state.py | P1 |
| 3 | quality_gate_node에 result 필드 포함하여 반환 | supervisor_nodes.py | P1 |
| 4 | 로거 호출에 result 정보 포함 | supervisor_nodes.py | P1 |
| 5 | 테스트: 통과 시 next_worker 초기화 확인 | tests/ | **P0 (필수)** |
| 6 | 테스트: 실패→재시도 시 next_worker=last_worker 확인 | tests/ | P0 |
| 7 | 테스트: 비활성 시 next_worker 초기화 확인 | tests/ | P1 |
| 8 | 테스트: route_after_quality 라우팅 검증 | tests/ | P0 |

---

## 4. 정상 동작 흐름 (수정 후)

```
supervisor (next_worker="worker_1")
  → worker_1 (실행, last_worker_id="worker_1")
    → quality_gate (통과 → return {"next_worker": "", "quality_gate_result": "passed"})
      → route_after_quality (next_worker="" → return "supervisor")
        → supervisor (다음 worker 결정 또는 FINISH)
```

```
supervisor (next_worker="worker_1")
  → worker_1 (품질 미달 응답)
    → quality_gate (실패 → return {"next_worker": "worker_1", "quality_gate_result": "failed"})
      → route_after_quality (next_worker="worker_1" → return "worker_1")
        → worker_1 (재시도)
```

---

## 5. 주의사항

- `build_initial_state`에서 `quality_gate_result` 초기값 `""` 추가 필요
- 기존 `SupervisorConfig`는 수정 불요 (quality_gate_enabled 설정은 그대로 유지)
- `workflow_compiler.py`의 그래프 토폴로지(노드/엣지)는 변경 없음 — 노드 내부 반환값만 수정
- LangSmith trace에서 `quality_gate_result` 필드가 state diff로 표시되어 디버깅 용이해짐
