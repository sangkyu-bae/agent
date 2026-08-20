---
template: report
version: 1.3
feature: intent-slot-elicitation
plan: docs/01-plan/features/intent-slot-elicitation.plan.md
design: docs/02-design/features/intent-slot-elicitation.design.md
analysis: docs/03-analysis/intent-slot-elicitation.analysis.md
---

# intent-slot-elicitation Completion Report

> **Project**: sangplusbot (idt — 백엔드)
> **Author**: 배상규 (tkdrb136@gmail.com)
> **Period**: 2026-08-14 ~ 2026-08-17
> **Final Match Rate**: 99% (정적) · 실 LLM 왕복 검증 통과
> **Status**: ✅ Completed

---

## Executive Summary

### 1.1 Project Overview

| Perspective | Content |
|-------------|---------|
| **Problem** | 채팅으로 에이전트를 만들 때 초안 품질을 가르는 정보는 **어떤 어조로 / 무슨 데이터를 / 어떻게 분석해 / 어떤 형태로** 인데, 이를 담당하던 `AgentPlanner`가 무엇을 물을지를 **LLM 자유재량**에 맡겨 질문이 매번 달랐고 파악된 내용은 `system_prompt` 문자열에 녹아 사라졌다. 그릇이 되어야 할 `domain/intent`는 슬롯이 `list[str]` 키 목록뿐이라 "무엇을 물어야 하는지"를 표현할 수 없었다. |
| **Solution** | `SlotSpec(key, description, options, allow_free_text, required)`로 **물어볼 축을 데이터로 선언**하고, 결과를 `filled_slots` + `missing_slots` + `questions`(맥락 기반 추천 선택지 포함) + `complete`로 확장했다. 답변을 `answers`로 되먹이는 **stateless 왕복 계약**을 포트에 명문화했다. 축의 *의미*는 `agent_composer` 프리셋에 두어 모듈의 범용성을 지켰다. |
| **Function/UX Effect** | 화면 변화 **없음** (Plan D8 — 배선은 다음 사이클). `POST /api/v1/intent/analyze`로 축 기반 판정과 되묻기 왕복이 실 LLM에서 동작함을 확인했다. |
| **Core Value** | 되묻기가 **LLM의 기분**이 아니라 **선언된 축의 미충족**에서 나온다 — 같은 요청이면 같은 질문이 나오고, 축을 추가하면 질문도 따라 늘어난다. |

### 1.2 Results Summary

| 항목 | 결과 |
|------|------|
| 변경 파일 | 수정 12 / 신규 3 (`build_slots.py`, `test_schemas.py`, `test_build_slots.py`) |
| 코드 변경량 | +1,649 / −240 라인 |
| 테스트 | intent + composer **222 passed** (신규·확장 약 150건) |
| 전체 스위트 | 58 failed / **7,228 passed** — 58건은 전부 기존 실패, **회귀 0건** |
| 정적 Match Rate | 99% (Structural 95 / Functional 98 / Contract 100 / Runtime 100) |
| 실 LLM 검증 | ✅ 라운드 0 질문 3개(options 포함) → 답변 되먹임 → `complete=True` |
| Act 반복 | 2회 (Act-1 strict 스키마 / Act-2 옵션 폴백 + 과충전 방지) |
| DB 마이그레이션 | 0건 |
| 프론트 변경 | 0건 |

### 1.3 Value Delivered

| Perspective | 실제 결과 |
|-------------|-----------|
| **Problem 해소** | 되묻기 질문이 `SlotSpec.required` 미충족의 함수가 되었다. 실측: "데이터 분석 에이전트" → `task`만 채우고 나머지 4축을 미충족으로 남긴 뒤 질문 3개 생성. "사내 규정 문서 QA" → 같은 축에 **다른 추천**(인사/재무/안전 규정) |
| **Solution 구현** | `SlotSpec`·`SlotAnswer`·`SlotQuestion`·`SlotValue`·`SlotSuggestion`·`SlotLimits`·`IntentDraft` 7개 VO 신설. 불변식 I1~I7을 순수함수 + 테스트로 잠금 |
| **Function/UX** | 화면 변화 0건(설계대로). API 계약은 다음 사이클 화면이 그대로 쓸 수 있는 형태(`questions[]`가 기존 `ClarifyQuestionCard` props와 동형)로 고정 |
| **Core Value** | 재현성 확보 + **숨어 있던 치명 결함 3건을 실 LLM 검증으로 발견·수정**. 특히 선행 사이클부터 존재하던 "실 LLM에서 100% 실패"를 드러냄 |

---

## 1.4 Success Criteria Final Status

### Definition of Done (Plan §4.1)

| # | 기준 | 상태 | 근거 |
|---|------|:----:|------|
| 1 | FR-01 ~ FR-16 전부 구현 | ✅ | Analysis §3 — 15 완전 충족 + FR-10 문언 이탈(동작 동등) |
| 2 | `pytest` 전체 통과, 기존 테스트 실패 0건 | ✅ | 7,228 passed. `git stash` 전후 53=53으로 기존 실패 분리 확인 |
| 3 | `planner.py`/`compose_agent_use_case.py`/supervisor/general_chat 변경 0건 | ✅ | `git diff --name-only -- src/application/agent_composer/` 결과 없음 |
| 4 | `db/migration/` 신규 0건 | ✅ | `git status --porcelain` = 0 |
| 5 | `idt_front/` 변경 0건 | ✅ | `git diff --stat` 결과 없음 |
| 6 | verify 스킬 3종 | ⚠️ 대체 | A1~A6 + ruff + TDD 순서 준수로 동등 검증 (Analysis §5 M4) |
| 7 | **실 LLM 수동 시나리오 1회** | ✅ | Analysis §10 — 3개 프로브 실행, Critical 3건 발견·수정 |

**7/7 달성** (1건은 동등 수단으로 대체)

### Quality Criteria (Plan §4.2)

| # | 기준 | 상태 |
|---|------|:----:|
| 1 | `IntentResultPolicy` 분기 커버리지 100% | ✅ |
| 2 | 구형 `slots=["a"]` / 신형 `SlotSpec` 두 입력 모두 동작 | ✅ |
| 3 | spec 밖 슬롯 키 제거 | ✅ |
| 4 | 사용자 `answers`가 LLM 값을 덮어씀 | ✅ (도메인 + 어댑터 종단) |
| 5 | 라운드 상한 시 `questions == []` | ✅ (프롬프트와 무관하게 하드 강제) |
| 6 | LLM 실패 3종 degraded | ✅ |
| 7 | API 200/401/422 | ✅ |
| 8 | 함수 40줄 이내, if 중첩 2단계 이내 | ✅ (AST 스캔 위반 0건) |

**8/8 달성**

---

## 1.5 Decision Record Summary

| ID | 결정 | 준수 | 결과 |
|----|------|:----:|------|
| Plan D1 | 슬롯 1급 승격 (포트 단일 유지) | ✅ | `analyze()` 하나로 분류+슬롯 처리. 호출자가 두 번 부르지 않음 |
| Plan D2 | 축 프리셋은 `agent_composer` | ✅ | `domain/intent` 코드에 도메인 어휘 0건 (AST 스캔). 모듈 범용성 유지 |
| Plan D3 | 추천 선택지 LLM 동적 생성 | ✅ | 실측 확인 — 요청이 다르면 추천도 다름 (Analysis §10.4) |
| Plan D4 | 왕복 stateless (요청 에코백) | ✅ | 라운드 간 상태 미보유 테스트로 잠금 |
| Plan D5 | `complete`는 Policy 계산 | ✅ | `IntentDraft`에 필드 자체가 없어 오염 경로 소멸 |
| Plan D6 | 사용자 답변 우선 | ✅ | 실 LLM 왕복에서도 확인 |
| Plan D7 | 실패 시 degraded 유지 | ✅ | **단, 이 설계가 C1을 3개월간 은폐했다** (§6.2) |
| Plan D8 | 모듈 + 독립 API까지만 | ✅ | `agent_composer` diff 0건 |
| Plan D9 | `entities` 대체 | ✅ | 별칭 없이 완전 제거. 소비자 0이라 비용 최소 |
| Design Option C | LLM 스키마 분리 | ⚠️ 이탈 | 배치를 domain(`IntentDraft`)으로 변경. **이 이탈이 C1 수정 비용을 크게 낮췄다** (§6.1) |
| Design C5 | 프롬프트 소프트 + Policy 하드 | ✅ | 라운드 상한이 프롬프트와 독립적으로 작동 |

**10/11 준수 + 1 문서화된 이탈**

---

## 2. Related Documents

| 문서 | 경로 |
|------|------|
| Plan | `docs/01-plan/features/intent-slot-elicitation.plan.md` |
| Design | `docs/02-design/features/intent-slot-elicitation.design.md` |
| Analysis | `docs/03-analysis/intent-slot-elicitation.analysis.md` |
| 선행 사이클 | `docs/archive/2026-08/intent-analyzer/` |
| 선행 사이클 | `docs/archive/2026-08/agent-create-entry/` |
| 위키 계약 2 | `docs/wiki/backend/patterns/supervisor-graph-contracts.md` |

> PRD 없음 — `/pdca pm` 미수행. Plan이 최상위 문서였다.

---

## 3. Completed Items

### 3.1 Functional Requirements

| ID | 요구사항 | 상태 |
|----|----------|:----:|
| FR-01 | `SlotSpec` 정의 | ✅ |
| FR-02 | `list[str]` → `SlotSpec` 자동 승격 (하위호환) | ✅ |
| FR-03 | `entities` → `filled_slots` 대체 | ✅ |
| FR-04 | `suggestions` — LLM 맥락 기반 동적 생성 | ✅ |
| FR-05 | `questions` — 미충족 축 한정 | ✅ |
| FR-06 | `complete` — Policy 계산 | ✅ |
| FR-07 | 포트에 `answers`/`round_` 추가 (stateless) | ✅ |
| FR-08 | 사용자 답변 우선 병합 | ✅ |
| FR-09 | Policy 정규화 6종 + 질문 중복 제거 | ✅ |
| FR-10 | 라운드 상한 → `questions=[]` | ⚠️ 동작 충족 (구현 방식 문언 이탈) |
| FR-11 | LLM 실패 3종 degraded | ✅ |
| FR-12 | API 요청·응답 확장 | ✅ |
| FR-13 | `AGENT_BUILD_SLOTS` 5축 | ✅ |
| FR-14 | 상한·모델 config 주입 | ✅ |
| FR-15 | 로그 필드 5개 추가 (슬롯 값 미기록) | ✅ |
| FR-16 | `labels` 또는 `slots` 조건 완화 | ✅ |

### 3.2 Non-Functional Requirements

| 항목 | 기준 | 결과 |
|------|------|------|
| 결합도 | domain에 도메인 어휘 0건 | ✅ AST 코드레벨 0건 (docstring 2줄은 의도적 유지) |
| 하위호환 | 구형 `slots` 입력 동작 | ✅ API 경계에서 승격 |
| 회귀 안전 | `agent_composer` 등 무변경 | ✅ diff 0건 |
| 되묻기 종료성 | 상한 도달 시 질문 없음 | ✅ 프롬프트와 독립 강제 |
| 관측성 | `exception=e` 스택 트레이스 | ✅ |
| PII | 슬롯 값 미로깅 | ✅ 테스트로 잠금 |
| 테스트 | Policy 분기 100% | ✅ |

### 3.3 Deliverables

**신규 (3)**

| 파일 | 라인 | 내용 |
|------|-----:|------|
| `src/application/agent_composer/build_slots.py` | 55 | `AGENT_BUILD_SLOTS` 5축 프리셋 |
| `tests/domain/intent/test_schemas.py` | 262 | 스키마 검증 + strict 호환성 회귀 방어 |
| `tests/application/agent_composer/test_build_slots.py` | 71 | 프리셋 무결성 |

**수정 (12)**

| 파일 | 내용 |
|------|------|
| `src/domain/intent/schemas.py` | VO 7개 신설, `IntentSpec` 승격 + validator 3개, `IntentResult` 재구성 |
| `src/domain/intent/policies.py` | `normalize` 재작성 + 순수함수 9개 (불변식 I1~I7) |
| `src/domain/intent/interfaces.py` | 포트에 `answers`/`round_` |
| `src/infrastructure/intent/adapter.py` | `IntentDraft` structured output, 프롬프트 블록 5종, 로그 5필드 |
| `src/infrastructure/config/intent_config.py` | env 3개 + `slot_limits()` |
| `src/application/intent/use_case.py` | 인자 전달 |
| `src/interfaces/schemas/intent.py` | 요청 `answers`/`round` |
| `src/api/routes/intent_router.py` | 인자 전달 |
| `tests/*` (4) | 시나리오 S1~S41 + Act-1/Act-2 회귀 방어 |

> `src/application/intent/node.py`와 `src/api/main.py`는 **무변경**. LangGraph state에는 되묻기 왕복이 없고(그래프는 사람을 기다리지 않는다), DI 배선은 생성자 시그니처가 그대로라 손댈 것이 없었다.

---

## 4. Incomplete Items

### 4.1 다음 사이클 이월

| 항목 | 이유 | 우선순위 |
|------|------|:--------:|
| **`AgentPlanner` 배선** | Plan D8이 명시적으로 범위 밖. **이걸 하지 않으면 이번 작업 가치가 0으로 남는다** | **최우선** |
| **C3 과충전 완전 해소** | 프롬프트로 3/3 달성 불가. 결정적 보장은 계약 확장 필요 (§5.3) | 높음 |
| compose 응답 계약 확장 | 화면단 재작업 결과에 종속. 지금 굳히면 두 번 고침 | 중간 |
| 프론트 진입 화면 | 사용자가 별도 재작업 예정 | — |

### 4.2 문서 갱신 필요 (SoT 규칙 — 코드가 진실)

| 문서 | 어긋난 내용 |
|------|-------------|
| Design §3.1 | `_IntentLLMOutput`/`_SlotQuestionOut` → 실제는 `IntentDraft`/`SlotQuestionDraft` (domain) |
| Design §3.1 | `IntentDraft.filled_slots`가 dict → 실제는 `list[SlotValue]` (Act-1) |
| Design §9.3 | "File Import Rules"가 적용 대상을 잃음 |

### 4.3 취소/보류

| 항목 | 판단 |
|------|------|
| `entities` 별칭 병행 노출 | **취소** — 소비자 0이라 즉시 제거가 더 쌈 |
| `method="function_calling"` 전환 | **기각** — 400은 피하지만 되묻기가 죽음 (실측) |
| 축 DB 설정화 | **보류** — 마이그레이션+UI로 범위 폭증 |
| `sNN` 테스트 태그 9건 보강 | **보류** — 추적성만 영향 |

---

## 5. Quality Metrics

### 5.1 최종 분석 결과

| 축 | 비율 |
|----|-----:|
| Structural | 95% |
| Functional | 98% |
| Contract | 100% |
| Runtime | 100% |
| **Overall** | **99%** |

### 5.2 해소한 이슈

| ID | 심각도 | 내용 | 조치 |
|----|:------:|------|------|
| **C1** | Critical | 자유 키 `dict`가 OpenAI strict structured outputs를 무효화 → 실 LLM 100% 실패 | `IntentDraft`만 배열 기반 전환 + 스키마 재귀 탐색 회귀 테스트 |
| **C2** | Critical | LLM이 선택지를 질문 문장에 녹여 `options=[]` → 화면이 버튼 생성 불가 | Policy `suggestions` 폴백 + 프롬프트 지시 (이중 방어) |
| **C3** | Critical | 과충전으로 `missing=[]` → 되묻기 미발동 | 프롬프트에서 "비우는 쪽이 기본"으로 반전 (3프로브 중 2개 정상화) |
| M5 | Minor | 실 LLM 미검증 | 해소 — 위 3건이 여기서 나왔다 |

### 5.3 미검증 잔여 영역 (정직한 공백)

| 영역 | 상태 |
|------|------|
| **C3 과충전** | **부분 해소.** "슬랙 아침 인사" 프로브는 여전히 5축을 다 채워 질문 0개. `tone="친근한 설명형"`은 순수 confabulation. 프롬프트로는 결정론적 보장 불가 |
| `suggestions` 공백 경향 | Act-2 이후 LLM이 `questions[].options`만 채우고 `suggestions`를 생략. 질문 상한(3) **밖** 축의 선택지를 API 소비자가 볼 수 없음 |
| 실 LLM 반복 안정성 | 프로브 3개 × 2회 실행. 통계적 신뢰구간을 논할 표본이 아님 |
| 다른 모델 | `gpt-4o-mini`만 검증. 모델 교체 시 재검증 필요 |
| 부하·동시성 | 미측정 (hot path 미배선이라 이번 범위 밖) |

---

## 6. Lessons Learned & Retrospective

### 6.1 Keep — 잘 된 것

1. **실 LLM 검증을 Report 앞에 배치한 판단.** Match Rate 99%·Critical 0건으로 통과한 코드가 실제로는 **한 번도 동작한 적이 없었다.** 이 순서가 아니었다면 결함을 안고 배선 사이클에 들어갔을 것이다.
2. **`IntentDraft` 분리(Design 이탈)가 수정 비용을 낮췄다.** LLM 스키마와 도메인 VO가 붙어 있었다면 C1 수정이 API 계약·라우터 테스트 30건까지 번졌을 것이다. 실제로는 `IntentDraft`만 바꾸고 도메인·API는 무변경이었다.
3. **불변식(I1~I7)을 먼저 잠근 세션 분할.** module-1,2에서 규칙을 전부 순수함수로 고정하니 이후 세션은 배선일 뿐이었다. Act-1/Act-2 수정도 Policy만 손대면 됐다.
4. **기존 실패와 신규 실패를 `git stash`로 분리.** 전체 스위트 58건 실패를 "우리 탓 아님"으로 근거 있게 말할 수 있었다.
5. **결함을 구조로 막았다.** C1 재발 방지를 "조심하자"가 아니라 스키마 재귀 탐색 테스트로 잠갔다.

### 6.2 Problem — 개선 필요

1. **`degraded` 폴백이 결함을 3개월간 은폐했다.** "실패해도 본 흐름을 막지 않는다"는 좋은 설계지만, **아무도 쓰지 않는 모듈에서는 침묵과 구분되지 않는다.** 선행 사이클도 실 LLM에서 400이었는데 폴백이 이를 삼켰다.
2. **테스트 전량 green이 동작을 보장하지 않았다.** fake chain은 우리가 정의한 스키마를 그대로 돌려주므로, **스키마 자체가 외부 계약과 어긋난 경우를 구조적으로 볼 수 없다.**
3. **Design이 레이어 위반을 담고 있었다.** §3.1이 domain의 `normalize()`가 infrastructure 타입을 받도록 설계했다. Do 단계에서 발견해 고쳤지만, Design 리뷰에서 잡혔어야 했다.
4. **검증 하네스의 판정 기준이 두 개 틀렸다.** "라운드 1에 질문 없음"은 optional 축을 고려하지 않았고, 맥락 적응 비교는 대상을 잘못 골랐다. **검증 코드도 검증이 필요하다.**
5. **미배선 프리셋(`AGENT_BUILD_SLOTS`)이 죽은 코드로 남았다.** Plan R6이 예견한 대로다. 배선 사이클이 늦어질수록 위험이 커진다.

### 6.3 Try — 다음에 시도할 것

1. **"미배선 모듈도 실호출 1회"를 DoD 고정 항목으로.** 이번엔 Plan §4.1 #7에 있었지만 마지막 순위였다. **fake로만 검증한 외부 연동은 미검증으로 간주**한다.
2. **외부 계약 스모크 테스트를 CI에 넣기.** `model_json_schema()`를 실제 provider 제약(자유 키 dict 금지 등)에 대조하는 테스트는 LLM 호출 없이도 돌릴 수 있다. 이미 하나 만들었으니 다른 structured output 모듈에도 확산.
3. **`degraded` 발생을 관측 지표로.** 로그에는 남지만 아무도 안 본다. degraded 비율이 임계 이상이면 알림이 필요하다 — 특히 신규 배선 직후.
4. **Design 단계에 레이어 방향 체크 1줄 추가.** "이 타입은 어느 레이어에 있고, 그것을 인자로 받는 함수는 어느 레이어인가"를 명시적으로 묻는다.
5. **LLM 행동 검증은 프로브 3개로 부족.** 최소 5~10개 요청 유형 + 반복 실행으로 확률적 실패율을 본다.

---

## 7. Process Improvement Suggestions

### 7.1 PDCA 프로세스

| 제안 | 근거 |
|------|------|
| **Check 단계를 "정적 → 실연동" 2단으로 분리** | 이번 사이클의 정적 99%와 실연동 결과가 정반대였다. 하나의 Match Rate로 합치면 실연동 실패가 가려진다 |
| Analysis 문서에 "미검증 공백" 절 필수화 | §5.3이 이번에 가장 유용한 절이었다. 무엇을 모르는지 적는 것이 무엇을 아는지 적는 것보다 중요할 때가 있다 |
| Design 산출물에 "이탈 시 기록 위치" 명시 | 이탈 자체는 정상인데, 근거가 코드 docstring에만 남아 Design과 코드가 조용히 어긋났다 |

### 7.2 도구/환경

| 제안 | 근거 |
|------|------|
| `.env` 로더를 검증 스크립트 공용 유틸로 | `ChatOpenAI`가 pydantic-settings를 안 거쳐 매번 수동 로딩이 필요했다 |
| Windows 콘솔 UTF-8 강제 | `cp949` 인코딩 에러로 첫 실행이 중단됐다 (`PYTHONIOENCODING=utf-8`) |
| 기존 실패 58건 정리 | 매 사이클 "우리 탓인가" 확인에 전체 스위트 2회 실행(약 8분)이 든다 |

---

## 8. Next Steps

### 8.1 즉시

1. [ ] Design §3.1·§9.3을 코드에 맞춰 갱신 (§4.2)
2. [ ] `/pdca archive intent-slot-elicitation`

### 8.2 다음 PDCA 사이클 — `AgentPlanner` 배선

**진입 조건 (Design §11.4)**

| # | 조건 | 상태 |
|---|------|:----:|
| 1 | R2(목록 프레이밍 과차단) 실측 재평가 | ✅ **충족** — 축 목록 밖 요청도 거절·왜곡 없음 |
| 2 | compose 응답 계약 확정 | ⏳ 화면단 재작업 이후 |

**배선 시 반드시 다룰 것**

| 항목 | 내용 |
|------|------|
| **C3 과충전 대응** | LLM이 채운 optional 축을 사용자에게 확인받는 UI, 또는 "사용자 확인 전까지 미확정" Policy 규칙 도입 여부 결정 |
| 종료 조건 교체 | `confidence >= 0.8` → `complete == True` 또는 라운드 상한 |
| 답변 매핑 | `ClarificationAnswerDto` ↔ `SlotAnswer` (구조 동형) |
| `suggestions` 공백 | 질문 상한 밖 축의 선택지를 화면이 필요로 하는지 판단 |

---

## 9. Changelog

### v1.0.0 (2026-08-17)

**Added**
- `SlotSpec` / `SlotAnswer` / `SlotQuestion` / `SlotQuestionDraft` / `SlotValue` / `SlotSuggestion` / `SlotLimits` / `IntentDraft` — 도메인 VO 8종
- `IntentResult`에 `filled_slots` / `suggestions` / `questions` / `complete` 추가
- 포트·UseCase·API에 `answers` / `round` 왕복 인자
- `AGENT_BUILD_SLOTS` 5축 프리셋 (`agent_composer`)
- env 3종: `INTENT_MAX_CLARIFICATION_ROUNDS` / `_QUESTIONS_PER_ROUND` / `_OPTIONS_PER_SLOT`
- 구조화 로그 5필드 (`filled_count`/`missing_count`/`question_count`/`complete`/`round`)

**Changed**
- `IntentSpec.slots`: `list[str]` → `list[SlotSpec]` (구형 입력 자동 승격)
- `IntentSpec.labels`: 필수 ≥2 → 선택 (0 또는 ≥2). `labels` 또는 `slots` 중 하나 필요
- LLM structured output 스키마를 `IntentResult` 겸용에서 `IntentDraft` 전용으로 분리
- 프롬프트: 슬롯 지시문을 "비워 두는 것이 기본"으로 반전 + 되묻기 규칙 분리

**Removed**
- `IntentResult.entities` (→ `filled_slots`, 별칭 없음)

**Fixed**
- 자유 키 `dict`가 OpenAI strict structured outputs를 무효화하던 문제 — **선행 사이클부터 존재**, 실 LLM 판정이 항상 `degraded`였다
- LLM이 선택지를 질문 문장에 녹여 `options`가 비던 문제
- LLM 과충전으로 되묻기가 발동하지 않던 문제 (부분)

**Breaking**
- `POST /api/v1/intent/analyze` 응답에서 `entities` 제거 (소비자 0)
- 요청 `spec.slots`가 객체 배열 권장 (문자열 배열도 계속 허용)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-08-17 | 완료 보고서 — Match Rate 99%, DoD 7/7, Quality 8/8, Critical 3건 발견·수정 | 배상규 |
