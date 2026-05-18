# multi-agent-composition Planning Document

> **Summary**: 기존 Tool 기반 단일 에이전트 조합 구조를 확장하여, 복수의 에이전트(Sub-Agent)를 워커로 엮어 하나의 상위 에이전트를 구성하는 멀티 에이전트 조합 기능 구현
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
| **Problem** | 현재 에이전트 빌더는 Tool(웹검색, 문서검색 등)만 워커로 조합하여 에이전트를 생성할 수 있어, 복잡한 업무 흐름(예: 문서분석 에이전트 → 요약 에이전트 → 보고서 생성 에이전트)을 하나의 에이전트로 구성할 수 없음 |
| **Solution** | WorkerDefinition에 `worker_type` 필드를 추가하여 `tool`과 `sub_agent` 두 유형을 지원하고, WorkflowCompiler가 sub_agent 유형 워커를 만나면 해당 에이전트의 전체 그래프를 재귀적으로 컴파일하여 노드로 삽입하는 구조 |
| **Function/UX Effect** | 사용자가 기존에 만든 에이전트들을 레고 블록처럼 조합하여 더 강력한 멀티 에이전트를 생성할 수 있고, Task 위임 방식으로 각 서브 에이전트가 독립적으로 실행되어 결과만 상위 에이전트에 반환 |
| **Core Value** | 에이전트 재사용성 극대화 및 복잡한 업무 파이프라인의 자동화, 금융/정책 도메인에서 전문 에이전트를 조합한 멀티스텝 분석 워크플로우 지원 |

---

## 1. Overview

### 1.1 Purpose

에이전트 빌더로 생성된 기존 에이전트를 서브 에이전트로 참조하여, "에이전트 + 에이전트 + 에이전트" 형태의 멀티 에이전트 조합을 가능하게 한다.

### 1.2 Background

**현재 구조:**
```
AgentDefinition
├── system_prompt (Supervisor 역할)
├── workers: [WorkerDefinition, ...]
│   ├── tool_id: "internal_document_search"  →  ToolFactory.create() → BaseTool
│   ├── tool_id: "tavily_search"             →  ToolFactory.create() → BaseTool
│   └── tool_id: "excel_export"              →  ToolFactory.create() → BaseTool
└── WorkflowCompiler.compile()
    └── StateGraph: Supervisor → Worker(ReactAgent+Tool) → QualityGate → ...
```

**목표 구조:**
```
AgentDefinition (상위 에이전트)
├── system_prompt (Supervisor 역할)
├── workers: [WorkerDefinition, ...]
│   ├── worker_type: "tool",      tool_id: "tavily_search"
│   ├── worker_type: "sub_agent", ref_agent_id: "agent-uuid-1"  (문서분석 에이전트)
│   └── worker_type: "sub_agent", ref_agent_id: "agent-uuid-2"  (요약 에이전트)
└── WorkflowCompiler.compile()
    └── StateGraph:
        Supervisor → Worker(Tool) or SubAgentWorker(compiled sub-graph) → QualityGate → ...
```

### 1.3 Scope

**In-Scope:**
- WorkerDefinition 도메인 모델에 `worker_type` + `ref_agent_id` 필드 추가
- WorkflowCompiler에서 sub_agent 유형 워커 컴파일 로직
- 순환참조(A→B→A) 방지 정책
- 중첩 깊이 제한 (현재 2단계, 확장 가능한 설계)
- Tool + Sub-Agent 혼합 워커 지원
- 서브 에이전트 접근 권한 검증 (본인 소유 + 구독 에이전트)
- Task 위임 방식 컨텍스트 전달
- CreateAgent API에서 sub_agent 워커 생성 지원
- DB 스키마 변경 (agent_tool 테이블)

**Out-of-Scope:**
- 프론트엔드 UI (별도 Plan에서 다룸)
- 서브 에이전트 간 병렬 실행 (Phase 2에서 고려)
- 서브 에이전트 실행 중 스트리밍 (현재 전체 완료 후 결과 반환)
- Auto Agent Builder에서의 자동 서브 에이전트 추천

---

## 2. Detailed Requirements

### 2.1 기능 요구사항

#### FR-01: WorkerDefinition 확장

현재 `WorkerDefinition`의 `tool_id` 필드만으로는 에이전트 참조를 표현할 수 없다.

| 필드 | 기존 | 변경 |
|------|------|------|
| `worker_type` | (없음) | `"tool"` / `"sub_agent"` — 기본값 `"tool"` |
| `tool_id` | 필수 | `worker_type="tool"`일 때 필수 |
| `ref_agent_id` | (없음) | `worker_type="sub_agent"`일 때 필수 |

하위 호환성: `worker_type` 미지정 시 기존과 동일하게 `"tool"`로 동작.

#### FR-02: WorkflowCompiler Sub-Agent 컴파일

`WorkflowCompiler.compile()` 시 `worker_type="sub_agent"` 워커를 만나면:

1. `ref_agent_id`로 AgentDefinition을 DB에서 조회
2. 해당 AgentDefinition의 `to_workflow_definition()` 호출
3. 재귀적으로 `compile()` 호출하여 서브 그래프 생성
4. 서브 그래프를 상위 StateGraph의 노드로 래핑

**Task 위임 방식:**
```
상위 Supervisor → "문서를 분석해주세요" (task 지시)
  → SubAgentWorker 노드: 
    → sub-graph.ainvoke({"messages": [{"role": "user", "content": task}]})
    → 결과만 상위 messages에 추가
```

#### FR-03: 순환참조 방지 정책

`CircularReferencePolicy` 도메인 정책:
- 컴파일 시점에 참조 체인을 추적 (`visited_agent_ids: set`)
- 이미 방문한 agent_id가 다시 나타나면 `CircularReferenceError` 발생
- 에이전트 생성/수정 시점에도 순환참조 사전 검증

#### FR-04: 중첩 깊이 제한

`NestingDepthPolicy` 도메인 정책:
- `MAX_NESTING_DEPTH = 2` (상수, 추후 config로 변경 가능)
- 현재 깊이를 `compile()` 호출 시 파라미터로 전달
- 깊이 초과 시 `NestingDepthExceededError` 발생

#### FR-05: 서브 에이전트 접근 권한 검증

`SubAgentAccessPolicy` 도메인 정책:
- 상위 에이전트 소유자가 서브 에이전트에 접근 가능한지 검증
- 허용 범위: 본인 소유 에이전트 + 구독 중인 에이전트
- 에이전트 생성 시 + 실행 시 양쪽 모두 검증

#### FR-06: DB 스키마 변경

`agent_tool` 테이블 확장:

```sql
ALTER TABLE agent_tool
  ADD COLUMN worker_type VARCHAR(20) NOT NULL DEFAULT 'tool',
  ADD COLUMN ref_agent_id VARCHAR(36) NULL,
  ADD CONSTRAINT fk_agent_tool_ref_agent
    FOREIGN KEY (ref_agent_id) REFERENCES agent_definition(id)
    ON DELETE SET NULL;
```

#### FR-07: CreateAgent API 확장

기존 `tool_configs` 외에 `sub_agent_configs` 추가:

```python
class SubAgentConfigRequest(BaseModel):
    ref_agent_id: str
    description: str = ""  # 상위 에이전트에서 이 서브 에이전트를 설명하는 텍스트

class CreateAgentRequest(BaseModel):
    # ... 기존 필드
    tool_configs: dict[str, RagToolConfigRequest] | None = None
    sub_agent_configs: list[SubAgentConfigRequest] | None = None  # 신규
```

#### FR-08: SupervisorConfig 확장

멀티 에이전트 관련 설정 추가:

```python
@dataclass(frozen=True)
class SupervisorConfig:
    max_iterations: int = 10
    token_limit: int = 8000
    quality_gate_enabled: bool = False
    max_retries_per_worker: int = 2
    max_nesting_depth: int = 2          # 신규
    sub_agent_token_limit: int = 4000   # 서브 에이전트별 토큰 한도
```

### 2.2 비기능 요구사항

| 항목 | 요구사항 |
|------|----------|
| **하위 호환성** | 기존 Tool 전용 에이전트는 변경 없이 동작해야 함 |
| **성능** | 서브 에이전트 실행 시 추가 DB 조회 최소화 (컴파일 시 1회 로드) |
| **안전성** | 순환참조, 무한중첩, 삭제된 에이전트 참조 방지 |
| **토큰 관리** | 서브 에이전트별 독립 토큰 한도로 전체 비용 제어 |

---

## 3. Architecture & Design Direction

### 3.1 레이어별 변경 범위

```
domain/agent_builder/
├── schemas.py           — WorkerDefinition에 worker_type, ref_agent_id 추가
├── policies.py          — CircularReferencePolicy, NestingDepthPolicy, SubAgentAccessPolicy 추가
└── interfaces.py        — (변경 없음)

application/agent_builder/
├── workflow_compiler.py — sub_agent 컴파일 로직 추가
├── create_agent_use_case.py — sub_agent_configs 처리 로직 추가
├── schemas.py           — SubAgentConfigRequest, CreateAgentRequest 확장
├── supervisor_nodes.py  — sub_agent 워커 래핑 함수 추가
└── run_agent_use_case.py — (간접 변경: compiler가 처리)

infrastructure/agent_builder/
├── models.py            — AgentToolModel에 worker_type, ref_agent_id 컬럼 추가
├── agent_definition_repository.py — 매핑 로직 업데이트
└── tool_factory.py      — (변경 없음, sub_agent는 ToolFactory 경유 안 함)
```

### 3.2 핵심 흐름

```
[에이전트 생성 시]
CreateAgentRequest (tool_configs + sub_agent_configs)
  → CreateAgentUseCase
    → sub_agent_configs 각각에 대해:
      1. ref_agent_id로 AgentDefinition 존재 확인
      2. SubAgentAccessPolicy 검증 (본인 소유 or 구독 중?)
      3. CircularReferencePolicy 검증 (재귀 탐색)
      4. NestingDepthPolicy 검증 (현재 깊이 체크)
    → WorkerDefinition(worker_type="sub_agent", ref_agent_id=...) 생성
    → AgentDefinition 저장

[에이전트 실행 시]
RunAgentUseCase.execute()
  → agent.to_workflow_definition()
  → WorkflowCompiler.compile(workflow, ...)
    → workers 순회:
      if worker.worker_type == "tool":
        → ToolFactory.create() → create_react_agent() → 기존 로직
      if worker.worker_type == "sub_agent":
        → repository.find_by_id(worker.ref_agent_id)
        → sub_agent.to_workflow_definition()
        → self.compile(sub_workflow, depth=depth+1)  # 재귀 컴파일
        → _wrap_sub_agent(worker_id, sub_graph) → 노드 등록
    → StateGraph 조립 및 컴파일
```

### 3.3 Sub-Agent 워커 래핑

```python
def _wrap_sub_agent(self, worker_id: str, sub_graph) -> Callable:
    async def wrapped(state: SupervisorState) -> dict:
        # 상위 Supervisor가 지시한 마지막 메시지(task)만 추출
        task_message = state["messages"][-1]
        
        # 서브 에이전트는 독립 컨텍스트로 실행 (Task 위임)
        sub_result = await sub_graph.ainvoke({
            "messages": [{"role": "user", "content": task_message.content}]
        })
        
        # 서브 에이전트 최종 응답만 상위에 반환
        sub_messages = sub_result.get("messages", [])
        final_answer = sub_messages[-1] if sub_messages else None
        
        return {
            "messages": [final_answer] if final_answer else [],
            "last_worker_id": worker_id,
            "token_usage": state["token_usage"] + sub_result.get("token_usage", 0),
        }
    return wrapped
```

---

## 4. Implementation Plan

### Phase 1: 도메인 레이어 (순수 로직)

| # | Task | 파일 | 설명 |
|---|------|------|------|
| 1-1 | WorkerDefinition 확장 | `domain/agent_builder/schemas.py` | `worker_type`, `ref_agent_id` 필드 추가 |
| 1-2 | CircularReferencePolicy | `domain/agent_builder/policies.py` | 순환참조 방지 정책 |
| 1-3 | NestingDepthPolicy | `domain/agent_builder/policies.py` | 중첩 깊이 제한 정책 (MAX=2, 확장 가능) |
| 1-4 | SubAgentAccessPolicy | `domain/agent_builder/policies.py` | 서브 에이전트 접근 권한 검증 |
| 1-5 | AgentBuilderPolicy 확장 | `domain/agent_builder/policies.py` | validate_workers() - tool/sub_agent 혼합 검증 |

### Phase 2: 인프라 레이어 (DB/모델)

| # | Task | 파일 | 설명 |
|---|------|------|------|
| 2-1 | DB 마이그레이션 | `db/migration/` | agent_tool 테이블에 worker_type, ref_agent_id 추가 |
| 2-2 | ORM 모델 확장 | `infrastructure/agent_builder/models.py` | AgentToolModel 컬럼 추가 |
| 2-3 | Repository 매핑 | `infrastructure/agent_builder/agent_definition_repository.py` | 도메인 ↔ ORM 변환 로직 수정 |

### Phase 3: 애플리케이션 레이어 (UseCase/Compiler)

| # | Task | 파일 | 설명 |
|---|------|------|------|
| 3-1 | Application 스키마 확장 | `application/agent_builder/schemas.py` | SubAgentConfigRequest, Response 확장 |
| 3-2 | WorkflowCompiler 확장 | `application/agent_builder/workflow_compiler.py` | sub_agent 컴파일, 재귀 호출, 깊이 체크 |
| 3-3 | CreateAgentUseCase 확장 | `application/agent_builder/create_agent_use_case.py` | sub_agent_configs 처리, 정책 검증 |
| 3-4 | RunAgentUseCase 조정 | `application/agent_builder/run_agent_use_case.py` | compiler에 repository 전달 (서브 에이전트 조회용) |

### Phase 4: API 라우터

| # | Task | 파일 | 설명 |
|---|------|------|------|
| 4-1 | CreateAgent API 확장 | `api/routes/agent_builder_router.py` | sub_agent_configs 파라미터 수용 |
| 4-2 | GetAgent API 확장 | `api/routes/agent_builder_router.py` | 응답에 sub_agent 정보 포함 |

---

## 5. Risk & Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| 순환참조로 인한 무한루프 | 시스템 hang | CircularReferencePolicy + 컴파일 시 visited set |
| 깊은 중첩으로 인한 토큰 폭발 | 비용 초과 | NestingDepthPolicy(MAX=2) + 서브 에이전트별 토큰 한도 |
| 삭제된 서브 에이전트 참조 | 실행 실패 | ref_agent_id FK ON DELETE SET NULL + 실행 시 null 체크 |
| 서브 에이전트 권한 변경 | 무단 접근 | 실행 시점에도 접근 권한 재검증 |
| 하위 호환성 깨짐 | 기존 에이전트 오류 | worker_type DEFAULT 'tool' + 기존 코드 변경 최소화 |

---

## 6. Test Strategy

TDD 원칙에 따라 각 Phase별 테스트를 먼저 작성한다.

| Phase | Test | 검증 항목 |
|-------|------|----------|
| 1 | `test_worker_definition_sub_agent` | worker_type="sub_agent" 생성, ref_agent_id 필수 검증 |
| 1 | `test_circular_reference_policy` | A→B→A 순환 탐지, A→B→C 정상 허용 |
| 1 | `test_nesting_depth_policy` | depth=2 허용, depth=3 거부, 확장 가능 검증 |
| 1 | `test_sub_agent_access_policy` | 본인 소유 허용, 구독 허용, 비접근 거부 |
| 2 | `test_agent_tool_model_migration` | worker_type, ref_agent_id 컬럼 존재 |
| 3 | `test_workflow_compiler_sub_agent` | sub_agent 워커 컴파일, 깊이 전파 |
| 3 | `test_create_agent_with_sub_agents` | sub_agent_configs 기반 에이전트 생성 |
| 3 | `test_mixed_tool_and_sub_agent` | Tool + Sub-Agent 혼합 워커 정상 동작 |
| 4 | `test_create_agent_api_sub_agent` | API 레벨 통합 테스트 |

---

## 7. Dependencies & Prerequisites

- 기존 `supervisor-custom-loop` 기능 완료 (현재 구현됨 ✅)
- AgentDefinition 조회를 위한 Repository가 WorkflowCompiler에 주입 가능해야 함
- 구독(subscription) 기능 구현 완료 (현재 구현됨 ✅)

---

## 8. Glossary

| Term | Definition |
|------|-----------|
| **Multi-Agent Composition** | 복수의 에이전트를 조합하여 하나의 상위 에이전트를 구성하는 패턴 |
| **Sub-Agent** | 상위 에이전트의 워커로 포함되어 실행되는 하위 에이전트 |
| **Task 위임** | 상위 Supervisor가 서브 에이전트에게 특정 task만 전달하고 결과를 받는 방식 |
| **순환참조** | A→B→A처럼 에이전트 참조가 순환하는 상태 |
| **중첩 깊이** | 최상위 에이전트에서 최하위 서브 에이전트까지의 단계 수 |
