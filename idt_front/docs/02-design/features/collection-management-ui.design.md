---
template: design
version: 1.0
feature: collection-management-ui
date: 2026-04-22
author: 배상규
project: idt_front
version_project: 0.0.0
---

# collection-management-ui Design Document

> **Summary**: 백엔드 Qdrant 컬렉션 관리 API(`/api/v1/collections`)를 프론트에 연결하여, 컬렉션 CRUD(목록/생성/삭제/이름변경)와 사용 이력 조회를 탭 기반 단일 페이지(`/collections`)로 제공한다.
>
> **Project**: idt_front
> **Version**: 0.0.0
> **Author**: 배상규
> **Date**: 2026-04-22
> **Status**: Draft
> **Planning Doc**: [collection-management-ui.plan.md](../../01-plan/features/collection-management-ui.plan.md)
> **Backend Ref**: `idt/src/api/routes/collection_router.py`

### Pipeline References

| Phase | Document | Status |
|-------|----------|--------|
| Phase 4 | Backend API (collection_router.py) | ✅ |
| Phase 6 | UI Integration (this design) | 🔄 |

---

## 1. Overview

### 1.1 Design Goals

- 백엔드 응답 스키마(snake_case)를 그대로 TypeScript 타입으로 수용한다 (별도 어댑터 불필요 — 스키마 자체가 단순).
- 컬렉션 목록·이력은 **TanStack Query 캐시**를 Single Source of Truth로 삼는다.
- 생성/삭제/이름변경 mutation 성공 시 `queryKeys.collections.all` 전체 invalidate로 일관된 동기화.
- 보호 컬렉션(`documents`)은 프론트에서 삭제/이름변경 버튼을 비활성화하여 UX 수준에서 차단.
- toast 알림 없이 인라인 상태 메시지로 피드백 (toast 라이브러리 미설치 상태).

### 1.2 Design Principles

- **Colocation**: `collection` 도메인의 타입/서비스/훅/컴포넌트를 각각의 관례 위치에 배치.
- **No Adapter**: 백엔드 응답이 이미 JSON-friendly snake_case이고 필드가 적으므로 별도 변환 레이어 없이 타입을 직접 매핑.
- **Optimistic-free**: CRUD 결과가 즉시 확인 가능한 규모이므로 낙관적 업데이트 없이 invalidate 후 refetch.
- **Progressive Enhancement**: 탭 전환 시 이력 데이터는 lazy load (컬렉션 탭이 기본 활성).

---

## 2. Architecture

### 2.1 Component Diagram

```
┌──────────────────────────────────────────────────────────────┐
│ Presentation (pages/CollectionPage)                          │
│   - CollectionTable / ActivityLogTable / Modals              │
└──────┬──────────────────────────────────────────────▲────────┘
       │ useCollections hooks                         │
       ▼                                              │
┌──────────────────────────────────────────────────────────────┐
│ Application Hooks (hooks/useCollections)                      │
│   - useCollectionList()                                      │
│   - useCollectionDetail(name)                                │
│   - useCreateCollection()                                    │
│   - useRenameCollection()                                    │
│   - useDeleteCollection()                                    │
│   - useActivityLogs(filters)                                 │
│   - useCollectionActivityLogs(name)                          │
└──────┬──────────────────────────────────────────────▲────────┘
       │ collectionService.*                          │
       ▼                                              │
┌──────────────────────────────────────────────────────────────┐
│ Service Layer (services/collectionService)                    │
│   - HTTP 호출 (apiClient)                                    │
└──────┬──────────────────────────────────────────────▲────────┘
       │ /api/v1/collections/*                        │
       ▼                                              │
┌──────────────────────────────────────────────────────────────┐
│ Backend (idt — collection_router.py)                         │
└──────────────────────────────────────────────────────────────┘
```

### 2.2 Data Flow

#### 2.2.1 컬렉션 목록 로드

```
CollectionPage mount
  → useCollectionList()
  → collectionService.getCollections()
  → GET /api/v1/collections
  → { collections: CollectionInfo[], total: number }
  → TanStack Query 캐시 → CollectionTable 렌더링
```

#### 2.2.2 컬렉션 생성

```
CreateCollectionModal onSubmit
  → useCreateCollection().mutate({ name, vector_size, distance })
  → POST /api/v1/collections
  → onSuccess: invalidateQueries(queryKeys.collections.all)
  → 모달 닫기 + 인라인 성공 메시지
  → onError: 에러 코드별 인라인 메시지 표시
```

#### 2.2.3 컬렉션 삭제

```
DeleteCollectionDialog onConfirm
  → useDeleteCollection().mutate(name)
  → DELETE /api/v1/collections/{name}
  → onSuccess: invalidateQueries(queryKeys.collections.all)
  → onError: 403(보호됨) / 404(없음) 메시지
```

#### 2.2.4 이력 조회

```
사용 이력 탭 클릭
  → useActivityLogs(filters) enabled=true
  → GET /api/v1/collections/activity-log?collection_name=...&limit=50&offset=0
  → ActivityLogTable 렌더링
  → 페이지네이션 클릭 → offset 변경 → refetch
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `useCollectionList` | `collectionService.getCollections`, `queryKeys.collections.list` | 목록 쿼리 |
| `useCreateCollection` | `collectionService.createCollection`, `queryKeys.collections.all` | 생성 + invalidate |
| `useRenameCollection` | `collectionService.renameCollection`, `queryKeys.collections.all` | 이름변경 + invalidate |
| `useDeleteCollection` | `collectionService.deleteCollection`, `queryKeys.collections.all` | 삭제 + invalidate |
| `useActivityLogs` | `collectionService.getActivityLogs`, `queryKeys.collections.activityLog` | 이력 목록 쿼리 |
| `CollectionPage` | 위 모든 훅 | 통합 오케스트레이션 |

---

## 3. Data Model

### 3.1 TypeScript 타입 (`src/types/collection.ts`)

```typescript
export interface CollectionInfo {
  name: string;
  vectors_count: number;
  points_count: number;
  status: string;
}

export interface CollectionConfig {
  vector_size: number;
  distance: string;
}

export interface CollectionDetail extends CollectionInfo {
  config: CollectionConfig;
}

export interface CollectionListResponse {
  collections: CollectionInfo[];
  total: number;
}

export interface CreateCollectionRequest {
  name: string;
  vector_size: number;
  distance: string;
}

export interface RenameCollectionRequest {
  new_name: string;
}

export interface CollectionMessageResponse {
  name: string;
  message: string;
}

export interface RenameCollectionResponse {
  old_name: string;
  new_name: string;
  message: string;
}

export interface ActivityLog {
  id: number;
  collection_name: string;
  action: string;
  user_id: string | null;
  detail: Record<string, unknown> | null;
  created_at: string;
}

export interface ActivityLogListResponse {
  logs: ActivityLog[];
  total: number;
  limit: number;
  offset: number;
}

export interface ActivityLogFilters {
  collection_name?: string;
  action?: string;
  user_id?: string;
  from_date?: string;
  to_date?: string;
  limit?: number;
  offset?: number;
}

export const PROTECTED_COLLECTIONS = ['documents'] as const;

export const DISTANCE_METRICS = ['Cosine', 'Euclid', 'Dot'] as const;
export type DistanceMetric = (typeof DISTANCE_METRICS)[number];

export const COLLECTION_STATUS_MAP = {
  green: { label: '정상', color: 'bg-emerald-400' },
  yellow: { label: '최적화 중', color: 'bg-yellow-400' },
  red: { label: '오류', color: 'bg-red-400' },
} as const;
```

### 3.2 Cache Key 전략

```typescript
// src/lib/queryKeys.ts 확장
collections: {
  all: ['collections'] as const,
  list: () => [...queryKeys.collections.all, 'list'] as const,
  detail: (name: string) =>
    [...queryKeys.collections.all, 'detail', name] as const,
  activityLog: (filters?: ActivityLogFilters) =>
    [...queryKeys.collections.all, 'activityLog', filters] as const,
  collectionActivityLog: (name: string) =>
    [...queryKeys.collections.all, 'collectionActivityLog', name] as const,
},
```

---

## 4. API Specification (Frontend Side)

### 4.1 Endpoint Constants (`src/constants/api.ts` 추가)

```typescript
// Collections (COLLECTION-MGMT)
COLLECTIONS: '/api/v1/collections',
COLLECTION_DETAIL: (name: string) => `/api/v1/collections/${name}`,
COLLECTION_RENAME: (name: string) => `/api/v1/collections/${name}`,
COLLECTION_DELETE: (name: string) => `/api/v1/collections/${name}`,
COLLECTION_ACTIVITY_LOG: '/api/v1/collections/activity-log',
COLLECTION_ACTIVITY_LOG_BY_NAME: (name: string) =>
  `/api/v1/collections/${name}/activity-log`,
```

### 4.2 Service Methods (`src/services/collectionService.ts`)

```typescript
import { apiClient } from './api/client';
import { API_ENDPOINTS } from '@/constants/api';
import type {
  CollectionListResponse,
  CollectionDetail,
  CreateCollectionRequest,
  RenameCollectionRequest,
  CollectionMessageResponse,
  RenameCollectionResponse,
  ActivityLogListResponse,
  ActivityLogFilters,
} from '@/types/collection';

export const collectionService = {
  getCollections: async (): Promise<CollectionListResponse> => {
    const res = await apiClient.get<CollectionListResponse>(
      API_ENDPOINTS.COLLECTIONS,
    );
    return res.data;
  },

  getCollection: async (name: string): Promise<CollectionDetail> => {
    const res = await apiClient.get<CollectionDetail>(
      API_ENDPOINTS.COLLECTION_DETAIL(name),
    );
    return res.data;
  },

  createCollection: async (
    data: CreateCollectionRequest,
  ): Promise<CollectionMessageResponse> => {
    const res = await apiClient.post<CollectionMessageResponse>(
      API_ENDPOINTS.COLLECTIONS,
      data,
    );
    return res.data;
  },

  renameCollection: async (
    name: string,
    data: RenameCollectionRequest,
  ): Promise<RenameCollectionResponse> => {
    const res = await apiClient.patch<RenameCollectionResponse>(
      API_ENDPOINTS.COLLECTION_RENAME(name),
      data,
    );
    return res.data;
  },

  deleteCollection: async (
    name: string,
  ): Promise<CollectionMessageResponse> => {
    const res = await apiClient.delete<CollectionMessageResponse>(
      API_ENDPOINTS.COLLECTION_DELETE(name),
    );
    return res.data;
  },

  getActivityLogs: async (
    params: ActivityLogFilters,
  ): Promise<ActivityLogListResponse> => {
    const res = await apiClient.get<ActivityLogListResponse>(
      API_ENDPOINTS.COLLECTION_ACTIVITY_LOG,
      { params },
    );
    return res.data;
  },

  getCollectionActivityLogs: async (
    name: string,
    params?: { limit?: number; offset?: number },
  ): Promise<ActivityLogListResponse> => {
    const res = await apiClient.get<ActivityLogListResponse>(
      API_ENDPOINTS.COLLECTION_ACTIVITY_LOG_BY_NAME(name),
      { params },
    );
    return res.data;
  },
};
```

### 4.3 Hooks (`src/hooks/useCollections.ts`)

```typescript
import { useQuery, useMutation } from '@tanstack/react-query';
import { collectionService } from '@/services/collectionService';
import { queryClient } from '@/lib/queryClient';
import { queryKeys } from '@/lib/queryKeys';
import type {
  CreateCollectionRequest,
  ActivityLogFilters,
} from '@/types/collection';

export const useCollectionList = () =>
  useQuery({
    queryKey: queryKeys.collections.list(),
    queryFn: collectionService.getCollections,
  });

export const useCollectionDetail = (name: string) =>
  useQuery({
    queryKey: queryKeys.collections.detail(name),
    queryFn: () => collectionService.getCollection(name),
    enabled: !!name,
  });

export const useCreateCollection = () =>
  useMutation({
    mutationFn: (data: CreateCollectionRequest) =>
      collectionService.createCollection(data),
    onSuccess: () =>
      queryClient.invalidateQueries({
        queryKey: queryKeys.collections.all,
      }),
  });

export const useRenameCollection = () =>
  useMutation({
    mutationFn: ({ name, newName }: { name: string; newName: string }) =>
      collectionService.renameCollection(name, { new_name: newName }),
    onSuccess: () =>
      queryClient.invalidateQueries({
        queryKey: queryKeys.collections.all,
      }),
  });

export const useDeleteCollection = () =>
  useMutation({
    mutationFn: (name: string) => collectionService.deleteCollection(name),
    onSuccess: () =>
      queryClient.invalidateQueries({
        queryKey: queryKeys.collections.all,
      }),
  });

export const useActivityLogs = (
  filters: ActivityLogFilters,
  options?: { enabled?: boolean },
) =>
  useQuery({
    queryKey: queryKeys.collections.activityLog(filters),
    queryFn: () => collectionService.getActivityLogs(filters),
    enabled: options?.enabled ?? true,
  });

export const useCollectionActivityLogs = (name: string) =>
  useQuery({
    queryKey: queryKeys.collections.collectionActivityLog(name),
    queryFn: () => collectionService.getCollectionActivityLogs(name),
    enabled: !!name,
  });
```

### 4.4 Invalidation Policy

| Trigger | Invalidated Keys | 목적 |
|---------|------------------|------|
| `useCreateCollection.onSuccess` | `queryKeys.collections.all` | 목록 + 이력 갱신 |
| `useRenameCollection.onSuccess` | `queryKeys.collections.all` | 목록 + 이력 갱신 |
| `useDeleteCollection.onSuccess` | `queryKeys.collections.all` | 목록 + 이력 갱신 |

> 모든 mutation은 `collections.all` 전체를 invalidate하여 목록과 이력이 동시에 갱신된다.

---

## 5. UI/UX Design

### 5.1 페이지 구조

```
/collections (CollectionPage)
┌─────────────────────────────────────────────────────────────┐
│  헤더: "컬렉션 관리"                                         │
│  ┌──────────────┐ ┌──────────────┐                          │
│  │ 컬렉션 관리  │ │  사용 이력   │  ← 탭                    │
│  └──────────────┘ └──────────────┘                          │
├─────────────────────────────────────────────────────────────┤
│  [컬렉션 관리 탭]                                            │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  [+ 새 컬렉션]  [↻ 새로고침]                             ││
│  │                                                         ││
│  │  ┌──────┬──────┬──────┬──────┬──────────────┐          ││
│  │  │ Name │ Vec. │ Pts. │Status│   Actions    │          ││
│  │  ├──────┼──────┼──────┼──────┼──────────────┤          ││
│  │  │ docs │  150 │  150 │  🟢  │ 보호됨 뱃지  │          ││
│  │  │ test │   50 │   50 │  🟢  │ [이름변경][삭제]│        ││
│  │  └──────┴──────┴──────┴──────┴──────────────┘          ││
│  └─────────────────────────────────────────────────────────┘│
│                                                             │
│  [사용 이력 탭]                                              │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  Filters: [컬렉션 ▼] [액션 ▼] [사용자] [날짜범위]       ││
│  │                                                         ││
│  │  ┌──┬──────┬────────┬──────┬──────┬──────────────┐     ││
│  │  │# │Coll. │ Action │ User │Detail│     Time     │     ││
│  │  ├──┼──────┼────────┼──────┼──────┼──────────────┤     ││
│  │  │1 │ docs │ CREATE │ sys  │  {}  │ 04-22 10:00  │     ││
│  │  └──┴──────┴────────┴──────┴──────┴──────────────┘     ││
│  │                                                         ││
│  │  < 1 2 3 ... >  ← 페이지네이션                          ││
│  └─────────────────────────────────────────────────────────┘│
│                                                             │
│  CreateCollectionModal (오버레이)                             │
│  RenameCollectionModal (오버레이)                             │
│  DeleteCollectionDialog (오버레이)                            │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 상태별 렌더링

#### CollectionTable

| 상태 | 표시 |
|------|------|
| `isLoading` | 3행 스켈레톤 (회색 펄스 블록) |
| `isError` | "컬렉션을 불러올 수 없습니다" + [다시 시도] 버튼 |
| `data.collections.length === 0` | "등록된 컬렉션이 없습니다" 빈 상태 |
| 정상 | 테이블 렌더링 |

#### ActivityLogTable

| 상태 | 표시 |
|------|------|
| `isLoading` | 스켈레톤 |
| `isError` | 에러 메시지 + 재시도 |
| `data.logs.length === 0` | "이력이 없습니다" |
| 정상 | 테이블 + 페이지네이션 |

### 5.3 컬렉션 상태 뱃지

| Backend `status` | 표시 |
|-----------------|------|
| `green` | `🟢 정상` (bg-emerald-400 원 + 텍스트) |
| `yellow` | `🟡 최적화 중` (bg-yellow-400) |
| `red` | `🔴 오류` (bg-red-400) |

### 5.4 보호 컬렉션 처리

- `PROTECTED_COLLECTIONS` 배열에 포함된 이름은 Actions 열에 삭제/이름변경 버튼 대신 `보호됨` 뱃지 표시.
- 뱃지 스타일: `text-[11.5px] font-semibold text-violet-500 bg-violet-50 px-2 py-0.5 rounded-md`

### 5.5 모달/다이얼로그 상세

#### CreateCollectionModal

| 필드 | 타입 | 기본값 | 검증 |
|------|------|--------|------|
| `name` | text input | `""` | 필수, 영숫자/`_`/`-`만 허용 |
| `vector_size` | number input | `1536` | 필수, >= 1 |
| `distance` | select | `"Cosine"` | `Cosine` / `Euclid` / `Dot` |

- 제출 중: 버튼 비활성 + 스피너
- 성공: 모달 닫기
- 409: "이미 존재하는 컬렉션입니다" (인라인 에러)
- 422: "유효하지 않은 이름입니다" (인라인 에러)

#### RenameCollectionModal

| 필드 | 타입 | 기본값 | 검증 |
|------|------|--------|------|
| `new_name` | text input | `""` | 필수, 현재 이름과 다름 |

- 현재 이름을 모달 상단에 표시: `"{name}" → 새 이름:`
- 성공: 모달 닫기
- 404/422: 인라인 에러

#### DeleteCollectionDialog

- 확인 메시지: `"'{name}' 컬렉션을 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다."`
- 삭제 버튼: `hover:bg-red-50 hover:text-red-500` 스타일
- 403: "보호된 컬렉션은 삭제할 수 없습니다" (인라인 에러)

### 5.6 이력 테이블 상세

- **Action 뱃지 색상**:
  - `CREATE` → `bg-emerald-50 text-emerald-600`
  - `DELETE` → `bg-red-50 text-red-600`
  - `SEARCH` → `bg-blue-50 text-blue-600`
  - `RENAME` → `bg-amber-50 text-amber-600`
  - 기타 → `bg-zinc-100 text-zinc-600`

- **Detail 컬럼**: JSON 축약 표시 (최대 50자), hover 시 전체 JSON 표시 (title 속성 또는 popover)
- **Time 컬럼**: `formatRelativeTime()` 사용 (유틸 기존 포맷터 활용)
- **페이지네이션**: limit=50 고정, offset 기반. 이전/다음 버튼 + 현재 페이지 표시

### 5.7 Component List

| Component | Location | 역할 |
|-----------|----------|------|
| `CollectionPage` | `src/pages/CollectionPage/index.tsx` | 탭 기반 메인 페이지 |
| `CollectionTable` | `src/components/collection/CollectionTable.tsx` | 목록 테이블 + 로딩/에러/빈 상태 |
| `ActivityLogTable` | `src/components/collection/ActivityLogTable.tsx` | 이력 테이블 + 페이지네이션 |
| `ActivityLogFilters` | `src/components/collection/ActivityLogFilters.tsx` | 필터 입력 (컬렉션/액션/사용자/날짜) |
| `CreateCollectionModal` | `src/components/collection/CreateCollectionModal.tsx` | 생성 폼 모달 |
| `RenameCollectionModal` | `src/components/collection/RenameCollectionModal.tsx` | 이름변경 모달 |
| `DeleteCollectionDialog` | `src/components/collection/DeleteCollectionDialog.tsx` | 삭제 확인 다이얼로그 |

### 5.8 디자인 시스템 적용 (CLAUDE.md 준수)

| 요소 | 적용 스타일 |
|------|------------|
| 페이지 타이틀 | `text-3xl font-bold tracking-tight text-zinc-900` |
| 탭 활성 | `border-b-2 border-violet-500 text-violet-600 font-semibold` |
| 탭 비활성 | `text-zinc-400 hover:text-zinc-600` |
| Primary 버튼 | `rounded-xl bg-violet-600 px-4 py-2.5 text-[13.5px] font-medium text-white shadow-sm hover:bg-violet-700 active:scale-95 transition-all` |
| Secondary 버튼 | `rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-2.5 text-[13.5px] font-medium text-zinc-600 hover:border-zinc-300 hover:bg-zinc-100 transition-all` |
| 삭제 버튼 | `rounded-xl border border-zinc-200 bg-white px-3 py-1.5 text-[12px] text-zinc-500 hover:bg-red-50 hover:text-red-500 hover:border-red-200 transition-all` |
| 테이블 헤더 | `text-[12px] font-semibold uppercase tracking-wider text-zinc-400 bg-zinc-50` |
| 테이블 셀 | `text-[13.5px] text-zinc-700 py-3 px-4` |
| 모달 오버레이 | `fixed inset-0 z-50 bg-black/50 flex items-center justify-center` |
| 모달 패널 | `rounded-2xl bg-white p-6 shadow-2xl w-full max-w-md` |
| 입력 필드 | `rounded-xl border border-zinc-300 px-4 py-2.5 text-[15px] text-zinc-900 placeholder-zinc-400 outline-none focus:border-violet-400 transition-all` |

---

## 6. Error Handling

### 6.1 Error Matrix

| Source | HTTP | UI 동작 | Fallback |
|--------|------|---------|----------|
| `useCollectionList` 500 | 500 | 에러 배너 + "다시 시도" 버튼 | 이전 캐시 |
| `useCreateCollection` 409 | 409 | 모달 내 인라인 에러: "이미 존재하는 컬렉션" | 모달 유지 |
| `useCreateCollection` 422 | 422 | 모달 내 인라인 에러: "유효하지 않은 이름" | 모달 유지 |
| `useDeleteCollection` 403 | 403 | 인라인 에러: "보호된 컬렉션" | 다이얼로그 유지 |
| `useDeleteCollection` 404 | 404 | 인라인 에러: "컬렉션을 찾을 수 없습니다" | 다이얼로그 닫기 + refetch |
| `useRenameCollection` 404 | 404 | 모달 내 인라인 에러 | 모달 유지 |
| `useRenameCollection` 422 | 422 | 모달 내 인라인 에러: "유효하지 않은 이름" | 모달 유지 |
| `useActivityLogs` 500 | 500 | 이력 탭 에러 배너 | 빈 상태 |
| 네트워크 오류 | - | 에러 배너 | - |

### 6.2 Mutation 에러 추출

```typescript
import { AxiosError } from 'axios';

const getErrorMessage = (error: unknown): string => {
  if (error instanceof AxiosError && error.response) {
    const { status, data } = error.response;
    if (status === 403) return '보호된 컬렉션은 삭제할 수 없습니다';
    if (status === 404) return '컬렉션을 찾을 수 없습니다';
    if (status === 409) return '이미 존재하는 컬렉션입니다';
    if (status === 422) return data?.detail ?? '유효하지 않은 입력입니다';
  }
  return '요청 처리 중 오류가 발생했습니다';
};
```

---

## 7. Security Considerations

- [x] CRUD 엔드포인트는 현재 인증 없이 접근 가능 (백엔드 정책). 향후 JWT 적용 시 `authClient`로 전환 필요.
- [x] XSS — 컬렉션 이름은 서버에서 영숫자/`_`/`-`만 허용하므로 XSS 위험 낮음. `detail` JSON은 `JSON.stringify`로 출력하되, `dangerouslySetInnerHTML` 사용 금지.
- [x] CSRF — axios 인스턴스의 공통 설정으로 대응 (기존 구조 유지).
- [x] 보호 컬렉션 — 프론트에서 UI 비활성화 + 서버에서 403 이중 보호.

---

## 8. Test Plan

### 8.1 Test Scope

| Type | Target | Tool |
|------|--------|------|
| Hook | `useCollectionList`, `useCreateCollection`, `useDeleteCollection`, `useRenameCollection`, `useActivityLogs` | Vitest + RTL + MSW |
| Component | `CollectionTable`, `CreateCollectionModal`, `DeleteCollectionDialog` | RTL + user-event + MSW |

### 8.2 Test Cases

#### 8.2.1 `useCollections.test.ts` (훅 테스트)

| # | 케이스 | Mock | 검증 |
|---|--------|------|------|
| C1 | `useCollectionList` — 목록 조회 성공 | MSW 200 (3 collections) | `data.collections.length === 3` |
| C2 | `useCollectionList` — 빈 목록 | MSW 200 collections: [] | `data.total === 0` |
| C3 | `useCollectionList` — 서버 에러 | MSW 500 | `isError === true` |
| C4 | `useCreateCollection` — 생성 성공 | MSW 201 | `data.message` 포함 |
| C5 | `useCreateCollection` — 409 충돌 | MSW 409 | `error.response.status === 409` |
| C6 | `useDeleteCollection` — 삭제 성공 | MSW 200 | `data.message` 포함 |
| C7 | `useDeleteCollection` — 403 보호됨 | MSW 403 | `error.response.status === 403` |
| C8 | `useRenameCollection` — 이름변경 성공 | MSW 200 | `data.new_name` 확인 |
| C9 | `useActivityLogs` — 이력 조회 | MSW 200 (5 logs) | `data.logs.length === 5`, `data.total === 5` |
| C10 | `useActivityLogs` — 필터 적용 | MSW 200 (filtered) | queryFn에 params 전달 확인 |

#### 8.2.2 컴포넌트 테스트 (선택적 P2)

| # | 시나리오 | 검증 |
|---|----------|------|
| U1 | CollectionTable — 보호 컬렉션은 삭제 버튼 없음 | `queryByRole('button', { name: /삭제/ })` 없음 |
| U2 | CreateCollectionModal — 유효한 입력 시 제출 가능 | submit 버튼 활성화 |
| U3 | DeleteCollectionDialog — 확인 클릭 시 onConfirm 호출 | `expect(onConfirm).toHaveBeenCalled()` |

### 8.3 MSW Handlers 확장

```typescript
// src/__tests__/mocks/handlers.ts 추가

// Collections
http.get(`*${API_ENDPOINTS.COLLECTIONS}`, () =>
  HttpResponse.json({
    collections: [
      { name: 'documents', vectors_count: 150, points_count: 150, status: 'green' },
      { name: 'test-collection', vectors_count: 50, points_count: 50, status: 'green' },
      { name: 'embeddings', vectors_count: 200, points_count: 200, status: 'green' },
    ],
    total: 3,
  }),
),

http.post(`*${API_ENDPOINTS.COLLECTIONS}`, async ({ request }) => {
  const body = (await request.json()) as { name: string };
  return HttpResponse.json(
    { name: body.name, message: 'Collection created successfully' },
    { status: 201 },
  );
}),

http.delete(`*/api/v1/collections/:name`, ({ params }) => {
  if (params.name === 'documents') {
    return HttpResponse.json(
      { detail: 'Cannot delete protected collection' },
      { status: 403 },
    );
  }
  return HttpResponse.json({
    name: params.name,
    message: 'Collection deleted successfully',
  });
}),

http.patch(`*/api/v1/collections/:name`, async ({ params, request }) => {
  const body = (await request.json()) as { new_name: string };
  return HttpResponse.json({
    old_name: params.name,
    new_name: body.new_name,
    message: 'Collection alias updated successfully',
  });
}),

http.get(`*${API_ENDPOINTS.COLLECTION_ACTIVITY_LOG}`, () =>
  HttpResponse.json({
    logs: [
      {
        id: 1,
        collection_name: 'documents',
        action: 'CREATE',
        user_id: 'system',
        detail: null,
        created_at: '2026-04-22T10:00:00Z',
      },
    ],
    total: 1,
    limit: 50,
    offset: 0,
  }),
),
```

---

## 9. Clean Architecture

### 9.1 Layer Assignment

| Layer | Responsibility | 이번 기능 매핑 |
|-------|---------------|----------------|
| **Presentation** | UI + 사용자 상호작용 | `pages/CollectionPage`, `components/collection/*` |
| **Application** | Orchestration (훅) | `hooks/useCollections.ts` |
| **Domain** | 타입/모델 | `types/collection.ts` |
| **Infrastructure** | HTTP / 캐시 | `services/collectionService.ts`, `lib/queryKeys.ts` |

### 9.2 Import Rules Compliance

| From | To | 허용 여부 |
|------|------|----------|
| `pages/CollectionPage` → `hooks/useCollections` | Presentation → Application | ✅ |
| `hooks/useCollections` → `services/collectionService` | Application → Infrastructure | ✅ |
| `services/collectionService` → `types/collection` | Infrastructure → Domain | ✅ |
| `components/collection/*` → `services/*` | Presentation → Infrastructure **직접** | ❌ (금지, 훅 경유) |

---

## 10. Coding Convention Reference

### 10.1 이번 기능 적용 컨벤션

| Item | Convention Applied |
|------|-------------------|
| 타입 네이밍 | `CollectionInfo`, `CollectionListResponse`, `ActivityLog` — 도메인 모델은 접미사 없음, API 응답은 `Response` 접미사 |
| queryKey 확장 | `queryKeys.collections.list()`, `queryKeys.collections.activityLog(filters)` |
| 훅 명명 | `useCollectionList`, `useCreateCollection`, `useActivityLogs` |
| 서비스 구조 | `collectionService` 객체에 메서드 모음 |
| 파일 명명 | `collectionService.ts`, `useCollections.ts`, `collection.ts` (camelCase) |
| 컴포넌트 명명 | `CollectionTable.tsx`, `CreateCollectionModal.tsx` (PascalCase) |
| 테스트 위치 | `src/hooks/useCollections.test.ts` (소스 옆), MSW는 `src/__tests__/mocks/handlers.ts` |

### 10.2 Import Order

```typescript
// 1. 외부 라이브러리
import { useQuery, useMutation } from '@tanstack/react-query';
import { useState } from 'react';

// 2. 내부 절대 경로
import { collectionService } from '@/services/collectionService';
import { queryKeys } from '@/lib/queryKeys';
import { queryClient } from '@/lib/queryClient';

// 3. 타입
import type { CollectionInfo, ActivityLogFilters } from '@/types/collection';
```

---

## 11. Implementation Guide

### 11.1 변경 파일 목록

#### 신규 파일 (10개)

| 파일 | 역할 |
|------|------|
| `src/types/collection.ts` | TypeScript 타입 정의 |
| `src/services/collectionService.ts` | API 호출 서비스 |
| `src/hooks/useCollections.ts` | TanStack Query 훅 (7개) |
| `src/hooks/useCollections.test.ts` | 훅 단위 테스트 |
| `src/components/collection/CollectionTable.tsx` | 목록 테이블 |
| `src/components/collection/ActivityLogTable.tsx` | 이력 테이블 |
| `src/components/collection/ActivityLogFilters.tsx` | 필터 UI |
| `src/components/collection/CreateCollectionModal.tsx` | 생성 모달 |
| `src/components/collection/RenameCollectionModal.tsx` | 이름변경 모달 |
| `src/components/collection/DeleteCollectionDialog.tsx` | 삭제 확인 |

#### 수정 파일 (5개)

| 파일 | 변경 내용 |
|------|----------|
| `src/constants/api.ts` | `COLLECTIONS` 외 6개 엔드포인트 상수 추가 |
| `src/lib/queryKeys.ts` | `collections` 도메인 키 추가 |
| `src/pages/CollectionPage/index.tsx` | 신규 — 탭 기반 메인 페이지 |
| `src/App.tsx` | `/collections` 라우트 추가 |
| `src/components/layout/TopNav.tsx` | 네비게이션 링크 추가 |
| `src/__tests__/mocks/handlers.ts` | Collections MSW 핸들러 추가 |

### 11.2 TDD 구현 순서

```
Phase 1: 기반 (Red → Green)
  1. Red  — useCollections.test.ts: C1~C3 (목록 조회 케이스) 작성 → vitest 실패
  2. Green — types/collection.ts 작성
           → constants/api.ts 엔드포인트 추가
           → lib/queryKeys.ts collections 추가
           → services/collectionService.ts 작성
           → hooks/useCollections.ts useCollectionList 구현
           → __tests__/mocks/handlers.ts MSW 핸들러 추가
           → vitest C1~C3 통과

Phase 2: Mutation (Red → Green)
  3. Red  — C4~C8 (생성/삭제/이름변경 케이스) 작성
  4. Green — useCreateCollection, useDeleteCollection, useRenameCollection 구현
           → MSW 핸들러 추가
           → vitest C4~C8 통과

Phase 3: 이력 (Red → Green)
  5. Red  — C9~C10 (이력 조회 케이스) 작성
  6. Green — useActivityLogs 구현 → vitest C9~C10 통과

Phase 4: UI 컴포넌트
  7. CollectionTable.tsx — 목록 테이블 + 보호 뱃지 + 상태 표시
  8. CreateCollectionModal.tsx — 생성 폼
  9. RenameCollectionModal.tsx — 이름변경 폼
  10. DeleteCollectionDialog.tsx — 삭제 확인
  11. ActivityLogFilters.tsx — 필터 UI
  12. ActivityLogTable.tsx — 이력 테이블 + 페이지네이션

Phase 5: 페이지 + 라우팅
  13. CollectionPage/index.tsx — 탭 기반 페이지 조립
  14. App.tsx — /collections 라우트 추가
  15. TopNav.tsx — 네비게이션 링크 추가

Phase 6: 수동 검증
  16. npm run type-check + npm run lint + npm run test:run
  17. npm run dev → /collections 접속 → 목록/생성/삭제/이름변경/이력 확인
```

---

## 12. Definition of Done

- [ ] `src/types/collection.ts` — 모든 타입 정의 완료
- [ ] `src/constants/api.ts` — 6개 엔드포인트 상수 추가
- [ ] `src/lib/queryKeys.ts` — collections 도메인 키 추가
- [ ] `src/services/collectionService.ts` — 7개 메서드 구현
- [ ] `src/hooks/useCollections.ts` — 7개 훅 구현
- [ ] `src/hooks/useCollections.test.ts` — 10개 테스트 통과
- [ ] 6개 컴포넌트 구현 (CollectionTable, ActivityLogTable, ActivityLogFilters, CreateCollectionModal, RenameCollectionModal, DeleteCollectionDialog)
- [ ] `src/pages/CollectionPage/index.tsx` — 탭 기반 메인 페이지
- [ ] `src/App.tsx` — `/collections` 라우트 추가
- [ ] `src/components/layout/TopNav.tsx` — 네비게이션 링크 추가
- [ ] `src/__tests__/mocks/handlers.ts` — MSW 핸들러 추가
- [ ] `npm run type-check`, `npm run lint`, `npm run test:run` 통과
- [ ] `npm run build` 성공
- [ ] 보호 컬렉션(`documents`)에 삭제/이름변경 버튼이 표시되지 않음
- [ ] 백엔드 로컬 기동 후 수동 E2E 검증 완료

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-04-22 | Initial design — Plan 기반 설계 (타입/서비스/훅/UI/테스트 매핑) | 배상규 |
