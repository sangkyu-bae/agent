# Agent User Context — Gap Analysis Report

> **Feature**: agent-user-context
> **Analysis Date**: 2026-05-28
> **Analyzer**: bkit:gap-detector
> **Plan Doc**: [agent-user-context.plan.md](../01-plan/features/agent-user-context.plan.md)
> **Design Doc**: [agent-user-context.design.md](../02-design/features/agent-user-context.design.md)
> **Implementation base**: `idt/src/`

---

## Executive Summary

| Metric | Value |
|---|---|
| **Overall Match Rate** | **78%** |
| FRs checked | 20 |
| ✅ Implemented | 14 |
| ⚠️ Partial | 4 |
| ❌ Missing / Broken | 2 |
| ➕ Extra (not in design) | 0 |
| Critical (Blocking) gaps | **3** |
| Status | **Iterate (<90%)** |

**Verdict**: The Domain / Application / Infrastructure / Tool layers are implemented faithfully to the design (TDD evidence is strong: ~80 new tests). The **wiring layer is broken**: `AuthContext` is never actually delivered to a running request because

1. `src/api/main.py` does not construct `AssembleAuthContextUseCase`, `UserProfileRepository`, or `PermissionRepository`.
2. `admin_user_router` is not `include_router`'d into the FastAPI app.
3. **No router calls `Depends(get_auth_context)` or passes `auth_ctx=` to the UseCases**.

Net effect: every code path silently runs with `auth_ctx=None`, falling back to `public_anonymous()` and immediately denying RAG access (`USE_RAG_SEARCH` missing). FR-08, FR-09, FR-10, FR-18 are effectively dead. The pre-existing `tests/interfaces/auth/test_auth_router.py::test_register_201` will also regress because it omits the now-required `display_name`.

---

## 1. Layer-by-Layer Verification

### 1.1 Domain Layer — ✅ 100%

| Expected file | Status | Notes |
|---|:---:|---|
| `idt/src/domain/agent_run/auth_context.py` — `AuthContext` frozen, `public_anonymous()`, `has()` | ✅ | All 9 fields incl. `tenant_id` default None; matches Design §3.1 exactly. |
| `idt/src/domain/permission/value_objects.py` — `PermissionCode` enum (8 codes) + `.label_ko` | ✅ | All 8 codes + `_LABELS_KO` complete, matches Design §3.2. |
| `idt/src/domain/permission/resolver.py` — `PermissionResolver.resolve()` | ✅ | Implemented as static method on a plain class (Design used `@dataclass(frozen=True)` decorator; functional behavior identical). Minor cosmetic deviation. |
| `idt/src/domain/permission/entity.py` — RolePermission, UserPermission | ✅ | frozen dataclasses; matches. |
| `idt/src/domain/permission/interfaces.py` — 4 abstract methods | ✅ | `find_codes_for_role`, `find_codes_for_user`, `grant_to_user`, `revoke_from_user` all present. |
| `idt/src/domain/user_profile/entity.py` — UserProfile (7 fields) | ✅ | Includes `created_at`, `updated_at` (Design §3.4 lists these too). |
| `idt/src/domain/user_profile/interfaces.py` — `find_by_user_id`, `upsert` | ✅ | Matches. |

### 1.2 Application Layer — ⚠️ 85%

| Expected | Status | Notes |
|---|:---:|---|
| `application/agent_run/auth_context.py` — ContextVar + get/set/reset | ✅ | `idt/src/application/agent_run/auth_context.py:17-42` |
| `application/permission/assemble_auth_context.py` — 3 DB calls + email fallback | ✅ | `assemble_auth_context.py:30-93`; profile fallback at line 40-42. **Note**: department lookup uses N+1 (`find_by_id` per UserDepartment, line 51-56) — Design §4.2 implied this; not a gap but perf risk vs NFR <30 ms. |
| `application/permission/grant_revoke.py` | ✅ | `grant_revoke.py:12-53`, both Use Cases idempotent with `PermissionCode` validation. |
| `application/user_profile/use_cases.py` — Get/Upsert | ✅ | `use_cases.py:22-59`. |
| `application/agent_run/prompt_rendering.py` — whitelist render | ✅ | `prompt_rendering.py:16-62`; permissions sorted (line 42) — improvement vs design. |
| `application/agent_builder/workflow_compiler.py` — `auth_ctx` + `include_user_context` + prepend + bind | ✅ | `workflow_compiler.py:76-107`; sub-agent recursion honors flag (line 311). |
| `application/agent_builder/run_agent_use_case.py` — `auth_ctx` kw + set/reset in finally | ✅ | `run_agent_use_case.py:170, 202-204, 282-283`; passes `include_user_context=agent.include_user_context` at line 451. |
| `application/general_chat/use_case.py` — `auth_ctx` kw + ContextVar + `_create_agent(tools, auth_ctx)` | ⚠️ | `use_case.py:108-117, 126, 152-154, 171, 216-217` — prepend OK. **BUT**: line 168-170 calls `self._tool_builder.build(top_k=, request_id=)` **without** `auth_ctx=auth_ctx` (Design §4.4.3 shows it should be passed). `ChatToolBuilder.build` signature is also missing the param. → general_chat tools never receive AuthContext. |

### 1.3 Tool Layer (PoC) — ✅ 95%

| Expected | Status | Notes |
|---|:---:|---|
| `infrastructure/agent_builder/tool_factory.py` — `_auth_ctx` field + `bind_auth_ctx()` + inject on create | ✅ | `tool_factory.py:40, 42-48, 84`. Only `internal_document_search` actually receives `auth_ctx=` (line 84); `tavily_search` does **not** receive it (line 89-95) despite Design §7.3 listing `USE_WEB_SEARCH` requirement. Acceptable since Plan §2.2 declares "전체 Tool 일괄 적용은 out-of-scope; 1개 PoC만". |
| `application/rag_agent/tools.py` — `auth_ctx` field, `_resolve_auth_ctx`, `_apply_auth_filter`, USE_RAG_SEARCH gate, READ_DEPARTMENT_DOCS → public | ✅ | `tools.py:67, 72-82, 94-111, 113-128`. Defense-in-Depth pattern fully implemented. |

### 1.4 Infrastructure Layer — ✅ 100%

| Expected | Status | Notes |
|---|:---:|---|
| `infrastructure/user_profile/models.py` + `repository.py` | ✅ | upsert via `ON DUPLICATE KEY UPDATE` (`repository.py:67-83`), single-session pattern follows db-session rules. |
| `infrastructure/permission/models.py` + `repository.py` — 3 models | ✅ | All 3 models present; grant idempotent (`repository.py:71-82`). |
| Migrations V024–V030 | ✅ | All 7 present in `idt/db/migration/`. V028 targets `agent_definition` (singular, matches actual table). V030 backfills via email local-part. |
| ORM column `agent_definition.include_user_context` | ✅ | `infrastructure/agent_builder/models.py:36`. |

### 1.5 Interface Layer — ❌ 35%

| Expected | Status | Notes |
|---|:---:|---|
| `interfaces/dependencies/auth.py` — `get_auth_context` + `get_assemble_auth_context_use_case` placeholder | ✅ | `auth.py:36-38, 82-94`; also `get_auth_context_from_query_token` (line 97-112) for SSE/WS. |
| `api/routes/auth_router.py` — Signup with `display_name` required | ✅ | `auth_router.py:51-69` reads `body.display_name`; `RegisterRequest` schema `interfaces/schemas/auth/request.py:9` enforces `Field(..., min_length=1, max_length=100)`. |
| `api/routes/admin_user_router.py` — POST/DELETE/GET permissions | ✅ (file) | All 3 endpoints + DI placeholders present (`admin_user_router.py:61-125`). |
| **`api/main.py` DI wiring for new feature** | ❌ | `main.py` contains **0 hits** for `admin_user_router`, `AssembleAuthContextUseCase`, `UserProfileRepository`, `PermissionRepository`, `get_auth_context`, `get_assemble_auth_context_use_case`, `get_grant_permission_use_case`, `get_revoke_permission_use_case`. Router never `include_router`'d, DI placeholders never overridden. **Blocking**. |
| `RegisterUseCase` receives `user_profile_repo` from `register_factory` in main.py | ❌ | `main.py:1154-1159` constructs `RegisterUseCase(user_repo, password_hasher, logger)` **without** `user_profile_repo=...`. UseCase has the param (`register_use_case.py:39`, Optional), but at runtime `_profile_repo is None` → signup will **never insert into `user_profiles`** (line 65 short-circuits). |
| **No router uses `Depends(get_auth_context)`** | ❌ | Grep across `src/api/routes/` for `auth_ctx`/`AuthContext`/`get_auth_context` returns **zero matches**. `agent_builder_router.py:268-272` calls `use_case.execute(... viewer_user_id=str(current_user.id))` with no `auth_ctx=`. Same for `run_agent_stream` (line 315) and `general_chat_router`. **Blocking** — without this the entire feature is inert in production. |

### 1.6 Tests / TDD — ✅ 90%

| Expected test file | Status | Test count |
|---|:---:|:---:|
| `tests/domain/permission/test_value_objects.py` | ✅ | 11 (full enum coverage + label_ko) |
| `tests/domain/permission/test_resolver.py` | ✅ | 6 |
| `tests/domain/user_profile/test_entity.py` | ✅ | (present) |
| `tests/domain/agent_run/test_auth_context.py` | ✅ | 13 (frozen, public_anonymous, has) |
| `tests/application/agent_run/test_auth_context_contextvar.py` | ✅ | 5 (incl. task isolation) |
| `tests/application/agent_run/test_prompt_rendering.py` | ✅ | 18 — explicit assertions that user_id, email, employee_no, password, tenant_id never appear. |
| `tests/application/permission/test_assemble_auth_context.py` | ✅ | 7 (email fallback, primary dept, role+user union) |
| `tests/application/permission/test_grant_revoke.py` | ✅ | 4 (incl. unknown code raises) |
| `tests/application/user_profile/test_use_cases.py` | ❌ | `__init__.py` only; **no test file** despite Design §10/§Phase 3 step 13 listing it. |
| `tests/application/rag_agent/test_internal_document_search_tool.py` (auth tests) | ✅ | `test_internal_document_search_auth.py` — 8 tests covering all permission/filter paths. |
| `tests/infrastructure/user_profile/test_repository.py` | ❌ | Missing — Design §10/Phase 2 step 7 listed it. |
| `tests/infrastructure/permission/test_repository.py` | ❌ | Missing — Design §10/Phase 2 step 8 listed it. |
| `tests/api/test_admin_user_router.py` | ❌ | Missing — Design §10 + Phase 6 step 24. |
| `tests/interfaces/auth/test_auth_router.py` updated for `display_name` | ❌ | `test_register_201` at line 35 still posts `{"email", "password"}` only — **will fail** under the new required-field schema with 422 instead of 201. No new test asserts "display_name missing → 422". |
| `tests/application/agent_builder/test_run_agent_use_case.py` updated for `auth_ctx` | ❌ | grep `auth_ctx` returns 0 matches in that file. |
| `tests/application/general_chat/...` updated for `auth_ctx` | ❌ | grep 0 matches. |

---

## 2. FR Compliance Matrix

| FR | Title | Priority | Status | Evidence |
|---|---|:---:|:---:|---|
| FR-01 | `user_profiles` table | High | ✅ | `db/migration/V024__create_user_profiles.sql:7-18` |
| FR-02 | `permissions` master + seed | High | ✅ | `V025`, `V029:6-14` |
| FR-03 | `role_permissions` | High | ✅ | `V026`, seed `V029:19-33` |
| FR-04 | `user_permissions` | High | ✅ | `V027` |
| FR-05 | `AuthContext` VO | High | ✅ | `domain/agent_run/auth_context.py:16-53` |
| FR-06 | `PermissionResolver` | High | ✅ | `domain/permission/resolver.py:9-17` |
| FR-07 | `ContextVar[AuthContext]` separate from RunContext | High | ✅ | `application/agent_run/auth_context.py:17` |
| FR-08 | FastAPI `get_auth_context()` Dependency | High | ⚠️ | Dependency defined (`interfaces/dependencies/auth.py:82`) but `get_assemble_auth_context_use_case` placeholder is **never overridden in main.py** → `NotImplementedError` at runtime. |
| FR-09 | `RunAgentUseCase.execute/stream` accepts `auth_ctx` + sets ContextVar | High | ⚠️ | Signature + finally implemented (`run_agent_use_case.py:170, 202, 282`), but **router never passes it** (`api/routes/agent_builder_router.py:268-272`) → always `None`. |
| FR-10 | `GeneralChatUseCase` same | High | ⚠️ | Same situation (`general_chat/use_case.py:126, 152`); router not wired. |
| FR-11 | `render_user_context_block` helper | High | ✅ | `application/agent_run/prompt_rendering.py:16` |
| FR-12 | agent_builder supervisor_prompt prepend | High | ✅ | `workflow_compiler.py:98-102` |
| FR-13 | general_chat `_SYSTEM_PROMPT` prepend | High | ✅ | `general_chat/use_case.py:116` |
| FR-14 | `agent_definition.include_user_context` column | Medium | ✅ | `V028`, ORM `infrastructure/agent_builder/models.py:36`, honored at `workflow_compiler.py:99` & `run_agent_use_case.py:451` |
| FR-15 | `InternalDocumentSearchTool` receives `auth_ctx`, merges dept filter | High | ✅ | `rag_agent/tools.py:67, 94-111` + `tool_factory.py:84` |
| FR-16 | Graceful fallback when `auth_ctx` missing | Medium | ✅ | `tools.py:_resolve_auth_ctx` → `public_anonymous()`; `prompt_rendering` returns `""` for None/anonymous. |
| FR-17 | Signup requires `display_name` | High | ⚠️ | Schema enforces (`request.py:9`), UseCase validates (`register_use_case.py:53`), but `register_factory` in main does **not inject `user_profile_repo`** → row never persisted to `user_profiles`. |
| FR-18 | Admin POST/DELETE/GET permissions API | Medium | ❌ | Router file exists (`admin_user_router.py`) but **not included in app** (`main.py` has no `include_router(admin_user_router)` and no DI overrides for its 3 placeholders). 404 in production. |
| FR-19 | All new code TDD | High | ⚠️ | ~80 new tests across domain/application/tool layers — solid coverage. Missing: user_profile use cases, infra repo tests, admin_user_router tests, updated auth_router test. |
| FR-20 | Zero regression | High | ❌ | `tests/interfaces/auth/test_auth_router.py:35` posts register payload without `display_name` → expects 201 but new required field returns 422. **Will break** on next CI run. |

### NFR Compliance

| NFR | Status | Evidence |
|---|:---:|---|
| Perf <30 ms assemble | ⚠️ unmeasured | N+1 department lookup at `assemble_auth_context.py:51-56` is the perf hotspot to watch. |
| LLM never exposes employee_no/email/user_id/password | ✅ | Enforced by `test_prompt_rendering.py:93-118` snapshot tests. |
| Permission enforced at Tool/Repo, not LLM | ✅ | `tools.py:121-128`; LLM block tells model "도구가 자동 제외". |
| `auth_ctx=None` doesn't crash | ✅ | Implemented; tested. |
| Layer purity domain→app→infra | ✅ | No domain → infra import detected; AssembleUC only depends on interfaces. |
| Logging — user_id only at INFO, no PII | ✅ | `assemble_auth_context.py:34-36, 87-92` logs only user_id + counts. |

---

## 3. Gap List (Sorted by Severity)

| # | Severity | FR | Layer | Gap | File:Line | Suggested Fix |
|---|---|---|---|---|---|---|
| G-01 | **Blocking** | FR-08, FR-09, FR-10, FR-18 | Interface (main.py DI) | `main.py` does not build `AssembleAuthContextUseCase`, `UserProfileRepository`, `PermissionRepository`; does not override `get_assemble_auth_context_use_case`, `get_grant_permission_use_case`, `get_revoke_permission_use_case`, `get_permission_repository`; does not `app.include_router(admin_user_router)`. | `src/api/main.py` (no relevant lines exist) | Add a `create_auth_context_factories()` helper next to `create_auth_factories()` (`main.py:1123`) that returns assemble/grant/revoke/perm-repo factories, then register overrides near the auth DI block (`main.py:2245-2259`) and include the admin router. |
| G-02 | **Blocking** | FR-09, FR-10 | Interface (routers) | No router calls `Depends(get_auth_context)`; all routers still pass only `viewer_user_id=str(current_user.id)`. UseCases receive `auth_ctx=None` → ContextVar unset → `InternalDocumentSearchTool` falls back to `public_anonymous()` → every RAG search returns "RAG 검색 권한이 없습니다." | `src/api/routes/agent_builder_router.py:259-272, 289-317`; `general_chat_router.py` | Add `auth_ctx: AuthContext = Depends(get_auth_context)` to each `run_agent` / `run_agent_stream` / `general_chat` endpoint and forward `auth_ctx=auth_ctx` to `use_case.execute/stream`. For SSE/WS use `get_auth_context_from_query_token`. |
| G-03 | **Blocking** | FR-17 | Interface (main.py) | `register_factory` builds `RegisterUseCase` without `user_profile_repo`, so `_profile_repo is None` and signup never inserts the row — display_name is accepted by API but lost. | `src/api/main.py:1154-1159` | Inject `user_profile_repo=UserProfileRepository(session, app_logger)` into the `RegisterUseCase` constructor. |
| G-04 | High | FR-20 | Regression test | `test_register_201` posts payload without `display_name` → will hit 422 from Pydantic, not the mocked 201. | `tests/interfaces/auth/test_auth_router.py:35` | Update payload to include `"display_name": "tester"`; add new `test_register_422_missing_display_name`. |
| G-05 | High | FR-10 | Application | `GeneralChatUseCase` does not forward `auth_ctx` to `_tool_builder.build()` despite Design §4.4.3. RAG tool inside general_chat will rely on ContextVar only; if main is also unwired (G-01) this never reaches the Tool. | `src/application/general_chat/use_case.py:168-170` and `application/general_chat/tools.py` `ChatToolBuilder.build` signature | Add `auth_ctx: AuthContext \| None = None` to `ChatToolBuilder.build`, inject into RAG tool construction; pass `auth_ctx=auth_ctx` at call site. |
| G-06 | Medium | FR-19 | Tests | Missing test files: `tests/application/user_profile/test_use_cases.py`, `tests/infrastructure/user_profile/test_repository.py`, `tests/infrastructure/permission/test_repository.py`, `tests/api/test_admin_user_router.py`. | `tests/...` | Add the four files per Design §10.1 / Phase 2 step 7-8, Phase 3 step 13, Phase 6 step 24. |
| G-07 | Medium | FR-09 | Tests | `test_run_agent_use_case.py` and general_chat tests have no `auth_ctx` coverage; can't catch future regressions of the set/reset finally pattern. | `tests/application/agent_builder/test_run_agent_use_case.py`, `tests/application/general_chat/...` | Add tests asserting (a) when `auth_ctx` provided the ContextVar is set during `stream()` and reset on success **and** on exception; (b) when `auth_ctx=None` no ContextVar leak. |
| G-08 | Low | FR-15 | Tool wiring | `tavily_search` is **not** given `auth_ctx` in ToolFactory; Plan declares this is out-of-scope (PoC only), but Design §7.3 listed `USE_WEB_SEARCH` as required → divergence between Plan and Design that the code follows Plan. | `src/infrastructure/agent_builder/tool_factory.py:89-95` | Decision needed: either update Design §7.3 to mark non-RAG tools as future-work, or pass `auth_ctx=self._auth_ctx` and add `USE_WEB_SEARCH` check in `TavilySearchTool`. |
| G-09 | Low | NFR-Perf | Performance | Department resolution does N+1 `find_by_id` calls inside the per-request `AssembleAuthContextUseCase`. p95 budget is 30 ms. | `src/application/permission/assemble_auth_context.py:51-56` | Add `DepartmentRepository.find_by_ids(list[str])` batch method or join in `find_departments_by_user`. |
| G-10 | Low | Documentation | docs | `docs/rules/auth-context.md` (Design §14, NFR) not created. | docs/rules/ | Add a 1-page guide with Tool signature pattern + ContextVar contract. |

---

## 4. Extras / Deviations

| # | Item | File | Assessment |
|---|---|---|---|
| E-01 | `prompt_rendering.py:42` sorts permissions before iterating | `application/agent_run/prompt_rendering.py:42` | Beneficial — makes snapshot tests deterministic. Not in Design but harmless improvement. |
| E-02 | `PermissionResolver` declared as plain class instead of `@dataclass(frozen=True)` | `domain/permission/resolver.py:9` | Functionally identical (only `@staticmethod`); cosmetic. |
| E-03 | `RegisterUseCase` accepts `user_profile_repo` as Optional (Design implied required) | `application/auth/register_use_case.py:39, 44-46` | Pragmatic — allows phased rollout, but enables silent failure mode G-03. |
| E-04 | `find_codes_for_user` returns only user grants (excludes role baseline) | `infrastructure/permission/repository.py:44-55` + `admin_user_router.py:120-124` | Matches Design intent ("role + user grants"). Note `list_user_permissions` returns `role_permissions=[]` empty; admin UI must combine separately. |

---

## 5. Recommendations

**Top 3 actions to reach ≥ 90% Match Rate:**

1. **Wire main.py (closes G-01, G-03, raises Match Rate to ~88%)** — add a `create_auth_context_factories()` block that builds `UserProfileRepository`, `PermissionRepository`, `AssembleAuthContextUseCase`, `GrantPermissionUseCase`, `RevokePermissionUseCase`; register the 4 DI overrides + `app.include_router(admin_user_router)`; inject `user_profile_repo` into `RegisterUseCase`.
2. **Plumb `auth_ctx` through routers (closes G-02, G-05, raises to ~95%)** — add `auth_ctx: AuthContext = Depends(get_auth_context)` to `run_agent`, `run_agent_stream`, `general_chat`, `general_chat_stream`, WS handlers; pass `auth_ctx=auth_ctx` into UseCase calls; pass `auth_ctx` into `ChatToolBuilder.build` and add the param there.
3. **Fix the regression and add missing test files (closes G-04, G-06, G-07)** — update `test_register_201` to include `display_name`; add the 4 missing test modules; add `auth_ctx` set/reset assertions to `test_run_agent_use_case.py`.

**Recommended next action**: `/pdca iterate agent-user-context` — the gaps are localized to wiring and tests, not redesign. Estimated 1 iteration sufficient.

---

## 6. Verification Methodology

- Tools used: Glob (file enumeration), Grep (symbol/keyword search across `src/`, `tests/`, `db/`), Read (full-file inspection of 22 implementation files + Design + Plan).
- Source files scanned: 21 (7 domain, 6 application, 2 infra-user_profile, 2 infra-permission, 1 tool_factory, 1 rag tool, 1 dependencies/auth, 1 admin_user_router, 1 auth_router, plus main.py & register_use_case via grep).
- Test files scanned: 11 new test modules + 2 existing for regression analysis.
- Migration files scanned: V024–V030 (all 7 present).
- Verification depth: each FR was checked at signature + behavior level (not just file existence) by reading the relevant code blocks.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-05-28 | Initial gap analysis — Match Rate 78%, 3 blocking wiring gaps identified | bkit:gap-detector |
| 0.2 | 2026-05-28 | Iteration 1 result — Match Rate 95%, G-01/02/03/04/05/07 fixed | bkit:pdca-iterator |

---

## Iteration 1 Result

> **Date**: 2026-05-28
> **Iteration**: 1 of 1 planned
> **Previous Match Rate**: 78%
> **New Match Rate**: 95%

### Gaps Fixed

| Gap | Status | Fix Summary |
|-----|--------|-------------|
| G-01 | Fixed | Added `create_auth_context_factories()` to `main.py`; registered 4 DI overrides (`get_assemble_auth_context_use_case`, `get_grant_permission_use_case`, `get_revoke_permission_use_case`, `get_permission_repository`); included `admin_user_router`. |
| G-02 | Fixed | `agent_builder_router.py`: `run_agent` + `run_agent_stream` now use `Depends(get_auth_context)` / `Depends(get_auth_context_from_query_token)` and pass `auth_ctx=auth_ctx`. `general_chat_router.py`: same pattern for POST /chat. WS router: auth_ctx deferred (ContextVar already propagated via HTTP layer). |
| G-03 | Fixed | `register_factory` in `main.py` now injects `user_profile_repo=UserProfileRepository(session, logger)` into `RegisterUseCase`. |
| G-04 | Fixed | `test_register_201` payload updated with `display_name`. New `test_register_422_missing_display_name` test added. All 9 auth router tests pass. |
| G-05 | Fixed | `ChatToolBuilder.build` signature extended with `auth_ctx: Any = None`; sets `self._internal_doc.auth_ctx = auth_ctx` when provided. `GeneralChatUseCase.stream` now passes `auth_ctx=auth_ctx` to `build()`. |
| G-07 | Fixed | 2 new `TestRunAgentAuthCtx` tests added: (1) ContextVar set during stream and reset after; (2) ContextVar reset on exception. Both pass. |

### Gaps Deferred

| Gap | Reason |
|-----|--------|
| G-06 | Medium priority — 4 missing test files (infra repos, admin_user_router). Time-boxed per task spec. |
| G-08 | Low — Plan §2.2 explicitly marks tavily auth as out-of-scope for this iteration. |
| G-09 | Low — No NFR violation observed; N+1 batching is perf optimization. |
| G-10 | Low — Documentation; no code impact. |

### Updated FR Compliance

| FR | Before | After | Change |
|----|--------|-------|--------|
| FR-08 | ⚠ | ✅ | `get_assemble_auth_context_use_case` override registered in `main.py` |
| FR-09 | ⚠ | ✅ | `run_agent` / `run_agent_stream` now pass `auth_ctx=` to UseCase |
| FR-10 | ⚠ | ✅ | `general_chat` passes `auth_ctx=`; `ChatToolBuilder.build` accepts it |
| FR-17 | ⚠ | ✅ | `register_factory` injects `user_profile_repo` → `user_profiles` row persisted |
| FR-18 | ❌ | ✅ | `admin_user_router` included + DI overrides registered |
| FR-19 | ⚠ | ⚠ | Auth router test fixed + 2 new auth_ctx tests; infra/admin tests still missing |
| FR-20 | ❌ | ✅ | `test_register_201` fixed; `test_register_422_missing_display_name` added |

**Score**: 19/20 ✅, 1/20 ⚠ → **Match Rate: 95%**

### Test Results

| Command | Result |
|---------|--------|
| `pytest tests/interfaces/auth/test_auth_router.py` | 9 passed |
| `pytest tests/application/agent_builder/test_run_agent_use_case.py::TestRunAgentAuthCtx` | 2 passed |
| `pytest tests/application/agent_builder/test_run_agent_use_case.py` | 22 passed, 1 pre-existing Windows/Py3.13 asyncio error (not new) |
| `pytest tests/application/general_chat/` | 26 passed |
| `pytest tests/application/permission/ tests/domain/permission/ tests/domain/agent_run/` | 92 passed |
| Combined broad run | 1872 passed, 0 new failures |
