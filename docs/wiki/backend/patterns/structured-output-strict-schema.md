---
title: OpenAI strict structured outputs — 자유 키 dict 금지 + 미배선 모듈 실 LLM 스모크
status: approved
reviewer: 배상규
source_type: conversation
source_refs:
  - idt/tests/domain/intent/test_schemas.py:189-260 (자유 키 dict 재귀 탐색 회귀 테스트, ⚠️ 미커밋)
  - idt/src/domain/intent/schemas.py:194-235 (IntentDraft — 배열 기반 전환 + mapping 관용 validator)
  - idt/src/infrastructure/intent/adapter.py (with_structured_output(IntentDraft))
  - docs/archive/2026-08/intent-slot-elicitation/intent-slot-elicitation.report.md (§5.2 C1 · §6.2 · §4.3 function_calling 기각)
confidence: 0.85
version: 1
created: 2026-08-20
updated: 2026-08-20
verified_at: 7c3ffdd
---

# OpenAI strict structured outputs — 자유 키 dict 금지 + 미배선 모듈 실 LLM 스모크

## 문제

`with_structured_output(Model)` 로 만든 모듈이 **테스트 전량 green, Match Rate 99%**
인데 실 LLM에서는 **100% 실패**하고 있었다 (intent-slot-elicitation C1). 원인은
스키마에 있던 자유 키 dict — `dict[str, str]` 필드 하나가 JSON Schema에서
`additionalProperties: {...}` 로 렌더되고, **OpenAI strict structured outputs는 이를
거부**해 매 호출이 400이 됐다. 이 결함은 **선행 사이클(intent-analyzer)부터 3개월간
존재**했다 (`IntentResult.entities: dict[str,str]`가 같은 이유로 깨져 있었다).

3개월간 아무도 몰랐던 이유가 이 문서의 핵심이다:

1. **fake chain은 구조적으로 이걸 못 본다.** 테스트의 fake는 우리가 정의한 스키마를
   그대로 돌려주므로, "스키마 자체가 외부 provider 계약과 어긋난 경우"는 어떤
   단위 테스트로도 잡히지 않는다.
2. **degraded 폴백이 실패를 삼켰다.** "LLM 실패는 흡수하고 본 흐름 유지"는 좋은
   설계지만([[degradation-vs-failure-boundary]]), **아무도 쓰지 않는(미배선) 모듈에서는
   침묵과 구분되지 않는다.** 판정이 항상 degraded였는데 로그를 보는 사람이 없었다.

## 검증된 사실

1. **LLM이 보는 스키마 어디에도 자유 키 dict가 있으면 안 된다** — 중첩 깊숙이 있어도
   전체 strict 모드가 무효화된다. 수정은 LLM 전용 스키마(`IntentDraft`)만 배열 기반
   (`list[SlotValue]` 등 key/value 객체 배열)으로 바꾸는 것으로 끝났다 — Draft/Result가
   분리돼 있었기 때문에 도메인 VO·API 응답은 dict를 유지하며 무변경
   ([[llm-output-trust-boundary]]의 분리가 수정 비용을 국소화한 실증).
2. **재발 방지는 LLM 호출 없이 가능하다** — `model_json_schema()`를 재귀 탐색해
   `additionalProperties`가 스키마인 지점을 찾는 테스트(`_free_key_dict_paths`)가
   위반을 정적으로 잡는다. LLM이 보는 스키마마다 1개씩 둔다.
3. **`method="function_calling"` 전환은 기각됐다 (실측)** — 400은 피하지만 strict
   보장이 사라져 되묻기 필드(`questions`)가 채워지지 않았다. "에러를 없애는" 우회가
   아니라 스키마를 고치는 것이 답이었다. 단, dict 형태로 값을 주는 구현체를 위해
   `mode="before"` validator로 **입력 관용**은 유지한다 (schemas.py `_pairs_from_mapping`).
4. **정적 검증과 실연동 결과가 정반대일 수 있다** — 이 사이클의 정적 Match Rate는
   99%였다. 실 LLM 프로브 3개를 Report 전에 돌린 것이 Critical 3건(C1 포함)을
   전부 찾아냈다.

## 다음에 적용하는 법

1. **structured output 스키마를 새로 만들면 자유 키 dict 재귀 탐색 테스트를 짝으로
   만든다** (test_schemas.py:189-260 복사 가능). `dict[str, X]` 타입 필드가 필요하면
   key/value 객체 배열로 바꾸고 도메인 쪽에서만 dict로 변환한다.
2. **fake로만 검증한 외부 연동은 미검증으로 간주한다.** 미배선 모듈이라도 Report 전에
   실 LLM 호출 1회를 DoD에 넣는다 — degraded 폴백이 있는 모듈일수록 필수다
   (실패가 조용하기 때문).
3. degraded를 반환하는 모듈을 새로 배선할 때는 **초기에 degraded 비율을 직접
   확인한다.** 로그에는 남지만 아무도 안 본다는 것이 C1의 3개월 은폐 경로였다.
4. 실 LLM 스모크 스크립트 실행 시 Windows 함정 2개: `ChatOpenAI`는 pydantic-settings를
   거치지 않으므로 `.env` 수동 로딩 필요, 콘솔은 `PYTHONIOENCODING=utf-8` 필요
   (cp949로 첫 실행 중단 실증).

## 관련 문서

- LLM 스키마와 도메인 VO 분리(수정 비용 국소화의 전제): `backend/patterns/llm-output-trust-boundary.md`
- degraded 흡수 경계(이 문서는 그 경계의 함정 사례): `backend/patterns/degradation-vs-failure-boundary.md`
- 슬롯 되묻기 계약 자체: `backend/patterns/declared-slot-elicitation.md`
