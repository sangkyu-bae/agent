# naver-search-mcp-integration Gap Analysis Report

> **Summary**: Design vs implementation Check-phase gap analysis for the Smithery Naver Search MCP (Streamable HTTP) integration into `mcp_registry`.
>
> **Project**: sangplusbot (idt)
> **Author**: 배상규
> **Created**: 2026-06-16
> **Last Modified**: 2026-06-16
> **Status**: Review
> **Design Doc**: [naver-search-mcp-integration.design.md](../02-design/features/naver-search-mcp-integration.design.md)

---

## 1. Analysis Overview

- **Analysis Target**: naver-search-mcp-integration (backend, `idt/`)
- **Design Document**: `docs/02-design/features/naver-search-mcp-integration.design.md`
- **Implementation Path**: `src/domain/mcp_registry/`, `src/application/mcp_registry/`, `src/infrastructure/mcp_registry/`, `src/infrastructure/security/`, `src/domain/mcp/`, `db/migration/`, `src/config.py`, `src/api/main.py`
- **Analysis Date**: 2026-06-16
- **Method**: Per-requirement file:line verification of 13 design items (FR/components) against actual code.

---

## 2. Overall Scores

| Category | Score | Status |
|----------|:-----:|:------:|
| Design Match | 98% | ✅ |
| Architecture Compliance (DDD) | 100% | ✅ |
| Convention Compliance | 95% | ✅ |
| **Overall Match Rate** | **97%** | ✅ |

**Verdict**: Design and implementation match very well. All 13 core design items are Implemented. Two minor non-blocking hygiene gaps (dependency declaration + `.env.example` documentation). No DDD violations, no secret leakage, no hardcoded secrets.

**Item tally**: Implemented **13** / Partial **0** / Missing **0** (13 design items). Two findings are project-hygiene deviations, not unimplemented design items.

---

## 3. Per-Requirement Verification

| # | Design Item | Status | Evidence (file:line) |
|---|-------------|:------:|----------------------|
| 1 | Domain `schemas.py`: `STREAMABLE_HTTP` enum, `auth_config`/`server_config` fields, `masked_auth()`/`masked_server_config()`, `mask_secrets()` helper, `apply_update` accepts transport/auth/server | ✅ Implemented | `src/domain/mcp_registry/schemas.py:11` (enum), `:42-43` (fields), `:14-24` (`mask_secrets`, recursive), `:50-56` (masked methods), `:64-92` (`apply_update`) |
| 2 | Domain `policies.py`: `validate_transport()` whitelist, `validate_auth()` requires api_key for streamable_http | ✅ Implemented | `src/domain/mcp_registry/policies.py:12` (`ALLOWED_TRANSPORTS`), `:39-42` (`validate_transport`), `:44-56` (`validate_auth`) |
| 3 | Domain `value_objects.py`: `MCPTransport.STREAMABLE_HTTP` + `StreamableHTTPServerConfig` (prerequisite) | ✅ Implemented | `src/domain/mcp/value_objects.py:18` (enum), `:80-87` (`StreamableHTTPServerConfig`), `:124` (transport map) |
| 4 | Application `schemas.py`: Request/Update gain transport/auth/server; Response masked fields; `to_response` masks | ✅ Implemented | `src/application/mcp_registry/schemas.py:15-25` (Register), `:34-36` (Update), `:51-52` (Response), `:73-74` (`to_response` masking) |
| 5 | `register_mcp_server_use_case.py`: no SSE hardcode, uses `request.transport`, validates transport+auth, stores plaintext secrets on entity; `update_*` handles transport/secrets | ✅ Implemented | `register_mcp_server_use_case.py:41-46` (validate), `:55` (`transport=MCPTransportType(request.transport)`), `:60-61` (secrets on entity); `update_mcp_server_use_case.py:40-56` (transport+secrets via `apply_update`) |
| 6 | `secret_cipher.py` (NEW): `SecretCipher` Fernet `encrypt_dict`/`decrypt_dict` | ✅ Implemented | `src/infrastructure/security/secret_cipher.py:12-41` — also raises on empty key (`:21`), `None→None` round-trip (`:25,32`) |
| 7 | `smithery_url.py` (NEW): `build_streamable_http()` — /mcp path fix, api_key/profile query, base64 JSON config query, headers from auth_config | ✅ Implemented | `src/infrastructure/mcp_registry/smithery_url.py:14-20` (`_ensure_mcp_path`), `:23-28` (`_encode_config` base64), `:50-53` (api_key/profile), `:54-56` (config), `:59` (headers) |
| 8 | `mcp_server_repository.py`: optional `cipher` param; `_to_model` encrypts, `_to_entity` decrypts; back-compat when None | ✅ Implemented | `mcp_server_repository.py:62-69` (optional `cipher`), `:13-31` (`_to_model` encrypt, guarded), `:34-55` (`_to_entity` decrypt, guarded `if cipher is not None`) |
| 9 | `models.py`: `auth_config_enc`/`server_config_enc` nullable Text columns | ✅ Implemented | `src/infrastructure/mcp_registry/models.py:21-22` (both `Text, nullable=True`) |
| 10 | `mcp_tool_loader.py`: transport branch building `StreamableHTTPServerConfig`, SSE preserved | ✅ Implemented | `mcp_tool_loader.py:26-45` (`_build_config` early-return branch, SSE fallback at `:41-45`) |
| 11 | DB migration `V032__alter_mcp_server_registry_add_secrets.sql` (NEW) | ✅ Implemented | `db/migration/V032__alter_mcp_server_registry_add_secrets.sql:1-5`; correctly sequenced after `V031` (latest pre-existing) |
| 12 | Config `config.py`: `mcp_secret_key` | ✅ Implemented | `src/config.py:100` (`mcp_secret_key: str = ""`, documented default = encryption disabled) |
| 13 | Wiring `api/main.py`: `_mcp_cipher()` helper + cipher injected at all `MCPServerRepository(...)` sites | ✅ Implemented | `src/api/main.py:334-340` (`_mcp_cipher`), injected at `:1757-1758`, `:2280`, `:2297`, `:2365` — all 4 sites covered |

---

## 4. Differences Found

### 🔴 Missing Features (Design O, Implementation X)

None.

### 🟡 Added / Deviation (hygiene — not in core 13 items)

| # | Item | Location | Severity | Description |
|---|------|----------|:--------:|-------------|
| D1 | `cryptography` not a direct dependency | `pyproject.toml:50` | **Medium** | Design §11.3 requires verifying/adding `cryptography`. It is present only transitively via `python-jose[cryptography]`. Fernet imports work today (installed in `.venv`), but the direct usage in `secret_cipher.py` should be declared explicitly to avoid breakage if jose's extra changes. |
| D2 | `MCP_SECRET_KEY` absent from `.env.example` | `.env.example` (no entry) | **Low** | Convention §10 / Phase-2 env convention expects the new server-only secret documented in the template. `config.py:99` has a generation hint comment, but `.env.example` has no `MCP_SECRET_KEY=` line. |

### 🔵 Changed Features (Design ≠ Implementation)

None of consequence. Minor naming note (not a defect):

| Item | Design | Implementation | Impact |
|------|--------|----------------|:------:|
| Settings key casing | `settings.MCP_SECRET_KEY` (doc uses UPPER) | `settings.mcp_secret_key` (pydantic field, env `MCP_SECRET_KEY`) | None — pydantic maps env var `MCP_SECRET_KEY` → field `mcp_secret_key`; design intent preserved |

---

## 5. Architecture & Security Review (DDD / NFR)

| Check | Result | Evidence |
|-------|:------:|----------|
| domain has no infra/network/crypto imports | ✅ Pass | `schemas.py` imports only `dataclasses`/`datetime`/`enum`; `policies.py` only `urllib.parse`; `mask_secrets` is pure dict transform |
| Encryption confined to infra boundary (Repository) | ✅ Pass | Encrypt/decrypt only in `mcp_server_repository._to_model`/`_to_entity`; UseCases handle plaintext dicts only |
| Loader uses plaintext dict (no decrypt in loader) | ✅ Pass | `mcp_tool_loader.py` consumes `registration.auth_config`/`server_config` already-decrypted by repository |
| Response masking applied | ✅ Pass | `to_response` calls `masked_auth()`/`masked_server_config()` (`schemas.py:73-74`); recursive masking covers nested `headers` |
| No plaintext secrets in logs | ✅ Pass | UseCase/loader logs carry `request_id`, `name`, `id`, `transport` only — never `auth_config`/`server_config` values |
| No hardcoded secret key | ✅ Pass | Key sourced from `settings.mcp_secret_key`; `SecretCipher.__init__` raises on empty key |
| Back-compat / non-destructive | ✅ Pass | Migration columns nullable; Request fields Optional with `transport` default `"sse"`; repository tolerates `cipher=None` (SSE path) |
| Secrets not stored in vector/conversation DB | ✅ Pass | Secrets only in `mcp_server_registry.*_enc` (Fernet); no vector/conversation write path |
| Function length ≤40 lines, if-nesting ≤2 | ✅ Pass | `build_streamable_http`, `_build_config` use early-return; all helpers small |

**Known-OK (per task brief)**: Router test flakiness in `tests/api/test_mcp_registry_router.py` is the pre-existing Windows event-loop teardown issue (run isolated to verify) — not a regression from this feature. Out-of-scope per design: real Smithery E2E, frontend UI, KMS/Vault.

### Test coverage (verification confidence)
All design layers have dedicated unit tests:
- `tests/domain/mcp_registry/test_policies_transport_auth.py`, `tests/domain/mcp/test_value_objects.py`
- `tests/infrastructure/security/test_secret_cipher.py`, `tests/infrastructure/mcp_registry/test_smithery_url.py`, `test_mcp_tool_loader_streamable.py`
- `tests/application/mcp_registry/test_register_streamable_http.py`
- `tests/api/test_mcp_registry_router.py`

---

## 6. Recommended Actions

### Immediate Actions
1. **D1 (Medium)** — Add `cryptography>=42` (or current pin) as a direct dependency in `pyproject.toml`. `secret_cipher.py` imports `cryptography.fernet` directly; relying on `python-jose`'s transitive extra is fragile.

### Documentation Update Needed
2. **D2 (Low)** — Add a `MCP_SECRET_KEY=` line to `.env.example` under an MCP Registry section, with the existing generation hint, so operators know the server-only key exists (Phase-2 env convention).

### No Action Needed
3. Settings casing difference (`mcp_secret_key` field vs `MCP_SECRET_KEY` env) is correct pydantic behavior — design intent preserved.

---

## 7. Match Rate Calculation

```
Core design items (13): 13 Implemented, 0 Partial, 0 Missing → 100% of required scope
Deductions:
  - D1 cryptography not direct dep (Medium hygiene)  -2%
  - D2 MCP_SECRET_KEY missing from .env.example (Low) -1%
Overall Match Rate = 97%  → ✅ (≥90%: proceed to report)
```

**Next step**: Match Rate ≥ 90% → eligible for `/pdca report naver-search-mcp-integration`. Optionally address D1/D2 first (both are <30 min fixes) for a clean 100%.

---

## Post-Analysis Resolution (2026-06-16)

분석에서 식별된 2개 하이진 갭을 즉시 해소함 → **Match Rate 97% → 100% (effective)**.

| Gap | 조치 | 위치 |
|-----|------|------|
| `cryptography` 직접 의존성 미선언 | `pyproject.toml` dependencies에 `cryptography>=42.0.0` 추가 | `pyproject.toml:54` |
| `MCP_SECRET_KEY` 문서화 누락 | `.env.example`에 키 + 생성 명령 주석 추가 | `.env.example` |

잔여 미결: 실 Smithery E2E(qualifiedName/`config` 전달 규칙 실측)는 설계상 out-of-scope(옵트인)로 유지.

---

## Related Documents
- Design: [naver-search-mcp-integration.design.md](../02-design/features/naver-search-mcp-integration.design.md)
- Plan: [naver-search-mcp-integration.plan.md](../01-plan/features/naver-search-mcp-integration.plan.md)
- Prerequisite Plan: [mcp-http-call-module.plan.md](../01-plan/features/mcp-http-call-module.plan.md)
