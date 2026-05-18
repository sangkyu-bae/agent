# admin-ui Plan

> 관리자 네비게이션 바 + 관리자 전용 레이아웃(사이드바) + 부서 관리 페이지

## 1. 배경 및 목표

### AS-IS (현재)

- 관리자(`role: 'admin'`) 로그인 후에도 **관리 페이지로 이동할 수 있는 UI 진입점이 없음**
- `/admin/users` 라우트가 존재하지만 `AgentChatLayout` 바깥에 배치되어 **사이드바/헤더 없이 단독 렌더링**됨
- 관리자 페이지가 `AdminUsersPage` (사용자 승인) 하나뿐이며 **부서 관리 기능이 없음**
- 백엔드에는 부서 CRUD API (`/api/v1/departments`) + 사용자-부서 배정 API가 이미 구현됨

### TO-BE (목표)

1. **관리자 전용 TopNav 메뉴**: admin 권한 유저 로그인 시 TopNav에 "관리" 메뉴가 추가로 표시됨
2. **관리자 전용 레이아웃**: `/admin/*` 경로 진입 시 좌측 사이드바가 있는 전용 레이아웃 적용
3. **부서 관리 페이지**: 부서 CRUD + 사용자-부서 배정/해제 UI 구현
4. **기존 사용자 관리 페이지**: 관리자 레이아웃 안에 통합

---

## 2. API 스펙 요약 (백엔드 구현 완료)

### 2-1. 부서 CRUD

| Method | Path | 설명 | 권한 |
|--------|------|------|------|
| GET | `/api/v1/departments` | 부서 목록 조회 | 인증 사용자 |
| POST | `/api/v1/departments` | 부서 생성 | admin |
| PATCH | `/api/v1/departments/{dept_id}` | 부서 수정 | admin |
| DELETE | `/api/v1/departments/{dept_id}` | 부서 삭제 | admin |

### 2-2. 사용자-부서 배정

| Method | Path | 설명 | 권한 |
|--------|------|------|------|
| POST | `/api/v1/users/{user_id}/departments` | 사용자에 부서 배정 | admin |
| DELETE | `/api/v1/users/{user_id}/departments/{dept_id}` | 사용자 부서 해제 | admin |

### 2-3. 스키마 (백엔드 Pydantic)

```python
# Request
CreateDepartmentRequest { name: str, description: str | None }
UpdateDepartmentRequest { name: str | None, description: str | None }
AssignUserDepartmentRequest { department_id: str, is_primary: bool = False }

# Response
DepartmentResponse { id: str, name: str, description: str | None, created_at: str, updated_at: str }
DepartmentListResponse { departments: list[DepartmentResponse] }
```

---

## 3. 구현 범위

### 3-1. TopNav 관리자 메뉴 추가

**파일**: `src/components/layout/TopNav.tsx`

- `user.role === 'admin'` 일 때만 "관리" 메뉴를 `NAV_MENUS` 뒤에 추가 렌더링
- 드롭다운 아이템:
  - 사용자 관리 → `/admin/users`
  - 부서 관리 → `/admin/departments`
- 기존 `NAV_MENUS` 상수는 변경하지 않고, admin 전용 메뉴를 조건부 병합

```tsx
// 조건부 렌더링 예시
const adminMenu: NavMenu = {
  label: '관리',
  items: [
    { label: '사용자 관리', path: '/admin/users', icon: '...', description: '가입 승인 및 사용자 관리' },
    { label: '부서 관리', path: '/admin/departments', icon: '...', description: '부서 생성·수정·삭제 및 사용자 배정' },
  ],
};

const menus = user?.role === 'admin' ? [...NAV_MENUS, adminMenu] : NAV_MENUS;
```

### 3-2. 관리자 전용 레이아웃 (`AdminLayout`)

**신규 파일**: `src/components/layout/AdminLayout.tsx`

- 구조: TopNav(상단) + AdminSidebar(좌측) + `<Outlet />`(본문)
- `AgentChatLayout`과 **별도 레이아웃** — 관리 영역은 채팅 사이드바/세션 패널이 불필요
- `AdminRoute` 가드 하위에 중첩

```
┌─────────────────────────────────────────────┐
│  TopNav (기존 TopNav 재사용)                  │
├──────────┬──────────────────────────────────┤
│ Admin    │                                  │
│ Sidebar  │    <Outlet /> (관리 페이지 본문)   │
│          │                                  │
│ - 사용자 │                                  │
│ - 부서   │                                  │
│          │                                  │
└──────────┴──────────────────────────────────┘
```

#### AdminSidebar 스타일

- 너비: `w-56` (224px) — 채팅 사이드바보다 좁게
- 배경: `bg-zinc-50` + `border-r border-zinc-200`
- 메뉴 아이템: 아이콘 + 레이블, 활성 상태 시 `bg-violet-50 text-violet-700`
- 메뉴 목록:
  - 사용자 관리 (`/admin/users`)
  - 부서 관리 (`/admin/departments`)
- 하단: "← 메인으로 돌아가기" 링크 (`/chatpage`로 navigate)

### 3-3. 라우팅 변경

**파일**: `src/App.tsx`

```tsx
// AS-IS
<Route element={<AdminRoute />}>
  <Route path="/admin/users" element={<AdminUsersPage />} />
</Route>

// TO-BE
<Route element={<AdminRoute />}>
  <Route element={<AdminLayout />}>
    <Route path="/admin/users" element={<AdminUsersPage />} />
    <Route path="/admin/departments" element={<AdminDepartmentsPage />} />
  </Route>
</Route>
```

### 3-4. 타입 정의

**신규 파일**: `src/types/department.ts`

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

### 3-5. API 상수 추가

**파일**: `src/constants/api.ts`

```typescript
// Admin — Department
ADMIN_DEPARTMENTS: '/api/v1/departments',
ADMIN_DEPARTMENT_DETAIL: (deptId: string) => `/api/v1/departments/${deptId}`,
ADMIN_USER_DEPARTMENT_ASSIGN: (userId: number) => `/api/v1/users/${userId}/departments`,
ADMIN_USER_DEPARTMENT_REMOVE: (userId: number, deptId: string) =>
  `/api/v1/users/${userId}/departments/${deptId}`,
```

### 3-6. 서비스 레이어

**신규 파일**: `src/services/departmentService.ts`

```typescript
const departmentService = {
  getDepartments: () => authApiClient.get<DepartmentListResponse>(...),
  createDepartment: (data: CreateDepartmentRequest) => authApiClient.post<Department>(...),
  updateDepartment: (deptId: string, data: UpdateDepartmentRequest) => authApiClient.patch<Department>(...),
  deleteDepartment: (deptId: string) => authApiClient.delete(...),
  assignUser: (userId: number, data: AssignUserDepartmentRequest) => authApiClient.post(...),
  removeUser: (userId: number, deptId: string) => authApiClient.delete(...),
};
```

### 3-7. TanStack Query 훅

**신규 파일**: `src/hooks/useDepartments.ts`

| 훅 이름 | 타입 | 설명 |
|---------|------|------|
| `useDepartments` | useQuery | 부서 목록 조회 |
| `useCreateDepartment` | useMutation | 부서 생성 |
| `useUpdateDepartment` | useMutation | 부서 수정 |
| `useDeleteDepartment` | useMutation | 부서 삭제 |
| `useAssignUserDepartment` | useMutation | 사용자에 부서 배정 |
| `useRemoveUserDepartment` | useMutation | 사용자 부서 해제 |

QueryKeys 추가: `queryKeys.admin.departments()`, `queryKeys.admin.department(id)`

### 3-8. 부서 관리 페이지

**신규 파일**: `src/pages/AdminDepartmentsPage/index.tsx`

#### UI 구성

```
┌─────────────────────────────────────────────────┐
│ [Admin] 부서 관리                    [+ 부서 추가] │
│ 부서를 생성·수정·삭제하고 사용자를 배정합니다.         │
├─────────────────────────────────────────────────┤
│ ┌───────────────────────────────────────────┐   │
│ │ 부서명 | 설명 | 생성일 | 수정일 | 액션      │   │
│ ├───────────────────────────────────────────┤   │
│ │ 개발팀 | 백엔드/프론트 | 2025-05-01 | ... │   │
│ │                        [수정] [삭제]       │   │
│ ├───────────────────────────────────────────┤   │
│ │ 기획팀 | 서비스 기획   | 2025-05-02 | ... │   │
│ │                        [수정] [삭제]       │   │
│ └───────────────────────────────────────────┘   │
└─────────────────────────────────────────────────┘
```

#### 기능 목록

| 기능 | 설명 |
|------|------|
| 부서 목록 | 테이블 형태로 부서 목록 표시 |
| 부서 추가 | 모달 또는 인라인 폼으로 name, description 입력 |
| 부서 수정 | 기존 값이 채워진 모달 → PATCH 호출 |
| 부서 삭제 | ConfirmDialog로 확인 후 DELETE 호출 |
| 빈 상태 | 부서가 없을 때 안내 메시지 + 추가 버튼 |
| 로딩/에러 | 스켈레톤 또는 스피너 + 에러 메시지 표시 |

### 3-9. AdminUsersPage 리팩토링

**파일**: `src/pages/AdminUsersPage/index.tsx`

- AdminLayout의 스크롤 컨테이너 안에서 렌더링되므로 **패턴 B (전체 스크롤)** 적용
- 기존 `mx-auto max-w-3xl` → `max-w-7xl`로 확장 (테이블이므로 넓은 영역)
- 상단 Admin 레이블/타이틀은 유지하되 AdminLayout 헤더와 중복되지 않게 조정

---

## 4. 파일 변경 목록

### 신규 파일

| 파일 | 설명 |
|------|------|
| `src/components/layout/AdminLayout.tsx` | 관리자 전용 레이아웃 (TopNav + Sidebar + Outlet) |
| `src/types/department.ts` | 부서 타입 정의 |
| `src/services/departmentService.ts` | 부서 API 서비스 |
| `src/hooks/useDepartments.ts` | 부서 TanStack Query 훅 |
| `src/pages/AdminDepartmentsPage/index.tsx` | 부서 관리 페이지 |

### 수정 파일

| 파일 | 변경 내용 |
|------|----------|
| `src/App.tsx` | AdminLayout 중첩 라우트 구성, AdminDepartmentsPage 라우트 추가 |
| `src/components/layout/TopNav.tsx` | admin 역할 시 "관리" 메뉴 조건부 추가 |
| `src/constants/api.ts` | 부서 관련 엔드포인트 상수 추가 |
| `src/lib/queryKeys.ts` | departments 쿼리키 팩토리 추가 |
| `src/pages/AdminUsersPage/index.tsx` | max-w 조정, AdminLayout 내부 스타일 맞춤 |

---

## 5. 구현 순서

| 순서 | 작업 | 의존성 |
|------|------|--------|
| 1 | 타입 정의 (`department.ts`) | 없음 |
| 2 | API 상수 추가 (`api.ts`) | 없음 |
| 3 | 서비스 레이어 (`departmentService.ts`) | 1, 2 |
| 4 | 쿼리키 추가 (`queryKeys.ts`) | 없음 |
| 5 | TanStack Query 훅 (`useDepartments.ts`) | 3, 4 |
| 6 | AdminLayout 컴포넌트 | 없음 |
| 7 | TopNav 관리자 메뉴 추가 | 없음 |
| 8 | 라우팅 변경 (`App.tsx`) | 6 |
| 9 | AdminDepartmentsPage | 5, 6 |
| 10 | AdminUsersPage 스타일 조정 | 6 |

---

## 6. 제외 사항 (이번 범위 밖)

- 부서별 사용자 배정/해제 UI (드래그앤드롭, 모달 내 사용자 검색 등) → 후속 기능으로 분리
- 부서별 에이전트 권한 관리 → 별도 Plan
- 관리자 대시보드 (통계, 차트) → 별도 Plan
- 반응형 모바일 대응 → 현재 데스크톱 우선

---

## 7. 비기능 요구사항

| 항목 | 기준 |
|------|------|
| 권한 검증 | `AdminRoute` + 백엔드 `require_role("admin")` 이중 검증 |
| 에러 처리 | 409 Conflict (중복 부서명) → 사용자 친화적 메시지 표시 |
| 낙관적 업데이트 | 삭제 시 목록에서 즉시 제거 → 실패 시 롤백 |
| 접근성 | 테이블 `<thead>`, 버튼 `aria-label` 적용 |
