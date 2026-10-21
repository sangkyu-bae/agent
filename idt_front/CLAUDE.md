# IDT Front — RAG + AI Agent Frontend

## 프로젝트 개요
React + TypeScript 기반의 RAG(Retrieval-Augmented Generation) 및 AI Agent 프론트엔드 프로젝트.
사용자가 문서를 업로드하고, AI Agent와 대화하며, 검색 증강 생성 결과를 확인할 수 있는 인터페이스 제공.

## 기술 스택
- **Framework**: React 19 + TypeScript
- **Build Tool**: Vite 8
- **Styling**: Tailwind CSS v4 (`@tailwindcss/vite` 플러그인)
- **State Management**: Zustand
- **Data Fetching**: TanStack Query (React Query v5)
- **Routing**: React Router v6
- **HTTP Client**: Axios
- **UI Components**: shadcn/ui
- **Markdown Rendering**: react-markdown + remark-gfm
- **Streaming**: EventSource / Fetch Stream (SSE 기반) + WebSocket
- **Testing**: Vitest + React Testing Library + MSW (Mock Service Worker)

## 폴더 구조
```
src/
├── assets/              # 정적 파일 (이미지, 폰트 등)
├── components/          # 재사용 가능한 UI 컴포넌트
│   ├── common/          # 공통 컴포넌트 (Button, Input, Modal 등)
│   ├── layout/          # 레이아웃 컴포넌트 (Header, Sidebar, PageLayout)
│   ├── chat/            # 채팅 관련 컴포넌트 (MessageBubble, ChatInput, StreamingText)
│   ├── agent/           # AI Agent 관련 컴포넌트 (AgentStatus, ToolCallDisplay, ThinkingIndicator)
│   └── rag/             # RAG 관련 컴포넌트 (DocumentUploader, SourceCitation, RetrievedChunks)
├── pages/               # 라우트 단위 페이지 컴포넌트
│   ├── ChatPage/
│   ├── AgentPage/
│   ├── DocumentPage/
│   └── SettingsPage/
├── hooks/               # 커스텀 React 훅
│   ├── useChat.ts       # 채팅 메시지 관리
│   ├── useStream.ts     # SSE 스트리밍 처리
│   ├── useWebSocket.ts  # WebSocket 공통 훅 (연결/재연결/송수신)
│   ├── useAgent.ts      # Agent 상태 관리
│   └── useDocuments.ts  # 문서 업로드/관리
├── services/            # API 통신 레이어
│   ├── api/             # axios 인스턴스 및 공통 설정
│   ├── chatService.ts   # 채팅 API
│   ├── agentService.ts  # Agent API
│   └── ragService.ts    # RAG / 문서 API
├── store/               # Zustand 전역 상태
│   ├── chatStore.ts
│   ├── agentStore.ts
│   └── documentStore.ts
├── types/               # TypeScript 타입 정의
│   ├── chat.ts
│   ├── agent.ts
│   ├── rag.ts
│   └── api.ts
├── utils/               # 유틸리티 함수
│   ├── formatters.ts    # 날짜, 텍스트 포맷
│   ├── streamParser.ts  # SSE/스트림 파싱
│   └── validators.ts
├── lib/                 # 라이브러리 공통 설정
│   ├── queryClient.ts   # TanStack Query QueryClient 싱글톤
│   └── queryKeys.ts     # 쿼리 키 팩토리 (중앙 관리)
├── constants/           # 상수 및 설정값
│   ├── api.ts           # API 엔드포인트 상수
│   └── agent.ts         # Agent 관련 상수
└── __tests__/           # 통합 테스트 (도메인별)
    ├── hooks/           # 커스텀 훅 테스트
    ├── components/      # 컴포넌트 통합 테스트
    └── mocks/           # MSW 핸들러 및 공통 Mock
        ├── handlers.ts  # API 핸들러 (chat, agent, rag)
        └── server.ts    # MSW 서버 설정
```

> 단위 테스트 파일은 소스 파일과 같은 디렉토리에 위치 (`useChat.test.ts`, `MessageBubble.test.tsx`)

## 코딩 컨벤션

### 파일/컴포넌트 네이밍
- 컴포넌트 파일: PascalCase (`ChatInput.tsx`)
- 훅/서비스/유틸 파일: camelCase (`useChat.ts`, `chatService.ts`)
- 타입 파일: camelCase (`chat.ts`)
- 페이지 디렉토리: PascalCase (`ChatPage/index.tsx`)

### 컴포넌트 작성 규칙
- 함수형 컴포넌트 + Arrow function 사용
- Props 타입은 `interface`로 정의, 파일 상단에 위치
- `export default`는 파일 하단에 단독으로 선언

```tsx
// 예시
interface MessageBubbleProps {
  role: 'user' | 'assistant' | 'tool';
  content: string;
  isStreaming?: boolean;
}

const MessageBubble = ({ role, content, isStreaming = false }: MessageBubbleProps) => {
  return (/* ... */);
};

export default MessageBubble;
```

### 타입 정의 규칙
- API 응답 타입: `XxxResponse` 접미사
- API 요청 타입: `XxxRequest` 접미사
- 도메인 모델: 접미사 없음 (`Message`, `Document`, `AgentRun`)
- Enum 대신 `as const` 객체 + 타입 추출 사용

### 상태 관리
- 서버 상태: TanStack Query (`useQuery`, `useMutation`)
- 클라이언트 전역 상태: Zustand
- 로컬 상태: `useState` / `useReducer`
- 스트리밍 상태는 `useStream` 훅으로 캡슐화
- Zustand 스토어는 `store/commonSlices.ts`의 슬라이스 팩토리 조합으로 작성
  - 비동기 로딩/에러: `createLoadingSlice` → `status`, `error`, `startLoading`, `finishLoading`, `failLoading`
  - 리스트 CRUD: `createListSlice` → `items`, `setItems`, `addItem`, `removeItem`, `updateItem`
  - 다중 선택: `createSelectionSlice` → `selectedIds`, `toggleSelection`, `selectAll`, `clearSelection`
- TanStack Query 공통 설정은 `lib/queryClient.ts` + `lib/queryKeys.ts` 사용
  - QueryClient 싱글톤: staleTime 1분, gcTime 5분, retry 1회
  - 모든 queryKey는 `queryKeys` 팩토리에서만 정의 (직접 문자열 배열 금지)
  - 도메인별 훅: `useChat.ts`, `useDocuments.ts`, `useAgent.ts`에서 `useQuery`/`useMutation` 사용

### API 통신
- 모든 API 호출은 `services/` 레이어를 통해 처리 (컴포넌트에서 직접 axios 호출 금지)
- SSE 스트리밍은 `useStream` 훅으로 처리
- 에러 처리는 axios interceptor에서 공통 처리

## AI/RAG/Agent 관련 주요 개념

### RAG Flow
1. 사용자가 문서 업로드 → `ragService.uploadDocument()`
2. 백엔드에서 청킹 및 임베딩 처리
3. 사용자 질문 → 유사 청크 검색 → LLM 응답 생성
4. 응답에 출처 표시 (`SourceCitation` 컴포넌트)

### AI Agent Flow
1. 사용자 입력 → Agent 실행 시작
2. Agent가 Tool을 호출하며 단계별 처리 (`ThinkingIndicator`, `ToolCallDisplay`)
3. 최종 응답 스트리밍 출력
4. Agent 상태: `idle` | `thinking` | `tool_calling` | `responding` | `error`

### 스트리밍 처리
- SSE(Server-Sent Events) 기반 스트리밍
- 델타(delta) 방식 텍스트 누적 처리
- 스트리밍 중 UI 업데이트는 `requestAnimationFrame` 활용

## UI 디자인 시스템

### 디자인 방향
Claude/ChatGPT 스타일의 모던 AI 채팅 UI. 깔끔하고 여백이 충분하며 타이포그래피가 명확하다.
토큰과 공통 컴포넌트는 `docs/02-design/features/ui-redesign-chat.design.md` §5가 원본이다. 채팅 화면이 적용 완료 기준이며, 나머지 화면은 후속 사이클에서 같은 규칙으로 옮긴다.

### 디자인 토큰 (`src/index.css` `@theme`)

토큰은 `index.css` 한 곳에만 정의한다. 컴포넌트에서 hex 리터럴, 인라인 `style={{ background }}`, 임의 글자 크기 `text-[Npx]`를 쓰지 않는다.

| 역할 | 토큰 클래스 | 비고 |
|------|------------|------|
| **브랜드** | `bg-brand-600` `hover:bg-brand-700` `text-brand-600/700` `border-brand-200` `bg-brand-50` | violet 계열. `brand-800`은 그라데이션 종점 |
| **그라데이션** | `bg-linear-to-br from-brand-600 to-brand-800` | AI 아바타. 인라인 style 금지 |
| **유저 버블** | `bg-linear-to-br from-bubble-from to-bubble-to text-white` | |
| **표면** | `bg-surface` / `bg-surface-muted` / `bg-surface-sunken` | 흰색 / zinc-50 / zinc-100 |
| **선** | `border-border` / `border-border-strong` | zinc-200 / zinc-300 |
| **텍스트** | `text-fg` / `text-fg-secondary` / `text-fg-muted` / `text-fg-subtle` | zinc-900 / 700 / 600 / 500. 힌트 하한은 `fg-subtle`(4.6:1). `zinc-400` 금지 |
| **사이드바** | `bg-sidebar` `text-sidebar-fg` `text-sidebar-fg-muted` `hover:bg-sidebar-hover` `bg-sidebar-active` `border-sidebar-border` | 다크 사이드바 전용 |
| **상태** | `text-success` `bg-success-bg` `border-success-border` (warning / danger / info 동일 구조) | 색만으로 의미 전달 금지, 텍스트 병행 |
| **글자 크기** | `text-xs`(12) `text-sm`(13) `text-base`(14) `text-md`(16) `text-lg`(20) `text-xl`(24) `text-2xl`(30) | 7단만 사용. 채팅 본문은 `text-md` |
| **라운드** | `rounded-md`(8, 컨트롤) / `rounded-xl`(14, 카드·패널·입력창) / `rounded-full`(알약) | 3단 |
| **그림자** | `shadow-sm`(카드) / `shadow-lg`(떠 있는 패널·입력창) | 2단 |
| **전환** | `transition-colors duration-150`, 레이아웃 전환 `duration-200` | reduced-motion은 전역에서 정지 |

- 폰트: Pretendard Variable(`main.tsx`에서 CSS import). `--font-sans` 토큰으로 연결.
- 포커스: 전역 `:focus-visible` 규칙이 브랜드 outline을 그린다. `outline-none`을 써도 키보드 포커스는 보인다. 별도 `focus:` 스타일을 추가하지 않는다.
- Tailwind 스캔 범위는 `src`와 `index.html`로 제한(`source(none)` + `@source`). `.bkit`·`.claude`의 경로가 CSS 변수 후보로 읽혀 빌드가 깨지는 문제를 막는다.

### 공통 컴포넌트 (`src/components/ui/`)

새 화면은 아래 키트를 먼저 쓰고, 없을 때만 직접 그린다.

| 컴포넌트 | 용도 | 핵심 props |
|---------|------|-----------|
| `Button` | 액션 버튼 | `variant` primary/secondary/ghost/danger, `size` sm/md, `isPending`+`pendingText`, `leadingIcon`/`trailingIcon` |
| `IconButton` | 아이콘 전용 버튼 | `aria-label` 필수(타입 강제), `size`, `tone` neutral/danger, `isActive`(aria-pressed) |
| `Input` / `Textarea` | 폼 입력 | `label` `hint` `error`(aria 자동 연결), `size`, Textarea `autoResize` `maxRows` `unstyled` |
| `Tabs` | 밑줄형 탭 | `items[{key,label,count?,disabled?}]` `value` `onChange` `aria-label`. 좌우/Home/End 키 이동 |
| `PageHeader` | 고정 헤더 바 | `title` `subtitle` `leading` `actions` `tabs` `compact`(52px) |
| `Badge` | 상태 배지 | `tone` neutral/success/warning/danger/info/brand, `dot`, `pulse` |
| `EmptyState` | 빈 상태 | `icon`(`iconUnstyled`) `title` `description` `action` `children` |

- `common/LoadingButton`·`common/StatusBadge`는 위 키트의 호환 래퍼다. 새 코드는 `Button`·`Badge`를 직접 쓴다.
- 아이콘은 `lucide-react`, 크기 16(sm)/20(md), `strokeWidth` 1.75. 장식 아이콘은 `aria-hidden`.
- className 합성은 `@/utils/cn` 사용(falsy 제거만).

### 레이아웃 규칙

```
전체 레이아웃: display:flex, height:100% (Tailwind h-screen 대신 인라인 스타일 사용)
사이드바: AppSidebar — w-64(펼침) / w-16(접힘 레일), bg-sidebar. 접기 상태는 layoutStore.isSidebarCollapsed(persist)
          768 이하 최초 진입 시 접힘. 접힌 상태에서도 모든 항목은 aria-label로 이름을 유지
메인 영역: flex-1, bg-surface
콘텐츠 최대 폭: max-w-3xl (768px), mx-auto
채팅 히스토리 패널: 768 이하에서는 overlay(레일 옆, 바깥 클릭·ESC 닫힘)
```

> **주의**: `h-screen`은 전역 CSS 충돌 가능성 있음. 레이아웃 컴포넌트는 `style={{ height: '100%' }}` 인라인 스타일 사용.

### 페이지 래퍼 규칙 (AgentChatLayout 내부 페이지)

`AgentChatLayout`의 `<main>`은 `overflow: hidden`이 적용되어 있다.
따라서 모든 하위 페이지는 **반드시 자체 스크롤 컨테이너**를 제공해야 한다.

#### 패턴 A: 고정 헤더 + 스크롤 바디 (권장)

페이지 상단에 헤더/툴바가 고정되고, 본문만 스크롤되는 패턴.

```tsx
<div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
  {/* 고정 헤더 영역 */}
  <div className="border-b border-zinc-200 px-6 py-4">
    {/* 타이틀, 필터, 액션 버튼 등 */}
  </div>

  {/* 스크롤 가능한 본문 */}
  <div style={{ flex: 1, overflowY: 'auto' }}>
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      {/* 페이지 콘텐츠 */}
    </div>
  </div>
</div>
```

#### 패턴 B: 전체 스크롤 (심플 페이지)

헤더 고정이 불필요한 단순 콘텐츠 페이지.

```tsx
<div className="h-full overflow-y-auto">
  <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
    {/* 페이지 콘텐츠 */}
  </div>
</div>
```

#### 콘텐츠 최대 폭 기준

| 페이지 유형 | max-w | 비고 |
|------------|-------|------|
| 채팅 | `max-w-3xl` (768px) | 대화 흐름에 최적 |
| 폼/설정 | `max-w-3xl` (768px) | 입력 필드 집중 |
| 테이블/카드 그리드 | `max-w-7xl` (1280px) | 데이터 열람에 넓은 영역 |
| 대시보드 | `max-w-7xl` (1280px) | 통계/차트 배치 |

> **금지**: 스크롤 래퍼 없이 `<div className="mx-auto max-w-...">` 단독 사용.
> `AgentChatLayout` 내부에서 콘텐츠가 잘리거나 스크롤이 불가능해진다.

### 컴포넌트 스타일 패턴

#### 아이콘 아바타 (AI)
```tsx
// MessageBubble.tsx의 AssistantAvatar 재사용
<div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-linear-to-br from-brand-600 to-brand-800 shadow-sm">
  <Sparkles className="h-5 w-5 text-white" strokeWidth={1.75} />
</div>
```

#### 유저 메시지 버블
```tsx
<div className="rounded-xl rounded-br-md bg-linear-to-br from-bubble-from to-bubble-to px-5 py-3.5 text-md leading-[1.65] text-white">
  <p className="whitespace-pre-wrap">{content}</p>
</div>
```

#### AI 메시지 (버블 없음, 자유 텍스트)
```tsx
<div className="text-md leading-[1.7] text-fg">
  <MarkdownRenderer content={content} />
</div>
```

#### 버튼
```tsx
<Button>저장</Button>                               // primary md
<Button variant="secondary" size="sm">취소</Button>
<Button isPending={mutation.isPending} pendingText="저장 중…">저장</Button>
<IconButton aria-label="삭제" tone="danger"><Trash2 className="h-4 w-4" /></IconButton>
```

#### 입력창
```tsx
<Input label="이메일" hint="회사 메일" error={errors.email} />
// 채팅처럼 바깥 컨테이너가 테두리를 그릴 때
<div className="rounded-xl border border-border-strong bg-surface shadow-lg focus-within:border-brand-400">
  <Textarea unstyled autoResize maxRows={8} aria-label="메시지 입력" />
</div>
```

#### 카드
```tsx
<div className="rounded-xl border border-border bg-surface p-4 shadow-sm transition-colors duration-150 hover:border-brand-200">
```
translate 애니메이션과 그림자 확대는 쓰지 않는다.

#### 사이드바 항목
`AppSidebar.tsx`의 `SidebarItem`을 쓴다. 활성 `bg-sidebar-active text-sidebar-fg` + 좌측 2px 브랜드 바, 비활성 `text-sidebar-fg-muted hover:bg-sidebar-hover`.

### 타이포그래피

| 용도 | 클래스 |
|------|--------|
| 페이지 타이틀 | `PageHeader`의 `title` (`text-lg font-semibold text-fg`) |
| 빈 상태 제목 | `EmptyState`의 `title` (`text-xl font-semibold text-fg`) |
| 섹션 제목 | `text-base font-semibold text-fg` |
| 본문 (AI 응답) | `text-md leading-[1.7] text-fg` |
| 본문 (유저) | `text-md leading-[1.65] text-white` |
| 보조 레이블 | `text-xs font-medium text-fg-subtle` (대문자·트래킹 eyebrow 금지) |
| 힌트/메타 | `text-xs text-fg-subtle` |
| 사이드바 본문 | `text-sm text-sidebar-fg-muted`, 활성 `text-sidebar-fg` |

### 간격 규칙
- 메시지 간 간격: `gap-8` (32px)
- 메시지 좌우 패딩: `px-4 sm:px-6`
- 메시지 상하 패딩: `py-8`
- 섹션 내부 패딩: `p-4` ~ `p-5`
- 입력창 영역: `px-4 pb-5 sm:px-6`

### 애니메이션
- 버튼 클릭: `active:scale-95` (Button primary 내장)
- 상태 전환: `transition-colors duration-150`, 폭·패널 전환 `duration-200`
- 타이핑 인디케이터: `animate-bounce [animation-delay:-0.3s]` 등
- 스트리밍 커서: `animate-pulse` (인라인 `<span>`)
- 온라인 상태 dot: `<Badge tone="success" dot pulse>`
- `prefers-reduced-motion: reduce`에서는 전역 규칙으로 모든 animation·transition이 정지된다. 개별 처리 불필요
- 비사용자 트리거 애니메이션은 타이핑 인디케이터·스트리밍 커서 2종만 둔다

### Tailwind v4 설정 규칙
- `index.css` 첫 줄: `@import "tailwindcss" source(none);` + `@source "../src"; @source "../index.html";`
- 토큰은 `@theme { ... }` 블록에만 정의
- `vite.config.ts`에 `@tailwindcss/vite` 플러그인 등록 필수
- 글로벌 CSS에서 `html, body, #root { height: 100%; width: 100%; }` 설정 필수
- 글로벌 스타일에서 font-size, color, text-align 등 직접 지정 금지 (Tailwind 클래스 사용). 예외는 `index.css`의 폰트·포커스·reduced-motion 전역 규칙
- 폰트 CSS(`pretendard/...css`)는 `main.tsx`에서 import한다. `index.css`에서 `@import`하면 Tailwind 파서가 unicode-range를 처리하지 못한다
- `npm i`는 vite 8과 `@tailwindcss/vite` peer 범위 충돌로 `--legacy-peer-deps`가 필요하다

## TDD (Test-Driven Development)

### TDD 사이클
모든 새 기능·훅·유틸리티는 **Red → Green → Refactor** 사이클을 따른다.

```
1. Red    — 실패하는 테스트 먼저 작성
2. Green  — 테스트가 통과하는 최소한의 코드 구현
3. Refactor — 테스트를 유지하며 코드 품질 개선
```

### 테스트 도구

| 도구 | 용도 |
|------|------|
| **Vitest** | 단위/통합 테스트 러너 (Vite 네이티브) |
| **React Testing Library** | 컴포넌트 렌더링 및 사용자 상호작용 테스트 |
| **MSW (Mock Service Worker)** | API 응답 모킹 (네트워크 레벨 인터셉트) |
| **@testing-library/user-event** | 실제 사용자 입력 시뮬레이션 |

### 테스트 파일 위치 및 네이밍

```
# 소스 옆 배치 (단위 테스트)
src/hooks/useChat.ts
src/hooks/useChat.test.ts       ← 훅 단위 테스트

src/components/chat/MessageBubble.tsx
src/components/chat/MessageBubble.test.tsx  ← 컴포넌트 테스트

# 통합 테스트
src/__tests__/hooks/useChatIntegration.test.ts
src/__tests__/components/ChatPageIntegration.test.tsx

# MSW 핸들러
src/__tests__/mocks/handlers.ts
src/__tests__/mocks/server.ts
```

### 테스트 작성 규칙

#### 커스텀 훅 테스트 (renderHook)
```typescript
import { renderHook, waitFor } from '@testing-library/react';
import { createWrapper } from '@/__tests__/mocks/wrapper'; // QueryClientProvider 래퍼

it('세션 목록을 조회한다', async () => {
  const { result } = renderHook(() => useChatSessions(), {
    wrapper: createWrapper(),
  });
  await waitFor(() => expect(result.current.isSuccess).toBe(true));
  expect(result.current.data?.items).toHaveLength(2);
});
```

#### 컴포넌트 테스트 (user-event)
```typescript
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

it('전송 버튼 클릭 시 onSubmit이 호출된다', async () => {
  const onSubmit = vi.fn();
  render(<ChatInput onSubmit={onSubmit} />);
  await userEvent.type(screen.getByRole('textbox'), '안녕하세요');
  await userEvent.click(screen.getByRole('button', { name: /전송/ }));
  expect(onSubmit).toHaveBeenCalledWith('안녕하세요');
});
```

#### MSW 핸들러 패턴
```typescript
// src/__tests__/mocks/handlers.ts
import { http, HttpResponse } from 'msw';
import { API_ENDPOINTS } from '@/constants/api';

export const handlers = [
  http.get(`*${API_ENDPOINTS.CHAT_SESSIONS}`, () =>
    HttpResponse.json({ items: mockSessions, total: 2 })
  ),
];
```

### 테스트 대상 우선순위

| 우선순위 | 대상 | 이유 |
|---------|------|------|
| **P1** | 커스텀 훅 (`useChat`, `useDocuments`, `useAgent`) | 비즈니스 로직 집중 |
| **P1** | 유틸리티 함수 (`formatters`, `streamParser`) | 순수 함수 → 테스트 용이 |
| **P1** | Zustand 슬라이스 팩토리 (`commonSlices`) | 상태 변이 검증 |
| **P2** | 컴포넌트 (`ChatInput`, `MessageBubble`) | 사용자 상호작용 |
| **P3** | 페이지 통합 (`ChatPage`) | E2E에 가까운 통합 |

### 테스트 커버리지 목표
- 훅/유틸리티: **80% 이상**
- 컴포넌트: **60% 이상**
- `npm run coverage`로 확인

## 개발 규칙
- 컴포넌트는 단일 책임 원칙 준수 (200줄 초과 시 분리 검토)
- 커스텀 훅으로 비즈니스 로직 분리
- 절대 경로 import 사용 (`@/components/...`)
- 환경변수는 `VITE_` 접두사 사용, `.env.local`에 관리
- 비밀키/API 키는 절대 프론트엔드 코드에 포함 금지
- **새 기능 구현 시 테스트 파일 함께 작성** (TDD 사이클 준수)

## 환경변수 (.env.local)
```
VITE_API_BASE_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000
```

## 주요 스크립트
```bash
npm run dev          # 개발 서버 실행
npm run build        # 프로덕션 빌드
npm run lint         # ESLint 검사
npm run type-check   # TypeScript 타입 검사
npm run test         # 테스트 실행 (watch 모드)
npm run test:run     # 테스트 1회 실행 (CI용)
npm run coverage     # 커버리지 리포트 생성
```

---

## 백엔드 API 참조

> 백엔드와 프론트엔드는 같은 저장소 내에 위치합니다.

- **백엔드 라우터 디렉토리**: `../src/api/routes/`
- **백엔드 task 스펙**: `../src/claude/task/`
- **API 기본 URL**: `http://localhost:8000` (`.env.local`의 `VITE_API_BASE_URL`)

### 구현된 백엔드 API 목록

| Task ID | 엔드포인트 | 설명 |
|---------|-----------|------|
| CONV-001 | `POST /api/v1/conversation/chat` | 멀티턴 대화 (user_id + session_id 기반) |
| RETRIEVAL-001 | `POST /api/v1/retrieval/search` | RAG 문서 검색 |
| INGEST-001 | `POST /api/v1/ingest/pdf` | PDF 파싱+청킹+벡터 저장 |
| RAG-001 | `POST /api/v1/rag/chat` | ReAct RAG Agent (BM25+Vector 하이브리드) |
| AGENT-004 | `POST /api/v1/agents` | Custom Agent Builder |
| AGENT-005 | `POST /api/v2/agents` | Middleware Agent Builder |
| AGENT-006 | `POST /api/v3/agents/auto` | 자연어 기반 자동 에이전트 빌더 |
| MCP-REG-001 | `POST /api/v1/mcp-registry` | MCP Tool Registry CRUD |

### API 연동 시 참조 순서
1. `../src/api/routes/{feature}_router.py` — 실제 요청/응답 스키마 확인
2. `../src/claude/task/task-{feature}.md` — 설계 스펙 확인
3. `src/constants/api.ts` — 엔드포인트 상수 추가/수정
4. `src/types/{feature}.ts` — 백엔드 스키마와 타입 동기화
5. `src/services/{feature}Service.ts` — API 호출 메서드 구현
6. `src/hooks/use{Feature}.ts` — TanStack Query 훅 구현

---

## 작업 현황 참조

> 태스크 목록 및 진행 상황은 **[TASK.md](./TASK.md)** 에서 관리합니다.

## Task Files Reference

모든 task.md 파일은 다음 규칙을 따른다:

| Task ID | 파일명 | 설명 |
|---------|--------|------|
| BASE-001 | src/claude/task/task-base.md | 프로젝트 기반 설정 (완료) |
| CHAT-001 | src/claude/task/task-chat.md | 채팅 기능 (UI 완료 / API 연동 예정) |
| AGENT-001 | src/claude/task/task-agent.md | AI Agent 기능 |
| RAG-001 | src/claude/task/task-rag.md | 문서(RAG) 기능 |
| MISC-001 | src/claude/task/task-misc.md | 기타 (라우팅, SEO, 반응형 등) |
| WS-001 | src/claude/task/task-websocket.md | 공통 WebSocket 커스텀 훅 (완료) |
| ZUSTAND-001 | src/claude/task/task-zustand.md | Zustand 공통 슬라이스 팩토리 (완료) |
| TQ-001 | src/claude/task/task-tanstack-query.md | TanStack Query 공통 구성 (완료) |
| EVAL-001 | src/claude/task/task-eval-dataset.md | 평가 데이터셋 추출 페이지 (Mock 완료 / API 연동 예정) |
| TOOL-001 | docs/archive/2026-08/utility-page/utility-page.plan.md | 유틸리티 카탈로그 페이지 — /tool-connection, 도구·모델·스킬 실연동 (구현 완료, Match 94.4%) |
| WORKFLOW-001 | src/claude/task/task-workflow-designer.md | 워크플로우 설계 페이지 (Mock 완료 / API 연동 예정) |
| AGENT-001 | src/claude/task/task-agent-builder.md | 에이전트 만들기 페이지 (Mock 완료 / API 연동 예정) |
| TOOL-ADMIN-001 | src/claude/task/task-tool-admin.md | 도구 관리 어드민 페이지 (Mock 완료 / API 연동 예정) |
| AUTH-001 | docs/01-plan/features/auth.plan.md | JWT 인증 + 관리자 승인 흐름 (Design 완료 / 구현 예정) |
| DOC-DEL-001 | docs/01-plan/features/document-delete-api.plan.md | 컬렉션 문서 삭제 API 연동 (Design 완료 / 구현 예정) |
| AGENT-STORE-001 | docs/01-plan/features/agent-store.plan.md | 에이전트 스토어 마켓플레이스 (구현 완료) |
| FIX-COMPOSER-001 | docs/archive/2026-07/fix-agent-composer/fix-agent-composer.plan.md | Fix 에이전트 탭 — 채팅→compose(current_config/history 확장)→초안 카드→폼 셋팅, MCP 저장 필터 제거 (구현 완료, Match 93%) |
| FIX-SLOT-ADD-001 | docs/archive/2026-07/doc-extractor-slot-add-fix/doc-extractor-slot-add-fix.plan.md | 문서추출기 슬롯 직접 추가 무반응 수정 — 원시 includes → 정규화 매칭(htmlContainsText) + 버튼 인접 인라인 피드백 + 공백 무시 폴백 매칭(layout 미리보기 하이라이트 대응) (구현 완료, Match 98%) |
| LLM-REGISTER-001 | docs/archive/2026-07/llm-register/llm-register.plan.md | LLM 모델 관리 어드민 페이지 — /admin/llm-models (등록/수정/가격변경/비활성화 + 뮤테이션 훅 4종, ADMIN_NAV 7번째 항목) (구현 완료, Match 100%) |

### 완료된 주요 파일 참조

| 분류 | 파일 | 설명 |
|------|------|------|
| **타입** | `src/types/chat.ts` | Message, ChatSession, SourceChunk |
| **타입** | `src/types/agent.ts` | AgentRun, AgentStep, AgentStatus |
| **타입** | `src/types/rag.ts` | Document, RetrievedChunk |
| **타입** | `src/types/api.ts` | ApiResponse, StreamEvent |
| **상수** | `src/constants/api.ts` | API_ENDPOINTS 전체 목록 |
| **상수** | `src/constants/agent.ts` | Agent 상태 레이블 |
| **서비스** | `src/services/api/client.ts` | axios 인스턴스 — 공개 엔드포인트 전용 (인터셉터 없음) |
| **서비스** | `src/services/api/authClient.ts` | axios 인스턴스 — 인증 전용 (Bearer 토큰 주입 + 자동 갱신) |
| **서비스** | `src/services/chatService.ts` | 채팅 API 호출 |
| **서비스** | `src/services/agentService.ts` | Agent API 호출 |
| **서비스** | `src/services/ragService.ts` | 문서 업로드/검색 API |
| **스토어** | `src/store/commonSlices.ts` | 공통 슬라이스 팩토리 (LoadingSlice, ListSlice, SelectionSlice) |
| **스토어** | `src/store/chatStore.ts` | 채팅 전역 상태 (스트리밍 포함, LoadingSlice 적용) |
| **스토어** | `src/store/agentStore.ts` | Agent 실행 상태 (LoadingSlice 적용) |
| **스토어** | `src/store/documentStore.ts` | 문서 목록 상태 (LoadingSlice + ListSlice + SelectionSlice 적용) |
| **훅** | `src/hooks/useStream.ts` | SSE 스트리밍 처리 |
| **훅** | `src/hooks/useWebSocket.ts` | WebSocket 공통 훅 (연결/재연결/송수신/상태) |
| **훅** | `src/hooks/useChat.ts` | 채팅 세션 목록 조회, 메시지 전송 (TanStack Query) |
| **훅** | `src/hooks/useDocuments.ts` | 문서 목록 조회, 업로드, 삭제 (TanStack Query) |
| **훅** | `src/hooks/useAgent.ts` | Agent 실행 시작, 상태 폴링 (TanStack Query) |
| **라이브러리** | `src/lib/queryClient.ts` | QueryClient 싱글톤 (공통 defaultOptions) |
| **라이브러리** | `src/lib/queryKeys.ts` | 쿼리 키 팩토리 (중앙 집중 관리) |
| **유틸** | `src/utils/formatters.ts` | 날짜/파일크기 포맷 |
| **유틸** | `src/utils/streamParser.ts` | SSE 파싱, Fetch Stream |
| **UI** | `src/pages/ChatPage/index.tsx` | 채팅 메인 페이지 (Mock 데이터 포함) |
| **UI** | `src/components/layout/Sidebar.tsx` | 세션 목록 사이드바 |
| **UI** | `src/components/layout/ChatHeader.tsx` | 채팅 헤더 |
| **UI** | `src/components/chat/MessageBubble.tsx` | 메시지 말풍선 |
| **UI** | `src/components/chat/ChatInput.tsx` | 입력창 (RAG 토글 포함) |
| **UI** | `src/components/chat/MessageList.tsx` | 메시지 목록 + 빈 상태 |
| **UI** | `src/components/chat/TypingIndicator.tsx` | 응답 대기 애니메이션 |
| **UI** | `src/components/chat/SourceCitation.tsx` | RAG 출처 표시 칩 |
| **타입** | `src/types/eval.ts` | EvalDatasetItem, EvalDatasetResponse |
| **서비스** | `src/services/evalService.ts` | 평가 데이터셋 추출 API (multipart/form-data) |
| **UI** | `src/pages/EvalDatasetPage/index.tsx` | 평가 데이터셋 추출 페이지 (드래그앤드롭, 스피너, 테이블) |
| **UI** | `src/components/layout/TopNav.tsx` | 상단 메뉴바 (드롭다운 네비게이션) |
| **UI** | `src/pages/AgentBuilderPage/index.tsx` | 에이전트 만들기 페이지 (예정 기능 안내) |
| **UI** | `src/pages/UtilityPage/index.tsx` | 유틸리티 카탈로그 페이지 (탭 4종 + 검색 + 유형 필터, 도구·모델·스킬 실데이터) |
| **타입** | `src/types/workflow.ts` | Workflow, WorkflowStep, WorkflowStepType, WORKFLOW_STEP_TYPE |
| **UI** | `src/pages/WorkflowDesignerPage/index.tsx` | 워크플로우 설계 페이지 (카드 그리드 + 플로우 시각화 + 상세 패널) |
| **타입** | `src/types/toolAdmin.ts` | AdminTool, ToolSchemaParam, ToolEndpoint, ToolParamType, HttpMethod, CRUD Request/Response |
| **서비스** | `src/services/toolAdminService.ts` | 도구 관리 CRUD API (getTools, createTool, updateTool, deleteTool) |
| **UI** | `src/pages/ToolAdminPage/index.tsx` | 도구 관리 어드민 페이지 (테이블 + 추가/수정 모달 + 삭제 확인) |
| **타입** | `src/types/auth.ts` | User, UserStatus, UserRole, AuthTokenResponse, PendingUser |
| **스토어** | `src/store/authStore.ts` | 인증 전역 상태 (accessToken 메모리 / refreshToken persist) |
| **훅** | `src/hooks/useAuth.ts` | useLogin, useLogout, useRegister, useMe, useInitAuth |
| **컴포넌트** | `src/components/common/ProtectedRoute.tsx` | 비인증 시 /login 리다이렉트 |
| **컴포넌트** | `src/components/common/AdminRoute.tsx` | 비admin 시 / 리다이렉트 |
| **컴포넌트** | `src/components/common/ConfirmDialog.tsx` | 공통 확인 다이얼로그 (variant: danger/warning/info) |
| **컴포넌트** | `src/components/common/LoadingButton.tsx` | 공통 대기 버튼 — isPending 필수 prop, 대기 중 disable+스피너+대체 문구 (뮤테이션 버튼은 이 컴포넌트 사용 권장) |
| **타입** | `src/types/agentStore.ts` | StoreAgentSummary, AgentDetail, SubscribeResponse, ForkAgentResponse 등 |
| **서비스** | `src/services/agentStoreService.ts` | 에이전트 스토어 API (목록, 상세, 구독, 포크, 등록) |
| **훅** | `src/hooks/useAgentStore.ts` | useAgentList, useAgentDetail, useMyAgents, useSubscribeAgent, useForkAgent 등 |
| **UI** | `src/pages/AgentStorePage/index.tsx` | 에이전트 스토어 페이지 (카드 그리드 + 검색 + 탭 + 페이지네이션) |
| **컴포넌트** | `src/components/agent-store/AgentStoreCard.tsx` | 에이전트 카드 (아바타, 구독/포크 버튼) |
| **컴포넌트** | `src/components/agent-store/AgentStoreTab.tsx` | 탭 네비게이션 (전체공개/부서별/내에이전트) |
| **컴포넌트** | `src/components/agent-store/AgentDetailModal.tsx` | 에이전트 상세 팝업 (프롬프트, 도구, 통계) |
| **컴포넌트** | `src/components/agent-store/PublishAgentModal.tsx` | 내 에이전트 공개 등록 모달 |

# React UI Redesign Rules

## Objective
Redesign the existing React UI to achieve a
modern, consistent, production-grade appearance.

## Existing Architecture
- Preserve the current React version and build system.
- Preserve React Router v6 routing.
- Preserve React Query v5 data-fetching behavior.
- Preserve Zustand state management and persist keys.
- Preserve API contracts and authentication flows.
- Follow the existing styling approach.

## Design Workflow
1. Analyze existing UI before modifying code.
2. Use UI UX Pro Max to define design tokens.
3. Use Frontend Design to improve visual quality.
4. Reuse existing components whenever possible.
5. Modify only one target screen at a time.
6. Validate changes using Chrome DevTools MCP.
7. Review accessibility and UX guidelines.

## Design Principles
- Modern SaaS / enterprise dashboard aesthetic.
- Consistent typography, spacing and visual hierarchy.
- Use CSS variables for shared design tokens.
- Support desktop and mobile layouts.
- Include hover, focus, disabled and loading states.
- Avoid excessive gradients, animations and shadows.
- Respect prefers-reduced-motion.

## Restrictions
- Do not migrate frameworks or build tools.
- Do not replace existing routing or state libraries.
- Do not modify API request/response contracts.
- Do not change business logic.
- Do not add large dependencies without approval.
- Do not make unnecessary global CSS changes.
- Do not modify unrelated screens.
- Preserve existing user-facing behavior.

## Verification
- Run existing lint, build and tests.
- Compare before/after screenshots.
- Check viewport widths 375, 768 and 1440.
- Check console errors and network failures.
- Verify navigation, forms and persistent state.
- Report changed files and remaining issues.