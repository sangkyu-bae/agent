# collection-permission-management Gap Analysis

> **Feature**: 컬렉션 권한 관리 (Scope 기반 접근 제어)
> **Date**: 2026-04-23
> **Match Rate**: **100%** (Iteration 1 후 76% → 100%)
> **Design Doc**: `docs/02-design/features/collection-permission-management.design.md`

---

## 1. Summary

| Category | Items | Matched | Rate |
|----------|-------|---------|------|
| Implementation (타입/상수/서비스/훅/UI) | 8 | 8 | 100% |
| Test Cases | 9 | 9 | 100% |
| Error Handling (에러→UX 매핑) | 6 | 6 | 100% |
| Security | 4 | 4 | 100% |
| **Weighted Total** | — | — | **100%** |

---

## 2. Implementation Checklist

### Phase 1: 기반 (타입, 상수, 서비스)

| # | Item | File | Status |
|---|------|------|--------|
| 1 | `CollectionScope`, `COLLECTION_SCOPES`, `SCOPE_LABELS` | `src/types/collection.ts` | ✅ |
| 2 | `CollectionInfo` + `scope`, `owner_id` | `src/types/collection.ts` | ✅ |
| 3 | `CreateCollectionRequest` + `scope`, `department_id` | `src/types/collection.ts` | ✅ |
| 4 | `UpdateScopeRequest`, `UpdateScopeResponse` | `src/types/collection.ts` | ✅ |
| 5 | `COLLECTION_PERMISSION` endpoint | `src/constants/api.ts` | ✅ |
| 6 | `apiClient` → `authApiClient` 전환 | `src/services/collectionService.ts` | ✅ |
| 7 | `updateScope()` 메서드 | `src/services/collectionService.ts` | ✅ |

### Phase 2: 훅

| # | Item | File | Status |
|---|------|------|--------|
| 8 | `useUpdateScope` mutation | `src/hooks/useCollections.ts` | ✅ |

### Phase 3: UI 컴포넌트

| # | Item | File | Status |
|---|------|------|--------|
| 9 | Scope 컬럼 + ScopeBadge | `CollectionTable.tsx` | ✅ |
| 10 | `canManage` 로직 + 권한변경 버튼 | `CollectionTable.tsx` | ✅ |
| 11 | Scope 라디오 + department_id 조건부 입력 | `CreateCollectionModal.tsx` | ✅ |
| 12 | UpdateScopeModal (신규) | `UpdateScopeModal.tsx` | ✅ |
| 13 | `useUpdateScope` 연동 + scopeTarget 상태 | `CollectionPage/index.tsx` | ✅ |

### Phase 4: 테스트

| # | Item | File | Status |
|---|------|------|--------|
| 14 | 기존 CreateCollectionModal 테스트 유지 | `CreateCollectionModal.test.tsx` | ✅ |
| 15 | scope=PERSONAL → department_id 미전송 | `CreateCollectionModal.test.tsx` | ✅ |
| 16 | scope=DEPARTMENT → department_id 필드 표시 & 검증 | `CreateCollectionModal.test.tsx` | ✅ (Iter1) |
| 17 | scope 배지 PERSONAL/DEPARTMENT/PUBLIC 렌더링 | `CollectionTable.test.tsx` | ✅ (Iter1) |
| 18 | `canManage=false` 액션 버튼 미표시 | `CollectionTable.test.tsx` | ✅ (Iter1) |
| 19 | `canManage=true` [이름변경][권한변경][삭제] 표시 | `CollectionTable.test.tsx` | ✅ (Iter1) |
| 20 | UpdateScopeModal: scope 선택 → 제출 | `UpdateScopeModal.test.tsx` | ✅ (Iter1) |
| 21 | UpdateScopeModal: 에러 상태 표시 | `UpdateScopeModal.test.tsx` | ✅ (Iter1) |
| 22 | scope 미설정(legacy) → 대시(—) 표시 | `CollectionTable.test.tsx` | ✅ (Iter1) |

### Phase 5: 에러 매핑

| # | Item | File | Status |
|---|------|------|--------|
| 23 | `ApiError` 클래스 (status 보존) | `src/services/api/ApiError.ts` | ✅ (Iter1) |
| 24 | `authApiClient` interceptor → `ApiError` 사용 | `src/services/api/authClient.ts` | ✅ (Iter1) |
| 25 | `getMutationError` HTTP 코드별 한국어 매핑 | `CollectionPage/index.tsx` | ✅ (Iter1) |
| 26 | `getScopeError` scope 전용 403 메시지 | `CollectionPage/index.tsx` | ✅ (Iter1) |
| 27 | `useUpdateScope` 훅 테스트 (성공/403) | `useCollections.test.ts` | ✅ (Iter1) |

---

## 3. Iteration History

### Iteration 1 (2026-04-23)

**Before**: Match Rate 76% | **After**: Match Rate 100%

**Changes Made**:

| File | Change |
|------|--------|
| `src/services/api/ApiError.ts` | 신규 — HTTP status 보존하는 커스텀 Error 클래스 |
| `src/services/api/authClient.ts` | `ApiError` import + interceptor에서 `ApiError` 사용 |
| `src/pages/CollectionPage/index.tsx` | `COLLECTION_ERROR_MAP` + `getMutationError`/`getScopeError` 개선 |
| `src/__tests__/mocks/handlers.ts` | collections 응답에 scope/owner_id 추가 + permission 핸들러 |
| `src/hooks/useCollections.test.ts` | `useUpdateScope` 성공/403 테스트 2건 추가 |
| `src/components/collection/CollectionTable.test.tsx` | 신규 — 7개 테스트 (scope 배지, canManage, 보호 컬렉션) |
| `src/components/collection/UpdateScopeModal.test.tsx` | 신규 — 6개 테스트 (scope 선택, 제출, 에러, DEPARTMENT) |
| `src/components/collection/CreateCollectionModal.test.tsx` | scope=DEPARTMENT 테스트 1건 추가 |

**Test Results**: 35/35 passed, TypeScript type check clean.

---

## 4. Final Match Summary

```
[Plan] ✅ → [Design] ✅ → [Do] ✅ → [Check] ✅ 100% → [Report] ⏳
```

### Weighted Scoring

| Category | Weight | Score | Weighted |
|----------|--------|-------|----------|
| Implementation (타입/상수/서비스/훅/UI) | 70% | 100% | 70.0 |
| Tests | 20% | 100% | 20.0 |
| Error Handling | 10% | 100% | 10.0 |
| **Total** | **100%** | — | **100%** |

> Match Rate >= 90% → `/pdca report collection-permission-management` 권장
