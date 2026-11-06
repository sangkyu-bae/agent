# wizard-template-request Completion Report

> **Feature**: wizard-template-request (위저드 양식 요청 카드)
> **Project**: sangplusbot (Agent Builder)
> **Period**: 2026-11-05 ~ 2026-11-06
> **Author**: 배상규
> **Status**: Completed (Match Rate 95%, Act 1회)
> **Worktree**: `wt/wizard-template-request` · 브랜치 `feature/wizard-template-request` · **미커밋**

---

## Executive Summary

### 1.1 Project Overview

채팅 위저드에서 확정 도구에 문서추출기가 있으면 서버가 "양식 파일을 올려주세요" 요청을 계산해 내려주고, 위저드 카드가 첨부 즉시 기존 추출 API로 슬롯을 추천받아 확인 1클릭으로 템플릿을 확정한다. 확정 템플릿은 스튜디오 핸드오프에 실려 [저장] 시 에이전트에 매핑된다. 설계 Option C(실용 균형).

### 1.2 Results Summary

| 항목 | 계획 | 실제 |
|---|---|---|
| 기간 | 3세션 | 3세션(module-1·2·3) + Check·Act-1 |
| Match Rate | ≥ 90% | 92% → Act-1 후 **95%** |
| 백엔드 | 수정 5 + 테스트 3 | 수정 6(+`agent_builder_router` Act-1) + 테스트 3(+보강 1) · 신규 테스트 31건 |
| 프론트 | 신규 3 + 수정 6 | 신규 6(테스트 포함) + 수정 13 · 신규·보강 테스트 약 90건 |
| DB 마이그레이션 | 0 | 0 |
| 회귀 | 0건 | 백엔드 전체 53 failed = master 상시 실패와 동일(0건). 프론트 전체는 미완료(메모리 부족 중단) |

### 1.3 Value Delivered

| Perspective | Planned | Delivered |
|---|---|---|
| **Problem** | 위저드가 추출기를 추천하면서 양식을 받지 않아 양식 없는 에이전트가 생기거나 패널을 못 찾는다 | 추출기 확정 시 서버가 요청 카드를 띄우고, 첨부 즉시 분석해 슬롯 확인까지 위저드 안에서 끝난다 |
| **Solution** | 서버 소유 문구·순수 함수 판단·LLM 0회, 템플릿은 파이프라인 요청에 동봉 | 그대로 구현. 추가로 스튜디오 저장 경로 422 매핑(G2)과 저장된 양식 표시(G3)까지 |
| **Function/UX** | 파일 드롭 + 슬롯 확인 두 동작 | 두 동작 + 건너뛰기 이력·에러 5종 안내·재시도. 스튜디오는 확정 템플릿이 프리필된 상태로 열린다 |
| **Core Value** | S3 "양식 등록"을 P2가 채팅 흐름 안에서 끝낸다 | 추출기 패널 탐색 0회. 저장 1회는 기존 위저드 무저장 계약에 따라 스튜디오에서(Act-1 정정) |

## 1.4 Success Criteria Final Status

| SC | 상태 | 근거 |
|---|---|---|
| SC-1 완주·템플릿 저장(정정 기준: 패널 탐색 0회·스튜디오 저장 1회) | ✅ | 핸드오프 `index.tsx` → `wizardResultToForm.ts` → 스튜디오 저장 `document_template`; `index.test.tsx` ⑥·⑦, `wizardResultToForm.test.ts` |
| SC-2 요청 0건이면 화면 동일 | ✅ | `DocumentsStep.tsx` 조건 렌더, `policies.py`; L2-01 테스트 |
| SC-3 실패 5종 안내·재시도 | ✅ | `documentExtractorErrors.ts`, 카드 L2-05, 유틸 테스트 5건 |
| SC-4 건너뛰기 → `?edit` 안내 | ✅ | 패널 안내 + Act-1 `savedTemplateId`로 저장된 양식은 "등록됨"; 테스트 L2-10 + 배지 2건 |
| SC-5 직접 만들기 → 패널 확정 상태 | ✅ (정적) | `wizardResultToForm` 프리필; 화면 확인은 수동 이월 |
| SC-6 추출기 없는 템플릿 422 | ✅ | `use_case.py` 저장 전 검증, 라우터 422; 테스트 2건 |

**Overall: 6/6 (SC-1은 정정된 기준)**

## 1.5 Decision Record Summary

| 결정 | 출처 | 준수 | 결과 |
|---|---|---|---|
| 판단 트리거 = 확정 도구에 추출기 포함(별도 LLM 없음) | Plan §7.2 | ✅ | LLM 호출 0회 추가, 도구 단계 편집과 항상 일치 |
| 요청 문구 서버 소유 결정적 템플릿 | Plan §7.2 | ✅ | 후속 LLM 문구 교체 시 프론트 무변경 |
| 템플릿은 파이프라인 요청에 동봉 → CREATE 전달 | Plan §7.2 / D3 | ✅ | 단, 위저드는 무저장 계약이라 이 경로는 외부 동기 호출자용. 실사용 경로는 스튜디오 저장(G1) |
| 추출은 프론트가 기존 API 직접 호출 | Plan §7.2 | ✅ | 5단계 계약 불변 |
| 슬롯 확인 1클릭, 편집은 스튜디오 | 사용자 확인 | ✅ | 카드는 미리보기 없음(D6) |
| 건너뛰기 = 도구 유지 + 안내 | 사용자 확인 | ✅ | Act-1에서 "등록됨/교체" 분기 추가 |
| D4 422는 파이프라인 라우터에만 | Design | ⚠️ 확장 | G1 때문에 스튜디오 라우터에도 매핑(G2) |
| D5 스튜디오 안내는 프론트 상수 | Design | ✅ | Act-1에서 상수 2개(미등록/교체) |
| D7 `document_template_attached` 에코백 | Design | ⚠️ | 서버 구현, 프론트 미소비(이월 G8) |

---

## 2. Related Documents

- Plan: `docs/01-plan/features/wizard-template-request.plan.md` (Act-1 정정 포함)
- Design: `docs/02-design/features/wizard-template-request.design.md` (Act-1 정정 포함)
- Analysis: `docs/03-analysis/wizard-template-request.analysis.md` (v0.2, 95%)
- 선행: `docs/archive/2026-11/agent-kb-quick-setup/`, `idt/docs/archive/2026-08/document-template-extractor/`

---

## 3. Completed Items

### 3.1 Functional Requirements

| FR | 내용 | 상태 |
|---|---|---|
| FR-01~03 | `document_requests` 계산(확정 목록 기준·문구·빈 배열) | ✅ |
| FR-04~05 | `document_template` 동봉·전달·정합 검증 422 | ✅ |
| FR-06~09 | 카드 렌더·첨부 즉시 추출·확인 확정·에러 5종 | ✅ |
| FR-10 | 건너뛰기 → 도구 유지·핸드오프(정정) | ✅ |
| FR-11 | 잠긴 이력·뒤로가기 재편집 | ✅ |
| FR-12 | 핸드오프 프리필 | ✅ |
| FR-13 | 스튜디오 "양식 미등록" 안내 (+Act-1 등록됨/교체) | ✅ |
| FR-14~15 | [계속] 조건·busy 가드 | ✅ |

### 3.2 Non-Functional Requirements

| 항목 | 결과 |
|---|---|
| 호환성(additive) | 기존 요청 본문 응답 동일 테스트(L1-05), 백엔드 회귀 0건 |
| 신뢰 경계 | 바인딩 경로 우회 금지 AST 계약 테스트 |
| 실패 경계 | 추출 실패는 카드 노출, 검증 실패는 422 전파 |
| 성능 | LLM 호출 0회 추가 |
| 접근성 | label·list·alert 시맨틱(aria-live 상시 마운트는 이월) |

### 3.3 Deliverables

백엔드: `policies.py`(DocumentRequest·`document_requests_for`·`validate_template_tools`), `events.py`, `use_case.py`, `schemas/agent_pipeline.py`, `agent_pipeline_router.py`, `agent_builder_router.py`(Act-1) + 테스트 4파일.
프론트: `types/agentPipeline.ts`, `utils/wizardTemplate.ts`, `utils/documentExtractorErrors.ts`, `FormTemplateRequestCard.tsx`, `DocumentsStep.tsx`, `AgentCreateEntryPage/index.tsx`, `agentDraftStore.ts`, `wizardResultToForm.ts`, `DocumentExtractorConfigPanel.tsx`, `DocumentExtractorConfigModal.tsx`, `LeftConfigPanel.tsx`, `agentDetailMapping.ts`, `types/agentBuilder.ts` + 테스트 9파일.

---

## 4. Incomplete Items

### 4.1 Carried Over to Next Cycle

| 항목 | 사유 |
|---|---|
| 프론트 전체 vitest 회귀 FAILED diff | 시스템 메모리 부족으로 중단. 커밋 전 재실행 필요 |
| 수동 E2E L3-01~03 | MCP 변환 도구가 등록된 로컬 서버 필요 |
| G4 스튜디오 패널 공유 에러 유틸 | Minor |
| G5·G6 카드 에러 detail 보조 표시·[다시 올리기] | Minor |
| G7 aria-live 상시 마운트 | Minor |
| G8 `document_template_attached` 프론트 소비 | Minor |
| `source_file_id` 소유자 미검증 | 기존 결함, 보고 항목(스튜디오 경로 동일) |

### 4.2 Cancelled/On Hold

- 위저드 직접 생성 버튼(스튜디오 진입 0회 달성) — 무저장 계약 변경이라 별도 사이클 후보.

---

## 5. Quality Metrics

### 5.1 Final Analysis Results

| 축 | 1차 | Act-1 후 |
|---|:-:|:-:|
| Structural | 97 | 98 |
| Functional | 91 | 95 |
| Contract | 95 | 97 |
| Runtime | 89 | 92 |
| **Overall** | 92 | **95** |

테스트: 백엔드 파이프라인 205건·빌더 라우터 37건 통과. 프론트 기능 관련 7파일 108건 + 스튜디오 4파일 115건 통과. ruff·eslint 신규 오류 0. tsc 오류 3건은 master 기존 테스트 헬퍼.

### 5.2 Resolved Issues

| # | 문제 | 해결 |
|---|---|---|
| G1 | Plan이 위저드 생성을 가정 | 문구 정정(코드 무변경) |
| G2 | 스튜디오 저장 경로 템플릿 검증 500 | 생성·수정 핸들러 422 매핑 + 테스트 2건 |
| G3 | 저장된 양식이 있어도 "미등록" 표시 | 워커 `tool_config.template_id` 프라임 → 배지·안내 분기 + 테스트 4건 |
| G9 | Design 경로·파일명 오기 | 문서 정정 |

---

## 6. Lessons Learned & Retrospective

### 6.1 Keep
- 요청 판단을 "확정 도구의 함수"로 둔 덕에 LLM 호출 없이 테스트 가능하고 도구 편집과 어긋나지 않았다.
- 위저드 템플릿을 스튜디오 드래프트와 같은 형태로 보관해 핸드오프·저장 변환이 한 줄로 끝났다.
- 프론트 컴포넌트 전용 카드 1개 + 유틸 2개로 범위를 묶어 세 세션에 끝났다.

### 6.2 Problem
- **Plan이 기존 위저드의 무저장 계약을 놓쳤다.** 코드 확인 단계에서 `index.tsx` 상단 주석을 읽었으면 잡혔을 전제였다. "생성" 단어가 들어가는 SC는 실제 저장 지점을 먼저 확인할 것.
- 상세 응답에 템플릿 본문이 없다는 사실을 Design에서 확인하지 않아 "양식 미등록" 안내가 오탐을 키웠다.
- gap-detector가 30턴 한도에서 보고 없이 멈췄다. 두 번째 호출에서 "탐색 중단, 즉시 보고"로 받아냈다.
- 프론트 전체 vitest가 메모리 부족으로 두 번 중단됐다.

### 6.3 Try
- Plan 작성 시 "저장/생성 지점" 한 줄을 Background 표에 필수로 넣는다.
- 서브에이전트에는 처음부터 "N턴 내 보고, 못 읽은 항목은 not verified"를 지시한다.
- 긴 TSX 테스트 블록은 셸 히어독 대신 파일 Write 후 `cat >>`(이번에 실증).

---

## 7. Process Improvement Suggestions

- gap-detector 브리프에 "읽을 파일 목록 + 턴 예산"을 명시하면 한도 도달이 줄어든다.
- worktree 셋업(uv sync --dev, .env·samples 복사, node_modules symlink)을 스크립트로 묶을 만하다.

---

## 8. Next Steps

### 8.1 Immediate
1. 프론트 전체 `vitest --no-file-parallelism` 회귀 FAILED diff(메모리 여유 확인 후)
2. 커밋(백엔드/프론트 분리 또는 단일) → PR
3. 수동 E2E L3-01~03 (MCP 변환 도구 등록 로컬)
4. `/pdca archive wizard-template-request`

### 8.2 Next PDCA Cycle
- Minor 이월 5건(G4~G8) 소형 사이클
- 스튜디오 생성 경로 `source_file_id` 소유자 검증(기존 결함)
- 문서생성기 예시 문서 → 섹션 추출, 위저드 직접 생성 버튼(스코프 후보)

---

## 9. Changelog

### v1.0.0 (2026-11-06)
- 파이프라인 응답 `document_requests`·`document_template_attached`, 요청 `document_template` (additive)
- 위저드 문서 단계 양식 요청 카드(첨부→추출→슬롯 확인→확정), 건너뛰기 이력
- 스튜디오 핸드오프 프리필, 추출기 패널 "양식 미등록/등록됨·교체" 안내
- 스튜디오 생성·수정 라우터 템플릿 검증 예외 422

## Version History

| Version | Date | Changes |
|---|---|---|
| 1.0 | 2026-11-06 | 완료 보고서 |
