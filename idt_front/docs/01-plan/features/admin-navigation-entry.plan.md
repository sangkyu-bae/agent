# admin-navigation-entry Planning Document

> **Summary**: 관리자(role==='admin') 사용자가 메인 앱에서 관리자 페이지 영역으로 진입할 수 있는 네비게이션 진입점이 없는 문제를 해결한다.
>
> **Project**: sangplusbot (idt_front)
> **Author**: AI Assistant
> **Date**: 2026-06-04
> **Status**: Draft

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem (문제)** | 관리자 페이지(`/admin/*`)와 라우트 가드(`AdminRoute`)는 존재하지만, 메인 앱(`AgentChatLayout` + `AppSidebar`)에 관리자 영역으로 들어가는 진입점이 전혀 없어 관리자도 URL을 직접 입력해야만 접근 가능하다. |
| **Solution (해결)** | 메인 사이드바(`AppSidebar`) 하단에 `role==='admin'`일 때만 노출되는 단일 "관리자" 진입 메뉴를 추가하고, 관리자 메뉴 정의를 단일 소스(constants)로 통합해 `AdminLayout` 사이드바·`TopNav` ADMIN_MENU가 공유하도록 한다. |
| **Function UX Effect (기능·UX 효과)** | 관리자는 메인 화면에서 한 번의 클릭으로 관리자 콘솔에 진입하고, 진입 후 4개 관리자 페이지(사용자/부서/RAGAS/Agent Run) 간 일관된 메뉴로 이동한다. 일반 사용자에게는 메뉴가 노출되지 않는다. |
| **Core Value (핵심 가치)** | "들어가는 문" 부재라는 치명적 UX 단절을 해소하고, 메뉴 정의 중복·누락(RAGAS·Agent Run)을 제거해 유지보수성과 권한별 네비게이션 일관성을 확보한다. |

---

## 1. Overview

### 1.1 Purpose

관리자 권한 사용자가 메인 앱 화면에서 관리자 전용 페이지 영역(`/admin/*`)으로
**UI를 통해 진입할 수 있는 네비게이션 진입점**을 제공한다.

### 1.2 Background

현재 라우팅·권한 구조는 정상적으로 구성되어 있다.

- `App.tsx`: `/admin/*` 라우트가 `AdminRoute`(role 가드) + `AdminLayout`으로 보호됨
  - `/admin/users` (사용자 관리)
  - `/admin/departments` (부서 관리)
  - `/admin/ragas` (RAGAS 평가)
  - `/admin/agent-runs`, `/admin/agent-runs/:runId` (Agent Run 관측)
- `AdminLayout`: 자체 사이드바로 4개 관리자 페이지 간 이동 + "메인으로 돌아가기" 링크 제공
- `AdminRoute`: `user?.role !== 'admin'`이면 `/`로 리다이렉트

### 1.3 Root Cause Analysis

| # | 원인 | 위치 | 설명 |
|---|------|------|------|
| 1 | 메인 앱에 관리자 진입점 부재 | `AppSidebar.tsx` | `NAV_ITEMS`/`BOTTOM_ITEMS` 어디에도 `/admin/*` 링크가 없음. 관리자도 진입 불가 |
| 2 | 관리자 메뉴가 진입 후에만 노출 | `TopNav.tsx:100` | `TopNav`의 `ADMIN_MENU`는 role==='admin'일 때 노출되나, `TopNav`는 `AdminLayout`에서만 사용되어 "이미 관리자 영역에 들어간 뒤"에만 보이는 모순 |
| 3 | 관리자 메뉴 정의 중복·불일치 | `TopNav.tsx` / `AdminLayout.tsx` | `TopNav.ADMIN_MENU`는 2개(사용자/부서)만, `AdminLayout` 사이드바는 4개. 메뉴 정의가 두 곳에 하드코딩되어 누락·불일치 발생 |

### 1.4 Related Documents

- Main Layout: `src/components/layout/AgentChatLayout.tsx`
- Main Sidebar: `src/components/layout/AppSidebar.tsx`
- Admin Layout/Sidebar: `src/components/layout/AdminLayout.tsx`
- Top Nav (admin menu 보유): `src/components/layout/TopNav.tsx`
- Route Guard: `src/components/common/AdminRoute.tsx`
- Auth State: `src/store/authStore.ts`, `src/types/auth.ts`
- Routing: `src/App.tsx`

---

## 2. Scope

### 2.1 In Scope

- [ ] `AppSidebar` 하단(`BOTTOM_ITEMS` 영역)에 `role==='admin'`일 때만 노출되는 "관리자" 진입 메뉴 추가
- [ ] "관리자" 클릭 시 `/admin/users`로 이동 (진입 후 `AdminLayout`이 페이지 간 네비게이션 담당)
- [ ] 관리자 메뉴 정의(label/path/icon)를 단일 소스(예: `src/constants/adminNav.ts`)로 통합
- [ ] `AdminLayout` 사이드바와 `TopNav` ADMIN_MENU가 통합 소스를 공유하도록 리팩토링
- [ ] 통합 과정에서 `TopNav` ADMIN_MENU의 RAGAS·Agent Run 누락 항목 보강
- [ ] 진입점 노출/비노출에 대한 테스트 추가 (admin vs 일반 사용자)

### 2.2 Out of Scope

- 관리자 라우트/가드(`AdminRoute`) 로직 변경 (이미 정상 동작)
- 관리자 페이지들 자체의 기능/디자인 변경
- 백엔드 API 변경 (role 판별은 기존 `user.role` 사용)
- 별도 관리자 대시보드(landing/index) 페이지 신규 생성
- `/tool-admin`, `/settings` 등 비-admin 라우트의 권한 재분류 (별도 과제)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | `AppSidebar` 하단에 "관리자" 진입 메뉴를 추가하고, `user.role === 'admin'`일 때만 렌더링 | High | Pending |
| FR-02 | "관리자" 메뉴 클릭 시 `/admin/users`로 이동 | High | Pending |
| FR-03 | 일반 사용자(role==='user')에게는 진입 메뉴가 노출되지 않음 | High | Pending |
| FR-04 | 관리자 메뉴 정의를 단일 소스로 분리하고 `AdminLayout`·`TopNav`가 이를 사용 | Medium | Pending |
| FR-05 | 통합된 메뉴에 4개 관리자 페이지(사용자/부서/RAGAS/Agent Run) 모두 포함 | Medium | Pending |
| FR-06 | 현재 경로가 `/admin/*`일 때 진입 메뉴에 active 표시 (선택) | Low | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Consistency | 메인↔관리자 네비게이션 시각 스타일 기존 디자인과 일관 | 시각 검토 |
| Maintainability | 관리자 메뉴 항목 추가 시 1곳만 수정 | 코드 리뷰 |
| Security(UX) | 비관리자에게 메뉴 미노출 (라우트 가드는 기존 유지, 심층 방어) | 테스트 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] 관리자로 로그인 시 메인 사이드바 하단에 "관리자" 메뉴가 보이고, 클릭하면 `/admin/users` 진입
- [ ] 일반 사용자로 로그인 시 "관리자" 메뉴가 보이지 않음
- [ ] 관리자 영역 내 4개 페이지 메뉴가 통합 소스 기준으로 일관되게 표시
- [ ] 단위/컴포넌트 테스트 작성 및 통과
- [ ] 기존 테스트 깨지지 않음

### 4.2 Quality Criteria

- [ ] TDD 방식 (테스트 먼저 작성)
- [ ] 기존 프론트 컨벤션(Zustand, react-router) 준수
- [ ] Zero lint error / 타입 에러 없음

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 메뉴 정의 통합 시 `TopNav`/`AdminLayout` 스타일 차이로 회귀 | Medium | Medium | 데이터(메뉴 항목)만 공유하고 렌더링/스타일은 각 컴포넌트 유지 |
| persist된 `user.role` stale로 메뉴 오노출 | Low | Low | 라우트 가드(`AdminRoute`)가 최종 방어선, 메뉴는 보조 |
| icon path 등 중복 데이터 이동 중 누락 | Low | Medium | 단일 소스 이전 후 시각 회귀 확인 |

---

## 6. Architecture Considerations

### 6.1 Project Level

- **Level**: Dynamic (React 19 + TypeScript + Zustand + TanStack Query)
- 기존 컴포넌트 구조 유지, 레이어/디렉토리 규칙 준수

### 6.2 Implementation Strategy

**접근 방식: 진입점 추가 + 메뉴 정의 단일 소스화**

```
1) src/constants/adminNav.ts (신규)
   - ADMIN_NAV_ITEMS: { label, path, icon }[]  (사용자/부서/RAGAS/Agent Run)
   - ADMIN_ENTRY_PATH = '/admin/users'

2) AppSidebar.tsx
   - BOTTOM_ITEMS 영역에 조건부 "관리자" 항목 추가
   - useAuthStore().user?.role === 'admin' 일 때만 렌더
   - onClick → navigate(ADMIN_ENTRY_PATH)

3) AdminLayout.tsx
   - 하드코딩된 ADMIN_SIDEBAR_ITEMS → ADMIN_NAV_ITEMS 사용

4) TopNav.tsx
   - ADMIN_MENU.items → ADMIN_NAV_ITEMS 기반으로 구성 (RAGAS·Agent Run 포함)
```

### 6.3 영향 받는 파일

| Type | File | 변경 내용 |
|------|------|----------|
| New | `src/constants/adminNav.ts` | 관리자 메뉴 단일 소스 정의 |
| Edit | `src/components/layout/AppSidebar.tsx` | 관리자 진입 메뉴(조건부) 추가 |
| Edit | `src/components/layout/AdminLayout.tsx` | 메뉴 정의를 단일 소스로 교체 |
| Edit | `src/components/layout/TopNav.tsx` | ADMIN_MENU를 단일 소스 기반으로 교체 + 누락 항목 보강 |
| New | `*.test.tsx` | 진입점 노출/비노출 테스트 |

---

## 7. Convention Prerequisites

### 7.1 Existing Project Conventions

- [ ] `idt_front/CLAUDE.md` 코딩 컨벤션 확인
- [ ] 상태관리(Zustand `useAuthStore`) 사용 패턴 확인
- [ ] 테스트(Vitest + React Testing Library) 패턴 확인

### 7.2 Conventions to Follow

| Category | Rule |
|----------|------|
| State | role 판별은 `useAuthStore().user.role` 사용 |
| Routing | `react-router-dom` `useNavigate` 사용 |
| Test | 테스트 먼저 작성 (Red → Green → Refactor) |
| Constants | 엔드포인트/공유 상수는 `src/constants/`에 위치 |

---

## 8. Open Questions (결정 완료)

| # | 질문 | 결정 |
|---|------|------|
| Q1 | 진입점 위치 | **왼쪽 사이드바 하단(AppSidebar BOTTOM_ITEMS)** |
| Q2 | 진입 방식 | **단일 링크 → /admin/users 진입 (이후 AdminLayout이 페이지 네비 담당)** |
| Q3 | 정합성 범위 | **단일 소스로 통합 (AdminLayout·TopNav 공유, RAGAS·Agent Run 누락 보강)** |

---

## 9. Next Steps

1. [ ] Design 문서 작성 (`/pdca design admin-navigation-entry`)
2. [ ] TDD로 구현 (`/pdca do admin-navigation-entry`)
3. [ ] Gap 분석 (`/pdca analyze admin-navigation-entry`)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-06-04 | Initial draft | AI Assistant |
