---
title: 화면↔API 지도 — 지식베이스·컬렉션 화면
status: approved
reviewer: 배상규
source_type: conversation
source_refs:
  - idt_front/src/App.tsx (라우트 선언)
  - idt_front/src/constants/api.ts (KNOWLEDGE_BASES / COLLECTIONS 블록)
  - idt/docs/archive/2026-07/kb-content-browser/kb-content-browser.report.md
  - idt_front/src/components/knowledge-base/KbUploadDocumentModal.tsx:92 (v2 — accept 목록)
  - idt/docs/archive/2026-10/hwp-parser/hwp-parser.report.md (v2)
confidence: 0.85
version: 2
created: 2026-07-21
updated: 2026-10-13
verified_at: 3b6353b
---

> v2 (2026-10-13): KB 상세 업로드 형식에 한글(.hwp/.hwpx) 추가. 다른 절은 v1(6cc25656) 그대로.

## KnowledgeBasesPage — `/knowledge-bases`

논리 지식베이스(KB) 목록·생성 화면. KB = 물리 컬렉션 위의 스코프(PERSONAL/DEPARTMENT/PUBLIC) 단위.

- 진입: `idt_front/src/pages/KnowledgeBasesPage/index.tsx`
- 훅: `useKnowledgeBases` → `KNOWLEDGE_BASES`
- 백엔드: `knowledge_base_router` → `knowledge_base` 테이블 ([[erd-kb]])

## KnowledgeBaseDetailPage — `/knowledge-bases/:kbId`

KB 상세 — 문서 목록·업로드(PDF/엑셀/한글), 청킹 설정, 콘텐츠 브라우저(3계층 드릴다운), 리트리버 테스트를 한 화면에서 처리.

- (v2) 업로드 모달 `KbUploadDocumentModal` `accept=".pdf,.xlsx,.xls,.hwp,.hwpx"`. 한글은 백엔드 `ExtensionRoutingParser`가 같은 청킹 경로로 보내며 암호·배포용·손상 파일은 422로 돌아온다(모달이 서버 메시지를 그대로 노출). 프론트 변경은 accept·안내 문구뿐 — 새 포맷 추가 시 백엔드 라우팅 + 이 두 줄이 전부 ([[hwp-parser-format-facts]])

- 진입: `idt_front/src/pages/KnowledgeBaseDetailPage/index.tsx`
- 훅: `useKnowledgeBases` (조회+뮤테이션 일괄)
- 엔드포인트: `KNOWLEDGE_BASE_DETAIL/DOCUMENTS/CHUNKING`, 콘텐츠 브라우저 3종(`DOCUMENT_SUMMARY`, `SECTION_SUMMARIES`, `DOCUMENT_CHUNKS`), 요약 잡(`SECTION_SUMMARY_STATUS/RETRY`), 검색(`KNOWLEDGE_BASE_SEARCH`, `KNOWLEDGE_BASE_SEARCH_HISTORY`)
- 백엔드: `knowledge_base_router` → KB 서비스 → ES/Qdrant + `document_metadata`/`section_summary_job`/`search_history`
- 계약 주의: 콘텐츠 브라우저는 `source` 토글로 ES/Qdrant 저장소별 조회를 선택한다 (kb-content-browser)
- 계약 주의: 청킹 설정 수정은 `PATCH`가 아니라 `KNOWLEDGE_BASE_CHUNKING` **전체 교체** 계약 (kb-custom-chunking D7)
- 연관: [[additive-contract-extension]] (use_custom_chunking 독립 opt-in 선례), E2E는 [[e2e-carryover-checklist]] 일괄 대기

## CollectionPage — `/collections`

물리 벡터 컬렉션 목록·권한·활동로그 화면 (KB보다 낮은 저장소 계층).

- 진입: `idt_front/src/pages/CollectionPage/index.tsx`
- 훅: `useCollections` → `COLLECTIONS`, `COLLECTION_PERMISSION`, `COLLECTION_ACTIVITY_LOG*`
- 백엔드: `collection_router` → Qdrant + `collection_permissions`/`collection_activity_log`

## CollectionDocumentsPage — `/collections/:collectionName/documents`

컬렉션 내 문서 목록·청크 열람·검색·삭제 화면.

- 진입: `idt_front/src/pages/CollectionDocumentsPage/index.tsx`
- 훅: `useCollections` → `COLLECTION_DOCUMENTS`, `COLLECTION_DOCUMENT_CHUNKS`, `COLLECTION_SEARCH(_HISTORY)`, `COLLECTION_DOCUMENT(S)_DELETE`
- 백엔드: `doc_browse_router` / `collection_search_router` → `document_metadata`, `search_history`

## KB vs 컬렉션 구분 (지도 요점)

- **컬렉션** = 물리 저장 단위(Qdrant/ES). `collection_name` 문자열이 키.
- **KB** = 논리 단위. `knowledge_base.collection_name`으로 물리 컬렉션을 가리키고, 문서는 `document_metadata.kb_id`(NULL=일반 업로드)로 귀속된다. KB 검색은 `kb_id` payload 필터로 격리 (kb-rag-filter / kb-retrieval-test).
