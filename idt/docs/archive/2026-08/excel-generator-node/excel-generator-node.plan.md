# excel-generator-node Planning Document

> **Summary**: 조립 에이전트의 excel_export를 document_generator 동형 전용 노드로 격상해 "데이터 수집 → 엑셀 생성 → 다운로드" 경로를 끝까지 잇는다.
>
> **Project**: sangplusbot (idt 백엔드)
> **Version**: idt 0.1.x
> **Author**: 배상규
> **Date**: 2026-08-24
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | excel_export 도구는 TOOL_REGISTRY·ToolFactory·프론트 카탈로그까지 등록돼 있으나, 조립 에이전트에서 일반 react 워커로 컴파일되어 LLM이 수집 데이터를 tool 인자로 재직렬화해야 하고(대용량 절단·유실), 생성 파일은 서버 임시 디렉토리 경로 문자열만 반환되어 사용자가 다운로드할 방법이 없다. |
| **Solution** | document_generator와 동형인 전용 합성 노드(excel generator node)로 격상한다. 구조화된 원천(analysis_source·첨부 엑셀 dict)은 LLM을 거치지 않고 코드로 직접 변환하고, 비정형 컨텍스트만 LLM이 표로 구조화하는 하이브리드 방식. 산출 파일은 DocumentAttachmentStore에 저장해 기존 `/api/v1/document-extractor/files/{file_id}` 다운로드 링크로 전달한다. |
| **Function/UX Effect** | "OO 데이터 수집하고 엑셀로 만들어줘" 요청 시 채팅에 다운로드 링크가 포함된 응답이 도착하고, 클릭하면 .xlsx가 내려받아진다. 프론트엔드 변경 없음(기존 마크다운 링크 렌더링 재사용). |
| **Core Value** | 문서생성기(PDF/Word)·발표자료생성기(PPTX)와 대칭을 이루는 표 산출물 채널이 완성되어, P2(에이전트 소유자)가 조립하는 에이전트의 산출물 커버리지가 넓어진다. 검증된 노드 패턴 재사용으로 아키텍처 변경 없음. |

---

## Context Anchor

> Design/Do 문서로 전파되는 컨텍스트 앵커.

| Key | Value |
|-----|-------|
| **WHY** | 도구는 있으나 "수집 데이터 → 엑셀 → 사용자 전달" 경로가 끊겨 있어 엑셀 산출 시나리오가 실사용 불가 |
| **WHO** | P2 (KB 운영자 / 에이전트 소유자) — 조립 에이전트로 데이터 수집·정리 업무를 자동화하려는 사용자 |
| **RISK** | LLM 표 구조화의 행 수 상한(비정형 경로), DocumentAttachmentStore의 pdf/docx 전제(만료 정책·미디어타입) 확인 필요 |
| **SUCCESS** | E2E: 수집→엑셀 요청 시 다운로드 링크 반환 + 파일 정상 오픈. 구조화 원천은 LLM 미경유 전량 보존. 실패 시 그래프 비중단(안내 노옵). |
| **SCOPE** | 백엔드 단독: WorkflowCompiler 분기 + 전용 노드 + store 저장/다운로드 배선. 프론트·위저드 UI·서식 커스터마이징은 스코프 밖 |

---

## 1. Overview

### 1.1 Purpose

조립 에이전트(Custom Supervisor)에서 엑셀 산출 요청이 end-to-end로 동작하게 한다:
상류 워커(검색·분석)가 수집한 데이터를 신뢰성 있게 표로 변환하고, 생성된 .xlsx 파일을
사용자가 채팅에서 바로 다운로드할 수 있게 한다.

### 1.2 Background

- `excel_export`는 초기 task(task-excel-export.md)에서 LangChain Tool + REST 라우트로 구현 완료.
- 이후 supervisor 아키텍처가 발전하면서 파일 산출 도구들(document_extractor, document_generator,
  presentation_generator)은 **전용 합성 노드** + **DocumentAttachmentStore 저장** + **다운로드 링크**
  패턴으로 정착했으나, excel_export만 일반 react 워커 경로에 남았다.
- 현재 증상: 사용자 요청("상위 데이터 수집하고 엑셀로 만들어줘") 시 엑셀 산출이 실질적으로 불가.
  - 데이터 흐름: LLM이 검색 결과를 `columns`/`rows` JSON 인자로 통째 재직렬화 → 대용량 절단·유실.
  - 전달: `ExcelExportTool._run()`이 `tempfile.gettempdir()`에 저장하고 서버 로컬 경로만 반환 → 사용자 접근 불가.

### 1.3 Related Documents

- 도구 원형: `src/claude/task/task-excel-export.md`
- 동형 패턴: `workflow_compiler.py` `_create_document_generator_node` (doc-generator Design §4-4)
- 원천 데이터 채널: `supervisor_state.py` `analysis_source` (analysis-source-preservation)
- 입력 첨부(참고): ws-agent-excel-attachment Design §4.3
- 파일 다운로드: `src/api/routes/document_extractor_router.py` GET `/files/{file_id}`

---

## 2. Scope

### 2.1 In Scope

- [ ] WorkflowCompiler에 `excel_export` 전용 분기 추가 — document_generator 동형 합성 노드 (function node, ToolFactory 미경유)
- [ ] 하이브리드 데이터 소싱:
  - 구조화 원천(`analysis_source`의 엑셀 dict, 첨부 엑셀 파싱 결과)이 있으면 **코드 직접 변환** (LLM 미경유, 행 수 무제한)
  - 비정형 컨텍스트(상류 워커 산출물·대화 문맥)만 **LLM 표 구조화** (행 수 상한 명시)
- [ ] 산출 파일을 DocumentAttachmentStore에 owner_user_id로 저장하고 `/api/v1/document-extractor/files/{file_id}` 다운로드 링크를 AIMessage로 반환
- [ ] `document_extractor_router._MEDIA_TYPES`에 `.xlsx` 미디어타입 추가
- [ ] 실패 시 안내 노옵 (document_generator D9 동형 — 사유를 AIMessage로 반환, 그래프 계속 진행)
- [ ] TOOL_REGISTRY의 excel_export 설명을 노드 동작(수집 데이터 소비·다운로드 제공)에 맞게 갱신
- [ ] 기존 소비자(REST `/api/v1/excel-export`, ToolFactory 단독 생성 경로) 무회귀 확인

### 2.2 Out of Scope

- 프론트엔드 변경 (다운로드는 기존 마크다운 링크 렌더링 재사용 — 전용 다운로드 카드 UI 없음)
- 에이전트 빌더 위저드의 엑셀 도구 설정 UI (기본 파일명·시트 힌트 등)
- 셀 서식·차트·조건부 서식 등 스타일링 (헤더+데이터 평면 표만)
- 엑셀 템플릿(양식) 기반 채우기 (document_extractor의 영역)
- WebSocket으로 파일 바이트 직접 push
- 대화 기록의 vector DB 저장 등 메모리 정책 변경 (금지 사항)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | WorkflowCompiler가 `tool_id == "excel_export"` 워커를 전용 합성 노드로 컴파일한다 (document_generator 동형, function_node_ids 등록) | High | Pending |
| FR-02 | 노드는 상류 워커 산출물 + 대화 문맥을 누적 컨텍스트로 소비한다 (D1 동형 — 조사·수집은 상류 워커 담당) | High | Pending |
| FR-03 | 구조화 원천(state의 `analysis_source` 엑셀 dict, 첨부 엑셀 파싱 결과)이 존재하면 LLM 재직렬화 없이 코드로 시트 데이터를 변환한다 (행 수 무제한) | High | Pending |
| FR-04 | 구조화 원천이 없으면 LLM이 비정형 컨텍스트를 표(columns/rows)로 구조화한다. 행 수 상한을 정책 상수로 명시한다 | High | Pending |
| FR-05 | 생성된 .xlsx를 DocumentAttachmentStore에 owner_user_id로 저장하고, 다운로드 링크(`/api/v1/document-extractor/files/{file_id}`)를 포함한 AIMessage를 반환한다 | High | Pending |
| FR-06 | `_MEDIA_TYPES`에 `.xlsx` → `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` 추가 | Medium | Pending |
| FR-07 | 데이터 없음·변환 오류 등 실패 시 안내 노옵으로 처리한다 (그래프 비중단, 사유 AIMessage) | High | Pending |
| FR-08 | 다중 시트 지원: 원천이 복수 시트/복수 소스면 시트를 나눠 담는다 (ExcelSheetData 재사용) | Medium | Pending |
| FR-09 | 기존 REST `/api/v1/excel-export` 라우트와 ExcelExportTool 단독 사용 경로는 동작 변경 없이 유지된다 | High | Pending |
| FR-10 | TOOL_REGISTRY excel_export 설명 갱신 (supervisor 라우팅 힌트: 수집 데이터를 엑셀 파일로 정리·다운로드 제공) | Medium | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 데이터 무결성 | 구조화 원천 경로에서 행/열 데이터 100% 보존 (LLM 미경유) | 단위 테스트 — 입력 dict ↔ 산출 xlsx 대조 |
| 안정성 | 노드 실패가 run 전체를 중단시키지 않음 | 실패 주입 테스트 — 그래프 완주 확인 |
| 보안 | 다운로드는 owner-only (기존 GB3 정책 상속) | 기존 라우트 테스트 재사용 |
| 레이어 준수 | domain → infrastructure 참조 금지, 노드는 application 레이어 | verify-architecture 스킬 |
| TDD | 테스트 먼저 작성 (Red → Green → Refactor) | verify-tdd 스킬 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] E2E 시나리오: 검색 워커 + excel_export 워커로 조립된 에이전트에 "OO 데이터 수집하고 엑셀로 만들어줘" 요청 → 응답에 다운로드 링크 포함 → GET 다운로드 시 유효한 .xlsx 반환
- [ ] 구조화 원천(분석 노드 엑셀 dict) 존재 시: LLM 미경유 경로로 전량 변환됨을 테스트로 증명
- [ ] 비정형 경로: 검색 결과만 있는 상태에서 LLM 구조화로 표 생성 (상한 이내)
- [ ] 실패 시나리오(빈 컨텍스트·store 미배선): 안내 노옵 반환, 그래프 완주
- [ ] 기존 테스트 전부 통과: `tests/infrastructure/excel_export/*`, `tests/api/test_excel_export_router.py`, workflow_compiler 관련 테스트
- [ ] 신규 코드에 대한 단위 테스트 선행 작성

### 4.2 Quality Criteria

- [ ] 함수 40줄 이하, if 중첩 2단계 이하 (CLAUDE.md 규칙)
- [ ] print() 미사용 — StructuredLogger, 스택 트레이스 포함 에러 로깅
- [ ] Repository 내 commit/rollback 없음 (해당 시)

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| LLM 표 구조화의 행 수 상한으로 비정형 대용량 데이터 절단 | Medium | High | 상한을 정책 상수로 명시하고, 상한 초과 시 안내 문구(요약/원천 경로 유도)를 AIMessage에 포함. 구조화 원천 우선 사용으로 대부분 회피 |
| DocumentAttachmentStore가 pdf/docx 전제(만료·정리 정책)일 가능성 | Medium | Medium | Design 단계에서 store 저장·만료 정책 검증. xlsx도 동일 수명주기를 따르는지 확인 후 필요 시 미디어타입만 확장 |
| TOOL_REGISTRY 설명 변경이 supervisor 라우팅·auto_agent_builder 추천에 영향 | Medium | Medium | 설명 변경분을 라우팅 회귀 테스트(tool_registry 테스트)와 함께 커밋. 추천 프롬프트(agent_spec_inference_service) 문구 동기화 |
| 전용 노드 격상으로 기존 react 워커 경로를 쓰던 에이전트의 동작 변화 | High | Low | tool_id는 동일 유지 — 컴파일 분기만 변경되므로 기존 에이전트 정의(JSON) 무수정. Check 단계에서 기존 조립 에이전트 회귀 확인 |
| 임시 파일 잔존(디스크 누수) | Low | Medium | store 저장 후 임시 산출물 정리. run 종료 정리 훅(ws-agent-excel-attachment §4.3)과 정합 확인 |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `src/application/agent_builder/workflow_compiler.py` | Application | excel_export 전용 노드 분기 + `_create_excel_generator_node` 추가 |
| `src/domain/agent_builder/tool_registry.py` | Domain | excel_export 설명 갱신 (라우팅 힌트) |
| `src/api/routes/document_extractor_router.py` | API | `_MEDIA_TYPES`에 `.xlsx` 추가 |
| (신규) excel generator 노드/서비스 모듈 | Application/Domain | 하이브리드 소싱 + 시트 변환 로직 (Design에서 위치 확정) |
| `src/infrastructure/excel_export/*` | Infrastructure | 변경 없음 목표 (PandasExcelExporter 재사용). 필요 시 bytes 반환 경로만 활용 |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| ExcelExportTool | CREATE (도구 생성) | `tool_factory.py:159` `case "excel_export"` | Needs verification — 전용 노드 도입 후에도 팩토리 경로 유지 (react 폴백/타 소비자용) |
| PandasExcelExporter | 변환 | `excel_export_use_case.py`, `excel_export_tool.py` | None — 그대로 재사용 |
| REST `/api/v1/excel-export` | CREATE | `excel_export_router.py` → `main.py:5279` | None — 동작 불변 (FR-09) |
| TOOL_REGISTRY["excel_export"] | READ | supervisor 라우팅 프롬프트, 프론트 도구 카탈로그, `agent_spec_inference_service.py:19` | Needs verification — 설명 문구 변경 시 카탈로그 표시·추천 문구 동기화 |
| `/api/v1/document-extractor/files/{file_id}` | READ | 프론트 다운로드 링크 (document/presentation 산출물) | None — xlsx 미디어타입 추가는 부가적 |
| workflow_compiler 컴파일 경로 | 컴파일 | 기존 조립 에이전트 전체 | Needs verification — excel_export 포함 에이전트만 노드 유형 변경, 정의(JSON) 무수정 |

### 6.3 Verification

- [ ] 위 소비자 전부 기존 테스트 + 신규 회귀 테스트로 검증
- [ ] 다운로드 owner-only 권한 동작 불변 확인
- [ ] 에이전트 정의 스키마(tool_ids) 무변경 확인 — 마이그레이션 불필요

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Selected |
|-------|:--------:|
| Starter | ☐ |
| Dynamic | ☐ |
| **Enterprise** (기존 Thin DDD 유지) | ☑ |

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 노드 통합 방식 | 전용 합성 노드 / react 워커 유지+전달 보강 / 단계적 | **전용 합성 노드** | document_generator·presentation_generator로 검증된 패턴. 상류 산출물 누적 소비(D1)로 LLM 인자 재직렬화 제거. 사용자 확정 |
| 파일 전달 | 기존 DocumentAttachmentStore 재사용 / 엑셀 전용 store 신설 / WS push | **기존 store 재사용** | owner-only 다운로드 라우트·프론트 링크 렌더링 재사용, 중복 코드 없음. 사용자 확정 |
| 데이터 소싱 | 하이브리드 / LLM만 / 코드만 | **하이브리드** | 구조화 원천은 코드 변환(무손실·무제한), 비정형만 LLM 구조화(상한 명시). 사용자 확정 |
| 실패 처리 | 안내 노옵 / 재시도 후 노옵 / 에러 중단 | **안내 노옵** | document_generator D9 동형 — 그래프 비중단. 사용자 확정 |
| 데이터 원천 범위 | — | 상류 워커 수집 + 분석 결과(analysis_source) + 첨부 엑셀 재가공 + 대화 문맥 | 사용자 확정 (4개 전부) |
| 변환 엔진 | PandasExcelExporter 재사용 / 신규 | **재사용** | 다중 시트 지원 완비, 검증된 코드 |
| Testing | pytest (TDD) | pytest | 프로젝트 표준 |

### 7.3 Clean Architecture Approach

```
Enterprise (기존 유지):
  domain/        시트 변환 정책·행 상한 정책 (순수 로직)
  application/   excel generator 노드 (workflow_compiler 내 or 인접 모듈)
  infrastructure/ PandasExcelExporter, DocumentAttachmentStore (기존 재사용)
  api/           document_extractor_router (_MEDIA_TYPES 1줄)
```

레이어 이동·아키텍처 변경 없음 — 기존 패턴에 노드 1종 추가.

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- [x] `idt/CLAUDE.md` 코딩 규칙 (레이어 책임, 함수 40줄, 타입 명시)
- [x] `docs/rules/db-session.md` / `logging.md` / `testing.md` / `tool-and-mcp.md`
- [x] pytest TDD 규칙

### 8.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| 노드 네이밍 | `_create_document_generator_node` 패턴 존재 | `_create_excel_generator_node` 동형 명명 | High |
| 행 상한 상수 | 없음 | LLM 구조화 행 상한 정책 상수 위치(domain policy) | High |
| 다운로드 링크 포맷 | `[{filename}](/api/v1/document-extractor/files/{file_id})` | 동일 포맷 재사용 | Medium |

### 8.3 Environment Variables Needed

없음 (`requires_env=[]` 유지 — 신규 외부 의존 없음).

---

## 9. Next Steps

1. [ ] `/pdca design excel-generator-node` — 설계 문서 작성
   - DocumentAttachmentStore 저장/만료 정책 검증 (Risk #2)
   - 노드 내부 흐름(소싱 판별 → 변환 → 저장 → 링크) 상세화, 3안 비교
   - 첨부 엑셀 재가공 경로(state.attachments → 파싱 dict)와 analysis_source 소비 우선순위 확정
2. [ ] 설계 승인 후 `/pdca do excel-generator-node` — TDD 구현
3. [ ] `/pdca analyze` — Gap 분석

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-08-24 | Initial draft — 아키텍처 조사 + 사용자 확정 사항(전용 노드·store 재사용·하이브리드 소싱·안내 노옵·4개 데이터 소스·프론트 무변경) 반영 | 배상규 |
