# supervisor-custom-loop Planning Document

> **Summary**: Agent Builder의 WorkflowCompiler를 Custom StateGraph 기반 Supervisor로 전환하여 내부루프 커스텀 로직(품질검증, 조건부 워커 선택/스킵, 반복·토큰 제한)을 지원
>
> **Project**: sangplusbot (idt)
> **Version**: 1.0
> **Author**: 배상규
> **Date**: 2026-05-11
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 현재 `WorkflowCompiler`는 `create_supervisor()`를 블랙박스로 사용하여 워커 응답 품질검증, 조건부 라우팅, 반복 제한 등 내부루프 커스텀 로직을 삽입할 수 없음 |
| **Solution** | `create_supervisor`를 제거하고 `StateGraph`로 Supervisor 그래프를 직접 구성하여, 노드 단위로 커스텀 로직(품질게이트, 조건부 스킵, 반복제한)을 삽입할 수 있는 확장 가능한 아키텍처 구축 |
| **Function/UX Effect** | 에이전트가 워커 응답을 자체 검증·재시도하여 최종 답변 품질이 향상되고, 무한루프 방지로 안정성 확보 |
| **Core Value** | 금융/정책 도메인에서 요구하는 보수적·정확한 응답 품질을 Supervisor 내부 루프 레벨에서 보장 |

---

## 1. Overview

### 1.1 Purpose

Agent Builder로 생성된 에이전트 실행 시 `WorkflowCompiler`가 생성하는 LangGraph 그래프를 `create_supervisor()` 의존에서 벗어나, Custom StateGraph 기반 Supervisor 패턴으로 전환한다. 이를 통해 Supervisor의 워커 위임 루프 내부에 다양한 커스텀 로직을 코드 레벨로 삽입할 수 있게 한다.

### 1.2 Background

**현재 구조의 한계:**
- `WorkflowCompiler.compile()`은 `langgraph_supervisor.create_supervisor()`에 `(workers, model, prompt)` 3개 인자만 전달
- Supervisor 내부의 워커 선택 → 호출 → 응답 수집 루프를 제어할 수 없음
- `flow_hint` 필드가 도메인에 존재하지만 컴파일 시 사용되지 않음
- `max_iterations` 파라미터가 `GeneralChatUseCase`에 존재하지만 미사용

**프로젝트 내 선례:**
- `SelfCorrectiveRAGWorkflow` (`research_agent/workflow.py`): StateGraph + conditional edges + retry loop 패턴 이미 구현됨
- `DocumentProcessingGraph` (`infrastructure/pipeline/graph/`): 커스텀 노드 + 에러 분기 패턴

### 1.3 Related Documents

- 대화 메모리 정책: `docs/rules/conversation-memory.md`
- 로깅 규칙: `docs/rules/logging.md`
- Agent Builder 스키마: `src/domain/agent_builder/schemas.py`
- 참고 구현: `src/application/research_agent/workflow.py`

---

## 2. Scope

### 2.1 In Scope (Phase 1)

- [ ] `create_supervisor` 제거, Custom StateGraph 기반 Supervisor 그래프 구성
- [ ] **품질 게이트**: Supervisor가 워커 응답을 받은 뒤 품질검증 노드를 거쳐 불합격 시 재호출
- [ ] **조건부 워커 선택/스킵**: Supervisor의 LLM 판단 외에 코드 레벨 규칙으로 특정 워커 강제 호출 또는 스킵
- [ ] **반복 횟수/토큰 제한**: Supervisor 루프의 max_iterations, 토큰 소비량 제한, 타임아웃
- [ ] 전체 마이그레이션: 기존 DB 에이전트도 새 컴파일러로 동작
- [ ] 기존 `RunAgentUseCase` + multi-turn 대화 기능과의 호환 유지

### 2.2 In Scope (Phase 2 — 후속)

- [ ] **워커 간 데이터 파이프라인**: 워커 A 결과를 변환/가공해서 워커 B에 전달하는 중간 처리 노드
- [ ] 워커별 개별 프롬프트 커스터마이징
- [ ] 실행 중간 결과 스트리밍

### 2.3 Out of Scope

- 프론트엔드 UI 변경
- 새로운 DB 테이블 생성 (기존 스키마로 충분)
- Agent Builder의 에이전트 생성 플로우 변경 (CreateAgentUseCase)
- Human-in-the-Loop 인터뷰 플로우 변경

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | `WorkflowCompiler.compile()`이 Custom StateGraph 기반 Supervisor 그래프를 반환 | High | Pending |
| FR-02 | Supervisor 노드가 LLM을 호출하여 다음 워커를 선택하거나 종료를 결정 | High | Pending |
| FR-03 | 각 워커 노드 실행 후 품질검증 노드(quality_gate)를 거침 | High | Pending |
| FR-04 | 품질검증 실패 시 동일 워커 재호출 (최대 재시도 횟수 제한) | High | Pending |
| FR-05 | 코드 레벨 규칙으로 특정 워커를 강제 호출하거나 스킵할 수 있는 hook 지점 제공 | Medium | Pending |
| FR-06 | Supervisor 루프 전체의 max_iterations 제한 (기본값 10, 설정 가능) | High | Pending |
| FR-07 | 총 토큰 소비량이 임계값 초과 시 루프 강제 종료 | Medium | Pending |
| FR-08 | 기존 DB 에이전트가 새 컴파일러에서 정상 동작 (전체 마이그레이션) | High | Pending |
| FR-09 | `langgraph_supervisor` 패키지 의존성 제거 | Low | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 성능 | 기존 대비 응답 지연 증가 < 200ms (품질검증 미적용 시) | 로그 타이밍 비교 |
| 확장성 | 새로운 커스텀 노드를 추가할 때 WorkflowCompiler 외 변경 없음 | 코드 리뷰 |
| 안정성 | max_iterations 초과 시 graceful 종료 + 중간 결과 반환 | 통합 테스트 |
| 하위호환 | 기존 에이전트 실행 결과가 동일 (품질게이트 비활성 시) | A/B 비교 테스트 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] `create_supervisor` 호출 완전 제거, Custom StateGraph로 대체
- [ ] 품질검증 비활성 상태에서 기존 에이전트와 동일한 응답 생성
- [ ] 품질검증 활성 시 워커 응답 재시도 동작 확인
- [ ] max_iterations=3으로 설정 시 3회 루프 후 종료 확인
- [ ] 조건부 워커 스킵 규칙 동작 확인
- [ ] 기존 RunAgentUseCase 테스트 + multi-turn 테스트 통과
- [ ] 단위 테스트 작성 및 통과

### 4.2 Quality Criteria

- [ ] 테스트 커버리지 80% 이상 (WorkflowCompiler, 각 노드 함수)
- [ ] DDD 레이어 규칙 준수: domain에서 LangGraph 직접 참조 금지
- [ ] LOG-001 규칙: 모든 노드에서 request_id 기반 구조화 로깅

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Custom StateGraph 복잡도 증가로 디버깅 난이도 상승 | Medium | High | 각 노드를 독립 함수로 분리, LangSmith 트레이싱 연동 |
| 기존 에이전트 응답 품질 변화 (미묘한 차이) | Medium | Medium | 품질게이트 off 모드를 기본으로 설정, 점진적 활성화 |
| Supervisor LLM 판단과 코드 규칙 충돌 | Medium | Medium | 코드 규칙 우선 정책 명확화, 규칙 적용 시 로그 기록 |
| 토큰 제한 로직의 정확한 토큰 수 계산 어려움 | Low | Medium | tiktoken 기반 추정 + 안전 마진 20% |
| `langgraph_supervisor` 제거 시 놓치는 edge case | High | Low | 기존 테스트 전수 실행 + integration test 추가 |

---

## 6. Architecture Considerations

### 6.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| **Starter** | Simple structure | Static sites | ☐ |
| **Dynamic** | Feature-based modules, BaaS | Web apps | ☐ |
| **Enterprise** | Strict layer separation, DI | High-traffic systems | ☑ |

### 6.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| Supervisor 구현 | create_supervisor / Custom StateGraph | Custom StateGraph | 내부루프 완전 제어, 노드별 커스텀 로직 삽입 가능 |
| 하위호환 | flow_hint 분기 / 전체 마이그레이션 | 전체 마이그레이션 | 코드 분기 복잡도 제거, 단일 경로 유지보수 |
| 품질게이트 위치 | 워커 내부 / 워커 후 별도 노드 | 워커 후 별도 노드 | 워커와 품질검증 관심사 분리, 재사용 가능 |
| 상태 관리 | messages만 / 전용 SupervisorState | 전용 SupervisorState | iteration_count, token_usage 등 루프 제어 상태 필요 |
| 커스텀 로직 확장 | 상속 / Hook 함수 주입 | Hook 함수 주입 | 조합 가능성 높음, 테스트 용이 |

### 6.3 Custom StateGraph Supervisor 아키텍처

```
┌─────────────────────────────────────────────────────────┐
│                  SupervisorState                         │
│  messages, iteration_count, max_iterations,              │
│  token_usage, token_limit, active_workers,               │
│  last_worker_result, retry_count_per_worker              │
└─────────────────────────────────────────────────────────┘

Entry
  │
  ▼
┌──────────────┐     route_to_worker()      ┌──────────────┐
│  supervisor  │ ──────────────────────────► │  worker_{N}  │
│  (LLM 판단) │ ◄── "__end__" ──┐          │ (ReAct Agent)│
└──────────────┘                 │          └──────┬───────┘
  ▲                              │                 │
  │ "pass"                       │                 ▼
  │                              │          ┌──────────────┐
  │                              │          │ quality_gate │
  │                              │          │ (검증 노드)  │
  │                              │          └──────┬───────┘
  │                              │                 │
  │         ┌────────────────────┤          route_after_quality()
  │         │                    │                 │
  │    "retry"              "max_reached"     "pass" │
  │         │                    │                 │
  │         ▼                    ▼                 │
  │   worker_{N}               END                 │
  │   (재호출)                                     │
  └────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  Pre-route Hooks (FR-05):                                │
│  - force_worker(state) → str | None                      │
│  - skip_workers(state) → list[str]                       │
│  - Supervisor LLM이 선택한 워커를 override 가능           │
│                                                          │
│  Loop Guards (FR-06, FR-07):                             │
│  - iteration_count >= max_iterations → END               │
│  - token_usage >= token_limit → END                      │
└─────────────────────────────────────────────────────────┘
```

### 6.4 Clean Architecture 변경 범위

```
src/
├── domain/agent_builder/
│   ├── schemas.py               ← 수정: SupervisorConfig 추가 (max_iterations, token_limit 등)
│   └── policies.py              ← 수정: QualityGatePolicy 추가 (품질검증 규칙)
├── application/agent_builder/
│   ├── workflow_compiler.py     ← 수정: Custom StateGraph 기반 compile() 전면 재작성
│   ├── supervisor_nodes.py      ← 신규: supervisor_node, quality_gate_node, 각 노드 함수
│   ├── supervisor_state.py      ← 신규: SupervisorState TypedDict 정의
│   ├── supervisor_hooks.py      ← 신규: Hook 인터페이스 + 기본 구현 (force_worker, skip_workers)
│   └── run_agent_use_case.py    ← 수정: SupervisorConfig 전달
├── infrastructure/agent_builder/
│   └── tool_factory.py          ← 변경 없음
└── tests/application/agent_builder/
    ├── test_workflow_compiler.py ← 수정: Custom StateGraph 테스트로 전환
    ├── test_supervisor_nodes.py  ← 신규: 각 노드 단위 테스트
    └── test_supervisor_hooks.py  ← 신규: Hook 로직 테스트
```

---

## 7. Implementation Strategy

### 7.1 변경 파일 목록

| 파일 | 변경 유형 | 설명 |
|------|----------|------|
| `src/domain/agent_builder/schemas.py` | 수정 | `SupervisorConfig` dataclass 추가 (max_iterations, token_limit, quality_gate_enabled 등) |
| `src/domain/agent_builder/policies.py` | 수정 | `QualityGatePolicy` 추가 (응답 검증 규칙, 재시도 판단) |
| `src/application/agent_builder/supervisor_state.py` | 신규 | `SupervisorState(TypedDict)` 정의 |
| `src/application/agent_builder/supervisor_nodes.py` | 신규 | supervisor_node, quality_gate_node, route 함수들 |
| `src/application/agent_builder/supervisor_hooks.py` | 신규 | Hook 프로토콜 + DefaultHooks 구현 |
| `src/application/agent_builder/workflow_compiler.py` | 수정 | `compile()` 전면 재작성 — StateGraph 기반 |
| `src/application/agent_builder/run_agent_use_case.py` | 수정 | SupervisorConfig 조립·전달 |
| `pyproject.toml` | 수정 | `langgraph-supervisor` 의존성 제거 |
| `tests/application/agent_builder/test_workflow_compiler.py` | 수정 | Custom StateGraph 검증 테스트 |
| `tests/application/agent_builder/test_supervisor_nodes.py` | 신규 | 노드별 단위 테스트 |
| `tests/application/agent_builder/test_supervisor_hooks.py` | 신규 | Hook 로직 테스트 |

### 7.2 구현 순서

1. **SupervisorState 정의** — `supervisor_state.py`: 루프 제어에 필요한 상태 필드 정의
2. **SupervisorConfig 도메인 모델** — `schemas.py`: max_iterations, token_limit, quality_gate 설정
3. **QualityGatePolicy** — `policies.py`: 품질검증 규칙 (도메인 레이어)
4. **Hook 프로토콜** — `supervisor_hooks.py`: force_worker, skip_workers 확장 지점
5. **노드 함수 구현** — `supervisor_nodes.py`: supervisor_node, quality_gate_node, worker wrapping
6. **WorkflowCompiler 재작성** — `workflow_compiler.py`: StateGraph 조립 로직
7. **RunAgentUseCase 연결** — SupervisorConfig 조립 및 전달
8. **테스트 작성** — 각 단계별 TDD
9. **`langgraph-supervisor` 의존성 제거** — pyproject.toml 수정

### 7.3 SupervisorState 설계 (핵심)

```python
class SupervisorState(TypedDict):
    messages: Annotated[list, add_messages]  # LangGraph 메시지 리스트
    iteration_count: int                      # 현재 루프 반복 횟수
    max_iterations: int                       # 최대 반복 횟수 (기본 10)
    token_usage: int                          # 누적 토큰 소비량 (추정)
    token_limit: int                          # 토큰 상한 (기본 8000)
    next_worker: str | None                   # Supervisor가 선택한 다음 워커
    last_worker_id: str | None                # 마지막 실행 워커 ID
    retry_counts: dict[str, int]              # 워커별 재시도 횟수
    max_retries_per_worker: int               # 워커당 최대 재시도 (기본 2)
    quality_gate_enabled: bool                # 품질게이트 활성 여부
    forced_worker: str | None                 # Hook에 의한 강제 워커 지정
    skipped_workers: list[str]                # Hook에 의한 스킵 워커 목록
```

### 7.4 노드 흐름 상세

```
[supervisor_node]
  │
  ├─ iteration_count >= max_iterations → "__end__"
  ├─ token_usage >= token_limit → "__end__"
  ├─ Hook: forced_worker 있으면 → 해당 워커로 직행
  ├─ LLM 판단 → next_worker 결정
  ├─ Hook: next_worker가 skipped_workers에 포함 → 다음 후보로 재선택
  └─ next_worker == "__end__" → END
  
[worker_{N}_node]
  │ (create_react_agent로 생성된 워커 실행)
  ▼
  
[quality_gate_node]
  │
  ├─ quality_gate_enabled == false → "pass" (바이패스)
  ├─ QualityGatePolicy.check(response) == pass → "pass"
  ├─ retry_counts[worker_id] >= max_retries → "max_reached" (강제 통과)
  └─ check == fail → "retry" (워커 재호출, retry_count 증가)
```

---

## 8. Phase 2 확장 포인트 (후속 작업 가이드)

Phase 1 완료 후 아래 항목을 추가할 때 변경 최소화되도록 설계한다:

| 확장 | 변경 예상 위치 | 방법 |
|------|--------------|------|
| 워커 간 데이터 파이프라인 | `supervisor_nodes.py` + `supervisor_hooks.py` | `transform_result` Hook 추가, 워커→품질게이트 사이에 transform 노드 삽입 |
| 워커별 개별 프롬프트 | `WorkerDefinition` + `supervisor_nodes.py` | worker_prompt 필드 추가, create_react_agent의 prompt 파라미터에 전달 |
| 실행 중간 결과 스트리밍 | `run_agent_use_case.py` | `graph.astream()` 전환 |
| Human-in-the-Loop 승인 | `supervisor_hooks.py` | `require_approval` Hook + interrupt 노드 |

---

## 9. Next Steps

1. [ ] Design 문서 작성 (`supervisor-custom-loop.design.md`)
2. [ ] TDD: SupervisorState + 노드 함수 테스트 먼저 작성
3. [ ] 구현 및 Gap 분석

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-05-11 | Initial draft | 배상규 |
