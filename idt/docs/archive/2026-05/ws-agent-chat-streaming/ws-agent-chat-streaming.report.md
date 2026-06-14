# WebSocket Agent Chat Streaming — Completion Report

> **Summary**: 사용자 정의 agent(UUID)를 ChatPage에서 WebSocket 토큰 스트리밍으로 전환. 백엔드 변경 0, FE 통합 완료(신규 9 tests + 기존 34 회귀), 98% match rate, 3번째 표준 패턴 적용으로 반나절 완성.
>
> **Project**: sangplusbot (idt + idt_front)
> **Version**: 1.0
> **Author**: 배상규
> **Date**: 2026-05-25
> **Status**: Complete
> **PDCA Cycle**: 1

---

## Executive Summary

### 1.1 Project Overview

| Field | Value |
|-------|-------|
| **Feature** | WebSocket Agent Chat Streaming — ChatPage 사용자 정의 agent UX 통합 |
| **Start Date** | 2026-05-25 |
| **End Date** | 2026-05-25 |
| **Duration** | 0.5 day (반나절) |
| **Owner** | 배상규 |
| **Related Tasks** | `[Design] ws-agent-chat-streaming`, `[Do] ws-agent-chat-streaming`, `[Check] ws-agent-chat-streaming` |

### 1.2 Results Summary

| Metric | Value |
|--------|-------|
| **Design Match Rate** | 98% |
| **Functional Requirements** | 9/9 DONE (0 PARTIAL, 0 MISSING) |
| **Design Sections** | 6/6 DONE |
| **Backend Changes** | 0 (인프라 재사용) |
| **Files Added** | 3 (agentStepToToolEvent.ts + 2 test files) |
| **Files Edited** | 3 (ChatPage/index.tsx + 2 existing test files) |
| **Lines Added/Modified** | ~282 (ChatPage) + ~22 (helper) + ~121 (tests) |
| **Frontend Tests** | 43/43 passed (신규 9 + 기존 34) |
| **Gaps** | 0 blocker/major/minor gaps |
| **Open Questions** | 3/3 answered and honored (Q1 mutex, Q2 tool filter, Q3 dead code preservation) |

### 1.3 Value Delivered

| Perspective | Content | Evidence |
|---|---|---|
| **Problem** | 사용자 정의 agent(UUID)는 ChatPage에서 HTTP `POST /api/v1/agents/{id}/run`으로 호출되어 token 단위 진행 표시·도구 호출 가시성이 없고, SUPER agent만 WS로 전환된 결과 UX 불일치 발생. 백엔드/hook 인프라는 이미 완성되었지만 ChatPage 통합이 누락됨. | `docs/01-plan/features/ws-agent-chat-streaming.plan.md:17` — gap 명시; `docs/02-design/features/ws-agent-chat-streaming.design.md:20` — 직전 사이클 결과 보존 |
| **Solution** | ChatPage의 사용자 정의 agent 분기를 `useAgentChat` mutation → `useAgentRunStream` hook으로 교체. `runId`는 client UUID로 생성, `/ws/agent/{run_id}` 엔드포인트과 `RunAgentUseCase.stream()`을 재사용. 단일 `activeStream` 상태로 두 hook을 enabled gating으로 관리하여 mutex 보장. 백엔드 변경 0, 신규 컴포넌트 0(ToolPreviewPanel 재사용). | `idt_front/src/pages/ChatPage/index.tsx:41-56` ActiveStream 타입; `:226-234` handleSend agent branch; `idt_front/src/hooks/agentStepToToolEvent.ts:13-21` helper |
| **Function/UX Effect** | 사용자 정의 agent 실행도 SUPER와 동일하게 placeholder → token → final answer 진행, tool 호출 `ToolPreviewPanel`에 표시. ChatPage 전체(general/SUPER/사용자 정의 agent) 3개 분기가 단일 WS transport로 통일. 사용자가 agent 타입 관계없이 일관된 스트리밍 UX 경험. | `analysis.md:25-35` FR-03~04 검증; `agentStepToToolEvent.test.ts:11-50` 5 test cases; `streamRouting.test.tsx:136-193` 4 test cases 통합 routing 검증 |
| **Core Value** | fe-websocket-integration-guide 표준 패턴 **3번째 적용 + 반나절 완성** — 가이드의 5단계 절차(§2)를 그대로 따르되, 백엔드 인프라 재사용(step 1-3)으로 시간 단축. 직전 두 사이클(agent-run 1일, chat-streaming 1일)의 가이드 효과를 재실증하고, 다음 WebSocket 적용(예: 인제스트 진행률)의 템플릿 확보. | `docs/guides/websocket-integration.md:227` 3번째 row: "반나절 적용" 기록; `docs/01-plan/features/ws-agent-chat-streaming.plan.md:209` 직전 사이클 대비 1/3 시간 단축 예측 달성 |

---

## 1. Summary

### 1.1 What Changed

본 사이클은 ChatPage에서 사용자 정의 agent(UUID)도 WebSocket으로 동작하도록 FE 통합을 완료했다.

#### 구현 범위 (FE only)
1. **Helper**: `agentStepToToolEvent.ts` (~22줄) — `AgentRunStep[]` → `ChatToolEvent[]` 변환, tool만 필터링
2. **ChatPage 전체 재구성**: 단일 `activeStream` mutex + `useChatStream` + `useAgentRunStream` + `view` useMemo 패턴
3. **테스트**: 신규 5+4 cases (helper + routing) + 기존 34 회귀 유지
4. **문서**: 가이드 §8에 3번째 적용 사례 1줄 추가

#### 백엔드: 변경 0
- `/ws/agent/{run_id}` 엔드포인트: fe-websocket-integration-guide 자산 그대로
- `RunAgentUseCase.stream()`: agent-run-streaming-sse 자산 그대로
- `AgentRunEventWsAdapter`: 재사용
- `SubscribeAgentRunPayload`: 재사용

### 1.2 Design-Implementation Alignment

- **Match Rate**: **98%** (analysis.md:14 — 즉시 `/pdca report` 진행 권장)
- **FR Coverage**: 9/9 완료 (analysis.md:24-36 per-FR matrix)
- **Design Sections**: 6/6 완료 (analysis.md:40-47 per-section coverage)
- **Open Questions**: Q1 mutex, Q2 tool filter, Q3 dead code — 모두 Design 명시 대로 구현 (analysis.md:49-55)

### 1.3 Process Summary

| Phase | 기간 | 산출물 |
|-------|------|--------|
| **Plan** | 2026-05-25 | `ws-agent-chat-streaming.plan.md` — 이미 완료된 인프라 재사용, 5단계 중 4-5만 수행 |
| **Design** | 2026-05-25 | `ws-agent-chat-streaming.design.md` — Q1/Q2/Q3 답변 반영, 단일 `activeStream` 패턴 결정 |
| **Do** | 2026-05-25 | FE 통합 + 9 신규 tests 작성, 백엔드 무터치, 타입체크/회귀 통과 |
| **Check** | 2026-05-25 | `ws-agent-chat-streaming.analysis.md` — 98% match rate, 0 gaps, 즉시 report 진행 |
| **Act** | 이 보고서 | 완료 보고서, 러닝 학습 기록 |

---

## 2. Related Documents

| 단계 | 문서 | 경로 |
|-----|------|------|
| Plan | `ws-agent-chat-streaming.plan.md` | `docs/01-plan/features/` |
| Design | `ws-agent-chat-streaming.design.md` | `docs/02-design/features/` |
| Analysis | `ws-agent-chat-streaming.analysis.md` | `docs/03-analysis/` |
| Guide | WebSocket Integration — §8 기록 | `docs/guides/websocket-integration.md:227` |
| Context | 직전 사이클 archive | `docs/archive/2026-05/fe-websocket-integration-guide/`, `docs/archive/2026-05/ws-chat-streaming/` |

---

## 3. Completed Items

### 3.1 Functional Requirements (9/9)

| FR | Requirement | Status | Evidence |
|----|-------------|--------|----------|
| FR-01 | ChatPage 사용자 정의 agent가 `useAgentRunStream` 사용 | ✅ DONE | `ChatPage/index.tsx:10` import; `:109-115` hook call; `:226-234` handleSend agent branch |
| FR-02 | `useChatStream`과 `useAgentRunStream` 중 하나만 활성 (enabled gating) | ✅ DONE | `:106` (`enabled: kind === 'chat'`) + `:114` (`enabled: kind === 'agent'`); `streamRouting.test.tsx:176-194` 검증 |
| FR-03 | Placeholder가 token으로 점진 갱신, final answer로 교체 | ✅ DONE | `:166-173` token effect; `:185-198` final answer effect |
| FR-04 | Tool 호출이 `ToolPreviewPanel`에 표시 | ✅ DONE | `:135` helper 호출; `:269-277` panel render with `view?.toolEvents` |
| FR-05 | `agent_run_failed` 에러 메시지 표시 | ✅ DONE | `:180-184` error formatting |
| FR-06 | `isPending` = active and not done | ✅ DONE | `:142` calculation |
| FR-07 | SUPER agent WS 흐름 무회귀 | ✅ DONE | `:226,235-243` SUPER falls through to chat; `streamRouting.test.tsx:136-153` explicit case |
| FR-08 | `useAgentChat` 정의 보존, ChatPage import만 제거 | ✅ DONE | `hooks/useChat.ts:52-63` mutation still exported; `ChatPage/index.tsx:8` 미포함 |
| FR-09 | `ChatPageIntegration.test.tsx` I3 갱신 | ✅ DONE | `:97-111` — transport-agnostic assertion |

### 3.2 Design Sections (6/6)

| Section | Item | Status | Evidence |
|---------|------|--------|----------|
| §3.1 | `ActiveStream` discriminated union | ✅ DONE | `ChatPage/index.tsx:41-56` |
| §3.2 | `agentStepsToToolEvents` helper (Q2 tool filter) | ✅ DONE | `agentStepToToolEvent.ts:13-21` |
| §3.3 | `view` useMemo normalize both streams | ✅ DONE | `ChatPage/index.tsx:118-140` |
| §4 | ChatPage changes (imports, hooks, handleSend, effects) | ✅ DONE | §4.1-4.5 all implemented |
| §5 | Test strategy (helper 5 + routing 4 + I3 update) | ✅ DONE | 모두 구현 및 통과 |
| §8 | Implementation order (including guide §8 row) | ✅ DONE | `guides/websocket-integration.md:227` row added |

### 3.3 Open Question Decisions (3/3)

| Q | Design 답변 | 구현 | Evidence |
|---|-----------|------|----------|
| **Q1** | 한 번에 하나 stream만 활성 | `activeStream` mutex + enabled gating + `isPending` early return | `index.tsx:204` + `streamRouting.test.tsx:188-193` |
| **Q2** | Tool만 표기 (node 제외) | `filter((s) => s.kind === 'tool')` | `agentStepToToolEvent.ts:15` + test `:11-20` |
| **Q3** | `useAgentChat` 정의 보존 | mutation 유지, ChatPage import만 제거 | `hooks/useChat.ts:52-63` 유지, `ChatPage/index.tsx:8` 제거 |

### 3.4 File Changes

#### New Files
- `idt_front/src/hooks/agentStepToToolEvent.ts` (~22줄) — pure helper
- `idt_front/src/hooks/agentStepToToolEvent.test.ts` — 5 test cases
- `idt_front/src/pages/ChatPage/__tests__/streamRouting.test.tsx` — 4 test cases

#### Edited Files
- `idt_front/src/pages/ChatPage/index.tsx` — 282줄 full rewrite (단일 `ActiveStream` mutex + 두 stream hook + `view` useMemo)
  - 제거: `useAgentChat` import 1줄
  - 추가: `useAgentRunStream` import, `agentStepsToToolEvents` import
  - 변경: `activeStream` state + 두 hook 호출 + view 분기 + handleSend + effects
- `idt_front/src/__tests__/components/ChatPageIntegration.test.tsx` — I3 갱신 (transport-agnostic)
- `idt/docs/guides/websocket-integration.md` — §8 적용 사례 메모 3번째 row 추가

#### No Backend Changes
- `idt/src/api/routes/ws_router.py`: 미터치
- `idt/src/application/agent_builder/run_agent_use_case.py`: 미터치 (design 원칙 준수)
- `idt/src/infrastructure/agent_run/ws_adapter.py`: 재사용
- `idt/src/api/routes/ws_schemas.py`: 재사용

---

## 4. Pending / Deferred Items

### 4.1 Out of Scope (Plan §2.2 선언)

| Item | Reason | Follow-up |
|------|--------|-----------|
| `AgentRunEvent.ANSWER_COMPLETED`에 sources 추가 | agent run 답변에는 sources 구조 미존재 (chat과 다름) | Design §3.3에서 `sources: []`로 대응. 향후 agent run에 sources 추가 시 별도 사이클 |
| `useAgentChat` mutation 완전 삭제 | dead code, 하지만 chatService.ts/단위 테스트 의존 | 별도 refactoring 사이클 (dead code cleanup) |
| Heartbeat / auto-reconnect 강화 | agent run에는 불필요 (짧은 실행 시간) | ws-chat-streaming에서 구현된 pattern 유지 |
| Multi-tab agent run subscription | 1 run = 1 connection 가정 | 향후 redis pub/sub 도입 시 별도 plan |

### 4.2 Known Limitations

| Item | Impact | Mitigation | Status |
|------|--------|-----------|--------|
| `ChatPageIntegration.test.tsx` I3가 실제 WS 연결 검증 안 함 | Transport-agnostic으로 약화 | `streamRouting.test.tsx`에서 enabled flag gating 명시 검증 | 허용 가능 (jsdom WebSocket 한계 인정) |
| ChatPage 282줄 (Design 가이드 200줄 초과) | 가독성/유지보수성 저하 가능 | 별도 hook(`useChatPageStreams`)으로 추출 검토 | 향후 refactor 사이클 |

---

## 5. Quality Metrics

| Metric | Target | Actual | Status |
|--------|--------|--------|--------|
| **Match Rate** | ≥90% | **98%** | ✅ PASS |
| **FR Coverage** | 100% | **9/9 (100%)** | ✅ PASS |
| **Design Coverage** | 100% | **6/6 (100%)** | ✅ PASS |
| **Backend Changes** | 0 | **0** | ✅ PASS |
| **Frontend Tests** | ≥80% | **43/43 (100%)** | ✅ PASS |
| **Gaps** | 0 blocker/major | **0 blocker/major/minor** | ✅ PASS |
| **TypeScript Type Check** | 0 errors | **0 errors** | ✅ PASS |
| **Regression** | BE 112 + FE 29 | **BE 112 + FE 43** | ✅ PASS (신규 9 추가) |

### 5.1 Test Breakdown

#### Frontend Tests (43/43 passed)
**신규 (9 tests)**
- `agentStepToToolEvent.test.ts` (5 tests)
  - node step 필터 ✅
  - tool started→started ✅
  - tool completed→completed(durationMs) ✅
  - 빈 배열 ✅
  - 혼합 입력 순서 보존 ✅
  
- `streamRouting.test.tsx` (4 tests)
  - selectedAgent=null → useChatStream enabled ✅
  - SUPER → useChatStream enabled ✅
  - UUID agent → useAgentRunStream enabled ✅
  - Q1 mutex 검증 (둘 다 enabled 프레임 없음) ✅

**기존 (34 tests — 회귀)**
- `useChatStream.test.ts` (8) ✅
- `useAgentRunStream.test.ts` (8) ✅
- `wsUrl.test.ts` (5) ✅
- `chatPreferencesStore.test.ts` (3) ✅
- `ToolPreviewPanel.test.ts` (5) ✅
- `ChatPageIntegration.test.tsx` (5, I3 갱신) ✅

### 5.2 Gaps Analysis (0 gaps)

**blocker**: 0
**major**: 0
**minor**: 0
**info**: 2 (미실질적)
- `streamRouting.test.tsx:32-44` — useChatStream mock에 `wasSummarized/isReplayed` 포함 (harmless)
- `ChatPage/index.tsx:200` — effect deps가 Design §4.4 abbreviation보다 stricter (실제로는 더 정확)

---

## 6. Learnings

### 6.1 What Went Well (Keep)

| Item | Insight |
|------|---------|
| **표준 패턴 재적용 효과** | fe-websocket-integration-guide §2의 5단계를 3번째 적용(agent-run 1일 → chat-streaming 1일 → ws-agent-chat-streaming 반나절). 인프라 재사용 비율 ↑, 적용 시간 ↓ 명시적 증명. 다음 WebSocket 기능(예: ingest progress)의 템플릿 확보. |
| **Open Question → Design → Implementation 일관성** | Plan의 3개 Open Question을 Design에서 명시적으로 답변 (Q1 activeStream mutex, Q2 tool filter, Q3 dead code keep). 이를 Implementation이 정확히 따름. 회귀 테스트 불필요하고, 처음부터 정확. |
| **단일 `activeStream` mutex 패턴** | 두 hook(chat/agent)을 동시에 보유하되, discriminated union으로 한 번에 하나만 enabled. Race condition 원천 차단, 호출자(handleSend)에서 분기 단순. 향후 3개 이상 stream 통합 시 템플릿 됨. |
| **백엔드 변경 0 게이트** | Plan §2.2 / Design §1.2 원칙 준수. 백엔드 인프라(UseCase/adapter/schema)를 정확히 예측하고, 정확히 그만 쓰고, 추가 변경 안 함. 이로써 다른 팀 리뷰/배포 대기 시간 0. |
| **ToolPreviewPanel 재사용** | agent run의 tool event를 chat event와 동일 형태로 변환. 컴포넌트 중복 없음. YAGNI 준수. |

### 6.2 Areas for Improvement (Problem)

| Issue | Severity | Root Cause | Next Step |
|-------|----------|-----------|-----------|
| **jsdom WebSocket 한계** | Medium | 통합 테스트 환경이 실제 WS 연결 미지원 | ChatPageIntegration I3를 transport-agnostic으로 약화. 실제 WS 경로는 unit test(streamRouting)에서 enabled flag만 검증. E2E 테스트는 별도 계획 필요. |
| **ChatPage 282줄 (가이드 200줄 초과)** | Low | 단일 `activeStream` 패턴이 여러 effect를 한 컴포넌트에 압축 | 향후 refactoring: `useChatPageStreams` custom hook으로 추출 → ChatPage는 state/effect 없이 view만 렌더. 하지만 본 사이클은 가독성 충분. |
| **Agent run sources 미지원** | Low | `AgentRunEvent.ANSWER_COMPLETED`에 sources field 없음 (design 수준의 제약) | Design §3.3에서 `sources: []`로 대응. 향후 backend agent run 강화 시 sources 추가 필요. |

### 6.3 To Apply Next Time

| Learning | 적용 범위 |
|----------|---------|
| **인프라 재사용 체크리스트** | 새 WebSocket 기능 추가 시, Plan에서 "이미 있는 자산 목록(Plan §1.2)" 섹션을 필수화. 5단계 중 몇 단계를 수행할지 명시. |
| **Open Question 조기 수렴** | Plan의 Open Question을 Design 초반에 일괄 정리(예: 한 메시지에). 이로써 Design이 완전해지고, Do가 번복 없이 진행. |
| **Match Rate >= 90% = 즉시 report** | Gap analysis 완료 후 Match Rate를 보고, 90% 이상이면 iterate 스킵하고 report로 진행. 이번 98%는 즉시 report, 특별한 반복 불필요. |
| **단일 책임 컴포넌트 + useMemo 분기** | 여러 stream을 한 컴포넌트에서 관리할 때, discriminated union state + useMemo로 분기 단일점 확보. 각 effect는 일반화된 `view` 객체만 봄. |
| **Backend 변경 원칙 서면화** | Design §1.2처럼 "백엔드 변경 0" 원칙을 초반 명시. 이로써 리뷰/계획 시간 단축, scope creep 방지. |

---

## 7. Process Improvement

### 7.1 Workflow 최적화

| Before | After |
|--------|-------|
| **Plan** (0.5일) + **Design** (0.5일) → **Design 리뷰** (하루~) → **Do** (1일) | **Plan** (0.5일 내) + **Design** (0.5일 내) + **Do** (반나절) + **Check** (0.25일) + **Report** (0.25일) = **1.5일 내 완전** |
| 각 단계 사이 대기 시간 존재 | 한 세션 내 모든 단계 + archive까지 일관 흐름 (이번 사이클 달성) |
| Open Question 미답변 상태에서 Design 시작 | Open Question을 한 메시지에 일괄 답변받으면 Design이 즉시 결정 + 구현 |

### 7.2 다음 사이클 제안 (WebSocket 기능)

다음 WebSocket 적용(예: ingest 진행률)에서:
1. 본 사이클 Plan §1.2 "이미 완료된 자산" 패턴 복사
2. 본 Design §3의 discriminated union + view useMemo 패턴 재사용
3. 테스트 구조: helper unit + routing integration + component integration
4. DoD: 수동 검증 5가지 시나리오 (§5.3 참고)
5. 가이드 §8에 "4번째 적용 사례" row 추가

예상 시간: **반나절** (인프라 재사용 비율 ≥ 80%)

---

## 8. Next Steps

### 8.1 권장 후속 작업

1. **본 사이클 archive**: `/pdca archive ws-agent-chat-streaming --summary`
   - 문서 이동: `docs/archive/2026-05/ws-agent-chat-streaming/`
   - 메트릭 보존: 98% match, 9 FRs, 0 iterations, 반나절

2. **ChatPage 분리 리팩토링** (별도 사이클)
   - `useChatPageStreams` custom hook으로 stream 로직 추출
   - ChatPage 컴포넌트 282줄 → 150줄 슬림화
   - 테스트 추가 (hook unit + component integration)

3. **Ingest 진행률 WS 적용** (4번째 패턴 적용)
   - Plan/Design/Do를 본 사이클 패턴 따라 진행
   - 예상: 반나절 이내

4. **Dead code cleanup** (별도 사이클, 선택)
   - `useAgentChat` mutation + chatService.ts 완전 삭제
   - 호출처 grep으로 확인 후 진행

5. **E2E 테스트** (기술 부채)
   - Playwright/Cypress로 실제 WS `/ws/agent/{run_id}` 연결 검증
   - integration test의 jsdom 한계 극복

---

## 9. Technical Spec Summary

### 9.1 `ActiveStream` Discriminated Union

```ts
type ActiveStream =
  | { kind: 'chat';  sessionId: string; message: string; topK?: number; placeholderId: string }
  | { kind: 'agent'; runId: string; agentId: string; sessionId: string; message: string; placeholderId: string };
```

- `kind` 필드로 type narrowing 자동화
- ChatPage 로컬 state (export 안 함, YAGNI)
- 두 hook의 enabled flag를 `kind` 값으로 결정

### 9.2 `agentStepsToToolEvents` Helper

```ts
export function agentStepsToToolEvents(steps: AgentRunStep[]): ChatToolEvent[] {
  return steps
    .filter((s) => s.kind === 'tool')
    .map((s) => ({
      kind: s.durationMs !== undefined ? 'completed' : 'started',
      toolName: s.name,
      durationMs: s.durationMs,
    }));
}
```

- Pure function (not a hook)
- Q2 구현: tool 종류만 필터링, node event 제외
- Order preserved by filter→map

### 9.3 ChatPage `view` useMemo 구조

```ts
const view = useMemo<NormalizedView | null>(() => {
  if (activeStream?.kind === 'chat') {
    return {
      tokens: chatStream.tokens,
      answer: chatStream.answer,
      error: chatStream.error,
      isDone: chatStream.isDone,
      toolEvents: chatStream.toolEvents,
      sources: chatStream.sources,
    };
  }
  if (activeStream?.kind === 'agent') {
    return {
      tokens: agentRun.tokens,
      answer: agentRun.answer,
      error: agentRun.error,
      isDone: agentRun.isDone,
      toolEvents: agentStepsToToolEvents(agentRun.steps),
      sources: [],
    };
  }
  return null;
}, [activeStream, chatStream, agentRun]);
```

- 두 stream의 차이(sources)를 정규화
- 모든 effect/render는 `view`만 봄 → 분기 단일점
- Dependencies: 전체 hook return object (nested fields 아님)

### 9.4 handleSend 분기 (Q1 mutex)

```ts
const handleSend = (content: string) => {
  if (!activeSessionId || isPending) return;  // Q1: mutex
  addMessage(activeSessionId, makeUserMessage(content));
  
  const placeholderId = crypto.randomUUID();
  addMessage(activeSessionId, makePlaceholder(placeholderId));

  if (selectedAgent && selectedAgent.id !== 'super') {
    // 사용자 정의 agent → agent stream
    setActiveStream({
      kind: 'agent',
      runId: crypto.randomUUID(),
      agentId: selectedAgent.id,
      sessionId: activeSessionId,
      message: content,
      placeholderId,
    });
  } else {
    // general OR SUPER → chat stream
    setActiveStream({
      kind: 'chat',
      sessionId: activeSessionId,
      message: content,
      topK: useRag ? 5 : undefined,
      placeholderId,
    });
  }
};
```

### 9.5 동작 매트릭스 (3 분기)

| Scenario | selectedAgent | Stream | Endpoint | Transport |
|----------|---------------|--------|----------|-----------|
| General (no agent) | `null` | chat | `/ws/chat/{sessionId}` | WS |
| SUPER agent | `id === 'super'` | chat | `/ws/chat/{sessionId}` | WS |
| 사용자 정의 agent(UUID) | `id !== 'super'` | agent | `/ws/agent/{runId}` | WS |

- 모두 WS → 일관 UX
- HTTP endpoint 0 (backward compat는 다른 페이지)

---

## 10. Changelog

### v1.0.0 — 2026-05-25

#### Added
- `agentStepToToolEvent.ts` helper — AgentRunStep → ChatToolEvent 변환, tool만 필터링
- `agentStepToToolEvent.test.ts` — 5 test cases (filter, started, completed, order)
- `streamRouting.test.tsx` — 4 test cases (null/SUPER/UUID agent routing, Q1 mutex)
- ChatPage에 `useAgentRunStream` hook 추가 + enabled gating
- ChatPage에 `activeStream` discriminated union state 추가
- ChatPage에 `view` useMemo normalize 추가 (chat/agent stream 분기)

#### Changed
- ChatPage `handleSend` 분기: 사용자 정의 agent를 `useAgentChat` mutation → `useAgentRunStream` hook으로 전환
- ChatPage import: `useAgentChat` 제거 (chatService.ts/mutation 정의는 유지)
- ChatPageIntegration.test.tsx I3: transport-agnostic 약화 (jsdom WS 한계 인정)
- websocket-integration.md §8: 3번째 적용 사례 row 추가 (반나절 시간 기록)

#### Fixed
- (없음 — bug fix 아님)

#### Deprecated
- (없음)

#### Removed
- (없음 — 정의/로직 보존, ChatPage import만 제거)

---

## 11. File Locations

### Source Files Added

```
idt_front/src/hooks/agentStepToToolEvent.ts
idt_front/src/hooks/agentStepToToolEvent.test.ts
idt_front/src/pages/ChatPage/__tests__/streamRouting.test.tsx
```

### Source Files Modified

```
idt_front/src/pages/ChatPage/index.tsx
idt_front/src/__tests__/components/ChatPageIntegration.test.tsx
idt/docs/guides/websocket-integration.md
```

### Documentation

```
docs/01-plan/features/ws-agent-chat-streaming.plan.md
docs/02-design/features/ws-agent-chat-streaming.design.md
docs/03-analysis/ws-agent-chat-streaming.analysis.md
docs/04-report/ws-agent-chat-streaming.report.md (이 파일)
```

### Reference

```
docs/guides/websocket-integration.md — §8 적용 사례 메모
docs/archive/2026-05/ — 직전 사이클 archive (fe-websocket-integration-guide, ws-chat-streaming)
```

---

## Appendix A: Test Evidence

### A.1 Frontend Test Results (43/43)

```bash
# agentStepToToolEvent.test.ts
✅ filters out node steps
✅ converts tool started to ChatToolEvent
✅ converts tool completed with durationMs
✅ handles empty array
✅ preserves order of mixed steps

# streamRouting.test.tsx
✅ selectedAgent=null → useChatStream enabled
✅ selectedAgent.id='super' → useChatStream enabled
✅ selectedAgent.id=UUID → useAgentRunStream enabled
✅ Q1 mutex: no concurrent enabled streams

# useChatStream.test.ts (regression)
✅ 8 tests PASS

# useAgentRunStream.test.ts (regression)
✅ 8 tests PASS

# wsUrl.test.ts (regression)
✅ 5 tests PASS

# chatPreferencesStore.test.ts (regression)
✅ 3 tests PASS

# ToolPreviewPanel.test.ts (regression)
✅ 5 tests PASS

# ChatPageIntegration.test.tsx (I3 updated)
✅ 5 tests PASS
```

### A.2 Backend Test Regression (112/112)

```bash
# pytest: all tests PASS
# No backend changes → 112 existing tests retained
```

### A.3 Type Check

```bash
tsc --noEmit
# 0 errors
```

---

**Report Created**: 2026-05-25  
**PDCA Phase**: Completed  
**Next Phase**: Archive (recommended: `/pdca archive ws-agent-chat-streaming --summary`)
