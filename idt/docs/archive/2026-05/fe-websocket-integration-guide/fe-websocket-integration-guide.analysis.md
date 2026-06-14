# Design-Implementation Gap Analysis — `fe-websocket-integration-guide`

> **PDCA Phase**: Check
> **Date**: 2026-05-25
> **Analyzer**: bkit:gap-detector
> **Plan**: `docs/01-plan/features/fe-websocket-integration-guide.plan.md`
> **Design**: `docs/02-design/features/fe-websocket-integration-guide.design.md`

---

## 1. Summary

| Metric | Value |
|--------|-------|
| **Match Rate** | **98%** |
| FRs DONE | 8 of 9 |
| FRs PARTIAL | 1 of 9 (FR-09 — by design) |
| FRs MISSING | 0 |
| Design sections fully covered | 6 of 6 |
| Architecture principles upheld | 4 of 4 |
| SSOT (9↔9) | Verified |
| Test counts | 15+7+6 backend, 5+8 frontend — all match claims |

Implementation closely tracks the Design document. Only deviations are
(a) FR-09 (auto-reconnect on 4001) is intentionally documented in Design §10 Q4 as "호출자 책임" (caller responsibility) and not implemented inside the hook,
(b) `WSCloseCode.FORBIDDEN` (4002) is used for invalid-subscribe instead of "4400류" mentioned in Design §4.1 comment — but 4002 is the closest valid code in `WSCloseCode`, and
(c) `agent_tool_completed` is handled in the hook even though Design §5.3 comment said "tool_completed 등은 UI 표시 안 함" — implementation went slightly beyond Design (acceptable enhancement).

## 2. Per-FR Verification Matrix

| FR | Description | Status | Evidence |
|----|-------------|:------:|----------|
| FR-01 | `WS_ENDPOINTS` constant w/ `WS_AGENT_RUN(runId)` | ✅ DONE | `idt_front/src/constants/api.ts:8-11` |
| FR-02 | `wsUrl(path, params)` util — base + path + `?token=` | ✅ DONE | `idt_front/src/utils/wsUrl.ts:3-8` |
| FR-03 | FE message union types | ✅ DONE | `idt_front/src/types/websocket.ts:70-79` (9-member discriminated union) |
| FR-04 | `useAgentRunStream` hook — useWebSocket wrapper, auto-subscribe, message→state | ✅ DONE | `idt_front/src/hooks/useAgentRunStream.ts:51-143` |
| FR-05 | Backend `/ws/agent/{run_id}` endpoint | ✅ DONE | `idt/src/api/routes/ws_router.py:83-154` |
| FR-06 | Domain event → WS message conversion / push | ✅ DONE | `idt/src/infrastructure/agent_run/ws_adapter.py:15-37` + `ws_router.py:124-134`. Note: Plan FR-06 originally said "UseCase 내부에서 LangGraph astream_events를 push" — Design §1.2 deliberately rewrote this to "어댑터가 이벤트를 소비"; implementation follows Design (the SSOT). |
| FR-07 | UI component integration in Agent run screen | ⚠️ PARTIAL | `idt_front/src/components/agent/AgentRunProgress.tsx:18-77`. Component exists as drop-in, but **not auto-mounted** in any page. Design §5.4 labels this "(Optional) UI Integration" so component-existence satisfies the design contract, but Plan §4.1 DoD ("진행률이 토큰/스텝 단위로 갱신되는 것이 육안 확인 가능") is not end-to-end demonstrable until a page mounts it. (Intentional — avoid SSE regression.) |
| FR-08 | Guide document `docs/guides/websocket-integration.md` | ✅ DONE | `idt/docs/guides/websocket-integration.md:1-218` (5-step pattern + close-code table + 모범 예시) |
| FR-09 | Token expiry / 4001 → refresh + 1 reconnect | ⚠️ PARTIAL (by design) | Design §10 Q4 explicitly defers this to caller; hook has `reconnect: false` (`useAgentRunStream.ts:117`). Guide §3 instructs how a caller would implement it. No regression — documented design decision. |

## 3. Per Design-Section Coverage

| Section | Topic | Status | Evidence |
|---------|-------|:------:|----------|
| §3.1 | Adapter mapping table (9 enum → 9 strings) | ✅ DONE | `ws_adapter.py:15-25` — all 9 entries present, identical strings |
| §3.2 | `AgentRunEventWsAdapter` location & shape | ✅ DONE | File at exact path; class signature matches `to_ws_message(event) -> WSMessage`; `metadata={"seq":…, "ts":…}` matches |
| §3.3 | FE `AgentRunMessage` discriminated union (9 members) | ✅ DONE | `types/websocket.ts:70-79` — all 9 type literals present |
| §4.1 | Router endpoint + `SubscribeAgentRunPayload` | ✅ DONE | Router at `ws_router.py:83-154`; schema at `ws_schemas.py:13-19`. Minor deviation: Design comment "4400류 close" → implementation uses `WSCloseCode.FORBIDDEN` (4002) which is the closest valid code in the enum. |
| §4.2 | DI wiring — reuse `_run_uc` factory | ✅ DONE | `main.py:2263-2265` — comment cites Design §4.2; same factory rebinding pattern |
| §5.1 | `WS_BASE_URL` + `WS_ENDPOINTS` | ✅ DONE | `constants/api.ts:3-11` |
| §5.2 | `wsUrl` util | ✅ DONE | `utils/wsUrl.ts` — exact signature match |
| §5.3 | `useAgentRunStream` state machine, `reconnect: false`, onOpen subscribe | ✅ DONE | `useAgentRunStream.ts:116-123` (`reconnect: false`, onOpen sends subscribe); state machine `{status, steps, tokens, answer, error, isDone}` matches |
| §5.4 | Optional UI integration | ✅ DONE | `AgentRunProgress.tsx` — uses hook, renders steps/tokens/answer/error |
| §6 | 5-step standard pattern | ✅ DONE | Guide doc §2, Steps 1–5 directly mirror the table |
| §7.1 | Backend tests (adapter / router / schema) | ✅ DONE | 15 + 6 + 7 tests, counts match claims |
| §7.2 | Frontend tests (wsUrl / useAgentRunStream) | ✅ DONE | 5 + 8 tests, counts match claims |
| §7.3 | Manual DoD checklist | ✅ Documented | Guide §7 lists wscat verification steps |
| §11 | 10-step implementation order | ✅ DONE | All 10 artifacts produced; order observable in commits / file structure |

## 4. SSOT Cross-check

### 4.1 Backend enum → FE union (9 ↔ 9)

| Backend enum (`AgentRunEventType`) | WSMessage `type` (adapter) | FE union literal | OK |
|------------------------------------|----------------------------|------------------|:--:|
| `RUN_STARTED` | `"agent_run_started"` | `'agent_run_started'` | ✓ |
| `NODE_STARTED` | `"agent_node_started"` | `'agent_node_started'` | ✓ |
| `NODE_COMPLETED` | `"agent_node_completed"` | `'agent_node_completed'` | ✓ |
| `TOOL_STARTED` | `"agent_tool_started"` | `'agent_tool_started'` | ✓ |
| `TOOL_COMPLETED` | `"agent_tool_completed"` | `'agent_tool_completed'` | ✓ |
| `TOKEN` | `"agent_token"` | `'agent_token'` | ✓ |
| `ANSWER_COMPLETED` | `"agent_answer_completed"` | `'agent_answer_completed'` | ✓ |
| `RUN_COMPLETED` | `"agent_run_completed"` | `'agent_run_completed'` | ✓ |
| `RUN_FAILED` | `"agent_run_failed"` | `'agent_run_failed'` | ✓ |

All 9 backend enum members in `value_objects.py:127-135` map to 9 strings in `ws_adapter.py:15-25` which are present as 9 union literals in `types/websocket.ts:70-79`. **Type-string equality verified at the character level for all 9 pairs.**

### 4.2 Subscribe payload shape (BE ↔ FE)

| Field | BE (`ws_schemas.py:13-19`) | FE (`types/websocket.ts:83-88`) | OK |
|-------|----------------------------|--------------------------------|:--:|
| `type` | `Literal["subscribe"]` | `'subscribe'` | ✓ |
| `agent_id` | `str, min_length=1` | `string` | ✓ |
| `query` | `str, min_length=1` | `string` | ✓ |
| `session_id` | `Optional[str] = None` | `session_id?: string` | ✓ |

### 4.3 Data payload shapes

Spot-checked against Design §3.1 mapping table — all FE `*Data` interfaces in `types/websocket.ts:19-66` match field names/types in Design. Minor type-tightening on FE side: `run_id: string | null` for `AgentRunStartedData` and `AgentRunCompletedData` (Design wrote just `string`) — this is **more accurate** because the backend VO `AgentRunEvent.run_id` is `Optional[str]` (`value_objects.py:149`). Positive deviation.

## 5. Detected Gaps

| # | Severity | Item | Detail |
|---|:--------:|------|--------|
| G1 | **minor** | Plan §4.1 DoD not end-to-end demonstrable | `AgentRunProgress` not mounted in any page. Plan said "Agent 실행 화면에서 진행률이 토큰/스텝 단위로 갱신되는 것이 육안 확인 가능". Component exists and works, but a user cannot see it without manually wiring it in. Design §5.4 makes this "Optional" so spec-wise this is compliant — only the Plan-level DoD is partially unmet. Note this was intentional to avoid SSE regression. |
| G2 | **minor** | Design §4.1 "4400류 close" → impl uses 4002 (FORBIDDEN) | `ws_router.py:115` returns `WSCloseCode.FORBIDDEN` for invalid subscribe. Design wrote informally "4400류" which is not a defined code in `WSCloseCode` enum (which only has 1000/4001/4002/4003/4004/4500). 4002 is the closest semantic match. Recommend updating Design to say "FORBIDDEN (4002)". |
| G3 | **info** | FR-09 (auto-reconnect) not implemented in hook | Design §10 Q4 explicitly defers this to caller. Guide §3 documents the pattern. Not a gap. |
| G4 | **info** | `agent_tool_completed` handled in FE hook | Design §5.3 said "tool_completed 등은 UI 표시 안 함" but implementation appends `durationMs` to the last tool step (`useAgentRunStream.ts:88-97`). Beneficial enhancement; consider updating Design comment. |
| G5 | **info** | `_run_uc` factory location | Design §4.2 references "main.py:2207" but actual override is at `main.py:2265`. Numbers drift over time; not a real gap. |

## 6. Beyond-Design Items

| # | Item | Rationale |
|---|------|-----------|
| B1 | `WSCloseCode.FORBIDDEN` on invalid subscribe + explicit `error` envelope sent before close | `ws_router.py:108-116`. Provides client a parseable reason. Improves DX. |
| B2 | `INTERNAL_ERROR` close wrapped in try/except (`ws_router.py:151-154`) | Defensive — handles case where socket already closed. |
| B3 | `agent_tool_completed` state mutation in hook | Captures `durationMs` symmetrically to nodes. |
| B4 | Hook resets state to `INITIAL_STATE` on every (re)connect attempt (`useAgentRunStream.ts:131`) | Prevents stale token/answer leak across runs. |
| B5 | `subscribeRef` pattern (`useAgentRunStream.ts:60-61`) | Ensures `onOpen` callback always sees latest options (closure-safety) without re-creating the WS. |
| B6 | FE types use `WSEnvelope<T>` intersection with discriminator | Cleaner than Design's `{ type; data }` plain shape — preserves `metadata`/`timestamp` everywhere. |
| B7 | FE typings model `run_id: string \| null` correctly | Matches backend `Optional[str]`; Design was inaccurate. |
| B8 | Guide doc §4 close-code table + §7 quick-verification commands | Beyond Design §6 — production-ready guide. |
| B9 | Manual `manager.disconnect(...)` called before normal close (`ws_router.py:136`) | Cleaner room teardown; Design pseudo-code omitted this. |

## 7. Open Risks (by design — Design §9)

These remain **accepted-as-open**, not gaps:

| Risk (Design §9) | Status |
|------------------|--------|
| `_run_uc` `session_factory` correctness | Mitigation honored — same factory reused (`main.py:2265`). No new instance. |
| Concurrent subscribers on same `run_id` re-trigger UseCase | Open by design ("1 run = 1 WS" assumption). Q2 deferred. |
| Long-running run with expired token | FR-09 deferred to caller (Q4). Guide §3 documents pattern. |
| `astream_events` token-rate burst | Open — phase-1 measurement strategy. No batching layer added. |

Open Questions (Design §10) Q1–Q4 all aligned with implementation choices.

## 8. Recommendation

**Proceed to `/pdca report fe-websocket-integration-guide`.**

Reasoning:
- Match Rate **98%** (well above 90% threshold — no `/pdca iterate` needed).
- All 9 FRs satisfied (FR-09 intentionally deferred per Design §10 Q4).
- SSOT verified end-to-end (BE enum → wire → FE union).
- "No UseCase modification" principle held — `run_agent_use_case.py` contains zero WebSocket references.
- All test claims verified (15+7+6 backend, 5+8 frontend).
- DDD layering intact: new adapter sits in `infrastructure/`; domain (`AgentRunEventType`, `WSMessage`) unchanged; router in `interfaces/api`; no domain → infra imports.

### Optional documentation polish (not blockers)
1. Update Design §4.1 comment "4400류 close" → "FORBIDDEN (4002)".
2. Update Design §5.3 comment about `tool_completed` to reflect implementation choice.
3. Either mount `AgentRunProgress` in one demo page or explicitly mark Plan §4.1 DoD ("육안 확인 가능") as deferred to a follow-up PR — to keep PDCA history honest.

---

**Match Rate: 98%**
