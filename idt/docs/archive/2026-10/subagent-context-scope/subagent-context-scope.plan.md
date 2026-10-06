# subagent-context-scope Planning Document

> **Summary**: 서브에이전트 워커가 부모 그래프에서 받는 입력을 `state.messages[-1]` 1건에서 **[이번 턴 사용자 원 질문 + supervisor 지시(worker_task) + 이번 턴 워커 산출 참고자료(상한)]** 로 바꾼다. 입력 조립은 **전략 인터페이스**로 분리해, 이번 사이클은 고정 정책 1종만 두되 이후 "서브에이전트 연결별 설정(context_mode)"으로 스키마 확장만 하면 갈아끼울 수 있게 한다. quality_gate 재시도 입력 결함과 입력 요약의 실행 이력 노출을 함께 다룬다.
>
> **Project**: sangplusbot (idt)
> **Version**: —
> **Author**: 배상규
> **Date**: 2026-10-02
> **Status**: Draft (v0.1)
> **Depends on**: agent-subagent-management(아카이브), worker-context-injection, approval-gate-run-termination

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | `_wrap_sub_agent`는 부모 `state["messages"][-1]` 1건만 넘기고, supervisor가 `state["worker_task"]`에 담은 지시는 읽지 않는다. 그래서 서브에이전트가 앞 워커 다음에 호출되면 **앞 워커의 산출물**만 받고, quality_gate가 재시도하면 **"[품질검증 실패] …" 문장만** 받는다. 어떤 경우에도 무엇을 해야 하는지 알 수 없다. |
| **Solution** | 입력 조립을 `SubAgentContextStrategy` 인터페이스로 분리하고, 기본 전략으로 `[원 질문] + [참고 자료(이번 턴 워커 산출, 상한 절단)] + [현재 작업(worker_task, 재시도면 피드백 덧붙임)]`을 구성한다. 길이 상한·블록 형식·원 질문 판별 규칙은 domain Policy가 가진다. |
| **Function/UX Effect** | 서브에이전트가 부모의 지시와 이미 수집된 자료를 받아, 같은 자료를 다시 수집하거나 엉뚱한 과제를 수행하지 않는다. 실행 이력 step에 "서브에이전트 입력: 메시지 N건·참고자료 M자(절단 여부)"가 남아 운영 중에 확인할 수 있다. |
| **Core Value** | 서브에이전트를 일반 워커와 같은 계약(지시 전달)으로 맞춘다. 전략 인터페이스로 분리해 두면, 다음 사이클에서 연결별 설정을 붙일 때 컴파일러를 고치지 않아도 된다. |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 서브에이전트가 supervisor 지시를 받지 못해, 두 번째 이후 라우팅과 QG 재시도에서 과제를 모른 채 실행된다. 런타임 위임이 사실상 첫 라우팅에서만 올바르게 동작한다. |
| **WHO** | P2 — 서브에이전트를 조합해 에이전트를 만드는 KB 운영자·에이전트 소유자. 간접적으로는 그 에이전트를 쓰는 채팅 사용자. |
| **RISK** | 참고자료 블록 때문에 자식 supervisor가 부모 워커 산출을 자기 워커 결과로 착각해 조기 FINISH할 수 있음 → Human 메시지 + 명시 라벨로 주입하고, 강제 라우팅 트리거(`is_search_result`) 비대상임을 테스트로 고정. 토큰 증가 → 참고자료 상한(기본 4000자)으로 제한. |
| **SUCCESS** | 서브에이전트 입력에 worker_task가 항상 포함(첫/중간/재시도 3경로) / QG 재시도 시 원 지시 + 피드백 둘 다 포함 / 참고자료 상한 준수 / 전략 교체가 컴파일러 수정 없이 DI로 가능 / 기존 서브에이전트·승인 게이트 전파 테스트 회귀 0. |
| **SCOPE** | domain Policy·인터페이스 → 기본 전략 구현 → `_wrap_sub_agent` 적용 → QG 재시도 경로 → 실행 이력 요약 → DI 배선. 프론트·DB 변경 없음. |

---

## 1. Overview

### 1.1 Purpose
서브에이전트 워커가 **"무엇을 해야 하는지(지시)"와 "무엇을 근거로 할지(원 질문·참고자료)"**를 항상 받도록 입력 조립을 바로잡는다. 이후 범위 설정을 확장할 수 있게 구조를 정한다.

### 1.2 Background (코드 실측, 2026-10-02 / master 797a61c)

| 지점 | 현재 동작 |
|------|-----------|
| `workflow_compiler.py:2567` `_wrap_sub_agent` | `task_content = state["messages"][-1].content` 1건 → `build_initial_state(messages=[user:task_content], attachments 없음)` |
| `supervisor_nodes.py:569` | 라우팅 시 지시를 메시지가 아닌 `worker_task` state 필드에 저장 |
| `workflow_compiler.py:377` `_build_worker_input` | 일반 react 워커는 `messages 전체 + [현재 작업]\n{task}`로 지시를 받음 (worker-context-injection FR-05) — **서브에이전트만 이 계약에서 빠져 있음** |
| `supervisor_nodes.py:626` quality_gate 실패 | `{"role":"user","content":"[품질검증 실패] …"}`를 append하고 같은 워커로 재라우팅 → 서브에이전트는 이 문장만 받음 |

경로별 서브에이전트 실제 입력:

| 상황 | 받는 메시지 | 판정 |
|------|-------------|------|
| 런 첫 라우팅 | 사용자 질문 | 우연히 맞음, 지시는 누락 |
| 다른 워커 다음 | 직전 워커 AIMessage 본문 | ❌ 과제 누락 |
| QG 재시도 | "[품질검증 실패] 응답이 기준에 미달…" | ❌ 과제·원 질문 모두 누락 |

### 1.3 Related Documents
- `docs/archive/2026-06/agent-subagent-management/*.report.md` §4 — "런타임 위임은 범위 외, 별도 검증 권장"
- `docs/wiki/backend/patterns/supervisor-graph-contracts.md` — 워커 산출물 1건 계약, 재주입분 강제 라우팅 제외 계약
- worker-context-injection (Design §4.1 FR-05: worker_task 무조건 append)

---

## 2. Scope

### 2.1 In Scope
- [ ] **FR-01 입력 조립 인터페이스**: application 레이어 `SubAgentContextStrategy` 프로토콜 `build(state) -> SubAgentInput(messages, summary)`. 컴파일러는 주입받은 전략만 호출한다.
- [ ] **FR-02 기본 전략 `TaskWithOriginStrategy`**: `[원 질문] + [참고 자료](선택) + [현재 작업]` 3블록 조립.
- [ ] **FR-03 domain Policy `SubAgentContextPolicy`**: 원 질문 판별(마지막 실사용자 HumanMessage. QG 피드백 접두 `[품질검증 실패]`·재주입 마커 제외), 이번 턴 워커 산출 판별(원 질문 이후의 name 있는 AIMessage), 참고자료 상한(기본 4000자)·절단 표기, 블록 라벨 문자열. LangChain 타입은 쓰지 않는다(duck typing, 기존 ToolErrorPolicy와 같은 방식).
- [ ] **FR-04 `_wrap_sub_agent` 적용**: `messages[-1]` 대신 전략 산출을 쓴다. 산출 계약(AIMessage(name) 1건)·토큰 합산·approval_pending 전파는 바꾸지 않는다.
- [ ] **FR-05 QG 재시도 입력**: 재시도 경로에서 서브에이전트가 `원 지시 + [재시도 사유] 피드백 문장`을 받는다(worker_task는 재시도 시에도 유지되는지 확인. 비어 있으면 직전 서브에이전트 호출 때의 task를 쓴다).
- [ ] **FR-06 worker_task 폴백**: task가 빈 경우(강제 라우팅 `forced_worker` 경로 등)에는 원 질문을 과제로 쓴다. 일반 워커의 `_FALLBACK_WORKER_INSTRUCTION`과 같은 취지다.
- [ ] **FR-07 실행 이력 요약**: 서브에이전트 step `STEP_OUTPUT_SUMMARY_KEY`에 `원질문 유무 / 참고자료 건수·길이(절단 여부) / 재시도 여부`를 남긴다(형식은 Design R8). 값(본문)은 싣지 않는다.
- [ ] **FR-08 DI**: 전략 인스턴스를 `WorkflowCompiler` 생성자로 주입한다(기본값 = TaskWithOriginStrategy). 미주입 시 기본 전략을 쓰므로 기존 생성 지점은 바뀌지 않는다.
- [ ] **FR-09 확장 지점 명시**: 전략 선택을 `resolve(worker_def) -> SubAgentContextStrategy`로 한 번 감싼다. 지금은 항상 기본값을 돌려주지만, 다음 사이클에 `WorkerDefinition.context_mode`가 생기면 여기서만 분기한다.

### 2.2 Out of Scope
- 서브에이전트 연결별 `context_mode` 설정(DB 컬럼·API·모달 UI). 이번엔 확장 지점만 두고 다음 사이클로 넘긴다.
- 이전 턴 대화 히스토리 전달(사용자 선택: 이전 턴은 supervisor가 task에 녹여 간접 전달)
- 첨부파일(attachments) 전달
- 실행 시점 서브에이전트 권한 재확인(VisibilityPolicy). 별도 사이클 후보.
- 서브에이전트 승인 대기 → 재개 경로의 입력 재구성(현행 유지)
- 프론트엔드 변경

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | `SubAgentContextStrategy` 인터페이스로 입력 조립 분리 | High | Pending |
| FR-02 | 기본 전략: 원 질문 + 참고자료 + 현재 작업 | High | Pending |
| FR-03 | `SubAgentContextPolicy` (판별·상한·라벨, 순수 규칙) | High | Pending |
| FR-04 | `_wrap_sub_agent`가 전략 산출 사용, 출력 계약 불변 | High | Pending |
| FR-05 | QG 재시도 시 원 지시 + 피드백 전달 | High | Pending |
| FR-06 | worker_task 빈 경우 원 질문을 과제로 폴백 | Medium | Pending |
| FR-07 | 입력 요약을 step output_summary에 기록(값 미포함) | Medium | Pending |
| FR-08 | 전략 DI(생성자 주입, 기본값 유지) | Medium | Pending |
| FR-09 | `resolve(worker_def)` 확장 지점 (현재는 단일 전략) | Low | Pending |
| FR-10 | **(Do 중 추가, 사용자 승인)** 서브에이전트 노드 런타임 실패 회귀 수정 — sub_agent 분기의 `function_node_ids` 누락으로 `_wrap_worker`가 래퍼 함수에 `.ainvoke` 호출 → `AttributeError`. 회귀 기점 `3a25eb7`(2026-06-14) | Critical | Pending |
| FR-11 | **(module-4 실런 중 추가, 사용자 승인)** `main.py`의 앱 싱글톤 `WorkflowCompiler`에 `agent_repository`·`llm_model_repository` 미주입 — 서브에이전트를 가진 에이전트는 compile 단계에서 `ValueError`로 런 전체 실패. 도입 이후 한 번도 주입된 적 없음(`git log -S`). 세션 스코프 어댑터 신설 + DI | Critical | Pending |
| FR-12 | **(module-4 실런 중 추가, 사용자 승인)** 서브에이전트 worker_id(`sub_agent_{이름}_{i}`)의 공백 → `AIMessage.name` OpenAI 패턴 위반 400 → 서브에이전트 다음 supervisor 결정 실패·조기 종료. 빌더에서 id 정규화 + `clamp_llm_name`에서 금지 문자 치환(저장된 id 방어) | High | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 토큰 | 서브에이전트 입력 증가분 ≤ 참고자료 상한(4000자) + 원 질문 + task | 단위 테스트(상한 경계값) |
| 아키텍처 | domain Policy는 LangChain·infra를 import하지 않음 | `/verify-architecture` |
| 로깅 | 요약 로그에 본문 값 미포함, 예외는 스택 트레이스 포함 | `/verify-logging` |
| 호환 | 기존 `test_workflow_compiler*.py`·승인 게이트 전파 테스트 무수정 통과 | pytest |

---

## 4. Success Criteria

### 4.1 Definition of Done
- [ ] SC-1: 서브에이전트 입력에 worker_task 포함 — 첫 라우팅 / 다른 워커 다음 / QG 재시도 3경로 테스트
- [ ] SC-2: QG 재시도 입력에 원 지시와 피드백이 모두 있음
- [ ] SC-3: 참고자료가 상한을 넘으면 절단 + 절단 표기, 상한 이하이면 무손실
- [ ] SC-4: 이전 턴 메시지·재주입분·QG 피드백은 "원 질문"·"참고자료"로 잡히지 않음
- [ ] SC-5: 테스트 대역 전략 주입으로 컴파일러 수정 없이 입력 교체가 가능함을 테스트로 증명
- [ ] SC-6: 서브에이전트 산출 계약(AIMessage(name) 1건)·approval_pending 전파 회귀 0
- [ ] SC-7 (L3 실런): 서브에이전트가 포함된 에이전트로 "A 조회 후 B 서브에이전트로 요약" 시나리오를 실행했을 때 서브에이전트가 지시대로 수행하고 재수집하지 않음(실행 이력 확인)

### 4.2 Quality Criteria
- [ ] TDD(Red→Green) 순서 준수, 신규 모듈 테스트 파일 존재(`/verify-tdd`)
- [ ] 함수 40줄·if 중첩 2단계 규칙 준수

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 자식 supervisor가 참고자료를 자기 워커 결과로 오인해 즉시 FINISH | High | Medium | AIMessage가 아닌 HumanMessage + `[참고 자료 — 상위 에이전트 제공]` 라벨로 주입. 자식의 `last_worker_id`는 비어 있으므로 final_answer DQ1 경로를 확인. 실런(SC-7) 검증 |
| 참고자료가 `is_search_result()` 등 강제 라우팅 규약에 걸려 자식에서 분석 워커가 강제 실행 | Medium | Medium | 라벨이 규약 패턴과 겹치지 않음을 테스트로 고정(위키 계약 ③의 교차 회귀 주의) |
| 원 질문 판별 오류(재주입 마커·QG 피드백·첨부 안내 메시지 등이 Human 타입) | Medium | Medium | Policy 단위 테스트로 제외 대상 전수 고정. 판별 실패 시 task만 전달(fail-safe) |
| 토큰 증가로 자식 token_limit(부모의 1/2) 조기 소진 | Medium | Low | 참고자료 상한 + 요약에 길이 기록으로 관측 |
| QG 재시도 시점에 worker_task가 이미 비어 있음 | Medium | Medium | Design에서 state 흐름 실측. 필요하면 래퍼가 마지막 task를 클로저/state 키로 보존 |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `WorkflowCompiler._wrap_sub_agent` | Application | 입력 조립을 전략 호출로 교체, step 요약 추가 |
| `WorkflowCompiler.__init__` | Application | `sub_agent_context_strategy` 선택 인자 추가(기본값) |
| `SubAgentContextPolicy` (신규) | Domain | 판별·상한·라벨 규칙 |
| `SubAgentContextStrategy` / `TaskWithOriginStrategy` (신규) | Application | 인터페이스 + 기본 구현 |
| `main.py` DI | Interfaces | (선택) 명시 주입. 기본값이 있으므로 필수는 아님 |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| `_wrap_sub_agent` | 서브 그래프 실행 | `_compile_sub_agent` → worker_map | 입력 변경(의도), 출력 불변 |
| `_wrap_sub_agent` 산출 | approval_pending 전파 | `route_after_gated_worker`, 재개 `_restore_state` | 불변 확인 필요 |
| `WorkflowCompiler()` 생성 | DI | `main.py`, 각종 테스트 픽스처 | 기본값으로 무영향 |
| quality_gate 피드백 메시지 | READ | 일반 워커 `_build_worker_input`, search 파이프라인 | 변경 없음(서브에이전트 래퍼만 해석) |

### 6.3 Verification
- [ ] `tests/application/agent_builder/test_workflow_compiler*.py` 전체 통과
- [ ] 승인 게이트 서브에이전트 전파 테스트(approval-gate-run-termination G3) 통과
- [ ] master 상시 실패 목록 외 신규 FAILED 0

---

## 7. Architecture Considerations

### 7.1 Project Level
Enterprise 상당 — Thin DDD(domain → application → infrastructure), 기존 구조 유지. 레이어 이동 없음.

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 대화 범위 | 지시+원 질문 / +최근 N턴 / 부모 messages 전체 | **지시+원 질문** | 서브에이전트를 독립 전문가로 다룸. 토큰이 적고 자식 supervisor가 혼동할 여지가 적음 (사용자 선택) |
| 워커 산출 | 상한 내 참고자료 / 미전달 / 직전 1건 | **상한 내 참고자료** | 재수집 방지. task 요약 과정의 데이터 손실 보완 (사용자 선택) |
| 설정 단위 | 고정 / 연결별 설정 / 서버 config | **고정 + 전략 인터페이스** | 이번엔 스키마·프론트 무변경. 다음 사이클에 연결별 설정으로 넘어갈 때 `resolve()`만 확장 (사용자 지시: "1로 하되 2로 넘어갈 수 있게 인터페이스화") |
| 규칙 위치 | 전략 내부 / domain Policy | **domain Policy** | 판별·상한은 비즈니스 규칙. 전략은 메시지 객체 조립만 담당 (CLAUDE.md 레이어 책임) |
| 주입 메시지 타입 | AIMessage / HumanMessage | **HumanMessage(라벨)** | 자식 supervisor의 워커 산출 판별·quality_gate(`type=="ai"`)와 충돌 방지 |

### 7.3 구조 미리보기

```
domain/agent_builder/policies.py
  └─ SubAgentContextPolicy        # 원 질문/이번 턴 산출 판별, 상한·절단, 라벨

application/agent_builder/sub_agent_context.py   (신규)
  ├─ SubAgentInput (dataclass: messages, summary)
  ├─ SubAgentContextStrategy (Protocol: build(state, worker_id) -> SubAgentInput)
  ├─ TaskWithOriginStrategy       # 기본 전략
  └─ resolve_strategy(worker_def, default) -> Strategy   # FR-09 확장 지점

application/agent_builder/workflow_compiler.py
  └─ _wrap_sub_agent: strategy.build(state) → build_initial_state(messages=...)
```

조립 결과(기본 전략):
```
Human: [원 질문]\n<이번 턴 사용자 질문>
Human: [참고 자료 — 상위 에이전트 제공]\n<worker_a 산출>\n---\n<worker_b 산출> (…절단됨)
Human: [현재 작업]\n<worker_task>  (+ 재시도면 [재시도 사유] <QG 피드백>)
```

---

## 8. Convention Prerequisites

| Category | Current State | To Verify |
|----------|---------------|-----------|
| 레이어 규칙 | `idt/CLAUDE.md` §2, `/verify-architecture` | domain Policy에서 LangChain import 금지 |
| 로깅 | `docs/rules/logging.md` | 요약 로그 값 미포함, `print` 금지 |
| 테스트 | `docs/rules/testing.md`, `uv run python -m pytest` | Red→Green 순서 |
| 위키 계약 | supervisor-graph-contracts ①③ | 산출 1건 계약 유지, 강제 라우팅 규약 비충돌 |

환경변수·DB 마이그레이션: 없음.

---

## 9. Next Steps

1. [ ] `/pdca design subagent-context-scope`. Design에서 확정할 열린 질문:
   - Q-D1: QG 재시도 시점의 `worker_task` 잔존 여부 실측 → 보존 방식 결정
   - Q-D2: 참고자료 상한 4000자 고정 vs `SearchPipelinePolicy.DEFAULT_COMPRESS_THRESHOLD` 공유
   - Q-D3: 원 질문 판별 제외 대상 전수(QG 피드백·재주입 마커·첨부 안내·user context 블록)
2. [ ] 구현 (TDD)
3. [ ] `/pdca analyze` + L3 실런(SC-7)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-10-02 | Initial draft — 코드 실측 + 사용자 질의 4건 반영 | 배상규 |
| 0.2 | 2026-10-03 | FR-10 추가 — module-3 착수 중 서브에이전트 런타임 실패 회귀 발견, 범위 포함 승인 | 배상규 |
| 0.3 | 2026-10-03 | FR-11·FR-12 추가 — module-4 실런 중 운영 차단 버그 2건 발견, 범위 포함 승인. 참고: `quality_gate_enabled`는 운영 경로에서 항상 False(QG 재시도 미발생) — FR-05 실효는 QG 활성 시에 한함 | 배상규 |
