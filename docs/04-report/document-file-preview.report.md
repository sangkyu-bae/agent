# document-file-preview Completion Report

> **Summary**: 채팅 산출 .docx·.pdf를 엑셀과 같은 "미리보기" 버튼과 모달로 다운로드 없이 확인한다 (프론트 전용)
>
> **Project**: sangplusbot (Agent Builder)
> **Author**: 배상규
> **Date**: 2026-11-16
> **Status**: Completed (미커밋 — worktree `wt/document-file-preview`, 브랜치 `feature/document-file-preview`)

---

## Executive Summary

### 1.1 Project Overview

| 항목 | 내용 |
|------|------|
| Feature | document-file-preview |
| 기간 | 2026-11-16 (Plan → Design → Do → Check → Act-1, 1일) |
| 범위 | `idt_front/` 신규 9 + 테스트 8, 수정 10 파일. 백엔드 변경 없음 |
| 설계안 | Option C (문서 전용 스토어·모달, 오류 매핑·진입 스위치만 공통화) + Shadow DOM 격리 |

### 1.2 Results Summary

| 지표 | 값 |
|------|-----|
| Match Rate | 96.5% (Check 95.3% → Act-1 후) |
| Iteration | 1 |
| Plan Success Criteria | 7개 중 6 Met, 1 Partial (PDF 화면 확인 이월) |
| Gap | Critical 0, Important 1, Minor 9 — 전부 Act-1에서 처리 |
| 테스트 | 관련 범위 809건 통과 (chat 133 · ChatPage 27 · hooks/utils/lib/store/services 649) |

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | 문서추출기·문서생성기가 만든 .docx/.pdf는 내려받아야만 볼 수 있었고, .xlsx만 미리보기가 있었다. |
| **Solution** | 기존 다운로드 API로 파일을 받아 브라우저에서 렌더한다. .docx는 `docx-preview@0.4.1`을 모달을 열 때만 불러와 Shadow DOM에 그리고, .pdf는 내장 PDF 뷰어(iframe)로 보여준다. |
| **Function/UX Effect** | .docx·.pdf 링크 옆에 엑셀과 같은 "미리보기" 버튼이 생겼다. 헤드리스 확인에서 실제 양식(여신심의서)의 제목·표 3개·본문이 표시됐고, 앱 화면 스타일은 렌더 전후 동일했다. 첫 화면 번들 증가는 4.1KB(gzip 약 1.5KB)이고, 렌더 라이브러리는 171KB 별도 청크로 분리됐다. |
| **Core Value** | 사용자와 에이전트 소유자(P2)가 파일을 열지 않고 산출 문서를 검토한다. 엑셀·Word·PDF 미리보기의 진입 방식과 오류 안내가 같아졌다. |

## 1.4 Success Criteria Final Status

| Plan §4 기준 | 상태 | 근거 |
|------|:-:|------|
| .docx 미리보기 → 본문·표 표시 | ✅ | 헤드리스: 합성 docx 2쪽, 실제 양식 docx 표 3개 렌더 |
| .pdf 미리보기 → iframe 표시 | ⚠️ | 단위 테스트 통과. 헤드리스 Chromium에 내장 PDF 뷰어가 없어 화면 확인 이월 |
| .xlsx 동작 불변 | ✅ | `ExcelPreviewModal*.test` 무수정 통과, 오류 문구 동일 |
| 404/403/손상 파일 문구 | ✅ | 단위 테스트(서비스 MSW 포함) + 헤드리스 깨진 파일 확인 |
| docx-preview 별도 청크 | ✅ | `vite build` 별도 청크 171.71KB |
| 새 테스트 통과·회귀 없음 | ✅ | 관련 범위 809건 통과 |
| lint·tsc·build | ✅ | 변경 26파일 lint error 0, tsc 오류 목록 master와 동일(211), build 성공 |

**Success Rate: 6/7 Met, 1 Partial.**

## 1.5 Decision Record Summary

| 단계 | 결정 | 준수 | 결과 |
|------|------|:-:|------|
| Plan | 브라우저 렌더 (서버 HTML·LibreOffice 변환 제외) | ✅ | 백엔드 무변경, 배포 이미지 영향 없음 |
| Plan | PDF 포함, 진입 방식은 엑셀과 동일(button) | ✅ | `FILE_PREVIEW_TRIGGER` 하나로 세 형식 전환 |
| Design | Option C | ✅ | 엑셀 모달 변경은 오류 매핑 함수 교체뿐 |
| Design | Shadow DOM 격리 | ✅ (수정) | CSS 규칙은 격리됐으나 상속 속성이 넘어옴 → `:host` 초기화로 보완 (Check G-01) |
| Design | docx 10MB 상한, blob 5분 캐시 | ✅ | `types/filePreview.ts`, `useGeneratedFileBlob.ts` |

---

## 2. Related Documents

| 단계 | 문서 |
|------|------|
| Plan | [document-file-preview.plan.md](../01-plan/features/document-file-preview.plan.md) (v0.2) |
| Design | [document-file-preview.design.md](../02-design/features/document-file-preview.design.md) (v0.2) |
| Analysis | [document-file-preview.analysis.md](../03-analysis/document-file-preview.analysis.md) (v0.2) |

---

## 3. Completed Items

### 3.1 Functional Requirements

| ID | 내용 | 상태 |
|----|------|:-:|
| FR-01 | .docx·.pdf 링크 옆 "미리보기" 버튼, 링크 클릭은 다운로드 | ✅ |
| FR-02 | 스토어 `open()`만 호출, ChatPage 1회 마운트 | ✅ |
| FR-03 | 기존 다운로드 API blob 조회, 재오픈 시 캐시 | ✅ |
| FR-04 | docx-preview 지연 로드·별도 청크 | ✅ |
| FR-05 | PDF blob URL iframe, 닫을 때 해제 | ✅ (화면 확인 이월) |
| FR-06 | 모달 다운로드 버튼 | ✅ |
| FR-07 | 404·403·렌더 실패·기타 오류 문구 | ✅ |
| FR-08 | 스타일 격리 | ✅ |
| FR-09 | 문서 링크 새 창·위험 스킴 제거 | ✅ |
| FR-10 | 로딩 표시 | ✅ |
| FR-11 | 공통 진입 스위치 | ✅ |

### 3.2 Non-Functional Requirements

| 항목 | 기준 | 결과 |
|------|------|------|
| Bundle | 메인 청크 증가 5KB 이하 | +4.1KB raw ✅ |
| Security | 인증은 기존 API, 렌더 영역 스크립트 없음 | `javascript:`·`file:` href 제거, altChunk·주석·변경 추적 렌더 끔 ✅ |
| Accessibility | 기존 Modal, iframe title | ✅ |
| License | 버전·라이선스 고정 | docx-preview 0.4.1 Apache-2.0, jszip 3.10.2 MIT/GPL 이중(MIT 선택) ✅ |
| Performance | 1MB 이하 docx 2초 내 | 수동 측정 미실시 (헤드리스에서 38KB 문서는 즉시 표시) |

### 3.3 Deliverables

| 구분 | 파일 |
|------|------|
| 신규 | `types/filePreview.ts`, `utils/previewKind.ts`, `utils/filePreviewError.ts`, `store/documentPreviewStore.ts`, `hooks/useGeneratedFileBlob.ts`, `lib/docxRenderer.ts`, `components/chat/{DocumentPreviewModal,DocxPreviewView,PdfPreviewView}.tsx` |
| 신규 테스트 | 위 파일별 테스트 + `MarkdownRendererDocumentPreview{,LinkMode}.test.tsx` |
| 수정 | `MarkdownRenderer.tsx`, `ExcelPreviewModal.tsx`, `types/excelPreview.ts`, `lib/queryKeys.ts`, `pages/ChatPage/index.tsx`, `package.json`·`package-lock.json`, 기존 테스트 3개(MarkdownRenderer 엑셀 2종, documentExtractorService) |

---

## 4. Incomplete Items

### 4.1 Carried Over

| 항목 | 이유 |
|------|------|
| PDF 실브라우저 확인 (Chrome·Edge, 가능하면 iOS Safari) | 헤드리스 Chromium에 내장 PDF 뷰어 없음 |
| 외부 이미지가 링크된 docx로 미로딩 확인 | 테스트 문서에 외부 이미지 없음 |
| 실백엔드에서 문서추출기·문서생성기 실행 → 채팅 버튼 → 모달 흐름 | 하네스(route 주입)로만 확인 |
| 1MB 이상 docx 렌더 시간 측정 | 미실시 |

### 4.2 Known Limitations

- docx-preview가 단일 줄 간격을 `line-height: 100%`로 그려 표 칸 글자가 Word보다 빽빽하다.
- 문서에 지정된 글꼴이 PC에 없으면 브라우저 대체 글꼴로 표시된다. 글꼴 지정이 없는 문서는 맑은 고딕으로 그린다.

---

## 5. Quality Metrics

### 5.1 Final Analysis Results

| 축 | 점수 |
|----|:-:|
| Structural | 100% |
| Functional | 100% |
| Contract | 100% |
| Runtime | 90% (PDF·외부 이미지 미확인) |
| **Overall** | **96.5%** |

### 5.2 Resolved Issues (Act-1)

| ID | 내용 | 조치 |
|----|------|------|
| G-01 | Shadow DOM 안으로 앱 글꼴·줄 간격이 상속됨 | `:host { all: initial }` + 기본 글꼴 맑은 고딕 |
| G-02 | `#책갈피` 링크가 이동하지 않고 채팅 URL에 해시만 붙음 | shadow root 안에서 직접 스크롤 |
| G-03 | blob 404·403의 `ApiError.status` 단언 없음 | 서비스 테스트 강화·403 추가 |
| G-04 | StrictMode 취소된 첫 렌더가 root를 건드림 | `isCancelled` 인자 |
| G-05 | 임시 확인 하네스 | 삭제 |
| G-06~G-09 | 문서 불일치, store 테스트 없음 | Plan·Design v0.2, store 테스트 추가 |
| G-10 | 테스트가 실제 재시도 지연을 기다림 | `retryDelay: 0` |

---

## 6. Lessons Learned

### 6.1 Keep

- 기존 자산부터 찾았다. blob 조회 함수(`fetchGeneratedFileBlob`)와 다운로드 API 소유자 검증을 그대로 써서 백엔드를 건드리지 않았다.
- 렌더 라이브러리 호출을 `lib/docxRenderer.ts` 한 곳에 두어 jsdom 테스트에서는 경계만 mock하고, 실제 렌더는 헤드리스로 따로 확인했다.
- 헤드리스 확인을 Playwright route 주입 + 임시 하네스 페이지로 해서 백엔드·로그인 없이 모달 전체를 실렌더했다.

### 6.2 Problem

- Design에 "앱 폰트는 문서에 상속되지 않는다"고 적었지만 틀렸다. Shadow DOM은 CSS 규칙만 막고 상속 속성은 막지 않는다. 단위 테스트(jsdom)로는 드러나지 않았고, 실렌더 측정에서 잡혔다.
- gap-detector 에이전트는 셸이 없어 테스트·빌드를 돌리지 못했다. 런타임 결과는 메인 세션에서 따로 채웠다.

### 6.3 Try

- Shadow DOM으로 외부 HTML을 넣는 기능은 설계 단계에서 `:host` 상속 초기화를 기본으로 넣는다.
- 렌더 결과가 화면 품질을 좌우하는 기능은 Do 단계 안에서 헤드리스 실렌더 확인을 먼저 한다.

---

## 7. Process Improvement Suggestions

| 영역 | 제안 |
|------|------|
| PDCA | Check에서 정적 분석(gap-detector)과 실렌더 확인을 병렬로 돌린 방식이 효과적이었다. 실렌더에서 정적 분석이 놓친 상속 문제를 잡았다 |
| 환경 | PDF 화면 확인은 헤드리스가 아닌 headed 브라우저 또는 Chrome 확장이 필요하다 |

---

## 8. Next Steps

### 8.1 Immediate

1. PDF 실브라우저 확인
2. 커밋·PR (프론트 코드 + PDCA 문서). 메인 체크아웃 `docs/`의 문서 사본은 PR 머지 전 정리 (pull 차단 함정)
3. 머지 후 `/pdca archive document-file-preview`, worktree 정리 (node_modules junction 먼저 제거)

### 8.2 Next Cycle 후보

- 실행 내역·워크스페이스 등 채팅 외 화면에 같은 미리보기 진입점
- 표 칸 줄 간격 보정 (docx-preview 출력에 CSS 덧씌우기)
- 형식이 더 늘면 Option B(공통 FilePreview 셸)로 엑셀까지 통합

---

## 9. Changelog

### v1.0.0 (2026-11-16)

**Added**
- 채팅 산출 .docx·.pdf 미리보기 버튼과 모달 (`DocumentPreviewModal`)
- `docx-preview@0.4.1` 의존성 (지연 로드)

**Changed**
- 미리보기 진입 스위치 `EXCEL_PREVIEW_TRIGGER` → `FILE_PREVIEW_TRIGGER` (`types/filePreview.ts`)
- 엑셀 모달 오류 매핑을 공통 유틸 `previewErrorView`로 이관 (문구 동일)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-11-16 | 완료 보고서 | 배상규 |
