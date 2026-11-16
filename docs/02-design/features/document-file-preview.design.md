# document-file-preview Design Document

> **Summary**: 채팅 산출 .docx·.pdf를 브라우저에서 렌더해 엑셀과 같은 "미리보기" 모달로 보여준다 (프론트 전용)
>
> **Project**: sangplusbot (Agent Builder)
> **Author**: 배상규
> **Date**: 2026-11-16
> **Status**: Draft
> **Planning Doc**: [document-file-preview.plan.md](../../01-plan/features/document-file-preview.plan.md)
> **Architecture**: Option C — Pragmatic Balance (사용자 선택)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | .docx/.pdf 산출물은 다운로드해야만 볼 수 있고, .xlsx만 미리보기가 있어 형식별 경험이 다르다 |
| **WHO** | 채팅에서 문서추출기·문서생성기 결과를 받는 사용자, 결과물을 검토하는 에이전트 소유자(P2) |
| **RISK** | docx를 DOM에 직접 렌더할 때 원본 서식이 앱 CSS와 섞이거나(스타일 누수), 문서 안 링크·외부 리소스가 그대로 동작할 수 있다 |
| **SUCCESS** | .docx/.pdf 링크 옆 "미리보기" 버튼 → 모달에 본문 표시, 404/403/렌더 실패 시 엑셀과 같은 오류 안내, 미리보기 라이브러리가 초기 번들에 포함되지 않음 |
| **SCOPE** | 프론트 전용: 미리보기 종류 판별·공통 오류 매핑·스토어·모달·docx/pdf 뷰어 + MarkdownRenderer 버튼 조건 확장. 백엔드·HWP·편집 기능 제외 |

---

## 1. Overview

### 1.1 Design Goals

- .docx/.pdf 산출 링크에 엑셀과 같은 진입점(버튼 모드)과 모달을 제공한다.
- 백엔드를 바꾸지 않는다. 소유자·만료 검증은 기존 다운로드 API(`GET /files/{id}`)에 맡긴다.
- 엑셀 미리보기 동작은 바꾸지 않는다. 공통으로 빼는 것은 오류 문구 매핑과 진입 스위치뿐이다.
- `docx-preview`(+`jszip`)는 별도 청크로 지연 로드한다.

### 1.2 Design Principles

- **기존 자산 재사용**: blob 조회는 이미 있는 `documentExtractorService.fetchGeneratedFileBlob`(image-generation-tool D-10, `AuthenticatedImage`가 사용 중)을 그대로 쓴다. Plan §2.1의 "함수 추가" 항목은 불필요한 것으로 정정한다.
- **memo 트리 밖 상태 소유**: excel-preview §5.3과 같이 MarkdownRenderer는 스토어 `open()`만 호출하고 모달은 ChatPage에 1회 마운트한다.
- **렌더 경계 분리**: `docx-preview` 호출은 `lib/docxRenderer.ts` 한 곳에만 둔다. jsdom에서 렌더할 수 없으므로 컴포넌트 테스트는 이 모듈을 vi.mock 한다.

---

## 2. Architecture Options

### 2.0 Architecture Comparison

| Criteria | A: Minimal | B: Clean | C: Pragmatic |
|----------|:-:|:-:|:-:|
| **Approach** | `excelPreviewStore`에 `kind` 추가, `ExcelPreviewModal` 안에서 분기 | 공통 FilePreview 스토어·모달 셸 + 형식별 뷰어 레지스트리, 엑셀도 이관 | docx/pdf 전용 스토어·모달 신설, 오류 매핑·스위치만 공통화 |
| **New Files** | 3 | 10+ | 9 |
| **Modified Files** | 4 | 8+ (엑셀 테스트 다수) | 6 |
| **Complexity** | Low | High | Medium |
| **Maintainability** | Low (엑셀 모달이 세 형식을 떠안음) | High | Medium-High |
| **Effort** | Low | High | Medium |
| **Risk** | 엑셀 회귀 Medium | 엑셀 회귀 High | 엑셀 회귀 Low |
| **Recommendation** | 빠른 시연용 | 형식이 4종 이상으로 늘 때 | **기본 선택** |

**Selected**: Option C. **Rationale**: 엑셀 모달(JSON 그리드)과 문서 모달(blob 렌더)은 데이터 원천·로딩 방식이 달라 한 컴포넌트에 넣으면 분기만 커진다. 공통점(오류 문구·다운로드 버튼·진입 스위치)만 빼면 엑셀 쪽 변경을 최소로 유지할 수 있다. 형식이 더 늘면 B로 옮기는 비용도 작다.

### 2.1 Component Diagram

```
MessageBubble → MarkdownRenderer (a 렌더러)
                   │ previewKindOf(filename)
                   ├─ 'xlsx' ──► useExcelPreviewStore.open()   ──► ExcelPreviewModal (기존)
                   └─ 'docx'|'pdf' ► useDocumentPreviewStore.open() ► DocumentPreviewModal (신규)
                                                                    │ useGeneratedFileBlob(fileId)
                                                                    │   └─ documentExtractorService.fetchGeneratedFileBlob (기존)
                                                                    ├─ DocxPreviewView ─► lib/docxRenderer ─► import('docx-preview')
                                                                    └─ PdfPreviewView  ─► blob URL → <iframe>
ChatPage: <ExcelPreviewModal/> <DocumentPreviewModal/> 각 1회 마운트
```

### 2.2 Data Flow

```
[미리보기 클릭] → store.open({fileId, filename, kind})
  → Modal 마운트 → useQuery(fileBlob) → GET /api/v1/document-extractor/files/{id} (responseType blob, JWT)
     ├─ 실패(ApiError 404/403/기타) → previewErrorView → 문구 + 다운로드 버튼 노출 여부
     └─ 성공(Blob)
          ├─ kind=docx: size > DOCX_PREVIEW_MAX_BYTES → "너무 커서 미리볼 수 없음"(다운로드 노출)
          │            else → shadowRoot 생성 → renderDocx(blob, shadowRoot) → 링크 후처리
          │                    └─ 렌더 예외 → "미리보기를 만들 수 없습니다"(다운로드 노출)
          └─ kind=pdf : new Blob([blob], {type:'application/pdf'}) → createObjectURL → iframe
                        unmount 시 revokeObjectURL
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| DocumentPreviewModal | `useDocumentPreviewStore`, `useGeneratedFileBlob`, `previewErrorView`, `Modal`, `Button` | 상태·조회·오류·레이아웃 |
| DocxPreviewView | `lib/docxRenderer` | shadow DOM 렌더 |
| lib/docxRenderer | `docx-preview@0.4.1` (동적 import) | docx → DOM |
| PdfPreviewView | 브라우저 내장 PDF 뷰어 | iframe 표시 |
| ExcelPreviewModal | `previewErrorView` (내부 `errorView` 이관) | 오류 문구 공통화 |

신규 의존성: `docx-preview@0.4.1` (Apache-2.0, 2026-09-21 배포 확인), 의존 `jszip>=3` (MIT/GPLv3 이중 라이선스 → MIT 선택). 버전은 `^` 없이 고정한다.

---

## 3. Data Model

DB·백엔드 변경 없음. 프론트 타입만 추가한다.

### 3.1 Entity Definition

```typescript
// src/types/filePreview.ts (신규)
export type PreviewKind = 'xlsx' | 'docx' | 'pdf';
export type DocumentPreviewKind = Exclude<PreviewKind, 'xlsx'>;
export type FilePreviewTrigger = 'button' | 'link';

/** 진입 스위치 — 엑셀·문서 공통 (Plan FR-11). types/excelPreview.ts의 EXCEL_PREVIEW_TRIGGER를 이관 */
export const FILE_PREVIEW_TRIGGER: FilePreviewTrigger = 'button';

/** docx-preview 렌더 상한 — 초과 시 렌더 생략·다운로드 안내 (Plan §5 큰 파일 위험) */
export const DOCX_PREVIEW_MAX_BYTES = 10 * 1024 * 1024;

// src/store/documentPreviewStore.ts (신규)
export interface DocumentPreviewTarget {
  fileId: string;
  filename: string;
  kind: DocumentPreviewKind;
}
```

`types/excelPreview.ts`의 `ExcelPreviewTrigger`·`EXCEL_PREVIEW_TRIGGER`는 제거하고 `filePreview.ts`로 옮긴다(사용처는 MarkdownRenderer와 LinkMode 테스트뿐).

---

## 4. API Specification

신규·변경 API 없음. 사용하는 기존 엔드포인트:

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/api/v1/document-extractor/files/{file_id}` | 산출 파일 바이너리 (`.docx`·`.pdf` media type 등록됨, `document_extractor_router.py:134`) | JWT, 소유자만 |

오류: 404(없음·만료), 403(소유자 아님). `responseType: 'blob'`이어도 인터셉터가 `ApiError(status)`로 바꾸므로 `status`로 분기한다(본문 메시지는 Blob이라 쓰지 않는다).

---

## 5. UI/UX Design

### 5.1 Screen Layout

```
┌──────────────────────────────────────────── size=4xl, scroll=body ─┐
│ 보고서.docx                                                    [×] │
│ 다운로드 전 미리보기 — 원본과 일부 서식이 다를 수 있습니다           │
├────────────────────────────────────────────────────────────────────┤
│  ┌──────────── 회색 배경, 세로 스크롤 ───────────────┐              │
│  │   ┌── A4 페이지(흰색, docx-preview wrapper) ──┐  │              │
│  │   │  본문 · 표 · 머리글/바닥글                │  │              │
│  │   └──────────────────────────────────────────┘  │              │
│  └────────────────────────────────────────────────┘              │
│  (pdf: 같은 영역에 <iframe title="보고서.pdf 미리보기" h-[70vh]>)  │
├────────────────────────────────────────────────────────────────────┤
│                                     [다운로드]  [닫기]             │
└────────────────────────────────────────────────────────────────────┘
```

### 5.2 User Flow

채팅 답변 → `.docx`/`.pdf` 링크 옆 "미리보기" → 모달(로딩 → 본문) → "다운로드" 또는 "닫기"/ESC.
링크 자체 클릭은 `'button'` 모드에서 기존처럼 다운로드한다. `FILE_PREVIEW_TRIGGER='link'`로 바꾸면 링크 클릭이 미리보기를 연다(엑셀과 동일 규칙).

### 5.3 Component List

| Component | Location | Responsibility |
|-----------|----------|----------------|
| `DocumentPreviewModal` | `components/chat/DocumentPreviewModal.tsx` | target 구독, 조회·오류·크기 상한, 다운로드 버튼, kind별 뷰어 선택. target null이면 null, `key={fileId}` |
| `DocxPreviewView` | `components/chat/DocxPreviewView.tsx` | host div에 `attachShadow({mode:'open'})`, `renderDocx` 호출, 렌더 상태(rendering/done/error) 콜백 |
| `PdfPreviewView` | `components/chat/PdfPreviewView.tsx` | blob URL 생성·해제, iframe |
| `renderDocx` | `lib/docxRenderer.ts` | 동적 import, renderAsync 옵션, 링크 후처리 |
| `previewKindOf` | `utils/previewKind.ts` | 파일명 확장자(대소문자 무시) → `PreviewKind \| null` |
| `previewErrorView` | `utils/filePreviewError.ts` | ApiError → `{message, canDownload}` (엑셀 `errorView` 이관 + 문서용 문구) |
| `useGeneratedFileBlob` | `hooks/useGeneratedFileBlob.ts` | blob useQuery |
| `useDocumentPreviewStore` | `store/documentPreviewStore.ts` | `target`/`open`/`close` |

#### renderDocx 세부

```typescript
// lib/docxRenderer.ts
export const renderDocx = async (blob: Blob, root: ShadowRoot): Promise<void> => {
  const { renderAsync } = await import('docx-preview'); // 별도 청크 (Plan FR-04)
  const body = document.createElement('div');
  const styles = document.createElement('div');
  root.replaceChildren(styles, body);
  await renderAsync(blob, body, styles, {
    inWrapper: true,             // 회색 배경 + 페이지 카드
    breakPages: true,
    ignoreLastRenderedPageBreak: true,
    renderHeaders: true,
    renderFooters: true,
    renderFootnotes: true,
    renderEndnotes: true,
    useBase64URL: true,          // 이미지 blob URL 누수 방지
    renderAltChunks: false,      // 문서 안 HTML 조각(altChunk) 렌더 금지
    renderComments: false,       // 주석·변경 추적은 노출하지 않음
    renderChanges: false,
    experimental: false,
  });
  // Plan FR-09: 문서 내 링크는 새 창 + opener 차단, http(s)·mailto 외 href 제거
  body.querySelectorAll('a[href]').forEach((a) => {
    const href = a.getAttribute('href') ?? '';
    if (href.startsWith('#')) return;                 // 문서 내부 책갈피 유지
    if (!/^(https?:|mailto:)/i.test(href)) { a.removeAttribute('href'); return; }
    a.setAttribute('target', '_blank');
    a.setAttribute('rel', 'noopener noreferrer');
  });
};
```

shadowRoot 안에 docx-preview의 `<style>`이 들어가므로 앱 Tailwind와 문서 CSS가 서로 섞이지 않는다(Plan FR-08). 단 shadow DOM은 **상속 속성(font-family·line-height·color)은 막지 못한다**(Check 헤드리스 측정: 문단이 앱의 Pretendard·line-height 24px 상속). 그래서 root 첫 요소로 `:host { all: initial; display: block; font-family: 'Malgun Gothic', …; color: #000 }`를 넣어 상속을 끊고, 글꼴을 지정하지 않은 문서는 맑은 고딕으로 그린다. 호스트의 Tailwind 클래스(높이·스크롤·테두리)는 바깥 규칙이 `:host`보다 우선해 유지된다. 문서에 지정된 글꼴이 PC에 없으면 브라우저 대체 글꼴을 쓴다(한계).

추가 처리(Check G-02·G-04):
- `#책갈피` 링크: 대상 id가 shadow root 안에 있어 브라우저 해시 이동이 닿지 않으므로, 본문 클릭을 가로채 `root.getElementById(id).scrollIntoView()`로 이동하고 URL 해시는 바꾸지 않는다.
- `renderDocx(blob, root, isCancelled)`: StrictMode 이중 effect 등으로 취소된 렌더는 import 후·렌더 후 두 지점에서 멈추고 root를 건드리지 않는다.
- 라이브러리 한계: docx-preview가 단일 줄 간격을 `line-height: 100%`로 그려 표 칸 글자가 Word보다 빽빽하다.

#### useGeneratedFileBlob 캐시 정책

```typescript
useQuery({
  queryKey: queryKeys.generatedFile.blob(fileId ?? ''),
  queryFn: () => documentExtractorService.fetchGeneratedFileBlob(fileId as string),
  enabled: !!fileId,
  staleTime: 5 * 60_000,   // Plan FR-03: 다시 열면 캐시 사용
  gcTime: 5 * 60_000,      // blob 메모리 보유 상한
  retry: 4xx는 재시도 안 함, 그 외 1회 (useExcelPreview와 동일)
});
```

엑셀(staleTime 0)과 다른 이유: 엑셀은 서버 파싱 결과라 매번 다시 받아도 가볍지만, 문서는 파일 전체를 받으므로 같은 대화에서 다시 열 때 재다운로드를 피한다. 캐시 중 TTL이 지나 파일이 만료되면 미리보기는 보이지만 다운로드 버튼이 실패하며, 이 경우 엑셀 모달과 같은 `downloadError` 문구를 표시한다.

### 5.4 Page UI Checklist

#### 채팅 메시지 (MarkdownRenderer)

- [ ] `.docx` 산출 링크 옆 "미리보기" 버튼 (`aria-label="{filename} 미리보기"`)
- [ ] `.pdf` 산출 링크 옆 "미리보기" 버튼
- [ ] `.xlsx` 버튼은 기존 엑셀 스토어를 연다 (불변)
- [ ] 미리보기 대상이 아닌 산출 링크(예: `.hwp`, `.txt`)에는 버튼 없음
- [ ] 링크 클릭은 다운로드 (`'button'` 모드)

#### DocumentPreviewModal

- [ ] 제목: 파일명 / 부제: "다운로드 전 미리보기 — 원본과 일부 서식이 다를 수 있습니다"
- [ ] 로딩: 스피너 + "문서를 불러오는 중…" (조회 중과 docx 렌더 중 모두)
- [ ] docx: 페이지 카드 렌더, 세로 스크롤
- [ ] pdf: `<iframe title="{filename} 미리보기">` 높이 70vh
- [ ] 오류 문구(§6) + 다운로드 버튼 노출 규칙
- [ ] footer: [다운로드] (진행 중 "다운로드 중…") · [닫기], 다운로드 실패 시 `role=alert` 문구
- [ ] ESC·배경 클릭·닫기 버튼으로 닫힘 (기존 `Modal`)

---

## 6. Error Handling

### 6.1 Error Code Definition

`previewErrorView(error)`가 반환한다 (종류 인자는 필요 없어 Do에서 제외). 엑셀은 기존 문구를 그대로 받는다.

| 상황 | 판별 | 메시지 | 다운로드 버튼 |
|------|------|--------|:---:|
| 만료·없음 | `ApiError.status === 404` | 파일이 만료되었거나 찾을 수 없습니다. | 숨김 |
| 소유자 아님 | `status === 403` | 본인이 생성한 파일만 볼 수 있습니다. | 숨김 |
| 엑셀 미지원·손상 | `status === 415 \| 422` (엑셀만) | 미리보기를 만들 수 없습니다. 파일은 다운로드할 수 있습니다. | 표시 |
| docx 크기 초과 | `blob.size > DOCX_PREVIEW_MAX_BYTES` | 파일이 커서 미리볼 수 없습니다. 다운로드해서 확인해주세요. | 표시 |
| docx 렌더 실패 | `renderDocx` reject (손상·미지원 구조, 청크 로드 실패) | 미리보기를 만들 수 없습니다. 파일은 다운로드할 수 있습니다. | 표시 |
| 네트워크·기타 | 그 외 | 미리보기를 불러오지 못했습니다. 다시 시도해주세요. | 표시 |

렌더 실패는 `console.warn('[document-preview] render failed', err)`로만 남긴다(사용자 데이터 미포함).

### 6.2 Error Response Format

백엔드 형식 변경 없음. 인터셉터의 `ApiError(message, status, code)`만 사용한다(`err.response` 사용 금지 — 프로젝트 규칙).

---

## 7. Security Considerations

- [x] 인증·소유자 검증: 기존 다운로드 API 재사용, `authApiClient`(JWT)로만 조회. 프론트에서 권한 판단 없음.
- [ ] 스크립트 실행 없음: docx-preview는 docx XML을 DOM 노드로 만들며 스크립트를 실행하지 않는다. 추가로 렌더 후 `a[href]`의 스킴을 `http(s)`·`mailto`·`#`로 제한한다 (`javascript:` 차단).
- [ ] 노출 최소화: `renderAltChunks`·`renderComments`·`renderChanges`는 false.
- [ ] 외부 리소스: `useBase64URL: true`로 내장 이미지만 data URL로 그린다. 외부 링크 이미지(`TargetMode="External"`)는 docx-preview가 불러오지 않음을 Do 단계에서 실파일로 확인한다.
- [ ] 스타일 격리: shadow DOM (FR-08).
- [ ] PDF: 같은 출처 blob URL을 iframe에 넣는다. 배포 설정에 CSP·`X-Frame-Options` 헤더가 없음을 확인했다(`deploy/` 검색 결과 0건). 이후 CSP를 넣을 때는 `frame-src blob:` 허용이 필요하다는 점을 E2E 이월 체크리스트에 남긴다.
- [ ] blob URL 해제: PdfPreviewView unmount 시 `revokeObjectURL`.

---

## 8. Test Plan

### 8.1 Test Scope

| Type | Target | Tool | Phase |
|------|--------|------|-------|
| Unit | `previewKindOf`, `previewErrorView`, `documentPreviewStore` | Vitest | Do |
| Hook | `useGeneratedFileBlob` enabled·retry | Vitest + MSW | Do |
| Component | `DocumentPreviewModal`, `PdfPreviewView`, `DocxPreviewView`(renderDocx mock) | RTL | Do |
| Integration | MarkdownRenderer 버튼 노출·스토어 분기 | RTL | Do |
| Lib | `renderDocx` 링크 후처리 (`docx-preview` vi.mock) | Vitest | Do |
| 화면 확인 | 실제 산출 docx/pdf | 브라우저 | Check |

L1(API) 시나리오는 없다(백엔드 무변경).

### 8.2 L2: UI Action Test Scenarios (Vitest + RTL)

| # | Target | Action | Expected |
|---|--------|--------|----------|
| 1 | MarkdownRenderer | `.docx` 링크 렌더 | "보고서.docx 미리보기" 버튼 존재 |
| 2 | MarkdownRenderer | `.pdf` 버튼 클릭 | documentPreviewStore.target = {kind:'pdf'}, 다운로드 미호출 |
| 3 | MarkdownRenderer | `.xlsx` 버튼 클릭 | excelPreviewStore만 열림, document 스토어 null |
| 4 | MarkdownRenderer | `.hwp` 링크 | 버튼 없음, 클릭 시 다운로드 |
| 5 | MarkdownRenderer (link 모드 mock) | `.docx` 링크 클릭 | 미리보기 열림, 다운로드 미호출 |
| 6 | DocumentPreviewModal | target null | 아무것도 렌더 안 함 |
| 7 | DocumentPreviewModal | MSW 404 | 만료 문구, 다운로드 버튼 없음 |
| 8 | DocumentPreviewModal | MSW 403 | 소유자 문구, 다운로드 버튼 없음 |
| 9 | DocumentPreviewModal | MSW 500 | 기타 문구, 다운로드 버튼 있음 |
| 10 | DocumentPreviewModal (docx) | 성공 + renderDocx mock resolve | renderDocx가 Blob·ShadowRoot로 1회 호출, 로딩 사라짐 |
| 11 | DocumentPreviewModal (docx) | renderDocx reject | 렌더 실패 문구, 다운로드 버튼 있음 |
| 12 | DocumentPreviewModal (docx) | blob 크기 > 상한 | 크기 초과 문구, renderDocx 미호출 |
| 13 | PdfPreviewView | 렌더 후 unmount | iframe src=blob URL, unmount 시 revokeObjectURL 호출 |
| 14 | DocumentPreviewModal | 다운로드 클릭 | `downloadGeneratedFile(fileId, filename)` 호출, 실패 시 alert 문구 |
| 15 | renderDocx | `javascript:`·`https:`·`#` 링크 포함 DOM | href 제거 / target·rel 부여 / 유지 |
| 16 | ExcelPreviewModal (기존 테스트) | 전부 | 무수정 통과 (오류 매핑 이관 회귀 확인) |

jsdom의 `URL.createObjectURL`·`revokeObjectURL`은 없으므로 테스트에서 `vi.stubGlobal`로 대체한다. `attachShadow`는 jsdom이 지원한다.

### 8.3 L3: 화면 확인 시나리오

| # | Scenario | Steps | Success Criteria |
|---|----------|-------|-----------------|
| 1 | 문서추출기 docx | 양식 채우기 에이전트 실행 → 미리보기 | 표·칸 값이 보이고 앱 화면 스타일이 깨지지 않음 |
| 2 | 문서생성기 docx/pdf | 생성 에이전트 실행(docx·pdf 각 1회) → 미리보기 | 본문 표시, pdf는 내장 뷰어 |
| 3 | 만료 | 파일 삭제 후 미리보기 | 만료 문구 |
| 4 | 번들 | `vite build` | `docx-preview`·`jszip`이 별도 청크, 메인 청크 증가 ≤ 5KB |

### 8.4 Seed Data Requirements

MSW 핸들러: `http.get('*' + DOCUMENT_EXTRACTOR_FILE(':fileId'))` → `new HttpResponse(new Uint8Array([...]), {headers:{'Content-Type': ...}})` (기존 `documentExtractorService.test.ts` 패턴). 크기 초과는 `Object.defineProperty(blob,'size')` 대신 서비스 mock으로 큰 Blob을 반환한다.

---

## 9. Clean Architecture

### 9.4 This Feature's Layer Assignment

| Component | Layer | Location |
|-----------|-------|----------|
| DocumentPreviewModal, DocxPreviewView, PdfPreviewView | Presentation | `src/components/chat/` |
| useGeneratedFileBlob | Application (hook) | `src/hooks/` |
| documentPreviewStore | Application (state) | `src/store/` |
| PreviewKind, FILE_PREVIEW_TRIGGER, DOCX_PREVIEW_MAX_BYTES | Domain (types) | `src/types/filePreview.ts` |
| previewKindOf, previewErrorView | Utils | `src/utils/` |
| renderDocx | Infrastructure (라이브러리 어댑터) | `src/lib/docxRenderer.ts` |
| fetchGeneratedFileBlob (기존) | Infrastructure | `src/services/documentExtractorService.ts` |

---

## 10. Coding Convention Reference

### 10.4 This Feature's Conventions

| Item | Convention Applied |
|------|-------------------|
| 런타임 상수 | 컴포넌트 파일 export 금지 → `types/filePreview.ts` |
| 오류 판별 | `ApiError.status` (인터셉터), `err.response` 금지 |
| queryKey | `queryKeys.generatedFile.blob(fileId)` 추가 (`lib/queryKeys.ts`) |
| 동적 import | `lib/docxRenderer.ts` 내부 `await import('docx-preview')` 1곳 |
| Design 추적 주석 | 파일 머리 `// Design Ref: document-file-preview §x` |
| 린트 | exhaustive-deps 억제 주석 금지 (React Compiler 린트 함정) → `useCallback`+deps |

---

## 11. Implementation Guide

### 11.1 File Structure

```
idt_front/
├── package.json                                (+ docx-preview 0.4.1 고정)
└── src/
    ├── types/filePreview.ts                    신규
    ├── types/excelPreview.ts                   수정 (트리거 상수 제거)
    ├── utils/previewKind.ts (+ .test.ts)       신규
    ├── utils/filePreviewError.ts (+ .test.ts)  신규
    ├── lib/docxRenderer.ts (+ .test.ts)        신규
    ├── lib/queryKeys.ts                        수정 (generatedFile)
    ├── store/documentPreviewStore.ts           신규
    ├── hooks/useGeneratedFileBlob.ts (+ .test.ts) 신규
    ├── components/chat/
    │   ├── DocumentPreviewModal.tsx (+ .test.tsx)  신규
    │   ├── DocxPreviewView.tsx                     신규
    │   ├── PdfPreviewView.tsx (+ .test.tsx)        신규
    │   ├── ExcelPreviewModal.tsx                   수정 (errorView → previewErrorView)
    │   ├── MarkdownRenderer.tsx                    수정 (previewKindOf 분기)
    │   ├── MarkdownRendererExcelPreview.test.tsx   수정 (pdf "버튼 없음" → .hwp)
    │   ├── MarkdownRendererExcelPreviewLinkMode.test.tsx 수정 (mock 경로 filePreview, pdf → .hwp)
    │   └── MarkdownRendererDocumentPreview.test.tsx 신규 (#1~5)
    └── pages/ChatPage/index.tsx                수정 (<DocumentPreviewModal/> 마운트)
```

### 11.2 Implementation Order

1. [ ] `npm i docx-preview@0.4.1 -E`, 라이선스 확인
2. [ ] types/filePreview + previewKindOf + previewErrorView (테스트 먼저)
3. [ ] ExcelPreviewModal 오류 매핑 이관 → 엑셀 테스트 무수정 통과 확인
4. [ ] MarkdownRenderer 분기 + documentPreviewStore + 기존 테스트 2종 수정 + 신규 테스트
5. [ ] useGeneratedFileBlob + queryKeys
6. [ ] lib/docxRenderer (링크 후처리 테스트)
7. [ ] PdfPreviewView, DocxPreviewView, DocumentPreviewModal + ChatPage 마운트
8. [ ] 관련 테스트 묶음·린트·`tsc`·`vite build` 청크 확인 → 화면 확인

### 11.3 Session Guide

#### Module Map

| Module | Scope Key | Description | Estimated Turns |
|--------|-----------|-------------|:---------------:|
| 공통 기반·진입점 | `module-1` | 의존성, types/utils, 엑셀 오류 이관, MarkdownRenderer 분기·스토어, 기존 테스트 수정 (순서 1~4) | 15~20 |
| 뷰어·모달 | `module-2` | 훅, docxRenderer, Pdf/Docx 뷰어, DocumentPreviewModal, ChatPage 마운트 (순서 5~7) | 20~25 |
| 검증 | `module-3` | 회귀·린트·빌드 청크·실파일 화면 확인 (순서 8) | 10 |

#### Recommended Session Plan

| Session | Phase | Scope | Turns |
|---------|-------|-------|:-----:|
| Session 1 | Do | `--scope module-1` | 15~20 |
| Session 2 | Do | `--scope module-2,module-3` | 30~35 |
| Session 3 | Check + Report | 전체 | 20~30 |

규모가 작아 한 세션(`/pdca do document-file-preview`)에 끝내도 된다.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-11-16 | Initial draft (Option C, Shadow DOM) | 배상규 |
| 0.2 | 2026-11-16 | Check 반영: 상속 속성 초기화(:host), 책갈피 이동, 취소 인자, 추가 렌더 옵션, previewErrorView 시그니처 | 배상규 |
