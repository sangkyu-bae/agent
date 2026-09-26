# worker-capability-denial-guard Design Document

> **Summary**: 워커 산출의 능력 부정 문구를 결정적 신호(`last_worker_denial`)로 state에 올리고, supervisor 결정 프롬프트에 전용 블록으로 알린 뒤, 기존 `finish_challenge_pending` 게이트로 첫 FINISH를 1회 되돌린다. 워커 규범에는 "task 외 능력 질문 무응답"을 추가한다.
>
> **Project**: sangplusbot (idt 백엔드)
> **Version**: 미지정
> **Author**: 배상규
> **Date**: 2026-09-25
> **Status**: Draft
> **Planning Doc**: [worker-capability-denial-guard.plan.md](../../01-plan/features/worker-capability-denial-guard.plan.md)

### 선행 계약 문서 (필수 준수)

| 문서 | 상태 | 이 설계에 미치는 구속 |
|------|:----:|----------------------|
| [Supervisor 그래프 계약 3종](../../../docs/wiki/backend/patterns/supervisor-graph-contracts.md) | ✅ approved | 계약 ①②③ 전부 적용 — §1.2 |
| [supervisor-early-finish-fix Design](./supervisor-early-finish-fix.design.md) | 구현 완료 (87%) | 신호 채널 수명주기(D-02), 되물음 게이트(D-05), **모든 return 경로가 pending을 확정하는 불변식**(§2.2 실측 정정), 패턴 config 외부화(D-07), 워커 규범 절대 프레이밍 금지(D-08) |
| [백엔드 아키텍처 조감도](../../../docs/wiki/backend/architecture-overview.md) | ✅ approved | supervisor 그래프는 요청마다 DB 정의로 동적 컴파일, DI는 `main.py` 단일 집중 |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 워커의 능력 부정 발언을 supervisor가 진실로 채택해 가능한 작업을 "불가"로 종료한다 (로컬 런 `031564e4`, `aff5935c` 실증) |
| **WHO** | P2 — KB 운영자/에이전트 소유자. 도구를 여러 개 등록한 에이전트가 등록한 만큼의 능력을 발휘하기를 기대하는 사용자 |
| **RISK** | 패턴 오탐으로 정당한 "확인되지 않았습니다" 답변까지 되물어 지연·토큰이 늘어난다 |
| **SUCCESS** | 재현 시나리오에서 능력 부정 블록이 렌더되고 첫 FINISH가 1회 되돌려진다. 신호가 없으면 결정 프롬프트가 기존과 바이트 동일. 워커 규범 추가 후 워커가 task 밖 능력 질문에 답하지 않는다 |
| **SCOPE** | A(워커 규범 1건) + B(능력 부정 신호·블록·기존 1회 되물음 게이트 재사용·패턴 config 외부화). 데이터 수정(MCP description·에이전트 프롬프트)은 권고만 |

---

## 1. Overview

### 1.1 Design Goals

1. **"이 워커가 못 한다"와 "이 에이전트가 못 한다"를 구분**한다 — 워커의 불가 선언을 에이전트 능력 판정의 근거에서 분리
2. 탐지는 **결정적**(패턴), 그 다음 행동은 **supervisor LLM 판단** — 특정 워커(`get_inquiry`)를 강제 라우팅하지 않는다
3. 되물음은 빈 결과 신호와 **합산 1회** — 기존 `finish_challenge_pending` 플래그 하나로 상한을 유지해 무한 루프 불가 보장을 한 곳에 둔다
4. 신호가 없으면 **결정 프롬프트 바이트 동일**
5. 기대 동작(가능함을 답하고 대상 확인 vs 능동 조회)은 **블록 문구와 config로만** 표현해, 코드 구조 변경 없이 전환 가능하게 한다
6. 1차 방어는 워커 규범(A) — 워커가 애초에 능력 질문에 답하지 않으면 신호는 서지 않는다. B는 A가 뚫렸을 때의 2차 방어

### 1.2 Design Principles

- **계약 ① 워커 산출물 = `AIMessage(name)` 1건** → 신호는 state 채널만. 메시지 삽입 금지
- **계약 ② 목록 프레이밍 금지** → 블록에 `get_inquiry` 등 워커·도구 이름을 나열하지 않는다. "해당 기능을 가진 워커가 위 목록에 있으면"이라는 조건부 서술만 쓴다
- **계약 ③ 결정적 신호 vs LLM 판단 분리** → 탐지만 결정적. "그러므로 get_inquiry를 불러라"는 판단은 LLM
- **선례 동형** → `last_worker_denial`은 `last_worker_empty`(D-02)와 같은 수명주기: 워커 노드가 매번 덮어쓰고(정상 시 `""`), supervisor가 소비 후 리셋
- **early-finish-fix 불변식** → `supervisor_node`의 *모든* return 경로가 `last_worker_denial`을 `""`로, `finish_challenge_pending`을 명시적으로 확정한다. 한도·강제 라우팅·결정 실패·draft 조기 return 5곳
- **D-08 절대 프레이밍 금지** → 워커 규범에 "~에는 답하지 말라"를 쓰되, 도구 결과 전달 의무(기존 규범)보다 뒤에 두고 대상을 '에이전트 능력·범위 질문'으로 한정한다. "A라고만 하라"류 문구 금지
- **블록 배타** → 한 결정에 안내 블록은 최대 1개. 우선순위 오류 > 빈 결과 > 능력 부정
- **외부 콘텐츠 승격 금지** → 사유 요약에 워커 산출 원문을 담지 않는다(고객 문의 본문 지시문 방지)
- **단일 책임** → 판정 규칙은 domain policy, 흐름 제어는 application, config 정규화는 composition root(`main.py`)

---

## 2. Architecture Options

### 2.0 Architecture Comparison

| Criteria | Option A: Minimal | Option B: Clean | Option C: Pragmatic |
|----------|:-:|:-:|:-:|
| **Approach** | 신규 state 없이 `last_worker_empty` 채널·기존 블록에 사유를 실음 | 신규 채널 + 사유별 플래그 + 블록 렌더를 `supervisor_blocks.py`로 분리 | 신규 채널 + 전용 블록 + 기존 pending 합산 재사용, 등록 루프 공용 데코레이터 |
| **New Files** | 0 | 1~2 | 0 |
| **Modified Files** | 4 | 8 | 6 |
| **적용 워커** | search/collect만 — **재현 결함(react)을 못 덮음** | 전 워커 | 전 워커 |
| **블록 문구** | "수집 결과 비어 있음" 재사용 → 의미 불일치 | 전용 | 전용 |
| **Complexity** | Low | High | Medium |
| **Maintainability** | Low | High | High |
| **Effort** | Low | High | Medium |
| **Risk** | High (재현 미해결, 빈 결과 테스트 의미 오염) | Medium (supervisor 노드 리팩토링 회귀 표면) | Low (early-finish-fix 동형, route 불변) |
| **Recommendation** | 비추천 | 장기 리팩토링 시 | **선택됨** |

**Selected**: **Option C — Pragmatic**

**Rationale**:
- Option A는 `_with_empty_signal`이 `empty_signal_worker_ids`(search/collect)에만 적용되므로(`workflow_compiler.py:985`) 미분류 react 워커인 `list_inquiries_worker`를 덮지 못한다. 재현 케이스를 해결하지 못하는 설계다.
- Option B는 `supervisor_node`(145줄, early-finish-fix carry item)를 줄이는 이점이 있지만, 이 피처의 목적과 무관한 리팩토링이 회귀 표면을 넓힌다. 블록 렌더 분리는 별건으로 남긴다.
- Option C는 early-finish-fix가 검증한 구조(신호 채널 → 블록 → route 되돌림)를 그대로 따르고 route 로직을 건드리지 않는다. 신규 파일 0개.

### 2.1 Component Diagram

```
┌────────────────────────────┐
│ worker node (모든 팩토리)  │  react(_wrap_worker) / search / collect /
│                            │  action / analysis / docgen / sub_agent
└──────────┬─────────────────┘
           │ _with_denial_signal 데코레이터 (등록 루프 단일 지점, 전 워커)
           │   · last_worker_error 있으면 판정 생략 → ""
           │   · CapabilityDenialPolicy.detect(messages[-1].content, patterns)
           ▼ last_worker_denial
┌────────────────────────────┐
│       quality_gate         │
└──────────┬─────────────────┘
           ▼
┌────────────────────────────┐
│        supervisor          │  블록 배타: error > empty > denial
│                            │  finish_challenge_pending = bool(empty or denial)
│                            │  last_worker_denial = "" (소비 후 리셋)
└──────────┬─────────────────┘ next_worker
           ▼
┌────────────────────────────┐
│ route_to_worker_or_final   │  (변경 없음)
│  approval > limit > pending│
└───┬────────────┬───────────┘
    │ pending    │ 그 외
    ▼            ▼
 "supervisor"  worker / final_answer
 (되물음 1회, 빈 결과와 합산)
```

### 2.2 Data Flow

```
0. 워커 프롬프트 (A)
   → _TOOL_USAGE_NORM에 "task 외 능력·범위 질문 무응답" 규범 → 1차 방어

1. 워커 실행
   → _with_denial_signal이 산출 content로 CapabilityDenialPolicy.detect() 호출
   → 능력 부정이면 state["last_worker_denial"] = 사유요약, 아니면 ""
   → last_worker_error가 이미 있으면 판정 생략 ("")

2. supervisor 결정
   → error_block 있음 → empty·denial 블록 생략
   → 아니고 empty_block 있음 → denial 블록 생략
   → 아니고 last_worker_denial 있음 → "[워커 능력 부정 감지]" 블록 주입
   → 반환 dict: finish_challenge_pending = bool(empty_block or denial_block)
                last_worker_empty = "", last_worker_denial = ""   (소비 후 리셋)
   → LLM 결정 (워커 선택 또는 FINISH)

3. route_to_worker_or_final (불변)
   → __end__ + pending + not limit_reached + not approval_pending → "supervisor"

4. supervisor 재진입 (2회차)
   → 두 신호 모두 "" → 정식 블록 없음
   → (Act-1 Gap-03) pending=True + finish_challenge_kind로 "[되물음 재결정]" 리마인더만 렌더
   → pending = False, kind = "" (기회 소진)
   → LLM이 다시 FINISH → route 통과 → final_answer
```

**합산 1회 상한의 근거**: `pending=True`는 empty 또는 denial 블록이 렌더될 때만 세워지고, 그 즉시 두 신호를 모두 리셋한다. 재진입 시 신호가 없으므로 `pending`은 False로만 갈 수 있다. 같은 턴에 두 신호가 동시에 서도(배타로 블록은 1개) 되돌림은 1회다. 워커가 다시 실행되면 신호가 새로 설 수 있으나, 그때는 새 워커 산출에 대한 새 기회이며 `max_iterations`가 상한을 잡는다(기존 빈 결과와 동일한 성질).

**되물음 후 LLM이 같은 FINISH를 내는 경우**: 블록이 "가능함과 필요한 입력을 answer에 적어라"를 지시하므로, FINISH를 유지하더라도 answer 내용이 바뀌는 것을 기대한다. 단, 워커가 이미 실행된 런은 `final_answer` 노드가 답변을 생성하고 supervisor의 answer는 폐기된다(final-answer-node DQ1). 따라서 **블록의 지시가 최종 답변에 닿는 경로는 (i) 워커 재호출 또는 (ii) supervisor reasoning이 대화 컨텍스트에 남지 않으므로 final_answer가 워커 주장을 그대로 종합하는 위험**이 남는다. → §6.2 열린 질문 Q1로 처리: `final_answer` 노드에 `last_worker_denial` 사유를 안내 블록으로 넘길지는 구현 시 L3 실런 결과로 확정한다. 1차 구현은 supervisor 되물음까지만 하고, 실런에서 (ii)가 관측되면 module-6에서 final_answer 안내를 추가한다.

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `CapabilityDenialPolicy` (domain) | 없음 (순수 규칙) | 능력 부정 판정. 외부 타입 미참조 |
| `_with_denial_signal` (application) | `CapabilityDenialPolicy` | 워커 산출 → state 신호 |
| `_render_capability_denial_block` (application) | `SupervisorState` | 신호 → 결정 프롬프트 블록 |
| `supervisor_node` (application) | 위 블록 함수, 기존 `_render_empty_result_block`/`_render_worker_error_block` | 배타·pending·리셋 |
| `WorkflowCompiler.__init__` | `capability_denial_patterns` kwarg | 패턴 주입 (`empty_result_patterns` 동형) |
| `src/api/main.py` | `settings.capability_denial_patterns` | 콤마 문자열 → tuple 정규화 |
| `_TOOL_USAGE_NORM` (application/agent_run) | 없음 | (A) 워커 규범 |

---

## 3. Data Model

### 3.1 State 스키마 확장 (`SupervisorState`)

```python
    # worker-capability-denial-guard D-02: 직전 워커 산출의 '능력 부정' 사유 요약.
    # last_worker_empty 동형 — 워커 노드가 매번 덮어쓰고(정상 시 ""), supervisor가
    # "[워커 능력 부정 감지]" 블록을 렌더한 뒤 ""로 리셋한다.
    # 워커가 자기 도구 범위를 에이전트 전체 능력으로 착각해 '어떤 도구로도 불가'라
    # 선언한 상태로, 도구 오류·빈 결과와 구분된다.
    last_worker_denial: str
```

- `build_initial_state`에 `"last_worker_denial": ""` 추가
- 읽기는 `state.get("last_worker_denial", "")` — 기존 체크포인트(키 부재) 하위호환
- `finish_challenge_pending`은 **필드 추가 없이** 의미만 "빈 결과 또는 능력 부정 되물음 기회"로 확장. 주석 갱신

### 3.2 Domain Policy 계약 (`CapabilityDenialPolicy`)

```python
class CapabilityDenialPolicy:
    """워커 산출의 '에이전트 능력 부정' 판정 — 결정적 신호만 담당.

    Design Ref: worker-capability-denial-guard §3.2 (D-01).

    EmptyResultPolicy와 같은 역할 분담: 확실한 문구만 여기서 잡고,
    '그래서 어느 워커를 부를 것인가'는 supervisor LLM이 판단한다(그래프 계약 ③).
    LangChain 타입을 참조하지 않는다 — 문자열만 받는다.

    판정 대상은 '에이전트 전체 또는 화자 권한을 부정하는' 문구로 한정한다.
    early-finish-fix D-08이 권장한 워커 표기 "이 워커의 범위 밖"은 정당한
    범위 표기이므로 기본 패턴에 넣지 않는다 — 오탐 방지.
    """

    MAX_SUMMARY_CHARS = 120
    _REASON = "워커가 에이전트 전체 능력을 부정함"

    @classmethod
    def detect(cls, body, patterns) -> str:
        """능력 부정 문구가 있으면 사유 요약을, 아니면 ''을 돌려준다.

        Args:
            body: 워커 산출 본문. str이 아니면 판정을 생략한다.
            patterns: 능력 부정 문구. None/빈 튜플이면 항상 ''(판정 비활성).

        Returns:
            사유 요약(MAX_SUMMARY_CHARS 이내, 매칭 패턴 1개 포함). 정상이면 ''.
            수집 원문을 담지 않는다 — 외부 콘텐츠의 지시문 승격 방지.
        """
```

- `EmptyResultPolicy`와 달리 **구조적 1차 판정이 없다** — 패턴 없으면 항상 비활성. 패턴을 비우는 것이 곧 기능 off 스위치다
- 사유 요약은 `"{_REASON}: '{matched}'"` 형식으로 매칭 패턴만 담는다(원문 미포함). 진단 로그와 블록에 어떤 문구가 걸렸는지 드러나야 오탐 튜닝이 가능하다

### 3.3 설정값 (`src/config.py`)

```python
    # Worker Capability Denial (worker-capability-denial-guard Design §3.3, D-03)
    # 워커 산출의 '에이전트 능력 부정' 판정 문구 (콤마 구분).
    # 소비 지점: src/api/main.py 가 tuple로 정규화해 WorkflowCompiler 생성자에
    #   capability_denial_patterns= 으로 주입 → CapabilityDenialPolicy.detect(patterns=...)
    # application/domain 레이어는 이 설정을 직접 import하지 않는다 (kwarg 주입만).
    # 과탐 주의: "할 수 없습니다"류 짧은 상위 문자열, 워커의 정당한 범위 표기
    # "이 워커의 범위 밖"은 넣지 않는다. 빈 문자열이면 판정이 꺼진다.
    capability_denial_patterns: str = (
        "어떤 도구로도,어떤 워커로도,조회할 수 없도록 제한,"
        "제 권한 밖,제 범위 밖,권한/범위 밖"
    )
```

- 기본 6개 패턴은 실측 워커 산출(런 `031564e4`)에서 뽑았다: "어떤 도구로도 조회할 수 없도록 제한", "제 권한/범위 밖"
- `main.py`에 `_capability_denial_patterns()` 헬퍼를 `_empty_result_patterns()`(2246행) 동형으로 추가

### 3.4 Database Schema

**변경 없음.** DB 마이그레이션 없음.

---

## 4. 내부 계약 명세 (API Specification 대체)

HTTP API 변경이 없다. 변경되는 내부 함수 계약을 명시한다.

### 4.1 변경/신설 함수 목록

| 함수 | 위치 | 구분 | 계약 |
|------|------|:----:|------|
| `CapabilityDenialPolicy.detect` | `domain/agent_builder/policies.py` | 신설 | `(body, patterns) -> str` |
| `_with_denial_signal` | `application/agent_builder/workflow_compiler.py` | 신설 | `(fn, patterns) -> fn'` — 반환 dict에 `last_worker_denial` 주입 |
| `WorkflowCompiler.__init__` | 동상 | 수정 | `capability_denial_patterns: tuple[str, ...] \| None = None` kwarg 추가, `self._capability_denial_patterns` 보관 |
| 노드 등록 루프 | 동상 (`:975-990`) | 수정 | 모든 워커 노드를 `_with_denial_signal`로 감싼다 (`_wrap_step` 안쪽) |
| `_render_capability_denial_block` | `application/agent_builder/supervisor_nodes.py` | 신설 | `(state) -> str` — 신호 없으면 `""` |
| `_select_guidance_block` | 동상 | 신설 | `(state, wiki_worker_id) -> tuple[str, str]` — 배타 규칙 적용해 `(block, kind)` 반환. `supervisor_node` 본문 길이를 늘리지 않기 위한 분리 |
| `create_supervisor_node.supervisor_node` | 동상 | 수정 | 배타 블록 주입, `finish_challenge_pending = bool(block)`, 5개 return 경로에 `last_worker_denial=""` |
| `build_initial_state` | 동상 | 수정 | `last_worker_denial: ""` |
| `_TOOL_USAGE_NORM` | `application/agent_run/prompt_rendering.py` | 수정 | (A) 규범 1건 추가 |
| `_capability_denial_patterns` | `api/main.py` | 신설 | config → tuple 정규화, 생성자 주입 |
| `_render_denial_notice` | `application/agent_builder/workflow_compiler.py` | 신설 (Q1 확정) | `(messages, patterns, worker_descriptions="") -> str` — final_answer 조건부 주의 블록. 이번 턴 워커 산출 재판정 |
| `_create_final_answer_node` | 동상 | 수정 (Act-1 Gap-04) | `worker_descriptions: str = ""` kwarg — 발동 시에만 등록 워커 목록을 근거로 싣는다 |
| `_render_challenge_reentry_block` | `application/agent_builder/supervisor_nodes.py` | 신설 (Act-1 Gap-03) | `(state) -> str` — pending 재진입에 사유 종류별 1줄 리마인더 |
| `_challenge_reset` | 동상 | 신설 (Act-1 Gap-05) | 되물음 채널 4개 일괄 리셋 dict — 조기 return 5곳이 공유 |
| `_WORKER_SCOPE_REMINDER` / `_build_worker_input` | `application/agent_builder/workflow_compiler.py` | 수정 (Act-1 Gap-02) | `[현재 작업]` 꼬리에 범위 리마인더 1줄 |
| `SupervisorState.finish_challenge_kind` | `application/agent_builder/supervisor_state.py` | 신설 (Act-1 Gap-03) | `"empty" \| "denial" \| ""` — pending과 함께 세워지고 소진 |

`route_to_worker_or_final`, `route_map`: **변경 없음**.

### 4.2 `_with_denial_signal` — 단일 배선 지점 (D-04)

**결정 D-04: 전 워커 적용.** `_with_empty_signal`은 search/collect에만 적용되지만(수집 목적 판정), 능력 부정은 어떤 워커도 할 수 있다. 실측 결함은 react 워커였고, 분석·문서생성 노드도 대화 전문을 받으므로 같은 오류가 가능하다. 패턴이 특정적이라 전 워커 적용의 오탐 비용은 낮다.

```python
# workflow_compiler.py 노드 등록 루프
for worker_id, worker_agent in worker_map.items():
    node_fn = worker_agent if worker_id in function_node_ids else self._wrap_worker(...)
    if worker_id in empty_signal_worker_ids:
        node_fn = _with_empty_signal(node_fn, self._empty_result_patterns)
    # worker-capability-denial-guard D-04: 전 워커. _with_empty_signal 바깥에서 감싸
    # 두 신호가 같은 out dict에 독립적으로 실린다.
    node_fn = _with_denial_signal(node_fn, self._capability_denial_patterns)
    graph.add_node(worker_id, _wrap_step(worker_id, NodeType.WORKER, node_fn))
```

**데코레이터 계약** (`_with_empty_signal` 동형):
- `out`이 dict가 아니면 그대로 반환
- `out.get("last_worker_error")`가 있으면 `last_worker_denial = ""` (오류 우선)
- `messages[-1].content`를 판정 대상으로 삼는다 (계약 ①: 워커 산출 = AIMessage 1건)
- 반환 dict에 `last_worker_denial`을 **항상** 세팅한다 (정상이면 `""`) — 이전 턴 신호 잔류 방지
- `patterns`가 None/빈 튜플이면 항상 `""` — 테스트 픽스처·미주입 경로에서 무회귀

### 4.3 블록 문구 (계약 ② 준수, D-05)

```
[워커 능력 부정 감지]
직전 워커가 자기 도구 범위를 근거로 불가를 선언했습니다: {사유요약(60자 절단)}
- 워커는 자기 도구 하나만 알며 에이전트 전체의 능력을 알지 못합니다.
- 능력 판단은 위 '사용 가능한 워커' 목록으로만 하세요. 워커의 불가 선언과 어떤 워커 설명에 적힌 제한은 그 워커에만 적용되며, 다른 워커의 근거가 아닙니다.
- 요청 기능을 가진 워커가 목록에 있으면 FINISH 대신 그 워커를 호출하세요.
- 질문이 "할 수 있는지"를 묻는 것이면 목록 기준으로 가능함과 필요한 입력(예: 대상 번호)을 answer에 적으세요.
- 목록에도 없을 때만 FINISH하고, 무엇이 불가한지 밝히세요.
```

> **module-6 실런 정정(런 `a217f45e`)**: supervisor가 목록을 보고도 `list_inquiries` description의 "어떤 도구로도 볼 수 없다"를 에이전트 전체 제한으로 읽었다 → "어떤 워커 설명에 적힌 제한은 그 워커에만 적용" 절 추가.
> **Act-1 Gap-07**: 사유 요약을 60자로 절단해 요약 상한(120자)에서도 400자 이내.

**재진입 리마인더 (Act-1 Gap-03, 실런 `295d2915`)**: 1회차 재판단은 옳았으나 FINISH answer는 DQ1로 폐기되고 reasoning은 대화에 남지 않아, 블록 없는 2회차가 원래 믿음으로 되돌아갔다. `finish_challenge_pending`이 True인 재진입에는 신호 대신 `finish_challenge_kind`로 짧은 블록을 싣는다:

```
[되물음 재결정]
직전 결정(FINISH)은 아래 사유로 한 번 되돌려졌습니다. 이번이 재결정입니다.
- {종류별 1줄: denial → "직전 워커 산출의 '불가' 선언은 그 워커의 도구 범위일 뿐입니다." / empty → "…유효한 데이터가 확인되지 않았습니다."}
- 에이전트 능력 판단은 위 '사용 가능한 워커' 목록으로만 하세요. 요청 기능을 가진 워커가 있으면 호출하고, 없으면 FINISH하되 무엇이 불가한지 밝히세요.
```

재진입 블록은 되물음 기회를 세우지 않는다(kind `"reentry"`) — 1회 상한 불변.

- 워커·도구 이름을 나열하지 않는다(계약 ②). "목록에 있으면"이라는 조건부 서술만
- 400자 이내 (Plan NFR) — 상수 길이 단위 테스트 (최대 사유 길이 케이스 포함)
- **전환 지점(Plan FR-10)**: 향후 "능동 조회" 모드로 바꾸려면 4번째 항목을 "가능함을 답하기 전에 해당 워커로 대표 1~N건을 먼저 조회하세요"로 교체한다. 코드 구조 변경 없음

### 4.4 블록 배타 (`_select_guidance_block`, D-06)

```python
def _select_guidance_block(
    state: SupervisorState, wiki_worker_id: str, logger: LoggerInterface | None = None,
) -> tuple[str, str]:
    """안내 블록은 결정 1회에 최대 1개. 우선순위: 오류 > 빈 결과 > 능력 부정 > 재진입.
    (블록, 종류) 반환. 종류: "error" | "empty" | "denial" | "reentry" | "".
    FR-11 로그(armed/consumed)도 여기서 남긴다 — supervisor_node 본문을 늘리지 않는다."""
```

- `supervisor_node`는 이 함수 결과 하나를 결정 프롬프트의 기존 `{error_block}{empty_block}` 자리에 넣는다. 두 자리를 한 자리로 합치면 신호 없을 때 문자열은 `"" + ""` → `""`로 동일 — **바이트 동일 보존**
- `finish_challenge_pending = bool(block) and block is not error_block` — 오류 블록은 되물음 대상이 아니다(기존 동작 유지). 구현은 `kind` 반환값으로 분기해 문자열 비교를 피한다
- 기존 `error_block` / `empty_block` 변수를 쓰던 테스트(`test_supervisor_empty_block.py` 시나리오 4)는 의미가 유지된다

### 4.5 `supervisor_node` return 경로 불변식 (D-07)

| 경로 | `last_worker_denial` | `finish_challenge_pending` |
|------|:---:|:---:|
| `max_iterations` 가드 | `""` | `False` |
| `token_limit` 가드 | `""` | `False` |
| 강제 라우팅 | `""` | `False` |
| LLM 결정 실패 fallback | `""` | `False` |
| 워커 미실행 + draft answer 조기 return | `""` | `False` |
| 정상 return | `""` | `bool(empty or denial)` |

early-finish-fix §2.2 실측 정정에서 확인된 무한 루프(`GraphRecursionError`)를 재발시키지 않기 위해 **6곳 전부**를 테스트로 고정한다 (§8.3 #5).

### 4.6 (A) 워커 규범 문구 (D-08)

`_TOOL_USAGE_NORM` 말미(기존 "에이전트 전체가 그 기능을 갖고 있지 않다고 단정하지 마세요" 다음)에 추가:

```
[현재 작업]에 적힌 일만 수행하세요.
대화에 다른 질문이 있어도, 특히 이 에이전트가 무엇을 볼 수 있는지·할 수 있는지를 묻는
질문에는 답하지 마세요 — 그 판단은 상위 노드가 전체 워커 목록으로 합니다.
```

- 도구 결과 전달 의무(기존 "빠짐없이 답변에 그대로 실으세요") **뒤**에 둔다 — D-08 교훈: 제한 규범이 전달 의무보다 앞서면 워커가 결과를 버린다
- '생략'이라는 낱말을 쓰지 않는다(절단 안내 테스트 오탐 방지)
- `[현재 작업]`은 `_build_worker_input`이 붙이는 실제 헤더와 일치해야 한다. task가 비어 `_FALLBACK_WORKER_INSTRUCTION`으로 폴백된 경우에도 규범은 무해하다("역할에 해당하는 작업"이 곧 현재 작업)
- 150자 이내 (Plan NFR)

---

## 5. UI/UX Design

**해당 없음.** 프론트엔드 변경 없음. 사용자에게는 최종 답변 품질 변화로만 드러난다.

---

## 6. Error Handling

### 6.1 예외 상황 처리

| 상황 | 처리 |
|------|------|
| 워커 산출 `content`가 str이 아님(리스트 블록 등) | 판정 생략 → `""` (EmptyResultPolicy 동형) |
| `patterns` 미주입(None)·빈 튜플 | 판정 비활성 → 항상 `""`. 테스트 픽스처 무회귀 |
| 오류 신호와 동시 발생 | 오류 우선, denial `""` (데코레이터 + 배타 함수 이중 방어) |
| 빈 결과 신호와 동시 발생 | 빈 결과 블록만 렌더, 되물음 1회는 공유 |
| 되물음 후 `max_iterations` 도달 | route에서 `limit_reached` 우선 → final_answer (기존 D-09) |
| 되물음 후 승인 대기 | route에서 `approval_pending` 우선 → `__end__` (기존 approval-gate ③) |
| 오탐(정당한 "확인되지 않았습니다") | 기본 패턴에 미포함. 걸리더라도 되물음 1회 비용, LLM이 FINISH 재선택 가능 |

### 6.2 열린 질문 (구현 착수 전·중 확정)

| # | 질문 | 1차 결정 | 확정 시점 |
|---|------|---------|----------|
| Q1 | 되물음 후 supervisor가 FINISH를 유지하면 `final_answer` 노드가 워커의 불가 주장을 그대로 종합할 수 있다. `final_answer`에 사유 안내를 넘길 것인가? | **확정(module-6 실런 `a217f45e`)**: 관측됨. 새 state 필드 없이 `_render_denial_notice`가 이번 턴 워커 산출을 같은 패턴으로 재판정해 "[워커 능력 주장 주의]" 블록을 조건부로 싣는다. **Act-1 Gap-04**: 근거를 에이전트 지침이 아닌 등록 워커 목록(`worker_descriptions`, 발동 시에만)으로 둔다. **한계(실런 `295d2915`, `59d25d9d`)**: 워커가 부정하지 않아 블록이 뜨지 않는 경우에도 final_answer는 에이전트 지침·description의 결함 문구("원문 불가")로 틀린 문장을 만든다 — 데이터 수정 없이는 해소 불가 | 확정 |
| Q2 | 분석·문서생성 노드까지 데코레이터를 적용해도 산출 형식(차트 config 등)에서 오탐이 없는가? | 전 워커 적용(D-04). `content`가 str이 아니면 생략되므로 구조화 산출은 안전 | module-2 단위 테스트 |
| Q3 | 되물음 사유(빈 결과 vs 능력 부정)를 로그·`ai_run_step` summary에서 구분할 필요가 있는가? | `logger.info`에 `reason_kind` 필드로 구분. state 플래그는 분리하지 않는다 | module-3 |

---

## 7. Security Considerations

- [x] 사유 요약에 워커 산출 원문(고객 문의 본문)을 담지 않는다 — 외부 콘텐츠 지시문 승격 방지
- [x] 블록은 supervisor 시스템 프롬프트 영역에만 들어가며 사용자·워커 메시지로 삽입되지 않는다
- [x] 권한·인증 경로 변경 없음. `get_inquiry` 호출 여부는 기존 워커 게이트·승인 정책이 그대로 적용
- [x] 신규 설정값은 문구 목록일 뿐 시크릿 아님

---

## 8. Test Plan

### 8.1 Test Scope

| 레벨 | 대상 | 도구 |
|------|------|------|
| L1 단위 | `CapabilityDenialPolicy.detect` | pytest |
| L1 단위 | `_render_capability_denial_block` 문구·길이·미발동 | pytest |
| L1 단위 | `_TOOL_USAGE_NORM` 규범 포함·순서·길이 | pytest |
| L2 노드 | supervisor 노드의 배타·pending·리셋 (6개 return 경로) | pytest + fake LLM |
| L2 배선 | `_with_denial_signal` 데코레이터, 등록 루프 전 워커 적용 | pytest |
| L3 통합 | 컴파일된 그래프에서 되물음 1회 → 2회차 통과 (무한 루프 없음) | pytest + 스텁 워커 |
| L3 회귀 | 신호 없을 때 결정 프롬프트 바이트 동일 | pytest |
| L3 실런 | 로컬 MCP 8007 대상 에이전트 재현 (선택) | TestClient 인프로세스 |

### 8.2 L1 — `CapabilityDenialPolicy` 시나리오

| # | 입력 | 기대 |
|---|------|------|
| 1 | 실측 산출: "…상세 본문 내용은 어떤 도구로도 조회할 수 없도록 제한되어 있습니다…" | 감지 — **재현 케이스** |
| 2 | "…이 부분은 제 권한/범위 밖입니다" | 감지 |
| 3 | "요청하신 2023년 데이터는 도구 결과에서 확인되지 않았습니다" | 미감지 (`""`) — 정당한 미확인 |
| 4 | "…이 워커의 범위 밖입니다" | 미감지 — D-08 권장 표기 |
| 5 | 패턴 튜플 빈 경우 + 케이스 1 본문 | 미감지 (비활성) |
| 6 | `content`가 list | 미감지 |
| 7 | 사유 요약 | `MAX_SUMMARY_CHARS` 이내, 매칭 패턴 포함, 본문 원문 미포함 |

### 8.3 L2 — supervisor 노드 시나리오

| # | 초기 state | 기대 |
|---|-----------|------|
| 1 | `last_worker_denial="..."` | 결정 프롬프트에 denial 블록 포함, 반환 `finish_challenge_pending=True`, `last_worker_denial=""` |
| 2 | `last_worker_denial=""`, `last_worker_empty=""`, `last_worker_error=""` | 블록 미포함, 프롬프트가 기존과 **바이트 동일** |
| 3 | `last_worker_denial` + `last_worker_empty` 동시 | 빈 결과 블록만, pending=True |
| 4 | `last_worker_denial` + `last_worker_error` 동시 | 오류 블록만, pending=False |
| 5 | 6개 return 경로 각각 | 모두 `last_worker_denial=""`, pending 확정값 (§4.5 표) |
| 6 | `finish_challenge_pending=True`로 재진입 | 블록 미포함, pending=False |

### 8.4 L2 — 배선 시나리오

| # | 조건 | 기대 |
|---|------|------|
| 1 | react 워커 산출에 패턴 포함 | out에 `last_worker_denial` 세팅 |
| 2 | 함수 노드(search) 산출에 패턴 포함 | 세팅 (전 워커 적용) |
| 3 | 산출 정상 | `last_worker_denial=""` (항상 덮어씀) |
| 4 | `last_worker_error` 있음 | `""` |
| 5 | `WorkflowCompiler(capability_denial_patterns=None)` | 데코레이터가 항상 `""` — 기존 픽스처 무회귀 |

### 8.5 L3 — 그래프 통합 (재현 시나리오)

스텁 워커가 "…어떤 도구로도 조회할 수 없도록 제한…"을 반환하고, 스텁 LLM이 항상 FINISH를 내도록 구성한다.

- **기대**: supervisor 노드가 정확히 **2회** 호출된다. 최종적으로 `final_answer`에 도달한다 (무한 루프 없음)
- **기대**: 1회차 결정 프롬프트에만 denial 블록이 포함된다
- 빈 결과 통합 테스트(`test_empty_result_integration.py`)가 여전히 통과한다 (합산 의미 무회귀)

### 8.6 L3 — 실런 재현 (선택, module-6)

- 대상: 에이전트 `e557f77e-9209-4a1a-a4b2-ed937176c757`, 로컬 MCP 8007
- 입력: "지금 답변이 안된 문의 글을 좀 확인해서 뭐뭐가 있는지 알려주실래요? 그리고 각각 본문을 읽을 수 있나요?"
- 실행: `TestClient(src.api.main.app)` + 로컬 JWT, `persist_conversation: false`
- 확인: `ai_run_step`에 supervisor 2회 이상, 재결정 reasoning에 능력 판단 근거 변경, 최종 답변에 "어떤 도구로도"·"어떤 워커로도" 미포함. Q1 확정 근거
- `list_inquiries`/`get_inquiry`는 읽기 전용, `submit_reply`는 승인 게이트 — 부작용 없음

### 8.7 회귀 보호

- `tests/application/agent_run/test_worker_context_block.py` — (A) 규범 추가에 따른 단언 갱신 (early-finish-fix 실측: `test_prompt_rendering.py`가 아님)
- `test_supervisor_empty_block.py`, `test_empty_result_integration.py`, `test_supervisor_worker_error.py`, `test_supervisor_nodes.py` 전량 통과
- master 상시 실패 목록(53건)은 대조군으로 제외
- `/verify-architecture`, `/verify-logging`, `/verify-tdd`

### 8.8 Seed Data Requirements

없음. L1~L3 통합은 스텁으로 동작. L3 실런만 로컬 DB·MCP 8007을 사용한다.

---

## 9. Clean Architecture

### 9.1 Layer Structure

```
domain/agent_builder/policies.py
  └ CapabilityDenialPolicy          ← 규칙만. 외부 타입 미참조

application/agent_builder/
  ├ supervisor_state.py             ← 채널 정의 (+1 필드)
  ├ supervisor_nodes.py             ← 블록 렌더, 배타 선택, pending·리셋
  └ workflow_compiler.py            ← 데코레이터 배선, 생성자 kwarg
application/agent_run/
  └ prompt_rendering.py             ← (A) 워커 규범

config.py                           ← 패턴 설정값
api/main.py                         ← 정규화 + 생성자 주입 (composition root)

infrastructure/ · interfaces/       ← 변경 없음
```

### 9.2 Dependency Rules

domain → 외부 참조 없음. application → domain만. config는 `main.py`에서만 읽어 kwarg로 내려보낸다(`agent_timezone`·`empty_result_patterns` 규약).

### 9.3 File Import Rules

| From | Can Import | Cannot Import |
|------|-----------|---------------|
| `policies.py` | 표준 라이브러리 | LangChain, application, infrastructure, config |
| `supervisor_nodes.py`, `workflow_compiler.py` | domain, LangGraph/LangChain | `src.config` |
| `main.py` | 전부 | — |

### 9.4 This Feature's Layer Assignment

| Component | Layer | Location |
|-----------|-------|----------|
| `CapabilityDenialPolicy` | Domain | `src/domain/agent_builder/policies.py` |
| `last_worker_denial` | Application (state) | `src/application/agent_builder/supervisor_state.py` |
| `_with_denial_signal` | Application | `src/application/agent_builder/workflow_compiler.py` |
| `_render_capability_denial_block`, `_select_guidance_block` | Application | `src/application/agent_builder/supervisor_nodes.py` |
| `_TOOL_USAGE_NORM` 규범 | Application | `src/application/agent_run/prompt_rendering.py` |
| `capability_denial_patterns` | Config | `src/config.py` |
| `_capability_denial_patterns()` | Composition root | `src/api/main.py` |

---

## 10. Coding Convention Reference

### 10.1 Naming Conventions

| Target | Rule | 이 피처 |
|--------|------|---------|
| 정책 클래스 | `XxxPolicy` | `CapabilityDenialPolicy` |
| state 채널 | `last_worker_<signal>` | `last_worker_denial` |
| 데코레이터 | `_with_<signal>_signal` | `_with_denial_signal` |
| 블록 렌더 | `_render_<name>_block` | `_render_capability_denial_block` |
| 설정값 | `<feature>_patterns` (콤마 문자열) | `capability_denial_patterns` |
| 테스트 | `test_<module>_<aspect>.py` | §11.1 |

### 10.2 Import Order

프로젝트 기존 관례(표준 → 서드파티 → `src.` 절대 임포트). 변경 없음.

### 10.3 Environment Variables

| Variable | Purpose | Scope |
|----------|---------|-------|
| `CAPABILITY_DENIAL_PATTERNS` | config 기본값 덮어쓰기(선택) | Server |

### 10.4 This Feature's Conventions

| Item | Convention Applied |
|------|-------------------|
| Design Ref 주석 | `# Design Ref: worker-capability-denial-guard §N (D-0N)` |
| Plan SC 주석 | `# Plan SC: FR-0N` |
| 함수 길이 | `supervisor_node` 본문을 늘리지 않는다 — 배타 선택은 `_select_guidance_block`으로 분리 |
| 로깅 | `logger.info("finish challenge raised", reason_kind="denial", ...)` 구조화, request_id 포함 |
| 프롬프트 낱말 | '생략' 금지, "A라고만" 절대 프레이밍 금지 |

---

## 11. Implementation Guide

### 11.1 File Structure

```
수정:
  src/domain/agent_builder/policies.py                  (+CapabilityDenialPolicy)
  src/config.py                                         (+capability_denial_patterns)
  src/api/main.py                                       (+_capability_denial_patterns, 생성자 주입)
  src/application/agent_builder/supervisor_state.py     (+1 필드, pending 주석 갱신)
  src/application/agent_builder/supervisor_nodes.py     (+블록 렌더, +배타 선택, ~supervisor_node 6 경로, ~build_initial_state)
  src/application/agent_builder/workflow_compiler.py    (+kwarg, +데코레이터, ~등록 루프)
  src/application/agent_run/prompt_rendering.py         (~_TOOL_USAGE_NORM)

테스트(신규/수정 — 구현 실측):
  tests/domain/agent_builder/test_capability_denial_policy.py        (신규)
  tests/unit/test_capability_denial_config.py                        (신규 — 설정 계약)
  tests/application/agent_builder/test_supervisor_denial_block.py    (신규 — 배타·6경로·재진입·길이)
  tests/application/agent_builder/test_denial_signal_wiring.py       (신규 — 데코레이터·kwarg·워커 입력 리마인더)
  tests/application/agent_builder/test_denial_integration.py         (신규, L3 스텁 + 전 워커 배선)
  tests/application/agent_builder/test_final_answer_denial_notice.py (신규 — Q1)
  tests/application/agent_run/test_worker_context_block.py           (수정)
  tests/application/agent_builder/test_workflow_compiler.py          (수정 — final_answer 대역 kwarg 흡수)
```
> 배타 시나리오는 `test_supervisor_empty_block.py` 대신 `test_supervisor_denial_block.py`에 담았다 — 기존 파일 무수정.

신규 소스 파일 0개 — 모두 기존 모듈 확장.

### 11.2 Implementation Order

TDD: 각 단계마다 **실패하는 테스트 선작성 → 구현 → 통과 확인**.

1. **module-1** (A) `_TOOL_USAGE_NORM` 규범 — 완전 독립, 즉시 효과
2. **module-2** `CapabilityDenialPolicy` + config + `main.py` 정규화 (독립)
3. **module-3** state 필드 + `_with_denial_signal` + 생성자 kwarg + 등록 루프 배선
4. **module-4** `_render_capability_denial_block` + `_select_guidance_block` + `supervisor_node` 6 경로 + 로그
5. **module-5** L3 그래프 통합 테스트 + 회귀 확인
6. **module-6** L3 실런 재현 + Q1 확정(필요 시 `final_answer` 안내 1줄)

### 11.3 Session Guide

**Module Map**

| Module | Scope Key | Description | 파일 | 의존 | Estimated Turns |
|--------|-----------|-------------|------|------|:---:|
| 워커 규범 | `module-1` | (A) 규범 1건 + 테스트 갱신 | `prompt_rendering.py` | 없음 | 5-8 |
| 판정 정책·설정 | `module-2` | 정책 클래스 + config + main 정규화 | `policies.py`, `config.py`, `main.py` | 없음 | 8-12 |
| 신호 채널·배선 | `module-3` | state 필드 + 데코레이터 + 등록 루프 | `supervisor_state.py`, `workflow_compiler.py` | module-2 | 10-15 |
| 블록·supervisor | `module-4` | 블록 렌더 + 배타 + 6 경로 + 로그 | `supervisor_nodes.py` | module-3 | 12-18 |
| 통합·회귀 | `module-5` | L3 스텁 통합 + 전량 회귀 | 테스트만 | module-1~4 | 8-12 |
| 실런 검증 | `module-6` | 로컬 MCP 재현 + Q1 확정 | (조건부) `final_answer` | module-5 | 8-12 |

**Recommended Session Plan**

| Session | Phase | Scope | Turns |
|---------|-------|-------|:-----:|
| 1 | Do | `--scope module-1,module-2` | 15-20 |
| 2 | Do | `--scope module-3,module-4` | 25-35 |
| 3 | Do + Check | `--scope module-5,module-6` → `/pdca analyze` | 25-35 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-09-25 | 최초 작성. Option C 선택. 전 워커 배선(D-04), 블록 배타(D-06), 6 경로 불변식(D-07), Q1 final_answer 열린 질문 | 배상규 |
| 0.2 | 2026-09-25 | Do/Act-1 실측 반영: Q1 확정(`_render_denial_notice`), 블록 문구 정정, 재진입 리마인더·`finish_challenge_kind`(Gap-03), 워커 목록 근거(Gap-04), `_challenge_reset`(Gap-05), 워커 입력 리마인더(Gap-02), 테스트 목록 갱신 | 배상규 |
