---
template: analysis
version: 1.3
feature: intent-slot-elicitation
plan: docs/01-plan/features/intent-slot-elicitation.plan.md
design: docs/02-design/features/intent-slot-elicitation.design.md
---

# intent-slot-elicitation Gap Analysis

> **Date**: 2026-08-16
> **Analyst**: 배상규 (tkdrb136@gmail.com)
> **Overall Match Rate**: **99%** (정적) → **Act-1·Act-2 반영 후 재판정 §10**
> **Verdict**: 정적 분석 Critical 0건 → **실 LLM 검증(M5)에서 Critical 2건 발견·수정**

> ⚠️ **이 문서는 2단계로 쓰였다.** §1~§9 는 정적 분석 결과(Match Rate 99%)이고,
> **§10 이 실 LLM 검증에서 드러난 것**이다. 정적으로는 완벽에 가까웠던 기능이
> 실 LLM 에서는 **100% 실패**하고 있었다. 두 결과를 모두 남겨 둔다 —
> "테스트가 다 통과했다"가 무엇을 보장하지 못하는지가 이 사이클의 핵심 교훈이다.

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 채팅형 에이전트 생성에서 되묻기 질문이 체계 없이 LLM 재량으로 생성되어 재현성이 없고, 파악된 의도가 구조화 객체로 남지 않는다 |
| **WHO** | P2(에이전트 소유자). 1차 소비자는 다음 사이클의 `AgentPlanner` |
| **RISK** | ① `slots` 타입 승격 = 계약 변경 ② 축 목록 프롬프트 ↔ 위키 계약 2 ③ 무한 되묻기 |
| **SUCCESS** | 미충족 축에 맥락 기반 선택지 + 되먹임 1라운드로 `complete=True` · LLM 실패 3종 degraded · `intent` 모듈 한정 변경 |
| **SCOPE** | 모듈 + 독립 API까지. AgentPlanner·프론트 = 다음 사이클 |

---

## 0. 분석 방법 고지

본 분석은 **gap-detector 에이전트를 호출하지 않고 직접 수행**했다. Plan·Design·구현이 모두 동일 세션 산출물이라 컨텍스트가 이미 적재되어 있고, 에이전트를 띄우면 같은 파일을 다시 읽는 비용만 든다.

대신 **기억이 아니라 코드로 대조**했다 — 아래 결론은 전부 실행 가능한 명령의 출력에 근거한다.

| 검증 수단 | 대상 |
|-----------|------|
| `grep` / AST 스캔 | 필드·validator·로그 필드 존재, 함수 길이, if 중첩, 도메인 어휘 침투 |
| `pytest` | 시나리오 S1~S41 실행 |
| `git diff --name-only` | 변경 범위 봉쇄(A4~A6) |
| `git stash` 전후 비교 | 기존 실패와 신규 실패 분리 |

---

## 1. Strategic Alignment Check

| 질문 | 판정 | 근거 |
|------|:----:|------|
| PRD의 핵심 문제를 다뤘는가 | — | PRD 없음 (`/pdca pm` 미수행). Plan이 최상위 문서 |
| Plan의 WHY를 코드가 실현하는가 | ⚠️ **부분 (설계된 대로)** | 되묻기가 `SlotSpec.required` 미충족의 함수가 되었다는 점은 실현. 다만 **소비자가 없어 사용자에게 도달하지 않는다** — Plan D8/§2.2가 명시적으로 이번 사이클 밖으로 뺀 범위이므로 미달이 아니다 |
| Plan Success Criteria 충족 | ✅ | §2 참조 (11/11) |
| Design 핵심 결정 준수 | ⚠️ **1건 이탈** | Option C의 *목적*(시스템 필드 격리)은 준수, *배치*는 이탈 (§4 G1) |

> **주의**: "WHY가 사용자에게 도달하지 않음"은 이번 사이클을 감점할 사유가 아니지만, **다음 사이클을 열지 않으면 이 작업의 가치가 0으로 남는다**. Plan R6이 지목한 위험이 그대로 살아 있다.

---

## 2. Plan Success Criteria

### 2.1 Definition of Done (Plan §4.1)

| # | 기준 | 판정 | 근거 |
|---|------|:----:|------|
| 1 | FR-01 ~ FR-16 전부 구현 | ✅ | §3 요구사항 대조표 |
| 2 | `pytest` 전체 스위트 통과 (기존 테스트 실패 0건) | ✅ | 58 failed / 7155 passed — 58건은 전부 기존 실패. `git stash` 전후 동일 파일집합 53=53으로 확인 |
| 3 | `planner.py`/`compose_agent_use_case.py`/`supervisor_nodes.py`/`general_chat/` 변경 0건 | ✅ | `git diff --name-only -- src/application/agent_composer/` 결과 없음 |
| 4 | `db/migration/` 신규 0건 | ✅ | `git status --porcelain db/migration/` = 0 |
| 5 | `idt_front/` 변경 0건 | ✅ | `git diff --stat -- idt_front/src` 결과 없음 |
| 6 | `/verify-architecture`·`/verify-logging`·`/verify-tdd` | ⚠️ **대체 검증** | 스킬 미실행. 동등 검증을 A1~A6 + ruff + TDD 순서 준수로 수행 (§5 M4) |
| 7 | 수동 시나리오 1회 (실 LLM) | ❌ **미수행** | `OPENAI_API_KEY` 실호출 필요. §5 M5 |

**6/7 충족 + 1 대체 + 1 미수행**

### 2.2 Quality Criteria (Plan §4.2)

| # | 기준 | 판정 | 근거 |
|---|------|:----:|------|
| 1 | `IntentResultPolicy` 분기 커버리지 100% | ✅ | `test_policies.py` 43건이 I1~I7 전 분기 커버 |
| 2 | 구형/신형 `slots` 두 입력 모두 동작 | ✅ | `test_str_slots_are_promoted_to_slot_spec`, `test_slot_spec_slots_pass_through`, `test_mixed_str_and_slot_spec_are_both_accepted` |
| 3 | spec 밖 슬롯 키 제거 | ✅ | `test_s1_unknown_slot_key_is_dropped` |
| 4 | 사용자 `answers`가 LLM 값 덮어씀 | ✅ | `test_s9_answer_overrides_llm_extraction` + 어댑터 종단 `test_answers_override_llm_extraction_end_to_end` |
| 5 | 라운드 상한 시 `questions == []` | ✅ | `test_s15_questions_are_forced_empty_at_round_cap`, `test_round_cap_hard_blocks_questions_regardless_of_prompt` |
| 6 | LLM 실패 3종 degraded | ✅ | `test_s25`(예외) / `test_s26`(타임아웃) / `test_s27`(스키마 위반) |
| 7 | API 200/401/422 | ✅ | `test_s40` / `test_s35` / `test_s36~s39` |
| 8 | 함수 40줄 이내, if 중첩 2단계 이내 | ✅ | AST 스캔 — 초과 함수 0건, 중첩 3단계 이상 0건 |

**8/8 충족**

---

## 3. 요구사항 대조 (FR-01 ~ FR-16)

| ID | 판정 | 구현 위치 | 비고 |
|----|:----:|-----------|------|
| FR-01 | ✅ | `schemas.py:47` `SlotSpec` | 5개 필드 전부 일치. `description` `min_length=1` |
| FR-02 | ✅ | `schemas.py:135` `_promote_str_slots` | `mode="before"` validator |
| FR-03 | ✅ | `schemas.py` `IntentResult.filled_slots` | `entities` **완전 제거**, 별칭 없음 (사용자 확정) |
| FR-04 | ✅ | `IntentDraft.suggestions` + 어댑터 프롬프트 | LLM 동적 생성. `SlotSpec.options`는 `(예: ...)` 힌트로만 |
| FR-05 | ✅ | `policies.py:167` `_resolve_questions` | 미충족 축에 한정 (I3) |
| FR-06 | ✅ | `policies.py` `_resolve_complete` | Policy 계산, `IntentDraft`에 필드 없음 |
| FR-07 | ✅ | `interfaces.py:22` | `answers` + `round_` 추가, stateless 계약 docstring 명시 |
| FR-08 | ✅ | `policies.py` `_merge_answers` | 사용자 답변 우선 |
| FR-09 | ✅ | `policies.py` 순수함수 9개 | ①~⑥ 전부 + 중복 질문 dedupe 추가 |
| FR-10 | ⚠️ **문언 이탈** | `policies.py:178` | §4 G3 참조 — 동작 동등, 구현 방식만 다름 |
| FR-11 | ✅ | `adapter.py` `_degrade` | 예외/타임아웃/스키마위반 3종 |
| FR-12 | ✅ | `schemas/intent.py`, `intent_router.py` | 요청 `answers`/`round`, 응답 확장 4필드 |
| FR-13 | ✅ | `build_slots.py` | 5축, required 3개 |
| FR-14 | ✅ | `intent_config.py` | env 3개 + `slot_limits()` |
| FR-15 | ✅ | `adapter.py:173-177` | 5개 필드 추가, 슬롯 **값**은 미기록 |
| FR-16 | ✅ | `schemas.py:148` | labels 또는 slots 조건부 |

**15 완전 충족 / 1 문언 이탈 (동작 동등)**

---

## 4. Gap 목록

### G1 — `_IntentLLMOutput` 미존재, `IntentDraft`로 domain 배치 [Minor · 의도적]

| 항목 | 내용 |
|------|------|
| **Design** | §3.1 — `_IntentLLMOutput` / `_SlotQuestionOut` 를 `adapter.py`에 모듈 프라이빗으로 |
| **구현** | `schemas.py` — `IntentDraft` / `SlotQuestionDraft` 공개 도메인 VO |
| **이유** | Design대로면 domain의 `normalize()`가 infrastructure 타입을 인자로 받아 **의존 방향이 뒤집힌다**. LLM 채움 필드만 가진 도메인 VO로 두면 §2.4의 목적(시스템 필드 격리)을 동일하게 달성하면서 레이어를 지킨다 |
| **기록** | `schemas.py` 모듈 docstring에 "Design 이탈" 명시 |
| **부수 이득** | `allow_free_text`를 LLM이 아니라 `SlotSpec`에서 채우게 되어 불변식 1개 추가 (`test_allow_free_text_comes_from_spec_not_llm`) |
| **조치** | Design 문서 §3.1 갱신 필요 (코드가 진실) |

### G2 — Design §9.3 "File Import Rules"가 무효화됨 [Minor]

Design §9.3은 `_IntentLLMOutput`을 언더스코어 접두 + `__all__` 미노출로 막는다고 규정했으나, G1로 그 클래스가 사라져 **규칙 자체가 적용 대상을 잃었다.** 코드에는 문제가 없고 문서만 남은 상태다.

`IntentDraft`는 공개 도메인 VO이므로 다른 레이어가 import해도 정상이다 — 어댑터가 `with_structured_output(IntentDraft)`로 쓰고, Policy가 인자로 받는 것이 설계된 흐름이다.

**조치**: Design §9.3을 "LLM 채움 필드와 시스템 계산 필드를 타입으로 분리한다"로 갱신.

### G3 — FR-10 "서버가 round를 clamp" 문언 불일치 [Minor]

| 항목 | 내용 |
|------|------|
| **Plan FR-10** | "요청의 `round`를 서버가 clamp하고, 상한 도달 시 `questions`를 빈 배열로 강제" |
| **구현** | clamp 함수 없음. ① 스키마 `ge=0`으로 음수 422 거부 ② `_resolve_questions`가 `round_ >= max_rounds` 비교로 차단 |
| **영향** | **없음.** clamp의 목적은 "상한 넘는 값이 질문을 만들지 못하게"인데 비교가 그것을 그대로 달성한다. `round=99`도 `questions == []` (`test_questions_empty_beyond_round_cap`) |
| **차이** | 응답에 clamp된 round를 되돌려주지 않는다. 다만 응답 스키마에 `round`가 없으므로 관측 가능한 차이가 아니다 |
| **조치** | 불필요. Plan 문언을 코드에 맞춰 읽으면 된다 |

### G4 — 테스트 명명 규칙 부분 미적용 [Minor · 추적성]

`sNN` 접두가 붙지 않은 시나리오 9건: **S18~S24**(`test_schemas.py`), **S32**(`test_build_slots.py`), **S33**(router happy path).

**내용은 전부 커버되어 있다** — 예: S18 → `test_str_slots_are_promoted_to_slot_spec`, S23 → `test_empty_labels_and_empty_slots_is_rejected`, S32 → `test_preset_declares_the_five_axes` 외 8건.

영향은 "Design 시나리오 번호로 grep이 안 된다"뿐이다.

### G5 — `domain/intent` docstring에 도메인 어휘 2줄 [Info · 의도적 유지]

A1 검증(`grep`)에 2건이 걸린다.

| 위치 | 내용 |
|------|------|
| `schemas.py:105` | "기본값은 agent_composer 의 `PlannerPolicy` 와 맞춰…" |
| `schemas.py:119` | "슬롯만: slots ≥ 1 ← 에이전트 생성이 쓰는 형태" |

**AST로 docstring을 제외한 코드 레벨 스캔은 0건**이다. import·상수·분기 어디에도 결합이 없으므로 A1/A3의 목적(의미 침투 차단)은 달성됐다. 문구를 지우면 "왜 이 기본값인가"라는 근거가 사라지므로 사용자 판단으로 유지했다.

---

## 5. 미충족 항목

### M4 — verify 스킬 3종 미실행 [Minor]

`/verify-architecture`·`/verify-logging`·`/verify-tdd`를 호출하지 않고 동등 검증으로 대체했다.

| 스킬 | 대체 수단 | 결과 |
|------|-----------|------|
| verify-architecture | A1~A3 (grep + AST 스캔) + 의존 방향 수동 확인 | 통과 |
| verify-logging | `logger.error(..., exception=e)` 단언 테스트 + PII 미유출 테스트 | 통과 |
| verify-tdd | 각 모듈 Red 확인 → 구현 → Green 순서 준수 (module-1,2에서 collection error로 Red 확인) | 통과 |

### M5 — 실 LLM 수동 시나리오 미수행 [Minor · 잔여 리스크]

Plan §4.1 #7의 "데이터 분석 에이전트 만들어줘 → 맥락 기반 선택지 → 답변 되먹임 → `complete=True`"를 **실제 LLM으로 돌려보지 않았다.**

테스트는 전부 fake chain이므로 다음이 미검증으로 남는다.

1. **`with_structured_output(IntentDraft)`가 실제로 통하는가** — 중첩 리스트(`questions: list[SlotQuestionDraft]`) + `dict[str, list[str]]`(`suggestions`) 조합을 `gpt-4o-mini`가 안정적으로 채우는지
2. **선택지 품질** — Plan R4가 지목한 "요청과 무관한 추천"이 실제로 나오는지
3. **R2 과차단** — 축 목록 프레이밍이 실제 응답을 왜곡하는지

**이것이 이번 사이클의 가장 큰 잔여 불확실성이다.** Design §11.4가 다음 사이클 진입 조건으로 "실 요청 10건 R2 재평가"를 걸어 둔 것과 같은 항목이며, 배선 전에 반드시 해소해야 한다.

---

## 6. Match Rate

| 축 | 비율 | 산출 근거 |
|----|-----:|-----------|
| **Structural** | 95% | Design §11.1 파일 17개(소스 10 + 테스트 7) 전부 존재. 명명된 클래스 2개(`_IntentLLMOutput`/`_SlotQuestionOut`) 미존재 — G1 이탈분 차감 |
| **Functional** | 98% | FR-01~16 중 15 완전 충족 + FR-10 문언 이탈(동작 동등). 불변식 I1~I7 전부 테스트로 잠김. 플레이스홀더 0건 |
| **Contract** | 100% | Design §4.2 요청 5필드 / 응답 10필드가 스키마·라우터·테스트 3자 일치. `test_response_contains_every_contract_field`가 필드 집합을 정확히 단언 |
| **Runtime** | 100% | 152건(intent 143 + preset 9) 전부 green. L1 시나리오 S33~S41이 FastAPI `TestClient`로 실행됨 |

```
Overall = (95 × 0.15) + (98 × 0.25) + (100 × 0.25) + (100 × 0.35)
        = 14.25 + 24.50 + 25.00 + 35.00
        = 98.75  →  99%
```

> **Runtime 판정의 한계**: `TestClient`는 in-process이며 **live 서버도 실 LLM도 아니다.** API 계약·직렬화·검증·인증 경로는 실제로 실행되지만, LLM structured output의 실동작은 이 수치에 포함되지 않는다 (M5).

---

## 7. Decision Record 준수 검증

| ID | 결정 | 준수 | 근거 |
|----|------|:----:|------|
| Plan D1 | 슬롯 1급 승격 (포트 단일 유지) | ✅ | `analyze()` 하나로 분류+슬롯 처리 |
| Plan D2 | 축 프리셋은 `agent_composer` | ✅ | `build_slots.py`. domain 코드에 어휘 0건 |
| Plan D3 | 추천 선택지 LLM 동적 생성 | ✅ | `IntentDraft.suggestions`, `options`는 힌트로만 |
| Plan D4 | 왕복 stateless (요청 에코백) | ✅ | `test_use_case_holds_no_round_state_between_calls` |
| Plan D5 | `complete`는 Policy 계산 | ✅ | `IntentDraft`에 필드 없음 |
| Plan D6 | 사용자 답변 우선 | ✅ | `_merge_answers` + 종단 테스트 |
| Plan D7 | 실패 시 degraded 유지 | ✅ | 3종 테스트 |
| Plan D8 | 모듈 + 독립 API까지만 | ✅ | `agent_composer/planner.py` diff 0건 |
| Plan D9 | `entities` 대체 | ✅ | `test_s41_entities_field_is_gone` |
| Design Option C | LLM 스키마 분리 | ⚠️ | 목적 준수, 배치 이탈 (G1) |
| Design C5 | 프롬프트 소프트 + Policy 하드 | ✅ | `test_round_cap_hard_blocks_questions_regardless_of_prompt` |

**10/11 준수 + 1 문서화된 이탈**

---

## 8. 회귀 검증 (A1~A6)

| # | 검증 | 결과 | 수단 |
|---|------|:----:|------|
| A1 | `domain/intent` 도메인 어휘 0건 | ⚠️→✅ | grep 2건(docstring) / **AST 코드레벨 0건** |
| A2 | `domain/intent` → infra·LangChain import 0건 | ✅ | import는 `abc`/`typing`/`pydantic`/자기 모듈뿐 |
| A3 | `domain/intent` → `agent_composer` 역참조 0건 | ✅ | 코드레벨 0건 (docstring 1건) |
| A4 | `agent_composer` 소스 무변경 | ✅ | `git diff --name-only` 결과 없음 |
| A5 | `db/migration/` 신규 0건 | ✅ | `git status --porcelain` = 0 |
| A6 | `idt_front/` 변경 0건 | ✅ | `git diff --stat` 결과 없음 |

**기존 실패 분리 검증**: 동일 파일집합을 변경 전(`git stash`)과 후로 각각 실행해 **53 = 53**으로 일치 확인. 전체 스위트 58 failed는 `pymupdf4llm`·`parent_child_retriever`·`agent_builder_router_stream` 등 intent와 무관한 기존 실패다.

---

## 9. 권고

| 우선순위 | 항목 | 근거 |
|:--------:|------|------|
| **1** | **실 LLM 수동 시나리오 1회** (M5) | 이번 사이클 최대 잔여 불확실성. `with_structured_output(IntentDraft)` 실동작 + 선택지 품질 + R2 과차단을 한 번에 본다. **다음 사이클 진입 조건** |
| 2 | Design §3.1·§9.3을 코드에 맞춰 갱신 (G1·G2) | SoT 규칙 — 코드가 진실. 문서만 어긋난 상태 |
| 3 | `sNN` 태그 9건 보강 (G4) | 추적성. 선택 사항 |
| — | G3·G5 | 조치 불필요 (동작 동등 / 의도적 유지) |

---

---

## 10. 실 LLM 검증 (M5) — Critical 2건 발견 및 수정

§9에서 1순위로 권고한 M5를 수행했고, **정적 분석이 잡지 못한 Critical 결함 2건**이 나왔다.

### 10.1 C1 — 자유 키 dict 가 structured output 을 무효화 [Critical · 수정 완료]

```
openai.BadRequestError: 400 — Invalid schema for response_format 'IntentDraft':
'required' is required to be supplied and to be an array including every key in properties.
```

OpenAI structured outputs 의 strict 모드는 **자유 키 dict(`dict[str, X]`)를 거부**한다.
`IntentDraft.filled_slots: dict[str,str]` 와 `suggestions: dict[str,list[str]]` 가 스키마 전체를
무효화해, 실 LLM 호출이 **매번 400 → `degraded=True`** 로 떨어졌다.

**이것은 이번 사이클의 회귀가 아니다.** 선행 사이클의 `IntentResult(entities: dict[str,str])` 도
동일하게 400 임을 실측으로 확인했다.

| 실험 | 결과 |
|------|------|
| 선행 `IntentResult` (entities: dict) / 기본 method | ❌ 400 |
| 현행 `IntentDraft` (dict) / 기본 method | ❌ 400 |
| 현행 `IntentDraft` (dict) / `method="function_calling"` | ⚠️ 통과하나 `suggestions={}`·`questions=[]` — 되묻기 미작동 |
| **list 기반 스키마 / 기본 method** | ✅ 통과 + 되묻기 정상 |

> **`intent-analyzer` 모듈은 출시 이후 실 LLM 에서 한 번도 동작한 적이 없다.**
> 미배선(Plan D8)이라 아무도 쓰지 않았고, 어댑터가 모든 실패를 `degraded` 로 삼키는
> 계약이 그 사실을 가려 왔다. 폴백 설계는 의도대로 작동했지만 **동시에 결함을 은폐했다.**
> 이것이 "미배선 모듈도 실호출 1회는 해야 한다"의 근거다.

**조치 (Act-1)**: `IntentDraft` 만 배열 기반으로 전환.

| 변경 | 내용 |
|------|------|
| `schemas.py` | `SlotValue(key, value)` · `SlotSuggestion(key, options)` 신설. `IntentDraft.filled_slots: list[SlotValue]`, `suggestions: list[SlotSuggestion]` |
| `schemas.py` | `mode="before"` validator 2개 — dict 로 오는 구현체도 수용(입력 관용). **출력 스키마는 언제나 배열**이므로 strict 호환성이 되돌아가지 않는다 |
| `policies.py` | `_filter_filled`·`_filter_suggestions` 가 배열을 받아 도메인 표현인 dict 로 접는다 |

**도메인 VO(`IntentResult.filled_slots: dict`)와 API 응답 계약은 무변경** — `IntentDraft` 를
분리해 둔 덕에 라우터 테스트 30건과 Design §4.2 가 그대로 유지됐다.

**회귀 방어**: `test_intent_draft_schema_has_no_free_key_dict` 가 스키마를 재귀 탐색해
`additionalProperties` 가 스키마인 object 를 0건으로 강제한다. 같은 결함이 재발할 수 없다.

### 10.2 C2 — `question.options` 가 빔 [Critical · 수정 완료]

```
questions:
    [domain_detail] 어떤 종류의 데이터 분석을 원하시나요? (예: 요약 통계, 추세 분석 등)
        options=[]          ← 비어 있음
suggestions:
    domain_detail: ['요약 통계', '추세 분석', '이상 탐지', '비교 분석']   ← 여긴 있음
```

LLM 이 선택지를 `options` 배열 대신 **질문 문장 안에 녹였다.** 화면이 선택 버튼을 만들 수 없다.

**조치 (Act-2 D1)**: `_to_question` 이 `draft.options or suggestions[slot_key]` 로 폴백.
프롬프트에도 "options 배열을 반드시 채우세요 / 질문 문장 안에 적지 말고" 를 추가해 **이중 방어**.

### 10.3 C3 — 과충전(confabulation) 이 되묻기를 무력화 [Critical · 부분 해소]

LLM 이 사용자가 말하지 않은 축까지 지어내 `missing_slots=[]` → `questions=[]` 가 되었다.
**어조·출력형식을 물어보려고 만든 모듈인데 LLM 이 멋대로 정해버려 HITL 이 발동하지 않는다.**
심지어 `reason` 에 "구체적인 세부사항이 부족함" 이라고 쓰면서 5축을 다 채웠다.

**조치 (Act-2 D2)**: 프롬프트에서 **비우는 쪽을 기본값으로 뒤집었다.**

| 이전 | 이후 |
|------|------|
| "확실히 알 수 있는 항목만 채우세요. 추측하거나 지어내지 마세요." | "**비워 두는 것이 기본입니다.** 사용자가 직접 말한 항목만…" + "짐작해서 채우면 **사용자에게 물어볼 기회가 사라집니다**" + 대조 예시 + "항목 대부분이 비어 있는 것이 정상입니다" |

**수정 전후 실측 (동일 3개 프로브)**

| 프로브 | 수정 전 | 수정 후 |
|--------|---------|---------|
| P1 "데이터 분석 에이전트" | filled 1, 질문 1 (options 없음) | filled 1, **질문 3 (options 전부 채워짐)** ✅ |
| P2 "사내 규정 문서 QA" | **filled 5, missing 0, 질문 0** ❌ | filled 2, missing 3, **질문 3 + options** ✅ |
| P3 "슬랙 아침 인사" | **filled 5, missing 0, 질문 0** ❌ | **filled 5, missing 0, 질문 0** ⚠️ 잔존 |

**P3 는 여전히 과충전한다** — `data_source="슬랙 API"`, `output_format="슬랙 메시지"` 는
추론으로 자연스럽지만 `tone="친근한 설명형"` 은 순수 confabulation 이다.

> **프롬프트로는 완전 해소가 불가능하다.** 3개 프로브 중 2개가 정상화된 것이 현재 도달점이며,
> 결정론적 보장을 원하면 계약을 늘려야 한다(예: "optional 축은 LLM 이 채워도 사용자 확인
> 전까지 미확정"). 이번 사이클에서는 채택하지 않았다 — 판정은 **조언 전용**(Plan D5)이고,
> 배선 시점의 화면이 "AI 가 이렇게 이해했어요, 수정하시겠어요?" 로 흡수할 수 있기 때문이다.
> **다음 사이클에서 이 판단을 재검토해야 한다.**

### 10.4 맥락 적응 확인 (Plan R4)

동일 축 `domain_detail` 의 추천이 요청에 따라 달라진다 — R4 우려는 해소.

| 요청 | `domain_detail` 추천 |
|------|---------------------|
| 데이터 분석 에이전트 | 요약 통계 / 추세 분석 / 이상 탐지 / 비교 분석 |
| 사내 규정 문서 QA | 인사 규정 / 재무 규정 / 안전 규정 / 기타 |

### 10.5 R2(위키 계약 2 · 과차단) 실측 — 해소

P3 "슬랙으로 매일 아침 인사 메시지" 는 축 목록이 상정하지 않은 요청이다.
결과는 `degraded=False`, `task` 정상 추출, 거절·왜곡 **없음**. §4.3 의 4겹 방어가 실제로 작동했다.

이로써 Design §11.4 의 다음 사이클 진입 조건 중 **"R2 실측 재평가"가 충족**됐다.

### 10.6 하네스 판정 기준 오류 2건 (참고)

자동 판정 중 2개가 잘못된 기준이었다. 결과 해석 시 주의.

| 항목 | 판정 | 실제 |
|------|:----:|------|
| "라운드 1 에 질문 없음" | False | **정상 동작.** `tone` 은 optional 이라 `complete=True` 이면서도 미충족 — 마저 묻는 것이 맞다 |
| "P2 data_source 추천이 r0 와 다름" | False | **비교 대상 오류.** 둘 다 `suggestions` 가 비어 `{} == {}`. 실제 선택지는 `questions[].options` 에 있고 맥락별로 다르다 (§10.4) |

### 10.7 잔여 관찰 — `suggestions` 가 비는 경향 [Minor]

D2 이후 LLM 이 `questions[].options` 만 채우고 `suggestions` 를 생략하는 경향이 생겼다.
질문 상한(3) 안의 축은 `options` 로 전달되므로 화면은 정상 동작하지만, **상한 밖 축의 선택지를
API 소비자가 볼 수 없다.** 기능 차단은 아니며 다음 사이클 화면 작업에서 필요 여부를 판단한다.

### 10.8 Act 후 최종 상태

| 항목 | 결과 |
|------|------|
| intent + composer 스위트 | **222 passed** |
| 전체 스위트 | 58 failed / **7228 passed** — 58건은 전부 기존 실패 |
| ruff | All checks passed |
| 실 LLM 왕복 | ✅ 라운드 0 질문 3개(options 포함) → 답변 되먹임 → `complete=True` |
| Plan §4.1 #7 (수동 시나리오) | ✅ **충족** — M5 해소 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-08-16 | 정적 Gap 분석 — Match Rate 99%, Critical 0 / Important 0 / Minor 4 / Info 1 | 배상규 |
| 0.2 | 2026-08-16 | §10 추가 — 실 LLM 검증(M5)에서 Critical 3건 발견. C1·C2 수정 완료, C3 부분 해소. Plan §4.1 #7 충족 | 배상규 |
