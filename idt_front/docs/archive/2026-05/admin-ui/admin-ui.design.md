# admin-ui Design

> 관리자 네비게이션 바 + AdminLayout(사이드바) + 부서 관리 페이지 상세 설계

---

## 1. 아키텍처 개요

```
┌─────────────────────────────────────────────────────────┐
│                     App.tsx (Routes)                      │
├─────────────────────────────────────────────────────────┤
│ /login, /register                  → Public              │
│ / (AgentChatLayout → Outlet)       → Protected           │
│ /admin/* (AdminLayout → Outlet)    → AdminRoute          │
└─────────────────────────────────────────────────────────┘

AdminRoute (역할 검사)
  └─ AdminLayout (TopNav + Sidebar + Outlet)
       ├─ /admin/users        → AdminUsersPage
       └─ /admin/departments  → AdminDepartmentsPage
```

### 진입 흐름

1. admin 유저 로그인 → TopNav에 "관리" 메뉴 표시됨
2. "관리" 드롭다운에서 메뉴 클릭 → `/admin/*` 이동
3. `AdminRoute`가 role 검증 → `AdminLayout` 렌더링
4. AdminLayout: TopNav(재사용) + AdminSidebar + 본문(Outlet)

---

## 2. 컴포넌트 상세 설계

### 2-1. TopNav 수정 — 관리자 메뉴 조건부 추가

**파일**: `src/components/layout/TopNav.tsx`

**변경 내용**: `NAV_MENUS` 렌더링 시 admin 역할일 때 "관리" 메뉴를 추가로 표시

```tsx
// TopNav 내부 — menus 계산
const adminMenu: NavMenu = {
  label: '관리',
  items: [
    {
      label: '사용자 관리',
      path: '/admin/users',
      icon: 'M15 19.128a9.38 9.38 0 0 0 2.625.372 9.337 9.337 0 0 0 4.121-.952 4.125 4.125 0 0 0-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128H5.228A2 2 0 0 1 3.22 17.07a8.632 8.632 0 0 1 2.026-4.564c1.128-1.188 2.714-1.927 4.504-1.927 1.79 0 3.375.739 4.504 1.927M12 9.75a3.75 3.75 0 1 0 0-7.5 3.75 3.75 0 0 0 0 7.5Z',
      description: '가입 승인 및 사용자 관리',
    },
    {
      label: '부서 관리',
      path: '/admin/departments',
      icon: 'M3.75 21h16.5M4.5 3h15M5.25 3v18m13.5-18v18M9 6.75h1.5m-1.5 3h1.5m-1.5 3h1.5m3-6H15m-1.5 3H15m-1.5 3H15M9 21v-3.375c0-.621.504-1.125 1.125-1.125h3.75c.621 0 1.125.504 1.125 1.125V21',
      description: '부서 생성·수정·삭제 및 사용자 배정',
    },
  ],
};

const menus = user?.role === 'admin' ? [...NAV_MENUS, adminMenu] : NAV_MENUS;
```

**스타일 특이사항**: 기존 `NAV_MENUS.map()` 루프를 `menus.map()`으로 교체. 나머지 동일.

---

### 2-2. AdminLayout 컴포넌트

**신규 파일**: `src/components/layout/AdminLayout.tsx`

```tsx
interface AdminSidebarItem {
  label: string;
  path: string;
  icon: string; // HeroIcon path
}

const ADMIN_SIDEBAR_ITEMS: AdminSidebarItem[] = [
  {
    label: '사용자 관리',
    path: '/admin/users',
    icon: 'M15 19.128a9.38...',  // Users icon
  },
  {
    label: '부서 관리',
    path: '/admin/departments',
    icon: 'M3.75 21h16.5M4.5...',  // Building icon
  },
];
```

#### 레이아웃 구조

```tsx
const AdminLayout = () => {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <TopNav />
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        <AdminSidebar />
        <main style={{ flex: 1, overflowY: 'auto', background: '#fff' }}>
          <Outlet />
        </main>
      </div>
    </div>
  );
};
```

#### AdminSidebar 영역 스타일

```
┌──────────────────────┐
│ ADMIN 헤더           │  ← text-[11.5px] uppercase tracking-widest text-violet-500
│                      │
│ ▸ 사용자 관리        │  ← 활성: bg-violet-50 text-violet-700 font-semibold
│ ▸ 부서 관리          │  ← 비활성: text-zinc-600 hover:bg-zinc-100
│                      │
│                      │
│                      │
│ ─────────────────── │
│ ← 메인으로 돌아가기  │  ← text-zinc-400 hover:text-zinc-600
└──────────────────────┘
```

| 속성 | 값 |
|------|-----|
| 너비 | `w-56` (224px) |
| 배경 | `bg-zinc-50` |
| 테두리 | `border-r border-zinc-200` |
| 메뉴 패딩 | `px-3 py-2` |
| 항목 radius | `rounded-xl` |
| 활성 상태 | `bg-violet-50 text-violet-700 font-semibold` |
| 비활성 상태 | `text-zinc-600 hover:bg-zinc-100 hover:text-zinc-900` |
| 아이콘 크기 | `h-4.5 w-4.5` (18px) |
| 하단 복귀 링크 | `border-t border-zinc-200` + `text-[13px] text-zinc-400` |

---

### 2-3. AdminDepartmentsPage

**신규 파일**: `src/pages/AdminDepartmentsPage/index.tsx`

#### 페이지 상태 (useState)

| State | Type | 용도 |
|-------|------|------|
| `isCreateOpen` | `boolean` | 생성 모달 표시 |
| `editingDept` | `Department \| null` | 수정 대상 (null이면 닫힘) |
| `deletingDept` | `Department \| null` | 삭제 확인 대상 |

#### 전체 레이아웃

```
┌────────────────────────────────────────────────────────────────┐
│ [11.5px uppercase violet] Admin                                 │
│ [3xl bold] 부서 관리                         [+ 부서 추가] 버튼  │
│ [13px zinc-400] 부서를 생성·수정·삭제합니다.                      │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ 부서명        │ 설명          │ 생성일     │ 액션         │  │
│  ├──────────────────────────────────────────────────────────┤  │
│  │ 개발팀        │ 백엔드/프론트  │ 2025.05.01 │ [수정][삭제] │  │
│  │ 기획팀        │ 서비스 기획    │ 2025.05.02 │ [수정][삭제] │  │
│  │ 영업팀        │ —             │ 2025.05.03 │ [수정][삭제] │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                │
│  (빈 상태 시)                                                   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │     등록된 부서가 없습니다. [+ 첫 번째 부서 추가하기]       │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

#### 테이블 컬럼 정의

| 컬럼 | 필드 | 너비 | 정렬 |
|------|------|------|------|
| 부서명 | `name` | auto | left |
| 설명 | `description` | auto | left |
| 생성일 | `created_at` | 120px | left |
| 액션 | — | 120px | right |

#### 모달: 부서 추가/수정

하나의 모달 컴포넌트(`DepartmentFormModal`)를 공용으로 사용.

```
┌────────────────────────────────┐
│ [15px semibold] 부서 추가       │  (or "부서 수정")
│                                │
│  부서명 *                       │
│  ┌─────────────────────────┐   │
│  │ (placeholder: 부서명)    │   │
│  └─────────────────────────┘   │
│                                │
│  설명 (선택)                    │
│  ┌─────────────────────────┐   │
│  │ (placeholder: 설명)      │   │
│  └─────────────────────────┘   │
│                                │
│  (에러 시: 빨간 박스 메시지)     │
│                                │
│          [취소]  [추가] ←Primary │
└────────────────────────────────┘
```

| 속성 | 스타일 |
|------|--------|
| 오버레이 | `fixed inset-0 z-50 bg-black/50` |
| 모달 카드 | `max-w-md rounded-2xl bg-white p-6 shadow-2xl` |
| Input | `rounded-xl border border-zinc-300 px-4 py-2.5 text-[14px]` |
| Focus | `focus:border-violet-400 focus:ring-2 focus:ring-violet-100` |
| 취소 버튼 | Secondary/Ghost 패턴 |
| 확인 버튼 | Primary 패턴 (violet-600) |
| 409 에러 | `bg-red-50 text-red-600 rounded-lg px-3 py-2 text-[13px]` |

#### 삭제 확인

기존 `ConfirmDialog` 컴포넌트 재사용 (`variant: 'danger'`).

```tsx
<ConfirmDialog
  isOpen={!!deletingDept}
  title="부서 삭제"
  description={`"${deletingDept?.name}" 부서를 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.`}
  confirmLabel="삭제"
  variant="danger"
  onClose={() => setDeletingDept(null)}
  onConfirm={() => deleteDept(deletingDept!.id)}
  isPending={isDeleting}
/>
```

---

## 3. 타입 설계

### 3-1. `src/types/department.ts`

```typescript
export interface Department {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface DepartmentListResponse {
  departments: Department[];
}

export interface CreateDepartmentRequest {
  name: string;
  description?: string;
}

export interface UpdateDepartmentRequest {
  name?: string;
  description?: string;
}

export interface AssignUserDepartmentRequest {
  department_id: string;
  is_primary?: boolean;
}
```

---

## 4. API 레이어 설계

### 4-1. 엔드포인트 상수 (`src/constants/api.ts` 추가분)

```typescript
// Admin — Department
ADMIN_DEPARTMENTS: '/api/v1/departments',
ADMIN_DEPARTMENT_DETAIL: (deptId: string) => `/api/v1/departments/${deptId}`,
ADMIN_USER_DEPT_ASSIGN: (userId: number) => `/api/v1/users/${userId}/departments`,
ADMIN_USER_DEPT_REMOVE: (userId: number, deptId: string) =>
  `/api/v1/users/${userId}/departments/${deptId}`,
```

### 4-2. 서비스 (`src/services/departmentService.ts`)

```typescript
import { authApiClient } from '@/services/api/authClient';
import { API_ENDPOINTS } from '@/constants/api';
import type {
  Department,
  DepartmentListResponse,
  CreateDepartmentRequest,
  UpdateDepartmentRequest,
  AssignUserDepartmentRequest,
} from '@/types/department';

export const departmentService = {
  getDepartments: async (): Promise<DepartmentListResponse> => {
    const { data } = await authApiClient.get<DepartmentListResponse>(
      API_ENDPOINTS.ADMIN_DEPARTMENTS,
    );
    return data;
  },

  createDepartment: async (req: CreateDepartmentRequest): Promise<Department> => {
    const { data } = await authApiClient.post<Department>(
      API_ENDPOINTS.ADMIN_DEPARTMENTS,
      req,
    );
    return data;
  },

  updateDepartment: async (deptId: string, req: UpdateDepartmentRequest): Promise<Department> => {
    const { data } = await authApiClient.patch<Department>(
      API_ENDPOINTS.ADMIN_DEPARTMENT_DETAIL(deptId),
      req,
    );
    return data;
  },

  deleteDepartment: async (deptId: string): Promise<void> => {
    await authApiClient.delete(API_ENDPOINTS.ADMIN_DEPARTMENT_DETAIL(deptId));
  },

  assignUser: async (userId: number, req: AssignUserDepartmentRequest): Promise<void> => {
    await authApiClient.post(API_ENDPOINTS.ADMIN_USER_DEPT_ASSIGN(userId), req);
  },

  removeUser: async (userId: number, deptId: string): Promise<void> => {
    await authApiClient.delete(API_ENDPOINTS.ADMIN_USER_DEPT_REMOVE(userId, deptId));
  },
};
```

### 4-3. Query Keys (`src/lib/queryKeys.ts` 추가분)

```typescript
admin: {
  all: ['admin'] as const,
  pendingUsers: () => [...queryKeys.admin.all, 'pendingUsers'] as const,
  // 신규 추가
  departments: () => [...queryKeys.admin.all, 'departments'] as const,
  department: (deptId: string) => [...queryKeys.admin.departments(), deptId] as const,
},
```

### 4-4. TanStack Query 훅 (`src/hooks/useDepartments.ts`)

```typescript
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { departmentService } from '@/services/departmentService';
import { queryKeys } from '@/lib/queryKeys';
import type { CreateDepartmentRequest, UpdateDepartmentRequest } from '@/types/department';

export const useDepartments = () =>
  useQuery({
    queryKey: queryKeys.admin.departments(),
    queryFn: departmentService.getDepartments,
  });

export const useCreateDepartment = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateDepartmentRequest) => departmentService.createDepartment(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.admin.departments() }),
  });
};

export const useUpdateDepartment = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ deptId, data }: { deptId: string; data: UpdateDepartmentRequest }) =>
      departmentService.updateDepartment(deptId, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.admin.departments() }),
  });
};

export const useDeleteDepartment = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (deptId: string) => departmentService.deleteDepartment(deptId),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.admin.departments() }),
  });
};
```

---

## 5. 라우팅 설계

### `src/App.tsx` 최종 구조

```tsx
<Routes>
  {/* 공개 라우트 */}
  <Route path="/login" element={<LoginPage />} />
  <Route path="/register" element={<RegisterPage />} />

  {/* 인증 필요 라우트 */}
  <Route element={<ProtectedRoute />}>
    <Route element={<AgentChatLayout />}>
      <Route path="/" element={<Navigate to="/chatpage" replace />} />
      <Route path="/chatpage" element={<ChatPage />} />
      {/* ... 기존 라우트 유지 */}
    </Route>
  </Route>

  {/* Admin 전용 라우트 */}
  <Route element={<AdminRoute />}>
    <Route element={<AdminLayout />}>
      <Route path="/admin/users" element={<AdminUsersPage />} />
      <Route path="/admin/departments" element={<AdminDepartmentsPage />} />
    </Route>
  </Route>
</Routes>
```

**변경 포인트**:
- `AdminRoute` 하위에 `AdminLayout` 중첩
- `AdminUsersPage`가 `AdminLayout` 안으로 이동 → 사이드바 포함
- `AdminDepartmentsPage` 신규 추가

---

## 6. AdminUsersPage 조정

**파일**: `src/pages/AdminUsersPage/index.tsx`

- `AdminLayout`이 이미 TopNav + Sidebar를 제공하므로 페이지 자체는 콘텐츠만 렌더
- `max-w-3xl` → `max-w-5xl`로 확장 (테이블 여유 공간)
- 기존 로직(approve/reject) 변경 없음

---

## 7. 구현 순서 (의존성 기반)

```
Step 1 ─ 병렬 가능 (의존성 없음)
├── [A] src/types/department.ts
├── [B] src/constants/api.ts (엔드포인트 추가)
└── [C] src/lib/queryKeys.ts (departments 키 추가)

Step 2 ─ Step 1에 의존
├── [D] src/services/departmentService.ts  (A, B 필요)
└── [E] src/hooks/useDepartments.ts        (C, D 필요)

Step 3 ─ 독립
├── [F] src/components/layout/AdminLayout.tsx (TopNav import만)
└── [G] src/components/layout/TopNav.tsx (관리 메뉴 추가)

Step 4 ─ Step 2, 3에 의존
├── [H] src/pages/AdminDepartmentsPage/index.tsx (E, F 필요)
└── [I] src/pages/AdminUsersPage/index.tsx (스타일 조정)

Step 5 ─ 통합
└── [J] src/App.tsx (라우트 재구성, F/H/I import)
```

---

## 8. 에러 처리 전략

| 시나리오 | HTTP 코드 | UI 대응 |
|---------|-----------|---------|
| 부서명 중복 | 409 Conflict | 모달 내 에러 메시지 "이미 존재하는 부서명입니다" |
| 존재하지 않는 부서 수정/삭제 | 404 | 토스트 알림 + 목록 refetch |
| 권한 없음 | 403 | AdminRoute에서 리다이렉트 (UI에 도달 불가) |
| 네트워크 오류 | — | 목록: "로딩 실패" + 재시도 버튼 |
| 유효성 검증 | 422 | 모달 내 에러 메시지 표시 |

---

## 9. 접근성 (a11y)

| 요소 | 적용 사항 |
|------|----------|
| 테이블 | `<thead>` + `<th scope="col">` |
| 모달 | `role="dialog"`, `aria-labelledby`, `aria-modal="true"` |
| 삭제 버튼 | `aria-label="부서명 삭제"` |
| 사이드바 nav | `<nav aria-label="관리 메뉴">` |
| 폼 필드 | `<label>` + `htmlFor` 연결 |

---

## 10. 테스트 계획

| 대상 | 파일 | 주요 검증 항목 |
|------|------|---------------|
| useDepartments 훅 | `src/hooks/useDepartments.test.ts` | CRUD 뮤테이션 호출, 캐시 무효화 |
| AdminLayout | `src/components/layout/AdminLayout.test.tsx` | Sidebar 렌더, 활성 메뉴 하이라이트, Outlet 렌더 |
| AdminDepartmentsPage | `src/pages/AdminDepartmentsPage/index.test.tsx` | 목록 표시, 생성/수정/삭제 플로우 |
| TopNav admin 메뉴 | `src/components/layout/TopNav.test.tsx` | role=admin 시 메뉴 표시, role=user 시 미표시 |

MSW 핸들러 추가:
```typescript
// src/__tests__/mocks/handlers.ts 에 추가
http.get('*/api/v1/departments', () => HttpResponse.json({ departments: mockDepartments })),
http.post('*/api/v1/departments', async ({ request }) => { ... }),
http.patch('*/api/v1/departments/:deptId', async ({ request }) => { ... }),
http.delete('*/api/v1/departments/:deptId', () => new HttpResponse(null, { status: 204 })),
```
