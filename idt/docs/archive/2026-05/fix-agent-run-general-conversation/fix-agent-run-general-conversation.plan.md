# fix-agent-run-general-conversation Planning Document

> **Summary**: Agent Run API에서 일반 대화(인사, 감사 등)에 대해 FINISH로 즉시 종료되어 응답이 사용자 질문 그대로 반환되는 버그 수정
>
> **Project**: sangplusbot (idt)
> **Version**: 1.0
> **Author**: 배상규
> **Date**: 2026-05-18
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | `POST /api/v1/agents/{id}/run`에서 "고마워", "안녕" 등 일반 대화를 입력하면 supervisor가 즉시 FINISH를 반환하고, `_parse_result`가 마지막 메시지(사용자 원본 쿼리)를 answer로 그대로 반환 |
| **Solution** | supervisor decision_prompt에 일반 대화 직접 응답 경로 추가 + FINISH 시 LLM 직접 응답 생성 노드(fallback_answer) 도입 |
| **Function/UX Effect** | 도구 호출 불필요한 질문에도 에이전트가 자연스러운 대화 응답을 생성 |
| **Core Value** | 에이전트 사용자 경험 정상화 — 모든 유형의 질문에 적절한 응답 보장 |

---

## 1. Overview

### 1.1 Purpose

Agent Builder의 에이전트 실행 API(`POST /api/v1/agents/{agent_id}/run`)에서 도구 호출이 필요 없는 일반 대화 질문(인사, 감사, 간단한 질문 등)에 대해 자연스러운 응답을 생성하도록 수정한다.

### 1.2 Background

현재 supervisor 그래프 구조:
```
User Query → supervisor (LLM decision) → worker 선택 OR FINISH → END
```

supervisor의 `decision_prompt`(`supervisor_nodes.py:73-79`)는 두 가지 선택지만 제공:
1. **워커 호출**: 해당 worker_id 선택
2. **FINISH**: 모든 작업 완료 시 선택

"고마워" 같은 일반 대화가 들어오면:
- LLM이 "도구 필요 없음" → `FINISH` 반환
- `FINISH` → `__end__` 변환 → 그래프 종료
- `_parse_result()`가 `messages[-1]`을 answer로 추출
- 이 시점의 마지막 메시지는 사용자 원본 쿼리 → **질문이 그대로 응답으로 반환**

### 1.3 Scope

| In Scope | Out of Scope |
|----------|-------------|
| supervisor decision 로직에 일반 대화 응답 경로 추가 | PromptGenerator 전체 재설계 |
| FINISH 시 fallback 응답 생성 노드 추가 | 대화 메모리 정책 변경 |
| 기존 워커 라우팅 로직 보존 | 새로운 도구 추가 |
| 단위 테스트 추가 | UI 변경 |

---

## 2. Root Cause Analysis

### 2.1 문제 흐름 (현재)

```
1. User: "고마워"
2. RunAgentUseCase._build_messages() → [{"role": "user", "content": "고마워"}]
3. build_initial_state(messages=[...]) → SupervisorState
4. graph.ainvoke(initial_state)
5. supervisor_node():
   - decision_prompt = supervisor_prompt + worker_descriptions + "워커 호출 or FINISH"
   - LLM → SupervisorDecision(next="FINISH", reasoning="추가 정보 요청 없음...")
6. next_worker = "FINISH" → "__end__" (line 94-95)
7. 그래프 종료 → result = {"messages": [원본 user message], ...}
8. _parse_result(): messages[-1] = 원본 user message → answer = "고마워"
```

### 2.2 원인 요약

| 원인 | 위치 | 설명 |
|------|------|------|
| **1차**: decision_prompt에 직접 응답 경로 없음 | `supervisor_nodes.py:73-79` | "워커 호출 or FINISH"만 존재, 일반 대화 응답 옵션 없음 |
| **2차**: FINISH 시 응답 생성 없이 즉시 종료 | `supervisor_nodes.py:94-95` | `FINISH → __end__`로 바로 그래프 종료 |
| **3차**: 마지막 메시지가 user 메시지 | `run_agent_use_case.py:236-241` | AI 응답 없이 종료되어 user 메시지가 answer로 추출됨 |

---

## 3. Solution Design

### 3.1 접근 방식: fallback_answer 노드 추가

supervisor가 FINISH를 결정했을 때, 워커 실행 결과가 없으면(= 도구 없이 바로 FINISH) LLM이 직접 응답을 생성하는 `fallback_answer` 노드를 경유하도록 한다.

```
[변경 후 흐름]
User Query → supervisor → FINISH 결정
  → 워커 실행 이력 있음? → YES → __end__ (기존 동작)
  → 워커 실행 이력 없음? → YES → fallback_answer 노드 → __end__
```

### 3.2 변경 파일 목록

| 파일 | 변경 내용 |
|------|----------|
| `src/application/agent_builder/supervisor_nodes.py` | (1) `SupervisorDecision`에 `answer` 필드 추가, (2) supervisor_node에서 FINISH + answer 반환 시 AI 메시지 생성 |
| `src/application/agent_builder/workflow_compiler.py` | `fallback_answer` 노드 추가 + 라우팅 로직 수정 |
| `tests/api/test_agent_builder_router.py` | 일반 대화 응답 테스트 케이스 추가 |
| `tests/unit/test_supervisor_nodes.py` | supervisor_node FINISH + fallback 단위 테스트 |

### 3.3 상세 변경 사항

#### 3.3.1 supervisor_nodes.py — SupervisorDecision 수정

```python
class SupervisorDecision(BaseModel):
    next: str = Field(description="다음 호출할 worker_id 또는 'FINISH'")
    reasoning: str = Field(description="선택 이유")
    answer: str = Field(
        default="",
        description="FINISH 선택 시 사용자에게 전달할 직접 응답 (워커 불필요 시)",
    )
```

#### 3.3.2 supervisor_nodes.py — decision_prompt 수정

```python
decision_prompt = (
    f"{supervisor_prompt}\n\n"
    f"사용 가능한 워커:\n{worker_descriptions}\n\n"
    f"다음 중 선택하세요:\n"
    f"- 워커 호출이 필요하면 해당 worker_id를 선택\n"
    f"- 모든 작업이 완료되었거나 워커 호출이 필요 없으면 'FINISH'를 선택하고, "
    f"answer 필드에 사용자에게 전달할 응답을 작성하세요\n"
    f"스킵된 워커(사용 불가): {skipped}"
)
```

#### 3.3.3 supervisor_nodes.py — FINISH 시 AI 메시지 생성

```python
if next_worker == "FINISH":
    result = {"next_worker": "__end__", ...}
    # answer가 있으면 AI 메시지로 추가
    if decision.answer:
        from langchain_core.messages import AIMessage
        result["messages"] = [AIMessage(content=decision.answer)]
    return result
```

### 3.4 대안 검토

| 방안 | 장점 | 단점 | 선택 |
|------|------|------|------|
| **A. SupervisorDecision.answer 필드** | 최소 변경, LLM 한 번 호출로 해결 | structured output 스키마 변경 필요 | **채택** |
| B. fallback_answer 별도 노드 | 분리된 관심사 | 불필요한 LLM 추가 호출, 그래프 복잡도 증가 | 기각 |
| C. _parse_result 후처리 | 기존 코드 변경 최소 | 근본 원인 해결이 아닌 우회, answer 품질 낮음 | 기각 |

**방안 A 채택 이유**: supervisor LLM이 이미 사용자 쿼리와 컨텍스트를 분석하는 시점에 answer도 함께 생성하면 추가 LLM 호출 없이 자연스러운 응답을 얻을 수 있다. 그래프 구조 변경도 최소화된다.

---

## 4. Implementation Plan

### 4.1 TDD 순서

| Step | Task | Type |
|------|------|------|
| 1 | `tests/unit/test_supervisor_nodes.py` — FINISH + answer 필드 반환 테스트 작성 (Red) | Test |
| 2 | `SupervisorDecision`에 `answer` 필드 추가 + decision_prompt 수정 + FINISH 시 AIMessage 생성 (Green) | Impl |
| 3 | `tests/unit/test_supervisor_nodes.py` — 워커 호출 시 answer 무시 테스트 (Red→Green) | Test+Impl |
| 4 | `tests/api/test_agent_builder_router.py` — run API 일반 대화 응답 검증 테스트 추가 | Test |
| 5 | 통합 동작 확인 및 기존 테스트 전체 통과 확인 | Verify |

### 4.2 영향 범위

- **직접 영향**: `supervisor_nodes.py` (SupervisorDecision, create_supervisor_node)
- **간접 영향 없음**: `workflow_compiler.py`의 그래프 구조 변경 불필요 (FINISH → `__end__` 라우팅 기존 유지)
- **기존 동작 보존**: 워커 호출이 필요한 경우 `answer` 필드는 빈 문자열로 무시됨

### 4.3 Risk & Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| structured output 스키마 변경으로 LLM 응답 파싱 실패 | High | `answer` 필드에 default="" 설정, 파싱 실패 시 기존 fallback 로직 유지 |
| answer 품질이 낮을 수 있음 (supervisor prompt가 도구 중심) | Medium | decision_prompt에 "자연스러운 대화 응답" 명시 지시 추가 |
| 기존 워커 라우팅 동작 회귀 | High | 기존 테스트 전체 실행 + 워커 호출 케이스 별도 테스트 |

---

## 5. Test Strategy

### 5.1 단위 테스트

```
tests/unit/test_supervisor_nodes.py:
  - test_supervisor_finish_with_answer_creates_ai_message
  - test_supervisor_finish_without_answer_returns_empty
  - test_supervisor_worker_selection_ignores_answer
  - test_supervisor_decision_answer_field_default_empty
```

### 5.2 라우터 테스트 (기존 파일 확장)

```
tests/api/test_agent_builder_router.py:
  - TestRunAgent.test_run_agent_general_conversation_returns_answer
    → "고마워" 입력 시 answer가 쿼리와 다른 자연스러운 응답인지 검증
```

### 5.3 검증 기준

| 항목 | 기준 |
|------|------|
| 일반 대화 응답 | answer != query (사용자 질문 그대로 반환되지 않음) |
| 워커 호출 동작 | 기존 테스트 전체 통과 |
| FINISH + answer | AIMessage가 state.messages에 추가됨 |

---

## 6. Acceptance Criteria

- [ ] "고마워", "안녕", "오늘 날씨 어때?" 같은 일반 질문에 자연스러운 응답 반환
- [ ] 기존 도구 호출 워크플로우(검색, 엑셀 등) 정상 동작 유지
- [ ] 기존 테스트 전체 통과
- [ ] 새 단위 테스트 + 라우터 테스트 통과
