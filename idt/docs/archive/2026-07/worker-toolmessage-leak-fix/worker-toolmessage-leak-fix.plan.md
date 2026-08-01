# Worker ToolMessage Leak Fix Planning Document

> **Summary**: 도구 워커(react agent)의 내부 실행 트레이스(tool_calls AIMessage + ToolMessage)가 supervisor state에 통째로 유출되고, `final_answer_node`의 워커 산출물 필터가 그중 AIMessage만 제거하면서 **ToolMessage가 고아(orphan)로 남아 OpenAI 400**(`messages with role 'tool' must be a response to a preceeding message with 'tool_calls'`)으로 런 전체가 실패하는 결함 수정 — 워커 wrapper의 최종 답변 단일 반환(sub_agent 선례) + final_answer 2차 방어
>
> **Project**: sangplusbot (idt 백엔드)
> **Version**: 1.0
> **Author**: 배상규
> **Date**: 2026-07-29
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 도구를 실제 호출한 워커(특히 wiki_list/wiki_read 체인 워커)가 실행된 런이 `final_answer_node`에서 OpenAI 400으로 **전체 실패**(AgentRun failed). 원인: `_wrap_worker`가 react agent 결과 messages 전체를 반환 → `add_messages` 리듀서가 `AIMessage(tool_calls, name=worker_id)`·`ToolMessage`·`AIMessage(최종답, name=worker_id)`를 모두 state에 누적 → `final_answer_node`의 `_is_worker_output` 필터(type=="ai" and name)가 tool_calls AIMessage는 제거하고 ToolMessage(type=="tool")는 남겨 짝이 깨짐 |
| **Solution** | ① `_wrap_worker`가 내부 트레이스를 state로 흘리지 않고 **최종 `AIMessage(name=worker_id)` 1건만 반환** (`_wrap_sub_agent`와 동일 규약으로 정렬) ② `final_answer_node` conversation 필터에 tool 타입 제외 2차 방어 ③ 부수 수정: 전체 히스토리 재합산으로 과대계상되던 token_usage 델타를 신규 산출분 기준으로 교정 |
| **Function/UX Effect** | 위키 워커 등 도구 호출 워커가 실행된 질의가 400 에러 대신 최종 답변까지 정상 완주. 멀티턴에서도 state에 고아 tool 메시지가 따라다니지 않아 후속 턴 오염 제거 |
| **Core Value** | "워커 산출물은 `AIMessage(name=worker_id)` 1건" 메시지 규약의 단일화 — search/analysis/sub_agent/document_extractor는 이미 준수, 유일한 이탈자(_wrap_worker)를 정렬해 wiki-agentic-navigation으로 상시화된 도구 호출 경로에서 supervisor 그래프의 메시지 불변식을 복원 |

---

## 1. Overview

### 1.1 Purpose

react agent 기반 도구 워커의 내부 tool 호출 흔적이 supervisor state에 유출되어
`final_answer_node`에서 고아 ToolMessage로 OpenAI 400을 유발하는 결함을 수정한다.
워커 wrapper 계층에서 유출을 원천 차단하고(소스 수정), LLM 호출 직전 필터에 방어선을 추가한다.

### 1.2 Background (2026-07-29 런 실패 트레이스 + 코드 추적으로 원인 확정)

**증상**: run_id `ba952a90` — `final_answer` 노드의 `llm.ainvoke`에서
`openai.BadRequestError: messages.[2].role = 'tool' ... must be a response to a preceeding
message with 'tool_calls'` → AgentRun failed.

**원인 체인 (전 구간 코드 실측)**:

1. **내부 트레이스 유출** — `workflow_compiler.py:971-1000` `_wrap_worker`가
   `worker_agent.ainvoke(...)` 결과의 `messages` **전체**를 반환. 도구를 호출한 런이면
   `AIMessage(tool_calls)` → `ToolMessage(도구 결과)` → `AIMessage(최종답)` 3종이 포함되고,
   `add_messages` 리듀서가 신규분을 모두 supervisor state에 append.
2. **tool_calls AIMessage에도 name이 찍힘** — 설치된 langgraph
   `chat_agent_executor.py:676` `response.name = name`. react agent가 생성하는 **모든**
   AIMessage(중간 tool_calls 포함)에 `name=worker_id` 부여.
3. **필터가 짝을 깨뜨림** — `workflow_compiler.py:602-604`
   `conversation_messages = [m for m in messages if not _is_worker_output(m)]`.
   `_is_worker_output`(`search_pipeline.py:57-64`)은 `type=="ai" and name`만 매칭 →
   tool_calls AIMessage는 **제거**, ToolMessage(type=="tool")는 **잔류**.
4. **결과**: LLM 입력이 `[system, Human(질문), ToolMessage, ...]` — 에러의
   `messages.[2]` 위치와 정확히 일치. OpenAI는 tool 역할 앞에 tool_calls assistant를
   강제하므로 400.

**왜 지금 상시화됐나**: wiki-agentic-navigation/wiki-folder-summaries로 추가된 wiki 워커
(`workflow_compiler.py:308-315`)는 설계상 **반드시** wiki_list/wiki_read 도구를 호출하고,
워커가 실행된 런은 `route_to_worker_or_final`이 구조적으로 `final_answer_node`를 경유시킴
(final-answer-node Design §3-3) → 재현 조건이 "위키 질의 = 항상"이 됨.

**부수 결함 (같은 지점)**: `_wrap_worker`의 `token_delta`(988-992행)가 react agent 결과
전체(입력 히스토리 포함)를 재합산 → `token_usage` 과대계상. 최종 답변 단일 반환 시 자연 해소.

### 1.3 Related Documents / 선례

- 준수 선례(최종 답변만 반환): `_wrap_sub_agent` `workflow_compiler.py:1002-1046`
- 메시지 규약 단일 출처: `search_pipeline.py` `is_worker_output`/`is_search_result`
  (search-node-query-pipeline D2)
- final_answer 경유 구조: final-answer-node Design §3-3
- 유사 계열 선례: fix-anthropic-prefill-error (`message_normalization.py` `ensure_user_tail`) —
  프로바이더 메시지 형식 제약 방어

---

## 2. Scope

### 2.1 In Scope

- [ ] **S1. `_wrap_worker` 최종 답변 단일 반환**: react agent 결과에서 최종
      `AIMessage(name=worker_id)` 1건만 state로 반환 (`_wrap_sub_agent` 규약 정렬).
      token_delta도 해당 1건 기준으로 교정
- [ ] **S2. `final_answer_node` 2차 방어**: conversation_messages 구성 시 tool 타입
      메시지 제외 (히스토리·타 경로에서 유입될 수 있는 고아 tool 메시지 방어)
- [ ] **S3. 회귀 테스트**: ① `_wrap_worker`가 도구 호출 트레이스를 유출하지 않음
      (ToolMessage·tool_calls AIMessage 부재, 최종 답변 name 규약) ② final_answer LLM 입력에
      tool 역할 부재 ③ token_delta 신규 산출분 기준 ④ 기존 workflow_compiler 테스트 무회귀
- [ ] **S4. E2E 수동 검증**: 위키 질의(도구 호출 확정 경로) → final_answer 완주,
      run 상세 step 실측

### 2.2 Out of Scope

- `_wrap_sub_agent`·search 파이프라인·analysis·document_extractor 노드 변경
  (이미 규약 준수 — 무변경)
- general_chat 경로 (별도 유스케이스, 자체 ToolMessage 처리 보유)
- `_is_worker_output` 판정 로직 자체 변경 (규약 단일 출처 유지 — 이탈자만 정렬)
- supervisor 결정 프롬프트·라우팅 그래프 구조 변경
- 프론트엔드·API 계약·DB 마이그레이션 (전부 무변경)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | 도구 워커 실행 후 supervisor state에 추가되는 메시지는 최종 `AIMessage(name=worker_id)` 1건뿐이다 (tool_calls AIMessage·ToolMessage 미유출) | High | Pending |
| FR-02 | 도구를 호출하지 않고 종료한 워커(직답)도 동일 규약으로 최종 AIMessage 1건만 반환한다 | High | Pending |
| FR-03 | `final_answer_node`가 LLM에 전달하는 메시지 배열에 tool 역할 메시지가 포함되지 않는다 (state에 고아 ToolMessage가 있어도) | High | Pending |
| FR-04 | `_wrap_worker`의 token_usage 델타는 워커 신규 산출분(최종 답변) 기준이다 | Medium | Pending |
| FR-05 | search/analysis/sub_agent/document_extractor 워커의 기존 메시지 규약·동작 불변 | High | Pending |
| FR-06 | 위키 워커 도구 호출 시나리오가 400 없이 final_answer까지 완주한다 (E2E 수동 — run step 실측) | High | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 회귀 안전 | 기존 pytest 무회귀 (사전 실패분 제외 기준) — workflow_compiler·wiki_toc 테스트 포함 | pytest 격리 실행 |
| 아키텍처 | application 레이어 내 수정, 레이어 이동 없음 | verify-architecture 스킬 |
| TDD | 테스트 선행 (Red → Green → Refactor) — 고아 ToolMessage 재현 테스트부터 | verify-tdd 스킬 |
| 관측성 | react agent 내부 도구 호출 트레이스는 LangSmith run tree로 계속 관측 가능 (state 유출 제거가 관측 손실이 아님을 Design에서 명시) | LangSmith 확인 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] 재현 시나리오: 도구 호출 워커 실행 런이 `final_answer_node`에서 400 없이 최종 답변 반환
- [ ] `_wrap_worker` 반환 메시지에 ToolMessage·tool_calls 부재 단언 테스트 통과 (Red 선행 확인)
- [ ] final_answer LLM 입력 tool 역할 부재 단언 테스트 통과
- [ ] 기존 테스트 무회귀 (`test_workflow_compiler*.py`, wiki 관련 신규 테스트 포함)

### 4.2 Quality Criteria

- [ ] Gap 분석(Match Rate) >= 90%
- [ ] 함수 40줄·if 중첩 2단계 규칙 준수, 하드코딩 없음

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 최종 답변만 남기면 도구 원문(열람 본문 등)이 state에서 사라져 후속 노드 참조 정보 감소 | Low | Low | 현행 소비자 실측: `final_answer_node`·`_analyze_context` 모두 `AIMessage(name)` content만 사용, ToolMessage를 읽는 코드는 agent_builder에 없음(grep 확인). react agent 최종 답변이 도구 결과를 근거로 작성됨 |
| react agent 결과의 마지막 메시지가 최종 답변이 아닐 가능성 (구조화 응답·재시도 경로) | Medium | Low | `_wrap_sub_agent`와 동일한 추출 방식 사용 + 마지막 AIMessage 부재 시 graceful 처리를 Design에서 확정 |
| 멀티턴 히스토리 재구성 경로에 이미 저장된 고아 tool 메시지 유입 | Medium | Low | S2 2차 방어가 커버. 히스토리 재구성이 role/content 기반인지 Design에서 확인 |
| token_usage 계산 변경이 반복 한도(IterationLimitPolicy) 판정에 영향 | Low | Medium | 과대계상 → 정상화 방향(한도 도달이 늦어짐). 기존 한도 테스트로 회귀 확인, 영향 있으면 Design에서 명시 |
| wiki 워커(도구 2종 번들)와 일반 단일 도구 워커의 경로 차이 | Low | Low | 둘 다 `_wrap_worker` 경유(생성부만 분기, `workflow_compiler.py:308-315`) — 단일 수정 지점 |

---

## 6. Architecture Considerations

### 6.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| **Starter** | Simple structure | Static sites | ☐ |
| **Dynamic** | Feature-based modules | Web apps | ☐ |
| **Enterprise** | Strict layer separation | 기존 프로젝트 구조 (Thin DDD) | ☑ |

### 6.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 수정 위치 | final_answer 필터만 / wrapper 소스 차단 / 양쪽 | 양쪽 (S1+S2) | 필터만이면 고아 메시지가 state·멀티턴에 잔존해 타 노드로 전이 — 소스 차단이 근본, 필터는 히스토리 유입 방어 |
| 최종 답변 추출 방식 | 마지막 메시지 / 마지막 AIMessage / content 있는 마지막 AIMessage | Design에서 확정 | `_wrap_sub_agent`(1039행) 선례와 react agent 종료 조건 검토 후 결정 |
| 2차 방어 판정 기준 | type=="tool" 제외 / 고아 여부 검사 후 제외 | Design에서 확정 | 단순 제외가 안전(짝 있는 tool도 final_answer엔 불필요 — 워커 블록으로 이미 요약 제공) |

### 6.3 변경 대상 파일 (예상)

```
idt/src/
├── application/agent_builder/workflow_compiler.py   # S1: _wrap_worker / S2: final_answer_node
└── tests/
    └── application/agent_builder/
        ├── test_workflow_compiler.py                # S3: 기존 무회귀 + 신규 단언
        └── (신규) 워커 트레이스 유출 회귀 테스트     # S3: FR-01~04
```

> `search_pipeline.py`·`supervisor_nodes.py`는 무변경 목표. 정확한 추출·필터 코드는 Design에서 확정.

---

## 7. Convention Prerequisites

- [x] 검증 스킬 존재: verify-architecture, verify-tdd
- [x] 백엔드 테스트 격리 실행 관례 (Windows 이벤트 루프 flakiness)
- 환경변수·마이그레이션·API 계약 변경 **없음** (프론트 동기화 불필요)

---

## 8. Implementation Guide

### 8.1 구현 순서

```
1. FR-01/02  재현 테스트 먼저: 도구 호출 mock react agent → _wrap_worker 반환 단언 (Red)
             → _wrap_worker 최종 답변 단일 반환으로 수정 (Green)
2. FR-03     final_answer_node tool 제외 테스트 먼저 → 필터 수정
3. FR-04     token_delta 단언 → 신규 산출분 기준 교정 (1과 동시 처리 가능)
4. FR-05     기존 pytest 격리 실행 무회귀 확인
5. FR-06     E2E 수동: 위키 질의 → run 완주 + step 실측
```

### 8.2 검증 자료

- 실패 트레이스: run_id `ba952a90-309e-4e89-ad81-43daad915a71` (2026-07-29,
  `tracker.py:fail_run:186` — final_answer 노드 openai.BadRequestError)
- 검증 경로: `GET /agents/runs/{run_id}` step 목록 + LangSmith `agent-run` 프로젝트
  (react agent 내부 도구 호출 트레이스 관측 유지 확인 포함)
- 재현 질의: 위키 문서 열람이 필요한 질문 (wiki_read 도구 호출 확정 경로)

---

## 9. Next Steps

1. [ ] Write design document (`/pdca design worker-toolmessage-leak-fix`) —
       최종 답변 추출 방식·2차 방어 판정 기준·히스토리 재구성 경로 확인
2. [ ] 구현 (TDD)
3. [ ] Gap 분석 (`/pdca analyze worker-toolmessage-leak-fix`)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-07-29 | Initial draft — 런 실패 트레이스 + _wrap_worker/langgraph name 주입 코드 추적 기반 | 배상규 |
