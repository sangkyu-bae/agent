# collection-permission-management Design Document

> **Summary**: 컬렉션 권한 관리 — scope(개인/부서/공개) 기반 접근 제어 UI 설계
>
> **Project**: sangplusbot (idt_front)
> **Author**: 배상규
> **Date**: 2026-04-23
> **Status**: Draft
> **Planning Doc**: [collection-permission-management.plan.md](../01-plan/features/collection-permission-management.plan.md)
> **API Spec**: [collection-permission-management API](../../docs/api/collection-permission-management.md)

---

## 1. Overview

### 1.1 Design Goals

- 기존 컬렉션 관리 UI를 scope 기반 권한 API에 맞게 수정
- 인증 전환: 모든 API 호출을 `authApiClient` (Bearer token)로 전환
- 최소 변경 원칙: 기존 컴포넌트 구조를 유지하면서 scope 관련 필드/UI만 추가

### 1.2 Design Principles

- 기존 코드 재사용 극대화 (신규 파일은 `UpdateScopeModal` 1개만)
- 서버 권한 필터링에 의존 (프론트에서 scope 필터 로직을 별도로 구현하지 않음)
- 소유자/Admin 판별은 `useAuthStore.user`로 수행

---

## 2. Architecture

### 2.1 Component Diagram

```
┌─ CollectionPage ──────────────────────────────────────┐
│                                                        │
│  [Tab: 컬렉션 관리]          [Tab: 사용 이력]         │
│   ├─ CollectionTable          ├─ ActivityLogFilters    │
│   │   ├─ ScopeBadge (신규)    └─ ActivityLogTable     │
│   │   └─ ActionButtons                                │
│   │       ├─ 이름변경 (기존)                          │
│   │       ├─ 권한변경 (신규)                          │
│   │       └─ 삭제 (기존)                              │
│   │                                                    │
│   ├─ CreateCollectionModal (수정: +scope/dept)         │
│   ├─ RenameCollectionModal (변경 없음)                 │
│   ├─ UpdateScopeModal (신규)                           │
│   └─ DeleteCollectionDialog (변경 없음)                │
└────────────────────────────────────────────────────────┘
```

### 2.2 Data Flow

```
1. 페이지 로드
   authApiClient → GET /collections (Bearer token)
   → 서버가 사용자 role/department 기반 필터링 → 접근 가능한 컬렉션만 반환
   → CollectionTable 렌더링 (scope 배지 포함)

2. 컬렉션 생성
   CreateCollectionModal (scope + department_id 입력)
   → authApiClient → POST /collections
   → invalidateQueries → 목록 갱신

3. Scope 변경
   UpdateScopeModal (새 scope 선택)
   → authApiClient → PATCH /collections/{name}/permission
   → invalidateQueries → 목록 갱신

4. 권한 기반 액션 제한
   user.id === collection.owner_id || user.role === 'admin'
   → true: [이름변경] [권한변경] [삭제] 표시
   → false: 버튼 미표시
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `collectionService` | `authApiClient` | Bearer token 주입 |
| `CollectionTable` | `useAuthStore` | 현재 사용자 id/role로 액션 버튼 제어 |
| `CreateCollectionModal` | `CollectionScope` 타입 | scope 선택 UI |
| `UpdateScopeModal` | `useUpdateScope` 훅 | scope 변경 mutation |

---

## 3. Data Model

### 3.1 타입 변경 상세

```typescript
// src/types/collection.ts — 변경/추가 부분

// ─── 신규 타입 ───
export const COLLECTION_SCOPES = ['PERSONAL', 'DEPARTMENT', 'PUBLIC'] as const;
export type CollectionScope = (typeof COLLECTION_SCOPES)[number];

export const SCOPE_LABELS: Record<CollectionScope, { label: string; color: string; bg: string }> = {
  PERSONAL: { label: '개인', color: 'text-violet-600', bg: 'bg-violet-50' },
  DEPARTMENT: { label: '부서', color: 'text-blue-600', bg: 'bg-blue-50' },
  PUBLIC: { label: '공개', color: 'text-emerald-600', bg: 'bg-emerald-50' },
};

// ─── 기존 인터페이스 수정 ───
export interface CollectionInfo {
  name: string;
  vectors_count: number;
  points_count: number;
  status: string;
  scope: CollectionScope;    // 추가
  owner_id: number;          // 추가
}

export interface CreateCollectionRequest {
  name: string;
  embedding_model?: string;
  vector_size?: number;
  distance: string;
  scope?: CollectionScope;   // 추가 (기본값 서버측 'PERSONAL')
  department_id?: string;    // 추가 (scope=DEPARTMENT일 때 필수)
}

// ─── 신규 인터페이스 ───
export interface UpdateScopeRequest {
  scope: CollectionScope;
  department_id?: string;    // scope=DEPARTMENT일 때 필수
}

export interface UpdateScopeResponse {
  name: string;
  message: string;
}
```

### 3.2 User 타입 참조 (변경 없음)

```typescript
// src/types/auth.ts — 기존
export interface User {
  id: number;
  email: string;
  role: UserRole;   // 'user' | 'admin'
  status: UserStatus;
}
```

> **주의**: `User`에 `department_id` 필드가 없다. 부서 scope 사용 시 department_id를 직접 입력하는 방식으로 우회한다. 향후 User 타입에 department 정보가 추가되면 자동 선택으로 전환 가능.

---

## 4. API Specification

### 4.1 Endpoint List (프론트엔드 연동 대상)

| Method | Path | Description | Auth | 변경 |
|--------|------|-------------|------|------|
| GET | `/api/v1/collections` | 접근 가능 목록 조회 | Bearer | 응답에 scope/owner_id 추가 |
| GET | `/api/v1/collections/{name}` | 상세 조회 | Bearer | 응답에 scope/owner_id 추가 |
| POST | `/api/v1/collections` | 생성 | Bearer | 요청에 scope/department_id 추가 |
| PATCH | `/api/v1/collections/{name}` | 이름 변경 | Bearer | 403 추가 (소유자/Admin만) |
| DELETE | `/api/v1/collections/{name}` | 삭제 | Bearer | 403 추가 (소유자/Admin만) |
| **PATCH** | **`/api/v1/collections/{name}/permission`** | **scope 변경** | **Bearer** | **신규** |

### 4.2 신규 엔드포인트 상세

#### `PATCH /api/v1/collections/{name}/permission`

**Request:**
```json
{
  "scope": "DEPARTMENT",
  "department_id": "dept-uuid"
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| scope | `"PERSONAL" \| "DEPARTMENT" \| "PUBLIC"` | O | 새 scope |
| department_id | string | 조건부 | scope=DEPARTMENT일 때 필수 |

**Response (200):**
```json
{
  "name": "my-docs",
  "message": "Collection scope updated successfully"
}
```

**Error Responses:**
| Code | Cause |
|------|-------|
| 403 | 소유자/Admin이 아님 |
| 404 | 컬렉션 또는 권한 레코드 없음 |
| 422 | scope=DEPARTMENT인데 department_id 누락 또는 미소속 부서 |

### 4.3 API 상수 추가

```typescript
// src/constants/api.ts — API_ENDPOINTS에 추가
COLLECTION_PERMISSION: (name: string) => `/api/v1/collections/${name}/permission`,
```

---

## 5. UI/UX Design

### 5.1 CollectionTable 컬럼 변경

```
Before: Name | Vectors | Points | Status | Actions
After:  Name | Scope   | Vectors | Points | Status | Actions
              ↑ 신규
```

### 5.2 Scope 배지 (ScopeBadge)

CollectionTable 내부에서 인라인으로 구현 (별도 컴포넌트 파일 불필요).

```tsx
// CollectionTable.tsx 내 인라인 구현
const ScopeBadge = ({ scope }: { scope?: CollectionScope }) => {
  if (!scope) return <span className="text-[12px] text-zinc-400">—</span>;
  const info = SCOPE_LABELS[scope];
  return (
    <span className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[11.5px] font-semibold ${info.bg} ${info.color}`}>
      {info.label}
    </span>
  );
};
```

| Scope | 배경 | 텍스트 | 표시 |
|-------|------|--------|------|
| PERSONAL | `bg-violet-50` | `text-violet-600` | 개인 |
| DEPARTMENT | `bg-blue-50` | `text-blue-600` | 부서 |
| PUBLIC | `bg-emerald-50` | `text-emerald-600` | 공개 |
| 미설정 (legacy) | — | `text-zinc-400` | — (대시) |

### 5.3 액션 버튼 로직

```typescript
// CollectionTable.tsx
const canManage = (col: CollectionInfo): boolean => {
  const user = useAuthStore.getState().user;
  if (!user) return false;
  if (user.role === 'admin') return true;
  return col.owner_id === user.id;
};
```

| 조건 | 표시 |
|------|------|
| 보호 컬렉션 | "보호됨" 뱃지 (기존) |
| `canManage === true` | [이름변경] [권한변경] [삭제] |
| `canManage === false` | 버튼 없음 |

### 5.4 CreateCollectionModal 변경

기존 폼 하단에 Scope 선택 섹션 추가:

```
┌─ 새 컬렉션 생성 ──────────────────┐
│                                     │
│ 컬렉션 이름:  [________________]    │
│                                     │
│ 임베딩 모델:  [▼ 선택         ]     │
│                                     │
│ 거리 메트릭:  [▼ Cosine       ]     │
│                                     │
│ ── 접근 범위 ──────────────────     │ ← 신규 섹션
│                                     │
│ (●) 개인   — 나만 접근 가능        │
│ ( ) 부서   — 소속 부서원 접근      │
│ ( ) 공개   — 전체 접근 가능        │
│                                     │
│ [scope=DEPARTMENT일 때만 표시]      │
│ 부서 ID:   [________________]       │
│                                     │
│            [취소]  [생성]           │
└─────────────────────────────────────┘
```

**상태 추가:**
```typescript
const [scope, setScope] = useState<CollectionScope>('PERSONAL');
const [departmentId, setDepartmentId] = useState('');
```

**제출 시:**
```typescript
onSubmit({
  name,
  embedding_model: selectedModel || undefined,
  vector_size: useFallback ? vectorSize : undefined,
  distance,
  scope,                                              // 추가
  department_id: scope === 'DEPARTMENT' ? departmentId : undefined,  // 추가
});
```

### 5.5 UpdateScopeModal (신규)

```
┌─ 접근 범위 변경 ──────────────────┐
│                                     │
│ 컬렉션: my-docs                     │
│ 현재 범위: 🔒 개인                  │
│                                     │
│ ── 새 접근 범위 ──────────────     │
│                                     │
│ (●) 개인   — 나만 접근 가능        │
│ ( ) 부서   — 소속 부서원 접근      │
│ ( ) 공개   — 전체 접근 가능        │
│                                     │
│ [scope=DEPARTMENT일 때만 표시]      │
│ 부서 ID:   [________________]       │
│                                     │
│ [에러 메시지 표시 영역]             │
│                                     │
│            [취소]  [변경]           │
└─────────────────────────────────────┘
```

**Props:**
```typescript
interface UpdateScopeModalProps {
  isOpen: boolean;
  collectionName: string;
  currentScope: CollectionScope;
  onClose: () => void;
  onSubmit: (data: UpdateScopeRequest) => void;
  isPending: boolean;
  error: string | null;
}
```

### 5.6 User Flow

```
컬렉션 목록 조회
  → 서버가 사용자 권한에 맞는 컬렉션만 반환
  → 각 컬렉션에 scope 배지 표시
  → 소유자/Admin인 컬렉션만 액션 버튼 표시

컬렉션 생성
  → 모달에서 이름/모델/메트릭 + scope 선택
  → scope=DEPARTMENT → department_id 입력 필드 표시
  → 서버에 생성 요청 → 목록 갱신

scope 변경
  → [권한변경] 버튼 클릭 → UpdateScopeModal 표시
  → 새 scope 선택 → PATCH /permission → 목록 갱신
```

---

## 6. Error Handling

### 6.1 Error Code → UX 매핑

| Code | API | 사용자 메시지 | 표시 위치 |
|------|-----|-------------|----------|
| 403 | rename/delete | "권한이 없습니다" | 모달 내 에러 |
| 403 | permission | "권한 변경 권한이 없습니다" | 모달 내 에러 |
| 404 | all | "컬렉션을 찾을 수 없습니다" | 모달 내 에러 |
| 409 | create | "이미 존재하는 컬렉션입니다" | 모달 내 에러 |
| 422 | create/permission | "유효하지 않은 부서입니다" | 모달 내 에러 |
| 401 | all | 자동 로그인 리다이렉트 | `authApiClient` 인터셉터 처리 |

### 6.2 에러 표시 방식

기존 패턴 유지 — 모달 내부 하단 빨간 박스:
```tsx
{error && (
  <p className="rounded-lg bg-red-50 px-3 py-2 text-[13px] text-red-600">
    {error}
  </p>
)}
```

---

## 7. Security Considerations

- [x] 인증: `authApiClient`가 Bearer token 자동 주입
- [x] 401 자동 처리: `authApiClient` 인터셉터가 토큰 갱신 → 실패 시 로그인 리다이렉트
- [x] 권한 검사: 서버에서 수행 (프론트는 UI 가시성만 제어, 실제 차단은 서버)
- [x] XSS: React 기본 이스케이핑 + 사용자 입력을 innerHTML로 렌더하지 않음
- [ ] department_id 입력: 서버에서 소속 부서 검증 (프론트 추가 검증 불필요)

---

## 8. Test Plan

### 8.1 Test Scope

| Type | Target | Tool |
|------|--------|------|
| Unit | `CreateCollectionModal` scope UI | Vitest + RTL |
| Unit | `UpdateScopeModal` 렌더링/제출 | Vitest + RTL |
| Unit | `CollectionTable` scope 배지/버튼 | Vitest + RTL |
| Unit | `useUpdateScope` 훅 | Vitest + RTL (renderHook) |
| Integration | MSW 핸들러 | MSW |

### 8.2 Test Cases (Key)

- [x] 기존 테스트 유지 (`CreateCollectionModal.test.tsx`)
- [ ] scope=PERSONAL 선택 시 department_id 미전송
- [ ] scope=DEPARTMENT 선택 시 department_id 필드 표시 & 필수 검증
- [ ] scope 배지가 PERSONAL/DEPARTMENT/PUBLIC에 맞게 렌더링
- [ ] `canManage=false`인 컬렉션에 액션 버튼 미표시
- [ ] `canManage=true`인 컬렉션에 [이름변경] [권한변경] [삭제] 표시
- [ ] UpdateScopeModal: scope 선택 → 제출 → onSubmit 호출
- [ ] UpdateScopeModal: 에러 상태 표시
- [ ] scope 미설정(legacy) 컬렉션: 대시(—) 표시

---

## 9. Clean Architecture Layer Assignment

| Component | Layer | Location | 변경 유형 |
|-----------|-------|----------|----------|
| `CollectionScope`, `SCOPE_LABELS` | Domain | `src/types/collection.ts` | 추가 |
| `UpdateScopeRequest/Response` | Domain | `src/types/collection.ts` | 추가 |
| `collectionService.updateScope` | Infrastructure | `src/services/collectionService.ts` | 추가 |
| `COLLECTION_PERMISSION` | Infrastructure | `src/constants/api.ts` | 추가 |
| `useUpdateScope` | Application | `src/hooks/useCollections.ts` | 추가 |
| `CollectionTable` | Presentation | `src/components/collection/CollectionTable.tsx` | 수정 |
| `CreateCollectionModal` | Presentation | `src/components/collection/CreateCollectionModal.tsx` | 수정 |
| `UpdateScopeModal` | Presentation | `src/components/collection/UpdateScopeModal.tsx` | **신규** |
| `CollectionPage` | Presentation | `src/pages/CollectionPage/index.tsx` | 수정 |

---

## 10. Coding Convention (idt_front/CLAUDE.md 준수)

| Item | Convention |
|------|-----------|
| 컴포넌트 | Arrow function + `interface XxxProps` 파일 상단 |
| Scope 상수 | `as const` 객체 + 타입 추출 (`CollectionScope`) |
| 모달 Props | `isOpen`, `onClose`, `onSubmit`, `isPending`, `error` 패턴 |
| API 호출 | 서비스 레이어 (`collectionService`) 경유 |
| Query Key | `queryKeys.collections.*` 팩토리 사용 |
| Import | 절대 경로 (`@/types/collection`, `@/hooks/useCollections`) |

---

## 11. Implementation Guide

### 11.1 변경 파일 전체 목록

```
src/
├── types/collection.ts                              ← 수정
├── constants/api.ts                                 ← 수정
├── services/collectionService.ts                    ← 수정
├── hooks/useCollections.ts                          ← 수정
├── components/collection/
│   ├── CollectionTable.tsx                           ← 수정
│   ├── CreateCollectionModal.tsx                     ← 수정
│   └── UpdateScopeModal.tsx                          ← 신규
└── pages/CollectionPage/index.tsx                   ← 수정
```

### 11.2 Implementation Order

1. [ ] **타입 정의** — `src/types/collection.ts`
   - `CollectionScope`, `COLLECTION_SCOPES`, `SCOPE_LABELS` 추가
   - `CollectionInfo`에 `scope`, `owner_id` 추가
   - `CreateCollectionRequest`에 `scope`, `department_id` 추가
   - `UpdateScopeRequest`, `UpdateScopeResponse` 추가

2. [ ] **API 상수** — `src/constants/api.ts`
   - `COLLECTION_PERMISSION` 엔드포인트 추가

3. [ ] **서비스 레이어** — `src/services/collectionService.ts`
   - `import apiClient` → `import authApiClient` 전환
   - `updateScope()` 메서드 추가

4. [ ] **훅** — `src/hooks/useCollections.ts`
   - `useUpdateScope` 뮤테이션 훅 추가

5. [ ] **CollectionTable** — `src/components/collection/CollectionTable.tsx`
   - Scope 컬럼 + ScopeBadge 추가
   - `canManage` 로직 + 권한변경 버튼 추가
   - Props에 `currentUserId`, `currentUserRole`, `onUpdateScope` 추가

6. [ ] **CreateCollectionModal** — `src/components/collection/CreateCollectionModal.tsx`
   - Scope 라디오 버튼 추가
   - scope=DEPARTMENT일 때 department_id 입력 표시
   - onSubmit에 scope/department_id 포함

7. [ ] **UpdateScopeModal** — `src/components/collection/UpdateScopeModal.tsx` (신규)
   - Scope 라디오 선택 + department_id 조건부 입력
   - 기존 모달 패턴(CreateCollectionModal)과 동일한 스타일

8. [ ] **CollectionPage** — `src/pages/CollectionPage/index.tsx`
   - `useUpdateScope` 연동
   - `scopeTarget` 상태 + UpdateScopeModal 통합
   - `useAuthStore`에서 user 정보 전달

---

## 12. Edge Cases

| 케이스 | 처리 |
|--------|------|
| scope 필드 없는 응답 (legacy 컬렉션) | `scope` 옵셔널 처리 → 배지 대신 `—` 표시 |
| owner_id 없는 응답 | `owner_id` 옵셔널 → `canManage` false (Admin 제외) |
| User.department_id 미존재 | department_id를 텍스트 입력으로 처리 (서버에서 검증) |
| 비로그인 상태 | `authApiClient` → 401 → 자동 로그인 리다이렉트 |
| Admin의 DEPARTMENT scope | 어떤 부서든 지정 가능 (서버 정책) |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-04-23 | Initial draft — 권한 기반 컬렉션 관리 설계 | 배상규 |
