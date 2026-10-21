---
template: plan
version: 1.3
feature: ui-redesign-chat
---

# ui-redesign-chat Planning Document

> **Summary**: A안(정돈된 바이올렛) 디자인 방향을 기준으로 디자인 토큰·폰트·공통 컴포넌트 키트를 만들고, 대표 화면인 채팅(ChatPage)을 그 키트로 리디자인한다. 셸 통합은 후속 사이클로 분리한다.
>
> **Project**: idt_front (sangplusbot)
> **Version**: 0.0.0
> **Author**: 배상규
> **Date**: 2026-10-20
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 색은 일관되지만 토큰·공통 컴포넌트·타입 스케일이 없어 화면마다 손으로 다시 그린다. 임의 px 글자 크기 20종, 1차 버튼 수기 작성 106곳, 탭 구현 3종, 페이지 헤더 6종이 공존하고, 포커스 링·reduced-motion·반응형이 사실상 없다. |
| **Solution** | Tailwind v4 `@theme` 토큰(색·타입 스케일·라운드·그림자·간격) + Pretendard Variable 폰트 + 공통 컴포넌트 7종(Button, IconButton, Input/Textarea, Tabs, PageHeader, Badge, EmptyState)을 만들고, 채팅 화면(헤더·빈 상태·메시지·입력창·히스토리 패널·사이드바 접기)을 이 키트로 재구성한다. |
| **Function/UX Effect** | 채팅 화면이 1440/768에서 동일한 규칙으로 렌더링되고, 키보드 포커스·hover·disabled·loading 상태가 모두 보인다. 11px 이하 글자가 사라지고 보조 텍스트 대비가 AA(4.5:1)를 만족한다. 이후 화면은 키트를 가져다 쓰기만 하면 된다. |
| **Core Value** | 한 번 정의한 토큰과 키트가 나머지 37개 화면의 리디자인 비용을 반복 작업 수준으로 낮춘다. 기능·API·상태관리는 손대지 않으므로 회귀 위험이 UI 레이어에 갇힌다. |

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

### 1.1 Purpose

A안 "정돈된 바이올렛" 방향으로 디자인 기반(토큰·폰트·공통 컴포넌트)을 만들고, 대표 화면인 채팅을 그 기반 위에서 리디자인한다. 이 사이클의 산출물은 이후 모든 화면 리디자인의 출발점이 된다.

### 1.2 Background

2026-10-20 UI 분석 결과(스크린샷 12장, 코드 통계) 요약:

| 항목 | 현황 |
|---|---|
| 토큰 | `index.css`는 Tailwind import + reset만. `@theme`·CSS 변수 0개. `App.css`는 Vite 템플릿 잔재로 미사용 |
| 폰트 | 미지정. OS별 한글 글꼴이 다름 |
| 글자 크기 | 임의 px 20종(8.5~26px) 1,700여 회, 표준 스케일 200여 회. 채팅 실측 최소 11px |
| 색 | zinc 2,978회·violet 800회로 팔레트는 일관. hex 리터럴 65곳, 인라인 gradient 31곳, 인라인 style 110곳 |
| 라운드·그림자 | 라운드 6단계 혼용, 그림자 11종 |
| 공통 컴포넌트 | Button·Input·Tabs·PageHeader·Badge·EmptyState 없음. 1차 버튼 수기 106곳, 상태 배지 수기 33파일 |
| 접근성 | `focus-visible` 0회, `outline-none` 96회, `prefers-reduced-motion` 0회. 힌트 텍스트 `text-zinc-400` on white ≈ 2.6:1 |
| 반응형 | 브레이크포인트 접두사 총 49회. 사이드바 256px 고정, 접기 없음 |

채팅 화면은 주 화면이며 헤더·빈 상태·메시지 버블·마크다운·출처 칩·입력창·히스토리 패널이 모두 들어 있어 토큰과 키트를 검증하기에 적합하다.

### 1.3 Related Documents

- 분석 스크린샷: `C:\Users\tkdrb\AppData\Local\Temp\claude\C--Users-tkdrb-project-agent-agent-idt-front\6af0fc81-eed8-4c48-8787-91c398a06cab\scratchpad\shot-*.png` (세션 임시 경로, 필요 시 Design 단계에서 `docs/02-design/assets/`로 복사)
- 디자인 시스템 기존 규칙: `idt_front/CLAUDE.md` "UI 디자인 시스템" 절
- 레이아웃 규칙: `idt_front/CLAUDE.md` "페이지 래퍼 규칙"
- 유저 시나리오: `docs/USER-SCENARIOS.md` (주인공 P2)
- 선행 PDCA: `docs/01-plan/features/layout-scroll-fix.plan.md`, `docs/archive/2026-08/question-card/`

---

## 2. Scope

### 2.1 In Scope

**Phase 1. 디자인 기반**

- [ ] `src/index.css`에 Tailwind v4 `@theme` 토큰 정의: 색(primary·surface·border·muted·상태 4색), 타입 스케일 7단(12/13/14/16/20/24/30), 라운드 3단(md/xl/full), 그림자 2단(sm/lg), 간격은 Tailwind 기본 4pt 유지
- [ ] Pretendard Variable npm 패키지 추가, `--font-sans` 토큰으로 연결, `index.html`의 `lang="ko"`·제목 수정
- [ ] `App.css` 잔재 제거(미사용 확인 후)
- [ ] 공통 컴포넌트 7종 신설(`src/components/ui/`): Button(primary/secondary/ghost/danger × sm/md), IconButton, Input·Textarea, Tabs(underline 1종), PageHeader(제목·부제·액션 슬롯), Badge(상태 5종), EmptyState(아이콘·제목·설명·액션)
- [ ] 기존 `LoadingButton`·`StatusBadge`는 새 Button·Badge를 감싸는 호환 래퍼로 유지(사용처 수정 없음)
- [ ] 전역 포커스 링 규칙(`focus-visible:ring-2 ring-primary`), `prefers-reduced-motion` 시 transition·animation 비활성
- [ ] 각 컴포넌트 단위 테스트(Vitest + RTL)

**Phase 2. 채팅 화면 적용**

- [ ] `ChatHeader`: PageHeader 규격으로 정리, 에이전트 배지·액션은 IconButton
- [ ] `MessageList` 빈 상태: EmptyState 사용, 로고·타이틀·설명 간격 토큰화
- [ ] `MessageBubble`·`MarkdownRenderer`·`SourceCitation`·`TypingIndicator`·`MessageFeedback`: 글자 크기·색·라운드를 토큰으로 교체(로직 변경 없음)
- [ ] `ChatInput`: Textarea·Button·IconButton 사용, 768에서 도구 토글과 전송 버튼이 한 줄에 유지, disabled/loading 상태 표시
- [ ] `ChatHistoryPanel`: 토큰 적용, 768에서 오버레이 패널로 전환
- [ ] `AppSidebar` 접기: 256px ↔ 64px 아이콘 레일, 상태는 `layoutStore`에 `isSidebarCollapsed` 추가(persist), 768 이하 기본 접힘
- [ ] `ToolPreviewPanel`·`ExcelPreviewModal`: 색·글자 토큰만 교체
- [ ] 1440/768 스크린샷 전후 비교, 콘솔 에러 0 확인

### 2.2 Out of Scope

- 셸 통합(AdminLayout·TopNav 제거, 관리자 메뉴 흡수) → 후속 사이클 `ui-redesign-shell`
- 채팅 이외 37개 화면의 리디자인 → 화면별 후속 사이클
- 모바일 375 완전 대응(드로어 내비, 모바일 전용 헤더) → 셸 통합 사이클에서 처리
- 다크 모드
- 채팅 기능 변경(스트리밍·첨부·도구 프리뷰·피드백 로직, API 계약, React Query 키, Zustand 스토어 구조)
- 관리자 테이블 공용 DataTable → `ui-redesign-admin-tables` 사이클
- 아이콘 라이브러리 교체(기존 인라인 SVG·lucide-react 혼용은 유지, 신규 컴포넌트만 lucide-react 사용)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | `@theme` 토큰을 `index.css`에 정의하고, CLAUDE.md의 색 토큰 표(Primary #7c3aed→#4f46e5 gradient, Sidebar #0f0f0f, User Bubble #2d2d2d→#1a1a1a, Border zinc-200/300, Muted zinc-500 이상)와 값이 일치한다 | High | Pending |
| FR-02 | Pretendard Variable을 npm으로 추가하고 `--font-sans`에 연결한다. 폴백은 system-ui, Apple SD Gothic Neo, Malgun Gothic | High | Pending |
| FR-03 | Button 컴포넌트: variant(primary/secondary/ghost/danger), size(sm/md), `isPending`(스피너 + disabled), `disabled`, 아이콘 슬롯. 포커스 링·hover·active(scale-95) 상태 포함 | High | Pending |
| FR-04 | IconButton: 접근 가능한 이름(`aria-label` 필수), 최소 32×32 히트 영역, 툴팁 title | High | Pending |
| FR-05 | Input·Textarea: 라벨·힌트·에러 슬롯, `aria-describedby` 연결, focus-within 스타일 | High | Pending |
| FR-06 | Tabs: `role="tablist"`·`aria-selected`, 밑줄형 1종, 키보드 좌우 이동 | Medium | Pending |
| FR-07 | PageHeader: 제목(text-xl semibold 고정)·부제·액션 슬롯·탭 슬롯. 고정 헤더 + 스크롤 바디 패턴 A와 결합 | High | Pending |
| FR-08 | Badge: tone(neutral/success/warning/danger/info), 점(dot) 옵션. 색만으로 의미를 전달하지 않도록 텍스트 필수 | Medium | Pending |
| FR-09 | EmptyState: 아이콘·제목·설명·1차 액션. 스토어·만들기·작업·설정의 4가지 빈 상태 양식을 대체할 수 있는 1종 | Medium | Pending |
| FR-10 | `LoadingButton`·`StatusBadge`는 기존 props 그대로 새 컴포넌트를 감싸 동작한다(기존 테스트 통과) | High | Pending |
| FR-11 | 채팅 화면 표현 레이어(ChatHeader, MessageList, MessageBubble, ChatInput, ChatHistoryPanel, SourceCitation, TypingIndicator, MessageFeedback, ToolPreviewPanel, ExcelPreviewModal, MarkdownRenderer)를 토큰·키트로 교체한다. props·훅·스토어 시그니처는 바꾸지 않는다 | High | Pending |
| FR-12 | AppSidebar 접기: 64px 아이콘 레일, 툴팁으로 라벨 표시, 토글 버튼, `layoutStore.isSidebarCollapsed` persist. 768 이하 초기 진입 시 접힘 | High | Pending |
| FR-13 | ChatHistoryPanel: 768 이하에서 본문 위 오버레이로 열리고 바깥 클릭·ESC로 닫힘 | Medium | Pending |
| FR-14 | 전역: `prefers-reduced-motion: reduce`에서 transition·animation·bounce 비활성(`index.css`) | Medium | Pending |
| FR-15 | 채팅 화면 전체에서 글자 크기는 토큰 7단만 사용(임의 `text-[Npx]` 0건), 최소 12px | High | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 접근성 | 본문·보조 텍스트 대비 4.5:1 이상, 모든 인터랙티브 요소 포커스 링 가시, 아이콘 버튼 `aria-label` | Chrome DevTools a11y 패널 + `chrome-devtools-mcp:a11y-debugging` 스킬, 수동 Tab 순회 |
| 반응형 | 1440·1024·768에서 가로 스크롤 없음, 글자 세로 줄바꿈 없음 | DevTools 스크린샷 3폭 비교 |
| 성능 | Pretendard 로딩으로 FOIT 없음(`font-display: swap`), 번들 증가 < 1MB(가변 폰트 1종 woff2) | `npm run build` 산출물 크기 비교 |
| 호환 | 기존 vitest 상시 실패 9건/4파일 외 신규 실패 0건, `tsc` 기존 오류 210건 외 증가 0, eslint 기존 39건 외 증가 0 | 실행 결과 목록 diff |
| 의존성 | 신규 의존성은 `pretendard` 1개 | package.json diff |
| 모션 | 인터랙션 전환 150~200ms, 비사용자 트리거 애니메이션은 타이핑 인디케이터·스트리밍 커서 2종만 | 코드 리뷰 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] FR-01~FR-15 구현
- [ ] 공통 컴포넌트 7종 각각 단위 테스트(렌더·variant·disabled·aria) 작성·통과
- [ ] 채팅 관련 기존 테스트 11파일 통과(상시 실패 ChatPage TC-FE-2 제외)
- [ ] 1440/768 전후 스크린샷을 `assets/`에 보관
- [ ] `idt_front/CLAUDE.md` "UI 디자인 시스템" 절을 토큰·컴포넌트 기준으로 갱신(위키는 건드리지 않음)
- [ ] 콘솔 에러·네트워크 실패 0건(기존 401 2회는 원인 확인 후 별도 이슈로 기록)

### 4.2 Quality Criteria

- [ ] 채팅 화면 파일(위 11개 + AppSidebar)에서 `text-[` 임의 글자 크기 0건, hex 리터럴 0건(gradient는 토큰 변수 참조)
- [ ] 1차 버튼은 Button 컴포넌트만 사용(수기 `bg-violet-600` 0건)
- [ ] `outline-none` 사용 시 반드시 `focus-visible:` 대체 스타일 동반
- [ ] 신규 컴포넌트 테스트 커버리지 80% 이상
- [ ] `npm run build` 성공

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 채팅 스트리밍·첨부·도구 프리뷰 로직 회귀 | High | Medium | 로직 훅(useChatStream, useAgentRunStream)과 서비스는 수정 금지. 컴포넌트는 className·구조만 교체. 기존 11개 테스트 + 실서버 수동 전송 1회로 검증 |
| Tailwind v4 `@theme`와 기존 임의 클래스 충돌 | Medium | Low | 토큰 이름을 기존 Tailwind 팔레트와 겹치지 않게(`--color-brand-*`) 정의. 기존 zinc/violet 클래스는 그대로 동작 |
| 폰트 교체로 줄 높이·너비가 변해 다른 화면 레이아웃이 미세하게 틀어짐 | Medium | High | 전역 폰트는 의도된 변경. 채팅 외 화면은 깨짐 여부만 스크린샷 5장(스토어·컬렉션·작업·대시보드·사용자관리)으로 확인하고 수정은 후속 사이클 |
| LoadingButton·StatusBadge 래퍼 전환 시 사용처 29+6파일 깨짐 | High | Low | props 호환 유지, 기존 테스트 2파일로 검증 |
| 사이드바 접기 상태가 persist되어 사용자가 당황 | Low | Medium | 토글 버튼을 레일 최상단에 상시 노출, 툴팁 제공 |
| `App.css` 제거 시 어딘가에서 참조 | Low | Low | import 검색으로 0건 확인 후 삭제 |
| 범위 확장(다른 화면까지 손대고 싶어짐) | Medium | High | Out of Scope 명시. 키트 적용이 필요한 화면은 후속 사이클 목록에 추가만 한다 |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `src/index.css` | 전역 CSS | `@theme` 토큰, 폰트, reduced-motion, 포커스 규칙 추가 |
| `src/App.css` | 전역 CSS | 삭제(미사용) |
| `index.html` | HTML | `lang="ko"`, `<title>` 변경 |
| `package.json` | 의존성 | `pretendard` 추가 |
| `src/components/ui/*` | 신규 컴포넌트 | Button, IconButton, Input, Textarea, Tabs, PageHeader, Badge, EmptyState |
| `src/components/common/LoadingButton.tsx` | 컴포넌트 | 새 Button 래퍼로 내부 교체(props 유지) |
| `src/components/common/StatusBadge.tsx` | 컴포넌트 | 새 Badge 래퍼로 내부 교체(props 유지) |
| `src/store/layoutStore.ts` | Zustand | `isSidebarCollapsed`, `toggleSidebar` 추가. persist 키 `layout-preferences` 유지 |
| `src/components/layout/AppSidebar.tsx` | 레이아웃 | 접기 레일 + 토큰 적용 |
| `src/components/layout/AgentChatLayout.tsx` | 레이아웃 | 사이드바 폭 전환·768 오버레이 처리 |
| `src/components/layout/ChatHeader.tsx`, `ChatHistoryPanel.tsx` | 레이아웃 | 토큰·키트 적용 |
| `src/components/chat/*` (MessageList, MessageBubble, ChatInput, SourceCitation, TypingIndicator, MessageFeedback, ToolPreviewPanel, ExcelPreviewModal, MarkdownRenderer) | 컴포넌트 | 표현 레이어만 교체 |
| `src/pages/ChatPage/index.tsx` | 페이지 | 래퍼 구조·여백만 조정 |
| `idt_front/CLAUDE.md` | 문서 | 디자인 시스템 절 갱신 |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| `index.css` 전역 폰트 | READ | 전체 38개 페이지 | 글꼴 변경(의도). 레이아웃 깨짐 여부 5장 스크린샷 확인 |
| `LoadingButton` | READ | 29개 파일(관리자·빌더·스토어 모달 등) | props 유지로 None. 테스트 `LoadingButton.test.tsx` 통과 필요 |
| `StatusBadge` | READ | 6개 파일 | props 유지로 None |
| `layoutStore` | READ/UPDATE | `AgentChatLayout`, `AppSidebar`, `ChatHistoryPanel`, `ChatPage` | 필드 추가만. 기존 `isChatPanelOpen`·`selectedAgentId` 유지. persist된 구 상태는 새 필드 기본값으로 머지 |
| `AppSidebar` | READ | `AgentChatLayout` → 사용자 셸 25개 라우트 전체 | 접기 레일이 모든 사용자 화면에 보임. 폭 변경은 `flex-1` 본문이 흡수. `AppSidebar.test.tsx` 통과 필요 |
| `AgentChatLayout` `<main>` overflow 규칙 | READ | 하위 25개 페이지(CLAUDE.md 패턴 A/B) | 유지. 변경 없음 |
| `ChatInput` | READ | `ChatPage`만 | `ChatInput.background.test.tsx` 통과 필요 |
| `MessageBubble`·`MarkdownRenderer`·`SourceCitation` | READ | `MessageList`, `AgentRunDetailPage`(마크다운), `KnowledgeArticlePage`(마크다운) | 마크다운 렌더러 토큰 변경이 2개 관리자/지식 화면에도 반영됨. 깨짐 여부만 확인 |
| `ToolPreviewPanel`·`ExcelPreviewModal` | READ | `ChatPage` | 테스트 3파일 통과 필요 |
| `App.css` | READ | import 0건(확인 예정) | None |

### 6.3 Verification

- [ ] 위 소비처 전부에 대해 기존 테스트 실행 결과를 기준선과 diff
- [ ] 인증·권한 흐름(ProtectedRoute, authStore) 변경 없음 확인
- [ ] API 요청/응답·React Query 키·Zustand persist 키 변경 없음 확인

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| **Starter** | Simple structure | Static sites | ☐ |
| **Dynamic** | Feature-based modules, 외부 백엔드 연동 | Web apps with backend | ☑ |
| **Enterprise** | Strict layer separation | High-traffic systems | ☐ |

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 토큰 정의 방식 | Tailwind v4 `@theme` / 별도 CSS 변수 파일 / JS 테마 객체 | `@theme` in `index.css` | Tailwind 유틸리티 클래스(`bg-brand-600`)로 바로 쓰이고 CSS 변수로도 노출됨. 추가 빌드 설정 없음 |
| 폰트 | Pretendard npm / CDN / 시스템 | Pretendard Variable npm | 사내망·오프라인에서도 동일 렌더링, 가변 폰트 1파일 |
| 컴포넌트 위치 | `components/common` 확장 / `components/ui` 신설 | `components/ui` 신설 | common에는 라우트 가드·모달 등 기능 컴포넌트가 섞여 있음. 순수 표현 키트를 분리 |
| 기존 컴포넌트 호환 | 교체 / 래퍼 유지 | LoadingButton·StatusBadge 래퍼 유지 | 사용처 35파일 수정 없이 전환 |
| 사이드바 접기 상태 | 로컬 state / layoutStore persist | layoutStore persist | 페이지 이동 간 유지, 기존 persist 키 재사용 |
| 셸 통합 | 포함 / 분리 | 분리(후속) | 대표 화면 1개 범위 초과, 관리자 13개 라우트 영향 |
| 아이콘 | lucide-react 통일 / 기존 혼용 유지 | 신규 컴포넌트만 lucide-react | 이미 의존성 존재. 기존 인라인 SVG 교체는 범위 밖 |
| 다크 모드 | 지금 / 나중 | 나중 | 토큰은 다크 변형을 넣을 수 있게 이름만 의미 기반(`surface`, `on-surface`)으로 정의 |

### 7.3 Clean Architecture Approach

```
Selected Level: Dynamic

변경 범위 폴더:
src/
├── index.css                 ← @theme 토큰, 폰트, 전역 규칙
├── components/
│   ├── ui/                   ← 신설: Button, IconButton, Input, Textarea, Tabs, PageHeader, Badge, EmptyState (+ *.test.tsx)
│   ├── common/               ← LoadingButton, StatusBadge 래퍼화
│   ├── layout/               ← AppSidebar(접기), AgentChatLayout, ChatHeader, ChatHistoryPanel
│   └── chat/                 ← 표현 레이어 교체
├── store/layoutStore.ts      ← isSidebarCollapsed 추가
└── pages/ChatPage/index.tsx  ← 래퍼 조정
```

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- [x] `idt_front/CLAUDE.md`에 코딩·디자인 컨벤션 존재
- [ ] `docs/01-plan/conventions.md` 없음
- [x] ESLint 설정(`eslint.config.js`)
- [ ] Prettier 설정 없음
- [x] TypeScript 설정(`tsconfig.app.json`)

### 8.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| 토큰 네이밍 | 없음 | `--color-brand-{50..900}`, `--color-surface`, `--color-on-surface`, `--color-muted`, `--color-border`, `--color-success/warning/danger/info`, `--text-{xs..3xl}` 7단, `--radius-{md,xl,full}`, `--shadow-{sm,lg}` | High |
| 글자 크기 | 임의 px 혼용 | 채팅 범위에서 임의 `text-[Npx]` 금지, 토큰 7단만 | High |
| 컴포넌트 파일 | 규칙 있음(PascalCase, default export) | `components/ui/` 동일 규칙, props는 `interface`, 테스트 동반 | High |
| 포커스 | `outline-none` 남용 | `outline-none`은 `focus-visible:` 대체와 함께만 | High |
| 상수 export | 메모리 규칙: 컴포넌트 파일에서 런타임 상수 export 금지 | variant 맵은 컴포넌트 내부 const, 타입은 `src/types/ui.ts` | Medium |
| 아이콘 | 인라인 SVG·lucide 혼용 | 신규는 lucide-react, 크기 16/20 두 단계 | Medium |

### 8.3 Environment Variables Needed

없음(기존 `VITE_API_BASE_URL`, `VITE_WS_URL` 그대로).

### 8.4 Pipeline Integration

해당 없음(기존 PDCA 흐름만 사용).

---

## 9. Next Steps

1. [ ] Design 문서 작성(`/pdca design ui-redesign-chat`): 토큰 값 표, 컴포넌트 API, 채팅 화면 와이어(1440/768), 사이드바 레일 동작, 세션 가이드(Phase 1 / Phase 2 분할)
2. [ ] Phase 1 구현 후 공통 컴포넌트 테스트 통과 확인
3. [ ] Phase 2 구현 후 전후 스크린샷·Gap 분석
4. [ ] 후속 사이클 등록: `ui-redesign-shell`(셸 통합), `ui-redesign-admin-tables`(관리자 테이블), 화면별 적용

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-10-20 | 초안. 2026-10-20 UI 분석 결과와 사용자 결정(A안, 채팅 대표 화면, 셸 통합 분리, Pretendard npm, 768 + 사이드바 접기) 반영 | 배상규 |
