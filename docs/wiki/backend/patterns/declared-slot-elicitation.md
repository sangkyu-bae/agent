---
title: 되묻기는 선언된 슬롯 축의 함수 — SlotSpec 엘리시테이션 계약
status: approved
reviewer: 배상규
source_type: conversation
source_refs:
  - idt/src/domain/intent/policies.py:1-17 (불변식 I1~I7 명문, ⚠️ 미커밋)
  - idt/src/domain/intent/schemas.py (SlotSpec/SlotAnswer/SlotQuestion/SlotLimits 등 VO 8종)
  - idt/src/application/agent_composer/build_slots.py (AGENT_BUILD_SLOTS 5축 — 축 의미는 소비자 쪽)
  - idt/src/infrastructure/intent/adapter.py:60-90 (_SLOTS_TEMPLATE — "비우는 것이 기본" 반전, Act-2 D2)
  - docs/archive/2026-08/intent-slot-elicitation/intent-slot-elicitation.report.md (D1~D9 · C2/C3 · §5.3 미검증 공백)
confidence: 0.8
version: 1
created: 2026-08-20
updated: 2026-08-20
verified_at: 7c3ffdd
---

# 되묻기는 선언된 슬롯 축의 함수 — SlotSpec 엘리시테이션 계약

## 문제

"부족한 정보를 LLM이 알아서 되묻게" 하면 무엇을 물을지가 **LLM 자유재량**이 되어
같은 요청에 매번 다른 질문이 나오고, 파악된 내용은 프롬프트 문자열에 녹아 사라진다.
intent-slot-elicitation 사이클이 이를 **선언된 축(SlotSpec) 데이터**로 바꿨다 —
질문은 "required 축의 미충족"의 함수가 되어 재현 가능해졌고, 축을 추가하면 질문도
따라 늘어난다.

## 검증된 사실

### 1. 계약의 뼈대 — 무엇이 어디서 결정되는가

| 결정 | 주체 | 근거 |
|---|---|---|
| 무엇을 물을 수 있는가 (축·필수 여부·예시) | 호출자가 주입하는 `SlotSpec` 목록 | D1 |
| 슬롯 값 추출·추천 선택지·질문 문장 | LLM (`IntentDraft`) | D3 — 추천은 요청 맥락 따라 실제로 달라짐 (실측) |
| `missing_slots` / `complete` / 질문의 대상 축 | **Policy 순수함수가 계산** — LLM 필드가 아예 없음 | I2/I4, D5. 오염 경로 소멸 |
| 라운드 상한 → `questions=[]` | Policy가 **프롬프트와 무관하게 하드 강제** (I5) | Design C5 — 프롬프트 소프트 + 코드 하드 |
| 사용자 `answers` vs LLM 값 충돌 | **사용자 답변이 항상 이긴다** (병합 우선) | D6, 실 LLM 왕복으로 확인 |

왕복 자체는 stateless(`answers` + `round` 에코백, 서버 재clamp) —
[[stateless-hitl-clarification]]과 같은 2요소이며 세션 테이블 0.

### 2. 축의 *의미*는 범용 모듈에 두지 않는다 (D2)

`domain/intent`는 "어조"·"데이터소스" 같은 도메인 어휘를 몰라야 한다. 5축 프리셋
`AGENT_BUILD_SLOTS`는 소비자 쪽(`application/agent_composer/build_slots.py`)에 두고
주입만 한다 — AST 스캔으로 domain/intent에 도메인 어휘 0건을 잠갔다.
required 배분에도 근거가 있다: 없으면 초안 자체가 불가능한 앞 3축(task/scope/data)만
required, 합리적 기본값이 있는 축은 optional로 두어 되묻기 예산(라운드 2 × 질문 3)을
앞쪽에 몰아준다. `options`는 고정 목록이 아니라 **LLM 앵커링용 예시**다.

### 3. 함정 — LLM은 채우는 쪽으로 강하게 기운다 (C3, 부분 해소)

"확실히 알 수 있는 항목만 채우세요"는 실 LLM에서 무시됐다 — 모델이 "세부사항이
부족함"이라고 써 놓고도 5축을 전부 지어내 채웠고(`tone="친근한 설명형"` 같은 순수
confabulation), `missing=[]`이 되어 **되묻기가 아예 발동하지 않았다** — 기능의 존재
이유가 사라지는 결함. 프롬프트를 **"비워 두는 것이 기본입니다"로 반전**하고 대조
예시를 넣어 3프로브 중 2개가 정상화됐지만, **프롬프트만으로는 결정론적 보장이
불가**하다 (1개 프로브는 여전히 과충전). 배선 시 "LLM이 채운 optional 축을 사용자에게
확인받는 UI" 또는 "사용자 확인 전 미확정" Policy 규칙이 필요하다 — 이월 항목.

### 4. 함정 — 선택지를 질문 문장에 녹인다 (C2)

LLM이 선택지를 질문 텍스트 안에 서술하고 `options=[]`로 보내면 화면이 버튼을 만들 수
없다. 방어는 이중 — 프롬프트 지시(2차) + **Policy가 `suggestions`에서 options를
폴백 충전**(1차, 코드). 단 Act-2 이후 LLM이 `suggestions` 자체를 생략하는 경향이
관측됐다(질문 상한 밖 축의 선택지가 비는 공백, §5.3).

### 5. 미배선 경고

이 계약의 소비자(`AgentPlanner`)는 아직 배선되지 않았다(D8). `AGENT_BUILD_SLOTS`는
죽은 코드 상태이며, 배선 사이클에서 종료 조건을 `confidence >= 0.8` →
`complete == True`로 교체하고 `ClarificationAnswerDto ↔ SlotAnswer`(구조 동형)를
매핑해야 한다. 코드 전체가 ⚠️ 미커밋.

## 다음에 적용하는 법

1. LLM 되묻기 기능을 만들 때 "무엇을 물을지"를 LLM 재량에 두지 말고 **축을 데이터로
   선언**한다 — 같은 요청 → 같은 질문이라는 재현성이 생기고, 질문 품질을 축 정의
   수정으로 개선할 수 있다.
2. `missing`/`complete` 같은 판정은 LLM 스키마에서 빼고 순수함수 Policy가 계산한다
   ([[llm-output-trust-boundary]]). 상한·종료 조건은 프롬프트가 아니라 코드로 강제.
3. 슬롯 채우기 프롬프트는 **"비우는 것이 기본" 방향으로 쓴다** — "확실한 것만
   채우세요"는 실측에서 통하지 않았다. 그래도 과충전은 남으므로 optional 축은 사용자
   확인 UI를 계획에 포함한다.
4. 축 프리셋·도메인 어휘는 범용 모듈이 아니라 소비자 모듈에 두고, AST 테스트로 어휘
   침투 0건을 잠근다 ([[ast-source-contract-tests]]).

## 관련 문서

- 왕복 전송 계약(에코백+재clamp): `backend/patterns/stateless-hitl-clarification.md`
- LLM 스키마의 provider 계약(자유 키 dict 금지): `backend/patterns/structured-output-strict-schema.md`
- 계산 필드는 스키마에서 제외: `backend/patterns/llm-output-trust-boundary.md`
