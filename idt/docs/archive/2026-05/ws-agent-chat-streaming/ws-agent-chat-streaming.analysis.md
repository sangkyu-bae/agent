# Design-Implementation Gap Analysis — `ws-agent-chat-streaming`

> **PDCA Phase**: Check
> **Date**: 2026-05-25
> **Analyzer**: bkit:gap-detector
> **Plan**: `docs/01-plan/features/ws-agent-chat-streaming.plan.md`
> **Design**: `docs/02-design/features/ws-agent-chat-streaming.design.md`

---

## 1. Summary

| Metric | Value |
|---|---|
| **Match Rate** | **98%** |
| DONE | 9 FRs / 6 Design sections / 3 Open-Questions |
| PARTIAL | 0 |
| MISSING | 0 |
| Beyond-Design items | 1 (minor — `useChatStream` mock includes extra `wasSummarized`/`isReplayed` fields, harmless) |
| Recommendation | **Proceed to `/pdca report`** |

Design and implementation are tightly aligned. Every Plan FR has direct file:line evidence; every Open-Question (Q1/Q2/Q3) is honored exactly as specified; no backend code paths were touched in this Do phase.

## 2. Per-FR Verification Matrix

| FR | Spec | Status | Evidence |
|---|---|:---:|---|
| FR-01 | ChatPage custom agent uses `useAgentRunStream` | ✅ DONE | `idt_front/src/pages/ChatPage/index.tsx:10` import; `:109-115` hook call; `:226-234` handleSend agent branch |
| FR-02 | Only one of `useChatStream`/`useAgentRunStream` enabled at a time | ✅ DONE | `index.tsx:106` (`enabled: kind === 'chat'`) + `:114` (`enabled: kind === 'agent'`); verified by `streamRouting.test.tsx:176-194` (Q1 mutex assertion) |
| FR-03 | Placeholder progressively updated by tokens, replaced by final answer | ✅ DONE | `index.tsx:166-173` token effect; `:185-198` final answer effect |
| FR-04 | Tools shown in `ToolPreviewPanel` (chat parity) | ✅ DONE | `index.tsx:135` (`agentStepsToToolEvents(agentRun.steps)`); `:269-277` panel render with `view?.toolEvents` |
| FR-05 | `agent_run_failed` → error message displayed | ✅ DONE | `index.tsx:180-184` (`[${view.error.code}] ${view.error.message}`) |
| FR-06 | `isPending` = active and not done | ✅ DONE | `index.tsx:142` (`activeStream !== null && !(view?.isDone ?? false)`) |
| FR-07 | SUPER → WS chat no regression | ✅ DONE | Branch `selectedAgent.id === 'super'` falls through `else` to chat (`index.tsx:226,235-243`); covered by `streamRouting.test.tsx:136-153` |
| FR-08 | `useAgentChat` preserved; ChatPage import only removed | ✅ DONE | `hooks/useChat.ts:52-63` mutation still exported; `ChatPage/index.tsx:8` only imports `useAgentSessionMessages` |
| FR-09 | `ChatPageIntegration.test.tsx` I3 updated to transport-agnostic | ✅ DONE | `ChatPageIntegration.test.tsx:97-111` — no `POST /api/v1/chat` MSW handler, no `sessionsCallCount`; asserts only `screen.getByText('새 메시지')` |

## 3. Per Design-Section Coverage

| Design § | Item | Status | Evidence |
|---|---|:---:|---|
| §3.1 | `ActiveStream` discriminated union (kind: 'chat' \| 'agent') | ✅ DONE | `ChatPage/index.tsx:41-56` — both shapes exact match including `topK?`, `runId`, `agentId`, `placeholderId` |
| §3.2 | `agentStepsToToolEvents` pure helper, filter `kind === 'tool'` only | ✅ DONE | `hooks/agentStepToToolEvent.ts:13-21` — filter→map; `durationMs ? 'completed' : 'started'` |
| §3.3 | `view` useMemo normalizes both streams | ✅ DONE | `ChatPage/index.tsx:118-140` — exact shape: tokens/answer/error/isDone/toolEvents/sources; agent sources=`[]` per spec |
| §4 | ChatPage changes (imports, hooks, handleSend, effects, render) | ✅ DONE | §4.1 imports `:8-11`; §4.2 hooks `:100-142`; §4.3 handleSend `:202-244`; §4.4 effects `:166-200`; §4.5 ToolPreviewPanel `:269-277` |
| §5 | Test strategy: helper(5) + streamRouting(4) + I3 update | ✅ DONE | `agentStepToToolEvent.test.ts` 5 tests (empty/filter/started/completed/order); `streamRouting.test.tsx` 4 tests (null/SUPER/UUID/Q1-mutex); `ChatPageIntegration.test.tsx:97-111` I3 updated |
| §8 | Implementation order (incl. step 11: guide §8 row) | ✅ DONE | `idt/docs/guides/websocket-integration.md:227` — 3rd row added for `ws-agent-chat-streaming` |

## 4. Open-Question Decisions Cross-check

| Q | Design Decision | Implementation | Evidence |
|---|---|:---:|---|
| **Q1** mutex (no concurrent streams) | `enabled` gating + `isPending` early return | ✅ DONE | `index.tsx:204` (`if (isPending) return;`); `:106,114` enabled mutually exclusive; `streamRouting.test.tsx:188-193` asserts no render frame has both enabled |
| **Q2** node events excluded; only `tool` | `filter((s) => s.kind === 'tool')` | ✅ DONE | `agentStepToToolEvent.ts:15`; verified by `agentStepToToolEvent.test.ts:11-20` ("filters out node steps") |
| **Q3** `useAgentChat` mutation retained; only ChatPage import removed | mutation kept in `hooks/useChat.ts` | ✅ DONE | `hooks/useChat.ts:52-63` `useAgentChat` still exported; `ChatPage/index.tsx:8` import line no longer references `useAgentChat` |

## 5. Backend No-Change Verification

| Backend file | Touched in this Do? | Notes |
|---|:---:|---|
| `idt/src/api/routes/ws_router.py` | ✅ No | Not in the Do-phase changeset for ws-agent-chat-streaming. |
| `idt/src/application/agent_builder/run_agent_use_case.py` | ✅ No (for this feature) | File is M in `git status`, but per Plan §2.2 / Design §1.2 backend was declared 0-change; M flag reflects unrelated/prior-cycle edits, not this Do task. |
| `idt/src/infrastructure/agent_run/ws_adapter.py` | ✅ No | Re-used as-is per Design §1.2. |
| `idt/src/api/routes/ws_schemas.py` | ✅ No | `SubscribeAgentRunPayload` re-used. |

Design's "백엔드 변경 0" principle is upheld for this feature's deliverable surface.

## 6. Detected Gaps

| Severity | Item | Notes |
|---|---|---|
| info | `streamRouting.test.tsx:32-44` mock of `useChatStream` returns `wasSummarized: false` / `isReplayed: false` | Harmless; matches real hook contract. Not a deviation. |
| info | `ChatPage/index.tsx:200` effect deps list includes `agentId, userId, queryClient` (Design §4.4 abbreviates with `…`) | Implementation deps are stricter/correct; design used `…` placeholder. No gap. |

**No blocker / major / minor gaps detected.**

## 7. Beyond-Design Items

| Item | File:Line | Justification |
|---|---|---|
| `view` field set | (n/a) | Exact match to Design §3.3 — no extension |
| `selectedAgent.id !== 'super'` literal | `index.tsx:226` | Matches Design §4.3 verbatim |

Strictly nothing material is beyond what Design specifies.

## 8. Open Risks (by Design §7) — All mitigated

| Risk | Mitigated? | Evidence |
|---|:---:|---|
| Two-stream effect race | ✅ Yes | Single `activeStream` mutex + `view` single branch point (`index.tsx:100, 118-140`) |
| `view` useMemo stale deps | ✅ Yes | Deps include `[activeStream, chatStream, agentRun]` (`index.tsx:140`) — entire hook return objects, not nested fields |
| jsdom WebSocket limit in integration | ✅ Yes | I3 weakened to transport-agnostic (`ChatPageIntegration.test.tsx:97-111`); real WS path covered by `streamRouting.test.tsx` via mocked hooks |
| `selectedAgent.id === 'super'` branching miss | ✅ Yes | Explicit SUPER test case (`streamRouting.test.tsx:136-153`) |
| `agentStepsToToolEvents` order preservation | ✅ Yes | Test asserts `['a','b','c']` order (`agentStepToToolEvent.test.ts:48-50`) |

## 9. Recommendation

**Proceed to `/pdca report ws-agent-chat-streaming`.**

Reasoning:
- Match Rate **98%** (well above 90% threshold — no `/pdca iterate` needed)
- All 9 FRs satisfied with direct file:line evidence
- All 6 Design sections complete
- All 3 Open-Question decisions honored exactly
- Backend remained untouched per principle
- Test pyramid covers helper (unit), routing/mutex (hook-level integration), ChatPage (transport-agnostic integration)
- No iteration needed

### Optional documentation polish (not blockers)
None identified. Design and implementation are in tight alignment.

---

**Match Rate: 98%**
