# document-file-preview Planning Document

> **Summary**: 에이전트가 만든 Word(.docx)·PDF 산출물을 엑셀처럼 채팅 화면의 모달에서 미리 본다
>
> **Project**: sangplusbot (Agent Builder)
> **Author**: 배상규
> **Date**: 2026-11-16
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 문서추출기·문서생성기가 만든 .docx/.pdf는 채팅 링크를 눌러 내려받아야만 내용을 볼 수 있다. .xlsx는 이미 "미리보기" 버튼과 모달이 있어 형식 간 경험이 다르다. |
| **Solution** | 기존 다운로드 API(`GET /files/{id}`)로 파일을 blob으로 받아 브라우저에서 그린다. .docx는 `docx-preview` 라이브러리(모달을 열 때만 지연 로드), .pdf는 브라우저 내장 PDF 뷰어(iframe)를 쓴다. 백엔드는 바꾸지 않는다. |
| **Function/UX Effect** | 문서 링크 옆에 엑셀과 같은 "미리보기" 버튼이 생기고, 모달에서 표·글꼴·쪽 나눔이 원본에 가깝게 보인다. 내용을 확인한 뒤 모달 안에서 바로 다운로드한다. |
| **Core Value** | 에이전트 소유자(P2)와 사용자가 산출 문서를 파일을 열지 않고 검토할 수 있다. 미리보기 진입 방식이 엑셀·Word·PDF에서 하나로 같아진다. |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | .docx/.pdf 산출물은 다운로드해야만 볼 수 있고, .xlsx만 미리보기가 있어 형식별 경험이 다르다 |
| **WHO** | 채팅에서 문서추출기·문서생성기 결과를 받는 사용자, 결과물을 검토하는 에이전트 소유자(P2) |
| **RISK** | docx를 DOM에 직접 렌더할 때 원본 서식이 앱 CSS와 섞이거나(스타일 누수), 문서 안 링크·외부 리소스가 그대로 동작할 수 있다 |
| **SUCCESS** | .docx/.pdf 링크 옆 "미리보기" 버튼 → 모달에 본문 표시, 404/403/렌더 실패 시 엑셀과 같은 오류 안내, 미리보기 라이브러리가 초기 번들에 포함되지 않음 |
| **SCOPE** | 프론트 전용: 서비스 blob 조회 함수 1개 + 미리보기 스토어·모달 일반화 + docx/pdf 뷰어 컴포넌트 + MarkdownRenderer 버튼 조건 확장. 백엔드·HWP·편집 기능 제외 |

---

## 1. Overview

### 1.1 Purpose

채팅에서 받은 Word·PDF 산출물을 다운로드 없이 모달에서 확인할 수 있게 한다.

### 1.2 Background

현재 동작(코드 확인 결과):

- 산출 형식은 `pdf`·`docx` 두 가지다 (`idt/src/domain/document_extractor/tool_config.py:8`, `idt/src/domain/document_generator/tool_config.py:8`). 파일은 `AgentAttachmentStore`에 저장되고, 채팅 답변에는 `DOC_EXTRACTOR_FILE_PREFIX` 링크로 나간다.
- 다운로드 API `GET /api/v1/document-extractor/files/{file_id}`는 소유자 검증 후 `FileResponse`를 내려준다. `.docx`·`.pdf` media type이 이미 등록돼 있다 (`document_extractor_router.py:134`).
- 엑셀 미리보기(excel-preview)는 백엔드가 openpyxl로 JSON을 만들고(`/files/{id}/preview`, .xlsx 외 415), 프론트는 `excelPreviewStore` + `ExcelPreviewModal`(ChatPage에 1회 마운트)로 보여준다. 진입 스위치는 `EXCEL_PREVIEW_TRIGGER='button'` (`idt_front/src/types/excelPreview.ts`).
- `MarkdownRenderer`의 링크 처리는 파일명 확장자가 `.xlsx`일 때만 "미리보기" 버튼을 그린다 (`MarkdownRenderer.tsx:76`). 그 외 형식은 클릭 시 `downloadGeneratedFile`로 저장만 된다.

방식 검토 결과(사용자 확인 완료):

| 방식 | 판단 |
|------|------|
| 브라우저 렌더 (docx-preview + PDF iframe) | **채택**. 백엔드 변경 없음, 서식 보존이 가장 좋은 경량 방식 |
| 서버 docx→HTML (mammoth 등) | 쪽 레이아웃·머리글·표 서식 손실이 커서 제외 |
| 서버 docx→PDF (LibreOffice) | 원본과 가장 가깝지만 배포 이미지에 LibreOffice가 필요해 제외 |

### 1.3 Related Documents

- excel-preview 구현: `idt/src/application/excel_preview/`, `idt_front/src/components/chat/ExcelPreviewModal.tsx`
- `docs/wiki/backend/api/router-map.md` — document_extractor 라우터, `/files/{id}/preview` 검증 순서
- `docs/wiki/backend/patterns/doc-extractor-fill-contracts.md` — DOCX 직접 채움 결과물 구조
- `docs/archive/2026-11/extractor-template-preview/` — 저장 양식 미리보기(빌더 화면, 이번 범위와 별개)

---

## 2. Scope

### 2.1 In Scope

- [ ] 서비스: 다운로드 엔드포인트를 blob으로 받아 반환하는 함수 (`documentExtractorService.fetchGeneratedFileBlob`), 저장은 하지 않음
- [ ] 미리보기 진입 일반화: 확장자 → 미리보기 종류(`xlsx`·`docx`·`pdf`) 판별 유틸, 진입 스위치를 문서 공통으로 정리
- [ ] 모달: 기존 엑셀 모달은 유지하고, docx/pdf용 `DocumentPreviewModal`을 추가 (스토어에 `kind` 포함)
- [ ] docx 뷰어: `docx-preview`를 `import()`로 지연 로드해 격리된 컨테이너에 렌더
- [ ] pdf 뷰어: `URL.createObjectURL(blob)` → iframe, 모달 닫을 때 `revokeObjectURL`
- [ ] 오류 상태: 404(만료)·403(소유자 아님)·렌더 실패를 엑셀 모달과 같은 문구·다운로드 버튼 규칙으로 표시
- [ ] MarkdownRenderer: `.docx`·`.pdf` 링크에도 "미리보기" 버튼 표시
- [ ] 테스트: 유틸·서비스(MSW blob)·모달 상태·버튼 노출 (Vitest + RTL + MSW)

### 2.2 Out of Scope

- 백엔드 변경 (새 API·변환 엔진 없음)
- .hwp/.hwpx 산출물 미리보기 (현재 산출 형식이 아님)
- 미리보기 안에서 편집·주석
- 채팅 외 화면(실행 내역·워크스페이스·빌더 저장 양식) 진입점
- 원본 Word와의 픽셀 단위 일치 (docx-preview의 지원 범위를 따름)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | 링크 텍스트(파일명) 확장자가 `.docx`·`.pdf`이면 링크 옆에 "미리보기" 버튼을 표시한다. 링크 클릭은 기존처럼 다운로드한다 (엑셀과 동일, `'button'` 모드) | High | Pending |
| FR-02 | 미리보기 버튼은 스토어 `open({fileId, filename, kind})`만 호출하고, 모달은 ChatPage에 1회 마운트한다 (엑셀과 같은 구조) | High | Pending |
| FR-03 | 파일은 기존 다운로드 엔드포인트에서 blob으로 받는다. 같은 파일을 다시 열면 TanStack Query 캐시를 쓴다 | High | Pending |
| FR-04 | .docx는 `docx-preview`로 렌더한다. 라이브러리는 모달이 열릴 때 동적 import하고, 초기 번들에 들어가지 않는다 | High | Pending |
| FR-05 | .pdf는 blob URL을 iframe에 넣어 브라우저 내장 뷰어로 보여주고, 모달을 닫으면 URL을 해제한다 | High | Pending |
| FR-06 | 모달 상단에 파일명, 본문 아래(또는 머리)에 "다운로드" 버튼을 두고 `downloadGeneratedFile`을 재사용한다 | High | Pending |
| FR-07 | 오류 매핑: 404 → "파일이 만료되었거나 찾을 수 없습니다"(다운로드 숨김), 403 → "본인이 생성한 파일만 볼 수 있습니다"(숨김), 렌더 실패 → "미리보기를 만들 수 없습니다. 파일은 다운로드할 수 있습니다", 네트워크·기타 → "미리보기를 불러오지 못했습니다. 다시 시도해주세요"(둘 다 다운로드 표시, Design §6.1) | High | Pending |
| FR-08 | docx 렌더 결과의 스타일이 앱 화면에 새지 않도록 격리한다 (shadow DOM 또는 sandbox iframe 중 Design에서 선택) | High | Pending |
| FR-09 | 렌더된 문서 안의 하이퍼링크는 새 창(`noopener`)으로만 열리게 한다 | Medium | Pending |
| FR-10 | 로딩 중에는 스피너와 "문서를 불러오는 중" 문구를 보여준다 | Medium | Pending |
| FR-11 | 진입 스위치(`button`/`link`)는 엑셀·문서 공통 상수 1곳에서 바꾼다. 런타임 상수는 `src/types/`에 둔다 | Low | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Performance | 1MB 이하 .docx는 모달 오픈 후 2초 안에 첫 화면 표시 (로컬) | 수동 측정 |
| Bundle | 메인 청크 크기 증가 5KB 이하 (docx-preview·jszip은 별도 청크) | `vite build` 결과 비교 |
| Security | 소유자 검증은 기존 다운로드 API에 맡기고, 프론트는 인증 클라이언트(`authApiClient`)로만 받는다. 렌더 영역에서 스크립트 실행 없음 | 코드 리뷰 + 링크 포함 docx 수동 확인 |
| Accessibility | 모달은 기존 `Modal` 컴포넌트(포커스 트랩·ESC 닫기) 사용, PDF iframe에 `title` 지정 | RTL 테스트 |
| License | `docx-preview`(Apache-2.0)·의존 `jszip` 라이선스와 버전을 Design에서 고정 확인 | package-lock 확인 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] .docx 링크 옆 "미리보기" → 모달에 본문·표가 보인다
- [ ] .pdf 링크 옆 "미리보기" → 모달 iframe에 PDF가 보인다
- [ ] .xlsx 미리보기 동작이 바뀌지 않는다 (기존 테스트 통과)
- [ ] 만료 파일(404)·타인 파일(403)·손상 파일에서 FR-07 문구가 나온다
- [ ] `docx-preview`가 별도 청크로 분리된다
- [ ] 새 단위 테스트 작성·통과, 관련 기존 테스트 회귀 없음

### 4.2 Quality Criteria

- [ ] ESLint 오류 0 (master 대비 신규 오류 없음)
- [ ] `tsc` 신규 타입 오류 없음, `vite build` 성공
- [ ] 화면 확인: 실제 문서추출기 산출 .docx 1건, 문서생성기 산출 .docx/.pdf 각 1건

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| docx 원본 CSS가 앱 화면에 섞임 | High | High | shadow DOM 또는 sandbox iframe에 렌더 (FR-08), Design에서 둘 중 하나 확정 |
| 문서 안 링크·외부 이미지가 동작 | Medium | Medium | 렌더 후 `a` 태그에 `target=_blank rel=noopener noreferrer` 부여, 외부 리소스 로드 옵션 끔 |
| docx-preview가 일부 서식(텍스트 상자·도형·각주) 미지원 | Medium | Medium | 모달 부제에 "원본과 일부 서식이 다를 수 있습니다" 안내, 다운로드 버튼 항상 노출(렌더 성공 시에도) |
| 큰 파일에서 blob 다운로드·렌더 지연 | Medium | Low | 기존 다운로드 timeout 120s 재사용, 로딩 상태 표시. 크기 상한은 Design에서 결정 |
| PDF iframe이 CSP(frame-src blob:)에 막힘 | Medium | Low | 배포 설정의 CSP 헤더 확인. 막히면 `object` 태그 또는 새 탭 열기로 대체 |
| jsdom에서 docx-preview·iframe 렌더 검증 불가 | Low | High | 렌더 함수는 모듈 경계로 분리해 vi.mock, 실제 렌더는 화면 확인으로 검증 |
| 모바일 브라우저(iOS Safari) iframe PDF 표시 제한 | Low | Medium | 표시 실패 시 다운로드 안내. 모바일 확인은 이월 가능 항목으로 둔다 |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `MarkdownRenderer.tsx` 링크 렌더러 | Component | 미리보기 버튼 조건을 `.xlsx` → `.xlsx/.docx/.pdf`로 확장, 종류별 스토어 호출 |
| `excelPreviewStore` | Zustand store | 그대로 두거나 `kind`를 가진 공통 스토어로 일반화 (Design에서 결정) |
| `types/excelPreview.ts` `EXCEL_PREVIEW_TRIGGER` | Const | 문서 공통 스위치로 이름·위치 정리 |
| `documentExtractorService` | Service | `fetchGeneratedFileBlob` 추가 (기존 `downloadGeneratedFile`은 변경 없음) |
| `ChatPage` | Page | `DocumentPreviewModal` 1회 마운트 추가 |
| `package.json` | Dependency | `docx-preview` 추가 |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| MarkdownRenderer 링크 | READ | 채팅 메시지 `MessageBubble` → `MarkdownRenderer` | Needs verification (`MarkdownRendererExcelPreview*.test.tsx` 2종 회귀) |
| excelPreviewStore | READ/UPDATE | `ExcelPreviewModal`, `MarkdownRenderer` | Needs verification (일반화 시) |
| EXCEL_PREVIEW_TRIGGER | READ | `MarkdownRenderer`, LinkMode 테스트 | Needs verification (이름 변경 시) |
| downloadGeneratedFile | READ | `ExcelPreviewModal`, `MarkdownRenderer`, `AuthenticatedImage` | None (변경 없음) |
| GET /files/{id} | READ | 다운로드 전 경로 | None (백엔드 변경 없음) |

### 6.3 Verification

- [ ] 엑셀 미리보기 테스트(`ExcelPreviewModal`·`ExcelPreviewGrid`·`MarkdownRendererExcelPreview*`) 통과
- [ ] 인증·소유자 검증 변경 없음 (백엔드 무변경)
- [ ] 이미지 첨부(`AuthenticatedImage`) 경로 영향 없음

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| **Starter** | Simple structure | Static sites | ☐ |
| **Dynamic** | Feature-based modules | Web apps with backend | ☑ (프론트 전용 변경) |
| **Enterprise** | Strict layer separation, DI | Complex architectures | ☐ |

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 렌더 위치 | 브라우저 / 서버 HTML / 서버 PDF | 브라우저 | 백엔드 무변경, 서식 보존, 배포 부담 없음 (사용자 확인) |
| docx 렌더러 | docx-preview / mammoth.js | docx-preview | 쪽 나눔·표·글꼴 보존. mammoth는 의미 구조만 변환 |
| PDF 렌더러 | iframe(내장 뷰어) / pdf.js | iframe | 추가 의존성 없음. pdf.js는 필요 시 후속 |
| 파일 조회 | 기존 다운로드 API blob / 새 API | 기존 API | 소유자·만료 검증을 그대로 공유 |
| 상태 관리 | Zustand(기존 패턴) | Zustand | 엑셀 모달과 같은 "memo 트리 밖 상태 소유" 구조 |
| 데이터 조회 | TanStack Query | TanStack Query | blob 캐시·로딩·오류 상태 일관 |
| 진입 방식 | button / link | button | 엑셀과 동일 (사용자 확인) |
| 테스트 | Vitest + RTL + MSW | 동일 | 프로젝트 표준 |

### 7.3 Folder Structure Preview

```
idt_front/src/
├── components/chat/
│   ├── DocumentPreviewModal.tsx      (신규: docx/pdf 모달)
│   ├── DocxPreviewView.tsx           (신규: 지연 로드 렌더)
│   └── PdfPreviewView.tsx            (신규: blob URL iframe)
├── hooks/useGeneratedFileBlob.ts     (신규)
├── services/documentExtractorService.ts  (fetchGeneratedFileBlob 추가)
├── store/documentPreviewStore.ts     (신규 또는 excelPreviewStore 일반화)
├── types/documentPreview.ts          (kind 타입·트리거 상수)
└── utils/previewKind.ts              (확장자 → kind)
```

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- [x] `CLAUDE.md`(루트·`idt_front/`) 코딩 규칙
- [x] ESLint·TypeScript 설정
- [x] 컴포넌트 파일 런타임 상수 export 금지 → 상수는 `src/types/*.ts`
- [x] `authApiClient` 오류는 `ApiError(message, status, code)`로 온다 (`err.response` 사용 금지)

### 8.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| 동적 import 청크 | 사용 사례 확인 필요 | `docx-preview` 지연 로드 패턴·테스트 mock 방식 | High |
| blob 응답 MSW 핸들러 | 다운로드 테스트 사례 확인 필요 | `HttpResponse.arrayBuffer` 기반 핸들러 | Medium |
| 오류 문구 | 엑셀 모달 `errorView` 내부 함수 | 공통 유틸로 뺄지 Design에서 결정 | Medium |

### 8.3 Environment Variables Needed

없음.

---

## 9. Next Steps

1. [ ] `/pdca design document-file-preview` — 스토어 일반화 범위, 스타일 격리 방식(shadow DOM / sandbox iframe), 파일 크기 상한 결정
2. [ ] `docx-preview` 버전·라이선스 고정, CSP `frame-src blob:` 확인
3. [ ] 구현 (TDD)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-11-16 | Initial draft | 배상규 |
| 0.2 | 2026-11-16 | FR-07 기타 오류 문구를 Design §6.1에 맞춤, blob 조회 함수는 기존 것 재사용 | 배상규 |
