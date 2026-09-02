# MCP Tool Auto Sync Design Document

> **Summary**: MCP 서버 등록/수정 UseCase가 같은 세션으로 `SyncMcpToolsUseCase`를 호출하되 예외를 `SQLAlchemyError`(재전파)와 그 외(삼킴)로 분류해 세션 오염 없이 best-effort를 보장하고, `SyncOutcome`을 응답 `tool_sync`로 실어 관리 화면에서 실패 인지·재동기화를 가능하게 한다
>
> **Project**: sangplusbot (idt 백엔드 + idt_front)
> **Version**: 0.1.0
> **Author**: 배상규
> **Date**: 2026-08-31
> **Status**: Draft
> **Planning Doc**: [mcp-tool-auto-sync.plan.md](../../01-plan/features/mcp-tool-auto-sync.plan.md)

### Pipeline References

| Phase | Document | Status |
|-------|----------|--------|
| Phase 1~4 | 9-phase Pipeline 미사용 (단일 기능 PDCA) | N/A |

---

## Context Anchor

> Plan 문서에서 복사. Design→Do 핸드오프에서 전략 맥락이 유실되지 않도록 유지한다.

| Key | Value |
|-----|-------|
| **WHY** | MCP 서버를 등록해도 `tool_catalog`에 반영되지 않아 도구 선택창에 노출되지 않는다. 반영 API는 있으나 호출자가 없다 |
| **WHO** | P2 — KB 운영자 / 에이전트 소유자 중 **MCP 서버를 등록하는 관리자(admin)**, 그리고 그 도구를 고르는 에이전트 생성자 |
| **RISK** | sync가 같은 DB 세션에서 실패하면 세션이 오염되어 **MCP 서버 등록 커밋 자체가 실패**할 수 있다 (best-effort 계약 위반) |
| **SUCCESS** | MCP 서버 등록 후 추가 조작 없이 `GET /api/v1/tool-catalog`에 해당 서버 도구가 나타나고, MCP 서버가 응답하지 않아도 등록은 201로 성공하며, 그 실패가 화면에 표시되고 동기화 버튼으로 복구된다 |
| **SCOPE** | 백엔드(application 레이어 + DI 배선 + 응답 스키마 1필드) + 프론트(sync 훅·서버별 동기화 버튼·실패 안내). 스케줄러·자동 재시도는 범위 밖 |

---

## 1. Overview

### 1.1 Design Goals

1. **best-effort 계약을 실제로 지킨다** — MCP 서버가 죽어 있어도 등록은 201로 성공한다. 단순히 `except Exception`으로 삼키는 것으로는 부족하다(§2.0 참조).
2. **DB-001을 위반하지 않는다** — 요청 1건 = 세션 1개. sync 전용 세션을 새로 만들지 않는다.
3. **레이어를 늘리지 않는다** — CLAUDE.md §6의 "과도한 추상화(두꺼운 DDD)" 금지에 따라 신규 Port·Orchestrator를 만들지 않는다.
4. **막다른 길을 만들지 않는다** — sync가 실패해도 관리자가 화면에서 인지하고 재시도할 수 있다.
5. **기존 소비자를 깨뜨리지 않는다** — UseCase 생성자 인자와 응답 필드 모두 optional.

### 1.2 Design Principles

- **부수효과는 주 트랜잭션을 인질로 잡지 않는다** — 단, "삼킬 수 있는 실패"와 "삼키면 안 되는 실패"를 구분한다.
- **네트워크 I/O를 DB 쓰기보다 앞에 둔다** — 실패 대부분이 DB를 건드리기 전에 끝나게 한다.
- **실패는 조용히 사라지지 않는다** — 로그 + 응답 + 화면 + 복구 수단까지 한 세트.
- **진단 정보는 가공해서 노출한다** — 원본 예외 메시지를 그대로 클라이언트에 보내지 않는다.

---

## 2. Architecture Options

### 2.0 Architecture Comparison

| Criteria | Option A: Minimal | Option B: Clean | **Option C: Pragmatic** |
|----------|:-:|:-:|:-:|
| **Approach** | UseCase에 optional 주입 + `except Exception` 일괄 삼킴 | domain에 `ToolCatalogSyncPort` + 오케스트레이션 UseCase 2개 신설 | UseCase에 optional 주입 + **예외 분류** + `SyncOutcome` 반환 |
| **세션 정책** | 공유 (DB-001 ✅) | 공유 (DB-001 ✅) | 공유 (DB-001 ✅) |
| **New Files** | 0 | 3 | 1 |
| **Modified Files** | 8 | 9 | 9 |
| **Complexity** | Low | High | Medium |
| **Maintainability** | Medium | High | High |
| **Effort** | Low | High | Medium |
| **Risk** | **High — R-01 미해결** | Low | Low |
| **Recommendation** | — | 소비자가 3곳 이상일 때 | **선택** |

**Selected**: **Option C — Pragmatic**

**Rationale**:

**Option A가 탈락한 이유** — 이 설계의 핵심 함정이다. `except Exception`으로 삼켜도 `SQLAlchemyError`가 발생한 `AsyncSession`은 `PendingRollbackError` 상태로 남는다. 예외를 삼킨 뒤 UseCase는 정상 반환하지만, `get_session` dependency가 `session.begin()` 블록을 빠져나가며 커밋할 때 터진다. 결과적으로 **등록 API가 500으로 실패**한다 — "실패해도 등록은 성공"이라는 요구사항(FR-03)이 정확히 이 구간에서 깨진다.

**Option B가 탈락한 이유** — `SyncMcpToolsUseCase`의 소비자는 Register/Update 2곳뿐이다. Port 추상화의 이득(교체 가능성·테스트 격리)이 없고, CLAUDE.md §6이 "과도한 추상화(두꺼운 DDD)"를 명시적으로 금지한다. 기존 코드베이스에서도 `SyncInternalToolsUseCase`가 부팅 훅에서 직접 호출되지, Port를 거치지 않는다.

**Option C를 고른 이유** — 배치는 A와 동일하되 예외를 두 부류로 나눈다.

| 실패 유형 | 세션 상태 | 처리 | 근거 |
|-----------|----------|------|------|
| `list_tools()` 실패 — MCP 서버 다운·인증 오류·타임아웃 | **깨끗함** (DB 미접촉) | **삼킴** + warning + `SyncOutcome.failed()` | 우리가 대비하려는 바로 그 실패. 세션이 멀쩡하므로 등록 커밋에 지장 없음 |
| `upsert_by_tool_id()` 실패 — `SQLAlchemyError` | 오염됨 | **재전파** | 삼켜도 커밋이 실패한다. DB가 고장난 상황에서 등록만 성공시킬 방법은 없으므로 정직하게 500을 낸다 |

`SyncMcpToolsUseCase`가 이미 `list_tools()`(네트워크) → `upsert` 루프(DB) 순서로 실행되므로, **실무에서 압도적으로 흔한 실패(MCP 서버 무응답)에서는 DB가 아직 손대지지 않았고 세션이 무결하다.** 즉 예외 분류만으로 R-01이 해소된다.

### 2.1 Component Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│ POST /api/v1/mcp-registry   (요청 1건 = AsyncSession 1개)             │
└───────────────────────────────┬──────────────────────────────────────┘
                                ▼
                 ┌──────────────────────────────┐
                 │ RegisterMCPServerUseCase     │
                 │  ① 정책 검증                  │
                 │  ② repo.save()   ← DB write  │
                 │  ③ _run_sync()   ← 신규       │
                 └──────────────┬───────────────┘
                                ▼
                 ┌──────────────────────────────┐
                 │ SyncMcpToolsUseCase (재사용)  │
                 │  a. find_by_id (DB read)     │
                 │  b. list_tools  ← 네트워크 ⚠ │
                 │  c. upsert 루프  ← DB write  │
                 └──────────────┬───────────────┘
                                │
        b 실패 ──▶ SyncOutcome.failed(hint)  ─┐  세션 무결 → 등록 커밋 OK
        c 실패 ──▶ SQLAlchemyError 재전파      │  세션 오염 → 요청 전체 롤백
        성공   ──▶ SyncOutcome.ok(count)      │
                                              ▼
                        MCPServerResponse.tool_sync
                                              ▼
                        AdminMcpServersPage — 실패 배지 + 안내
                                              ▼
                        [도구 동기화] 버튼 → POST /tool-catalog/sync
```

### 2.2 Data Flow

**정상 경로**
```
관리자 등록 → 서버 저장 → list_tools() → tool_catalog upsert N건
  → 201 + tool_sync{ok:true, synced_count:N}
  → 에이전트 생성 화면 도구 선택창에 MCP 배지와 함께 노출
```

**MCP 서버 무응답 경로 (핵심 시나리오)**
```
관리자 등록 → 서버 저장 → list_tools() 타임아웃/404
  → warning 로그 (request_id, server_id, error)
  → 201 + tool_sync{ok:false, synced_count:0, error_hint:"..."}
  → 화면에 "도구 동기화 실패" 배지 + 안내 문구
  → 관리자가 [도구 동기화] 클릭 → POST /tool-catalog/sync {mcp_server_id}
  → 성공 시 toolCatalog 캐시 무효화 → 도구 노출
```

**비활성화 경로 (원 설계 Q5 복구)**
```
관리자 수정(is_active=false) → 서버 갱신 → sync 호출
  → deactivate_by_mcp_server() → 해당 서버 도구 is_active=0
  → 도구 선택창(list_active)에서 사라짐
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `RegisterMCPServerUseCase` | `SyncMcpToolsUseCase` (optional) | 등록 후 도구 카탈로그 반영 |
| `UpdateMCPServerUseCase` | `SyncMcpToolsUseCase` (optional) | 수정 후 도구 카탈로그 반영 |
| 두 UseCase | `SyncOutcome` (application VO) | sync 결과 표현 |
| `SyncMcpToolsUseCase` | `ToolCatalogRepository`, `MCPServerRepository`, `MCPToolLoader` | 기존 — **변경 없음** |
| `create_mcp_registry_factories()` | `create_tool_catalog_factories()`의 조립 로직 | 동일 세션으로 sync UseCase 조립 |
| `useSyncMcpTools` (프론트) | `toolCatalogService.syncMcpTools` | 수동 재동기화 |

---

## 3. Data Model

### 3.1 Entity Definition

DB 스키마 변경 없음. 신규 값 객체 1개만 추가한다.

```python
# src/application/tool_catalog/sync_outcome.py  (NEW)
"""SyncOutcome: MCP 도구 동기화 시도 결과.

부수효과 sync의 성패를 호출자(=등록/수정 UseCase)와 응답 스키마에
전달하기 위한 application 레이어 값 객체. 도메인 규칙을 담지 않는다.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class SyncOutcome:
    attempted: bool          # sync를 시도했는가 (미주입/미수행 시 False)
    ok: bool                 # 시도했고 성공했는가
    synced_count: int        # 동기화된 도구 수
    error_hint: str | None   # 실패 시 관리자용 진단 힌트 (원본 예외 아님)

    @classmethod
    def skipped(cls) -> "SyncOutcome":
        """sync 의존성 미주입 — 기존 동작 유지 경로 (FR-06)."""
        return cls(attempted=False, ok=False, synced_count=0, error_hint=None)

    @classmethod
    def succeeded(cls, count: int) -> "SyncOutcome":
        return cls(attempted=True, ok=True, synced_count=count, error_hint=None)

    @classmethod
    def failed(cls, hint: str) -> "SyncOutcome":
        return cls(attempted=True, ok=False, synced_count=0, error_hint=hint)
```

### 3.2 Entity Relationships

```
mcp_server_registry (1) ──── (N) tool_catalog
                              FK mcp_server_id, ON DELETE CASCADE (V006)
                              → 삭제 시 자동 정리, sync 불필요
```

### 3.3 Database Schema

**변경 없음.** 마이그레이션 파일을 추가하지 않는다.

- `tool_catalog` — V006 생성 + V054 `is_builtin` 추가. 그대로 사용
- `mcp_server_registry` — 그대로 사용

---

## 4. API Specification

### 4.1 Endpoint List

| Method | Path | Description | Auth | 변경 |
|--------|------|-------------|------|------|
| POST | `/api/v1/mcp-registry` | MCP 서버 등록 | User | **응답에 `tool_sync` 추가** |
| PUT | `/api/v1/mcp-registry/{id}` | MCP 서버 수정 | User | **응답에 `tool_sync` 추가** |
| GET | `/api/v1/mcp-registry` | 목록 조회 | User | `tool_sync` 항상 `null` |
| GET | `/api/v1/mcp-registry/{id}` | 단건 조회 | User | `tool_sync` 항상 `null` |
| DELETE | `/api/v1/mcp-registry/{id}` | 삭제 | User | 변경 없음 (FK CASCADE) |
| POST | `/api/v1/mcp-registry/{id}/test` | 연결 테스트 | User | 변경 없음 |
| POST | `/api/v1/tool-catalog/sync` | 도구 동기화 | **Admin** | **변경 없음 — 프론트가 처음 사용** |
| GET | `/api/v1/tool-catalog` | 도구 카탈로그 | User | 변경 없음 |

### 4.2 Detailed Specification

#### `POST /api/v1/mcp-registry` — 등록 (sync 성공)

**Response (201 Created):**
```json
{
  "id": "a1b2c3d4-...",
  "user_id": "42",
  "name": "weather-server",
  "description": "날씨 조회",
  "endpoint": "https://server.smithery.ai/weather/mcp",
  "transport": "streamable_http",
  "input_schema": null,
  "is_active": true,
  "tool_id": "mcp_a1b2c3d4-...",
  "created_at": "2026-08-31T09:00:00Z",
  "updated_at": "2026-08-31T09:00:00Z",
  "auth_config": { "api_key": "****" },
  "server_config": null,
  "tool_sync": { "ok": true, "synced_count": 3, "error_hint": null }
}
```

#### `POST /api/v1/mcp-registry` — 등록 (sync 실패, **등록은 성공**)

**Response (201 Created):**
```json
{
  "id": "a1b2c3d4-...",
  "...": "...",
  "tool_sync": {
    "ok": false,
    "synced_count": 0,
    "error_hint": "MCP 서버에 연결하지 못했습니다. api_key 누락으로 인한 404(‘Session terminated’) 가능성을 확인하세요."
  }
}
```

#### `GET /api/v1/mcp-registry` — 조회 (sync 미수행)

```json
{ "items": [ { "id": "a1b2c3d4-...", "...": "...", "tool_sync": null } ], "total": 1 }
```

> `tool_sync: null`은 **"이번 응답은 sync를 수행하지 않았다"**를 의미한다. `{"ok": false}`(시도했으나 실패)와 명확히 구분된다 — 이것이 평면 필드 대신 중첩 객체를 선택한 이유다.

#### `POST /api/v1/tool-catalog/sync` — 수동 재동기화 (기존 API)

**Request:**
```json
{ "mcp_server_id": "a1b2c3d4-..." }
```

**Response (200 OK):**
```json
{ "synced_count": 3 }
```

**Error Responses:**
- `401 Unauthorized` — 미인증
- `403 Forbidden` — admin 아님 (`require_role("admin")`)
- `500` — MCP 서버 연결 실패 시 예외가 그대로 전파됨 ⚠️ **§6.3 참조**

### 4.3 스키마 정의

```python
# src/application/mcp_registry/schemas.py

class ToolSyncResultResponse(BaseModel):
    """MCP 도구 동기화 결과. 등록/수정 응답에만 실리고 조회 응답에서는 null."""

    ok: bool
    synced_count: int
    error_hint: str | None = None


class MCPServerResponse(BaseModel):
    # ... 기존 12개 필드 그대로 ...
    # mcp-tool-auto-sync FR-09: sync 미수행(GET) 시 None
    tool_sync: ToolSyncResultResponse | None = None


def to_response(entity, tool_sync: SyncOutcome | None = None) -> MCPServerResponse:
    """기존 호출부(인자 1개)를 그대로 지원하기 위해 tool_sync는 기본 None."""
    return MCPServerResponse(
        # ... 기존 필드 ...
        tool_sync=(
            ToolSyncResultResponse(
                ok=tool_sync.ok,
                synced_count=tool_sync.synced_count,
                error_hint=tool_sync.error_hint,
            )
            if tool_sync is not None and tool_sync.attempted
            else None
        ),
    )
```

> `attempted=False`(의존성 미주입)일 때도 `null`을 반환한다 — FR-06의 "기존과 동일하게 동작"을 응답 수준에서도 지킨다.

---

## 5. UI/UX Design

### 5.1 Screen Layout — `AdminMcpServersPage`

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Admin                                                    [+ 서버 등록]     │
│ MCP 서버 관리                                                             │
├──────────┬──────────────┬───────────┬────────┬───────────────────────────┤
│ 이름      │ 엔드포인트     │ Transport │ 상태    │ 액션                      │
├──────────┼──────────────┼───────────┼────────┼───────────────────────────┤
│ weather  │ https://...  │ Str.HTTP  │ 활성    │ [동기화][테스트][수정][삭제] │
│ 날씨 조회  │              │           │        │                           │
│ ⚠ 도구 동기화 실패 — api_key 누락으로 인한 404 가능성을 확인하세요.  ← 실패 시만  │
├──────────┴──────────────┴───────────┴────────┴───────────────────────────┤
│ github   │ https://...  │ SSE       │ 활성    │ [동기화][테스트][수정][삭제] │
└──────────────────────────────────────────────────────────────────────────┘
```

액션 컬럼 폭을 `w-[180px]` → `w-[240px]`로 넓히고 **[동기화]를 맨 앞**에 둔다.

### 5.2 User Flow

```
[정상]  서버 등록 → 모달 닫힘 → 목록 갱신 → (배너 없음) → 에이전트 생성 시 도구 노출

[실패]  서버 등록 → 모달 닫힘 → 목록에 ⚠ 실패 배너
        → 관리자가 MCP 서버 상태 확인/수정
        → [동기화] 클릭 → 스피너 → 성공 시 배너 사라짐 + 카탈로그 캐시 무효화

[재동기화] MCP 서버 쪽에 도구가 추가됨 → 관리자가 [동기화] 클릭 → 반영
```

### 5.3 Component List

| Component | Location | Responsibility |
|-----------|----------|----------------|
| `AdminMcpServersPage` | `src/pages/AdminMcpServersPage/index.tsx` | 동기화 버튼·실패 배너 상태 관리 |
| `useSyncMcpTools` | `src/hooks/useToolCatalog.ts` | sync mutation + `toolCatalog` 캐시 무효화 |
| `toolCatalogService.syncMcpTools` | `src/services/toolCatalogService.ts` | `POST /tool-catalog/sync` 호출 |
| `ToolSyncResult` / `McpServer.tool_sync` | `src/types/toolCatalog.ts`, `src/types/mcpServer.ts` | 응답 타입 |

### 5.4 Page UI Checklist

#### AdminMcpServersPage

- [ ] Button: 서버 행 액션에 "동기화" 버튼 (**항상 노출**, 실패 여부 무관 — FR-12)
- [ ] Button: 동기화 진행 중 **해당 행만** 비활성 + 라벨 "동기화 중..." (다른 행은 정상 — 기존 `테스트` 버튼이 전역 `isPending`으로 모든 행을 잠그는 패턴을 답습하지 않는다)
- [ ] Banner: sync 실패 시 행 하단 경고 배너 — 배경 `bg-amber-50`, 텍스트 `text-amber-700`
- [ ] Banner Text: "도구 동기화 실패" + `error_hint` 원문
- [ ] Banner: 동기화 성공 시 즉시 사라짐
- [ ] Banner: 등록/수정 응답의 `tool_sync.ok === false`일 때만 표시 (`tool_sync === null`이면 미표시)
- [ ] Toast/State: 동기화 성공 시 "도구 N개를 동기화했습니다" 안내
- [ ] Error: 동기화 실패(403 포함) 시 실패 사유 표시
- [ ] 기존 요소 유지: 테스트/수정/삭제 버튼, 활성·비활성 배지, Transport 배지

> **상태 보관 방식**: 등록/수정 응답의 `tool_sync`는 서버 목록 재조회(`GET`)를 하면 `null`로 덮인다. 따라서 실패 정보는 **페이지 로컬 state**(`Record<serverId, ToolSyncResult>`)에 담고, 해당 서버를 재동기화하거나 성공 응답을 받으면 제거한다.

---

## 6. Error Handling

### 6.1 예외 분류 정책 (본 설계의 핵심)

| 예외 | 세션 영향 | 처리 | 등록 결과 |
|------|----------|------|----------|
| `SQLAlchemyError` (및 하위) | 오염 | **재전파** | 500 — 정직한 실패 |
| `asyncio.TimeoutError` | 없음 | 삼킴 + warning | 201 + `ok:false` |
| MCP 프로토콜/HTTP 예외 | 없음 | 삼킴 + warning | 201 + `ok:false` |
| 그 외 `Exception` | 없음 | 삼킴 + warning | 201 + `ok:false` |
| `asyncio.CancelledError` | — | **재전파** | 요청 취소 전파 (BaseException이라 `except Exception`에 안 걸리지만 명시) |

```python
# src/application/mcp_registry/register_mcp_server_use_case.py

async def _run_tool_sync(self, server_id: str, request_id: str) -> SyncOutcome:
    """등록/수정 후 도구 카탈로그 동기화 (best-effort).

    Design Ref: §2.0 — SQLAlchemyError는 세션을 오염시켜 삼켜도 커밋이
    실패하므로 재전파한다. 네트워크/MCP 계열 실패만 흡수해 FR-03을 지킨다.
    """
    if self._sync_use_case is None:
        return SyncOutcome.skipped()          # FR-06

    try:
        count = await asyncio.wait_for(
            self._sync_use_case.execute(server_id, request_id),
            timeout=self._sync_timeout_sec,   # FR-03 / R-03
        )
        return SyncOutcome.succeeded(count)
    except SQLAlchemyError:
        raise                                  # §6.1 — 세션 오염, 삼키면 안 됨
    except Exception as e:
        self._logger.warning(
            "MCP tool sync failed after registration",
            request_id=request_id,
            server_id=server_id,
            error_type=type(e).__name__,
            error=str(e),
        )
        return SyncOutcome.failed(_hint_for(e))
```

> **LOG-001 정합**: `logger.warning`은 스택 트레이스를 남기지 않지만, 여기서는 예외를 **처리 완료**했고 `error_type`·`error`를 구조화 필드로 남기므로 "스택 트레이스 없는 에러 처리" 금지 조항에 저촉되지 않는다. 재전파하는 `SQLAlchemyError`는 상위에서 정상적으로 스택과 함께 기록된다.

### 6.2 진단 힌트 매핑 (`_hint_for`)

원본 예외 메시지를 클라이언트에 그대로 노출하지 않는다 (내부 URL·헤더 유출 방지).

```python
# TOOL-MCP-001 §3: 'Session terminated'는 대부분 세션 만료가 아니라 HTTP 404이며,
# 주 원인은 빈 api_key가 URL에서 누락된 경우다.
_HINT_RULES: tuple[tuple[str, str], ...] = (
    ("session terminated",
     "MCP 서버가 요청을 거부했습니다. api_key 누락으로 인한 404 가능성이 높습니다 — "
     "인증 설정을 확인한 뒤 [동기화]를 다시 실행하세요."),
    ("timeout",
     "MCP 서버 응답이 지연되어 동기화를 중단했습니다. 서버 상태를 확인한 뒤 "
     "[동기화]를 다시 실행하세요."),
    ("404",
     "MCP 서버 엔드포인트를 찾을 수 없습니다(404). endpoint와 인증 설정을 확인하세요."),
    ("401", "MCP 서버 인증에 실패했습니다(401). api_key를 확인하세요."),
    ("403", "MCP 서버가 접근을 거부했습니다(403). 권한 설정을 확인하세요."),
)

_DEFAULT_HINT = (
    "MCP 서버에서 도구 목록을 가져오지 못했습니다. "
    "[테스트]로 연결을 확인한 뒤 [동기화]를 다시 실행하세요."
)


def _hint_for(exc: Exception) -> str:
    msg = str(exc).lower()
    for needle, hint in _HINT_RULES:
        if needle in msg:
            return hint
    return _DEFAULT_HINT
```

### 6.3 기존 `/tool-catalog/sync` 오류 응답 ⚠️

`sync_mcp_tools` 라우터는 예외를 잡지 않으므로 MCP 서버 연결 실패 시 **500**이 나간다. 프론트가 이 API를 처음 실사용하게 되므로 프론트에서 500을 사용자 문구로 변환한다.

**이번 범위에서 라우터는 수정하지 않는다** — FR-07("시그니처·동작 변경 없이 유지")을 지키기 위함. 프론트 처리:

| 상태 | 화면 문구 |
|------|----------|
| 200 | "도구 N개를 동기화했습니다" |
| 403 | "관리자 권한이 필요합니다" |
| 500 / 그 외 | "MCP 서버에서 도구 목록을 가져오지 못했습니다. [테스트]로 연결을 확인하세요." |

> **후속 과제**: `/tool-catalog/sync`가 500 대신 `{ok:false, error_hint}`를 반환하도록 정규화하면 등록 경로와 오류 표현이 통일된다. Plan Out of Scope로 남긴다.

### 6.4 에러 코드 정의

| Code | 발생 지점 | 원인 | 처리 |
|------|----------|------|------|
| 201 + `tool_sync.ok=false` | 등록 | MCP 서버 무응답 | 등록 성공 + 화면 배너 + 동기화 버튼 |
| 422 | 등록/수정 | 정책 검증 실패 (기존) | 폼 에러 표시 |
| 404 | 수정 | 서버 미존재 (기존) | 목록 갱신 |
| 500 | 등록/수정 | `SQLAlchemyError` — DB 장애 | 요청 전체 롤백. 등록도 안 됨 (정상 동작) |
| 403 | 동기화 버튼 | admin 아님 | "관리자 권한이 필요합니다" |

---

## 7. Security Considerations

- [x] **예외 메시지 비노출** — `error_hint`는 사전 정의 문구로만 매핑(§6.2). 원본 예외·내부 URL·헤더가 클라이언트로 나가지 않는다
- [x] **`auth_config` 마스킹 유지** — `to_response()`가 기존대로 `masked_auth()`를 사용. `tool_sync` 추가가 마스킹 경로를 우회하지 않음
- [x] **admin 권한 유지** — `/tool-catalog/sync`의 `require_role("admin")` 변경 없음. 동기화 버튼은 admin이 아닌 사용자에게 403을 받는다
- [x] **입력 검증** — sync는 서버 자신의 `id`만 인자로 받으므로 사용자 입력이 개입하지 않음
- [ ] **로그 시크릿 노출 점검** — warning 로그의 `error=str(e)`에 URL 쿼리스트링(`?api_key=...`)이 섞여 들어갈 수 있다. **Do 단계에서 마스킹 여부 확인 필수**
- [x] **Rate Limiting** — 동기화 버튼은 행 단위 `isPending`으로 중복 클릭 차단(R-08)

---

## 8. Test Plan

### 8.1 Test Scope

| Type | Target | Tool | Phase |
|------|--------|------|-------|
| L0: Unit | UseCase sync 분기, `SyncOutcome`, `_hint_for` | pytest | Do |
| L1: API | 등록/수정 응답의 `tool_sync`, 실패 시 201 | pytest + TestClient | Do |
| L2: UI Action | 동기화 버튼, 실패 배너 | Vitest + RTL + MSW | Do |
| L3: E2E | 등록 실패 → 배너 → 동기화 → 도구 노출 | 수동 검증 (Playwright 미도입) | Check |

### 8.2 L0/L1: 백엔드 테스트 시나리오

| # | 대상 | 시나리오 | 기대 결과 |
|---|------|---------|----------|
| 1 | `RegisterMCPServerUseCase` | sync 미주입 | 기존과 동일 동작, `to_response`의 `tool_sync`가 `None` (FR-06) |
| 2 | `RegisterMCPServerUseCase` | sync 성공 (mock이 3 반환) | `SyncOutcome.succeeded(3)`, 응답 `tool_sync.ok=true, synced_count=3` |
| 3 | `RegisterMCPServerUseCase` | sync가 `ConnectionError` 발생 | 예외 전파 없음, `ok=false`, warning 로그 1건, **서버는 저장됨** |
| 4 | `RegisterMCPServerUseCase` | sync가 `SQLAlchemyError` 발생 | **예외 재전파** (§2.0 계약) |
| 5 | `RegisterMCPServerUseCase` | sync가 타임아웃 초과 | `ok=false`, `error_hint`에 지연 안내 |
| 6 | `UpdateMCPServerUseCase` | 1~5 동일 시나리오 | 동일 |
| 7 | `UpdateMCPServerUseCase` | `is_active=false`로 수정 | sync 호출됨 → `deactivate_by_mcp_server` 경로 (FR-08) |
| 8 | `SyncOutcome` | `skipped`/`succeeded`/`failed` 팩토리 | `attempted`·`ok` 조합이 의도대로 |
| 9 | `_hint_for` | `'Session terminated'` 포함 예외 | api_key/404 힌트 반환 (TOOL-MCP-001 §3) |
| 10 | `_hint_for` | 매칭 규칙 없는 예외 | 기본 힌트 반환, 원본 메시지 미포함 |
| 11 | `to_response` | `tool_sync=None` (기존 호출부) | `tool_sync` 필드가 `None` — 하위 호환 |
| 12 | `POST /api/v1/mcp-registry` | sync 실패 mock | **HTTP 201** + `tool_sync.ok=false` |
| 13 | `GET /api/v1/mcp-registry` | 목록 조회 | 모든 항목 `tool_sync=null` |
| 14 | 회귀 | `tests/application/mcp_registry/` 6개 파일 | 무수정 전량 통과 |
| 15 | 회귀 | 반복 sync 후 `is_builtin` | 관리자 토글값 보존 (R-04, builtin-tools D2) |

### 8.3 L2: 프론트 테스트 시나리오

| # | 대상 | 액션 | 기대 결과 |
|---|------|------|----------|
| 1 | `AdminMcpServersPage` | 목록 렌더 | 모든 서버 행에 "동기화" 버튼 존재 (FR-12) |
| 2 | `AdminMcpServersPage` | 동기화 클릭 | `POST /tool-catalog/sync`가 `{mcp_server_id}`로 호출됨 |
| 3 | `AdminMcpServersPage` | 동기화 성공 | 성공 안내 + `toolCatalog` 쿼리 무효화 |
| 4 | `AdminMcpServersPage` | 동기화 진행 중 | **해당 행 버튼만** 비활성, 다른 행은 활성 |
| 5 | `AdminMcpServersPage` | 등록 응답 `tool_sync.ok=false` | 해당 행에 경고 배너 + `error_hint` 표시 |
| 6 | `AdminMcpServersPage` | 위 상태에서 동기화 성공 | 배너 사라짐 |
| 7 | `AdminMcpServersPage` | 등록 응답 `tool_sync.ok=true` | 배너 미표시 |
| 8 | `AdminMcpServersPage` | 동기화 403 | "관리자 권한이 필요합니다" |
| 9 | `useSyncMcpTools` | mutate 성공 | `queryKeys.toolCatalog.all` 무효화 호출 |
| 10 | 회귀 | 기존 테스트/수정/삭제 버튼 | 동작 불변 |

### 8.4 L3: E2E 시나리오 (수동)

| # | 시나리오 | 단계 | 성공 기준 |
|---|---------|------|----------|
| 1 | 정상 등록 | 실서버 등록 → 에이전트 생성 화면 | 도구 선택창에 MCP 배지와 함께 노출 |
| 2 | **막다른 길 없음** | 도달 불가 endpoint 등록 → 배너 확인 → endpoint 수정 → [동기화] | 201 성공 → 배너 표시 → 동기화 후 도구 노출 |
| 3 | 재동기화 | 정상 등록 후 [동기화] 재클릭 | 도구 수 동일, `is_builtin` 보존 |
| 4 | 비활성화 | 서버 `is_active=false` 수정 | 도구 선택창에서 사라짐 |

### 8.5 Seed Data Requirements

| Entity | Minimum Count | Key Fields Required |
|--------|:------------:|---------------------|
| `mcp_server_registry` | 2 | 정상 서버 1 + 도달 불가 endpoint 1 |
| `tool_catalog` | 0 | sync가 채우는 것을 검증하므로 사전 데이터 불필요 |

> 단위/API 테스트는 `SyncMcpToolsUseCase`와 `MCPToolLoader`를 mock으로 대체한다 — 실제 MCP 서버 없이 전 경로 검증 가능.

---

## 9. Clean Architecture

### 9.1 Layer Structure

| Layer | Responsibility | 본 기능 변경 |
|-------|---------------|-------------|
| **interfaces** | FastAPI router, schema | **없음** — 라우터에 로직 추가 금지 |
| **application** | UseCase, 흐름 제어 | Register/Update UseCase, `SyncOutcome`, 응답 스키마 |
| **domain** | Entity, VO, Policy | **없음** — 새 도메인 규칙 없음 |
| **infrastructure** | MySQL, MCP loader | **없음** |

### 9.2 Dependency Rules

```
interfaces ──→ application ──→ domain ←── infrastructure
                    │                          ▲
                    └──────────────────────────┘

본 기능: application 내부에서 application을 호출 (UseCase → UseCase)
         → 레이어 역참조 없음, domain 무변경
```

### 9.3 File Import Rules

| From | Can Import | 본 기능 |
|------|-----------|---------|
| `application/mcp_registry/*` | `application/tool_catalog/*`, `domain/*` | ✅ `SyncMcpToolsUseCase`, `SyncOutcome` import |
| `application/*` | `infrastructure/*` 직접 import | ❌ 하지 않음 — DI로만 주입 |
| `domain/*` | 없음 | ✅ 변경 없음 |

> **`SyncOutcome`을 domain이 아닌 application에 두는 이유**: 비즈니스 규칙이 아니라 "부수효과 시도 결과"라는 흐름 제어 정보다. domain에 두면 domain이 인프라 사정(네트워크 실패)을 알게 된다.

### 9.4 This Feature's Layer Assignment

| Component | Layer | Location |
|-----------|-------|----------|
| `SyncOutcome` | Application | `src/application/tool_catalog/sync_outcome.py` (NEW) |
| `_hint_for` / `_HINT_RULES` | Application | `src/application/tool_catalog/sync_outcome.py` |
| `RegisterMCPServerUseCase._run_tool_sync` | Application | `src/application/mcp_registry/register_mcp_server_use_case.py` |
| `UpdateMCPServerUseCase._run_tool_sync` | Application | `src/application/mcp_registry/update_mcp_server_use_case.py` |
| `ToolSyncResultResponse` | Application | `src/application/mcp_registry/schemas.py` |
| DI 배선 | Composition Root | `src/api/main.py` |
| `mcp_tool_sync_timeout_sec` | Config | `src/config.py` |
| `useSyncMcpTools` | Presentation(Application) | `idt_front/src/hooks/useToolCatalog.ts` |
| `syncMcpTools` | Infrastructure | `idt_front/src/services/toolCatalogService.ts` |
| `ToolSyncResult` | Domain(Type) | `idt_front/src/types/toolCatalog.ts` |

---

## 10. Coding Convention Reference

### 10.1 Naming Conventions

| Target | Rule | 본 기능 예시 |
|--------|------|-------------|
| Python 클래스 | PascalCase | `SyncOutcome`, `ToolSyncResultResponse` |
| Python 함수 | snake_case | `_run_tool_sync()`, `_hint_for()` |
| Python 모듈 상수 | UPPER_SNAKE | `_HINT_RULES`, `_DEFAULT_HINT` |
| TS 훅 | `use` + PascalCase | `useSyncMcpTools` |
| TS 타입 | PascalCase | `ToolSyncResult` |
| 엔드포인트 상수 | UPPER_SNAKE | `TOOL_CATALOG_SYNC` |

### 10.2 Import Order (프론트)

```typescript
import { useMutation, useQueryClient } from '@tanstack/react-query';  // 외부
import { toolCatalogService } from '@/services/toolCatalogService';   // 내부 절대
import { queryKeys } from '@/lib/queryKeys';
import type { CatalogTool, ToolSyncResult } from '@/types/toolCatalog'; // 타입
```

### 10.3 Environment Variables

| Variable | Purpose | Scope | 신규 |
|----------|---------|-------|:---:|
| `MCP_TOOL_SYNC_TIMEOUT_SEC` | 등록/수정 시 sync 타임아웃(초) | Server | ☑ |
| `MCP_SECRET_KEY` | `auth_config` 암복호화 | Server | ☐ (기존) |

```python
# src/config.py — MCP Registry 섹션 (기존 line 185 부근)
    # mcp-tool-auto-sync R-03: 등록/수정 시 도구 sync 대기 상한.
    # 초과 시 sync만 중단하고 등록/수정은 성공시킨다 (FR-03).
    # 선례: tool_selector_timeout_sec
    mcp_tool_sync_timeout_sec: float = 10.0
```

> **config 하드코딩 금지**(CLAUDE.md §3)에 따라 타임아웃을 상수로 박지 않는다.

### 10.4 This Feature's Conventions

| Item | Convention Applied |
|------|-------------------|
| 부수효과 실패 처리 | `try/except → logger.warning` — `seed_internal_tools_on_startup()` 기존 패턴 |
| 하위 호환 | 생성자 인자·응답 필드 모두 optional 기본값 |
| 프론트 상수 위치 | 엔드포인트는 `constants/api.ts`, 타입은 `types/*.ts` — 컴포넌트 파일에서 런타임 상수 export 금지 |
| 코드 주석 | `# Design Ref: §{절} — {결정 근거}` 형태로 추적 링크 |
| 함수 길이 | 40줄 이하 — `_run_tool_sync`는 ~20줄 |

---

## 11. Implementation Guide

### 11.1 File Structure

```
idt/
├── src/
│   ├── config.py                                            ◀ 타임아웃 설정
│   ├── application/
│   │   ├── tool_catalog/
│   │   │   └── sync_outcome.py                              ★ NEW
│   │   └── mcp_registry/
│   │       ├── schemas.py                                   ◀ ToolSyncResultResponse
│   │       ├── register_mcp_server_use_case.py              ◀ _run_tool_sync
│   │       └── update_mcp_server_use_case.py                ◀ _run_tool_sync
│   └── api/main.py                                          ◀ DI 배선
└── tests/
    ├── application/tool_catalog/test_sync_outcome.py        ★ NEW
    ├── application/mcp_registry/test_register_tool_sync.py  ★ NEW
    ├── application/mcp_registry/test_update_tool_sync.py    ★ NEW
    └── api/test_mcp_registry_router.py                      ◀ tool_sync 단언

idt_front/
├── src/
│   ├── constants/api.ts                                     ◀ TOOL_CATALOG_SYNC
│   ├── types/toolCatalog.ts                                 ◀ ToolSyncResult
│   ├── types/mcpServer.ts                                   ◀ McpServer.tool_sync
│   ├── services/toolCatalogService.ts                       ◀ syncMcpTools
│   ├── hooks/useToolCatalog.ts                              ◀ useSyncMcpTools
│   └── pages/AdminMcpServersPage/
│       ├── index.tsx                                        ◀ 버튼 + 배너
│       └── index.test.tsx                                   ◀ 신규 케이스
```

★ = 신규 (5) / ◀ = 수정 (12)

### 11.2 Implementation Order

**TDD 원칙**: 각 단계에서 테스트를 먼저 작성하고 실패를 확인한 뒤 구현한다.

1. [ ] `SyncOutcome` + `_hint_for` 테스트 작성 → 실패 확인 → 구현
2. [ ] `config.py`에 `mcp_tool_sync_timeout_sec` 추가
3. [ ] `RegisterMCPServerUseCase` sync 5경로 테스트 작성 → 실패 확인 → `_run_tool_sync` 구현
4. [ ] `UpdateMCPServerUseCase` 동일 (공통 로직 중복 시 `sync_outcome.py`로 헬퍼 승격 검토)
5. [ ] `schemas.py` — `ToolSyncResultResponse` + `to_response(tool_sync=None)` 확장, 하위 호환 테스트
6. [ ] `main.py` DI 배선 — 같은 세션으로 `SyncMcpToolsUseCase` 조립해 주입
7. [ ] 라우터 통합 테스트 — sync 실패 시 201 확인
8. [ ] 백엔드 회귀 실행 + `/verify-architecture` `/verify-logging` `/verify-tdd`
9. [ ] 프론트 타입·상수·서비스·훅 추가 (테스트 먼저)
10. [ ] `AdminMcpServersPage` 동기화 버튼 + 실패 배너 (테스트 먼저)
11. [ ] `/api-contract-sync`로 백엔드↔프론트 타입 대조
12. [ ] L3 수동 E2E — 특히 시나리오 2(막다른 길 없음)

### 11.3 Session Guide

#### Module Map

| Module | Scope Key | Description | Estimated Turns |
|--------|-----------|-------------|:---------------:|
| Sync 결과 값 객체 | `module-1` | `SyncOutcome` + `_hint_for` + config 타임아웃 (1~2단계) | 8-12 |
| UseCase sync 통합 | `module-2` | Register/Update `_run_tool_sync` + 예외 분류 (3~4단계) | 15-20 |
| 응답 스키마 + DI | `module-3` | `ToolSyncResultResponse`, `to_response`, `main.py` 배선, 라우터 테스트 (5~8단계) | 15-20 |
| 프론트 배선 | `module-4` | 상수·타입·서비스·훅 (9단계) | 10-15 |
| 관리 화면 UI | `module-5` | 동기화 버튼 + 실패 배너 + 테스트 (10~12단계) | 20-25 |

#### Recommended Session Plan

| Session | Phase | Scope | Turns |
|---------|-------|-------|:-----:|
| Session 1 | Plan + Design | 전체 | 완료 |
| Session 2 | Do | `--scope module-1,module-2` | 25-30 |
| Session 3 | Do | `--scope module-3` | 15-20 |
| Session 4 | Do | `--scope module-4,module-5` | 30-40 |
| Session 5 | Check + Report | 전체 | 25-35 |

### 11.4 DI 배선 상세 (module-3 핵심)

```python
# src/api/main.py — create_mcp_registry_factories()
# Design Ref: §2.0 — DB-001 준수. sync UseCase가 등록 UseCase와
# 동일한 session 인스턴스를 공유한다 (요청 1건 = 세션 1개).

def _make_sync_uc(session: AsyncSession):
    return SyncMcpToolsUseCase(
        tool_catalog_repo=ToolCatalogRepository(session=session, logger=app_logger),
        mcp_server_repo=_make_repo(session),      # 등록 UseCase와 같은 repo 조립 경로
        mcp_tool_loader=MCPToolLoader(logger=app_logger),
        logger=app_logger,
    )

def register_factory(session: AsyncSession = Depends(get_session)):
    return RegisterMCPServerUseCase(
        repository=_make_repo(session),
        logger=app_logger,
        secrets_enabled=secrets_enabled,
        sync_use_case=_make_sync_uc(session),           # ← 신규
        sync_timeout_sec=settings.mcp_tool_sync_timeout_sec,
    )
```

> ⚠️ `Depends(get_session)`이 주입한 **동일 세션 객체**를 두 repo가 공유하는지 Do 단계에서 반드시 확인한다. `_make_repo(session)`을 두 번 호출해 `MCPServerRepository` 인스턴스가 2개 생기는 것은 무방하다 — **금지되는 것은 세션이 2개인 경우**다.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-08-31 | 초안 작성. Option C(Pragmatic) 선택 — 예외 분류로 R-01 해소, 중첩 `tool_sync` 응답 채택 | 배상규 |
