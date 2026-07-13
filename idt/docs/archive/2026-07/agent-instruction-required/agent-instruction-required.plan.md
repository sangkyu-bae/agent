# agent-instruction-required Planning Document

> **Summary**: 에이전트 생성/수정 시 지침(system_prompt)을 필수값으로 강제하고, 레거시 LLM 자동생성 경로(PromptGenerator·ToolSelector·interview)를 제거한다. 자동 구성은 Fix 에이전트(agent_composer)가 전담한다.
>
> **Project**: sangplusbot (idt 백엔드 + idt_front 프론트엔드)
> **Author**: 배상규
> **Date**: 2026-07-06
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 에이전트 생성 시 지침을 비우면 백엔드 PromptGenerator가 LLM으로 자동생성하는 레거시 경로가 남아 있어, Fix 에이전트(agent_composer)와 자동생성 책임이 이원화되어 있다. UI 문구("비워두면 AI가 자동 생성")도 이 레거시 동작을 안내하고 있다. |
| **Solution** | 지침 자동생성 경로 전체 제거(PromptGenerator, ToolSelector 자동선택, interview 흐름). 생성/수정 모두 지침이 비면 에러 처리(프론트 사전 차단 + 백엔드 검증). 도구는 자동선택만 제거하고 0개 허용. |
| **Function/UX Effect** | 지침 입력란이 필수 필드가 되고, 비운 채 저장하면 즉시 인라인 에러 표시. 생성 API가 create→update 2회 호출에서 1회 호출로 단순화. 자동 구성이 필요하면 Fix 에이전트 탭 사용. |
| **Core Value** | 자동생성 책임을 Fix 에이전트로 일원화하여 예측 가능한 에이전트 생성 동작 확보 + 미사용 LLM 호출 경로(dead code) 제거로 유지보수 비용 절감. |

---

## 1. Overview

### 1.1 Purpose

`/agent-builder`에서 에이전트 생성 시 지침(시스템 프롬프트)이 없으면 **에러 처리**되도록 하고, 백엔드의 레거시 지침 자동생성 경로를 전부 제거한다. 지침·도구 자동 구성은 이미 구현된 **Fix 에이전트(agent_composer, FIX-COMPOSER-001)** 가 전담한다.

### 1.2 Background (현재 코드 확인 결과)

**백엔드 (`idt/`)**
- `POST /api/v1/agents` → `CreateAgentUseCase` (`src/application/agent_builder/create_agent_use_case.py`)
  - Step 1: `tool_ids`/`tool_configs`가 없으면 `ToolSelector.select()`가 LLM으로 도구 자동 선택 (L97-100)
  - Step 3: `system_prompt`가 비면 `PromptGenerator.generate()`가 LLM으로 지침 자동 생성 (L143-152)
- `PromptGenerator`/`ToolSelector`는 create 외에 **interview 흐름**(`interview_use_case.py`, `/api/v1/agents/interview/start·answer·finalize`)에서도 사용되나, **프론트는 interview API를 전혀 호출하지 않음** (dead feature)
- `CreateAgentRequest.system_prompt: str | None` (optional, max 4000자) — `schemas.py:73`
- `AgentBuilderPolicy`: `MIN_TOOLS = 1`, `MIN_WORKERS = 1` (도구 0개 생성 불가), `validate_system_prompt`는 **상한만 검증** (빈 값 미검증)
- `/api/v3/agents/auto` (auto_agent_builder)는 v2 middleware 경로(`CreateMiddlewareAgentRequest`)를 사용하며 항상 `system_prompt`를 채워 보냄 → **이번 변경과 무관**

**프론트 (`idt_front/`)**
- `LeftConfigPanel.tsx:211` — 생성 모드 placeholder: "비워두면 AI가 설명을 기반으로 자동 생성합니다"
- `AgentBuilderPage/index.tsx handleSave`:
  - 검증은 `name`만 수행 (L130)
  - **생성 시 create 요청에 `system_prompt`를 아예 포함하지 않고**, 성공 후 지침이 있으면 update로 덮어쓰는 2-call 구조 (L192-198)
  - 수정 시 빈 지침은 `undefined`(변경 안 함)로 전송 (L138)
- `types/agentBuilder.ts` — `CreateBuilderAgentRequest`에 `system_prompt` 필드 없음 (백엔드는 이미 수용)

**Fix 에이전트**: `agent_composer`(compose API)가 초안의 `system_prompt`를 폼에 프리필 → 사용자가 확인 후 저장. 이 경로는 유지.

### 1.3 Related Documents

- FIX-COMPOSER-001: `idt_front/docs/archive/2026-07/fix-agent-composer/fix-agent-composer.plan.md` (Fix 에이전트, 구현 완료)
- 백엔드 원 설계: `idt/src/claude/task/task-custom-agent-builder.md` (PromptGenerator/ToolSelector 도입 시점 문서 — 본 plan으로 대체됨)

### 1.4 사용자 결정 사항 (2026-07-06 확인)

| 질문 | 결정 |
|------|------|
| 자동생성 제거 범위 | **전부 제거** — create fallback + interview 흐름 + PromptGenerator 클래스 삭제 |
| 도구 자동 선택(ToolSelector) | **자동선택 제거하되 에러 처리는 안 함** — 도구 없는(0개) 에이전트 생성 허용 |
| 수정 모드에서 지침을 비우면 | **에러 처리** — 생성과 동일하게 저장 차단 |

---

## 2. Scope

### 2.1 In Scope

**백엔드 (idt/)**
- [ ] `CreateAgentRequest.system_prompt` 필수화 (공백 문자열 포함 거부)
- [ ] `CreateAgentUseCase` Step 3의 PromptGenerator fallback 제거 → 지침 없으면 에러
- [ ] `CreateAgentUseCase` Step 1의 ToolSelector 자동선택 분기 제거 → `tool_ids`/`tool_configs` 없으면 **빈 워커(0개)로 생성 허용**
- [ ] `AgentBuilderPolicy.validate_system_prompt`에 빈 값/공백 검증 추가 (에러 메시지: "지침(system_prompt)은 비어 있을 수 없습니다." 계열)
- [ ] `AgentBuilderPolicy` 하한 완화: `MIN_TOOLS`/`MIN_WORKERS` 검증 제거 또는 0으로 조정 (상한 검증 유지)
- [ ] `UpdateAgentPolicy.validate_update`: `system_prompt`가 빈 문자열/공백이면 에러 (None = 변경 안 함은 유지)
- [ ] interview 흐름 전체 삭제: 라우터 3개 엔드포인트(start/answer/finalize) + `interview_use_case.py` + `interviewer.py` + `interview_session_store.py` + 관련 스키마 + `main.py` 배선
- [ ] `prompt_generator.py`, `tool_selector.py` 파일 삭제 + `main.py` 배선(L271-272, L1984-1985, L2122-2123, L2194-2195) 및 `CreateAgentUseCase` 생성자 시그니처 정리
- [ ] 도구 0개 에이전트의 실행(run) 경로 검증: `workflow_compiler`가 workers=0을 수용하는지 확인, 미수용 시 LLM 단독 응답 그래프로 처리 (Design 단계에서 확정)
- [ ] 백엔드 테스트: 자동생성 기대 테스트 제거/수정, 빈 지침 에러 테스트·도구 0개 생성 테스트 추가 (TDD)

**프론트 (idt_front/)**
- [ ] `LeftConfigPanel.tsx`: placeholder를 생성/수정 공통 "에이전트의 시스템 프롬프트/지침을 입력하세요..."로 통일, 지침 섹션 필수 표시, 빈 값 저장 시도 시 인라인 에러 메시지
- [ ] `AgentBuilderPage/index.tsx handleSave`: 생성·수정 모두 `systemPrompt.trim()` 비면 저장 차단 + 에러 표시
- [ ] 생성 흐름 단순화: create 요청 본문에 `system_prompt` 직접 포함 (기존 create→update 2-call 패치 제거)
- [ ] 수정 흐름: `system_prompt`를 항상 전송 (`|| undefined` 폴백 제거)
- [ ] `types/agentBuilder.ts`: `CreateBuilderAgentRequest`에 `system_prompt: string` 추가 (API 계약 동기화)
- [ ] 프론트 테스트: `LeftConfigPanel.test.tsx`(placeholder/에러 표시), AgentBuilderPage 저장 검증 테스트 갱신 (TDD)

### 2.2 Out of Scope

- Fix 에이전트(agent_composer) 및 compose API — 변경 없음 (자동 구성 전담 경로로 유지)
- `/api/v2/agents` (middleware agent), `/api/v3/agents/auto` (auto_agent_builder) — 별도 경로, 이번 변경 무관
- 도구 미선택 시 안내/추천 UX 개선 (도구 0개는 에러 없이 허용만)
- 에이전트 스토어 fork/구독 흐름 (기존 지침 복사이므로 영향 없음)
- `user_request`(설명) 필드의 필수 여부 변경 — 현행 유지

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | 생성 API: `system_prompt` 미제공/공백이면 422 에러 (한국어 메시지) | High | Pending |
| FR-02 | 생성 API: PromptGenerator 자동생성 fallback 제거 | High | Pending |
| FR-03 | 생성 API: `tool_ids`/`tool_configs` 미제공 시 도구 0개로 생성 성공 (ToolSelector 제거, 에러 아님) | High | Pending |
| FR-04 | 수정 API: `system_prompt`가 빈 문자열/공백이면 422 에러 (None은 변경 안 함 유지) | High | Pending |
| FR-05 | interview 엔드포인트 3종 및 관련 유스케이스/스토어/스키마 삭제 | Medium | Pending |
| FR-06 | `prompt_generator.py`·`tool_selector.py` 삭제 및 DI 배선 정리 | Medium | Pending |
| FR-07 | 프론트: 지침 비면 생성/수정 저장 차단 + 인라인 에러 표시 | High | Pending |
| FR-08 | 프론트: placeholder에서 자동생성 안내 문구 제거 (생성/수정 통일) | High | Pending |
| FR-09 | 프론트: create 요청에 `system_prompt` 포함 (2-call → 1-call) | High | Pending |
| FR-10 | 도구 0개 에이전트 실행(run/stream) 정상 동작 보장 | High | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| API 계약 동기화 | 백엔드 스키마 변경 시 프론트 타입 동일 PR 내 반영 | `/api-contract-sync` 체크리스트 |
| 하위 호환 | 기존 저장된 에이전트(지침 有)는 조회/실행/수정에 영향 없음 | 회귀 테스트 |
| 아키텍처 준수 | 검증 규칙은 domain policy에, 흐름 제어는 application에 위치 | `/verify-architecture` |
| 테스트 | 변경 유스케이스/컴포넌트 테스트 선행 작성 (Red→Green) | pytest / vitest |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] 지침 없이 생성/수정 요청 시 프론트에서 차단되고, API 직접 호출 시에도 422 에러 반환
- [ ] `PromptGenerator`, `ToolSelector`, interview 관련 코드가 저장소에서 제거됨 (`grep` 0건)
- [ ] 도구 0개 에이전트가 생성되고 실행(run)까지 정상 동작
- [ ] Fix 에이전트 초안 → 폼 프리필 → 저장 흐름 회귀 없음
- [ ] 백엔드 pytest·프론트 vitest 통과 (기존 사전 실패 건 제외 — 신규 회귀 0건)

### 4.2 Quality Criteria

- [ ] 신규/수정 로직 테스트 커버리지 확보 (use case·policy·컴포넌트)
- [ ] lint/type-check 통과
- [ ] `main.py` DI 배선에서 미사용 의존성 잔존 없음

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 도구 0개 에이전트가 `workflow_compiler`/supervisor 그래프에서 실행 불가할 수 있음 | High | Medium | Design 단계에서 `compile()` 0-worker 경로 검증. 미지원 시 final_answer(LLM 단독) 그래프 fallback 설계 |
| `system_prompt` 필수화는 **breaking API change** — 외부 스크립트/테스트가 지침 없이 create 호출 시 422 | Medium | Medium | 프론트와 동일 PR 배포. 에러 메시지에 Fix 에이전트 안내 포함 |
| interview·자동생성 기대 기존 테스트 다수 실패 | Medium | High | 삭제 대상 테스트 목록을 Design에서 명시, 테스트 수정을 구현 순서 첫 단계로 |
| create 2-call→1-call 변경으로 Fix 프리필/스케줄 등록 등 onSuccess 후속 로직 회귀 | Medium | Low | AgentBuilderPage 저장 흐름 통합 테스트로 보호 |
| `MIN_TOOLS`/`MIN_WORKERS` 완화가 서브에이전트 구성 검증(`validate_worker_count`)에 부수 영향 | Low | Low | 상한 검증 유지, 하한만 제거. 서브에이전트 전용 케이스 테스트 유지 |

---

## 6. Architecture Considerations

### 6.1 Project Level

기존 프로젝트 구조 유지 — 백엔드 **Enterprise**(Thin DDD: domain/application/infrastructure/interfaces), 프론트 **Dynamic**(React SPA). 신규 레이어/폴더 없음.

### 6.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 빈 지침 검증 위치 | pydantic min_length / domain policy / 둘 다 | **domain policy(`validate_system_prompt`) 중심 + 스키마는 optional 유지** | 한국어 에러 메시지 통일, create/update 공용. 라우터의 기존 ValueError→422 매핑 재사용 |
| `CreateAgentRequest.system_prompt` 타입 | `str` 필수 / `str \| None` 유지 | **`str \| None` 유지 + use case에서 검증** | v1 스키마를 공유하는 내부 호출자 파급 최소화, 검증 책임은 policy로 일원화 |
| 도구 0개 처리 | 에러 / 허용 | **허용** (사용자 결정) | 도구 없는 순수 대화형 에이전트 허용, 하한 정책 완화 |
| interview 코드 | 유지 / 삭제 | **삭제** (사용자 결정) | 프론트 미사용 dead feature, PromptGenerator 삭제와 결합 |
| 프론트 생성 호출 | 2-call 유지 / 1-call 통합 | **1-call 통합** | 백엔드가 지침 필수가 되므로 create 본문에 포함이 자연스럽고 원자적 |

### 6.3 영향 파일 목록 (확인 완료)

```
백엔드 (idt/)
├── src/application/agent_builder/create_agent_use_case.py   [수정] Step1·Step3 분기 제거, 생성자 정리
├── src/application/agent_builder/prompt_generator.py        [삭제]
├── src/application/agent_builder/tool_selector.py           [삭제]
├── src/application/agent_builder/interview_use_case.py      [삭제]
├── src/application/agent_builder/interviewer.py             [삭제]
├── src/application/agent_builder/interview_session_store.py [삭제]
├── src/application/agent_builder/schemas.py                 [수정] interview 스키마 제거, system_prompt 주석 갱신
├── src/domain/agent_builder/policies.py                     [수정] validate_system_prompt 빈 값 검증, MIN 하한 완화
├── src/api/routes/agent_builder_router.py                   [수정] interview 3 엔드포인트 삭제, docstring 갱신
├── src/api/main.py                                          [수정] DI 배선 정리
├── src/application/agent_builder/workflow_compiler.py       [검증/수정 가능] 0-worker 실행 경로
└── tests/ (agent_builder 관련)                               [수정/추가/삭제]

프론트 (idt_front/)
├── src/components/agent-builder/LeftConfigPanel.tsx          [수정] placeholder·필수 표시·인라인 에러
├── src/components/agent-builder/LeftConfigPanel.test.tsx     [수정]
├── src/pages/AgentBuilderPage/index.tsx                      [수정] handleSave 검증 + 1-call 통합
├── src/types/agentBuilder.ts                                 [수정] CreateBuilderAgentRequest.system_prompt 추가
└── 관련 테스트                                                 [수정/추가]
```

---

## 7. Convention Prerequisites

- 기존 컨벤션 준수: 백엔드 `idt/CLAUDE.md`(레이어 규칙·함수 40줄·logger 필수), 프론트 `idt_front/CLAUDE.md`(services 레이어 경유·TDD·MSW 퍼파일 listen)
- 신규 환경변수: **없음**
- API 계약 동기화: 백엔드 스키마 변경 → `idt_front/src/types/agentBuilder.ts` 동시 수정 (`/api-cotract` 스킬 활용)
- 에러 처리: 스택 트레이스 포함 logger 사용, 라우터의 기존 ValueError 매핑 패턴 재사용

---

## 8. Next Steps

1. [ ] `/pdca design agent-instruction-required` — 설계 문서 작성 (0-worker 실행 경로 검증 결과 반영, 삭제 대상 테스트 목록 확정)
2. [ ] 구현 (TDD: 백엔드 policy/use case → 라우터 → 프론트 타입/페이지/패널 순)
3. [ ] `/pdca analyze agent-instruction-required` — Gap 분석

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-07-06 | Initial draft — 코드 조사 + 사용자 결정 3건 반영 | 배상규 |
