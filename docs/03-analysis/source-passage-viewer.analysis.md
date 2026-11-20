# source-passage-viewer Analysis Report

> **Feature**: 근거 칩 → 원문 구절 음영 뷰어
> **Date**: 2026-11-20
> **Branch / Commits**: `feat/source-passage-viewer` 219ba17 … d574c59 (7 commits, master aae4565 기준)
> **Plan**: [source-passage-viewer.plan.md](../01-plan/features/source-passage-viewer.plan.md)
> **Design**: [source-passage-viewer.design.md](../02-design/features/source-passage-viewer.design.md) (§12 M1–M21 = Do 중 확정한 의도된 변경)
> **Method**: gap-detector 정적 대조(독립 판독) + 단위·전체 테스트 + 인프로세스 스모크 + 실제 PDF·Claude 라이브 E2E

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 근거 칩이 파일명만 알려 주고, 원문에서 그 구절의 위치·문맥을 보여 주지 못한다 |
| **WHO** | 채팅에서 RAG 답변을 받는 사용자, 검색 품질을 점검하는 에이전트 소유자(P2) |
| **RISK** | 음영 매칭 실패, 원본 노출 경로 권한 누락, 새 기능 오류가 기존 채팅·업로드·삭제를 막는 것 |
| **SUCCESS** | 칩 → 패널 → 구절 음영·이동, 매칭 실패 시 단계적 대체, 권한 403, 스위치 off = 기존과 동일 |
| **SCOPE** | 백엔드 source_viewer 패키지 + 연결 지점, 프론트 sourceViewer 컴포넌트 + 연결 지점 |

---

## Strategic Alignment Check

PRD 없음(Plan 에서 시작). Plan 의 문제 정의 기준으로 판단한다.

| 항목 | 기대 | 상태 |
|------|------|:----:|
| 핵심 문제 | 근거 구절을 원문 위에서 확인 | ✅ 라이브 화면에서 칩 → 원본 PDF 음영 확인 |
| 대상 사용자 | 답변 사용자·P2 | ✅ 채팅 화면 안에서 동작, KB 권한 그대로 |
| 사용자 추가 요구 | "오류 시 빼기 쉬운 형태" | ✅ 킬스위치 기본 off, 마이그레이션 없음, 연결 지점 AST 고정(프론트 표 누락 2행은 갭 #2) |

### Success Criteria Status

| # | Criteria (Plan §4.1) | Status | Evidence |
|---|---------------------|:------:|----------|
| SC-1 | 원본 보관 on + PDF 업로드 → 칩 클릭 시 원본 PDF·음영 | ✅ | Claude 라이브(화면 질문→칩 "원문 보기"→원본 패널), Design §12.1 |
| SC-2 | 원본 없는 문서 → 텍스트 뷰어 음영 | ✅ | `SourceViewerPanelOriginal.test.tsx`(original null·원본 404 → 텍스트), 라이브 텍스트 모드(ES 대체) 확인 |
| SC-3 | 같은 파일 다중 구절 음영·이동 | ✅ | 라이브 5구절 5/5 현재 표시(M21 수정 후), `SourceViewerPanel.test.tsx` |
| SC-4 | 매칭 실패 구절 안내·텍스트 뷰어 전환 | ⚠️ | 텍스트 뷰어는 안내+발췌 완비. **원본 뷰어는 안내 문구만 있고 발췌·[텍스트로 보기] 없음**(갭 #1). 헤더 전환 버튼으로 우회 가능 |
| SC-5 | 권한 없음 403, 없는 문서 404 | ✅ | `test_source_viewer_router.py` 403/404/415, 스모크 무토큰 401·없는 KB 404(실DB) |
| SC-6 | 경로 비우면 기존 동작 | ✅ | `test_source_viewer_di.py`(text-only 라우터 미등록), 스모크 off 404, 백엔드 전체 신규 실패 0 |
| SC-7 | 문서 삭제 후 원본 제거 | ✅ | 라이브 2회(삭제 전후 파일 존재 확인). 컬렉션 전체 삭제 경로는 갭 #10 |
| SC-8 | 재진입 시 같은 칩·구절 | ✅ | 세션 근거 API 3개 세션 모두 viewer(original=pdf, 구절 5), `test_source_item_dto_viewer.py` |
| DoD | 테스트 먼저(TDD) | ✅ | 모듈마다 Red 확인 후 구현 |

**Quality Criteria**: 전체 회귀 신규 실패 0(백엔드 60건 = 상시 54 + worktree samples 부재 6, 프론트 = 상시 10건/5파일), 변경 파일 린트·타입 오류 0, 빌드 통과(pdf.js 별도 청크), 실파일 매칭률 실측 100%(§12.1). → 8/9 충족, SC-4 부분.

### Decision Record Verification

| Source | Decision | Followed? | Deviation |
|--------|----------|:---------:|-----------|
| [Plan] | A+B 함께, 기존 문서 재업로드 없음 | ✅ | — |
| [Plan] | 로컬 디스크 + 환경변수 경로 | ✅ | — |
| [Plan] | 음영 단위 = 검색 청크 전체, 칩 1개·뷰어에서 전부 | ✅ | — |
| [Plan] | 오른쪽 사이드 패널 | ✅ | 겹쳐 띄움(사용자 결정, M13) |
| [Design] | C안 탈착형, 기본 off | ✅ | 조립을 `source_viewer_di.py` 로(M7) |
| [Design] | 마이그레이션 없음 | ✅ | — |
| [Design] | 정규화 매칭 + 단계적 대체 | ✅ | 하이픈 규칙 변경(M18), FFFD(M19), 겹침 분할(M21) — 모두 실측 근거 |

---

## 1. Analysis Overview

- **목적**: Design 대비 구현의 구조·기능·계약 일치와 탈착 가능성 검증
- **범위**: 백엔드 9개 신규 + 연결 7곳, 프론트 17개 신규 + 연결 5곳, 테스트

## 2. Gap Analysis

### 2.1 API Endpoints

| Design | Implementation | Status |
|--------|---------------|:------:|
| `GET /api/v1/source-viewer/kb/{kb_id}/documents/{document_id}/original` | `source_viewer_router.py` | ✅ (검사 순서 M8) |
| 기존 `GET /api/v1/knowledge-bases/{kb}/documents/{doc}/chunks` 재사용 | `useSourceViewerChunks` | ✅ (ES 대체 M17) |

### 2.2 Data Model (wire)

| Field | Backend | Frontend | Status |
|-------|---------|----------|:------:|
| `viewer.document_id/kb_id` | `ViewerRef.to_payload` | `SourceViewerRef` | ✅ |
| `viewer.original` | `"pdf"\|"docx"\|null` | `OriginalKind \| null` | ✅ |
| `viewer.passages[]` | chunk_id·parent_id·page·excerpt | `SourceViewerPassage` | ✅ (`rank` 미전송, 갭 #9) |
| `DocumentSource.viewer` | DTO `null` 허용 | `viewer?: … \| null` | ✅ (M11) |

### 2.3 Component Structure

Design §5.3·§11.1 의 컴포넌트·파일 전부 존재. 추가 파일(Mount·Shell·Body·OriginalPassageViewer·exceptions·buildPassageDocument·domHighlight·pdfRenderer·훅 2개)은 §12 에 기록됨.

### 2.4 Failure absorption (Design §6) — 전부 성립

| 지점 | 안쪽 겹 | 바깥 겹 |
|------|--------|--------|
| 조립 | `source_viewer_di.py` try → None | 라우터 미등록 |
| 업로드 원본 저장 | `original_sink.py` | `unified_upload/use_case.py` `_save_original` |
| 삭제 원본 정리 | `original_sink.py` | `delete_document_use_case.py` `_delete_original` |
| 칩 viewer | `enricher.py`(+개별 exists 실패) | `run_sources.py` `_enrich` |
| 프론트 렌더 | `SourceViewerBoundary` | 지연 로드 실패도 포착 |

### 2.5 Detachability

- **백엔드**: 연결 지점이 Design §11.2 #1–#7 과 정확히 일치(gap-detector 독립 확인).
- **프론트**: F1–F4 일치, **표에 없는 2곳** — `lib/queryKeys.ts`(주석은 F5 지칭), `package.json` `pdfjs-dist`(갭 #2).
- AST 테스트는 import 소비자만 강제한다. duck typing 연결 지점은 §11.2 표가 SoT(갭 #6).

## 3. Match Rate

| 축 | 점수 |
|----|:----:|
| Structural | 97% |
| Functional | 90% |
| Contract | 98% |
| Runtime (단위·전체 회귀·스모크·라이브 SC 7/8 + 부분 1) | 95% |

**Overall = 97×0.15 + 90×0.25 + 98×0.25 + 95×0.35 = 94.8%** (정적만: 94.6%)

## 4. Gap List

| # | Severity | Conf. | Evidence | Gap | Fix |
|---|----------|:-----:|----------|-----|-----|
| 1 | **Important** | 90% | `PdfPassageViewer.tsx` 안내 블록, `DocxPassageViewer.tsx` 안내 블록 | 원본 뷰어 매칭 실패 시 발췌·[텍스트로 보기] 없음 (FR-12, SC-4) | 공용 안내 컴포넌트(FFFD 제거 발췌 + 텍스트 전환 버튼)를 두 뷰어에서 사용 |
| 2 | Minor | 85% | `lib/queryKeys.ts`, `package.json` | 프론트 연결 지점 표 누락 | §11.2 에 F5·F6 행 추가 |
| 3 | Minor | 80% | `PdfPassageViewer.tsx` 로드 effect | `loadPdf` 완료 전 cleanup 시 문서·워커 미정리 | `if (cancelled) { doc.destroy(); return; }` |
| 4 | Minor | 75% | `SourceViewerPanel.tsx`, `SourceViewerBoundary.tsx` | Boundary 대체 화면에서 Esc 로 안 닫힘 | Esc 처리를 Shell 로 이동 |
| 5 | Minor | 85% | `config.py` source_viewer 주석 | 소비 지점이 `main.py get_source_viewer()` 로 잘못 적힘 | `source_viewer_di.py build_source_viewer` 로 정정 |
| 6 | Minor | 80% | `test_module_boundaries.py` 주석, Design §11.2 문장 | "주입 3곳"(실제 4곳), "표 = AST 선언 목록" 과장 | 주석·문장 정정 |
| 7 | Minor | 70% | `PdfPassageViewer.tsx` 매칭 | 구절별 탐색 범위가 page±1 이 아닌 렌더된 전체 쪽 | 현재 동작을 Design 에 기록(쪽 메타가 비어 있는 실측상 전체 탐색이 실용적) |
| 8 | Minor | 70% | `main.py` 최상위 import | di 모듈 import 실패는 None 으로 흡수되지 않음 | graph_rag_di 와 같은 수준 — 유지 |
| 9 | Minor(문서) | 85% | 음영색 토큰, 스토어 mode, `Passage.rank` | Design 본문과 구현 표기 차이 | §12 M22 로 기록 |
| 10 | Minor | 80% | `collection/use_case.py delete_collection` | 컬렉션 전체 삭제는 문서별 훅을 거치지 않아 원본이 고아로 남음. KB 삭제는 소프트 삭제라 벡터·메타와 함께 보존(기존 정책과 일치) | 이월 — 정리 잡 도입 시 원본 루트도 대상에 포함 |

## 5. 이월(미확인)

- 임베딩(Qdrant) 검색 결과 칩 — OpenAI 크레딧 복구 후
- 모바일 폭 화면
- 청킹의 U+FFFD 생성(토큰 단위 child 분할) — 기존 결함, 매칭은 M19 로 흡수

## 6. Act-1 반영 (2026-11-20, 사용자 선택: Important + 쉬운 Minor)

| # | 조치 | 근거 |
|---|------|------|
| 1 | `MissingPassageNotice` 공용 안내 — 세 뷰어 모두 FFFD 제거 발췌, PDF·docx 뷰어에 [텍스트로 보기] → `SourceViewerBody.showText` | `PdfPassageViewer.test`·`DocxPassageViewer.test` 신규 케이스 |
| 2 | Design §11.2 에 F5(queryKeys)·F6(pdfjs-dist) 행 추가 | Design §11.2 |
| 3 | PDF 로드 중 언마운트 시 도착한 문서 `destroy()` | `PdfPassageViewer.test` "로드 완료 전에 언마운트…" |
| 4 | Esc 닫기를 `SourceViewerShell` 로 이동 — 오류 대체 화면도 닫힘 | `SourceViewerMount.test` "오류 대체 화면도 Esc…" |
| 5 | `config.py` 소비 지점 주석 → `source_viewer_di.py build_source_viewer()` | — |
| 6 | 경계 테스트 주석 "주입 4곳", Design §11.2 "AST 는 import 소비자만, 나머지는 표가 SoT" | — |
| 9 | Design §12 M22 로 표기 차이 기록 | — |
| 7·8·10 | Design §12 M24·M25·M26 로 기록하고 이월 | — |

**재채점**: Structural 97→99 (표 정합), Functional 90→97 (FR-12·SC-4 충족), Contract 98, Runtime 95→96
→ **Overall = 99×0.15 + 97×0.25 + 98×0.25 + 96×0.35 = 97.2%**. SC 9/9 충족(SC-4 ⚠️→✅).

## 7. 권장 다음 단계

Act-1 후 97.2%. `/pdca report` → master rebase → PR. 이월: 임베딩 경로 칩(크레딧), 모바일 폭, M24·M26, 청킹 FFFD 생성(기존 결함).
