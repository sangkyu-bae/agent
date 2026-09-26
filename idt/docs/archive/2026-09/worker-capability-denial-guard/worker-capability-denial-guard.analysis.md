# worker-capability-denial-guard Gap Analysis

> **Analysis Type**: Gap Analysis (정적 Design↔구현 대조 + 실런 사실 반영)
>
> **Project**: sangplusbot (idt 백엔드)
> **Version**: 미지정
> **Analyst**: 배상규 (bkit gap-detector)
> **Date**: 2026-09-25
> **Design Doc**: [worker-capability-denial-guard.design.md](../02-design/features/worker-capability-denial-guard.design.md)
> **Planning Doc**: [worker-capability-denial-guard.plan.md](../01-plan/features/worker-capability-denial-guard.plan.md)
> **구현 상태**: git working tree (미커밋)

### Pipeline References

| 문서 | 검증 대상 |
|------|----------|
| [Supervisor 그래프 계약 3종](../../../docs/wiki/backend/patterns/supervisor-graph-contracts.md) | 계약 ①②③ 준수 |
| [supervisor-early-finish-fix Analysis](./supervisor-early-finish-fix.analysis.md) | 재사용 게이트(D-05)·6경로 불변식·carry item |
| `CLAUDE.md` §3 | 함수 40줄·중첩 2단계·명시적 타입 |

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

## Strategic Alignment Check

### 핵심 문제가 해결되었는가 — ⚠️ 메커니즘은 동작, 사용자 결과는 미달 (0/2)

**가드 메커니즘은 설계대로 동작했지만, 실런 2건 모두 최종 답변이 여전히 "본문 조회 불가"였다.**

| 런 | 코드 상태 | supervisor 호출 | 되물음 | 최종 답변 |
|---|---|:-:|:-:|---|
| `a217f45e` | Q1 수정 전 (final_answer 주의 블록 없음) | 3회 | 발동 | ❌ "본문 조회 불가" |
| `295d2915` | Q1 수정 후 (`_render_denial_notice` + 블록 문구 정정) | 3회 | 발동 | ❌ "본문 조회 불가" |

`295d2915`에서 **블록이 렌더된 결정(#2)은 "get_inquiry로 볼 수 있다"고 올바르게 판단했다.** 그러나 되물음 재결정(#3)과 `final_answer`는 다시 "본문 조회 불가"로 돌아갔고, 근거로 다음 두 문구를 인용했다.

- `list_inquiries` 도구 description: *"원문은 어떤 도구로도 볼 수 없습니다"* (연락처 원문을 뜻함)
- 에이전트 프롬프트 Tool Guidelines: *"원문을 확인할 수 없다"* (개인정보 원문을 뜻함)

두 문구는 Plan §2.2에서 범위 밖으로 둔 **데이터 결함**(결함 3)이다. 그런데 이 결함은 워커 **산출**만이 아니라 supervisor·final_answer가 **신뢰하는 입력**에도 들어 있다.

- supervisor 블록은 "능력 판단은 '사용 가능한 워커' 목록으로만"이라고 지시한다. 그 목록의 `list_inquiries` 설명에 결함 문구가 들어 있다.
- final_answer 주의 블록은 "위 에이전트 지침에 있는 다른 도구"를 근거로 삼으라고 지시한다. 그 에이전트 지침(Tool Guidelines)에 결함 문구가 들어 있다.

→ 워커 산출만 무력화하는 이 가드로는 이길 수 없는 구조다. Plan §5 Risk #8은 *"본 피처는 오독이 있어도 최종 답변이 오염되지 않게 하는 것이 목표"* 라고 했지만 실측에서는 성립하지 않았다. **Critical 전략 미정렬(Gap-01).** 해소 수단은 코드가 아니라 데이터 수정(§9.1-1)이 가장 싸다.

### Success Criteria Status (Plan §3.1 FR)

| ID | 요구사항 | 상태 | 근거 |
|----|----------|:----:|------|
| FR-01 | (A) `_TOOL_USAGE_NORM` task 외 능력 질문 무응답 규범 | ⚠️ Partial | 정적: `prompt_rendering.py:97-105` — 전달 의무(`:93`) 뒤에 배치, '생략' 미사용, 추가분 ≤150자, 절대 프레이밍 없음. `TestTaskScopeNorm` 6건. **실런: 두 런 모두 되물음이 발동했다 = 워커가 여전히 능력 부정 문구를 냈다** → 1차 방어가 도구 description에 밀림(Gap-02) |
| FR-02 | `CapabilityDenialPolicy.detect(body, patterns) -> str` | ✅ Met | `policies.py:368-408`. str 아님→`""`, 공백 패턴 무시, 요약 `"{_REASON}: '{pattern}'"`[:120], 원문 미포함. 단위 11건 |
| FR-03 | 패턴 config 외부화 + main.py tuple 정규화 + kwarg 주입 | ✅ Met | `config.py:120-131`(기본 6개, Plan과 동일), `main.py:2259-2268`, `main.py:2862-2863`. application에 `src.config` import 0건. 설정 테스트 5건 |
| FR-04 | `last_worker_denial` 필드, 워커 덮어쓰기·supervisor 리셋, 전 종료 경로 리셋 | ✅ Met | `supervisor_state.py:48-53`, `supervisor_nodes.py:287`(초기값), 6개 return 경로 `:356/:370/:386/:469/:494/:520`. 경로별 테스트 6건 |
| FR-05 | `_wrap_worker` 산출 판정 + 오류 시 생략, 함수 노드는 Design 결정 | ✅ Met | Design D-04 "전 워커" 채택. `workflow_compiler.py:238-265`(오류 우선 `:256-258`), 등록 루프 `:1053-1057`(빈 결과 바깥, `_wrap_step` 안쪽) |
| FR-06 | "[워커 능력 부정 감지]" 블록, 이름 미나열 | ✅ Met | `supervisor_nodes.py:114-139`. 5개 항목 + a217f45e 정정 문구("워커 설명에 적힌 제한은 그 워커에만"). 이름 미나열 테스트 |
| FR-07 | 블록 배타 오류 > 빈 결과 > 능력 부정 | ✅ Met | `_select_guidance_block` `supervisor_nodes.py:142-164`, 프롬프트 한 자리 `:425`. 배타 테스트 4+2건 |
| FR-08 | `finish_challenge_pending` 합산 1회, route 순서 불변 | ✅ Met | `:404` `guidance_kind in ("empty","denial")`, route `:592-` 무수정. 통합: 동시 신호에도 supervisor 3회로 고정 |
| FR-09 | 신호 없으면 결정 프롬프트 바이트 동일 | ✅ Met | `test_prompt_byte_identical_when_no_signal` + 기존 early-finish-fix 바이트 동일 테스트 통과 |
| FR-10 | 복합 질문에서 "어떤 도구로도 볼 수 없다"가 최종 답변에 나가지 않음 | ⚠️ Partial | **메커니즘 충족**: 블록·되물음·Q1 final_answer 주의 블록(`workflow_compiler.py:268-295`, `:1486-1503`), 전환 지점은 블록 문구뿐. **결과 미충족**: 실런 0/2 — 데이터 결함(Plan §2.2 범위 밖)이 원인 |
| FR-11 | 되물음 발동 구조화 로그(사유·request_id·워커 id) | ✅ Met | `supervisor_nodes.py:405-411` `logger.info("finish challenge raised", reason_kind=, last_worker_id=)`. request_id는 LogContext ContextVar가 암묵으로 주입(Gap-08). **부수 효과**: `empty`도 기록 → early-finish-fix Gap-04(FR-09 로그 누락) 해소 |
| FR-12 | `ai_run_step` supervisor reasoning 추적 경로 유지 | ✅ Met | `_step_output_summary` 무변경(`:475`). 실런 2건에서 supervisor 3회 reasoning 추적 확인 |

**충족률**: 완전 10 / 부분 2 / 미충족 0 = **11 / 12 (91.7%)**

### Plan §4.1 Definition of Done

| 항목 | 상태 | 근거 |
|------|:----:|------|
| FR-01~12 구현 | ✅ | 위 표 |
| TDD 준수 | ⚠️ 미검증 | 테스트 파일은 전부 존재. 작성 순서는 미커밋 상태라 이력으로 확인 불가 |
| 재현 단위 시나리오 (되물음 1회, 재결정 프롬프트에 블록, 2번째 FINISH 통과) | ✅ | `test_denial_integration.py::test_denial_triggers_one_challenge_then_finishes`, `test_challenge_prompt_carries_denial_block_once` |
| 오탐 시나리오 ("확인되지 않았습니다" 미발동) | ✅ | `test_legitimate_unconfirmed_answer_is_not_detected` |
| 실런 L3 | ⚠️ | 실행 완료(2건). 메커니즘 ✅, 최종 답변 ❌ |
| `_TOOL_USAGE_NORM` 단언 갱신 | ✅ | `test_worker_context_block.py::TestTaskScopeNorm` |
| `/verify-architecture`·`/verify-logging`·`/verify-tdd` | ⚠️ 미실행 | 본 분석의 정적 점검(§6)으로 대체 |

### Decision Record Verification

| Source | Decision | Followed? | 비고 |
|--------|----------|:---------:|------|
| [Plan] | 판정 위치 = domain policy | ✅ | `policies.py:368`, stdlib 외 import 없음 |
| [Plan] | 판정 방식 = 문구 패턴(config), LLM 0회 | ✅ | 추가 LLM 호출 없음 (final_answer 주의 블록도 결정적 재판정) |
| [Plan] | 되물음 플래그 재사용(합산 1회) | ✅ | 신규 플래그 없음 |
| [Plan] | 신호 채널 = state 필드(메시지 삽입 금지) | ✅ | |
| [Plan] | 기대 동작은 블록 문구 + config로만 | ✅ | 코드 분기 없음 |
| [Plan] | 데이터 결함은 권고 | ✅(범위) / ❌(결과) | 범위 결정은 지켰으나 결과를 좌우한 요인이 됨(Gap-01) |
| [Design] | Option C Pragmatic, 신규 소스 파일 0 | ✅ | 신규 소스 0, 수정 7 |
| [Design] D-01 | `CapabilityDenialPolicy` 계약 | ✅ | `@classmethod`, 인자 타입힌트 없음(Gap-09, EmptyResultPolicy 동형) |
| [Design] D-02 | `last_worker_denial` 수명주기 = `last_worker_empty` 동형 | ✅ | |
| [Design] D-03 | config 기본 6개 + main 정규화 | ✅ | |
| [Design] D-04 | 전 워커 데코레이터, 빈 결과 바깥·`_wrap_step` 안쪽 | ✅ | `worker_map` 전 항목(react·search·collect·action·analysis·docgen·sub_agent) 경유 |
| [Design] D-05 | 블록 문구, 계약 ②, ≤400자 | ✅ | 문구는 Design §4.3보다 확장(Gap-06), 길이는 기본 패턴 기준만 보장(Gap-07) |
| [Design] D-06 | 배타 선택 분리 함수 + `kind` 분기 | ✅ | `tuple[str, str]` 반환 — §4.1 계약 준수(§4.4 예시 코드의 `-> str`은 Design 내부 불일치) |
| [Design] D-07 | 6개 return 경로 불변식 + 테스트 고정 | ✅ | 6/6 테스트 |
| [Design] D-08 | 워커 규범 위치·낱말·길이 | ✅ | `[현재 작업]` 헤더가 `_build_worker_input`(`workflow_compiler.py:374`)과 일치 |
| [Design] Q1 | final_answer 안내는 L3 결과로 확정 | ✅ 확정·구현 | a217f45e에서 필요 확정 → 새 state 필드 없이 이번 턴 워커 산출 재판정으로 구현. Design 미반영(Gap-06) |
| [Design] Q2 | 분석·문서생성 노드 오탐 없음 | ⚠️ 부분 | 비str content 생략은 정책 단위로만 검증. 노드 단위 테스트 없음(Gap-11) |
| [Design] Q3 | 로그 `reason_kind`로 구분, state 플래그 미분리 | ✅ | `:409` |

**결정 이탈 없음.** Q1은 설계가 열어 둔 분기대로 확정됐다.

---

## 1. Analysis Overview

### 1.1 Analysis Purpose

Design §4 내부 계약과 구현의 일치도, Plan FR-01~12 충족도, 그리고 실런 2건에서 사용자 결과가 개선됐는지를 검증한다.

### 1.2 Analysis Scope

- **Design Document**: `docs/02-design/features/worker-capability-denial-guard.design.md`
- **Implementation Path**: `src/domain/agent_builder/policies.py`, `src/config.py`, `src/api/main.py`, `src/application/agent_builder/{supervisor_state,supervisor_nodes,workflow_compiler}.py`, `src/application/agent_run/prompt_rendering.py`
- **Tests**: 신규 6파일 + 수정 1파일 (§5)
- **Runtime**: pytest 전량 + 로컬 실런 2건 (`a217f45e`, `295d2915`) — 사실은 Do 단계 기록을 인용, 본 분석에서 재실행하지 않음
- **N/A**: HTTP API 엔드포인트·UI 없음 → §2.1 API / §2.5 Page UI Checklist / L2 UI 테스트 생략. Contract 축은 Design §4 "내부 계약 명세"로 대체

---

## 2. Gap Analysis (Design vs Implementation)

### 2.1 API Endpoints — N/A

HTTP API 변경 없음. 내부 계약은 §2.6에서 대조한다.

### 2.2 Data Model

| 항목 | Design | Implementation | Status |
|------|--------|----------------|:------:|
| `SupervisorState.last_worker_denial: str` | §3.1 | `supervisor_state.py:53` + 설계 출처·수명주기 주석 `:48-52` | ✅ |
| `build_initial_state` 초기값 `""` | §3.1 | `supervisor_nodes.py:287` | ✅ |
| 읽기 `state.get(..., "")` 하위호환 | §3.1 | `supervisor_nodes.py:123` | ✅ |
| `finish_challenge_pending` 의미 확장 + 주석 | §3.1 | `supervisor_state.py:57-58` | ✅ |
| `capability_denial_patterns: str` | §3.3 | `config.py:128-131` (문자열 동일) | ✅ |
| payload 누출 | Plan §6.2 | `run_agent_use_case.py`는 `finish_challenge_pending`만 복원 시 리셋(`:874`), 신규 필드를 payload에 싣지 않음 | ✅ |
| DB 스키마 | 변경 없음 | 변경 없음 | ✅ |

### 2.3 Component Structure (Design §4.1 변경/신설 함수)

| # | Design 항목 | 구현 위치 | Status |
|---|------------|----------|:------:|
| 1 | `CapabilityDenialPolicy.detect` | `policies.py:390-408` | ✅ |
| 2 | `_with_denial_signal(fn, patterns)` | `workflow_compiler.py:238-265` | ✅ |
| 3 | `WorkflowCompiler.__init__` kwarg | `workflow_compiler.py:479-481`, `:527-528` | ✅ |
| 4 | 노드 등록 루프 전 워커 적용 | `workflow_compiler.py:1053-1057` | ✅ |
| 5 | `_render_capability_denial_block(state)` | `supervisor_nodes.py:114-139` | ✅ |
| 6 | `_select_guidance_block(state, wiki_worker_id)` | `supervisor_nodes.py:142-164` | ✅ |
| 7 | `supervisor_node` 배타 주입·pending·6경로 | `supervisor_nodes.py:341-522` | ✅ |
| 8 | `build_initial_state` | `supervisor_nodes.py:286-287` | ✅ |
| 9 | `_TOOL_USAGE_NORM` | `prompt_rendering.py:97-105` | ✅ |
| 10 | `_capability_denial_patterns()` | `main.py:2259-2268`, 주입 `:2862-2863` | ✅ |
| + | `_render_denial_notice(messages, patterns)` (Q1 확정분, Design 미기재) | `workflow_compiler.py:268-295`, 사용 `:1486-1503` | ⚠️ Design 미반영 |
| — | `route_to_worker_or_final`, `route_map` 변경 없음 | `supervisor_nodes.py:592-` 무수정 | ✅ (주석만 낡음, Gap-10) |

**Structural: 10/10 + 추가 1 (Design 반영 필요)**

### 2.4 Functional Depth Analysis

| 파일 | Depth | Placeholder | 비고 |
|------|:-----:|:-----------:|------|
| `policies.py` (CapabilityDenialPolicy) | 100 | 없음 | 실측 문구 기반, 오탐 방지 docstring |
| `supervisor_nodes.py` (블록·배타·6경로·로그) | 100 | 없음 | |
| `workflow_compiler.py` (데코레이터·배선·final_answer 주의) | 100 | 없음 | |
| `prompt_rendering.py` (A 규범) | 100 | 없음 | 정적으로는 완전, 런타임 효과는 미달(Gap-02) |
| `config.py` / `main.py` | 100 | 없음 | |
| `supervisor_state.py` | 100 | 없음 | |

**Shallow File Count**: 0 / 7 (0%)

### 2.5 Page UI Checklist — N/A

### 2.6 내부 계약 검증 (Design §4 — API Contract 축 대체)

| # | 계약 | Design | 구현 | 테스트 | Contract |
|---|------|:------:|:----:|:------:|:--------:|
| 1 | `detect`: str 아니면 `""` | §3.2 | ✅ `:403` | ✅ | PASS |
| 2 | `detect`: 패턴 None/빈 → `""` (off 스위치) | §3.2 | ✅ `:405` | ✅ | PASS |
| 3 | `detect`: 요약 ≤120자, 매칭 패턴 포함, 원문 미포함 | §3.2 | ✅ `:407` | ✅ 3건 | PASS |
| 4 | 데코레이터: 비 dict 통과 | §4.2 | ✅ `:253` | ✅ | PASS |
| 5 | 데코레이터: 오류 있으면 `""` | §4.2 | ✅ `:256-258` | ✅ | PASS |
| 6 | 데코레이터: `messages[-1].content` 판정 | §4.2 | ✅ `:259-260` | ✅ | PASS |
| 7 | 데코레이터: 항상 세팅(정상 `""`) | §4.2 | ✅ `:262` | ✅ | PASS |
| 8 | 데코레이터: 패턴 None → `""` | §4.2 | ✅ | ✅ | PASS |
| 9 | 등록 루프: 빈 결과 바깥 / `_wrap_step` 안쪽 | §4.2 | ✅ `:1051-1060` | ✅(react) | PASS |
| 10 | 블록: 신호 없으면 `""` | §4.3 | ✅ `:124-125` | ✅ | PASS |
| 11 | 블록: 워커·도구 이름 미나열 (계약 ②) | §4.3 | ✅ | ✅ | PASS |
| 12 | 블록: ≤400자 | §4.3 | ⚠️ 기본 패턴(요약 ≈35자)에서 ≈370자, 사용자 지정 긴 패턴이면 요약 120자까지 → 최대 ≈457자 | ⚠️ 고정 사유로만 측정 | PARTIAL |
| 13 | 블록: 문구 = Design §4.3 | §4.3 | ⚠️ 의미 동일 + a217f45e 정정 절 추가, Design 미갱신 | ✅ | PARTIAL(문서) |
| 14 | 배타: 오류 > 빈 결과 > 능력 부정 | §4.4 | ✅ | ✅ | PASS |
| 15 | pending: `kind` 분기, 오류 제외 | §4.4 | ✅ `:404` | ✅ | PASS |
| 16 | 한 자리 치환으로 바이트 동일 | §4.4 | ✅ `:425` | ✅ | PASS |
| 17~22 | return 6경로: `last_worker_denial=""`, pending 확정 | §4.5 | ✅ `:351-358`, `:367-372`, `:378-388`, `:465-471`, `:483-496`, `:506-522` | ✅ 6건 | PASS ×6 |
| 23 | 규범: 전달 의무 뒤 | §4.6 | ✅ | ✅ | PASS |
| 24 | 규범: '생략' 미사용 | §4.6 | ✅ | ✅ | PASS |
| 25 | 규범: `[현재 작업]` 헤더 일치 | §4.6 | ✅ `workflow_compiler.py:374` | — | PASS |
| 26 | 규범: ≤150자 | §4.6 | ✅ | ✅ | PASS |
| 27~31 | `__init__` kwarg 기본 None→`()`, main 정규화, 레이어 import 금지 | §4.1 / §9.3 | ✅ | ✅ | PASS ×5 |
| 32 | 그래프 계약 ① 신호는 state 채널만 (메시지 삽입 없음) | §1.2 | ✅ 데코레이터·supervisor·final_answer 모두 system/state만 사용 | ✅ `test_preserves_existing_keys` | PASS |
| 33 | 그래프 계약 ② 목록 프레이밍 금지 | §1.2 | ✅ supervisor 블록·final_answer 주의 블록 모두 이름 없음 | ✅ 2건 | PASS |
| 34 | 그래프 계약 ③ 탐지만 결정적, 행동은 LLM | §1.2 | ✅ 강제 라우팅 없음 | ✅ `test_challenge_lets_supervisor_route_to_another_worker` | PASS |

**Contract Match Rate**: 33 / 34 = **97%** (PARTIAL 2건을 각 0.5로 계산)

### 2.7 Runtime Verification Results

#### L1: 자동 테스트 (pytest — API curl 대체)

| # | 대상 | 결과 |
|---|------|:----:|
| 1 | `uv run python -m pytest tests/application tests/domain tests/unit` | ✅ **6405 passed, 0 failed** |
| 2 | 신규/수정 테스트 76건 (§5) | ✅ 포함 |
| 3 | 빈 결과 회귀 (`test_supervisor_empty_block.py`, `test_empty_result_integration.py`, `test_supervisor_worker_error.py`, `test_supervisor_nodes.py`) | ✅ 포함 |

**L1 Score**: 100%

#### L2: UI Action Tests — N/A (UI 없음)

#### L3: 실런 재현 (로컬 Customer Inquiry MCP 8007, 에이전트 `e557f77e…`)

입력: "지금 답변이 안된 문의 글을 좀 확인해서 뭐뭐가 있는지 알려주실래요? 그리고 각각 본문을 읽을 수 있나요?"

| # | 점검 항목 (Design §8.6) | `a217f45e` (Q1 전) | `295d2915` (Q1 후) | 판정 |
|---|------------------------|:---:|:---:|:---:|
| 1 | `ai_run_step` supervisor ≥2회 | ✅ 3회 | ✅ 3회 | ✅ |
| 2 | 되물음 정확히 1회, 무한 루프 없음 | ✅ | ✅ | ✅ |
| 3 | 재결정 reasoning 추적 (FR-12) | ✅ | ✅ | ✅ |
| 4 | 부작용 없음 (읽기 전용 도구, `submit_reply`는 승인 게이트) | ✅ | ✅ | ✅ |
| 5 | 재결정이 능력 판단 근거를 바꿈 | ❌ | ⚠️ #2는 "get_inquiry로 볼 수 있다", #3에서 원복 | ⚠️ |
| 6 | 최종 답변에 "본문 조회 불가"류 부재 (FR-10) | ❌ | ❌ | ❌ |

- 두 런 모두 되물음 발동 = 워커 산출에 능력 부정 문구가 있었다 → FR-01(A) 1차 방어 미작동 (Gap-02)
- #3·final_answer의 인용 근거는 `list_inquiries` description("원문은 어떤 도구로도 볼 수 없습니다")과 에이전트 Tool Guidelines("원문을 확인할 수 없다") → 데이터 결함 (Gap-01)

**L3 Score** = 메커니즘(1~4) 4/4 × 0.5 + 결과(5: 0.5, 6: 0)/2 × 0.5 = 50 + 12.5 = **62.5%**

**Runtime Match Rate** (가중식에 투입): **L3 = 62.5%** — L1은 정적 축(Functional·Contract)의 증거로 이미 반영했으므로 중복 가산하지 않는다(보수적 산정).

### 2.8 Match Rate Summary

| 축 | 점수 | 근거 |
|----|:----:|------|
| Structural | **100%** | Design §4.1 10/10 구현·배선 + Q1 확정분 1개 추가 |
| Functional | **91.7%** | FR 12건 중 완전 10 / 부분 2 (FR-01 런타임, FR-10 결과) |
| Contract | **97%** | 내부 계약 34항목 중 PASS 32 / PARTIAL 2 (블록 길이 최악값, Design 문구 미갱신) |
| Runtime (L3) | **62.5%** | 메커니즘 4/4, 사용자 결과 0/2 |

```
정적 공식 (Structural×0.2 + Functional×0.4 + Contract×0.4)
  = 100×0.2 + 91.7×0.4 + 97×0.4
  = 20 + 36.67 + 38.80
  = 95.5%

런타임 가중 공식 (Structural×0.15 + Functional×0.25 + Contract×0.25 + Runtime×0.35)
  = 100×0.15 + 91.7×0.25 + 97×0.25 + 62.5×0.35
  = 15 + 22.92 + 24.25 + 21.88
  = 84.0%
```

**Overall Match Rate: 84.0%** (런타임 실행분 반영, 목표 90% 미달) / 정적 전용 참고치 95.5%

미달 원인은 코드 결함이 아니라 **실런 사용자 결과 0/2**다. 가장 싼 해소 수단은 데이터 수정 후 재실런이다(§9.1).

---

## 3. Code Quality Analysis

### 3.1 함수 길이·중첩 (CLAUDE.md §3: 40줄 / 2단계)

| 파일 | 함수 | 길이 | 중첩 | Status |
|------|------|:----:|:----:|:------:|
| `policies.py` | `CapabilityDenialPolicy.detect` | 18 (docstring 포함) | 2 (for→if) | ✅ |
| `workflow_compiler.py` | `_with_denial_signal` (+`wrapped`) | 28 / 13 | 1 | ✅ |
| `workflow_compiler.py` | `_render_denial_notice` | 28 | 2 (for→if) | ✅ |
| `supervisor_nodes.py` | `_render_capability_denial_block` | 26 | 1 | ✅ |
| `supervisor_nodes.py` | `_select_guidance_block` | 23 | 1 | ✅ |
| `main.py` | `_capability_denial_patterns` | 10 | 0 | ✅ |
| `supervisor_nodes.py` | `supervisor_node` (클로저) | **182** (`:341-522`) | 2 | ❌ carry item (Gap-05) |
| `workflow_compiler.py` | `final_answer_node` (클로저) | 100+ (`:1424-`) | 2 | ❌ 사전 위반, 이번 +8줄 |

`supervisor_node`는 early-finish-fix 시점 145줄 carry item이었다. 배타 선택은 `_select_guidance_block`으로 분리했지만, D-07 신호 리셋 6줄 + FR-11 로그 7줄 + 주석이 더해져 Plan §4.2 *"본문 길이를 늘리지 않는다"* 는 지켜지지 않았다.

### 3.2 Code Smells

| Type | File | Location | Description | Severity |
|------|------|----------|-------------|:--------:|
| 타입힌트 누락 | `policies.py` / `workflow_compiler.py` / `supervisor_nodes.py` | `detect(cls, body, patterns)`, `_with_denial_signal(fn, patterns)`, `_render_capability_denial_block(state)`, `_render_denial_notice(..., patterns)` | CLAUDE.md §3 "명시적 타입". 선례 `EmptyResultPolicy`와 동형 | 🟢 |
| 모듈 간 private 참조 | `workflow_compiler.py` | `:41` | `supervisor_nodes._current_turn_messages`를 import해 재사용 | 🟢 |
| 낡은 주석 | `supervisor_nodes.py` | `:609-612` | route 주석이 "빈 결과 미해소"만 언급, 능력 부정 합산 의미 누락 | 🟢 |
| 로그 이벤트명 | `supervisor_nodes.py` | `:405-411` | 블록 렌더 시점에 "finish challenge raised" 기록 — LLM이 워커를 고르면 실제 되돌림 없이도 찍힘 | 🟢 |
| Design Ref / Plan SC 주석 | 전 변경 지점 | — | 11곳 부착 (`policies.py:371`, `workflow_compiler.py:241/272/479/527/1053/1486`, `supervisor_nodes.py:117/145/355/518`, `prompt_rendering.py:97`, `config.py:120`, `main.py:2260`) | ✅ |
| `print()` | — | — | 없음 | ✅ |

### 3.3 Security Issues

| Severity | 항목 | 결과 |
|:--------:|------|------|
| 🟢 | 외부 콘텐츠 승격 | 요약·블록·주의 블록에 워커 산출 원문 없음. 운영자 설정 패턴만 인용 (`test_summary_is_policy_authored_not_raw_content`) |
| 🟢 | 블록 위치 | supervisor/final_answer system 프롬프트에만. 대화 메시지 삽입 없음 |
| 🟢 | 권한 경로 | 변경 없음. `get_inquiry` 호출은 기존 워커 게이트·승인 정책 적용 |

---

## 4. Performance Analysis

| 항목 | 결과 |
|------|------|
| 추가 LLM 호출 | 판정 0회. 되물음 발동 시 supervisor 결정 1회 추가 (실런 3회 = 1 + 1 + 1 되물음) |
| 토큰 | 블록은 발동 시에만(≈370자), 규범 추가분 ≤150자. final_answer 주의 블록은 발동 시에만 (≈260자 + 요약) |
| 판정 비용 | 워커 산출 1건당 부분 문자열 탐색 × 패턴 6개 — 무시 가능 |

---

## 5. Test Coverage

| 파일 | 구분 | 케이스 | 대상 |
|------|:----:|:------:|------|
| `tests/domain/agent_builder/test_capability_denial_policy.py` | 신규 | 11 | FR-02, Design §8.2 #1~7 |
| `tests/unit/test_capability_denial_config.py` | 신규(Design 미기재) | 5 | FR-03 |
| `tests/application/agent_builder/test_denial_signal_wiring.py` | 신규 | 12 | FR-04, FR-05, §8.4 #1·3·4·5 |
| `tests/application/agent_builder/test_supervisor_denial_block.py` | 신규 | 29 | FR-06~09, FR-11, §8.3 #1~6, a217f45e 정정 |
| `tests/application/agent_builder/test_denial_integration.py` | 신규 | 8 | §8.5 L3 스텁, 합산 1회, 무한 루프 없음 |
| `tests/application/agent_builder/test_final_answer_denial_notice.py` | 신규(Design 미기재) | 5 | Q1 / FR-10 |
| `tests/application/agent_run/test_worker_context_block.py` | 수정 | +6 (`TestTaskScopeNorm`) | FR-01 |

**신규·수정 합계 76건.** 전량 스위트 6405 passed.

### 5.2 미커버 영역

- **함수 노드 배선** (Design §8.4 #2): search/collect/action/analysis/docgen 산출에 패턴이 있을 때 신호가 서는지 — 등록 루프 구조상 덮이지만 통합 테스트는 react 워커만 검증
- **Q2 노드 단위 오탐**: 분석·문서생성 노드 실제 산출 형식에서의 미발동 — 정책 단위(비str 생략)로만 확인
- **블록 최악 길이**: 요약 120자 상한에서 400자 예산 — 고정 사유로만 측정
- `test_supervisor_empty_block.py` 배타 시나리오 확장(Design §11.1)은 `test_supervisor_denial_block.py`로 옮겨 구현 — 커버리지는 동등
- **프롬프트의 행동 효과** — 단위 테스트로 증명 불가, 실런으로만 측정 (L3 결과는 §2.7)

---

## 6. Clean Architecture Compliance

| Layer | 기대 의존 | 실제 | Status |
|-------|----------|------|:------:|
| Domain (`policies.py`) | 표준 라이브러리만 | `dataclasses`, `enum` 외 없음. `CapabilityDenialPolicy`는 str만 수신 | ✅ |
| Application (`supervisor_*`, `workflow_compiler`, `prompt_rendering`) | domain, LangGraph/LangChain | `src.config` import 0건 (주석 1줄만 일치) | ✅ |
| Composition root (`main.py`) | 전부 | config → tuple → kwarg | ✅ |
| Infrastructure / Interfaces | 변경 없음 | 변경 없음 | ✅ |

| Component | Designed Layer | Actual | Status |
|-----------|---------------|--------|:------:|
| `CapabilityDenialPolicy` | Domain | `src/domain/agent_builder/policies.py` | ✅ |
| `last_worker_denial` | Application(state) | `supervisor_state.py` | ✅ |
| `_with_denial_signal`, `_render_denial_notice` | Application | `workflow_compiler.py` | ✅ |
| `_render_capability_denial_block`, `_select_guidance_block` | Application | `supervisor_nodes.py` | ✅ |
| `_TOOL_USAGE_NORM` | Application | `prompt_rendering.py` | ✅ |
| `capability_denial_patterns` | Config | `config.py` | ✅ |
| `_capability_denial_patterns()` | Composition root | `main.py` | ✅ |

**Architecture Score: 100%**

---

## 7. Convention Compliance

| Category | Convention (Design §10) | 결과 |
|----------|------------------------|:----:|
| 정책 클래스 | `XxxPolicy` → `CapabilityDenialPolicy` | ✅ |
| state 채널 | `last_worker_<signal>` → `last_worker_denial` | ✅ |
| 데코레이터 | `_with_<signal>_signal` → `_with_denial_signal` | ✅ |
| 블록 렌더 | `_render_<name>_block` → `_render_capability_denial_block` | ✅ (final_answer용은 `_render_denial_notice` — 블록 아닌 notice로 구분) |
| 설정값 | `<feature>_patterns` 콤마 문자열 | ✅ |
| 환경변수 | `CAPABILITY_DENIAL_PATTERNS` (선택) | ✅ env override 테스트 |
| Design Ref / Plan SC 주석 | 필수 | ✅ |
| 프롬프트 낱말 | '생략'·"A라고만" 금지 | ✅ |
| 함수 길이 | `supervisor_node` 늘리지 않음 | ❌ (Gap-05) |
| 명시적 타입 | CLAUDE.md §3 | ⚠️ (Gap-09) |

**Convention Score: 90%**

---

## 8. Gap 목록 (심각도·신뢰도)

| ID | 심각도 | 신뢰도 | 내용 | 근거 |
|----|:------:|:------:|------|------|
| **Gap-01** | 🔴 Critical (전략) | 90% | FR-10 사용자 결과 미달 — 실런 0/2에서 최종 답변이 "본문 조회 불가". 원인은 데이터 결함(범위 밖)이지만, Plan §5 Risk #8이 약속한 "오독이 있어도 최종 답변 무오염"이 성립하지 않았다. 결함 문구가 워커 산출이 아니라 **신뢰 입력**(워커 목록 description, 에이전트 Tool Guidelines)에 있어서 가드의 판단 근거 자체를 오염시킨다 | §2.7 L3 #6 |
| **Gap-02** | 🟡 Important | 80% | FR-01(A) 1차 방어가 런타임에서 작동하지 않음 — 두 런 모두 되물음 발동 = 워커가 여전히 능력 질문에 불가를 답함. 규범이 도구 description에 밀린 Plan §1.2 결함 1 기전이 그대로 재현 (추정: 되물음 발동에서 역산, 워커 원문은 재확인하지 않음) | §2.7 L3 |
| **Gap-03** | 🟡 Important | 75% | 되물음 재결정(#3)에는 블록이 없다 — 신호를 #2에서 소비·리셋하므로(Design §2.2 step 4), 실제 "되물음" 결정은 안내 없이 원래 믿음으로 돌아간다. `295d2915`의 #2가 옳게 판단했지만 FINISH `answer`는 DQ1로 폐기되고 reasoning은 대화에 남지 않아 #3·final_answer로 전달되지 않았다. early-finish-fix Gap-01과 같은 구조 | `supervisor_nodes.py:506-522`, 실런 #2→#3 |
| **Gap-04** | 🟡 Important | 75% | final_answer 주의 블록의 판단 근거가 "위 에이전트 지침에 있는 다른 도구"(`workflow_compiler.py:291`)다. final_answer 노드는 등록 워커 목록을 받지 않으므로 Plan Core Value("능력은 등록된 워커 목록이 결정")와 근거가 어긋난다. 이 에이전트에서는 지침 자체가 결함 문구를 담고 있어 주의 블록이 이길 수 없다 | `workflow_compiler.py:1494-1504` |
| **Gap-05** | 🟡 Important | 85% | `supervisor_node` 182줄(`:341-522`) — 40줄 규칙 위반(사전 carry). 이번에 신호 리셋·FR-11 로그로 늘어나 Plan §4.2 "본문 길이를 늘리지 않는다" 미충족 | §3.1 |
| **Gap-06** | 🟢 Minor | 95% | Design 문서 표류: §4.1에 `_render_denial_notice` 없음, §4.3 블록 문구(정정 절) 미반영, §6.2 Q1 "1차는 넘기지 않는다" 그대로, §4.4 예시 `-> str`와 §4.1 `tuple` 불일치, §11.1 테스트 목록(설정·final_answer 테스트 추가, empty_block 파일 미수정) | §2.3, §5 |
| **Gap-07** | 🟢 Minor | 70% | 블록 ≤400자는 기본 패턴 길이에서만 성립. 사용자 지정 긴 패턴이면 요약 상한 120자까지 커져 최대 ≈457자. 길이 테스트는 고정 사유로만 측정 (길이는 수작업 추산) | §2.6 #12 |
| **Gap-08** | 🟢 Minor | 80% | FR-11 로그: request_id는 명시 필드가 아니라 LogContext ContextVar 암묵 주입(HTTP 밖 실행이면 자동 UUID). 이벤트가 블록 렌더 시점에 찍혀 실제 되돌림 여부와 1:1이 아님 | `supervisor_nodes.py:405-411` |
| **Gap-09** | 🟢 Minor | 95% | 신규 함수 인자 타입힌트 누락 (CLAUDE.md §3) | §3.2 |
| **Gap-10** | 🟢 Minor | 95% | `route_to_worker_or_final` 주석이 빈 결과만 언급 — 합산 의미 미반영 | `supervisor_nodes.py:609-612` |
| **Gap-11** | 🟢 Minor | 85% | 함수 노드 배선·Q2 노드 단위 오탐 테스트 부재 (구조상 덮이나 회귀 고정 없음) | §5.2 |

---

## 9. Recommended Actions

### 9.1 Immediate (iterate 대상)

| Priority | Item | 위치 | 기대 효과 |
|:--------:|------|------|----------|
| 🔴 1 | **[Gap-01] 데이터 수정 후 재실런** — `list_inquiries` description을 "**연락처** 원문은 어떤 도구로도 볼 수 없습니다"로, 에이전트 `e557f77e…` Tool Guidelines를 "고객 **개인정보(연락처)** 원문은 확인할 수 없다"로 명확화. 코드 변경 없음 | `sangplus/mcp` 저장소, DB `agent_definition` | FR-10 결과·FR-01 효과를 결함 없는 조건에서 측정. 이 재실런 없이는 코드 가드의 실효를 분리 평가할 수 없다 |
| 🟡 2 | **[Gap-03] 되물음 재결정에 판단 근거 유지** — 대안: (a) pending인 재진입 결정에 1줄 리마인더("직전 결정에서 능력 부정 신호가 있었다"), (b) 신호 리셋을 pending 소진 시점으로 늦춤. 둘 다 합산 1회 상한은 그대로 | `supervisor_nodes.py` 블록 선택부 | #2의 올바른 판단이 #3에서 원복되는 경로 차단. early-finish-fix Gap-01에도 적용 가능 |
| 🟡 3 | **[Gap-04] final_answer 주의 블록의 근거를 워커 목록으로** — 대안: supervisor 결정 프롬프트와 같은 `사용 가능한 워커` 설명을 조건부로 싣기(발동 시에만, 이름 나열이 아니라 기존 목록 재사용이므로 계약 ②와 충돌 여부는 위키 계약 문서로 확인 필요) | `workflow_compiler.py:268-295` | Plan Core Value와 근거 일치 |

### 9.2 Short-term

| Priority | Item | 위치 |
|:--------:|------|------|
| 🟡 1 | [Gap-02] 재실런(9.1-1) 결과로 A 규범 재평가. 데이터 수정 후에도 워커가 능력 질문에 답하면 규범 문구 강화 검토(D-08 절대 프레이밍 금지 유지) | `prompt_rendering.py:103-105` |
| 🟢 2 | [Gap-07] 블록 길이 테스트를 요약 상한(120자) 기준으로 보강하거나 블록에서 사유 요약을 짧게 절단 | `test_supervisor_denial_block.py` |
| 🟢 3 | [Gap-11] search 함수 노드 배선 통합 테스트 1건 추가 | `test_denial_integration.py` |
| 🟢 4 | [Gap-08/09/10] 로그 이벤트명·타입힌트·route 주석 정리 | 해당 위치 |

### 9.3 Long-term (backlog)

| Item | 비고 |
|------|------|
| [Gap-05] `supervisor_node` 분해 (Design Option B의 블록 렌더 분리 + return dict 빌더) | early-finish-fix부터 이어진 carry item |
| 프롬프트 컴포저가 도구 description의 모호한 제한 문구를 에이전트 Tool Guidelines로 옮기지 않도록 개선 | Plan §2.2 별도 피처 |

---

## 10. Design Document Updates Needed

- [ ] §4.1 변경/신설 함수 목록에 `_render_denial_notice(messages, patterns)` (final_answer 주의 블록) 추가
- [ ] §4.3 블록 문구를 구현본으로 갱신 — "어떤 워커 설명에 적힌 제한은 그 워커에만 적용" 절 (실런 `a217f45e` 정정)
- [ ] §6.2 Q1 확정 기록: 새 state 필드 없이 이번 턴 워커 산출을 같은 정책으로 재판정해 조건부 주의 블록
- [ ] §4.4 예시 코드 반환형을 `tuple[str, str]`로 정정
- [ ] §11.1 테스트 목록 갱신 (`test_capability_denial_config.py`, `test_final_answer_denial_notice.py` 추가 / `test_supervisor_empty_block.py` 미수정)
- [ ] §2.2 "재진입 시 블록 없음"이 Gap-03의 원인이 될 수 있음을 기록

---

## 11. Runtime Verification Plan

### L1: 자동 테스트 (pytest — HTTP API 없음, curl 대체)

| # | 명령 | 기대 |
|---|------|------|
| 1 | `uv run python -m pytest tests/domain/agent_builder/test_capability_denial_policy.py tests/unit/test_capability_denial_config.py -q` | 16 passed |
| 2 | `uv run python -m pytest tests/application/agent_builder/test_denial_signal_wiring.py tests/application/agent_builder/test_supervisor_denial_block.py tests/application/agent_builder/test_denial_integration.py tests/application/agent_builder/test_final_answer_denial_notice.py -q` | 54 passed |
| 3 | `uv run python -m pytest tests/application/agent_run/test_worker_context_block.py -q` | 전량 통과 |
| 4 | `uv run python -m pytest tests/application tests/domain tests/unit -q` | 0 failed (기준 6405 passed) |

### L2: UI Action Tests — N/A

### L3: 실런 재현 (데이터 수정 후 재실행 권장)

| # | 시나리오 | 절차 | 성공 기준 |
|---|---------|------|----------|
| 1 | 결함 데이터 그대로 (대조군) | 에이전트 `e557f77e…`, 로컬 MCP 8007, `TestClient(src.api.main.app)` + 로컬 JWT, `persist_conversation: false`, Design §8.6 입력 | 기존 결과 재현 확인 (되물음 1회, supervisor 3회) |
| 2 | description·Tool Guidelines 수정 후 | 동일 입력 | 최종 답변이 "본문 조회 가능 + 문의 번호 지정 요청" 또는 `get_inquiry` 실행. "어떤 도구로도"·"본문 조회 불가" 부재 |
| 3 | FR-01 효과 분리 측정 | 시나리오 2의 `ai_run_step`에서 `list_inquiries` 워커 산출 확인 | 워커가 능력 질문에 답하지 않음 → 되물음 미발동(supervisor 2회) |
| 4 | 오탐 대조 | "2023년 답변 완료 문의 알려줘"처럼 결과에 없는 기간 질의 | 되물음 미발동, 워커의 "확인되지 않았습니다" 그대로 전달 |
| 5 | Gap-03 수정 시 | 시나리오 1 재실행 | #3 재결정 reasoning이 #2 판단을 유지 |

확인 지점: `ai_run_step`(supervisor `output_summary` reasoning 순서), 애플리케이션 로그 `finish challenge raised reason_kind=denial`, 최종 답변 본문.

---

## 12. Next Steps

1. [ ] 데이터 수정(9.1-1) → L3 시나리오 2·3 재실런
2. [ ] `/pdca iterate worker-capability-denial-guard` — Gap-03·Gap-04 수정 여부 결정, Minor 정리
3. [ ] Design 문서 갱신(§10)
4. [ ] 재분석 후 90% 도달 시 `/pdca report worker-capability-denial-guard`

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-09-25 | 최초 분석. 정적 95.5% / 런타임 가중 84.0%. Critical 1 (전략, 데이터 기인), Important 4, Minor 6 | 배상규 |

---

## 13. Act-1 재검증 (2026-09-25)

사용자 결정 "지금 모두 수정" → 코드 측 Gap 전부 처리 후 회귀·실런 재실행.

### 13.1 Gap 처리 결과

| ID | 조치 | 검증 |
|----|------|------|
| Gap-01 | 코드 밖(데이터). 권고 유지 — §9.1-1 | 실런 3차에서도 final_answer가 지침의 "원문 불가"로 틀린 문장 생성 (아래) |
| Gap-02 | `[현재 작업]` 꼬리에 `_WORKER_SCOPE_REMINDER` 1줄 (`workflow_compiler.py`) | 실런 3차 `59d25d9d`: 워커가 능력 질문에 답하지 않음 → 되물음 미발동(supervisor 2회). **FR-01 런타임 충족** |
| Gap-03 | `finish_challenge_kind` 채널 + `_render_challenge_reentry_block` — 재진입에 사유별 리마인더, kind `"reentry"`는 pending을 세우지 않음 | `TestChallengeReentryReminder` 7건. 1회 상한 불변(통합 테스트 3회 호출 유지) |
| Gap-04 | `_render_denial_notice(…, worker_descriptions)` — 발동 시에만 등록 워커 목록을 근거로 실음. `_create_final_answer_node` kwarg | `TestNoticeGroundedInWorkerList` 2건 |
| Gap-05 | FR-11 로그를 `_select_guidance_block`으로 이동, `_challenge_reset()` 헬퍼로 조기 return 5곳 축약 | `supervisor_node` 182 → **167줄** (원 carry 145줄보다 여전히 김 — backlog 유지) |
| Gap-06 | Design v0.2: §2.2·§4.1·§4.3·§4.4·§6.2 Q1·§11.1 갱신 | 문서 |
| Gap-07 | 블록 내 사유 60자 절단 | `TestBlockLengthWorstCase` (120자 사유에서 ≤400) |
| Gap-08 | 이벤트명 `finish challenge armed` / `consumed` 분리 | `test_arm_log_event_name`, `test_reentry_logs_consumed`. request_id는 LogContext 암묵 주입 그대로 |
| Gap-09 | `_select_guidance_block`, `_render_*_block`, `_with_denial_signal`, `_render_denial_notice` 타입힌트 | 코드 |
| Gap-10 | `route_to_worker_or_final` 주석에 합산 의미 반영 | 코드 |
| Gap-11 | `TestAllWorkerNodesWrapped` — 컴파일 시 워커 수만큼 데코레이터 적용 | 통합 테스트 1건 |

### 13.2 실런 3차 (`59d25d9d-3431-471c-ad45-194462a22a96`)

| 단계 | 관측 |
|------|------|
| 워커 | 목록 50건 반환, **능력 부정 문구 없음** (Gap-02 효과) |
| supervisor #2 | "본문을 읽으려면 get_inquiry_worker를 문의별로 호출… 건별 조회 가능하지만 아직 호출하지 않았음을 설명" → FINISH (올바른 판단) |
| final_answer | "고객 개인정보 보호를 위해 문의 원문(본문)은 도구에서 제공되지 않으며… get_inquiry 도구 역시 메타 정보 조회용" — **틀림**. 워커 산출에 부정이 없어 주의 블록 미발동, 근거는 에이전트 지침 Tool Guidelines("원문을 확인할 수 없다")뿐 |

세 런의 실패 지점이 워커(1차) → supervisor 재진입(2차) → final_answer 단독(3차)으로 **상류에서 하류로 밀려났다**. 코드 가드가 각 단계를 순서대로 막았고, 마지막 남은 오염원은 코드가 신뢰 입력으로 받는 데이터(에이전트 프롬프트·도구 description)다.

### 13.3 Match Rate 재산정

| 축 | Before | After | 근거 |
|---|:-:|:-:|---|
| Structural | 100% | 100% | Design v0.2 §4.1 18항목 전부 구현 |
| Functional | 91.7% | 95.8% | FR-01 런타임 충족(실런 3차). FR-10 결과만 부분 |
| Contract | 97% | 100% | 블록 길이 최악 케이스 고정, Design 문구 동기화 |
| Runtime | 62.5% | 66.7% | 메커니즘 4/4 + FR-01 1/1 + 사용자 결과 0/3 → 6/9 |
| **정적 공식** | 95.5% | **98.3%** | |
| **런타임 가중** | 84.0% | **87.3%** | 목표 90% 미달 — 잔여 격차는 전부 Gap-01(데이터) |

회귀: `uv run python -m pytest tests/application tests/domain tests/unit` → **6418 passed**.

### 13.4 남은 항목

- **Gap-01**: `list_inquiries` description("**연락처** 원문은…")과 에이전트 `e557f77e…` Tool Guidelines("개인정보 원문") 수정 후 `real_run.py` 재실행. 이 두 곳을 고치지 않으면 어떤 코드 가드도 final_answer의 마지막 문장을 바꾸지 못한다.
- backlog: supervisor의 올바른 FINISH 판단(reasoning/answer)이 DQ1로 폐기되어 final_answer에 닿지 않는 구조 — final-answer-node 설계 재검토(별도 피처). `supervisor_node` 40줄 규칙(carry).
