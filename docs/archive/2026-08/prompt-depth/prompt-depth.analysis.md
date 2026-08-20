# prompt-depth Analysis Report

> **Analysis Type**: Gap Analysis (Static + Runtime)
>
> **Project**: sangplusbot (`idt` 백엔드 + `idt_front` 프론트엔드)
> **Version**: 0.1
> **Analyst**: 배상규
> **Date**: 2026-08-20
> **Design Doc**: [prompt-depth.design.md](../02-design/features/prompt-depth.design.md)
> **Plan Doc**: [prompt-depth.plan.md](../01-plan/features/prompt-depth.plan.md)

### 검증 환경

| 항목 | 상태 |
|------|------|
| 백엔드 서버 | ✅ 기동 (`localhost:8000`, `--reload` 로 변경분 반영 확인) |
| 프론트 서버 | ✅ 기동 (`localhost:5173`) |
| 실 LLM | ✅ 호출 (OpenAI, `.env` 키) |
| 인증 | `scripts/seed_test_users.sql` 의 `testuser@sangplus.dev` 1건 적용 (사용자 승인) |
| Playwright | ❌ 미설치 — 이 프로젝트의 프론트 검증 규약은 Vitest + RTL + MSW (§2.7 참조) |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 생성되는 시스템 프롬프트가 얕아 에이전트가 기대만큼 동작하지 않는다. 원인은 질문 부족이 아니라 출력 스키마가 4필드로 고정된 것 |
| **WHO** | P2 — 에이전트 소유자. 특히 도메인 규칙·금지사항이 명확한 업무(분석·심사·상담)에 에이전트를 쓰려는 실무자 |
| **RISK** | ① strict 모드 위반 ② 표기 이원화 ③ 호출당 고정 토큰 비용 |
| **SUCCESS** | 1문장 → 7섹션 프롬프트 생성 + 8000자 이내 저장, 기존 경로 회귀 0 |
| **SCOPE** | prompt_composer 스키마·조립 + intent 2축 + 길이 상한 + 프론트 정합 |

---

## Strategic Alignment Check

### 핵심 문제(WHY) 해소 여부

| 문제 | 기대 | 실측 | 판정 |
|------|------|------|:----:|
| 출력 스키마 4필드 고정 | 7섹션 확장 | `_PromptDraft` 8필드, 실 LLM 8/8 충족 | ✅ |
| 조립이 4블록 고정 | 마크다운 7섹션 | 실서버 출력에 7개 `##` 헤딩 전부 존재 | ✅ |
| 길이 상한 4000 | 8000 | OpenAPI 3개 스키마 `maxLength=8000` | ✅ |
| 의도 축 4개 | 6개 (제약·우선순위) | 스펙엔 6축이나 **되묻기에서 신규 2축이 물어지지 않음** | ❌ |

**전략 정합 판정**: WHY의 주된 진단("병목은 질문이 아니라 그릇")은 **해소됨**. 다만 Plan이 부수적으로 설정한 "받은 답을 담을 자리"의 **입력 경로 절반(신규 2축 수집)이 실제로 열리지 않았다** — G-01 참조.

### Success Criteria Status

| # | Criteria | 상태 | 증거 |
|---|----------|:----:|------|
| SC-1 | 1문장 → **7섹션 모두 채워진** 프롬프트 생성 | ✅ | `POST /api/v1/agents/pipeline` → 1,571자, `##` 헤딩 7개 전부, `degraded_stages: []` |
| SC-2 | 8000자 이내 **저장 성공** (`GET /agents/{id}`) | ✅ | agent `842f0ea6…` 생성 → GET 200, `system_prompt` 1,232자에 7섹션 그대로 |
| SC-3 | 되묻기에서 `constraints`·`decision_priority` **질문이 나오고** 답변이 프롬프트에 반영 | ⚠️ | **Act-1 수정 후**: round 2에서 두 축이 실제로 질문됨 ✅ / 답변이 `filled_slots` 6축 전부에 병합됨 ✅ / 다만 짧은 옵션값은 출력에서 희석됨 (G-05) |
| SC-4 | 상세히 쓴 1문장은 **되묻기 없이** 도구 단계로 | ✅ | 상세 요청 → `prompt_ready`, `questions: []`, round 0 |
| SC-5 | 마크다운 조립 + 빈 섹션 헤더째 생략 | ✅ | `test_policies.py` 70 passed (T-P1/P2 포함) |
| SC-6 | 확장 스키마로 **실 LLM 1회 성공** (strict 400 없음) | ✅ | `pytest -m llm` → `degraded=False`, filled 8/8, 12.2s |
| SC-7 | 규칙기반 폴백도 7섹션 | ✅ | `test_fallback_assembles_into_seven_section_markdown` |
| SC-8 | 신규 코드 TDD (red → green) | ✅ | 4개 모듈 전부 red 확인 후 구현 (module-1 ImportError, module-3 red 8건, module-4 red 5건) |
| SC-9 | 기존 경로 회귀 0 — 정렬된 FAILED 목록 diff | ✅ | 백엔드 `diff` IDENTICAL (80건), 프론트 9건도 stash 실측으로 기존 실패 확정 |

**Success Rate**: **8 Met / 1 Partial / 0 Not Met** (Act-1 수정 반영)

### Decision Record Verification

| Source | Decision | 준수 | 비고 |
|--------|----------|:----:|------|
| [Plan] | 핵심 7섹션 (11섹션 아님) | ✅ | Examples/Error Handling은 `workflows`/`principles`에 흡수됨 (실 출력 확인) |
| [Plan] | 마크다운 헤딩 표기 | ✅ | |
| [Plan] | 신규 2축 **optional** | ✅ | `required=False` — 그러나 이 결정이 G-01의 직접 원인 |
| [Plan] | 라운드 상한 3 | ⚠️ | 값은 3이나 **관측 가능한 효과 없음** (G-01) |
| [Plan] | 길이 8000 | ✅ | 4곳 일치, 테스트로 고정 |
| [Plan] | 기존 에이전트 재생성 제외 | ✅ | 변경 없음 |
| [Plan] | Fix 탭 제외 | ✅ | `agent_composer` diff 0줄, `schemas.py:13` 의 4000 유지 |
| [Design] | Option C (구조가 값을 하는 곳만 VO) | ✅ | `ContextSection`/`WorkflowSection` 2종만 신설 |
| [Design] | 번호 없음 + 이름 제목 없음 | ✅ | 실 출력에 `## 1.` / `# {이름}` 없음 |
| [Design] | 폴백 고정 문구 7섹션 | ✅ | `_FALLBACK_ROLES` 추가로 설계 보완 (Do 단계 보고) |
| [Design] | `intent_block()` 화이트리스트 | ✅ | `_SLOT_LABELS` 5키 — 인젝션 경로 차단 |
| [Design] | `replace()` 전면 전환 | ✅ | `_replace_guides` 필드 누락 버그 제거 |
| [Design] | `MAX_CLARIFY_ROUNDS` 를 `types/` 로 | ⚠️ | 설계는 `index.tsx` 하드코딩 — 테스트 가능성 위해 의도적 이탈 (Do 단계 보고) |

---

## 1. Analysis Overview

### 1.1 목적

Plan/Design이 정의한 "7섹션 그릇 확장 + 의도 2축 + 길이 상한"이 **실제로 동작하는 프롬프트를 만들어내는지** 확인한다. 이 사이클의 성패는 테스트 통과가 아니라 실서버가 뱉는 프롬프트 자체가 판단한다 (Plan §9-5).

### 1.2 범위

- 변경 파일: 백엔드 9 · 프론트 3 · 테스트 11
- 정적: FR-01~26 대조, 4-way 필드 집합, 레이어 규칙
- 런타임: 실서버 HTTP 5회 (실 LLM 포함), DB 직접 조회 3회, OpenAPI 스키마 검증

---

## 2. Gap Analysis

### 2.1 Requirements 대조

**prompt_composer (FR-01~13)**

| FR | 내용 | 구현 | 판정 |
|----|------|------|:----:|
| FR-01 | `identity` 섹션 | `schemas.py` `PromptSections.identity` | ✅ |
| FR-02 | `context` (constraints+background) | `ContextSection` | ✅ |
| FR-03 | `workflows` (situation+steps) | `WorkflowSection` | ✅ |
| FR-04 | `style` | `PromptSections.style` | ✅ |
| FR-05 | strict 호환 (dict 0건) | `test_prompt_draft_schema_has_no_free_key_dict` + 실 LLM 400 없음 | ✅ |
| FR-06 | 계산 필드 LLM 스키마 제외 | `test_draft_schema_has_no_system_owned_fields` (4 param) | ✅ |
| FR-07 | 마크다운 조립, 빈 섹션 헤더째 생략 | `assemble()` + T-P2 9케이스 | ✅ |
| FR-08 | 결정적 조립 | `test_assemble_is_deterministic_across_repeated_calls` | ✅ |
| FR-09 | `clamp_sections` 신규 섹션 | 상한 6종 + T-P5 6케이스 | ✅ |
| FR-10 | 폴백 7섹션 유지 | `_FALLBACK_*` 5종 | ✅ |
| FR-11 | 환각 폐기 후 신규 필드 보존 | `replace()` + T-P6 | ✅ |
| FR-12 | `schema_version = 2` | DB 실조회 3행 전부 `schema_version=2` | ✅ |
| FR-13 | SYSTEM 섹션 지침 | `prompts.SYSTEM` + 4 param 테스트 | ✅ |

**intent / 파이프라인 (FR-14~19)**

| FR | 내용 | 구현 | 판정 |
|----|------|------|:----:|
| FR-14 | `constraints` 축 (optional) | `spec.py` | ✅ |
| FR-15 | `decision_priority` 축 (optional) | `spec.py` | ✅ |
| FR-16 | `purpose` 만 required | 실서버 `missing_slots` 6축 · SC-4 통과 | ✅ |
| FR-17 | 라운드 2 → 3, 단일 출처 IntentConfig | Act-1 후 round 2가 실제 발생 — 효과 관측됨 | ✅ |
| FR-18 | 회당 질문 3 유지 | 실서버 round 1 질문 정확히 3개 | ✅ |
| FR-19 | 2축이 프롬프트 `context`/`principles` 근거로 | 실서버 에코백 → `## Context` 2줄 + `## Important Notes` 반영 | ✅ |

**길이 상한 / 프론트 (FR-20~26)**

| FR | 내용 | 구현 | 판정 |
|----|------|------|:----:|
| FR-20 | `system_prompt` 8000 (2곳) | OpenAPI `CreateAgentRequest`/`UpdateAgentRequest` `maxLength=8000` | ✅ |
| FR-21 | `PROMPT_MAX_CHARS` 8000 + 사유 문구 | 상수 + `test_clamp_prompt_boundary` | ✅ |
| FR-22 | `assembled` 8000 | OpenAPI `AppendVersionRequest` `maxLength=8000` | ✅ |
| FR-23 | 프론트 8000 정합 | `types/agentPipeline.ts` + `PromptStep.test.tsx` | ✅ |
| FR-24 | 프론트 라운드 3 | `MAX_CLARIFY_ROUNDS = 3` + `IntentStep.test.tsx` | ✅ |
| FR-25 | textarea 가독성 | rows 22 + `max-h-[60vh]` + `overflow-y-auto` | ✅ |
| FR-26 | 기존 경로 무변경 | `git diff --stat` 0줄 (agent_composer/auto_agent_builder) | ✅ |

**FR 충족**: 26 ✅ / 0 ⚠️ = **100%** (Act-1 후 FR-17 회복)

### 2.2 Data Model — 4-way 필드 집합 동등성 (§3.4)

| 축 | 키 집합 | 검증 |
|----|---------|------|
| `PromptSections` (VO) | 8키 | `test_domain_vo_and_draft_field_sets_match` |
| `_PromptDraft` (LLM) | 8키 | `test_draft_schema_has_exactly_the_seven_sections` |
| `_sections_to_json` (영속) | 8키 | **DB 실조회 `JSON_KEYS` 8키 확인** |
| `SectionsOut` (응답) | 8키 | **OpenAPI 실조회 8키 확인** |

정적 테스트 + 런타임 양쪽에서 일치. ✅

### 2.3 Component Structure

| Design §11.1 | 실제 | 판정 |
|--------------|------|:----:|
| `domain/prompt_composer/schemas.py` | 신규 VO 2종 + 필드 4 | ✅ |
| `domain/prompt_composer/policies.py` | 조립·clamp·폴백·`replace()` | ✅ |
| `infrastructure/prompt_composer/adapter.py` | Draft 2종 + 매핑 + 관측 6종 | ✅ |
| `infrastructure/prompt_composer/prompts.py` | SYSTEM + `_SLOT_LABELS` | ✅ |
| `infrastructure/prompt_composer/repository.py` | JSON 8키 + `_SCHEMA_VERSION=2` | ✅ |
| `interfaces/schemas/prompt_composer.py` | `ContextOut`/`WorkflowOut`/8000 | ✅ |
| `api/routes/prompt_composer_router.py` | `_to_sections_out` + `_to_context_out` | ✅ |
| `domain/agent_create_pipeline/spec.py` | 슬롯 6축 | ✅ |
| `domain/agent_create_pipeline/policies.py` | `PROMPT_MAX_CHARS=8000` | ✅ |
| `infrastructure/config/intent_config.py` | 라운드 3 | ✅ |
| `application/agent_builder/schemas.py` | 8000 (2곳) | ✅ |
| `types/agentPipeline.ts` | 8000 + 라운드 3 | ✅ |
| `AgentCreateEntryPage/index.tsx` | 상수 import | ✅ |
| `components/PromptStep.tsx` | textarea | ✅ |

**Structural Match Rate**: 14/14 = **100%**

### 2.4 Functional Depth

| 파일 | 깊이 | 근거 |
|------|:----:|------|
| `policies.py` (조립) | 100 | 블록 헬퍼 6종, 상한 6종, 폴백 상수 5종 — placeholder 0 |
| `adapter.py` | 100 | 매핑 8필드 전부, 관측 6종 |
| `prompts.py` | 95 | 섹션 지침 완비. `style` 지침이 실측에서 얕은 출력 유발 (G-03) |
| `repository.py` | 100 | 8키 직렬화 + `context=None` 처리 |
| `spec.py` | 70 | 축은 선언됐으나 **되묻기에 도달하지 못함** (G-01) |
| `intent_config.py` | 60 | 값·배선 정상이나 라운드 2가 발생하지 않아 효과 없음 (G-01) |
| 프론트 3파일 | 100 | 상수 정합 + textarea |

**Shallow (<60)**: 0 / 14
**Functional Match Rate**: **92%** (SC-3 미달을 반영해 FR 충족률 98%에서 하향)

### 2.5 API Contract Verification

| # | 엔드포인트 | Design | Server | Client | 계약 |
|---|-----------|:------:|:------:|:------:|:----:|
| 1 | `POST /api/v1/agents/pipeline` | ✅ | ✅ 200 | ✅ | PASS |
| 2 | `POST /api/v1/prompt-composer/compose` | ✅ | ✅ (OpenAPI 8키) | ✅ | PASS |
| 3 | `GET /api/v1/prompt-composer/sessions/{id}` | ✅ 무변경 | ✅ | ✅ | PASS |
| 4 | `POST …/sessions/{id}/versions` | ✅ 8000 | ✅ `maxLength=8000` | ✅ `MAX_ASSEMBLED_CHARS` | PASS |
| 5 | `POST /api/v1/agents` | ✅ 8000 | ✅ `maxLength=8000` | ✅ | PASS |
| 6 | `PATCH /api/v1/agents/{id}` | ✅ 8000 | ✅ `maxLength=8000` | ✅ | PASS |

**Contract Match Rate**: 6/6 = **100%**

### 2.6 Runtime Verification

#### L1: API (실서버 + 실 LLM)

| # | 테스트 | 기대 | 실측 | 판정 |
|---|--------|------|------|:----:|
| 1 | 상세 1문장 → `stop_after=prompt` | 200 / 7섹션 | 200, 1,571자, `##` 7개, degraded 0 | ✅ |
| 2 | 동 요청 되묻기 여부 | `questions: []` | `questions: []`, round 0 (SC-4) | ✅ |
| 3 | 모호 요청 → 되묻기 | `need_input` | `need_input`, 질문 3개 (round 1은 required 우선이 정상) | ✅ |
| 4 | 라운드 2 (purpose 답변 후) | 잔여 축 질문 | **Act-1 전** 즉시 proceed ❌ → **Act-1 후** `[tone, constraints, decision_priority]` | ✅ |
| 4b | 라운드 3 (6축 답변) | 6축 병합 | `filled_slots` 6축 전부 | ✅ |
| 4c | SC-4 회귀 (상세 1문장) | 되묻기 없음 | round 0, `questions: []` | ✅ |
| 5 | 2축 에코백 → 프롬프트 반영 | Context/Notes 반영 | `## Context` 2줄 + `## Important Notes` 반영 (FR-19) | ✅ |
| 6 | 논스톱 파이프라인 → 생성 | `created` + bind | `created`, agent_id 발급, `bind_ok: true`, 5단계 전부 ok | ✅ |
| 7 | `GET /agents/{id}` 저장 확인 | 7섹션 보존 | 200, 1,232자, `##` 7개, constraints 반영 (SC-2) | ✅ |
| 8 | OpenAPI 상한 3스키마 | 8000 | 전부 `maxLength=8000` | ✅ |
| 9 | DB `prompt_version` | `schema_version=2`, 8키 | 최근 3행 전부 v2 + 8키 | ✅ |

**L1 Score (Act-1 후)**: 12/12 = **100%**

> Act-1 이전 점수는 7/9 = 78% 였다 (#3·#4가 G-01로 실패).

#### L2: 프론트 액션 (Vitest + RTL + MSW — 규약 이탈 명시)

Playwright가 이 저장소에 없다. `idt_front/CLAUDE.md`가 프론트 검증 도구를 **Vitest + RTL + MSW**로 규정하므로 그 스위트를 L2 대체로 사용한다.

| # | 대상 | 결과 |
|---|------|:----:|
| 1 | `AgentCreateEntryPage` 6파일 81 케이스 | ✅ 81/81 |
| 2 | 카운터 `/ 8000` 표기 | ✅ |
| 3 | 상한 초과 시 저장 차단 / 경계에서 허용 | ✅ |
| 4 | textarea rows·max-h·overflow | ✅ |
| 5 | 라운드 3 안내 | ✅ |

**L2 Score**: **100%**

#### L3: E2E 시나리오

프로젝트에 E2E 하니스가 없다. L1 #1~#7이 서버 측 전체 여정(의도→도구→프롬프트→생성→바인딩→조회)을 실제로 통과했으므로 **L3를 별도 산정하지 않고 L1에 흡수**한다.

**Runtime Match Rate** = (L1 100% + L2 100%) / 2 = **100%**

### 2.7 Match Rate Summary

```
Act-1 이전 (G-01 미수정)
┌─────────────────────────────────────────────┐
│  Structural 100 │ Functional  92             │
│  Contract   100 │ Runtime     89             │
│  Overall: 94.2%   SC 8/9, Critical 1건       │
└─────────────────────────────────────────────┘

Act-1 이후 (현재)
┌─────────────────────────────────────────────┐
│  Structural Match Rate:   100%               │
│  Functional Match Rate:    97%               │
│  Contract Match Rate:     100%               │
│  Runtime Match Rate:      100%               │
│  ─────────────────────────────────────────── │
│  Overall Match Rate:       99%               │
│  =(100×0.15)+(97×0.25)+(100×0.25)+(100×0.35)│
│  = 15.0 + 24.25 + 25.0 + 35.0 = 99.25%      │
├─────────────────────────────────────────────┤
│  ✅ Match:            26 FR (FR-17 회복)     │
│  ⚠️ Partial:           0 FR                  │
│  ❌ Not implemented:   0 FR                  │
│  ⚠️ SC Partial:        1 (SC-3 — G-05 잔여)  │
└─────────────────────────────────────────────┘
```

> Functional 을 100 이 아닌 97 로 두는 이유: 질문·수집 경로는 열렸으나 짧은
> 옵션값의 프롬프트 반영이 약하다 (G-05). 구조가 아니라 지시 품질 문제다.

---

## 3. Gap 목록

### G-01 🔴 Critical — 신규 2축이 되묻기에서 **한 번도 물어지지 않는다** (SC-3 미달)

**증상**

```
요청: "봇 하나 만들어줘"
 round 1 → need_input, 질문 3개: purpose / target_users / data_sources
           missing_slots: [purpose, target_users, data_sources, tone,
                           constraints, decision_priority]   ← 6축 정상
 round 2 → (purpose 답변 후) prompt_ready, 질문 0개
```

**원인** (구조적, LLM 변덕 아님)

1. `PipelinePolicy.decide_after_intent`(`policies.py:56`)는 `result.complete` 면 `proceed` 한다.
2. `complete` 는 **required 슬롯만** 기준으로 계산된다. required 는 `purpose` 하나뿐(FR-16).
3. 따라서 **round 1에서 `purpose` 가 채워지는 순간 되묻기는 끝난다.**
4. round 1의 질문 수는 `max_questions=3`(FR-18)으로 고정이고, LLM은 required 인 `purpose` 를 우선한다.
5. 결과: 신규 2축은 "round 1의 3개 슬롯에 우연히 뽑히는" 경우에만 물어질 수 있고, 6축 중 우선순위가 가장 낮아 **사실상 도달 불가**.

**연쇄 영향 — FR-17이 무력하다**

`INTENT_MAX_CLARIFICATION_ROUNDS` 를 2→3으로 올렸으나, round 2 자체가 `purpose` 미충족일 때만 발생한다. 라운드를 3으로 늘려도 관측 가능한 변화가 없다. Plan이 이 값을 올린 근거("6축을 회당 3개씩 물으면 2라운드로 부족")는 **6축을 다 묻는다는 전제**에 서 있는데, 그 전제가 성립하지 않는다.

**영향 범위**

Plan의 문제 정의는 두 축이었다 — ① 그릇(7섹션) ② 재료(2축 수집). ①은 완전히 해소됐고 ②는 **에코백으로 값이 주어질 때만** 동작한다(L1 #5로 확인). 즉 위저드가 사용자에게서 제약·우선순위를 받아내는 경로가 없다. Plan §1.3이 "이 2개가 목표 예시의 §2 기술적 제약 / §7 Decision Logic / §11 NEVER 항목을 만든다"고 지목한 바로 그 정보다.

**후보 대응** (Act 단계 선택지 — 전부 optional 유지 가능)

| # | 방안 | 변경 지점 | 대가 |
|---|------|-----------|------|
| A | `decide_after_intent` 에 "optional 축이 N개 이상 비어 있고 round < max_rounds 면 ask" 조건 추가 | `domain/agent_create_pipeline/policies.py` 순수 함수 1곳 | 되묻기 왕복이 늘어난다 (R-06). optional 정신과 충돌 가능 |
| B | round 1 질문 선정에서 신규 2축을 우선하도록 프롬프트 지시 | `infrastructure/intent/adapter.py` 프롬프트 | LLM 신뢰 의존 — 2차 방어선 없음 |
| C | 프론트 프롬프트 검토 단계에 "제약/우선순위" 선택 입력을 두고 에코백 | 프론트 + 기존 에코백 경로 재사용 | 위저드 단계가 늘어난다 |
| D | 수용 — SC-3을 "에코백 경로로 반영됨"으로 재정의 | 문서만 | 사용자가 2축을 입력할 방법이 여전히 없음 |

**권고**: A. 순수 함수 1곳 변경이고 테스트 가능하며, 신규 축을 required로 승격하지 않고도(사용자 결정 유지) 문제를 해결한다.

---

#### ✅ Act-1 조치 결과 (사용자 결정: 방안 A)

**사전 실측으로 확인한 것** — 판정만 바꿔도 되는지 검증했다:

```
AnalyzeIntentUseCase 직접 호출
  round 1 + purpose/target_users/data_sources 답변
   → complete=True, missing=[tone, constraints, decision_priority]
   → questions=[tone, constraints, decision_priority]      ← LLM 은 이미 만들고 있었다
  round 0 + 상세 1문장
   → complete=True, questions=[data_sources, tone, constraints]  ← round 0 에도 질문이 생성된다
```

질문은 `complete` 가 아니라 `missing` 으로 필터링되므로(`domain/intent/policies.py:_resolve_questions`) LLM 측 변경은 불필요했다. **동시에 round 0 에서도 질문이 생성된다는 사실이 드러나, "complete 여도 ask" 를 무조건 적용하면 SC-4 가 깨진다는 것이 확인됐다.**

**변경** — `PipelinePolicy.decide_after_intent` (domain 순수 함수 1곳) + 호출부 인자 2개:

```python
if result.degraded:      return "proceed"
if not result.questions: return "proceed"
if not result.complete:  return "ask"
if 1 <= round_ < max_rounds: return "ask"   # ← 신규
return "proceed"
```

구분 기준은 **"이미 물어본 적이 있는가"** 다. round 0 은 아직 아무것도 안 물었으므로 사용자의 한 문장을 존중해 진행하고(SC-4), round ≥ 1 은 이미 대화를 시작했으므로 남은 선언 축을 마저 묻는다(SC-3).

**실서버 재검증**

| 시나리오 | 결과 |
|---|---|
| "봇 하나 만들어줘" round 1 | `need_input`, 질문 `[purpose, target_users, data_sources]` |
| 동 round 2 (purpose 등 답변 후) | `need_input`, 질문 **`[tone, constraints, decision_priority]`** ← 신규 2축 등장 |
| 동 round 3 (6축 전부 답변) | `prompt_ready`, `filled_slots` **6축 전부** 병합 확인 |
| **SC-4 회귀 확인** — 상세 1문장 | `prompt_ready`, **round 0, questions []** ← 되묻기 없이 통과 유지 |

**부수 효과 (수용)**: "건너뛰고 계속하기" 를 round ≥ 1 에서 누르면 한 번 더 물어본다. 라운드 상한 3에서 `_resolve_questions` 가 `round_ >= max_rounds` 일 때 질문을 비우므로 **추가 왕복은 최대 1회로 유계**다. 사용자가 방안 A 선택 시 수용한 R-06 대가에 해당한다.

**FR-17 회복**: round 2가 실제로 발생하므로 라운드 상한 3이 관측 가능한 효과를 갖게 됐다.

### G-02 🟡 Important — 프롬프트 생성 지연이 타임아웃에 근접

| 단계 | 실측 |
|------|------|
| intent | 9.5s |
| tools | 1.5s |
| **prompt** | **14.5s** (설정 상한 20s) |
| 파이프라인 총계 | ~25.5s |

`PROMPT_COMPOSER_TIMEOUT_SEC=20` 대비 여유 5.5s. 도구가 많거나 모델이 느린 시점에 초과하면 degraded 폴백으로 떨어져 **7섹션 고정 문구 프롬프트**가 저장된다. Design O-1이 예상한 항목이며 실측으로 확인됐다.

**권고**: `.env` 에 `PROMPT_COMPOSER_TIMEOUT_SEC=30`. 코드 변경 불필요(config 단일 출처).

### G-03 🟢 Info — `style` 섹션이 얕다

실측 3회 모두 `## Communication Style` 이 한 줄이며, intent `tone` 이 주어지면 그 값을 거의 그대로 복사한다(`격식체` → `격식체`). Plan R-02가 예상한 "섹션이 늘면 일부를 얕게 쓴다"가 이 섹션에서 실제로 나타났다.

**권고**: `prompts.SYSTEM` 의 `style` 지침에 "말투 + 응답 형식 + 권장 구조 3요소를 각각 쓴다"를 명시. Design O-2 항목.

### G-05 🟡 Important — 짧은 옵션값은 프롬프트에서 희석된다 (Act-1 이후 발견)

같은 `constraints` 축이라도 값의 서술성에 따라 반영 강도가 다르다.

| 입력값 | 출력 `## Context` |
|--------|-------------------|
| `"규정 원문에 없는 내용은 절대 답하지 않는다"` (문장) | `- 규정 원문에 없는 내용은 절대 답하지 않는다.` — **거의 그대로** |
| `"출처 명시 필수"` (스펙이 제공하는 옵션값) | `- 정확하고 신뢰할 수 있는 정보를 제공해야 합니다.` — **희석** |

`decision_priority="안전성 우선"` 도 같은 패턴으로 `- 보안과 개인정보 보호를 최우선` 정도로 번역됐다.

문제는 **희석되는 쪽이 우리가 스펙에 넣어 사용자에게 제시하는 선택지**라는 점이다(`spec.py` 의 `options`). 사용자가 버튼으로 고르는 경로가 가장 약한 반영을 낳는다. `intent_block` 은 값을 정상 전달하고 있으므로(FR-19 확인) 원인은 `prompts.SYSTEM` 의 지시 강도다.

**권고**: `constraints`/`decision_priority` 지침을 "주어진 문구를 **그대로 한 줄로 싣고**, 필요하면 부연을 덧붙인다"로 강화. G-03과 같은 파일·같은 성격의 후속 조정이다.

### G-04 🟢 Info — 검증용 데이터가 개발 DB에 남았다

| 대상 | 식별자 | 정리 방법 |
|------|--------|-----------|
| 테스트 계정 | `testuser@sangplus.dev` | `DELETE FROM users WHERE email='testuser@sangplus.dev'` |
| 검증용 에이전트 | `842f0ea6-81ed-4cea-8359-34552e4fe579` (`[검증용] prompt-depth E2E`) | `DELETE /api/v1/agents/{id}` 또는 스튜디오에서 삭제 |
| prompt_session/version | 5건 (위 검증 과정) | 세션은 에이전트 삭제와 무관하게 남는다 |

---

## 4. Risk 재평가 (Plan §5 대비)

| # | Risk | Plan 예상 | 실측 | 재평가 |
|---|------|-----------|------|--------|
| R-01 | strict 모드 위반 | High/Medium | 실 LLM 400 없음, 재귀 탐색 테스트로 정적 차단 | ✅ **해소** |
| R-02 | 생성 품질 저하 | High/High | 7/8 섹션 충실, `style` 만 얕음 | ⚠️ **부분 발현** (G-03) |
| R-03 | 토큰 비용 2배 | Medium/High | 실측 최대 **1,850자** = 상한의 23% | ✅ **크게 완화** |
| R-04 | 지연 → 타임아웃 | Medium/Medium | 14.5s / 20s | ⚠️ **현실 위험** (G-02) |
| R-05 | 표기 이원화 | Low/High | 예상대로 발생, 동작 영향 없음 | ✅ 수용 |
| R-06 | 되묻기 3라운드 피로 | Medium/Medium | 라운드가 아예 2회로 안 감 | ✅ 미발현 (G-01의 이면) |
| R-07 | `schema_version` 분기 누락 | Medium/Low | 역방향 파서 부재 확인, v1 행 1건 존재하나 조회는 `assembled` 만 사용 | ✅ 해소 |
| R-08 | 8000자 지점 누락 | High/Medium | 4곳 일치 테스트로 고정 + OpenAPI 실측 | ✅ 해소 |
| R-09 | 앞 사이클 Check 미실행 | Medium/High | agent-create-wizard 이미 completed(95%) | ✅ 무효 |

---

## 5. Test Coverage

| 영역 | 케이스 | 결과 |
|------|--------|------|
| `tests/domain/prompt_composer/` | 70 | ✅ |
| `tests/infrastructure/prompt_composer/` | 84 | ✅ |
| `tests/application/prompt_composer/` | 34 | ✅ |
| `tests/domain/agent_create_pipeline/` | 58 | ✅ |
| `tests/api/test_prompt_composer_router.py` | 포함 | ✅ |
| 실 LLM (`-m llm`) | 1 | ✅ |
| 프론트 `AgentCreateEntryPage` | 81 | ✅ |

**회귀**: 백엔드 전체 FAILED 목록이 baseline과 **바이트 동일**(80건). 프론트 9건도 stash 실측으로 기존 실패 확정.

> ⚠️ **Plan QC-3 기준값 정정 필요**: Plan은 baseline을 58건으로 적었으나 실측은 **80건**이다. 실패 파일 10개 전부 `prompt_composer` 와 커플링 0.

---

## 6. Clean Architecture Compliance

| Layer | 규칙 | 실측 | 판정 |
|-------|------|------|:----:|
| domain/prompt_composer | 외부 import 0 | `test_domain_layer_has_no_forbidden_imports` (langchain/sqlalchemy/fastapi/pydantic/agent_composer) | ✅ |
| domain | env 미참조 | `spec.py`/`policies.py` 에 os.environ 없음 | ✅ |
| infrastructure | LLM 스키마 격리 | `_PromptDraft` 계열이 domain에 없음 | ✅ |
| interfaces | 로직 금지 | `SectionsOut` 은 선언만 | ✅ |
| 순수성 | `assemble()` 결정적 | 시간·랜덤 없음, 100회 동일 | ✅ |
| 프론트 | 런타임 상수는 `types/` | `MAX_CLARIFY_ROUNDS` 이동 완료 | ✅ |

**Architecture Score**: **100%**

---

## 7. Convention Compliance

| 항목 | 기준 | 실측 | 판정 |
|------|------|------|:----:|
| 함수 길이 | ≤40줄 | 조립을 블록 헬퍼 6종으로 분리 | ✅ |
| if 중첩 | ≤2단 | 조기 반환 패턴 | ✅ |
| config 하드코딩 금지 | env/상수 | 라운드·타임아웃 env, 조립 상한 Policy 상수 | ✅ |
| DDL 주석 | 마이그레이션 시 | **N/A** — 마이그레이션 없음 | — |
| `print()` 금지 | logger | 프로덕션 코드 0건 (테스트 보고 출력은 예외) | ✅ |
| ruff (변경 파일) | 0 | **3건** — 전부 미변경 줄의 기존 오류 (`schemas.py:80` E501, 테스트 I001/UP017) | ⚠️ |
| eslint | 0 | 0 | ✅ |
| `tsc --noEmit` (테스트 포함) | 0 | **0** — QC-2의 직전 사이클 전례 방어 성공 | ✅ |

**Convention Score**: **96%**

---

## 8. Overall Score

```
┌─────────────────────────────────────────────┐
│  Overall Match Rate: 99%   (Act-1 후)        │
├─────────────────────────────────────────────┤
│  Structural:      100                        │
│  Functional:       97                        │
│  Contract:        100                        │
│  Runtime:         100                        │
│  Architecture:    100                        │
│  Convention:       96                        │
│  Success Criteria: 8 Met / 1 Partial         │
└─────────────────────────────────────────────┘
```

> **회귀 측정 주의**: Act-1 직후 전체 스위트가 86 FAILED 로 나왔으나, `.pytest_cache`
> 잔재가 섞인 결과였다. 캐시 삭제 후 재실행하니 baseline 과 **바이트 동일한 80건**.
> 회귀 판정은 캐시를 지우고 측정해야 한다 (`false-green-quality-gates` 계열 함정).

---

## 9. Recommended Actions

### 9.1 완료 (Act-1)

| 항목 | 파일 | 결과 |
|------|------|------|
| ✅ 신규 2축 되묻기 경로 (방안 A) | `domain/agent_create_pipeline/policies.py` + 호출부 | 실서버 round 2에서 두 축 질문 확인, SC-4 무회귀 |

### 9.2 남은 조치

| 우선 | 항목 | 파일 | 기대 효과 |
|:----:|------|------|-----------|
| 🟡 1 | `PROMPT_COMPOSER_TIMEOUT_SEC=30` | `.env` | G-02 / R-04 — 코드 변경 없음 |
| 🟡 2 | `constraints`/`decision_priority` 지침 강화 ("주어진 문구를 그대로 싣는다") | `infrastructure/prompt_composer/prompts.py` | G-05 — 옵션 버튼 경로의 반영 강도 |
| 🟢 3 | `style` 작성 지침 구체화 | 동상 | G-03 / R-02 |
| 🟢 4 | 검증용 계정·에이전트 정리 | DB / 스튜디오 | G-04 |

### 9.3 문서 갱신 필요

- [ ] Plan QC-3의 baseline 58건 → **80건**
- [ ] Design §13 O-1 판정 확정: 타임아웃 30s 권고
- [ ] Design §13 O-3(R-03) 해소 기록: 실측 최대 1,850자
- [ ] Design §5.1에 `_FALLBACK_ROLES` 반영 (Do 단계 보완분)
- [ ] Design §9.2의 `MAX_CLARIFY_ROUNDS` 위치를 `types/agentPipeline.ts` 로 정정

---

## 10. Next Steps

- [ ] Checkpoint 5 결정 → `/pdca iterate prompt-depth` (G-01 수정) 또는 현행 수용
- [ ] 수정 후 재검증: 모호 요청 → round 2에서 신규 2축 질문 확인
- [ ] `/pdca report prompt-depth`

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-08-20 | 최초 분석 — 정적 + 런타임(실서버·실 LLM). Overall 94%, SC 8/9, Critical 1건(G-01) | 배상규 |
