# source-passage-viewer Planning Document

> **Summary**: 답변 근거 칩을 누르면 오른쪽 패널에 문서를 열고, 검색된 구절에 음영을 표시한다
>
> **Project**: sangplusbot (Agent Builder)
> **Author**: 배상규
> **Date**: 2026-11-19
> **Status**: Draft
> **Related**: `docs/archive/*/agent-run-source-citations` (근거 칩, PR #86), `docs/archive/2026-11/document-file-preview` (docx/pdf 미리보기), `idt/docs/archive/2026-07/doc-extractor-preview-highlight` (문자열 일치 강조 실패 사례)

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 근거 칩은 파일명과 청크 앞부분만 보여 준다. 사용자는 그 구절이 문서의 어디에 있는지, 앞뒤 문맥이 무엇인지 확인할 수 없다. 원본 파일은 업로드 후 저장되지 않아 원본을 다시 열 방법도 없다. |
| **Solution** | 업로드 시 원본을 로컬 디스크(환경변수로 경로 지정)에 보관한다. 근거 칩에 `document_id`·`kb_id`·인용 청크 목록·페이지를 싣는다. 원본이 있는 PDF·docx는 원본 뷰어에서 청크 문장을 찾아 음영을 표시하고, 원본이 없거나 형식이 지원되지 않으면 저장된 청크를 이어 붙인 텍스트 뷰어에서 표시한다. |
| **Function/UX Effect** | 칩을 누르면 오른쪽 패널에 문서가 열리고 첫 인용 구절로 이동한다. 같은 파일의 인용 구절은 모두 음영으로 표시되고 이전/다음 버튼으로 이동한다. |
| **Core Value** | 금융·정책 문서 답변을 원문과 바로 대조할 수 있다. 에이전트 소유자(P2)는 검색이 맞는 구절을 가져왔는지 확인하고 KB를 고칠 근거를 얻는다. |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 근거 칩이 파일명만 알려 주고, 원문에서 그 구절의 위치·문맥을 보여 주지 못한다 |
| **WHO** | 채팅에서 RAG 답변을 받는 사용자, 검색 품질을 점검하는 에이전트 소유자(P2) |
| **RISK** | 파서 추출 텍스트와 뷰어 렌더 텍스트가 달라 음영 매칭이 실패한다(2026-07 문서추출기 사례). 원본 파일 노출 경로에서 KB 권한 검사가 빠진다 |
| **SUCCESS** | 칩 클릭 → 패널에 문서 표시 → 인용 구절 음영·이동. 원본 PDF/docx 매칭 실패 시 페이지 이동 또는 텍스트 뷰어로 내려감. 권한 없는 사용자는 403 |
| **SCOPE** | 백엔드: 원본 저장 포트+로컬 어댑터, 업로드·삭제 연동, 칩 계약 확장, 원본·청크 조회 API. 프론트: 사이드 패널, 텍스트/PDF/docx 뷰어, 음영 매칭, 타입 동기화. 기존 문서 재업로드·HWP 원본 렌더 제외 |

---

## 1. Overview

### 1.1 Purpose

답변 근거를 "어느 파일"에서 "어느 구절"까지 좁혀 원문 위에서 보여 준다.

### 1.2 Background — 현재 코드 기준 사실

| 항목 | 현재 상태 | 근거 |
|------|----------|------|
| 근거 칩 내용 | `kind`·`source`(파일명)·`content`(청크 앞부분)·`chunk_id`만 내보낸다. 페이지·document_id는 내보내지 않는다 | `idt/src/domain/agent_run/source_policy.py:49` `RunSourceItem.to_payload` |
| 파일별 합치기 | 같은 파일의 청크는 칩 1개로 합쳐지고 첫 청크만 남는다 | `source_policy.py` `_document_items` |
| 원본 파일 | KB 업로드는 파싱·청킹 후 원본 바이트를 버린다. `document_metadata`에는 파일명·청크 수만 남는다 | `idt/src/application/unified_upload/use_case.py:84`, `idt/src/infrastructure/doc_browse/models.py` |
| 페이지 정보 | PDF 파서가 페이지별 `page`를 붙이고 parent-child 청킹이 `merge_metadata`로 이어받는다. 다른 전략(section_aware·clause_aware·semantic)과 docx·HWP 파서의 page 유지 여부는 미확인 | `pymupdf_parser.py:54`, `parent_child_strategy.py:75` |
| 위치 정보 | 청크에 char offset·bbox가 없다 → 음영은 텍스트 매칭으로 찾아야 한다 | — |
| 검색 기록 | `RetrievalSource`에 `document_id`·`chunk_id`·`content_preview`·`metadata_json`이 실행마다 저장된다 | `idt/src/domain/agent_run/entities.py:94` |
| 청크 조회 API | `GET /kb/{kb_id}/documents/{document_id}/chunks` 가 이미 있다 | `knowledge_base_router.py:901` |
| 프론트 미리보기 | `docx-preview` 설치됨. PDF는 브라우저 내장 뷰어(iframe)라 텍스트 음영을 넣을 수 없다 → `pdfjs-dist` 도입 필요 | `idt_front/package.json`, document-file-preview Plan |

### 1.3 사용자 확정 사항 (2026-11-19)

| 질문 | 결정 |
|------|------|
| 뷰어 범위 | 텍스트 뷰어(A)와 원본 뷰어(B)를 이번에 함께 만든다 |
| 기존 문서 | 다시 올리지 않는다. 원본이 없는 기존 문서는 텍스트 뷰어로 보여 준다. 원본 보관은 이후 업로드부터 적용한다 |
| 원본 보관 위치 | 서버 로컬 디스크. 경로는 환경변수로 지정한다. 저장소는 포트로 분리해 나중에 오브젝트 스토리지로 바꿀 수 있게 한다 |
| 음영 단위 | 검색된 청크 전체 |
| 같은 파일 다중 구절 | 칩은 파일당 1개를 유지하고, 뷰어에서 인용 구절을 모두 음영 처리한 뒤 이전/다음으로 이동한다 |
| 뷰어 형태 | 오른쪽 사이드 패널. 모바일 폭에서는 전체 화면으로 연다 |

---

## 2. Scope

### 2.1 In Scope

- [ ] 원본 저장 포트(`DocumentOriginalStoragePort`)와 로컬 디스크 어댑터. 경로는 환경변수 하나로 지정한다
- [ ] KB 업로드 시 원본 저장, 문서 삭제 시 원본 삭제. 저장에 실패해도 업로드는 성공시키고 경고 로그만 남긴다
- [ ] `document_metadata`에 원본 보관 정보 컬럼 추가(Flyway 마이그레이션)
- [ ] 근거 칩 계약 확장: `document_id`, `kb_id`, `has_original`, `passages[]`(chunk_id, page, content)
- [ ] 원본 다운로드 API(KB 읽기 권한 검사, inline 응답)
- [ ] 텍스트 뷰어: 기존 청크 조회 API로 문서를 이어 붙이고 인용 청크에 음영을 칠한다
- [ ] PDF 원본 뷰어: `pdfjs-dist` 텍스트 레이어에서 정규화 매칭으로 음영을 칠한다. 실패하면 해당 페이지로 이동하고 "정확한 위치를 찾지 못함" 안내
- [ ] docx 원본 뷰어: `docx-preview` 렌더 DOM에서 정규화 매칭으로 음영을 칠한다. 실패하면 텍스트 뷰어로 전환할 수 있게 한다
- [ ] 오른쪽 사이드 패널, 구절 이전/다음 이동, 텍스트↔원본 전환
- [ ] 프론트 타입·서비스·훅 동기화(`api-contract-sync`)

### 2.2 Out of Scope

- 기존 문서의 원본 소급 보관·재업로드 유도
- HWP·xlsx 원본 렌더링(텍스트 뷰어로 처리)
- 답변 문장 단위 강조(근거 판정 결과와 연결하는 작업)
- 파싱 단계의 char offset·bbox 저장
- 웹·위키·MCP 칩의 뷰어 연결(기존 동작 유지)
- 오브젝트 스토리지 어댑터 구현(포트만 열어 둔다)
- 관리자 화면에서 저장 경로 변경

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | KB 업로드 시 원본 바이트를 저장 포트로 보관하고, 보관 결과를 문서 메타데이터에 기록한다 | High | Pending |
| FR-02 | 원본 저장 경로는 환경변수로 지정한다. 미설정 시 원본 보관 기능은 꺼지고 업로드는 기존과 같이 동작한다 | High | Pending |
| FR-03 | 원본 저장 실패는 업로드를 실패시키지 않는다(경고 로그, `has_original=false`) | High | Pending |
| FR-04 | KB 문서 삭제 시 보관된 원본도 삭제한다. 원본 삭제 실패는 로그만 남긴다 | High | Pending |
| FR-05 | 문서 칩 payload에 `document_id`, `kb_id`, `has_original`, `passages[]`를 더한다. `passages`는 해당 실행에서 그 파일로 검색된 청크 전체이며 순위순이다. 기존 키(`source`, `content`, `chunk_id`)는 유지한다 | High | Pending |
| FR-06 | 실시간 답변과 세션 재진입이 같은 정책(`RunSourcePolicy`)을 지나 같은 칩·구절 목록을 만든다 | High | Pending |
| FR-07 | `GET` 원본 다운로드 API: KB 읽기 권한 검사 → 404/403 → `Content-Disposition: inline` 으로 반환 | High | Pending |
| FR-08 | 칩 클릭 시 오른쪽 사이드 패널이 열린다. 원본이 있고 PDF/docx면 원본 뷰어, 아니면 텍스트 뷰어로 연다 | High | Pending |
| FR-09 | 텍스트 뷰어: 청크 조회 API로 문서 전문을 순서대로 구성하고 인용 청크에 음영을 칠한 뒤 첫 구절로 스크롤한다 | High | Pending |
| FR-10 | PDF 뷰어: 인용 구절의 page로 이동하고 텍스트 레이어에서 공백·줄바꿈·하이픈을 정규화해 매칭한 범위에 음영을 칠한다 | High | Pending |
| FR-11 | docx 뷰어: 렌더된 DOM 텍스트를 정규화해 매칭한 범위에 음영을 칠한다 | Medium | Pending |
| FR-12 | 매칭 실패 구절은 패널에 "원문에서 정확한 위치를 찾지 못했습니다"를 표시하고, 청크 내용과 텍스트 뷰어 전환 버튼을 보여 준다 | High | Pending |
| FR-13 | 여러 구절은 "n / N" 표시와 이전/다음 버튼으로 이동한다 | Medium | Pending |
| FR-14 | 웹·위키·MCP 칩은 기존 동작을 유지한다 | High | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Security | 원본·청크 조회는 KB 읽기 권한을 검사한다. 저장 경로는 서버가 만든 키로만 구성해 경로 조작(`../`)을 막는다 | 권한·경로 단위 테스트 |
| Security | docx 렌더는 기존 미리보기와 같은 격리(shadow DOM, 외부 리소스 차단)를 쓴다 | document-file-preview 방식 재사용 |
| Performance | `pdfjs-dist`·`docx-preview`는 패널을 열 때만 지연 로드하고 초기 번들에 포함하지 않는다 | 빌드 산출물 확인 |
| Performance | 큰 PDF는 현재 페이지 주변만 렌더한다 | 수동 확인(100쪽 이상 문서) |
| Compatibility | 기존 칩 소비자(`SourceCitation`, `sessionSources`)는 새 필드가 없어도 동작한다 | 프론트 회귀 테스트 |
| Storage | 원본은 업로드 크기 상한 안에서만 저장한다(기존 업로드 제한 그대로) | — |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] SC-1: 원본 보관이 켜진 상태에서 PDF를 올리고 질문하면, 칩 클릭 시 패널에 원본 PDF가 열리고 인용 구절에 음영이 칠해진다
- [ ] SC-2: 기존(원본 없는) 문서의 칩을 누르면 텍스트 뷰어가 열리고 인용 청크에 음영이 칠해진다
- [ ] SC-3: 같은 파일에서 2개 이상 구절이 검색되면 모두 음영 처리되고 이전/다음으로 이동된다
- [ ] SC-4: 매칭이 실패한 구절은 안내 문구와 텍스트 뷰어 전환이 표시된다(조용히 빠지지 않는다)
- [ ] SC-5: KB 읽기 권한이 없는 사용자의 원본 요청은 403, 없는 문서는 404
- [ ] SC-6: 원본 저장 경로 환경변수를 비우면 업로드·칩이 기존과 같게 동작한다
- [ ] SC-7: KB 문서 삭제 후 원본 파일이 디스크에서 사라진다
- [ ] SC-8: 세션 재진입 시 실시간과 같은 칩·구절 목록이 나온다
- [ ] 백엔드 pytest·프론트 Vitest 테스트를 먼저 작성하고 통과

### 4.2 Quality Criteria

- [ ] 변경 범위 테스트 통과, master 대비 신규 실패 0
- [ ] 프론트 린트·빌드 통과, 뷰어 라이브러리 지연 로드 확인
- [ ] 실제 금융 PDF 1개 이상으로 음영 매칭률 측정(인용 구절 중 정확히 칠해진 비율)

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| PyMuPDF 추출 텍스트와 pdf.js 텍스트 레이어의 공백·줄바꿈·하이픈·표 순서가 달라 매칭 실패 | High | High | 문자열 완전일치 금지(2026-07 교훈). 양쪽 정규화 후 매칭하고, 실패 시 앞/뒤 일부 구간 매칭 → 페이지 이동 → 텍스트 뷰어 순으로 내려간다. Design에서 실파일로 매칭률을 먼저 측정 |
| PDF 외 파서·전략에서 `page`가 유실 | Medium | Medium | Design 단계에서 전략별 page 유지를 실측한다. page 없으면 전체 문서에서 검색 |
| 원본 노출 API가 권한 검사를 빠뜨림 | High | Low | 기존 청크 조회 API와 같은 KB 정책을 거치고 403 테스트를 먼저 작성 |
| 디스크 사용량 증가·백업 누락 | Medium | Medium | 삭제 연동(FR-04), 배포 가이드에 볼륨·백업 항목 추가 |
| 원본 저장 성공 후 인덱싱 실패로 고아 파일 생김 | Low | Medium | 인덱싱 성공 후 저장하거나, 실패 시 저장분 정리. 순서는 Design에서 정함 |
| `passages` 추가로 칩 payload가 커짐 | Low | Medium | 구절 content는 기존 미리보기 길이 상한을 적용하고 전문은 뷰어에서 청크 API로 가져온다 |
| parent-child 청크가 겹쳐 텍스트 뷰어 문서가 중복됨 | Medium | Medium | 텍스트 뷰어는 parent 청크를 `chunk_index` 순으로 잇고, child 인용은 parent 안에서 위치를 찾는다. Design에서 확정 |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `document_metadata` | DB | 원본 보관 정보 컬럼 추가(예: `original_storage_key`, `original_content_type`, nullable) |
| `UnifiedUploadUseCase` / KB 업로드 | Application | 원본 저장 포트 호출 추가(optional 협력자, 미주입=기존 동작) |
| `DeleteDocumentUseCase` | Application | 원본 삭제 호출 추가 |
| `RunSourceItem` / `RunSourcePolicy` | Domain | 문서 칩에 document_id·kb_id·has_original·passages 추가 |
| `SourceItemDto` | API Schema | 필드 추가(선택 필드) |
| 원본 다운로드 라우트 | API | 신규 |
| `DocumentSource` 타입, `SourceCitation`, `sessionSources` | Frontend | 필드 추가, 칩 클릭 동작 변경 |
| 사이드 패널·뷰어 컴포넌트 | Frontend | 신규 |
| `.env.example` | Config | 원본 저장 경로 키 추가 |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| `RunSourceItem.to_payload` | READ | `run_agent_use_case.py` `_attach_sources` (실시간·강등 경로) | 필드 추가만, 기존 키 유지 |
| `RunSourcesService.build_for_runs` | READ | 세션 재진입 API | 같은 정책을 지나므로 함께 확장 |
| `DocumentSource` | READ | `SourceCitation.tsx`, `useAgentRunStream.ts`, `ChatPage/index.tsx`, `utils/sessionSources.ts` | 선택 필드라 기존 렌더 유지, 클릭 동작만 변경 |
| `document_metadata` | CREATE | `unified_upload/use_case.py:132` | nullable 컬럼이라 기존 저장 경로 영향 없음 |
| `document_metadata` | READ | doc_browse·KB 문서 목록 | 컬럼 추가만, 확인 필요 |
| 업로드 경로 | CREATE | 일반 업로드(`document_upload.py`)·KB 업로드 | 이번 범위는 KB 업로드만. 일반 업로드 포함 여부는 Design에서 결정 |
| `DocumentSource` 계약 | READ | `rag_agent_router.py` `DocumentSourceItem` | 별도 경로, 변경 없음 확인 필요 |

### 6.3 Verification

- [ ] 위 소비자 전부 새 필드 유무 양쪽에서 동작 확인
- [ ] 권한 검사가 기존 청크 조회 API와 같은 정책을 지나는지 확인
- [ ] 원본 보관이 꺼진 상태(환경변수 없음)에서 기존 테스트 전부 통과

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Selected |
|-------|:--------:|
| Enterprise (레이어 분리·DI 단일 집중, 기존 idt 구조) | ✅ |

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 원본 보관 | 로컬 디스크 / LONGBLOB / 오브젝트 스토리지 | 로컬 디스크 + 저장 포트 | 사용자 결정. Oracle PoC 단일 서버에 맞고, 포트로 나중에 교체 가능 |
| 기능 끄기 | 플래그 / 경로 미설정 | 경로 미설정 = 기능 off | 탈착형 모듈 이음매 규칙(optional 협력자, 미주입=기존 동작) |
| 음영 위치 찾기 | offset 저장 / 텍스트 매칭 | 정규화 텍스트 매칭 + 단계적 대체 | 기존 청크에 offset이 없고, 파서 전반 수정은 범위 밖 |
| PDF 렌더 | iframe / pdfjs-dist | pdfjs-dist(지연 로드) | iframe 내장 뷰어에는 음영을 넣을 수 없음 |
| docx 렌더 | docx-preview | docx-preview(기존) | 이미 설치·격리 방식 검증됨 |
| 뷰어 위치 | 모달 / 사이드 패널 | 오른쪽 사이드 패널 | 사용자 결정. 답변과 원문 대조 |
| 패널 상태 | Zustand / 로컬 state | Zustand 스토어(기존 미리보기 스토어 패턴) | 칩은 메시지 안, 패널은 ChatPage 1회 마운트 |
| 테스트 | pytest / Vitest+RTL+MSW | 두 프로젝트 기존 도구 | TDD 공통 원칙 |

### 7.3 구조 미리보기

```
idt/
  domain/document_original/        포트(DocumentOriginalStoragePort), 저장 키 규칙
  infrastructure/document_original/ LocalDiskOriginalStorage
  application/unified_upload/       업로드 후 원본 저장(optional)
  application/knowledge_base/       삭제 시 원본 삭제, 원본 조회 유스케이스(권한)
  domain/agent_run/source_policy.py 문서 칩 passages·document_id·kb_id
  api/routes/knowledge_base_router.py  GET /{kb_id}/documents/{document_id}/original
idt_front/
  components/chat/SourcePanel/      패널, TextPassageViewer, PdfPassageViewer, DocxPassageViewer
  store/sourcePanelStore.ts
  utils/passageMatch.ts             정규화·매칭(순수 함수, 단위 테스트 집중)
```

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- [x] `CLAUDE.md` 3종 + `idt/docs/rules/`
- [x] 탈착형 모듈 이음매(`docs/wiki/backend/patterns/detachable-module-seam.md`)
- [x] 운영 config 단일 출처(`docs/wiki/conventions/config-single-source-at-consumption.md`)
- [x] 프론트: 컴포넌트 파일 런타임 상수 export 금지, `as const`는 `src/types/*.ts`
- [x] 미리보기 모달 1회 마운트·트리거 상수 1곳(엑셀 미리보기 선례)

### 8.2 Environment Variables Needed

| Variable | Purpose | Scope | To Be Created |
|----------|---------|-------|:-------------:|
| `DOCUMENT_ORIGINAL_STORAGE_DIR` | 원본 보관 경로. 비우면 보관 기능 off | Server | ☐ |

---

## 9. Next Steps

1. [ ] `/pdca design source-passage-viewer` — 설계안 3가지 비교, 저장 순서·parent/child 처리·매칭 알고리즘 확정
2. [ ] Design 전 실측: 전략별 `page` 유지 여부, 실제 금융 PDF로 PyMuPDF↔pdf.js 텍스트 차이
3. [ ] 마이그레이션 번호 확인(현재 마지막 V091)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-11-19 | Initial draft (사용자 확정 사항 반영) | 배상규 |
