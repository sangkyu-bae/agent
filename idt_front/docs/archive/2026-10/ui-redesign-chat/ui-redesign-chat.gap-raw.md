# ui-redesign-chat Gap 분석 원문 (gap-detector 에이전트, 정적)

> 분석일: 2026-10-21. 작업 트리 기준(미커밋 변경 포함). 요약·판정은 `ui-redesign-chat.analysis.md` 참조.

## 1. 축별 점수

| 축 | 점수 | 산출 근거 |
|---|:---:|---|
| Structural | 98% | §11.1 파일 28개 모두 존재. App.css 삭제는 staged. §5.3 공개 props 모두 일치, 차이는 추가 prop뿐 |
| Functional | 92.9% | §5.4 체크리스트 28개 중 Met 24, Partial 4 → (24 + 4×0.5)/28 |
| Contract | 100% | 채팅 훅·서비스·queryKeys·authStore·chatPreferencesStore diff 0줄. layoutStore는 필드 추가만, persist 키 유지 |
| Static Overall | 96.8% | Structural×0.2 + Functional×0.4 + Contract×0.4 |

### 1.1 Structural 근거

| Design §11.1 항목 | 상태 | 근거 |
|---|:-:|---|
| index.html `lang="ko"`, title | ✅ | index.html:2, :7 |
| package.json + pretendard | ✅ | package.json:22 |
| index.css 토큰 + 전역 규칙 | ✅ | src/index.css:11-88, :112-127 |
| App.css 삭제, import 제거 | ✅ | `git diff --cached` 184줄 삭제, src 내 참조 0건 |
| types/ui.ts, utils/cn.ts(+test) | ✅ | types/ui.ts:3-38, utils/cn.ts:4 |
| ui 8종 + test 8종 | ✅ | components/ui/ 16개 파일 |
| LoadingButton / StatusBadge 래퍼 | ✅ | LoadingButton.tsx:14-16, StatusBadge.tsx:13-18 |
| AppSidebar(+토글 테스트) | ✅ | AppSidebar.tsx:167-173, AppSidebar.test.tsx:52-92 |
| AgentChatLayout, ChatHeader, ChatHistoryPanel | ✅ | AgentChatLayout.tsx:35-42, :174 / ChatHeader.tsx:16 / ChatHistoryPanel.tsx:22 |
| chat 9종 | ✅ | git status M |
| layoutStore(+test) | ✅ | layoutStore.ts:10, :14-15, :23, :27-28 |
| ChatPage 래퍼 클래스화 | ✅ | pages/ChatPage/index.tsx:391, :400-401 |
| CLAUDE.md 디자인 시스템 절 | ✅ | CLAUDE.md:153 토큰 표, :176 키트 절 |
| (추가) useMediaQuery(+test), ChatHistoryPanel.test | 추가 | 문서 반영 대상 |

§5.3 공개 API 대조: Button `unstyled` 추가, Input `size`·`wrapperClassName` 추가, Textarea `wrapperClassName` 추가, Tabs/PageHeader `className` 추가, EmptyState `iconUnstyled`·`className` 추가, MessageBubble named export `AssistantAvatar` 추가. 나머지 일치.

### 1.2 Functional 근거 (§5.4)

공통 키트 9/9 Met (Button.tsx:19-30,56-61 / IconButton.tsx:14-22,37,43 / Input.tsx:34-41,57-59,74 / Textarea.tsx:31,48-57,85-87 / Tabs.tsx:27-55,60,72-83 / PageHeader.tsx:24,29-30 / Badge.tsx:15-27,37 / EmptyState.tsx:32-39 / 테스트 30개).

채팅 1440: Met 12, Partial 2 — 빈 상태 제안 카드(G-01), ToolPreviewPanel 접힘 바(G-04).
채팅 768: Met 3, Partial 2 — 안내문 숨김(G-02), 버블 85%(G-03).

### 1.3 토큰 잔존 grep (채팅 범위, 테스트 제외)

| 패턴 | chat/* | layout 4종 | ui/* | ChatPage |
|---|:-:|:-:|:-:|:-:|
| `text-[N` | 0 | 0 | 0 | 0 |
| hex | 0 | 1 (AgentChatLayout.tsx:178) | 0 | 0 |
| 인라인 style | 1 (ChartRenderer 동적 height) | 2 (레이아웃 인라인; :178 background 위반) | 0 | 0 |
| zinc/violet/indigo | 0 | 0 | 0 | 0 |
| uppercase/tracking-widest | 0 | 0 | — | — |
| `rounded`(4px) | 1 | 4 | 0 | 0 |

### 1.4 Contract 근거

useChatStream·useAgentRunStream·useChat·services/**·queryKeys·authStore·chatPreferencesStore 변경 0줄. layoutStore +25/-1(필드 1·액션 2·헬퍼 1, persist 값 동일). Design §4 "필드 2개"는 표기 오류(실제 1개).

## 2. Gap 목록

Important: G-01 빈 상태 제안 카드 미노출(ChatPage/index.tsx:37-52,402 / MessageList.tsx:21-66).
Minor: G-02 안내문 `hidden sm:block`(ChatInput.tsx:165), G-03 버블 `sm:max-w-[75%]`(MessageBubble.tsx:16), G-04 ToolPreviewPanel 접힘(ToolPreviewPanel.tsx:28-34), G-05 첨부 제거 버튼 16px(ChatInput.tsx:83-90), G-06 `<main>` hex 배경(AgentChatLayout.tsx:178), G-07 배너 오류 톤(ChatPage/index.tsx:426-438), G-08 `rounded` 잔존(MarkdownRenderer.tsx:50, ChatHistoryPanel.tsx:125-126, AppSidebar.tsx:274-275), G-09 duration 토큰 문서(index.css), G-10 ChatHeader 핸들러 없음(ChatHeader.tsx:39-44, 기존).

확인됨(의도적 편차): SidebarItem 대체, StatusBadge T3 갱신, 폰트 main.tsx import, source(none)+@source, ChartRenderer·ExcelPreviewGrid 토큰화.

참고: `hasPersistedSidebarPreference`는 다른 layoutStore 액션이 한 번이라도 실행되면 true가 되어 ≤768 자동 접힘은 첫 진입에만 적용됨(Design 문구와 일치). Plan FR-07 `text-xl` vs Design `text-lg`(Design 따름), Plan `ring` vs Design `outline`(Design 따름).

## 3. FR 판정

FR-01~FR-15 전부 Met. 근거: index.css:13,23,25,31-32,36,39,47-48,112-127 / package.json:22 / main.tsx:6 / Button.tsx:19-30,56-70 / IconButton.tsx:7,15,37 / Input.tsx:34-36,59 / Textarea.tsx:43-45,87 / Tabs.tsx:27-74 / PageHeader.tsx:19-36 / Badge.tsx:12-39 / EmptyState.tsx:18-41 / LoadingButton.tsx:14-16 / StatusBadge.tsx:20-23 / AppSidebar.tsx:167-190 / layoutStore.ts:10,27-28 / AgentChatLayout.tsx:35-42 / ChatHistoryPanel.tsx:44-51,168-181.

## 4. Runtime Verification Plan

L1: refresh POST 200 + access_token; 세션 목록 GET 200.
L2: `npx vitest run src/components/ui` / cn·layoutStore·useMediaQuery / LoadingButton·StatusBadge / layout 3 test / `src/components/chat` / ChatPage 2 / 전체 `test:run` 기준선 diff / build·type-check·lint.
L3: 1440 전송·응답(제안 카드 G-01 판정), 768 초기 접힘·hScroll·툴바·안내문·버블 폭, 토글 persist, 히스토리 오버레이(left 112px), Tab 순회 포커스 링, 폰트, 다른 화면 5장, reduced-motion 에뮬레이션, 백그라운드 409 배너 톤, 스크린샷 `assets/`.

## 5. 다음 단계

Static Overall 96.8% ≥ 90%. Important 1건(G-01) 처리 방향 결정 후 L2/L3 실행 → report. G-02·G-03·G-06은 한 줄 수정, G-09와 문서 표기 차이는 문서 정정.
