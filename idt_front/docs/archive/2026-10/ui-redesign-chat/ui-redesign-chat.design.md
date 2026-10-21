---
template: design
version: 1.3
feature: ui-redesign-chat
---

# ui-redesign-chat Design Document

> **Summary**: Tailwind v4 `@theme` 디자인 토큰 + Pretendard + `components/ui` 키트 7종을 만들고, 채팅 화면(헤더·빈 상태·메시지·입력창·히스토리 패널·사이드바 접기)을 그 키트로 재구성한다. 로직 훅·서비스·API 계약은 변경하지 않는다.
>
> **Project**: idt_front (sangplusbot)
> **Version**: 0.0.0
> **Author**: 배상규
> **Date**: 2026-10-20
> **Status**: Draft
> **Planning Doc**: [ui-redesign-chat.plan.md](ui-redesign-chat.plan.md)

### Pipeline References

| Phase | Document | Status |
|-------|----------|--------|
| Phase 2 | Coding Conventions | `idt_front/CLAUDE.md` 사용 (별도 문서 없음) |
| Phase 3 | Mockup | 분석 스크린샷 12장 (세션 임시 경로, Plan §1.3) |
| Phase 4 | API Spec | N/A (API 변경 없음) |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 디자인 토큰과 공통 컴포넌트가 없어 화면마다 스타일을 손으로 재작성하고, 결과가 화면마다 다르다 |
| **WHO** | 1차: 채팅 화면을 쓰는 전 사용자(P1 질문자, P2 KB 운영자). 2차: 이후 화면을 리디자인할 개발자 |
| **RISK** | 채팅 화면의 스트리밍·첨부·도구 프리뷰 로직을 건드려 기능 회귀가 생기는 것. 완화: 로직 파일은 import만 유지하고 표현 레이어만 교체, 기존 11개 chat 테스트를 회귀 기준으로 사용 |
| **SUCCESS** | 채팅 화면 전역에서 임의 px 글자 크기 0건, 1차 버튼은 Button 컴포넌트만 사용, 포커스 링 가시, 보조 텍스트 대비 4.5:1 이상, 1440/768 스크린샷에서 겹침·세로 줄바꿈 없음, 기존 vitest 통과 |
| **SCOPE** | Phase 1 토큰·폰트·공통 컴포넌트 키트 → Phase 2 채팅 화면 적용(사이드바 접기 포함) → (후속 사이클) 셸 통합, 관리자 테이블 화면 |

---

## 1. Overview

### 1.1 Design Goals

1. 토큰을 한 곳(`src/index.css` `@theme`)에 정의하고 Tailwind 유틸리티 클래스로 소비한다. 컴포넌트에 hex·임의 px가 남지 않는다.
2. 공통 컴포넌트는 "variant 맵 + className 합성"만으로 구현한다. 추가 라이브러리 없음.
3. 기존 공개 API(컴포넌트 props, 훅, 스토어 필드, persist 키)를 유지해 소비처를 건드리지 않는다.
4. 접근성 기본기를 컴포넌트 안에 넣는다. 포커스 링, aria-label, 색 외 수단, reduced-motion.
5. 채팅 화면은 1440과 768에서 같은 규칙으로 렌더링되고, 사이드바는 접힌다.

### 1.2 Design Principles

- **표현만 교체**: `chat/*`, `layout/*`의 JSX 구조와 className만 바꾼다. 상태·이벤트·훅 호출은 그대로 둔다.
- **토큰 우선**: 색·글자 크기·라운드·그림자는 토큰 클래스만. 예외는 코드 리뷰에서 거부한다.
- **호환 래퍼**: `LoadingButton`·`StatusBadge`는 기존 props를 받아 새 컴포넌트로 위임한다.
- **한 요소 한 역할**: Button은 액션, IconButton은 아이콘 액션, Badge는 상태 표시. 역할을 섞지 않는다.
- **A안 유지**: violet + zinc + 다크 사이드바. 브랜드 인상은 바꾸지 않고 정돈한다.

---

## 2. Architecture Options

### 2.0 Architecture Comparison

| Criteria | Option A: Minimal | Option B: Clean | Option C: Pragmatic |
|----------|:-:|:-:|:-:|
| **Approach** | 토큰만 추가, 채팅 className 직접 교체, Button 1종 | ui 7종 + cva variant 시스템 + Sidebar 4분할 + 래퍼 삭제·사용처 35파일 이전 | ui 7종(단순 variant 맵) + 래퍼 호환 + AppSidebar 내부 접기 |
| **New Files** | 3 | 24 | 17 |
| **Modified Files** | 14 | 50 | 17 |
| **Complexity** | Low | High | Medium |
| **Maintainability** | Low (재사용 키트 없음) | High | High |
| **Effort** | Low | High | Medium |
| **Risk** | Low | Medium (범위가 채팅을 넘음) | Low |
| **Dependencies** | 0 | cva 1 | 0 (pretendard만) |
| **Recommendation** | 핫픽스 | 장기 리팩터링 | **기본 선택** |

**Selected**: Option C — **Rationale**: Plan의 범위(토큰 + 키트 + 채팅 1화면)와 정확히 일치한다. 키트는 후속 화면에서 재사용되고, 래퍼 호환으로 다른 35개 파일은 손대지 않는다. 사용자 선택(2026-10-20).

### 2.1 Component Diagram

```
src/index.css (@theme 토큰, 폰트, 전역 focus/motion 규칙)
        │ Tailwind 유틸리티 클래스 (bg-brand-600, text-sm, rounded-xl ...)
        ▼
src/components/ui/           ← 신설 키트 (표현 전용, 상태 없음)
  Button  IconButton  Input  Textarea  Tabs  PageHeader  Badge  EmptyState
        │ import
        ├──────────────────────────────┐
        ▼                              ▼
src/components/common/           src/components/layout/      src/components/chat/
  LoadingButton → Button 래퍼      AppSidebar (접기 레일)        MessageList(EmptyState)
  StatusBadge   → Badge 래퍼       AgentChatLayout             MessageBubble, ChatInput
                                   ChatHeader(PageHeader)      SourceCitation, TypingIndicator
                                   ChatHistoryPanel            MessageFeedback, ToolPreviewPanel
                                           │                   ExcelPreviewModal, MarkdownRenderer
                                           ▼
                                 src/store/layoutStore.ts (+ isSidebarCollapsed)
                                           ▲
                                 src/pages/ChatPage/index.tsx (래퍼 구조만)
```

훅(`useChatStream`, `useAgentRunStream`, `useAgentSessionMessages`), 서비스, 쿼리 키는 이 그림 밖에 있고 변경하지 않는다.

### 2.2 Data Flow

```
사용자 입력 ─▶ ChatInput(표현) ─▶ onSend (기존) ─▶ useChatStream / useAgentRunStream (기존) ─▶ MessageList(표현)
사이드바 토글 ─▶ AppSidebar 토글 버튼 ─▶ layoutStore.toggleSidebar ─▶ persist('layout-preferences') ─▶ AppSidebar 폭 64/256
뷰포트 ≤ 768 최초 진입 ─▶ AgentChatLayout matchMedia ─▶ setSidebarCollapsed(true) (persist 값이 없을 때만)
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `components/ui/*` | `index.css` 토큰, `types/ui.ts`, `lucide-react` | 표현 키트 |
| `common/LoadingButton` | `ui/Button` | 호환 래퍼 |
| `common/StatusBadge` | `ui/Badge`, `types/progress` | 호환 래퍼 |
| `layout/AppSidebar` | `layoutStore`, 내부 `SidebarItem`(다크 표면 전용 버튼) | 접기 레일. ui/IconButton의 tone은 밝은 표면 기준이라 쓰지 않는다 |
| `layout/ChatHeader` | `ui/PageHeader`, `ui/IconButton`, `ui/Badge` | 헤더 규격화 |
| `chat/MessageList` | `ui/EmptyState` | 빈 상태 |
| `chat/ChatInput` | `ui/Textarea`, `ui/Button`, `ui/IconButton` | 입력창 |
| `package.json` | `pretendard` (신규) | 폰트 |

---

## 3. Data Model

### 3.1 Entity Definition

서버 데이터 모델 변경 없음. 클라이언트 타입만 추가한다.

```typescript
// src/types/ui.ts  (as const 객체 + 타입 추출. 컴포넌트 파일에서 런타임 상수 export 금지 규칙 준수)
export const BUTTON_VARIANT = { primary: 'primary', secondary: 'secondary', ghost: 'ghost', danger: 'danger' } as const;
export type ButtonVariant = (typeof BUTTON_VARIANT)[keyof typeof BUTTON_VARIANT];

export const CONTROL_SIZE = { sm: 'sm', md: 'md' } as const;
export type ControlSize = (typeof CONTROL_SIZE)[keyof typeof CONTROL_SIZE];

export const BADGE_TONE = { neutral: 'neutral', success: 'success', warning: 'warning', danger: 'danger', info: 'info', brand: 'brand' } as const;
export type BadgeTone = (typeof BADGE_TONE)[keyof typeof BADGE_TONE];

export interface TabItem { key: string; label: string; count?: number; disabled?: boolean }
```

```typescript
// src/store/layoutStore.ts (추가 필드)
interface LayoutState {
  isChatPanelOpen: boolean;        // 기존
  selectedAgentId: string | null;  // 기존
  isSidebarCollapsed: boolean;     // 신규, 기본 false
  toggleChatPanel: () => void;     // 기존
  setChatPanelOpen: (open: boolean) => void; // 기존
  selectAgent: (id: string | null) => void;  // 기존
  toggleSidebar: () => void;       // 신규
  setSidebarCollapsed: (collapsed: boolean) => void; // 신규
}
// persist name 'layout-preferences' 유지. 기존 저장값에 필드가 없으면 Zustand merge로 기본값 false 적용.
```

### 3.2 Entity Relationships

해당 없음.

### 3.3 Database Schema

해당 없음.

---

## 4. API Specification

API 변경 없음. 채팅이 쓰는 기존 엔드포인트·WebSocket·React Query 키는 그대로 사용한다. Gap 분석 시 Contract 축은 "변경 없음 확인"으로 평가한다.

| 항목 | 상태 |
|---|---|
| `POST /api/v1/...chat`, `/ws/agent/{room}` | 변경 없음 |
| `queryKeys.chat.*`, `queryKeys.auth.*` | 변경 없음 |
| `authStore`, `chatPreferencesStore` | 변경 없음 |
| `layoutStore` | 필드 1개(`isSidebarCollapsed`)·액션 2개·헬퍼 1개(`hasPersistedSidebarPreference`) 추가, persist 키 유지 |

---

## 5. UI/UX Design

### 5.0 Design Tokens (`src/index.css`)

```css
@import "tailwindcss";
@import "pretendard/dist/web/variable/pretendardvariable.css";

@theme {
  /* 폰트 */
  --font-sans: "Pretendard Variable", Pretendard, ui-sans-serif, system-ui, "Apple SD Gothic Neo", "Malgun Gothic", sans-serif;
  --font-mono: ui-monospace, "Cascadia Mono", "D2Coding", Consolas, monospace;

  /* 브랜드 (violet 유지) */
  --color-brand-50:  #f5f3ff;
  --color-brand-100: #ede9fe;
  --color-brand-200: #ddd6fe;
  --color-brand-400: #a78bfa;
  --color-brand-500: #8b5cf6;
  --color-brand-600: #7c3aed;   /* Primary */
  --color-brand-700: #6d28d9;
  --color-brand-800: #4f46e5;   /* gradient 종점 (기존 indigo-600) */

  /* 표면·텍스트·선 (zinc 기반, 의미 이름) */
  --color-surface:          #ffffff;
  --color-surface-muted:    #fafafa;   /* zinc-50 */
  --color-surface-sunken:   #f4f4f5;   /* zinc-100 */
  --color-border:           #e4e4e7;   /* zinc-200 */
  --color-border-strong:    #d4d4d8;   /* zinc-300 */
  --color-fg:               #18181b;   /* zinc-900 */
  --color-fg-secondary:     #3f3f46;   /* zinc-700 */
  --color-fg-muted:         #52525b;   /* zinc-600, white 위 7.0:1 */
  --color-fg-subtle:        #71717a;   /* zinc-500, white 위 4.6:1 — 힌트 텍스트 하한 */

  /* 사이드바 (다크) */
  --color-sidebar:          #0f0f0f;
  --color-sidebar-fg:       #ffffff;
  --color-sidebar-fg-muted: rgba(255,255,255,0.62); /* #0f0f0f 위 ≥ 7:1 */
  --color-sidebar-hover:    rgba(255,255,255,0.07);
  --color-sidebar-active:   rgba(255,255,255,0.12);
  --color-sidebar-border:   rgba(255,255,255,0.08);

  /* 유저 버블 */
  --color-bubble-from: #2d2d2d;
  --color-bubble-to:   #1a1a1a;

  /* 상태 */
  --color-success: #059669;  --color-success-bg: #ecfdf5;  --color-success-border: #a7f3d0;
  --color-warning: #b45309;  --color-warning-bg: #fffbeb;  --color-warning-border: #fde68a;
  --color-danger:  #dc2626;  --color-danger-bg:  #fef2f2;  --color-danger-border:  #fecaca;
  --color-info:    #0369a1;  --color-info-bg:    #f0f9ff;  --color-info-border:    #bae6fd;

  /* 타입 스케일 7단 (Tailwind 기본 text-* 오버라이드) */
  --text-xs: 12px;   --text-xs--line-height: 1.5;
  --text-sm: 13px;   --text-sm--line-height: 1.5;
  --text-base: 14px; --text-base--line-height: 1.6;
  --text-md: 16px;   --text-md--line-height: 1.7;   /* 채팅 본문 */
  --text-lg: 20px;   --text-lg--line-height: 1.4;
  --text-xl: 24px;   --text-xl--line-height: 1.3;
  --text-2xl: 30px;  --text-2xl--line-height: 1.2;

  /* 라운드 3단 */
  --radius-md: 8px;    /* 컨트롤: 버튼·입력·칩 */
  --radius-xl: 14px;   /* 컨테이너: 카드·패널·입력창 */
  --radius-full: 9999px;

  /* 그림자 2단 */
  --shadow-sm: 0 1px 2px 0 rgb(0 0 0 / 0.05);
  --shadow-lg: 0 12px 32px -8px rgb(24 24 27 / 0.18);

  /* 모션: Tailwind v4에는 --duration-* 테마 네임스페이스가 없어 토큰을 두지 않는다. duration-150(인터랙션)/duration-200(레이아웃) 유틸리티를 직접 쓴다. */
}

/* 전역 규칙 */
*, *::before, *::after { box-sizing: border-box; }
html, body, #root { height: 100%; width: 100%; margin: 0; padding: 0; }
body { font-family: var(--font-sans); -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale; }

/* 포커스: outline-none을 쓰는 요소도 키보드 포커스는 보인다 */
:where(button, a, input, textarea, select, [role="tab"], [tabindex]):focus-visible {
  outline: 2px solid var(--color-brand-600);
  outline-offset: 2px;
}

/* reduced-motion */
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}
```

**토큰 사용 규칙**

| 용도 | 클래스 |
|---|---|
| 1차 색 | `bg-brand-600 hover:bg-brand-700 text-white`, 강조 텍스트 `text-brand-600` |
| 그라데이션 아바타 | `bg-linear-to-br from-brand-600 to-brand-800` (인라인 style 금지) |
| 유저 버블 | `bg-linear-to-br from-bubble-from to-bubble-to` |
| 본문 | `text-md text-fg` (채팅), `text-base text-fg` (일반) |
| 보조 | `text-sm text-fg-muted`, 힌트 `text-xs text-fg-subtle` (zinc-400 사용 금지) |
| 선 | `border-border`, 강조 `border-border-strong` |
| 라운드 | 컨트롤 `rounded-md`, 컨테이너 `rounded-xl`, 알약 `rounded-full` |
| 그림자 | 카드 `shadow-sm`, 떠 있는 패널·입력창 `shadow-lg` |
| 전환 | `transition-colors duration-150`, 레이아웃 전환 `duration-200` |

기존 `zinc-*`·`violet-*` 클래스는 Tailwind 기본 팔레트라 다른 화면에서 계속 동작한다. 채팅 범위 파일에서만 토큰 클래스로 교체한다.

### 5.1 Screen Layout

**1440 (사이드바 펼침)**

```
┌──────────┬────┬───────────────────────────────────────────────────┐
│ Sidebar  │Hist│ PageHeader  [제목] [N개 메시지]      [●RAG·Agent][↓][🗑]│ 52px
│ 256px    │ory ├───────────────────────────────────────────────────┤
│ [≡ 접기] │rail│                                                   │
│ 로고     │48px│          max-w-3xl (768px) 메시지 영역              │
│ +새에이전트│    │                                                   │
│ 내비 6   │    │   EmptyState: 아바타 → 제목(text-xl) → 설명 → 제안 4  │
│ ─────    │    │                                                   │
│ 에이전트 │    ├───────────────────────────────────────────────────┤
│ 목록     │    │  [ToolPreviewPanel 접힘: ghost Button "추론 진행 보기 (N)"]                         │
│ ─────    │    │  ┌─ Textarea (rounded-xl, shadow-lg) ───────────┐  │
│ 하단 6   │    │  │ 첨부칩  [문서검색 토글] ... Enter 안내  [▶송신] │  │
│ 사용자   │    │  └───────────────────────────────────────────────┘  │
│          │    │  안내문 text-xs text-fg-subtle                      │
└──────────┴────┴───────────────────────────────────────────────────┘
```

**768 (사이드바 접힘 레일 64px, 히스토리는 오버레이)**

```
┌────┬──────────────────────────────────────────────┐
│ ≡  │ PageHeader [제목]                [●][↓][🗑]    │
│ 로고│──────────────────────────────────────────────│
│ +  │                                              │
│ ✦  │   메시지 영역 px-4 (max-w-3xl 그대로, 꽉 참)      │
│ 🏬 │                                              │
│ ▦  │                                              │
│ 🔧 │                                              │
│ ⏱  │                                              │
│ 📊 │──────────────────────────────────────────────│
│ ·· │  ┌─ Textarea ────────────────────────────┐   │
│ ⚙  │  │ [문서검색]            Enter·Shift  [▶] │   │
│ T  │  └────────────────────────────────────────┘   │
└────┴──────────────────────────────────────────────┘
  히스토리 패널: 레일 옆 ☰ 클릭 시 w-72 오버레이(absolute, shadow-lg) + 바깥 클릭/ESC 닫힘
```

### 5.2 User Flow

```
진입(/chatpage) → [≤768이면 사이드바 접힘] → 빈 상태(제안 카드) → 입력 → 전송(Button loading) → 스트리밍(커서) → 응답(출처 칩·피드백)
사이드바 [≡] → 접힘/펼침 토글 → persist → 다른 라우트에도 유지
히스토리 [☰] → 1440: 인라인 w-72 패널 / ≤768: 오버레이 → 세션 선택 → 닫힘
```

### 5.3 Component List

| Component | Location | Responsibility | 공개 API |
|-----------|----------|----------------|---------|
| Button | `src/components/ui/Button.tsx` | 액션 버튼. variant 4 × size 2, `isPending`(스피너+disabled), `leadingIcon`/`trailingIcon` | `ButtonHTMLAttributes & { variant?, size?, isPending?, pendingText?, leadingIcon?, trailingIcon? }` |
| IconButton | `src/components/ui/IconButton.tsx` | 아이콘 전용 버튼. `aria-label` 필수(타입 강제), size sm 32px / md 36px, tone neutral/danger | `{ 'aria-label': string; size?; tone?; isActive? } & ButtonHTMLAttributes` |
| Input | `src/components/ui/Input.tsx` | 라벨·힌트·에러 슬롯, `aria-describedby` 자동 연결, `invalid` 상태 | `InputHTMLAttributes & { label?, hint?, error?, leadingIcon? }` |
| Textarea | `src/components/ui/Textarea.tsx` | Input과 같은 슬롯, `autoResize`(기존 ChatInput 로직 이관), `unstyled`(ChatInput 내부용) | `TextareaHTMLAttributes & { label?, hint?, error?, autoResize?, maxRows?, unstyled? }` |
| Tabs | `src/components/ui/Tabs.tsx` | 밑줄형 탭. `role="tablist"`, 좌우 화살표 이동, count 뱃지 | `{ items: TabItem[]; value: string; onChange(key); 'aria-label': string }` |
| PageHeader | `src/components/ui/PageHeader.tsx` | 고정 헤더 바(52px). 제목 `text-lg font-semibold`, 부제, `actions` 슬롯, `tabs` 슬롯, `leading` 슬롯(아이콘·토글) | `{ title: ReactNode; subtitle?; leading?; actions?; tabs?; compact? }` |
| Badge | `src/components/ui/Badge.tsx` | 상태 표시. tone 6, `dot`, `pulse`(온라인) | `{ tone?: BadgeTone; dot?; pulse?; children }` |
| EmptyState | `src/components/ui/EmptyState.tsx` | 빈 상태 1종. 아이콘/이미지 슬롯, 제목, 설명, 액션, children(제안 카드 등) | `{ icon?: ReactNode; title; description?; action?: ReactNode; children? }` |
| LoadingButton | `src/components/common/LoadingButton.tsx` | 래퍼: `isPending`·`pendingText`·나머지 props를 Button(variant 미지정 시 `className` 그대로 전달)에 위임. 기존 테스트 통과 | 변경 없음 |
| StatusBadge | `src/components/common/StatusBadge.tsx` | 래퍼: `ProgressStepStatus`→`BadgeTone` 매핑(completed→brand, in_progress→info, pending→neutral, error→danger) | 변경 없음 |
| AppSidebar | `src/components/layout/AppSidebar.tsx` | `collapsed` 상태에 따라 256px 전체 / 64px 레일 렌더. 레일은 아이콘 + `title` 툴팁, 토글 버튼 최상단(다크 표면이라 네이티브 button + 토큰). 버튼 접근 가능한 이름은 접혀도 유지(`aria-label`) → 기존 테스트 `getByRole('button', {name})` 통과 | props 변경 없음 (상태는 스토어에서 읽음) |
| AgentChatLayout | `src/components/layout/AgentChatLayout.tsx` | ≤768 최초 진입 시 `setSidebarCollapsed(true)`(persist에 값이 없을 때만, `matchMedia('(max-width: 768px)')`), 히스토리 패널 오버레이 모드 전달 | 변경 없음 |
| ChatHeader | `src/components/layout/ChatHeader.tsx` | PageHeader로 구성. 제목·메시지 수 Badge(neutral)·에이전트 상태 Badge(success, pulse)·워크스페이스/다운로드/삭제 IconButton | props 변경 없음 |
| ChatHistoryPanel | `src/components/layout/ChatHistoryPanel.tsx` | 토큰 적용, `overlay?: boolean` prop 추가(≤768). 새 대화 Button(secondary, sm), 검색 Input(sm) | `overlay?` 추가 |
| MessageList | `src/components/chat/MessageList.tsx` | 내부 EmptyState를 `ui/EmptyState` + 제안 카드 4개(`SuggestionCards` named export)로 교체. ChatPage의 `EmptyAgentState`가 같은 카드를 사용 | `SuggestionCards` export 추가 |
| MessageBubble | `src/components/chat/MessageBubble.tsx` | 유저 버블 토큰, 어시스턴트 아바타 그라데이션 토큰, eyebrow 라벨(uppercase) 제거 → `text-xs font-medium text-fg-subtle` 에이전트명 | 변경 없음 |
| ChatInput | `src/components/chat/ChatInput.tsx` | Textarea(unstyled, autoResize), 첨부 칩 Badge(brand), 문서검색 토글 Button(secondary sm, `aria-pressed`), 백그라운드 Button(secondary sm, 전송 가능 시 brand 톤), 엑셀 첨부 Button(secondary sm, 라벨 "엑셀"), 전송 IconButton(md, brand 채움, `isLoading`→disabled+스피너) | props 변경 없음 |
| SourceCitation, TypingIndicator, MessageFeedback, ToolPreviewPanel, ExcelPreviewModal, MarkdownRenderer | `src/components/chat/*` | 색·글자·라운드 토큰 교체만 | 변경 없음 |
| ChatPage | `src/pages/ChatPage/index.tsx` | 인라인 style 래퍼를 Tailwind 클래스로(`flex h-full flex-col`, 본문 `flex-1 overflow-y-auto`, 컨테이너 `mx-auto w-full max-w-3xl px-4 sm:px-6`), 백그라운드 배너 토큰화(info tone) | 변경 없음 |

### 5.4 Page UI Checklist

#### 공통 컴포넌트 키트 (`components/ui`)

- [ ] Button: variant `primary`(bg-brand-600/hover 700/active scale-95) · `secondary`(border-border bg-surface-muted) · `ghost`(투명, hover sunken) · `danger`(text-danger, hover danger-bg); size `sm`(h-8 px-3 text-sm) · `md`(h-10 px-4 text-base); `disabled`(opacity-50 cursor-not-allowed); `isPending`(스피너 + disabled + `pendingText`); `leadingIcon`/`trailingIcon` 슬롯; `focus-visible` 링
- [ ] IconButton: `aria-label` 필수, size `sm`(32px) · `md`(36px), tone `neutral` · `danger`, `isActive`(bg-sunken + text-fg), `title` 자동 = aria-label
- [ ] Input: `label`(for/id 연결), `hint`(id → aria-describedby), `error`(role="alert", border-danger, aria-invalid), `leadingIcon`, size sm/md, `focus-within` border-brand-400
- [ ] Textarea: Input과 같은 슬롯 + `autoResize`(maxRows 기본 8) + `unstyled`
- [ ] Tabs: `role="tablist"`/`tab`, `aria-selected`, 활성 `border-b-2 border-brand-600 text-brand-700`, 비활성 `text-fg-muted hover:text-fg`, `count` 표시, ←/→/Home/End 키 이동, `disabled` 항목
- [ ] PageHeader: 높이 52px(`compact`) 또는 auto, `border-b border-border`, 제목 `text-lg font-semibold text-fg truncate`, 부제 `text-sm text-fg-muted`, `leading`/`actions`/`tabs` 슬롯, 768에서 부제 숨김(`hidden md:block`)
- [ ] Badge: tone 6종 배경/텍스트/테두리 토큰, `dot`(w-1.5 h-1.5), `pulse`(reduced-motion 시 정지), `text-xs font-medium rounded-full px-2 py-0.5 whitespace-nowrap`
- [ ] EmptyState: 세로 중앙 정렬, 아이콘 슬롯(기본 48px 원형 surface-sunken), 제목 `text-xl font-semibold`, 설명 `text-base text-fg-muted max-w-md`, 액션 슬롯, children 슬롯
- [ ] 각 컴포넌트 `*.test.tsx`: 렌더, variant 클래스, disabled/pending, aria 속성

#### 채팅 화면 (`/chatpage`) — 1440

- [ ] 사이드바(펼침 256px): 상단 토글 IconButton(`aria-label="사이드바 접기"`), 로고+브랜드명, "새 에이전트" 다크 표면용 네이티브 버튼(`border-sidebar-border`), 내비 6항목(활성 `bg-sidebar-active` + 좌측 2px brand 바), 에이전트 그룹 목록(스켈레톤·에러·빈 상태 3종), 하단 6항목(즐겨찾기·역할설정·리소스·지식베이스·환경설정·관리자[admin만]), 사용자 블록(아바타·이메일·로그아웃 버튼 `aria-label="로그아웃"`)
- [ ] 히스토리 레일(48px): 열기 IconButton(`aria-label="대화 목록 열기"`), 새 대화 IconButton
- [ ] 히스토리 패널(펼침 w-72): 닫기 IconButton, "새 대화" Button(secondary sm, 전체 폭), 검색 Input(sm, leadingIcon), 세션 목록(활성 `bg-brand-50 text-brand-700`), 로딩 스켈레톤, 에러+재시도
- [ ] ChatHeader: 제목 truncate, 메시지 수 Badge(neutral, 0이면 숨김), 워크스페이스 IconButton(agentId 있을 때), 상태 Badge(success dot pulse "RAG · Agent"), 다운로드 IconButton, 삭제 IconButton(danger)
- [ ] 빈 상태: EmptyState(에이전트 아바타 56px 그라데이션 또는 로고, 제목 "{에이전트명}와 대화하세요" `text-xl`, 설명 `text-base text-fg-muted`, 제안 카드 4개 `rounded-xl border-border shadow-sm hover:border-brand-200` — translate 애니메이션 없음. ChatPage `EmptyAgentState`가 `SuggestionCards`를 children으로 받아 `handleSend`에 연결)
- [ ] 메시지: 유저 버블(`rounded-xl rounded-br-md` gradient 토큰, `text-md leading-[1.65]`), 어시스턴트(아바타 36px 그라데이션, 에이전트명 `text-xs text-fg-subtle`, 본문 `text-md leading-[1.7] text-fg`, 스트리밍 커서 `animate-pulse`), 메시지 간 `gap-8`
- [ ] 출처 칩(SourceCitation): `rounded-full border-border bg-surface-muted text-xs`, hover `border-brand-200 text-brand-700`
- [ ] 피드백(MessageFeedback): IconButton(sm) 2개, 활성 `isActive`
- [ ] 타이핑 인디케이터: 점 3개 `bg-fg-subtle animate-bounce`, reduced-motion 시 정지
- [ ] ToolPreviewPanel: 접힘 상태는 ghost Button "추론 진행 보기 (N)", 펼침 패널 `rounded-xl border-border bg-surface-muted text-sm`, 이벤트 행 `text-sm`, 도구명 `font-mono text-xs`, 아이콘은 lucide(Lightbulb/Loader2/Check)
- [ ] 백그라운드 배너: `role="status"`, Badge info 톤 색(`bg-info-bg border-info-border text-info`), 스피너
- [ ] ChatInput: 컨테이너 `rounded-xl border-border-strong bg-surface shadow-lg focus-within:border-brand-400`, 첨부 칩 Badge(brand, 제거 버튼 24px 히트 영역), Textarea(`text-md`, placeholder `text-fg-subtle`, 최소 1행 최대 8행), 하단 툴바(문서검색 토글 Button secondary sm `aria-pressed`, 첨부 Button secondary sm "엑셀"[attachmentEnabled], 백그라운드 Button secondary sm[backgroundEnabled], 안내 `text-xs text-fg-subtle hidden lg:block`(768 이하 숨김), 전송 IconButton md brand 채움 `disabled` 조건 동일), 하단 안내문 `text-xs text-fg-subtle`
- [ ] ExcelPreviewModal: 기존 Modal 유지, 내부 글자·선 토큰만
- [ ] 글자 크기: 위 모든 요소가 `text-xs/sm/base/md/lg/xl` 토큰만 사용. 최소 12px

#### 채팅 화면 — 768

- [ ] 최초 진입 시 사이드바 접힘(persist 값 없을 때). 레일 64px: 토글, 로고 아이콘, 새 에이전트 `+`, 내비 6 아이콘(툴팁 title), 구분선, 하단 6 아이콘, 사용자 아바타. 모든 버튼 `aria-label` = 라벨 텍스트
- [ ] 히스토리 패널: `overlay` 모드 → `absolute left-[112px] top-0 h-full w-72 shadow-lg z-20` + 바깥 클릭/ESC 닫힘
- [ ] ChatHeader: 부제 숨김, 액션 3개 유지, 제목 truncate
- [ ] ChatInput: 툴바 한 줄 유지(안내문 숨김), 전송 버튼 36px, 가로 스크롤 없음
- [ ] 메시지 영역 `px-4`, 버블 최대 폭 `max-w-[85%]`(1024 이상에서 75%)

### 5.5 Sidebar Collapse Behavior

| 상태 | 폭 | 내용 | 전환 |
|---|---|---|---|
| expanded | 256px | 현행 전체 | `transition-[width] duration-200`, reduced-motion 시 즉시 |
| collapsed | 64px | 아이콘 레일. 라벨은 `title`과 `aria-label`로만. 에이전트 그룹 목록은 숨기고 "에이전트" 아이콘 1개로 대체(클릭 시 펼침) | 동일 |
| 초기값 | persist 값 → 없으면 `matchMedia('(max-width: 768px)').matches` | | |

---

## 6. Error Handling

| 상황 | 처리 |
|---|---|
| 에이전트 목록 로드 실패 | 기존 AppSidebar 에러 블록 유지, 재시도는 Button(secondary sm 다크 변형) |
| 세션 목록 로드 실패 | 기존 ChatHistoryPanel 에러 + 재시도 Button |
| 전송 실패·409 백그라운드 안내 | 기존 `bgNotice` 로직 유지, 배너 톤만 info/danger 토큰 |
| persist 구 데이터에 `isSidebarCollapsed` 없음 | Zustand persist merge 기본값(false) 적용, 그 후 ≤768 판정 1회 |
| 폰트 로드 실패 | `font-display: swap`(Pretendard 패키지 CSS 기본) + 폴백 스택 |

API 에러 코드·응답 형식 변경 없음.

---

## 7. Security Considerations

- [x] 입력 검증: 기존 ChatInput의 trim·빈 입력 차단 로직 유지
- [x] 인증·권한: ProtectedRoute, `user.role === 'admin'` 분기 유지(사이드바 접힘 상태에서도 관리자 항목 조건 동일)
- [x] XSS: MarkdownRenderer의 기존 sanitize 경로 유지(렌더러 로직 미변경)
- [x] 신규 의존성 `pretendard`는 폰트 파일만 포함(스크립트 없음)
- [ ] N/A: HTTPS·Rate limiting은 이 기능 범위 밖

---

## 8. Test Plan

### 8.1 Test Scope

| Type | Target | Tool | Phase |
|------|--------|------|-------|
| L1: API Tests | 변경 없음 → 기존 채팅 엔드포인트 스모크 1건(인증 후 세션 목록 200) | curl | Check |
| L2: UI Component/Action Tests | ui 8종 단위 + 채팅 컴포넌트 기존 11파일 + AppSidebar/ChatHeader 기존 테스트 | Vitest + RTL | Do |
| L3: E2E Scenario Tests | 채팅 화면 수동 시나리오(스크린샷 + 콘솔) | Chrome DevTools MCP | Check |

### 8.2 L1: API Test Scenarios

| # | Endpoint | Method | Test Description | Expected Status | Expected Response |
|---|----------|--------|-----------------|:--------------:|-------------------|
| 1 | `/api/v1/auth/refresh` | POST | 기존 토큰 갱신 동작 유지 | 200 | `access_token` 존재 |
| 2 | 채팅 세션 목록(기존 `useAgentSessions` 엔드포인트) | GET | 인증 후 목록 반환 | 200 | 배열 |

### 8.3 L2: UI Test Scenarios

| # | 대상 | Action | Expected Result |
|---|------|--------|----------------|
| 1 | Button | variant/size 렌더 | 각 variant 클래스 포함, `isPending` 시 disabled + 스피너 + pendingText |
| 2 | IconButton | 렌더 | `aria-label` 접근 가능 이름, `title` 동일, `isActive` 클래스 |
| 3 | Input/Textarea | label·hint·error | `label[for]`↔`input#id`, `aria-describedby`에 hint/error id, error 시 `aria-invalid="true"`·`role="alert"` |
| 4 | Textarea autoResize | 긴 입력 | height가 maxRows 상한에서 멈춤 |
| 5 | Tabs | 클릭·키보드 | `aria-selected` 전환, ←/→ 로 포커스 이동, disabled 건너뜀 |
| 6 | PageHeader | 슬롯 렌더 | title/subtitle/actions/tabs 모두 노출 |
| 7 | Badge | tone/dot/pulse | tone 클래스, dot 요소, pulse 클래스 |
| 8 | EmptyState | 슬롯 렌더 | title 필수, action·children 노출 |
| 9 | LoadingButton(기존 테스트) | isPending | 기존 2 테스트 통과 |
| 10 | StatusBadge(기존 테스트) | 4 상태 | 기존 라벨 텍스트 유지 |
| 11 | AppSidebar(기존 테스트) | admin 분기·내비 클릭 | 기존 통과 + 신규: 토글 클릭 시 `aria-label` "사이드바 펼치기"로 전환, 접힘 상태에서도 `getByRole('button', {name: '에이전트 스토어'})` 존재 |
| 12 | ChatHeader(기존 테스트) | 렌더 | 기존 통과 |
| 13 | ChatInput(기존 `.background.test`) | 백그라운드 전송 | 기존 통과 |
| 14 | MessageBubble·SourceCitation·MessageFeedback·ToolPreviewPanel·MarkdownRenderer·ExcelPreview* (기존 8파일) | 렌더 | 기존 통과 |
| 15 | layoutStore | toggleSidebar | 값 토글, persist 키 `layout-preferences` 유지 |

### 8.4 L3: E2E Scenario Tests (수동, Chrome DevTools MCP)

| # | Scenario | Steps | Success Criteria |
|---|----------|-------|-----------------|
| 1 | 1440 채팅 | 로그인 → /chatpage → 빈 상태 → 제안 클릭 → 응답 수신 | 콘솔 에러 0, 스트리밍 커서·출처 칩 표시, 스크린샷 비교 |
| 2 | 768 채팅 | 768 리사이즈 → 새 세션 진입 | 사이드바 접힘, 가로 스크롤 없음, 입력 툴바 한 줄 |
| 3 | 사이드바 토글 | 접기 → 다른 라우트 이동 → 복귀 | 접힘 상태 유지(persist) |
| 4 | 히스토리 오버레이 | 768에서 ☰ → 바깥 클릭 | 열림/닫힘, ESC 닫힘 |
| 5 | 키보드 | Tab 순회 | 모든 인터랙티브 요소에 포커스 링 가시 |
| 6 | 폰트 | 채팅 로드 | `getComputedStyle(body).fontFamily`가 Pretendard로 시작 |
| 7 | 다른 화면 회귀 | 스토어·컬렉션·작업·대시보드·사용자관리 스크린샷 | 깨짐 없음(폰트 변경 외) |

### 8.5 Seed Data Requirements

| Entity | Minimum Count | Key Fields |
|--------|:------------:|-----------|
| 사용자 | 1 | `idt/scripts/seed_test_users.sql` 테스트 관리자 |
| 에이전트 | 0~1 | 없어도 SUPER 에이전트로 시나리오 가능 |

---

## 9. Clean Architecture

### 9.1 Layer Structure

| Layer | Responsibility | Location |
|-------|---------------|----------|
| Presentation | ui 키트, layout, chat 컴포넌트, 페이지 | `src/components/`, `src/pages/` |
| Application | 훅(스트리밍·세션), 스토어 | `src/hooks/`, `src/store/` |
| Domain | 타입 | `src/types/` |
| Infrastructure | 서비스, axios 클라이언트, 쿼리 키 | `src/services/`, `src/lib/` |

### 9.2 Dependency Rules

`components/ui`는 `types/ui`와 `lucide-react`만 import한다. 스토어·훅·서비스를 import하지 않는다(순수 표현). `layout`·`chat`은 기존대로 훅·스토어를 쓰되 이번 작업에서 import 목록을 바꾸지 않는다(ui 추가 제외).

### 9.3 File Import Rules

| From | Can Import | Cannot Import |
|------|-----------|---------------|
| `components/ui` | `types/ui`, `lucide-react`, react | store, hooks, services, 다른 components |
| `components/common` 래퍼 | `components/ui`, `types` | store, services |
| `components/layout`, `components/chat` | `components/ui`, `components/common`, hooks, store, types | services 직접 호출(기존 규칙) |

### 9.4 This Feature's Layer Assignment

| Component | Layer | Location |
|-----------|-------|----------|
| Button, IconButton, Input, Textarea, Tabs, PageHeader, Badge, EmptyState | Presentation | `src/components/ui/` |
| ButtonVariant, ControlSize, BadgeTone, TabItem | Domain | `src/types/ui.ts` |
| layoutStore (필드 추가) | Application | `src/store/layoutStore.ts` |
| 토큰 | Presentation(전역) | `src/index.css` |

---

## 10. Coding Convention Reference

### 10.1 Naming Conventions

`idt_front/CLAUDE.md` 규칙 그대로. 컴포넌트 PascalCase + arrow function + 하단 `export default`, props `interface` 파일 상단.

### 10.2 Import Order

외부 → `@/` 절대 → 상대 → `type` import.

### 10.3 Environment Variables

변경 없음.

### 10.4 This Feature's Conventions

| Item | Convention Applied |
|------|-------------------|
| 컴포넌트 export | `export default` 단독. 런타임 상수(variant 맵)는 파일 내부 `const`, export 금지. 공유 상수·타입은 `src/types/ui.ts` |
| className 합성 | 템플릿 리터럴 + 단순 join 헬퍼 `cn(...parts)` (`src/utils/cn.ts`, falsy 제거만. 외부 라이브러리 없음) |
| 아이콘 | 신규 코드는 `lucide-react`, 크기 16(sm)/20(md). 기존 인라인 SVG는 이번 범위에서 교체하지 않음(ChatHeader·ChatInput·AppSidebar 레일은 교체 대상) |
| 글자 크기 | 채팅 범위 파일에서 `text-[Npx]` 금지. 토큰 7단만 |
| 색 | hex·`style={{ background }}` 금지. 그라데이션은 `bg-linear-to-br from-* to-*` |
| 포커스 | `outline-none` 사용 시 전역 `:focus-visible` 규칙이 적용되므로 별도 `focus:` 스타일 추가 금지(중복 방지) |
| 테스트 | 컴포넌트 파일 옆 `*.test.tsx`, RTL `getByRole` 우선 |
| Design 참조 주석 | 파일 상단 `// Design Ref: ui-redesign-chat §5.3 — ...`, 핵심 로직 `// Plan SC: FR-xx` |

---

## 11. Implementation Guide

### 11.1 File Structure

```
idt_front/
├── index.html                          ← lang="ko", <title>
├── package.json                        ← + pretendard
└── src/
    ├── index.css                       ← @theme 토큰 + 전역 규칙 (§5.0)
    ├── App.css                         ← 삭제
    ├── App.tsx                         ← App.css import 제거(있다면)
    ├── types/ui.ts                     ← 신규
    ├── utils/cn.ts (+ cn.test.ts)      ← 신규
    ├── hooks/useMediaQuery.ts (+ test) ← 신규: 뷰포트 판정(useSyncExternalStore)
    ├── components/
    │   ├── ui/                         ← 신규 8 + test 8
    │   │   Button.tsx IconButton.tsx Input.tsx Textarea.tsx
    │   │   Tabs.tsx PageHeader.tsx Badge.tsx EmptyState.tsx
    │   ├── common/LoadingButton.tsx    ← 래퍼
    │   ├── common/StatusBadge.tsx      ← 래퍼
    │   ├── layout/AppSidebar.tsx       ← 접기 레일 + 토큰
    │   ├── layout/AppSidebar.test.tsx  ← 토글 테스트 추가
    │   ├── layout/AgentChatLayout.tsx  ← 초기 접힘 판정, overlay 전달
    │   ├── layout/ChatHeader.tsx       ← PageHeader
    │   ├── layout/ChatHistoryPanel.tsx ← 토큰 + overlay
    │   ├── layout/ChatHistoryPanel.test.tsx ← 신규: overlay 백드롭·ESC
    │   └── chat/ (MessageList, MessageBubble, ChatInput, SourceCitation,
    │             TypingIndicator, MessageFeedback, ToolPreviewPanel,
    │             ExcelPreviewModal, MarkdownRenderer)  ← 토큰 교체
    ├── store/layoutStore.ts (+ layoutStore.test.ts)   ← 필드 추가
    └── pages/ChatPage/index.tsx        ← 래퍼 클래스화
```

신규 17파일(ui 8 + test 8 + types/ui.ts), 보조 신규 3(cn.ts, cn.test.ts, layoutStore.test.ts), 수정 17파일, 삭제 1.

### 11.2 Implementation Order

1. [ ] `npm i pretendard` → `index.css` 토큰·폰트·전역 규칙 → `index.html` → `App.css` 삭제 → `npm run build` 확인 (다른 화면 깨짐 스크린샷 5장)
2. [ ] `types/ui.ts`, `utils/cn.ts`(+test)
3. [ ] `ui/Button` + test → `LoadingButton` 래퍼 전환 → 기존 테스트 통과
4. [ ] `ui/Badge` + test → `StatusBadge` 래퍼 전환 → 기존 테스트 통과
5. [ ] `ui/IconButton`, `ui/Input`, `ui/Textarea`, `ui/Tabs`, `ui/PageHeader`, `ui/EmptyState` + 각 test
6. [ ] `layoutStore` 필드 추가 + test
7. [ ] `AppSidebar` 접기 레일 + 토큰 → 기존 테스트 + 토글 테스트
8. [ ] `AgentChatLayout` 초기 접힘·overlay 전달, `ChatHistoryPanel` 토큰·overlay
9. [ ] `ChatHeader`(PageHeader), `MessageList`(EmptyState), `MessageBubble`, `ChatInput`(Textarea/Button/IconButton)
10. [ ] `SourceCitation`, `TypingIndicator`, `MessageFeedback`, `ToolPreviewPanel`, `ExcelPreviewModal`, `MarkdownRenderer` 토큰 교체
11. [ ] `ChatPage` 래퍼 클래스화 → 전체 vitest(채팅 11파일 + 신규) → 1440/768 스크린샷 → 콘솔 확인
12. [ ] `idt_front/CLAUDE.md` 디자인 시스템 절 갱신

### 11.3 Session Guide

#### Module Map

| Module | Scope Key | Description | Estimated Turns |
|--------|-----------|-------------|:---------------:|
| 토큰·폰트·전역 | `module-1` | 순서 1~2. index.css, pretendard, index.html, App.css 삭제, types/ui, cn | 15-20 |
| UI 키트 | `module-2` | 순서 3~5. ui 8종 + 테스트 + 래퍼 2종 전환 | 40-50 |
| 사이드바·레이아웃 | `module-3` | 순서 6~8. layoutStore, AppSidebar 접기, AgentChatLayout, ChatHistoryPanel | 25-35 |
| 채팅 화면 | `module-4` | 순서 9~12. ChatHeader, chat/* 토큰 교체, ChatPage, 스크린샷, CLAUDE.md | 35-45 |

#### Recommended Session Plan

| Session | Phase | Scope | Turns |
|---------|-------|-------|:-----:|
| Session 1 | Plan + Design | 전체 | 완료 (2026-10-20) |
| Session 2 | Do | `--scope module-1,module-2` | 55-70 |
| Session 3 | Do | `--scope module-3` | 25-35 |
| Session 4 | Do | `--scope module-4` | 35-45 |
| Session 5 | Check + Report | 전체 | 30-40 |

의존 순서: module-1 → module-2 → module-3 → module-4. module-3과 module-4는 module-2 완료 후 병렬 가능하나, ChatHeader·ChatInput이 module-3의 overlay prop을 쓰지 않으므로 충돌은 `AgentChatLayout` 1파일뿐이다.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-10-20 | 초안. Option C 선택, 토큰 표, ui 키트 8종 API, 채팅 UI 체크리스트(1440/768), 사이드바 접기 동작, 세션 가이드 4모듈 | 배상규 |
| 0.2 | 2026-10-21 | Check 단계 정정: duration 토큰 제거, 다크 사이드바 SidebarItem, 제안 카드 4개·SuggestionCards, ToolPreviewPanel 접힘 버튼, ChatInput 버튼 variant·안내문 lg, 버블 폭 lg, layoutStore 필드 수, useMediaQuery·ChatHistoryPanel.test 추가 | 배상규 |
