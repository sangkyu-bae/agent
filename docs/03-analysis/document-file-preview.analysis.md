# document-file-preview Analysis Report

> **Analysis Type**: Gap Analysis (Design vs Implementation) + Runtime Verification
>
> **Project**: sangplusbot (Agent Builder)
> **Analyst**: 배상규 (gap-detector 정적 분석 + 헤드리스 브라우저 확인)
> **Date**: 2026-11-16
> **Design Doc**: [document-file-preview.design.md](../02-design/features/document-file-preview.design.md)
> **Implementation**: worktree `wt/document-file-preview`, 브랜치 `feature/document-file-preview` (미커밋)

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

## Strategic Alignment Check

### PRD Alignment

PRD 없음. Plan의 WHY(다운로드 없이 확인, 형식 간 경험 통일)를 기준으로 본다. 구현은 .docx/.pdf에 엑셀과 같은 버튼·모달 진입점을 제공하고, 진입 스위치를 세 형식 공통으로 묶었다 → 문제 해결 방향 일치.

### Success Criteria Status

| Plan §4 기준 | 상태 | 근거 |
|------|:-:|------|
| .docx 미리보기 → 본문·표 표시 | ✅ Met | 헤드리스 렌더: 합성 docx(머리글·표·2쪽) `section.docx` 2개, 실제 양식 docx(여신심의서) 표 3개 정상 표시 |
| .pdf 미리보기 → iframe 표시 | ⚠️ Partial | 단위 테스트(`PdfPreviewView.test.tsx`, 모달 pdf 케이스) 통과. 헤드리스 Chromium은 내장 PDF 뷰어가 없어 화면 확인 불가 → 실브라우저 확인 이월 |
| .xlsx 동작 불변 | ✅ Met | `ExcelPreviewModal*.test` 무수정 18건 통과, 오류 문구 master와 동일 |
| 404/403/손상 파일 문구 | ✅ Met | 단위 테스트 + 헤드리스: 깨진 파일 → "미리보기를 만들 수 없습니다…" + 다운로드 버튼 |
| docx-preview 별도 청크 | ✅ Met | `vite build`: `docx-preview-*.js` 171.71KB 별도, 메인 청크 +3.6KB(gzip +1.2KB) |
| 새 테스트 통과·회귀 없음 | ✅ Met | chat 133 / ChatPage 27 / hooks·utils·lib·store·services 641 전부 통과 |
| ESLint 0 · tsc 신규 0 · build 성공 | ✅ Met | 변경 파일 lint error 0(ChatPage 기존 warning 2), tsc 211건으로 master와 동일 목록 |

**7개 중 6 Met, 1 Partial.**

### Decision Record Verification

| 결정 | 준수 | 결과 |
|------|:-:|------|
| [Plan] 브라우저 렌더(docx-preview + PDF iframe), 백엔드 무변경 | ✅ | 백엔드 diff 0 |
| [Design] Option C — 문서 전용 스토어·모달, 공통은 오류 매핑·스위치만 | ✅ | 엑셀 모달 변경은 import·함수명 2줄 |
| [Design] Shadow DOM 스타일 격리 | ✅ (규칙) / ⚠️ (상속) | 문서 `<style>` 4개는 shadow 안, 앱 제목 스타일 불변. 단 상속 속성은 넘어감(G-01) |
| [Design] button 진입·10MB 상한·5분 캐시 | ✅ | `types/filePreview.ts`, `useGeneratedFileBlob.ts` |

---

## 1. Analysis Overview

- **목적**: Design 대비 구현 일치도와 실제 렌더 동작 확인
- **범위**: `idt_front/src` 신규 9 + 수정 8 파일 (worktree), 백엔드 변경 없음
- **방법**: gap-detector 정적 분석(구조·기능·계약), 자동 검증(vitest·eslint·tsc·vite build), 헤드리스 Chromium(Playwright)으로 임시 하네스 페이지에서 `DocumentPreviewModal` 실렌더 — 파일 API는 Playwright route로 docx 응답 주입

---

## 2. Gap Analysis

### 2.1 API Endpoints

| Method | Path | 사용처 | Status |
|--------|------|--------|:-:|
| GET | `/api/v1/document-extractor/files/{id}` | `documentExtractorService.fetchGeneratedFileBlob` (기존) | ✅ |

### 2.2 Data Model

신규 타입 `PreviewKind`·`DocumentPreviewKind`·`FilePreviewTrigger`·`DocumentPreviewTarget`, 상수 `FILE_PREVIEW_TRIGGER`·`DOCX_PREVIEW_MAX_BYTES` 모두 Design §3.1과 일치. `EXCEL_PREVIEW_TRIGGER` 잔존 참조 0.

### 2.3 Component Structure

Design §5.3의 8개 구성요소 전부 존재. ChatPage 1회 마운트(`pages/ChatPage/index.tsx:532`).

### 2.4 Functional Depth

FR-01~11 전부 구현(gap-detector 표 기준). placeholder·TODO·eslint-disable 없음. 엣지: StrictMode 이중 effect(`shadowRoot ?? attachShadow` + cancelled 플래그), fileId 전환(`key`), 렌더 중 호스트 숨김 + 스피너.

### 2.5 Page UI Checklist

§5.4 채팅 메시지 5항목 · 모달 8항목 전부 확인. 헤드리스 화면에서 제목·부제·페이지 카드·다운로드/닫기 버튼 확인.

### 2.6 API Contract

`authApiClient` Bearer + blob 응답, 오류는 `ApiError.status`만 분기 — 100%.

### 2.7 Runtime Verification Results

L1(API): 해당 없음(백엔드 무변경).

L2(UI Action, Vitest + RTL): Design §8.2 16개 중 15개 테스트 존재·통과, #16(엑셀 회귀)은 기존 테스트 무수정 통과로 충족.

L3(헤드리스 브라우저):

| # | 시나리오 | 결과 |
|---|---------|:-:|
| 1 | 합성 docx (머리글·바닥글·제목·굵게·크기·표 4×3·쪽 나눔·https/javascript 링크) | ✅ 2쪽 렌더, https 링크 `target=_blank rel=noopener noreferrer`, javascript 링크 href 제거 |
| 2 | 실제 양식 docx (`idt/uploads/document_templates/` 중 1건, 로컬에서만) | ✅ 제목·표 3개·본문 표시 |
| 3 | 깨진 파일 (`not a zip`) | ✅ 렌더 실패 문구 + 다운로드 버튼, `console.warn` 1회 |
| 4 | 스타일 누수 (모달 밖 앱 제목) | ✅ 렌더 전후 color·font-size 동일, document head `<style>` 수 불변(문서 스타일 4개는 shadow 안) |
| 5 | 상속 속성 | ⚠️ shadow 안 문단이 앱의 `Pretendard`·`line-height 24px` 상속 (G-01) |
| 6 | PDF | ⏸ 헤드리스 Chromium 내장 뷰어 없음 — 실브라우저 확인 이월 |
| 7 | 외부 링크 이미지 미로딩 (Design §7) | ⏸ 테스트 문서에 외부 이미지 없음 — 미확인 |

참고: 표 칸 글자가 위 테두리에 붙어 보이는 것은 docx-preview가 문단에 `line-height: 100%`를 직접 지정하기 때문이며(초기화 후에도 동일), 라이브러리 표현 한계로 분류한다.

### 2.8 Match Rate Summary

```
Structural 100% × 0.15 = 15.0
Functional  95% × 0.25 = 23.75
Contract   100% × 0.25 = 25.0
Runtime     90% × 0.35 = 31.5   (L2 전부 통과, L3 7개 중 5 통과·PDF/외부 이미지 미확인)
─────────────────────────────
Overall                 = 95.3%   (정적만: 98%)
```

---

## 3. Gap List

| ID | 심각도 | 위치 | 내용 | 제안 |
|----|------|------|------|------|
| G-01 | Important | Design §5.3 마지막 문단, `lib/docxRenderer.ts` | Design은 "앱 폰트가 문서에 상속되지 않는다"고 했지만, 실제로는 font-family·line-height·color가 shadow 경계를 넘어 상속된다(헤드리스 측정: 문단 `Pretendard`). `:host{all:initial;display:block}`로 끊으면 docx에 글꼴 지정이 없는 경우 브라우저 기본(Times New Roman)으로 바뀐다 | (a) 상속 유지 + Design 문구 정정, 또는 (b) `:host` 초기화 + 기본 글꼴을 `'Malgun Gothic', sans-serif`로 지정 |
| G-02 | Minor | `lib/docxRenderer.ts:38` | `#책갈피` 링크는 shadow root 안 id를 찾지 못해 채팅 URL에 해시만 붙고 이동하지 않는다 | root 안에서 클릭 가로채 `root.getElementById(id)?.scrollIntoView()`, 또는 href 제거 |
| G-03 | Minor | `services/documentExtractorService.test.ts:36` | blob 응답 404가 `ApiError.status=404`로 오는지 직접 단언하는 테스트가 없음(`rejects.toBeTruthy()`만) | `rejects.toMatchObject({ status: 404 })` + 403 케이스 |
| G-04 | Minor | `components/chat/DocxPreviewView.tsx`, `lib/docxRenderer.ts` | StrictMode 첫 실행이 취소된 뒤에도 import 완료 후 `replaceChildren`을 호출한다. import 순서 덕에 결과는 맞음 | `renderDocx`에 취소 확인 인자 전달 |
| G-05 | Minor | `idt_front/__check.html`, `src/__check/` | 화면 확인용 임시 하네스가 worktree에 있음 | 커밋 전 삭제 |
| G-06 | Minor | Design §6.1 | 시그니처 `previewErrorView(error, kind)` → 실제 `previewErrorView(error)` | Design 정정 |
| G-07 | Minor | Design §5.3·§7 | 추가 옵션 `renderEndnotes`·`renderAltChunks:false`·`renderComments:false`·`renderChanges:false` 미기재 | Design 반영 |
| G-08 | Minor | Plan FR-07 | "기타 오류" 문구가 Design §6.1·코드와 다름 | Plan 정정 |
| G-09 | Minor | Design §8.1 | `documentPreviewStore` 직접 단위 테스트 없음(MarkdownRenderer 테스트로만 검증) | 작은 open/close 테스트 추가 또는 §8.1 정정 |
| G-10 | Minor | `DocumentPreviewModal.test.tsx` 500 케이스 | 실제 재시도 지연(약 1초)을 기다림 | `retryDelay` 0 주입 또는 fake timer |

Critical 없음.

---

## 4. Security

- 인증은 기존 다운로드 API·`authApiClient` 그대로. 프론트 권한 판단 없음.
- 문서 링크: `javascript:`·`file:` href 제거를 단위·헤드리스 양쪽에서 확인.
- altChunk(문서 안 HTML 조각)·주석·변경 추적 렌더 끔.
- 외부 이미지 미로딩은 미확인(이월).

## 5. Test Coverage

신규 테스트 7파일(+기존 2파일 수정), Design §8.2 16개 시나리오 중 16개 충족. 미커버: store 직접 테스트(G-09), blob 404 → ApiError 경로(G-03).

## 6. Convention Compliance

- 런타임 상수는 `types/filePreview.ts` (컴포넌트 파일 export 없음) ✅
- `ApiError.status` 분기, `err.response` 미사용 ✅
- exhaustive-deps 억제 주석 없음, effect 내 동기 setState 없음 ✅
- `npm i` 시 `--legacy-peer-deps` (idt_front/CLAUDE.md:342) ✅

---

## 6.5 Act-1 결과 (2026-11-16)

사용자 결정: "G-01 + 작은 보강 수정".

| ID | 조치 | 검증 |
|----|------|------|
| G-01 | `renderDocx`가 root 첫 요소로 `:host { all: initial; display: block; font-family: 'Malgun Gothic', …; color: #000 }` 삽입 | 단위 테스트 + 헤드리스 재측정: host·td `line-height: normal`, 글꼴 맑은 고딕, 앱 제목 스타일 불변, 호스트 테두리·높이 유지 |
| G-02 | 본문 클릭 가로채 `#책갈피`를 root 안에서 `scrollIntoView`, 기본 동작 차단 | 단위 테스트 |
| G-03 | blob 404·403이 `ApiError.status`로 오는지 단언 (MSW 실경로) | 기존 서비스 테스트 강화, 403 케이스 추가 |
| G-04 | `renderDocx(blob, root, isCancelled)` — import 후·렌더 후 취소 확인 | 단위 테스트 2건 |
| G-05 | 임시 하네스 삭제, vite 종료 | `git status`에 없음 |
| G-06·07 | Design §5.3·§6.1·§7 정정 (v0.2) | 문서 |
| G-08 | Plan FR-07 문구 정정 (v0.2) | 문서 |
| G-09 | `documentPreviewStore.test.ts` 추가 (3건) | 통과 |
| G-10 | 모달 테스트 QueryClient `retryDelay: 0` | 500 케이스 지연 없음 |

재검증: chat 133 / ChatPage 27 / hooks·utils·lib·store·services 649 통과, 변경 26파일 lint error 0(ChatPage 기존 warning 2), tsc 211건 master와 동일, build 정상(docx-preview 별도 청크, 메인 +4.1KB raw).

```
Act-1 후: Structural 100 × 0.15 + Functional 100 × 0.25 + Contract 100 × 0.25 + Runtime 90 × 0.35 = 96.5%
(Runtime 감점은 PDF 실브라우저·외부 이미지 미확인 — 이월 항목)
```

## 7. 이월 항목

- PDF 실브라우저 확인 (Chrome·Edge, 가능하면 모바일 Safari)
- 외부 링크 이미지를 가진 docx로 미로딩 확인
- 실제 백엔드에서 문서추출기·문서생성기 실행 후 채팅 화면 버튼 → 모달 흐름

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-11-16 | 초기 분석 (정적 98%, 런타임 포함 95.3%) | 배상규 |
| 0.2 | 2026-11-16 | Act-1 반영 (G-01~G-10 처리, 96.5%) | 배상규 |
