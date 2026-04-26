# collection-management-ui Plan Document

> **Feature**: Qdrant 컬렉션 관리 프론트엔드 UI
>
> **Project**: sangplusbot (idt_front)
> **Author**: 배상규
> **Date**: 2026-04-22
> **Status**: Draft
> **Backend Design Ref**: `idt/docs/02-design/features/qdrant-collection-management.design.md` Section 8

---

## 1. 개요

백엔드에 구현 완료된 Qdrant 컬렉션 관리 API(`/api/v1/collections`)에 대한 프론트엔드 UI를 구현한다.

### 1.1 목표

- 컬렉션 목록 조회 / 생성 / 삭제 / 이름 변경 UI
- 컬렉션 사용이력 조회 UI (필터 + 페이지네이션)
- 탭 기반 단일 페이지 (`/collections`)
- 기본 컬렉션(`documents`) 삭제 보호 표시

### 1.2 비목표 (Scope Out)

- 컬렉션 내 문서 관리 (기존 DocumentPage 담당)
- 벡터 검색 UI (기존 ChatPage에서 처리)
- 컬렉션 상세 설정 변경 (vector_size, distance 등은 생성 시에만)

---

## 2. 백엔드 API 계약

> 백엔드 구현 완료 상태. 모든 엔드포인트 테스트 통과 (55+ tests).

| Method | Endpoint | Description | Status Codes |
|--------|----------|-------------|--------------|
| GET | `/api/v1/collections` | 목록 조회 | 200 |
| GET | `/api/v1/collections/{name}` | 상세 조회 | 200, 404 |
| POST | `/api/v1/collections` | 생성 | 201, 409, 422 |
| PATCH | `/api/v1/collections/{name}` | 이름 변경 (alias) | 200, 404, 422 |
| DELETE | `/api/v1/collections/{name}` | 삭제 | 200, 403, 404 |
| GET | `/api/v1/collections/activity-log` | 전체 이력 | 200 |
| GET | `/api/v1/collections/{name}/activity-log` | 컬렉션별 이력 | 200 |

### 2.1 주요 응답 스키마

```typescript
// 컬렉션 목록
{ collections: CollectionInfo[], total: number }

// 컬렉션 상세
{ name, vectors_count, points_count, status, config: { vector_size, distance } }

// 이력 조회
{ logs: ActivityLog[], total: number, limit: number, offset: number }

// 성공 메시지
{ name: string, message: string }

// 이름 변경 성공
{ old_name: string, new_name: string, message: string }
```

---

## 3. 화면 설계

### 3.1 페이지 구조

```
/collections (CollectionPage)
├── [탭: 컬렉션 관리]
│   ├── 헤더: "컬렉션 관리" + [새 컬렉션] 버튼 + [새로고침] 버튼
│   └── CollectionTable
│       ├── 컬럼: Name | Vectors | Points | Status | Actions
│       ├── 보호 컬렉션: Actions 칸에 "보호됨" 뱃지
│       └── 일반 컬렉션: [이름변경] [삭제] 버튼
│
├── [탭: 사용 이력]
│   ├── ActivityLogFilters (컬렉션, 액션, 사용자, 날짜범위)
│   ├── ActivityLogTable
│   │   └── 컬럼: # | Collection | Action | User | Detail | Time
│   └── 페이지네이션
│
├── CreateCollectionModal
│   └── 입력: name, vector_size, distance(select)
│
├── RenameCollectionModal
│   └── 입력: new_name
│
└── DeleteCollectionDialog
    └── 확인 다이얼로그 ("정말 삭제하시겠습니까?")
```

### 3.2 UI 컴포넌트 목록

| Component | 위치 | 역할 |
|-----------|------|------|
| `CollectionPage` | `pages/CollectionPage/index.tsx` | 탭 기반 메인 페이지 |
| `CollectionTable` | `components/collection/CollectionTable.tsx` | 컬렉션 목록 테이블 |
| `ActivityLogTable` | `components/collection/ActivityLogTable.tsx` | 이력 테이블 |
| `ActivityLogFilters` | `components/collection/ActivityLogFilters.tsx` | 필터 UI |
| `CreateCollectionModal` | `components/collection/CreateCollectionModal.tsx` | 생성 모달 |
| `RenameCollectionModal` | `components/collection/RenameCollectionModal.tsx` | 이름변경 모달 |
| `DeleteCollectionDialog` | `components/collection/DeleteCollectionDialog.tsx` | 삭제 확인 |

---

## 4. 파일 구조 및 구현 순서

### Phase 1: 기반 (타입, 상수, 서비스)

| # | 파일 | 설명 |
|---|------|------|
| 1 | `src/types/collection.ts` | TypeScript 인터페이스 정의 |
| 2 | `src/constants/api.ts` | 엔드포인트 상수 추가 |
| 3 | `src/lib/queryKeys.ts` | queryKey 팩토리 추가 |
| 4 | `src/services/collectionService.ts` | Axios API 호출 함수 |

### Phase 2: 훅

| # | 파일 | 설명 |
|---|------|------|
| 5 | `src/hooks/useCollections.ts` | TanStack Query 훅 (7개) |

### Phase 3: 컴포넌트

| # | 파일 | 설명 |
|---|------|------|
| 6 | `src/components/collection/CollectionTable.tsx` | 목록 테이블 |
| 7 | `src/components/collection/CreateCollectionModal.tsx` | 생성 모달 |
| 8 | `src/components/collection/RenameCollectionModal.tsx` | 이름변경 모달 |
| 9 | `src/components/collection/DeleteCollectionDialog.tsx` | 삭제 확인 |
| 10 | `src/components/collection/ActivityLogFilters.tsx` | 필터 컴포넌트 |
| 11 | `src/components/collection/ActivityLogTable.tsx` | 이력 테이블 |

### Phase 4: 페이지 + 라우팅

| # | 파일 | 설명 |
|---|------|------|
| 12 | `src/pages/CollectionPage/index.tsx` | 탭 기반 메인 페이지 |
| 13 | `src/App.tsx` | `/collections` 라우트 추가 |
| 14 | `src/components/layout/TopNav.tsx` | 네비게이션 링크 추가 |

### Phase 5: 테스트

| # | 파일 | 설명 |
|---|------|------|
| 15 | `src/__tests__/mocks/handlers.ts` | MSW 핸들러 추가 |
| 16 | `src/hooks/useCollections.test.ts` | 훅 테스트 |

---

## 5. TypeScript 타입 상세

```typescript
// src/types/collection.ts

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

export interface MessageResponse {
  name: string;
  message: string;
}

export interface RenameResponse {
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
```

---

## 6. API 상수 및 Query Keys

### 6.1 API Endpoints 추가

```typescript
// src/constants/api.ts — API_ENDPOINTS에 추가
COLLECTIONS: '/api/v1/collections',
COLLECTION_DETAIL: (name: string) => `/api/v1/collections/${name}`,
COLLECTION_RENAME: (name: string) => `/api/v1/collections/${name}`,
COLLECTION_DELETE: (name: string) => `/api/v1/collections/${name}`,
COLLECTION_ACTIVITY_LOG: '/api/v1/collections/activity-log',
COLLECTION_ACTIVITY_LOG_BY_NAME: (name: string) =>
  `/api/v1/collections/${name}/activity-log`,
```

### 6.2 Query Keys 추가

```typescript
// src/lib/queryKeys.ts — queryKeys에 추가
collections: {
  all: ['collections'] as const,
  list: () => [...queryKeys.collections.all, 'list'] as const,
  detail: (name: string) => [...queryKeys.collections.all, 'detail', name] as const,
  activityLog: (filters?: ActivityLogFilters) =>
    [...queryKeys.collections.all, 'activityLog', filters] as const,
  collectionActivityLog: (name: string) =>
    [...queryKeys.collections.all, 'collectionActivityLog', name] as const,
},
```

---

## 7. 서비스 레이어

```typescript
// src/services/collectionService.ts
import axios from './api/axiosInstance';

export const collectionService = {
  getCollections: () => axios.get(COLLECTIONS),
  getCollection: (name: string) => axios.get(COLLECTION_DETAIL(name)),
  createCollection: (data: CreateCollectionRequest) => axios.post(COLLECTIONS, data),
  renameCollection: (name: string, data: RenameCollectionRequest) =>
    axios.patch(COLLECTION_RENAME(name), data),
  deleteCollection: (name: string) => axios.delete(COLLECTION_DELETE(name)),
  getActivityLogs: (params: ActivityLogFilters) =>
    axios.get(COLLECTION_ACTIVITY_LOG, { params }),
  getCollectionActivityLogs: (name: string, params?) =>
    axios.get(COLLECTION_ACTIVITY_LOG_BY_NAME(name), { params }),
};
```

---

## 8. TanStack Query 훅

```typescript
// src/hooks/useCollections.ts
export const useCollectionList = () =>
  useQuery({ queryKey: queryKeys.collections.list(), queryFn: ... });

export const useCollectionDetail = (name: string) =>
  useQuery({ queryKey: queryKeys.collections.detail(name), queryFn: ..., enabled: !!name });

export const useCreateCollection = () =>
  useMutation({
    mutationFn: collectionService.createCollection,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.collections.all }),
  });

export const useRenameCollection = () =>
  useMutation({
    mutationFn: ({ name, newName }) => collectionService.renameCollection(name, { new_name: newName }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.collections.all }),
  });

export const useDeleteCollection = () =>
  useMutation({
    mutationFn: collectionService.deleteCollection,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.collections.all }),
  });

export const useActivityLogs = (filters: ActivityLogFilters) =>
  useQuery({ queryKey: queryKeys.collections.activityLog(filters), queryFn: ... });

export const useCollectionActivityLogs = (name: string) =>
  useQuery({ queryKey: queryKeys.collections.collectionActivityLog(name), queryFn: ... });
```

---

## 9. UX 상세

### 9.1 컬렉션 테이블

| 상태 | 표시 |
|------|------|
| `green` | 초록색 원 + "정상" |
| `yellow` | 노란색 원 + "최적화 중" |
| `red` | 빨간색 원 + "오류" |

### 9.2 보호 컬렉션 처리

- `documents` (기본 컬렉션): Actions 열에 삭제/이름변경 버튼 대신 `보호됨` 뱃지
- 서버에서 403 반환하므로 프론트에서도 미리 비활성화

### 9.3 에러 처리 UX

| HTTP Code | 사용자 메시지 | 컴포넌트 |
|-----------|-------------|----------|
| 201 | "컬렉션이 생성되었습니다" | toast 성공 |
| 403 | "보호된 컬렉션은 삭제할 수 없습니다" | toast 에러 |
| 404 | "컬렉션을 찾을 수 없습니다" | toast 에러 |
| 409 | "이미 존재하는 컬렉션입니다" | toast 에러 |
| 422 | "유효하지 않은 이름입니다" | 인라인 에러 |

### 9.4 생성 폼 기본값

| 필드 | 기본값 | 비고 |
|------|--------|------|
| `name` | (빈 문자열) | 영숫자, _, - 만 허용 |
| `vector_size` | `1536` | OpenAI text-embedding-3-small 기본 |
| `distance` | `"Cosine"` | select: Cosine / Euclid / Dot |

### 9.5 이력 테이블 상세

- **Detail 컬럼**: JSON을 축약 표시, 클릭 시 전체 JSON 팝오버
- **Action 컬럼**: 뱃지 스타일 (CREATE=초록, DELETE=빨강, SEARCH=파랑 등)
- **페이지네이션**: limit=50 기본, offset 기반

---

## 10. 기술 규칙 (idt_front/CLAUDE.md 준수)

- **shadcn/ui** 컴포넌트 사용 (Dialog, Table, Button, Input, Select, Badge)
- **Tailwind CSS v4** 스타일링
- **Arrow function** 컴포넌트
- **서비스 레이어** 통해 API 호출 (컴포넌트에서 직접 axios 호출 금지)
- **queryKeys 팩토리** 사용 (직접 문자열 배열 금지)
- **toast 알림**: 성공/에러 피드백

---

## 11. 의존성

- 추가 패키지 없음 (기존 shadcn/ui + TanStack Query + Tailwind 활용)
- 백엔드 API 구현 완료 (별도 백엔드 작업 불필요)

---

## 12. 예상 소요

| Phase | 파일 수 | 예상 |
|-------|---------|------|
| Phase 1: 기반 | 4 | 작음 |
| Phase 2: 훅 | 1 | 작음 |
| Phase 3: 컴포넌트 | 6 | 중간 |
| Phase 4: 라우팅 | 3 | 작음 |
| Phase 5: 테스트 | 2 | 작음 |
| **합계** | **16** | **중간** |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-04-22 | Initial draft — 백엔드 설계 문서 Section 8 기반 | 배상규 |
