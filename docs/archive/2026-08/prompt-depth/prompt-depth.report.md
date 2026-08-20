# prompt-depth Completion Report

> **Status**: **Complete** (잔여 조치 3건은 코드가 아닌 설정·프롬프트 문구)
>
> **Project**: sangplusbot (`idt` 백엔드 + `idt_front` 프론트엔드)
> **Version**: 0.1
> **Author**: 배상규
> **Completion Date**: 2026-08-20
> **PDCA Cycle**: Plan → Design → Do(4 모듈) → Check → Act-1

---

## Executive Summary

### 1.1 Project Overview

| Item | Content |
|------|---------|
| Feature | prompt-depth — 시스템 프롬프트 4블록 → 7섹션 마크다운 확장 |
| Start Date | 2026-08-20 |
| End Date | 2026-08-20 |
| Duration | 1일 (단일 세션, Do 4모듈 분할) |
| 선행 사이클 | agent-create-wizard (completed, 95%) |

### 1.2 Results Summary

```
┌─────────────────────────────────────────────┐
│  Overall Match Rate: 99%   (목표 90%)        │
├─────────────────────────────────────────────┤
│  ✅ FR 완료:        26 / 26                  │
│  ✅ SC 충족:         8 Met / 1 Partial       │
│  ⏳ 잔여 조치:       4건 (설정·문구·정리)     │
│  ❌ 취소:            0                       │
└─────────────────────────────────────────────┘

Structural 100 │ Functional 97 │ Contract 100 │ Runtime 100
Architecture 100 │ Convention 96
```

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | "간단한 데이터 분석 에이전트 만들어줘"에 대해 `purpose` + 대괄호 3블록, **~500자**짜리 얕은 프롬프트만 생성됐다. 사용자는 Role/Context/Responsibilities/Workflow/Style/Notes를 갖춘 문서를 기대했으나 **파이프라인 어디에도 그 정보를 담을 자리가 없었다.** |
| **Solution** | 세 지점을 동시에 넓혔다 — ① LLM 출력 스키마 `_PromptDraft` 4→8필드 ② `assemble()`을 마크다운 헤딩 조립으로 전환 ③ 의도 수집에 "LLM이 추측하면 위험한" 2축(제약·판단 우선순위) 추가. 길이 상한 4000→8000. |
| **Function/UX Effect** | 같은 한 문장 요청에서 **1,232~1,850자 / 7섹션 전부 채워진** 프롬프트가 실서버에서 생성·저장된다(실측 4회). 되묻기는 최대 3라운드로 늘었으나 **상세히 쓴 요청은 여전히 round 0에서 왕복 없이 통과**한다. |
| **Core Value** | 에이전트 품질의 병목이 "무엇을 물어보는가"가 아니라 **"받은 답을 담을 그릇의 크기"**였음을 실측으로 확인하고 해소했다. 의도 수집만 깊게 해서는 도달 불가능한 지점이었다 — 실제로 이번 사이클에서 의도 축을 2개 늘렸을 때, **그릇이 없었다면 그 답은 `principles[]` 몇 줄로 뭉개졌을 것**이다. |

---

## 1.4 Success Criteria Final Status

| # | Criteria | Status | Evidence |
|---|----------|:------:|----------|
| SC-1 | 1문장 → **7섹션 모두 채워진** 프롬프트 생성 | ✅ Met | 실서버 `POST /api/v1/agents/pipeline` → 1,571자, `##` 헤딩 7개 전부, `degraded_stages: []` |
| SC-2 | 8000자 이내 **저장 성공** (`GET /agents/{id}`) | ✅ Met | agent `842f0ea6…` 생성 → GET 200, `system_prompt` 1,232자에 7섹션 보존 |
| SC-3 | 되묻기에서 `constraints`·`decision_priority` **질문이 나오고** 답변이 반영 | ⚠️ Partial | **질문 ✅** (Act-1 후 round 2에서 두 축 등장) / **수집 ✅** (`filled_slots` 6축 병합) / **반영 ⚠️** 짧은 옵션값은 출력에서 희석 (G-05) |
| SC-4 | 상세히 쓴 1문장은 **되묻기 없이** 도구 단계로 | ✅ Met | round 0, `questions: []` — Act-1 수정 **후에도 유지** 확인 |
| SC-5 | 마크다운 조립 + 빈 섹션 헤더째 생략 | ✅ Met | `tests/domain/prompt_composer/test_policies.py` 70 passed |
| SC-6 | 확장 스키마로 **실 LLM 1회 성공** (strict 400 없음) | ✅ Met | `pytest -m llm` → `degraded=False`, 섹션 8/8, 12.2s |
| SC-7 | 규칙기반 폴백도 7섹션 | ✅ Met | `test_fallback_assembles_into_seven_section_markdown` |
| SC-8 | 신규 코드 TDD (red → green) | ✅ Met | 4모듈 전부 red 선확인 (module-1 ImportError, m3 red 8, m4 red 5, Act-1 red 5) |
| SC-9 | 기존 경로 회귀 0 — 정렬된 FAILED 목록 diff | ✅ Met | 백엔드 baseline과 **바이트 동일 80건**, 프론트 9건도 stash 실측으로 기존 실패 확정 |

**Success Rate**: **8 Met / 1 Partial / 0 Not Met** (89% 완전 충족, 100% 착수)

## 1.5 Decision Record Summary

| Source | Decision | 준수 | 실제 결과 |
|--------|----------|:----:|-----------|
| [Plan] | 핵심 **7섹션** (11섹션 아님) | ✅ | Examples·Error Handling이 `workflows`/`principles`에 자연 흡수됨 — 실 출력에서 확인. 11섹션이었다면 스키마 비대화로 R-01 위험이 컸다 |
| [Plan] | **마크다운 헤딩** 표기 | ✅ | LLM이 섹션 경계를 정확히 인식. 7섹션이 대괄호였다면 계층이 안 보였을 것 |
| [Plan] | 신규 2축 **optional** | ✅ | 결정은 지켜졌으나 **이 결정이 G-01의 직접 원인**이었다 (required가 purpose 하나뿐 → complete 즉시 되묻기 종료). Act-1에서 optional을 유지한 채 해결 |
| [Plan] | 라운드 상한 **3** | ✅ | Check 시점엔 **무력**했으나(round 2 발생 불가) Act-1 후 회복 |
| [Plan] | 길이 상한 **8000** | ✅ | 4곳 일치를 테스트로 고정. 다만 실측 최대 1,850자로 **상한의 23%** — 여유가 예상보다 컸다 |
| [Plan] | 기존 에이전트 재생성 **제외** | ✅ | 저장된 프롬프트 무변경 |
| [Plan] | Fix 탭 **제외** | ✅ | `agent_composer` diff 0줄, `schemas.py:13`의 4000 그대로 유지 |
| [Design] | **Option C** — 구조가 값을 하는 곳만 VO | ✅ | `ContextSection`/`WorkflowSection` 2종만 신설. Option B였다면 LLM 스키마 필드가 배로 늘어 R-02가 더 심했을 것 |
| [Design] | 섹션 번호 없음 + 이름 제목 없음 | ✅ | 빈 섹션 생략 시 번호가 튀는 문제가 **원천 소멸** |
| [Design] | 폴백 고정 문구 7섹션 | ✅ | `_FALLBACK_ROLES` 추가로 설계 보완 (설계서에 누락돼 있던 항목) |
| [Design] | `intent_block()` **화이트리스트** | ✅ | `extra="allow"` 경로의 프롬프트 인젝션 차단. 테스트로 고정 |
| [Design] | `replace()` 전면 전환 | ✅ | `_replace_guides`가 신규 필드를 떨어뜨리던 **실제 버그**를 구조적으로 제거 |
| [Design] | `MAX_CLARIFY_ROUNDS`를 `index.tsx`에 | ⚠️ 이탈 | `types/agentPipeline.ts`로 이동 — 컴포넌트 런타임 상수 export 금지 규칙 때문에 그 자리에선 테스트가 불가능했다 |

---

## 2. Related Documents

| Phase | Document | Status |
|-------|----------|--------|
| PM | — | ❌ 미실행 (Plan에서 직행, 사용자 결정 8건이 Plan §7.2에 기록) |
| Plan | [prompt-depth.plan.md](../01-plan/features/prompt-depth.plan.md) | ✅ Finalized |
| Design | [prompt-depth.design.md](../02-design/features/prompt-depth.design.md) | ✅ Finalized |
| Check | [prompt-depth.analysis.md](../03-analysis/prompt-depth.analysis.md) | ✅ Complete (Act-1 반영) |
| Act | 현재 문서 | ✅ |

---

## 3. Completed Items

### 3.1 Functional Requirements

| ID | Requirement | Status |
|----|-------------|:------:|
| FR-01~04 | `identity` / `context` / `workflows` / `style` 섹션 | ✅ |
| FR-05 | strict 호환 (자유 키 dict 0건) | ✅ |
| FR-06 | 계산 필드를 LLM 스키마에서 제외 | ✅ |
| FR-07~08 | 마크다운 조립 · 빈 섹션 생략 · 결정성 | ✅ |
| FR-09 | `clamp_sections` 신규 상한 6종 | ✅ |
| FR-10 | 폴백 7섹션 유지 | ✅ |
| FR-11 | 환각 폐기 후 신규 필드 보존 | ✅ |
| FR-12 | `schema_version = 2` | ✅ |
| FR-13 | SYSTEM 섹션 작성 지침 | ✅ |
| FR-14~15 | `constraints` · `decision_priority` 축 | ✅ |
| FR-16 | `purpose`만 required | ✅ |
| FR-17 | 라운드 2 → 3, 단일 출처 IntentConfig | ✅ (Act-1에서 효과 회복) |
| FR-18 | 회당 질문 3 유지 | ✅ |
| FR-19 | 2축이 프롬프트 근거로 전달 | ✅ |
| FR-20~22 | 길이 상한 8000 (백엔드 4곳) | ✅ |
| FR-23~24 | 프론트 8000 · 라운드 3 정합 | ✅ |
| FR-25 | textarea 가독성 | ✅ |
| FR-26 | 기존 5경로 무변경 | ✅ |

**26 / 26 완료**

### 3.2 Non-Functional Requirements

| 항목 | 목표 | 달성 | 판정 |
|------|------|------|:----:|
| strict 호환 | `_PromptDraft` 자유 키 dict 0건 | 재귀 탐색 테스트 + 실 LLM 400 없음 | ✅ |
| 실 LLM 검증 | 실제 호출 1회 이상 성공 | 성공, 섹션 8/8 | ✅ |
| 지연 | `PROMPT_COMPOSER_TIMEOUT_SEC`(20s) 내 | **14.5s** — 여유 5.5s | ⚠️ |
| 결정성 | 동일 입력 → 바이트 동일 | 100회 동일 | ✅ |
| 회귀 | 기존 경로 무변경 | FAILED 목록 바이트 동일 | ✅ |
| 아키텍처 | domain 순수 / LLM 스키마 infra 격리 | AST 경계 테스트 통과 | ✅ |
| 타입 검사 | **테스트 파일 포함** 0 에러 | `tsc --noEmit` 0 | ✅ |

### 3.3 Deliverables

**백엔드 (12 파일, 신규 파일 0)**

| 영역 | 파일 |
|------|------|
| Domain VO | `domain/prompt_composer/schemas.py` — `ContextSection`·`WorkflowSection` 신설, `PromptSections` 8필드 |
| Domain 규칙 | `domain/prompt_composer/policies.py` — 마크다운 조립, 블록 헬퍼 6종, 상한 6종, 폴백 상수 5종, `replace()` 전환 |
| Domain 파이프라인 | `domain/agent_create_pipeline/spec.py` (6축), `policies.py` (`PROMPT_MAX_CHARS`, `decide_after_intent`) |
| Infra LLM | `infrastructure/prompt_composer/adapter.py` — Draft 2종, 매핑, 관측 6종 |
| Infra 프롬프트 | `infrastructure/prompt_composer/prompts.py` — SYSTEM 7섹션 지침, `_SLOT_LABELS` 화이트리스트 |
| Infra 영속 | `infrastructure/prompt_composer/repository.py` — JSON 8키, `_SCHEMA_VERSION=2` |
| Infra 설정 | `infrastructure/config/intent_config.py` — 라운드 3 |
| Interfaces | `interfaces/schemas/prompt_composer.py` — `ContextOut`/`WorkflowOut`/8000 |
| API | `api/routes/prompt_composer_router.py` — `_to_sections_out`/`_to_context_out` |
| Application | `application/agent_builder/schemas.py` (8000×2), `application/agent_create_pipeline/use_case.py` (round 전달) |

**프론트 (3 파일)**

| 파일 | 변경 |
|------|------|
| `types/agentPipeline.ts` | `MAX_ASSEMBLED_CHARS` 8000, `MAX_CLARIFY_ROUNDS` 3 신설 |
| `pages/AgentCreateEntryPage/index.tsx` | 로컬 상수 제거 → `types/` import |
| `components/PromptStep.tsx` | textarea rows 22 + `max-h-[60vh]` + `overflow-y-auto` |

**테스트 (11 파일)**

| 파일 | 케이스 |
|------|--------|
| `tests/domain/prompt_composer/test_policies.py` | 34 → **70** |
| `tests/infrastructure/prompt_composer/test_adapter.py` | +T-S1/T-S2/T-A1/T-A2/T-A3 |
| `tests/infrastructure/prompt_composer/test_repository.py` | +3 (신규 섹션·`context=None`·v2) |
| `tests/infrastructure/prompt_composer/test_real_llm.py` | 7섹션 충족률·지연·길이 실측 보고 |
| `tests/domain/agent_create_pipeline/test_spec.py` | +8 (6축·optional·라운드·상한 4곳 정합) |
| `tests/domain/agent_create_pipeline/test_policies.py` | +8 (SC-4/SC-3 판정 + 2축 에코백) |
| `tests/api/test_prompt_composer_router.py` | +3 (신규 섹션 응답·additive·8000 경계) |
| 그 외 3 | 상한 리터럴 → 상수 참조 전환 |
| 프론트 3 | 8000·라운드 3·textarea |

---

## 4. Incomplete Items

### 4.1 다음 사이클로 이월

| 항목 | 사유 | 우선순위 | 예상 |
|------|------|:--------:|------|
| `PROMPT_COMPOSER_TIMEOUT_SEC=30` | 실측 14.5s/20s — 여유 부족 (G-02) | 🟡 High | `.env` 1줄 |
| `constraints`/`decision_priority` 지침 강화 | 짧은 옵션값이 출력에서 희석 (G-05) | 🟡 High | `prompts.py` 문구 |
| `style` 지침 구체화 | 한 줄 출력, `tone` 값 복사 (G-03) | 🟢 Medium | `prompts.py` 문구 |
| 검증 잔여물 정리 | `testuser@sangplus.dev`, agent `842f0ea6…` (G-04) | 🟢 Low | DB/스튜디오 |

### 4.2 의도적 범위 밖 (Plan §2.2 그대로 유지)

| 항목 | 사유 | 상태 |
|------|------|------|
| 기존 에이전트 프롬프트 재생성 | 의도 수집 없는 재생성은 얕은 프롬프트가 기존 것을 덮을 위험 | 유지 |
| Fix 탭 (`POST /api/v1/agents/compose`) | 별도 모듈·별도 스키마. R1 수렴 사이클 대상 | 유지 (diff 0줄) |
| `/api/v3/agents/auto` | 동상 | 유지 |
| 11섹션 전체 | 핵심 7섹션으로 흡수 — 실 출력에서 타당성 확인 | 유지 |
| 토큰 비용 최적화(캐싱) | 실측 1,850자로 우려가 크게 낮아짐 | **불필요 판정** |

---

## 5. Quality Metrics

### 5.1 최종 지표

| 지표 | 목표 | Check 시점 | Act-1 후 | 변화 |
|------|:----:|:----------:|:--------:|------|
| Overall Match Rate | 90% | 94% | **99%** | +5 |
| Functional | — | 92% | **97%** | +5 |
| Runtime | — | 89% | **100%** | +11 |
| Structural / Contract / Architecture | — | 100% | **100%** | — |
| Convention | — | 96% | 96% | — |
| Success Criteria | — | 8/9 (1 ❌) | **8 Met / 1 Partial** | ❌ 해소 |
| 신규 FAILED | 0 | 0 | **0** | — |

### 5.2 해결된 이슈

| 이슈 | 조치 | 결과 |
|------|------|------|
| **G-01** 신규 2축이 되묻기에 도달 못함 (SC-3 ❌) | `decide_after_intent`에 "round ≥ 1 이고 라운드가 남으면 ask" 조건 (domain 순수 함수 1곳) | ✅ 실서버 round 2에서 두 축 질문 확인, **SC-4 무회귀 확인** |
| **FR-17 무력화** | 위 수정의 부수 효과 | ✅ round 2가 실제 발생 → 라운드 3이 효과를 가짐 |
| `_replace_guides` 필드 유실 | `dataclasses.replace()` 전환 | ✅ 향후 필드 추가에서 재발 불가 |
| 4-way 필드 집합 불일치 위험 | VO/Draft/JSON/`SectionsOut` 키 동등성 테스트 | ✅ 정적 + 런타임(OpenAPI·`JSON_KEYS`) 양쪽 확인 |
| 프롬프트 인젝션 표면 | `intent_block()` 화이트리스트 | ✅ `extra="allow"` 경로 차단, 테스트 고정 |
| 상한 5곳 불일치 위험 (R-08) | 4곳 값 비교 테스트 + 리터럴 → 상수 참조 | ✅ 한 곳만 바뀌면 즉시 실패 |
| R-01 strict 위반 | 재귀 탐색 테스트 + 실 LLM 검증 | ✅ 400 없음 |
| R-03 토큰 비용 2배 | 실측 | ✅ 최대 1,850자 = 상한의 23% |

---

## 6. Lessons Learned & Retrospective

### 6.1 Keep — 잘 된 것

- **진단을 실측으로 뒤집었다.** 사용자의 최초 진단은 "의도 파악을 더 자세히"였으나, 코드를 실측해 보니 의도 수집은 원인의 1/3이었고 **결정적 병목은 출력 스키마 4필드 고정**이었다. Plan §1.2가 이 재진단을 근거와 함께 기록했고, 결과적으로 그릇을 넓히지 않았다면 2축 추가는 무의미했을 것이다.

- **설계 단계에서 코드를 먼저 읽어 8개 열린 질문을 전부 닫았다.** 특히 `intent_block()`이 `filled_slots`를 버리고 있다는 사실을 Design 시점에 발견해, FR-19의 실제 변경 지점을 확정했다. 이걸 Do에서 발견했다면 module-2가 통째로 흔들렸을 것이다.

- **수정 전에 가정을 두 번 실측했다 (Act-1).** ① "LLM이 round 2 질문을 만드는가" → 만든다(판정만 막고 있었음) ② "round 0에서도 질문이 생성되는가" → 생성된다. **두 번째 실측이 없었으면 SC-3을 고치면서 SC-4를 깨뜨렸을 것이다.**

- **실서버·실 LLM으로 닫았다.** fake만으로 통과한 코드가 실제로는 매 호출 400을 내던 사례(intent 모듈, 3개월 은폐)가 위키에 있었고, 그 전례 때문에 SC-6을 DoD에 넣었다. 결과적으로 런타임 검증이 G-01이라는 Critical을 잡아냈다 — **정적 분석만 했다면 "FR 26/26 완료, 100%"로 잘못 닫혔을 사이클**이다.

- **회귀 판정을 건수가 아니라 `FAILED` 목록 diff로 했다.** Plan의 baseline(58건)이 틀렸다는 것과, `.pytest_cache` 잔재가 6건을 가짜로 부풀린 것을 모두 잡아냈다.

### 6.2 Problem — 개선 필요

- **Plan/Design이 "선언"과 "도달 가능성"을 구분하지 않았다.** FR-14/15는 "축을 추가한다"만 요구했고 설계는 그대로 구현했다. 그러나 축이 **스펙에 존재하는 것**과 **사용자에게 실제로 물어지는 것**은 다른 문제였고, 그 간극이 Check에서야 드러났다. FR을 "`spec.py`에 축이 있다"가 아니라 "되묻기에서 축이 물어진다"로 썼다면 Design에서 `decide_after_intent`를 검토했을 것이다.

- **Plan의 baseline 수치(58건)가 검증 없이 적혔다.** 실측은 80건. 회귀 게이트의 기준값이 틀리면 게이트 자체가 무의미하다.

- **Design §5.1의 폴백 상수 목록에 `roles`가 빠져 있었다.** "7섹션 전부 채움"이라는 결정과 설계서 본문이 어긋난 채로 Do에 넘어갔다.

- **`style` 섹션 지침이 약했다** (R-02가 예상했으나 예방하지 못함). 지침에 "무엇을 쓰는지"만 있고 "얼마나 구체적으로"가 없어 LLM이 `tone` 값을 그대로 복사했다.

- **짧은 옵션값이 프롬프트에서 희석되는 문제(G-05)를 늦게 발견했다.** 우리가 스펙에 넣어 사용자에게 버튼으로 제시하는 선택지가 가장 약한 반영을 낳는다 — 실 LLM 검증을 긴 문장 값으로만 했기 때문에 module-2에서 놓쳤다.

### 6.3 Try — 다음에 시도할 것

- **FR을 "관측 가능한 행동"으로 쓴다.** "축을 추가한다"가 아니라 "모호한 요청에서 이 축이 질문으로 나온다". 이러면 Design 단계에서 그 행동을 만드는 코드 경로를 강제로 훑게 된다.

- **Plan에 적는 baseline/현재값은 적기 전에 한 번 돌려본다.** 특히 회귀 게이트의 기준값.

- **실 LLM 검증에 "짧은 값"과 "긴 값"을 둘 다 넣는다.** 프롬프트 지시 준수도는 입력값의 서술성에 민감하다는 것이 이번에 드러났다.

- **회귀 측정 전 `.pytest_cache`를 지운다.** `-p no:cacheprovider`만으로는 부족했다. `false-green-quality-gates` 위키에 추가할 가치가 있는 사례다.

- **PM 단계를 건너뛴 사이클에서도 "누가 이 값을 입력하는가"를 한 번 묻는다.** G-01은 결국 "제약·우선순위를 **사용자가 어떻게 입력하는가**"를 아무 문서도 명시하지 않아서 생긴 구멍이었다.

---

## 7. Process Improvement Suggestions

### 7.1 PDCA 프로세스

| Phase | 이번 사이클 실태 | 개선 제안 |
|-------|------------------|-----------|
| Plan | 사용자 결정 8건이 잘 기록됐으나, 일부 수치(baseline)가 미검증 | 수치는 기록 전 1회 실행 |
| Design | 코드 실측으로 열린 질문 8건을 전부 닫은 것이 효과적 | 유지. 추가로 "이 FR을 만족시키는 **런타임 경로**"를 한 줄씩 적기 |
| Do | 4모듈 분할 + 모듈마다 red 확인이 잘 작동 | 유지 |
| Check | **런타임 검증이 Critical을 잡았다** — 정적만이었다면 100%로 오판 | 런타임 없는 Check는 상한을 명시 (예: "정적 only는 최대 85%") |
| Act | 수정 전 가정 실측 2회가 SC-4 회귀를 예방 | 유지: "고치기 전에 원인 가설을 실측으로 확인" |

### 7.2 도구/환경

| 영역 | 제안 | 기대 효과 |
|------|------|-----------|
| 테스트 | 회귀 측정 스크립트화 (`.pytest_cache` 삭제 + FAILED diff) | 이번에 실제로 겪은 오탐 제거 |
| E2E | 프로젝트에 E2E 하니스 없음 — L3를 L1으로 흡수해 측정 | 프론트-백 연결 시나리오의 자동 검증 |
| 관측 | `_log_success`에 섹션별 카운트·`assembled_chars` 추가 완료 | 어떤 섹션이 상습적으로 비는지 운영 데이터로 판단 가능 |

---

## 8. Next Steps

### 8.1 즉시

- [ ] `.env`에 `PROMPT_COMPOSER_TIMEOUT_SEC=30` (G-02)
- [ ] `prompts.py` — `constraints`/`decision_priority` 지침 강화 (G-05)
- [ ] `prompts.py` — `style` 지침 구체화 (G-03)
- [ ] 검증 잔여물 정리 (G-04)
- [ ] Design 문서 갱신 5건 (analysis §9.3)
- [ ] `/pdca archive prompt-depth`

### 8.2 다음 PDCA 사이클 후보

| 항목 | 우선순위 | 근거 |
|------|:--------:|------|
| **R1 수렴** — 생성 경로 3종(파이프라인 / Fix 탭 / auto) 통합 | High | 이번 사이클이 두 번 "범위 밖"으로 미룬 항목. 프롬프트 스키마가 이제 두 벌(7섹션 vs 4블록)이라 격차가 커졌다 |
| 기존 에이전트 프롬프트 마이그레이션 | Medium | `schema_version=1` 행과 대괄호 프롬프트가 공존. 재생성이 아니라 "사용자가 원할 때 업그레이드" 형태 |
| 프롬프트 생성 품질 관측 대시보드 | Low | `_log_success`의 섹션별 카운트를 집계 |

---

## 9. Changelog

### prompt-depth (2026-08-20)

**Added**
- `PromptSections`에 `identity` / `context` / `workflows` / `style` 4섹션 (신규 VO `ContextSection`·`WorkflowSection`)
- `_PromptDraft`에 대응 필드 4개 + 서브모델 2종 (strict 호환 유지)
- intent 스펙에 `constraints` · `decision_priority` 2축 (둘 다 optional)
- `intent_block()`의 슬롯 화이트리스트 렌더 — 신규 2축이 프롬프트 재료로 전달
- `SectionsOut`에 `ContextOut`/`WorkflowOut` (additive)
- 프롬프트 생성 관측 6종 (섹션별 카운트 + `assembled_chars`)

**Changed**
- `assemble()` 조립 표기: 대괄호 블록 → **마크다운 헤딩** (`## Role and Identity` 등 7섹션)
- `system_prompt` / `assembled` / `PROMPT_MAX_CHARS` 상한 **4000 → 8000** (4곳)
- `INTENT_MAX_CLARIFICATION_ROUNDS` **2 → 3**
- `prompt_version.schema_version` **1 → 2** (마이그레이션 없음)
- `decide_after_intent`: required 충족 후에도 round ≥ 1이면 남은 optional 축을 묻는다
- 프론트 `MAX_CLARIFY_ROUNDS`를 `types/agentPipeline.ts`로 이동
- 프롬프트 검토 textarea 높이·스크롤 확대

**Fixed**
- `_replace_guides`가 신규 섹션 필드를 유실하던 문제 — `dataclasses.replace()` 전환
- 신규 2축이 되묻기에서 한 번도 물어지지 않던 문제 (G-01)

**Unchanged (의도)**
- `agent_composer`(Fix 탭) · `auto_agent_builder` — diff 0줄
- 기존 에이전트의 저장된 프롬프트

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-08-20 | 완료 보고서 — Overall 99%, FR 26/26, SC 8 Met/1 Partial | 배상규 |
