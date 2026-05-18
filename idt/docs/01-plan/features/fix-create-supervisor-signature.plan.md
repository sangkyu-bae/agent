# Plan: fix-create-supervisor-signature

## Executive Summary

| 항목 | 내용 |
|------|------|
| Feature | create_supervisor() 호출 시그니처 수정 |
| 작성일 | 2026-05-11 |
| 예상 소요 | 30분 |
| 영향 범위 | workflow_compiler.py, 관련 테스트 1개 |

| 관점 | 설명 |
|------|------|
| Problem | Agent Builder로 생성한 에이전트 실행 시 TypeError로 500 에러 발생 |
| Solution | langgraph-supervisor 0.0.31 API 시그니처에 맞게 호출부 수정 |
| Function UX Effect | 사용자가 빌드한 에이전트가 정상 실행되어 응답 반환 |
| Core Value | Agent Builder 핵심 기능(에이전트 실행)의 정상 동작 보장 |

---

## 1. 문제 분석

### 1.1 에러 요약

```
File "workflow_compiler.py", line 55, in compile
    supervisor = create_supervisor(
        llm,
        agents=worker_agents,
        system_prompt=workflow.supervisor_prompt,
    )
TypeError: create_supervisor() got multiple values for argument 'agents'
```

### 1.2 근본 원인

`langgraph-supervisor==0.0.31`의 `create_supervisor()` 시그니처가 변경됨:

```python
# 현재 시그니처 (0.0.31)
def create_supervisor(
    agents: list[Pregel],        # ← 첫 번째 positional
    *,                           # ← 이후 keyword-only
    model: Runnable,             # ← llm은 여기
    prompt: ...,                 # ← system_prompt가 아닌 prompt
    ...
)
```

코드에서 `llm`을 첫 번째 positional로 전달 → `agents` 파라미터에 바인딩됨.
동시에 `agents=worker_agents`를 keyword로 전달 → "multiple values" 에러.

추가로 `system_prompt` 파라미터명도 `prompt`로 변경됨.

### 1.3 영향 범위

| 파일 | 변경 사유 |
|------|-----------|
| `src/application/agent_builder/workflow_compiler.py` | 호출 시그니처 수정 |
| `tests/application/agent_builder/test_workflow_compiler.py` | mock 검증 업데이트 |

---

## 2. 수정 계획

### 2.1 workflow_compiler.py (Line 55-59)

**Before:**
```python
supervisor = create_supervisor(
    llm,
    agents=worker_agents,
    system_prompt=workflow.supervisor_prompt,
)
```

**After:**
```python
supervisor = create_supervisor(
    worker_agents,
    model=llm,
    prompt=workflow.supervisor_prompt,
)
```

### 2.2 변경 포인트 정리

| 변경 | Before | After |
|------|--------|-------|
| 첫 번째 positional | `llm` | `worker_agents` |
| model 전달 | positional | `model=llm` (keyword) |
| prompt 파라미터명 | `system_prompt` | `prompt` |

---

## 3. 테스트 계획

- [ ] `test_workflow_compiler.py` - mock에서 `create_supervisor` 호출 인자 검증 업데이트
- [ ] 수동 테스트: Agent Builder로 에이전트 생성 후 실행 → 정상 응답 확인

---

## 4. 주의사항

- `langgraph-supervisor` 버전 고정 필요 (`requirements.txt`에 `==0.0.31` 명시 확인)
- `prompt` 파라미터는 `str | SystemMessage | Callable` 타입 허용 — 현재 `workflow.supervisor_prompt`가 `str`이므로 호환됨
- `output_mode` 기본값이 `'last_message'`로 변경됨 — 기존 동작과 동일하므로 추가 조치 불필요
