# agent-builder-edit-mapping Analysis Report

> **Analysis Type**: Gap Analysis (PDCA Check)
> **Project**: sangplusbot (idt 백엔드 + idt_front 프론트)
> **Analyst**: gap-detector
> **Date**: 2026-07-14
> **Design Doc**: [agent-builder-edit-mapping.design.md](../02-design/features/agent-builder-edit-mapping.design.md)
> **Plan Doc**: [agent-builder-edit-mapping.plan.md](../01-plan/features/agent-builder-edit-mapping.plan.md)

---

## 1. Analysis Overview

- **Scope**: Design 문서 §2(프론트) + §3(백엔드) + §5(테스트) 설계 항목을 구현 코드와 항목 단위 대조.
- **범위 경계**: FR-6(도구 워커 저장)은 Design에서 명시적으로 후속 feature로 분리 — 본 분석 대상 아님(§2-5 유예 방어 배너만 검증).
- **대상 파일**: 백엔드 5개(application/domain/infrastructure/api) + 프론트 4개 + 테스트 4개.

---

## 2. Overall Scores

| Category | Score | Status |
|----------|:-----:|:------:|
| Design Match | 97% | ✅ |
| Architecture Compliance | 100% | ✅ |
| Convention Compliance | 100% | ✅ |
| **Overall** | **97%** | ✅ |

설계 항목 29개 중 28개 완전 구현, 1개(페이지 레벨 프라임 통합 테스트) 미구현. 프로덕션 코드는 설계와 100% 일치하며, 유일한 갭은 테스트 커버리지 항목이다.

---

## 3. 항목별 대조 (Design vs Implementation)

### 3.1 프론트엔드 §2-1 `mapDetailToForm` 매핑 규칙

| # | 설계 항목 | 구현 위치 | 상태 |
|---|-----------|-----------|:----:|
| 1 | model: `id → model_name` 역매핑 (`?? raw id` 폴백) | agentDetailMapping.ts:27-29 | ✅ |
| 2 | tools: `mapDraftToolIdsToCatalog` 재사용 | agentDetailMapping.ts:60 | ✅ |
| 3 | toolConfigs: RAG worker `tool_config` + DEFAULT 머지 | agentDetailMapping.ts:31-45 | ✅ |
| 4 | subAgents: sub_agent 워커 필터 + `ref_agent_name ?? ref_agent_id` | agentDetailMapping.ts:47-53 | ✅ |
| 5 | skills: `skill_ids ?? []` | agentDetailMapping.ts:64 | ✅ |
| 6 | name/description/systemPrompt/temperature 현행 유지 | agentDetailMapping.ts:56-62 | ✅ |
| 7 | schedules: `[]` (edit 모드 정책) | agentDetailMapping.ts:66 | ✅ |
| 8 | `RAG_CATALOG_TOOL_ID` export + index.tsx/LeftConfigPanel import 전환 | agentDetailMapping.ts:18, index.tsx:24/40, LeftConfigPanel.tsx:25/29 | ✅ |

### 3.2 프론트엔드 §2-2 프라임 effect

| # | 설계 항목 | 구현 위치 | 상태 |
|---|-----------|-----------|:----:|
| 9 | `primedAgentRef` 1회 가드 | index.tsx:89, 93-94 | ✅ |
| 10 | 쿼리 settled 대기 (`isModelsLoading \|\| isToolsLoading`) | index.tsx:92 | ✅ |
| 11 | `setForm(mapDetailToForm(...))` | index.tsx:95 | ✅ |
| 12 | handleEdit/handleNew에서 `primedAgentRef.current = null` 리셋 | index.tsx:108, 116 | ✅ |
| 13 | 기본 모델 effect `view === 'create'` 한정 | index.tsx:78 | ✅ |

### 3.3 프론트엔드 §2-3 수정 저장 모델 전송

| # | 설계 항목 | 구현 위치 | 상태 |
|---|-----------|-----------|:----:|
| 14 | `UpdateBuilderAgentRequest.llm_model_id?` 추가 | agentBuilder.ts:96 | ✅ |
| 15 | handleSave edit 분기 `model_name → id` 역조회 전송 | index.tsx:151 | ✅ |

### 3.4 프론트엔드 §2-4 / §2-5 라벨·배너

| # | 설계 항목 | 구현 위치 | 상태 |
|---|-----------|-----------|:----:|
| 16 | modelLabel: `provider:model_name` / `(미등록 모델)` / `모델 미선택` | LeftConfigPanel.tsx:152-158 | ✅ |
| 17 | `isEditMode` 도구 미저장 안내 배너 | LeftConfigPanel.tsx:323-327 | ✅ |

### 3.5 백엔드 §3-1 ~ §3-5

| # | 설계 항목 | 구현 위치 | 상태 |
|---|-----------|-----------|:----:|
| 18 | `UpdateAgentRequest.llm_model_id: str \| None = None` | application/schemas.py:117 | ✅ |
| 19 | UseCase 생성자 `llm_model_repo` 옵셔널 주입 | update_agent_use_case.py:42, 56 | ✅ |
| 20 | `_validate_llm_model` (repo None → ValueError, 미존재 → ValueError) | update_agent_use_case.py:98-99, 150-158 | ✅ |
| 21 | `apply_update(..., llm_model_id=request.llm_model_id)` 전달 | update_agent_use_case.py:108 | ✅ |
| 22 | 도메인 `apply_update` `llm_model_id` 파라미터 + 대입(존재검증 없음) | domain/schemas.py:129, 144-145 | ✅ |
| 23 | Repository `update()` `model.llm_model_id = agent.llm_model_id` | agent_definition_repository.py:114 | ✅ |
| 24 | DI 배선 `update_uc_factory`에 `_make_llm_model_repo(session)` 재사용 | main.py:2291 | ✅ |

### 3.6 테스트 §5

| # | 설계 항목 | 구현 위치 | 상태 |
|---|-----------|-----------|:----:|
| 25 | FE 단위 `agentDetailMapping.test.ts` (설계 10케이스) | agentDetailMapping.test.ts (14케이스) | ✅ 초과 |
| 26 | FE 컴포넌트 라벨 3 + 배너 2 케이스 | LeftConfigPanel.test.tsx:115-146 | ✅ |
| 27 | BE 도메인 `apply_update` llm_model_id 2케이스 | test_schemas.py:173-184 | ✅ |
| 28 | BE 애플리케이션 `TestUpdateLlmModel` 4케이스 | test_update_agent_use_case.py:402-437 | ✅ |
| 29 | §5-2 페이지 레벨 프라임 통합 테스트 (AgentBuilderStudio.test.tsx / 페이지 테스트) | 없음 | ❌ 미구현 |

---

## 4. Gap 목록

### 🔴 Missing (설계 O, 구현 X)

| 항목 | 설계 위치 | 구현 지점 | 심각도 | 권장 조치 |
|------|-----------|-----------|:------:|-----------|
| 페이지/스튜디오 레벨 프라임 통합 테스트 | design §5-2 | AgentBuilderPage 테스트 부재 | 🟢 Low | 1회 프라임 가드 · settled 대기 · 카탈로그 지연 도착 시 폼 리셋 없음 시나리오를 페이지 테스트로 고정. 순수 함수(mapDetailToForm)는 14케이스로 이미 충분히 검증되어 기능 리스크는 낮으나, effect 배선(primedAgentRef reset, 재프라임 방지)은 자동 회귀 보호가 없다. |

### 🟡 Added (설계 X, 구현 O)

| 항목 | 구현 위치 | 설명 |
|------|-----------|------|
| RAG 오인 방지 테스트 | agentDetailMapping.test.ts:168-184 | sub_agent 워커의 tool_config를 RAG 설정으로 오인하지 않음을 검증하는 추가 케이스(설계 10케이스 외 방어 테스트). 프로덕션 코드 추가 아님 — 설계 함수 구현(worker_type==='tool' 가드)에 대응하는 정당한 초과 커버리지. |

### 🔵 Changed (설계 ≠ 구현)

없음. 프로덕션 코드는 설계 서술과 파일·라인·시그니처 수준까지 일치.

---

## 5. Clean Architecture 준수

| Layer | 설계 기대 | 실제 | 상태 |
|-------|-----------|------|:----:|
| domain (`apply_update`) | 문자열 대입만, 존재 검증 없음 | llm_model_id 대입만 수행 (schemas.py:144-145) | ✅ |
| application (UseCase) | 존재 검증 책임 + 옵셔널 repo 주입 | `_validate_llm_model`에서 검증, 생성자 옵셔널 (기존 조립 무변경) | ✅ |
| infrastructure (repo) | update 컬럼 반영 | 1줄 컬럼 대입, 비즈니스 규칙 없음 | ✅ |
| interfaces/DI (main.py) | 신규 세션 생성 금지, create 팩토리 재사용 | `_make_llm_model_repo(session)` 재사용 | ✅ |

- 의존 방향 위반 없음. domain → infrastructure 참조 없음. 옵셔널 주입 패턴으로 기존 생성 코드 무변경(additive) 확장 준수(CLAUDE.md §4/§6).

---

## 6. Convention 준수

| 항목 | 결과 | 비고 |
|------|:----:|------|
| 네이밍 (PascalCase 컴포넌트 / camelCase 함수 / UPPER_SNAKE 상수) | ✅ | `RAG_CATALOG_TOOL_ID`, `mapDetailToForm`, `AgentBuilderFormData` 규칙 준수 |
| API 계약 동기화 (BE schemas ↔ FE types) | ✅ | `UpdateAgentRequest.llm_model_id` ↔ `UpdateBuilderAgentRequest.llm_model_id` 필드·옵셔널 의미(None/undefined=무변경) 일치 |
| 함수 길이 / if 중첩 (백엔드 CLAUDE.md §3) | ✅ | `_validate_llm_model` 9줄, 중첩 1단계 |
| TDD 흔적 (Red 케이스 존재) | ✅ | 도메인 2 + 애플리케이션 4 + FE 14 + 컴포넌트 5 |

---

## 7. Overall Score

```
┌─────────────────────────────────────────────┐
│  Overall Match Rate: 97% (28/29 items)       │
├─────────────────────────────────────────────┤
│  ✅ Match:              28 items              │
│  🟡 Added (test only):   1 item              │
│  ❌ Not implemented:      1 item (test)       │
│  🔵 Changed:              0 items             │
└─────────────────────────────────────────────┘
```

---

## 8. Recommended Actions

### 8.1 Short-term (선택 — 회귀 보호 강화)

| 우선순위 | 항목 | 파일 | 기대 효과 |
|----------|------|------|-----------|
| 🟢 1 | 프라임 effect 통합 테스트 추가 | idt_front AgentBuilderPage 테스트 신규 | 1회 프라임·settled·재프라임 방지 배선의 자동 회귀 보호 |

### 8.2 Design 문서 갱신 필요 여부

없음. 구현이 설계를 그대로 따르므로 문서 수정 불필요.

### 8.3 수동 확인 (Design §6-5 이월)

- [ ] 기존 에이전트 수정 진입 → 모델 표시명 · 도구 목록 · RAG 배지 확인
- [ ] 모델 변경 저장 → 재진입 시 변경 모델 표시
- [ ] 도구 미저장 안내 배너 노출 확인

---

## 9. 결론

Match Rate **97%** (>= 90%) — 설계와 구현이 잘 일치한다. 9개 프로덕션 파일 전부 설계 서술과 파일·라인 수준까지 일치하며, 프론트/백엔드 계약(None/undefined=무변경)도 동기화되어 있다. 유일한 갭은 페이지 레벨 프라임 통합 테스트(🟢 Low) 부재이며 순수 함수는 이미 충분히 커버되어 기능 리스크는 낮다. 다음 단계로 `/pdca report agent-builder-edit-mapping` 완료 보고서 작성을 권장한다.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-07-14 | Initial gap analysis | gap-detector |
