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

### 색상 토큰

| 역할 | 값 | 사용처 |
|------|-----|--------|
| **Primary** | `linear-gradient(135deg, #7c3aed, #4f46e5)` | 아바타, 버튼 활성, 포인트 색 |
| **Primary Text** | `text-violet-500` / `text-violet-600` | 강조 텍스트, 레이블, RAG 점수 |
| **User Bubble** | `linear-gradient(135deg, #2d2d2d, #1a1a1a)` | 유저 메시지 배경 |
| **Surface** | `#fff` | 메인 콘텐츠 영역 배경 |
| **Sidebar BG** | `#0f0f0f` | 사이드바 배경 |
| **Border** | `border-zinc-200` / `border-zinc-300` | 기본 선 |
| **Muted Text** | `text-zinc-400` / `text-zinc-500` | 보조 텍스트, 힌트 |
| **Destructive** | `hover:bg-red-50 hover:text-red-500` | 삭제 버튼 hover |

### 레이아웃 규칙

```
전체 레이아웃: display:flex, height:100% (Tailwind h-screen 대신 인라인 스타일 사용)
사이드바: w-64, bg-[#0f0f0f]
메인 영역: flex-1, bg-white
콘텐츠 최대 폭: max-w-3xl (768px), mx-auto
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
<div
  className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl shadow-md"
  style={{ background: 'linear-gradient(135deg, #7c3aed 0%, #4f46e5 100%)' }}
>
  <svg className="h-5 w-5 text-white" ... />
</div>
```

#### 유저 메시지 버블
```tsx
<div
  className="rounded-2xl rounded-br-sm px-5 py-3.5 text-[15px] leading-[1.65] text-white"
  style={{ background: 'linear-gradient(135deg, #2d2d2d 0%, #1a1a1a 100%)' }}
>
  <p className="whitespace-pre-wrap">{content}</p>
</div>
```

#### AI 메시지 (버블 없음, 자유 텍스트)
```tsx
<div className="text-[15px] leading-[1.8] text-zinc-800">
  <p className="whitespace-pre-wrap">{content}</p>
</div>
```

#### 기본 버튼 (Primary)
```tsx
<button className="flex items-center justify-center rounded-xl bg-violet-600 px-4 py-2.5 text-[13.5px] font-medium text-white shadow-sm hover:bg-violet-700 active:scale-95 transition-all">
```

#### 기본 버튼 (Secondary/Ghost)
```tsx
<button className="flex items-center rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-2.5 text-[13.5px] font-medium text-zinc-600 hover:border-zinc-300 hover:bg-zinc-100 transition-all">
```

#### 입력창 (Input/Textarea)
```tsx
<div className="overflow-hidden rounded-2xl border border-zinc-300 bg-white shadow-xl shadow-zinc-200/50 transition-all focus-within:border-violet-400 focus-within:shadow-violet-100/60">
  <textarea className="block w-full resize-none bg-transparent text-[15px] leading-relaxed text-zinc-900 placeholder-zinc-400 outline-none" />
</div>
```

#### 카드 (호버 lift 효과)
```tsx
<div className="group relative overflow-hidden rounded-2xl border border-zinc-200 bg-white p-4 shadow-sm transition-all duration-200 hover:-translate-y-1 hover:border-transparent hover:shadow-xl">
```

#### 사이드바 내 세션 아이템
```tsx
// 활성 상태
<button className="bg-white/[0.12] text-white rounded-xl px-4 py-3">
// 비활성 상태
<button className="text-white/45 hover:bg-white/[0.07] hover:text-white/80 rounded-xl px-4 py-3">
```

### 타이포그래피

| 용도 | 클래스 |
|------|--------|
| 페이지 타이틀 | `text-3xl font-bold tracking-tight text-zinc-900` |
| 섹션 제목 | `text-[15px] font-semibold text-zinc-900` |
| 본문 (AI 응답) | `text-[15px] leading-[1.8] text-zinc-800` |
| 본문 (유저) | `text-[15px] leading-[1.65] text-white` |
| 보조 레이블 | `text-[11.5px] font-semibold uppercase tracking-widest text-violet-500` |
| 힌트/메타 | `text-[12px] text-zinc-400` |
| 사이드바 본문 | `text-[13.5px] font-medium text-white` |

### 간격 규칙
- 메시지 간 간격: `gap-8` (32px)
- 메시지 좌우 패딩: `px-4 sm:px-6`
- 메시지 상하 패딩: `py-8`
- 섹션 내부 패딩: `p-4` ~ `p-5`
- 입력창 영역: `px-4 pb-5 sm:px-6`

### 애니메이션
- 버튼 클릭: `active:scale-95`
- 카드 hover: `hover:-translate-y-1`
- 상태 전환: `transition-all duration-150` ~ `duration-200`
- 타이핑 인디케이터: `animate-bounce [animation-delay:-0.3s]` 등
- 스트리밍 커서: `animate-pulse` (인라인 `<span>`)
- 온라인 상태 dot: `animate-pulse bg-emerald-400`

### Tailwind v4 설정 규칙
- `index.css` 첫 줄: `@import "tailwindcss";`
- `vite.config.ts`에 `@tailwindcss/vite` 플러그인 등록 필수
- 글로벌 CSS에서 `html, body, #root { height: 100%; width: 100%; }` 설정 필수
- 글로벌 스타일에서 font-size, color, text-align 등 직접 지정 금지 (Tailwind 클래스 사용)

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
| TOOL-001 | src/claude/task/task-tool-connection.md | 도구 연결 페이지 (Mock 완료 / API 연동 예정) |
| WORKFLOW-001 | src/claude/task/task-workflow-designer.md | 워크플로우 설계 페이지 (Mock 완료 / API 연동 예정) |
| AGENT-001 | src/claude/task/task-agent-builder.md | 에이전트 만들기 페이지 (Mock 완료 / API 연동 예정) |
| TOOL-ADMIN-001 | src/claude/task/task-tool-admin.md | 도구 관리 어드민 페이지 (Mock 완료 / API 연동 예정) |
| AUTH-001 | docs/01-plan/features/auth.plan.md | JWT 인증 + 관리자 승인 흐름 (Design 완료 / 구현 예정) |
| DOC-DEL-001 | docs/01-plan/features/document-delete-api.plan.md | 컬렉션 문서 삭제 API 연동 (Design 완료 / 구현 예정) |
| AGENT-STORE-001 | docs/01-plan/features/agent-store.plan.md | 에이전트 스토어 마켓플레이스 (구현 완료) |

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
| **타입** | `src/types/tool.ts` | Tool, ToolCategory, TOOL_CATEGORY 상수 |
| **서비스** | `src/services/toolService.ts` | 도구 목록 조회 및 토글 API |
| **UI** | `src/components/layout/TopNav.tsx` | 상단 메뉴바 (드롭다운 네비게이션) |
| **UI** | `src/pages/AgentBuilderPage/index.tsx` | 에이전트 만들기 페이지 (예정 기능 안내) |
| **UI** | `src/pages/ToolConnectionPage/index.tsx` | 도구 연결 페이지 (카드 그리드 + 토글 + 필터) |
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
| **타입** | `src/types/agentStore.ts` | StoreAgentSummary, AgentDetail, SubscribeResponse, ForkAgentResponse 등 |
| **서비스** | `src/services/agentStoreService.ts` | 에이전트 스토어 API (목록, 상세, 구독, 포크, 등록) |
| **훅** | `src/hooks/useAgentStore.ts` | useAgentList, useAgentDetail, useMyAgents, useSubscribeAgent, useForkAgent 등 |
| **UI** | `src/pages/AgentStorePage/index.tsx` | 에이전트 스토어 페이지 (카드 그리드 + 검색 + 탭 + 페이지네이션) |
| **컴포넌트** | `src/components/agent-store/AgentStoreCard.tsx` | 에이전트 카드 (아바타, 구독/포크 버튼) |
| **컴포넌트** | `src/components/agent-store/AgentStoreTab.tsx` | 탭 네비게이션 (전체공개/부서별/내에이전트) |
| **컴포넌트** | `src/components/agent-store/AgentDetailModal.tsx` | 에이전트 상세 팝업 (프롬프트, 도구, 통계) |
| **컴포넌트** | `src/components/agent-store/PublishAgentModal.tsx` | 내 에이전트 공개 등록 모달 |
