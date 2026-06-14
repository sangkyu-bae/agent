---
name: fix-ws-auth-context-missing_completion
description: WebSocket auth context assembly fix (100% match, short-lived resolver pattern, fail-closed degradation)
metadata:
  type: project
---

# fix-ws-auth-context-missing Feature Completion

**Status**: Completed 2026-06-03 | **Match Rate**: 100% (9/9 criteria Met) | **Iterations**: 0

## Feature Summary

Fixed missing user context (`AuthContext`) assembly in WebSocket agent/chat endpoints (`/ws/agent`, `/ws/chat`). Problem: `verify_ws_token` produced only `User` entity, never assembling `AuthContext` → `render_user_context_block(None)` returned "" → `[현재 사용자 정보]` block missing from system prompt, permission Tools neutered. HTTP/SSE paths unaffected.

## Solution Architecture

Implemented `WsAuthContextResolver` (application layer) to assemble `AuthContext` via existing `AssembleAuthContextUseCase` using:
- **Short-lived session** (`async with session_factory()`) — opened, used, closed within `execute()` method
- **Builder injection** (`session → AssembleAuthContextUseCase` Callable) — maintains DDD (application never imports infrastructure repos)
- **Fail-closed degradation** — assembly exception → logs + returns `AuthContext.public_anonymous()`, WS connection preserved

Both endpoints now resolve `auth_ctx` right after `verify_ws_token`, pass `auth_ctx=` + `viewer_department_ids=list(auth_ctx.department_ids)` to `stream()`.

## Reusable Patterns Established

### 1. Short-Lived Resolver Template (WS/Non-Request-Scoped Contexts)

```python
class MyResolver:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        uc_builder: Callable[[AsyncSession], MyUseCase],
    ):
        self._session_factory = session_factory
        self._uc_builder = uc_builder

    async def execute(self, *args, **kwargs) -> Result:
        async with self._session_factory() as session:
            uc = self._uc_builder(session)
            return await uc.execute(*args, **kwargs)
```

**Wiring** (composition root):
```python
def create_my_resolver() -> MyResolver:
    def _uc_builder(session: AsyncSession) -> MyUseCase:
        return MyUseCase(repo1=Repo1(session), ..., logger=...)
    
    return MyResolver(
        session_factory=get_session_factory(),
        uc_builder=_uc_builder,
    )
```

**Use Case**: WebSocket, background tasks, any non-request-scoped code needing short-lived DB access without holding request scope for entire operation lifetime.

### 2. Fail-Closed AuthContext Degradation

When auth assembly fails in streaming contexts, degrade safely:
```python
async def _resolve_with_fallback(user, resolver, logger) -> AuthContext:
    try:
        return await resolver.execute(user, request_id)
    except Exception as e:
        logger.error("Assembly failed — degrading to anonymous", exception=e, ...)
        return AuthContext.public_anonymous()
```

**Safety**: Connection open, chat functional, permissions empty (no privilege escalation), error logged (audit trail).

## Metrics

| Aspect | Value |
|--------|-------|
| Duration | 3 days (2026-06-01 to 2026-06-03) |
| Files Changed | 5 core + 4 test |
| LOC Added | ~260 source + ~265 test |
| Tests | 6 new (0 failures) + 12 regression passed |
| Match Rate | 100% |
| Gaps | 0 |
| Iterations | 0 |
| Layer Violations | 0 |

## Key Decisions

- Fix **both** `/ws/agent` and `/ws/chat` (parity)
- **Short-lived session** pattern (not request-scoped)
- **Fail-closed** on assembly failure (anonymous fallback)
- **No composition-level caching** (defer to backlog)
- **DDD compliance**: application → no infrastructure imports

## Follow-Up Opportunities

1. **Optional AuthContext Caching**: HTTP/SSE/WS all do 3 DB round-trips per request. Measure p95; implement (user_id, request_date) cache if ROI clear.
2. **ContextVar Propagation Semantics**: Decide if `set_current_auth_context()` should explicitly set anonymous (currently only on non-None).
3. **Manual Dev-Server Verification**: Connect via WebSocket, verify `[현재 사용자 정보]` block appears in LangSmith trace (optional but recommended).

## Related Documents

- **Report**: `docs/04-report/fix-ws-auth-context-missing.report.md`
- **Analysis**: `docs/03-analysis/fix-ws-auth-context-missing.analysis.md`
- **Design**: `docs/02-design/features/fix-ws-auth-context-missing.design.md`
- **Plan**: `docs/01-plan/features/fix-ws-auth-context-missing.plan.md`
