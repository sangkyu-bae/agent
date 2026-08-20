# prompt-depth Planning Document

> **Summary**: 시스템 프롬프트 생성을 4블록에서 **7섹션 마크다운**으로 확장하고, 그것을 채우기 위해 의도 수집에 `constraints`·`decision_priority` 2축을 추가한다.
>
> **Project**: sangplusbot (`idt` 백엔드 + `idt_front` 프론트엔드)
> **Version**: 0.1
> **Author**: 배상규
> **Date**: 2026-08-20
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | "간단한 데이터 분석 에이전트 만들어줘"에 대해 생성되는 프롬프트가 `purpose` + `[역할]` + `[도구 지침]` + `[동작 원칙]` 4블록뿐이다. 사용자가 실제로 필요로 하는 것은 Role/Context/Responsibilities/Workflow/Style/Notes를 갖춘 상세 프롬프트인데, **파이프라인 어느 단계에도 그 정보를 담을 자리가 없다.** |
| **Solution** | 세 지점을 함께 넓힌다 — ① LLM 출력 스키마 `_PromptDraft`를 7섹션으로 ② `assemble()`을 마크다운 헤딩 조립으로 ③ 의도 스펙에 "LLM이 추측하면 위험한" 2축(제약·판단 우선순위)만 추가. 길이 상한은 4000→8000자. |
| **Function/UX Effect** | 같은 한 문장 요청에서 나오는 프롬프트가 4블록 ~500자에서 7섹션 ~3000자 수준으로 깊어진다. 되묻기는 최대 3라운드로 늘지만 신규 2축이 optional이라 **상세히 쓴 요청은 왕복 없이 통과**한다. |
| **Core Value** | 에이전트 품질의 병목이 "무엇을 물어보는가"가 아니라 **"받은 답을 담을 그릇의 크기"**였음을 해소한다. 의도 수집만 깊게 하는 것으로는 도달 불가능한 지점이었다. |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 생성되는 시스템 프롬프트가 얕아 에이전트가 기대만큼 동작하지 않는다. 원인은 질문 부족이 아니라 출력 스키마가 4필드로 고정된 것 |
| **WHO** | P2 — 에이전트 소유자. 특히 도메인 규칙·금지사항이 명확한 업무(분석·심사·상담)에 에이전트를 쓰려는 실무자 |
| **RISK** | ① LLM 출력 스키마 확장 → strict 모드 위반·생성 실패·지연 증가 ② 마크다운 전환으로 기존 저장 프롬프트와 표기 이원화 ③ 프롬프트 8000자는 에이전트 **호출마다** 실리는 고정 토큰 비용 |
| **SUCCESS** | "데이터 분석 에이전트 만들어줘" 1문장 → 7섹션이 모두 채워진 프롬프트가 생성되고 8000자 이내로 저장된다. 기존 경로 회귀 0 |
| **SCOPE** | prompt_composer 스키마·조립 + intent 스펙 2축 + 길이 상한 + 프론트 정합. **기존 에이전트 재생성·Fix 탭은 범위 밖** |

---

## 1. Overview

### 1.1 Purpose

사용자가 목표로 제시한 프롬프트 수준(11섹션 상세 문서)에 **구조적으로 도달 가능한 상태**를 만든다.

현재와 목표의 격차:

```
현재 출력                          목표 출력
─────────────────                  ─────────────────────────────
{purpose}                          # {에이전트 이름}
                                   ## 1. Role and Identity
[역할]                             ## 2. Context
- 검색: 규정을 찾는다              ## 3. Core Responsibilities
                                   ## 4. Tool Guidelines
[도구 지침]                        ## 5. Workflow
- ...                              ## 6. Communication Style
                                   ## 7. Important Notes
[동작 원칙]
- 한국어로 답한다
```

### 1.2 Background

사용자가 목표 예시(데이터 분석 에이전트, 11섹션)를 제시하며 **"의도 파악 에이전트 쪽에서 더 자세하게 분석해서 받아오는 게 필요한 것 같다"**고 진단했다. 실측해 보니 의도 수집은 원인의 **1/3**이었다.

| # | 실제 병목 | 근거 |
|---|-----------|------|
| 1 | **LLM 출력 스키마가 4필드** | `infrastructure/prompt_composer/adapter.py:57-70` — `_PromptDraft`에 `purpose`/`roles`/`tool_guides`/`principles`만 존재 |
| 2 | **조립이 4블록 고정** | `domain/prompt_composer/policies.py:50-54` — `assemble()`이 4개 블록만 이어붙임 |
| 3 | 의도 슬롯 4축 | `domain/agent_create_pipeline/spec.py:19-45` — purpose(required)/target_users/data_sources/tone |

②가 특히 결정적이다: 의도를 아무리 깊게 받아도 그 정보가 `principles[]` 몇 줄로 뭉개진다.

**추가 발견 — 길이 상한**: 목표 수준의 프롬프트는 4000자를 넘는다. `CreateAgentRequest.system_prompt`가 `max_length=4000`이라 저장 자체가 실패한다. 다만 DB 컬럼은 `Text`(`infrastructure/agent_builder/models.py:17`)이므로 **마이그레이션 없이 pydantic 상한만 조정하면 된다.**

### 1.3 질문할 것과 추론할 것의 경계

11섹션을 전부 물어보면 왕복이 폭발한다. 목표 예시를 뜯어보면 두 종류가 섞여 있다.

| 사용자만 아는 것 → **묻는다** | 목적만 알면 LLM이 채우는 것 → **추론한다** |
|---|---|
| 대상 사용자 (기존 `target_users`) | Core Responsibilities |
| 말투·형식 (기존 `tone`) | Workflow 절차 |
| 참조 자료 (기존 `data_sources`) | Examples |
| **지켜야 할 제약·금지사항** ← 신규 | Error Handling |
| **판단 충돌 시 우선순위** ← 신규 | Tool Guidelines (도구 목록에서 파생) |

"데이터 분석 에이전트"라는 목적 한 줄이면 우측은 LLM이 도메인 지식으로 쓴다. 좌측 중 기존 스펙에서 빠져 있던 것이 정확히 **2개**이며, 그 2개가 목표 예시의 §2 기술적 제약 / §7 Decision Logic / §11 NEVER 항목을 만든다.

### 1.4 Related Documents

| 구분 | 문서 |
|------|------|
| 선행 사이클 | `docs/archive/2026-08/prompt-composer/` (§3.2 조립 규칙, Q3/Q4 결정) |
| 선행 사이클 | `docs/archive/2026-08/intent-slot-elicitation/`, `intent-analyzer/` |
| 직전 사이클 | `docs/01-plan/features/agent-create-wizard.plan.md` + `.design.md` (위저드 계약) |
| 위키 (필독) | `conventions/../backend/patterns/structured-output-strict-schema.md` — 자유 키 dict 금지 |
| 위키 (필독) | `backend/patterns/llm-output-trust-boundary.md` — 계산 필드를 LLM 스키마에 두지 않는다 |
| 위키 (필독) | `backend/patterns/declared-slot-elicitation.md` — 되묻기는 선언된 슬롯 축의 함수 |
| 위키 | `conventions/additive-contract-extension.md`, `conventions/config-single-source-at-consumption.md` |
| 위키 | `conventions/false-green-quality-gates.md` — 회귀는 FAILED 목록 diff로 |

---

## 2. Scope

### 2.1 In Scope

**백엔드 — prompt_composer**

- [ ] `PromptSections`를 7섹션으로 확장: `purpose` · `identity` · `context` · `roles[]` · `tool_guides[]` · `workflows[]` · `style` · `principles[]`
- [ ] LLM 스키마 `_PromptDraft` 동반 확장 (**strict 모드 호환 — 자유 키 dict 금지**)
- [ ] `assemble()`을 **마크다운 헤딩 조립**으로 전환 (`## 1. Role and Identity` 형식)
- [ ] 섹션별 항목 수 상한(`clamp_sections`) 신규 섹션까지 확대
- [ ] `prompt_version.schema_version`을 **2**로 (V062가 이 용도로 넣어둔 컬럼 — 마이그레이션 불필요)
- [ ] 생성 프롬프트(`prompts.py SYSTEM`)에 신규 섹션 작성 지침 추가

**백엔드 — intent**

- [ ] `build_agent_create_spec()`에 `constraints` · `decision_priority` 2축 추가 (**둘 다 optional**)
- [ ] `INTENT_MAX_CLARIFICATION_ROUNDS` 2 → 3

**백엔드 — 길이 상한 (4000 → 8000)**

- [ ] `CreateAgentRequest.system_prompt` / `UpdateAgentRequest.system_prompt`
- [ ] `PipelinePolicy.PROMPT_MAX_CHARS`
- [ ] `AppendVersionRequest.assembled` (`MAX_ASSEMBLED_CHARS`)

**프론트엔드**

- [ ] `MAX_ASSEMBLED_CHARS` 8000 정합 (PromptStep 카운터 포함)
- [ ] `MAX_CLARIFY_ROUNDS` 3 정합
- [ ] 프롬프트 검토 단계가 길어진 본문을 다룰 수 있는지 확인 (textarea 높이·스크롤)

### 2.2 Out of Scope

| 제외 항목 | 사유 |
|-----------|------|
| **기존 에이전트 프롬프트 재생성** | 사용자 결정. 의도 수집 없이 재생성하면 오히려 얕은 프롬프트가 기존 것을 덮을 위험. 저장된 프롬프트는 그대로 동작하며 필요 시 스튜디오에서 직접 편집 |
| **Fix 탭(`POST /api/v1/agents/compose`)** | 사용자 결정. `agent_composer`는 별도 모듈·별도 스키마다. 동시 변경은 변경면을 2배로 만든다. "생성 경로 3종 공존"(R1) 수렴 사이클에서 함께 다룬다 |
| `/api/v3/agents/auto` (세션형 빌더) | 위와 동일 — R1 수렴 대상 |
| 11섹션 전체 (Examples·Error Handling·Decision Logic·Middleware Guidelines 독립 섹션) | 사용자 결정(핵심 7섹션). 해당 내용은 `workflows`·`principles`에 흡수한다 |
| 신규 2축을 required로 승격 | 사용자 결정 — "간단한 봇 하나"에 3라운드를 강요하지 않는다 |
| 프롬프트 토큰 비용 최적화 (캐싱 등) | 별도 관심사. 본 사이클은 상한만 올리고 비용은 R-03으로 관측 |

---

## 3. Requirements

### 3.1 Functional Requirements — prompt_composer

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | `PromptSections`에 `identity`(대상 사용자·톤·핵심 목적) 섹션 추가 | High | Pending |
| FR-02 | `PromptSections`에 `context` 섹션 추가 — `constraints[]`(기술적 제약·금지) + `background[]`(관련 배경) | High | Pending |
| FR-03 | `PromptSections`에 `workflows[]` 추가 — 상황별 절차(`situation` + `steps[]`). 일반/복잡/모호 요청 등 | High | Pending |
| FR-04 | `PromptSections`에 `style` 추가 — 톤·응답 형식·표현 원칙·권장 구조 | High | Pending |
| FR-05 | LLM 스키마 `_PromptDraft`를 동반 확장하되 **`dict[str, X]` 필드를 만들지 않는다** — strict 모드가 무효화된다 | High | Pending |
| FR-06 | 계산 필드(`degraded`/`dropped_tool_ids`/`unknown_tool_ids`/`elapsed_ms`)는 여전히 LLM 스키마에 두지 않는다 | High | Pending |
| FR-07 | `assemble()`이 마크다운 헤딩으로 조립 — `# {이름}` + `## 1..7`. **빈 섹션은 헤더째 생략** | High | Pending |
| FR-08 | `assemble()`의 **결정적 조립** 유지 — 동일 입력 → 바이트 동일 출력 (시간·UUID·랜덤 금지) | High | Pending |
| FR-09 | `clamp_sections`가 신규 섹션에도 항목 수 상한 적용 | Medium | Pending |
| FR-10 | 규칙기반 폴백(`degraded`) 경로도 7섹션 구조를 유지 — 섹션 일부만 채우고 나머지는 생략 | High | Pending |
| FR-11 | 환각 도구 폐기(`drop_hallucinated`)가 신규 섹션 추가 후에도 그대로 동작 | High | Pending |
| FR-12 | `prompt_version.schema_version = 2`. 기존 `schema_version=1` 행은 그대로 읽힌다(조회 API 무변경) | High | Pending |
| FR-13 | `prompts.py SYSTEM`에 신규 섹션 작성 지침 추가 — 각 섹션이 무엇인지, 도구가 없어도 작성하는지 | High | Pending |

### 3.2 Functional Requirements — intent / 파이프라인

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-14 | `build_agent_create_spec()`에 `constraints` 축 추가 — "반드시 지켜야 할 것 / 하지 말아야 할 것", **optional** | High | Pending |
| FR-15 | 동 `decision_priority` 축 추가 — "판단이 충돌할 때 우선순위", **optional** | High | Pending |
| FR-16 | `purpose`만 required 유지 — 상세히 쓴 1문장 요청은 되묻기 없이 도구 단계로 진행 | High | Pending |
| FR-17 | `INTENT_MAX_CLARIFICATION_ROUNDS` 기본값 2 → 3. **단일 출처는 IntentConfig** (파이프라인이 별도 값을 갖지 않는다) | High | Pending |
| FR-18 | 6축이 되어도 회당 질문 상한(`max_questions=3`)은 유지 — 한 번에 3개를 넘겨 묻지 않는다 | Medium | Pending |
| FR-19 | 신규 2축의 값이 `prompt_composer`에 전달되어 `context`/`principles` 섹션의 근거가 된다 | High | Pending |

### 3.3 Functional Requirements — 길이 상한 / 프론트

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-20 | `system_prompt` 상한 4000 → **8000** (Create/Update 요청 스키마 2곳) | High | Pending |
| FR-21 | `PipelinePolicy.PROMPT_MAX_CHARS` 8000 정합 — clamp 사유 문구도 갱신 | High | Pending |
| FR-22 | `AppendVersionRequest.assembled` 상한 8000 정합 | High | Pending |
| FR-23 | 프론트 `MAX_ASSEMBLED_CHARS` 8000 — PromptStep 카운터·초과 차단이 서버와 동일 기준 | High | Pending |
| FR-24 | 프론트 `MAX_CLARIFY_ROUNDS` 3 — 서버 `SlotLimits.max_rounds`와 정합 | Medium | Pending |
| FR-25 | 프롬프트 검토 textarea가 3000자 이상 본문에서도 읽을 만해야 한다 (높이·스크롤 확인) | Medium | Pending |
| FR-26 | 기존 논스톱 파이프라인·기존 5경로 무변경 | High | Pending |

### 3.4 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| **strict 호환** | `_PromptDraft`에 자유 키 dict 0건 — 재귀 탐색 테스트로 정적 차단 | 기존 strict 스키마 테스트 확장 |
| **실 LLM 검증** | 확장 스키마로 **실제 OpenAI 호출 1회 이상** 성공 — fake로만 검증하고 닫지 않는다 | `test_real_llm.py` 갱신 (스킵 조건 명시) |
| **지연** | 섹션 증가로 생성 시간이 늘어난다. `PROMPT_COMPOSER_TIMEOUT_SEC`(20s) 내 완료되는지 실측 | 실서버 계측 + 초과 시 config 조정 |
| **결정성** | `assemble()` 동일 입력 → 바이트 동일 (SC-03 승계) | 순수 함수 테스트 |
| **회귀** | 기존 경로 무변경 | 정렬된 `FAILED` 목록 diff |
| **아키텍처** | 조립·절단 규칙은 domain 순수 함수 유지, LLM 스키마는 infrastructure에만 | AST 경계 테스트 + 리뷰 |

---

## 4. Success Criteria

### 4.1 Definition of Done

| # | Criteria | 검증 방법 |
|---|----------|-----------|
| SC-1 | "데이터 분석 에이전트 만들어줘" 1문장 → **7섹션이 모두 채워진** 프롬프트 생성 | 실서버 수동 E2E + 섹션 존재 단언 |
| SC-2 | 생성 프롬프트가 8000자 이내로 **저장 성공** (`GET /agents/{id}`로 확인) | 실서버 E2E |
| SC-3 | 되묻기에서 `constraints`·`decision_priority` 질문이 실제로 나오고, 답변이 프롬프트 `context`/`principles`에 반영된다 | 실서버 E2E + 응답 단언 |
| SC-4 | 상세히 쓴 1문장 요청은 **되묻기 없이** 도구 단계로 진행 (optional 축이 왕복을 강요하지 않음) | API 테스트 |
| SC-5 | `assemble()`이 마크다운 헤딩으로 조립하고 빈 섹션은 헤더째 생략 | 순수 함수 테스트 |
| SC-6 | 확장 스키마로 **실제 LLM 호출 1회 성공** — strict 400이 나지 않는다 | `test_real_llm.py` |
| SC-7 | 규칙기반 폴백도 7섹션 구조로 나온다 | 단위 테스트 |
| SC-8 | 신규 코드 TDD (테스트 선작성 → red → 구현 → green) | 커밋 순서 |
| SC-9 | 기존 경로 회귀 0 — **정렬된 `FAILED` 목록 diff** | 백엔드/프론트 전체 스위트 |

### 4.2 Quality Criteria

> 전역 기준은 단일 사이클로 달성 불가하므로 **이 사이클이 변경한 파일 기준**으로 서술한다.

| # | Criteria |
|---|----------|
| QC-1 | 변경 파일 lint 0건 (전역 기존 에러는 baseline으로 분리 기록) |
| QC-2 | 변경 파일 타입 에러 0건. **테스트 파일 포함** — 직전 사이클에서 테스트 파일 타입 에러를 놓친 전례가 있다 |
| QC-3 | 백엔드 전체 스위트 baseline(58건) 외 신규 `FAILED` 0건 |
| QC-4 | 프론트 실패 목록이 직전 커밋과 동일 |
| QC-5 | `_PromptDraft` 재귀 탐색에서 `dict` 필드 0건 |

---

## 5. Risks and Mitigation

| # | Risk | Impact | Likelihood | Mitigation |
|---|------|--------|------------|------------|
| R-01 | **strict 모드 위반** — 신규 섹션에 dict를 쓰면 매 호출 400, 판정이 항상 degraded로 떨어진다. 위키에 3개월 은폐된 실사례 존재 | High | Medium | 전 필드를 고정 필드/배열로. 재귀 탐색 테스트로 정적 차단. **실 LLM 1회 성공을 DoD로**(fake만으로 닫지 않는다) |
| R-02 | **생성 품질 저하** — 섹션이 늘면 LLM이 각 섹션을 얕게 쓰거나 일부를 비울 수 있다 | High | High | `prompts.py`에 섹션별 작성 지침 명시. 실서버에서 실제 출력 확인 후 프롬프트 조정. degraded 폴백이 7섹션을 유지하도록 |
| R-03 | **토큰 비용 증가** — 시스템 프롬프트는 에이전트 **호출마다** 전송된다. 4000→8000자면 호출당 고정 비용이 최대 2배 | Medium | High | 상한일 뿐 항상 8000자가 되진 않음. 실제 생성 길이를 실측해 보고. 필요하면 후속 사이클에서 캐싱/압축 검토 |
| R-04 | **지연 증가** — 섹션 7개 생성이 20초 타임아웃을 넘기면 degraded 폴백으로 떨어진다 | Medium | Medium | 실측 후 `PROMPT_COMPOSER_TIMEOUT_SEC` 조정. config 단일 출처 원칙 준수 |
| R-05 | **표기 이원화** — 기존 에이전트는 대괄호, 신규는 마크다운. 스튜디오에서 나란히 보면 섞여 보인다 | Low | High | 사용자 결정으로 수용(재생성 범위 밖). 동작에는 영향 없음 |
| R-06 | **되묻기 3라운드 피로** — 축이 6개가 되어 질문이 길어지면 사용자가 이탈한다 | Medium | Medium | 신규 2축 optional + 회당 질문 3개 유지 + 건너뛰기 버튼 존재. 실사용에서 라운드 분포 관측 |
| R-07 | **`schema_version` 분기 누락** — 2로 올렸는데 조회 코드가 1/2를 구분하지 않으면 과거 행 파싱이 깨진다 | Medium | Low | 현재 조회는 `assembled` 텍스트만 쓰고 `sections`를 역파싱하지 않음(`repository.py:220` 주석) — 실제 위험 낮음. Design에서 재확인 |
| R-08 | **8000자 변경 지점 누락** — 5곳 중 하나만 빠져도 마지막 저장 단계에서 422 | High | Medium | 변경 지점을 FR로 개별 명시(FR-20~23) + 8000자 경계 테스트 |
| R-09 | 앞 사이클(agent-create-wizard)이 **Check 미실행** 상태에서 코드가 또 바뀐다 | Medium | High | 이 사이클 Do 착수 **전에** agent-create-wizard의 analyze/report를 먼저 닫는다 (§9 순서) |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `domain/prompt_composer/schemas.py` | Domain VO | `PromptSections` 4→7섹션, 신규 VO 3종(Identity/Context/Workflow/Style) |
| `domain/prompt_composer/policies.py` | Domain 규칙 | `assemble()` 마크다운 전환, `clamp_sections` 확대, 폴백 확장 |
| `infrastructure/prompt_composer/adapter.py` | LLM 스키마 | `_PromptDraft` 확장 (strict 호환 필수) |
| `infrastructure/prompt_composer/prompts.py` | 프롬프트 | SYSTEM 규칙에 신규 섹션 지침 |
| `infrastructure/prompt_composer/repository.py` | 영속 | `_sections_to_json` 신규 섹션 직렬화, `_SCHEMA_VERSION` 2 |
| `interfaces/schemas/prompt_composer.py` | API | `SectionsOut` 확장, `MAX_ASSEMBLED_CHARS` 8000 |
| `domain/agent_create_pipeline/spec.py` | Domain 상수 | 슬롯 2축 추가 |
| `domain/agent_create_pipeline/policies.py` | Domain | `PROMPT_MAX_CHARS` 8000 |
| `infrastructure/config/intent_config.py` | Config | `INTENT_MAX_CLARIFICATION_ROUNDS` 3 |
| `application/agent_builder/schemas.py` | API | `system_prompt` 상한 8000 (2곳) |
| `idt_front/src/types/agentPipeline.ts` | 프론트 상수 | `MAX_ASSEMBLED_CHARS` 8000 |
| `idt_front/src/pages/AgentCreateEntryPage/index.tsx` | 프론트 | `MAX_CLARIFY_ROUNDS` 3 |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| `PromptSections` | 생성 | `ComposePromptUseCase._finalize` | **Breaking(의도)** — 필드 추가, 생성자 호출부 전부 확인 |
| `PromptSections` | 조립 | `PromptAssemblyPolicy.assemble` | **Breaking(의도)** — 출력 포맷 변경 |
| `PromptSections` | 폐기 | `drop_hallucinated` / `_replace_guides` | **Needs verification** — `tool_guides`만 교체하는 헬퍼가 신규 필드를 떨어뜨리지 않는지 |
| `PromptSections` | 직렬화 | `repository._sections_to_json` | **Needs verification** — 신규 섹션 누락 시 조용히 유실 |
| `PromptSections` | 응답 | `prompt_composer_router._to_sections_out` | **Needs verification** — `SectionsOut` 확장 동반 필요 |
| `assemble()` 출력 | 소비 | 파이프라인 `assembled_prompt` → 위저드 PromptStep → 스튜디오 `system_prompt` | **None** — 문자열 계약이라 포맷 변경은 투명 |
| `system_prompt` 4000 상한 | 검증 | Create/Update 요청, `clamp_prompt`, append 엔드포인트 | **Breaking(의도)** — 8000으로 완화(값 확대라 기존 입력 전부 유효) |
| `build_agent_create_spec()` | 주입 | `AgentCreatePipelineUseCase._spec` | **Needs verification** — 축 증가가 `reuse_intent`의 spec 검증(신규 축 허용)에 반영되는지 |
| `SlotLimits.max_rounds` | clamp | `PipelinePolicy.clamp_round`, 어댑터 "남은 라운드" 안내 | **Needs verification** — 단일 출처(IntentConfig) 유지 |
| `MAX_CLARIFY_ROUNDS`(프론트) | 표기 | `IntentStep` "남은 질문 라운드" | **Needs verification** — 서버와 어긋나면 안내가 거짓말이 된다 |
| `prompt_version.sections` | 저장/조회 | `append_version` / `GET /sessions/{id}` | **Needs verification** — 조회는 `assembled`만 쓰므로 영향 낮음(재확인) |
| `agent_composer` (Fix 탭) | 별도 경로 | `compose_agent_use_case` | **None** — 범위 밖, 물리적 무변경 확인 |

### 6.3 Verification

- [ ] `PromptSections` 생성자 호출부 전수 확인 (누락 시 TypeError)
- [ ] `_replace_guides` 등 부분 교체 헬퍼가 신규 필드를 보존하는지
- [ ] `_sections_to_json` ↔ `SectionsOut` ↔ `_PromptDraft` 세 곳의 필드 집합 동등성
- [ ] 8000자 변경 지점 5곳 전부 반영 (경계 테스트 8000/8001)
- [ ] 라운드 상한이 서버·프론트·어댑터 안내 3곳에서 일치
- [ ] `agent_composer`·`auto_agent_builder` 물리적 무변경 (`git diff --stat`)
- [ ] 기존 `schema_version=1` 행 조회가 깨지지 않음

---

## 7. Architecture Considerations

### 7.1 Project Level

Enterprise — 기존 Thin DDD 구조를 그대로 따른다 (domain 규칙 / infrastructure LLM 스키마 분리).

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 섹션 범위 | 4 유지 / **7** / 11 / 자유 마크다운 | **핵심 7섹션** | 사용자 결정. 11섹션은 LLM 스키마가 커져 생성 실패·지연 위험, 자유 마크다운은 결정적 조립·환각 도구 폐기·섹션 재생성을 전부 잃는다 |
| 출력 표기 | 대괄호 유지 / **마크다운 헤딩** | **마크다운** | 사용자 결정. 7섹션은 대괄호로 계층이 안 보이고, LLM도 마크다운 헤딩을 섹션 경계로 더 잘 인식 |
| 의도 축 | 유지 / **+2** / +5 | **+2 (constraints·decision_priority)** | 사용자 결정. LLM이 추측하면 위험한 것만 묻는다 — 나머지는 목적에서 추론 가능 |
| 신규 축 required | required / **optional** | **둘 다 optional** | 사용자 결정. required면 "간단한 봇"에도 되묻기를 강요한다 |
| 라운드 상한 | 2 / **3** / 4 | **3** | 사용자 결정. 6축을 회당 3개씩 물으면 2라운드로 부족 |
| 길이 상한 | 4000 / **8000** / 12000 | **8000** | 사용자 결정. 목표 예시에 여유를 두되 호출당 고정 토큰 비용 통제 |
| 기존 에이전트 재생성 | 포함 / **제외** | **제외** | 사용자 결정. 의도 수집 없는 재생성은 얕은 프롬프트가 기존 것을 덮을 위험 |
| Fix 탭 동반 확장 | 포함 / **제외** | **제외** | 사용자 결정. 별도 모듈·별도 스키마, R1 수렴 사이클에서 |

### 7.3 Design 단계에서 판정할 열린 질문

| # | 질문 | 후보 |
|---|------|------|
| A-1 | 7섹션 VO 구조 | (a) 섹션별 전용 VO 4종 신설 (b) 범용 `NamedSection(title, items[])` 하나로 통일 — 유연하지만 조립 규칙이 약해짐 |
| A-2 | `_PromptDraft` 확장 방식 | (a) 도메인 VO와 1:1 대응 (b) LLM 부담을 줄이려 일부 섹션을 평면 배열로 받고 서버가 구조화 |
| A-3 | 마크다운 섹션 번호 | (a) 고정 번호(`## 1.`~`## 7.`) — 빈 섹션 생략 시 번호가 튄다 (b) 번호 없이 제목만 (c) 렌더 시 재부여 |
| A-4 | 에이전트 이름을 `# 제목`으로 넣을 것인가 | 프롬프트 생성 시점에 이름이 확정되지 않을 수 있다(위저드는 서버 제안값) |
| A-5 | 도구 0개일 때 `## Tool Guidelines` | (a) 헤더째 생략(현행 계약) (b) "사용 가능한 도구 없음" 명시 |
| A-6 | degraded 폴백의 7섹션 형태 | 어디까지 채우고 어디를 비울 것인가 |
| A-7 | 신규 2축을 프롬프트에 전달하는 경로 | `intent_snapshot`의 `filled_slots`를 `intent_block()`이 어떻게 싣는가 (현재는 label만 명시적) |
| A-8 | `PROMPT_COMPOSER_TIMEOUT_SEC` 상향 필요 여부 | 실측 후 판단 |

---

## 8. Convention Prerequisites

### 8.1 Existing Conventions

- [x] CLAUDE.md 3종 + `idt/docs/rules/`
- [x] `docs/wiki/` — 특히 strict 스키마·LLM 신뢰 경계·슬롯 되묻기 3종이 이 사이클의 직접 근거
- [x] TDD (pytest / Vitest), ruff, eslint

### 8.2 To Verify

| Category | 확인 사항 | Priority |
|----------|-----------|:--------:|
| **strict 스키마** | `_PromptDraft` 재귀 탐색에 dict 0건 — 기존 테스트가 신규 필드까지 훑는지 | High |
| **LLM 신뢰 경계** | 계산 필드를 신규 섹션에 끼워넣지 않았는지 | High |
| **config 단일 출처** | 라운드 상한이 IntentConfig 한 곳에서만 정의되는지 | High |
| **결정적 조립** | `assemble()`에 시간·랜덤 유입 없는지 | High |
| **additive 확장** | 응답 스키마 신규 필드가 구형 소비자를 깨지 않는지 | Medium |
| **타입 검사 범위** | `tsc`를 **테스트 파일 포함**해서 확인 (직전 사이클 누락 전례) | High |

### 8.3 Environment Variables

| Variable | Purpose | Change |
|----------|---------|:------:|
| `INTENT_MAX_CLARIFICATION_ROUNDS` | 되묻기 라운드 상한 | 2 → **3** |
| `PROMPT_COMPOSER_TIMEOUT_SEC` | 프롬프트 생성 타임아웃 | 실측 후 판단 (기본 20.0) |
| `OPENAI_API_KEY` | 실 LLM 검증(SC-6)에 필요 | 기존 |

### 8.4 Migration

**없음.** `prompt_version.schema_version`은 V062에 이미 존재하는 컬럼이고 값만 2로 올린다. `system_prompt`는 DB가 `Text`라 8000자 확대에 DDL 변경이 불필요하다.

---

## 9. Next Steps

1. [ ] **선행 — `agent-create-wizard` 사이클을 먼저 닫는다** (`/pdca analyze` → `/pdca report`). 서버가 떠 있는 지금이 runtime 검증 포함 채점의 적기이며, 코드가 또 바뀌기 전에 그 사이클의 계약을 확정해야 한다 (R-09)
2. [ ] Design 문서 작성 — §7.3 열린 질문 A-1~A-8을 3안 비교로 판정
3. [ ] Design에 **Plan FR → Design 절 매핑 표** 포함 (요구 유실 방지)
4. [ ] Do 세션 분할 예상: ① prompt_composer 스키마·조립 ② 프롬프트 지침 + 실 LLM 검증 ③ intent 2축 + 라운드 ④ 길이 상한 5곳 + 프론트 정합
5. [ ] 실서버 E2E에서 **실제 생성된 프롬프트 전문을 사용자와 함께 확인** — 이 사이클의 성패는 테스트가 아니라 그 출력물이 판단한다

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-08-20 | 최초 작성 — 사용자 결정 8건(7섹션·마크다운·2축 optional·라운드 3·8000자·재생성 제외·Fix 탭 제외·새 사이클) 반영 | 배상규 |
