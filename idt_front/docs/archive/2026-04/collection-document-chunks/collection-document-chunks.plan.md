# collection-document-chunks Plan Document

> **Feature**: 컬렉션별 문서 목록 및 청크 상세 조회 UI
>
> **Project**: sangplusbot (idt_front)
> **Author**: 배상규
> **Date**: 2026-04-23
> **Status**: Draft
> **API Spec Ref**: `docs/api/collection-document-chunks.md`

---

## 1. 개요

### 1.1 목표

기존 `/documents` 문서 관리 페이지를 독립 메뉴에서 분리하여, **컬렉션 관리 → 컬렉션 클릭 → 문서 목록 → 문서 클릭 → 청크 상세** 로 이어지는 드릴다운 탐색 구조를 구현한다.

**핵심 변경 사항:**

1. TopNav에서 "문서 관리" 메뉴 항목을 제거
2. 컬렉션 관리 페이지(`/collections`)에서 컬렉션 행 클릭 시 `/collections/:collectionName/documents`로 이동
3. 새 페이지: 컬렉션별 문서 목록 조회 (GET `/{collection_name}/documents`)
4. 문서 클릭 시 해당 문서의 청크 상세 조회 (GET `/{collection_name}/documents/{document_id}/chunks`)
5. parent-child 계층 구조 토글 지원

### 1.2 비목표 (Scope Out)

- 문서 업로드/삭제 기능 (기존 DocumentPage의 업로드 기능은 이 범위에 포함하지 않음)
- 벡터 검색 UI (기존 ChatPage에서 처리)
- 컬렉션 생성/삭제/이름변경 (이미 CollectionPage에서 구현 완료)
- 청크 편집/삭제 기능

---

## 2. 백엔드 API 계약

> 백엔드 구현 완료 상태. Base URL: `/api/v1/collections`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/{collection_name}/documents` | 컬렉션 내 문서 목록 조회 |
| GET | `/{collection_name}/documents/{document_id}/chunks` | 문서별 청크 상세 조회 |

### 2.1 문서 목록 응답 스키마

```typescript
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
```

**Query Parameters**: `offset` (default 0), `limit` (default 20, max 100)

### 2.2 청크 상세 응답 스키마

```typescript
interface DocumentChunksResponse {
  document_id: string;
  filename: string;
  chunk_strategy: 'parent_child' | 'full_token' | 'semantic';
  total_chunks: number;
  chunks: ChunkDetail[];
  parents: ParentChunkGroup[] | null;
}

interface ChunkDetail {
  chunk_id: string;
  chunk_index: number;
  chunk_type: 'parent' | 'child' | 'full' | 'semantic';
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
```

**Query Parameters**: `include_parent` (default false) — parent_child 전략에서만 유효

### 2.3 에러 코드

| 코드 | 설명 |
|------|------|
| 422 | 파라미터 유효성 검증 실패 |
| 500 | Qdrant 연결 실패 등 서버 내부 오류 |

> 존재하지 않는 document_id 조회 시 에러가 아닌 빈 결과(total_chunks=0, chunks=[])를 반환

---

## 3. 사용자 스토리

### US-1: 컬렉션에서 문서 목록 탐색

**As a** 사용자  
**I want** 컬렉션 관리 페이지에서 특정 컬렉션을 클릭하면 해당 컬렉션에 포함된 문서 목록을 볼 수 있기를  
**So that** 어떤 문서가 어떤 컬렉션에 임베딩되어 있는지 파악할 수 있다.

**Acceptance Criteria:**
- [ ] 컬렉션 테이블에서 컬렉션 이름을 클릭하면 `/collections/:collectionName/documents`로 이동
- [ ] 문서 목록에 파일명, 카테고리, 청크 수, 청크 타입이 표시
- [ ] offset/limit 기반 페이지네이션 동작
- [ ] 빈 컬렉션일 때 "문서가 없습니다" 빈 상태 표시
- [ ] 브레드크럼으로 "컬렉션 관리 > {컬렉션명}" 경로 표시

### US-2: 문서 청크 상세 조회

**As a** 사용자  
**I want** 문서 목록에서 특정 문서를 클릭하면 해당 문서의 청크를 상세히 볼 수 있기를  
**So that** 청킹 결과를 확인하고 RAG 품질을 검증할 수 있다.

**Acceptance Criteria:**
- [ ] 문서 클릭 시 청크 목록이 펼쳐지거나 별도 영역에 표시
- [ ] 청크 전략(parent_child, full_token, semantic)에 따른 뱃지 표시
- [ ] 각 청크의 content, chunk_type, metadata 표시
- [ ] parent_child 전략일 때 "계층 구조 보기" 토글로 parent-children 트리 뷰 제공
- [ ] 청크 content는 기본 접혀있고 클릭 시 펼침 (accordion)

### US-3: 네비게이션 구조 변경

**As a** 사용자  
**I want** TopNav에서 "문서 관리"가 사라지고 "컬렉션 관리"를 통해 문서에 접근하기를  
**So that** 컬렉션 → 문서 → 청크의 자연스러운 계층 탐색이 가능하다.

**Acceptance Criteria:**
- [ ] TopNav "데이터" 메뉴에서 "문서 관리" 항목 제거
- [ ] `/documents` 라우트를 `/collections/:collectionName/documents`로 대체
- [ ] 기존 `/documents` URL 접근 시 `/collections`로 리다이렉트
- [ ] 컬렉션 테이블의 컬렉션 이름이 클릭 가능한 링크로 변경

---

## 4. 화면 흐름

```
TopNav [데이터 > 컬렉션 관리]
  │
  ▼
┌─────────────────────────────────────────────┐
│  컬렉션 관리 (/collections)                   │
│  ┌─────────────────────────────────────────┐ │
│  │ 컬렉션명(클릭)│ 벡터 수 │ 상태 │ 액션  │ │
│  │ documents     │  1,234  │  ●   │ ...   │ │
│  │ my_finance ←클릭                       │ │
│  └─────────────────────────────────────────┘ │
└─────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────┐
│  컬렉션 관리 > my_finance                     │
│  (/collections/my_finance/documents)          │
│                                               │
│  문서 N건                          [← 돌아가기]│
│  ┌─────────────────────────────────────────┐ │
│  │ 파일명          │카테고리│청크수│타입    │ │
│  │ 금융정책_2026.pdf│finance │  15 │P/C    │ │
│  │ 세금가이드.pdf ←클릭                    │ │
│  └─────────────────────────────────────────┘ │
│  ┌ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┐ │
│  │ 청크 상세 패널 (선택된 문서)              │ │
│  │ 전략: parent_child  [□ 계층 구조 보기]    │ │
│  │                                          │ │
│  │ #0 [child] 청크 텍스트 내용...           │ │
│  │ #1 [child] 청크 텍스트 내용...           │ │
│  └ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┘ │
└─────────────────────────────────────────────┘
```

---

## 5. 구현 범위

### 5.1 프론트엔드 변경 파일

| 분류 | 파일 | 작업 |
|------|------|------|
| **타입** | `src/types/collection.ts` | DocumentSummary, ChunkDetail, ParentChunkGroup 등 타입 추가 |
| **상수** | `src/constants/api.ts` | COLLECTION_DOCUMENTS, COLLECTION_DOCUMENT_CHUNKS 엔드포인트 추가 |
| **쿼리키** | `src/lib/queryKeys.ts` | collections.documents(), collections.chunks() 키 추가 |
| **서비스** | `src/services/collectionService.ts` | getDocuments(), getDocumentChunks() 메서드 추가 |
| **훅** | `src/hooks/useCollections.ts` | useCollectionDocuments(), useDocumentChunks() 훅 추가 |
| **페이지** | `src/pages/CollectionDocumentsPage/index.tsx` | 새 페이지: 문서 목록 + 청크 뷰어 |
| **컴포넌트** | `src/components/collection/CollectionTable.tsx` | 컬렉션명 클릭 시 네비게이션 추가 |
| **컴포넌트** | `src/components/collection/DocumentTable.tsx` | 새 컴포넌트: 문서 테이블 |
| **컴포넌트** | `src/components/collection/ChunkDetailPanel.tsx` | 새 컴포넌트: 청크 상세 패널 |
| **컴포넌트** | `src/components/collection/ParentChildTree.tsx` | 새 컴포넌트: 계층 구조 트리 뷰 |
| **라우팅** | `src/App.tsx` | 새 라우트 추가, /documents 리다이렉트 |
| **네비게이션** | `src/components/layout/TopNav.tsx` | "문서 관리" 메뉴 항목 제거 |

### 5.2 구현 순서

```
1. 타입 정의 (types/collection.ts)
2. API 상수 추가 (constants/api.ts)
3. 쿼리 키 추가 (lib/queryKeys.ts)
4. 서비스 메서드 추가 (services/collectionService.ts)
5. TanStack Query 훅 추가 (hooks/useCollections.ts)
6. DocumentTable 컴포넌트 구현
7. ChunkDetailPanel 컴포넌트 구현
8. ParentChildTree 컴포넌트 구현
9. CollectionDocumentsPage 페이지 조합
10. CollectionTable에 클릭 네비게이션 추가
11. App.tsx 라우팅 변경
12. TopNav 메뉴 항목 정리
```

---

## 6. 기술 결정

### 6.1 라우팅 구조

```
/collections                            → CollectionPage (기존)
/collections/:collectionName/documents  → CollectionDocumentsPage (신규)
/documents                              → Navigate to /collections (리다이렉트)
```

### 6.2 청크 상세 표시 방식

문서 목록과 청크 상세를 같은 페이지에 배치한다 (마스터-디테일 패턴).
- 문서 클릭 → 하단에 청크 상세 패널이 나타남
- 별도 라우트(`/collections/:name/documents/:docId/chunks`)는 사용하지 않음 → URL 간결성

### 6.3 페이지네이션

offset/limit 기반 서버 사이드 페이지네이션.
- 기본 limit: 20
- 이전/다음 버튼 방식 (총 문서 수 표시)

### 6.4 parent-child 토글

`include_parent` 쿼리 파라미터로 서버에서 두 가지 뷰를 제공.
- 기본: flat list (include_parent=false)
- 토글 on: 계층 트리 (include_parent=true) — parent_child 전략에서만 활성화

---

## 7. 의존성

| 의존 | 상태 | 비고 |
|------|------|------|
| 컬렉션 관리 UI (collection-management-ui) | 완료 | CollectionPage, CollectionTable 등 |
| 컬렉션 권한 관리 (collection-permission-management) | 완료 | scope 관련 UI |
| collection-document-chunks API (백엔드) | 완료 | GET documents, GET chunks |
| TanStack Query 공통 구성 (TQ-001) | 완료 | queryClient, queryKeys |

---

## 8. 리스크 및 고려사항

| 리스크 | 영향 | 대응 |
|--------|------|------|
| 기존 `/documents` 경로를 사용하는 외부 링크 | 낮음 | 리다이렉트로 호환성 유지 |
| 대량 청크(수백 개) 렌더링 성능 | 중간 | accordion 접기/펼치기로 DOM 최소화 |
| parent_child 계층 구조가 깊어질 때 | 낮음 | 현재 1단계(parent-child)만 지원 |

---

## 9. 성공 지표

- [ ] 컬렉션 → 문서 → 청크 드릴다운 탐색이 3클릭 이내로 가능
- [ ] 페이지네이션으로 20건씩 문서 목록 조회 가능
- [ ] parent-child 계층 토글이 정상 동작
- [ ] 기존 `/documents` URL이 `/collections`로 리다이렉트
- [ ] TopNav에서 "문서 관리" 항목이 제거됨
