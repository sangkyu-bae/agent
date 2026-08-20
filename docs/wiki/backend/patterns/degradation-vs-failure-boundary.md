---
title: degraded 로 흡수할 실패 vs 그대로 올릴 실패 — 경계 긋는 법
status: approved
reviewer: 배상규
source_type: conversation
source_refs:
  - idt/src/api/routes/prompt_composer_router.py:1-13 (LLM 실패=200+degraded / DB 실패=예외 전파 명문)
  - idt/src/application/prompt_composer/compose_prompt_use_case.py (try/except 0개 — DB 예외 그대로 전파)
  - idt/src/application/prompt_composer/compose_prompt_use_case.py:167-175 (_usable_intent — 오염 판정은 스냅샷에서도 제외)
  - idt/src/infrastructure/prompt_composer/adapter.py:106-139 (모든 LLM 실패를 degraded로 흡수)
  - idt/src/domain/prompt_composer/interfaces.py:14-31 (PromptGeneratorPort — "예외를 던지지 않는다"를 포트 계약으로 명문화)
  - idt/tests/application/prompt_composer/test_use_case.py::test_storage_failure_propagates_instead_of_degrading
  - idt/tests/application/prompt_composer/test_use_case.py::test_compose_stores_null_snapshot_when_intent_degraded
  - docs/archive/2026-08/prompt-composer/prompt-composer.design.md (§6.2)
  - idt/src/application/agent_create_pipeline/use_case.py:1-13 (try/except는 bind 1곳 — 다단계 적용, ⚠️ 미커밋)
  - idt/tests/application/agent_create_pipeline/test_use_case.py:398 (test_bind_conflict_contract_exception_is_absorbed)
  - docs/archive/2026-08/agent-create-pipeline/agent-create-pipeline.report.md (§1.4 SC-5, FR-06/FR-08)
confidence: 0.85
version: 2
created: 2026-08-18
updated: 2026-08-19
verified_at: 7c3ffdd
---

# degraded 로 흡수할 실패 vs 그대로 올릴 실패 — 경계 긋는 법

## 문제

graceful degradation을 도입하면 "그럼 뭘 degrade하고 뭘 실패시키지?"가 즉시
애매해진다. 전부 흡수하면 호출자가 존재하지 않는 결과를 참조하게 되고, 전부
던지면 부가 기능의 장애가 본 기능을 막는다.

두 번째 문제: 실패를 흡수하는 코드가 **어댑터와 UseCase 두 곳에** 생기면 실패 경로가
2벌이 되어, 어느 쪽이 어떤 실패를 먹는지 아무도 모르게 된다.

## 검증된 사실

### 1. 판별 기준은 "쓸 수 있는 결과가 존재하는가"

`degraded=true` 는 **"품질이 낮지만 쓸 수 있는 결과가 있다"** 는 뜻이다. 이 정의를
기준으로 삼으면 경계가 기계적으로 갈린다.

| 실패 | 결과가 존재하는가 | 처리 |
|---|---|---|
| LLM 예외·타임아웃·스키마 위반·빈 응답 | 규칙기반 폴백 섹션이 있다 | 200 + `degraded=true` + `reason` |
| DB 저장 실패 | `version_id` 를 줄 수 없다 → 없다 | 예외 그대로 전파 → 5xx |

저장 실패를 200으로 위장하면 **호출자가 존재하지 않는 레코드를 참조**한다. 이것이
degraded로 감싸면 안 되는 이유이고, 라우터 독스트링에 계약으로 적혀 있다.

`reason` 문자열(`timeout` / `schema` / `error` / `empty`)을 함께 내면 degraded가
"LLM이 느린 건지 프롬프트가 깨진 건지"를 사후에 구분할 수 있다 — 플래그만으로는 못 한다.

### 2. 흡수 지점은 **어댑터 한 곳**, 그리고 그것을 포트 계약으로 못 박는다

`PromptGeneratorPort` 독스트링이 "**예외를 던지지 않는다**. 모든 실패를 흡수해
degraded=True와 폴백 섹션으로 반환한다"를 계약으로 선언한다. UseCase에는 try/except가
0개이고, 그것을 AST 테스트가 강제한다([[ast-source-contract-tests]]).

이 배치의 부수 효과가 정확히 §1의 경계다 — **UseCase에 try/except가 없으므로
DB 예외는 자동으로 전파된다.** 경계를 조건문으로 표현하지 않고 구조로 표현했다.

어댑터 쪽 흡수는 `except Exception` 을 쓰되(`# noqa: BLE001`), 로그 레벨을 나눈다:
예상 범위(타임아웃·빈 응답)는 `warning`, 그 외는 `error`. 로그에 프롬프트 본문은
남기지 않는다 — 사용자 입력이 섞여 PII 위험이 있다.

### 3. 오염된 입력은 "사용 안 함"에 그치지 말고 **저장에서도 제외**한다

주입된 intent가 `degraded=true` 면 프롬프트에 붙이지 않는 것까지는 자연스럽다.
그런데 `_usable_intent()` 는 **`intent_snapshot` 저장에서도 제외**해 `None` 을
남긴다.

이유: 스냅샷은 "이 버전이 무엇을 근거로 만들어졌는가"의 기록이다. 실제로 쓰이지
않은 오염 판정을 남겨 두면, 나중에 그 레코드를 해석할 때 **쓰인 것처럼 오독**된다.
반대로 정상 intent는 알 수 없는 키까지 **원문 그대로**(verbatim) 저장한다 — 스냅샷을
정규화하면 나중에 추가된 필드가 소급 소실된다.

일반화: **입력을 배제하기로 했다면 그 결정을 관측 기록에도 반영**한다. "쓰지 않았다"와
"기록에 남아 있다"가 어긋나면 그 기록은 나중에 거짓말을 한다.

### 4. 다단계 파이프라인에서도 같은 기준이 단계별로 성립한다 (v2 추가)

agent-create-pipeline(5단계: intent→tools→prompt→create→bind)이 이 경계를 단계
단위로 적용한 확장 사례다 (⚠️ 코드 미커밋):

| 단계 | 실패 시 | 근거 |
|---|---|---|
| intent / tools / prompt (LLM) | 단계 `degraded` + 폴백으로 계속 진행 | 쓸 수 있는 결과(폴백)가 있다 — 흡수는 각 모듈 **어댑터**가 포트 계약으로 |
| prompt 버전 저장 / create (DB) | 예외 그대로 전파 → 5xx | `version_id`/`agent_id`를 줄 수 없다 |
| bind (세션↔에이전트 백필) | **흡수** — `bind_ok=false` + 단계 failed, 200 유지 | 이미 `agent_id`라는 "쓸 수 있는 결과"가 존재 — 백필 실패가 생성 성공을 뒤집으면 안 된다 |

UseCase의 try/except는 **bind 한 곳뿐**이고 그 이유가 모듈 docstring에 계약으로
명문화돼 있다 — §1의 기준("결과가 존재하는가")을 단계마다 물으면 같은 예외(bind)도
기계적으로 갈린다는 실증. bind 흡수는 계약 예외(`AgentAlreadyBoundError`)로 테스트
고정. SSE 경로에서는 전파된 예외를 라우터가 이벤트로 합성한다 —
[[sync-sse-dual-exposure]] §4.

## 다음에 적용하는 법

1. 새 기능에 폴백을 넣기 전에 표를 하나 그린다 — **실패 종류 × "결과가 존재하는가"**.
   존재하면 degraded, 아니면 예외. 애매하면 "호출자가 이 응답으로 다음 동작을 할 수
   있는가"로 되묻는다.
2. **흡수는 딱 한 레이어에서.** 흡수를 맡은 포트 독스트링에 "예외를 던지지 않는다"를
   적고, 호출측 소스에 try/except가 없음을 AST 테스트로 고정한다.
3. degraded 플래그와 **`reason` 문자열을 세트로** 낸다. 응답 스키마에도 노출한다.
4. 부분 성공을 만들지 않는다 — 폴백은 "이 모듈이 없던 상태"로 정의한다
   ([[detachable-module-seam]] §2).
5. 오염·미사용으로 판정한 입력은 프롬프트뿐 아니라 **스냅샷·로그 등 모든 영속
   기록에서 일관되게 뺀다.** 반대로 정상 입력은 정규화 없이 원문 저장.
6. 이 경계를 테스트 2개로 고정한다 — `degraded 결과도 저장된다`,
   `저장 실패는 degrade하지 않고 전파된다`.

## 관련 문서

- LLM 산출물과 계산 필드 분리: `backend/patterns/llm-output-trust-boundary.md`
- 계약을 AST로 강제: `backend/patterns/ast-source-contract-tests.md`
- 폴백=모듈 부재 상태: `backend/patterns/detachable-module-seam.md`
- 예외 로깅 규약: `backend/patterns/structured-logger-warning-exception.md`
