---
name: project-agent-user-context-iteration1
description: agent-user-context feature PDCA iteration 1 — wiring gaps fixed, Match Rate raised 78%→95%
metadata:
  type: project
---

agent-user-context Iteration 1 completed 2026-05-28. Match Rate raised from 78% to 95%.

**Why:** The domain/application/infra layers were fully implemented but the wiring layer was broken — AuthContext was never delivered to running requests because main.py DI was not registered and no router called `Depends(get_auth_context)`.

**Fixes applied:**
- `src/api/main.py`: Added `create_auth_context_factories()` + DI overrides for `AssembleAuthContextUseCase`, `GrantPermissionUseCase`, `RevokePermissionUseCase`, `PermissionRepository`. Added `user_profile_repo` injection into `register_factory`. Added `app.include_router(admin_user_router)`.
- `src/api/routes/agent_builder_router.py`: `run_agent` + `run_agent_stream` now use `get_auth_context` / `get_auth_context_from_query_token` and pass `auth_ctx=` to UseCase.
- `src/api/routes/general_chat_router.py`: POST /chat now uses `get_auth_context` and passes `auth_ctx=` to UseCase.
- `src/application/general_chat/tools.py`: `ChatToolBuilder.build` now accepts `auth_ctx` kwarg and injects into `InternalDocumentSearchTool`.
- `src/application/general_chat/use_case.py`: `stream()` now passes `auth_ctx=auth_ctx` to `_tool_builder.build()`.
- `tests/interfaces/auth/test_auth_router.py`: Updated `test_register_201` payload with `display_name`; added `test_register_422_missing_display_name`.
- `tests/application/agent_builder/test_run_agent_use_case.py`: Added `TestRunAgentAuthCtx` with 2 tests for ContextVar set/reset behavior.

**Deferred:** G-06 (infra repo tests), G-08 (tavily auth), G-09 (N+1 batch), G-10 (docs).

**How to apply:** If continuing work on this feature, run `/pdca report agent-user-context` to generate the completion report. Remaining gap is FR-19 partial TDD (4 missing test files).
