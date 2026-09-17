# supervisor-early-finish-fix Design Document

> **Summary**: 빈 수집 결과를 결정적 신호로 state에 올리고, supervisor 결정 프롬프트에 조건부 블록으로 알린 뒤, 미해소 상태의 첫 FINISH를 라우팅 함수가 1회 되돌린다.
>
> **Project**: sangplusbot (idt 백엔드)
> **Version**: 미지정
> **Author**: 배상규
> **Date**: 2026-09-16
> **Status**: Draft
> **Planning Doc**: [supervisor-early-finish-fix.plan.md](../../01-plan/features/supervisor-early-finish-fix.plan.md)

### 선행 계약 문서 (필수 준수)

| 문서 | 상태 | 이 설계에 미치는 구속 |
|------|:----:|----------------------|
| [Supervisor 그래프 계약 3종](../../wiki/backend/patterns/supervisor-graph-contracts.md) | ✅ approved | 계약 ①②③ 전부 적용 — §1.2 참조 |
| [백엔드 아키텍처 조감도](../../wiki/backend/architecture-overview.md) | ✅ approved | supervisor 그래프는 요청마다 DB 정의로 동적 컴파일 |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 빈 결과를 데이터 부재로 오판해 남은 워커를 시도하지 않고 종료한다 (트레이스 `01a0a82b` 실증) |
| **WHO** | P2 — KB 운영자/에이전트 소유자. 자연어로 수집 지침을 등록하고 결과를 신뢰해야 하는 사용자 |
| **RISK** | 빈 결과 오탐으로 정상적인 "0건" 응답까지 되물어 지연·토큰이 늘어난다 |
| **SUCCESS** | 재현 시나리오에서 FINISH 1회 차단이 발생하고 후속 워커가 실행된다. 빈 결과 신호가 없으면 결정 프롬프트가 기존과 바이트 동일 |
| **SCOPE** | D(워커 규범 1건) + C(빈 결과 신호·블록·1회 되물음). 위키 절차 체크리스트(A)는 후속 피처 |

---

## 1. Overview

### 1.1 Design Goals

1. **"못 찾았다"와 "아직 안 해봤다"를 구분**한다 — 수집 성공 + 결과 없음을 별도 상태로 인식
2. 탐지는 **결정적**으로, 그 다음 행동은 **LLM 판단**에 맡긴다 (특정 워커를 강제하지 않는다)
3. 되물음은 **1회로 결정적 상한**을 가진다 — 종료 불가 상태를 구조적으로 만들 수 없어야 한다
4. 신호가 없으면 **기존 동작과 바이트 동일**하다
5. 후속 피처 `wiki-procedure-completion`이 **같은 게이트에 사유만 추가**하면 되도록 확장점을 남긴다

### 1.2 Design Principles

- **계약 ① 워커 산출물 = `AIMessage(name)` 1건** → 빈 결과 신호를 메시지로 넣지 않는다. state 채널만 사용한다. (메시지 추가 시 final_answer 필터가 짝을 깨 고아 tool 메시지 → OpenAI 400 재발)
- **계약 ② 목록 프레이밍 금지** → 블록에 `browser_click` 등 워커/도구 이름을 나열하지 않는다. 화이트리스트는 방어 지시를 이기고 과차단을 부른다. "상호작용이 필요한 작업이 남아 있다면" 같은 **조건부 서술**만 쓴다.
- **계약 ③ 결정적 신호 vs LLM 판단 책임 분리** → 빈 결과 *탐지*만 결정적이다. "그러므로 클릭해야 한다"는 판단은 LLM이 한다. 되물음은 특정 워커로 강제 라우팅하지 않고 **재결정 기회 1회**만 부여한다.
- **선례 동형** → 신규 state 채널은 `last_worker_error`(wiki-guided-routing D4)의 수명주기를 그대로 따른다: 워커가 매번 덮어쓰고, supervisor가 소비 후 리셋한다.
- **(D-08) 워커 규범에 "A라고만 하라"류 절대 프레이밍 금지** → 실측 회귀(트레이스 `01a0ae68`, 2026-09-17): 초안 문구 *"당신의 도구로 할 수 없는 일은 '이 워커의 범위 밖'이라고만 밝히세요"* 가 바로 위 기존 규범 *"데이터를 정재만 할뿐 어떠한 작업을 하지 마세요"* 와 결합되어, **4개 워커 전부가 도구 결과 전달을 버리고 그 문구만 반환**했다. `wiki_read`·`scrape_url` 모두 도구는 성공했는데 supervisor는 이를 도구 실패로 오인했다(`"wiki_read 호출이 실패한 상태"`). 규범은 **전달 의무를 먼저 못 박고**, 범위 밖 표기는 그 뒤에 덧붙이는 부가 행위로 격하해야 한다. 계약 ②(목록 프레이밍)와 같은 계열의 함정이다.
- **단일 책임** → 판정 규칙은 domain policy, 흐름 제어는 application.

---

## 2. Architecture Options

### 2.0 Architecture Comparison

| Criteria | Option A: Minimal | Option B: Clean | Option C: Pragmatic |
|----------|:-:|:-:|:-:|
| **Approach** | supervisor 노드 내부에서 판정 + LLM 2회 호출 | `finish_gate` 노드 신설 | state 신호 + 라우팅 함수 되돌림 |
| **New Files** | 0 | 1~2 | 0 |
| **Modified Files** | 4 | 7 | 6 |
| **그래프 변경** | 없음 | 노드+엣지 추가 | `route_map` 자기순환 1줄 |
| **State 변경** | 없음 | 신호+사유 필드 | 신호+pending 플래그 |
| **Complexity** | Low | High | Medium |
| **Maintainability** | Low (supervisor 노드 비대화) | High | High |
| **Effort** | Low | High | Medium |
| **Risk** | Medium (40줄 규칙 위반, 되물음이 트레이스에 안 보임) | Medium (모든 런의 실행 경로 변경) | Low |
| **A 피처 확장성** | Low | High | Medium~High |
| **Recommendation** | 핫픽스용 | 장기 프로젝트 | **선택됨** |

**Selected**: **Option C — Pragmatic**

**Rationale**:
- Option A는 `supervisor_node`가 이미 약 80줄(`supervisor_nodes.py:260-340`)이라 판정+재질의를 넣으면 CLAUDE.md §3 "함수 40줄" 규칙을 확실히 위반하고, 후속 A 피처가 같은 자리를 또 키운다. 되물음이 같은 노드 내 LLM 2회 호출로 나타나 트레이스에서 진단이 어렵다.
- Option B는 책임 분리가 가장 깨끗하지만, 워커 0개 순수 대화형 에이전트의 고아 노드 처리(`workflow_compiler.py:781` 선례)가 추가로 필요하고 **모든 에이전트 런의 실행 경로**가 바뀌어 회귀 표면이 가장 넓다.
- Option C는 그래프 노드를 추가하지 않고 기존 라우팅 함수 확장 패턴을 따른다. 되물음이 트레이스에 `supervisor` 2회로 드러나 진단 가능하고, 후속 A 피처는 같은 신호 채널에 사유를 더하면 된다.

### 2.1 Component Diagram

```
┌──────────────┐   messages/state    ┌───────────────┐
│  worker node │ ──────────────────▶ │  quality_gate │
│ (4개 팩토리) │                     └───────┬───────┘
└──────┬───────┘                             │
       │ _with_empty_signal 데코레이터        ▼
       │ (등록 루프 단일 지점)          ┌──────────────┐
       └──── last_worker_empty ───────▶│  supervisor  │
                                        └──────┬───────┘
                        블록 렌더 + pending=True│ next_worker
                        신호 리셋               ▼
                                    ┌───────────────────────────┐
                                    │ route_to_worker_or_final  │
                                    └───┬───────────┬───────────┘
                     pending & __end__  │           │ 그 외
                                        ▼           ▼
                                  "supervisor"  worker / final_answer
                                  (되물음 1회)
```

### 2.2 Data Flow

```
1. 워커 실행
   → 데코레이터가 산출 content로 EmptyResultPolicy.detect() 호출
   → 비었으면 state["last_worker_empty"] = 사유요약, 아니면 ""

2. supervisor 결정
   → last_worker_empty 가 비어있지 않으면:
        · "[수집 결과 확인 필요]" 블록을 결정 프롬프트에 주입
        · 반환 dict에 finish_challenge_pending = True
        · 반환 dict에 last_worker_empty = ""   (소비 후 리셋 — 블록은 1회만)
   → LLM 결정 (워커 선택 또는 FINISH)

3. route_to_worker_or_final
   → next_worker == "__end__" and finish_challenge_pending 이면 "supervisor" 반환
   → 그 외는 기존 로직 그대로

4. supervisor 재진입 (2회차)
   → last_worker_empty 는 이미 "" → 블록 없음
   → 반환 dict에 finish_challenge_pending = False (기회 소진)
   → LLM이 다시 FINISH를 내면 route가 통과시킴 → final_answer
```

**1회 상한이 카운터 없이 보장되는 근거**: 블록 렌더와 `pending=True` 세팅은 `last_worker_empty`가 비어있지 않을 때만 일어나고, 그 즉시 신호를 리셋한다. 재진입 시 신호가 없으므로 `pending`은 False로만 갈 수 있다. 따라서 되돌림은 신호 1건당 최대 1회다.

> **실측 정정(세션 3) — 위 보장은 happy path에만 성립했다.**
> `supervisor_node`에는 조기 return이 2곳 있다: ① LLM 결정 실패 fallback,
> ② 워커 미실행 + draft answer. 이 둘이 `finish_challenge_pending`을 그대로 두면
> route가 계속 supervisor로 돌려보내고, ①은 같은 실패를 반복해 **무한 루프**가 된다
> (`GraphRecursionError`, 회귀 3건으로 실측).
> **보강된 불변식**: `supervisor_node`의 *모든* return 경로가 `finish_challenge_pending`을
> 명시적으로 확정해야 한다. 특히 결정 실패는 되물음 대상이 아니므로 반드시 False다.
> 후속 피처 A가 같은 게이트에 사유를 추가할 때도 이 불변식을 먼저 확인할 것.

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `EmptyResultPolicy` (domain) | 없음 (순수 규칙) | 빈 결과 판정. 외부 라이브러리 타입 미참조 |
| `_with_empty_signal` 데코레이터 (application) | `EmptyResultPolicy`, `config` | 워커 산출 → state 신호 변환 |
| `_render_empty_result_block` (application) | 없음 | 조건부 블록 문자열 생성 |
| `supervisor_node` | 위 블록 렌더러 | 결정 프롬프트 조립 |
| `route_to_worker_or_final` | `SupervisorState` | 되물음 판정 (순수 함수 유지) |
| `_TOOL_USAGE_NORM` | 없음 | (D) 워커 규범 |

---

## 3. Data Model

### 3.1 State 스키마 확장 (`SupervisorState`)

```python
    # supervisor-early-finish-fix D-02: 직전 수집 워커의 '빈 결과' 요약.
    # last_worker_error 동형 — 워커가 매번 덮어쓰고(정상 시 ""), supervisor가
    # "[수집 결과 확인 필요]" 블록을 렌더한 뒤 ""로 리셋한다.
    # 도구는 성공했으나 유효 데이터가 없는 상태 (오류와 구분됨).
    last_worker_empty: str

    # supervisor-early-finish-fix D-05: FINISH 되물음 1회 기회 보유 플래그.
    # supervisor가 빈 결과 블록을 렌더할 때 True, 재진입 시 False로 소진된다.
    # route_to_worker_or_final이 읽어 __end__를 supervisor로 되돌린다.
    finish_challenge_pending: bool
```

> 두 필드 모두 `state.get(...)` 접근으로 읽어 기존 체크포인트(키 부재) 하위호환을 지킨다 — `limit_reached`·`last_worker_error` 선례와 동일.

### 3.2 Domain Policy 계약 (`EmptyResultPolicy`)

```python
class EmptyResultPolicy:
    """수집 산출의 '유효 데이터 부재' 판정 — 결정적 신호만 담당.

    Design Ref: supervisor-early-finish-fix D-07.
    ToolErrorPolicy와 같은 역할 분담: 확실한 신호는 여기서 결정적으로 뽑고,
    '그래서 무엇을 할 것인가'는 supervisor LLM이 판단한다 (그래프 계약 ③).
    LangChain 타입을 참조하지 않는다 — 문자열만 받는다.
    """

    MAX_SUMMARY_CHARS = 120
    MIN_BODY_CHARS = 200          # 1차: 산출 자체가 이보다 짧으면 빈 수집

    @staticmethod
    def detect(body: str, patterns: tuple[str, ...]) -> str:
        """빈 결과면 사유 요약을, 아니면 빈 문자열을 돌려준다.

        1차(구조적): body가 공백이거나 MIN_BODY_CHARS 미만 → 빈 수집
        2차(패턴):   설정으로 주입된 문구가 body에 있으면 → 데이터 영역 비어 있음
        """
```

**판정 재현율에 대한 정직한 기록**: 이번 실패 케이스(`fsb.or.kr`)는 네비게이션 메뉴 때문에 본문이 수천 자였고 `0.00%` 같은 숫자도 있었다. 따라서 **1차 구조적 신호로는 탐지되지 않으며, 실질적 탐지는 2차 패턴 분기가 담당한다.** 1차는 "도구가 빈 응답을 준" 케이스를 덮는 보완재다. 이 비대칭 때문에 패턴을 코드 상수가 아닌 **설정값**으로 두어 배포 없이 확장 가능하게 한다.

### 3.3 설정값 (`src/config.py`)

```python
    # supervisor-early-finish-fix D-07: 빈 결과 판정 보조 문구.
    # 사이트·언어별 표현은 데이터로 관리한다 (CLAUDE.md §3 config 하드코딩 금지,
    # 루트 §6-2 '특화는 데이터로, 코어에 하드코딩 금지').
    empty_result_patterns: str = "등록된 데이터가 없습니다,검색 결과가 없습니다,조회된 데이터가 없습니다,결과가 없습니다"
```

- 콤마 구분 문자열로 받아 로드 시 `tuple[str, ...]`로 정규화한다 (기존 config의 목록형 설정 관례를 따를 것 — 구현 시 확인)
- 환경변수로 덮어쓸 수 있어야 한다

### 3.4 Database Schema

**변경 없음.** DB 마이그레이션 없음.

---

## 4. 내부 계약 명세 (API Specification 대체)

HTTP API 변경이 없다. 대신 변경되는 내부 함수 계약을 명시한다.

### 4.1 변경/신설 함수 목록

| 함수 | 위치 | 구분 | 계약 |
|------|------|:----:|------|
| `EmptyResultPolicy.detect` | `domain/agent_builder/policies.py` | 신설 | `(body: str, patterns: tuple[str,...]) -> str` |
| `_with_empty_signal` | `application/agent_builder/workflow_compiler.py` | 신설 | `(fn, patterns) -> fn'` — 반환 dict에 `last_worker_empty` 주입 |
| `_render_empty_result_block` | `application/agent_builder/supervisor_nodes.py` | 신설 | `(state) -> str` — 신호 없으면 `""` |
| `create_supervisor_node.supervisor_node` | `application/agent_builder/supervisor_nodes.py` | 수정 | 블록 주입 + `finish_challenge_pending` 관리 |
| `route_to_worker_or_final` | `application/agent_builder/supervisor_nodes.py` | 수정 | pending 시 `"supervisor"` 반환 |
| `_TOOL_USAGE_NORM` | `application/agent_run/prompt_rendering.py` | 수정 | 규범 1건 추가 |
| `route_map` 구성 | `application/agent_builder/workflow_compiler.py:854` | 수정 | `route_map["supervisor"] = "supervisor"` |

### 4.2 `_with_empty_signal` — 단일 배선 지점

**결정 D-06**: 워커 팩토리는 실제로 4개다 — `_wrap_worker`(react), `create_collect_node`(collect), `create_search_pipeline_node`(search), `create_deep_search_node`(deep search). 각 팩토리를 개별 수정하는 대신 **노드 등록 루프 한 곳**에서 감싼다.

```python
# workflow_compiler.py 노드 등록 루프 (787행대)
for worker_id, worker_agent in worker_map.items():
    node_fn = (worker_agent if worker_id in function_node_ids
               else self._wrap_worker(worker_id, worker_agent, tool_call_limit))
    # D-06: 4개 워커 팩토리를 한 지점에서 덮는다.
    node_fn = _with_empty_signal(node_fn, empty_patterns)
    graph.add_node(worker_id, _wrap_step(worker_id, NodeType.WORKER, node_fn))
```

> **`_wrap_step`을 재사용하지 않는 이유**: `_wrap_step`은 `tracker is None or callback is None or run_id is None`이면 **원본 함수를 그대로 반환**한다(`workflow_compiler.py:749-750`). 추적이 미배선인 실행 경로(테스트, 백그라운드 잡 등)에서 신호가 통째로 사라진다. 신호 배선은 추적 배선 여부와 독립이어야 하므로 별도 데코레이터를 둔다.

**데코레이터 계약**:
- 입력 dict의 `messages[-1].content`(= 워커 산출 규약상 `AIMessage(name)` 1건)를 판정 대상으로 삼는다
- 반환 dict에 `last_worker_empty`를 항상 세팅한다 (정상이면 `""`) — 이전 턴 신호가 남지 않도록
- 워커가 `last_worker_error`를 이미 세팅했으면 **빈 결과 판정을 건너뛴다** (오류가 우선, 두 블록 동시 렌더 방지)
- 분석/차트/sub_agent 워커는 수집 워커가 아니므로 대상 여부를 구현 시 확정한다 → **§6.2 열린 질문**

### 4.3 블록 문구 (계약 ② 준수)

```
[수집 결과 확인 필요]
직전 워커는 정상 실행됐지만 유효한 데이터가 확인되지 않았습니다: {사유요약}
- 조작(검색 실행·조건 적용 등)이 선행돼야 데이터가 나타나는 페이지일 수 있습니다.
- 아직 시도하지 않은 방법이 남아 있다면 FINISH 대신 그 방법을 먼저 시도하세요.
- 이미 충분히 시도했다면 FINISH를 선택하고, 무엇이 확인되지 않았는지 answer에 밝히세요.
```

- 워커 이름·도구 이름을 **나열하지 않는다** (계약 ②). "아직 시도하지 않은 방법"이라는 조건부 서술로만 표현한다
- "반드시 시도하라"가 아니라 "남아 있다면"으로 서술해 오탐 시 LLM이 곧바로 FINISH를 재선택할 여지를 남긴다
- 블록 총 길이 400자 이내 (Plan NFR)

### 4.4 되물음 판정 (`route_to_worker_or_final`)

```python
def route_to_worker_or_final(state: SupervisorState) -> str:
    next_worker = state["next_worker"]
    # D-05: 빈 결과 미해소 상태의 첫 FINISH를 1회 되돌린다.
    # D-09: 한도 도달(limit_reached)은 되물음보다 우선 — 종료를 막지 않는다.
    if (next_worker == "__end__"
            and state.get("finish_challenge_pending")
            and not state.get("limit_reached")):
        return "supervisor"
    if next_worker == "__end__" and (
        state.get("last_worker_id") or state.get("limit_reached")
    ):
        return "final_answer"
    return next_worker
```

**순수 함수 유지**: 이 함수는 state를 쓰지 않는다. `pending` 소진은 supervisor 노드가 재진입 시 수행한다.

---

## 5. UI/UX Design

**해당 없음.** 프론트엔드 변경 없음. 사용자에게는 최종 답변 품질 변화로만 드러난다.

---

## 6. Error Handling

### 6.1 예외 상황 처리

| 상황 | 처리 | 근거 |
|------|------|------|
| 워커 산출이 `messages` 없이 반환 | 판정 생략, `last_worker_empty = ""` | 데코레이터가 방어적으로 처리 — 신규 코드가 기존 경로를 깨뜨리지 않는다 |
| `content`가 str이 아님 (list 등 멀티모달) | 판정 생략 | `_wrap_worker`의 기존 `hasattr(last, "content")` 방어와 동일 수준 |
| 패턴 설정이 비어 있음 | 1차 구조적 신호만 동작 | 설정 누락이 런 실패를 만들지 않는다 |
| `last_worker_error`와 빈 결과가 동시 성립 | 오류 우선, 빈 결과 판정 생략 | 블록 2개 동시 렌더 시 지시 충돌 |
| 되물음 직후 `max_iterations` 도달 | 한도 가드가 우선해 `__end__`/`final_answer` | D-09, Plan FR-07 |
| 되물음 후 LLM이 또 워커를 선택 | 정상 — 되물음의 의도된 결과 | |

### 6.2 열린 질문 (구현 착수 전 확정 필요)

| # | 질문 | 잠정 결론 |
|---|------|-----------|
| Q-01 | 분석(analysis)·차트·sub_agent 워커도 빈 결과 판정 대상인가? | **제외 권장** — 이들은 수집이 목적이 아니라 빈 산출이 정상일 수 있다. `analysis_worker_ids` / `function_node_ids` 로 구분 가능. Do 단계 착수 시 확정 |
| Q-02 | `config`의 패턴을 콤마 문자열로 둘지 리스트형 설정으로 둘지 | 기존 `src/config.py`의 목록형 설정 관례를 확인해 맞춘다 |
| Q-03 | `MIN_BODY_CHARS = 200`이 적정한가 | 실측 트레이스로 조정. 임계는 policy 상수로 두어 변경 비용을 낮춘다 |

---

## 7. Security Considerations

| 항목 | 검토 결과 |
|------|-----------|
| 권한·인증 | 변경 없음. 워커 도구가 기존대로 권한을 검증한다 |
| 개인정보 | 신호는 사유 요약(최대 120자)만 담는다. 수집 원문을 state에 추가 보관하지 않는다 |
| 프롬프트 인젝션 | 블록에 들어가는 사유 요약은 **정책이 생성한 고정 문구**이지 수집 원문이 아니다 — 외부 콘텐츠가 지시문 위치로 승격되지 않는다 |
| 비용 남용 | 되물음 1회 상한 + `max_iterations`·`token_limit` 가드 우선 |
| 로깅 | 사유 요약과 되물음 발동을 구조화 로그로 남긴다. 수집 원문은 로깅하지 않는다 |

---

## 8. Test Plan

### 8.1 Test Scope

| 레벨 | 대상 | 도구 |
|------|------|------|
| L1 단위 | `EmptyResultPolicy.detect` | pytest |
| L1 단위 | `_render_empty_result_block` 문구·길이·미발동 | pytest |
| L2 노드 | supervisor 노드의 블록 주입 / pending 세팅 / 신호 리셋 | pytest + fake LLM |
| L2 함수 | `route_to_worker_or_final` 되물음 분기 | pytest (순수 함수) |
| L3 통합 | 컴파일된 그래프에서 되물음 1회 → 2회차 통과 | pytest + 스텁 워커 |
| L3 회귀 | 신호 없을 때 결정 프롬프트 바이트 동일 | pytest |

### 8.2 L1 — `EmptyResultPolicy` 시나리오

| # | 입력 | 기대 |
|---|------|------|
| 1 | `""` | 빈 결과 (구조적) |
| 2 | 150자 본문 | 빈 결과 (구조적, `MIN_BODY_CHARS` 미만) |
| 3 | 3000자 본문 + `"등록된 데이터가 없습니다"` 포함 | 빈 결과 (패턴) — **재현 케이스** |
| 4 | 3000자 본문, 패턴 없음 | 정상 (`""`) |
| 5 | 패턴 튜플이 빈 경우 + 긴 본문 | 정상 (`""`) |
| 6 | 사유 요약 길이 | `MAX_SUMMARY_CHARS` 이내 |

### 8.3 L2 — supervisor 노드 시나리오

| # | 초기 state | 기대 |
|---|-----------|------|
| 1 | `last_worker_empty="..."` | 결정 프롬프트에 블록 포함, 반환에 `finish_challenge_pending=True`, `last_worker_empty=""` |
| 2 | `last_worker_empty=""` | 블록 미포함, 프롬프트가 기존과 **바이트 동일** |
| 3 | `finish_challenge_pending=True`로 재진입 | 블록 미포함, 반환에 `pending=False` |
| 4 | `last_worker_error`와 `last_worker_empty` 동시 | 오류 블록만 렌더 |

### 8.4 L2 — `route_to_worker_or_final` 시나리오

| # | state | 기대 반환 |
|---|-------|-----------|
| 1 | `__end__` + `pending=True` + `limit_reached=False` | `"supervisor"` |
| 2 | `__end__` + `pending=False` + `last_worker_id` 있음 | `"final_answer"` |
| 3 | `__end__` + `pending=True` + `limit_reached=True` | `"final_answer"` (한도 우선, D-09) |
| 4 | 워커 id | 그대로 반환 (기존 동작) |
| 5 | `__end__` + 워커 미실행 + pending False | `"__end__"` (순수 대화형 보존) |

### 8.5 L3 — 그래프 통합 (재현 시나리오)

스텁 워커가 `"…등록된 데이터가 없습니다…"`를 반환하고, 스텁 LLM이 항상 FINISH를 내도록 구성한다.

- **기대**: supervisor 노드가 정확히 **2회** 호출된다. 최종적으로 `final_answer`에 도달한다 (무한 루프 없음)
- **기대**: 1회차 결정 프롬프트에만 블록이 포함된다

### 8.6 회귀 보호

- `tests/application/agent_run/test_prompt_rendering.py` — (D) 규범 추가에 따른 단언 갱신
- 기존 supervisor·workflow_compiler 테스트 전량 통과
- `/verify-architecture`, `/verify-logging`, `/verify-tdd`

### 8.7 Seed Data Requirements

없음. 모든 테스트가 스텁으로 동작하며 외부 서비스·DB를 요구하지 않는다.

---

## 9. Clean Architecture

### 9.1 Layer Structure

```
domain/agent_builder/policies.py
  └ EmptyResultPolicy            ← 규칙만. 외부 타입 미참조

application/agent_builder/
  ├ supervisor_state.py          ← 채널 정의
  ├ supervisor_nodes.py          ← 블록 렌더, pending 관리, 라우팅 판정
  └ workflow_compiler.py         ← 데코레이터 배선, route_map
application/agent_run/
  └ prompt_rendering.py          ← (D) 워커 규범

config.py                        ← 빈 결과 패턴

infrastructure/  변경 없음
interfaces/      변경 없음
```

### 9.2 Dependency Rules

- `domain` → 어떤 상위 레이어도 참조하지 않는다. `EmptyResultPolicy`는 `str`만 받는다 (LangChain 타입 미참조 — `ToolErrorPolicy` 선례)
- `application` → `domain`, `config` 참조 가능
- 역방향 참조 없음

### 9.3 File Import Rules

- `supervisor_nodes.py`는 이미 `from src.domain.agent_builder.policies import QualityGatePolicy`를 한다 — 같은 모듈에서 `EmptyResultPolicy`를 가져온다
- 패턴 설정은 컴파일 시점에 `workflow_compiler`가 읽어 데코레이터에 주입한다. 노드 런타임에서 config를 직접 읽지 않는다 (테스트 주입 가능성 확보)

### 9.4 This Feature's Layer Assignment

| 산출물 | 레이어 | 근거 |
|--------|--------|------|
| `EmptyResultPolicy` | domain | 판정은 비즈니스 규칙 |
| `_with_empty_signal` | application | 그래프 배선·흐름 제어 |
| `_render_empty_result_block` | application | 프롬프트 조립 |
| 되물음 판정 | application | 라우팅 흐름 제어 |
| 패턴 값 | config | 데이터 |

---

## 10. Coding Convention Reference

### 10.1 Naming Conventions

| 대상 | 규칙 | 예 |
|------|------|-----|
| 도메인 정책 클래스 | `<대상>Policy` | `EmptyResultPolicy` (`ToolErrorPolicy` 선례) |
| 프롬프트 블록 렌더러 | `_render_<대상>_block` | `_render_empty_result_block` |
| state 채널 | `last_worker_<속성>` / `<동작>_<상태>` | `last_worker_empty`, `finish_challenge_pending` |
| 데코레이터 | `_with_<기능>` | `_with_empty_signal` |

### 10.2 Import Order

기존 파일 관례를 따른다 (표준 → 서드파티 → `src.*`).

### 10.3 Environment Variables

| Variable | Purpose | Scope | 신규 |
|----------|---------|-------|:----:|
| `EMPTY_RESULT_PATTERNS` (가칭) | 빈 결과 판정 보조 문구 | Server | ☑ |

기본값이 있어 미설정 시에도 동작해야 한다. 정확한 이름은 `src/config.py` 기존 명명 규칙에 맞춘다.

### 10.4 This Feature's Conventions

- 모든 신규 코드에 `# Design Ref: supervisor-early-finish-fix §N` 부착
- 핵심 로직에 `# Plan SC: FR-0N` 부착
- state 필드마다 설계 출처·수명주기 주석 (기존 `last_worker_error` 형식)
- 함수 40줄 이내, if 중첩 2단계 이내
- `print()` 금지, 구조화 로거 사용

---

## 11. Implementation Guide

### 11.1 File Structure

```
수정:
  src/domain/agent_builder/policies.py                  (+EmptyResultPolicy)
  src/config.py                                         (+패턴 설정)
  src/application/agent_builder/supervisor_state.py     (+2 필드)
  src/application/agent_builder/supervisor_nodes.py     (+블록 렌더, +pending, ~route)
  src/application/agent_builder/workflow_compiler.py    (+데코레이터, ~등록 루프, ~route_map)
  src/application/agent_run/prompt_rendering.py         (~_TOOL_USAGE_NORM)

테스트(신규/수정):
  tests/domain/agent_builder/test_empty_result_policy.py          (신규)
  tests/application/agent_builder/test_supervisor_empty_block.py  (신규)
  tests/application/agent_builder/test_finish_challenge_route.py  (신규)
  tests/application/agent_builder/test_empty_signal_wiring.py     (신규)
  tests/application/agent_run/test_worker_context_block.py        (수정)
```

> 실측 정정(세션 1): (D) 규범의 테스트 위치는 `test_prompt_rendering.py`가 아니라
> `test_worker_context_block.py`다. 전자는 `render_user_context_block`·
> `render_datetime_block` 전용이며 `render_worker_context_block` 테스트를 담지 않는다.

신규 파일 0개 — 모두 기존 모듈 확장.

### 11.2 Implementation Order

TDD: 각 단계마다 **실패하는 테스트 선작성 → 구현 → 통과 확인**.

1. **module-1** `EmptyResultPolicy` + config 패턴 (독립, 의존 없음)
2. **module-2** state 2필드 + `_with_empty_signal` 데코레이터 + 등록 루프 배선
3. **module-3** `_render_empty_result_block` + supervisor 노드 블록 주입/pending/리셋
4. **module-4** `route_to_worker_or_final` 되물음 + `route_map` 자기순환
5. **module-5** (D) `_TOOL_USAGE_NORM` 규범 1건 — 완전 독립, 순서 무관
6. **module-6** L3 그래프 통합 테스트 + 회귀 확인

### 11.3 Session Guide

**Module Map**

| Scope Key | 범위 | 파일 | 의존 | 예상 규모 |
|-----------|------|------|------|-----------|
| `module-1` | 판정 규칙 + 설정 | `policies.py`, `config.py` | 없음 | 소 |
| `module-2` | 신호 채널 + 배선 | `supervisor_state.py`, `workflow_compiler.py` | module-1 | 중 |
| `module-3` | 블록 렌더 + supervisor | `supervisor_nodes.py` | module-2 | 중 |
| `module-4` | 되물음 라우팅 | `supervisor_nodes.py`, `workflow_compiler.py` | module-3 | 소 |
| `module-5` | (D) 워커 규범 | `prompt_rendering.py` | 없음 | 극소 |
| `module-6` | 통합·회귀 | 테스트만 | module-1~5 | 중 |

**권장 세션 분할**

| 세션 | Scope | 목표 |
|:----:|-------|------|
| 1 | `--scope module-5,module-1` | 독립 모듈 2개를 먼저 끝내 즉시 효과(D)를 확보 |
| 2 | `--scope module-2,module-3` | 신호 채널과 블록 렌더까지 연결 |
| 3 | `--scope module-4,module-6` | 되물음 완성 + 통합·회귀 |

**후속 피처 연결점**: `wiki-procedure-completion`(A)은 `finish_challenge_pending`과 `route_to_worker_or_final`의 되돌림 분기를 **그대로 재사용**하고, 사유만 "미완 절차"로 추가한다. 이때 두 사유가 같은 플래그를 공유하므로 **기회 소진 규율을 사유별로 분리할지 통합할지**를 A의 Design에서 결정해야 한다 (Plan `wiki-procedure-completion` §6.3 검증 항목).

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-09-16 | 최초 작성. Option C 선택, 4개 워커 팩토리를 단일 데코레이터로 덮는 D-06 확정 | 배상규 |
