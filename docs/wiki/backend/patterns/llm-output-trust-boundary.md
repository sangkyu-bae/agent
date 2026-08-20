---
title: LLM 출력 신뢰 경계 — 계산 필드는 스키마에서 빼고, 금지는 코드가 집행한다
status: approved
reviewer: 배상규
source_type: conversation
source_refs:
  - idt/src/infrastructure/prompt_composer/adapter.py:42-72 (_PromptDraft / _GuideDraft — 계산 필드·name 부재)
  - idt/src/infrastructure/prompt_composer/adapter.py:211-242 (_to_sections — 표기 이름을 카탈로그에서 채움)
  - idt/src/infrastructure/prompt_composer/prompts.py:24-27 (프롬프트 지시는 2차 방어선이라는 명문)
  - idt/src/domain/prompt_composer/policies.py:59-77 (drop_hallucinated — 실제 차단은 코드)
  - idt/src/infrastructure/intent/adapter.py:1-14 (선행 사이클 — 겸용 + 3층 방어가 확장에 실패한 기록)
  - idt/tests/infrastructure/prompt_composer/test_adapter.py:93-115 (필드 집합 동등 비교 테스트)
  - docs/archive/2026-08/prompt-composer/prompt-composer.design.md (§1.3 · §2.4 P2/P3)
confidence: 0.85
version: 1
created: 2026-08-18
updated: 2026-08-18
verified_at: 7c3ffdd
---

# LLM 출력 신뢰 경계 — 계산 필드는 스키마에서 빼고, 금지는 코드가 집행한다

## 문제

`with_structured_output(SomeModel)` 을 쓸 때, 그 `SomeModel` 을 그대로 도메인 결과
객체로 재사용하고 싶어진다(스키마가 하나면 매핑 코드가 없으니까). 그런데 도메인
결과에는 **시스템이 계산하는 필드**가 섞여 있다 — `degraded`, `dropped_tool_ids`,
`unknown_tool_ids`, `elapsed_ms` 같은 것들. 스키마에 있으면 LLM이 그 필드를 채울 수
있고, 채우면 "LLM이 스스로 성공/실패를 보고"하는 신뢰 구멍이 생긴다.

같은 문제의 다른 얼굴: 프롬프트에 "목록에 없는 도구를 지어내지 마세요"라고 써 두고
그것을 방어로 착각하는 것.

## 검증된 사실

### 1. "겸용 + 방어 코드"는 계산 필드가 늘면 무너진다 (선행 사이클의 실패 기록)

intent 모듈은 `IntentResult` 하나를 LLM 스키마와 도메인 VO로 겸용하고, 대신
호출측이 `raw.degraded` 를 **읽지 않는** 3층 방어를 쌓았다. 그 방식은 계산 필드가
`missing_slots` / `complete` / `degraded` 3개로 늘면서 확장에 실패했고, 이 실패가
`infrastructure/intent/adapter.py:1-14` 독스트링에 명시적으로 남아 있다.

방어 코드는 **필드마다 1개씩 늘어나고, 새 필드를 추가할 때 빼먹으면 조용히 뚫린다.**

### 2. 유일하게 확장되는 방어는 "필드를 두지 않는 것"

prompt_composer는 LLM이 보는 스키마(`_PromptDraft`)에 4개 섹션(`purpose` / `roles` /
`tool_guides` / `principles`)만 두고, 계산 필드는 **아예 넣지 않았다**. 값이 오염될
경로 자체가 존재하지 않으므로 방어 코드가 0줄이다.

어댑터의 반환 타입이 그 분리를 강제한다:

```
generate(...) -> tuple[PromptSections, bool, str | None, int]
                        └ LLM 산출   └ degraded  └ reason  └ elapsed_ms
```

계산값은 **튜플의 별도 자리**로 나오지 LLM 산출물 안에 섞이지 않는다.

이 모듈은 결과를 DB에 영속하므로(`prompt_version`) 대가가 더 크다 — 오염값이 되돌릴
수 없게 남는다. **LLM 결과를 저장하는 기능이면 겸용을 더더욱 하지 않는다.**

### 3. 표시용 이름도 LLM에게 주지 않는다

`_GuideDraft` 에는 `name` 필드가 **없다**. `tool_id` 만 받고, 사람이 보는 이름은
`_to_sections()` 가 카탈로그 메타(`by_id[tool_id].name`)에서 채운다. 결과적으로
LLM이 도구를 개명할 수 없다.

일반화: **어떤 값의 소유자가 이미 시스템 안에 있으면(카탈로그·DB·설정) 그 필드는
LLM 스키마에서 뺀다.** LLM은 "무엇을 참조할지"(ID)만 고르게 하고 표기는 소유자가 준다.

### 4. 프롬프트 지시는 2차 방어선이다 — 1차는 코드

프롬프트에 "위 도구 목록에 있는 tool_id만 사용하세요. 목록에 없는 도구를 지어내지
마세요"가 들어 있지만, 실제 차단은 `PromptAssemblyPolicy.drop_hallucinated()` 가
후보 밖 `tool_id` 를 **실제로 폐기**하고 폐기 목록을 `dropped_tool_ids` 관측 필드로
남기는 것이다. `prompts.py` 상단 주석이 이 역할 분담을 명문으로 적고 있다.

책임 분리도 지켜졌다: 매핑 함수(`_to_sections`)는 거르지 않고, 폐기·관측은 도메인
정책 한 곳에서만 한다.

### 5. 검증은 "없음 확인"이 아니라 **필드 집합 동등 비교**

```python
assert set(_PromptDraft.model_fields) == {"purpose", "roles", "tool_guides", "principles"}
```

`assert "degraded" not in model_fields` 만 두면 **나중에 추가되는 새 계산 필드는
못 잡는다.** 동등 비교로 두면 스키마에 무엇이든 추가하는 순간 테스트가 깨지고,
"이 필드를 LLM에게 보여도 되는가"를 강제로 한 번 생각하게 된다.
(개별 필드 부재 테스트는 실패 메시지를 읽기 쉽게 하는 보조로 함께 두면 좋다.)

## 이전 안을 버린 이유 (ADR)

- **버린 안**: LLM 스키마와 도메인 결과 객체를 겸용하고, 호출측이 오염 가능 필드를
  읽지 않는 규율(3층 방어)로 막는다 — [[detachable-module-seam]] §3에 기록된 안.
- **버린 이유**: 방어의 개수가 필드 수에 비례해 늘고, 새 필드를 추가할 때 방어를
  빼먹으면 조용히 뚫린다. 실제로 계산 필드가 3개로 늘면서 실패했다. 규율은 사람이
  지켜야 하지만, 필드 부재는 타입 시스템이 지킨다.
- **대체안**: Draft(LLM 전용) / Result(도메인)를 분리하고, 변환 함수 1개만 둔다.
  매핑 코드가 20줄 늘지만 방어 코드와 그 규율이 0이 된다.

## 다음에 적용하는 법

1. LLM 구조화 출력 스키마를 정의할 때 필드마다 묻는다 — **"이 값을 LLM이 정하는가,
   시스템이 정하는가?"** 시스템이 정하면 스키마에서 뺀다.
2. 어댑터 반환은 `(도메인VO, 계산값들...)` 튜플이나 별도 래퍼로. LLM 산출물과
   계산값이 한 객체에 섞이지 않게 한다.
3. 스키마 필드 집합을 **동등 비교하는 단위 테스트 1개**를 반드시 같이 만든다.
4. 프롬프트에 금지 문구를 넣더라도 **같은 규칙을 강제하는 코드(폐기 + 관측 필드)를
   반드시 짝으로 넣는다.** 프롬프트만 있는 규칙은 규칙이 아니다.
5. 관측 필드(`dropped_*`, `unknown_*`)는 응답·저장 스키마에 남긴다 — 프롬프트가
   실제로 통하는지는 이 값의 분포로만 사후 확인할 수 있다.

## 관련 문서

- 실패를 어디까지 흡수할지: `backend/patterns/degradation-vs-failure-boundary.md`
- 계약을 테스트로 못박는 법: `backend/patterns/ast-source-contract-tests.md`
- 탈착형 이음매(§3은 이 문서로 대체됨): `backend/patterns/detachable-module-seam.md`
