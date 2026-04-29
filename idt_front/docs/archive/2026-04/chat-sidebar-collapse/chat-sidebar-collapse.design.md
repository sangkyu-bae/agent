# chat-sidebar-collapse Design Document

> **Summary**: 2단 사이드바(ChatHistoryPanel) 접기/펼치기를 아이콘 스트립 방식으로 리팩토링
>
> **Project**: sangplusbot (idt_front)
> **Version**: 0.1.0
> **Author**: 배상규
> **Date**: 2026-04-29
> **Status**: Draft
> **Planning Doc**: [chat-sidebar-collapse.plan.md](../01-plan/features/chat-sidebar-collapse.plan.md)

---

## 1. Overview

### 1.1 Design Goals

1. 2단 사이드바가 접힌 상태에서도 아이콘 스트립(w-12, 48px)으로 항상 존재하도록 변경
2. 접기/펼치기 토글을 1단 사이드바(AppSidebar)에서 제거하고 2단 사이드바 자체에서만 제어
3. 참조 디자인(docs/img/image1.png)과 일치하는 UI 구현

### 1.2 Design Principles

- **최소 변경**: 기존 ChatHistoryPanel 펼친 상태의 내부 구조는 유지
- **단일 책임**: 토글 제어는 2단 사이드바 컴포넌트 내부에서만 관리
- **상태 보존**: layoutStore의 persist 키 유지로 새로고침 시 접힘/펼침 상태 복원

---

## 2. Architecture

### 2.1 Component Diagram (변경 후)

```
┌───────────────────────────────────────────────────────────────┐
│ AgentChatLayout (flex, h-100%)                                │
│ ┌──────────┬──────────────────┬─────────────────────────────┐ │
│ │ AppSidebar│ ChatHistoryPanel │       main (Outlet)         │ │
│ │   w-64   │ w-12 or w-72     │       flex-1                │ │
│ │ (1단)    │ (2단: 항상 존재)  │                             │ │
│ │          │                  │                             │ │
│ │ [채팅    │                  │                             │ │
│ │  접기]   │                  │                             │ │
│ │  제거됨  │                  │                             │ │
│ └──────────┴──────────────────┴─────────────────────────────┘ │
└───────────────────────────────────────────────────────────────┘
```

### 2.2 State Flow

```
layoutStore.isChatPanelOpen ──→ ChatHistoryPanel (isOpen prop)
                                    │
                          ┌─────────┴──────────┐
                          │                    │
                     isOpen=false          isOpen=true
                     (아이콘 스트립)        (전체 패널)
                     w-12, 48px            w-72, 288px
                          │                    │
                     [펼치기] 클릭 ───→ toggleChatPanel()
                                       ←─── [접기] 클릭
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| ChatHistoryPanel | layoutStore.isChatPanelOpen | 접힘/펼침 상태 결정 |
| ChatHistoryPanel | layoutStore.toggleChatPanel | 토글 콜백 |
| AgentChatLayout | layoutStore | 상태 제공 및 ChatHistoryPanel에 전달 |
| AppSidebar | 변경 없음 (채팅 토글 props 제거) | 네비게이션 전용 |

---

## 3. Data Model

이 기능은 UI 리팩토링이므로 데이터 모델 변경 없음.

### 3.1 State 변경

**layoutStore.ts** — 변경 없음 (기존 인터페이스 유지)

```typescript
interface LayoutState {
  isChatPanelOpen: boolean;       // 유지
  selectedAgentId: string | null; // 유지
  toggleChatPanel: () => void;    // 유지
  setChatPanelOpen: (open: boolean) => void; // 유지
  selectAgent: (id: string | null) => void;  // 유지
}
```

persist 키 `'layout-preferences'` 유지 — 하위 호환성 보장.

---

## 4. API Specification

API 변경 없음. 순수 프론트엔드 UI 리팩토링.

---

## 5. UI/UX Design

### 5.1 접힌 상태 (Collapsed) — w-12

참조 디자인(docs/img/image1.png)에서 확인된 구조:

```
┌────────┐
│  [≡]   │  ← PanelLeftOpen 아이콘. 클릭 → 펼치기. title="펼치기"
│        │
│  [✏]   │  ← SquarePen 아이콘. 클릭 → 새 채팅. title="새 채팅"
│        │
│        │
│  (빈   │
│  공간) │
│        │
└────────┘
  w-12
```

**스타일 상세**:

| 요소 | Tailwind 클래스 |
|------|----------------|
| 컨테이너 | `flex h-full w-12 shrink-0 flex-col items-center border-r border-zinc-200 bg-white pt-4 gap-1` |
| 아이콘 버튼 영역 | `flex h-9 w-9 items-center justify-center rounded-lg` |
| 아이콘 기본 | `text-zinc-400 hover:bg-zinc-100 hover:text-zinc-600 transition-all` |
| 아이콘 크기 | `h-5 w-5` |
| 전환 | `transition-all duration-200 ease-in-out` |

### 5.2 펼친 상태 (Expanded) — w-72

기존 ChatHistoryPanel 구조 유지 + 헤더에 접기 버튼 추가:

```
┌──────────────────────────┐
│ [←]  ✏ 채팅              │  ← 헤더: 접기 버튼 추가
│──────────────────────────│
│ [+ 새 채팅]              │  ← 기존 유지
│──────────────────────────│
│ [🔍 채팅 검색...]        │  ← 기존 유지
│──────────────────────────│
│ ● 세션 1                 │
│   세션 2                 │
│   세션 3                 │  ← 기존 유지
│   ...                    │
└──────────────────────────┘
  w-72
```

**헤더 변경 상세**:

| 요소 | 현재 | 변경 후 |
|------|------|---------|
| 헤더 레이아웃 | `flex items-center gap-2 px-4 pt-5 pb-3` | `flex items-center justify-between px-4 pt-5 pb-3` |
| 왼쪽 영역 | 연필 아이콘 + "채팅" 텍스트 | **접기 버튼** (PanelLeftClose 아이콘) |
| 오른쪽 영역 | 없음 | 연필 아이콘 + "채팅" 텍스트 (기존 내용 유지) |

접기 버튼 스타일:
```
flex h-8 w-8 items-center justify-center rounded-lg
text-zinc-400 hover:bg-zinc-100 hover:text-zinc-600 transition-all
```

### 5.3 User Flow

```
[접힌 상태]
  ├── 펼치기 아이콘 클릭 → toggleChatPanel() → [펼친 상태]
  └── 새 채팅 아이콘 클릭 → onNewChat() → 새 세션 생성 (접힌 상태 유지)

[펼친 상태]
  ├── 접기 버튼 클릭 → toggleChatPanel() → [접힌 상태]
  ├── 새 채팅 버튼 클릭 → onNewChat()
  ├── 세션 선택 → onSelectSession(id)
  └── 검색 → 세션 필터링
```

### 5.4 라우트별 표시 조건

| 라우트 | 2단 사이드바 |
|--------|-------------|
| `/chatpage` | 접힌 또는 펼친 상태로 항상 표시 |
| 기타 라우트 | 렌더링하지 않음 |

**변경 전**: `showChatPanel = isChatRoute && isChatPanelOpen` → ChatHistoryPanel에 `isOpen={showChatPanel}` 전달
**변경 후**: `isChatRoute`일 때 ChatHistoryPanel 렌더링, `isOpen={isChatPanelOpen}` 전달

### 5.5 Component List

| Component | Location | 변경 내용 |
|-----------|----------|-----------|
| ChatHistoryPanel | `src/components/layout/ChatHistoryPanel.tsx` | 접힌 상태 아이콘 스트립 UI 추가, props에 `onToggle` 추가 |
| AppSidebar | `src/components/layout/AppSidebar.tsx` | 섹션(b) "채팅 접기/펼치기" 제거, `onToggleChatPanel`/`isChatPanelOpen` props 제거 |
| AgentChatLayout | `src/components/layout/AgentChatLayout.tsx` | AppSidebar props 제거, ChatHistoryPanel 렌더링 조건 변경 및 `onToggle` 전달 |

---

## 6. Error Handling

UI 리팩토링으로 새로운 에러 시나리오 없음. 기존 에러 처리(세션 로드 실패, 재시도) 그대로 유지.

---

## 7. Security Considerations

보안 변경 없음. UI 표시 로직만 변경.

---

## 8. Test Plan

### 8.1 Test Scope

| Type | Target | Tool |
|------|--------|------|
| Unit Test | ChatHistoryPanel 접힘/펼침 렌더링 | Vitest + RTL |
| Unit Test | AppSidebar 채팅 토글 제거 확인 | Vitest + RTL |
| Integration Test | AgentChatLayout 전체 흐름 | Vitest + RTL |

### 8.2 Test Cases

- [ ] ChatHistoryPanel `isOpen=false` → w-12 아이콘 스트립 렌더링 (펼치기 + 새 채팅 아이콘)
- [ ] ChatHistoryPanel `isOpen=true` → w-72 전체 패널 렌더링 (접기 버튼 포함)
- [ ] 펼치기 아이콘 클릭 시 `onToggle` 호출
- [ ] 접기 버튼 클릭 시 `onToggle` 호출
- [ ] 접힌 상태에서 새 채팅 아이콘 클릭 시 `onNewChat` 호출
- [ ] AppSidebar에 "채팅 접기/펼치기" 버튼이 없는지 확인
- [ ] 비채팅 라우트에서 ChatHistoryPanel이 렌더링되지 않는지 확인

---

## 9. Implementation Guide

### 9.1 File Structure (변경 대상)

```
src/
├── components/
│   └── layout/
│       ├── ChatHistoryPanel.tsx   ← 수정 (접힌 상태 UI 추가)
│       ├── AppSidebar.tsx         ← 수정 (채팅 토글 제거)
│       └── AgentChatLayout.tsx    ← 수정 (props 정리, 렌더링 조건)
└── store/
    └── layoutStore.ts             ← 변경 없음
```

### 9.2 Implementation Order

1. [ ] **ChatHistoryPanel 수정** — `onToggle` prop 추가, `isOpen=false`일 때 아이콘 스트립 렌더링, `isOpen=true`일 때 헤더에 접기 버튼 추가
2. [ ] **AppSidebar 수정** — 섹션(b) "채팅 접기/펼치기" 버튼 제거, `onToggleChatPanel`/`isChatPanelOpen` props 제거
3. [ ] **AgentChatLayout 수정** — AppSidebar에 채팅 관련 props 제거, ChatHistoryPanel 렌더링 조건을 `isChatRoute`로 변경, `onToggle={toggleChatPanel}` 전달
4. [ ] **테스트 작성** — 접힘/펼침 렌더링 및 토글 동작 테스트

### 9.3 ChatHistoryPanel 변경 상세

#### Props 변경

```typescript
// Before
interface ChatHistoryPanelProps {
  isOpen: boolean;
  sessions: ChatSession[];
  activeSessionId: string | null;
  onSelectSession: (id: string) => void;
  onNewChat: () => void;
  isLoading?: boolean;
  isError?: boolean;
  onRetry?: () => void;
}

// After
interface ChatHistoryPanelProps {
  isOpen: boolean;
  onToggle: () => void;              // 추가
  sessions: ChatSession[];
  activeSessionId: string | null;
  onSelectSession: (id: string) => void;
  onNewChat: () => void;
  isLoading?: boolean;
  isError?: boolean;
  onRetry?: () => void;
}
```

#### 렌더링 분기

```tsx
// 접힌 상태 — 아이콘 스트립
if (!isOpen) {
  return (
    <div className="flex h-full w-12 shrink-0 flex-col items-center border-r border-zinc-200 bg-white pt-4 gap-1">
      <button onClick={onToggle} title="펼치기" className="...">
        {/* PanelLeftOpen 아이콘 */}
      </button>
      <button onClick={onNewChat} title="새 채팅" className="...">
        {/* SquarePen 아이콘 */}
      </button>
    </div>
  );
}

// 펼친 상태 — 기존 + 접기 버튼
return (
  <div className="flex h-full w-72 shrink-0 flex-col border-r border-zinc-200 bg-white">
    <div className="flex items-center justify-between px-4 pt-5 pb-3">
      <button onClick={onToggle} title="접기" className="...">
        {/* PanelLeftClose 아이콘 */}
      </button>
      <div className="flex items-center gap-2">
        {/* 기존 연필 아이콘 + "채팅" 텍스트 */}
      </div>
    </div>
    {/* 이하 기존 내용 유지 */}
  </div>
);
```

#### 테두리 방향 변경

현재 코드: `border-l border-zinc-200` (왼쪽 테두리)
변경 후: `border-r border-zinc-200` (오른쪽 테두리)

> ChatHistoryPanel은 AppSidebar 오른쪽에 위치하므로, 메인 콘텐츠와의 구분선은 `border-r`이 자연스러움. 참조 디자인 이미지에서도 오른쪽 테두리 사용 확인.

### 9.4 AppSidebar 변경 상세

```typescript
// Before
interface AppSidebarProps {
  agents: AgentSummary[];
  selectedAgentId: string | null;
  onSelectAgent: (id: string) => void;
  onToggleChatPanel: () => void;     // 제거
  isChatPanelOpen: boolean;          // 제거
}

// After
interface AppSidebarProps {
  agents: AgentSummary[];
  selectedAgentId: string | null;
  onSelectAgent: (id: string) => void;
}
```

JSX에서 섹션(b) "채팅 접기/펼치기" 버튼 블록 전체 제거 (라인 60-71).

### 9.5 AgentChatLayout 변경 상세

```tsx
// Before
const showChatPanel = isChatRoute && isChatPanelOpen;

<AppSidebar
  agents={MOCK_AGENTS}
  selectedAgentId={selectedAgentId}
  onSelectAgent={selectAgent}
  onToggleChatPanel={toggleChatPanel}   // 제거
  isChatPanelOpen={isChatPanelOpen}     // 제거
/>

<ChatHistoryPanel
  isOpen={showChatPanel}                // 변경
  ...
/>

// After
<AppSidebar
  agents={MOCK_AGENTS}
  selectedAgentId={selectedAgentId}
  onSelectAgent={selectAgent}
/>

{isChatRoute && (
  <ChatHistoryPanel
    isOpen={isChatPanelOpen}            // layoutStore 직접 사용
    onToggle={toggleChatPanel}          // 추가
    sessions={sessions}
    activeSessionId={activeSessionId}
    onSelectSession={handleSelectSession}
    onNewChat={handleNewChat}
    isLoading={sessionsLoading}
    isError={sessionsError}
    onRetry={() => refetchSessions()}
  />
)}
```

---

## 10. Coding Convention Reference

### 10.1 이 기능의 컨벤션 적용

| Item | Convention Applied |
|------|-------------------|
| Component naming | PascalCase (ChatHistoryPanel, AppSidebar) |
| File organization | `src/components/layout/` — 기존 위치 유지 |
| State management | Zustand `layoutStore` + persist |
| Props typing | `interface` 상단 정의, `export default` 하단 |
| 아이콘 | 인라인 SVG (`<svg>` + `<path>`) — Heroicons 스타일 유지 |

---

## 11. Design Tokens

| 요소 | 값 | 비고 |
|------|-----|------|
| 접힌 폭 | `w-12` (48px) | 아이콘 2개 세로 배치 |
| 펼친 폭 | `w-72` (288px) | 기존 유지 |
| 배경 | `bg-white` | 1단 사이드바(`#0f0f0f`)와 대비 |
| 테두리 | `border-r border-zinc-200` | 메인 콘텐츠와 구분 |
| 아이콘 기본 | `text-zinc-400` | |
| 아이콘 호버 | `hover:bg-zinc-100 hover:text-zinc-600` | |
| 아이콘 크기 | `h-5 w-5` | |
| 버튼 영역 | `h-9 w-9 rounded-lg` | |
| 전환 애니메이션 | `transition-all duration-200 ease-in-out` | 접힘↔펼침 시 적용 없음 (조건 렌더링) |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-04-29 | Initial draft | 배상규 |
