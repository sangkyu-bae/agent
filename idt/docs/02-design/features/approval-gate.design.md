# approval-gate Design Document

> **Summary**: 부작용 도구 호출을 순수 미들웨어가 차단하고, 워커 래퍼가 신호를 SupervisorState로 리프트하며, UseCase가 스냅샷과 함께 승인 요청을 영속한다. 승인은 집행 허가이고 집행은 `execute_after` 시각에 선점 스케줄러가 수행한 뒤 런을 재개한다.
>
> **Project**: sangplusbot (idt)
> **Author**: 배상규
> **Date**: 2026-09-20
> **Status**: Draft
> **Planning Doc**: [approval-gate.plan.md](../../01-plan/features/approval-gate.plan.md) (v0.2)

### Pipeline References

| Phase | Document | Status |
|-------|----------|--------|
| Phase 1~4 | — | N/A (9-phase 파이프라인 미사용 기능) |

---

## Context Anchor

> Plan v0.2에서 복사. Design→Do 인계 시 전략 맥락 보존.

| Key | Value |
|-----|-------|
| **WHY** | 에이전트의 비가역 부작용이 사람 검증 없이 실행된다. 동시에 새벽 집행 작업 때문에 사람을 그 시각에 묶어두는 것도 비효율이다. |
| **WHO** | P2 KB 운영자/에이전트 소유자(설정·승인) + 관리자(강제 정책) |
| **RISK** | 승인 중복 클릭에 의한 **이중 집행**. 예약 집행 시각까지 대기하는 동안 스냅샷·초안이 낡음. |
| **SUCCESS** | 게이트 도구는 승인 없이 **0회** 실행되고, 승인 후 지정 시각에 정확히 1회 집행되며, 런이 멈춘 지점부터 이어져 최종 답변까지 도달한다. |
| **SCOPE** | Phase 1(이번): 게이트 골격 + 미들웨어 편입 + 승인 API + 예약 집행 + 재개 + 작업함 탭(집행기 mock). Phase 2: 실도구. Phase 3: 자동 승인 조건식. |

---

## 1. Overview

### 1.1 Design Goals

1. **승인 없는 부작용 실행을 구조적으로 0회로** — 프롬프트 방어가 아니라 호출 경로 차단
2. **판단 시각과 집행 시각의 분리** — 사람을 기계의 시간표에 묶지 않는다
3. **에이전트별 제어를 기존 인프라로** — 신규 설정 테이블·검증·UI를 만들지 않는다
4. **기존 에이전트 무회귀** — 게이트 도구 미보유 시 실행 경로가 코드 수준에서 동일
5. **B(LangGraph interrupt) 전환 여지 보존** — Protocol 경계 유지

### 1.2 Design Principles

- **순수 미들웨어**: 게이트 미들웨어는 DB·그래프 상태에 접근하지 않는다. 차단하고 마커를 남길 뿐 → DB 없이 단위 테스트 가능하고 `MiddlewareBuilder`의 static 구조를 깨지 않는다
- **신호 리프트 재사용**: 워커 내부 트레이스 → SupervisorState 승격은 `ToolErrorPolicy.summarize` / `last_worker_empty`와 **완전 동형**으로 구현한다
- **안전 기능은 fail-closed**: 편의 미들웨어(재시도·폴백)의 "실패 시 스킵" 정책을 게이트에 적용하지 않는다
- **정책은 도메인 단일 지점**: 게이트 발동 조건·상태 전이·승인 권한을 각각 하나의 Policy 메서드로
- **멱등은 DB 제약으로**: 애플리케이션 체크가 아니라 유니크 인덱스 + 조건부 UPDATE

---

## 2. Architecture Options

### 2.0 Architecture Comparison

| Criteria | Option A: Minimal | Option B: Clean | **Option C: Pragmatic** |
|----------|:-:|:-:|:-:|
| **Approach** | 게이트 로직을 `_wrap_worker`에 인라인 | 진짜 LangChain 미들웨어 + Builder에 repo DI | 미들웨어는 차단·마커만, 래퍼가 신호 리프트 |
| **미들웨어 DB 접근** | 안 함 | **함** | **안 함** |
| **New Files** | ~12 | ~22 | ~16 |
| **Modified Files** | ~10 | ~14 | ~11 |
| **Complexity** | Low | High | Medium |
| **Maintainability** | Low | High | High |
| **Effort** | Low | High | Medium |
| **Risk** | Medium | Medium | **Low** |
| **Recommendation** | — | — | **Selected** |

**Selected**: **Option C** — **Rationale**:

- A는 초안(이메일 본문)을 얻으려면 결국 래퍼에서 LLM을 돌려야 해 approval 로직이 `workflow_compiler`에 눌러앉는다.
- B는 미들웨어가 react agent 내부에서 돌아 **`SupervisorState`에 접근할 수 없다** — 스냅샷을 밖에서 따로 합쳐야 하므로 결국 C와 같은 2단계가 되면서, `MiddlewareBuilder._build_one`의 `@staticmethod` 해제와 langchain 격리 계약(builtin-middleware D8) 재설계 비용만 추가된다.
- C는 미들웨어를 순수하게 유지해 **repo DI 문제 자체를 소멸**시키고, 기존 검증된 패턴 3개(신호 리프트 / 카탈로그 병합 / `FOR UPDATE SKIP LOCKED` 선점)를 그대로 재사용한다.

### 2.1 Component Diagram

```
┌────────────────────── 런 1 (게이트 발동) ──────────────────────┐
│                                                                │
│  supervisor ──▶ worker(email_send 단독)                        │
│                    │                                           │
│                    │  create_agent(middleware=[…, Gate])       │
│                    ▼                                           │
│            ┌───────────────────────────────┐                   │
│            │ ApprovalGateMiddleware (순수)  │                   │
│            │  wrap_tool_call:              │                   │
│            │   실도구 handler 호출 안 함 ❌  │                   │
│            │   ToolMessage 반환:            │                   │
│            │   "[APPROVAL_REQUIRED]{json}"  │                   │
│            └───────────────────────────────┘                   │
│                    │                                           │
│                    ▼  _wrap_worker                             │
│            ApprovalSignalPolicy.extract(result_messages)       │
│                    │        ↑ ToolErrorPolicy.summarize 동형    │
│                    ▼                                           │
│            state["approval_pending"] = {tool_id, args, draft}  │
│                    │                                           │
│                    ▼  route_to_worker_or_final                 │
│                 "__end__"   ← limit_reached 동형 최우선 분기     │
│                    │                                           │
│                    ▼  RunAgentUseCase                          │
│            ApprovalRequest 생성 + resume_snapshot 저장          │
│            런 정상 종료 ✅                                       │
└────────────────────────────────────────────────────────────────┘
                              │
              (사람의 시간)   ▼
┌────────────────────── 승인 ────────────────────────────────────┐
│  POST /approvals/{id}/approve                                  │
│   ApprovalPolicy.can_decide(user, req)   ← 에이전트 소유자       │
│   pending ──조건부 UPDATE──▶ scheduled                          │
│   execute_after = cron(config) 또는 now                        │
└────────────────────────────────────────────────────────────────┘
                              │
              (시스템의 시간) ▼  00:00
┌────────────────────── 집행 + 재개 ──────────────────────────────┐
│  ExecuteDueApprovalsUseCase (tick)                             │
│   repo.claim_due(now)  ← FOR UPDATE SKIP LOCKED                │
│   ActionExecutor.execute(tool_id, args)   [Phase1: Mock]       │
│   scheduled ──▶ executed | failed                              │
│        │                                                       │
│        ▼  ResumeRunUseCase                                     │
│   snapshot 복원 + AIMessage(name=worker_id, 결과) 주입          │
│   supervisor 노드부터 그래프 재진입 ──▶ 최종 답변 ✅              │
└────────────────────────────────────────────────────────────────┘
```

### 2.2 Data Flow

**게이트 발동 조건 (FR-21 합성 규칙)** — `ApprovalPolicy.should_gate()` 단일 지점

```
gate_on = tool_catalog.requires_approval(tool_id)
          AND  APPROVAL_GATE ∈ applied_middleware(agent_id)

applied_middleware = MiddlewareMergePolicy.merge(records, catalog)
                   = 스냅샷(에이전트 설정)  ∪  enforced(관리자 강제)
```

도구 축("무엇이 위험한가")과 에이전트 축("누가 통제받는가")은 직교하므로 둘 다 필요하다. `is_enforced=true`여도 부작용 도구가 없는 에이전트는 무영향이다.

**상태 기계**

```
                    ┌──── reject ────▶ rejected ──▶ (재개: 거절 사유 주입)
                    │
  pending ──approve─┼──▶ scheduled ──due+claim──▶ executed ──▶ (재개: 결과 주입)
     │              │                    │
     │              └─ execute_after=null ┘ (즉시 집행)
     │
     └──── expires_at 경과 ────▶ expired
                                                   └─실패─▶ failed (자동 재시도 없음)
```

역방향·건너뛰기 전이 금지. 전이 판정은 `ApprovalPolicy.next_status()` 단일 지점.

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `ApprovalGateMiddleware` | (없음 — 순수) | 차단 + 마커 생성. langchain `AgentMiddleware`만 상속 |
| `ApprovalSignalPolicy` | domain only | 트레이스에서 마커 파싱 |
| `_wrap_worker` | `ApprovalSignalPolicy` | 신호 리프트 |
| `RunAgentUseCase` | `ApprovalRepositoryInterface`, `SnapshotSerializer` | pending 영속 |
| `DecideApprovalUseCase` | `ApprovalPolicy`, repo, `ActionExecutorInterface` | 승인/거절 |
| `ExecuteDueApprovalsUseCase` | repo(`claim_due`), executor, `ResumeRunUseCase` | 예약 집행 |
| `ResumeRunUseCase` | `WorkflowCompiler`, `SnapshotSerializer` | 스냅샷 복원 + 재진입 |
| `MiddlewareBuilder` | `MiddlewareType.APPROVAL_GATE` | `case` 1개 추가 (fail-closed 재전파) |

---

## 3. Data Model

### 3.1 Entity Definition

```python
# src/domain/approval/entity.py
ApprovalStatus = Literal[
    "pending", "approved", "scheduled", "executed",
    "rejected", "expired", "failed",
]

@dataclass(frozen=True)
class ResumeSnapshot:
    """게이트 발동 런의 **최종** SupervisorState 직렬화 스냅샷 (v0.2 정제).

    Design v0.1 은 '워커 진입 시점' 이라고 적었으나, astream_events(v2) 에는
    워커 진입 시점 전체 상태를 잡는 후크가 없다(chain_end 는 노드 출력
    델타만 준다). 최종 chain_end 출력을 스냅샷하면 기존
    limit_reached/charts 캡처 선례를 그대로 쓰면서 맥락도 더 완전하다
    — 워커의 "승인 대기 등록됨" AIMessage 까지 포함된다.
    재개 단위가 '워커 1홉' 인 것은 동일하고, 집행 결과는
    AIMessage(name=worker_id) 로 덧붙인다.
    """
    schema_version: int          # 포맷 변경 대비 (현재 1)
    agent_updated_at: datetime   # 재개 전 정의 변경 검증용 (FR-14)
    worker_id: str
    state_json: str              # SupervisorState 직렬화 (messages 포함)

@dataclass
class ApprovalRequest:
    id: str
    run_id: str
    agent_id: str
    requested_by: str            # 런 실행 신원 (시스템일 수 있음)
    worker_id: str
    tool_id: str
    tool_args: dict              # 집행 시 그대로 사용
    draft: str                   # 사람이 검토할 초안 (이메일 본문 등)
    status: ApprovalStatus
    idempotency_key: str         # run_id:worker_id:tool_call_id — UNIQUE
    snapshot: ResumeSnapshot
    execute_after: datetime | None   # None = 즉시 집행
    expires_at: datetime
    decided_by: str | None
    decided_at: datetime | None
    decision_reason: str | None      # 거절 사유 (재개 시 주입)
    executed_at: datetime | None
    error_message: str | None
    seen_at: datetime | None         # 벨 배지 기준 (background_job 동형)
    created_at: datetime
    updated_at: datetime
```

### 3.2 Entity Relationships

```
[agent_definition] 1 ──── N [approval_request]
        │                        │
        │ user_id = 승인 권한자    │ run_id
        │                        ▼
        │                   [ai_run]  (관측 연결, AGENT-OBS-001)
        ▼
[middleware_catalog] ── N ── [agent_middleware]   (게이트 on/off + config)
[tool_catalog] .requires_approval                  (도구 축)
```

### 3.3 Database Schema

**V071 — `approval_request` (신규)**

```sql
CREATE TABLE approval_request (
    id                VARCHAR(36)  NOT NULL COMMENT '승인 요청 ID (UUID)',
    run_id            VARCHAR(36)  NOT NULL COMMENT '게이트가 발동한 에이전트 런 ID (ai_run 연결)',
    agent_id          VARCHAR(36)  NOT NULL COMMENT '대상 에이전트 ID (agent_definition.id)',
    requested_by      VARCHAR(100) NOT NULL COMMENT '런 실행 신원. 스케줄/웹훅이면 시스템 식별자',
    worker_id         VARCHAR(100) NOT NULL COMMENT '게이트가 걸린 워커 ID. 재개 시 결과 주입 대상',
    tool_id           VARCHAR(200) NOT NULL COMMENT '차단된 도구 ID (tool_catalog.tool_id)',
    tool_args         JSON         NOT NULL COMMENT '차단 시점 도구 인자. 집행 시 그대로 사용',
    draft             LONGTEXT     NOT NULL COMMENT '사람이 검토할 초안(이메일 본문 등)',
    status            VARCHAR(20)  NOT NULL COMMENT 'pending|approved|scheduled|executed|rejected|expired|failed',
    idempotency_key   VARCHAR(255) NOT NULL COMMENT '중복 집행 차단 키. run_id:worker_id:tool_call_id',
    snapshot_version  INT          NOT NULL DEFAULT 1 COMMENT 'resume_snapshot 포맷 버전',
    agent_updated_at  DATETIME     NOT NULL COMMENT '적재 시점 agent_definition.updated_at. 재개 전 대조(FR-14)',
    resume_snapshot   LONGTEXT     NOT NULL COMMENT '워커 진입 시점 SupervisorState 직렬화(JSON). 상한 256KB',
    execute_after     DATETIME     NULL COMMENT '집행 예정 시각(UTC). NULL이면 승인 즉시 집행',
    expires_at        DATETIME     NOT NULL COMMENT '만료 시각(UTC). 경과 시 expired, 승인 불가',
    decided_by        VARCHAR(100) NULL COMMENT '승인/거절한 사용자 ID',
    decided_at        DATETIME     NULL COMMENT '승인/거절 시각(UTC)',
    decision_reason   TEXT         NULL COMMENT '거절 사유. 재개 시 에이전트에 주입',
    executed_at       DATETIME     NULL COMMENT '집행 완료 시각(UTC)',
    error_message     TEXT         NULL COMMENT '집행 실패 사유. 자동 재시도 없음',
    seen_at           DATETIME     NULL COMMENT 'NULL=미확인. 벨 배지 기준 (background_job 동형)',
    request_id        VARCHAR(64)  NOT NULL COMMENT '적재 요청의 추적 ID',
    created_at        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '생성 시각(UTC)',
    updated_at        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                      ON UPDATE CURRENT_TIMESTAMP COMMENT '수정 시각(UTC)',
    PRIMARY KEY (id),
    UNIQUE KEY uk_approval_idempotency (idempotency_key),
    KEY ix_approval_agent_status (agent_id, status),
    KEY ix_approval_due (status, execute_after),
    KEY ix_approval_run (run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
  COMMENT='에이전트 부작용 도구의 사람 승인 요청 및 런 재개 스냅샷';
```

> `uk_approval_idempotency`가 **이중 집행 방어의 1차 저지선**이다. 같은 도구 호출로 두 번 pending이 생기지 않는다.
> `ix_approval_due`는 `claim_due`의 `WHERE status='scheduled' AND execute_after <= now` 스캔용.

**V072 — `tool_catalog.requires_approval` (컬럼 추가)**

```sql
ALTER TABLE tool_catalog
  ADD COLUMN requires_approval TINYINT(1) NOT NULL DEFAULT 0
  COMMENT '1이면 이 도구 호출 시 사람 승인 필요(런타임 SoT, 관리자 토글). ToolMeta.requires_approval_default는 신규 DB 시드 전용';
```

> **upsert 보존 계약**: `tool_catalog_repository`의 UPDATE 분기 SET 절에 `requires_approval`를 **넣지 않는다**. sync 재실행이 관리자 토글을 덮지 않도록 — `is_builtin`(V054)과 동일하며, SQL SET 절 컴파일 검사 테스트로 계약화한다.

**V073 — `middleware_catalog` 시드 (approval_gate 행)**

```sql
INSERT INTO middleware_catalog
  (id, middleware_type, name, description,
   is_builtin, is_enforced, default_config, is_active, sort_order)
VALUES
  (UUID(), 'approval_gate', '승인 게이트',
   '부작용 도구 호출 전 사람 승인을 요구한다. 승인 시각과 집행 시각을 분리할 수 있다.',
   0, 0,
   JSON_OBJECT('mode','always','execute_after',NULL,'expires_hours',168,'on_expire','expire'),
   1, 100);
```

> `sort_order=100` — 기존 4종보다 뒤. **게이트는 체인 마지막**이어야 `ToolCallLimitMiddleware` 등이 먼저 걸러낸 뒤 판정한다.
> `is_builtin=0, is_enforced=0`으로 시드 — 관리자가 명시적으로 켜기 전엔 **무회귀**.

### 3.4 에이전트별 config 스키마

```json
{
  "mode": "always",          // always | off   (is_enforced=true면 off 무시)
  "execute_after": null,     // cron 문자열 | null(즉시 집행)
  "expires_hours": 168,      // 1 ~ 720
  "on_expire": "expire"      // 현재 고정값
}
```

금리 에이전트 예시 — `agent_middleware.config`:
```json
{"mode":"always", "execute_after":"0 0 * * *", "expires_hours":24}
```

**per-agent 오버라이드 구현 (발견 1 대응)**

```python
# domain/middleware/policies.py — 시그니처 변경
class MiddlewareMergePolicy:
    @staticmethod
    def merge(
        records: list[AgentMiddlewareRecord],   # ← 기존 list[str] 에서 변경
        catalog: list[MiddlewareCatalogEntry],
    ) -> list[AppliedMiddleware]:
        """config = catalog.default_config ∪ record.config (record 우선).

        기존 4종은 record.config가 비어 있어 default_config 그대로 — 무회귀.
        """
```

`MiddlewareProvider.prepare`는 `snapshot_types` 대신 `records`를 넘긴다. `agent_id=None` 경로(General Chat / 컴파일러 미상)는 빈 config의 가상 record로 변환해 기존 동작을 보존한다.

---

## 4. API Specification

### 4.1 Endpoint List

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/api/v1/approvals` | 승인 대기 목록 (내가 승인 가능한 것) | Required |
| GET | `/api/v1/approvals/{id}` | 상세 (초안 전문 포함) | Required |
| POST | `/api/v1/approvals/{id}/approve` | 승인 → scheduled 또는 즉시 집행 | Required |
| POST | `/api/v1/approvals/{id}/reject` | 거절 (사유 필수) | Required |
| POST | `/api/v1/approvals/{id}/seen` | 확인 처리 (벨 배지 해제) | Required |
| POST | `/api/v1/internal/approvals/tick` | 예약 집행 tick (내부 전용) | Internal |

> `tick`은 기존 `/api/v1/internal/schedules` 라우터와 동일한 내부 인증 방식을 따른다.

### 4.2 Detailed Specification

#### `POST /api/v1/approvals/{id}/approve`

**Request**: 본문 없음

**Response (200 OK)**
```json
{
  "id": "a1b2…",
  "status": "scheduled",
  "execute_after": "2026-09-21T00:00:00Z",
  "message": "2026-09-21 00:00 (UTC)에 집행 예정입니다."
}
```
`execute_after`가 null이면 즉시 집행되어 `status: "executed"`로 응답한다.

**Error Responses**
- `400 APPROVAL_INVALID_WINDOW` — `expires_at < execute_after` (영원히 집행 안 되는 조합, FR-26)
- `403 APPROVAL_FORBIDDEN` — `can_decide` 실패 (에이전트 소유자 아님)
- `404 APPROVAL_NOT_FOUND`
- `409 APPROVAL_NOT_PENDING` — 이미 처리됨 (조건부 UPDATE 영향 행 0). **중복 클릭의 정상 응답**
- `410 APPROVAL_EXPIRED` — 만료됨
- `409 APPROVAL_AGENT_CHANGED` — 에이전트 정의 변경으로 재개 불가 (집행만 원하면 `?execute_only=true`)

#### `POST /api/v1/approvals/{id}/reject`

**Request**
```json
{ "reason": "금리 인상폭이 승인 한도를 초과합니다" }
```
`reason`은 필수(min 1자) — 재개 시 에이전트에 주입되므로 빈 사유는 의미가 없다.

#### `GET /api/v1/approvals`

**Query**: `status` (기본 `pending,scheduled`), `agent_id`, `page`, `size`

**Response (200 OK)**
```json
{
  "data": [{
    "id": "a1b2…", "agent_id": "…", "agent_name": "금리 변경 에이전트",
    "tool_id": "rate_update", "draft_preview": "기준금리를 3.50%…",
    "status": "pending", "execute_after": null,
    "expires_at": "2026-09-27T09:00:00Z", "seen_at": null,
    "created_at": "2026-09-20T09:00:00Z"
  }],
  "pagination": { "total": 3, "page": 1, "size": 20 }
}
```

---

## 5. UI/UX Design

### 5.1 Screen Layout

```
┌──────────────────────────────────────────────────────┐
│  작업함                                    🔔 3       │
├──────────────────────────────────────────────────────┤
│  [작업 기록]  [스케줄]  [승인 대기 ●3]   ← 탭 추가     │
├──────────────────────────────────────────────────────┤
│  ┌────────────────────────────────────────────────┐  │
│  │ 금리 변경 에이전트          [pending]  ●미확인  │  │
│  │ 도구: rate_update                              │  │
│  │ ┌────────────────────────────────────────────┐ │  │
│  │ │ 기준금리를 3.50% → 3.25%로 변경합니다…      │ │  │
│  │ └────────────────────────────────────────────┘ │  │
│  │ 집행 예정: 2026-09-21 00:00                    │  │
│  │ 만료: 2026-09-21 09:00                         │  │
│  │                        [거절]  [승인]           │  │
│  └────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────┘
```

### 5.2 User Flow

```
작업함 진입 → '승인 대기' 탭 → 초안 확인 → 승인
                                    │
                                    ├─ execute_after 있음 → "○시에 집행 예정" 안내
                                    └─ 없음 → 즉시 집행 → 결과 표시

                                  거절 → 사유 입력 모달 → 제출
```

### 5.3 Component List

| Component | Location | Responsibility |
|-----------|----------|----------------|
| `ApprovalTable` | `pages/JobsPage/` | 승인 대기 목록 렌더 |
| `ApprovalCard` | `pages/JobsPage/` | 단건 — 초안 미리보기 + 액션 버튼 |
| `RejectReasonDialog` | `pages/JobsPage/` | 거절 사유 입력 |
| `useApprovals` | `hooks/` | TanStack Query 목록/뮤테이션 |
| `approvalService` | `services/` | API 호출 |
| `ApprovalGateConfigForm` | 에이전트 미들웨어 설정 화면 | mode/execute_after/expires_hours 편집. `is_enforced`면 읽기 전용 |

### 5.4 Page UI Checklist

#### 작업함 — 승인 대기 탭

- [ ] Tab: '승인 대기' 탭 (pending+scheduled 건수 배지, 0이면 배지 숨김)
- [ ] Badge: 상태 배지 5종 (pending / scheduled / executed / rejected / expired / failed)
- [ ] Indicator: 미확인 점(`seen_at === null`)
- [ ] Card: 에이전트명 + 도구 ID 표시
- [ ] Card: 초안 미리보기 (3줄 클램프, 클릭 시 전문 확장)
- [ ] Card: 집행 예정 시각 (`execute_after` 있을 때만, 로컬 타임존 표기)
- [ ] Card: 만료 시각 + 잔여 시간
- [ ] Button: [승인] — 처리 중 disabled, 중복 클릭 방지
- [ ] Button: [거절] — 사유 입력 다이얼로그 오픈
- [ ] Dialog: 거절 사유 textarea (필수, 1자 이상, 미입력 시 제출 disabled)
- [ ] Empty: 대기 건 0일 때 빈 상태 문구
- [ ] Error: 409(이미 처리됨) 수신 시 토스트 + 목록 자동 갱신
- [ ] Filter: 상태 필터 (전체 / 대기 / 예약됨 / 완료)

#### 에이전트 설정 — 미들웨어 섹션

- [ ] Toggle: '승인 게이트' on/off (`is_enforced`면 강제 on + 비활성 + "관리자 강제" 뱃지)
- [ ] Input: 집행 시각 cron (비우면 즉시 집행)
- [ ] Input: 만료 시간(시간 단위, 1~720)
- [ ] Hint: 게이트는 `requires_approval` 도구에만 발동한다는 안내 문구

### 5.5 벨 배지 확장

`GET /api/v1/jobs/unseen-count` 응답을 **가산이 아니라 분해**한다 — 기존 소비자를 깨지 않기 위해:

```json
{ "count": 5, "jobs": 2, "approvals": 3 }
```
기존 `count` 필드 의미(총 미확인)는 유지되고, 프론트는 필요 시 `approvals`로 분해 표시한다.

---

## 6. Error Handling

### 6.1 Error Code Definition

| Code | HTTP | Cause | Handling |
|------|:----:|-------|----------|
| `APPROVAL_NOT_FOUND` | 404 | 없는 ID | 목록 갱신 |
| `APPROVAL_FORBIDDEN` | 403 | `can_decide` 실패 | "승인 권한이 없습니다" |
| `APPROVAL_NOT_PENDING` | 409 | 이미 처리됨(중복 클릭) | **정상 흐름** — 토스트 + 목록 갱신 |
| `APPROVAL_EXPIRED` | 410 | 만료 | "만료된 요청입니다" |
| `APPROVAL_INVALID_WINDOW` | 400 | `expires_at < execute_after` | 설정 오류 안내 |
| `APPROVAL_AGENT_CHANGED` | 409 | 정의 변경으로 재개 불가 | "집행만 진행" 선택지 제시 |
| `APPROVAL_GATE_BUILD_FAILED` | 500 | **게이트 조립 실패 (fail-closed)** | 에이전트 실행 중단. 관리자 알림 |
| `APPROVAL_SNAPSHOT_TOO_LARGE` | — | 스냅샷 256KB 초과 | messages 절단 + warning 로그, 적재는 진행 |

### 6.2 fail-closed 처리 (발견 2 대응)

```python
# MiddlewareBuilder.build() — 게이트만 예외 재전파
for a in applied:
    try:
        instances.append(self._build_one(a, fallback_models or []))
    except Exception as e:
        if a.middleware_type is MiddlewareType.APPROVAL_GATE:
            self._logger.error(
                "Approval gate build failed — aborting agent compile",
                request_id=request_id, exception=e,
            )
            raise            # ← 안전 기능은 조용히 빠지지 않는다
        self._logger.warning("Middleware build skipped", ...)
```

### 6.2b 예약 대기 중 에이전트 정의 변경 (Check G8 명시)

FR-14 에 따라 **집행은 진행하고 재개만 거부**한다. 사람이 승인한 것은
`tool_args` 에 고정된 부작용 내용(이메일 본문·금리값)이지 에이전트 구성이
아니므로 집행을 막을 근거가 없다. 재개는 스냅샷이 옛 구성을 가정하므로
`RunAgentUseCase._can_resume` 이 `updated_at` 불일치로 거부하고 경고를 남긴다.

### 6.3 집행 실패

`scheduled → failed` + `error_message` 기록. **자동 재시도하지 않는다** — 비가역 작업의 재시도는 이중 집행 위험. `failed`는 작업함 벨에 노출되어 사람이 재판단한다.

---

## 7. Security Considerations

- [ ] **권한**: 모든 승인/거절은 `ApprovalPolicy.can_decide` 통과 필수. 라우터에서 우회 불가
- [ ] **우회 차단**: 게이트는 미들웨어 체인에 있으므로 LLM이 어떤 `tool_call`을 내도 실도구에 도달 불가 — 프롬프트 방어 아님
- [ ] **강제 불가역성**: `is_enforced=true`면 `mode=off`로도 비활성화 불가 (`MergePolicy`가 구조적으로 보장)
- [ ] **멱등**: `uk_approval_idempotency` + 조건부 UPDATE + `FOR UPDATE SKIP LOCKED` 3중
- [ ] **내부 엔드포인트**: `/internal/approvals/tick`은 기존 internal 라우터와 동일 인증
- [ ] **초안 내용**: `draft`에 PII가 담길 수 있음 — 기존 PII 미들웨어와의 상호작용은 Phase 2에서 검토 (본 사이클 out of scope)
- [ ] **감사**: `decided_by`/`decided_at`/`executed_at`/`error_message` 영속
- [ ] **스냅샷**: `resume_snapshot`에 대화 messages가 포함됨 — 기존 대화 저장 정책과 동일한 보안 등급으로 취급

---

## 8. Test Plan

### 8.1 Test Scope

| Type | Target | Tool | Phase |
|------|--------|------|-------|
| L0: Unit | Policy·Middleware·Serializer (DB 없이) | pytest | Do |
| L1: API | 승인 엔드포인트 — 상태·권한·멱등 | pytest + TestClient | Do |
| L2: UI Action | 승인 탭 요소·액션 | Vitest + RTL + MSW | Do |
| L3: E2E | 게이트→승인→집행→재개 전 구간 | pytest (인프로세스) | Do |

> 로컬 실행은 `TestClient` 인프로세스 방식을 쓴다 (dev 서버 `--reload`가 변경을 즉시 반영하지 않는 함정 회피).

### 8.2 L1: API Test Scenarios

| # | Endpoint | Method | Test | Expected | Response |
|---|----------|--------|------|:--------:|----------|
| 1 | `/approvals` | GET | 내가 소유한 에이전트 건만 반환 | 200 | 타 소유자 건 미포함 |
| 2 | `/approvals/{id}/approve` | POST | 소유자 승인 → scheduled | 200 | `.status="scheduled"`, `.execute_after` 존재 |
| 3 | `/approvals/{id}/approve` | POST | `execute_after=null` → 즉시 집행 | 200 | `.status="executed"` |
| 4 | `/approvals/{id}/approve` | POST | **비소유자** 승인 시도 | 403 | `APPROVAL_FORBIDDEN` |
| 5 | `/approvals/{id}/approve` | POST | **중복 클릭** (2회차) | 409 | `APPROVAL_NOT_PENDING`, 집행 1회 |
| 6 | `/approvals/{id}/approve` | POST | 만료 건 | 410 | `APPROVAL_EXPIRED` |
| 7 | `/approvals/{id}/approve` | POST | `expires_at < execute_after` | 400 | `APPROVAL_INVALID_WINDOW` |
| 8 | `/approvals/{id}/approve` | POST | 에이전트 정의 변경됨 | 409 | `APPROVAL_AGENT_CHANGED` |
| 9 | `/approvals/{id}/reject` | POST | 사유 없이 거절 | 422 | 검증 오류 |
| 10 | `/approvals/{id}/reject` | POST | 사유 포함 거절 | 200 | `.status="rejected"` |
| 11 | `/internal/approvals/tick` | POST | due 건 집행 | 200 | `.executed_count` 증가 |
| 12 | `/internal/approvals/tick` | POST | due 아닌 건 미집행 | 200 | `.executed_count=0` |
| 13 | `/jobs/unseen-count` | GET | approvals 분해 필드 | 200 | `.count = .jobs + .approvals` |

### 8.3 L0: Unit Test Scenarios (핵심)

| # | Target | Test | Expected |
|---|--------|------|----------|
| 1 | `ApprovalGateMiddleware` | `wrap_tool_call` 호출 | **handler 미호출** + 마커 ToolMessage 반환 |
| 2 | `ApprovalSignalPolicy.extract` | 마커 포함 트레이스 | `{tool_id, args, draft}` 파싱 |
| 3 | `ApprovalSignalPolicy.extract` | 마커 없는 트레이스 | `None` |
| 4 | `ApprovalPolicy.should_gate` | 도구 O / 미들웨어 X | `False` |
| 5 | `ApprovalPolicy.should_gate` | 도구 X / enforced O | `False` (도구 축 없으면 미발동) |
| 6 | `ApprovalPolicy.should_gate` | 도구 O / enforced O / `mode=off` | **`True`** (강제 우선) |
| 7 | `ApprovalPolicy.next_status` | `executed → approved` 역전이 | `ValueError` |
| 8 | `MergePolicy.merge` | record.config 오버라이드 | default_config ∪ record.config |
| 9 | `MergePolicy.merge` | 기존 4종, record.config 빈 값 | **default_config 그대로 (무회귀)** |
| 10 | `MiddlewareBuilder.build` | APPROVAL_GATE 조립 실패 | **예외 재전파** (fail-closed) |
| 11 | `MiddlewareBuilder.build` | TOOL_RETRY 조립 실패 | warning + 스킵 (기존 정책 유지) |
| 12 | `SnapshotSerializer` | round-trip | `SupervisorState` 동등성 |
| 13 | `SnapshotSerializer` | 256KB 초과 | messages 절단 + warning |
| 14 | `CreateAgentUseCase` | 게이트 도구 + 타 도구 동일 워커 | **거부** (단독 워커 제약) |
| 15 | `CreateAgentUseCase` | 빌트인 주입 **후** 제약 위반 | 거부 (검증 순서) |
| 16 | `claim_due` | 동시 5워커 | 정확히 1워커만 클레임 |

### 8.4 L3: E2E Scenario Tests

| # | Scenario | Steps | Success Criteria |
|---|----------|-------|-----------------|
| 1 | **즉시 집행 전 구간** | 게이트 에이전트 실행 → pending 생성 → 런 정상 종료 → 승인 → 집행 → 재개 → 최종 답변 | 실도구 호출 1회, 최종 `AIMessage` 존재 |
| 2 | **예약 집행 (금리 시나리오)** | `execute_after="0 0 * * *"` 설정 → 실행 → pending → 승인(`scheduled`) → 시각 경과 → tick → 집행 → 재개 | tick 전 집행 0회, tick 후 1회 |
| 3 | **거절 재개** | pending → 거절(사유) → 사유 주입 재개 | 최종 답변에 거절 맥락 반영, 실도구 0회 |
| 4 | **우회 차단** | LLM이 게이트 도구를 여러 번 호출 시도 | 실도구 호출 **0회**, pending 1건 |
| 5 | **무회귀** | 게이트 도구 없는 기존 에이전트 실행 | 응답 형태·워커 경로가 기존과 동일 |
| 6 | **강제 정책** | `is_enforced=1` + 에이전트 `mode=off` | 게이트 발동 |
| 7 | **만료** | `expires_hours=0.01` → 경과 후 승인 시도 | 410, 집행 0회 |
| 8 | **런당 1건** | 한 런에서 게이트 2회 도달 | pending 1건, 런 종료 |

### 8.5 Seed Data Requirements

| Entity | Minimum Count | Key Fields Required |
|--------|:------------:|---------------------|
| `tool_catalog` | 2 | `requires_approval` = 1 / 0 각 1건 |
| `middleware_catalog` | 1 | `approval_gate` 행 (`is_enforced` 토글 가능) |
| `agent_definition` | 2 | 게이트 도구 보유 / 미보유 각 1건 |
| `agent_middleware` | 1 | `approval_gate` + config 오버라이드 |
| `approval_request` | 4 | pending / scheduled / expired / executed 각 1건 |

---

## 9. Clean Architecture

### 9.1 Layer Structure

| Layer | Responsibility | Location |
|-------|---------------|----------|
| **domain** | Entity, VO, Policy, Interface | `src/domain/approval/`, `src/domain/middleware/` |
| **application** | UseCase, Middleware, 흐름 제어 | `src/application/approval/` |
| **infrastructure** | Model, Repository, Executor, Serializer | `src/infrastructure/approval/` |
| **interfaces** | Router, Schema | `src/api/routes/`, `src/interfaces/schemas/` |

### 9.2 Dependency Rules

```
interfaces ──→ application ──→ domain ←── infrastructure
                    │                          ▲
                    └──────────────────────────┘
      규칙: domain 은 아무것도 참조하지 않는다 (langchain 포함)
```

**주의**: `ApprovalGateMiddleware`는 langchain을 상속하므로 **application**에 둔다. domain에 두면 `domain → langchain` 위반이다. 단, 게이트 **판정**(`should_gate`)은 domain Policy에 둔다.

### 9.3 This Feature's Layer Assignment

| Component | Layer | Location |
|-----------|-------|----------|
| `ApprovalRequest`, `ResumeSnapshot`, `ApprovalStatus` | domain | `domain/approval/entity.py` |
| `ApprovalPolicy` (`should_gate`/`can_decide`/`next_status`/`is_expired`) | domain | `domain/approval/policies.py` |
| `ApprovalSignalPolicy` (마커 파싱) | domain | `domain/approval/policies.py` |
| `ApprovalRepositoryInterface`, `ActionExecutorInterface` | domain | `domain/approval/interfaces.py` |
| `MiddlewareType.APPROVAL_GATE` | domain | `domain/middleware/entities.py` *(수정)* |
| `MiddlewareConfigPolicy` APPROVAL_GATE case | domain | `domain/middleware/config_policy.py` *(수정)* |
| `MiddlewareMergePolicy.merge` config 병합 | domain | `domain/middleware/policies.py` *(수정)* |
| `ApprovalGateInterface` (Protocol) | application | `application/approval/gate_interface.py` |
| `ApprovalGateMiddleware` | application | `application/approval/gate_middleware.py` |
| `DecideApprovalUseCase` | application | `application/approval/decide_use_case.py` |
| `ExecuteDueApprovalsUseCase` | application | `application/approval/execute_scheduler.py` |
| `ResumeRunUseCase` | application | `application/approval/resume_use_case.py` |
| `ListApprovalsUseCase` | application | `application/approval/list_use_case.py` |
| `ApprovalRequestModel` | infrastructure | `infrastructure/approval/models.py` |
| `ApprovalRepository` (+`claim_due`) | infrastructure | `infrastructure/approval/repository.py` |
| `SnapshotSerializer` | infrastructure | `infrastructure/approval/snapshot.py` |
| `MockActionExecutor` | infrastructure | `infrastructure/approval/mock_executor.py` |
| `approval_router` | interfaces | `api/routes/approval_router.py` |
| DTO | interfaces | `interfaces/schemas/approval.py` |

> `ApprovalGateInterface`는 파라미터가 application DTO를 물므로 **application에 둔다** — `PlannerInterface`(위키 stateless-hitl D9)와 동일한 이유. domain에 두면 역참조.

---

## 10. Coding Convention Reference

### 10.1 Naming Conventions

프로젝트 기존 규칙 준수 (Python: snake_case 함수 / PascalCase 클래스, TS: PascalCase 컴포넌트).

### 10.4 This Feature's Conventions

| Item | Convention Applied |
|------|-------------------|
| 세션/트랜잭션 | Repository 내부 commit/rollback 금지. 한 UseCase 내 단일 세션 (`docs/rules/db-session.md`) |
| 로깅 | `print()` 금지, `request_id` 전파, 스택 트레이스 보존 (`docs/rules/logging.md`) |
| DDL | 테이블 + 전 컬럼 COMMENT 필수 (`test_migration_ddl_comments.py` 검사) |
| 도메인 순수성 | `domain/`에서 langchain·DB·env 참조 금지. 상한은 어댑터가 주입 |
| 미들웨어 인스턴스 | 워커마다 새 인스턴스 (builtin-middleware D6) |
| langchain 격리 | langchain v1 클래스 참조는 `MiddlewareBuilder`와 `gate_middleware.py`에만 (D8) |
| 코드 주석 | `# Design Ref: §N — 결정 근거` / `# Plan SC: FR-NN` |

---

## 11. Implementation Guide

### 11.1 File Structure

```
idt/
├── db/migration/
│   ├── V071__create_approval_request.sql
│   ├── V072__add_requires_approval_to_tool_catalog.sql
│   └── V073__seed_approval_gate_middleware.sql
├── src/domain/approval/{entity,policies,interfaces}.py
├── src/domain/middleware/{entities,config_policy,policies}.py        (수정)
├── src/domain/agent_builder/schemas.py                                (수정: ToolMeta)
├── src/application/approval/
│   ├── gate_interface.py  gate_middleware.py
│   ├── decide_use_case.py execute_scheduler.py
│   ├── resume_use_case.py list_use_case.py
├── src/application/middleware/{middleware_builder,middleware_provider}.py  (수정)
├── src/application/agent_builder/{workflow_compiler,supervisor_state,supervisor_nodes}.py (수정)
├── src/infrastructure/approval/{models,repository,snapshot,mock_executor}.py
├── src/api/routes/approval_router.py
└── src/interfaces/schemas/approval.py

idt_front/src/
├── pages/JobsPage/{ApprovalTable,ApprovalCard,RejectReasonDialog}.tsx
├── hooks/useApprovals.ts
├── services/approvalService.ts
├── types/approval.ts
└── constants/api.ts                                                   (수정)
```

### 11.2 Implementation Order

1. [ ] 마이그레이션 3종 + 모델 + Repository (TDD: DDL COMMENT 테스트 먼저)
2. [ ] domain/approval — Entity + Policy 4종 (DB 없이 전부 단위 테스트)
3. [ ] domain/middleware 확장 — Enum + ConfigPolicy + MergePolicy config 병합
4. [ ] `MiddlewareBuilder` case + fail-closed
5. [ ] `ApprovalGateMiddleware` (순수 — DB 없이 테스트)
6. [ ] `_wrap_worker` 신호 리프트 + `SupervisorState.approval_pending` + 라우팅
7. [ ] `SnapshotSerializer` + `RunAgentUseCase` 적재
8. [ ] 단독 워커 제약 (`CreateAgentUseCase`, 빌트인 주입 **후**)
9. [ ] 승인/거절 UseCase + 라우터
10. [ ] 예약 집행 스케줄러 (`claim_due`) + tick 엔드포인트
11. [ ] `ResumeRunUseCase`
12. [ ] 프론트 — 타입 → 서비스 → 훅 → 컴포넌트 → 탭
13. [ ] E2E 8종

### 11.3 Session Guide

#### Module Map

| Module | Scope Key | Description | Est. Turns |
|--------|-----------|-------------|:---:|
| 영속 계층 | `module-1` | V071~V073 + 모델 + Repository(`claim_due` 포함) | 25-30 |
| 도메인 정책 | `module-2` | `domain/approval` 전체 + `domain/middleware` 확장 3종 | 30-35 |
| 게이트 배선 | `module-3` | Middleware + Builder fail-closed + 래퍼 리프트 + 라우팅 + 단독워커 제약 | 40-50 |
| 승인·집행 | `module-4` | Decide/List UseCase + 라우터 + 예약 스케줄러 + Resume | 40-50 |
| 프론트 | `module-5` | 승인 탭 + 에이전트 설정 노출 + 벨 배지 | 30-40 |

> `module-2`는 `module-1` 없이도 가능(순수 도메인). `module-3`은 1·2 완료 필요. `module-4`는 3 완료 필요. `module-5`는 4의 API 계약만 있으면 병행 가능.

#### Recommended Session Plan

| Session | Phase | Scope | Turns |
|---------|-------|-------|:-----:|
| 1 | Plan + Design | 전체 | ✅ 완료 |
| 2 | Do | `--scope module-1,module-2` | 55-65 |
| 3 | Do | `--scope module-3` | 40-50 |
| 4 | Do | `--scope module-4` | 40-50 |
| 5 | Do | `--scope module-5` | 30-40 |
| 6 | Check + QA + Report | 전체 | 40-50 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.2 | 2026-09-21 | 스냅샷 시점 정제 — '워커 진입 시점' → '런 최종 상태'. astream_events(v2) 에 진입 후크가 없고, 최종 상태가 캡처 선례(limit_reached/charts)와 동형이며 맥락도 더 완전하다 | 배상규 |
| 0.1 | 2026-09-20 | 초안 — Option C 선택(미들웨어 차단 + 래퍼 신호 리프트), per-agent config 오버라이드 전체 구현, 게이트 fail-closed. 조사 중 발견 2건(config 미구현 / fail-open) 반영 | 배상규 |
