# collection-permission-management Plan Document

> **Feature**: 컬렉션 권한 관리 (개인/부서/공개 Scope 기반 접근 제어)
>
> **Project**: sangplusbot (idt_front)
> **Author**: 배상규
> **Date**: 2026-04-23
> **Status**: Draft
> **Predecessor**: `collection-management-ui.plan.md` (기존 컬렉션 관리 UI)
> **API Spec**: `docs/api/collection-permission-management.md`

---

## 1. 개요

### 1.1 배경

기존 `/collections` 페이지는 모든 사용자가 모든 컬렉션(벡터 DB)에 무제한 접근할 수 있었다.
보안 및 데이터 격리를 위해 백엔드 API가 **scope 기반 권한 모델**(PERSONAL / DEPARTMENT / PUBLIC)로 변경되었으며,
프론트엔드도 이에 맞춰 수정이 필요하다.

### 1.2 목표

- 기존 컬렉션 관리 페이지를 권한 API에 맞게 수정
- **인증 필수**: 모든 API 호출을 `authApiClient`(Bearer token)로 전환
- **Scope 표시**: 컬렉션 목록에 scope(개인/부서/공개) 배지 표시
- **Scope 선택**: 컬렉션 생성 시 scope + department 선택 UI 추가
- **Scope 변경**: 기존 컬렉션의 scope를 변경하는 기능 추가
- **권한 기반 액션 제한**: 소유자/Admin만 이름변경, 삭제, scope 변경 가능하도록 UI 반영

### 1.3 비목표 (Scope Out)

- 부서 관리 CRUD (부서 목록은 별도 API에서 조회한다고 가정)
- 다중 부서 공유 (1 컬렉션 = 1 department_id)
- 컬렉션 내 문서별 세부 권한 관리

---

## 2. 현재 코드 vs 새 API 차이 분석

### 2.1 타입 변경 (`src/types/collection.ts`)

| 항목 | 현재 | 변경 후 |
|------|------|---------|
| `CollectionInfo` | `name, vectors_count, points_count, status` | + `scope`, `owner_id` |
| `CreateCollectionRequest` | `name, embedding_model?, vector_size?, distance` | + `scope`, `department_id` |
| Scope 타입 | 없음 | `'PERSONAL' \| 'DEPARTMENT' \| 'PUBLIC'` |
| Permission 변경 요청 | 없음 | `UpdateScopeRequest { scope, department_id? }` |

### 2.2 서비스 레이어 변경 (`src/services/collectionService.ts`)

| 항목 | 현재 | 변경 후 |
|------|------|---------|
| HTTP 클라이언트 | `apiClient` (공개, 인증 없음) | `authApiClient` (Bearer token 주입) |
| `updateScope` 메서드 | 없음 | `PATCH /collections/{name}/permission` |

### 2.3 API 상수 변경 (`src/constants/api.ts`)

| 항목 | 현재 | 변경 후 |
|------|------|---------|
| `COLLECTION_PERMISSION` | 없음 | `(name) => /api/v1/collections/${name}/permission` |

### 2.4 UI 컴포넌트 변경

| 컴포넌트 | 변경 내용 |
|----------|----------|
| `CollectionTable` | scope 컬럼 추가, scope 배지 표시, scope 변경 버튼 추가 |
| `CreateCollectionModal` | scope 선택 드롭다운 + department 조건부 입력 추가 |
| `CollectionPage` | scope 변경 모달 추가 |
| (신규) `UpdateScopeModal` | scope 변경 전용 모달 |

---

## 3. 백엔드 API 계약

> 백엔드 구현 완료 상태. 인증 필수 (Bearer Token).

| Method | Endpoint | 설명 | Error Codes |
|--------|----------|------|-------------|
| GET | `/api/v1/collections` | 접근 가능한 컬렉션 목록 (scope 필터 자동 적용) | 200 |
| GET | `/api/v1/collections/{name}` | 컬렉션 상세 (read 권한 검사) | 200, 403, 404 |
| POST | `/api/v1/collections` | 컬렉션 생성 + 권한 레코드 동시 생성 | 200, 409, 422 |
| PATCH | `/api/v1/collections/{name}` | 이름 변경 (소유자/Admin) | 200, 403, 404 |
| DELETE | `/api/v1/collections/{name}` | 삭제 (소유자/Admin) | 200, 403, 404 |
| PATCH | `/api/v1/collections/{name}/permission` | scope 변경 (소유자/Admin) | 200, 403, 404, 422 |

### 3.1 주요 응답 스키마 변경점

```typescript
// GET /api/v1/collections — Response
{
  collections: [
    {
      name: string;
      vectors_count: number;
      points_count: number;
      status: string;
      scope: 'PERSONAL' | 'DEPARTMENT' | 'PUBLIC';  // 신규
      owner_id: number;                               // 신규
    }
  ],
  total: number;
}

// POST /api/v1/collections — Request
{
  name: string;
  vector_size?: number;
  embedding_model?: string;
  distance?: string;       // default: "Cosine"
  scope?: string;          // 신규: default "PERSONAL"
  department_id?: string;  // 신규: scope=DEPARTMENT일 때 필수
}

// PATCH /api/v1/collections/{name}/permission — Request
{
  scope: 'PERSONAL' | 'DEPARTMENT' | 'PUBLIC';
  department_id?: string;  // scope=DEPARTMENT일 때 필수
}
```

### 3.2 필터 규칙 (서버에서 자동 적용)

| 역할 | 표시되는 컬렉션 |
|------|----------------|
| Admin | 전체 |
| 일반 사용자 | PUBLIC + 본인 PERSONAL + 소속 부서 DEPARTMENT |

### 3.3 권한 규칙

| Scope | Read | Write | Delete | Rename | Change Scope |
|-------|------|-------|--------|--------|--------------|
| PERSONAL | 소유자, Admin | 소유자, Admin | 소유자, Admin | 소유자, Admin | 소유자, Admin |
| DEPARTMENT | 소속 부서원, Admin | 소속 부서원, Admin | 소유자, Admin | 소유자, Admin | 소유자, Admin |
| PUBLIC | 전체 | Admin만 | 소유자, Admin | 소유자, Admin | 소유자, Admin |

---

## 4. 화면 설계

### 4.1 CollectionTable 변경

```
컬럼: Name | Scope | Vectors | Points | Status | Actions
                ↑ 신규

Scope 배지:
  PERSONAL   → 🔒 개인 (violet-100 bg, violet-600 text)
  DEPARTMENT → 🏢 부서 (blue-100 bg, blue-600 text)
  PUBLIC     → 🌐 공개 (green-100 bg, green-600 text)

Actions:
  소유자/Admin → [이름변경] [권한변경] [삭제]
  읽기 전용   → (버튼 없음 또는 비활성)
  보호 컬렉션 → "보호됨" 뱃지 (기존 로직 유지)
```

### 4.2 CreateCollectionModal 변경

```
기존 필드:
  - 컬렉션 이름
  - 임베딩 모델 (or 벡터 차원 수 fallback)
  - 거리 메트릭

추가 필드:
  - Scope 선택 (라디오 버튼 또는 select)
    ├── 개인 (기본값)
    ├── 부서 → department_id 선택 드롭다운 표시
    └── 공개

  - 부서 선택 (scope=DEPARTMENT일 때만 표시)
    └── select: 사용자 소속 부서 목록
```

### 4.3 UpdateScopeModal (신규)

```
UpdateScopeModal
├── 현재 상태 표시: "현재: 개인"
├── 새 scope 선택 (라디오 or select)
├── department_id 조건부 표시
├── [취소] [변경] 버튼
└── 에러 표시 (403/422)
```

### 4.4 컴포넌트 목록

| Component | 파일 | 변경 유형 |
|-----------|------|----------|
| `CollectionTable` | `components/collection/CollectionTable.tsx` | 수정 — scope 컬럼, 권한 버튼 |
| `CreateCollectionModal` | `components/collection/CreateCollectionModal.tsx` | 수정 — scope/dept 필드 추가 |
| `UpdateScopeModal` | `components/collection/UpdateScopeModal.tsx` | **신규** |
| `CollectionPage` | `pages/CollectionPage/index.tsx` | 수정 — scope 변경 모달 연동 |

---

## 5. 파일 변경 목록 및 구현 순서

### Phase 1: 기반 (타입, 상수, 서비스)

| # | 파일 | 변경 유형 | 설명 |
|---|------|----------|------|
| 1 | `src/types/collection.ts` | 수정 | `CollectionInfo`에 `scope`, `owner_id` 추가. `CollectionScope` 타입 추가. `CreateCollectionRequest`에 `scope`, `department_id` 추가. `UpdateScopeRequest` 신규 인터페이스. `SCOPE_LABELS` 상수 추가. |
| 2 | `src/constants/api.ts` | 수정 | `COLLECTION_PERMISSION` 엔드포인트 추가 |
| 3 | `src/services/collectionService.ts` | 수정 | `apiClient` → `authApiClient` 전환. `updateScope()` 메서드 추가 |

### Phase 2: 훅

| # | 파일 | 변경 유형 | 설명 |
|---|------|----------|------|
| 4 | `src/hooks/useCollections.ts` | 수정 | `useUpdateScope` 뮤테이션 훅 추가 |

### Phase 3: UI 컴포넌트

| # | 파일 | 변경 유형 | 설명 |
|---|------|----------|------|
| 5 | `src/components/collection/CollectionTable.tsx` | 수정 | scope 컬럼 추가, scope 배지, 권한 변경 버튼, owner 기반 액션 조건부 렌더링 |
| 6 | `src/components/collection/CreateCollectionModal.tsx` | 수정 | scope 선택 UI + department 조건부 입력 추가 |
| 7 | `src/components/collection/UpdateScopeModal.tsx` | **신규** | scope 변경 모달 |
| 8 | `src/pages/CollectionPage/index.tsx` | 수정 | `useUpdateScope` 연동 + UpdateScopeModal 통합 |

### Phase 4: 테스트

| # | 파일 | 변경 유형 | 설명 |
|---|------|----------|------|
| 9 | `src/components/collection/CreateCollectionModal.test.tsx` | 수정 | scope 관련 테스트 케이스 추가 |
| 10 | `src/hooks/useCollections.test.ts` (신규) | 신규 | `useUpdateScope` 테스트 |

---

## 6. 상세 타입 정의

```typescript
// src/types/collection.ts — 추가/변경 부분

export const COLLECTION_SCOPES = ['PERSONAL', 'DEPARTMENT', 'PUBLIC'] as const;
export type CollectionScope = (typeof COLLECTION_SCOPES)[number];

export const SCOPE_LABELS: Record<CollectionScope, { label: string; icon: string }> = {
  PERSONAL: { label: '개인', icon: '🔒' },
  DEPARTMENT: { label: '부서', icon: '🏢' },
  PUBLIC: { label: '공개', icon: '🌐' },
} as const;

export interface CollectionInfo {
  name: string;
  vectors_count: number;
  points_count: number;
  status: string;
  scope: CollectionScope;    // 신규
  owner_id: number;          // 신규
}

export interface CreateCollectionRequest {
  name: string;
  embedding_model?: string;
  vector_size?: number;
  distance: string;
  scope?: CollectionScope;      // 신규 (기본값: 'PERSONAL')
  department_id?: string;       // 신규 (scope=DEPARTMENT일 때 필수)
}

export interface UpdateScopeRequest {
  scope: CollectionScope;
  department_id?: string;
}

export interface UpdateScopeResponse {
  name: string;
  message: string;
}
```

---

## 7. API 상수 추가

```typescript
// src/constants/api.ts — API_ENDPOINTS에 추가
COLLECTION_PERMISSION: (name: string) => `/api/v1/collections/${name}/permission`,
```

---

## 8. 서비스 레이어 변경

```typescript
// src/services/collectionService.ts — 주요 변경

// import 변경: apiClient → authApiClient
import authApiClient from './api/authClient';

// 메서드 추가
updateScope: async (name: string, data: UpdateScopeRequest): Promise<UpdateScopeResponse> => {
  const res = await authApiClient.patch<UpdateScopeResponse>(
    API_ENDPOINTS.COLLECTION_PERMISSION(name),
    data,
  );
  return res.data;
},
```

---

## 9. TanStack Query 훅 추가

```typescript
// src/hooks/useCollections.ts — 추가

export const useUpdateScope = () =>
  useMutation({
    mutationFn: ({ name, data }: { name: string; data: UpdateScopeRequest }) =>
      collectionService.updateScope(name, data),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: queryKeys.collections.all }),
  });
```

---

## 10. UX 상세

### 10.1 Scope 배지 스타일

| Scope | 배경 | 텍스트 | 아이콘 |
|-------|------|--------|--------|
| PERSONAL | `bg-violet-50` | `text-violet-600` | 자물쇠 |
| DEPARTMENT | `bg-blue-50` | `text-blue-600` | 빌딩 |
| PUBLIC | `bg-emerald-50` | `text-emerald-600` | 지구 |

### 10.2 액션 버튼 가시성

| 조건 | 표시되는 버튼 |
|------|-------------|
| 보호 컬렉션 (`documents`) | "보호됨" 뱃지 (기존 동작 유지) |
| 소유자 또는 Admin | [이름변경] [권한변경] [삭제] |
| 그 외 (읽기만 가능) | 버튼 없음 |

> 현재 사용자 정보는 `useAuthStore`의 `user` (id, role)에서 가져온다.

### 10.3 에러 처리

| HTTP Code | 상황 | 사용자 메시지 |
|-----------|------|-------------|
| 403 (rename/delete) | 소유자/Admin이 아님 | "권한이 없습니다" |
| 403 (permission) | scope 변경 권한 없음 | "권한 변경 권한이 없습니다" |
| 404 | 컬렉션 없음 | "컬렉션을 찾을 수 없습니다" |
| 409 | 이름 중복 | "이미 존재하는 컬렉션입니다" |
| 422 | dept 누락 또는 미소속 부서 | "유효하지 않은 부서입니다" |

### 10.4 부서 목록 조회

- scope=DEPARTMENT 선택 시 부서 목록이 필요하다.
- **임시 접근**: 현재 사용자의 소속 부서 정보(`useAuthStore.user.department_id`)를 사용하여 단일 부서만 표시.
- **향후**: 부서 목록 API가 구현되면 드롭다운으로 전환.

---

## 11. Edge Cases

| 케이스 | 동작 |
|--------|------|
| 권한 레코드 미등록 컬렉션 (legacy) | 서버가 read/write 허용 — scope 미표시 또는 "미설정" 표시 |
| Admin의 DEPARTMENT scope 설정 | 어떤 부서든 지정 가능 |
| 비로그인 사용자 | `authApiClient`가 401 → 자동 로그인 페이지 리다이렉트 |
| scope 필드 없는 응답 (하위 호환) | `scope ?? undefined` → scope 배지 미표시 |

---

## 12. 의존성

- 추가 패키지 없음 (기존 스택 활용)
- `authApiClient` 구현 완료 (`src/services/api/authClient.ts`)
- `useAuthStore` 구현 완료 (`src/store/authStore.ts`)
- 백엔드 API 구현 완료 (Bearer token 인증 포함)

---

## 13. 예상 소요

| Phase | 파일 수 | 난이도 |
|-------|---------|--------|
| Phase 1: 기반 (타입, 상수, 서비스) | 3 | 작음 |
| Phase 2: 훅 | 1 | 작음 |
| Phase 3: UI 컴포넌트 | 4 | 중간 |
| Phase 4: 테스트 | 2 | 작음 |
| **합계** | **10** | **중간** |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-04-23 | Initial draft — 권한 기반 컬렉션 관리 API 연동 계획 | 배상규 |
