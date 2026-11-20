# source-passage-viewer Completion Report

> **Feature**: 근거 칩 → 원문 구절 음영 뷰어
> **Branch**: `feat/source-passage-viewer` (worktree `wt/source-passage-viewer`), 219ba17 … dd6b128 (8 commits, master aae4565 기준)
> **Final Match Rate**: 97.2% (Check 94.8% → Act-1)

---

## Executive Summary

### 1.1 Project Overview

| Item | Content |
|------|---------|
| Feature | source-passage-viewer |
| Start Date | 2026-11-19 |
| End Date | 2026-11-20 |
| Duration | 2일 (Plan → Design → Do 7모듈 → Check → Act-1) |

### 1.2 Results Summary

- 성공 기준 **9/9 충족** (Check 시점 8/9, Act-1 로 SC-4 보완)
- 실제 공개 PDF(7쪽)를 pdf.js 텍스트 레이어로 렌더해 잰 음영 매칭률: 수정 전 child 청크 **29%** → 정규화 규칙 수정 후 **100%**(child 17/17, parent 7/7)
- Claude(sonnet-4-6) 라이브 실행에서 화면 질문 → 답변 칩 "원문 보기" → 원본 PDF 음영까지 확인, 구절 5/5 표시
- 회귀: 백엔드 전체 신규 실패 0, 프론트 전체 2,040건 중 실패 10건 = 기존 상시 실패와 동일

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | 근거 칩이 파일명과 청크 앞부분만 보여 줘, 답변의 근거가 원문 어디에 있는지 확인할 수 없었다. 원본 파일도 보관하지 않았다. |
| **Solution** | 업로드 시 pdf·docx 원본을 로컬 디스크에 보관하고, 근거 칩에 문서·KB·인용 구절 정보를 실었다. 채팅 화면 오른쪽 패널에서 원본(PDF·docx) 또는 저장 청크로 다시 만든 텍스트 위에 인용 구절을 음영으로 표시한다. |
| **Function/UX Effect** | 칩의 "원문 보기" → 패널이 열리며 첫 구절로 이동, 구절 n/N 이동, 텍스트↔원본 전환. 실제 문서 기준 매칭률 100%, 위치를 못 찾으면 발췌와 [텍스트로 보기]로 대체. 원본이 없는 기존 문서는 텍스트 뷰어로 열린다. |
| **Core Value** | 금융·정책 문서 답변을 원문과 바로 대조할 수 있다. 에이전트 소유자(P2)는 검색이 맞는 구절을 가져왔는지 확인하고 KB 를 고칠 근거를 얻는다. 기능은 환경변수 하나로 없던 상태가 되고, DB 변경이 없다. |

## 1.4 Success Criteria Final Status

| # | Criteria | Status | Evidence |
|---|---------|:------:|----------|
| SC-1 | 원본 보관 on + PDF 업로드 → 칩 클릭 시 원본 PDF·음영 | ✅ Met | Claude 라이브 화면 확인(Design §12.1) |
| SC-2 | 원본 없는 문서 → 텍스트 뷰어 음영 | ✅ Met | `SourceViewerPanelOriginal.test.tsx`(null·404 → 텍스트), 라이브 텍스트 모드 |
| SC-3 | 다중 구절 음영·이동 | ✅ Met | 라이브 5구절 5/5(M21 수정 후) |
| SC-4 | 매칭 실패 안내·텍스트 전환 | ✅ Met | Act-1 `MissingPassageNotice`, Pdf·Docx 뷰어 테스트 |
| SC-5 | 권한 403, 없는 문서 404 | ✅ Met | `test_source_viewer_router.py`, 스모크(무토큰 401·없는 KB 404) |
| SC-6 | 경로·스위치 off → 기존 동작 | ✅ Met | `test_source_viewer_di.py`, 스모크 off, 전체 회귀 |
| SC-7 | 문서 삭제 → 원본 제거 | ✅ Met | 라이브 2회 파일 존재 전후 확인 |
| SC-8 | 재진입 시 같은 칩·구절 | ✅ Met | 세션 근거 API 3개 세션 viewer 포함 |
| DoD | 테스트 먼저 | ✅ Met | 모듈마다 Red 확인 후 구현 |

**Overall Success Rate: 9/9**

## 1.5 Decision Record Summary

| Source | Decision | Followed? | Outcome |
|--------|----------|:---------:|---------|
| [Plan] | 텍스트 뷰어 + 원본 뷰어 함께, 기존 문서 재업로드 없음 | ✅ | 원본 없는 문서는 텍스트 뷰어로 자연스럽게 대체 |
| [Plan] | 원본은 로컬 디스크, 경로는 환경변수 | ✅ | `DOCUMENT_ORIGINAL_STORAGE_DIR`, 포트로 분리해 교체 가능 |
| [Plan] | 음영 단위 = 검색 청크 전체, 칩은 파일당 1개 | ✅ | 겹치는 청크 처리(M21)가 필요했다 |
| [Plan] | 오른쪽 사이드 패널 | ✅ | 채팅 위 겹쳐 띄움(사용자 결정) — ChatPage 연결 1줄 |
| [Design] | C안 탈착형, 킬스위치 기본 off | ✅ | off = 라우트·칩 키·원본 보관 모두 없음(스모크 확인) |
| [Design] | DB 마이그레이션 없음 | ✅ | 원본 존재 여부는 `document_id` 저장 키로 판정 |
| [Design] | 정규화 매칭 + 단계적 대체(완전일치 금지) | ✅ | 실측으로 규칙을 2번 고쳐 100% 달성(M18·M19) |
| [Design] | 조립 위치 `main.py` | 변경 | `source_viewer_di.py` 로 이동(M7) — main.py 연결이 import·wire·주입 4곳으로 줄었다 |

## 2. Related Documents

| Phase | Document | Status |
|-------|----------|--------|
| Plan | [source-passage-viewer.plan.md](../01-plan/features/source-passage-viewer.plan.md) | ✅ Finalized |
| Design | [source-passage-viewer.design.md](../02-design/features/source-passage-viewer.design.md) (§12 M1–M26) | ✅ Finalized |
| Check | [source-passage-viewer.analysis.md](../03-analysis/source-passage-viewer.analysis.md) | ✅ Complete |
| Report | Current document | ✅ |

## 3. Completed Items

### 3.1 Functional Requirements

| ID | Requirement | Status | Notes |
|----|-------------|--------|-------|
| FR-01 | KB 업로드 원본 보관 | ✅ | 메타데이터 컬럼 대신 저장 키(M2·§1.3) |
| FR-02 | 경로 미설정 = 보관 off | ✅ | |
| FR-03 | 저장 실패가 업로드를 막지 않음 | ✅ | 두 겹 흡수 |
| FR-04 | 문서 삭제 시 원본 삭제 | ✅ | `_notify_deleted` 한 지점 |
| FR-05 | 칩 viewer(document_id·kb_id·original·passages) | ✅ | `viewer` 객체 1개로 묶음 |
| FR-06 | 실시간·재진입 같은 정책 | ✅ | `RunSourcesService` 단일 경로 |
| FR-07 | 원본 API 권한·inline | ✅ | 검사 순서 권한→형식→원본(M8) |
| FR-08 | 칩 클릭 → 패널, 원본 우선 | ✅ | |
| FR-09 | 텍스트 뷰어 | ✅ | Qdrant 비면 ES 대체(M17) |
| FR-10 | PDF 뷰어 음영 | ✅ | pdf.js 6 텍스트 레이어 |
| FR-11 | docx 뷰어 음영 | ✅ | 기존 shadow DOM 렌더러 재사용 |
| FR-12 | 매칭 실패 안내·발췌·전환 | ✅ | Act-1 |
| FR-13 | 구절 n/N 이동 | ✅ | |
| FR-14 | 웹·위키·MCP 칩 기존 동작 | ✅ | |

### 3.2 Non-Functional Requirements

| Item | Target | Achieved | Status |
|------|--------|----------|:------:|
| 권한 | KB 읽기 권한 재사용, 경로 조작 차단 | `KbDocumentGuard` + UUID 저장 키 + 루트 밖 경로 거부 | ✅ |
| 렌더 격리 | docx shadow DOM, pdf 스크립트 미실행 | 기존 렌더러 재사용, `enableXfa: false` | ✅ |
| 번들 | 뷰어 라이브러리 초기 번들 제외 | 패널 12.7KB·pdf.js 445KB·워커 1.27MB 모두 별도 청크 | ✅ |
| 큰 PDF | 현재 쪽 주변만 렌더 | 구절 쪽 ±1, 쪽 메타 없으면 앞 10쪽 | ✅ |
| 호환 | 기존 칩 소비자 무변경 동작 | 선택 필드, 기존 SourceCitation 테스트 통과 | ✅ |

### 3.3 Deliverables

| Deliverable | Location |
|-------------|----------|
| 백엔드 도메인·응용·인프라 | `idt/src/{domain,application,infrastructure}/source_viewer/` |
| 조립·라우터 | `idt/src/api/source_viewer_di.py`, `idt/src/api/routes/source_viewer_router.py` |
| 프론트 컴포넌트 | `idt_front/src/components/sourceViewer/` (Mount·Panel·Shell·Body·Boundary·Text/Pdf/Docx/Original 뷰어·MissingPassageNotice·Button) |
| 매칭·렌더 유틸 | `idt_front/src/utils/{passageMatch,buildPassageDocument,domHighlight}.ts`, `idt_front/src/lib/{pdfRenderer.ts,pdfTextLayer.css}` |
| 테스트 | 백엔드·프론트 신규 테스트 파일 28개 |
| 문서 | Plan·Design(§12 구현 메모·§12.1 실측)·Analysis·본 보고서 |
| 설정 | `.env.example` `SOURCE_VIEWER_ENABLED`, `DOCUMENT_ORIGINAL_STORAGE_DIR` |

## 4. Incomplete Items

### 4.1 Carried Over

| Item | Reason | Priority |
|------|--------|:--------:|
| 임베딩(Qdrant) 검색 결과의 칩 라이브 확인 | 로컬 OpenAI 크레딧 소진 — BM25 경로로만 확인 | High |
| 모바일 폭 화면 확인 | 이번 사이클 미실시 | Medium |
| 원본 뷰어 매칭 범위를 구절 쪽 ±1 로 좁히기(M24) | 실측 문서는 child `page` 메타가 비어 있음 | Low |
| 컬렉션 전체 삭제 시 원본 고아(M26) | 문서별 삭제 훅을 거치지 않음 — 정리 잡 도입 시 함께 | Low |
| 청킹이 한글을 바이트 중간에서 자르는 결함(U+FFFD) | 기존 청킹 결함, 매칭은 M19 로 흡수 | Medium (별도 사이클) |

### 4.2 Cancelled/On Hold

| Item | Reason | Alternative |
|------|--------|-------------|
| HWP·xlsx 원본 렌더 | Plan 범위 밖 | 텍스트 뷰어 |
| 답변 문장 단위 강조 | Plan 범위 밖 | 검색 청크 단위 |

## 5. Quality Metrics

### 5.1 Final Analysis Results

| Metric | Target | Final |
|--------|--------|-------|
| Match Rate | ≥ 90% | 97.2% (Structural 99 · Functional 97 · Contract 98 · Runtime 96) |
| 실문서 매칭률 | 측정 | child 17/17 · parent 7/7 · 라이브 5/5 |
| 백엔드 회귀 | 신규 실패 0 | 0 (전체 60건 = 상시 54 + worktree samples 부재 6) |
| 프론트 회귀 | 신규 실패 0 | 0 (2,040건 중 상시 10건/5파일) |
| 변경 파일 린트·타입 | 0 | 0 |

### 5.2 Resolved Issues (실측·Check 에서 찾아 고친 것)

| Issue | 발견 경로 | Resolution |
|-------|-----------|------------|
| 매칭률 29% — 줄끝 하이픈만 지우는 규칙이 추출기별 줄바꿈 차이로 비대칭 | 실제 PDF + pdf.js 측정 | 하이픈 계열 위치 무관 제거(M18) |
| 청크 속 U+FFFD 가 매칭을 깸 | 같은 측정 | 정규화·표시에서 제거(M19) |
| partial 업로드 문서의 텍스트 뷰어가 빈 문서 | 크레딧 소진 E2E | Qdrant 비면 ES 대체(M17) |
| 포함 관계 구절이 mark 0개 → 이동해도 강조·스크롤 없음 | Claude 라이브 | 경계 분할·다중 소속(M21) |
| 원본 뷰어 실패 안내에 발췌·전환 없음 | Check 갭 #1 | `MissingPassageNotice`(Act-1) |
| PDF 로드 중 언마운트 시 문서·워커 누수 | Check 갭 #3 | 늦게 도착한 문서 destroy |
| 오류 대체 화면 Esc 미동작 | Check 갭 #4 | Esc 를 Shell 로 이동 |
| vitest `beforeEach(() => mock.mockReset())` 반환값이 teardown 으로 호출 | 테스트 디버깅 | 중괄호로 반환값 제거 |

## 6. Lessons Learned & Retrospective

### 6.1 What Went Well (Keep)

- **탈착 설계를 처음부터 계약으로 고정**했다. 백엔드 연결 지점은 AST 테스트(import 소비자)와 Design §11.2 표로 열거했고, gap-detector 가 독립적으로 "표와 정확히 일치"를 확인했다.
- **실제 문서로 잰 뒤 규칙을 고쳤다.** 합성 테스트는 모두 통과했지만 실제 PDF 매칭률은 29%였다. 숫자를 보고 원인(하이픈·FFFD)을 특정해 100% 로 올렸다.
- **라이브 경로가 막히자 경로를 바꿔 끝까지 확인**했다(Claude + BM25). 그 과정에서 겹침 결함을 찾았다 — 단위 테스트 데이터로는 드러나지 않는 종류였다.

### 6.2 What Needs Improvement (Problem)

- 합성 매칭 테스트가 "같은 추출기에서 나온 텍스트"를 전제했다. 두 추출기(PyMuPDF·pdf.js)의 차이를 다루는 기능은 Design 단계에서 실문서 측정을 먼저 했어야 했다(Design §11.3 의 module-7 을 앞당길 것).
- 백그라운드 전체 테스트를 돌리는 중에 Red 테스트를 추가해 결과가 오염됐다 — 전체 실행 중에는 테스트 파일을 건드리지 않는다.

### 6.3 What to Try Next (Try)

- 텍스트 비교가 핵심인 기능은 Do 첫 모듈에 "실데이터 측정 스크립트"를 둔다.
- 라이브 E2E 레시피(8011 백엔드·5175 프록시·`setAuth` 주입·Vite 모듈 import)를 재사용한다.

## 7. Process Improvement Suggestions

### 7.1 PDCA Process

- gap-detector 는 30턴 제한에 걸려 보고 없이 멈출 수 있다 — 범위가 넓으면 "N턴 안에 보고" 지시를 처음부터 넣는다.

### 7.2 Tools/Environment

- 8001 포트는 Docker 가 점유 — worktree 백엔드는 8011 사용.
- Chrome 백그라운드 탭은 pdf.js 렌더(rAF)가 멈춘다 — 측정 중 탭을 앞으로.
- 로컬 OpenAI 크레딧 소진 상태 — 임베딩·기본 LLM 경로 E2E 전 확인 필요.

## 8. Next Steps

### 8.1 Immediate

- [ ] master(04e55b0 이후)로 rebase → PR 생성
- [ ] 운영 반영 시 `SOURCE_VIEWER_ENABLED=true`, `DOCUMENT_ORIGINAL_STORAGE_DIR` 를 볼륨 경로로 지정하고 백업 대상에 포함
- [ ] 머지 후 메인 체크아웃 `npm install`(pdfjs-dist), worktree 정리 시 `idt_front/node_modules` junction 먼저 제거
- [ ] `/pdca archive source-passage-viewer`

### 8.2 Next PDCA Cycle

| Item | Priority |
|------|:--------:|
| 임베딩 경로 칩 라이브 확인(크레딧 복구 후) | High |
| 청킹 U+FFFD 생성 결함 수정 | Medium |
| 모바일 폭 확인 | Medium |
| 원본 정리 잡(컬렉션 삭제 고아·KB 소프트 삭제 후 정리) | Low |

## 9. Changelog

### v1.0.0 (2026-11-20)

**Added:**
- 근거 칩 "원문 보기" → 오른쪽 패널(원본 PDF·docx / 텍스트) 인용 구절 음영·이동
- KB 업로드 pdf·docx 원본 보관(로컬 디스크), 원본 조회 API `GET /api/v1/source-viewer/kb/{kb_id}/documents/{document_id}/original`
- 칩 payload `viewer`, 재진입 API `SourceItemDto.viewer`
- 설정 `SOURCE_VIEWER_ENABLED`(기본 false), `DOCUMENT_ORIGINAL_STORAGE_DIR`
- 의존성 `pdfjs-dist` 6.5.438(지연 로드)

**Changed:**
- 업로드·삭제·근거 서비스에 optional 협력자(미주입 시 기존 동작 그대로)

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-11-20 | Completion report | 배상규 |
