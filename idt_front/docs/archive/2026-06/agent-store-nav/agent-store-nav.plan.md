# agent-store-nav Planning Document

> **Summary**: 메인 앱 사이드바(`AppSidebar`)에 에이전트 스토어(`/agent-store`)로 가는 네비게이션 진입점이 없어, 일반 사용자가 이미 구현된 스토어 페이지에 접근할 수 없는 문제를 해결한다.
>
> **Project**: sangplusbot (idt_front)
> **Author**: AI Assistant
> **Date**: 2026-06-10
> **Status**: Draft

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem (문제)** | `/agent-store` 라우트와 `AgentStorePage`는 이미 존재하지만, 일반 사용자가 보는 메인 레이아웃(`AgentChatLayout` → `AppSidebar`)에 스토어로 가는 메뉴가 없다. 스토어 링크는 `TopNav`에만 있고 `TopNav`는 관리자 영역(`AdminLayout`)에서만 렌더링되어, 일반 사용자는 URL 직접 입력 외에는 진입할 방법이 없다. |
| **Solution (해결)** | 메인 사이드바(`AppSidebar`)의 `NAV_ITEMS`에 "에이전트 스토어"(`/agent-store`) 항목을 추가한다. 아이콘·라벨은 기존 `TopNav`의 에이전트 스토어 항목과 일관되게 사용한다. |
| **Function UX Effect (기능·UX 효과)** | 사용자가 메인 화면 좌측 사이드바에서 한 번의 클릭으로 공개 에이전트 스토어를 탐색·구독·포크할 수 있다. 현재 경로가 `/agent-store`면 active 표시된다. |
| **Core Value (핵심 가치)** | 이미 구현된 에이전트 스토어 기능의 "진입 동선" 부재를 해소해, 만들어둔 기능이 실제로 사용되도록 한다. (dead feature 활성화) |

---

## 1. Overview

### 1.1 Purpose

메인 앱 화면에서 사용자가 **UI를 통해 에이전트 스토어(`/agent-store`)로 진입할 수 있는
네비게이션 진입점**을 제공한다.

### 1.2 Background

스토어 기능 자체는 이미 완성되어 있다.

- `App.tsx:51`: `/agent-store` 라우트가 `AgentChatLayout` 하위에 정상 등록됨
- `AgentStorePage` (`src/pages/AgentStorePage/index.tsx`) 및 `components/agent-store/*` 구현 완료
- `TopNav.tsx`: "에이전트" 드롭다운에 "에이전트 스토어" → `/agent-store` 링크 보유

### 1.3 Root Cause Analysis

| # | 원인 | 위치 | 설명 |
|---|------|------|------|
| 1 | 메인 사이드바에 스토어 진입점 부재 | `AppSidebar.tsx` | `NAV_ITEMS`(SUPER AI/템플릿/유틸리티/작업/평가)·`BOTTOM_ITEMS` 어디에도 `/agent-store` 링크 없음 |
| 2 | 스토어 링크가 관리자 전용 컴포넌트에만 존재 | `TopNav.tsx:34` | `TopNav`에 스토어 링크가 있으나, `TopNav`는 `AdminLayout`에서만 렌더링되어 일반 사용자에게 노출되지 않음 |

### 1.4 Related Documents

- Main Layout: `src/components/layout/AgentChatLayout.tsx`
- Main Sidebar (수정 대상): `src/components/layout/AppSidebar.tsx`
- Store Page: `src/pages/AgentStorePage/index.tsx`
- Top Nav (참고 — 기존 스토어 링크/아이콘): `src/components/layout/TopNav.tsx`
- Routing: `src/App.tsx`
- 선행 유사 과제: `docs/01-plan/features/admin-navigation-entry.plan.md`

---

## 2. Scope

### 2.1 In Scope

- [ ] `AppSidebar`의 `NAV_ITEMS`에 "에이전트 스토어"(`/agent-store`) 항목 추가
- [ ] 현재 경로가 `/agent-store`일 때 active 스타일 표시 (기존 `NAV_ITEMS` active 로직 재사용)
- [ ] 라벨/아이콘을 기존 `TopNav` 스토어 항목과 일관되게 적용
- [ ] 스토어 메뉴 렌더링/네비게이션 테스트 추가

### 2.2 Out of Scope

- `AgentStorePage` 및 `components/agent-store/*` 기능·디자인 변경
- 라우트(`App.tsx`)·권한 가드 변경 (이미 정상)
- `TopNav` / 관리자 영역 변경
- 백엔드 API 변경

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | `AppSidebar` `NAV_ITEMS`에 "에이전트 스토어" 항목 추가, 클릭 시 `/agent-store`로 이동 | High | Pending |
| FR-02 | 현재 경로가 `/agent-store`일 때 해당 메뉴 active 표시 | Medium | Pending |
| FR-03 | 라벨·아이콘이 기존 디자인(`TopNav` 스토어 항목)과 일관 | Low | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Consistency | 기존 사이드바 메뉴 스타일과 시각적 일관 | 시각 검토 |
| Maintainability | 기존 `NAV_ITEMS` 패턴 그대로 항목 1개 추가 | 코드 리뷰 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] 로그인 후 메인 사이드바에서 "에이전트 스토어" 메뉴가 보이고, 클릭 시 `/agent-store` 진입
- [ ] `/agent-store`에 있을 때 메뉴가 active로 표시
- [ ] 컴포넌트 테스트 작성 및 통과, 기존 테스트 비파괴

### 4.2 Quality Criteria

- [ ] TDD 방식 (테스트 먼저 작성)
- [ ] 기존 프론트 컨벤션(react-router `useNavigate`) 준수
- [ ] Zero lint / 타입 에러

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 메뉴 항목 추가로 사이드바 레이아웃 깨짐 | Low | Low | 기존 `NAV_ITEMS` 동일 구조 사용, 시각 회귀 확인 |
| 아이콘 path 오타로 렌더 실패 | Low | Low | `TopNav`의 기존 스토어 아이콘 path 재사용 |

---

## 6. Architecture Considerations

### 6.1 Project Level

- **Level**: Dynamic (React 19 + TypeScript + Zustand + TanStack Query)
- 기존 컴포넌트 구조 유지, 항목 추가만 수행

### 6.2 Implementation Strategy

**접근 방식: 기존 `NAV_ITEMS` 패턴에 항목 1개 추가 (최소 변경)**

```
AppSidebar.tsx
  - NAV_ITEMS 배열에 추가:
    {
      id: 'agent-store',
      label: '에이전트 스토어',
      path: '/agent-store',
      iconPath: <TopNav 스토어 아이콘 path 재사용>
    }
  - 기존 map 렌더링 + active 로직(location.pathname === item.path)이 그대로 동작
  - handleNavClick: 'super'가 아닌 일반 path이므로 navigate(item.path)만 수행 (기존 로직 그대로)
```

### 6.3 영향 받는 파일

| Type | File | 변경 내용 |
|------|------|----------|
| Edit | `src/components/layout/AppSidebar.tsx` | `NAV_ITEMS`에 에이전트 스토어 항목 추가 |
| Edit/New | `src/components/layout/AppSidebar.test.tsx` | 스토어 메뉴 노출·네비게이션 테스트 |

---

## 7. Convention Prerequisites

### 7.1 Existing Project Conventions

- [ ] `idt_front/CLAUDE.md` 코딩 컨벤션 확인
- [ ] 테스트(Vitest + React Testing Library, `--pool=threads`) 패턴 확인

### 7.2 Conventions to Follow

| Category | Rule |
|----------|------|
| Routing | `react-router-dom` `useNavigate` 사용 (기존 `handleNavClick` 재사용) |
| Test | 테스트 먼저 작성 (Red → Green → Refactor) |
| Style | 기존 `NAV_ITEMS` Tailwind 클래스/active 패턴 그대로 |

---

## 8. Open Questions (결정 완료)

| # | 질문 | 결정 |
|---|------|------|
| Q1 | 진입점 위치 | **왼쪽 사이드바 상단 `NAV_ITEMS`** (템플릿·평가 등과 동일 레벨) |
| Q2 | 메뉴 순서 | **'SUPER AI 에이전트' 다음 또는 목록 끝** (Design에서 확정) |
| Q3 | TopNav 스토어 링크 | **변경하지 않음** (메인 진입점은 사이드바로 충분) |

---

## 9. Next Steps

1. [ ] Design 문서 작성 (`/pdca design agent-store-nav`)
2. [ ] TDD로 구현 (`/pdca do agent-store-nav`)
3. [ ] Gap 분석 (`/pdca analyze agent-store-nav`)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-06-10 | Initial draft | AI Assistant |
