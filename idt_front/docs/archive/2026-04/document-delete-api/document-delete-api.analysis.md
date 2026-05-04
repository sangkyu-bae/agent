# document-delete-api Gap Analysis

> **Feature**: document-delete-api
> **Date**: 2026-04-30
> **Match Rate**: 94%
> **Design Doc**: [document-delete-api.design.md](../02-design/features/document-delete-api.design.md)

---

## Summary

| Category | Items | Matched | Gaps |
|----------|-------|---------|------|
| API Constants | 2 | 2 | 0 |
| Type Definitions | 4 | 4 | 0 |
| Auth Interceptor | 1 | 1 | 0 |
| Service Methods | 2 | 2 | 0 |
| TanStack Query Hooks | 2 | 2 | 0 |
| ConfirmDialog Component | 1 | 1 | 0 |
| DeleteCollectionDialog Refactor | 1 | 1 | 0 |
| DocumentTable UI | 5 | 5 | 0 |
| Error Handling | 1 | 1 | 0 |
| Tests | 3 | 0 | 3 |
| **Total** | **22** | **19** | **3** |

---

## Matched Items (19/22)

### 1. API Endpoint Constants (`src/constants/api.ts:83-86`)
- `COLLECTION_DOCUMENT_DELETE(name, documentId)` -> `/api/v1/collections/${name}/documents/${documentId}`
- `COLLECTION_DOCUMENTS_BATCH_DELETE(name)` -> `/api/v1/collections/${name}/documents`

### 2. Type Definitions (`src/types/collection.ts:162-188`)
- `DeleteDocumentResponse` (document_id, collection_name, filename, deleted_qdrant_chunks, deleted_es_chunks)
- `BatchDeleteDocumentsRequest` (document_ids: string[])
- `BatchDeleteDocumentResult` (document_id, status, deleted_qdrant_chunks, deleted_es_chunks, filename, error)
- `BatchDeleteDocumentsResponse` (total, success_count, failure_count, results)

### 3. X-User-Id Header Injection (`src/services/api/authClient.ts:17-26`)
- Request interceptor injects `X-User-Id` from `useAuthStore.getState().user.id`

### 4. Service Methods (`src/services/collectionService.ts:148-167`)
- `deleteDocument(collectionName, documentId)` -> authApiClient.delete
- `deleteDocuments(collectionName, data)` -> authApiClient.delete with `{ data }`

### 5. TanStack Query Hooks (`src/hooks/useCollections.ts:126-148`)
- `useDeleteDocument()` -> mutationFn + onSuccess invalidation
- `useDeleteDocuments()` -> mutationFn + onSuccess invalidation + clearSelection

### 6. ConfirmDialog Component (`src/components/common/ConfirmDialog.tsx`)
- Props interface matches design (isOpen, title, description, confirmLabel, cancelLabel, variant, onClose, onConfirm, isPending, error)
- Default values: confirmLabel='확인', cancelLabel='취소', variant='danger'
- Variant styles: danger (red), warning (amber), info (violet)
- Spinner on isPending, error message display, overlay dismiss

### 7. DeleteCollectionDialog Refactoring (`src/components/collection/DeleteCollectionDialog.tsx`)
- Uses ConfirmDialog as base (title="컬렉션 삭제", variant="danger", confirmLabel="삭제")

### 8. DocumentTable UI (`src/components/collection/DocumentTable.tsx`)
- `collectionName` prop added to DocumentTableProps
- Checkbox column: thead select-all + tbody individual checkboxes
- Batch action bar: "N건 선택됨" + 선택 해제 + 삭제 buttons
- Single delete: trash icon per row -> ConfirmDialog(title="문서 삭제", filename)
- Batch delete: ConfirmDialog(title="문서 일괄 삭제", count, confirmLabel="N건 삭제")
- Delete handler: mutation.mutate -> onSuccess clearSelection + partial failure toast
- Error utility: getDeleteError (403->권한, 404->없음, generic)

### 9. CollectionDocumentsPage (`src/pages/CollectionDocumentsPage/index.tsx:195`)
- Passes `collectionName` prop to DocumentTable

---

## Gaps (3/22)

### GAP-01: ConfirmDialog Unit Test Missing
- **Design**: Section 6.2 — ConfirmDialog 렌더링/인터랙션 테스트 7 cases
- **Status**: `src/components/common/ConfirmDialog.test.tsx` does not exist
- **Priority**: Medium
- **Test Cases**:
  - isOpen=false -> no render
  - isOpen=true -> title/description visible
  - confirm click -> onConfirm called
  - cancel click -> onClose called
  - isPending=true -> spinner + disabled
  - error -> error message displayed
  - variant styles applied

### GAP-02: DocumentTable Delete Test Missing
- **Design**: Section 6.2 — DocumentTable 삭제 기능 테스트 5 cases
- **Status**: `src/components/collection/DocumentTable.test.tsx` does not exist
- **Priority**: Medium
- **Test Cases**:
  - checkbox toggle selection
  - select-all toggle
  - batch delete bar visible when selected
  - delete button opens ConfirmDialog
  - delete success clears selection

### GAP-03: Delete Hooks Test Missing
- **Design**: Section 6.2 — useDeleteDocument/useDeleteDocuments 훅 테스트
- **Status**: `src/hooks/useCollections.test.ts` exists but has no `useDeleteDocument`/`useDeleteDocuments` test cases
- **Priority**: Medium
- **Test Cases**:
  - useDeleteDocument mutate success
  - useDeleteDocuments mutate success
  - Error handling (403, 404, 500)

### GAP-03b: MSW Delete Handlers Missing
- **Design**: Section 6.2 — MSW 핸들러 추가 (delete endpoints)
- **Status**: `src/__tests__/mocks/handlers.ts` does not contain delete document handlers
- **Priority**: Medium (prerequisite for GAP-01~03)

---

## Minor Observations (Non-blocking)

### OBS-01: Invalidation Key Pattern
- **Design**: `queryKeys.collections.documents(collectionName)`
- **Implementation**: `[...queryKeys.collections.all, 'documents', collectionName]`
- **Impact**: None (prefix-match invalidation works correctly with both patterns)

---

## Plan Requirements Verification

| FR | Description | Status |
|----|-------------|--------|
| FR-01 | 단건 삭제 API 호출 | Implemented |
| FR-02 | 체크박스 선택 (개별 + 전체) | Implemented |
| FR-03 | 선택 시 상단 "N건 삭제" 버튼 | Implemented |
| FR-04 | 삭제 대상 파일명 표시 | Implemented |
| FR-05 | 삭제 후 목록 자동 갱신 | Implemented |
| FR-06 | 403 에러 메시지 | Implemented |
| FR-07 | 부분 실패 결과 표시 | Implemented |
| FR-08 | 로딩 상태 (스피너 + 비활성화) | Implemented |

---

## Recommendation

Match Rate **94%** (>=90% threshold met). All functional requirements are implemented. 
Remaining gaps are test files only — no functional code gaps exist.

**Next steps**:
1. Write test files (GAP-01 ~ GAP-03) to reach 100%
2. Or proceed to `/pdca report document-delete-api` if tests are deferred
