# approval-gate-phase2-mcp-executor Design Document

> **Summary**: 승인된 MCP 도구를 `MCPCallClient`로 **검증(list_tools) → 1회 호출(call_tool, 재시도 0)** 하는 `McpActionExecutor`, 지원 집행기가 없으면 `failed`로 떨어뜨리는 `CompositeActionExecutor`, 그리고 MCP 서버 등록 플래그(`default_requires_approval`)로 신규 카탈로그 엔트리의 게이트 초기값을 정하는 설계.
>
> **Project**: sangplusbot (idt + idt_front)
> **Version**: —
> **Author**: 배상규
> **Date**: 2026-09-21
> **Status**: Draft (v0.1)
> **Planning Doc**: [approval-gate-phase2-mcp-executor.plan.md](../../01-plan/features/approval-gate-phase2-mcp-executor.plan.md)

### Pipeline References

| Phase | Document | Status |
|-------|----------|--------|
| Phase 1~4 | — | N/A (PDCA 단독) |

선행 문서: [approval-gate.design.md](./approval-gate.design.md) (§2.3 집행기, §3.3 requires_approval)

---

## Context Anchor

> Copied from Plan document. Ensures strategic context survives Design→Do handoff.

| Key | Value |
|-----|-------|
| **WHY** | 승인해도 MCP 도구가 실행되지 않고 `executed`로 기록되는 가짜 성공 + 신규 MCP 도구가 게이트 없이 시작하는 fail-open. |
| **WHO** | P2 에이전트 소유자(자기 MCP 서버 등록·자기 에이전트 승인) + 관리자(카탈로그 `requires_approval` 최종 통제) |
| **RISK** | 타임아웃·연결 끊김 시 **"발송됐는지 모르는" 상태에서의 이중 집행**. 그리고 Phase 1 미해결 Critical 갭(G1 재개 저장 실패, G5 tick 호출자 없음, G13 KST 9시간 오차) 위에 쌓는 위험. |
| **SUCCESS** | 승인된 MCP 도구가 **정확히 1회** 실제 호출되고, 집행기 없는 도구는 `executed`가 **0건**, 플래그를 켠 서버의 신규 도구는 sync 직후 `requires_approval=true`. |
| **SCOPE** | In: McpActionExecutor + 집행기 체인 + Mock 배선 제거 + 서버 등록 플래그(V075)·sync 초기값·등록 폼 필드. Out: 메일 MCP 서버 자체, OAuth, 메일 특화 정책, 내장 send_email, 승인 화면 발신 계정 표시, Phase 3 자동 승인. |

---

## 1. Overview

### 1.1 Design Goals

1. **"승인됨 = 실행됨"** — 승인된 MCP 도구가 실제 서버에 1회 도달한다.
2. **거짓 성공 0** — 집행기 없음·도구 에러·연결 실패 어느 경우에도 `executed`가 찍히지 않는다.
3. **실패를 사람이 판단할 수 있게** — "보내지지 않은 게 확실함" / "보내졌는지 모름" / "도구가 실패라고 답함"을 구분한다.
4. **등록 순간부터 통제** — 부작용 MCP 서버의 새 도구는 sync 직후 게이트 대상이다.
5. **Phase 1을 흔들지 않는다** — 미커밋·갭 열린 상태이므로 인터페이스 변경은 선택 kwarg 1개로 제한.

### 1.2 Design Principles

- **fail-closed**: 도구를 특정할 수 없거나 확신이 없으면 호출하지 않는다. 추측 호출 금지.
- **재시도 0**: 비가역 작업의 자동 재시도는 이중 집행이다 (Phase 1 FR-25 계승).
- **실패는 값이다**: 집행기는 예외를 던지지 않는다. `decide_use_case._execute_now`가 예외를 가두지 않기 때문이다.
- **코어는 메일을 모른다**: 집행기는 "MCP 도구"만 안다. 도구별 분기·인자 매핑 없음.
- **자격증명은 복제하지 않는다**: 서버 등록은 집행 시점에 조회하고 approval 행에 담지 않는다.
- **시크릿은 에러 문구에 들어가지 않는다**: streamable_http는 `api_key`가 URL 쿼리에 실린다 — 예외 문자열을 그대로 영속하면 유출된다.

---

## 2. Architecture Options

### 2.0 Architecture Comparison

| Criteria | Option A: Minimal | Option B: Clean | Option C: Pragmatic |
|----------|:-:|:-:|:-:|
| **Approach** | `MCPToolLoader` + `tool.ainvoke` | 도메인 포트 `McpToolInvoker` + `failure_kind` enum·DB 컬럼·API·UI 뱃지 | `MCPCallClient` 직접 (list_tools → call_tool) + 합성 집행기 + 문구 3분류 |
| **New Files** (테스트 제외) | 1 | 6 | 4 |
| **Modified Files** | 9 | 16 | 13 |
| **Complexity** | Low | High | Medium |
| **Maintainability** | Low | High | High |
| **Effort** | Low | High | Medium |
| **Risk** | **High** — 어댑터가 `isError`를 무시해 도구 실패가 `executed`로 기록 | Medium — 미커밋 Phase 1의 DB·API를 함께 수정 | Low |
| **Recommendation** | 결격 | Phase 1 안정화 후 후속 | **선택** |

**Selected**: **Option C** — **Rationale**: 코드 조사에서 호출 경로가 둘임을 확인했다.

| | `MCPToolAdapter._arun` (워커 런타임 경로) | `MCPCallClient.call_tool` (연결 테스트 경로) |
|---|---|---|
| 도구 에러(`isError`) | **무시** — 에러 텍스트를 정상 문자열로 반환 (`tool_adapter.py:124`) | `MCPToolResult.is_error` 값 (`call_client.py:105`) |
| placeholder 인자 | 예외 아닌 **지시 문자열 반환** | 없음 |
| 전체 타임아웃 | 없음 | `asyncio.wait_for(total)` |
| 재시도 | 없음 | `MCPRetryPolicy` 주입 — `max_retries=0`이면 0회 |

A는 메일 서버가 "발송 실패"를 돌려줘도 성공으로 기록한다 — Mock의 가짜 성공이 형태만 바꿔 남는다. B의 `failure_kind` 컬럼은 가치가 있지만 Phase 1이 check 83%·미커밋인 지금 그 테이블·API를 같이 고치는 것은 위험 대비 이득이 작다. C는 안전 요건을 모두 갖추고 Phase 1 접점을 kwarg 1개로 묶는다. 문구 접두를 도메인 정책 한 곳에서 만들기 때문에, 후속에 B의 컬럼으로 승격하기 쉽다.

### 2.1 Component Diagram

```
┌──────────────────────── application/approval (Phase 1, 거의 불변) ───────────────────────┐
│  DecideApprovalUseCase._execute_now ─┐                                                   │
│  ExecuteDueApprovalsUseCase._run_one ─┼─▶ executor.execute(tool_id, tool_args,           │
│                                       │          request_id, idempotency_key=…)  ◀─ 신규 kwarg
└───────────────────────────────────────┼──────────────────────────────────────────────────┘
                                        ▼
                    ┌─ infrastructure/approval ──────────────────────────┐
                    │  CompositeActionExecutor   [신규]                  │
                    │    supports 첫 매치에 위임 / 없으면 ok=False       │
                    │            │                                       │
                    │            ▼                                       │
                    │  McpActionExecutor         [신규]                  │
                    │    ① parse_mcp_tool_id ──────────▶ domain/tool_catalog
                    │    ② 서버 등록 조회 ─────────────▶ SessionScopedMcpServerRepository
                    │    ③ list_tools (검증)  ─┐                         │
                    │    ④ call_tool  (1회)   ─┴───────▶ infrastructure/mcp/MCPCallClient
                    │    문구·인자 규칙 ───────────────▶ domain/approval/execution_policy [신규]
                    └────────────────────────────────────────────────────┘

┌─ MCP 서버 등록 플래그 ─────────────────────────────────────────────────────────────────┐
│ AdminMcpServersPage ─▶ POST/PUT /api/v1/mcp-registry ─▶ Register/UpdateMCPServerUseCase │
│                                   │ default_requires_approval                            │
│                                   ▼                                                      │
│                        mcp_server_registry (V075 컬럼)                                   │
│                                   │                                                      │
│ SyncMcpToolsUseCase ──────────────┘ 신규 엔트리: requires_approval = server 플래그       │
│        └─▶ ToolCatalogRepository.upsert_by_tool_id  (INSERT만 영속 / UPDATE는 보존 — 기존 계약)
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Data Flow — 집행 1건

```
승인(또는 tick) ─▶ executor.execute(tool_id="mcp:{sid}:{tool}", tool_args={"arguments":{…}}, key)
  │
  ├─ ① tool_id 해석 실패 / tool_name 없음(레거시)        ─▶ [집행 불가]  호출 0회
  ├─ ② 서버 등록 없음 / is_active=False                  ─▶ [집행 불가]  호출 0회
  ├─ ③ list_tools 실패(연결·인증·타임아웃)               ─▶ [집행 불가]  호출 0회   ← 아무것도 안 보냈음이 확실
  │     도구명이 목록에 없음                             ─▶ [집행 불가]  호출 0회
  ├─ 인자 준비: 래퍼 해제 → (스키마에 있으면) idempotency_key 주입
  ├─ ④ call_tool 1회
  │     예외(타임아웃·연결 끊김·기타)                    ─▶ [집행 여부 불명]        ← 보냈을 수도 있음
  │     result.is_error                                  ─▶ [도구 실패] + 도구 메시지(절단)
  └─     정상                                            ─▶ ok=True, output=content(절단)
```

**③과 ④를 나눈 이유**: `list_tools`는 읽기 전용이라 실패해도 부작용이 없다. 여기서 연결·인증 문제를 걸러내면 "미발송 확실"과 "불명"의 경계가 호출 구조만으로 생긴다 — 예외 타입을 분류하는 취약한 휴리스틱이 필요 없다. 비용은 집행 1건당 세션 1회 추가(집행은 저빈도).

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `McpActionExecutor` (infra) | `ActionExecutorInterface`, `ExecutionResult` (domain/approval) | 포트 구현 |
| | `parse_mcp_tool_id` (domain/tool_catalog) | tool_id → server_id·tool_name |
| | `ExecutionFailurePolicy`, `McpArgumentPolicy` (domain/approval) | 문구·인자 규칙 |
| | `SessionScopedMcpServerRepository` (infra/mcp_registry) | 요청 컨텍스트 없는 등록 조회 |
| | `MCPCallClient`, `MCPToolLoader._build_config` (infra) | 호출 코어·config 조립 (`mcp_connection_test_use_case.py:80`과 동일 사용법) |
| `CompositeActionExecutor` (infra) | `ActionExecutorInterface` | 위임 |
| `ApprovalExecutionConfig` (infra/config) | pydantic-settings | 타임아웃·출력 상한 |
| `SyncMcpToolsUseCase` (app) | `MCPServerRegistration.default_requires_approval` | 초기값 |

domain → infrastructure 참조 없음. application/approval은 인터페이스 kwarg 전달 외 변경 없음.

---

## 3. Data Model

### 3.1 Entity Definition

**`MCPServerRegistration`** (`domain/mcp_registry/schemas.py`) — 필드 1개 추가

```python
# approval-gate-phase2 D-07: 이 서버의 도구가 카탈로그에 "처음" 들어올 때의
# requires_approval 초기값. 기존 엔트리에는 소급하지 않는다 (FR-16).
default_requires_approval: bool = False
```

`apply_update(...)`에도 `default_requires_approval: bool | None = None` 추가(None이면 미변경 — 기존 필드들과 동형).

**`ExecutionResult`** — 변경 없음.

**`ActionExecutorInterface.execute`** (`domain/approval/interfaces.py`) — 선택 kwarg 추가

```python
async def execute(
    self, *, tool_id: str, tool_args: dict, request_id: str,
    idempotency_key: str | None = None,   # D-05
) -> ExecutionResult: ...
```

**신규 도메인 정책** (`domain/approval/execution_policy.py`)

```python
ExecutionFailureKind = Literal["blocked", "unknown", "tool_error"]

class ExecutionFailurePolicy:
    """집행 실패 문구의 단일 생성 지점 (D-04)."""
    _PREFIX = {
        "blocked":    "[집행 불가]",       # 호출 0회 — 미집행 확실
        "unknown":    "[집행 여부 불명]",  # 호출함 — 결과를 모름
        "tool_error": "[도구 실패]",       # 도구가 실패라고 답함
    }
    _HINT = {
        "blocked":    "대상 시스템에는 아무것도 전달되지 않았습니다.",
        "unknown":    "대상 시스템에서 실제 집행 여부를 먼저 확인한 뒤 재승인하세요.",
        "tool_error": "",
    }
    @classmethod
    def render(cls, kind: ExecutionFailureKind, reason: str) -> str: ...

class McpArgumentPolicy:
    IDEMPOTENCY_PARAM = "idempotency_key"

    @staticmethod
    def unwrap(tool_args: dict) -> dict:
        """MCPToolInput 래퍼({"arguments": {...}}) 해제 (D-03)."""

    @classmethod
    def with_idempotency_key(cls, arguments: dict, input_schema: dict, key: str | None) -> dict:
        """스키마 properties 에 파라미터가 있고, 인자에 아직 없을 때만 주입 (D-05)."""

    @staticmethod
    def truncate(text: str, max_chars: int) -> str: ...
```

### 3.2 Entity Relationships

```
[mcp_server_registry] 1 ──── N [tool_catalog (source='mcp', mcp_server_id)]
        │ default_requires_approval ──(신규 INSERT 시 1회 복사)──▶ requires_approval
        │
        └─ (집행 시 server_id로 조회) ◀── [approval_request.tool_id = "mcp:{server_id}:{tool}"]
```

새 FK 없음 → errno 3780(콜레이션) 해당 없음.

### 3.3 Database Schema

`db/migration/V075__add_default_requires_approval_to_mcp_server_registry.sql`

```sql
-- approval-gate-phase2-mcp-executor Design §3.3 (D-07) — 서버 축 초기값.
-- 이 서버의 도구가 tool_catalog 에 "신규 INSERT" 될 때 requires_approval 의
-- 초기값으로 1회 복사된다. 이미 있는 엔트리에는 소급하지 않는다 —
-- 런타임 SoT 는 여전히 tool_catalog.requires_approval (V072, 관리자 토글).

ALTER TABLE mcp_server_registry
    ADD COLUMN default_requires_approval TINYINT(1) NOT NULL DEFAULT 0
    COMMENT '1이면 이 서버의 도구가 카탈로그에 처음 등록될 때 requires_approval=1 로 시작 (초기값 전용, 기존 엔트리 소급 없음). 기본 0 이라 기존 서버는 무영향';
```

`MCPServerModel`에 동일 컬럼 + `comment=` 동일 문구. `tests/db/test_migration_ddl_comments.py` 대상.

---

## 4. API Specification

### 4.1 Endpoint List (변경분만)

| Method | Path | Change | Auth |
|--------|------|--------|------|
| POST | `/api/v1/mcp-registry` | 요청·응답에 `default_requires_approval` | 기존 |
| PUT | `/api/v1/mcp-registry/{id}` | 요청(optional)·응답에 동일 필드 | 기존 |
| GET | `/api/v1/mcp-registry`, `/{id}` | 응답에 동일 필드 | 기존 |

승인 API(`/api/v1/approvals/*`)는 **계약 변경 없음** — 실패 사유는 기존 `error_message` 문자열에 접두 문구로 담긴다.

### 4.2 Detailed Specification

**`RegisterMCPServerRequest`** — `default_requires_approval: bool = False`
**`UpdateMCPServerRequest`** — `default_requires_approval: bool | None = None`
**`MCPServerResponse`** — `default_requires_approval: bool`

```json
// POST /api/v1/mcp-registry  (발췌)
{ "name": "my-mail", "endpoint": "https://…/mcp", "transport": "streamable_http",
  "auth_config": {"headers": {"Authorization": "Bearer …"}},
  "default_requires_approval": true }
```

하위 호환: 필드 생략 시 False. 기존 클라이언트·MSW 핸들러 무영향.

**PUT으로 플래그만 바꿨을 때**: 등록/수정 직후 auto-sync(mcp-tool-auto-sync FR-09)가 돌지만, 기존 엔트리는 UPDATE 분기라 값이 바뀌지 않는다(FR-16). 그 사이 서버에 **새로 생긴 도구**만 새 플래그 값을 받는다.

---

## 5. UI/UX Design

### 5.1 Screen Layout — `AdminMcpServersPage` 등록/수정 모달 (발췌)

```
│ 연결 방식   [ streamable_http ▾ ]                          │
│ ☑ 활성                                                     │
│ ☐ 이 서버의 도구는 기본으로 승인 필요                       │  ← 신규
│   발송·변경·삭제처럼 되돌릴 수 없는 도구가 있는 서버는 켜세요. │
│   새로 동기화되는 도구에만 적용됩니다 — 이미 등록된 도구는     │
│   도구 관리 화면에서 바꿉니다.                                │
```

### 5.2 User Flow

```
MCP 서버 등록(체크 ☑) → 자동 sync → 카탈로그 새 엔트리 requires_approval=1
  → 에이전트 빌더에서 그 도구를 단독 워커로 배치 → 실행 시 게이트 → 작업함 승인 → 실제 집행
```

### 5.3 Component List

| Component | Location | Responsibility |
|-----------|----------|----------------|
| `McpServer` / `RegisterMcpServerRequest` / `UpdateMcpServerRequest` | `idt_front/src/types/mcpServer.ts` | 필드 추가 |
| `mcpServerService` | `idt_front/src/services/mcpServerService.ts` | payload 전달(타입만 바뀌면 변경 최소) |
| 폼 상태(`form`)·`toForm`·submit payload | `idt_front/src/pages/AdminMcpServersPage/index.tsx` | 체크박스 + 기본 false + 수정 시 서버 값 로드 |
| MSW 핸들러 | `idt_front/src/__tests__/mocks/handlers.ts` (mcp-registry) | 응답에 필드 포함 |

프론트 규칙: 컴포넌트 파일에서 런타임 상수 export 금지 — 안내 문구는 컴포넌트 내부 리터럴로 둔다.

### 5.4 Page UI Checklist

#### AdminMcpServersPage — 등록/수정 모달

- [ ] Checkbox: "이 서버의 도구는 기본으로 승인 필요" (`default_requires_approval`, 신규 등록 시 기본 **꺼짐**)
- [ ] Help text: "발송·변경·삭제처럼 되돌릴 수 없는 도구가 있는 서버는 켜세요."
- [ ] Help text: "새로 동기화되는 도구에만 적용됩니다 — 이미 등록된 도구는 도구 관리 화면에서 바꿉니다."
- [ ] 수정 모드: 서버에서 받은 현재 값으로 체크 상태 초기화
- [ ] 등록 submit payload에 `default_requires_approval` 포함
- [ ] 수정 submit payload에 `default_requires_approval` 포함

#### AdminMcpServersPage — 서버 목록

- [ ] Badge: 플래그가 켜진 서버에 "승인 기본" 뱃지 (활성/비활성 뱃지 옆, 꺼진 서버는 미표시)

#### JobsPage 승인 탭 — 변경 없음

- [ ] (확인만) `failed` 건의 `error_message`가 접두 문구 포함 그대로 표시된다

---

## 6. Error Handling

### 6.1 집행 실패 분류 (D-04)

| Kind | 접두 | 발생 조건 | MCP 호출 | 사람이 할 일 |
|------|------|----------|:-------:|-------------|
| `blocked` | `[집행 불가]` | tool_id 해석 실패 · 레거시 id(tool_name 없음) · 등록 없음 · 비활성 · list_tools 실패 · 도구명 불일치 · **지원 집행기 없음** | 0회 | 원인 수정 후 재실행 |
| `unknown` | `[집행 여부 불명]` | call_tool 단계의 모든 예외(타임아웃·연결 끊김·기타) | 1회 시도 | **대상 시스템 확인 후** 재승인 |
| `tool_error` | `[도구 실패]` | `MCPToolResult.is_error == True` | 1회 | 도구 메시지 보고 판단 |

reason 문구는 **고정 문자열 + 안전한 식별자만** 쓴다.

| 상황 | reason |
|------|--------|
| 집행기 없음 | `지원 집행기 없음: {tool_id}` |
| tool_id 해석 실패 | `MCP 도구 id 형식이 아님` |
| 레거시 id | `도구 이름이 없는 구형 id — 에이전트에서 도구를 다시 선택하세요` |
| 등록 없음 / 비활성 | `MCP 서버 등록을 찾을 수 없음` / `MCP 서버가 비활성 상태` |
| list_tools 실패 | `MCP 서버 연결 실패 ({ExcType})` |
| 도구명 불일치 | `서버에 '{tool_name}' 도구가 없음` |
| call_tool 예외 | `호출 중 오류 ({ExcType})` |
| is_error | 도구 content 절단본 |

> **`str(e)` 금지** — streamable_http는 `api_key`·`profile`이 URL 쿼리에 실린다(`smithery_url.py:50`). httpx 예외 메시지에 URL이 들어가면 `error_message`로 영속·화면 노출된다. 예외 **타입명만** 문구에 쓰고, 전체 예외는 `logger.error(exception=e)`로만 남긴다.

### 6.2 예외 경계

`McpActionExecutor.execute`와 `CompositeActionExecutor.execute`는 **예외를 던지지 않는다.** 최상위에 `except Exception`을 두고 `unknown`이 아닌 **단계에 맞는 kind**로 변환한다(③ 이전이면 `blocked`, ④면 `unknown`). 스택 트레이스는 로거로.

### 6.3 트랜잭션·잠금 영향 (Phase 1 구조, 인지만)

- 즉시 집행은 승인 HTTP 요청의 DB 트랜잭션 안에서, 예약 집행은 `claim_due`의 `FOR UPDATE SKIP LOCKED` 잠금 안에서 돈다.
- MCP 호출이 길면 그만큼 트랜잭션·행 잠금이 유지된다 → **total 타임아웃을 짧게**(기본 60s) 두는 이유. 구조 변경은 이번 범위 밖.

---

## 7. Security Considerations

- [x] **시크릿 비노출**: 에러 문구에 `str(e)`·URL·헤더 금지(§6.1). 응답의 `auth_config`는 기존 마스킹 유지
- [x] **PII 비로깅**: `tool_args` 값은 로그에 남기지 않는다 — `arg_keys=sorted(arguments)`만. 도구 output도 로그에는 길이만
- [x] **권한**: 집행은 tool_id가 가리키는 등록(=에이전트 소유자의 것)의 자격증명으로 나간다. 승인권자도 소유자뿐(`ApprovalPolicy.can_decide`) — D-08. 새 권한 경로 없음
- [x] **자격증명 미복제**: 등록은 집행 시점 조회. approval 행·스냅샷에 넣지 않는다
- [x] **인자 변조 없음**: 집행기가 바꾸는 것은 래퍼 해제와 `idempotency_key` 주입뿐. 사람이 승인한 인자 값은 그대로 간다
- [ ] **플래그 우회**: 사용자가 플래그를 끄고 등록할 수 있다 — 최종 통제는 관리자 카탈로그 토글 + `is_enforced`(Phase 1 G2 종결 필요). 잔여 위험으로 기록
- [x] 입력 검증: `default_requires_approval`은 bool — pydantic 검증

---

## 8. Test Plan

> 이 프로젝트는 pytest(백엔드) + Vitest/RTL/MSW(프론트). Playwright 미사용 — L1은 `TestClient`, L2는 RTL로 수행.
> TDD: 아래 각 항목의 테스트를 **구현보다 먼저** 작성한다.

### 8.1 Test Scope

| Type | Target | Tool | Phase |
|------|--------|------|-------|
| Unit (domain) | `ExecutionFailurePolicy`, `McpArgumentPolicy` | pytest | Do |
| Unit (infra) | `McpActionExecutor`, `CompositeActionExecutor` (가짜 client 주입) | pytest + AsyncMock | Do |
| Unit (app) | `SyncMcpToolsUseCase` 초기값, Register/Update UseCase 필드 전달 | pytest | Do |
| Integration | decide / scheduler + Composite (집행기 없음 → failed) | pytest | Do |
| L1: API | mcp-registry 등록·수정·조회 필드 왕복 | FastAPI TestClient | Do |
| L2: UI | AdminMcpServersPage 체크박스 | Vitest + RTL + MSW | Do |
| DDL | V075 COMMENT | `test_migration_ddl_comments.py` | Do |
| PoC (수동) | 실등록 MCP 도구 승인 → 서버 도달 1회 | `/verify-mcp-connections` + 로컬 E2E | Check |

### 8.2 백엔드 단위 테스트 시나리오

**`tests/domain/approval/test_execution_policy.py`**

| # | 대상 | 시나리오 | 기대 |
|---|------|---------|------|
| P1 | `render` | kind별 접두 3종 | `[집행 불가]` / `[집행 여부 불명]` / `[도구 실패]`로 시작 |
| P2 | `render` | `unknown` | "확인한 뒤 재승인" 힌트 포함 |
| P3 | `unwrap` | `{"arguments": {"to": "a"}}` | `{"to": "a"}` |
| P4 | `unwrap` | 래퍼 아님 `{"to": "a"}` / `arguments`가 dict 아님 / 키가 2개 이상 | 원본 그대로 |
| P5 | `with_idempotency_key` | 스키마 properties에 있음 | 주입됨 |
| P6 | `with_idempotency_key` | 스키마에 없음 / 스키마 빈 dict / key None | 미주입 |
| P7 | `with_idempotency_key` | 인자에 이미 같은 키 존재 | 덮어쓰지 않음 |
| P8 | `with_idempotency_key` | 입력 dict 불변(사본 반환) | 원본 미변경 |
| P9 | `truncate` | 상한 초과 | 상한 + 절단 표식 |

**`tests/infrastructure/approval/test_mcp_executor.py`**

| # | 시나리오 | 기대 (kind · list_tools · call_tool 호출 수) |
|---|---------|------|
| E1 | `supports("mcp:sid:send")` / `supports("mcp_uuid")` / `supports("excel_export")` | True / True / False |
| E2 | 정상 | ok=True, output=content · 1 · **1** |
| E3 | 레거시 id (tool_name None) | blocked · 0 · 0 |
| E4 | 등록 없음 | blocked · 0 · 0 |
| E5 | `is_active=False` | blocked · 0 · 0 |
| E6 | list_tools 예외 | blocked · 1 · 0 |
| E7 | 도구명이 목록에 없음 | blocked · 1 · 0 |
| E8 | call_tool `TimeoutError` | unknown · 1 · **1 (재호출 없음)** — SC-7 |
| E9 | call_tool 임의 예외 | unknown · 1 · 1, **예외 전파 없음** |
| E10 | `is_error=True` | tool_error, 메시지에 content 포함 · 1 · 1 |
| E11 | 래퍼 인자 | call_tool이 받은 arguments == 해제된 dict |
| E12 | 스키마에 `idempotency_key` 있음 + key 전달 | arguments에 key 포함 |
| E13 | 스키마에 없음 | arguments에 key 없음 |
| E14 | 예외 메시지에 `api_key=SECRET` URL 포함 | `error_message`에 `SECRET` **없음** |
| E15 | 로그 캡처 | `tool_args` 값 문자열이 로그에 없음, `arg_keys`만 |
| E16 | output 상한 초과 | 절단됨 |
| E17 | client factory가 받은 retry 정책 | `max_retries == 0` |

**`tests/infrastructure/approval/test_composite_executor.py`**

| # | 시나리오 | 기대 |
|---|---------|------|
| C1 | 첫 매치 집행기에 위임, `idempotency_key` 전달 | 해당 집행기만 1회 호출 |
| C2 | 매치 없음 | ok=False, `[집행 불가] 지원 집행기 없음: …` — SC-2 |
| C3 | 하위 집행기가 예외를 던짐(계약 위반) | ok=False로 변환, 전파 없음 |
| C4 | `supports` | 하위 중 하나라도 True면 True |

**`tests/application/tool_catalog/test_sync_mcp_tools_use_case.py` (추가)**

| # | 시나리오 | 기대 |
|---|---------|------|
| S1 | 플래그 True 서버 | upsert에 넘긴 entry 전부 `requires_approval=True` — SC-5 |
| S2 | 플래그 False 서버 | `False` |
| S3 | (repo 테스트) 기존 엔트리 `requires_approval=0` + entry True로 upsert | DB 값 0 유지 — SC-6 |
| S4 | (repo 테스트) 기존 엔트리 `=1` + entry False로 upsert | DB 값 1 유지 — SC-6 |

**통합 (`tests/application/approval/`)**

| # | 시나리오 | 기대 |
|---|---------|------|
| I1 | decide 즉시 집행 + Composite(빈 목록) | 상태 `failed`, `executed` 전이 없음 |
| I2 | scheduler tick + Composite(빈 목록) | `failed` |
| I3 | decide/scheduler가 `approval.idempotency_key`를 executor에 전달 | kwarg 값 일치 |
| I4 | `main.py` 소스에 `MockActionExecutor` 문자열 없음 | SC-8 (정적 검사) |

### 8.3 L1: API Test Scenarios

| # | Endpoint | Method | Test | Status | Response |
|---|----------|--------|------|:------:|----------|
| A1 | `/api/v1/mcp-registry` | POST | 플래그 true로 등록 | 201/200 | `.default_requires_approval == true` |
| A2 | `/api/v1/mcp-registry` | POST | 필드 생략 | 201/200 | `false` (하위 호환) |
| A3 | `/api/v1/mcp-registry/{id}` | PUT | 플래그만 변경 | 200 | 변경 반영, 다른 필드 불변 |
| A4 | `/api/v1/mcp-registry/{id}` | PUT | 필드 생략 | 200 | 기존 값 유지 |
| A5 | `/api/v1/mcp-registry` | GET | 목록 | 200 | 각 item에 필드 존재 |
| A6 | `/api/v1/mcp-registry` | POST | `"yes"` 같은 비-bool 아닌 잘못된 타입(`{}`) | 422 | 검증 에러 |

### 8.4 L2: UI Test Scenarios (`AdminMcpServersPage/index.test.tsx`)

| # | Action | Expected |
|---|--------|----------|
| U1 | 등록 모달 열기 | 체크박스 존재, **미체크** |
| U2 | 체크 후 저장 | 요청 body `default_requires_approval: true` |
| U3 | 플래그 true 서버 수정 모달 | 체크된 상태로 열림 |
| U4 | 체크 해제 후 저장 | 요청 body `false` |
| U5 | 목록 렌더 | true 서버에만 "승인 기본" 뱃지 |

### 8.5 Seed / PoC 요구

| 대상 | 요구 |
|------|------|
| 로컬 PoC | 부작용이 무해한 실등록 MCP 도구 1개(예: 기존 Scrap 8002 / Browser 8005 중 하나)에 관리자 토글 또는 플래그로 `requires_approval=1` → 단독 워커 에이전트 → 승인 → **MCP 서버 로그에서 호출 1회** 확인 |
| 전제 | Phase 1 G1 종결(재개 저장), 게이트 부착 가능 상태(G2 또는 DB 직접 설정) |

---

## 9. Clean Architecture

### 9.1 Layer Structure (이 프로젝트: Thin DDD)

| Layer | Responsibility | Location |
|-------|---------------|----------|
| **domain** | 규칙·VO·포트. 외부 의존 없음 | `src/domain/` |
| **application** | UseCase·흐름 제어 | `src/application/` |
| **infrastructure** | MCP·DB·config 어댑터 | `src/infrastructure/` |
| **interfaces / api** | 라우터·스키마·DI | `src/api/`, `src/interfaces/` |

### 9.2 Dependency Rules

```
api ──▶ application ──▶ domain ◀── infrastructure
              └────────▶ infrastructure (DI로 주입된 구현)
```

### 9.3 Import Rules (이 기능에서 지킬 것)

| From | Can Import | Cannot Import |
|------|-----------|---------------|
| `domain/approval/execution_policy.py` | typing만 | langchain, mcp SDK, infra 전부 |
| `infrastructure/approval/mcp_executor.py` | domain/*, infrastructure/mcp, infrastructure/mcp_registry | application/* |
| `application/tool_catalog/sync_mcp_tools_use_case.py` | domain/* | infrastructure 구현 직접 참조 |

### 9.4 This Feature's Layer Assignment

| Component | Layer | Location |
|-----------|-------|----------|
| `ExecutionFailurePolicy`, `McpArgumentPolicy`, `ExecutionFailureKind` | domain | `src/domain/approval/execution_policy.py` **[신규]** |
| `ActionExecutorInterface.execute(+idempotency_key)` | domain | `src/domain/approval/interfaces.py` |
| `MCPServerRegistration.default_requires_approval` | domain | `src/domain/mcp_registry/schemas.py` |
| `McpActionExecutor` | infrastructure | `src/infrastructure/approval/mcp_executor.py` **[신규]** |
| `CompositeActionExecutor` | infrastructure | `src/infrastructure/approval/composite_executor.py` **[신규]** |
| `ApprovalExecutionConfig` | infrastructure | `src/infrastructure/config/approval_execution_config.py` **[신규]** |
| `MCPServerModel` 컬럼 + 매핑 | infrastructure | `src/infrastructure/mcp_registry/models.py`, `mcp_server_repository.py` |
| 초기값 로직 | application | `src/application/tool_catalog/sync_mcp_tools_use_case.py` |
| 필드 전달 | application | `src/application/mcp_registry/{schemas,register_…,update_…}.py` |
| kwarg 전달 | application | `src/application/approval/{decide_use_case,execute_scheduler}.py` |
| DI 교체 | api | `src/api/main.py` (approval 팩토리, `:3100-3110`) |
| `MockActionExecutor` | tests | `tests/support/approval/mock_executor.py` (**src에서 이동**, D-06) |

---

## 10. Coding Convention Reference

### 10.1~10.2 — 프로젝트 기존 규칙 준수

`idt/CLAUDE.md` §3·§6, `docs/rules/{db-session,logging,tool-and-mcp,testing}.md`. 함수 40줄·if 중첩 2단계 제한 → `McpActionExecutor.execute`는 단계별 private 메서드로 쪼갠다(§11.4 골격).

### 10.3 Environment Variables (신규, 전부 선택·기본값 있음)

| Variable | Default | Purpose |
|----------|:------:|---------|
| `APPROVAL_EXEC_CONNECT_TIMEOUT` | `15` | 집행 MCP 연결 타임아웃(초) |
| `APPROVAL_EXEC_TOTAL_TIMEOUT` | `60` | 집행 1건 전체 상한(초) — 트랜잭션·행 잠금 유지 시간의 상한(§6.3) |
| `APPROVAL_EXEC_OUTPUT_MAX_CHARS` | `8000` | 재개 주입·error_message용 출력 절단 상한 |

`ApprovalExecutionConfig(BaseSettings)` — `analysis_config.py`와 같은 형태, `model_config = {"env_file": ".env", "extra": "ignore"}`. `get_timeout() -> MCPTimeoutConfig`(read=total로 맞춤), `.env.example`에 주석과 함께 추가.

### 10.4 This Feature's Conventions

| Item | Convention Applied |
|------|-------------------|
| 집행 경로 retry | `MCPRetryPolicy(max_retries=0)` 고정 — config로 노출하지 않는다(켜면 안 되는 값) |
| 실패 문구 | `ExecutionFailurePolicy.render`만 사용. 집행기 안에서 접두 문자열 직접 작성 금지 |
| 에러 문구의 예외 | `type(e).__name__`만. `str(e)` 금지 |
| 로깅 | `request_id`·`tool_id`·`server_id`·`arg_keys`·`elapsed_ms`. 값·본문 금지. 실패는 `logger.error(exception=e)` |
| DDL | 컬럼 COMMENT + 모델 `comment=` 동일 |
| 코드 주석 | `# Design Ref: approval-gate-phase2 §N (D-xx)` / `# Plan SC-n` |
| 프론트 | 런타임 상수 export 금지, 타입은 `src/types/mcpServer.ts` |

---

## 11. Implementation Guide

### 11.1 File Structure

```
idt/
├── db/migration/V075__add_default_requires_approval_to_mcp_server_registry.sql   [신규]
├── src/domain/approval/execution_policy.py                                        [신규]
├── src/domain/approval/interfaces.py                          (kwarg)
├── src/domain/mcp_registry/schemas.py                         (필드)
├── src/infrastructure/approval/mcp_executor.py                                    [신규]
├── src/infrastructure/approval/composite_executor.py                              [신규]
├── src/infrastructure/approval/mock_executor.py               (삭제 → tests/support/approval/)
├── src/infrastructure/config/approval_execution_config.py                         [신규]
├── src/infrastructure/mcp_registry/{models,mcp_server_repository}.py
├── src/application/mcp_registry/{schemas,register_mcp_server_use_case,update_mcp_server_use_case}.py
├── src/application/tool_catalog/sync_mcp_tools_use_case.py
├── src/application/approval/{decide_use_case,execute_scheduler}.py   (kwarg 전달)
├── src/api/main.py                                            (DI)
├── .env.example
└── tests/ … (§8.2)

idt_front/src/
├── types/mcpServer.ts
├── services/mcpServerService.ts
├── pages/AdminMcpServersPage/index.tsx (+ index.test.tsx)
└── __tests__/mocks/handlers.ts (mcp-registry 핸들러)
```

### 11.2 Implementation Order (TDD — 각 단계 테스트 먼저)

1. [ ] **module-1 도메인**: `execution_policy.py` (P1~P9) → `interfaces.py` kwarg
2. [ ] **module-2 집행기**: `approval_execution_config.py` → `mcp_executor.py` (E1~E17) → `composite_executor.py` (C1~C4)
3. [ ] **module-3 배선**: decide/scheduler kwarg 전달(I3) → Mock을 `tests/support`로 이동 + import 수정 → `main.py` DI 교체(I1·I2·I4)
4. [ ] **module-4 서버 플래그(BE)**: V075 + 모델 → 도메인 스키마 → repo 매핑 → app 스키마·Register/Update UseCase → 라우터 응답(A1~A6) → sync 초기값(S1~S4)
5. [ ] **module-5 프론트**: 타입 → MSW → 페이지 체크박스·뱃지(U1~U5) — `/api-contract-sync`
6. [ ] `/verify-architecture`, `/verify-logging`, `/verify-tdd`, 회귀(FAILED diff), 로컬 PoC(§8.5)

### 11.3 Session Guide

#### Module Map

| Module | Scope Key | Description | Estimated Turns |
|--------|-----------|-------------|:---------------:|
| 도메인 정책 + 포트 kwarg | `module-1` | `execution_policy.py`, `interfaces.py` | 10-15 |
| MCP 집행기 + 합성 집행기 + config | `module-2` | 핵심. 가짜 client로 17+4 케이스 | 30-40 |
| 배선·Mock 이동 | `module-3` | decide/scheduler/main.py, 테스트 픽스처 경로 | 15-20 |
| 서버 플래그 백엔드 | `module-4` | V075 → 도메인 → repo → UseCase → API → sync | 25-35 |
| 서버 플래그 프론트 | `module-5` | 타입·MSW·페이지 | 15-20 |

#### Recommended Session Plan

| Session | Phase | Scope | Turns |
|---------|-------|-------|:-----:|
| Session 1 | Plan + Design | 전체 (완료) | — |
| Session 2 | Do | `--scope module-1,module-2` | 45-55 |
| Session 3 | Do | `--scope module-3,module-4` | 40-55 |
| Session 4 | Do | `--scope module-5` | 15-20 |
| Session 5 | Check + Report | 전체 + PoC | 30-40 |

module-1~3(집행)과 module-4~5(플래그)는 서로 독립이다 — 순서를 바꾸거나 worktree로 병행 가능.

### 11.4 핵심 골격 (참고 — 구현 시 40줄 제한 준수)

```python
# infrastructure/approval/mcp_executor.py
class McpActionExecutor(ActionExecutorInterface):
    def __init__(self, *, server_repo, client_factory, max_output_chars: int,
                 logger: LoggerInterface) -> None: ...
    # client_factory: Callable[[MCPServerRegistration], MCPCallClient]
    #   main.py 가 timeout=config.get_timeout(), retry=MCPRetryPolicy(max_retries=0) 로 조립.
    #   테스트는 가짜 client 를 돌려주는 람다를 주입한다.

    def supports(self, tool_id: str) -> bool:
        return parse_mcp_tool_id(tool_id) is not None

    async def execute(self, *, tool_id, tool_args, request_id, idempotency_key=None):
        ref = parse_mcp_tool_id(tool_id)
        if ref is None or ref.tool_name is None:
            return self._fail("blocked", …)
        client, blocked = await self._connect(ref, request_id)      # ①② → client | 실패결과
        if blocked: return blocked
        descriptor, blocked = await self._verify(client, ref, request_id)   # ③
        if blocked: return blocked
        arguments = McpArgumentPolicy.with_idempotency_key(
            McpArgumentPolicy.unwrap(tool_args), descriptor.input_schema, idempotency_key)
        return await self._call(client, ref, arguments, request_id)  # ④

# api/main.py (approval 팩토리)
exec_cfg = ApprovalExecutionConfig()
executor = CompositeActionExecutor(
    executors=[McpActionExecutor(
        server_repo=SessionScopedMcpServerRepository(get_session_factory(), app_logger, cipher=_mcp_cipher()),
        client_factory=lambda reg: MCPCallClient(
            config=MCPToolLoader._build_config(reg), timeout=exec_cfg.get_timeout(),
            retry=MCPRetryPolicy(max_retries=0), logger=app_logger),
        max_output_chars=exec_cfg.APPROVAL_EXEC_OUTPUT_MAX_CHARS, logger=app_logger)],
    logger=app_logger,
)
```

`SessionScopedMcpServerRepository`의 `cipher` 인자는 `main.py:2713`의 기존 생성부와 **같은 값**을 넘긴다(암호화된 `auth_config` 복호화에 필요). 세션은 집행기가 직접 열지 않는다 — session-scoped 어댑터가 `find_by_id` 호출마다 연다(`docs/rules/db-session.md`, tool-and-mcp §3).

---

## 12. Decision Record

| ID | Decision | Alternatives | Rationale |
|----|----------|--------------|-----------|
| D-01 | 호출 코어는 `MCPCallClient` | `MCPToolLoader`+`ainvoke` | 어댑터는 `isError` 무시·placeholder 문자열 반환·전체 타임아웃 없음 → 거짓 성공 (Plan Q-5) |
| D-02 | `list_tools` 검증 후 `call_tool` 2단계 | 바로 call_tool | "미발송 확실/불명" 경계를 예외 분류 없이 호출 구조로 얻음. 도구명 검증·input_schema 확보를 겸함 |
| D-03 | `{"arguments": {...}}` 래퍼 해제 | 게이트 쪽에서 해제해 저장 | Phase 1 저장 형식 불변. 해제 규칙은 도메인 정책 1곳 |
| D-04 | 실패 3분류는 문구 접두 | `failure_kind` 컬럼(Option B) | approval_request 스키마·API 불변. 정책 1곳이라 후속 승격 용이 |
| D-05 | 멱등키는 **도구 스키마에 있을 때만** 주입 | 항상 주입 / 미전달 | 스키마에 없는 인자는 서버 검증 실패 유발. 자체 구축 메일 서버가 받으면 R-1 근본 해소 (Plan Q-2) |
| D-06 | Mock은 `tests/support`로 이동 | src에 미배선으로 잔류 | `supports()=True` 집행기가 프로덕션 코드에 남지 않게 (Plan Q-4) |
| D-07 | 서버 플래그는 **신규 INSERT 초기값 전용**, UI 기본 꺼짐 | 매 sync 덮어쓰기 / UI 기본 켜짐 | V072 "sync는 관리자 값을 덮지 않는다" 계약 보존. 현재 등록 서버 5개가 전부 조회·수집용 — 켜짐 기본이면 단독 워커 제약에 걸린다 (Plan Q-1) |
| D-08 | 발신 계정 = tool_id가 가리키는 등록(소유자) | 실행자≠소유자 거부 | 승인권자=소유자. 추가 코드 없음 (Plan FR-18) |
| D-09 | 레거시 `mcp_{uuid}`는 fail-closed, 복원 로직 없음 | 게이트에 호출 도구명 추가 기록 | 로컬 DB 계량: `agent_tool` MCP 12건 **전부 카탈로그 형식**, 레거시 0건 (Plan Q-3) |
| D-10 | retry 0은 코드 고정, config 비노출 | env로 조절 | 켜면 안 되는 값을 설정으로 열어두지 않는다 |
| D-11 | 에러 문구에 예외 타입명만 | `str(e)` | URL 쿼리의 `api_key` 유출 방지 |

### Phase 1에 넘기는 관찰 (이번 범위 밖)

- `gate_middleware._extract_draft`는 최상위 키(`draft`/`body`/`content`/`본문`)만 본다 → MCP 도구는 인자가 `arguments` 아래라 승인 화면 초안이 JSON 덤프로 나온다. `McpArgumentPolicy.unwrap`을 재사용하면 한 줄로 개선 가능 — `approval-gate` iterate 후보.
- `execute_scheduler._run_one`의 예외 경로는 `f"{type(e).__name__}: {e}"`를 영속한다 → D-11과 같은 유출 가능성. 이번 집행기는 예외를 던지지 않으므로 경로가 닫히지만, 방어적으로 같이 고칠 가치가 있다.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-09-21 | Initial draft — Option C 선택, D-01~D-11, Plan Q-1~Q-5 종결 | 배상규 |
| 0.2 | 2026-09-21 | Do 반영 — ① 마이그레이션 V074→**V075** (V074 는 approval-gate iterate 가 선점) ② `build_execution_client` 를 main.py 람다에서 `mcp_executor.py` 함수로 이동 (D-10 재시도 0 을 테스트로 고정) ③ 예외 그룹은 안쪽 예외 타입명으로 표기 (`_exception_name`) ④ main.py 조립은 `_build_approval_executor` 헬퍼로 분리 ⑤ S3·S4(UPDATE 분기 보존)는 Phase 1 의 repository SQL 테스트가 이미 고정 — 이번엔 sync 흐름 테스트만 추가. 선행 조건이던 Phase 1 G1·G2·G3·G5·G13 은 iterate 로 종결됨(94%) | 배상규 |
