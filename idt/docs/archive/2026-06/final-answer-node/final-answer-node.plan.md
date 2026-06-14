# Plan: final-answer-node

> Created: 2026-06-10
> Phase: Plan
> Scope: `idt/` 백엔드 — Supervisor 그래프(workflow_compiler.py)에 모든 워커 결과(웹서치·데이터분석·차트)를 종합하는 **필수 최종 답변 노드** 도입

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | Supervisor 그래프의 최종 답변 생성 주체가 경로마다 다르다. ① 검색 워커가 있으면 `answer_agent`(검색결과만 종합), ② supervisor가 FINISH 시 `decision.answer`로 직접 작성, ③ 그것도 없으면 마지막 워커의 raw 메시지가 그대로 답변이 된다. 웹서치+분석+차트가 섞인 멀티 워커 실행에서는 결과가 종합되지 않고 마지막 노드 출력에 좌우되어 답변 품질이 비일관적이다. |
| **Solution** | 워커가 1개 이상 실행된 모든 런이 종료 직전 **`final_answer` 노드를 필수 경유**하도록 그래프를 재배선한다. 검색결과·분석결과·차트 메타데이터를 한 번에 모아 정제된 최종 답변을 생성하고, 기존 `answer_agent`(가상 워커 방식)는 이 노드로 통합·제거한다. |
| **Function UX Effect** | 어떤 워커 조합이 실행되든 사용자는 항상 하나의 일관된 종합 답변을 받는다. 차트(`state["charts"]`)는 그대로 프론트에 전달되고 답변 텍스트가 차트를 자연스럽게 참조한다. 단순 대화(워커 미실행)는 기존처럼 즉시 응답 — 비용·지연 증가 없음. |
| **Core Value** | "최종 답변 생성"이라는 단일 책임을 가진 노드 하나로 수렴 → 그래프 예측 가능성·답변 품질 일관성 확보. 검색 전용 `answer_agent` 가상 워커 핵 제거로 컴파일 로직 단순화. |

---

## 0. 확정된 설계 결정 (사용자 Q&A, 2026-06-10)

| # | 질문 | 결정 |
|---|------|------|
| D1 | final_answer 실행 조건 | **워커 실행 시에만** 경유. supervisor 직접 답변(단순 대화)은 기존처럼 즉시 END — LLM 호출 추가 없음 |
| D2 | 기존 answer_agent 처리 | **final_answer로 통합·제거**. 가상 워커(`__virtual__`) 등록 방식도 제거 |
| D3 | quality_gate 경유 여부 | **END 직행**. 각 워커 결과가 이미 quality_gate를 통과했으므로 최종 정제 단계는 검증 생략(무한루프 위험 차단, 기존 answer_agent와 동일 패턴) |
| D4 | sub_agent 적용 범위 | **최상위(depth=0)만**. 서브 에이전트는 원시 결과를 부모에게 그대로 반환(토큰 이중 정제 방지) |

---

## 1. 배경 / 문제 정의

### 1-1. 현재 최종 답변 생성 경로 3가지 (코드 근거)

| 경로 | 조건 | 답변 생성 주체 | 한계 |
|------|------|---------------|------|
| ① `answer_agent` | 검색 워커 존재 시에만 (`workflow_compiler.py:214~222`) | `_create_answer_node` — **검색결과만** 종합 (`:451~507`) | 분석결과·차트는 종합 대상 아님. supervisor가 명시적으로 라우팅해야만 실행(가상 워커) |
| ② supervisor FINISH answer | `SupervisorDecision.answer` 작성 시 (`supervisor_nodes.py:150~160`) | supervisor LLM (라우팅 결정과 동일 호출) | 라우팅 결정용 structured output의 부산물 — 종합·정제 품질 보장 없음 |
| ③ 마지막 메시지 | 그 외 (`run_agent_use_case.py:819~823` `messages[-1]`) | 마지막 워커의 raw 출력 | 분석 노드 출력 등이 정제 없이 그대로 사용자에게 노출 |

### 1-2. 핵심 문제

1. **종합 부재**: 웹서치 + 데이터분석 + 차트빌더가 모두 실행된 런에서, 각 결과를 한 번에 모아 정제하는 노드가 없다. analysis 노드는 검색결과를 참조하지만(`_analyze_context`), 그 반대 방향이나 차트 메타 반영은 없다.
2. **answer_agent의 불완전한 보장**: 가상 워커라 supervisor LLM이 호출을 "선택"해야 실행됨 — 검색 후 FINISH로 직행하면 우회된다. "무조건 거친다"가 구조적으로 보장되지 않는다.
3. **차트-답변 비정합**: chart_builder가 만든 차트(`state["charts"]`)와 최종 답변 텍스트 사이에 아무 연결이 없어, 답변이 차트를 언급하지 않거나 모순될 수 있다.

---

## 2. 목표 / 비목표

### 2-1. 목표
- **G1.** `final_answer` 노드 신설 — 워커가 1개 이상 실행된 런은 종료 직전 **구조적으로(라우팅으로) 필수 경유**. supervisor LLM의 선택에 의존하지 않는다.
- **G2.** 입력 종합: 검색결과 AIMessage + 분석결과 AIMessage + `state["charts"]` 메타(개수/제목) + 대화 맥락을 컨텍스트로 정제된 최종 답변 생성.
- **G3.** 차트 보존: `state["charts"]`는 수정·재생성하지 않고 그대로 통과. 답변 텍스트에 차트 JSON 인라인 금지(차트 참조 문장만 허용).
- **G4.** `answer_agent` 통합 제거 — 가상 워커 등록(`workflow_compiler.py:214~222`), 전용 노드/엣지, supervisor 라우트 맵 항목 제거.
- **G5.** depth=0에서만 적용 (D4).
- **G6.** 멀티턴 대화 맥락 보존 — `FIX-ANSWER-NODE-MULTITURN-CONTEXT` 회귀 방지(첫 user 메시지만 전달되던 버그 재발 금지).
- **G7.** 관측성·스트리밍 연동 — `track_step` 래핑, `_collect_node_names`/`_infer_node_type` 갱신, WS 토큰 스트리밍 정상 동작.

### 2-2. 비목표
- **N1.** supervisor 직접 답변 경로(워커 미실행) 변경 — 기존 즉시 END 유지 (D1).
- **N2.** quality_gate 로직·정책 변경 (D3: final_answer는 END 직행).
- **N3.** sub_agent 내부 그래프 변경 (D4).
- **N4.** General Chat / Excel Standalone 경로 변경 — Supervisor 그래프 한정.
- **N5.** 프론트 차트 렌더링 확장(메모리 기준: 차트 렌더는 General Chat 경로만 연결, Supervisor 확장은 별도 feature).

---

## 3. 목표 아키텍처

### 3-1. 현재 (As-Is)

```
supervisor ──route_to_worker──▶ worker(search/analysis/action/sub_agent)
   │                              ├─ analysis → chart_router → (chart_builder) → quality_gate
   │                              └─ 그 외 → quality_gate
   │                                              └─ route_after_quality → supervisor | worker(재시도)
   ├─ "answer_agent" 선택 시(검색 워커 있을 때만) → answer_agent → END
   └─ "__end__"(FINISH) → END    ← 종합 없이 종료되는 구멍
```

### 3-2. 변경 후 (To-Be)

```
supervisor ──route_to_worker──▶ worker(search/analysis/action/sub_agent)
   │                              ├─ analysis → chart_router → (chart_builder) → quality_gate
   │                              └─ 그 외 → quality_gate
   │                                              └─ route_after_quality → supervisor | worker(재시도)
   └─ "__end__"(FINISH) ─┬─ last_worker_id == ""(워커 미실행) → END     (D1: 단순 대화)
                          └─ last_worker_id != ""              → final_answer → END  (D3: 직행)

final_answer 입력 컨텍스트:
  - 검색결과 AIMessage들 (_is_search_result)
  - 분석결과 AIMessage들 (name=worker_id, 분석 워커 산출)
  - state["charts"] 메타 (개수/제목 — JSON 본문은 인라인 금지, state로 그대로 전달)
  - 대화 맥락 (멀티턴 보존)
  - (Design 결정) supervisor FINISH 시 작성한 draft answer
```

- 라우팅은 `route_to_worker`의 `__end__` 분기에서 `last_worker_id` 유무로 결정 — **supervisor LLM 선택이 아닌 그래프 라우팅 함수로 보장** (G1의 핵심).
- depth>0(sub_agent 내부 컴파일)에서는 `final_answer` 미등록 + 기존 `__end__ → END` 라우팅 유지 (D4).

### 3-3. 구현 방향 (Design에서 상세화)

| 항목 | 방향 |
|------|------|
| 라우팅 | `route_to_worker`(또는 신규 `route_to_worker_or_final`)가 `next_worker == "__end__"`일 때 `state["last_worker_id"]` 유무로 `"final_answer"` / `"__end__"` 분기. route_map에 `"final_answer"` 추가. depth 인자로 분기 활성화 제어 |
| 노드 구현 | `_create_answer_node`를 `_create_final_answer_node`로 일반화. 검색결과 수집 로직 유지 + 분석결과(name 있는 AIMessage) 수집 + `state["charts"]` 메타 블록 추가. 멀티턴 처리(검색결과만 본체 제외, 대화 맥락 전달) 패턴 유지 |
| answer_agent 제거 | 가상 WorkerDefinition(`:214~222`), `has_search_workers` 기반 노드/엣지/route_map 등록(`:302~310, :344~345, :369~370`) 제거. supervisor decision prompt에서 answer_agent 관련 의존 정리 |
| 관측성 | `_wrap_step("final_answer", NodeType.OTHER, ...)` 래핑. `run_agent_use_case.py:118`(`_infer_node_type`), `:133`(`_collect_node_names`)의 `"answer_agent"` → `"final_answer"` 교체 |
| 차트 | final_answer는 `charts`를 읽기 전용으로 참조(메타만 프롬프트에 주입). 반환 dict에 `charts` 미포함(state 병합 유지) |

---

## 4. 영향 범위 (Affected Files)

### 4-1. 백엔드 (idt/)

| 파일 | 변경 |
|------|------|
| `src/application/agent_builder/workflow_compiler.py` | **핵심** — final_answer 노드 등록(depth=0), answer_agent 가상 워커·노드·엣지 제거, `_create_answer_node` → `_create_final_answer_node` 일반화 |
| `src/application/agent_builder/supervisor_nodes.py` | `__end__` 분기 라우팅 함수(`last_worker_id` 기반), supervisor decision prompt 문구 정리(FINISH 의미: "작업 완료 시 FINISH → 시스템이 최종 답변 생성") |
| `src/application/agent_builder/run_agent_use_case.py` | `_infer_node_type`(:118), `_collect_node_names`(:133) 노드명 교체, 스트리밍 이벤트 매핑 확인 |
| `src/application/agent_builder/supervisor_state.py` | (필요 시) 변경 없음 예상 — 기존 `last_worker_id`/`charts` 활용 |

### 4-2. 테스트

| 테스트 | 내용 |
|--------|------|
| `tests/.../test_workflow_compiler.py` 등 answer_agent 관련 | answer_agent → final_answer 전환 갱신 |
| 신규: final_answer 라우팅 | 워커 실행 후 FINISH → final_answer 경유, 워커 미실행 FINISH → END 직행, sub_agent(depth>0) 미경유 |
| 신규: final_answer 종합 | 검색+분석+차트 혼합 state에서 모든 소스가 프롬프트 컨텍스트에 포함, charts 비파괴, 멀티턴 맥락 보존(회귀: fix-answer-node-multiturn-context) |
| `test_run_agent_use_case_stream.py` | final_answer 노드의 토큰 스트리밍/step 이벤트 매핑 |

### 4-3. Cross-Project (idt_front)

- 프론트 step 변환은 `kind` 기반 필터(`agentStepToToolEvent.ts:17`)라 **노드명 변경의 기능 영향 없음**.
- `useAgentRunStream.test.ts`의 `answer_agent` fixture와 주석만 정리(선택). API 스키마 변경 없음 → `/api-contract-sync` 불필요 추정(Design에서 최종 확인).

---

## 5. 작업 분해 (TDD: Red → Green → Refactor)

1. **(Red)** 라우팅 테스트 — FINISH + `last_worker_id` 있음 → `final_answer`, 없음 → `__end__`, depth>0 → 기존 동작.
2. **(Green)** 라우팅 함수 + route_map + depth 게이트 구현.
3. **(Red)** final_answer 노드 테스트 — 검색/분석/차트 혼합 종합, charts 비파괴, 멀티턴 보존, 검색결과 없는 분석-only 런.
4. **(Green)** `_create_final_answer_node` 구현 (기존 `_create_answer_node` 일반화).
5. **(Red→Green)** answer_agent 제거 + 기존 테스트 갱신 (가상 워커/엣지/route_map).
6. **(Red→Green)** run_agent_use_case 노드명·스트리밍 매핑 갱신.
7. **(Refactor/verify)** `verify-architecture`, `verify-logging`, `verify-tdd`, pytest 격리 실행(Windows 이벤트 루프 flakiness 회피).

---

## 6. 리스크 / 주의사항

- **R1. 이중 답변 생성** — supervisor가 워커 실행 후 FINISH하면서 `decision.answer`도 작성하면, final_answer와 답변이 2개가 된다. → Design에서 처리 방식 확정(§7-1). supervisor prompt에서 "워커 실행 후에는 answer 작성 불필요" 안내가 유력.
- **R2. 강제 종료 경로** — `max_iterations`/`token_limit` 도달 시 `next_worker="__end__"`로 강제 종료되는데(`supervisor_nodes.py:98~106`), 이때도 워커가 실행됐다면 final_answer로 라우팅된다. 부분 결과로라도 정제 답변을 주는 장점 vs 한도 초과 상태에서 LLM +1회 호출. → Design 결정(§7-2).
- **R3. 멀티턴 회귀** — `FIX-ANSWER-NODE-MULTITURN-CONTEXT` 수정 사항(검색결과만 본체 제외, 전체 대화 맥락 전달)을 일반화 과정에서 반드시 보존. 회귀 테스트 필수.
- **R4. WS 스트리밍** — final_answer의 LLM 토큰이 WS로 스트림된다. chunk.content가 block list인 모델에서 `[object Object]` 깨짐 이슈(메모리) → `coerce_message_text` 정규화 경유 확인.
- **R5. 분석결과 식별 규칙** — 현재 검색결과는 `_is_search_result`(content 내 "검색결과" 문자열)로 식별하지만, 분석결과는 `name=worker_id`만 있다. 일반 action 워커·sub_agent 결과도 name이 붙으므로 "워커 산출물 수집 규칙"을 Design에서 명확히 정의(§7-4). 취약한 문자열 매칭 의존 줄이는 방향 검토.
- **R6. 기존 answer_agent 의존 테스트/문서** — 백엔드 8곳 + 프론트 테스트 fixture. 제거 시 일괄 갱신.
- **R7. 테스트 flakiness** — pytest 교차 실행 시 Windows 이벤트 루프 teardown 산발 실패 → 격리 실행으로 검증.

---

## 7. Design 단계 Open Questions

1. **supervisor FINISH draft answer 처리** — (a) final_answer 입력 컨텍스트로 포함(초안 활용), (b) 폐기, (c) prompt에서 워커 실행 후 answer 작성 자체를 금지. *(a 또는 c 유력)*
2. **강제 종료 시 final_answer 실행 여부** — token_limit 초과 상태에서도 정제 호출을 허용할지, 마지막 메시지 fallback으로 둘지.
3. **노드명** — 신규 `final_answer` vs 기존 `answer_agent` 명칭 유지(역할만 확장 — 백엔드/프론트 fixture 변경 최소화). 본 Plan은 `final_answer` 기준으로 기술.
4. **워커 산출물 수집 규칙** — 분석/검색/action/sub_agent 결과 메시지를 final_answer 컨텍스트로 모으는 기준(name 기반 전부 vs 카테고리별 마킹). `_is_search_result` 문자열 매칭 의존도 정리 여부.
5. **차트 메타 주입 형식** — 프롬프트에 차트 개수/제목만 줄지, 차트 유형·축 정보까지 줄지(답변-차트 정합성 수준).

---

## 8. 다음 단계

```
/pdca design final-answer-node
```
