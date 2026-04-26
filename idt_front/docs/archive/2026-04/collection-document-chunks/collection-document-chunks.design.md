# collection-document-chunks Design Document

> **Summary**: 컬렉션별 문서 목록 및 청크 상세 조회 드릴다운 UI
>
> **Project**: sangplusbot (idt_front)
> **Version**: 0.1.0
> **Author**: 배상규
> **Date**: 2026-04-23
> **Status**: Draft
> **Planning Doc**: [collection-document-chunks.plan.md](../01-plan/features/collection-document-chunks.plan.md)

---

## 1. Overview

### 1.1 Design Goals

- 컬렉션 관리 페이지에서 **컬렉션 → 문서 → 청크** 3단계 드릴다운 탐색 구조를 구현한다
- 기존 컬렉션 인프라(타입, 서비스, 훅, 쿼리키)를 확장하여 문서/청크 API를 통합한다
- parent-child 청크 전략을 트리 뷰로 시각화한다
- TopNav에서 "문서 관리" 메뉴를 제거하고 컬렉션 중심 네비게이션으로 통합한다

### 1.2 Design Principles

- **기존 인프라 확장**: 새 파일 최소화, 기존 `collection.ts`, `collectionService.ts`, `useCollections.ts`, `queryKeys.ts` 에 추가
- **마스터-디테일 패턴**: 문서 목록과 청크 상세를 같은 페이지에 배치하여 URL 간결성 유지
- **점진적 공개(Progressive Disclosure)**: 청크 content는 기본 접힘, 클릭 시 펼침

---

## 2. Architecture

### 2.1 Component Diagram

```
TopNav (메뉴 수정)
  │
  ▼
CollectionPage (/collections)
  │  CollectionTable — 컬렉션명 클릭 시 navigate
  │
  ▼
CollectionDocumentsPage (/collections/:collectionName/documents)
  ├── Breadcrumb (컬렉션 관리 > {collectionName})
  ├── DocumentTable (문서 목록 + 페이지네이션)
  └── ChunkDetailPanel (선택된 문서의 청크 상세)
       └── ParentChildTree (parent-child 계층 뷰, 토글)
```

### 2.2 Data Flow

```
1. 컬렉션 테이블 클릭
   → navigate(`/collections/${name}/documents`)

2. CollectionDocumentsPage 마운트
   → useCollectionDocuments(collectionName, { offset, limit })
   → GET /api/v1/collections/{collection_name}/documents
   → 문서 목록 렌더링 (DocumentTable)

3. 문서 행 클릭
   → setSelectedDocumentId(docId)
   → useDocumentChunks(collectionName, docId, { includeParent })
   → GET /api/v1/collections/{collection_name}/documents/{document_id}/chunks
   → 청크 상세 렌더링 (ChunkDetailPanel)

4. 계층 구조 토글 (parent_child 전략일 때만)
   → includeParent = true
   → 재요청 → ParentChildTree 렌더링
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| CollectionDocumentsPage | useCollectionDocuments, useDocumentChunks | 데이터 조회 |
| DocumentTable | CollectionDocumentsPage (props) | 문서 목록 표시 |
| ChunkDetailPanel | useDocumentChunks 결과 | 청크 상세 표시 |
| ParentChildTree | ChunkDetailPanel (props) | 계층 뷰 렌더링 |
| CollectionTable | react-router navigate | 드릴다운 네비게이션 |

---

## 3. Data Model

### 3.1 Entity Definition

```typescript
// src/types/collection.ts 에 추가

// ── 문서 목록 ────────────────────────────────
interface CollectionDocumentsResponse {
  collection_name: string;
  documents: DocumentSummary[];
  total_documents: number;
  offset: number;
  limit: number;
}

interface DocumentSummary {
  document_id: string;
  filename: string;
  category: string;
  chunk_count: number;
  chunk_types: string[];
  user_id: string;
}

// ── 청크 상세 ────────────────────────────────
type ChunkStrategy = 'parent_child' | 'full_token' | 'semantic';
type ChunkType = 'parent' | 'child' | 'full' | 'semantic';

interface DocumentChunksResponse {
  document_id: string;
  filename: string;
  chunk_strategy: ChunkStrategy;
  total_chunks: number;
  chunks: ChunkDetail[];
  parents: ParentChunkGroup[] | null;
}

interface ChunkDetail {
  chunk_id: string;
  chunk_index: number;
  chunk_type: ChunkType;
  content: string;
  metadata: Record<string, unknown>;
}

interface ParentChunkGroup {
  chunk_id: string;
  chunk_index: number;
  chunk_type: 'parent';
  content: string;
  children: ChunkDetail[];
}

// ── 쿼리 파라미터 ─────────────────────────────
interface CollectionDocumentsParams {
  offset?: number;
  limit?: number;
}

interface DocumentChunksParams {
  include_parent?: boolean;
}
```

### 3.2 Entity Relationships

```
[Collection] 1 ──── N [DocumentSummary]
                          │
                          └── 1 ──── N [ChunkDetail]
                                         │
                          [ParentChunkGroup] 1 ──── N [ChunkDetail (children)]
```

---

## 4. API Specification

### 4.1 Endpoint List

> 백엔드 구현 완료 상태. 프론트엔드에서 호출만 구현.

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/api/v1/collections/{collection_name}/documents` | 컬렉션 내 문서 목록 | Required |
| GET | `/api/v1/collections/{collection_name}/documents/{document_id}/chunks` | 문서별 청크 상세 | Required |

### 4.2 API 상수 추가 (constants/api.ts)

```typescript
// API_ENDPOINTS 에 추가
COLLECTION_DOCUMENTS: (name: string) =>
  `/api/v1/collections/${name}/documents`,
COLLECTION_DOCUMENT_CHUNKS: (name: string, documentId: string) =>
  `/api/v1/collections/${name}/documents/${documentId}/chunks`,
```

### 4.3 서비스 메서드 (collectionService.ts)

```typescript
// collectionService 에 추가
getDocuments: async (
  collectionName: string,
  params?: CollectionDocumentsParams,
): Promise<CollectionDocumentsResponse> => {
  const res = await authApiClient.get<CollectionDocumentsResponse>(
    API_ENDPOINTS.COLLECTION_DOCUMENTS(collectionName),
    { params },
  );
  return res.data;
},

getDocumentChunks: async (
  collectionName: string,
  documentId: string,
  params?: DocumentChunksParams,
): Promise<DocumentChunksResponse> => {
  const res = await authApiClient.get<DocumentChunksResponse>(
    API_ENDPOINTS.COLLECTION_DOCUMENT_CHUNKS(collectionName, documentId),
    { params },
  );
  return res.data;
},
```

### 4.4 에러 처리

| 코드 | 원인 | UI 처리 |
|------|------|---------|
| 422 | 파라미터 유효성 실패 | 토스트 에러 표시 |
| 500 | Qdrant 연결 실패 | "서버 오류" 에러 상태 + 재시도 버튼 |
| 빈 결과 | 존재하지 않는 문서 | "청크가 없습니다" 빈 상태 표시 |

---

## 5. UI/UX Design

### 5.1 Screen Layout — CollectionDocumentsPage

```
┌─────────────────────────────────────────────────────────┐
│ TopNav                                                  │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌─ Breadcrumb ──────────────────────────────────────┐  │
│  │ 컬렉션 관리 > my_finance                          │  │
│  └───────────────────────────────────────────────────┘  │
│                                                         │
│  문서 N건                               [← 돌아가기]    │
│                                                         │
│  ┌─ DocumentTable ───────────────────────────────────┐  │
│  │ 파일명          │ 카테고리 │ 청크 수 │ 청크 타입   │  │
│  │ 금융정책.pdf    │ finance  │   15    │ parent/child│  │
│  │ ▶ 세금가이드.pdf│ tax      │    8    │ full_token  │  │
│  │ 보험약관.pdf    │ insurance│   22    │ semantic    │  │
│  ├───────────────────────────────────────────────────┤  │
│  │              < 이전  1/3  다음 >                   │  │
│  └───────────────────────────────────────────────────┘  │
│                                                         │
│  ┌─ ChunkDetailPanel (선택된 문서) ──────────────────┐  │
│  │ 세금가이드.pdf                                    │  │
│  │ 전략: full_token  총 8개 청크                     │  │
│  │ [□ 계층 구조 보기] ← parent_child 일 때만 활성    │  │
│  │                                                   │  │
│  │ ┌─ Chunk #0 [full] ───────────────────────────┐  │  │
│  │ │ ▶ 청크 내용 미리보기...                      │  │  │
│  │ └─────────────────────────────────────────────┘  │  │
│  │ ┌─ Chunk #1 [full] ───────────────────────────┐  │  │
│  │ │ ▼ 전체 청크 텍스트가 펼쳐진 상태              │  │  │
│  │ │   metadata: { page: 2, source: "..." }       │  │  │
│  │ └─────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────┘  │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### 5.2 계층 구조 뷰 (ParentChildTree — 토글 ON 시)

```
┌─ ChunkDetailPanel ───────────────────────────────────┐
│ 금융정책.pdf                                         │
│ 전략: parent_child  총 15개 청크                      │
│ [✓ 계층 구조 보기]                                    │
│                                                      │
│ ┌─ Parent #0 ────────────────────────────────────┐   │
│ │ ▶ 부모 청크 내용 미리보기...                     │   │
│ │   ├── Child #1 [child] 자식 청크 내용...        │   │
│ │   ├── Child #2 [child] 자식 청크 내용...        │   │
│ │   └── Child #3 [child] 자식 청크 내용...        │   │
│ └────────────────────────────────────────────────┘   │
│ ┌─ Parent #4 ────────────────────────────────────┐   │
│ │ ▶ 부모 청크 내용 미리보기...                     │   │
│ │   ├── Child #5 [child] ...                     │   │
│ │   └── Child #6 [child] ...                     │   │
│ └────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────┘
```

### 5.3 User Flow

```
컬렉션 관리 (/collections)
  → 컬렉션명 클릭
  → 문서 목록 (/collections/:name/documents)
  → 문서 행 클릭
  → 청크 상세 패널 표시 (같은 페이지 하단)
  → [선택] 계층 구조 토글
```

### 5.4 Component List

| Component | Location | Responsibility |
|-----------|----------|----------------|
| CollectionDocumentsPage | `src/pages/CollectionDocumentsPage/index.tsx` | 페이지 조합: 브레드크럼 + DocumentTable + ChunkDetailPanel |
| DocumentTable | `src/components/collection/DocumentTable.tsx` | 문서 목록 테이블, 행 선택, 페이지네이션 |
| ChunkDetailPanel | `src/components/collection/ChunkDetailPanel.tsx` | 청크 목록 표시, accordion 접기/펼치기, 전략 뱃지 |
| ParentChildTree | `src/components/collection/ParentChildTree.tsx` | parent-children 계층 트리 뷰 |
| CollectionTable (수정) | `src/components/collection/CollectionTable.tsx` | 컬렉션명을 클릭 가능한 링크로 변경 |
| TopNav (수정) | `src/components/layout/TopNav.tsx` | "문서 관리" 메뉴 항목 제거 |

### 5.5 스타일 가이드 (프로젝트 디자인 시스템 준수)

| 요소 | 스타일 |
|------|--------|
| 브레드크럼 링크 | `text-[13.5px] text-violet-600 hover:underline` |
| 문서 테이블 | 기존 CollectionTable과 동일한 `rounded-2xl border border-zinc-200` |
| 선택된 문서 행 | `bg-violet-50` |
| 청크 전략 뱃지 | `rounded-md px-2 py-0.5 text-[11.5px] font-semibold` + 전략별 색상 |
| 청크 아코디언 헤더 | `text-[13.5px] font-medium text-zinc-800 cursor-pointer` |
| 청크 content | `text-[13px] leading-relaxed text-zinc-600 whitespace-pre-wrap` |
| metadata 표시 | `text-[12px] text-zinc-400 font-mono` |
| 계층 구조 토글 | Checkbox 스타일: `accent-violet-600` |
| 페이지네이션 버튼 | 기존 Secondary 버튼 패턴 |

#### 청크 전략 뱃지 색상

| 전략 | 색상 |
|------|------|
| parent_child | `bg-blue-50 text-blue-600` |
| full_token | `bg-emerald-50 text-emerald-600` |
| semantic | `bg-amber-50 text-amber-600` |

#### 청크 타입 뱃지 색상

| 타입 | 색상 |
|------|------|
| parent | `bg-violet-50 text-violet-600` |
| child | `bg-sky-50 text-sky-600` |
| full | `bg-emerald-50 text-emerald-600` |
| semantic | `bg-amber-50 text-amber-600` |

---

## 6. Error Handling

### 6.1 Error States

| 상황 | UI 표현 |
|------|---------|
| 문서 목록 로딩 중 | SkeletonRows (3행, CollectionTable 패턴 동일) |
| 문서 목록 에러 | 에러 카드 + "다시 시도" 버튼 |
| 문서 0건 | "이 컬렉션에 문서가 없습니다" 빈 상태 |
| 청크 로딩 중 | Skeleton 3개 블록 |
| 청크 0건 | "청크가 없습니다" 빈 상태 |
| 잘못된 collectionName | 404 처리 → `/collections`로 리다이렉트 |

---

## 7. Security Considerations

- [x] 인증 필수: `authApiClient` (Bearer 토큰) 사용 — 기존 인프라 활용
- [x] XSS 방지: 청크 content를 `whitespace-pre-wrap` 텍스트로만 렌더링 (innerHTML 사용 금지)
- [x] URL 파라미터 검증: `collectionName`은 useParams에서 추출, 서버 측 검증에 위임
- [x] 민감 데이터 없음: 모든 데이터는 서버에서 이미 권한 검증 완료

---

## 8. Test Plan

### 8.1 Test Scope

| Type | Target | Tool |
|------|--------|------|
| Unit Test | useCollectionDocuments, useDocumentChunks 훅 | Vitest + MSW |
| Unit Test | DocumentTable, ChunkDetailPanel, ParentChildTree 컴포넌트 | Vitest + RTL |
| Unit Test | collectionService.getDocuments, getDocumentChunks | Vitest + MSW |
| Integration Test | CollectionDocumentsPage 전체 흐름 | Vitest + RTL + MSW |

### 8.2 Test Cases (Key)

**훅 테스트 (useCollectionDocuments)**
- [ ] 문서 목록 정상 조회
- [ ] offset/limit 파라미터 전달 확인
- [ ] 빈 컬렉션일 때 빈 배열 반환

**훅 테스트 (useDocumentChunks)**
- [ ] 청크 목록 정상 조회
- [ ] include_parent=true 시 parents 필드 포함 확인
- [ ] documentId가 없을 때 enabled=false

**컴포넌트 테스트 (DocumentTable)**
- [ ] 문서 행이 올바르게 렌더링
- [ ] 문서 행 클릭 시 onSelect 콜백 호출
- [ ] 페이지네이션 이전/다음 버튼 동작
- [ ] 로딩 상태에서 스켈레톤 표시
- [ ] 빈 상태 메시지 표시

**컴포넌트 테스트 (ChunkDetailPanel)**
- [ ] 청크 목록이 아코디언으로 렌더링
- [ ] 아코디언 클릭 시 content 펼침/접힘
- [ ] 전략 뱃지 올바르게 표시
- [ ] parent_child 전략일 때만 "계층 구조 보기" 토글 활성

**컴포넌트 테스트 (ParentChildTree)**
- [ ] parent-children 계층 구조 렌더링
- [ ] parent 접기/펼치기 동작

**통합 테스트 (CollectionDocumentsPage)**
- [ ] 문서 목록 로드 → 문서 클릭 → 청크 패널 표시 전체 흐름

### 8.3 MSW Handler 추가

```typescript
// src/__tests__/mocks/handlers.ts 에 추가
http.get('*/api/v1/collections/:name/documents', ({ params }) => {
  return HttpResponse.json(mockCollectionDocumentsResponse);
}),
http.get('*/api/v1/collections/:name/documents/:docId/chunks', ({ params }) => {
  return HttpResponse.json(mockDocumentChunksResponse);
}),
```

---

## 9. Clean Architecture

### 9.1 Layer Structure

| Layer | Responsibility | Location |
|-------|---------------|----------|
| **Presentation** | 페이지, 컴포넌트, 사용자 상호작용 | `src/pages/`, `src/components/collection/` |
| **Application** | TanStack Query 훅, 비즈니스 로직 | `src/hooks/useCollections.ts` |
| **Domain** | 타입 정의, 상수 | `src/types/collection.ts` |
| **Infrastructure** | API 호출, HTTP 클라이언트 | `src/services/collectionService.ts`, `src/constants/api.ts` |

### 9.2 This Feature's Layer Assignment

| Component | Layer | Location |
|-----------|-------|----------|
| CollectionDocumentsPage | Presentation | `src/pages/CollectionDocumentsPage/index.tsx` |
| DocumentTable | Presentation | `src/components/collection/DocumentTable.tsx` |
| ChunkDetailPanel | Presentation | `src/components/collection/ChunkDetailPanel.tsx` |
| ParentChildTree | Presentation | `src/components/collection/ParentChildTree.tsx` |
| useCollectionDocuments | Application | `src/hooks/useCollections.ts` (추가) |
| useDocumentChunks | Application | `src/hooks/useCollections.ts` (추가) |
| DocumentSummary, ChunkDetail 등 | Domain | `src/types/collection.ts` (추가) |
| collectionService.getDocuments | Infrastructure | `src/services/collectionService.ts` (추가) |
| collectionService.getDocumentChunks | Infrastructure | `src/services/collectionService.ts` (추가) |
| COLLECTION_DOCUMENTS 등 | Infrastructure | `src/constants/api.ts` (추가) |
| queryKeys.collections.documents | Infrastructure | `src/lib/queryKeys.ts` (추가) |

---

## 10. Coding Convention Reference

### 10.1 This Feature's Conventions

| Item | Convention Applied |
|------|-------------------|
| Component naming | PascalCase: `DocumentTable.tsx`, `ChunkDetailPanel.tsx` |
| File organization | 컬렉션 도메인 통합: `components/collection/` 디렉토리 |
| State management | 서버 상태 = TanStack Query, 로컬 상태 = useState (selectedDocId, expandedChunks) |
| Error handling | TanStack Query isError + 에러 카드 UI |
| Props 타입 | interface + PascalCase (e.g., `DocumentTableProps`) |
| Export | 파일 하단 `export default` |

---

## 11. Implementation Guide

### 11.1 File Structure

```
src/
├── types/collection.ts                          # (수정) 문서/청크 타입 추가
├── constants/api.ts                             # (수정) 엔드포인트 추가
├── lib/queryKeys.ts                             # (수정) 쿼리키 추가
├── services/collectionService.ts                # (수정) 서비스 메서드 추가
├── hooks/useCollections.ts                      # (수정) 훅 추가
├── components/collection/
│   ├── CollectionTable.tsx                      # (수정) 컬렉션명 클릭 네비게이션
│   ├── DocumentTable.tsx                        # (신규) 문서 목록 테이블
│   ├── ChunkDetailPanel.tsx                     # (신규) 청크 상세 패널
│   └── ParentChildTree.tsx                      # (신규) 계층 구조 트리
├── pages/CollectionDocumentsPage/
│   └── index.tsx                                # (신규) 문서 목록 페이지
├── components/layout/TopNav.tsx                 # (수정) "문서 관리" 메뉴 제거
└── App.tsx                                      # (수정) 라우트 추가
```

### 11.2 Implementation Order

1. [ ] **Domain Layer**: `src/types/collection.ts` — 문서/청크 타입 추가
2. [ ] **Infrastructure Layer**: `src/constants/api.ts` — 엔드포인트 상수 추가
3. [ ] **Infrastructure Layer**: `src/lib/queryKeys.ts` — 쿼리키 추가
4. [ ] **Infrastructure Layer**: `src/services/collectionService.ts` — getDocuments, getDocumentChunks 추가
5. [ ] **Application Layer**: `src/hooks/useCollections.ts` — useCollectionDocuments, useDocumentChunks 훅 추가
6. [ ] **Test**: 훅/서비스 단위 테스트 작성 (MSW 핸들러 포함)
7. [ ] **Presentation**: `DocumentTable` 컴포넌트 구현 + 테스트
8. [ ] **Presentation**: `ChunkDetailPanel` 컴포넌트 구현 + 테스트
9. [ ] **Presentation**: `ParentChildTree` 컴포넌트 구현 + 테스트
10. [ ] **Presentation**: `CollectionDocumentsPage` 페이지 조합 + 통합 테스트
11. [ ] **Navigation**: `CollectionTable` — 컬렉션명 클릭 시 navigate 추가
12. [ ] **Routing**: `App.tsx` — 새 라우트 추가, `/documents` 리다이렉트
13. [ ] **Navigation**: `TopNav` — "문서 관리" 메뉴 항목 제거

### 11.3 Query Key 추가 (queryKeys.ts)

```typescript
// collections 섹션에 추가
documents: (name: string, params?: CollectionDocumentsParams) =>
  [...queryKeys.collections.all, 'documents', name, params] as const,
chunks: (name: string, documentId: string, params?: DocumentChunksParams) =>
  [...queryKeys.collections.all, 'chunks', name, documentId, params] as const,
```

### 11.4 라우팅 변경 (App.tsx)

```typescript
// 인증 필요 라우트 블록 내에 추가
<Route path="/collections/:collectionName/documents" element={<CollectionDocumentsPage />} />

// /documents → /collections 리다이렉트로 변경
<Route path="/documents" element={<Navigate to="/collections" replace />} />
```

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-04-23 | Initial draft | 배상규 |
