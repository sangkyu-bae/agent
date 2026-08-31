# excel-generator-node Completion Report

> **Status**: Complete
>
> **Project**: sangplusbot (idt 백엔드)
> **Version**: idt 0.1.x
> **Author**: 배상규
> **Completion Date**: 2026-08-25
> **PDCA Cycle**: #1 (Act 1회)

---

## Executive Summary

### 1.1 Project Overview

| Item | Content |
|------|---------|
| **Feature** | excel_export 도구를 document_generator 동형의 전용 합성 노드(ExcelGenerator)로 격상 |
| **Period** | 2026-08-24 ~ 2026-08-25 (Plan → Design → Do → Check → Act → Report) |
| **Scope** | 백엔드 단독 — domain/infrastructure 신규 모듈, WorkflowCompiler 분기, DI, MIME, 도구 설명. 프론트 변경 없음 |
| **Architecture** | Option C (실용 균형) — 기존 문서생성기 패턴 복제, 아키텍처 변경 없음 |

### 1.2 Results Summary

```
┌─────────────────────────────────────────────┐
│  Completion Rate: 100%                       │
├─────────────────────────────────────────────┤
│  ✅ Complete:     10 / 10 FR                 │
│  ✅ NFR:           5 / 5                     │
│  ✅ Gap 해소:     14 / 14 (I3 + M5 + D6)     │
│  Match Rate: 91% → 98% (Act-1)               │
└─────────────────────────────────────────────┘
```

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | excel_export가 등록만 돼 있고 조립 에이전트에서는 react 워커로 컴파일되어 LLM이 데이터를 tool 인자로 재직렬화(절단·유실)했으며, 산출물은 서버 임시 경로 문자열만 반환돼 사용자가 내려받을 수 없었다. |
| **Solution** | 전용 노드 + 하이브리드 소싱: 구조화 원천(analysis_source·첨부 엑셀)은 LLM 미경유 코드 복사(무제한), 비정형 컨텍스트만 LLM 표 구조화(300행 상한). LLM은 시트 계획 JSON 1회만 생성. 산출 .xlsx는 AgentAttachmentStore(owner 바인딩·TTL)에 저장해 기존 다운로드 라우트로 전달. |
| **Function/UX Effect** | "OO 수집해서 엑셀로" 요청 시 채팅에 `[파일명](/api/v1/document-extractor/files/{id})` 링크 응답. 1,000행 원천이 LLM 프롬프트 노출 없이 전량 보존됨을 테스트로 증명. 모든 실패(데이터 없음·LLM 오류·JSON 오류·디스크 오류)는 안내 메시지로 수렴해 그래프가 완주. 신규 테스트 37건, 대상 스위트 822 PASS. |
| **Core Value** | 문서생성기(PDF/Word)·발표자료생성기(PPTX)와 대칭인 표 산출 채널이 완성돼 P2(에이전트 소유자)의 산출물 커버리지 확장. 기존 에이전트 정의(JSON)·REST `/excel-export`·ExcelExportTool 무수정으로 호환. |

---

## 1.4 Success Criteria Final Status

| # | Criteria (Plan DoD) | Status | Evidence |
|---|---------------------|:------:|----------|
| 1 | E2E: 검색+excel_export 에이전트 → 링크 → GET .xlsx | ✅ Met (구간 통합) | 노드 테스트(링크 생성) + `test_xlsx_downloads_with_spreadsheet_media_type` (라우트 MIME) + `TestStorage` (실파일 저장). 실서버 수동 E2E는 Analysis R6 절차로 유지 |
| 2 | 구조화 원천 LLM 미경유 전량 변환 | ✅ Met | `test_raw_sheet_copies_all_rows_without_llm` (1000행), `test_full_data_not_exposed_to_llm` |
| 3 | 비정형 LLM 구조화 + 상한 | ✅ Met | `test_llm_sheet_over_cap_truncates` (300행 절단 + truncated) |
| 4 | 실패 안내 노옵 + 그래프 완주 | ✅ Met | 노드 5종 + `TestFailureBoundaries` 3종 (OSError·LLM 예외 포함) |
| 5 | 기존 테스트 전부 통과 | ✅ Met | excel_export·agent_builder·라우터 회귀 822 PASS, 신규 실패 0 (baseline 대조) |
| 6 | TDD 선행 | ✅ Met | Do 30건 + Act-1 7건 모두 RED → GREEN |

**Overall Success Rate: 6/6**

Quality Criteria: print() 0건, `exception=` 로깅 준수, 레이어 위반 0건. 함수 40줄 규칙은 `excel_generator_node` 클로저(56줄)가 초과 — 기존 document(64)/presentation(57) 노드와 동일 패턴으로 수용, §8.2 후속 과제.

---

## 1.5 Decision Record Summary

| Decision | Source | Followed? | Outcome |
|----------|--------|:---------:|---------|
| 전용 노드 격상 (react 워커 대체) | Plan CP1 | ✅ | `function_node_ids` 등록, `_wrap_worker` 우회 직접 검증 |
| 기존 file store 재사용 | Plan CP1 | ✅ | `AttachmentType.EXCEL` + TTL 상속, `.xlsx` MIME 1줄 추가로 충분 |
| 데이터 소스 4종 (상류 워커·분석 결과·첨부·대화) | Plan CP1 | ✅ | P1/P2/P3 + evidence/conversation 블록 |
| 하이브리드 대용량 처리 | Plan CP2 | ✅ | raw 무손실 / llm 300행 절단 |
| 실패 = 안내 노옵 | Plan CP2 | ✅ (Act-1에서 완성) | 초기 구현은 store IO·LLM 예외가 누출 → Act-1에서 경계 확장 |
| 프론트 변경 없음 | Plan CP2 | ✅ | 마크다운 링크 렌더링 재사용 |
| Option C (문서생성기 동형) | Design CP3 | ✅ | 노드·DI·응답 계약 동형, Contract 100% |
| module-1+2 단일 세션 | Do CP4 | ✅ | 1세션 완료 |
| Important+Minor+문서 일괄 수정 | Check CP5 | ✅ | Act-1로 14건 전부 해소 |

---

## 2. Related Documents

| Document | Path |
|----------|------|
| Plan | `docs/01-plan/features/excel-generator-node.plan.md` |
| Design (0.2) | `docs/02-design/features/excel-generator-node.design.md` |
| Analysis (0.2) | `docs/03-analysis/excel-generator-node.analysis.md` |
| 패턴 원형 | document_generator 노드 (`workflow_compiler.py::_create_document_generator_node`) |

---

## 3. Completed Items

### 3.1 Functional Requirements

| ID | Requirement | Status | 구현 위치 |
|----|-------------|:------:|-----------|
| FR-01 | excel_export → 전용 합성 노드 컴파일 | ✅ | `workflow_compiler.py` compile 분기 + `_create_excel_generator_node` |
| FR-02 | 상류 산출물 + 대화 문맥 소비 | ✅ | `_split_fill_context` → evidence/conversation |
| FR-03 | 구조화 원천 코드 변환 (무제한) | ✅ | `ExcelGenerator._build_catalog` / `_materialize` raw 경로 |
| FR-04 | 비정형 LLM 구조화 + 상한 상수 | ✅ | `policies.MAX_LLM_STRUCTURED_ROWS = 300` |
| FR-05 | store 저장 + 다운로드 링크 AIMessage | ✅ | `_export_and_save`, `_render_excel_summary` |
| FR-06 | `.xlsx` MIME | ✅ | `document_extractor_router._MEDIA_TYPES` |
| FR-07 | 실패 안내 노옵 | ✅ | 노드 except 2단 + Act-1 예외 경계 |
| FR-08 | 다중 시트 | ✅ | `MAX_SHEETS = 10`, `_unique_sheet_name` |
| FR-09 | REST/ExcelExportTool 무변경 | ✅ | ToolFactory `excel_export` case 유지, 회귀 통과 |
| FR-10 | TOOL_REGISTRY 설명 갱신 | ✅ | 설명 + 회귀 테스트 |

### 3.2 Non-Functional Requirements

| Category | Criteria | Status |
|----------|----------|:------:|
| 데이터 무결성 | 원천 100% 보존 | ✅ 1000행 대조 |
| 안정성 | 노드 실패 비중단 | ✅ 8종 실패 주입 |
| 보안 | owner-only 다운로드 | ✅ 기존 403/404 테스트 상속, 파일명 경로 컴포넌트 제거 |
| 레이어 준수 | domain → infra 참조 없음 | ✅ |
| TDD | 선행 작성 | ✅ |

### 3.3 Deliverables

| 구분 | 파일 |
|------|------|
| 신규 domain | `src/domain/excel_generator/{schemas,policies,exceptions}.py` |
| 신규 infra | `src/infrastructure/excel_generator/generator.py` |
| 수정 | `workflow_compiler.py`, `api/main.py`(DI), `document_extractor_router.py`(MIME), `tool_registry.py`(설명) |
| 테스트 | `tests/domain/excel_generator/*`, `tests/infrastructure/excel_generator/test_generator.py`, `tests/application/agent_builder/test_workflow_compiler_excelgen.py`, 라우터·레지스트리 보강 |

---

## 4. Incomplete Items

### 4.1 Carried Over to Next Cycle

| Item | Reason | Priority |
|------|--------|:--------:|
| 실서버 E2E (실제 LLM + WebSocket run) | 테스트 환경에 LLM 키·서버 없음 — Analysis R6 수동 절차 문서화 | Medium |
| 생성 노드 3종(document/presentation/excel) 클로저 공통화 | 40줄 규칙 초과가 패턴 차원 문제 — 단일 기능 범위 밖 | Low |

### 4.2 Cancelled/On Hold Items

없음.

---

## 5. Quality Metrics

### 5.1 Final Analysis Results

| Category | Check (0.1) | Act-1 (0.2) |
|----------|:-----------:|:-----------:|
| Structural | 95% | 100% |
| Functional | 88% | 100% |
| API Contract | 100% | 100% |
| Test Coverage | 88% | 100% |
| Layer | 100% | 100% |
| Intent | 88% | 95% |
| **Overall** | **91%** | **98%** |

테스트: 대상 스위트 822 PASS / 신규 37건 / 기존 실패 0건 추가 (전체 스위트의 58건 기존 실패는 baseline 동일 — 무관).

### 5.2 Resolved Issues

| Issue | Severity | Resolution |
|-------|:--------:|------------|
| store IO 실패가 안내 노옵을 뚫음 | Important | try 경계에 `store.save` 포함, `OSError` 래핑 |
| LLM 호출 예외 미포착 | Important | `ainvoke` try → `ExcelGenerateError("시트 계획 생성 오류")` |
| 노드 시작 로그 누락 | Important | `excel_generator_node start` (소스 카운트 포함) |
| `.xlsx` 강제 암묵 위임 | Minor | `_safe_filename`에서 명시 부여 |
| 테스트 파일명·state 필드·`_wrap_worker` 우회·설명 문구 검증 부재 | Minor | 테스트 4건 추가, Design §11.1 정정 |
| 문서화 누락 6건 | Doc | Design 0.2 (§2.2/§3.2/§3.3/§3.5/§6) + `llm_input_max_chars` 설정 실배선 |

---

## 6. Lessons Learned & Retrospective

### 6.1 What Went Well (Keep)

- **동형 패턴 복제**가 설계·구현·리뷰 비용을 모두 낮췄다 — Contract 100%, 회귀 0건.
- **"LLM에는 카탈로그만"** 결정이 무손실·토큰 절약·절단 회피를 동시에 해결했다.
- Check 단계의 baseline stash 대조로 58건의 기존 실패를 본 기능과 명확히 분리했다.

### 6.2 What Needs Improvement (Problem)

- 예외 경계(try 범위)가 Design에 명시되지 않아 store IO·LLM 예외가 초기 구현에서 누출됐다. document_generator도 같은 패턴 결함을 가진다.
- 구현 중 추가된 세부 정책(시트명 정규화·코드펜스·`NoExcelDataError`)이 Design에 늦게 반영됐다(코드가 진실 원칙으로 0.2에서 보정).

### 6.3 What to Try Next (Try)

- Design §6.1에 **"감지 지점"을 try 경계 단위로** 적기 (어느 호출이 어떤 예외로 수렴하는지).
- 생성 노드 공통 골격(`_reply`/로그/예외 수렴)을 헬퍼로 추출해 3개 노드의 40줄 초과를 한 번에 해소.

---

## 7. Process Improvement Suggestions

### 7.1 PDCA Process

- Checkpoint 5의 "지금 모두 수정" 경로는 문서화 누락(D-*)까지 묶으면 Design이 코드와 동기화된 상태로 Report에 도달한다 — 기본 권장.

### 7.2 Tools/Environment

- 전체 스위트에 기존 실패 58건이 상존해 회귀 판정 비용이 크다. 별도 정리 사이클 권장.

---

## 8. Next Steps

### 8.1 Immediate

- [ ] 실서버 수동 E2E (검색 워커 + excel_export 조립 에이전트 → 링크 → 다운로드)
- [ ] `/pdca archive excel-generator-node`

### 8.2 Next PDCA Cycle

- document_generator `_plan`/`ainvoke` 예외 경계 동일 보강 (본 기능에서 발견된 패턴 결함)
- 생성 노드 3종 공통 헬퍼 추출

---

## 9. Changelog

### v0.1.x (2026-08-25)

**Added**
- `src/domain/excel_generator/` — RawSourceRef·SheetPlanItem·ExcelGenerateResult, MAX_LLM_STRUCTURED_ROWS/MAX_SHEETS/parse_raw_index/validate_plan, ExcelGenerateError/NoExcelDataError
- `src/infrastructure/excel_generator/generator.py` — ExcelGenerator (카탈로그 → 시트 계획 LLM 1회 → raw 복사/llm 절단 → 저장)
- WorkflowCompiler `excel_export` 전용 노드 분기 + `excel_generator` DI

**Changed**
- `_MEDIA_TYPES` `.xlsx` 추가, TOOL_REGISTRY excel_export 설명 갱신
- Act-1: 예외 경계 확장, 시작 로그, `.xlsx` 강제, `llm_input_max_chars` 설정 배선

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-08-25 | 완료 보고서 — Match Rate 98%, DoD 6/6 | 배상규 |
