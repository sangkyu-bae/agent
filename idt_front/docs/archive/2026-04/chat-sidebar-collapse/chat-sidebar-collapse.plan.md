# chat-sidebar-collapse Plan Document

> **Feature**: 채팅 2단 사이드바 접기/펼치기 리팩토링
>
> **Project**: sangplusbot (idt_front)
> **Author**: 배상규
> **Date**: 2026-04-29
> **Status**: Draft

---

## 1. 개요

### 1.1 목표

현재 1단 사이드바(AppSidebar)에 위치한 "채팅 접기/펼치기" 버튼을 제거하고,
2단 사이드바(ChatHistoryPanel)가 **접힌 상태에서도 아이콘 스트립으로 항상 존재**하도록 변경한다.

- **접힌 상태**: 좁은 아이콘 바(~48px)로 존재. 상단에 펼치기 아이콘, 그 아래 연필(새 채팅) 아이콘 표시
- **펼친 상태**: 현재 ChatHistoryPanel 그대로 (w-72, 검색 + 세션 목록)
- 접기/펼치기 토글은 2단 사이드바 자체에서만 제어
- 1단 사이드바의 "채팅 접기/펼치기" 버튼 완전 제거

### 1.2 비목표 (Scope Out)

- 채팅 라우트 외 페이지에서의 2단 사이드바 표시 (채팅 라우트에서만 표시)
- 에이전트 클릭 시 2단 사이드바 자동 펼침 (접힌 상태 유지)
- ChatHistoryPanel 내부 기능 변경 (검색, 세션 목록 등은 현재 상태 유지)
- 애니메이션 고도화 (기본 transition만 적용)

---

## 2. 현재 상태 분석

### 2.1 현재 레이아웃 구조

```
┌─────────────────────────────────────────────────────────┐
│ AgentChatLayout (flex, h-100%)                          │
│ ┌──────────┬───────────────┬──────────────────────────┐ │
│ │ AppSidebar│ChatHistoryPanel│      main (Outlet)      │ │
│ │  w-64    │ w-72 or w-0   │       flex-1             │ │
│ │ (1단)    │ (2단)         │                          │ │
│ │          │               │                          │ │
│ │ [채팅    │               │                          │ │
│ │  접기]   │               │                          │ │
│ │  버튼    │               │                          │ │
│ └──────────┴───────────────┴──────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

- `ChatHistoryPanel`: `isOpen` false일 때 `w-0 overflow-hidden opacity-0`으로 완전히 숨겨짐
- "채팅 접기/펼치기" 토글이 1단 사이드바(`AppSidebar`)에 위치

### 2.2 문제점

1. 채팅 접기/펼치기가 1단 사이드바에 있어 UX 직관성 부족
2. 접힌 상태에서 2단 사이드바가 완전히 사라져 존재 인지 불가
3. 이미지(docs/img/image1.png) 참조 디자인과 불일치

---

## 3. 변경 후 목표 구조

### 3.1 목표 레이아웃

```
┌───────────────────────────────────────────────────────────┐
│ AgentChatLayout (flex, h-100%)                            │
│ ┌──────────┬────┬──────────────────────────────────────┐  │
│ │ AppSidebar│ 2단│          main (Outlet)               │  │
│ │  w-64    │접힘│           flex-1                     │  │
│ │ (1단)    │~48px                                     │  │
│ │          │[≡] │                                      │  │
│ │          │[✏] │                                      │  │
│ │          │    │                                      │  │
│ └──────────┴────┴──────────────────────────────────────┘  │
│                                                           │
│ ┌──────────┬──────────────┬────────────────────────────┐  │
│ │ AppSidebar│  2단 펼침    │       main (Outlet)        │  │
│ │  w-64    │  w-72        │        flex-1              │  │
│ │ (1단)    │ [접기] [검색]│                            │  │
│ │          │ [새 채팅]    │                            │  │
│ │          │ [세션 목록]  │                            │  │
│ └──────────┴──────────────┴────────────────────────────┘  │
└───────────────────────────────────────────────────────────┘
```

### 3.2 접힌 상태 (Collapsed) 상세

```
┌────────┐
│  [≡]   │  ← 호버 시 "펼치기" 툴팁. 클릭 시 패널 펼침
│        │
│  [✏]   │  ← 호버 시 "새 채팅" 툴팁. 클릭 시 새 채팅 생성
│        │
│        │
│        │
│        │
└────────┘
 ~48px
```

- 배경: `bg-white`, 오른쪽 `border-r border-zinc-200`
- 아이콘: `text-zinc-400`, 호버 시 `text-zinc-600`
- 상단 아이콘: 펼치기 토글 (sidebar-expand 아이콘)
- 하단 아이콘: 연필 아이콘 (새 채팅)
- 각 아이콘에 `title` 속성으로 툴팁 제공

### 3.3 펼친 상태 (Expanded) 상세

현재 `ChatHistoryPanel` 내용 그대로 유지하되, 상단에 **접기 버튼** 추가:
- 헤더 영역에 접기 아이콘 버튼 추가 (← 또는 패널 닫기 아이콘)
- 호버 시 "접기" 툴팁

---

## 4. 영향 범위

### 4.1 수정 대상 파일

| 파일 | 변경 내용 |
|------|-----------|
| `src/components/layout/ChatHistoryPanel.tsx` | 접힌 상태 아이콘 스트립 UI 추가, `isOpen` 로직 변경 |
| `src/components/layout/AppSidebar.tsx` | "채팅 접기/펼치기" 버튼(섹션 b) 완전 제거, `onToggleChatPanel`/`isChatPanelOpen` props 제거 |
| `src/components/layout/AgentChatLayout.tsx` | AppSidebar에 전달하던 채팅 패널 props 제거 |
| `src/store/layoutStore.ts` | `isChatPanelOpen` 상태 유지 (2단 사이드바에서 사용) |

### 4.2 수정하지 않는 파일

| 파일 | 이유 |
|------|------|
| `src/pages/ChatPage/index.tsx` | 채팅 페이지 내부 로직 변경 없음 |
| `src/types/agent.ts` | 타입 변경 없음 |
| `src/hooks/useChat.ts` | 채팅 훅 변경 없음 |

---

## 5. 구현 계획

### 5.1 구현 순서

1. **ChatHistoryPanel 수정**: `isOpen=false`일 때 `w-0`이 아닌 아이콘 스트립(~48px) 표시
2. **AppSidebar 수정**: "채팅 접기/펼치기" 버튼 섹션(b) 제거, 관련 props 제거
3. **AgentChatLayout 수정**: AppSidebar에 전달하던 `onToggleChatPanel`, `isChatPanelOpen` props 제거
4. **ChatHistoryPanel에 토글 기능 이관**: 접힌 상태에서 펼치기, 펼친 상태에서 접기 버튼 추가

### 5.2 ChatHistoryPanel 변경 상세

```
// 접힌 상태 (isOpen === false)
<div className="flex h-full w-12 shrink-0 flex-col items-center border-r border-zinc-200 bg-white py-4 gap-2">
  <button title="펼치기" onClick={onToggle}>
    <!-- sidebar expand icon -->
  </button>
  <button title="새 채팅" onClick={onNewChat}>
    <!-- pencil icon -->
  </button>
</div>

// 펼친 상태 (isOpen === true)
<div className="flex h-full w-72 shrink-0 flex-col border-r border-zinc-200 bg-white">
  <!-- 기존 헤더에 접기 버튼 추가 -->
  <!-- 기존 내용 그대로 -->
</div>
```

### 5.3 Props 변경

**ChatHistoryPanel**:
- `isOpen`: 유지 (2단 사이드바 접힘/펼침 상태)
- `onToggle`: 추가 (접기/펼치기 토글 콜백)
- 기존 props (sessions, activeSessionId, onSelectSession, onNewChat, isLoading, isError, onRetry): 유지

**AppSidebar**:
- `onToggleChatPanel`: 제거
- `isChatPanelOpen`: 제거

---

## 6. 표시 조건

| 조건 | 2단 사이드바 표시 |
|------|-------------------|
| `/chatpage` 라우트 | 접힌 또는 펼친 상태로 표시 |
| 기타 라우트 (`/agent-builder`, `/tool-connection` 등) | 표시하지 않음 |
| 에이전트 클릭 시 | `/chatpage` 이동, 2단 사이드바 이전 상태(접힘/펼침) 유지 |

---

## 7. 디자인 토큰 참조

| 요소 | 값 |
|------|-----|
| 접힌 폭 | `w-12` (48px) |
| 펼친 폭 | `w-72` (288px) |
| 배경 | `bg-white` |
| 테두리 | `border-r border-zinc-200` |
| 아이콘 색상 | `text-zinc-400` → 호버 `text-zinc-600` |
| 아이콘 크기 | `h-5 w-5` |
| 아이콘 버튼 영역 | `h-9 w-9 rounded-lg` |
| 전환 애니메이션 | `transition-all duration-200 ease-in-out` |

---

## 8. 리스크 및 대응

| 리스크 | 대응 |
|--------|------|
| 접힌 상태에서 메인 콘텐츠 영역 너비 변화 | `flex-1`이므로 자동 조절, 추가 대응 불필요 |
| persist된 `isChatPanelOpen` 상태 | layoutStore에서 기존 persist 키 유지, 하위 호환 |
| 비채팅 라우트에서 2단 사이드바 깜빡임 | `isChatRoute` 조건으로 렌더링 자체를 제어 |
