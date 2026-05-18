# search-pipeline-refactor Planning Document

> **Summary**: 도구 카테고리 기반 워커 자동 분기 + Answer Agent 자동 할당으로 에이전트 역할 구조적 제어
>
> **Project**: sangplusbot (idt)
> **Author**: 배상규
> **Date**: 2026-05-11
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 현재 모든 워커가 `create_react_agent`로 생성되어 LLM이 자유 추론 — 검색 도구에 불필요한 판단/추천이 섞이며 system prompt만으로 역할 제어 불가 |
| **Solution** | 도구 카테고리(`search`/`action`)를 TOOL_REGISTRY에 추가하고, 검색 도구는 LLM 없이 직접 실행 + 자동 Answer Agent가 결과를 종합하는 파이프라인 구조로 전환 |
| **Function/UX Effect** | 검색 에이전트의 응답이 사실 기반 원본 데이터만 포함 → 답변 품질 예측 가능 + 불필요한 LLM 호출 제거로 latency/비용 절감 |
| **Core Value** | "LLM 행동을 제어"에서 "LLM이 개입할 자리를 구조적으로 제한"으로 패러다임 전환 — 안정적인 멀티에이전트 역할 분리 |

---

## 1. Overview

### 1.1 Purpose

에이전트 빌더에서 사용자가 검색 도구(벡터 DB, 웹 검색)를 선택했을 때, 해당 워커가 **검색만** 수행하고 판단/추천을 하지 않도록 파이프라인 구조로 보장한다. 최종 답변 생성은 별도의 Answer Agent가 수집된 데이터를 기반으로 수행한다.

### 1.2 Background

현재 `WorkflowCompiler`는 모든 워커를 `create_react_agent(llm, tools=[tool])`로 생성한다.
이 방식에서는:
- 검색 도구 워커도 LLM이 자유롭게 추론하여 판단/추천/결론을 포함할 수 있음
- system prompt로 "검색만 해라"고 지시해도 LLM이 이를 무시할 수 있음
- output schema + validator 계층을 두더라도 LLM이 교묘하게 우회 가능

**핵심 인사이트**: 검색 도구(`internal_document_search`, `tavily_search`)는 개발자가 만든 deterministic 함수다. LLM 추론 없이 직접 호출하면 결과는 항상 "검색 결과 원본"이다. LLM이 개입할 자리를 구조적으로 없애면 역할 일탈이 원천 차단된다.

### 1.3 Related Documents

- 현행 코드: `src/application/agent_builder/workflow_compiler.py`
- 도메인 스키마: `src/domain/agent_builder/schemas.py`
- 도구 레지스트리: `src/domain/agent_builder/tool_registry.py`
- 도구 팩토리: `src/infrastructure/agent_builder/tool_factory.py`
- Supervisor 노드: `src/application/agent_builder/supervisor_nodes.py`

---

## 2. Scope

### 2.1 In Scope

- [ ] `ToolMeta`에 `category: "search" | "action"` 필드 추가
- [ ] `TOOL_REGISTRY` 4개 도구에 카테고리 할당
- [ ] `WorkflowCompiler`에서 카테고리별 워커 생성 분기 (search → 직접 실행, action → 기존 ReAct)
- [ ] Search Node 구현 (LLM 없이 tool 직접 호출 → 원본 결과 반환)
- [ ] Answer Agent Node 구현 (수집된 검색 결과 + system_prompt → 최종 답변)
- [ ] Supervisor 라우팅 로직 수정 (검색 완료 → Answer Agent 자동 라우팅)
- [ ] MCP 도구(`mcp_` prefix)에 대한 카테고리 기본값 처리
- [ ] 기존 테스트 업데이트 + 신규 테스트 작성

### 2.2 Out of Scope

- 검색 쿼리 리라이팅 (Query Rewriting) — 추후 별도 기능으로 추가
- Answer Agent의 출력 스키마 강제 — 이번 스코프에서는 자유 형식 답변
- 프론트엔드 UI 변경 — 백엔드 내부 리팩터링만
- DB 스키마 변경 — `agent_tool` 테이블의 기존 컬럼으로 처리 가능

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | `ToolMeta`에 `category` 필드 추가, 기본값 `"action"` | High | Pending |
| FR-02 | `TOOL_REGISTRY`의 `internal_document_search`, `tavily_search`를 `category="search"`로 설정 | High | Pending |
| FR-03 | `WorkflowCompiler.compile()`에서 search 카테고리 워커는 `create_react_agent` 대신 직접 실행 노드 생성 | High | Pending |
| FR-04 | Search Node: 마지막 메시지에서 쿼리 추출 → tool.ainvoke() → 원본 결과 AIMessage로 반환 | High | Pending |
| FR-05 | Answer Agent Node: 검색 결과 메시지 수집 → system_prompt + 컨텍스트로 LLM 호출 → 최종 답변 | High | Pending |
| FR-06 | Supervisor가 모든 검색 워커 완료 후 자동으로 Answer Agent로 라우팅 | High | Pending |
| FR-07 | 검색 도구만 있는 에이전트: 자동 Answer Agent 추가 | High | Pending |
| FR-08 | 액션 도구만 있는 에이전트: 기존 동작 유지 (변경 없음) | High | Pending |
| FR-09 | 혼합(검색+액션) 에이전트: 검색은 직접 실행, 액션은 ReAct, 최종 Answer Agent 종합 | Medium | Pending |
| FR-10 | MCP 도구(`mcp_` prefix)는 기본 `category="action"` 처리 | Medium | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Performance | 검색 전용 에이전트의 latency 30% 이상 감소 (LLM 호출 1회 제거) | 기존 vs 신규 응답 시간 비교 |
| 호환성 | 기존 에이전트 정의(DB 데이터) 변경 없이 동작 | 기존 에이전트 실행 테스트 |
| 확장성 | 새 도구 추가 시 `category` 값만 지정하면 자동 분기 | 코드 리뷰 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] 검색 도구만 사용하는 에이전트 실행 시 LLM이 검색 단계에 개입하지 않음
- [ ] 검색 결과 원본이 Answer Agent에 그대로 전달됨
- [ ] 액션 도구만 사용하는 에이전트는 기존과 동일하게 동작
- [ ] 혼합 에이전트에서 검색/액션이 올바르게 분리 실행됨
- [ ] 모든 기존 테스트 통과 + 신규 테스트 커버리지 80% 이상
- [ ] 코드 리뷰 완료

### 4.2 Quality Criteria

- [ ] 테스트 커버리지 80% 이상
- [ ] Zero lint errors
- [ ] DDD 레이어 규칙 준수 (domain → infrastructure 참조 금지)

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 검색 쿼리가 사용자 원문 그대로라 품질 저하 | Medium | Medium | 1차는 원문 그대로, 추후 Query Rewriting 노드 추가 가능한 구조로 설계 |
| 혼합 에이전트에서 검색/액션 순서 제어 복잡 | Medium | Low | Supervisor가 기존처럼 라우팅 판단, 검색/액션 구분은 노드 타입만 다름 |
| 기존 에이전트 동작 깨짐 | High | Low | `category` 기본값 `"action"` → 카테고리 미지정 도구는 기존 ReAct 유지 |
| MCP 도구의 카테고리 판단 어려움 | Low | Medium | MCP는 기본 `"action"`, 추후 MCP 메타데이터에서 카테고리 추출 가능 |

---

## 6. Architecture Considerations

### 6.1 Project Level

| Level | Selected |
|-------|:--------:|
| **Enterprise** | **O** |

기존 Thin DDD 아키텍처(domain → application → infrastructure) 유지.

### 6.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 역할 제어 방식 | A) Output Schema + Validator / B) 파이프라인 구조 분리 | **B** | LLM 행동 제어(A)는 우회 가능, 구조적 제한(B)은 원천 차단 |
| Search Node 구현 | A) 얇은 LLM 래퍼 / B) tool 직접 호출 | **B** | 검색 도구는 deterministic — LLM 불필요 |
| Answer Agent 위치 | A) 별도 워커로 DB 저장 / B) 컴파일 시 자동 주입 | **B** | 사용자가 관리할 필요 없음, 시스템 내부 노드 |
| 카테고리 저장 위치 | A) DB agent_tool 테이블 / B) TOOL_REGISTRY 코드 | **B** | 도구 특성은 코드 레벨 결정사항, DB 변경 불필요 |
| 그래프 구조 | A) 검색 병렬 실행 / B) Supervisor 순차 라우팅 유지 | **B (1차)** | 기존 Supervisor 라우팅 유지하며 점진적 전환, 병렬화는 추후 |

### 6.3 변경 대상 파일

```
변경 범위:
┌─────────────────────────────────────────────────────────────┐
│ domain/ (스키마 확장)                                        │
│   schemas.py          — ToolMeta에 category 필드 추가        │
│   tool_registry.py    — 4개 도구에 category 할당              │
│   policies.py         — 변경 없음 (QualityGate 그대로)        │
├─────────────────────────────────────────────────────────────┤
│ application/ (핵심 로직)                                      │
│   workflow_compiler.py — search/action 분기 + answer_agent   │
│   supervisor_nodes.py  — answer_agent 라우팅 조건 추가        │
│   supervisor_state.py  — 변경 없음 또는 최소 확장             │
├─────────────────────────────────────────────────────────────┤
│ infrastructure/ (변경 없음)                                   │
│   tool_factory.py     — 기존 그대로 (tool 생성 로직 불변)     │
├─────────────────────────────────────────────────────────────┤
│ tests/ (신규 + 업데이트)                                      │
│   test_workflow_compiler.py — search/action 분기 테스트       │
│   test_supervisor_nodes.py  — answer_agent 라우팅 테스트      │
│   (신규) test_search_node.py — Search Node 단위 테스트        │
│   (신규) test_answer_node.py — Answer Agent 단위 테스트       │
└─────────────────────────────────────────────────────────────┘
```

---

## 7. Implementation Order

### Phase 1: Domain 확장 (스키마)

1. `ToolMeta.category` 필드 추가 (기본값 `"action"`)
2. `TOOL_REGISTRY` 카테고리 할당
3. 테스트: 카테고리 조회 테스트

### Phase 2: Search Node 구현

1. `_create_search_node()` 메서드 구현 (LLM 없이 tool 직접 호출)
2. 테스트: Search Node가 tool 결과를 원본 그대로 반환하는지 검증

### Phase 3: Answer Agent Node 구현

1. `_create_answer_node()` 메서드 구현 (검색 결과 수집 → LLM 답변)
2. 테스트: 검색 결과 메시지를 정확히 수집하고 LLM에 전달하는지 검증

### Phase 4: WorkflowCompiler 분기 로직

1. `compile()`에서 카테고리별 워커 생성 분기
2. 검색 도구 존재 시 Answer Agent 자동 주입
3. Supervisor 라우팅 로직 수정
4. 통합 테스트: 검색 전용 / 액션 전용 / 혼합 시나리오

### Phase 5: 기존 테스트 업데이트 + 회귀 테스트

1. 기존 `test_workflow_compiler.py` 업데이트
2. 기존 `test_run_agent_use_case.py` 회귀 확인
3. E2E 시나리오 테스트

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- [x] `CLAUDE.md` has coding conventions section
- [x] `docs/rules/testing.md` exists
- [x] DDD 레이어 규칙 적용 중
- [x] pytest 기반 TDD 워크플로우

### 8.2 Environment Variables

변경 없음 — 기존 환경변수 그대로 사용.

---

## 9. Next Steps

1. [ ] Design 문서 작성 (`search-pipeline-refactor.design.md`)
2. [ ] TDD 사이클로 구현 시작 (Phase 1부터)
3. [ ] Gap Analysis 후 완료 보고서

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-05-11 | Initial draft | 배상규 |
