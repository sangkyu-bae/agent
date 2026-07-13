# agent-recursion-limit Planning Document

> **Summary**: 에이전트 그래프 실행 시 supervisor 반복 한도를 **에이전트별로 DB에 설정**(기본 25회, 10~1000회)하고, 한도 도달 시 오류(RUN_FAILED)나 무한 루프 대신 **그동안 수집한 정보로 final_answer 노드를 경유해 정상 답변으로 종료**한다. LangGraph 자체 `recursion_limit`(기본 25 스텝)이 state 기반 가드보다 먼저 터지는 현재 결함도 함께 해소한다(설정값에서 파생 계산해 상향). 한도 도달 사실은 이벤트 플래그 + 답변 내 안내로 사용자에게 전달한다.
>
> **Project**: sangplusbot (idt 백엔드 전용 — Studio UI는 후속)
> **Author**: 배상규
> **Date**: 2026-07-08
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 에이전트 그래프의 반복 한도가 이원화·방치되어 있다. ① LangGraph `recursion_limit`을 어디서도 설정하지 않아 시스템 기본 25 스텝이 적용되는데, 1회 반복이 3~5 스텝(supervisor→worker→[chart_router→chart_builder]→quality_gate)을 소비하므로 자체 가드(`max_iterations=10`)에 닿기 전 **GraphRecursionError로 RUN_FAILED** 되는 경우가 있다. ② `max_iterations`는 하드코딩(10)이라 에이전트별 조정이 불가능하다. ③ 한도 도달 시 사용자는 그때까지 워커가 수집한 정보를 전혀 받지 못한다. |
| **Solution** | `agent_definition`에 `max_iterations`(INT, 기본 25, 범위 10~1000) 컬럼을 추가하고 생성/수정 API로 노출한다. 실행 시 이 값을 `SupervisorConfig`에 주입하고, LangGraph `recursion_limit`은 `max_iterations × 스텝계수 + 여유분`으로 파생 설정해 **항상 state 가드가 먼저** 발동하게 한다. 한도 도달 시 supervisor는 `limit_reached` 플래그를 세우고 기존 `final_answer` 경유 라우팅으로 지금까지의 정보로 답변을 생성·종료한다. GraphRecursionError는 최후 안전망으로 잡아 축적 메시지 기반 답변으로 강등 처리한다. |
| **Function/UX Effect** | 에이전트 제작자: API로 에이전트별 반복 한도 설정(미설정 시 25). 최종 사용자: 복잡한 질의도 무한 루프·오류 없이 "한도 내 최선의 답변 + 한도 도달 안내"를 받는다. 프론트: `ANSWER_COMPLETED` payload의 `limit_reached` 플래그로 배지/알림 표시 가능(UI 구현은 후속). |
| **Core Value** | 답변 불능(RUN_FAILED/무한 루프)을 구조적으로 제거해 에이전트 실행의 **예측 가능성**을 확보한다. 한도는 에이전트 복잡도에 맞게 조정 가능하되 기본값·범위로 안전하게 제한되며, 부분 정보라도 반드시 사용자에게 전달된다. |

---

## 1. Overview

### 1.1 Purpose

에이전트 그래프 실행의 반복 한도를 **단일 소스(agent_definition.max_iterations)**로 통합하고, 한도 도달을 "실패"가 아니라 "조기 답변"으로 처리한다.

```
현재:  recursion_limit(시스템 25 스텝, 설정 불가) ──먼저 발동──▶ GraphRecursionError → RUN_FAILED
       max_iterations(하드코딩 10)              ──늦게/미발동──▶ __end__ (안내 없음)

목표:  agent_definition.max_iterations (기본 25, 10~1000)
         ├─▶ SupervisorConfig.max_iterations  → state 가드 (반복 카운트, 항상 먼저 발동)
         │      └─ 도달 시: limit_reached=true → final_answer 경유 → 지금까지 정보로 답변 + 안내
         └─▶ graph_config["recursion_limit"] = max_iterations × K + buffer (파생, 안전망)
                └─ 그래도 터지면: GraphRecursionError catch → 축적 메시지로 강등 답변
```

### 1.2 Background — 현재 구조 (2026-07-08 코드 확인)

**반복 카운트 인프라는 이미 존재 — 설정 경로만 부재**
- `SupervisorState.iteration_count / max_iterations` 존재 (`src/application/agent_builder/supervisor_state.py:11-12`).
- supervisor 노드 가드: `iteration_count >= max_iterations`면 `{"next_worker": "__end__"}` 반환 (`src/application/agent_builder/supervisor_nodes.py:168-171`) — warning 로그만 남기고 **사용자 안내 없음**.
- `SupervisorConfig` 기본값 `max_iterations=10` (`src/domain/agent_builder/schemas.py:12-18`), 실행 시 `SupervisorConfig()` 무인자 생성 (`src/application/agent_builder/run_agent_use_case.py:480`) — **에이전트별 값 주입 경로 없음**.

**한도 도달 시 final_answer 경유 라우팅도 depth=0에 이미 존재**
- `route_to_worker_or_final`: `next_worker == "__end__"` 이고 `last_worker_id`가 있으면 `final_answer`로 우회 (`supervisor_nodes.py:331-340`). `final_answer` 노드는 depth=0에만 등록 (`workflow_compiler.py:351-361`), `final_answer → END` (`workflow_compiler.py:427`).
- 즉 "지금까지 정보로 답변"의 골격은 있음. 부족한 것: ① 한도 도달 사실을 final_answer 프롬프트·이벤트로 전달, ② 워커 미실행 상태(`last_worker_id` 빈 값)로 한도 도달 시 END 직행하는 엣지 케이스.

**LangGraph recursion_limit 미설정 — 관측된 결함의 원인**
- `graph.astream_events(initial_state, config=graph_config, ...)` (`run_agent_use_case.py:254-256`)의 `graph_config`(`_build_graph_config`, `:539`)에 `recursion_limit` 없음 → LangGraph 기본 **25 슈퍼스텝**.
- 1회 반복 소비 스텝: supervisor(1) + worker(1) + [chart_router(1) + chart_builder(1)] + quality_gate(1) = 3~5 → **약 5~8회 반복 만에 GraphRecursionError** 발생 가능. `max_iterations=10` 가드가 있어도 그 전에 시스템 한도가 먼저 터진다. 예외는 `except Exception` (`run_agent_use_case.py:309-318`)에서 `RUN_FAILED`로 종료 — 답변 없음.

**sub-agent(중첩 실행)**
- `_wrap_sub_agent`가 `SupervisorConfig(token_limit=state["token_limit"] // 2)`로 서브 그래프 실행 (`workflow_compiler.py:931-937`) — `max_iterations`는 기본 10 고정. token_limit 절반 상속 선례 있음.

**DB / API**
- `agent_definition` 모델(`src/infrastructure/agent_builder/models.py:10`)에 반복 한도 컬럼 없음. 도메인 `AgentDefinition`(`src/domain/agent_builder/schemas.py:78`)은 `temperature` 범위 검증 선례(`__post_init__`, `:102-104`) 보유.
- 최신 마이그레이션 V044 → **이번 사이클 V045부터**. 단순 INT 컬럼 추가(FK 아님 — 콜레이션 이슈 무관).

### 1.3 사용자 결정 사항 (2026-07-08 확인)

| 질문 | 결정 |
|------|------|
| limit 1회의 단위 | **supervisor 반복 횟수** (기존 `iteration_count` 재사용). LangGraph `recursion_limit`은 이 값에서 파생 계산해 내부 설정 |
| 기본값 / 범위 | **기본 25회, 설정 범위 10~1000회** (미설정 시 25) |
| 한도 도달 알림 | **이벤트 + 답변 안내** — `ANSWER_COMPLETED` payload에 `limit_reached` 플래그(전용 이벤트 추가 여부는 Design에서 확정) + final_answer 프롬프트에 "반복 한도 도달, 지금까지 정보로 답변" 지시 |
| 작업 범위 | **백엔드만 먼저** (DB + 도메인 + API + 실행 경로). Studio UI 입력 필드는 후속 |
| sub-agent 한도 | **부모의 절반(`// 2`)** — 단, 계수를 정책 상수로 분리해 문제 발생 시 즉시 변경 가능하게 |

---

## 2. Scope

### 2.1 In Scope (백엔드 idt/)

**A. DB 마이그레이션**
- [ ] `V045__alter_agent_definition_add_max_iterations.sql` (additive): `max_iterations INT NOT NULL DEFAULT 25`
- [ ] `AgentDefinitionModel`에 컬럼 매핑 추가 (`src/infrastructure/agent_builder/models.py`), repository save/update/매핑 반영

**B. 도메인 규칙**
- [ ] `AgentDefinition.max_iterations: int = 25` 필드 + `__post_init__` 범위 검증(10~1000) — temperature 선례와 동형
- [ ] 반복 한도 정책(`src/domain/agent_builder/policies.py`): 기본값 25 / MIN 10 / MAX 1000 / **recursion_limit 파생 계수(스텝계수 K, 여유 buffer)** / **sub-agent 상속 계수(기본 `// 2`, 하한 보장)** — 전부 상수로 두어 변경 용이
- [ ] `SupervisorConfig` 기본 `max_iterations` 25로 상향(하드코딩 10 대체)

**C. API (생성/수정/조회)**
- [ ] create/update 요청 스키마에 `max_iterations` 선택 필드(미전달 시 25), 범위 밖이면 검증 오류 (`src/application/agent_builder/schemas.py`, `create_agent_use_case.py`, `agent_builder_router.py`)
- [ ] 응답 스키마에 `max_iterations` 포함 (additive — 프론트 타입 동기화는 후속 UI 작업에서 `/api-cotract`로 일괄)

**D. 실행 경로 — 한도 주입과 조기 답변**
- [ ] `run_agent_use_case._prepare_graph`: `SupervisorConfig(max_iterations=agent.max_iterations, ...)` 주입 + `graph_config["recursion_limit"] = 파생값` 설정 → **state 가드가 항상 먼저 발동** 보장
- [ ] supervisor 가드 도달 시 `limit_reached: true`를 state에 기록(`SupervisorState`에 additive 필드) → `final_answer` 프롬프트에 한도 도달 안내 지시 주입 → 답변에 자연스러운 안내 포함
- [ ] `ANSWER_COMPLETED` payload에 `limit_reached` 플래그 추가 (전용 이벤트 타입 추가 여부는 Design 결정)
- [ ] 엣지 케이스: 워커 미실행 상태로 한도 도달(`last_worker_id` 빈 값) 시에도 답변 없이 END 직행하지 않도록 라우팅 보완(Design에서 확정 — MIN 10이라 실사용 확률은 낮음)
- [ ] **안전망**: `GraphRecursionError` catch 시 RUN_FAILED 대신 축적 메시지(`state.final_messages`) 기반 강등 답변 시도, 실패 시에만 RUN_FAILED (기존 `except Exception` 분기 앞에 전용 분기)

**E. sub-agent**
- [ ] `_wrap_sub_agent`: `SupervisorConfig(max_iterations=부모값 // 2 (정책 상수·하한 적용), token_limit=기존 유지)` — token_limit 절반 선례와 동형

**F. 테스트 (TDD — 구현 전 작성)**
- [ ] 도메인: 범위 검증(9/10/1000/1001), 기본값 25, recursion_limit 파생 계산, sub-agent 계수
- [ ] 유스케이스: 에이전트 설정값이 SupervisorConfig·graph_config에 반영되는지 / 한도 도달 → final_answer 경유 + `limit_reached` payload / GraphRecursionError 안전망
- [ ] API: create/update에서 max_iterations 저장·검증 오류·기본값
- [ ] 노드: supervisor 가드가 `limit_reached` 플래그를 남기는지, 라우팅 보완 케이스

### 2.2 Out of Scope

- **Studio UI 입력 필드** (idt_front) — 후속 PDCA. 응답 스키마는 이번에 미리 노출
- `general_chat` 경로의 `max_iterations`(별도 파이프라인, `use_case.py:122`) — 대상 아님
- `token_limit` 재설계, quality_gate `max_retries_per_worker` 설정화 — 필요 시 별도 사이클
- 대화 메모리 정책·Parent/Child 문서 구조 변경 없음 (CLAUDE.md 금지 사항 준수)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | 요구사항 | 수용 기준 |
|----|----------|-----------|
| FR-01 | 에이전트별 반복 한도 저장 | `agent_definition.max_iterations` INT NOT NULL DEFAULT 25, 기존 행은 자동 25 |
| FR-02 | 범위 검증 | 10 미만 또는 1000 초과 입력 시 생성/수정 API가 검증 오류 반환. 미입력 시 25 |
| FR-03 | 실행 시 한도 적용 | 그래프 실행이 에이전트의 `max_iterations`를 supervisor 반복 한도로 사용. LangGraph `recursion_limit`은 파생값으로 설정되어 state 가드보다 먼저 발동하지 않음 |
| FR-04 | 한도 도달 시 조기 답변 | 한도 도달 시 오류가 아니라 `final_answer` 노드를 경유해 그때까지 수집된 정보로 답변 생성·정상 종료(RUN_COMPLETED) |
| FR-05 | 도달 사실 전달 | 답변 텍스트에 한도 도달 안내 포함 + `ANSWER_COMPLETED` payload `limit_reached: true` |
| FR-06 | 안전망 | 만에 하나 GraphRecursionError 발생 시 축적 메시지로 답변 시도 후 종료(불가 시에만 RUN_FAILED) |
| FR-07 | sub-agent 한도 | 부모 한도의 절반(정책 상수, 하한 보장)로 실행. 계수는 상수 1곳 수정으로 변경 가능 |

### 3.2 Non-Functional

- additive 변경만 — 기존 에이전트는 마이그레이션 후 동작 변화가 "더 관대한 한도(10→25) + 조기 답변"뿐
- 레이어 준수: 한도 규칙(범위·파생 계수)은 domain, 주입·라우팅은 application, 컬럼은 infrastructure
- 로깅: 한도 도달·안전망 발동 시 request_id 포함 warning (LOG-001)

---

## 4. Risks & Considerations

| 리스크 | 대응 |
|--------|------|
| recursion_limit 파생 계수(K)가 작으면 여전히 시스템 한도가 먼저 터짐 | 그래프 최악 경로(supervisor+worker+chart_router+chart_builder+quality_gate=5) 기준 K≥6 + buffer로 산정, Design에서 그래프 구조 기준 확정. FR-06 안전망 병행 |
| max_iterations=1000 × 워커 다수 = 실행 시간·토큰 폭주 | 기존 `token_limit` 가드가 병행 발동(변경 없음). sub-agent 절반 상속으로 중첩 폭주 방지 |
| 한도 도달 답변의 품질(정보 부족 시 환각) | final_answer 프롬프트에 "수집 정보 범위 내에서만, 부족하면 부족하다고 명시" 지시 포함 |
| `limit_reached` payload 추가 → 프론트 계약 | additive 필드라 무해. UI 후속 작업 시 `/api-cotract` 실행 명시 |

---

## 5. Success Criteria

- [ ] 재현 시나리오(빙글 도는 에이전트)에서 RUN_FAILED 없이 한도 도달 안내가 포함된 답변으로 종료
- [ ] 에이전트별로 다른 한도가 실제 반복 횟수에 반영됨 (LangSmith 트레이스로 확인 가능)
- [ ] 전체 테스트 통과 (사전 실패분 제외 — tests/api 28건·infra 30건은 기존 실패)

## 6. Next Steps

1. `/pdca design agent-recursion-limit` — recursion_limit 파생식(K, buffer), `limit_reached` 이벤트 형태(플래그 vs 전용 타입), 워커 미실행 엣지 케이스 라우팅, GraphRecursionError 안전망 구현 위치 확정
2. Do: TDD로 A→F 순 구현 (마이그레이션 → 도메인 → API → 실행 경로 → sub-agent)
3. 후속 PDCA: Studio UI 입력 필드 + `/api-cotract` 동기화
