# Rollback Guide: agent-chat-layout

> **Feature**: agent-chat-layout (Deep Agent Builder 스타일 UI 재구성)
> **Created**: 2026-04-28
> **Base Commit**: `459a9cc9bab5301f12b01ad151ae1319a1dab65f` (master)
> **Base Branch**: master

---

## 1. 롤백 명령어 (Quick Rollback)

### 방법 1: Git Reset (가장 간단)

```bash
# agent-chat-layout 작업 시작 전 커밋으로 복귀
git reset --hard 459a9cc9bab5301f12b01ad151ae1319a1dab65f
```

### 방법 2: Git Revert (커밋 히스토리 유지)

```bash
# agent-chat-layout 관련 커밋들을 역순으로 revert
git log --oneline --grep="agent-chat-layout" | while read hash msg; do
  git revert --no-commit $hash
done
git commit -m "revert: rollback agent-chat-layout feature"
```

### 방법 3: 파일 단위 복원

```bash
# 특정 파일만 원래 상태로 복원
git checkout 459a9cc9 -- src/App.tsx
git checkout 459a9cc9 -- src/components/layout/Sidebar.tsx
git checkout 459a9cc9 -- src/components/layout/TopNav.tsx
git checkout 459a9cc9 -- src/components/layout/ChatHeader.tsx
git checkout 459a9cc9 -- src/pages/ChatPage/index.tsx
git checkout 459a9cc9 -- src/types/agent.ts

# 신규 생성 파일 삭제
rm -f src/components/layout/AppSidebar.tsx
rm -f src/components/layout/ChatHistoryPanel.tsx
rm -f src/components/layout/AgentChatLayout.tsx
```

---

## 2. 변경 대상 파일 목록

### 수정되는 기존 파일

| 파일 | 변경 유형 | 설명 |
|------|----------|------|
| `src/App.tsx` | **Major** | AuthenticatedLayout 구조 변경, TopNav 제거 |
| `src/components/layout/Sidebar.tsx` | **Replace** | ChatHistoryPanel로 대체 |
| `src/components/layout/TopNav.tsx` | **Remove** | 사이드바로 네비 이관 후 제거 |
| `src/components/layout/ChatHeader.tsx` | **Minor** | 에이전트 정보 표시 추가 가능 |
| `src/pages/ChatPage/index.tsx` | **Major** | 3단 레이아웃 통합, Sidebar 의존 제거 |
| `src/types/agent.ts` | **Extend** | AgentSummary 타입 추가 |

### 신규 생성 파일

| 파일 | 설명 |
|------|------|
| `src/components/layout/AppSidebar.tsx` | 왼쪽 네비 + 에이전트 목록 사이드바 |
| `src/components/layout/ChatHistoryPanel.tsx` | 토글 가능 채팅 히스토리 패널 |
| `src/components/layout/AgentChatLayout.tsx` | 3단 레이아웃 래퍼 컴포넌트 |

---

## 3. 현재 파일 상태 스냅샷 (변경 전)

### 3-1. src/App.tsx

**핵심 구조**: `BrowserRouter > AuthInitializer > Routes`

```
AuthenticatedLayout 구조:
  <div style="display:flex; flexDirection:column; height:100%">
    <TopNav />           ← 상단 가로 메뉴바 (데이터/에이전트 드롭다운)
    <div style="flex:1; overflow:auto">
      <Outlet />         ← 각 페이지 렌더링
    </div>
  </div>
```

**라우트**:
- `/` → `/chatpage` redirect
- `/chatpage` → ChatPage
- `/collections` → CollectionPage
- `/agent-builder` → AgentBuilderPage
- `/tool-connection` → ToolConnectionPage
- `/tool-admin` → ToolAdminPage
- `/workflow-designer` → WorkflowDesignerPage
- `/workflow-builder` → WorkflowBuilderPage
- `/eval-dataset` → EvalDatasetPage
- `/collections/:collectionName/documents` → CollectionDocumentsPage
- `/admin/users` → AdminUsersPage (AdminRoute)

### 3-2. src/components/layout/TopNav.tsx (237줄)

**역할**: 상단 가로 메뉴바

**NAV_MENUS 구조**:
- 데이터 → 컬렉션 관리 (`/collections`)
- 에이전트 → 에이전트 만들기 (`/agent-builder`), 도구 연결 (`/tool-connection`), 워크플로우 설계 (`/workflow-designer`), 플로우 빌더 (`/workflow-builder`), 도구 관리 (`/tool-admin`)

**사용자 영역**: 아바타 버튼 + 로그아웃 드롭다운

### 3-3. src/components/layout/Sidebar.tsx (193줄)

**역할**: 채팅 세션 목록 + 하단 네비게이션

**Props**: sessions, activeSessionId, onSelectSession, onNewChat, isLoading, isError, onRetry

**NAV_ITEMS 구조**:
- 문서 관리 (`/documents`)
- 에이전트 만들기 (`/agent-builder`)
- 도구 연결 (`/tool-connection`)
- 워크플로우 설계 (`/workflow-designer`)
- 평가 데이터셋 (`/eval-dataset`)
- 설정 (`/settings`)

**스타일**: w-64, bg-[#0f0f0f] (다크 테마)

### 3-4. src/components/layout/ChatHeader.tsx (47줄)

**역할**: 채팅 헤더 (제목 + 메시지 수 + 상태 뱃지 + 액션 버튼)

**Props**: title, messageCount

### 3-5. src/pages/ChatPage/index.tsx (180줄)

**역할**: 채팅 메인 페이지

**레이아웃**: `<div flex> <Sidebar /> <main flex-col> <ChatHeader /> <MessageList /> <ChatInput /> </main> </div>`

**상태 관리**:
- `draftSessions`, `activeSessionId`, `messagesBySession`, `useRag` (로컬 state)
- `useConversationSessions(userId)` (서버 세션 조회)
- `useSessionMessages(sessionId)` (서버 메시지 조회)
- `useGeneralChat()` (메시지 전송)

**주요 핸들러**: handleSend, handleNewChat, handleSelectSession, syncSessionId

### 3-6. src/types/agent.ts (32줄)

**현재 타입**: AgentStatus, AgentRun, AgentStep, RunAgentRequest, RunAgentResponse

---

## 4. 의존성 그래프 (현재)

```
App.tsx
  ├── TopNav.tsx ← 제거 대상
  │   ├── useAuthStore (로그아웃)
  │   └── NAV_MENUS (네비 데이터)
  └── ChatPage/index.tsx
       ├── Sidebar.tsx ← 대체 대상
       │   ├── ChatSession type
       │   ├── formatDate util
       │   └── NAV_ITEMS (네비 데이터)
       ├── ChatHeader.tsx
       ├── MessageList.tsx (유지)
       ├── ChatInput.tsx (유지)
       ├── useChat hooks (유지)
       └── useAuthStore (유지)
```

---

## 5. 롤백 시 주의사항

1. **새로 생성된 파일 삭제 필수**: AppSidebar.tsx, ChatHistoryPanel.tsx, AgentChatLayout.tsx
2. **타입 파일 확인**: agent.ts에 추가된 AgentSummary 타입 제거 필요
3. **라우팅 확인**: App.tsx 롤백 후 모든 라우트 정상 동작 확인
4. **npm run dev 후 전체 페이지 접근 테스트**
5. **pdca-status.json**: `agent-chat-layout` feature 항목 수동 제거
