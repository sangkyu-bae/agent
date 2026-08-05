---
template: design
version: 1.0
feature: admin-nav-restructure
date: 2026-08-02
author: 배상규
project: idt_front
---

# admin-nav-restructure Design Document

> **Summary**: `adminNav.ts`를 그룹 구조(`ADMIN_NAV_GROUPS` 4그룹)로 재편하고, `AdminLayout` 사이드바는 그룹만 렌더링 + 본문 상단에 2차 탭 바를 레이아웃이 소유하는 방식으로 렌더링한다. TopNav "관리" 드롭다운은 그룹 헤더로 구분한다. 기존 11개 URL·페이지 컴포넌트는 무수정.
>
> **Project**: idt_front
> **Author**: 배상규
> **Date**: 2026-08-02
> **Status**: Draft
> **Planning Doc**: [admin-nav-restructure.plan.md](../../01-plan/features/admin-nav-restructure.plan.md)

---

## 1. Overview

### 1.1 Design Goals

- 사이드바 항목을 11개 → **그룹 4개**로 줄인다: 관측 / 조직 관리 / 문서·품질 / 에이전트 리소스.
- 그룹 클릭 → 그룹 첫 탭 경로로 이동. 하위 페이지 전환은 **본문 상단 2차 탭 바**가 담당한다.
- 탭 바는 `AdminLayout`이 소유한다 — 11개 페이지 컴포넌트는 한 줄도 수정하지 않는다.
- URL은 전부 기존 유지 (`/admin/users` 등). 라우트(`App.tsx`)도 무수정.
- 단일 소스 원칙 유지: 그룹/탭/TopNav 드롭다운/진입 경로가 모두 `adminNav.ts`에서 파생.

### 1.2 Design Principles

- **Layout-owned tabs**: 탭 바를 레이아웃에 두어 페이지 무수정·라우트 무변경으로 2차 네비를 얻는다 (라우트 중첩 재구성 대안은 11개 라우트 + 테스트 전면 수정이라 기각).
- **Data-driven**: 그룹 판정·활성 매칭은 전부 상수에서 파생한 순수 함수 — 컴포넌트에 경로 하드코딩 금지.
- **관계 기반 테스트 단언**: 개수 하드코딩(기존 N1 `toHaveLength(10)` 어긋남) 대신 "그룹 flatten = 전체 항목" 관계로 단언한다.

---

## 2. Architecture

### 2.1 Component Diagram

```
┌────────────────────────────────────────────────────────────────┐
│ constants/adminNav.ts  (단일 소스 — 구조 변경)                  │
│   AdminNavItem (기존 유지)                                     │
│   AdminNavGroup { key, label, icon, items }  (NEW)             │
│   ADMIN_NAV_GROUPS: AdminNavGroup[4]         (NEW)             │
│   ADMIN_NAV_ITEMS = groups.flatMap(items)    (파생, 하위 호환) │
│   ADMIN_ENTRY_PATH = groups[0].items[0].path (= /admin/dashboard)│
│   findAdminGroupByPath(pathname)             (NEW 유틸)        │
│   isAdminItemActive(item, pathname)          (NEW 유틸)        │
└──────┬──────────────────────┬──────────────────────┬───────────┘
       ▼                      ▼                      ▼
┌──────────────┐   ┌────────────────────┐   ┌──────────────────┐
│ AppSidebar   │   │ AdminLayout        │   │ TopNav           │
│ (진입점)     │   │ 사이드바: 그룹 4개 │   │ ADMIN_MENU:      │
│ ENTRY_PATH만 │   │ 본문 상단: 탭 바   │   │ 그룹 헤더 구분   │
│ 소비 (무수정)│   │ + <Outlet/>        │   │ 드롭다운         │
└──────────────┘   └────────────────────┘   └──────────────────┘
```

### 2.2 확정 그룹 데이터

| # | key | label | 그룹 아이콘(재사용) | items (탭 순서) |
|---|-----|-------|---------------------|-----------------|
| 1 | `observability` | 관측 | 운영 대시보드 grid 아이콘 | 운영 대시보드(`/admin/dashboard`) → Agent Run 관측(`/admin/agent-runs`) |
| 2 | `org` | 조직 관리 | 사용자 관리 users 아이콘 | 사용자 관리(`/admin/users`) → 부서 관리(`/admin/departments`) |
| 3 | `docs-quality` | 문서·품질 | 청킹 프로파일 lines 아이콘 | 청킹 프로파일(`/admin/chunking-profiles`) → RAGAS 평가(`/admin/ragas`) |
| 4 | `agent-resources` | 에이전트 리소스 | 도구 관리 wrench 아이콘 | MCP 서버(`/admin/mcp-servers`) → 도구 관리(`/admin/tools`) → Skill 관리(`/admin/skills`) → LLM 모델(`/admin/llm-models`) → 위키 관리(`/admin/wiki`) |

- 11개 `AdminNavItem`은 기존 label/path/icon/description 그대로 그룹 안으로 이동만 한다.
- `ADMIN_NAV_ITEMS` flatten 순서가 기존과 달라지지만(대시보드→agent-runs→users→…), 소비처는 path 기반이라 영향 없음 (TopNav T2 단언은 존재 여부만 검사).

---

## 3. Detailed Design

### 3.1 `constants/adminNav.ts`

```ts
export interface AdminNavItem { label: string; path: string; icon: string; description: string; }

export interface AdminNavGroup {
  key: 'observability' | 'org' | 'docs-quality' | 'agent-resources';
  label: string;
  /** 사이드바 그룹 아이콘 — 대표 하위 항목 아이콘 재사용 */
  icon: string;
  items: AdminNavItem[];
}

export const ADMIN_NAV_GROUPS: AdminNavGroup[] = [ /* §2.2 표 순서대로 */ ];

/** 하위 호환 flatten — TopNav T2 등 path 기반 소비처용 */
export const ADMIN_NAV_ITEMS: AdminNavItem[] = ADMIN_NAV_GROUPS.flatMap((g) => g.items);

/** 메인 앱에서 관리자 영역 진입 시 첫 페이지 (관측 그룹 첫 탭) */
export const ADMIN_ENTRY_PATH = ADMIN_NAV_GROUPS[0].items[0].path; // '/admin/dashboard'

/** 항목 활성 매칭: exact 또는 하위 경로 (예: /admin/agent-runs/:runId) */
export const isAdminItemActive = (item: AdminNavItem, pathname: string): boolean =>
  pathname === item.path || pathname.startsWith(`${item.path}/`);

/** 현재 경로가 속한 그룹 (admin 밖 경로면 undefined) */
export const findAdminGroupByPath = (pathname: string): AdminNavGroup | undefined =>
  ADMIN_NAV_GROUPS.find((g) => g.items.some((item) => isAdminItemActive(item, pathname)));
```

### 3.2 `AdminLayout.tsx`

구조 (전체 프레임·"메인으로 돌아가기"·`<main>` 스크롤은 기존 유지):

```tsx
const AdminLayout = () => {
  const { pathname } = useLocation();
  const activeGroup = findAdminGroupByPath(pathname);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <TopNav />
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        {/* 사이드바: 그룹 4개만 */}
        <nav aria-label="관리 메뉴" className="flex w-56 shrink-0 flex-col border-r border-zinc-200 bg-zinc-50">
          {ADMIN_NAV_GROUPS.map((group) => (
            <button onClick={() => navigate(group.items[0].path)} /* 활성: group === activeGroup */>
              {/* group.icon + group.label — 기존 항목 버튼 스타일 그대로 */}
            </button>
          ))}
          {/* 하단 "메인으로 돌아가기" 기존 유지 */}
        </nav>

        {/* 본문: 탭 바 + Outlet */}
        <div style={{ display: 'flex', flexDirection: 'column', flex: 1, overflow: 'hidden' }}>
          {activeGroup && <AdminSectionTabs group={activeGroup} />}
          <main style={{ flex: 1, overflowY: 'auto', background: '#fff' }}>
            <Outlet />
          </main>
        </div>
      </div>
    </div>
  );
};
```

주의: 기존 `<main>` 래퍼 바깥에 flex-column 래퍼가 하나 추가된다. 탭 바는 고정, `<main>`만 스크롤 — CLAUDE.md 페이지 래퍼 규칙(패턴 A)과 동일한 프레임.

### 3.3 `AdminSectionTabs` (신규 컴포넌트)

- 위치: `src/components/layout/AdminSectionTabs.tsx`
- Props: `interface AdminSectionTabsProps { group: AdminNavGroup; }`
- 렌더링: 얇은 수평 탭 바. 페이지 자체 헤더와 중복감을 줄이기 위해 **텍스트 탭 + 하단 보더** 미니멀 스타일.

```tsx
<div role="tablist" aria-label={`${group.label} 하위 메뉴`}
     className="flex shrink-0 items-center gap-1 border-b border-zinc-200 bg-white px-6">
  {group.items.map((item) => {
    const isActive = isAdminItemActive(item, pathname);
    return (
      <button role="tab" aria-selected={isActive} onClick={() => navigate(item.path)}
        className={`-mb-px border-b-2 px-3.5 py-3 text-[13.5px] font-medium transition-all ${
          isActive
            ? 'border-violet-600 text-violet-700'
            : 'border-transparent text-zinc-500 hover:text-zinc-800'
        }`}>
        {item.label}
      </button>
    );
  })}
</div>
```

- 활성 판정은 `isAdminItemActive` 재사용 → `/admin/agent-runs/:runId`에서도 "Agent Run 관측" 탭 활성.
- 아이콘은 탭에 넣지 않는다 (텍스트만 — 페이지 헤더와의 시각 위계 분리).

### 3.4 `TopNav.tsx` — ADMIN_MENU 그룹 헤더

- `NavMenu`에 optional 확장: `interface NavMenu { label: string; items?: DropdownItem[]; groups?: AdminNavGroup[]; }`
  - `ADMIN_MENU = { label: '관리', groups: ADMIN_NAV_GROUPS }`
  - 일반 `NAV_MENUS`(데이터/에이전트)는 `items` 유지 — 렌더링 분기.
- 드롭다운 렌더링: `menu.groups`가 있으면 그룹 순회 —

```tsx
<div className="max-h-[70vh] overflow-y-auto p-1.5">
  {menu.groups.map((group) => (
    <div key={group.key}>
      <p className="px-3.5 pb-1 pt-2.5 text-[10.5px] font-semibold uppercase tracking-widest text-zinc-400">
        {group.label}
      </p>
      {group.items.map((item) => /* 기존 항목 버튼 렌더링 그대로 재사용 */)}
    </div>
  ))}
</div>
```

- `isMenuActive`는 flatten 항목 기준 유지하되 하위 경로 매칭으로 보강: `isAdminItemActive` 사용.
- 항목 버튼 마크업은 기존 것을 함수로 추출(`renderDropdownItem`)해 items/groups 두 분기가 공유.

### 3.5 변경 파일 목록

| 파일 | 변경 | 내용 |
|------|------|------|
| `src/constants/adminNav.ts` | 수정 | `AdminNavGroup`·`ADMIN_NAV_GROUPS`·유틸 2종 추가, `ADMIN_NAV_ITEMS`/`ADMIN_ENTRY_PATH` 파생값으로 전환 |
| `src/components/layout/AdminSectionTabs.tsx` | **신규** | 2차 탭 바 컴포넌트 |
| `src/components/layout/AdminLayout.tsx` | 수정 | 사이드바 그룹 렌더링 + 본문 flex-column 래퍼 + 탭 바 삽입 |
| `src/components/layout/TopNav.tsx` | 수정 | ADMIN_MENU 그룹 헤더 렌더링 분기 + 드롭다운 스크롤 |
| `src/constants/adminNav.test.ts` | 수정 | 그룹 구조 단언으로 재작성 |
| `src/components/layout/AdminSectionTabs.test.tsx` | **신규** | 탭 렌더링·전환·활성 테스트 |
| `src/components/layout/AdminLayout.test.tsx` | **신규** | 그룹 사이드바·탭 바 통합 테스트 |
| `src/components/layout/TopNav.test.tsx` | 수정 | 그룹 헤더 단언 추가 (T2는 유지) |
| `src/components/layout/AppSidebar.test.tsx` | 수정 | A4 기대 경로 `/admin/users` → `/admin/dashboard` |

무수정: `App.tsx`, 11개 페이지 컴포넌트, `AdminRoute`, `AppSidebar.tsx`(상수 소비만 하므로 코드 무변경 — 동작만 entry 변경).

---

## 4. Test Design (TDD 순서)

### 4.1 `adminNav.test.ts` (재작성)

| ID | 케이스 |
|----|--------|
| G1 | 그룹은 4개다 (`observability`/`org`/`docs-quality`/`agent-resources` key 존재) |
| G2 | `ADMIN_NAV_ITEMS`는 그룹 flatten과 동일하다 (개수 하드코딩 금지 — 관계 단언) |
| G3 | 전체 path 중복 없음 + 모든 path는 `/admin/`으로 시작 |
| G4 | 기존 11개 path 전부 포함 (`/admin/dashboard` ~ `/admin/wiki` — 이동 중 유실 방지 명시 단언) |
| G5 | `ADMIN_ENTRY_PATH === '/admin/dashboard'`이며 flatten에 포함된다 |
| G6 | `findAdminGroupByPath('/admin/agent-runs/run-1')` → 관측 그룹 |
| G7 | `findAdminGroupByPath('/chatpage')` → undefined |
| G8 | `isAdminItemActive`: exact / 하위 경로 true, 무관 경로·prefix 유사 경로(`/admin/tools` vs `/admin/tools-x`) false |

### 4.2 `AdminSectionTabs.test.tsx` (신규)

| ID | 케이스 |
|----|--------|
| TB1 | 그룹 items가 순서대로 tab으로 렌더링된다 (`role="tab"`) |
| TB2 | 현재 경로 탭이 `aria-selected=true` (MemoryRouter initialEntries) |
| TB3 | 탭 클릭 시 해당 경로로 이동한다 (location 프로브) |
| TB4 | 상세 경로(`/admin/agent-runs/run-1`)에서 Agent Run 탭이 활성이다 |

### 4.3 `AdminLayout.test.tsx` (신규)

| ID | 케이스 |
|----|--------|
| AL1 | 사이드바에 그룹 라벨 4개만 노출, 개별 항목 라벨(예: "부서 관리")은 사이드바에 없음 |
| AL2 | `/admin/users` 진입 시 "조직 관리" 그룹 활성 + 탭 바에 사용자/부서 탭 노출 |
| AL3 | 그룹 버튼 클릭 시 그룹 첫 탭 경로로 이동 (예: 문서·품질 → `/admin/chunking-profiles`) |
| AL4 | admin 외 경로 요소 없음 검증은 범위 외 (AdminRoute 가드 기존 테스트 유지) |

> jsdom 주의: `AdminLayout`은 `TopNav`를 포함하므로 authStore 초기화(admin user) + MemoryRouter + Outlet 스텁 필요. MSW per-file listen 훅 규칙 적용 대상 아님(네트워크 없음).

### 4.4 기존 테스트 갱신

| 파일 | 변경 |
|------|------|
| `TopNav.test.tsx` | T4(신규): 관리 드롭다운에 그룹 헤더 4개("관측"/"조직 관리"/"문서·품질"/"에이전트 리소스") 노출. T2(전 항목 노출)는 그대로 통과해야 함 |
| `AppSidebar.test.tsx` | A4: 기대 경로 `/admin/dashboard`로 수정 |

---

## 5. Implementation Order

1. **Red**: `adminNav.test.ts` 재작성 (G1~G8) → 실패 확인
2. **Green**: `adminNav.ts` 그룹 구조 구현
3. **Red→Green**: `AdminSectionTabs.test.tsx` → `AdminSectionTabs.tsx` 구현
4. **Red→Green**: `AdminLayout.test.tsx` → `AdminLayout.tsx` 개편
5. `TopNav.tsx` 그룹 렌더링 분기 + `TopNav.test.tsx` T4 추가
6. `AppSidebar.test.tsx` A4 갱신
7. 전체 검증: `npm run test:run -- --pool=threads` (사전 실패 8건 제외) + `npm run type-check` + `npm run lint`
8. 수동 확인: 11개 URL 직접 진입 → 그룹·탭 활성 / 드롭다운 스크롤

---

## 6. Open Items

- 탭 바 스타일이 페이지 자체 헤더와 겹쳐 보이면 Design 리뷰에서 탭 바 배경을 `bg-zinc-50/50`으로 낮추는 옵션 검토 (구현 후 시각 판단).
- 드롭다운 `max-h-[70vh]`는 1080p 기준 전 항목 노출 예상 — 실측 후 조정.
