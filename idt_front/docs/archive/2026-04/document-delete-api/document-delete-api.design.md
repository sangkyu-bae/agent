# document-delete-api Design Document

> **Summary**: 컬렉션 문서 삭제 API 연동 — 타입, 서비스, 훅, 공통 ConfirmDialog, 체크박스 선택 UI
>
> **Project**: IDT Front (idt_front)
> **Version**: 0.1.0
> **Author**: 배상규
> **Date**: 2026-04-30
> **Status**: Draft
> **Planning Doc**: [document-delete-api.plan.md](../01-plan/features/document-delete-api.plan.md)

---

## 1. Overview

### 1.1 Design Goals

- 백엔드 문서 삭제 API(단건/일괄)를 프론트엔드에서 호출할 수 있도록 연동
- 재사용 가능한 공통 확인 다이얼로그(`ConfirmDialog`) 추출
- 기존 `DeleteCollectionDialog`를 `ConfirmDialog` 기반으로 리팩터링하여 중복 제거

### 1.2 Design Principles

- 기존 아키텍처 패턴 준수 (constants → types → services → hooks → components)
- 공통 컴포넌트는 `components/common/`에 배치하여 프로젝트 전반에서 재사용
- TanStack Query mutation 패턴으로 서버 상태 관리

---

## 2. Architecture

### 2.1 Data Flow

```
사용자 액션 (삭제 버튼 / 일괄 삭제)
  ↓
ConfirmDialog 표시 (파일명 목록)
  ↓ (확인 클릭)
useMutation 호출
  ↓
collectionService.deleteDocument / deleteDocuments
  ↓
authApiClient.delete (X-User-Id 헤더 포함)
  ↓
백엔드 DELETE API
  ↓ (응답)
onSuccess → queryClient.invalidateQueries (문서 목록 갱신)
onError → ConfirmDialog 내 에러 메시지 표시
```

### 2.2 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `DocumentTable` | `useDeleteDocument`, `useDeleteDocuments` | 삭제 API 호출 |
| `useDeleteDocument` | `collectionService.deleteDocument` | 단건 삭제 mutation |
| `useDeleteDocuments` | `collectionService.deleteDocuments` | 일괄 삭제 mutation |
| `collectionService` | `authApiClient` | HTTP 요청 전송 |
| `authApiClient` | `authStore` | Bearer 토큰 + X-User-Id 헤더 주입 |
| `ConfirmDialog` | 없음 (독립) | 범용 확인 다이얼로그 |

---

## 3. Data Model

### 3.1 API 엔드포인트 상수 추가

```typescript
// src/constants/api.ts — 추가 항목
COLLECTION_DOCUMENT_DELETE: (name: string, documentId: string) =>
  `/api/v1/collections/${name}/documents/${documentId}`,
COLLECTION_DOCUMENTS_BATCH_DELETE: (name: string) =>
  `/api/v1/collections/${name}/documents`,
```

### 3.2 타입 정의

```typescript
// src/types/collection.ts — 추가 타입

/** 단건 삭제 응답 */
export interface DeleteDocumentResponse {
  document_id: string;
  collection_name: string;
  filename: string;
  deleted_qdrant_chunks: number;
  deleted_es_chunks: number;
}

/** 일괄 삭제 요청 */
export interface BatchDeleteDocumentsRequest {
  document_ids: string[];
}

/** 일괄 삭제 개별 결과 */
export interface BatchDeleteDocumentResult {
  document_id: string;
  status: 'deleted' | 'failed';
  deleted_qdrant_chunks: number;
  deleted_es_chunks: number;
  filename: string;
  error: string | null;
}

/** 일괄 삭제 응답 */
export interface BatchDeleteDocumentsResponse {
  total: number;
  success_count: number;
  failure_count: number;
  results: BatchDeleteDocumentResult[];
}
```

---

## 4. API Specification

### 4.1 Endpoint List

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| DELETE | `/api/v1/collections/{name}/documents/{document_id}` | 단건 문서 삭제 | X-User-Id |
| DELETE | `/api/v1/collections/{name}/documents` | 일괄 문서 삭제 | X-User-Id |

### 4.2 X-User-Id 헤더 주입

`authClient.ts`의 request interceptor에서 `authStore.user.id`를 `X-User-Id` 헤더로 주입한다.

```typescript
// src/services/api/authClient.ts — request interceptor 수정
authApiClient.interceptors.request.use((config) => {
  const { accessToken, user } = useAuthStore.getState();
  if (accessToken) {
    config.headers.Authorization = `Bearer ${accessToken}`;
  }
  if (user?.id) {
    config.headers['X-User-Id'] = String(user.id);
  }
  return config;
});
```

### 4.3 서비스 메서드

```typescript
// src/services/collectionService.ts — 추가 메서드

deleteDocument: async (
  collectionName: string,
  documentId: string,
): Promise<DeleteDocumentResponse> => {
  const res = await authApiClient.delete<DeleteDocumentResponse>(
    API_ENDPOINTS.COLLECTION_DOCUMENT_DELETE(collectionName, documentId),
  );
  return res.data;
},

deleteDocuments: async (
  collectionName: string,
  data: BatchDeleteDocumentsRequest,
): Promise<BatchDeleteDocumentsResponse> => {
  const res = await authApiClient.delete<BatchDeleteDocumentsResponse>(
    API_ENDPOINTS.COLLECTION_DOCUMENTS_BATCH_DELETE(collectionName),
    { data },
  );
  return res.data;
},
```

### 4.4 TanStack Query 훅

```typescript
// src/hooks/useCollections.ts — 추가 훅

export const useDeleteDocument = () =>
  useMutation({
    mutationFn: ({ collectionName, documentId }: {
      collectionName: string;
      documentId: string;
    }) => collectionService.deleteDocument(collectionName, documentId),
    onSuccess: (_, { collectionName }) =>
      queryClient.invalidateQueries({
        queryKey: queryKeys.collections.documents(collectionName),
      }),
  });

export const useDeleteDocuments = () =>
  useMutation({
    mutationFn: ({ collectionName, documentIds }: {
      collectionName: string;
      documentIds: string[];
    }) => collectionService.deleteDocuments(collectionName, { document_ids: documentIds }),
    onSuccess: (_, { collectionName }) =>
      queryClient.invalidateQueries({
        queryKey: queryKeys.collections.documents(collectionName),
      }),
  });
```

### 4.5 Error Handling

| HTTP 코드 | 원인 | UI 처리 |
|-----------|------|---------|
| 403 | 삭제 권한 없음 | ConfirmDialog 내 에러: "삭제 권한이 없습니다" |
| 404 | 문서 없음 | ConfirmDialog 내 에러: "문서를 찾을 수 없습니다" |
| 500 | 서버 오류 | ConfirmDialog 내 에러: "삭제 중 오류가 발생했습니다" |

에러 메시지 추출 유틸:

```typescript
const getDeleteError = (error: unknown): string | null => {
  if (!error) return null;
  if (error instanceof ApiError) {
    if (error.status === 403) return '삭제 권한이 없습니다';
    if (error.status === 404) return '문서를 찾을 수 없습니다';
    return error.message;
  }
  return '삭제 중 오류가 발생했습니다';
};
```

---

## 5. UI/UX Design

### 5.1 공통 ConfirmDialog 컴포넌트

**위치**: `src/components/common/ConfirmDialog.tsx`

```typescript
interface ConfirmDialogProps {
  isOpen: boolean;
  title: string;
  description: string | React.ReactNode;
  confirmLabel?: string;        // 기본값: '확인'
  cancelLabel?: string;         // 기본값: '취소'
  variant?: 'danger' | 'warning' | 'info';  // 기본값: 'danger'
  onClose: () => void;
  onConfirm: () => void;
  isPending?: boolean;
  error?: string | null;
}
```

**variant별 스타일**:

| variant | confirm 버튼 | 아이콘/강조 |
|---------|-------------|------------|
| `danger` | `border-red-200 text-red-500 hover:bg-red-50` | 빨간 강조 |
| `warning` | `border-amber-200 text-amber-600 hover:bg-amber-50` | 노란 강조 |
| `info` | `border-violet-200 text-violet-600 hover:bg-violet-50` | 보라 강조 |

**기존 DeleteCollectionDialog 리팩터링**:

```tsx
// src/components/collection/DeleteCollectionDialog.tsx — 리팩터링 후
import ConfirmDialog from '@/components/common/ConfirmDialog';

interface DeleteCollectionDialogProps {
  isOpen: boolean;
  collectionName: string;
  onClose: () => void;
  onConfirm: () => void;
  isPending: boolean;
  error: string | null;
}

const DeleteCollectionDialog = ({
  isOpen, collectionName, onClose, onConfirm, isPending, error,
}: DeleteCollectionDialogProps) => (
  <ConfirmDialog
    isOpen={isOpen}
    title="컬렉션 삭제"
    description={
      <>
        &lsquo;{collectionName}&rsquo; 컬렉션을 삭제하시겠습니까?
        <br />
        <span className="text-red-500">이 작업은 되돌릴 수 없습니다.</span>
      </>
    }
    confirmLabel="삭제"
    variant="danger"
    onClose={onClose}
    onConfirm={onConfirm}
    isPending={isPending}
    error={error}
  />
);

export default DeleteCollectionDialog;
```

### 5.2 DocumentTable 체크박스 + 일괄 삭제 UI

#### 체크박스 상태 관리 (로컬 useState)

```typescript
const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

const toggleSelect = (id: string) =>
  setSelectedIds((prev) => {
    const next = new Set(prev);
    next.has(id) ? next.delete(id) : next.add(id);
    return next;
  });

const toggleSelectAll = () =>
  setSelectedIds((prev) =>
    prev.size === documents.length
      ? new Set()
      : new Set(documents.map((d) => d.document_id))
  );

const clearSelection = () => setSelectedIds(new Set());
```

#### 테이블 레이아웃 변경

```
기존:
| 파일명 | 카테고리 | 상태 | 청크 | 삭제 |

변경 후:
| ☐ | 파일명 | 카테고리 | 상태 | 청크 | 삭제 |
```

- thead 첫 번째 열: 전체 선택 체크박스
- tbody 각 행 첫 번째 열: 개별 선택 체크박스

#### 일괄 삭제 바 (선택 시 테이블 상단에 표시)

```
┌─────────────────────────────────────────────────────┐
│  ☑ 3건 선택됨           [ 선택 해제 ]  [ 🗑 삭제 ]  │
└─────────────────────────────────────────────────────┘
```

선택된 문서가 1건 이상이면 테이블 상단에 일괄 삭제 바가 나타난다.

#### 삭제 확인 다이얼로그 사용

**단건 삭제**:
```tsx
<ConfirmDialog
  title="문서 삭제"
  description={<>&lsquo;{filename}&rsquo; 문서를 삭제하시겠습니까?<br/><span className="text-red-500">이 작업은 되돌릴 수 없습니다.</span></>}
  confirmLabel="삭제"
  variant="danger"
  ...
/>
```

**일괄 삭제**:
```tsx
<ConfirmDialog
  title="문서 일괄 삭제"
  description={<>{selectedIds.size}건의 문서를 삭제하시겠습니까?<br/><span className="text-red-500">이 작업은 되돌릴 수 없습니다.</span></>}
  confirmLabel={`${selectedIds.size}건 삭제`}
  variant="danger"
  ...
/>
```

### 5.3 DocumentTable Props 변경

```typescript
// 기존 props 유지 + 추가
interface DocumentTableProps {
  documents: DocumentSummary[];
  totalDocuments: number;
  offset: number;
  limit: number;
  isLoading: boolean;
  isError: boolean;
  selectedDocumentId: string | null;
  onSelect: (documentId: string) => void;
  onPageChange: (newOffset: number) => void;
  onRetry: () => void;
  // ── 추가 ──
  collectionName: string;  // 삭제 API 호출 시 필요
}
```

삭제 관련 상태(`selectedIds`, `deleteTarget`, mutation)는 **DocumentTable 내부**에서 관리한다.
`collectionName`만 외부에서 주입받는다.

### 5.4 User Flow

```
[단건 삭제]
행 끝 🗑 버튼 클릭 → ConfirmDialog('문서 삭제', 파일명) → 확인 → DELETE API → 목록 갱신

[일괄 삭제]
체크박스 선택 → 상단 삭제 바 표시 → '삭제' 버튼 클릭 → ConfirmDialog('일괄 삭제', N건) → 확인 → DELETE API → 목록 갱신 + 선택 초기화
```

---

## 6. Test Plan

### 6.1 Test Scope

| Type | Target | Tool |
|------|--------|------|
| Unit Test | `useDeleteDocument`, `useDeleteDocuments` 훅 | Vitest + MSW |
| Unit Test | `ConfirmDialog` 렌더링 및 인터랙션 | Vitest + RTL |
| Unit Test | `DocumentTable` 체크박스 및 삭제 플로우 | Vitest + RTL + user-event |

### 6.2 Test Cases

**ConfirmDialog**:
- [ ] `isOpen=false`일 때 렌더링되지 않음
- [ ] `isOpen=true`일 때 title, description 표시
- [ ] 확인 버튼 클릭 시 `onConfirm` 호출
- [ ] 취소 버튼 클릭 시 `onClose` 호출
- [ ] `isPending=true`일 때 스피너 표시 + 버튼 비활성화
- [ ] `error` 전달 시 에러 메시지 표시
- [ ] variant별 confirm 버튼 스타일 적용

**DocumentTable 삭제**:
- [ ] 체크박스 클릭 시 선택 상태 토글
- [ ] 전체 선택 체크박스 클릭 시 전체 선택/해제
- [ ] 선택된 문서 있을 때 일괄 삭제 바 표시
- [ ] 삭제 버튼 클릭 시 ConfirmDialog 표시
- [ ] 삭제 성공 시 선택 초기화

**MSW 핸들러 추가**:
```typescript
http.delete('*/api/v1/collections/:name/documents/:docId', () =>
  HttpResponse.json({ document_id: 'doc-1', ... })
),
http.delete('*/api/v1/collections/:name/documents', () =>
  HttpResponse.json({ total: 2, success_count: 2, ... })
),
```

---

## 7. Implementation Order

| 순서 | 파일 | 작업 | 의존성 |
|------|------|------|--------|
| 1 | `src/constants/api.ts` | 엔드포인트 상수 2개 추가 | 없음 |
| 2 | `src/types/collection.ts` | 삭제 관련 타입 4개 추가 | 없음 |
| 3 | `src/services/api/authClient.ts` | X-User-Id 헤더 주입 | authStore |
| 4 | `src/services/collectionService.ts` | `deleteDocument`, `deleteDocuments` 메서드 | 1, 2 |
| 5 | `src/hooks/useCollections.ts` | `useDeleteDocument`, `useDeleteDocuments` 훅 | 4 |
| 6 | `src/components/common/ConfirmDialog.tsx` | 공통 확인 다이얼로그 (신규) | 없음 |
| 7 | `src/components/collection/DeleteCollectionDialog.tsx` | ConfirmDialog 기반 리팩터링 | 6 |
| 8 | `src/components/collection/DocumentTable.tsx` | 체크박스 + 삭제 핸들러 + ConfirmDialog 연결 | 5, 6 |
| 9 | 테스트 파일들 | ConfirmDialog, DocumentTable, 훅 테스트 | 6, 7, 8 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-04-30 | Initial draft | 배상규 |
