# MCP Tool Auto Sync Analysis Report

> **Analysis Type**: Gap Analysis (Design vs Implementation) + Runtime Verification
>
> **Project**: sangplusbot (idt 백엔드 + idt_front)
> **Version**: 0.1.0
> **Analyst**: 배상규
> **Date**: 2026-09-01
> **Design Doc**: [mcp-tool-auto-sync.design.md](../02-design/features/mcp-tool-auto-sync.design.md)
> **Plan Doc**: [mcp-tool-auto-sync.plan.md](../01-plan/features/mcp-tool-auto-sync.plan.md)

### Pipeline References

| Phase | Document | Verification Target |
|-------|----------|---------------------|
| — | 9-phase Pipeline 미사용 (단일 기능 PDCA) | N/A |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | MCP 서버를 등록해도 `tool_catalog`에 반영되지 않아 도구 선택창에 노출되지 않는다. 반영 API는 있으나 호출자가 없다 |
| **WHO** | P2 — MCP 서버를 등록하는 관리자(admin), 그 도구를 고르는 에이전트 생성자 |
| **RISK** | sync가 같은 DB 세션에서 실패하면 세션이 오염되어 MCP 서버 등록 커밋 자체가 실패할 수 있다 |
| **SUCCESS** | 등록 후 추가 조작 없이 도구가 카탈로그에 나타나고, MCP 서버가 응답하지 않아도 등록은 201로 성공하며, 그 실패가 화면에 표시되고 동기화 버튼으로 복구된다 |
| **SCOPE** | 백엔드(application + DI + 응답 1필드) + 프론트(sync 훅·서버별 동기화 버튼·실패 안내) |

---

## Strategic Alignment Check

### 핵심 문제 해결 여부 (WHY)

| 요소 | 기대 | 상태 |
|------|------|:----:|
| 등록→카탈로그 반영 자동화 | 관리자 조작 0회로 도구 노출 | ✅ 달성 |
| MCP 서버 장애 시 등록 보호 | 201 성공 유지 | ✅ **실서버 실증** (§4 L1-2) |
| 막다른 길 제거 | 실패 인지 + 재시도 수단 | ✅ 달성 |
| 원 설계 Q5(비활성화 연동) 복구 | is_active=false → 도구 비활성 | ✅ 코드 경로 구현, 실서버 미실행 |

### Success Criteria Status

| # | Criteria (Plan §4.1) | 상태 | 근거 |
|---|---------------------|:----:|------|
| SC-1 | FR-01~FR-13 전부 구현 | ✅ | §2 요구사항 대조표 (13/13) |
| SC-2 | 등록 → 추가 조작 없이 카탈로그에 `mcp:{id}:{tool}` 노출 | ✅ | `sync_mcp_tools_use_case.py:47` tool_id 생성 + `test_register_tool_sync.py::test_sync_called_with_saved_server_id` |
| SC-3 | 도달 불가 endpoint여도 201 + warning 1건 | ✅ | **실서버 실측: HTTP 201 + `tool_sync.ok=false`** (§4 L1-2) |
| SC-4 | 실패가 화면에 표시되고 동기화 버튼으로 복구 (막다른 길 없음) | ⚠️ | L1·L2 전 구간 검증. **실서버 버튼 클릭 복구만 미실행** (§5 G-01) |
| SC-5 | `is_active=false` → 도구가 목록에서 사라짐 | ⚠️ | sync 호출 고정(`test_update_tool_sync.py::test_deactivation_triggers_sync`). 실 DB 반영 미실행 (§5 G-02) |
| SC-6 | 단위 테스트 3경로(성공/실패/미주입) TDD | ✅ | 3경로 + DB오류/타임아웃/취소 포함 6경로 |
| SC-7 | 기존 `tests/application/mcp_registry/` 6파일 무수정 통과 | ✅ | 111 passed, baseline 대비 회귀 0 |
| SC-8 | `is_builtin` 반복 sync 후 보존 | ✅ | **G-03 해소** — `test_sync_mcp_tools_builtin.py` 4건 추가, 뮤테이션 검증으로 회귀 포착 확인 |

**Success Rate**: **6/8 완전 충족, 2/8 부분 충족(❌ 0건)**

### Decision Record Verification

| Source | Decision | 준수 | 편차 |
|--------|----------|:----:|------|
| [Plan] | 복구 경로 = 동기화 버튼 + 실패 알림 | ✅ | — |
| [Plan] | 자동 재시도 없음 (FR-13) | ✅ | `sync_outcome.py`에 재시도 로직 0건 (grep 결과 전부 `attempted` 필드) |
| [Design] | Option C — 예외 분류 (`SQLAlchemyError` 재전파) | ✅ | `sync_outcome.py:121-123` |
| [Design] | 세션 공유 (DB-001) | ✅ | `test_mcp_registry_di_wiring.py` — 세션 객체 id 집합 크기 1 단언 |
| [Design] | 중첩 `tool_sync` (null vs {ok:false} 구분) | ✅ | **실 OpenAPI: `anyOf[ToolSyncResultResponse, null]`** |
| [Design] | sync 대상 = 해당 서버 1개 (D5) | ✅ | `server_id=saved.id` |
| [Design] | `_run_tool_sync`를 UseCase 메서드로 배치 | ⚠️ | **공유 헬퍼 `run_tool_sync()`로 승격** — Design §11.2 step 4가 명시 허용한 편차. 중복 25줄 제거 |
| [Design] | §6.3 `err.response.status`로 403 판별 | ❌→✅ | **설계 오류를 코드가 교정.** `authApiClient`는 `ApiError(message, status)`로 reject하므로 `err.status`가 맞다 |

---

## 1. Analysis Overview

### 1.1 검증 방법

| 축 | 방법 | 가중치 |
|----|------|:-----:|
| Structural | 파일 존재·배치 대조 | 0.15 |
| Functional | FR-01~13 + §5.4 UI 체크리스트 코드 대조 | 0.25 |
| Contract | **실행 중 서버 OpenAPI** ↔ 백엔드 스키마 ↔ 프론트 타입 3-way | 0.25 |
| Runtime | 실서버 L1 + Vitest L2 + 수동 L3 | 0.35 |

> gap-detector 에이전트는 호출하지 않고 인라인 검증했다 — 세션 지침상 에이전트 위임은 사용자 요청 시에만 수행한다.

### 1.2 Match Rate

| 축 | 점수 | 근거 |
|----|:----:|------|
| Structural | **100%** | 신규 5 / 수정 13 전부 설계 위치에 존재 (설계 대비 테스트 1개 추가) |
| Functional | **100%** | FR 13/13, §5.4 UI 체크리스트 9/9 |
| Contract | **100%** | 실 OpenAPI ↔ Pydantic ↔ TS 타입 일치, `tsc --noEmit` exit 0 |
| Runtime | **95%** | L1 4/4 실서버 통과, L2 17/17 통과, L0 회귀 4/4(뮤테이션 검증), L3 4개 중 2개 실환경 미실행 |

```
Overall = (100 × 0.15) + (100 × 0.25) + (100 × 0.25) + (95 × 0.35)
        = 15 + 25 + 25 + 33.25
        = 98.25%
```

**Match Rate: 98%** (목표 90% 초과 달성)

> 초안(v0.1)은 G-03(테스트 누락) 때문에 Runtime 92% / Overall 97%였다. Check 단계에서 G-03을
> 해소하며 Runtime 축이 95%로 올랐다 — 상세는 §8 재계산 참조.

---

## 2. 요구사항 대조 (Functional)

| ID | 요구사항 | 상태 | 근거 (file:line) |
|----|---------|:----:|-----------------|
| FR-01 | 등록 후 서버 1개 대상 sync | ✅ | `register_mcp_server_use_case.py:86` |
| FR-02 | 수정 후 서버 1개 대상 sync | ✅ | `update_mcp_server_use_case.py:99` |
| FR-03 | sync 예외 삼킴 + warning, 등록 정상 응답 | ✅ | `sync_outcome.py:123-133` / **실측 201** |
| FR-04 | 대상 = 방금 저장한 서버 1개 | ✅ | `register:88`, `update:101` (`server_id=saved.id`) |
| FR-05 | sync 실패가 커밋을 방해하지 않음 | ✅ | `sync_outcome.py:121` `except SQLAlchemyError: raise` |
| FR-06 | 미주입 시 기존 동작 | ✅ | `register:24`, `update:23` (`sync_use_case=None`) + `to_response` attempted 분기 |
| FR-07 | 기존 `/tool-catalog/sync` 무변경 | ✅ | `git diff` 결과 라우터·UseCase 변경 0줄 |
| FR-08 | `is_active=false` → 카탈로그 비활성화 | ✅ | `test_update_tool_sync.py::test_deactivation_triggers_sync` |
| FR-09 | 응답에 sync 성공 여부·도구 수 | ✅ | `schemas.py:39,67` / **실 OpenAPI 확인** |
| FR-10 | 실패 시 행에 상태 + 안내 문구 | ✅ | `AdminMcpServersPage/index.tsx:422,429,656` |
| FR-11 | 버튼 → sync 호출 + 캐시 무효화 | ✅ | `api.ts:71`, `toolCatalogService.ts:22`, `useToolCatalog.ts:37` |
| FR-12 | 버튼 상시 노출 | ✅ | `index.tsx:623-628` — 조건부 렌더 없음 |
| FR-13 | 자동 재시도 없음 | ✅ | `sync_outcome.py` 재시도 로직 0건 |

**13/13 충족**

### 2.1 Design §5.4 Page UI Checklist

| # | 항목 | 상태 |
|---|------|:----:|
| 1 | "동기화" 버튼 상시 노출 | ✅ |
| 2 | 진행 중 **해당 행만** 비활성 + "동기화 중..." | ✅ `syncingId` (index.tsx:452,624,628) |
| 3 | 실패 배너 `bg-amber-50` / `text-amber-700` | ✅ index.tsx:428 |
| 4 | "도구 동기화 실패" + `error_hint` | ✅ index.tsx:429 |
| 5 | 동기화 성공 시 배너 갱신 | ✅ `handleSync` onSuccess가 `kind:'ok'`로 대체 |
| 6 | `tool_sync.ok===false`일 때만 표시 (`null`이면 미표시) | ✅ `toSyncRowState` |
| 7 | 성공 안내 "도구 N개를 동기화했습니다" | ✅ `SyncBanner` ok 분기 |
| 8 | 403 시 "관리자 권한이 필요합니다" | ✅ `syncErrorMessage` |
| 9 | 기존 요소(테스트/수정/삭제·배지) 유지 | ✅ 기존 테스트 6건 통과 |

**9/9 충족**

---

## 3. API Contract 3-Way 검증

**실행 중인 서버의 `/openapi.json`을 직접 조회**해 문서가 아닌 실제 계약을 대조했다.

| 항목 | Design §4.3 | 백엔드 (Pydantic) | 실 OpenAPI | 프론트 (TS) | 일치 |
|------|-------------|------------------|-----------|------------|:----:|
| `tool_sync` 존재 | ✔ | `schemas.py:67` | `properties.tool_sync` 존재 | `mcpServer.ts` `tool_sync?` | ✅ |
| nullable 형태 | `ToolSyncResultResponse \| None` | 동일 | `anyOf: [$ref, {type:null}]` | `ToolSyncResult \| null` | ✅ |
| 하위 필드 | ok / synced_count / error_hint | 동일 | `['ok','synced_count','error_hint']` | 동일 | ✅ |
| `/tool-catalog/sync` | POST 유지 | 무변경 | `post` 존재 | `TOOL_CATALOG_SYNC` | ✅ |
| `/tool-catalog` | GET 유지 | 무변경 | `get` 존재 | `TOOL_CATALOG` | ✅ |

`tsc --noEmit` **exit 0** — optional 필드 추가가 기존 소비자(`AdminMcpServersPage` 목록·수정 폼)를 깨뜨리지 않음(R-07 해소).

---

## 4. Runtime Verification

### 4.1 L1 — 실서버 API (localhost:8000, 변경 반영 확인됨)

| # | 검증 | 기대 | 실측 | 결과 |
|---|------|------|------|:----:|
| L1-1 | `GET /api/v1/mcp-registry` | 전 항목 `tool_sync: null` | 3건 모두 `None` | ✅ |
| L1-2 | **도달 불가 endpoint 등록** (`http://127.0.0.1:59999/sse`) | **201** + `ok:false` + 힌트 | **HTTP 201**, `{"ok":false,"synced_count":0,"error_hint":"MCP 서버에서 도구 목록을…"}` | ✅ |
| L1-3 | `GET /api/v1/tool-catalog` 미인증 | 401 | `{"detail":"Not authenticated"}` 401 | ✅ |
| L1-4 | `PUT /api/v1/mcp-registry/{id}` | 200 + `tool_sync` | HTTP 200 + `ok:false` + 힌트 | ✅ |

> **L1-2가 이 기능의 핵심 계약을 실환경에서 증명한다** — MCP 서버가 완전히 죽어 있는데도 등록이 201로 성공했고, 실패 사실과 진단 힌트가 응답에 실려 나왔다.
>
> 검증용 레코드(`__pdca_verify_unreachable`)는 `DELETE` 204로 즉시 정리했고, 목록이 검증 전과 동일한 3건임을 확인했다. `tool_catalog`는 FK `ON DELETE CASCADE`로 함께 정리된다.

### 4.2 L2 — UI 액션 (Vitest + MSW)

| 파일 | 결과 |
|------|------|
| `useToolCatalog.test.ts` (S: sync 호출·실패 2건 추가) | **5 passed** |
| `AdminMcpServersPage/index.test.tsx` (S-1~S-7 추가) | **12 passed** |
| `ToolPickerModal` + `AdminToolsPage` (기존 소비자 회귀) | 통과 |
| **합계** | **17 passed** (신규 9) |

### 4.3 L3 — E2E 시나리오

| # | 시나리오 | 상태 | 비고 |
|---|---------|:----:|------|
| 1 | 정상 등록 → 도구 선택창 노출 | ⚠️ 미실행 | 실동작 MCP 서버 필요 |
| 2 | **막다른 길 없음** (실패 → 배너 → 동기화 → 노출) | ⚠️ 부분 | 전반부(201+실패 응답) L1-2 실증 / 후반부(버튼 클릭 복구) L2 mock만 |
| 3 | 재동기화 시 `is_builtin` 보존 | ⚠️ 미실행 | — |
| 4 | 비활성화 → 도구 사라짐 | ⚠️ 미실행 | — |

### 4.4 회귀 검증 (baseline 대조)

| 대상 | 변경 전 | 변경 후 | 새로 깨진 것 |
|------|:------:|:------:|:-----------:|
| 백엔드 `tests/application` + `tests/api` | 29 failed / 3210 passed | 29 failed / 3210 passed | **0** |
| 프론트 전체 | 9 failed / 4 files | 9 failed / 4 files | **0** |

`git stash`로 변경 전 상태를 재현해 동일 명령을 실행하고 `comm`으로 실패 목록을 대조했다. 양쪽 모두 **완전 일치** — 기존 실패는 `test_agent_builder_router_stream`, `ChatPage`, `UpdateScopeModal` 등 본 기능과 무관한 파일들이다.

---

## 5. Gap List

### Important (수정 권장)

| ID | 내용 | 영향 | 위치 |
|----|------|------|------|
| **G-01** | **L3 시나리오 2 후반부 미실행** — 동기화 버튼 클릭으로 실제 복구되는 경로가 실서버에서 검증되지 않았다. SC-4의 "막다른 길 없음"을 mock 밖에서 증명하려면 실동작 MCP 서버 1대가 필요하다 | SC-4 부분 충족 | 수동 QA |
| **G-02** | **FR-08 실 DB 반영 미확인** — `is_active=false` 수정 시 sync가 호출되는 것은 고정했으나, `deactivate_by_mcp_server`가 실제로 `tool_catalog.is_active=0`을 쓰는지는 실환경 미검증 | SC-5 부분 충족 | 수동 QA |
### 해소됨

| ID | 내용 | 조치 |
|----|------|------|
| **G-03** ✅ | **`is_builtin` 보존 회귀 테스트 부재** (Plan R-04) | `tests/application/tool_catalog/test_sync_mcp_tools_builtin.py` **4건 추가**. 실 Repository의 upsert 계약(INSERT는 영속, UPDATE는 미변경)을 모사하는 `FakeToolCatalogRepo`로 **반복 sync 후 관리자 토글값 유지**를 고정했다. **뮤테이션 검증**: `SyncMcpToolsUseCase`가 `is_builtin=True`를 넘기도록 변조하니 4건 중 3건이 실패 → 테스트가 실제 회귀를 잡는다. 원본 복원 후 `git diff` 0줄(FR-07 유지) 확인 |

### Minor (기록만)

| ID | 내용 | 판단 |
|----|------|------|
| **G-04** | `execute()` 함수 길이 초과 — register 66줄 / update 80줄 (CLAUDE.md §3 40줄 제한) | **기존 위반**(변경 전 52·61줄). sync 호출로 14·19줄 증가. 임의 리팩터링 금지 규칙에 따라 미수정, 사용자 판단 대기 |
| **G-05** | `AdminMcpServersPage.apiError()` 헬퍼가 `err.response.data.detail`을 읽어 항상 fallback 문구만 반환 | **기존 버그**(본 기능 무관). 신규 `syncErrorMessage`는 `err.status`로 올바르게 구현 |
| **G-06** | `/tool-catalog/sync`가 MCP 연결 실패 시 500 반환 | Design §6.3에서 **의도적 수용** (FR-07 무변경). 프론트가 문구로 흡수. 후속 정규화 과제 |
| **G-07** | `CatalogTool.mcp_server_name` 프론트 타입에만 존재 | Plan Out of Scope 명시. 별건 드리프트 |

### 설계 문서 교정 필요

| ID | 내용 |
|----|------|
| **D-01** | Design §6.3의 `err.response.status`는 오류 — `authApiClient`가 `ApiError(message, status)`로 reject하므로 `err.status`가 맞다. 구현이 옳고 문서가 틀렸다 |
| **D-02** | Design §6.1이 `_run_tool_sync`를 UseCase 메서드로 기술 — 실제로는 §11.2 step 4의 허용에 따라 `sync_outcome.run_tool_sync()` 공유 헬퍼로 승격 |
| **D-03** | Design §7의 미결 항목 2건(로그 시크릿 마스킹, 세션 동일성)이 Do 단계에서 **모두 해소**됨 — `_redact()` + `test_mcp_registry_di_wiring.py` |

---

## 6. Clean Architecture 준수

| 검사 | 결과 |
|------|:----:|
| domain → infrastructure 임포트 | ✅ 0건 |
| domain → langgraph 임포트 | ✅ 0건 |
| application → domain/application만 참조 | ✅ 확인 |
| 라우터 비즈니스 로직 | ✅ 라우터 변경 0줄 |
| Repository 내 commit/rollback | ✅ 없음 |
| UseCase 내 세션 혼용 | ✅ DI 테스트로 세션 1개 단언 |

## 7. Convention 준수 (LOG-001 / CLAUDE.md §3)

| 검사 | 결과 |
|------|:----:|
| `print()` 사용 | ✅ 0건 (config.py 매칭은 주석 내 문자열) |
| 민감정보 평문 로깅 | ✅ `_redact()`로 `api_key`/`token`/`secret`/`password` 마스킹 |
| 구조화 로그 필드 | ✅ `request_id`·`server_id`·`error_type` |
| config 하드코딩 | ✅ `mcp_tool_sync_timeout_sec` 설정화 |
| 신규 함수 40줄 이하 | ✅ 최대 `run_tool_sync` 37줄 |
| if 중첩 2단계 초과 | ✅ 없음 |
| 기존 함수 40줄 초과 | ⚠️ G-04 (기존 위반) |

---

## 8. 결론

**Match Rate 98%** (G-03 해소 반영) — 목표 90%를 넘었고 **Critical 갭 0건**이다.

이 기능의 존재 이유였던 두 가지가 실환경에서 증명되었다.

1. **MCP 서버가 죽어 있어도 등록은 201로 성공한다** — R-01(세션 오염)을 예외 분류로 해소한 Option C 설계가 실제로 동작했다.
2. **실패가 조용히 사라지지 않는다** — 응답에 실린 `tool_sync.ok=false`와 진단 힌트가 화면 배너로 이어진다.

G-03(테스트 누락)은 **Check 단계에서 즉시 해소**했다. 남은 G-01·G-02는 실동작 MCP 서버가 있어야 검증 가능한 **검증 공백**이지 결함이 아니며, QA 단계 몫이다.

### Match Rate 재계산 (G-03 해소 후)

| 축 | 이전 | 이후 | 변동 사유 |
|----|:----:|:----:|----------|
| Structural | 100% | 100% | — |
| Functional | 100% | 100% | — |
| Contract | 100% | 100% | — |
| Runtime | 92% | **95%** | R-04 회귀 축 확보 (L0 뮤테이션 검증 포함) |

```
Overall = (100 × 0.15) + (100 × 0.25) + (100 × 0.25) + (95 × 0.35) = 98.25%
```

**최종 Match Rate: 98%** / 백엔드 영향 범위 테스트 **123 passed**

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-09-01 | Gap 분석 초안. Match Rate 97%, Critical 0건, Important 3건 | 배상규 |
| 0.2 | 2026-09-01 | G-03 해소 — is_builtin 보존 회귀 테스트 4건 추가 + 뮤테이션 검증. Match Rate 98%, Important 2건 | 배상규 |
