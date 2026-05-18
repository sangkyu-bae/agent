# Design: fix-quality-gate-infinite-loop

## Executive Summary

| 항목 | 내용 |
|------|------|
| Feature | Quality Gate 무한루프 및 LangSmith 추적 불가 수정 |
| 작성일 | 2026-05-18 |
| 참조 Plan | `docs/01-plan/features/fix-quality-gate-infinite-loop.plan.md` |
| 영향 범위 | supervisor_nodes.py, supervisor_state.py, test_supervisor_nodes.py |

| 관점 | 설명 |
|------|------|
| Problem | quality_gate 통과 시 `next_worker`가 초기화되지 않아 동일 worker로 무한 재라우팅, LangSmith에서 gate 판정 결과 추적 불가 |
| Solution | quality_gate가 모든 경로에서 `next_worker: ""`를 명시 반환 + `quality_gate_result` 필드로 판정 메타데이터 기록 |
| Function UX Effect | 에이전트 실행이 정상 종료되고, LangSmith에서 각 worker의 품질 판정 결과를 즉시 확인 가능 |
| Core Value | Agent Builder 에이전트의 안정적 실행 보장 + 운영 디버깅 가능성 확보 |

---

## 1. 현재 코드 분석

### 1.1 그래프 토폴로지 (변경 없음)

```
[entry] → supervisor → (route_to_worker) → worker_N → quality_gate → (route_after_quality) → supervisor | worker_N
                     ↘ __end__                                                                ↗
```

그래프 구조(노드, 엣지)는 수정하지 않는다. 노드 내부 반환값과 state 필드만 수정한다.

### 1.2 버그 재현 흐름

| Step | Node | State 변화 | 문제 |
|------|------|-----------|------|
| 1 | supervisor | `next_worker="worker_0"` 설정 | - |
| 2 | route_to_worker | `"worker_0"` 반환 | - |
| 3 | worker_0 | `last_worker_id="worker_0"` | - |
| 4 | quality_gate | `return {}` (통과) | `next_worker="worker_0"` 잔존 |
| 5 | route_after_quality | `next_worker="worker_0"` 읽음 → `"worker_0"` 반환 | supervisor로 안 돌아감 |
| 6 | worker_0 | 다시 실행 | 무한루프 시작 |

### 1.3 기존 테스트 현황

`test_supervisor_nodes.py`의 4개 테스트가 `result == {}`를 기대 — 버그 동작을 검증 중:

| 테스트 | 라인 | 현재 assert | 수정 필요 |
|--------|------|------------|----------|
| `test_disabled_bypasses` | 231 | `result == {}` | Yes |
| `test_enabled_pass` | 249 | `result == {}` | Yes |
| `test_enabled_fail_max_retries_force_pass` | 290 | `result == {}` | Yes |
| `test_no_ai_message_bypasses` | 303 | `result == {}` | Yes |

---

## 2. 상세 설계

### 2.1 SupervisorState 필드 추가

**파일**: `src/application/agent_builder/supervisor_state.py`

```python
class SupervisorState(TypedDict):
    messages: Annotated[list, add_messages]

    iteration_count: int
    max_iterations: int
    token_usage: int
    token_limit: int

    next_worker: str
    last_worker_id: str
    available_workers: list[str]

    quality_gate_enabled: bool
    retry_counts: dict[str, int]
    max_retries_per_worker: int

    forced_worker: str
    skipped_workers: list[str]

    quality_gate_result: str          # ← 추가
```

**필드 스펙**:

| 필드 | 타입 | 초기값 | 가능한 값 | 용도 |
|------|------|--------|----------|------|
| `quality_gate_result` | `str` | `""` | `""`, `"passed"`, `"failed"`, `"skipped"`, `"max_retries"` | LangSmith 추적 + 디버깅 |

### 2.2 build_initial_state 수정

**파일**: `src/application/agent_builder/supervisor_nodes.py:12-31`

추가할 초기값:

```python
def build_initial_state(...) -> SupervisorState:
    return {
        ...
        "skipped_workers": [],
        "quality_gate_result": "",      # ← 추가
    }
```

### 2.3 quality_gate_node 반환값 수정

**파일**: `src/application/agent_builder/supervisor_nodes.py:110-162`

모든 `return {}` 경로를 `next_worker: ""` + `quality_gate_result` 포함으로 변경:

| 경로 | 조건 | 현재 반환 | 수정 후 반환 |
|------|------|----------|-------------|
| A | `quality_gate_enabled == False` | `{}` | `{"next_worker": "", "quality_gate_result": "skipped"}` |
| B | `last_ai_msg is None` | `{}` | `{"next_worker": "", "quality_gate_result": "skipped"}` |
| C | `is_acceptable == True` | `{}` | `{"next_worker": "", "quality_gate_result": "passed"}` |
| D | `current_retries >= max_retries` | `{}` | `{"next_worker": "", "quality_gate_result": "max_retries"}` |
| E | 실패 + 재시도 | `{next_worker: last_worker, ...}` | `{next_worker: last_worker, quality_gate_result: "failed", ...}` (기존 유지 + 필드 추가) |

**수정 후 전체 코드**:

```python
def create_quality_gate_node(
    policy: QualityGatePolicy,
    logger: LoggerInterface,
):
    async def quality_gate_node(state: SupervisorState) -> dict:
        if not state["quality_gate_enabled"]:
            return {"next_worker": "", "quality_gate_result": "skipped"}

        last_worker = state["last_worker_id"]
        messages = state["messages"]

        last_ai_msg = None
        for msg in reversed(messages):
            if hasattr(msg, "type") and msg.type == "ai":
                last_ai_msg = msg
                break

        if last_ai_msg is None:
            return {"next_worker": "", "quality_gate_result": "skipped"}

        is_acceptable = policy.check_response(last_ai_msg.content)

        if is_acceptable:
            logger.info("quality_gate passed", worker_id=last_worker)
            return {"next_worker": "", "quality_gate_result": "passed"}

        retry_counts = dict(state["retry_counts"])
        current_retries = retry_counts.get(last_worker, 0)

        if current_retries >= state["max_retries_per_worker"]:
            logger.warning(
                "quality_gate max_retries reached, forcing pass",
                worker_id=last_worker, retries=current_retries,
            )
            return {"next_worker": "", "quality_gate_result": "max_retries"}

        retry_counts[last_worker] = current_retries + 1
        feedback_msg = {
            "role": "user",
            "content": (
                f"[품질검증 실패] 응답이 기준에 미달합니다. "
                f"더 정확하고 구체적인 답변을 다시 생성해주세요. "
                f"(재시도 {current_retries + 1}/{state['max_retries_per_worker']})"
            ),
        }

        logger.info(
            "quality_gate failed, retrying",
            worker_id=last_worker, retry=current_retries + 1,
        )

        return {
            "messages": [feedback_msg],
            "retry_counts": retry_counts,
            "next_worker": last_worker,
            "quality_gate_result": "failed",
        }

    return quality_gate_node
```

### 2.4 route_after_quality (변경 없음)

현재 로직은 수정 후 정상 동작한다:

```python
def route_after_quality(state: SupervisorState) -> str:
    next_worker = state.get("next_worker", "")
    if next_worker and next_worker != "__end__":
        return next_worker    # quality_gate가 재시도 설정한 경우만 진입
    return "supervisor"       # next_worker="" 이면 여기로
```

- 통과/스킵 시: `next_worker=""` → `"supervisor"` 반환 (정상)
- 재시도 시: `next_worker="worker_0"` → `"worker_0"` 반환 (정상)

### 2.5 workflow_compiler.py (변경 없음)

그래프 토폴로지는 변경 불요. `quality_gate_result`는 `SupervisorState` 필드로만 흐르므로 `add_conditional_edges` 수정 없음.

---

## 3. 수정 후 흐름 검증

### 3.1 정상 통과 흐름

```
supervisor {next_worker="worker_0"}
  → worker_0 {last_worker_id="worker_0"}
    → quality_gate {next_worker="", quality_gate_result="passed"}
      → route_after_quality: next_worker="" → return "supervisor"  ✅
        → supervisor (다음 worker 결정 또는 FINISH)
```

### 3.2 재시도 흐름

```
supervisor {next_worker="worker_0"}
  → worker_0 {last_worker_id="worker_0", 품질 미달 응답}
    → quality_gate {next_worker="worker_0", quality_gate_result="failed", retry_counts +1}
      → route_after_quality: next_worker="worker_0" → return "worker_0"
        → worker_0 (재시도)
          → quality_gate {next_worker="", quality_gate_result="passed"}
            → route_after_quality → "supervisor"  ✅
```

### 3.3 비활성 흐름

```
supervisor {next_worker="worker_0"}
  → worker_0
    → quality_gate {next_worker="", quality_gate_result="skipped"}
      → route_after_quality → "supervisor"  ✅
```

### 3.4 재시도 한계 도달 흐름

```
quality_gate {next_worker="", quality_gate_result="max_retries"}
  → route_after_quality → "supervisor"  ✅
```

---

## 4. 테스트 설계

### 4.1 기존 테스트 수정 (4건)

| 테스트 | 수정 내용 |
|--------|----------|
| `test_disabled_bypasses` | `assert result == {}` → `assert result["next_worker"] == ""` + `assert result["quality_gate_result"] == "skipped"` |
| `test_enabled_pass` | `assert result == {}` → `assert result["next_worker"] == ""` + `assert result["quality_gate_result"] == "passed"` |
| `test_enabled_fail_max_retries_force_pass` | `assert result == {}` → `assert result["next_worker"] == ""` + `assert result["quality_gate_result"] == "max_retries"` |
| `test_no_ai_message_bypasses` | `assert result == {}` → `assert result["next_worker"] == ""` + `assert result["quality_gate_result"] == "skipped"` |

### 4.2 기존 테스트 보강 (1건)

| 테스트 | 추가 assert |
|--------|------------|
| `test_enabled_fail_retry` | `assert result["quality_gate_result"] == "failed"` 추가 |

### 4.3 신규 테스트 (2건)

| TC | 테스트명 | 시나리오 | 검증 |
|----|---------|---------|------|
| TC-NEW-1 | `test_pass_resets_next_worker` | supervisor→worker→quality_gate(pass) 후 `route_after_quality` 호출 | `route_after_quality` 반환값 == `"supervisor"` |
| TC-NEW-2 | `test_build_initial_state_has_quality_gate_result` | `build_initial_state` 호출 | `state["quality_gate_result"] == ""` |

**TC-NEW-1 상세** (무한루프 방지 통합 검증):

```python
@pytest.mark.asyncio
async def test_pass_resets_next_worker(self):
    """quality_gate 통과 후 route_after_quality가 supervisor로 라우팅."""
    from src.application.agent_builder.supervisor_nodes import (
        create_quality_gate_node,
        route_after_quality,
    )

    ai_msg = MagicMock()
    ai_msg.type = "ai"
    ai_msg.content = "검색 결과입니다. 최신 AI 뉴스를 정리했습니다."

    fn = create_quality_gate_node(policy=QualityGatePolicy(), logger=MagicMock())
    state = _make_state(
        quality_gate_enabled=True,
        last_worker_id="worker_0",
        next_worker="worker_0",       # supervisor가 설정한 값이 잔존
        messages=[ai_msg],
    )
    result = await fn(state)

    # quality_gate가 next_worker를 초기화했는지 확인
    assert result["next_worker"] == ""

    # state를 업데이트한 후 route_after_quality 검증
    updated_state = {**state, **result}
    assert route_after_quality(updated_state) == "supervisor"
```

---

## 5. 구현 순서 (체크리스트)

| # | 작업 | 파일 | TDD 단계 |
|---|------|------|---------|
| 1 | `SupervisorState`에 `quality_gate_result: str` 추가 | `supervisor_state.py` | - |
| 2 | `build_initial_state`에 `quality_gate_result: ""` 추가 | `supervisor_nodes.py:17-31` | - |
| 3 | 기존 테스트 4건 수정 + TC-NEW-1, TC-NEW-2 작성 (Red) | `test_supervisor_nodes.py` | Red |
| 4 | `quality_gate_node` 반환값 수정 (5개 경로) | `supervisor_nodes.py:110-162` | Green |
| 5 | 테스트 실행 확인 | - | Green |
| 6 | 불필요한 중복 제거 (있다면) | - | Refactor |

---

## 6. LangSmith 추적 효과

수정 전후 LangSmith trace 비교:

**수정 전**:
```
supervisor → worker_0 → quality_gate (state diff: 없음) → worker_0 → quality_gate → ...
```
- quality_gate 노드에 state 변경 기록 없음
- pass/fail 구분 불가
- 무한루프로 trace가 끝나지 않음

**수정 후**:
```
supervisor → worker_0 → quality_gate (state diff: {next_worker: "", quality_gate_result: "passed"}) → supervisor → FINISH
```
- 매 quality_gate 실행마다 `quality_gate_result` 필드가 state diff에 기록
- LangSmith UI에서 각 worker 응답의 품질 판정 결과 즉시 확인 가능
- 정상 종료

---

## 7. 주의사항

- `workflow_compiler.py`의 `route_map` 수정 불요 — `quality_gate_result`는 conditional edge에 사용되지 않음
- `_wrap_worker`, `_wrap_sub_agent`, `_create_search_node`은 `quality_gate_result`를 설정하지 않음 (quality_gate_node 전용 필드)
- `SupervisorConfig`는 수정 불요 — `quality_gate_enabled` 설정은 기존 그대로 유지
