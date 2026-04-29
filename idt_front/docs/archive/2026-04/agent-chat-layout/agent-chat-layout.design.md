# Design: Agent Chat Layout — Deep Agent Builder 스타일 UI 재구성

> **Feature ID**: agent-chat-layout
> **Plan**: [agent-chat-layout.plan.md](../../01-plan/features/agent-chat-layout.plan.md)
> **Rollback**: [agent-chat-layout.rollback.md](../../rollback/agent-chat-layout.rollback.md)
> **Created**: 2026-04-28
> **Status**: Draft

---

## 1. 컴포넌트 아키텍처

### 1-1. 전체 컴포넌트 트리

```
App.tsx
├── LoginPage / RegisterPage (변경 없음)
└── ProtectedRoute
    └── AgentChatLayout              ← 신규 (TopNav + AuthenticatedLayout 대체)
        ├── AppSidebar               ← 신규 (왼쪽 사이드바)
        │   ├── SidebarLogo
        │   ├── SidebarNav           (SUPER AI, 에이전트 템플릿, 유틸리티 등)
        │   ├── SidebarAgentList     (에이전트 목록 섹션)
        │   │   ├── AgentActionBar   (아이콘 액션바)
        │   │   └── AgentCategoryGroup (카테고리별 에이전트 아이템)
        │   ├── SidebarBottomMenu    (즐겨찾기, 역할설정, 리소스, 환경설정)
        │   └── SidebarUserProfile   (사용자 이름 + 이메일)
        ├── ChatHistoryPanel         ← 신규 (토글 가능 중간 패널)
        │   ├── ChatHistoryHeader    (새 채팅 + 검색)
        │   └── ChatSessionList      (기존 Sidebar 세션 로직 이관)
        └── <Outlet />               (메인 영역 — 라우트별 페이지)
             ├── ChatPage            (리팩토링 — Sidebar 의존 제거)
             ├── AgentBuilderPage    (기존 유지)
             ├── CollectionPage      (기존 유지)
             └── ... (기타 페이지)
```

### 1-2. 파일 구조

```
src/
├── components/
│   └── layout/
│       ├── AgentChatLayout.tsx      ← 신규 (3단 레이아웃 래퍼)
│       ├── AppSidebar.tsx           ← 신규 (왼쪽 사이드바)
│       ├── ChatHistoryPanel.tsx     ← 신규 (채팅 히스토리 패널)
│       ├── Sidebar.tsx              ← 제거 (ChatHistoryPanel로 대체)
│       ├── TopNav.tsx               ← 제거 (AppSidebar로 이관)
│       └── ChatHeader.tsx           ← 유지 (minor 수정)
├── store/
│   └── layoutStore.ts               ← 신규 (레이아웃 상태)
├── types/
│   └── agent.ts                     ← 확장 (AgentSummary 추가)
└── pages/
    └── ChatPage/
        └── index.tsx                ← 리팩토링
```

---

## 2. 컴포넌트 상세 설계

### 2-1. AgentChatLayout (레이아웃 래퍼)

**파일**: `src/components/layout/AgentChatLayout.tsx`

**역할**: TopNav + AuthenticatedLayout을 대체하는 최상위 레이아웃

```tsx
interface AgentChatLayoutProps {
  // children 대신 Outlet 사용
}
```

**레이아웃 구조**:
```
┌─────────────────────────────────────────────────────────┐
│ display: flex; height: 100%;                            │
│                                                         │
│ ┌──────────┐ ┌───────────────┐ ┌──────────────────────┐ │
│ │AppSidebar│ │ChatHistory    │ │ <Outlet />           │ │
│ │ w-64     │ │Panel          │ │ flex: 1              │ │
│ │ shrink-0 │ │ w-72          │ │                      │ │
│ │          │ │ (토글)         │ │                      │ │
│ │          │ │               │ │                      │ │
│ └──────────┘ └───────────────┘ └──────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

**핵심 로직**:
- `useLayoutStore()`에서 `isChatPanelOpen` 읽기
- ChatHistoryPanel에 세션 데이터 전달 (ChatPage에서 분리)
- Outlet으로 라우트별 페이지 렌더링

### 2-2. AppSidebar (왼쪽 사이드바)

**파일**: `src/components/layout/AppSidebar.tsx`

**역할**: 네비게이션 + 에이전트 목록

**Props**:
```tsx
interface AppSidebarProps {
  agents: AgentSummary[];
  selectedAgentId: string | null;
  onSelectAgent: (id: string) => void;
  onToggleChatPanel: () => void;
  isChatPanelOpen: boolean;
}
```

**내부 구조 (top → bottom)**:

#### (a) 로고 영역
```tsx
<div className="flex items-center gap-3 px-5 py-5">
  <div
    className="flex h-8 w-8 items-center justify-center rounded-lg"
    style={{ background: 'linear-gradient(135deg, #7c3aed 0%, #4f46e5 100%)' }}
  >
    <SparklesIcon className="h-4 w-4 text-white" />
  </div>
  <span className="text-[14px] font-semibold text-white">Deep Agent Builder</span>
</div>
```

#### (b) 채팅 펼치기/접기 토글
```tsx
<div className="px-3 pb-2">
  <button
    onClick={onToggleChatPanel}
    className="flex w-full items-center gap-2 rounded-xl border border-white/10 px-3 py-2 text-[12.5px] text-white/50 hover:bg-white/[0.07] hover:text-white/80"
    title={isChatPanelOpen ? '채팅 접기' : '채팅 펼치기'}
  >
    <ChatBubbleIcon />
    {isChatPanelOpen ? '채팅 접기' : '채팅 펼치기'}
  </button>
</div>
```

#### (c) 새 에이전트 버튼
```tsx
<div className="px-3 pb-2">
  <button className="flex w-full items-center gap-2 rounded-xl border border-white/10 px-3 py-2.5 text-[13px] text-white/60 hover:bg-white/[0.08]">
    <PlusIcon />
    새 에이전트
  </button>
</div>
```

#### (d) 네비게이션 메뉴
```tsx
const NAV_ITEMS = [
  { id: 'super-ai', icon: SparklesIcon, label: 'SUPER AI 에이전트', path: '/chatpage', isDefault: true },
  { id: 'templates', icon: TemplateIcon, label: '에이전트 템플릿', path: '/agent-builder' },
  { id: 'utility',  icon: WrenchIcon,   label: '유틸리티',         path: '/tool-connection' },
  { id: 'tasks',    icon: ClockIcon,     label: '작업',            path: '/workflow-designer' },
  { id: 'eval',     icon: ChartIcon,     label: '평가',            path: '/eval-dataset' },
];
```

스타일:
- 활성: `bg-white/[0.12] text-white`
- 비활성: `text-white/40 hover:bg-white/[0.07] hover:text-white/70`
- SUPER AI 에이전트 항목에는 왼쪽에 보라색 아이콘 강조

#### (e) 에이전트 섹션
```tsx
<div className="mt-2 border-t border-white/[0.06] pt-3">
  {/* 에이전트 헤더 + 액션바 */}
  <div className="flex items-center justify-between px-4 py-1">
    <div className="flex items-center gap-2">
      <SparklesIcon className="h-4 w-4 text-violet-400" />
      <span className="text-[13px] font-medium text-white">에이전트</span>
    </div>
    <div className="flex items-center gap-1">
      {/* 숨기기, 필터, 복사, 새로고침 아이콘 버튼 */}
      <IconButton icon={EyeOffIcon} title="숨기기" />
      <IconButton icon={FilterIcon} title="필터" />
      <IconButton icon={CopyIcon} title="복사" />
      <IconButton icon={RefreshIcon} title="새로고침" />
    </div>
  </div>

  {/* 카테고리별 에이전트 목록 */}
  <div className="mt-1 px-3">
    <CategoryGroup label="미분류" count={agents.length}>
      {agents.map(agent => (
        <AgentItem
          key={agent.id}
          agent={agent}
          isSelected={agent.id === selectedAgentId}
          onClick={() => onSelectAgent(agent.id)}
        />
      ))}
    </CategoryGroup>
  </div>
</div>
```

AgentItem 스타일:
```tsx
<button className={`
  w-full rounded-lg px-3 py-2 text-left transition-all
  ${isSelected
    ? 'bg-white/[0.12] text-white'
    : 'text-white/45 hover:bg-white/[0.06] hover:text-white/70'}
`}>
  <p className="text-[13px] font-medium truncate">{agent.name}</p>
  <p className="text-[11px] text-white/25 truncate mt-0.5">{agent.description}</p>
</button>
```

#### (f) 하단 메뉴
```tsx
const BOTTOM_ITEMS = [
  { icon: StarIcon,     label: '즐겨찾기',  path: null },
  { icon: KeyIcon,      label: '역할설정',  path: null },
  { icon: FolderIcon,   label: '리소스',    path: '/collections' },
  { icon: SettingsIcon, label: '환경설정',  path: '/settings' },
];
```

#### (g) 사용자 프로필
```tsx
<div className="border-t border-white/[0.06] px-4 py-3">
  <div className="flex items-center gap-3">
    <div className="flex h-7 w-7 items-center justify-center rounded-full bg-violet-600 text-[11px] font-semibold text-white">
      {user.email[0].toUpperCase()}
    </div>
    <div className="min-w-0 flex-1">
      <p className="truncate text-[13px] font-medium text-white">{user.username ?? user.email}</p>
      <p className="truncate text-[11px] text-white/30">{user.email}</p>
    </div>
  </div>
</div>
```

**전체 사이드바 스타일**:
- 너비: `w-64` (256px)
- 배경: `bg-[#0f0f0f]` (기존 Sidebar와 동일)
- 구조: `flex flex-col h-full`

---

### 2-3. ChatHistoryPanel (채팅 히스토리 패널)

**파일**: `src/components/layout/ChatHistoryPanel.tsx`

**역할**: 토글 가능한 채팅 세션 목록 패널

**Props**:
```tsx
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
```

**레이아웃**:
```
┌─────────────────────────┐
│  [연필 아이콘] 채팅      │  ← 헤더 (제목)
├─────────────────────────┤
│  [✏] 새 채팅            │  ← 새 채팅 버튼
├─────────────────────────┤
│  🔍 채팅 검색...        │  ← 검색 입력
├─────────────────────────┤
│  안녕                    │  ← 세션 아이템
│  2026-04-02 11:02       │
│                         │
│  이전 대화              │
│  2026-04-01 09:15       │
│                         │
│  ...                    │
└─────────────────────────┘
```

**스타일**:
- 너비: `w-72` (288px)
- 배경: `bg-white`
- 왼쪽 보더: `border-l border-zinc-200`
- 열림/닫힘 애니메이션: `transition-all duration-200`
- 닫힌 상태: `w-0 overflow-hidden opacity-0`

**세션 아이템** (기존 Sidebar 로직 이관):
```tsx
<button className={`
  w-full rounded-xl px-4 py-3 text-left transition-all
  ${isActive
    ? 'bg-violet-50 border-l-2 border-violet-500'
    : 'hover:bg-zinc-50'}
`}>
  <span className="text-[13.5px] font-medium text-zinc-800 truncate">{session.title}</span>
  <span className="text-[11px] text-zinc-400 mt-1">{formatDate(session.updatedAt)}</span>
</button>
```

---

### 2-4. ChatPage 리팩토링

**파일**: `src/pages/ChatPage/index.tsx`

**변경 핵심**: Sidebar 의존 제거, 메인 채팅 영역만 담당

**변경 전**:
```tsx
<div style={{ display: 'flex', height: '100%' }}>
  <Sidebar ... />           // ← 제거
  <main>
    <ChatHeader ... />
    <MessageList ... />
    <ChatInput ... />
  </main>
</div>
```

**변경 후**:
```tsx
<div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
  <ChatHeader
    agentName={selectedAgent?.name ?? 'SUPER AI Agent'}
    agentDescription={selectedAgent?.description}
    messageCount={messages.length}
  />
  <div style={{ flex: 1, overflowY: 'auto' }}>
    <div style={{ maxWidth: '768px', margin: '0 auto', height: '100%' }}>
      {messages.length === 0
        ? <EmptyAgentState agent={selectedAgent} />
        : <MessageList messages={messages} isStreaming={isPending} onSuggestionClick={handleSend} />
      }
    </div>
  </div>
  <ChatInput
    onSend={handleSend}
    isLoading={isPending}
    useRag={useRag}
    onToggleRag={() => setUseRag(v => !v)}
    modelName="claude-sonnet-4-5"
  />
</div>
```

**EmptyAgentState** (빈 상태 컴포넌트):
```tsx
// 레퍼런스 image1.png의 중앙 영역과 동일
<div className="flex flex-col items-center justify-center h-full">
  {/* 에이전트 아바타 */}
  <div
    className="flex h-16 w-16 items-center justify-center rounded-2xl shadow-lg mb-6"
    style={{ background: 'linear-gradient(135deg, #7c3aed 0%, #4f46e5 100%)' }}
  >
    <SparklesIcon className="h-8 w-8 text-white" />
  </div>
  {/* 타이틀 */}
  <h2 className="text-2xl font-bold text-violet-600 mb-2">
    {agent?.name ?? 'SUPER AI Agent'}와 대화하세요
  </h2>
  <p className="text-[14px] text-zinc-400">
    {agent?.description ?? 'Auto-routing meta agent for all your agents'}
  </p>
</div>
```

**세션/메시지 로직**: 기존 ChatPage의 상태 관리 로직은 그대로 유지하되, 세션 목록 관련 props를 AgentChatLayout으로 올린다.

---

## 3. 상태 관리 설계

### 3-1. layoutStore (신규)

**파일**: `src/store/layoutStore.ts`

```tsx
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface LayoutState {
  isChatPanelOpen: boolean;
  selectedAgentId: string | null;
  toggleChatPanel: () => void;
  setChatPanelOpen: (open: boolean) => void;
  selectAgent: (id: string | null) => void;
}

export const useLayoutStore = create<LayoutState>()(
  persist(
    (set) => ({
      isChatPanelOpen: false,
      selectedAgentId: 'super-ai',
      toggleChatPanel: () => set((s) => ({ isChatPanelOpen: !s.isChatPanelOpen })),
      setChatPanelOpen: (open) => set({ isChatPanelOpen: open }),
      selectAgent: (id) => set({ selectedAgentId: id }),
    }),
    { name: 'layout-preferences' }
  )
);
```

**persist 이유**: 채팅 패널 열림/닫힘, 선택된 에이전트를 새로고침 후에도 유지

### 3-2. 데이터 흐름

```
AgentChatLayout
  ├── useLayoutStore() → isChatPanelOpen, selectedAgentId
  ├── useConversationSessions(userId) → sessions
  ├── useMockAgents() → agents (Mock 데이터)
  │
  ├── AppSidebar
  │   ← agents, selectedAgentId, onSelectAgent, isChatPanelOpen, onToggleChatPanel
  │
  ├── ChatHistoryPanel
  │   ← isOpen, sessions, activeSessionId, onSelectSession, onNewChat
  │
  └── <Outlet context={{ selectedAgent, sessions, activeSessionId, ... }} />
       └── ChatPage
            ← useOutletContext() 또는 useLayoutStore()로 상태 접근
```

### 3-3. 세션 상태 lift-up

현재 ChatPage에 있는 세션 관련 상태를 AgentChatLayout으로 올린다:

| 상태 | 현재 위치 | 변경 후 위치 | 이유 |
|------|----------|-------------|------|
| `draftSessions` | ChatPage | AgentChatLayout | ChatHistoryPanel에서도 표시 필요 |
| `activeSessionId` | ChatPage | AgentChatLayout | ChatHistoryPanel + ChatPage 모두 사용 |
| `messagesBySession` | ChatPage | ChatPage (유지) | 메시지는 ChatPage 내부에서만 사용 |
| `useRag` | ChatPage | ChatPage (유지) | 채팅 입력 관련이므로 ChatPage 유지 |

---

## 4. 타입 설계

### 4-1. AgentSummary (agent.ts에 추가)

```tsx
export interface AgentSummary {
  id: string;
  name: string;
  description: string;
  category: string;
  isDefault?: boolean;
}
```

### 4-2. Mock 에이전트 데이터

```tsx
export const MOCK_AGENTS: AgentSummary[] = [
  {
    id: 'super-ai',
    name: 'SUPER AI Agent',
    description: 'Auto-routing meta agent for all your agents',
    category: '기본',
    isDefault: true,
  },
  {
    id: 'doc-rag',
    name: '사내 문서 RAG 챗봇',
    description: '업로드된 사내 문서를 기반으로 정보를 검색합니다',
    category: '미분류',
  },
  {
    id: 'trading-assistant',
    name: 'AI 트레이딩 어시스턴트',
    description: '시장 데이터, 기술적 분석, 뉴스 및 트렌드를 기반으로 투자 인사이트를 제공합니다',
    category: '미분류',
  },
  {
    id: 'doc-rag-2',
    name: '사내 문서 RAG 챗봇',
    description: '업로드된 사내 문서를 기반으로 정보를 검색합니다',
    category: '미분류',
  },
];
```

### 4-3. Outlet Context 타입

```tsx
export interface AgentChatOutletContext {
  selectedAgent: AgentSummary | null;
  activeSessionId: string | null;
  setActiveSessionId: (id: string) => void;
  handleNewChat: () => void;
  sessions: ChatSession[];
}
```

---

## 5. App.tsx 변경 설계

### 변경 전:

```tsx
const AuthenticatedLayout = () => (
  <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
    <TopNav />
    <div style={{ flex: 1, overflow: 'auto' }}>
      <Outlet />
    </div>
  </div>
);
```

### 변경 후:

```tsx
// TopNav import 제거
// AgentChatLayout import 추가

<Route element={<ProtectedRoute />}>
  <Route element={<AgentChatLayout />}>
    <Route path="/" element={<Navigate to="/chatpage" replace />} />
    <Route path="/chatpage" element={<ChatPage />} />
    <Route path="/collections" element={<CollectionPage />} />
    <Route path="/collections/:collectionName/documents" element={<CollectionDocumentsPage />} />
    <Route path="/agent-builder" element={<AgentBuilderPage />} />
    <Route path="/tool-connection" element={<ToolConnectionPage />} />
    <Route path="/tool-admin" element={<ToolAdminPage />} />
    <Route path="/workflow-designer" element={<WorkflowDesignerPage />} />
    <Route path="/workflow-builder" element={<WorkflowBuilderPage />} />
    <Route path="/eval-dataset" element={<EvalDatasetPage />} />
  </Route>
</Route>
```

**AuthenticatedLayout 제거**: AgentChatLayout이 이 역할을 대체

---

## 6. 스타일 상세

### 6-1. 색상 토큰 (기존 디자인 시스템 준수)

| 요소 | 토큰 | 값 |
|------|------|-----|
| AppSidebar 배경 | `bg-[#0f0f0f]` | #0f0f0f |
| ChatHistoryPanel 배경 | `bg-white` | #fff |
| 메인 영역 배경 | `bg-white` | #fff |
| 활성 네비 아이템 | `bg-white/[0.12] text-white` | rgba(255,255,255,0.12) |
| 비활성 네비 아이템 | `text-white/40` | rgba(255,255,255,0.4) |
| 에이전트 헤더 아이콘 | `text-violet-400` | #a78bfa |
| 활성 세션 (히스토리) | `bg-violet-50 border-l-2 border-violet-500` | - |
| 구분선 | `border-white/[0.06]` (사이드바) / `border-zinc-200` (메인) | - |

### 6-2. 너비 규격

| 요소 | 너비 | Tailwind |
|------|------|----------|
| AppSidebar | 256px | `w-64` |
| ChatHistoryPanel (열림) | 288px | `w-72` |
| ChatHistoryPanel (닫힘) | 0px | `w-0 overflow-hidden` |
| 메인 영역 | 나머지 | `flex-1` |
| 메시지 최대 폭 | 768px | `max-w-3xl` |

### 6-3. 애니메이션

| 요소 | 애니메이션 |
|------|-----------|
| ChatHistoryPanel 토글 | `transition-all duration-200 ease-in-out` |
| 네비 아이템 hover | `transition-all duration-150` |
| 에이전트 아이템 hover | `transition-all duration-150` |
| 세션 아이템 hover | `transition-all duration-150` |

---

## 7. 구현 순서 (상세)

### Phase 1: 기반 작업

| 순서 | 파일 | 작업 | 설명 |
|------|------|------|------|
| 1-1 | `src/types/agent.ts` | 확장 | `AgentSummary` 타입 + `MOCK_AGENTS` 상수 추가 |
| 1-2 | `src/store/layoutStore.ts` | 신규 | `isChatPanelOpen`, `selectedAgentId` 상태 관리 |

### Phase 2: AppSidebar

| 순서 | 파일 | 작업 | 설명 |
|------|------|------|------|
| 2-1 | `src/components/layout/AppSidebar.tsx` | 신규 | 로고 + 네비 + 에이전트 목록 + 하단 메뉴 + 프로필 |

### Phase 3: ChatHistoryPanel

| 순서 | 파일 | 작업 | 설명 |
|------|------|------|------|
| 3-1 | `src/components/layout/ChatHistoryPanel.tsx` | 신규 | 토글 패널 + 세션 목록 (Sidebar 로직 이관) |

### Phase 4: AgentChatLayout + 통합

| 순서 | 파일 | 작업 | 설명 |
|------|------|------|------|
| 4-1 | `src/components/layout/AgentChatLayout.tsx` | 신규 | 3단 레이아웃 래퍼 + 세션 상태 lift-up |
| 4-2 | `src/pages/ChatPage/index.tsx` | 수정 | Sidebar 제거, useOutletContext 연동, EmptyAgentState 추가 |
| 4-3 | `src/App.tsx` | 수정 | AuthenticatedLayout → AgentChatLayout 교체 |

### Phase 5: 정리

| 순서 | 파일 | 작업 | 설명 |
|------|------|------|------|
| 5-1 | `src/components/layout/TopNav.tsx` | 제거 | AppSidebar로 완전 이관 확인 후 삭제 |
| 5-2 | `src/components/layout/Sidebar.tsx` | 제거 | ChatHistoryPanel로 대체 확인 후 삭제 |
| 5-3 | 전체 | 검증 | 모든 라우트 접근, 채팅 기능, 세션 전환 테스트 |

---

## 8. 비에이전트 페이지 처리

에이전트/채팅이 아닌 페이지에서는 ChatHistoryPanel이 숨겨지고, 메인 영역에 해당 페이지가 표시된다.

| 라우트 | ChatHistoryPanel | 메인 영역 |
|--------|-----------------|----------|
| `/chatpage` | 토글 가능 | ChatPage |
| `/agent-builder` | 자동 닫힘 | AgentBuilderPage |
| `/collections` | 자동 닫힘 | CollectionPage |
| `/tool-connection` | 자동 닫힘 | ToolConnectionPage |
| 기타 | 자동 닫힘 | 해당 페이지 |

**구현**: `useLocation()` 감시 → `/chatpage`가 아닌 경우 `setChatPanelOpen(false)` 호출하지 않고 패널을 렌더링하지 않음

```tsx
// AgentChatLayout 내부
const location = useLocation();
const isChatRoute = location.pathname === '/chatpage';
const showChatPanel = isChatRoute && isChatPanelOpen;
```

---

## 9. 검증 체크리스트

### 기능 검증

- [ ] SUPER AI Agent 선택 시 채팅 페이지로 이동 및 대화 가능
- [ ] 에이전트 목록에서 다른 에이전트 선택 시 UI 전환
- [ ] 채팅 히스토리 패널 열기/닫기 토글 동작
- [ ] 새 채팅 생성 → 세션 목록 반영
- [ ] 세션 선택 → 메시지 로드
- [ ] 메시지 전송 → 응답 수신 (기존 API 동일)
- [ ] 비채팅 페이지(컬렉션, 에이전트 빌더 등) 접근 정상
- [ ] 로그아웃 기능 정상 동작

### 레이아웃 검증

- [ ] 사이드바 w-64 고정, 스크롤 시 고정 유지
- [ ] 채팅 패널 닫힘 시 메인 영역 전체 너비 활용
- [ ] 채팅 패널 열림 시 3단 레이아웃 정상 표시
- [ ] 메시지 영역 max-w-3xl 중앙 정렬 유지
- [ ] 높이 100% 채움 (스크롤바 올바른 위치)

### 회귀 검증

- [ ] 기존 모든 라우트 접근 가능 확인
- [ ] 기존 채팅 기능 회귀 없음
- [ ] 로그인/로그아웃 흐름 정상
- [ ] AdminRoute 정상 동작
