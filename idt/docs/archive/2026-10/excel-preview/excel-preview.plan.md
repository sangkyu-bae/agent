# excel-preview Planning Document

> **Summary**: 에이전트가 생성한 .xlsx 산출물을 다운로드하기 전에 채팅 화면에서 시트별 상위 N행을 모달로 미리 확인할 수 있게 한다. 백엔드가 파싱해 JSON을 주고, 프론트는 시트 탭 + 텍스트 그리드로 렌더한다.
>
> **Project**: sangplusbot (idt 백엔드 + idt_front 프론트)
> **Version**: 0.1
> **Author**: 배상규
> **Date**: 2026-10-12
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 에이전트가 "엑셀로 만들어줘" 요청에 생성한 .xlsx는 채팅에 링크로만 오고, 클릭하면 즉시 blob 저장된다. 사용자는 내용이 맞는지 확인하려면 파일을 받아 엑셀로 열어야 하고, 틀렸으면 다시 요청해 또 받아야 한다. |
| **Solution** | 산출 파일 저장소(`AgentAttachmentStore`)의 .xlsx를 서버가 openpyxl로 읽어 시트별 상위 100행×50열을 문자열 JSON으로 돌려주는 프리뷰 API를 추가하고, 채팅 링크 옆 "미리보기" 버튼으로 시트 탭 모달을 연다. 모달 안에서 바로 다운로드한다. |
| **Function/UX Effect** | 다운로드 없이 시트 구성·헤더·앞부분 데이터를 바로 확인. 잘린 경우 "전체 N행 중 100행" 안내. 만료·손상·타인 파일은 모달 안에서 사유를 보여주되 다운로드 경로는 그대로 유지. |
| **Core Value** | P2(에이전트 소유자)와 그 부서 사용자가 산출물 검증 왕복 비용을 줄인다. 기존 다운로드 계약·에이전트 정의·엑셀 생성 노드는 무수정이며, 진입 방식(버튼→링크)과 그리드 구현(텍스트→전문 그리드)을 설정/컴포넌트 교체만으로 바꿀 수 있게 경계를 잡는다. |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 산출 엑셀의 내용 확인이 "다운로드 → 엑셀 실행"을 강제해 검증 왕복이 느리다 |
| **WHO** | 채팅에서 엑셀 산출물을 받는 모든 사용자 (주인공 P2 에이전트 소유자 및 배포받은 부서 사용자) |
| **RISK** | 대용량 시트 파싱이 요청 스레드를 점유하거나 응답이 비대해져 채팅 UI가 멈추는 것 → 서버 측 행/열 상한 + `asyncio.to_thread` + read_only 모드 |
| **SUCCESS** | .xlsx 링크 옆 버튼 → 모달에서 모든 시트 탭·헤더·상위 100행 확인 → 모달 내 다운로드가 기존과 동일 파일을 저장. 10MB 파일 프리뷰 응답 2초 이내. 신규 테스트 RED→GREEN, 기존 `FAILED` 목록 diff 0 |
| **SCOPE** | Phase 1(이번 사이클): 산출 엑셀 프리뷰 API + 모달. Out: 첨부 엑셀·KB 업로드·분석 스냅샷 프리뷰, 서식 렌더, 페이지네이션 |

---

## 1. Overview

### 1.1 Purpose

에이전트 산출 .xlsx 파일을 다운로드하기 전에 화면에서 내용을 미리 확인하는 기능을 제공한다.

### 1.2 Background — 현재 구조 조사 결과

| 항목 | 현재 상태 | 근거 |
|------|----------|------|
| 산출 링크 형식 | `다운로드: [{filename}](/api/v1/document-extractor/files/{file_id})` — 링크 텍스트가 파일명이라 확장자 판별 가능 | `src/application/agent_builder/workflow_compiler.py:2039,2148,2354,2690` |
| 다운로드 라우트 | `GET /api/v1/document-extractor/files/{file_id}` — owner 검증(403), 만료(404), `.xlsx` MIME 등록 | `src/api/routes/document_extractor_router.py:135-157` |
| 저장소 | `AgentAttachmentStore` — `{upload_dir}/{file_id}{ext}` + 사이드카 meta, TTL 3600s, file_id uuid4 hex 검증 | `src/infrastructure/agent_attachment/store.py`, `config.py:204-208` |
| 프론트 링크 처리 | `MarkdownRenderer`의 `a` 컴포넌트가 `/api/v1/document-extractor/files/` 접두 링크를 가로채 `documentExtractorService.downloadGeneratedFile`로 blob 저장 | `idt_front/src/components/chat/MarkdownRenderer.tsx:68-86` |
| 파싱 라이브러리 | 백엔드 pandas + openpyxl 보유. 프론트에 엑셀 파싱/그리드 라이브러리 없음 | `pyproject.toml:55-56`, `package.json` |
| 유사 상한 config | `kb_excel_max_rows_per_sheet=20000` 등 엑셀 상한은 config로 관리 | `config.py:60-61` |

엑셀이 화면에 닿는 접점은 4곳(산출 다운로드, 채팅 첨부, KB 업로드, 분석 스냅샷)이나, 이번 사이클은 **산출 다운로드 접점만** 대상으로 한다(Checkpoint 1 확정).

### 1.3 Related Documents

- 선행: `docs/archive/2026-08/excel-generator-node/` (산출 저장소·링크 계약)
- 선행: `docs/archive/2026-08/doc-generator/` (다운로드 라우트 GB3, owner-only D3)
- 규칙: `docs/rules/db-session.md`, `docs/rules/logging.md`, `docs/rules/testing.md`
- 위키: `docs/wiki/conventions/additive-contract-extension.md` (additive 확장), `docs/wiki/frontend/patterns/tsx-authoring-pitfalls.md` (런타임 상수 분리), `docs/wiki/conventions/false-green-quality-gates.md` (FAILED diff), `docs/wiki/backend/patterns/degradation-vs-failure-boundary.md`
- 시나리오: `docs/USER-SCENARIOS.md` P2 (산출물 배포·검증)

---

## 2. Scope

### 2.1 In Scope

- [ ] **백엔드** 프리뷰 API: `GET /api/v1/document-extractor/files/{file_id}/preview` — 기존 다운로드와 동일한 owner/만료 검증, `.xlsx`만 허용
- [ ] 시트별 상위 `excel_preview_max_rows`(100) × `excel_preview_max_cols`(50) 추출, 전체 행/열 수·truncated 플래그 동반, 모든 시트 1회 응답
- [ ] 셀 값 문자열 통일(빈 셀 `""`, 날짜 ISO 8601, 숫자 `str()`), 수식은 계산 결과값(`data_only=True`)
- [ ] 파싱은 `asyncio.to_thread` + openpyxl `read_only=True`
- [ ] 오류 계약: 404 `FILE_NOT_FOUND`(만료 포함), 403 `FORBIDDEN`, 415 `PREVIEW_UNSUPPORTED`(.xlsx 외), 422 `PREVIEW_PARSE_FAILED`(손상 파일)
- [ ] **프론트** `.xlsx` 링크 옆 "미리보기" 버튼 (링크 클릭은 기존 다운로드 유지)
- [ ] 진입 방식 스위치 상수 `EXCEL_PREVIEW_TRIGGER: 'button' | 'link'` — `'link'`로 바꾸면 링크 클릭이 프리뷰를 열고 모달에서 다운로드 (코드 변경 1곳)
- [ ] `ExcelPreviewModal`: 시트 탭, 헤더+행 그리드, "전체 N행×M열 중 100×50 표시" 안내, 다운로드 버튼(기존 `downloadGeneratedFile` 재사용), 로딩·오류·빈 시트 상태
- [ ] 그리드는 `ExcelPreviewGrid` 컴포넌트로 격리(props: `columns`, `rows`) — 전문 그리드 라이브러리로 교체 시 이 컴포넌트만 교체
- [ ] 서비스·훅·타입·엔드포인트 상수 추가 및 MSW 핸들러
- [ ] 양쪽 TDD (pytest / Vitest+RTL+MSW)

### 2.2 Out of Scope

- 채팅 첨부 엑셀(전송 전)·KB 업로드 엑셀(인제스트 전)·분석 스냅샷 원천 데이터 프리뷰 — 후속 사이클. 단, 프리뷰 API 응답 스키마와 모달은 재사용 가능하게 설계한다
- 서식(병합·색·열 너비·숫자 포맷) 렌더링, 정렬·필터, 셀 편집
- 페이지네이션·lazy 시트 로딩(상한 1회 로딩으로 확정)
- `.xls` 레거시 포맷(산출 노드는 .xlsx만 생성), PDF/DOCX/PPTX 프리뷰
- REST `POST /api/v1/excel/export`(프론트 소비자 없음)의 프리뷰
- 프리뷰 결과 캐싱(TTL 1시간 파일이라 매 호출 파싱으로 충분)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | `GET /files/{file_id}/preview`는 다운로드 라우트와 동일한 저장소·owner 검증을 거쳐 .xlsx 프리뷰 JSON을 반환한다 | High | Pending |
| FR-02 | 응답은 `{file_id, filename, max_rows, max_cols, sheets:[{name, columns:[str], rows:[[str]], total_rows, total_cols, truncated}]}` 형식이며 모든 시트를 포함한다 | High | Pending |
| FR-03 | 시트당 상위 `max_rows`행·`max_cols`열만 담고, 초과 시 `truncated=true`와 실제 `total_rows/total_cols`를 함께 준다. 상한은 config 키(기본 100/50)로 조정 | High | Pending |
| FR-04 | 첫 행을 `columns`(헤더)로, 이후를 `rows`로 분리한다. 헤더 빈 셀은 `""`, 행이 0개면 `columns=[]`, `rows=[]` | High | Pending |
| FR-05 | 셀 값은 문자열로 통일: None/NaN→`""`, datetime→ISO 8601, 숫자→`str()`(정수형 float은 `1.0`이 아니라 `1`), bool→`true/false`, 수식→계산 결과 | High | Pending |
| FR-06 | 오류: 만료/없음 404 `FILE_NOT_FOUND`, 타인 403 `FORBIDDEN`, .xlsx 외 415 `PREVIEW_UNSUPPORTED`, 손상 422 `PREVIEW_PARSE_FAILED`(원인은 로그에 스택 트레이스) | High | Pending |
| FR-07 | 파싱은 `asyncio.to_thread`에서 openpyxl `read_only=True, data_only=True`로 수행해 이벤트 루프를 막지 않는다 | High | Pending |
| FR-08 | 프론트: 링크 텍스트가 `.xlsx`로 끝나는 산출 링크 옆에 "미리보기" 버튼을 표시한다. 다른 확장자 링크는 변화 없음 | High | Pending |
| FR-09 | `EXCEL_PREVIEW_TRIGGER` 상수(`src/constants/` 또는 `src/types/`)가 `'button'`이면 링크=다운로드·버튼=프리뷰, `'link'`면 링크 클릭=프리뷰·다운로드는 모달 안에서만. 두 모드 모두 테스트 | Medium | Pending |
| FR-10 | `ExcelPreviewModal`은 열릴 때만 프리뷰를 조회(TanStack Query, `enabled: open`)하고 시트 탭·그리드·truncated 안내·다운로드 버튼을 보여준다 | High | Pending |
| FR-11 | 모달 상태: 로딩 스피너 / 404 "파일이 만료되었습니다" / 403 "본인이 생성한 파일만 볼 수 있습니다" / 422·415 "미리보기를 만들 수 없습니다" + 다운로드 버튼 유지 / 빈 시트 "데이터 없음" | High | Pending |
| FR-12 | `ExcelPreviewGrid`는 `columns`/`rows`만 받는 순수 표시 컴포넌트로 분리해, 전문 그리드(ag-grid 등)로 교체 시 이 파일만 바뀐다 | Medium | Pending |
| FR-13 | 모달 다운로드 버튼은 `documentExtractorService.downloadGeneratedFile`을 재사용한다(중복 구현 금지, LoadingButton 패턴) | Medium | Pending |
| FR-14 | 엔드포인트 상수 `DOCUMENT_EXTRACTOR_FILE_PREVIEW(fileId)`와 타입 `ExcelPreviewResponse`를 백엔드 스키마와 동일 필드로 추가 (API 계약 동기화 규칙 4-1) | High | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Performance | 10MB·5시트·2만 행 .xlsx 프리뷰 응답 2초 이내, 응답 본문 1MB 이하(100×50×시트 수 기준) | pytest 타이밍 테스트(픽스처 생성) + 응답 크기 단언 |
| Performance | 이벤트 루프 비차단 — 파싱 중 다른 요청이 응답 | `to_thread` 사용 AST/호출 테스트 |
| Security | 다운로드와 동일 인증·owner 검증. file_id 형식 검증은 저장소가 이미 수행. 파일 경로는 store가 결정 | 라우터 테스트 401/403/404 |
| Security | 셀 값은 텍스트로만 렌더(React 기본 이스케이프), `dangerouslySetInnerHTML` 금지 | 프론트 테스트: `<script>` 문자열 셀이 텍스트로 표시 |
| Reliability | 파싱 실패가 프로세스·다른 요청에 전파되지 않음(422로 수렴) | 손상 파일 픽스처 테스트 |
| Compatibility | 기존 다운로드 라우트·링크 형식·에이전트 노드 무수정. 기존 테스트 `FAILED` 목록 diff 0 | 정렬된 FAILED 목록 비교 |
| Accessibility | 모달 `role="dialog"`, ESC 닫기, 탭 키보드 이동, 표는 `<table>` 시맨틱 | RTL 테스트 |
| Code rules | 함수 40줄 이하, if 중첩 2단계 이하, print 금지, 컴포넌트 파일 런타임 상수 export 금지 | 리뷰 + lint |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] FR-01~14 구현 및 각 FR에 대응하는 테스트가 RED→GREEN 순서로 작성됨
- [ ] 백엔드: 라우터 테스트(200/401/403/404/415/422), 유스케이스 테스트(상한·truncated·직렬화 규칙), 리더 테스트(실 .xlsx 픽스처 — 날짜·수식·빈 셀·다중 시트·빈 시트·2만 행)
- [ ] 프론트: `MarkdownRenderer`(버튼 노출 조건·두 트리거 모드), `ExcelPreviewModal`(로딩/오류 4종/빈 시트/탭 전환/다운로드 호출), `ExcelPreviewGrid`(열·행 렌더·이스케이프), 훅(MSW)
- [ ] 수동 E2E: 엑셀 생성 에이전트로 .xlsx 응답 → 미리보기 → 모든 시트 확인 → 모달에서 다운로드한 파일이 링크 다운로드와 바이트 동일
- [ ] `tsc -b` 및 lint 0 오류, pytest 기존 `FAILED` 목록 diff 0 (`uv run python -m pytest`)
- [ ] `docs/SOURCE-OF-TRUTH.md`·`idt/docs/task-registry.md` 갱신은 사용자 지시 시에만(위키는 `/wiki update` 전용)

### 4.2 Quality Criteria

- [ ] 프리뷰 응답 스키마가 백엔드 pydantic ↔ 프론트 TS 타입 필드 동일 (api-contract-sync 체크리스트)
- [ ] 트리거 모드 전환이 상수 1곳 변경으로 끝남(테스트로 두 모드 모두 고정)
- [ ] 그리드 교체 경계: `ExcelPreviewModal`은 `ExcelPreviewGrid`의 props 인터페이스에만 의존
- [ ] 로그: 프리뷰 시작/완료(file_id, sheet_count, elapsed_ms), 실패는 `exception=` 스택 포함

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 대용량 시트(수십만 행)에서 `total_rows` 계산을 위해 전 행을 순회해 느려짐 | Medium | Medium | openpyxl read_only의 `ws.max_row/max_column`(메타 기반, 즉시)를 사용. 메타가 부정확한 파일은 "약 N행"으로 허용하고 Design에서 확정 |
| 상한 100×50에 안 걸리는 넓은 시트(열 200개)가 가로 스크롤로 사용성 저하 | Low | Medium | 열도 상한 50 + "총 M열 중 50열" 안내, 모달 내부 가로 스크롤 |
| 링크 텍스트가 파일명이 아닌 경우(향후 노드가 문구를 바꾸면) 버튼이 사라짐 | Medium | Low | 1차 판별은 링크 텍스트 확장자. Design에서 응답 메타(`filename`)로 폴백할지 결정. 노드 링크 형식 테스트가 이미 존재 |
| 'link' 모드 전환 시 기존 "링크 클릭=다운로드" 테스트가 깨짐 | Low | Medium | 트리거 상수를 테스트에서 주입 가능하게(모킹) 설계해 두 모드 테스트 분리 |
| TTL 1시간 만료 후 프리뷰 404 — 사용자가 "버그"로 인식 | Low | High | 모달에 만료 사유 문구 명시(FR-11). TTL 변경은 범위 밖 |
| openpyxl `data_only=True`에서 수식 캐시가 없는 파일은 값이 None | Low | Low | 산출 노드는 pandas로 값만 기록하므로 수식 없음. 외부 파일 확장 시 재검토 |
| 프리뷰 응답을 react-markdown `a` 컴포넌트 내부에서 상태 관리하면 리렌더·메모 깨짐 | Medium | Medium | 모달 열림 상태는 `MarkdownRenderer` 밖(메시지 컴포넌트 또는 소형 Zustand 스토어)에서 소유. Design에서 확정 |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `src/api/routes/document_extractor_router.py` | API | `GET /files/{file_id}/preview` 라우트 추가(additive). 기존 다운로드 라우트 무수정 |
| `src/config.py` | Config | `excel_preview_max_rows=100`, `excel_preview_max_cols=50` 추가. 소비 지점 docstring 명기 |
| `src/domain/excel_preview/` (신규) | Domain | 응답 스키마(dataclass/pydantic), 셀 직렬화·상한 Policy, 예외 2종 |
| `src/application/excel_preview/` (신규) | Application | `PreviewExcelUseCase` — store.load → owner 검증 → 확장자 검사 → to_thread(reader) |
| `src/infrastructure/excel/preview_reader.py` (신규) | Infrastructure | openpyxl read_only 리더(ReaderInterface 구현) |
| `src/api/main.py` | DI | 유스케이스 팩토리 + `dependency_overrides` 1건 |
| `idt_front/src/constants/api.ts` | Const | `DOCUMENT_EXTRACTOR_FILE_PREVIEW(fileId)` 추가 |
| `idt_front/src/types/excelPreview.ts` (신규) | Type | `ExcelPreviewResponse`, `ExcelPreviewSheet`, `ExcelPreviewTrigger`, `EXCEL_PREVIEW_TRIGGER` 상수 |
| `idt_front/src/services/excelPreviewService.ts` (신규) | Service | `getPreview(fileId)` (authApiClient) |
| `idt_front/src/hooks/useExcelPreview.ts` (신규) | Hook | TanStack Query, `enabled` 제어 |
| `idt_front/src/components/chat/ExcelPreviewModal.tsx`, `ExcelPreviewGrid.tsx` (신규) | UI | 모달·그리드 |
| `idt_front/src/components/chat/MarkdownRenderer.tsx` | UI | `a` 컴포넌트에 .xlsx 분기 + 미리보기 버튼 + 트리거 모드 분기 |
| `idt_front/src/__tests__/mocks/handlers.ts` | Test | 프리뷰 MSW 핸들러 |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| `/files/{file_id}` 다운로드 라우트 | READ | `MarkdownRenderer` → `documentExtractorService.downloadGeneratedFile` | None (무수정, 모달에서 재사용) |
| `/files/{file_id}` 다운로드 라우트 | READ | `tests/api/test_document_extractor_router.py` | None |
| `AgentAttachmentStore.load` | READ | 다운로드 라우트, WS 첨부 라우팅(`supervisor_hooks`), 엑셀/문서/발표 생성 노드 | None (읽기만 추가) |
| `get_document_attachment_store` DI | READ | `main.py:5465` override | None (프리뷰 유스케이스가 동일 store 주입) |
| `MarkdownRenderer.a` | RENDER | `MessageBubble` 등 모든 채팅 메시지, `MarkdownRenderer.test.tsx` | Needs verification — .xlsx 외 링크 렌더 결과 불변 단언 필요 |
| `workflow_compiler` 링크 문자열 | WRITE | 문서/발표/엑셀 생성 노드 4곳 | None (형식 무수정, 프론트가 텍스트 확장자로 판별) |
| `config.Settings` | READ | 전 모듈 | None (키 추가만) |

### 6.3 Verification

- [ ] 위 소비자 전부가 변경 후 동작함을 기존 테스트 통과로 확인(FAILED diff 0)
- [ ] 인증·권한 변경 없음(기존 `get_current_user` + owner 비교 재사용)
- [ ] 응답 필드 추가만 있고 기존 응답·쿼리 변경 없음

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| **Starter** | Simple structure | Static sites | ☐ |
| **Dynamic** | Feature-based modules, BaaS | SaaS MVPs | ☐ |
| **Enterprise** | Strict layer separation, DI | 기존 idt Thin DDD | ☑ |

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 파싱 위치 | 백엔드 API / 프론트 SheetJS / 혼합 | **백엔드 API** | owner 검증·상한을 서버가 보장, 프론트 번들 증가 0, 후속 접점(첨부·KB)도 같은 응답 스키마 재사용 가능 (CP1 확정) |
| 파서 | openpyxl read_only / pandas read_excel | **openpyxl read_only, data_only** | 상위 N행만 스트리밍 읽기 가능, pandas는 전 시트 로드라 대용량에 불리. 값 직렬화 규칙은 domain Policy에 둠 |
| 라우트 위치 | document_extractor_router 하위 / 신규 라우터 | **document_extractor_router 하위 `/files/{id}/preview`** | 다운로드와 같은 저장소·인증·오류 계약을 공유. 라우터 지도 위키 갱신 대상 |
| 로딩 | 전 시트 1회 / 시트 lazy / 페이지네이션 | **전 시트 1회(상한 적용)** | API 1개, 탭 전환 즉시 (CP2 확정) |
| 셀 표현 | 문자열 통일 / 원시 타입 | **문자열 통일** | 프론트 타입 분기 없음, 예측 가능 (CP2 확정) |
| 진입 | 링크=프리뷰 / 링크 옆 버튼 / 자동 | **버튼, 상수로 링크 모드 전환 가능** | 기존 다운로드 UX 유지하면서 전환 비용 최소화 (CP2 확정) |
| 그리드 | 텍스트 `<table>` / 서식 반영 / 전문 그리드 | **텍스트 table, 컴포넌트 격리** | 1단계 단순, 전문 그리드 교체 시 `ExcelPreviewGrid`만 교체 (CP1 확정) |
| 모달 상태 소유 | 링크 컴포넌트 내부 / 메시지 레벨 / 스토어 | Design에서 결정 | react-markdown 컴포넌트 메모 특성 고려 |
| 프론트 데이터 | TanStack Query | TanStack Query | 프로젝트 표준, `enabled`로 열릴 때만 조회 |

### 7.3 Clean Architecture Approach

```
Selected Level: Enterprise (기존 Thin DDD 준수)

백엔드:
  interfaces   src/api/routes/document_extractor_router.py  (+ /preview 라우트)
  application  src/application/excel_preview/preview_use_case.py
  domain       src/domain/excel_preview/{schemas,policies,exceptions,interfaces}.py
  infrastructure src/infrastructure/excel/preview_reader.py   (openpyxl)
  DI           src/api/main.py

프론트:
  types/excelPreview.ts  ← 상수(EXCEL_PREVIEW_TRIGGER)·타입
  constants/api.ts       ← 엔드포인트
  services/excelPreviewService.ts
  hooks/useExcelPreview.ts
  components/chat/ExcelPreviewModal.tsx
  components/chat/ExcelPreviewGrid.tsx   ← 교체 경계
  components/chat/MarkdownRenderer.tsx   ← 버튼/트리거 분기
```

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- [x] `CLAUDE.md` 코딩 규칙 (루트·idt·idt_front)
- [x] `idt/docs/rules/*.md` (db-session, logging, testing, rag-retrieval, tool-and-mcp)
- [x] ESLint / Prettier / tsconfig (idt_front)
- [x] 위키 패턴: 런타임 상수 분리, LoadingButton, additive 계약, FAILED diff

### 8.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| 오류 코드 | document_extractor는 `{code, message}` detail | `PREVIEW_UNSUPPORTED`(415), `PREVIEW_PARSE_FAILED`(422) 추가 | High |
| 셀 직렬화 | 없음 | FR-05 규칙을 domain Policy + 테이블 테스트로 고정 | High |
| 트리거 상수 | 없음 | `types/excelPreview.ts`에 `as const` (컴포넌트 파일 export 금지) | Medium |
| 응답 타입 명명 | 백엔드 pydantic ↔ 프론트 TS | 필드명 snake_case 그대로(기존 `AttachmentUploadResponse` 관례) | Medium |

### 8.3 Environment Variables Needed

| Variable | Purpose | Scope | To Be Created |
|----------|---------|-------|:-------------:|
| `EXCEL_PREVIEW_MAX_ROWS` | 시트당 프리뷰 행 상한 (기본 100) | Server | ☐ |
| `EXCEL_PREVIEW_MAX_COLS` | 시트당 프리뷰 열 상한 (기본 50) | Server | ☐ |

프론트 환경변수 추가 없음.

### 8.4 Pipeline Integration

해당 없음 (단일 기능 PDCA).

---

## 9. Next Steps

1. [ ] `/pdca design excel-preview` — 모달 상태 소유 위치, `total_rows` 산출 방식, 트리거 상수 주입 방식 확정
2. [ ] Design 검토 후 `/pdca do excel-preview` (백엔드 → 프론트 순, TDD)
3. [ ] 후속 사이클 후보: 채팅 첨부 엑셀 프리뷰(전송 전), KB 업로드 엑셀 프리뷰, 분석 스냅샷 원천 표 보기 — 본 사이클의 응답 스키마·모달 재사용

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-10-12 | Initial draft — Checkpoint 1·2 확정 사항 반영 | 배상규 |
