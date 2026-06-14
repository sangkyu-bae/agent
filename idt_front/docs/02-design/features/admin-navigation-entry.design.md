---
template: design
version: 1.0
feature: admin-navigation-entry
date: 2026-06-04
author: 배상규
project: idt_front
version_project: 0.0.0
---

# admin-navigation-entry Design Document

> **Summary**: 관리자(role==='admin')가 메인 앱(`AppSidebar`) 하단에서 단일 "관리자" 메뉴로 관리자 영역(`/admin/users`)에 진입할 수 있게 하고, 관리자 메뉴 정의를 단일 소스(`constants/adminNav.ts`)로 통합하여 `AppSidebar`·`AdminLayout`·`TopNav`가 공유하도록 한다.
>
> **Project**: idt_front
> **Version**: 0.0.0
> **Author**: 배상규
> **Date**: 2026-06-04
> **Status**: Draft
> **Planning Doc**: [admin-navigation-entry.plan.md](../../01-plan/features/admin-navigation-entry.plan.md)

### Pipeline References

| Phase | Document | Status |
|-------|----------|--------|
| Phase 6 | UI Navigation (this design) | 🔄 |

---

## 1. Overview

### 1.1 Design Goals

- 메인 앱(`AgentChatLayout` → `AppSidebar`)에 관리자 영역 **진입점**을 추가하되, `user.role === 'admin'`일 때만 렌더링한다.
- 진입은 **단일 링크 방식**: "관리자" 클릭 → `/admin/users`로 이동. 진입 이후 페이지 간 이동은 기존 `AdminLayout` 사이드바가 담당한다.
- 관리자 메뉴 정의(label/path/icon)를 **단일 소스**(`src/constants/adminNav.ts`)로 모아 `AdminLayout`·`TopNav`가 공유하게 하여 중복·누락(RAGAS·Agent Run)을 제거한다.
- 백엔드/라우트 가드는 변경하지 않는다 (`AdminRoute`가 최종 방어선, 메뉴는 보조 UX 레이어).

### 1.2 Design Principles

- **Single Source of Truth**: 메뉴 *데이터*만 공유한다. 렌더링/스타일은 각 컴포넌트(어두운 사이드바 vs 흰 사이드바 vs 드롭다운)가 그대로 유지한다 → 시각 회귀 최소화.
- **Defense in Depth**: 메뉴 노출 조건(`role==='admin'`)은 UX 편의일 뿐, 접근 통제는 기존 `AdminRoute`가 책임진다.
- **Minimal Surface**: 신규 1파일 + 기존 3파일 수정. 새 페이지/대시보드/라우트 추가 없음.
- **No Backend Coupling**: 순수 클라이언트 네비게이션. API 호출/타입/서비스 변경 없음.

---

## 2. Architecture

### 2.1 Component Diagram

```
┌──────────────────────────────────────────────────────────────┐
│ constants/adminNav.ts  (NEW — Single Source of Truth)        │
│   - ADMIN_NAV_ITEMS: { label, path, icon, description }[]    │
│   - ADMIN_ENTRY_PATH = '/admin/users'                        │
└───────┬───────────────────┬───────────────────┬─────────────┘
        │ (entry path)      │ (items)           │ (items)
        ▼                   ▼                   ▼
┌───────────────┐  ┌──────────────────┐  ┌──────────────────┐
│ AppSidebar    │  │ AdminLayout      │  │ TopNav           │
│ (메인, 어두움)│  │ (관리자 사이드바)│  │ (관리자 드롭다운)│
│ 진입 메뉴     │  │ 4개 페이지 네비  │  │ ADMIN_MENU       │
│ role==admin   │  │                  │  │ role==admin      │
└──────┬────────┘  └──────────────────┘  └──────────────────┘
       │ navigate('/admin/users')
       ▼
┌──────────────────────────────────────────────────────────────┐
│ App.tsx 라우트 — <AdminRoute> 가드 → <AdminLayout> (기존)    │
└──────────────────────────────────────────────────────────────┘
```

### 2.2 Navigation Flow

#### 2.2.1 관리자 진입 (메인 → 관리자)

```
관리자 로그인 (user.role === 'admin')
  → AgentChatLayout 렌더 → AppSidebar 하단에 "관리자" 메뉴 노출
  → 클릭 → navigate(ADMIN_ENTRY_PATH = '/admin/users')
  → AdminRoute 통과(role==='admin') → AdminLayout 렌더
  → AdminLayout 사이드바(ADMIN_NAV_ITEMS)로 4개 페이지 간 이동
```

#### 2.2.2 일반 사용자 (메뉴 미노출)

```
일반 로그인 (user.role === 'user')
  → AppSidebar 하단 "관리자" 메뉴 렌더되지 않음
  → (URL 직접 입력 시) AdminRoute가 '/'로 리다이렉트 (기존 동작 유지)
```

#### 2.2.3 관리자 → 메인 복귀

```
AdminLayout 하단 "메인으로 돌아가기" → navigate('/chatpage')  (기존 유지)
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `AppSidebar` | `useAuthStore`, `ADMIN_ENTRY_PATH`, `useNavigate` | 진입 메뉴 조건부 렌더 + 이동 |
| `AdminLayout` | `ADMIN_NAV_ITEMS`, `useNavigate`, `useLocation` | 4개 페이지 네비 (데이터만 교체) |
| `TopNav` | `ADMIN_NAV_ITEMS`, `useAuthStore` | ADMIN_MENU 구성 (데이터만 교체) |
| `constants/adminNav.ts` | (없음) | 메뉴 단일 소스 |

---

## 3. Data Model

### 3.1 단일 소스 정의 (`src/constants/adminNav.ts`)

```typescript
export interface AdminNavItem {
  label: string;
  path: string;
  /** Heroicons outline path 'd' attribute */
  icon: string;
  /** TopNav 드롭다운에서 사용하는 보조 설명 */
  description: string;
}

/** 관리자 영역 4개 페이지 — AdminLayout 사이드바 / TopNav ADMIN_MENU 공유 */
export const ADMIN_NAV_ITEMS: AdminNavItem[] = [
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
  {
    label: 'RAGAS 평가',
    path: '/admin/ragas',
    icon: 'M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 0 1 3 19.875v-6.75ZM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 0 1-1.125-1.125V8.625ZM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 0 1-1.125-1.125V4.125Z',
    description: 'RAGAS 기반 답변 품질 평가',
  },
  {
    label: 'Agent Run 관측',
    path: '/admin/agent-runs',
    icon: 'M2.25 18 9 11.25l4.306 4.306a11.95 11.95 0 0 1 5.814-5.518l2.74-1.22m0 0-5.94-2.281m5.94 2.28-2.28 5.941',
    description: '에이전트 실행 이력·사용량 관측',
  },
];

/** 메인 앱에서 관리자 영역 진입 시 첫 페이지 */
export const ADMIN_ENTRY_PATH = '/admin/users';
```

> icon path는 기존 `AdminLayout.ADMIN_SIDEBAR_ITEMS` 및 `TopNav.ADMIN_MENU`에서 그대로 추출한다.
> RAGAS·Agent Run의 description은 신규 추가(기존 TopNav에 없던 항목).

### 3.2 진입 메뉴 항목 (AppSidebar 전용)

`AppSidebar` 진입 메뉴는 `ADMIN_NAV_ITEMS`를 펼치지 않고 단일 항목으로 표현한다.

```typescript
const ADMIN_ENTRY_ITEM = {
  label: '관리자',
  path: ADMIN_ENTRY_PATH,            // '/admin/users'
  iconPath:
    'M9 12.75 11.25 15 15 9.75M21 12c0 1.268-.63 2.39-1.593 3.068a3.745 3.745 0 0 1-1.043 3.296 3.745 3.745 0 0 1-3.296 1.043A3.745 3.745 0 0 1 12 21c-1.268 0-2.39-.63-3.068-1.593a3.746 3.746 0 0 1-3.296-1.043 3.745 3.745 0 0 1-1.043-3.296A3.745 3.745 0 0 1 3 12c0-1.268.63-2.39 1.593-3.068a3.745 3.745 0 0 1 1.043-3.296 3.745 3.745 0 0 1 3.296-1.043A3.745 3.745 0 0 1 12 3c1.268 0 2.39.63 3.068 1.593a3.746 3.746 0 0 1 3.296 1.043 3.746 3.746 0 0 1 1.043 3.296A3.745 3.745 0 0 1 21 12Z', // shield-check 계열 (관리자 식별용)
};
```

---

## 4. UI/UX Design

### 4.1 AppSidebar — 진입 메뉴 배치

위치: `AppSidebar` 하단 `BOTTOM_ITEMS`(즐겨찾기/역할설정/리소스/환경설정) 영역. 관리자일 때만 해당 그룹 상단(또는 하단)에 "관리자" 항목을 1개 추가한다.

```
┌─ AppSidebar (어두운 배경 #0f0f0f) ──────────────┐
│  [로고]                                          │
│  [+ 새 에이전트]                                 │
│  NAV_ITEMS (SUPER AI / 템플릿 / 유틸리티 / ...)  │
│  ───────────────────────────────                 │
│  에이전트 목록 (스크롤)                          │
│  ───────────────────────────────                 │
│  BOTTOM_ITEMS                                    │
│    즐겨찾기 / 역할설정 / 리소스 / 환경설정       │
│    ★ 관리자   ← role==='admin'일 때만 추가       │
│  ───────────────────────────────                 │
│  [user 프로필 + 로그아웃]                        │
└──────────────────────────────────────────────────┘
```

### 4.2 진입 메뉴 렌더링 규칙

| 조건 | 동작 |
|------|------|
| `user?.role === 'admin'` | "관리자" 항목 렌더 |
| `user?.role !== 'admin'` (또는 user 없음) | 렌더하지 않음 |
| 클릭 | `navigate(ADMIN_ENTRY_PATH)` |
| 현재 경로가 `/admin`으로 시작 | active 스타일 적용 (선택, FR-06) |

### 4.3 스타일 (기존 BOTTOM_ITEMS 패턴 재사용)

진입 메뉴는 `BOTTOM_ITEMS`의 버튼 스타일을 그대로 따른다. 단, 관리자 식별을 위해 active가 아닐 때도 약간 강조(violet) 처리 옵션을 둔다.

| 상태 | className |
|------|----------|
| 기본 | `flex w-full items-center gap-3 rounded-xl px-3 py-2 text-[12.5px] text-violet-300/70 hover:bg-white/[0.07] hover:text-violet-200 transition-all` |
| active (`/admin/*`) | `bg-white/[0.12] text-white` |

> 기존 BOTTOM_ITEMS 색(`text-white/30`)과 구분되도록 violet 계열을 사용해 "관리자 전용" 시각 단서를 제공한다.

### 4.4 AdminLayout — 데이터 교체 (스타일 무변경)

- 기존 모듈 상수 `ADMIN_SIDEBAR_ITEMS`(파일 내 하드코딩 4개)를 제거하고 `ADMIN_NAV_ITEMS`를 import하여 사용한다.
- 기존 필드명 `icon`은 `ADMIN_NAV_ITEMS`의 `icon`과 동일하므로 매핑 그대로 동작한다.
- 렌더링 JSX/스타일/`isActive` 로직은 변경하지 않는다.

### 4.5 TopNav — ADMIN_MENU 데이터 교체 + 누락 보강

- 기존 `ADMIN_MENU.items`(2개: 사용자/부서)를 `ADMIN_NAV_ITEMS`(4개) 기반으로 생성한다.

```typescript
const ADMIN_MENU: NavMenu = {
  label: '관리',
  items: ADMIN_NAV_ITEMS, // label/path/icon/description 구조 동일
};
```

- `menus = user?.role === 'admin' ? [...NAV_MENUS, ADMIN_MENU] : NAV_MENUS;` (기존 유지)
- 결과: 관리 드롭다운에 RAGAS 평가·Agent Run 관측이 추가로 노출된다.

---

## 5. Error / Edge Cases

| 케이스 | 처리 |
|--------|------|
| `user`가 null (비로그인) | 진입 메뉴 미노출. (메인 앱은 `ProtectedRoute` 하위이므로 비로그인 도달 불가) |
| persist된 `user.role`이 stale하여 비관리자에게 노출 | 클릭 시 `AdminRoute`가 `/`로 리다이렉트 → 실접근 차단 |
| `ADMIN_NAV_ITEMS`가 빈 배열인 경우 | AdminLayout/TopNav는 빈 메뉴 렌더(런타임 에러 없음). 진입 메뉴는 별도 `ADMIN_ENTRY_PATH` 사용으로 영향 없음 |
| 라우트(`/admin/users`)가 App.tsx에 없는 경우 | 해당 사항 없음(이미 존재). 변경 시 라우트 동기화 필요 |

---

## 6. Security Considerations

- [x] **접근 통제 불변**: 메뉴 노출은 UX 편의. 실제 인가는 기존 `AdminRoute`(`user?.role !== 'admin'` → redirect)가 담당.
- [x] **민감정보 노출 없음**: 메뉴는 라우트 경로/라벨/아이콘만 포함, 데이터 fetch 없음.
- [x] **클라이언트 신뢰 금지**: 관리자 API 보호는 백엔드 책임(본 작업 범위 외). 프론트 role 체크는 보조 레이어임을 명시.

---

## 7. Test Plan

### 7.1 Test Scope

| Type | Target | Tool |
|------|--------|------|
| Component | `AppSidebar` 진입 메뉴 노출/비노출 + 클릭 네비게이션 | Vitest + RTL + react-router (MemoryRouter) |
| Component | `TopNav` ADMIN_MENU 4개 항목 노출 (admin) | Vitest + RTL |
| (선택) Unit | `adminNav` 상수 일관성 (path 중복 없음, 4개) | Vitest |

### 7.2 Test Cases

#### 7.2.1 `AppSidebar.test.tsx`

| # | 케이스 | 사전조건 | 검증 |
|---|--------|----------|------|
| A1 | 관리자일 때 "관리자" 메뉴 노출 | `useAuthStore` user.role='admin' | `getByRole('button', { name: '관리자' })` 존재 |
| A2 | 일반 사용자일 때 미노출 | user.role='user' | `queryByRole('button', { name: '관리자' })` null |
| A3 | user 없음일 때 미노출 | user=null | `queryByRole('button', { name: '관리자' })` null |
| A4 | "관리자" 클릭 시 /admin/users 이동 | role='admin' | navigate('/admin/users') 호출 (router location 변경 확인) |

#### 7.2.2 `TopNav.test.tsx`

| # | 케이스 | 사전조건 | 검증 |
|---|--------|----------|------|
| T1 | admin 시 "관리" 메뉴 노출 | role='admin' | "관리" 버튼 존재 |
| T2 | "관리" 드롭다운에 4개 항목 | role='admin', 메뉴 오픈 | 사용자/부서/RAGAS/Agent Run 텍스트 모두 존재 |
| T3 | 일반 사용자 시 "관리" 메뉴 미노출 | role='user' | "관리" 버튼 null |

#### 7.2.3 `adminNav.test.ts` (선택)

| # | 케이스 | 검증 |
|---|--------|------|
| N1 | ADMIN_NAV_ITEMS 4개 | `length === 4` |
| N2 | path 유일성 | path 중복 없음 |
| N3 | ADMIN_ENTRY_PATH 포함 | items에 `/admin/users` 존재 |

### 7.3 Auth Store 모킹 패턴

```typescript
import { useAuthStore } from '@/store/authStore';

beforeEach(() => {
  useAuthStore.setState({
    user: { id: 1, email: 'admin@test.com', role: 'admin', status: 'approved' },
    isAuthenticated: true,
  });
});
// role='user' 케이스는 각 테스트에서 setState로 덮어쓴다.
```

> 라우터는 `MemoryRouter`로 감싸고, 네비게이션 검증은 `useNavigate` mock 또는 location 표시용 테스트 컴포넌트를 사용한다.

---

## 8. Clean Architecture

### 8.1 Layer Assignment

| Layer | Responsibility | 이번 기능 매핑 |
|-------|---------------|----------------|
| **Presentation** | UI + 상호작용 | `AppSidebar`, `AdminLayout`, `TopNav` |
| **Domain/Const** | 공유 상수/모델 | `constants/adminNav.ts` |
| **Application** | 상태 | `store/authStore`(기존, 변경 없음) |

### 8.2 Import Rules Compliance

| From | To | 허용 여부 |
|------|------|----------|
| `components/layout/*` → `constants/adminNav` | Presentation → Const | ✅ |
| `components/layout/*` → `store/authStore` | Presentation → Application | ✅ |
| `constants/adminNav` → (없음) | 의존성 없음 | ✅ |

---

## 9. Coding Convention Reference

| Item | Convention Applied |
|------|-------------------|
| 상수 위치 | 공유 상수는 `src/constants/`에 배치 (`api.ts`와 동일) |
| 타입 네이밍 | `AdminNavItem` (도메인 모델, 접미사 없음) |
| 상수 네이밍 | `ADMIN_NAV_ITEMS`, `ADMIN_ENTRY_PATH` (UPPER_SNAKE) |
| 컴포넌트 | 기존 `AppSidebar`/`AdminLayout`/`TopNav` 패턴 유지 (PascalCase) |
| 테스트 위치 | 컴포넌트 옆 `*.test.tsx`, 상수 옆 `*.test.ts` |
| Role 판별 | `useAuthStore().user?.role === 'admin'` |

---

## 10. Implementation Guide

### 10.1 변경 파일 목록

#### 신규 파일

| 파일 | 역할 |
|------|------|
| `src/constants/adminNav.ts` | `ADMIN_NAV_ITEMS` + `ADMIN_ENTRY_PATH` 단일 소스 |
| `src/components/layout/AppSidebar.test.tsx` | 진입 메뉴 노출/네비 테스트 |
| `src/components/layout/TopNav.test.tsx` | ADMIN_MENU 4개 항목 테스트 |
| `src/constants/adminNav.test.ts` (선택) | 상수 일관성 테스트 |

#### 수정 파일

| 파일 | 변경 내용 |
|------|----------|
| `src/components/layout/AppSidebar.tsx` | `useAuthStore` import, `ADMIN_ENTRY_PATH` import, BOTTOM_ITEMS 영역에 admin 조건부 진입 메뉴 추가 |
| `src/components/layout/AdminLayout.tsx` | 하드코딩 `ADMIN_SIDEBAR_ITEMS` 제거 → `ADMIN_NAV_ITEMS` import 사용 |
| `src/components/layout/TopNav.tsx` | 하드코딩 `ADMIN_MENU.items` 제거 → `ADMIN_NAV_ITEMS` 사용 (RAGAS·Agent Run 자동 포함) |

> `AppSidebar`는 이미 `useAuthStore`를 import하고 있으므로(`const { user } = useAuthStore()`), role 조건만 추가하면 된다.

### 10.2 TDD 구현 순서

```
Phase 1: 단일 소스 (Green 기반)
  1. src/constants/adminNav.ts 작성 (ADMIN_NAV_ITEMS 4개 + ADMIN_ENTRY_PATH)
  2. (선택) adminNav.test.ts N1~N3 작성·통과

Phase 2: AppSidebar 진입 메뉴 (Red → Green)
  3. Red  — AppSidebar.test.tsx A1~A4 작성 → 실패
  4. Green — AppSidebar.tsx에 admin 조건부 진입 메뉴 추가 → A1~A4 통과

Phase 3: 메뉴 정의 통합 (Red → Green)
  5. Red  — TopNav.test.tsx T1~T3 작성 → 실패(현재 2개만 노출)
  6. Green — TopNav.tsx ADMIN_MENU.items = ADMIN_NAV_ITEMS 로 교체 → T1~T3 통과
  7. AdminLayout.tsx ADMIN_SIDEBAR_ITEMS → ADMIN_NAV_ITEMS 교체 (시각 회귀 확인)

Phase 4: 검증
  8. npm run type-check + npm run lint + npm run test:run
  9. npm run dev →
     - 관리자 로그인: 사이드바 하단 "관리자" 클릭 → /admin/users 진입 확인
     - 관리자 영역 사이드바 4개 메뉴 동작 확인
     - 상단 "관리" 드롭다운 4개 항목 확인
     - 일반 사용자 로그인: "관리자"/"관리" 메뉴 미노출 확인
```

---

## 11. Definition of Done

- [ ] `src/constants/adminNav.ts` — `ADMIN_NAV_ITEMS`(4개) + `ADMIN_ENTRY_PATH` 정의
- [ ] `src/components/layout/AppSidebar.tsx` — role==='admin'일 때만 "관리자" 진입 메뉴 노출, 클릭 시 `/admin/users` 이동
- [ ] `src/components/layout/AdminLayout.tsx` — `ADMIN_NAV_ITEMS` 사용으로 교체 (시각 동일)
- [ ] `src/components/layout/TopNav.tsx` — `ADMIN_NAV_ITEMS` 사용, RAGAS·Agent Run 포함
- [ ] `AppSidebar.test.tsx` A1~A4 통과
- [ ] `TopNav.test.tsx` T1~T3 통과
- [ ] `npm run type-check`, `npm run lint`, `npm run test:run` 통과
- [ ] `npm run build` 성공
- [ ] 관리자/일반 사용자 각각 수동 검증 완료

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-06-04 | Initial design — Plan 기반 설계 (단일 소스 + 진입점 + 테스트 매핑) | 배상규 |
