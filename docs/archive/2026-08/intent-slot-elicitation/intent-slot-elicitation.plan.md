---
template: plan
version: 1.3
feature: intent-slot-elicitation
---

# intent-slot-elicitation Planning Document

> **Summary**: `domain/intent` 모듈의 `slots: list[str]`을 **`SlotSpec` 1급 객체**로 승격해, 의도 판정이 "라벨 1개 고르기"에서 "여러 축(어조·작업·도메인·데이터소스·출력형식)을 값으로 채우고, 못 채운 축은 **LLM이 맥락에 맞춰 만든 추천 선택지와 함께 되묻는**" 것까지 하도록 확장한다. 에이전트 생성용 축 프리셋은 `agent_composer` 쪽에 두어 모듈의 범용성을 지킨다. 이번 사이클은 **모듈 + 독립 API까지**, AgentPlanner 배선과 화면은 다음 사이클.
>
> **Project**: sangplusbot (idt — 백엔드)
> **Author**: 배상규 (tkdrb136@gmail.com)
> **Date**: 2026-08-14
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 채팅으로 에이전트를 만들 때("데이터 분석해주는 에이전트 만들어줘") 실제로 초안 품질을 가르는 정보는 **어떤 어조로 답할지 / 무슨 데이터를 / 어떻게 분석해 / 어떤 형태로 내놓을지**다. 지금 이걸 담당하는 `AgentPlanner`는 무엇을 물을지를 **LLM 자유재량**에 맡기고 있어 질문이 매번 달라지고, 파악된 내용은 `system_prompt` 문자열에 녹아 사라진다. 한편 `domain/intent`는 슬롯이 `list[str]` 키 목록뿐이라 "무엇을 물어야 하는지"를 표현할 수 없다. |
| **Solution** | `SlotSpec(key, description, options, allow_free_text, required)`를 도입해 **물어볼 축을 데이터로 선언**한다. 판정 결과는 `filled_slots`(채운 값) + `missing_slots`(못 채운 축) + `questions`(축별 되묻기 문안 + **LLM이 요청 맥락에 맞춰 생성한 추천 선택지**) + `complete`(required 충족 여부)로 확장한다. 답변을 `answers`로 되먹여 다음 라운드를 돌리는 **stateless 왕복 계약**을 포트에 명문화한다. |
| **Function/UX Effect** | 이번 사이클엔 화면 변화 **없음**(AgentPlanner 미배선). `POST /api/v1/intent/analyze`에서 축 기반 판정과 되묻기 왕복을 곧바로 검증할 수 있고, 다음 사이클에 Planner가 이 결과를 소비하면 "무엇을 물을지"가 재현 가능해진다. |
| **Core Value** | 되묻기가 **LLM의 기분**이 아니라 **선언된 축의 미충족**에서 나온다 — 같은 요청이면 같은 질문이 나오고, 축을 추가하면 질문도 따라 늘어난다. 그러면서도 축의 *의미*는 모듈 밖(`agent_composer` 프리셋)에 있어 모듈은 여전히 범용이다. |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 채팅형 에이전트 생성에서 되묻기 질문이 체계 없이 LLM 재량으로 생성되어 재현성이 없고, 파악된 의도가 구조화 객체로 남지 않는다 |
| **WHO** | P2(에이전트 소유자) — 채팅으로 에이전트를 만드는 사람. 1차 소비자는 다음 사이클의 `AgentPlanner`(개발자) |
| **RISK** | ① `slots: list[str]` → `SlotSpec` 은 **기존 계약 변경**(모듈이 미배선이라 실피해는 없으나 API 계약이 깨짐) ② 축 목록을 프롬프트에 넣는 일이 위키 계약 2(목록 프레이밍 과차단)와 다시 맞닿는다 ③ 다중 라운드 왕복이 무한 질문 루프가 될 수 있다 |
| **SUCCESS** | required 축 미충족 시 축별 질문 + 맥락 기반 추천 선택지 생성 · 답변 되먹임 1라운드로 `complete=True` 도달 · LLM 실패 3종 모두 `degraded=True` · 기존 파일 변경은 `intent` 모듈 + `api/main.py` 한정 |
| **SCOPE** | `domain/intent` 확장 + 어댑터/UseCase/API + `agent_composer` 축 프리셋 상수. **AgentPlanner 배선·compose 응답 계약·프론트 = 다음 사이클** |

---

## 1. Overview

### 1.1 Purpose

"어떤 에이전트를 만들고 싶은가"를 파악하는 일을, **선언된 축(슬롯)을 채우는 문제**로 재정의한다.
LLM은 두 가지를 한다 — ① 사용자 메시지에서 채울 수 있는 축을 채우고, ② **못 채운 축에 대해 이 요청 맥락에 맞는 추천 선택지를 만들어 되묻는다.**
사람은 선택지에서 고르거나 직접 입력한다(Human-in-the-Loop). 이 왕복이 required 축을 다 채울 때까지 반복된다.

### 1.2 Background

현재 코드 기준 사실관계(확인 완료):

| 위치 | 현재 하는 일 | 이번 작업과의 관계 |
|------|-------------|-------------------|
| `src/domain/intent/schemas.py` | `IntentSpec(labels, slots: list[str], allow_unknown)` / `IntentResult(label, confidence, entities, ambiguous, missing_slots, reason, degraded)` | **확장 대상.** 슬롯이 문자열 키뿐이라 "무엇을 물어야 하는지"·"어떤 선택지가 있는지"를 못 담는다 |
| `src/domain/intent/policies.py` | `IntentResultPolicy.normalize()` — 라벨 강등·confidence clamp·미지 슬롯 필터 | **확장 대상.** 슬롯 정규화가 `missing_slots` 필터 1줄뿐 |
| `src/infrastructure/intent/adapter.py` | `with_structured_output(IntentResult)` 1회 호출. `_slots_block()`이 슬롯 키를 나열 | **확장 대상.** 축 설명·선택지 힌트·이전 답변을 프롬프트에 실어야 함 |
| `src/application/intent/use_case.py` | 위임만 하는 얇은 UseCase | 시그니처에 `answers` 추가 |
| `src/api/routes/intent_router.py` | `POST /api/v1/intent/analyze` | 요청/응답 스키마 확장 |
| `src/application/agent_composer/planner.py` | 요청 → `BuildPlan` + `clarifying_questions`. **질문 내용이 LLM 자유재량**, 축 개념 없음 | **이번엔 무변경.** 다음 사이클의 1차 배선 지점 |
| `src/domain/agent_composer/policies.py` | `PlannerPolicy` — `CONFIDENCE_THRESHOLD=0.8`, `MAX_CLARIFICATION_ROUNDS=2`, `MAX_QUESTIONS_PER_ROUND=3` | **선례 재사용.** 라운드/질문 상한 관례를 intent 쪽에도 동일하게 적용 |

즉 되묻기 자체는 이미 `agent_composer`에 있으나 **체계(축)가 없고**, 체계를 담을 그릇인 `intent` 모듈은 **되묻기를 모른다.** 이번 작업은 그릇 쪽에 되묻기를 심고, 축의 의미는 밖에 남긴다.

### 1.3 Related Documents

- 선행 사이클: `docs/archive/2026-08/intent-analyzer/` (모듈 신설, D1~D8)
- 선행 사이클: `docs/archive/2026-08/agent-create-entry/` (진입 화면 + compose/HITL 왕복)
- **위키 계약 2**(목록 프레이밍 과차단, 커밋 08d37cab) — `docs/wiki/backend/patterns/supervisor-graph-contracts.md` ★ R2 근거
- 페르소나·스코프: `docs/USER-SCENARIOS.md` (P2 주인공, 일반화 > 특화)
- 코딩 규칙: `idt/CLAUDE.md`, `idt/docs/rules/logging.md`, `idt/docs/rules/testing.md`

---

## 2. Scope

### 2.1 In Scope

- [ ] `domain/intent/schemas.py` — `SlotSpec` 신설, `IntentSpec.slots: list[SlotSpec]`로 승격, `IntentResult`에 `filled_slots` / `suggestions` / `questions` / `complete` 추가
- [ ] `domain/intent/schemas.py` — `SlotQuestion(slot_key, question, options, allow_free_text)`, `SlotAnswer(slot_key, value)` VO
- [ ] `domain/intent/policies.py` — 슬롯 정규화 확장(미지 키 제거 / required 충족 판정 / 질문 상한 / 선택지 상한 / 답변 우선순위)
- [ ] `domain/intent/interfaces.py` — 포트 시그니처에 `answers: list[SlotAnswer] | None` 추가 (stateless 왕복)
- [ ] `infrastructure/intent/adapter.py` — 축 블록·선택지 힌트·이전 답변 블록 프롬프트화, 확장 structured output
- [ ] `application/intent/use_case.py` · `node.py` — 인자 전달 (얇게 유지)
- [ ] `interfaces/schemas/intent.py` + `api/routes/intent_router.py` — 요청/응답 확장
- [ ] `application/agent_composer/` — **`AGENT_BUILD_SLOTS` 프리셋 상수 5축** 정의 (정의만, 소비는 다음 사이클)
- [ ] `infrastructure/config/intent_config.py` — 라운드/질문/선택지 상한 env 추가
- [ ] TDD: Policy 분기 100% + 어댑터 fake + UseCase + API 통합테스트 + 기존 intent 테스트 마이그레이션

### 2.2 Out of Scope

- **`AgentPlanner` 배선** — `planner.py` / `compose_agent_use_case.py` 무변경. compose 응답 계약(`ClarifyingQuestionDto` 등) 무변경.
- **프론트엔드 일체** — 화면단은 사용자가 별도로 재작업 예정. `idt_front/` 변경 0건, API 계약 동기화(루트 CLAUDE.md §4-1) 불필요.
- **의도 프로파일 저장** — 휘발성. `ai_agent` 컬럼 추가·DB 마이그레이션 0건. 왕복 상태는 요청에 실린 `answers` 에코백으로만 복원(stateless).
- **축의 DB 설정화·관리 UI** — 프리셋은 코드 상수.
- **기존 3개 판정 모듈(multi_query / chart_router / search_decision) 통합** — 무관.
- **축 프리셋을 `domain/intent` 안에 두는 것** — 모듈이 도메인 의미를 알게 되므로 금지(D2).

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | `SlotSpec(key, description, options: list[str] = [], allow_free_text: bool = True, required: bool = False)`를 `domain/intent/schemas.py`에 정의한다. `description`은 필수(빈 문자열 금지) — 축 설명이 곧 프롬프트 품질이다. | High | Pending |
| FR-02 | `IntentSpec.slots`를 `list[SlotSpec]`으로 승격한다. **하위호환**: `list[str]`로 들어오면 `SlotSpec(key=s, description=s)`로 자동 승격하는 validator를 둔다(기존 호출부·테스트 무파손). | High | Pending |
| FR-03 | `IntentResult`에 `filled_slots: dict[str, str]`(채운 축)를 추가한다. 기존 `entities`는 **`filled_slots`로 대체**하되, 응답 스키마에서 한 사이클간 별칭으로 함께 노출할지는 Design에서 확정한다. | High | Pending |
| FR-04 | `IntentResult.suggestions: dict[str, list[str]]` — 못 채운 축별 **추천 선택지**. **LLM이 사용자 요청 맥락에 맞춰 동적 생성**한다(D3). `SlotSpec.options`는 고정값이 아니라 프롬프트 힌트로만 쓴다. | High | Pending |
| FR-05 | `IntentResult.questions: list[SlotQuestion]` — 축별 되묻기 문안(한국어 1문장) + 해당 축의 `suggestions` + `allow_free_text`. 질문은 **required이면서 미충족인 축에 대해서만** 만든다. | High | Pending |
| FR-06 | `IntentResult.complete: bool` — `spec.slots` 중 `required=True`인 축이 모두 `filled_slots`에 있으면 `True`. **Policy가 계산**하며 LLM 출력을 신뢰하지 않는다. | High | Pending |
| FR-07 | 포트 시그니처를 `analyze(message, spec, history=None, answers: list[SlotAnswer] \| None = None, request_id="")`로 확장한다. `answers`가 있으면 프롬프트에 `[이전 답변]` 블록으로 실어 재판정한다. **모듈은 왕복 상태를 보유하지 않는다**(기존 D7 유지). | High | Pending |
| FR-08 | 답변 우선순위: 같은 축에 대해 `answers`에 값이 있으면 **LLM 추출값보다 사용자 답변이 이긴다**. Policy가 병합한다. | High | Pending |
| FR-09 | `IntentResultPolicy` 확장 — ① `spec.slots`에 없는 키는 `filled_slots`/`suggestions`/`questions`에서 제거 ② 이미 채워진 축의 질문 제거 ③ 질문 상한 clamp ④ 축당 선택지 상한 clamp ⑤ `complete` 재계산 ⑥ 빈 값(`""`) 슬롯은 미충족으로 취급. **전부 순수함수.** | High | Pending |
| FR-10 | 라운드 상한: 요청의 `round`를 서버가 clamp하고, 상한 도달 시 `questions`를 빈 배열로 강제해 무한 되묻기를 차단한다(`PlannerPolicy.clamp_round` 선례 미러링). | High | Pending |
| FR-11 | LLM 실패(예외 / 타임아웃 / 스키마 위반) 시 기존과 동일하게 `degraded=True` 반환. 확장 필드는 빈 값. **예외를 밖으로 던지지 않는다.** | High | Pending |
| FR-12 | `POST /api/v1/intent/analyze` 요청에 `slots`(SlotSpec 배열), `answers`, `round`를 받고 응답에 `filled_slots`/`suggestions`/`questions`/`complete`를 반환한다. | High | Pending |
| FR-13 | `AGENT_BUILD_SLOTS` 프리셋을 `application/agent_composer`에 정의한다 — **5축**: `tone`(답변 어조/페르소나), `task`(원하는 작업), `domain_detail`(작업 도메인 상세), `data_source`(데이터 소스·지식베이스), `output_format`(출력 형식/산출물). 각 축은 `description` 필수 + 대표 `options` 힌트 + `required` 지정. **이번 사이클엔 정의만 하고 배선하지 않는다.** | High | Pending |
| FR-14 | 라운드/질문/축당 선택지 상한과 모델·온도·타임아웃은 config로 주입한다. 하드코딩 금지. | Medium | Pending |
| FR-15 | 판정 1회마다 구조화 로그 1건에 `filled_count`, `missing_count`, `question_count`, `complete`, `round`를 추가한다. `print()` 금지. | Medium | Pending |
| FR-16 | `spec.labels`가 2개 미만이면 422(기존 FR-11 유지). **단 슬롯 전용 사용을 위해 `labels` 최소 개수 완화 여부는 Design에서 판단** — 에이전트 생성 맥락에선 분류 라벨이 불필요할 수 있다. | Medium | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 결합도 | `domain/intent`가 infrastructure·LangChain·DB를 import하지 않음. `domain/intent`에 에이전트 생성 도메인 어휘(어조·데이터소스 등) 상수 **0개** | `/verify-architecture` + grep |
| 하위호환 | `slots=["a","b"]` 형태의 기존 호출이 그대로 동작 | 기존 intent 테스트 무수정 통과 |
| 회귀 안전 | `agent_composer` / `general_chat` / supervisor 그래프 변경 0건 | `git diff --name-only` |
| 되묻기 종료성 | 라운드 상한 도달 시 `questions == []` 보장 | Policy 단위테스트 |
| 지연 | 판정 timeout 기본 10s 유지, 초과 시 degraded | 어댑터 타임아웃 fake |
| 관측성 | 실패 시 `logger.error(..., exception=e)` 스택 트레이스 | `/verify-logging` |
| 테스트 | `IntentResultPolicy` 분기 100% 커버 | pytest |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] FR-01 ~ FR-16 전부 구현
- [ ] `pytest` 전체 스위트 통과 (기존 테스트 실패 0건)
- [ ] `git diff --name-only`에 `planner.py` / `compose_agent_use_case.py` / `supervisor_nodes.py` / `general_chat/` **0건**
- [ ] `db/migration/` 신규 파일 **0건**, `idt_front/` 변경 **0건**
- [ ] `/verify-architecture` · `/verify-logging` · `/verify-tdd` 통과
- [ ] **수동 시나리오 1회 성공**: "데이터 분석해주는 에이전트 만들어줘" + `AGENT_BUILD_SLOTS` → required 미충족 축에 대해 **맥락에 맞는 추천 선택지**가 붙은 질문이 생성됨 → 답변을 `answers`로 되먹임 → `complete=True` 도달

### 4.2 Quality Criteria

- [ ] `IntentResultPolicy` 분기 커버리지 100% (순수함수)
- [ ] `slots=["a","b"]`(구형) / `slots=[SlotSpec(...)]`(신형) 두 입력 모두 동작하는 테스트 존재
- [ ] LLM이 spec에 없는 슬롯 키를 반환한 케이스 → 제거되는 테스트 존재
- [ ] 사용자 `answers`가 LLM 추출값을 덮어쓰는 테스트 존재 (FR-08)
- [ ] 라운드 상한 도달 시 `questions == []` 테스트 존재 (FR-10)
- [ ] LLM 실패 3종 각각 `degraded=True` 테스트 존재
- [ ] API 200 / 401 / 422 테스트 존재
- [ ] 모든 함수 40줄 이내, if 중첩 2단계 이내 (CLAUDE.md §3)

---

## 5. Risks and Mitigation

| ID | Risk | Impact | Likelihood | Mitigation |
|----|------|--------|------------|------------|
| R1 | **`slots: list[str]` → `list[SlotSpec]`은 계약 변경**이다. 모듈이 아직 미배선이라 런타임 피해는 없지만 `POST /api/v1/intent/analyze` 요청 스키마가 바뀐다. | Medium | High | FR-02의 **자동 승격 validator**로 구형 입력을 계속 받는다. 기존 테스트를 수정하지 않고 통과시키는 것을 DoD에 넣어 하위호환을 강제한다. |
| R2 | **위키 계약 2 재현 위험** — 축 목록 + 선택지 목록을 프롬프트에 넣는 일은 "할 수 있는 것 목록"을 주는 것과 구조가 같다. LLM이 목록 밖 요청을 과차단하거나, 사용자가 원하지 않는 선택지로 억지 수렴시킬 수 있다. | High | Medium | ① 선례대로 "이 목록은 권한이 아니라 분류표/힌트"를 프롬프트에 명시 ② **`allow_free_text` 기본 True**, 선택지는 항상 "예시"로 프레이밍 ③ 사용자 답변이 LLM 추출값을 이기는 규칙(FR-08)이 구조적 탈출구 ④ 판정 결과는 여전히 **조언 전용** — 아무것도 게이팅하지 않는다(기존 D5 유지). |
| R3 | **무한 되묻기 루프** — required 축을 사용자가 계속 안 채우면 질문이 끝없이 반복된다. | Medium | Medium | FR-10 라운드 상한 + 서버 clamp. `PlannerPolicy.MAX_CLARIFICATION_ROUNDS=2` 선례를 그대로 따라 기본값을 맞춘다. 상한 도달 시 `complete=False`인 채로 질문 없이 종료 → 호출자가 기본값 가정. |
| R4 | **LLM 동적 선택지의 품질 편차** — 요청이 모호하면 엉뚱한 추천이 나온다. | Medium | High | 축당 선택지 상한(3~4개) + `SlotSpec.options`를 힌트로 제공해 앵커링. `allow_free_text=True`로 항상 우회로 확보. 품질은 Design의 프롬프트 문안에서 다룬다. |
| R5 | **`entities` → `filled_slots` 개명이 이중 필드를 만든다** — 둘 다 남기면 어느 것이 진실인지 모호해진다. | Medium | Medium | Design에서 **하나로 확정**한다. 기본 방침: 도메인 VO는 `filled_slots` 단일 필드, API 응답에만 한시적 별칭. 별칭을 둔다면 제거 사이클을 Design에 명시. |
| R6 | **축 프리셋이 죽은 코드가 된다** — 이번 사이클엔 `AGENT_BUILD_SLOTS`를 아무도 소비하지 않는다. | Low | High | 의도된 것(사용자 확정 범위). 프리셋은 순수 데이터 + 단위테스트(키 중복 없음/description 비어있지 않음)로 유지비 최소화. **다음 사이클의 1차 배선 지점(`AgentPlanner`)을 Design에 명시**한다. |
| R7 | **비용·지연 증가** — 출력 스키마가 커지고 되묻기로 호출이 라운드마다 반복된다. | Medium | Medium | hot path 미배선이라 이번 사이클 실사용 비용 0. 경량 모델(`gpt-4o-mini` 기본) 유지 + 라운드 상한이 곧 호출 상한. |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `src/domain/intent/schemas.py` | 확장 | `SlotSpec`/`SlotQuestion`/`SlotAnswer` 신설, `IntentSpec.slots` 타입 승격, `IntentResult` 필드 4개 추가 |
| `src/domain/intent/policies.py` | 확장 | 슬롯 정규화·병합·`complete` 계산·질문 clamp |
| `src/domain/intent/interfaces.py` | 확장 | 포트에 `answers` 인자 추가 |
| `src/infrastructure/intent/adapter.py` | 확장 | 프롬프트 블록 3종(축/선택지 힌트/이전 답변) + 로그 필드 추가 |
| `src/application/intent/use_case.py`, `node.py` | 확장 | 인자 전달 |
| `src/interfaces/schemas/intent.py` | 확장 | 요청/응답 스키마 |
| `src/api/routes/intent_router.py` | 확장 | 인자 전달 |
| `src/infrastructure/config/intent_config.py` | 확장 | 상한 3종 env 추가 |
| `src/application/agent_composer/` | 신규 파일 | `AGENT_BUILD_SLOTS` 프리셋 (신규 모듈, 기존 파일 무변경) |
| `src/api/main.py` | — | **변경 없음** (DI 배선은 이미 존재) |
| DB / 프론트 | — | **변경 없음** |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| `POST /api/v1/intent/analyze` | 판정 | `intent_router.py` | **Additive** — 신규 필드는 전부 기본값 보유. 구형 요청(`slots: list[str]`)도 FR-02로 동작 |
| `tests/domain/intent/`, `tests/application/intent/`, `tests/api/test_intent_router.py` | TEST | 기존 스위트 | **Needs verification** — 무수정 통과가 하위호환의 측정 기준(§4.2) |
| `create_intent_node()` | 그래프 노드 | `application/intent/node.py` | **None** — 소비자 0(미배선). state 1키 갱신 계약 유지 |
| `AgentPlanner` / compose 파이프라인 | HITL | `application/agent_composer/planner.py` | **None (의도적)** — 다음 사이클 배선 지점 |
| `idt_front/` | — | — | **None** — API 계약 동기화 불필요 |

### 6.3 Verification

- [ ] 기존 intent 테스트를 **한 줄도 고치지 않고** 통과하는지 확인 (FR-02 하위호환)
- [ ] `git diff --name-only`에 `agent_composer/planner.py`·`compose_agent_use_case.py`가 없음을 확인
- [ ] `grep -r "어조\|tone\|데이터소스" src/domain/intent/` 결과 0건 — 도메인 어휘 미침투 확인
- [ ] `db/migration/` 신규 0건 · `idt_front/` diff 0건 확인

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Characteristics | Selected |
|-------|-----------------|:--------:|
| Starter | 단순 구조 | ☐ |
| Dynamic | 기능 단위 모듈 | ☐ |
| **Enterprise** | 레이어 분리 + DI (기존 idt/ Thin DDD) | ☑ |

기존 구조를 그대로 따른다. 새 레이어·새 패턴 없음.

### 7.2 Key Architectural Decisions

| ID | Decision | Options | Selected | Rationale |
|----|----------|---------|:--------:|-----------|
| D1 | 확장 형태 | 슬롯 1급 승격 / 별도 포트(`elicit`) 추가 / 슬롯 전용 모듈로 재정의 | **슬롯 1급 승격** | 진입점을 하나로 유지. 라벨 분류와 슬롯 채우기는 "메시지 → 구조화 의도"라는 같은 일의 두 축이라 포트를 쪼개면 호출자가 두 번 부른다 |
| D2 | 축 정의 위치 | intent 모듈 내 프리셋 / **agent_composer 프리셋 상수** / DB 설정화 | **agent_composer 프리셋 상수** | 선행 사이클 D3("분류 체계는 호출자 주입, 모듈은 의미를 모른다")를 그대로 승계. 여신·에이전트 특화 어휘가 코어에 침투하지 않는다(USER-SCENARIOS "일반화가 이긴다"). DB 설정화는 마이그레이션+UI로 범위 폭증 |
| D3 | 추천 선택지 생성 | 축별 고정값 / **LLM 동적 생성** / 하이브리드 | **LLM 동적 생성** | "데이터 분석 에이전트"와 "문서 QA 에이전트"는 필요한 데이터소스 선택지가 다르다. 고정값은 맥락 부적합. `SlotSpec.options`는 힌트로만 남겨 앵커링(R4 완화) |
| D4 | 왕복 상태 | 서버 세션 / **요청 에코백(stateless)** / DB 저장 | **요청 에코백** | 선행 사이클 D7("모듈은 상태를 보유하지 않는다") + `agent_composer`의 `ClarificationAnswerDto` 에코백 선례(D8)와 동일. 사용자 결정 "저장 안 함(휘발)"과 정합 |
| D5 | `complete` 판정 주체 | LLM / **Policy(순수함수)** | **Policy** | LLM 출력을 신뢰하지 않는 기존 3층 방어와 동일. required 충족은 계산 가능한 사실이지 판단이 아니다 |
| D6 | 답변 충돌 해소 | LLM 우선 / **사용자 답변 우선** | **사용자 답변 우선** | 되묻기의 존재 이유가 사람의 결정을 받는 것이다. LLM이 뒤집으면 HITL이 무의미해진다 |
| D7 | 실패 정책 | 예외 / **degraded 유지** | **degraded 유지** | 선행 사이클 D6 승계. 확장 필드는 빈 값으로 두어 호출자가 "의도 모름"으로 읽는다 |
| D8 | 이번 배선 범위 | 모듈+API만 / +AgentPlanner / +compose 응답 계약 | **모듈 + 독립 API만** | 회귀 위험 0으로 계약을 먼저 확정. 화면단을 사용자가 재작업 중이므로 compose 응답 계약을 지금 굳히면 두 번 고치게 된다 |
| D9 | `entities` 처리 | 유지+`filled_slots` 병행 / **`filled_slots`로 대체** / 개명만 | **대체 (별칭 여부는 Design 확정)** | 이중 소스 금지(R5). 소비자가 API 하나뿐이라 지금이 정리 비용이 가장 싼 시점 |

### 7.3 Clean Architecture Approach

```
Selected Level: Enterprise (Thin DDD — 기존 idt/ 구조 준수)

src/
├── domain/intent/                       ← 외부 의존 0. 도메인 어휘 0
│   ├── schemas.py                         Turn, IntentLabel, IntentSpec
│   │                                      + SlotSpec, SlotQuestion, SlotAnswer   ★신규
│   │                                      IntentResult(+filled_slots, suggestions,
│   │                                                   questions, complete)      ★확장
│   ├── interfaces.py                      IntentAnalyzerInterface(+answers)      ★확장
│   └── policies.py                        IntentResultPolicy
│                                          + merge_answers / resolve_complete
│                                          + clamp_questions / filter_slots       ★확장
│
├── application/intent/                  ← 흐름 제어만
│   ├── use_case.py                        AnalyzeIntentUseCase(+answers, +round)
│   └── node.py                            create_intent_node (계약 유지)
│
├── application/agent_composer/
│   └── build_slots.py                     AGENT_BUILD_SLOTS = [                  ★신규
│                                            tone, task, domain_detail,
│                                            data_source, output_format ]
│                                          └ 이번 사이클엔 정의만. 소비 = 다음 사이클
│
├── infrastructure/intent/adapter.py     ← 유일하게 LangChain을 아는 곳
│                                          _slots_block / _suggestions_hint /
│                                          _answers_block 프롬프트화             ★확장
│
├── infrastructure/config/intent_config.py  +MAX_ROUNDS/QUESTIONS/OPTIONS        ★확장
├── interfaces/schemas/intent.py            요청·응답 확장                        ★확장
└── api/routes/intent_router.py             인자 전달                             ★확장

의존 방향:  interfaces → application → domain ← infrastructure
            agent_composer(프리셋) ──주입──▶ domain/intent (역방향 참조 없음)
```

**되묻기 왕복 계약 (stateless)**

```
1) analyze(message, spec)                        → filled_slots{...}, questions[3], complete=False
2) 사용자가 선택지에서 고르거나 직접 입력
3) analyze(message, spec, answers=[...], round=1) → filled_slots 병합, questions[], complete=True
   └ 모듈은 1)과 3) 사이에 아무것도 기억하지 않는다. 상태는 전부 호출 인자에 있다.
```

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- [x] `idt/CLAUDE.md` — 레이어 책임·함수 40줄·if 2단계
- [x] `idt/docs/rules/logging.md` — StructuredLogger, `exception=e`
- [x] `idt/docs/rules/testing.md` — TDD Red→Green→Refactor
- [x] `docs/wiki/backend/patterns/supervisor-graph-contracts.md` — 계약 2(목록 프레이밍) ★R2
- [x] `domain/{x}/{interfaces,schemas,policies}.py` 모듈 관례 (4회 선례)
- [x] `PlannerPolicy` — 라운드/질문 상한 clamp 선례

### 8.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| 슬롯 스펙 | 없음 (`list[str]`) | `SlotSpec` 필드 구성 + `description` 필수 규약 | High |
| 하위호환 승격 | 없음 | pydantic validator로 `str → SlotSpec` 자동 승격 — **신규 관례**, Design에 명문화 | High |
| 되묻기 왕복 | `agent_composer`에 선례 존재(에코백) | intent 쪽에도 동일 에코백 계약 적용. 필드명 정합(`answers`/`round`) | High |
| 상한 상수 출처 | `PlannerPolicy` 상수 | intent 쪽은 **config(env)** 로 — 두 모듈이 서로 다른 출처를 갖는 이유를 Design에 기록 | Medium |
| 축 프리셋 | 없음 | `AGENT_BUILD_SLOTS` 5축의 `description` 문안 — 판정 품질을 좌우하므로 Design 산출물 | High |

### 8.3 Environment Variables Needed

| Variable | Purpose | Scope | Default | To Be Created |
|----------|---------|-------|---------|:-------------:|
| `INTENT_MAX_CLARIFICATION_ROUNDS` | 되묻기 라운드 상한 | Server (idt/.env) | `2` (PlannerPolicy 정합) | ☑ |
| `INTENT_MAX_QUESTIONS_PER_ROUND` | 라운드당 질문 상한 | Server | `3` | ☑ |
| `INTENT_MAX_OPTIONS_PER_SLOT` | 축당 추천 선택지 상한 | Server | `4` | ☑ |
| `INTENT_ANALYZER_MODEL` / `_TEMPERATURE` / `_TIMEOUT_SEC` / `_HISTORY_LIMIT` | 기존 | Server | 기존값 | ☐ (기존) |

> 전 항목이 기본값을 가지므로 **미설정 환경에서도 동작**한다.

### 8.4 Pipeline Integration

해당 없음 — 단일 기능 PDCA 사이클.

---

## 9. Next Steps

1. [ ] 본 Plan 검토·승인
2. [ ] `/pdca design intent-slot-elicitation` — 3안 비교. **Design에서 반드시 확정할 항목**:
   - `entities` vs `filled_slots` 최종 처리 (D9 / R5)
   - `labels` 최소 2개 제약 완화 여부 (FR-16 — 슬롯 전용 사용 시)
   - R2 완화 프롬프트 문안 (축 블록 / 선택지 힌트 / "목록은 권한이 아니다" 프레이밍)
   - `AGENT_BUILD_SLOTS` 5축의 `description`·`options`·`required` 확정 문안
   - `SlotQuestion` 문안 생성을 LLM에 맡길지, 템플릿(`{description}을(를) 알려주세요`)으로 할지
3. [ ] TDD 구현 (`/pdca do intent-slot-elicitation`)
4. [ ] `/pdca analyze intent-slot-elicitation` — Gap 분석
5. [ ] **후속 사이클**(별도 PDCA): `AgentPlanner` 배선 + compose 응답 계약 확장 + 진입 화면 재작업. 진입 조건으로 R2(과차단) 실측 재평가

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-08-14 | 초안 — 사용자 인터뷰 8문항 기반 (D1~D9 확정) | 배상규 |
