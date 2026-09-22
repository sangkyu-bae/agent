# Plan — prompt-fallback-visibility

> Feature: `prompt-fallback-visibility`
> Created: 2026-09-20
> Phase: plan
> 선행: [[pipeline-langsmith-tracing]] — 관측성이 먼저 들어가야 원인 규명이 가능

---

## Executive Summary

| 관점 | 내용 |
|---|---|
| **Problem** | 에이전트 생성 시 PROMPT 단계 LLM 호출이 실패하면 규칙기반 폴백이 **그럴듯한 형태의 무의미한 프롬프트**를 내놓는다. degraded 신호는 응답에 있으나 사용자가 알아채지 못한 채 그 프롬프트로 에이전트를 저장할 수 있다. |
| **Solution** | 폴백 문구는 관측성 설계 의도대로 **유지**하고, degraded 프롬프트의 **저장 경로를 차단**한다. 동시에 실패 사유를 사용자가 볼 수 있게 노출하고 재시도 경로를 제공한다. |
| **Function UX Effect** | degraded 프롬프트로는 "스튜디오로 보내기"/"저장"이 막히고, 실패 사유와 "다시 생성" 버튼이 전면에 노출된다. |
| **Core Value** | **실패를 실패로 보이게 한다.** 현재는 실패가 성공처럼 보여 사용자가 빈 껍데기 에이전트를 만들게 된다. |

---

## Context Anchor

| 축 | 내용 |
|---|---|
| **WHY** | 사용자가 받은 프롬프트는 `PromptAssemblyPolicy.fallback_sections()` 출력과 **바이트 단위로 일치**한다 — LLM 생성 결과가 아니라 실패의 산물이다. 그런데 사용자는 그것을 "품질 낮은 생성 결과"로 인식했다. |
| **WHO** | P2(KB 운영자/에이전트 소유자) — 자연어로 에이전트를 만드는 주체. |
| **RISK** | 저장 차단이 과하면 "일단 만들고 고치기" 흐름을 막는다. 폴백 문구 변경은 명시적 설계 결정(prompt-depth §5.1 A-6)을 뒤집는 일이다. |
| **SUCCESS** | degraded 프롬프트가 저장으로 흘러가지 않고, 사용자가 실패 사유를 읽고 재시도할 수 있다. |
| **SCOPE** | 폴백 **가시성과 저장 차단**. LLM 프롬프트 품질 튜닝은 원인 규명 후 별건. |

---

## 1. Overview

### 1-1. 근본 원인 — 피드백의 진단과 코드가 다르다

받은 피드백은 *"compose가 정보량 적은 요청을 generic fallback 문구로 메워서 빈 껍데기를 만들었다"*, *"AgentPlanner가 이 케이스용이다"*라고 진단했다. **코드 대조 결과 둘 다 사실이 아니다.**

#### (a) 붙여진 프롬프트는 LLM 출력이 아니다

`src/domain/prompt_composer/policies.py`의 모듈 상수와 바이트 단위로 일치한다:

| 사용자가 받은 문장 | 소스 |
|---|---|
| "사용자의 요청을 처리하는 에이전트입니다. 요청 요약: …" | `:43-44` `_FALLBACK_PURPOSE_BASE` + `_FALLBACK_REQUEST_PREFIX` |
| "사용자의 요청을 처리하는 **범용** 에이전트입니다." | `:51` `_FALLBACK_IDENTITY` |
| "제공된 제약 조건이 없으므로 일반적인 안전 기준을 따른다" | `:52-54` `_FALLBACK_CONTEXT` |
| "요청 처리: 사용자의 요청을 확인하고 가능한 범위에서 답한다" | `:55-60` `_FALLBACK_ROLES` |
| "요청 내용을 확인한다 / 필요하면 도구를 사용한다 / 결과를 정리해 답한다" | `:62-71` `_FALLBACK_WORKFLOWS` |
| "한국어로 간결하게 답한다." | `:72` `_FALLBACK_STYLE` |
| 마지막 3줄 | `:73-77` `_FALLBACK_PRINCIPLES` |

즉 **PROMPT 단계 LLM 호출이 통째로 실패했다** (`prompt_composer/adapter.py:189-208`). 실패 사유는 4가지 중 하나:

| reason | 조건 | 위치 |
|---|---|---|
| `timeout` | `PROMPT_COMPOSER_TIMEOUT_SEC` (기본 20초) 초과 | `adapter.py:196-200` |
| `schema` | pydantic `ValidationError` | `:201-204`, `_is_schema_error:357` |
| `error` | 그 외 모든 예외 | `:201-204` |
| `empty` | `draft.purpose`가 빈 문자열 | `:206-208` |

#### (b) "Tool Guidelines가 description 복붙"도 폴백 동작이다

`policies.py:232-241` — 폴백은 `when=meta.description, how="", caution=""`로 채운다. 정상 경로(`adapter.py:_to_sections`)는 LLM이 `when`/`how`/`caution`을 **각각 생성**한다. 즉 피드백이 지적한 "복붙"은 정상 경로의 결함이 아니다.

#### (c) `AgentPlanner`는 다른 경로 소속이다

| | A. 위저드 | B. Fix 패널 |
|---|---|---|
| 화면 | **`/agent-builder/new`** ← 이번 사건 | `/agent-builder` 우측 탭 |
| 엔드포인트 | `POST /api/v1/agents/pipeline/stream` | `POST /api/v1/agents/compose` |
| 되물음 담당 | `IntentUseCase` + `PipelinePolicy.decide_after_intent` | **`AgentPlanner`** |

`AgentPlanner`를 손봐도 위저드 경로에는 아무 영향이 없다.

### 1-2. degraded 신호는 이미 존재한다

| 계층 | 신호 |
|---|---|
| 도메인 | `generate()`가 `(sections, degraded=True, reason, elapsed)` 반환 |
| UseCase | `use_case.py:270-276` `StageRecord(PROMPT, StageStatus.DEGRADED, reason)` |
| 응답 | `steps[].status="degraded"` + `steps[].reason`, `degraded_stages: ["prompt"]` |
| 로그 | `adapter.py:284-289` `"prompt generation {reason}, fallback=degraded"` |
| 프론트 | `PromptStep.tsx:52` degraded 안내 배너, `WizardProgress` 사유 배지 |

**문제는 신호의 부재가 아니라 신호의 약함이다.** 사용자는 배너를 보지 못했다고 확인했다.

### 1-3. 폴백 문구는 의도적 설계다 (변경 금지 결정)

`policies.py:47-50` (prompt-depth §5.1 A-6):

> *"폴백은 고정 문구로 7섹션을 전부 채운다. 값이 전부 모듈 상수라는 사실이 폴백 관측성을 유지한다: 요청이 달라도 같은 문구가 나오므로 출력만 보고 폴백임을 식별할 수 있다."*

피드백의 *"채울 내용이 없는 섹션은 filler로 채우지 말고 섹션 자체를 생략"* 제안은 이 결정과 정면 충돌한다.

**사용자 결정: 폴백 문구 유지 + 저장 차단.** 이 Plan은 그 결정을 따른다.

### 1-4. 선례 — 이 실패 모드는 이미 한 번 일어났다

`prompt_composer/adapter.py:94-100` (`_PromptDraft` docstring):

> *"이 스키마의 재귀 전개에 자유 키 dict가 0건이어야 한다. 하나라도 있으면 OpenAI structured outputs가 매 호출 400을 돌려 판정이 **항상** degraded로 떨어지고, **폴백이 그 사실을 가린다** (intent 모듈에서 3개월 은폐된 실사례)."*

동일 은폐 구조가 재발했을 가능성이 있다. **이것이 [[pipeline-langsmith-tracing]]을 선행 feature로 둔 이유다.**

---

## 2. Scope

### In Scope

1. degraded 프롬프트의 저장 경로 차단 (위저드 → 스튜디오 인계, 스튜디오 저장)
2. 실패 사유의 사용자 가시성 강화 (배너 → 차단형 UI, reason 한국어화)
3. 재시도 경로 제공
4. **실패 원인 규명** — 재현 후 근본 원인 수정

### Out of Scope

- 폴백 문구 내용 변경 (§1-3 결정에 따라 **유지**)
- 섹션 생략 규칙 도입 (동일)
- `AgentPlanner` 수정 (§1-1(c) — 다른 경로)
- B 경로(`/compose`) 품질 개선
- 정상 경로 LLM 프롬프트(`prompts.SYSTEM`) 튜닝 → 원인 규명 후 필요 시 별건

---

## 3. Requirements

### FR — 기능 요구사항

| ID | 요구사항 | 근거 |
|---|---|---|
| FR-01 | `prompt` 단계가 degraded면 위저드의 "스튜디오로 보내기"를 **비활성화**한다. | `PromptStep.tsx:137-141` |
| FR-02 | degraded 상태를 안내 배너가 아니라 **차단형 UI**로 제시한다 — 실패 사유 + "다시 생성" 버튼을 주 동선에 둔다. | `PromptStep.tsx:52` |
| FR-03 | `reason` 코드(`timeout`/`schema`/`empty`/`error`)를 사용자가 읽을 수 있는 한국어 문구로 매핑한다. 재시도 가능 여부를 구분해 안내한다(타임아웃은 재시도 권장, 스키마 오류는 관리자 문의). | `adapter.py:39-42` |
| FR-04 | 서버 측에서도 degraded 프롬프트의 저장을 막는다 — **프론트 차단만으로는 API 직접 호출을 못 막는다.** 차단 위치·강도는 Design에서 결정(§7-2). | — |
| FR-05 | 사용자가 degraded 프롬프트를 **직접 편집**해 정상화한 경우는 저장을 허용한다. 실패를 막되 사람의 수정 경로는 남긴다. | `promptEdited` 상태 존재 |
| FR-06 | "다시 생성"은 기존 `handleRegeneratePrompt`(`index.tsx:291`) 경로를 재사용한다. | — |
| FR-07 | **실패 원인을 재현·규명하고 근본 수정한다.** 규명 전까지 FR-01~06은 증상 완화일 뿐임을 명시한다. | §1-4 |

### NFR

| ID | 요구사항 |
|---|---|
| NFR-01 | 폴백 문구 상수는 변경하지 않는다 (§1-3). |
| NFR-02 | `tools` 단계 degraded는 저장 차단 대상이 **아니다** — 도구 추천 실패는 "쓸 수 있는 결과"가 존재한다(`main.py:2581-2583` 주석의 판정 기준). |
| NFR-03 | 백엔드 스키마 변경 시 프론트 타입 동기화 (루트 CLAUDE.md §4-1, `/api-contract-sync`). |

---

## 4. Success Criteria

> **갱신 (2026-09-21, Check)**: Design 단계에서 근본 원인이 규명되어 **module-0
> (`root-cause-fix`)** 가 신설되었다. 아래 SC-00a~c 가 그 판정 기준이며,
> SC-01~05 는 module-1/2 소관이다.

| ID | 기준 | 검증 | 모듈 |
|---|---|---|---|
| SC-00a | 보조 LLM 모델이 명시되어 관리자의 기본 모델 변경이 프롬프트 생성에 전파되지 않는다 | 설정 + 코드 | module-0 |
| SC-00b | 프롬프트 생성 타임아웃이 실측 분포 기준으로 재산정된다 | 실측 | module-0 |
| SC-00c | 어떤 모델로 돌고 있는지, 어떤 예산에서 실패했는지가 로그만으로 드러난다 | 단위 테스트 | module-0 |

| ID | 기준 | 검증 |
|---|---|---|
| SC-01 | PROMPT 단계 실패를 주입하면 "스튜디오로 보내기"가 비활성화되고 실패 사유가 화면 주 영역에 보인다. | MSW 목 + RTL |
| SC-02 | degraded 프롬프트를 편집하지 않은 채 `POST /api/v1/agents`를 직접 호출하면 거부된다. | pytest |
| SC-03 | 사용자가 프롬프트를 편집하면 저장이 허용된다. | pytest + RTL |
| SC-04 | "다시 생성"으로 성공하면 차단이 해제되고 정상 흐름으로 복귀한다. | RTL |
| SC-05 | 4개 `reason` 각각에 고유한 한국어 안내가 대응된다. | 단위 테스트 |
| SC-06 | **실패 원인이 특정되고 재발 방지 테스트가 추가된다.** | Do 단계 산출물 |
| SC-07 | `tools` degraded는 저장을 막지 않는다. | 회귀 테스트 |

---

## 5. Risks and Mitigation

| 위험 | 영향 | 완화 |
|---|---|---|
| **원인 규명 실패** | FR-01~06만 하면 증상만 가림 | [[pipeline-langsmith-tracing]]을 선행. 그래도 못 잡으면 Do 단계에서 재현 스크립트를 먼저 만든다 |
| 저장 차단이 과함 | "일단 만들고 고치기" 흐름 차단 | FR-05로 편집 후 저장 허용. Design에서 차단 강도 3안 비교 |
| 서버 차단 위치가 부적절 | `POST /api/v1/agents`는 위저드 전용이 아님 — B 경로·수동 생성도 통과 | §7-2에서 별도 설계. **폴백 문구 문자열 매칭은 취약**하므로 지양 |
| 프론트만 막고 서버를 안 막음 | API 직접 호출로 우회 | FR-04 필수 |
| 폴백 문구 유지 결정이 UX와 충돌 | 사용자가 계속 "품질 낮은 생성"으로 오인 | FR-02 차단형 UI가 "이건 생성 결과가 아니다"를 명시 |

---

## 6. Impact Analysis

### 백엔드 (`idt/`)

| 파일 | 변경 |
|---|---|
| `src/application/agent_builder/create_agent_use_case.py` | FR-04 검증 추가 (Step 3 근처, `:216`) |
| `src/domain/agent_builder/policies.py` 또는 신규 | degraded 판정 규칙 |
| `src/interfaces/schemas/` · `agent_builder` 요청 스키마 | degraded 플래그 전달 필드 (설계안에 따라) |

### 프론트 (`idt_front/`)

| 파일 | 변경 |
|---|---|
| `src/pages/AgentCreateEntryPage/components/PromptStep.tsx` | FR-01/02/03 |
| `src/pages/AgentCreateEntryPage/index.tsx` | `promptDegraded` 기반 인계 차단 (`:309 handleSendToStudio`) |
| `src/pages/AgentBuilderPage/index.tsx` | 저장 버튼 가드 (`:245 handleSave`) |
| `src/store/agentDraftStore.ts` | degraded 플래그 인계 |
| `src/types/agentPipeline.ts` / `agentBuilder.ts` | 타입 동기화 |

> ⚠️ 백엔드 요청 스키마가 바뀌면 **`/api-contract-sync` 필수** (루트 CLAUDE.md §4-1).

---

## 7. Architecture Considerations

### 7-1. 차단 강도 — Design에서 3안 비교

| 안 | 내용 | 트레이드오프 |
|---|---|---|
| A (최소) | 프론트만 차단 | 빠름. API 우회 가능 → FR-04 미충족 |
| B (권장 후보) | 프론트 차단 + 서버가 degraded 플래그를 신뢰해 거부 | 균형적. 클라이언트가 보내는 플래그를 신뢰한다는 약점 |
| C (엄격) | 서버가 프롬프트 세션(`prompt_composer` 세션)에서 degraded 여부를 **재조회**해 판정 | 위변조 불가. 세션 조회 의존이 생기고 세션 없는 수동 생성 경로 처리가 필요 |

**핵심 쟁점**: `POST /api/v1/agents`는 위저드 전용이 아니다. 수동 생성·B 경로·API 직접 사용도 통과한다. 세션이 없는 요청을 어떻게 다룰지가 C안의 관건이다.

### 7-2. 폴백 문자열 매칭은 쓰지 않는다

"저장하려는 프롬프트가 폴백 상수와 일치하는가"로 판정하는 방식은 유혹적이지만:
- 사용자가 한 글자만 고쳐도 우회된다
- 폴백 문구를 나중에 바꾸면 조용히 깨진다
- `policies.py`의 상수에 도메인 밖 의존이 생긴다

**플래그 기반 판정으로 간다.**

### 7-3. 레이어

degraded 판정은 **도메인 규칙**이므로 `domain/`에 둔다. `create_agent_use_case`는 호출만 한다 (CLAUDE.md §2: application은 비즈니스 규칙 직접 구현 금지).

---

## 8. Convention Prerequisites

- **TDD 필수** — 백엔드 pytest, 프론트 Vitest + RTL + MSW (루트 CLAUDE.md §4-4)
- API 스키마 변경 시 프론트 타입 동기화 (§4-1)
- `docs/wiki/_INDEX.md`의 `degradation-vs-failure-boundary` 문서를 Design 전에 읽는다 — `prompt_composer/policies.py`가 이 문서를 판정 원칙의 출처로 참조한다
- 함수 40줄 / if 중첩 2단계 / logger 필수

---

## 9. Next Steps

### 9-1. 사용자 확인 필요 (Design 진입 전)

| # | 질문 |
|---|---|
| 1 | **차단 강도**: §7-1의 A/B/C 중 어느 선인가? C안은 세션 없는 수동 생성 경로 처리 설계가 추가로 필요하다. |
| 2 | **`tools` degraded 처리**: NFR-02대로 저장을 허용하는 게 맞는가? 도구 추천이 실패해 사용자가 지정한 도구만 들어간 에이전트도 "정상"으로 볼 것인지. |
| 3 | **재현 우선순위**: 원인 규명(FR-07)을 Do의 첫 항목으로 놓고 결과에 따라 나머지 범위를 조정할지, 아니면 차단 UI를 먼저 넣어 피해를 막고 병행할지. |
| 4 | **피드백 처리**: 받은 피드백 중 "섹션 생략", "generic 문구 lint", "AgentPlanner 재질문 트리거"는 이번 진단에 따라 **채택하지 않는다**. 이 판단에 동의하는지 — 특히 "generic 문구 lint"는 폴백 탐지 수단으로 재해석하면 살릴 여지가 있다. |

### 9-2. 실행 순서 권장

```
1) /pdca design pipeline-langsmith-tracing   ← 관측성 먼저
2) /pdca do   pipeline-langsmith-tracing
3) 실패 재현 + LangSmith로 원인 규명
4) /pdca design prompt-fallback-visibility   ← 규명 결과 반영해 설계
```

---

## Version History

| 버전 | 일자 | 내용 |
|---|---|---|
| 0.1 | 2026-09-20 | 최초 작성. 피드백 진단을 코드 대조로 정정. |
