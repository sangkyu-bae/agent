# Design — prompt-fallback-visibility

> Feature: `prompt-fallback-visibility`
> Created: 2026-09-20
> Phase: design
> Plan: `docs/01-plan/features/prompt-fallback-visibility.plan.md`
> 선택 아키텍처: **Option C — 서버가 DB 재조회로 판정**
> 선행: [[pipeline-langsmith-tracing]] (module-1~3 완료)

---

## Context Anchor

| 축 | 내용 |
|---|---|
| **WHY** | 사용자가 받은 프롬프트는 `PromptAssemblyPolicy.fallback_sections()` 출력과 바이트 단위로 일치한다 — LLM 생성 결과가 아니라 실패의 산물이다. |
| **WHO** | P2(KB 운영자/에이전트 소유자) — 자연어로 에이전트를 만드는 주체. |
| **RISK** | 저장 차단이 과하면 "일단 만들고 고치기" 흐름을 막는다. 폴백 문구 변경은 명시적 설계 결정(prompt-depth §5.1 A-6)을 뒤집는 일이다. |
| **SUCCESS** | degraded 프롬프트가 저장으로 흘러가지 않고, 사용자가 실패 사유를 읽고 재시도할 수 있다. |
| **SCOPE** | ~~폴백 가시성과 저장 차단~~ → **근본 원인 수정 + 차단·가시성** (§1-1에서 확장) |

---

## 1. Overview

### 1-1. ★ Design 단계에서 근본 원인이 규명되었다 — 스코프 확장

Plan FR-07("실패 원인을 재현·규명한다")을 Do가 아니라 **Design에서 완료**했다.
`prompt_version` 테이블에 증거가 이미 쌓여 있었다.

**DB 실측 (로컬, 2026-09-20)**

```
prompt_version 전체 : 18
degraded=1          : 4
reason 분포         : 'timeout' × 4     ← 100%
source 분포         : llm/degraded=0 14 | llm/degraded=1 4 | human 0
```

| 월 | 성공 | 타임아웃 |
|---|---|---|
| 2026-08 | 13 | **0** |
| 2026-09 | 1 | **4** |

degraded 4건의 `elapsed_ms`: **20000 / 20016 / 20023 / 20030** — 전부
`PROMPT_COMPOSER_TIMEOUT_SEC = 20.0` 벽에 정확히 붙었다.
성공 건 분포는 5692 ~ **14549** ms (중앙값 ~9초) — 8월에도 여유가 5.5초뿐이었다.

**원인 체인 (전부 코드·DB로 확인)**

```
.env 에 UTILITY_LLM_MODEL_NAME 없음
   → src/config.py:37  utility_llm_model_name = None
   → UtilityLLMProvider._resolve_model()   utility_llm_provider.py:105-118
     name 이 없으므로 _resolve_default() — llm_model 테이블의 is_default=1
   → llm_model: openai/gpt-5.1  is_default=1  updated_at = 2026-09-04 10:50:09
   → prompt_version 첫 timeout   created_at = 2026-09-04 10:52:25   (2분 16초 후)
   → prompt_composer/adapter.py:193-200  asyncio.wait_for(..., timeout=20.0) 초과
   → _degrade(_REASON_TIMEOUT) → PromptAssemblyPolicy.fallback_sections()
```

**따라서 진단이 두 번 교정되었다:**

| 단계 | 진단 | 판정 |
|---|---|---|
| 받은 피드백 | "compose가 정보량 적은 요청을 generic 문구로 메웠다" | ❌ LLM 출력이 아예 없었다 |
| Plan §1-1 | "PROMPT 단계 LLM 호출이 실패했다 (원인 미상)" | △ 맞지만 절반 |
| **Design §1-1** | **"관리자가 기본 LLM을 추론 모델로 바꾸자 보조 작업용 20초 타임아웃이 뚫렸다"** | ✅ |

**차단 UI만으로는 80% 실패율이 해결되지 않는다.** 사용자 결정에 따라
근본 수정을 module-0으로 앞에 둔다.

### 1-2. 설계 결정 요약

| # | 결정 | 근거 |
|---|---|---|
| D1 | **module-0 근본 수정을 최우선** — 보조 모델 명시 + 타임아웃 재산정 | §1-1 |
| D2 | **Option C** — 서버가 `prompt_version`을 재조회해 판정 | 클라이언트 플래그는 위변조 가능 |
| D3 | 편집 여부는 **저장본과 제출본의 내용 비교**로 판정 | 저장 시점에 `human` 버전이 아직 없다 (§2-3) |
| D4 | 폴백 문구는 **변경하지 않는다** | prompt-depth §5.1 A-6 관측성 결정 유지 (Plan §1-3, 사용자 확정) |
| D5 | `tools` degraded는 **차단하지 않는다** | "쓸 수 있는 결과"가 존재 (Plan NFR-02, 사용자 확정) |

---

## 2. 현황 — 설계를 결정한 코드 사실

### 2-1. degraded는 이미 DB에 영속된다

`src/infrastructure/prompt_composer/models.py`

| 컬럼 | 라인 | 내용 |
|---|---|---|
| `degraded` | `:133` | `"LLM 실패로 규칙기반 폴백이 쓰였는지 여부"` |
| `reason` | `:141` | `"degraded 사유(error\|timeout\|schema\|empty)"` |
| `assembled` | `:114` | `"서버가 결정적으로 조립한 최종 시스템 프롬프트 문자열"` |
| `source` | `:104` | `llm` \| `human` |
| `elapsed_ms` | `:146` | 관측용 |

→ **서버가 클라이언트 말을 믿을 필요가 없다.** Plan §7-1이 "세션 조회 의존이
생긴다"며 비싸게 봤던 Option C가 실제로는 가장 저렴하다.

### 2-2. `version_id`가 이미 응답·프론트에 흐른다

```
use_case.py:370  _stopped_outcome(... version_id=compose.version_id)
  → AgentPipelineResponse.version_id
  → index.tsx:175-189  setState({ versionId })
  → index.tsx:124  goStudio({ result: { sessionId, versionId, ... } })
  → agentDraftStore → AgentBuilderPage
```

→ 프론트가 이미 들고 있으므로 요청에 실어 보내는 데 추가 배선이 없다.

### 2-3. 저장 시점에는 `human` 버전이 없다 (D3의 근거)

`idt_front/src/pages/AgentBuilderPage/index.tsx`

```
:331  createMutation.mutate(...)        ← 저장
:400  await linkPromptSession(...)      ← 그 다음에야 human 버전 append
:63     if (wizard.promptEdited) → POST /prompt-composer/sessions/{id}/versions
```

→ `source == 'human'` 으로는 "편집했는가"를 저장 시점에 판정할 수 없다.
DB 실측에서도 `human` 버전은 **0건**이다. 따라서 D3(내용 비교)을 택한다.

### 2-4. `CreateAgentRequest`에는 세션 식별자가 없다

`src/application/agent_builder/schemas.py:95-128` — `prompt_session_id`도
`prompt_version_id`도 없다. → **API 계약 변경이 필요**하다 (§5).

### 2-5. degraded 신호는 이미 있으나 약하다

| 계층 | 신호 | 위치 |
|---|---|---|
| 응답 | `steps[].status="degraded"`, `steps[].reason`, `degraded_stages` | `agent_pipeline_router.py:228` |
| 프론트 | 안내 배너 | `PromptStep.tsx:52` |
| 프론트 | 진행바 사유 배지 | `WizardProgress` |
| 로그 | `"prompt generation timeout, fallback=degraded"` | `adapter.py:284-289` |

문제는 신호의 부재가 아니라 **약함**이다 — 사용자는 배너를 보지 못했다.

---

## 3. Requirements → 설계 매핑

### module-0 — 근본 수정 (신규, Plan에 없던 항목)

| ID | 요구사항 | 근거 |
|---|---|---|
| FR-00a | `UTILITY_LLM_MODEL_NAME`을 빠른 모델로 **명시 설정**한다. 관리자의 기본 모델 변경이 보조 작업(프롬프트 생성·의도 판정)에 전파되지 않게 분리한다. | §1-1 원인 체인 |
| FR-00b | `PROMPT_COMPOSER_TIMEOUT_SEC`을 관측 분포 기준으로 재산정한다. 성공 최대 14.5초 / 중앙값 9초 → 20초는 여유 1.4배에 불과하다. | §1-1 분포 |
| FR-00c | `UtilityLLMProvider`가 기본 모델로 폴백할 때 **어떤 모델을 쓰는지 로그에 남긴다**. 현재는 무로그라 모델이 바뀐 사실이 관측되지 않는다. | `utility_llm_provider.py:118` |
| FR-00d | `_degrade` 로그에 **실사용 모델명과 타임아웃 값**을 포함한다. | `adapter.py:284-289` |

> ⚠️ FR-00a/00b의 **구체 값은 Do에서 실측 후 확정**한다. gpt-5.1의 실제 지연을
> 모른 채 숫자를 못 박으면 같은 사고가 반복된다 (§9-1).

### module-1 — 서버 차단 (Option C)

| ID | 요구사항 |
|---|---|
| FR-01 | `CreateAgentRequest`에 `prompt_version_id: str \| None = None`을 추가한다. |
| FR-02 | `prompt_version_id`가 주어지면 서버가 해당 버전을 조회한다. 없거나 타인 소유면 **검증을 건너뛴다**(404를 내지 않는다 — 생성 실패로 번지면 안 된다). |
| FR-03 | 조회된 버전이 `degraded=True`이고, 제출 `system_prompt`가 저장된 `assembled`와 **같으면** 422로 거부한다. |
| FR-04 | 비교는 `PipelinePolicy.clamp_prompt()`를 **양쪽에 동일 적용한 뒤** 앞뒤 공백을 제거하고 수행한다 — 응답은 clamp된 값이, DB는 원본이 담긴다 (§7-1). |
| FR-05 | 내용이 다르면 사용자가 편집한 것이므로 **허용**한다. |
| FR-06 | `prompt_version_id`가 없는 요청(수동 생성·Fix 경로·API 직접)은 **그대로 통과**한다 — 검증할 근거가 없다. |
| FR-07 | 422 응답 본문에 `reason`(timeout 등)을 담아 프론트가 사유를 표시할 수 있게 한다. |

### module-2 — 프론트 가시성·차단

| ID | 요구사항 |
|---|---|
| FR-10 | `prompt` 단계가 degraded면 `PromptStep`의 "스튜디오로 보내기"를 비활성화한다. |
| FR-11 | 안내 배너가 아니라 **차단형 UI**로 제시한다 — 실패 사유 + "다시 생성"을 주 동선에 둔다. |
| FR-12 | `reason` 코드를 한국어로 매핑하고 재시도 가능 여부를 구분한다 (§4-3). |
| FR-13 | 저장 요청에 `prompt_version_id`를 실어 보낸다. |
| FR-14 | 사용자가 프롬프트를 편집하면 차단이 해제된다. |
| FR-15 | `tools` degraded는 차단하지 않는다 (D5). |

---

## 4. 아키텍처

### 4-1. 판정 로직 배치 (레이어)

degraded 판정은 **도메인 규칙**이므로 `domain/`에 둔다. UseCase는 조회와 호출만 한다
(CLAUDE.md §2 — application은 비즈니스 규칙 직접 구현 금지).

```
src/domain/agent_builder/policies.py  (또는 신규 prompt_gate.py)
  class DegradedPromptPolicy:
      @staticmethod
      def blocks(version_degraded: bool, stored_assembled: str,
                 submitted_prompt: str) -> bool:
          """degraded 버전을 편집 없이 그대로 저장하려는가."""
          if not version_degraded:
              return False
          return _norm(stored_assembled) == _norm(submitted_prompt)
```

순수 함수이므로 DB·LLM 목 없이 테스트된다.

### 4-2. 호출 흐름

```
POST /api/v1/agents   (agent_builder_router.py:168)
  → CreateAgentUseCase.execute()            create_agent_use_case.py:108
      Step 3  system_prompt 필수 검증        :216
      Step 3.5 ★ NEW — degraded 게이트
         prompt_version_id 없음 → skip (FR-06)
         있음 → PromptRepositoryPort 로 버전 조회
              → DegradedPromptPolicy.blocks(...) 
              → True 면 ValueError → 라우터가 422
      Step 4  저장                            :221
```

**협력자 주입**: `CreateAgentUseCase`에 프롬프트 버전 조회용 Port를 **선택
인자**로 넣는다(기본 `None`). 미주입이면 게이트가 통째로 비활성 — 기존 호출부
(파이프라인 `_run_create`, 테스트 다수)가 무변경으로 동작한다.

### 4-3. `reason` → 사용자 문구 매핑 (FR-12)

| reason | 문구 | 재시도 |
|---|---|---|
| `timeout` | "프롬프트 생성이 시간 내에 끝나지 않았습니다." | 권장 |
| `empty` | "생성 결과가 비어 있습니다." | 권장 |
| `schema` | "생성 결과 형식이 올바르지 않습니다. 관리자에게 문의하세요." | 비권장 |
| `error` | "프롬프트 생성 중 오류가 발생했습니다." | 1회 권장 |

매핑 테이블은 프론트 `src/types/agentPipeline.ts` 인접에 `as const`로 둔다
(메모리 규칙: 컴포넌트 파일에 런타임 상수 export 금지).

### 4-4. Port 조회 메서드

현재 `PromptRepositoryPort`에는 `list_versions(session_id)`만 있고
버전 단건 조회가 없다 (`domain/prompt_composer/interfaces.py:54-95`).

→ `find_version(version_id, user_id) -> object | None`을 Port에 추가한다.
도메인 개념(프롬프트 버전)이라 레이어 위반이 아니며,
`pipeline-langsmith-tracing`에서 문제가 됐던 "LangChain 형상 인자"와 다르다.

---

## 5. 계약 변경

| 항목 | 변경 |
|---|---|
| `CreateAgentRequest` (백엔드) | `prompt_version_id: str \| None = None` 추가 |
| `CreateBuilderAgentRequest` (프론트 `types/agentBuilder.ts`) | 동일 필드 추가 |
| 422 응답 | `detail`에 사유 포함 |
| DB 스키마 | **변경 없음** (`degraded`/`reason`/`assembled` 모두 기존 컬럼) |

> ⚠️ 백엔드 스키마가 바뀌므로 **`/api-contract-sync` 필수** (루트 CLAUDE.md §4-1).
> 신규 필드는 전부 optional이라 기존 클라이언트는 무영향.

---

## 6. 에러 처리

| 상황 | 동작 |
|---|---|
| `prompt_version_id` 미전달 | 게이트 skip, 정상 생성 (FR-06) |
| 버전 조회 실패(없음·타인 소유·DB 오류) | **게이트 skip + warning 로그.** 관측성 결함이 생성 실패로 번지지 않게 한다 |
| Port 미주입 | 게이트 전체 비활성 (§4-2) |
| degraded이고 내용 동일 | `ValueError` → 422 + reason |
| degraded이나 내용 다름 | 통과 (FR-05) |

---

## 7. 설계상 위험

### 7-1. 내용 비교의 취약성 — 최대 위험

응답의 `assembled_prompt`는 `PipelinePolicy.clamp_prompt()`를 거친 값이고
(`use_case.py:348-349`), DB의 `assembled`는 **원본**이다. 단순 `==` 비교는
8000자를 넘는 프롬프트에서 항상 "편집함"으로 오판해 게이트를 무력화한다.

→ FR-04: 양쪽에 `clamp_prompt()`를 동일 적용한 뒤 `strip()` 비교.
`clamp_prompt`는 순수 함수라 결정적이다.

> **Plan §7-2가 금지한 "폴백 문자열 매칭"과 다르다.** 폴백 상수와 대조하는 것이
> 아니라 *이 세션이 생성한 그 버전*과 대조한다. 상수가 바뀌어도 깨지지 않고,
> 한 글자 수정이 "편집함"이 되는 것은 **의도된 동작**이다 (FR-05).

### 7-2. 차단이 과할 위험

`POST /api/v1/agents`는 위저드 전용이 아니다. FR-06으로 `prompt_version_id`가
없는 경로는 전부 통과시켜, 수동 생성·Fix 경로·API 직접 사용은 영향을 받지 않는다.

### 7-3. module-0 값 확정의 위험

FR-00a/00b의 숫자를 실측 없이 정하면 같은 사고가 반복된다. Do에서 gpt-5.1
실지연을 측정한 뒤 확정한다 (§9-1).

### 7-4. 폴백 문구 유지 결정과 UX의 충돌

폴백 문구를 그대로 두면 사용자가 계속 "품질 낮은 생성"으로 오인할 수 있다.
FR-11의 차단형 UI가 "이건 생성 결과가 아니다"를 명시해 이를 상쇄한다.

---

## 8. Test Plan

> **갱신 (2026-09-21, Check G7)**: 최초 작성 시 module-0 에 해당하는 항목이
> T-15 하나뿐이었다. Do 단계에서 FR-00c/00d 를 고정하는 테스트를 추가했으므로
> T-00a~T-00d 로 채번해 기록한다.

**module-0 (`root-cause-fix`)**

| ID | 레벨 | 내용 | 파일 |
|---|---|---|---|
| T-00a | L1 | 기본 모델 해석 시 `model_name` + `source="default"` 로그 | `test_utility_llm_default_observability.py` |
| T-00b | L1 | 명시 모델 해석 시 `source="utility"` / 미해석 시 기존 warning 유지 | 〃 |
| T-00c | L1 | `_degrade` 로그에 `model`·`timeout_sec`·`latency_ms` (timeout·error 경로) | `test_degrade_observability.py` |
| T-00d | L1 | **`_active_model_name()` 이 provider 해석 결과를 우선** (운영 경로) | 〃 (Check G1 로 추가) |

**module-1 / module-2**

| ID | 레벨 | 내용 |
|---|---|---|
| T-01 | L1 | `DegradedPromptPolicy.blocks` — degraded=False면 항상 False |
| T-02 | L1 | degraded=True + 내용 동일 → True |
| T-03 | L1 | degraded=True + 내용 다름 → False (FR-05) |
| T-04 | L1 | **8000자 초과 프롬프트에서 clamp 적용 후 동일 판정** (§7-1 고정) |
| T-05 | L1 | 앞뒤 공백 차이는 동일로 본다 |
| T-06 | L2 | `CreateAgentUseCase` — Port 미주입이면 게이트 skip |
| T-07 | L2 | `prompt_version_id` 미전달이면 skip (FR-06) |
| T-08 | L2 | 버전 조회 예외 → skip + warning (생성은 성공) |
| T-09 | L2 | degraded 버전 + 미편집 → `ValueError` |
| T-10 | L2 | `tools` degraded는 차단하지 않는다 (D5, FR-15) |
| T-11 | L2(프론트) | degraded면 "스튜디오로 보내기" 비활성 (MSW+RTL) |
| T-12 | L2(프론트) | 4개 reason 각각 고유 한국어 문구 |
| T-13 | L2(프론트) | "다시 생성" 성공 시 차단 해제 |
| T-14 | L2(프론트) | 저장 요청에 `prompt_version_id` 포함 |
| T-15 | 수동 | module-0 적용 후 실제 생성이 degraded 없이 완료 |

TDD 필수: 각 모듈에서 테스트 먼저 작성 → 실패 확인 → 구현.

---

## 9. Implementation Guide

### 9.1 구현 순서

```
[module-0] 근본 수정
 1. gpt-5.1 로 prompt 생성 실지연 3~5회 측정 (scratchpad 스크립트)
 2. 측정 결과로 UTILITY_LLM_MODEL_NAME / PROMPT_COMPOSER_TIMEOUT_SEC 확정
 3. FR-00c/00d 로그 추가 (+ 테스트)
 4. 수동 검증 T-15

[module-1] 서버 차단
 5. [TDD] T-01~T-05 → DegradedPromptPolicy 구현
 6. [TDD] T-06~T-10 → Port find_version + CreateAgentUseCase Step 3.5
 7. CreateAgentRequest 필드 추가

[module-2] 프론트
 8. /api-contract-sync — 타입 동기화
 9. [TDD] T-11~T-14 → PromptStep 차단형 UI + reason 매핑 + 저장 배선
```

### 9.2 파일별 변경

| 파일 | 유형 |
|---|---|
| `.env` / `src/infrastructure/config/prompt_composer_config.py` | 수정 (module-0) |
| `src/application/llm_model/utility_llm_provider.py` | 수정 — 폴백 로그 (FR-00c) |
| `src/infrastructure/prompt_composer/adapter.py` | 수정 — `_degrade` 로그 보강 (FR-00d) |
| `src/domain/agent_builder/policies.py` | 추가 — `DegradedPromptPolicy` |
| `src/domain/prompt_composer/interfaces.py` | 수정 — `find_version` |
| `src/infrastructure/prompt_composer/repository.py` | 수정 — 구현 |
| `src/application/agent_builder/create_agent_use_case.py` | 수정 — Step 3.5 |
| `src/application/agent_builder/schemas.py` | 수정 — 요청 필드 |
| `src/api/main.py` | 수정 — Port 주입 |
| `idt_front/.../PromptStep.tsx` · `AgentCreateEntryPage/index.tsx` · `AgentBuilderPage/index.tsx` · `agentDraftStore.ts` · `types/*.ts` | 수정 |

### 9.3 Session Guide

| 모듈 | 키 | 선행 |
|---|---|---|
| module-0 | `root-cause-fix` | — |
| module-1 | `server-gate` | — |
| module-2 | `frontend-block` | module-1 |

```
/pdca do prompt-fallback-visibility --scope root-cause-fix     ← 최우선, 단독 가치
/pdca do prompt-fallback-visibility --scope server-gate
/pdca do prompt-fallback-visibility --scope frontend-block
```

**module-0만으로도 실사용 문제가 해결된다.** module-1/2는 다음 장애를 위한 안전망이다.

---

## 10. Plan 대비 변경

| Plan | Design | 사유 |
|---|---|---|
| FR-07(원인 규명)을 Do 항목으로 | **Design에서 완료** | DB에 증거가 이미 있었다 (§1-1) |
| 스코프 = 가시성·차단 | **근본 수정(module-0) 추가** | 원인이 타임아웃 설정으로 밝혀짐. 차단만으로 80% 실패율 미해결 |
| §7-1 차단 강도 A/B/C | **C 확정** | `prompt_version.degraded`가 이미 영속돼 C가 가장 저렴 |
| §7-1 C = "세션에서 재조회" | **버전 단건 조회 + 내용 비교** | 저장 시점에 `human` 버전이 없다 (§2-3) |
| §7-2 "문자열 매칭 금지" | **유지** — 폴백 상수가 아닌 *해당 버전*과 비교 | 구분 근거는 §7-1 |
| NFR-02 tools 미차단 | 유지 (D5) | 사용자 확정 |

---

## 11. 미해결 / 후속

| # | 항목 |
|---|---|
| 1 | **FR-00a/00b 구체 값** — Do module-0에서 실측 후 확정 |
| 2 | `TraceExtractor` 미작동 (`ai_run` 152건 중 trace_id 0건) — [[pipeline-langsmith-tracing]] §12-2, 별도 feature |
| 3 | `.env` UTF-8 BOM — 도구에 따라 파싱 실패 가능 |
| 4 | 받은 피드백 중 "섹션 생략" / "generic 문구 lint" / "AgentPlanner 재질문 트리거"는 **미채택** (Plan §9-1 Q4). 다만 lint는 *폴백 탐지* 수단으로 재해석하면 살릴 여지가 있다 |

---

## Version History

| 버전 | 일자 | 내용 |
|---|---|---|
| 0.1 | 2026-09-20 | 최초 작성. 근본 원인(gpt-5.1 × 20초 타임아웃) 규명, Option C 확정, module-0 추가. |
