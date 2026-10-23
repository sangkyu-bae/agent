# ui-redesign-chat Analysis Report

> **Analysis Type**: Gap Analysis (Design vs Implementation) + Runtime Verification
>
> **Project**: idt_front (sangplusbot)
> **Version**: 0.0.0
> **Analyst**: 배상규 (gap-detector 에이전트 정적 분석 + 런타임 검증)
> **Date**: 2026-10-21
> **Design Doc**: [ui-redesign-chat.design.md](ui-redesign-chat.design.md)
> **Plan Doc**: [ui-redesign-chat.plan.md](ui-redesign-chat.plan.md)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 디자인 토큰과 공통 컴포넌트가 없어 화면마다 스타일을 손으로 재작성하고, 결과가 화면마다 다르다 |
| **WHO** | 1차: 채팅 화면을 쓰는 전 사용자(P1 질문자, P2 KB 운영자). 2차: 이후 화면을 리디자인할 개발자 |
| **RISK** | 채팅 화면의 스트리밍·첨부·도구 프리뷰 로직을 건드려 기능 회귀가 생기는 것 |
| **SUCCESS** | 채팅 화면 전역에서 임의 px 글자 크기 0건, 1차 버튼은 Button 컴포넌트만 사용, 포커스 링 가시, 보조 텍스트 대비 4.5:1 이상, 1440/768 스크린샷에서 겹침·세로 줄바꿈 없음, 기존 vitest 통과 |
| **SCOPE** | Phase 1 토큰·폰트·공통 컴포넌트 키트 → Phase 2 채팅 화면 적용(사이드바 접기 포함) |

---

## Strategic Alignment Check

### Plan Alignment

| 요소 | 기대 | 구현 상태 |
|------|------|:---------:|
| 핵심 문제(WHY) | 토큰·키트 부재 해소 | ✅ `index.css` `@theme` 토큰 + `components/ui` 8종 |
| 대상(WHO) | 채팅 사용자, 후속 개발자 | ✅ 채팅 화면 적용 완료, CLAUDE.md 갱신 |
| 핵심 가치 | 후속 화면 리디자인을 반복 작업으로 | ✅ 키트·토큰·규칙 문서화 |
| 위험 완화 | 로직 훅·서비스 미수정 | ✅ `git diff` 0줄 (Contract 100%) |

### Success Criteria Status (Plan §4)

| # | 기준 | 상태 | 근거 |
|---|------|:----:|------|
| SC-1 | FR-01~FR-15 구현 | ✅ | §3 FR 표 15/15 Met |
| SC-2 | 공통 컴포넌트 7종 단위 테스트 통과 | ✅ | `src/components/ui/*.test.tsx` 30건 통과 (L2 #1) |
| SC-3 | 채팅 기존 테스트 11파일 통과(TC-FE-2 제외) | ✅ | L2 #5·#6 통과, TC-FE-2만 상시 실패 |
| SC-4 | 1440/768 전후 스크린샷 보관 | ⚠️ | 스크린샷은 세션 임시 경로에만 있음. `assets/` 미생성 |
| SC-5 | CLAUDE.md 디자인 시스템 절 갱신 | ✅ | CLAUDE.md:147~ 토큰·키트·레이아웃 규칙 |
| SC-6 | 콘솔 에러·네트워크 실패 0 | ⚠️ | 5174 검증 서버는 CORS로 API 전부 차단. 5173 서버는 재시작 전이라 미확인 |
| SC-7 | 채팅 범위 임의 px 0, hex 0 | ✅ | grep 0건 (Plan 지정 12파일). 목록 밖 `AgentChatLayout:178`에 `#fff` 1건 (G-06) |
| SC-8 | 1차 버튼 Button만 사용 | ✅ | 채팅 범위 `bg-violet-600` 수기 0건 |
| SC-9 | `outline-none` 시 focus-visible 대체 | ✅ | 전역 `:focus-visible` 규칙 (`index.css:112`) |
| SC-10 | 신규 컴포넌트 커버리지 80% | ⚠️ | `@vitest/coverage-v8` 미설치로 측정 불가. 테스트 수(30건)로 대체 판단 |
| SC-11 | `npm run build` 성공 | ✅ | 4.85s 빌드 성공 |

**Success Rate**: 8/11 Met, 3 Partial (측정 환경 제약)

### Decision Record Verification

| Source | Decision | Followed? | Deviation |
|--------|----------|:---------:|-----------|
| [Plan] | A안 유지, 채팅 1화면, 셸 통합 분리 | ✅ | 없음 |
| [Plan] | Pretendard npm, 768 + 사이드바 접기 | ✅ | 폰트 CSS는 `main.tsx`에서 import (Tailwind 파서 제약) |
| [Design] | Option C: ui 키트 + 래퍼 호환 | ✅ | 없음 |
| [Design] | 토큰은 `@theme` 한 곳 | ✅ | `--duration-*` 토큰은 Tailwind v4 네임스페이스에 없어 미정의 (G-09, 문서 정정 대상) |
| [Design] | 사이드바 레일은 IconButton | ⚠️ | 다크 표면용 `SidebarItem`으로 대체 (Do 단계에서 보고된 의도적 편차) |

---

## 1. Analysis Overview

### 1.1 Analysis Purpose

Design §5.3·§5.4·§5.5 및 Plan §3·§4 대비 구현 일치도를 정적(구조·기능·계약)과 런타임(L1·L2·L3)으로 측정하고 Gap을 분류한다.

### 1.2 Analysis Scope

- **Design Document**: `docs/02-design/features/ui-redesign-chat.design.md`
- **Implementation Path**: `src/index.css`, `src/components/ui/`, `src/components/layout/`, `src/components/chat/`, `src/pages/ChatPage/`, `src/store/layoutStore.ts`, `src/hooks/useMediaQuery.ts`
- **Analysis Date**: 2026-10-21
- **정적 분석 원문**: `docs/03-analysis/ui-redesign-chat.gap-raw.md`

---

## 2. Gap Analysis (Design vs Implementation)

### 2.1 API Endpoints

API 변경 없음(Design §4). 채팅 훅·서비스·queryKeys·authStore·chatPreferencesStore `git diff` 0줄. `layoutStore`는 필드 1개·액션 2개·헬퍼 1개 추가, persist 키 `layout-preferences` 유지.

### 2.2 Data Model

| Field | Design | Impl | Status |
|-------|--------|------|--------|
| `layoutStore.isSidebarCollapsed` | boolean, 기본 false | `layoutStore.ts:10,23` | ✅ |
| `toggleSidebar`, `setSidebarCollapsed` | 액션 2개 | `layoutStore.ts:27-28` | ✅ |
| `types/ui.ts` BUTTON_VARIANT·CONTROL_SIZE·BADGE_TONE·TabItem | as const + 타입 | `types/ui.ts:3-38` | ✅ (ICON_BUTTON_TONE 추가) |

### 2.3 Component Structure

| Design Component | Implementation File | Status |
|------------------|---------------------|--------|
| ui 8종 (Button, IconButton, Input, Textarea, Tabs, PageHeader, Badge, EmptyState) | `src/components/ui/*.tsx` + test 8 | ✅ |
| LoadingButton·StatusBadge 래퍼 | `src/components/common/` | ✅ |
| AppSidebar(접기), AgentChatLayout, ChatHeader, ChatHistoryPanel(overlay) | `src/components/layout/` | ✅ |
| chat 9종 | `src/components/chat/` | ✅ (+ ChartRenderer, ExcelPreviewGrid 추가 토큰화) |
| ChatPage 래퍼 | `src/pages/ChatPage/index.tsx` | ✅ |
| useMediaQuery(+test), ChatHistoryPanel.test, layoutStore.test | Design 미기재 추가 | 문서 반영 대상 |

공개 props는 모두 Design과 일치하거나 상위 호환(추가 prop: Button `unstyled`, Input `size`·`wrapperClassName`, EmptyState `iconUnstyled`·`className`, Tabs/PageHeader `className`).

**Structural Match Rate**: 98%

### 2.4 Functional Depth Analysis

| File | Depth | Placeholder | 비고 |
|------|:-----:|-------------|------|
| `components/ui/*` 8종 | 100 | 없음 | 테스트 30건 |
| `AppSidebar.tsx` | 100 | 없음 | 레일·토글·aria 완비 |
| `ChatHistoryPanel.tsx` | 100 | 없음 | overlay·ESC·백드롭 |
| `ChatHeader.tsx` | 80 | 다운로드·삭제 onClick 없음 | 리디자인 전부터 핸들러 없던 placeholder (G-10) |
| `ChatInput.tsx` | 90 | 없음 | 안내문 브레이크포인트, 제거 버튼 크기 (G-02, G-05) |
| `ChatPage/index.tsx` | 80 | 빈 상태에 제안 카드 없음 | G-01 |
| `ToolPreviewPanel.tsx` | 90 | 접힘 상태가 바 형태 아님 | G-04 |

**Shallow File Count**: 0 / 32

### 2.5 Page UI Checklist Verification (Design §5.4)

| Page | Design Elements | Met | Partial | Missing | Rate |
|------|:--------------:|:---:|:-------:|:-------:|:----:|
| 공통 키트 | 9 | 9 | 0 | 0 | 100% |
| 채팅 1440 | 14 | 12 | 2 | 0 | 92.9% |
| 채팅 768 | 5 | 3 | 2 | 0 | 80% |

**Functional Match Rate**: (24 + 4×0.5) / 28 = **92.9%**

### 2.6 API Contract Verification

| # | 대상 | Design | 구현 | Contract |
|---|------|:------:|:----:|:--------:|
| 1 | 채팅 훅 3종·서비스·queryKeys | 변경 없음 | diff 0줄 | PASS |
| 2 | authStore·chatPreferencesStore | 변경 없음 | diff 0줄 | PASS |
| 3 | layoutStore persist 키 | `layout-preferences` 유지 | `STORAGE_KEY` 상수, 값 동일 | PASS |

**Contract Match Rate**: 3/3 = **100%**

### 2.7 Runtime Verification Results

#### L1: API (curl, 백엔드 8000)

| # | Test | Expected | Actual | Pass |
|---|------|----------|--------|:----:|
| 1 | `POST /api/v1/auth/refresh` | 200, `access_token` | 200, 존재 | ✅ |
| 2 | 세션 목록 GET (인증) | 200 | 200, `{user_id, agent_id, sessions}` | ✅ |

**L1 Score**: 2/2 = 100%
(관찰: 세션 목록이 인증 헤더 없이도 200을 반환함. 이 기능 범위 밖의 백엔드 사항으로 별도 기록)

#### L2: vitest

| # | 대상 | 결과 | Pass |
|---|------|------|:----:|
| 1 | `src/components/ui` | 8파일 30건 통과 | ✅ |
| 2 | cn·layoutStore·useMediaQuery | 통과 | ✅ |
| 3 | LoadingButton·StatusBadge | 통과 (T3 토큰 단언) | ✅ |
| 4 | AppSidebar·ChatHeader·ChatHistoryPanel | 통과 (C1~C3 포함) | ✅ |
| 5 | `src/components/chat` 11파일 | 통과 | ✅ |
| 6 | ChatPage 2파일 | TC-FE-2 1건만 실패(상시 실패) | ✅ |
| 7 | 전체 `vitest run` | 10 실패 / 5파일. 기준선 9건 + SubAgentManagerModal 1건(단독 실행 6/6 통과, 병렬 부하) | ✅ |
| 8 | build / tsc / eslint | 성공 / 210(기준선) / 신규 0 | ✅ |

**L2 Score**: 8/8 = 100%

#### L3: 브라우저 (Chrome DevTools MCP, 임시 5174 서버. CORS로 API 차단되어 데이터 없는 상태)

| # | Scenario | Result | Pass |
|---|----------|--------|:----:|
| 1 | 1440 채팅 전송·응답 | 빈 상태·헤더·입력창 렌더 확인. 전송은 CORS로 불가 | ⚠️ 부분 |
| 2 | 768(740) 초기 접힘, 가로 스크롤 | 64px 레일, hScroll false, 툴바 한 줄 | ✅ |
| 3 | 사이드바 토글 persist | 64px, `isSidebarCollapsed: true` 저장 | ✅ |
| 4 | 히스토리 오버레이 | left 112px, w 288, 백드롭 존재 | ✅ |
| 5 | 키보드 Tab 순회 포커스 링 | 미실행 | ❌ |
| 6 | 폰트 | `"Pretendard Variable"`, 8 face 로드 | ✅ |
| 7 | 다른 화면 회귀 5장 | 깨짐 없음 | ✅ |
| 8 | reduced-motion | 미실행 | ❌ |
| 9 | 백그라운드 배너 409 | 미실행 | ❌ |

**L3 Score**: 5.5/9 = 61%

**Runtime Match Rate**: 100×0.4 + 100×0.3 + 61×0.3 = **88.3%**

### 2.8 Match Rate Summary

```
┌─────────────────────────────────────────────┐
│  Structural Match Rate:   98.0%              │
│  Functional Match Rate:   92.9%              │
│  Contract Match Rate:    100.0%              │
│  Runtime Match Rate:      88.3%              │
│  ─────────────────────────────────────────── │
│  Overall Match Rate:      93.8%              │
│  = (98×0.15) + (92.9×0.25) + (100×0.25)      │
│    + (88.3×0.35)                             │
├─────────────────────────────────────────────┤
│  ✅ Match:           24 items (85.7%)        │
│  ⚠️ Partial:          4 items (14.3%)        │
│  ❌ Not implemented:  0 items (0%)           │
└─────────────────────────────────────────────┘
```

### 2.9 Gap 목록

| ID | 심각도 | 내용 | 위치 | 권장 조치 |
|----|:------:|------|------|-----------|
| G-01 | Important | /chatpage 빈 상태에 제안 카드 없음. `EmptyAgentState`가 그려지고 `MessageList.EmptyMessages`(제안 카드)는 실행 불가 경로 | `ChatPage/index.tsx:37-52,402` / `MessageList.tsx:21-66` | `EmptyAgentState`에 제안 카드를 children으로 넘기고 `handleSend` 연결, MessageList의 사용 불가 빈 상태 제거 |
| G-02 | Minor | 768에서 입력 안내문이 보임 (`hidden sm:block`) | `ChatInput.tsx:165` | `hidden lg:block` |
| G-03 | Minor | 768에서 유저 버블 최대 폭 75% (`sm:max-w-[75%]`) | `MessageBubble.tsx:16` | `lg:max-w-[75%]` |
| G-04 | Minor | ToolPreviewPanel 접힘 상태가 ghost Button 한 줄 | `ToolPreviewPanel.tsx:28-34` | Design 정정(접힘은 버튼) 또는 바 형태 |
| G-05 | Minor | 첨부 칩 제거 버튼 16px 히트 영역 | `ChatInput.tsx:83-90` | 히트 영역 확장 |
| G-06 | Minor | `<main>` 인라인 `background: '#fff'` | `AgentChatLayout.tsx:178` | `className="bg-surface"` |
| G-07 | Minor | 백그라운드 배너 오류 안내도 info 톤 + 스피너 | `ChatPage/index.tsx:426-438` | 오류 시 danger 톤·스피너 숨김 |
| G-08 | Minor | 3단 밖 `rounded`(4px) 잔존 | `MarkdownRenderer.tsx:50`, `ChatHistoryPanel.tsx:125`, `AppSidebar.tsx:274` | `rounded-md` |
| G-09 | Minor | Design의 `--duration-*` 토큰은 Tailwind v4에 네임스페이스 없음 | Design §5.0 | 문서 정정 (`duration-150/200`) |
| G-10 | Minor | ChatHeader 다운로드·삭제 onClick 없음(리디자인 전부터) | `ChatHeader.tsx:39-44` | 별도 이슈 |

---

### 2.10 Act 반복 1회 결과 (2026-10-21)

Checkpoint 5에서 "지금 모두 수정"을 선택해 다음을 반영했다.

| ID | 처리 | 변경 |
|----|------|------|
| G-01 | 수정 | `MessageList.tsx` `SuggestionCards` named export 신설, `ChatPage` `EmptyAgentState`가 children으로 받아 `handleSend` 연결. 브라우저에서 제안 카드 4개 렌더 확인(`assets/after-fix-chat-1440.png`) |
| G-02 | 수정 | 안내문 `hidden lg:block` |
| G-03 | 수정 | 유저 버블 `lg:max-w-[75%]` |
| G-04 | 문서 정정 | Design §5.1·§5.4: 접힘 상태는 ghost Button |
| G-05 | 수정 | 첨부 제거 버튼 24px 히트 영역 |
| G-06 | 수정 | `AgentChatLayout` `<main>` `className="bg-surface"` |
| G-07 | 수정 | `bgNoticeIsError` 상태 추가. 오류 안내는 danger 톤 + `role="alert"` + 경고 아이콘, 접수 안내는 info 톤 + 스피너 |
| G-08 | 수정 | `rounded` 5곳 → `rounded-md` |
| G-09 | 문서 정정 | Design §5.0 duration 토큰 제거, `duration-150/200` 명시 |
| G-10 | 이월 | 리디자인 전부터 핸들러 없던 placeholder. 별도 이슈 |
| 기타 | 문서 정정 | Design §4 필드 수, §5.3·§5.4 SidebarItem·ChatInput variant·제안 카드 4개, §11.1 useMediaQuery·ChatHistoryPanel.test 추가. Version 0.2 |

재검증: 채팅·레이아웃 테스트 20파일 112건 통과(TC-FE-2 제외), tsc 신규 0, eslint 신규 0(경고 4건은 기존), build 성공, 1440 가로 스크롤 없음, `:focus-visible` outline 규칙 적용 확인.

```
┌─────────────────────────────────────────────┐
│  Structural Match Rate:   98.0%              │
│  Functional Match Rate:  100.0%  (28/28)     │
│  Contract Match Rate:    100.0%              │
│  Runtime Match Rate:      88.3%  (L3 미실행 3건)│
│  ─────────────────────────────────────────── │
│  Overall Match Rate:      95.6%              │
└─────────────────────────────────────────────┘
```

### 2.11 QA 런타임 추가 실행 (2026-10-21, 5173 dev 서버 재시작 후)

| # | Scenario | Result | Pass |
|---|----------|--------|:----:|
| 1 | 1440 채팅 전송·응답 | 제안 카드 클릭 → 유저 버블 → 스트리밍 커서 + 타이핑 인디케이터 → 200자 답변(마크다운 목록) → 피드백 IconButton 2개. 헤더 메시지 수 Badge "2". 가로 스크롤 없음 (`qa-chat-sending-1440.png`, `qa-chat-answered-1440.png`). 출처 칩은 일반 채팅이라 미노출 | ✅ |
| 5 | 키보드 Tab 순회 | Tab 3회 후 `activeElement`="새 에이전트", `:focus-visible` true, outline solid `rgb(124,58,237)` (`qa-focus-ring-1440.png`). 인터랙티브 23개 전부 포커스 가능 | ✅ |
| 8 | reduced-motion | 에뮬레이션 켜면 상태 dot `animation-duration: 1e-05s`, iteration 1, 사이드바·버튼 `transition-duration: 1e-05s` | ✅ |
| 9 | 백그라운드 409 배너 | 테스트 계정에 등록된 에이전트가 없어 백그라운드 전송 경로를 열 수 없음. 코드 분기(`bgNoticeIsError`)는 단위 수준으로만 확인 | ⏳ 미실행 |

콘솔: 401 2건(`/jobs`, `/agents/my`)은 토큰 갱신 전에 먼저 나간 요청이며 갱신 후 200으로 재요청됨. 리디자인 전부터 있던 초기화 순서 문제로 별도 이슈.

**L3 Score**: 8/9 = 88.9% → Runtime = 100×0.4 + 100×0.3 + 88.9×0.3 = **96.7%**
**Overall Match Rate** = 98×0.15 + 100×0.25 + 100×0.25 + 96.7×0.35 = **98.5%**

---

## 3. Code Quality Analysis

| Type | File | 내용 | 심각도 |
|------|------|------|:------:|
| Dead path | `MessageList.tsx` | `EmptyMessages`가 ChatPage 경로에서 실행되지 않음 (G-01과 동일 원인) | 🟡 |
| Pre-existing | `ChatPage/index.tsx:259,291,304` | eslint 경고 3건, 리디자인 전부터 | 🟢 |
| Pre-existing | `AgentChatLayout.tsx:109` | exhaustive-deps 경고, 리디자인 전부터 | 🟢 |

보안 이슈 없음(입력 검증·인증 경로·sanitize 로직 미변경).

---

## 5. Test Coverage

| Area | 상태 |
|------|------|
| 신규 테스트 | ui 8파일 30건, cn 4건, layoutStore 4건, useMediaQuery 2건, ChatHistoryPanel 4건, AppSidebar +3건 |
| 수치 커버리지 | `@vitest/coverage-v8` 미설치로 미측정. 설치 후 `npm run coverage`로 확인 필요 |

---

## 6. Clean Architecture Compliance

| Layer | 기대 | 실제 | Status |
|-------|------|------|:------:|
| `components/ui` | types/ui, lucide-react, react만 | 동일 (`@/utils/cn` 추가) | ✅ |
| `components/common` 래퍼 | ui, types | 동일 | ✅ |
| `components/layout`·`chat` | ui, common, hooks, store, types | 동일. 서비스 직접 호출 없음 | ✅ |

**Architecture Compliance**: 100% (32/32 파일 설계 레이어 일치)

---

## 7. Convention Compliance

| 항목 | 결과 |
|------|------|
| 컴포넌트 PascalCase·arrow·default export | ✅ |
| 런타임 상수는 컴포넌트 내부 const, 공유는 `types/ui.ts` | ✅ |
| 채팅 범위 `text-[Npx]` 0 | ✅ |
| hex·인라인 배경 0 | ⚠️ G-06 1건(범위 경계) |
| 포커스: 전역 `:focus-visible`, 개별 `focus:` 미추가 | ✅ (Input `focus:border`는 Design 명시) |
| 테스트 동반 | ✅ |

---

## 8. 미완료 산출물·후속

- 스크린샷 폴더 `assets/` 생성 (현재 세션 임시 경로에 after-m1·m3·m4 10장)
- 5173 dev 서버 재시작 후 L3 #1(실제 전송·스트리밍·출처 칩), #5(키보드), #8(reduced-motion), #9(409 배너) 실행
- Design 문서 정정: §4 "필드 2개"→1개, §5.0 duration 토큰, §5.3 IconButton→SidebarItem(다크), §5.4 제안 카드 수, 추가 파일(useMediaQuery 등)
- 백엔드 관찰: 세션 목록 엔드포인트가 비인증 요청에도 200 (범위 밖, 별도 이슈)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-10-21 | 초안. 정적 96.8% + 런타임 88.3% → Overall 93.8%, Gap 10건(Important 1) | 배상규 |
| 0.2 | 2026-10-21 | Act 1회: G-01~G-03·G-05~G-08 수정, G-04·G-09 문서 정정, G-10 이월 → Overall 95.6% | 배상규 |
| 0.3 | 2026-10-21 | QA 런타임 3건 추가 통과(전송·스트리밍, 키보드 포커스, reduced-motion) → Overall 98.5%. 409 배너는 에이전트 미등록으로 미실행 | 배상규 |
