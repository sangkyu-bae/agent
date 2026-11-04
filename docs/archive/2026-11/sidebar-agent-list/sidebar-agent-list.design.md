# sidebar-agent-list Design Document

> **Summary**: AppSidebar의 에이전트 목록과 하단 메뉴를 두 개의 하위 컴포넌트로 분리하면서, 2줄 압축 항목·그룹 접기(persist)·아이콘 도크로 바꾼다.
>
> **Project**: sangplusbot (idt_front)
> **Author**: 배상규
> **Date**: 2026-11-04
> **Status**: Draft
> **Planning Doc**: [sidebar-agent-list.plan.md](sidebar-agent-list.plan.md)
> **시안**: https://claude.ai/artifact/LRLpeMHw5dicsiKLnz8YRk

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 에이전트 목록의 가시성이 낮고 세로 공간이 하단 메뉴에 밀린다 |
| **WHO** | 사이드바로 에이전트를 골라 대화하는 모든 로그인 사용자, 특히 에이전트를 여러 개 가진 P2 |
| **RISK** | 하단 메뉴를 아이콘만 남기면 메뉴 이름을 알아보기 어려워짐 → 툴팁·aria-label 유지, 기존 테스트의 이름 기반 조회 보존 |
| **SUCCESS** | 1440×900 기준 보이는 에이전트 수 증가, 이름 `sidebar-fg` 적용, 그룹 접기 상태 새로고침 후 유지, 기존 AppSidebar 테스트 통과 |
| **SCOPE** | 프론트 단일 컴포넌트(AppSidebar) + layoutStore 필드 1개. 백엔드·API 변경 없음 |

---

## 1. Overview

### 1.1 Design Goals

- 에이전트 항목 높이를 줄이고 이름 대비를 높여 한 화면에 보이는 수를 늘린다.
- 하단 보조 메뉴를 아이콘 한 줄로 바꿔 목록 영역의 세로 공간을 확보한다.
- `AppSidebar`의 외부 props와 동작(접힌 레일, 로딩·오류·빈 상태)은 그대로 둔다.
- 아바타는 상수 하나로 끌 수 있게 한다.

### 1.2 Design Principles

- 기존 디자인 토큰(`sidebar-*`, `brand-*`)만 사용. hex·`text-[Npx]`·인라인 색 금지
- 접근 가능한 이름은 기존 라벨 그대로 유지 (테스트·스크린리더 호환)
- 상태는 이미 있는 `layoutStore`(persist 키 `layout-preferences`)에 필드만 추가

---

## 2. Architecture Options

### 2.0 Architecture Comparison

| Criteria | Option A: Minimal | Option B: Clean | Option C: Pragmatic |
|----------|:-:|:-:|:-:|
| **Approach** | AppSidebar 안에서 마크업만 변경 | 항목 단위 컴포넌트 6개 + 훅 | 목록·도크 2개 컴포넌트로 분리 |
| **New Files** | 0 | 7~8 | 3 (+테스트 2) |
| **Modified Files** | 3 | 3 | 3 |
| **Complexity** | Low | High | Medium |
| **Maintainability** | Low (≈470줄 단일 파일) | High | High |
| **Effort** | Low | High | Medium |

**Selected**: Option C — **Rationale**: 바뀌는 영역(목록·하단)만 떼어내 AppSidebar를 약 250줄로 줄이고, 파일 수는 최소로 유지한다.

### 2.1 Component Diagram

```
AgentChatLayout
└─ AppSidebar (props 그대로)
   ├─ (a) 토글+로고 / (b) 새 에이전트 / (d) 기본 내비      ← 변경 없음
   ├─ (e) 접힘: "에이전트 목록" SidebarItem                 ← 변경 없음
   │      펼침: <AgentList .../>                           ← 신규
   └─ (f)(g) <SidebarDock collapsed />                     ← 신규 (하단 메뉴 + 사용자 + 로그아웃)
```

### 2.2 Data Flow

```
useMyAgents (AgentChatLayout) ─agents─▶ AppSidebar ─▶ AgentList
                                                       ├─ groupAgents(agents) → 4그룹
                                                       ├─ layoutStore.collapsedAgentGroups (읽기)
                                                       └─ 그룹 제목 클릭 → toggleAgentGroup(key) → persist
SidebarDock ─ useAuthStore(user), useLogout, useNavigate/useLocation
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| AgentList | `layoutStore`, `constants/sidebar.ts`, `types/agent.ts` | 접기 상태, 아바타 플래그, 타입 |
| SidebarDock | `authStore`, `useLogout`, `constants/adminNav`, react-router | 메뉴 이동, 관리자 노출, 로그아웃 |
| AppSidebar | AgentList, SidebarDock, `SidebarItem`(파일 내부 유지) | 조립 |

---

## 3. Data Model

### 3.1 타입 (`src/types/agent.ts`에 추가)

```typescript
// sidebar-agent-list D1: 사이드바 그룹 키. 순서는 표시 순서와 같다.
export const SIDEBAR_AGENT_GROUP = {
  PINNED: 'pinned',
  OWNED: 'owned',
  SUBSCRIBED: 'subscribed',
  FORKED: 'forked',
} as const;
export type SidebarAgentGroupKey = (typeof SIDEBAR_AGENT_GROUP)[keyof typeof SIDEBAR_AGENT_GROUP];
```

> `as const` 런타임 상수는 컴포넌트 파일이 아닌 `src/types/*.ts`에 둔다 (프로젝트 규칙).

### 3.2 layoutStore 확장 (`src/store/layoutStore.ts`)

```typescript
interface LayoutState {
  // ...기존 필드 그대로
  /** sidebar-agent-list D2: 접힌 에이전트 그룹 키 목록. 기본 [] = 모두 펼침 */
  collapsedAgentGroups: SidebarAgentGroupKey[];
  toggleAgentGroup: (key: SidebarAgentGroupKey) => void;
}
// 초기값: collapsedAgentGroups: []
// toggleAgentGroup: 있으면 제거, 없으면 추가
```

- persist 키 `layout-preferences` 유지. 기존 저장값에 필드가 없으면 zustand persist 기본 merge로 초기값 `[]`이 쓰인다 → 마이그레이션 불필요.
- `hasPersistedSidebarPreference`는 `isSidebarCollapsed`만 보므로 영향 없음.

### 3.3 아바타 플래그 (`src/constants/sidebar.ts`, 신규)

```typescript
/** sidebar-agent-list D3: 에이전트 이름 첫 글자 아바타 표시. false로 바꾸면 아바타만 사라지고 레이아웃은 유지된다. */
export const SHOW_AGENT_AVATAR = true;
```

`AgentList`는 `showAvatar?: boolean` prop(기본값 `SHOW_AGENT_AVATAR`)을 받아 테스트에서 두 경우를 모두 검증한다.

---

## 4. API Specification

변경 없음. 기존 `useMyAgents` 응답(`MyAgent[]`)과 `refetch`만 사용한다.

---

## 5. UI/UX Design

### 5.1 Screen Layout (펼침, w-64)

```
┌──────────────────────────────┐
│ [≡] [logo] 상상인플러스저축은행 │  (a) 변경 없음
│ [+ 새 에이전트]               │  (b) 변경 없음
│ ✦ SUPER AI 에이전트 …  평가   │  (d) 변경 없음
├──────────────────────────────┤
│ ✦ 에이전트              [↻]   │  목록 헤더 (onRetry 있을 때만 ↻)
│ ▾ 고정됨 2                    │  그룹 토글 버튼
│ ┃[여] 여신 심사 보조 ★        │  선택: 활성 배경 + 좌측 2px 바
│ ┃     신용평가 서류를 읽고…   │
│  [정] 정책 문서 Q&A ★         │
│ ▸ 내 에이전트 5               │  접힌 그룹
│ ▾ 구독 3 …                    │
├──────────────────────────────┤
│ ☆  🔑  📁  📖  ⚙  🛡          │  SidebarDock: 아이콘 한 줄 (관리자는 admin만)
├──────────────────────────────┤
│ (T) tkdrb136@gmail.com   [⎋] │  사용자 1줄
└──────────────────────────────┘
```

접힌 레일(w-16)에서는 SidebarDock이 아이콘을 세로 한 열로 쌓는다(현재 모습과 같음). 사용자 영역도 현재 접힘 동작 그대로.

### 5.2 스타일 명세

| 요소 | 클래스 |
|------|--------|
| 목록 헤더 새로고침 버튼 | `h-7 w-7 rounded-md text-sidebar-fg-muted hover:bg-sidebar-hover hover:text-sidebar-fg`, 아이콘 `RotateCw` h-3.5 w-3.5 |
| 그룹 토글 | `flex w-full items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium text-sidebar-fg-muted hover:bg-sidebar-hover hover:text-sidebar-fg`, `ChevronDown` h-3 w-3, 접힘 시 `-rotate-90`, `transition-transform duration-150` |
| 그룹 개수 | `tabular-nums` (괄호 없이 숫자) |
| 항목 버튼 | `relative flex w-full items-start gap-2.5 rounded-md py-1.5 pl-3 pr-2 text-left transition-colors duration-150`, 비선택 `hover:bg-sidebar-hover`, 선택 `bg-sidebar-active` |
| 선택 바 | `SidebarItem`과 동일: `absolute left-0 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-full bg-linear-to-b from-brand-500 to-brand-800` |
| 아바타 | `mt-0.5 flex h-5.5 w-5.5 shrink-0 items-center justify-center rounded-md bg-brand-500/15 text-xs font-semibold text-brand-300` |
| 이름 | `truncate text-sm font-medium leading-snug text-sidebar-fg` |
| 설명 | `truncate text-xs leading-snug text-sidebar-fg-muted` (빈 설명이면 줄 생략) |
| 고정 별 | 기존 그대로 `h-3 w-3 fill-current text-brand-400`, `aria-label="고정됨"` |
| 도크 | `grid grid-cols-6 gap-0.5 border-t border-sidebar-border px-2.5 py-2` / 접힘 `grid-cols-1 px-3` |
| 도크 버튼 | `flex h-9 items-center justify-center rounded-md`, 상태 색은 `SidebarItem` 규칙 재사용(활성·accent) |
| 사용자 행 | `flex items-center gap-3 px-4 py-2.5`, 아바타 h-7 w-7, 이메일 1줄 truncate |

### 5.3 Component List

| Component | Location | Responsibility |
|-----------|----------|----------------|
| `AgentList` | `src/components/layout/sidebar/AgentList.tsx` | 헤더·그룹화·접기·항목·아바타, 로딩/오류/빈 상태 |
| `SidebarDock` | `src/components/layout/sidebar/SidebarDock.tsx` | 하단 메뉴 아이콘 도크 + 관리자 + 사용자/로그아웃 |
| `AppSidebar` | `src/components/layout/AppSidebar.tsx` | 상단·내비 + 두 컴포넌트 조립 (`SidebarItem`은 파일 내부 유지) |

**AgentList props**
```typescript
interface AgentListProps {
  agents: MyAgent[];
  selectedAgentId: string | null;
  onSelectAgent: (id: string) => void;
  isLoading?: boolean;
  isError?: boolean;
  onRetry?: () => void;
  showAvatar?: boolean; // 기본 SHOW_AGENT_AVATAR
}
```
항목 클릭 시 기존처럼 `onSelectAgent(id)` 후 `navigate('/chatpage')`. 빈 상태 버튼은 기존처럼 `/agent-builder`.

**SidebarDock props**
```typescript
interface SidebarDockProps { collapsed: boolean }
```
`BOTTOM_ITEMS`·관리자 항목·`isBottomActive` 로직은 AppSidebar에서 SidebarDock으로 옮긴다(동작 동일).

### 5.4 Page UI Checklist

#### AppSidebar (펼침)

- [ ] 목록 헤더: "에이전트" 제목 + `aria-label="에이전트 목록 새로고침"` 버튼(onRetry 있을 때)
- [ ] 그룹 토글 버튼 4종(고정됨/내 에이전트/구독/포크, 에이전트 있는 그룹만), 개수 표시, `aria-expanded`
- [ ] 접힌 그룹은 항목을 렌더하지 않음
- [ ] 항목: 아바타(첫 글자) + 이름 + 설명 2줄, `title`에 설명 전체
- [ ] 선택 항목: `aria-current="true"` + 좌측 브랜드 바
- [ ] 고정 항목: 별 아이콘
- [ ] 도크: 즐겨찾기·역할설정·리소스·지식베이스·환경설정 아이콘 버튼(aria-label·title), admin일 때 관리자 추가
- [ ] 사용자 행: 이메일 1줄 + 로그아웃 버튼
- [ ] 로딩 스켈레톤·오류(다시 시도)·빈 상태(에이전트 만들기) 기존 문구 유지

#### AppSidebar (접힘 레일)

- [ ] "에이전트 목록" 버튼 → 펼침 (기존 C3)
- [ ] 도크 아이콘 세로 한 열, 이름은 aria-label

---

## 6. Error Handling

| 상황 | 처리 |
|------|------|
| 목록 조회 실패 | 기존 오류 박스 + "다시 시도"(onRetry) 유지 |
| persist 값 손상/누락 | `collapsedAgentGroups` 기본 `[]` (모두 펼침) |
| 저장된 접힘 키가 현재 비어 있는 그룹 | 빈 그룹은 렌더하지 않으므로 무해 |
| 설명이 빈 문자열 | 설명 줄 생략 (1줄 항목) |
| 이름이 빈 문자열 | 아바타는 `?` 표시 |

---

## 7. Security Considerations

- 사용자 입력 렌더는 React 텍스트 노드만 사용 (XSS 해당 없음)
- 관리자 버튼 노출 조건 `user.role === 'admin'` 유지 (라우트 가드는 기존 AdminRoute)

---

## 8. Test Plan

API 변경이 없어 L1은 해당 없음. Vitest + RTL로 컴포넌트·스토어를 검증하고, 화면은 Chrome DevTools로 확인한다.

### 8.1 Test Scope

| Type | Target | Tool | Phase |
|------|--------|------|-------|
| Unit | `layoutStore.toggleAgentGroup` | Vitest | Do |
| Component | `AgentList`, `SidebarDock`, `AppSidebar` 회귀 | Vitest + RTL + user-event | Do |
| Visual | 1440·768·375 전후 스크린샷 | Chrome DevTools MCP | Check |

### 8.2 Store (`layoutStore.test.ts`에 추가)

| # | Test | Expected |
|---|------|----------|
| ST1 | 초기값 | `collapsedAgentGroups` = `[]` |
| ST2 | `toggleAgentGroup('owned')` 두 번 | 추가 후 제거 |
| ST3 | persist | 토글 후 `localStorage['layout-preferences']`에 `collapsedAgentGroups` 포함 |
| ST4 | 기존 저장값(필드 없음) 복원 | rehydrate 후 `[]` |

### 8.3 AgentList (`sidebar/AgentList.test.tsx`, 신규)

| # | Action | Expected |
|---|--------|----------|
| AL1 | pinned 1·owned 2·forked 1 렌더 | 그룹 토글 3개, 각 개수 표시, 구독 그룹 없음 |
| AL2 | "내 에이전트" 토글 클릭 | `aria-expanded=false`, 해당 그룹 항목 사라짐, 스토어에 `owned` 저장 |
| AL3 | 스토어에 `pinned` 접힘 상태로 렌더 | 고정됨 항목이 처음부터 숨겨짐 |
| AL4 | 항목 클릭 | `onSelectAgent(id)` 호출, `/chatpage` 이동 |
| AL5 | 선택 항목 | `aria-current="true"` |
| AL6 | `showAvatar` true/false | 첫 글자 아바타 존재/부재 |
| AL7 | 빈 설명 항목 | 이름만 렌더 |
| AL8 | onRetry 전달 후 새로고침 클릭 | onRetry 호출 / 미전달 시 버튼 없음 |
| AL9 | isLoading / isError / 빈 배열 | 스켈레톤(`role=status`) / 오류+다시 시도 / 빈 상태 버튼 |

### 8.4 SidebarDock (`sidebar/SidebarDock.test.tsx`, 신규)

| # | Action | Expected |
|---|--------|----------|
| SD1 | 일반 사용자 | 버튼 5개(이름: 즐겨찾기·역할설정·리소스·지식베이스·환경설정), 관리자 없음 |
| SD2 | admin | "관리자" 버튼 추가, 클릭 시 `ADMIN_ENTRY_PATH` 이동 |
| SD3 | "지식베이스" 클릭 | `/knowledge-bases` 이동, `/knowledge-bases/kb1`에서도 `aria-current="page"` |
| SD4 | 로그아웃 클릭 | `useLogout` mutate 호출 |

### 8.5 AppSidebar 회귀

- 기존 C1~C3, A1~A4, S1~S2 수정 없이 통과해야 한다. (관리자 버튼 이름 "관리자" 유지)

---

## 9. Clean Architecture

| Layer | 이번 변경 | Location |
|-------|----------|----------|
| Presentation | AgentList, SidebarDock, AppSidebar | `src/components/layout/` |
| State | layoutStore 필드 1개 | `src/store/layoutStore.ts` |
| Domain(types) | `SIDEBAR_AGENT_GROUP`, `SidebarAgentGroupKey` | `src/types/agent.ts` |
| Config | `SHOW_AGENT_AVATAR` | `src/constants/sidebar.ts` |

의존 방향: components → store/types/constants. 역방향 없음.

---

## 10. Coding Convention Reference

- Arrow function 컴포넌트, props `interface` 상단, `export default` 하단
- 아이콘 `lucide-react`, `strokeWidth={1.75}`, 장식 아이콘 `aria-hidden`
- className 합성 `@/utils/cn`
- 파일 상단 `// Design Ref: sidebar-agent-list §N — …` 주석

---

## 11. Implementation Guide

### 11.1 Implementation Order (TDD)

1. `types/agent.ts` 그룹 키 + `constants/sidebar.ts` 플래그
2. `layoutStore` 테스트(ST1~ST4) → 필드·액션 구현
3. `AgentList.test.tsx`(AL1~AL9) → `AgentList.tsx` 구현
4. `SidebarDock.test.tsx`(SD1~SD4) → `SidebarDock.tsx` 구현
5. `AppSidebar.tsx`에서 해당 영역을 두 컴포넌트로 교체, 기존 테스트 회귀 확인
6. lint·type-check·build, Chrome DevTools 1440·768·375 스크린샷

### 11.2 File Summary

| File | 변경 | 예상 |
|------|------|------|
| `src/types/agent.ts` | 수정 | +8 |
| `src/constants/sidebar.ts` | 신규 | +3 |
| `src/store/layoutStore.ts` (+test) | 수정 | +15 / +40 |
| `src/components/layout/sidebar/AgentList.tsx` (+test) | 신규 | ~170 / ~150 |
| `src/components/layout/sidebar/SidebarDock.tsx` (+test) | 신규 | ~110 / ~90 |
| `src/components/layout/AppSidebar.tsx` | 수정 | −170 +10 |

### 11.3 Session Guide

| Module | Scope key | 내용 | 의존 |
|--------|-----------|------|------|
| 1 | `module-1` | 타입·상수·layoutStore(+테스트) | - |
| 2 | `module-2` | AgentList(+테스트) | module-1 |
| 3 | `module-3` | SidebarDock(+테스트) + AppSidebar 조립·회귀 + 화면 확인 | module-1 |

규모가 작아 한 세션(`/pdca do sidebar-agent-list`)에 모두 진행하는 것을 권장한다.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-11-04 | Initial draft (Option C 선택) | 배상규 |
