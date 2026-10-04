# subagent-context-scope Design Document

> **Summary**: 서브에이전트 워커의 입력을 `[원 질문] + [참고 자료(이번 턴 워커 산출, 최신 우선 4000자)] + [현재 작업(worker_task, 재시도면 사유 덧붙임)]`으로 조립한다. 판별·상한·라벨 규칙은 domain `SubAgentContextPolicy`, 메시지 조립은 application `SubAgentContextStrategy`(Protocol)가 맡고, `resolve_strategy()`를 연결별 설정의 확장 지점으로 둔다.
>
> **Project**: sangplusbot (idt)
> **Version**: —
> **Author**: 배상규
> **Date**: 2026-10-03
> **Status**: Draft (v0.1)
> **Planning Doc**: [subagent-context-scope.plan.md](../../01-plan/features/subagent-context-scope.plan.md)

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

### 1.1 Design Goals
1. 서브에이전트가 일반 react 워커와 같은 계약(worker-context-injection FR-05: 지시 전달)을 따르게 한다.
2. 입력 조립을 교체 가능한 단위로 분리한다. 다음 사이클의 `context_mode`(연결별 설정)는 `resolve_strategy()` 한 곳만 바꾸면 되게 한다.
3. 기존 출력 계약을 그대로 둔다: AIMessage(name) 1건, 토큰 합산, approval_pending 전파, 반복·토큰 한도 절반.

### 1.2 Design Principles
- **규칙은 domain, 메시지 객체는 application**: Policy는 `str`·dataclass만 다룬다. LangChain 타입은 application의 어댑터 함수 한 곳에서만 해석한다(ToolErrorPolicy와 같은 duck typing 방식).
- **fail-safe 하위호환**: 원 질문도 과제도 못 찾으면 현행 동작(마지막 메시지 1건)을 그대로 쓴다. 기존 MagicMock 기반 테스트 5건을 고치지 않고 통과시킨다.
- **얇게**: 전략은 지금 1종이다. 레지스트리·enum은 만들지 않는다(CLAUDE.md "과도한 추상화 금지").

---

## 2. Architecture Options

### 2.0 Architecture Comparison

| Criteria | Option A: Minimal | Option B: Clean | Option C: Pragmatic |
|----------|:-:|:-:|:-:|
| **Approach** | 컴파일러 안 헬퍼 함수 | 포트+enum+레지스트리+settings DI | domain Policy + application Protocol/기본 전략/resolve |
| **New Files** | 0 | 4 | 2 |
| **Modified Files** | 1 | 4 | 1 (+테스트) |
| **Complexity** | Low | High | Medium |
| **Maintainability** | Low (확장 시 컴파일러 수정) | High | High |
| **Effort** | Low | High | Medium |
| **Risk** | 요구("인터페이스화") 미충족 | 과한 추상화 | Low |

**Selected**: **Option C — Pragmatic** (Checkpoint 3, 사용자 선택). **Rationale**: 사용자 요구("1로 하되 2로 넘어갈 수 있게 인터페이스화")를 최소 파일로 충족한다. 전략이 하나뿐인 지금 단계에서 레지스트리와 enum은 YAGNI다.

### 2.1 Component Diagram

```
┌──────────────────── application/agent_builder ─────────────────────┐
│ workflow_compiler.py                                                │
│   __init__(…, sub_agent_context_strategy=None)                      │
│   _compile_sub_agent ──resolve_strategy(worker_def, default)──┐     │
│   _wrap_sub_agent(worker_id, sub_graph, strategy=None) ◀──────┘     │
│        │ strategy.build(state, worker_id) → SubAgentInput           │
│        ▼                                                            │
│ sub_agent_context.py  (신규)                                        │
│   SubAgentInput · SubAgentContextStrategy(Protocol)                 │
│   TaskWithOriginStrategy · resolve_strategy · to_message_views      │
└───────────────────────────────┬─────────────────────────────────────┘
                                │ MessageView(str 만)
┌───────────────────────────────▼──── domain/agent_builder ───────────┐
│ sub_agent_context_policy.py  (신규)                                  │
│   MessageView · ReferenceBlock · SubAgentContextPolicy              │
│   (REINJECTED_MARKER ← domain/conversation/analysis_snapshot_policy)│
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 Data Flow

```
부모 SupervisorState
  ├ messages ──to_message_views()──▶ [MessageView…]
  └ worker_task
          │
          ▼  TaskWithOriginStrategy.build(state, worker_id)
  policy.find_origin_index(views)          → 원 질문 index (QG 피드백·재주입 제외)
  policy.collect_references(views, idx, worker_id) → 이번 턴 다른 워커 산출
  policy.render_references(refs)           → 최신 우선 4000자, 시간순 출력
  policy.detect_retry_feedback(views)      → 마지막이 QG 피드백이면 그 문장
  policy.compose_task(task, origin, feedback)
          │
          ▼
  SubAgentInput(messages=[user:원 질문, user:참고자료?, user:현재 작업], summary)
          │
          ▼  _wrap_sub_agent
  build_initial_state(messages=…) → sub_graph.ainvoke → AIMessage(name) 1건
  out[STEP_OUTPUT_SUMMARY_KEY] = summary
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `SubAgentContextPolicy` | `REINJECTED_MARKER` (domain/conversation) | 재주입분 판별 단일 출처 |
| `TaskWithOriginStrategy` | `SubAgentContextPolicy`, `QUALITY_FEEDBACK_PREFIX` (search_pipeline) | QG 피드백 접두를 Policy에 주입. domain이 application 상수를 import하지 않게 한다 |
| `WorkflowCompiler._wrap_sub_agent` | `SubAgentContextStrategy` | 입력 조립 위임 |

---

## 3. Data Model (메모리 내 VO — DB 변경 없음)

### 3.1 domain — `sub_agent_context_policy.py`

```python
@dataclass(frozen=True)
class MessageView:
    role: str      # "user" | "ai" | "system" | "tool" | "" (정규화 결과)
    name: str      # AIMessage.name (워커 id), 없으면 ""
    content: str   # str 이 아니면 str() 변환

@dataclass(frozen=True)
class ReferenceBlock:
    text: str          # 렌더된 [참고 자료] 블록 본문 (라벨 포함). 산출 없으면 ""
    item_count: int    # 실린 산출 수
    total_chars: int   # 실린 본문 글자 수 (라벨 제외)
    truncated: bool    # 산출 드롭 또는 개별 절단 발생 여부

class SubAgentContextPolicy:
    DEFAULT_REFERENCE_MAX_CHARS = 4000
    ORIGIN_LABEL = "[원 질문]"
    REFERENCE_LABEL = "[참고 자료 — 상위 에이전트가 이번 요청에서 이미 수집한 결과]"
    REFERENCE_GUIDE = "아래 자료는 참고용입니다. 필요한 경우에만 다시 수집하세요."
    TASK_LABEL = "[현재 작업]"
    RETRY_LABEL = "[재시도 사유]"
    TRUNCATED_NOTE = "…(절단됨)"

    def __init__(self, feedback_prefixes: tuple[str, ...] = (),
                 reference_max_chars: int | None = None) -> None: ...

    def find_origin_index(self, views) -> int | None
    def collect_references(self, views, origin_index, self_worker_id) -> list[MessageView]
    def render_references(self, refs) -> ReferenceBlock
    def detect_retry_feedback(self, views) -> str
    def compose_task(self, task: str, origin: str, feedback: str) -> str
    def summarize(self, *, has_origin, ref: ReferenceBlock, retry: bool, fallback: bool) -> str
```

### 3.2 application — `sub_agent_context.py`

```python
@dataclass(frozen=True)
class SubAgentInput:
    messages: list[dict]   # build_initial_state 입력 그대로 ({"role":"user","content":…})
    summary: str           # step output_summary 용. 본문 값 미포함

class SubAgentContextStrategy(Protocol):
    def build(self, state: SupervisorState, worker_id: str) -> SubAgentInput: ...

class TaskWithOriginStrategy:          # 기본 전략
    def __init__(self, policy: SubAgentContextPolicy | None = None) -> None
    def build(self, state, worker_id) -> SubAgentInput

def to_message_views(messages: list) -> list[MessageView]   # LangChain/dict → VO
def resolve_strategy(worker_def: WorkerDefinition,
                     default: SubAgentContextStrategy) -> SubAgentContextStrategy
    # 현재: 항상 default. 다음 사이클 context_mode 분기의 유일한 지점 (FR-09)
```

### 3.3 규칙 상세 (Policy가 소유)

| 규칙 | 정의 | 근거 |
|------|------|------|
| **R1 역할 정규화** | dict는 `role`, 객체는 `type`. `human`→`user`, `assistant`→`ai`. 그 외는 그대로, 문자열이 아니면 `""` | MagicMock 메시지는 `""`가 되어 원 질문으로 잡히지 않는다 → fallback |
| **R2 원 질문** | 뒤에서부터 role=`user`이고, 본문이 feedback 접두로 시작하지 않으며, `REINJECTED_MARKER`를 포함하지 않는 첫 메시지 | `latest_user_question()`(search_pipeline:130)과 같은 규칙 + 재주입 제외 |
| **R3 이번 턴 경계** | R2의 index. 기존 `_current_turn_messages`는 QG 피드백을 경계로 오인하므로 쓰지 않는다 | Q-D3 실측 |
| **R4 참고자료 대상** | 경계 이후 + role=`ai` + name 있음 + name ≠ 자기 worker_id + 재주입 아님 + 본문 비어 있지 않음 | 자기 직전 실패 산출을 되먹이지 않는다(재시도는 R6이 담당) |
| **R5 상한·절단** | 최신 산출부터 예산(기본 4000자, 본문 기준)을 채운다. 첫 산출(=최신)이 혼자 예산을 넘으면 앞부분 `budget`자 + `TRUNCATED_NOTE`. 예산이 바닥나면 더 오래된 산출은 드롭(`truncated=True`). 출력은 **시간순**, 각 항목 `"[{name} 산출]\n{content}"`, 구분자 `"\n---\n"` | 사용자 선택: 최신 산출 우선 |
| **R6 재시도 판별** | 마지막 view가 role=`user`이고 feedback 접두로 시작하면 그 본문 | QG 재시도는 supervisor를 거치지 않아 worker_task가 유지된다(Q-D1 실측, `route_after_quality`) |
| **R7 과제 합성** | `task or origin`을 본문으로 한다. feedback이 있으면 `\n\n{RETRY_LABEL}\n{feedback}`을 덧붙인다 | FR-05, FR-06 |
| **R8 요약** | `"서브에이전트 입력: 원질문 {O/X} / 참고자료 {n}건 {chars}자{(절단)} / 재시도 {O/X}"`, fallback이면 `"서브에이전트 입력: 레거시(마지막 메시지)"` | FR-07, 본문 값 없음 |

### 3.4 조립 결과 (TaskWithOriginStrategy.build)

```
case 정상:
  [{"role":"user","content":"[원 질문]\n<origin>"},
   {"role":"user","content":"[참고 자료 — …]\n<guide>\n\n[w1 산출]\n…\n---\n[w2 산출]\n…"},   # 참고자료 없으면 생략
   {"role":"user","content":"[현재 작업]\n<task>(\n\n[재시도 사유]\n<feedback>)"}]

case fallback (origin 없음 AND task 없음):
  [{"role":"user","content": <state.messages[-1].content>}]      # 현행과 바이트 동일
```

- 메시지를 3건으로 나누고 마지막을 `[현재 작업]`으로 두는 이유: 자식 search 파이프라인의 `latest_user_question()`이 쿼리 재작성 입력으로 **과제**를 집도록 하기 위해서다. 연속 user 메시지는 `_build_worker_input`(첫 워커 호출)에서도 이미 쓰는 패턴이다.
- origin만 있고 task가 없으면(강제 라우팅 등) `[원 질문]` 블록과 `[현재 작업]\n<origin>`이 중복된다. 중복을 피하려고 이 경우는 `[원 질문]` 블록을 생략하고 `[현재 작업]`만 둔다.

---

## 4. API Specification

변경 없음. 외부 API·스키마·프론트 타입 모두 그대로다(API 계약 동기화 불필요).

---

## 5. UI/UX Design

해당 없음. 실행 이력 화면에 step output_summary 문자열만 새로 보인다. 기존 렌더링을 그대로 쓰므로 프론트는 바꾸지 않는다.

---

## 6. Error Handling

| 상황 | 처리 |
|------|------|
| `strategy.build` 예외 | `_wrap_sub_agent`가 잡아 `logger.error(..., exception=e)`로 스택을 남기고 **fallback 입력(현행)**으로 진행한다. 서브에이전트 실행 자체는 막지 않는다 |
| content가 list(멀티모달) 등 비문자열 | R1처럼 `str()`로 변환한다. 원 질문 판별에 쓰는 데는 문제가 없다 |
| `worker_task` 키 부재(구 state) | `state.get("worker_task", "")` |
| 참고자료 0건 | 블록을 생략하고 summary에 `0건`으로 남긴다 |

로깅: `logger.info("sub_agent input built", worker_id=…, blocks=<메시지 수>, summary=<R8 요약 문자열>)`. 원질문 유무·참고자료 건수·글자 수·절단·재시도·fallback 정보는 R8 요약 문자열에 이미 들어 있으므로 따로 필드를 두지 않는다(step output_summary와 같은 문자열을 써서 출처를 하나로 유지). 본문은 남기지 않는다(테스트 C4b).

---

## 7. Security Considerations

- [ ] 참고자료는 부모 워커 산출(외부 수집물 포함)을 그대로 싣는다. 지시문이 승격되지 않도록 **라벨 + "참고용" 안내**로 감싸고, 자식의 `[현재 작업]`보다 앞에 둔다. EmptyResultPolicy §7과 같은 취지다.
- [ ] 로그와 step summary에는 길이·개수만 남기고 본문은 남기지 않는다.
- [ ] 권한 범위는 바뀌지 않는다. 자식은 부모의 auth_ctx/subject로 실행되며 현행과 같다.

---

## 8. Test Plan

> L1/L2(HTTP·UI)는 해당 없음(내부 그래프 변경). 단위·통합 테스트(pytest)와 L3 실런으로 대체한다.

### 8.1 Test Scope

| Type | Target | Tool |
|------|--------|------|
| Unit | `SubAgentContextPolicy` R1~R8 | pytest (`tests/domain/agent_builder/test_sub_agent_context_policy.py`) |
| Unit | `TaskWithOriginStrategy`, `to_message_views`, `resolve_strategy` | pytest (`tests/application/agent_builder/test_sub_agent_context.py`) |
| Integration | `_wrap_sub_agent` 입력·summary·fallback·예외 | pytest (`test_workflow_compiler_sub_agent.py` 확장) |
| Regression | 기존 `_wrap_sub_agent` 사용 테스트 5건 무수정 통과 | pytest |
| L3 | 실제 에이전트 실런 | TestClient 인프로세스 + 실행 이력 조회 |

### 8.2 Unit — Policy

| # | Case | Expected |
|---|------|----------|
| P1 | 메시지 `[user q, ai(w1), user "[품질검증 실패]…"]` | origin=0, retry=피드백 문장 |
| P2 | 이전 턴 `[user q1, ai final, user q2, ai(w1)]` | origin=2, refs=[w1]. 이전 턴 ai는 제외 |
| P3 | 재주입 메시지(`REINJECTED_MARKER` 포함, user/ai 각각) | origin·refs 모두에서 제외 |
| P4 | refs에 자기 worker_id 산출 포함 | 제외 |
| P5 | 산출 3건 합계 < 4000 | 시간순 전부, truncated=False |
| P6 | 산출 3건 중 최신 1건만 들어가는 경우 | 최신 1건만, 오래된 2건 드롭, truncated=True, 출력은 시간순 |
| P7 | 최신 1건이 5000자 | 앞 4000자 + TRUNCATED_NOTE, truncated=True |
| P8 | `compose_task("", origin, "")` | origin |
| P9 | `compose_task(task, origin, fb)` | task + RETRY_LABEL + fb |
| P10 | `summarize` | 본문 값 미포함, 형식 고정 |
| P11 | MagicMock(type 속성이 MagicMock) | role `""` → origin 없음 |

### 8.3 Unit — Strategy

| # | Case | Expected |
|---|------|----------|
| S1 | 첫 라우팅: `[user q]`, task="X 조회" | 2건: 원 질문, 현재 작업(X 조회) |
| S2 | 중간 라우팅: `[user q, ai(w1) 결과]`, task="요약" | 3건, 참고자료에 w1 산출, 마지막이 현재 작업 |
| S3 | QG 재시도: `[user q, ai(w1), ai(sub) 짧음, user 피드백]`, task 유지 | 마지막 블록 = task + 재시도 사유. 참고자료에 sub 자기 산출 없음 |
| S4 | task 없음 + origin 있음 | `[현재 작업]\n<origin>` 1건(원 질문 블록 생략) |
| S5 | origin·task 모두 없음 | fallback: 마지막 메시지 content 그대로 1건 |
| S6 | 출력 messages 어떤 것도 `is_search_result()` True가 아님 | dict이므로 False (강제 라우팅 비충돌 고정) |
| S7 | `resolve_strategy(worker_def, d)` | `d` 반환 |

### 8.4 Integration — Compiler

| # | Case | Expected |
|---|------|----------|
| C0 | (FR-10) 컴파일된 부모 그래프의 서브에이전트 노드를 실제 실행 | `_wrap_worker` 미경유, AttributeError 없이 AIMessage(name) 1건 |
| C1 | `_wrap_sub_agent(id, g)` (strategy=None) | 기본 전략으로 입력을 조립하고 `sub_graph.ainvoke` 첫 인자 messages에 반영 |
| C2 | 대역 전략 주입(`_wrap_sub_agent(id, g, FakeStrategy())`) | FakeStrategy의 messages가 그대로 전달됨 (SC-5) |
| C3 | 생성자 `sub_agent_context_strategy=Fake` → `_compile_sub_agent` | resolve 경유로 Fake 사용 |
| C4 | out에 `STEP_OUTPUT_SUMMARY_KEY` 존재, 기존 키·approval_pending 전파 불변 | SC-6 |
| C5 | 전략이 예외 발생 | error 로그(exception) + fallback 입력으로 정상 실행 |
| C6 | `WorkflowCompiler.__new__` 로 만든 인스턴스(`__init__` 미호출) | AttributeError 없이 동작 (test_gated_run_termination 호환) |

### 8.5 L3 실런 시나리오

| # | Scenario | Success Criteria |
|---|----------|-----------------|
| L3-1 | 부모(검색 워커 w1 + 서브 "요약 에이전트") 지침: "조회 결과는 요약 에이전트에게 3줄 요약을 맡겨라". 질문: "X 조회해서 요약해줘" | 실행 이력: w1 → sub. sub step summary `참고자료 1건`, 자식 내부에서 검색 재수집 0회, 최종 답변이 3줄 요약 |
| L3-2 | 부모 지침에 "요약 에이전트에게는 대상·기간을 명시해 넘겨라" | 자식 입력 `[현재 작업]`에 대상·기간 포함 (부모 지침의 호출 방식 전달 확인) |
| L3-3 | QG 재시도 유도(자식이 10자 미만 응답) | 재시도 시 자식 입력의 마지막 블록 = 원 task + 재시도 사유 |

### 8.5.1 L3 실행 결과 (2026-10-03, gpt-5.1, 인프로세스 TestClient)

| # | run_id | 결과 | 근거 |
|---|--------|------|------|
| L3-1 | `41cc2367` | ✅ | 라우팅 supervisor → tavily_search_worker → `sub_agent_[L3]_요약_서브_0`. 서브 step 요약 `원질문 O / 참고자료 1건 1052자`. 도구 호출 2건 모두 부모 워커 — 자식 supervisor: "추가 검색 없이 3줄 요약만 하면 된다" (재수집 0) |
| L3-2 | `41cc2367` | ✅ | 자식 입력 `[현재 작업]`: "주제: 2026년 9월 … 기간: 2026-09-01 ~ 2026-09-30 … 3줄로 요약" — 부모 지침의 호출 방식 전달 |
| L3-3 | `d6b5affc` | ✅ (QG 강제 활성) | 서브 호출 3회: 1회차 `재시도 X`, 2·3회차 마지막 블록 = 원 task + `[재시도 사유] [품질검증 실패] …`, 자기 산출 제외로 참고자료 0건. 운영 경로는 `quality_gate_enabled=False` 고정이라 프로세스 내 패치로만 재현 |
| (선행) | `08f917c7` | ⚠→수정 | FR-12 발견 런 — 서브 다음 supervisor 400(name 패턴) → `__end__` 폴백 |

관측 메모(범위 밖): 자식 그래프 step이 같은 run에 `supervisor`/`quality_gate` 이름으로 섞여 기록돼 부모·자식 구분이 안 되고, 일부 latency가 음수로 찍힌다.

### 8.6 Seed Data
로컬 DB에 부모·자식 에이전트 정의 2건(sub_agent 연결)을 둔다. `memory: idt-local-db-and-run-repro` 레시피(TestClient 인프로세스, JWT 로컬 토큰)를 쓴다.

---

## 9. Clean Architecture

### 9.4 Layer Assignment

| Component | Layer | Location |
|-----------|-------|----------|
| `MessageView`, `ReferenceBlock`, `SubAgentContextPolicy` | Domain | `src/domain/agent_builder/sub_agent_context_policy.py` |
| `SubAgentInput`, `SubAgentContextStrategy`, `TaskWithOriginStrategy`, `to_message_views`, `resolve_strategy` | Application | `src/application/agent_builder/sub_agent_context.py` |
| `_wrap_sub_agent`, `_compile_sub_agent`, `__init__` | Application | `src/application/agent_builder/workflow_compiler.py` |

Import 규칙: domain 파일은 `src.domain.conversation.analysis_snapshot_policy`만 import한다. LangChain·application은 import하지 않는다(`/verify-architecture`).

---

## 10. Coding Convention Reference

| Item | Convention Applied |
|------|-------------------|
| 함수 길이 | 40줄 이하. `build()`는 views 변환 → 판별 → 조립 3단계 private 메서드로 분리 |
| if 중첩 | 2단계 이하. R4 필터는 조건 함수 `_is_reference(v)`로 평탄화 |
| 로깅 | `LoggerInterface`, 예외는 `exception=e`, `print` 금지 |
| 주석 | `# Design Ref: subagent-context-scope §3.3 R5 — …`, `# Plan SC: SC-n` |
| 테스트 실행 | `uv run python -m pytest` |

---

## 11. Implementation Guide

### 11.1 File Structure

```
src/domain/agent_builder/sub_agent_context_policy.py          (신규)
src/application/agent_builder/sub_agent_context.py            (신규)
src/application/agent_builder/workflow_compiler.py            (수정: __init__, _compile_sub_agent, _wrap_sub_agent)
tests/domain/agent_builder/test_sub_agent_context_policy.py   (신규)
tests/application/agent_builder/test_sub_agent_context.py     (신규)
tests/application/agent_builder/test_workflow_compiler_sub_agent.py (확장)
```

### 11.2 Implementation Order (TDD)

1. [ ] P1~P11 Red → `SubAgentContextPolicy` Green
2. [ ] S1~S7 Red → `sub_agent_context.py` Green
3. [ ] C1~C6 Red → `workflow_compiler.py` 수정 Green
4. [ ] 회귀: `tests/application/agent_builder/` 전체 + master 상시 실패 목록과 FAILED diff
5. [ ] `/verify-architecture`, `/verify-logging`, `/verify-tdd`
6. [ ] L3-1~3 실런

### 11.3 Session Guide

#### Module Map

| Module | Scope Key | Description | Estimated Turns |
|--------|-----------|-------------|:---:|
| Domain Policy | `module-1` | VO + Policy R1~R8 + P 테스트 | 8~10 |
| Strategy | `module-2` | Protocol·기본 전략·resolve·변환 + S 테스트 | 6~8 |
| Compiler wiring | `module-3` | 생성자 인자·resolve 호출·래퍼 교체·summary·예외 fallback + C 테스트 + 회귀 | 6~8 |
| L3 verification | `module-4` | 로컬 실런 3시나리오 | 5~8 |

#### Recommended Session Plan
- 세션 1: `/pdca do subagent-context-scope --scope module-1,module-2`
- 세션 2: `/pdca do subagent-context-scope --scope module-3`, 이어서 `module-4`

---

## 12. Decision Record

| ID | Decision | Rationale |
|----|----------|-----------|
| D-01 | Option C (Policy + Protocol + resolve) | 사용자 선택. 확장 지점 1곳, 과추상화 회피 |
| D-02 | 참고자료 최신 우선 채움, 출력은 시간순 | 사용자 선택. 서브에이전트는 직전 단계 결과를 이어받는 경우가 많다 |
| D-03 | 상한은 전용 상수 4000자(생성자로 조정 가능) | 사용자 선택. 검색 압축 임계와 의미가 다르다 |
| D-04 | 메시지 3건 분리, 마지막이 `[현재 작업]` | 자식 `latest_user_question()`이 과제를 집도록 |
| D-05 | 이번 턴 경계를 새로 정의(R3), `_current_turn_messages` 재사용 안 함 | 기존 함수는 QG 피드백을 경계로 오인한다(실측) |
| D-06 | 자기 산출 제외(R4) | 재시도 시 실패 산출을 되먹이지 않는다. 사유는 R6가 전달 |
| D-07 | 전략은 `_wrap_sub_agent` 인자(기본 None)로 받음 | `__new__` 테스트 호환, 래퍼 단위 테스트 용이 |
| D-08 | 조립 실패 시 현행 입력으로 fail-safe | 관측 기능 때문에 위임을 막지 않는다 |
| D-09 | QG 피드백 접두는 전략이 Policy에 주입 | domain → application import 금지 |
| D-10 | (Do 중 추가) sub_agent 분기에서 `function_node_ids.add` | 회귀 `3a25eb7` 수정 — 래퍼가 이미 노드 함수라 `_wrap_worker`를 거치면 안 된다 |
| D-11 | (Do 중 추가) fail-safe 입력을 `legacy_input()` 공개 함수로 | 전략 내부 폴백과 컴파일러 예외 폴백이 같은 함수를 쓴다(단일 출처) |
| D-12 | (FR-11) `SessionScopedAgentDefinitionRepository` 신설 + `main.py`에서 컴파일러에 `agent_repository`·`llm_model_repository`(기존 `SessionScopedLlmModelRepository`) 주입 | 앱 싱글톤은 per-request 세션을 쥘 수 없다 — 기존 SessionScoped 어댑터 6종과 같은 패턴. 서브에이전트 정의 조회는 메인 세션과 별개 세션(읽기 전용) |
| D-13 | (FR-12) `sanitize_llm_name()` 공개 + 빌더 id 생성·`clamp_llm_name` 양쪽 적용, 전략의 자기 산출 비교는 `clamp_llm_name(worker_id)` 기준 | 신규 id는 저장 시점에, 기존 저장 id는 메시지 이름 단계에서 방어. 한글은 OpenAI 패턴 허용이라 보존(supervisor 가독성) |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-10-03 | Initial draft — Option C, 열린 질문 Q-D1~3 실측 확정 | 배상규 |
| 0.2 | 2026-10-03 | module-3: C0·D-10(런타임 회귀 수정)·D-11(legacy_input) 추가 | 배상규 |
| 0.3 | 2026-10-03 | module-4: D-12(FR-11 저장소 DI)·D-13(FR-12 name 정규화)·L3 실행 결과 §8.5.1 | 배상규 |
