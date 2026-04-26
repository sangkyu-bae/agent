# Plan: collection-document-browser

> Feature: 컬렉션 관리 페이지에서 문서 목록 조회 + 청크 뷰어 UI
> Created: 2026-04-26
> Status: Plan
> Priority: Medium
> Related: `qdrant-collection-management` (archived), `qdrant-mysql-data-migration` (plan)

---

## 1. 목적 (Why)

`qdrant-collection-management` 기능으로 컬렉션 CRUD + 이력 조회 UI가 완성되었으나,
**컬렉션 안에 어떤 문서가 있는지 확인하는 UI가 없다.**

사용자가 컬렉션 관리 화면에서:
1. 컬렉션을 클릭하면 → 해당 컬렉션에 포함된 **문서 목록**을 볼 수 있어야 하고
2. 문서를 클릭하면 → 해당 문서의 **청크 데이터**를 Qdrant에서 필터링하여 볼 수 있어야 한다

---

## 2. 현재 상태 분석 (As-Is)

### 이미 구축된 인프라

| 구분 | 상태 | 파일 |
|------|------|------|
| MySQL `document_metadata` 테이블 | ✅ | `db/migration/V014__create_document_metadata.sql` |
| Ingest 시 MySQL 자동 저장 | ✅ | `src/application/ingest/ingest_use_case.py:141-153` |
| 문서 목록 API | ✅ | `GET /api/v1/collections/{name}/documents` → MySQL 조회 |
| 청크 조회 API | ✅ | `GET /api/v1/collections/{name}/documents/{id}/chunks` → Qdrant 필터 |
| ListDocumentsUseCase | ✅ | `src/application/doc_browse/list_documents_use_case.py` |
| GetChunksUseCase | ✅ | `src/application/doc_browse/get_chunks_use_case.py` |
| doc_browse_router | ✅ | `src/api/routes/doc_browse_router.py` |
| 프론트 서비스 레이어 | ✅ | `collectionService.getDocuments()`, `.getDocumentChunks()` |
| TanStack Query 훅 | ✅ | `useCollectionDocuments()`, `useDocumentChunks()` |
| 프론트 타입 정의 | ✅ | `CollectionDocumentsResponse`, `DocumentChunksResponse` |

### 누락된 부분

| 구분 | 상태 |
|------|------|
| CollectionPage 문서 목록 뷰 | ❌ UI 컴포넌트 없음 |
| 문서 청크 뷰어 컴포넌트 | ❌ UI 컴포넌트 없음 |
| CollectionTable에서 문서 보기 진입점 | ❌ 클릭/확장 동작 없음 |

---

## 3. 기능 범위 (Scope)

### In Scope

**A. 문서 목록 패널 (DocumentListPanel)**
- [x] 컬렉션 테이블에서 컬렉션 행 클릭 시 하단에 문서 목록 패널 표시
- [x] `useCollectionDocuments(collectionName)` 훅으로 MySQL 데이터 조회
- [x] 표시 항목: filename, category, chunk_count, user_id, created_at
- [x] 페이지네이션 (offset/limit)
- [x] 로딩/에러/빈 상태 처리

**B. 청크 뷰어 (ChunkViewer)**
- [x] 문서 행 클릭 시 모달 또는 사이드패널로 청크 목록 표시
- [x] `useDocumentChunks(collectionName, documentId)` 훅으로 Qdrant 데이터 조회
- [x] 표시 항목: chunk_index, chunk_type, content (접기/펼치기), metadata
- [x] parent-child 전략일 경우 계층 구조 표시

**C. CollectionTable 확장**
- [x] 컬렉션 행에 문서 수(points_count) 이미 표시 중 → 클릭 가능하도록 변경
- [x] 선택된 컬렉�� 하이라이트
- [x] 문서 목록 패널 토글 (같은 컬렉션 재클릭 시 닫기)

### Out of Scope

- 문서 삭제 기능 (별도 기능으로 분리)
- 청크 내용 편집
- 문서 재인덱싱/재청킹
- 레거시 데이터 마이그레이션 (`qdrant-mysql-data-migration` 플랜에서 처리)
- 문서 검색/필터링 (향후 확장)

---

## 4. UI 설계

### 4.1 인터랙션 흐름

```
CollectionPage
├── [컬렉션 관리] 탭 (기존)
│   └── CollectionTable
│       └── 컬���션 행 클릭
│           └── DocumentListPanel (하단 확장)
│               ├���─ 문서 목록 테이블
│               └── 문서 행 클릭
│                   └── ChunkViewerModal (모달)
│                       ├���─ 청크 목록
│                       └── 청크 내용 (접기/펼치기)
├── [사용 이력] 탭 (기존)
```

### 4.2 문서 목록 패널 레이아웃

```
┌──��───────────────────────────────────────────────────┐
│  CollectionTable                                      │
│  ┌────────────┬─────────┬────────┬──────────────┐    │
│  │ Name       │ Vectors │ Status │ Actions      │    │
│  ├─��──────────┼─────────┼────────┼──────���───────┤    │
│  │ documents ▼│  1,523  │ 🟢    │ ...          │    │ ← 클릭됨 (하이라이트)
│  │ my-col     │    452  │ 🟢    │ ...          │    │
│  └────────────┴���────────┴────────��──────────────┘    │
│                                                       │
│  ── documents 컬렉션 문서 (3건) ──────────────────    │
│  ┌─────────────────┬──────────┬────────┬────────┐    │
│  │ Filename        │ Category │ Chunks │ User   │    │
│  ├────────────────���┼──────────┼────────┼────────┤    │
│  │ 금리보고서.pdf    │ finance  │   42   │ user1  │    │
│  │ 정책자료.pdf      │ policy   │   28   │ user2  │    │
│  │ 분석보고서.pdf    ��� analysis │   15   │ user1  │    │
│  └─────────────���───┴──────────┴────────┴────────┘    │
│  [◀ 1 2 ▶]                                           │
└──────────────────────────────────────────────────────┘
```

### 4.3 청크 뷰어 모달 레이아웃

```
┌─────────���───────��────────────────────────┐
│  📄 금리보고서.pdf — 청크 목록            │  [✕]
│  전략: parent_child | 총 42개 청크        │
├─────────────────────────────────────────���┤
│  #1 [parent]                             │
│  ┌──────────��───────────────────────┐    │
│  │ 2024년 금리 동향 보고서의 주요    │    │
│  │ 내용을 요약하면 다음과 같다...    │    │
│  └──────��───────────────────────────┘    │
│    ├─ #2 [child] "금리 인상 배경..."  ▼  │
│    └─ #3 [child] "통화정책 방향..."   ▼  │
│                                          │
│  #4 [parent]                             │
│  ┌──────────────��───────────────────┐    │
│  │ 국내 경제 현황 분석 결과,         │    │
│  │ 소비자 물가지수는...              │    │
│  └─────────────────────���────────────┘    │
│    ├─ #5 [child] "소비자 물가..."     ▼  │
│    └─ #6 [child] "생산자 물가..."     ▼  │
│                                          │
│  [더 보기 ▼]                             │
└───────────────────────────���──────────────┘
```

---

## 5. 기술 의존성

| 모듈 | 상태 | 비고 |
|------|------|------|
| `useCollectionDocuments` 훅 | ✅ 구현됨 | `idt_front/src/hooks/useCollections.ts:82-90` |
| `useDocumentChunks` 훅 | ✅ 구현됨 | `idt_front/src/hooks/useCollections.ts:92-101` |
| `collectionService.getDocuments()` | ✅ 구현됨 | `idt_front/src/services/collectionService.ts:97-106` |
| `collectionService.getDocumentChunks()` | ✅ 구현됨 | `idt_front/src/services/collectionService.ts:108-118` |
| `doc_browse_router` API | ✅ 구현됨 | `src/api/routes/doc_browse_router.py` |
| `ListDocumentsUseCase` | ✅ 구현됨 | MySQL 기반 ��서 목록 조회 |
| `GetChunksUseCase` | ✅ 구현됨 | Qdrant 기반 청크 조회 |
| 프론트 타입 정의 | ✅ 구현됨 | `idt_front/src/types/collection.ts` |

**백엔드 추가 작업: 없음** — 모든 API/UseCase/Repository 구현 완료 상태

---

## 6. 파일 구조

### 신규 생성 (프론트엔드만)

```
idt_front/src/
├── components/collection/
│   ├── DocumentListPanel.tsx      # 컬렉션 내 문서 목록 패널 (신규)
│   └── ChunkViewerModal.tsx       # 청크 뷰어 모달 (신규)
```

### 수정 대상

```
idt_front/src/
├── pages/CollectionPage/index.tsx         # selectedCollection 상태 추가, DocumentListPanel 연결
├── components/collection/CollectionTable.tsx  # 행 클릭 이벤트 추가
```

---

## 7. TDD 계획

### 프론트엔드

| 테스트 파일 | 대상 |
|------------|------|
| `src/__tests__/mocks/handlers.ts` | MSW 핸들러 추가 (documents, chunks 엔드포인트) |
| `src/components/collection/DocumentListPanel.test.tsx` | 문서 목록 렌더링, 페이지네이션, 빈 상태 |
| `src/components/collection/ChunkViewerModal.test.tsx` | 청크 목록 렌더���, parent-child 계층, 접기/펼치기 |

### 백엔드

백엔드 추가 개발 없음 — 기존 테스트 유지.

---

## 8. CLAUDE.md 규칙 체크

- [x] router에 비즈니스 로직 없음 (기존 API 그대로 사용)
- [x] domain에 외부 의존성 없음 (변경 없음)
- [x] TDD: 테스트 먼저 작성 (프론트 컴포넌트 테스트)
- [x] API 계약 동기화: 백엔드 변경 없으므로 타입 불일치 위험 없음

---

## 9. 리스크 및 대응

| 리스크 | 영향 | 대응 |
|--------|------|------|
| 레거시 문서가 MySQL에 없어 목록이 비어 보임 | 중 | `qdrant-mysql-data-migration` 선행 실행 권장 |
| 청크 수가 많은 문서(100+) 모달 성능 | 낮 | 청크 목록 가상 스크롤 또는 페이지네이션 |
| parent-child 구조가 아닌 청크의 계층 표시 | 낮 | chunk_strategy에 따라 flat/tree 뷰 분기 |

---

## 10. 완료 기준

- [ ] 컬렉션 행 클릭 시 문서 목록 패널 표시
- [ ] 문서 목록에 filename, category, chunk_count, user_id 표시
- [ ] 문서 목록 페이지네이션 동작
- [ ] 문서 클릭 시 청크 뷰어 모달 표시
- [ ] 청크 목록에 chunk_index, chunk_type, content 표시
- [ ] parent-child 전략 시 계층 구조 표���
- [ ] 로딩/에러/빈 상태 처리
- [ ] 프론트 컴포넌트 테스트 통과

---

## 11. 구현 순서

| 순서 | 작업 | 예상 시간 |
|------|------|----------|
| 1 | MSW 핸들러 추가 (documents, chunks mock) | 15분 |
| 2 | `DocumentListPanel.tsx` 컴포넌트 + 테스트 | 40분 |
| 3 | `ChunkViewerModal.tsx` 컴포넌트 + 테스트 | 40분 |
| 4 | `CollectionTable.tsx` 수정 — 행 클릭 이벤트 | 15분 |
| 5 | `CollectionPage/index.tsx` 통합 — 상태 관리, 패널 연결 | 20분 |
| 6 | 브라우저 ��스트 (dev 서버 실행 후 확인) | 15분 |

**총 예상: ~2.5시간 (프론트엔드만)**

---

## 12. 다음 단계

1. [ ] Design 문서 작성 (`/pdca design collection-document-browser`)
2. [ ] `qdrant-mysql-data-migration` 선행 실행 여부 결정
3. [ ] 구현 시작 (TDD)
