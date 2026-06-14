# fix-ws-auth-context-missing — Gap Analysis (Check Phase)

> **Match Rate: 100% (9/9 acceptance criteria Met)**
>
> **Feature**: fix-ws-auth-context-missing
> **Project**: sangplusbot (idt)
> **Analysis Date**: 2026-06-03
> **Design Doc**: [../02-design/features/fix-ws-auth-context-missing.design.md](../02-design/features/fix-ws-auth-context-missing.design.md)
> **Plan Doc**: [../01-plan/features/fix-ws-auth-context-missing.plan.md](../01-plan/features/fix-ws-auth-context-missing.plan.md)

---

## 1. Analysis Overview

| Item | Value |
|------|-------|
| Feature | fix-ws-auth-context-missing |
| Impl Paths | `src/application/agent_run/ws_auth_context.py`, `src/api/routes/ws_router.py`, `src/api/main.py` |
| Tests | `tests/application/agent_run/test_ws_auth_context.py`, `tests/api/test_ws_router_auth_context.py` |
| Method | Design Acceptance Criteria (§6) + Detailed Design (§3) ↔ implementation |

---

## 2. Acceptance Criteria (§6) → Verification

| # | Acceptance Criterion | Status | Evidence |
|---|----------------------|:------:|----------|
| 1 | `ws_agent_run` passes `auth_ctx` + `viewer_department_ids=list(auth_ctx.department_ids)` to stream | Met | `ws_router.py:177-184` — `viewer_department_ids=list(auth_ctx.department_ids)` (L182), `auth_ctx=auth_ctx` (L183) |
| 2 | `ws_chat` passes `auth_ctx` to stream | Met | `ws_router.py:265-267` — `use_case.stream(request, request_id=session_id, auth_ctx=auth_ctx)` |
| 3 | `WsAuthContextResolver` opens/closes a short-lived session (`async with session_factory`) | Met | `ws_auth_context.py:31-33` — `async with self._session_factory() as session: uc = self._assemble_uc_builder(session); return await uc.execute(...)` |
| 4 | Fail-closed degrade to `AuthContext.public_anonymous()` on assembly failure, WS connection preserved | Met | `ws_router.py:80-88` — `_resolve_ws_auth_ctx` try/except returns `AuthContext.public_anonymous()`, logs error, no `websocket.close`. Called at `:154` / `:236` before `manager.connect` |
| 5 | `main.py` WS DI registers resolver/logger overrides | Met | `main.py` — `_ws_auth_resolver = create_ws_auth_context_resolver()` + overrides for `get_ws_auth_context_resolver`, `get_ws_logger`; factory injects `get_session_factory()` |
| 6 | HTTP `/run`, SSE `/run/stream` signatures unchanged | Met | `agent_builder_router.py` `/run` uses `Depends(get_auth_context)`; `/run/stream` uses `Depends(get_auth_context_from_query_token)` — request-scoped path intact (Design §2.3) |
| 7 | `domain/` unchanged; application does NOT import infrastructure repos directly | Met | `ws_auth_context.py:9-17` imports only `typing`, `sqlalchemy.ext.asyncio`, `src.application.permission...`, `src.domain.*` — no `src.infrastructure.*`. Repo wiring lives in `main.py` composition root |
| 8 | New/existing tests present | Met | `test_ws_auth_context.py` (3 tests) + `test_ws_router_auth_context.py` (3 tests) cover all §3.4 cases |
| 9 | "deferred" comment removed from `ws_router.py` | Met | Grep `deferred\|not plumbed\|TODO.*auth_ctx` in `ws_router.py` → no matches |

---

## 3. Gaps Found

**None.** No Missing, Added, or Changed items relative to the Design.

### Minor observations (non-blocking, severity Info)

| Item | Severity | Note |
|------|:--------:|------|
| Test names differ from Design §3.4 labels (class-based grouping used) | Info | Coverage equivalent; not a gap |
| Anonymous test additionally asserts `viewer_department_ids == []` | Info | Stronger than spec — acceptable |
| `render_user_context_block` real-block verification | Info | Manual local dev step (Design §5/Step 5), out of automated-test scope |
| Windows event-loop flakiness | Info | Design §3.4 prescribes isolated test execution; consistent with project guidance |

---

## 4. Layer / Convention Compliance

| Check | Result |
|-------|:------:|
| domain/ unchanged (`public_anonymous` pre-existing) | Pass |
| application → no infrastructure import | Pass |
| CLAUDE.md §6: `session_factory` injected, `async with`, no `get_session_factory()()` in factory | Pass |
| Single new class only (`WsAuthContextResolver`) | Pass |
| `import uuid` added to ws_router | Pass |
| main.py imports resolver/logger placeholders + `WsAuthContextResolver` | Pass |

---

## 5. Test Verification (isolated execution)

| Test file | Result |
|-----------|--------|
| `tests/application/agent_run/test_ws_auth_context.py` | 3 passed |
| `tests/api/test_ws_router_auth_context.py` | 3 passed |
| `tests/api/test_ws_agent_router.py` + `test_ws_chat_router.py` (regression) | 12 passed |

---

## 6. Recommended Actions

- None required for code. Implementation fully matches Design (100%).
- Optional: manual dev-server verification that the `[현재 사용자 정보]` block appears in the system prompt (LangSmith trace) when chatting from the real screen.
- Match Rate ≥ 90% → proceed to Report phase: `/pdca report fix-ws-auth-context-missing`.
