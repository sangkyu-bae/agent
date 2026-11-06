# wizard-template-request Gap Analysis

> **Feature**: wizard-template-request
> **Date**: 2026-11-06
> **Analyzer**: gap-detector (정적) + 세션 런타임 검증
> **Design**: `docs/02-design/features/wizard-template-request.design.md`
> **Plan**: `docs/01-plan/features/wizard-template-request.plan.md`
> **Worktree**: `wt/wizard-template-request` (브랜치 `feature/wizard-template-request`, 미커밋)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 위저드는 문서추출기를 추천하지만 양식을 받지 않아, 비개발자가 양식 없는 에이전트를 만들거나 스튜디오에서 올릴 곳을 못 찾는다. |
| **WHO** | P2 부서 담당자(비개발자). |
| **RISK** | 추출 실패 5종을 삼키면 "완료"로 위장. 추천 슬롯 그대로 확정. 클라 템플릿 입력 신뢰. |
| **SUCCESS** | 스튜디오 진입 0회로 템플릿 저장. 기존 위저드·스튜디오 패널 회귀 0건. |
| **SCOPE** | M1 백엔드 → M2 위저드 카드 → M3 핸드오프·스튜디오 안내 |

---

## Strategic Alignment Check

### Plan Alignment

- 핵심 문제(WHY)는 해결됐다. 추출기가 확정되면 위저드가 양식을 먼저 묻고, 첨부 즉시 분석해 템플릿을 에이전트에 매핑한다. 사용자는 스튜디오 패널을 찾지 않는다.
- **전제 오류 1건(G1)**: Plan SC-1·FR-10과 Design §2.2 "[생성 요청] (stop_after 없음)"·§5.2 4단계 "[에이전트 만들기]"는 위저드가 에이전트를 생성한다고 가정했다. 그러나 기존 위저드는 **무저장 계약**이다(`index.tsx:127` 주석, 모든 요청에 `stop_after`, 마지막 버튼은 "스튜디오로 보내기"). 생성은 스튜디오 [저장]에서 일어난다. 템플릿은 핸드오프를 거쳐 스튜디오 저장 요청에 실리므로 최종 결과(템플릿이 저장된 에이전트)는 같지만, "스튜디오 진입 0회"는 성립하지 않는다. 백엔드 CREATE 전달(FR-04)과 422(SC-6)는 외부 동기 호출자 경로에서만 실행된다.

### Success Criteria Status

| SC | 상태 | 근거 |
|----|------|------|
| SC-1 완주·템플릿 저장 | ⚠️ Partial | 핸드오프 `index.tsx:402-404` → `wizardResultToForm.ts:38-42` → 스튜디오 저장 `AgentBuilderPage/index.tsx:448`. 템플릿은 저장되나 스튜디오 1회 진입 필요(G1). GET 상세 확인은 수동(L3-01) |
| SC-2 요청 0건이면 화면 동일 | ✅ Met | `DocumentsStep.tsx:70` 조건 렌더, `policies.py:274-275`; 테스트 `DocumentsStep.test.tsx`(L2-01), `index.test.tsx`(⑥ 첫 케이스) |
| SC-3 실패 5종 안내·재시도 | ✅ Met | `documentExtractorErrors.ts:9-17` + `FormTemplateRequestCard.tsx:68-70,140`; 테스트 `documentExtractorErrors.test.ts` 5건, 카드 L2-05 |
| SC-4 건너뛰기 → `?edit` 안내 | ⚠️ Partial | 안내는 뜬다(`DocumentExtractorConfigPanel.tsx:289-296`, 테스트 L2-10). 그러나 템플릿이 **이미 저장된** 에이전트에서도 뜬다(G3) |
| SC-5 직접 만들기 → 패널 확정 상태 | ✅ Met (정적) | 핸드오프 + `wizardResultToForm.test.ts` 4건, `index.test.tsx` ⑦. 화면 확인은 수동 |
| SC-6 추출기 없는 템플릿 422 | ✅ Met | `use_case.py:339-341`, 라우터 `:93-94`; 테스트 `test_use_case_template.py:77`, 라우터 테스트 `:130` |

### Decision Record Verification

| ID | 준수 | 비고 |
|----|:--:|------|
| D1 요청은 모든 outcome에서 확정 목록 기준 | ✅ | `use_case.py:436,470`, need_input은 `()` |
| D2 드래프트 형태 재사용 | ✅ | `wizardTemplate.ts:26-40` |
| D3 저장 전 정합 검증 | ✅ | `use_case.py:339` |
| D4 422는 파이프라인 라우터에만 | ✅ | 단, G1 때문에 위저드 경로는 이 매핑의 보호를 받지 못한다(G2) |
| D5 스튜디오 안내는 프론트 상수 | ✅ | `agentPipeline.ts:140` |
| D6 카드 미리보기 없음 | ✅ | `previewHtml` 미보관 |
| D7 `document_template_attached` 에코백 | ⚠️ | 서버는 내려주나 프론트가 읽지 않음(G8) |

---

## 1. Analysis Overview

### 1.1 Analysis Purpose

Design(Option C)과 worktree 구현의 일치도를 정적 3축 + 런타임(기존 pytest·vitest 실행)으로 측정하고, Plan SC 충족 여부와 결정 준수를 확인한다.

### 1.2 Analysis Scope

백엔드 5파일 + 테스트 3파일, 프론트 10파일 수정 + 6파일 신규(테스트 포함). 기존 결함 2건(스튜디오 생성 경로 템플릿 검증 500, `source_file_id` 소유자 미검증)은 이 기능의 갭으로 세지 않는다.

---

## 2. Gap Analysis (Design vs Implementation)

### 2.1 API Endpoints

| Design §4.1 | 실제 | 상태 |
|---|---|---|
| `POST /api/agent-pipeline` (+`/stream`) | `/api/v1/agents/pipeline` (+`/stream`) | 동작 일치, 문서 경로 오기(G9) |
| `POST /api/document-extractor/extract` | `/api/v1/document-extractor/extract` | 무변경, 호출자 추가만 |

### 2.2 Data Model

DB 변경 없음(설계대로). DTO·상태 4필드·카드 상태 머신 전부 구현(`events.py:77,83`, `agentPipeline.ts:121-140`, `index.tsx:71-75`).

### 2.3 Component Structure

| Design §11.1 | 상태 |
|---|---|
| 백엔드 5파일 | 일치 |
| 백엔드 테스트 3파일 | 존재. 파일명 2개가 Design과 다름(`test_use_case_template.py`, `test_agent_pipeline_router_template.py`) |
| 프론트 신규 3 + 수정 6 | 일치. `confirmDraft` → `confirmTemplateDraft` 개명 |
| `LeftConfigPanel.tsx` 수정 | 미수정 — 패널 prop 기본값으로 대체(의도된 편차, 결과 동일) |

**Structural Match: 97%**

### 2.4 Functional Depth Analysis

플레이스홀더·스텁 없음. FR 15개 중 13 완전, 2 부분(FR-10 G1, FR-13 G3). **Functional Depth: 91%**

### 2.5 Page UI Checklist Verification

| 항목 | 결과 |
|---|---|
| 파일 입력(label·accept·즉시 호출) | ✅ |
| 진행 표시 | ⚠️ `aria-live` 영역이 busy일 때만 마운트(G7) |
| 슬롯 목록(role=list, 20개 접기) | ✅ |
| 확인 버튼(review에서만) | ✅ |
| 에러(role=alert, 코드 문구) | ⚠️ 원문 detail 보조 표시 없음(G5) |
| 잠금 이력 | ✅ |
| 버튼 가드 | ✅ |
| [계속] 조건 | ✅ |
| 모바일 | 코드상 ✅(육안 미확인) |

7 완전 + 2 부분 / 9 = 89%

### 2.6 API Contract Verification

요청 `document_template`, 응답 `document_requests`·`document_template_attached`, kind wire 값, 도구 id 표기, 422 매핑, SSE 실패 합성, 동기=SSE 동일성, 추출 에러 코드 5종 ↔ 문구 전부 3-way PASS. 경로 표기 오류 1건(G9). **API Contract: 95%**

### 2.7 Runtime Verification Results

| 레벨 | 실행 | 결과 |
|---|---|---|
| L1 (pytest TestClient 실요청) | 2026-11-06, 파이프라인 관련 6파일 | **205 passed** — L1-01~10 전부 + AST 우회 금지 + need_input 빈 배열 + 본문 422 |
| L1 전체 회귀 | 2026-11-05 전체 스위트 | 53 failed = master 상시 실패 53건과 동일, 회귀 0건 |
| L2 (vitest) | 2026-11-06, 기능 관련 7파일 | **108 passed** — L2-01~11 전부 |
| L2 전체 회귀 | 미완료 | 시스템 메모리 부족으로 중단됨. 재실행 필요 |
| L3 (수동) | 미실행 | L3-01~03 + G3 확인 + 모바일·스크린리더. MCP 변환 도구가 등록된 로컬 필요 |
| `tsc -b` / eslint | 수정 파일 | 신규 오류 0 (`wizardResultToForm.test.ts:28` tsc 오류는 master 기존) |

Runtime: 자동 24 시나리오 통과 / 수동 3 미실행 → **89%**

### 2.8 Match Rate Summary

| 축 | 점수 | 가중치 |
|---|:-:|:-:|
| Structural | 97% | 0.15 |
| Functional | 91% | 0.25 |
| Contract | 95% | 0.25 |
| Runtime | 89% | 0.35 |
| **Overall** | **92%** | |

---

## 3. Gap List

| # | 심각도 | 확신 | 내용 | 조치 후보 |
|---|---|:-:|---|---|
| G1 | **Important (전제)** | 90% | 위저드는 저장하지 않는다. SC-1 "스튜디오 진입 0회"와 FR-10·Design §2.2/§5.2의 "[에이전트 만들기]"는 기존 무저장 계약과 충돌. 코드는 올바르며 템플릿은 스튜디오 [저장]으로 저장된다 | (a) Plan/Design 문구를 "패널 탐색 0회, 스튜디오 저장 1회"로 정정 (b) 위저드에 직접 생성 버튼 추가(스코프 변경) |
| G2 | **Important** | 85% | G1 결과 위저드 템플릿은 전부 `/api/v1/agents`로 저장되는데, 그 경로의 `InvalidSlotError`/`TemplateTokenMismatchError`는 500(기존 결함). D4의 파이프라인 전용 422는 위저드 사용자를 보호하지 못한다 | `agent_builder_router` 생성·수정 핸들러에 `DocumentExtractorError` → 422 매핑(소규모, 기존 결함 수정) |
| G3 | **Important** | 90% (세션 확인) | 에이전트 상세 `document_template`을 `documentExtractorDraft`로 되돌리는 매핑이 없다. 템플릿이 저장된 에이전트를 `?edit`로 열면 드래프트가 null이라 새 안내 "양식 미등록"이 거짓으로 뜬다. 기존 배지 "⚠ 양식 미등록"도 같은 오탐이었으나 안내가 이를 더 두드러지게 한다 | 상세 응답의 템플릿 존재 여부를 패널에 전달해(`hasSavedTemplate`) 안내·배지를 "등록됨(수정하려면 업로드)"으로 바꾼다 |
| G4 | Minor | 95% | 스튜디오 패널이 `extractErrorMessage`를 쓰지 않고 `error.message` 원문 표시 | 공유 유틸로 교체 |
| G5 | Minor | 90% | 카드 에러에 원문 detail 보조 표시 없음 | 선택 |
| G6 | Minor | 85% | 에러 상태에 명시적 [다시 올리기] 없음(파일 재선택으로 재시도 가능) | 선택 |
| G7 | Minor | 70% | `aria-live` 조건부 마운트 | 상시 마운트 |
| G8 | Minor | 90% | `document_template_attached` 프론트 미사용 | 후속 |
| G9 | Minor(문서) | 95% | Design §4.1 경로 오기, §11.1 테스트 파일명 불일치 | 문서 정정 |
| G10 | Minor(기존) | 60% | 건너뛰기 후 스튜디오가 sessionStorage의 옛 드래프트를 복원할 수 있음 | 관찰 |

---

## 4. Code Quality / Security

- 신규 백엔드 함수 40줄 이하, if 중첩 2단계 이하. 컴포넌트 파일 런타임 상수 export 없음.
- 보안: 템플릿 검증 우회 경로 없음(AST 계약 테스트). `source_file_id` 소유자 미검증은 **기존 결함**(스튜디오 경로 동일) — 보고 항목.

## 5. Test Coverage

백엔드 신규 29건(도메인 12·유스케이스 8·라우터 9), 프론트 신규·보강 약 80건. 미커버: L3 수동 3종, 프론트 전체 회귀 diff.

## 6. Clean Architecture Compliance

domain은 bool만 받고 application 스키마를 import하지 않는다(`validate_template_tools(tool_ids, has_template)`). interfaces가 `DocumentTemplateRequest`를 재사용하는 것은 `CreateAgentRequest`와 같은 위치의 모델이라 기존 선례와 동일. 위반 0건.

## 7. Convention Compliance

문구 상수 서버 단일 출처, wire 값 StrEnum, 프론트 상수는 `types/`. LoadingButton 사용. 위반 0건.

## 8. Overall Score

**92%** (≥ 90). 단, G1은 문서 전제의 오류이고 G3는 사용자가 보는 오표시이므로 Report 전 처리 방침을 정한다.

---

## 9. Act-1 결과 (Important 3건 수정)

| # | 조치 | 근거 |
|---|---|---|
| G1 | Plan SC-1·FR-10, Design §2.2·§5.2를 "패널 탐색 0회, 스튜디오 저장 1회"로 정정. 코드 무변경 | 위저드 무저장 계약 유지(스코프 변경 없음) |
| G2 | `agent_builder_router` 생성·수정 핸들러에 `DocumentExtractorError` → 422 매핑 | `test_agent_builder_router.py::TestTemplateValidationErrorMapping` 2건, 파일 37건 통과 |
| G3 | `mapDetailToForm`이 추출기 워커 `tool_config.template_id`를 `savedTemplateId`로 프라임(드래프트로 되돌리지 않음 — 원본 파일 만료). 배지 "✓ 양식 등록됨", 패널 안내 `FORM_TEMPLATE_REPLACE_NOTICE`("등록되어 있습니다. 새 파일을 올리면 교체") | `agentDetailMapping.test.ts` 2건, `LeftConfigPanel.test.tsx` 2건, 관련 4파일 115건 통과 |
| G9 | Design §4.1 경로·§11.1 파일명 정정 | 문서 |

SC 재평가: SC-1 ✅(정정된 기준), SC-4 ✅(저장된 템플릿 오표시 해소). Overall **95%** (Structural 98 · Functional 95 · Contract 97 · Runtime 92 — L3 수동 3종은 그대로 미실행).
이월(Minor): G4 스튜디오 패널 공유 에러 유틸, G5 detail 보조 표시, G6 에러 상태 [다시 올리기], G7 aria-live 상시 마운트, G8 `document_template_attached` 프론트 소비, G10 sessionStorage 옛 드래프트 복원 관찰.

## Version History

| Version | Date | Changes |
|---|---|---|
| 0.1 | 2026-11-06 | gap-detector 정적 분석 + 런타임 결과 통합, G3 세션 확인 |
| 0.2 | 2026-11-06 | Act-1: G1 문서 정정, G2 422 매핑, G3 저장된 양식 표시 — 95% |
