# tool-access-control Design Document

> **Summary**: 도구별 허용 규칙(기본 세트·부서·사용자, 합집합)을 테이블 3개에 저장하고, `ToolAccessResolver`가 만든 `ToolAccessSet` 하나로 카탈로그 조회·에이전트 저장·포크·실행·승인 집행을 판정한다. 실행 필터는 `WorkflowCompiler.compile` 첫머리에서 워커 목록을 거르는 방식이라 전용 노드·서브에이전트까지 한 지점에서 적용된다.
>
> **Project**: sangplusbot (Agent Builder)
> **Version**: idt 0.1.0 / idt_front 0.0.0
> **Author**: 배상규
> **Date**: 2026-11-03
> **Status**: Draft
> **Planning Doc**: [tool-access-control.plan.md](../../01-plan/features/tool-access-control.plan.md)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 도구 선택·실행에 부서·사용자 조건이 없어 권한과 관계없이 누구나 도구를 통해 자료에 접근한다. |
| **WHO** | P3 시스템 관리자(권한 지정), P2 에이전트 소유자(허용된 도구로 구성·배포), P1·P4 실행 사용자(허용된 도구만 사용). |
| **RISK** | 기본 차단 전환으로 기존 에이전트 도구가 일제히 막히는 회귀, 실행 경로 중 판정이 빠진 우회로(서브에이전트·빌트인 주입·서버 단위 MCP 참조·포크), 도구 ID 이중 네임스페이스로 인한 판정 불일치. |
| **SUCCESS** | 배포 직후 기존 에이전트 동작 변화 0건(기본 세트 시드), 권한 없는 도구가 목록·저장·실행 어느 경로로도 쓰이지 않음(실행 경로 전수 테스트), MCP 레지스트리 무인증 호출 401. |
| **SCOPE** | M1 판정 정책·저장소·마이그레이션 → M2 관리자 권한 API + MCP 레지스트리 인증 → M3 목록·저장·포크 적용 → M4 실행 시점 필터(전 실행 경로) → M5 관리자 권한 화면 → M6 빌더·채팅 표시 |

---

## 0. Plan 이후 코드 대조로 바뀐 사실

Plan 작성 후 실행 경로를 전수 확인한 결과, Plan의 가정 두 가지가 달랐다. 이 Design은 아래 사실을 전제로 한다.

| # | Plan 가정 | 코드 사실 | 근거 | 결정 |
|---|-----------|----------|------|------|
| F1 | 비대화 실행은 모두 `auth_ctx`를 넘긴다 | 웹훅·백그라운드 잡만 넘긴다. **스케줄·승인 재개·RAGAS 에이전트 평가는 `auth_ctx` 없이 `user_id`만 넘긴다** | `trigger_due_schedules_use_case.py:145`, `run_agent_use_case.py:1265`, `api/main.py:4062`, `workflow_compiler.py:629-630` 주석 | `auth_ctx`가 없으면 `user_id`로 DB 조회해 판정 (사용자 결정). 기존 `auth_ctx` 반응 동작(메모리 주입·사용자 컨텍스트 블록)은 바꾸지 않는다 |
| F2 | 판정 지점 후보는 `ToolFactory` | 문서추출기·문서생성기·발표자료·이미지·엑셀 워커는 `ToolFactory`를 거치지 않는 전용 노드다 | `workflow_compiler.py:759-812` | 판정을 `compile` 첫머리 워커 목록 단계로 옮긴다. `ToolFactory`는 서버 단위 MCP 참조 필터만 맡는다 |
| F3 | 웹훅 실행 주체 = 채널 생성자 | 웹훅은 **에이전트 소유자** `auth_ctx`를 조립해 넘긴다 | `invoke_webhook_agent_use_case.py:150-155` | 현재 코드 그대로(에이전트 소유자) 사용 |
| F4 | (없음) | 승인 집행(`decide`·예약 집행)이 `compile`을 거치지 않고 `CompositeActionExecutor.execute`로 도구를 직접 실행한다 | `decide_use_case.py:248`, `execute_scheduler.py:96` | 집행 직전 요청자 권한 재확인 (사용자 결정) |
| F5 | (없음) | 레거시 v2 `/api/v2/agents` 라우터(`middleware_agent_router.py`)는 인증이 없고, 실행 시 `ToolFactory.create_async`로 도구를 직접 만든다 | `middleware_agent_router.py`, `run_middleware_agent_use_case.py:44` | 라우터 전체 admin 전용 (사용자 결정) |
| F6 | 카탈로그만 거르면 된다 | 빌더의 선택 칩이 카탈로그와 대조해 그려져(`LeftConfigPanel.tsx:190`), 이미 붙어 있으나 권한 없는 도구는 칩이 사라진다. 저장 payload는 `form.tools`라 도구 자체는 유지됨 | `utils/agentToolPayload.ts` | 에이전트 상세 응답에 붙은 도구의 이름·허용 여부를 optional 필드로 추가 (FR-13) |
| F7 (Check 추가) | 실행 경로는 `RunAgentUseCase` 호출자 8종이 전부 | 에이전트를 거치지 않는 **일반 채팅**(REST `/api/v1/chat`, WS `/ws/chat`)이 별도 UseCase 로 Tavily·내부 문서·등록 MCP 전부를 바인딩 — 판정 없음 | `general_chat/tools.py:103-109`, `general_chat/use_case.py:444` | `GeneralChatUseCase._permitted_tools` 로 바인딩 전 실행자 판정 (도구 id 는 tool-recommender 의 `DefaultToolIdResolver` 규칙 재사용), 생성 호출부 AST 계약 테스트 |
| F8 (Check 추가) | 레거시 경로는 `/api/v2/agents` 하나 | 자동 빌더 `/api/v3/agents/auto` 도 무인증으로 LLM 호출·레거시 에이전트 저장 | `auto_agent_builder_router.py` | 라우터 단위 admin 잠금 (v2 와 동일, 인증 계약 테스트에 포함) |

---

## 1. Overview

### 1.1 Design Goals

- 판정 규칙은 도메인 정책 한 곳, 허용 집합 조립은 Resolver 한 곳에만 둔다.
- 실행 필터는 그래프 컴파일 전 워커 목록 한 지점에서 수행해 전용 노드·카테고리 워커·서브에이전트를 같이 덮는다.
- 기존 API 계약은 optional 필드 추가만 한다. 기존 호출자는 인자를 바꾸지 않아도 동작한다.
- 배포 직후 동작 변화 0건: 현재 카탈로그 도구 전부를 기본 세트로 시드한다.

### 1.2 Design Principles

- **Fail-Closed**: 실행자를 특정할 수 없거나 사용자 조회가 실패하면 비관리자 기준 빈 허용 집합. 저장 검증에서 규칙 조회가 실패하면 저장을 막는다(`gated_worker_validation`의 "조회 실패 시 건너뜀"과 반대 — 보안 검사라서).
- **주체는 인자로만 흐른다**: `ToolFactory`·`WorkflowCompiler`는 싱글턴이므로 `bind_auth_ctx` 같은 가변 필드에 허용 집합을 싣지 않는다 (mcp-identity-header §1.1과 같은 원칙).
- **Additive 계약**: `compile(tool_access=None)`은 필터 없음(기존 동작). 대신 프로덕션 호출 지점이 반드시 값을 넘기는지 AST 계약 테스트로 고정한다.

---

## 2. Architecture Options

### 2.0 Architecture Comparison

| Criteria | A: 최소 변경 | B: 클린 | C: 실용 균형 |
|----------|:-:|:-:|:-:|
| **방식** | 도구 허용을 `TOOL:{id}` 권한 코드로 `permissions`에 저장, 부서 부여만 추가 | C + `AuthContext`에 허용 집합 포함, 모든 실행 경로가 `auth_ctx` 조립 | 도메인 정책 + Resolver(auth_ctx 또는 user_id) 공유, compile 첫머리 필터 |
| **신규 파일** | ~5 | ~18 | ~14 |
| **수정 파일** | ~8 | ~20 | ~12 |
| **복잡도** | Low | High | Medium |
| **유지보수성** | Low (도구 생성 시마다 권한 코드 행 필요) | High | High |
| **위험** | `auth_ctx` 없는 3경로 미차단 | 스케줄 등에 메모리·사용자 컨텍스트가 새로 주입되어 답변 변화 | 낮음 |
| **Recommendation** | — | — | **선택** |

**Selected**: Option C — **Rationale**: `auth_ctx`가 없는 경로를 기존 동작 변경 없이 덮고, 판정 위치가 정책 1·Resolver 1·필터 1로 모인다 (사용자 선택).

### 2.1 Component Diagram

```
                       ┌──────────────────────────────┐
                       │ domain/tool_access            │
                       │  ToolAccessPolicy (순수 판정) │
                       │  ToolAccessSet (frozen VO)    │
                       │  ToolIdNormalizer             │
                       │  Repository 포트              │
                       └──────────────┬───────────────┘
                                      │
                       ┌──────────────▼───────────────┐
                       │ application/tool_access       │
                       │  ToolAccessResolver           │◄── user_repo, dept_repo, grant_repo
                       │   .for_auth_ctx(ctx)          │
                       │   .for_user_id(user_id)       │
                       │   .for_user(User)             │
                       │  validate_tool_access (공용)  │
                       │  Admin*UseCase (조회/PUT x3)  │
                       └──┬──────┬──────┬──────┬──────┘
          ┌───────────────┘      │      │      └──────────────────┐
          ▼                      ▼      ▼                         ▼
 ListToolCatalogUseCase   Create/Update  RunAgentUseCase     CompositeActionExecutor
 (비관리자 필터)          /Fork UseCase  _prepare_graph /    (승인 집행 재확인)
                         (저장 검증,     _resume_graph
                          포크 제외,       │ tool_access
                          빌트인 제외)     ▼
                                     WorkflowCompiler.compile
                                      ① 워커 목록 필터(전용 노드 포함)
                                      ② 제외 안내 블록 prepend
                                      ③ sub_agent 재귀에 동일 tool_access 전달
                                      ④ wiki_list 동봉 판정
                                           │
                                           ▼
                                      ToolFactory.create_all_async
                                       (mcp_{srv} 서버 참조: 허용 도구만)
```

### 2.2 Data Flow

**실행 (채팅·웹훅·잡)**
```
auth_ctx → ToolAccessResolver.for_auth_ctx → ToolAccessSet
  → compile(tool_access=set, excluded_sink=[])
     → ToolAccessPolicy.partition(workers) → (허용 워커, 제외 워커)
     → 제외 워커는 그래프·supervisor 목록에서 제외 (failed_worker_ids와 같은 취급)
     → excluded_sink에 기록 → RunAgentResponse.excluded_tools / ANSWER_COMPLETED payload
```

**실행 (스케줄·승인 재개·RAGAS)**
```
user_id(request.user_id / approval.requested_by) → for_user_id → ToolAccessSet → 이후 동일
```

**저장**
```
Create/Update: 최종 워커 목록(빌트인 주입 후) − 기존 정의 워커 = 신규 도구
  → 신규 도구 중 불허 존재 → ToolAccessDeniedError(tool_ids) → 403
Fork: 원본 워커 중 불허 도구 제거 후 저장 → ForkAgentResponse.excluded_tools
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| ToolAccessResolver | UserRepositoryInterface, DepartmentRepositoryInterface, ToolAccessRepositoryInterface | 역할·소속 부서·허용 규칙 조회 |
| WorkflowCompiler | ToolAccessSet (인자) | 워커 필터 |
| ToolFactory | ToolAccessSet (인자, 서버 단위 MCP만) | 서버 도구 부분 허용 |
| CompositeActionExecutor | ToolAccessResolver (optional 주입) | 집행 직전 재확인 |

---

## 3. Data Model

### 3.1 Entity Definition

```python
# domain/tool_access/value_objects.py
@dataclass(frozen=True)
class ToolAccessSet:
    is_admin: bool
    allowed: frozenset[str]          # 카탈로그 표기 tool_id 집합

    @staticmethod
    def deny_all() -> "ToolAccessSet": ...   # Fail-Closed 기본값
    def allows(self, raw_tool_id: str) -> bool: ...          # 정규화 후 판정
    def allowed_mcp_tool_names(self, server_id: str) -> frozenset[str] | None:
        """서버 단위 참조용. admin이면 None(=전부)."""

@dataclass(frozen=True)
class ToolGrantSource:              # 관리자 조회 응답용
    kind: Literal["default", "department"]
    department_id: str | None = None
    department_name: str | None = None
```

### 3.2 도구 ID 정규화 (ToolIdNormalizer)

규칙 키는 항상 **카탈로그 표기**다. 판정 전 저장 표기를 카탈로그 표기로 바꾼다. 기존 `update_agent_use_case._catalog_tool_id`와 같은 규칙이며, 이 함수를 도메인으로 옮겨 단일화한다(기존 함수는 위임).

| 입력 (저장/요청 표기) | 카탈로그 표기 | 판정 |
|----------------------|--------------|------|
| `internal_document_search` | `internal:internal_document_search` | 집합 포함 여부 |
| `internal:excel_export` | 그대로 | 집합 포함 여부 |
| `mcp:{uuid}:{tool}` | 그대로 | 집합 포함 여부 |
| `mcp_{uuid}` (레거시 서버 단위) | 해당 없음 | 서버 도구 중 하나라도 허용이면 워커 유지, 바인딩 시 허용 도구만 (FR-12) |
| 빈 문자열·알 수 없는 형식 | — | 불허 |

### 3.3 Database Schema

마이그레이션 번호는 Do 시점 최신(현재 V081) 다음 번호를 쓴다. FK 참조 테이블과 같은 기본 CHARSET만 쓰고 COLLATE는 명시하지 않는다(위키 mysql-fk-collation). COMMENT에 콤마 금지.

```sql
-- V082__create_tool_access_tables.sql
CREATE TABLE tool_access_default (
    tool_id     VARCHAR(150) NOT NULL PRIMARY KEY,
    granted_by  BIGINT       NULL,
    granted_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_tad_tool FOREIGN KEY (tool_id) REFERENCES tool_catalog(tool_id) ON DELETE CASCADE,
    CONSTRAINT fk_tad_granter FOREIGN KEY (granted_by) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB;  -- CHARSET/COLLATE 생략 (위키 mysql-fk-collation)

CREATE TABLE tool_access_department (
    tool_id       VARCHAR(150) NOT NULL,
    department_id VARCHAR(36)  NOT NULL,
    granted_by    BIGINT       NULL,
    granted_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tool_id, department_id),
    INDEX ix_tadept_dept (department_id),
    CONSTRAINT fk_tadept_tool FOREIGN KEY (tool_id) REFERENCES tool_catalog(tool_id) ON DELETE CASCADE,
    CONSTRAINT fk_tadept_dept FOREIGN KEY (department_id) REFERENCES departments(id) ON DELETE CASCADE,
    CONSTRAINT fk_tadept_granter FOREIGN KEY (granted_by) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB;  -- CHARSET/COLLATE 생략 (위키 mysql-fk-collation)

CREATE TABLE tool_access_user (
    tool_id     VARCHAR(150) NOT NULL,
    user_id     BIGINT       NOT NULL,
    granted_by  BIGINT       NULL,
    granted_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tool_id, user_id),
    INDEX ix_tau_user (user_id),
    CONSTRAINT fk_tau_tool FOREIGN KEY (tool_id) REFERENCES tool_catalog(tool_id) ON DELETE CASCADE,
    CONSTRAINT fk_tau_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_tau_granter FOREIGN KEY (granted_by) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB;  -- CHARSET/COLLATE 생략 (위키 mysql-fk-collation)

-- V083__seed_tool_access_default.sql  (FR-03: 배포 직후 동작 변화 0)
INSERT INTO tool_access_default (tool_id, granted_by)
SELECT tool_id, NULL FROM tool_catalog;
```

**선택 근거 — 왜 테이블 3개인가**
- 대상별 진짜 FK를 걸 수 있어 FR-17(도구·부서·사용자 삭제 시 규칙 정리)이 CASCADE로 성립한다. 다형 테이블(`subject_type`, `subject_id`)은 FK를 걸 수 없다.
- `tool_catalog`에 컬럼을 추가하지 않는다. ORM 매핑 컬럼 추가는 마이그레이션 미적용 시 카탈로그 조회 자체를 깨뜨리고(위키 migration-deploy-deps), sync upsert SET 절 보존 규칙도 건드려야 한다. 별도 테이블이면 sync 코드 변경이 0이다.
- 신규 sync 도구는 어떤 테이블에도 행이 없으므로 자동으로 기본 차단(FR-03).
- `is_active=0`으로 비활성화된 도구의 규칙은 남는다. 재활성화 시 권한 복원.

### 3.4 Entity Relationships

```
tool_catalog (tool_id UQ) 1 ──── 0..1 tool_access_default
                          1 ──── N    tool_access_department N ──── 1 departments
                          1 ──── N    tool_access_user       N ──── 1 users
mcp_server_registry 1 ── N tool_catalog (CASCADE) → 규칙도 연쇄 삭제
```

### 3.5 판정 정책 (ToolAccessPolicy)

```
allowed(subject, tool_id):
  subject.role == "admin"                       → True
  subject is anonymous / unresolved             → False
  norm = normalize(tool_id); norm is None       → False
  norm ∈ default ∪ dept_grants(subject.depts) ∪ user_grants(subject) → True
  else                                          → False
```

Resolver 조회 비용: `auth_ctx`가 있으면 쿼리 1회(세 테이블 UNION, 부서는 `auth_ctx.department_ids` 사용). `user_id`만 있으면 사용자·부서·규칙 3회. 실행당 depth 0에서 1회만 조회하고 서브에이전트 재귀에는 같은 `ToolAccessSet`을 넘긴다.

---

## 4. API Specification

### 4.1 Endpoint List

| Method | Path | Description | Auth | 변경 |
|--------|------|-------------|------|------|
| GET | `/api/v1/admin/tool-access/default` | 기본 세트 조회 | admin | 신규 |
| PUT | `/api/v1/admin/tool-access/default` | 기본 세트 전체 교체 | admin | 신규 |
| GET | `/api/v1/admin/tool-access/departments/{department_id}` | 부서 허용 조회 | admin | 신규 |
| PUT | `/api/v1/admin/tool-access/departments/{department_id}` | 부서 허용 전체 교체 | admin | 신규 |
| GET | `/api/v1/admin/tool-access/users/{user_id}` | 사용자 직접 허용 + 상속분 | admin | 신규 |
| PUT | `/api/v1/admin/tool-access/users/{user_id}` | 사용자 직접 허용 전체 교체 | admin | 신규 |
| GET | `/api/v1/tool-catalog` | 비관리자: 허용 도구만 | login | 동작 변경 (스키마 동일) |
| GET | `/api/v1/agents/{id}` | `tool_access[]` optional 추가 | login | additive |
| POST/PUT | 에이전트 생성·수정 | 신규 불허 도구 403 | login | 오류 경로 추가 |
| POST | 포크 | `excluded_tools[]` optional 추가 | login | additive |
| POST/WS | 실행 | `excluded_tools[]` optional 추가 | login | additive |
| * | `/api/v1/mcp-registry/*` | 전부 admin (조회 포함, v0.2) | 변경 | 라우터 단위 인증 추가 |
| * | `/api/v2/agents/*` (레거시 v2 미들웨어 에이전트) | 전부 admin | 변경 | 라우터 단위 인증 추가 |

### 4.2 Detailed Specification

#### `GET /api/v1/admin/tool-access/default`
```json
{ "tool_ids": ["internal:internal_document_search", "mcp:7f3c...:search"] }
```

#### `PUT /api/v1/admin/tool-access/default` · `.../departments/{id}` · `.../users/{id}`
**Request**: `{ "tool_ids": ["internal:excel_export", "..."] }`
- 카탈로그 표기만 허용. 저장 표기(`excel_export`)가 오면 정규화해 저장한다.
- 중복 제거 후 전체 교체(트랜잭션 내 DELETE + INSERT). `granted_by` = 요청 관리자.

**Response 200**: GET과 같은 형태.
**Errors**: `400 UNKNOWN_TOOL_IDS` (카탈로그에 없는 id, `detail.tool_ids` 포함), `404` (부서·사용자 없음), `401`/`403`.

#### `GET /api/v1/admin/tool-access/departments/{department_id}`
```json
{
  "department_id": "d-1", "department_name": "여신부",
  "tool_ids": ["internal:python_code_executor"],
  "default_tool_ids": ["internal:internal_document_search"]
}
```

#### `GET /api/v1/admin/tool-access/users/{user_id}`
```json
{
  "user_id": 12, "is_admin": false,
  "tool_ids": ["mcp:7f3c...:write_ticket"],
  "inherited": [
    { "tool_id": "internal:internal_document_search", "sources": [{ "kind": "default" }] },
    { "tool_id": "internal:python_code_executor",
      "sources": [{ "kind": "department", "department_id": "d-1", "department_name": "여신부" }] }
  ]
}
```
`is_admin: true`면 화면은 "관리자는 모든 도구 사용 가능" 안내만 표시하고 편집을 막는다.

#### 에이전트 저장 403
```json
{ "detail": { "code": "TOOL_ACCESS_DENIED",
              "message": "권한이 없는 도구가 포함되어 있습니다",
              "tool_ids": ["mcp:7f3c...:write_ticket"] } }
```
`ToolAccessDeniedError(PermissionError)`에 `tool_ids`를 싣고, 라우터는 기존 `except PermissionError`보다 **먼저** 이 예외를 잡는다.

#### `GetAgentResponse.tool_access` (additive)
```json
"tool_access": [
  { "tool_id": "internal:excel_export", "name": "Excel 파일 생성", "permitted": true },
  { "tool_id": "mcp:7f3c...:write_ticket", "name": "write_ticket", "permitted": false }
]
```
도구 워커만 대상. 이름은 카탈로그 → 레지스트리 → id 끝 조각 순으로 정한다.

#### 실행 응답 (additive)
- `RunAgentResponse.excluded_tools: list[ExcludedTool] = []`
- WS `ANSWER_COMPLETED` payload에 `excluded_tools` (비어 있으면 키 생략 가능, 프론트는 없음=빈 배열)
- `ForkAgentResponse.excluded_tools: list[ExcludedTool] = []`

```json
{ "tool_id": "mcp:7f3c...:write_ticket", "name": "write_ticket", "reason": "no_permission" }
```

---

## 5. UI/UX Design

### 5.1 Screen Layout — `/admin/tool-access` (조직 관리 그룹)

```
┌ 도구 권한 ─────────────────────────────────────────────────┐
│ [기본 허용 도구] [부서별] [사용자별]                        │
├────────────────────────────────────────────────────────────┤
│ 부서: [여신부 ▼]                         [저장]            │
│ ─ 내부 도구 ───────────────────────────────────────────── │
│ ☑ 내부 문서 검색        기본         (잠금)                │
│ ☑ Python 코드 실행                                         │
│ ☐ 발표자료생성기                                           │
│ ─ MCP: 사내 티켓 시스템 ─────────────── [전체 선택][해제] │
│ ☑ search_ticket         기본         (잠금)                │
│ ☐ write_ticket          승인 필요                          │
│ ☐ close_ticket          미지정(차단)                       │
└────────────────────────────────────────────────────────────┘
사용자별 탭: 부서 상속 도구는 "부서: 여신부" 배지 + 잠금
기본 허용 도구 탭: 빌트인인데 기본 세트 아님 → "빌트인·비기본" 경고 배지 (FR-15)
```

### 5.2 User Flow

```
관리자: 조직 관리 > 도구 권한 > 부서별 > 여신부 선택 > 도구 체크 > 저장
  → 여신부 사용자: 빌더 도구 선택 모달에 표시 → 에이전트 저장 가능
관리자: 체크 해제 > 저장
  → 여신부 사용자: 기존 에이전트 실행 시 해당 도구 제외 + 답변 하단 안내
```

### 5.3 Component List

| Component | Location | Responsibility |
|-----------|----------|----------------|
| `AdminToolAccessPage` | `src/pages/AdminToolAccessPage/index.tsx` | 탭 3개 + 대상 선택 |
| `ToolAccessChecklist` | `src/components/admin/tool-access/ToolAccessChecklist.tsx` | 내부/MCP 서버별 그룹 체크리스트, 잠금·배지 |
| `useToolAccess*` | `src/hooks/useToolAccess.ts` | 조회/PUT 쿼리·뮤테이션 |
| `toolAccessService` | `src/services/toolAccessService.ts` | API 호출 |
| 타입·상수 | `src/types/toolAccess.ts` | 응답 타입, 배지 라벨 `as const` |
| 빌더 칩 | `LeftConfigPanel.tsx` | 카탈로그에 없는 붙은 도구는 `tool_access`로 칩 표시 + "권한 없음" |
| 채팅 안내 | 답변 메시지 하단 | `excluded_tools` 있으면 "권한이 없어 사용하지 않은 도구: …" |
| 포크 안내 | 포크 결과 토스트 | `excluded_tools` 있으면 제외 목록 |

### 5.4 Page UI Checklist

#### AdminToolAccessPage
- [ ] Tab: 기본 허용 도구 / 부서별 / 사용자별 (3개, `adminNav.ts`에 "도구 권한" 항목, 조직 관리 그룹)
- [ ] Select: 부서 선택 드롭다운 (부서별 탭), 사용자 검색 선택 (사용자별 탭)
- [ ] Group: 내부 도구 그룹, MCP 서버별 그룹(서버명 헤더)
- [ ] Button: MCP 서버 그룹별 "전체 선택" / "전체 해제" (잠금 항목 제외)
- [ ] Checkbox: 도구별 체크, 잠금 항목은 disabled + 체크
- [ ] Badge: "기본" (기본 세트), "부서: {이름}" (사용자 탭 상속), "승인 필요", "미지정(차단)", "빌트인·비기본"
- [ ] Banner: 대상 사용자가 admin이면 "관리자는 모든 도구 사용 가능" + 편집 비활성
- [ ] Button: 저장 (`LoadingButton`, 변경 없으면 disabled), 저장 성공 토스트
- [ ] Error: 400 UNKNOWN_TOOL_IDS 메시지 표시

#### AgentBuilderPage (LeftConfigPanel / ToolPickerModal)
- [ ] ToolPickerModal: 필터된 카탈로그만 표시 (변경 없음, 서버가 거름)
- [ ] Chip: 붙어 있으나 카탈로그에 없는 도구도 `tool_access` 이름으로 표시 + "권한 없음" 배지
- [ ] 저장 403 TOOL_ACCESS_DENIED: 해당 도구 이름 목록과 함께 오류 표시

#### ChatPage
- [ ] 답변 하단 안내: `excluded_tools` 1개 이상일 때만 표시, 도구 이름 나열

---

## 6. Error Handling

### 6.1 Error Code Definition

| Code | HTTP | Cause | Handling |
|------|------|-------|----------|
| `TOOL_ACCESS_DENIED` | 403 | 저장 시 신규 도구 불허 | 빌더 오류 표시 |
| `UNKNOWN_TOOL_IDS` | 400 | 관리자 PUT에 카탈로그에 없는 id | 관리자 화면 오류 표시 |
| (없음) | 404 | 부서·사용자 없음 | 관리자 화면 오류 |
| (기존) | 401/403 | 인증·관리자 아님 | 기존 인터셉터 (`ApiError`) |
| 승인 집행 거부 | — | 집행 직전 재확인 실패 | `ExecutionResult(ok=False, kind="blocked", "도구 권한 없음")` → 기존 failed 전이 |
| 실행 중 제외 | — | 실행자 불허 | 오류 아님. 워커 제외 + `excluded_tools` |

### 6.2 Resolver 실패

| 상황 | 동작 |
|------|------|
| 실행 시 규칙 조회 예외 | `ToolAccessSet.deny_all()` + error 로그 (Fail-Closed, 에이전트는 도구 없이 실행) |
| 저장 시 규칙 조회 예외 | 저장 실패 (500) — 권한 미확인 상태로 저장하지 않음 |
| 카탈로그 조회 시 예외 | 500 (기존과 동일 계열) |
| user_id가 숫자가 아니거나 사용자 없음 | `deny_all()` |

---

## 7. Security Considerations

- [ ] 서버 측 판정이 화면 필터와 독립 (API 직접 호출로 우회 불가)
- [ ] 모든 실행 경로(REST·SSE·WS·웹훅·잡·스케줄·승인 재개·RAGAS) + 서브에이전트 + 승인 집행에서 판정
- [ ] `compile` 프로덕션 호출 지점 2곳(`_prepare_graph`, `_resume_graph`)이 `tool_access`를 넘기는지 AST 계약 테스트
- [ ] MCP 레지스트리 무인증 401, 비관리자 쓰기 403
- [ ] 레거시 `/api/v2/agents` 비관리자 403
- [ ] 관리자 권한 API 비관리자 403
- [ ] LLM 노출: 제외 안내 블록에는 도구 **이름**만 싣고 tool_id·서버 id는 싣지 않는다

---

## 8. Test Plan

### 8.1 Test Scope

| Type | Target | Tool | Phase |
|------|--------|------|-------|
| Unit | ToolAccessPolicy, ToolAccessSet, ToolIdNormalizer | pytest | Do |
| Unit | Resolver (auth_ctx/user_id/실패) | pytest + fake repo | Do |
| Integration | Repository (CASCADE 포함) | pytest + DB | Do |
| API | 관리자 API, 카탈로그 필터, 저장 403, MCP·레거시 인증 | pytest TestClient | Do |
| Compile | 실제 컴파일 그래프에서 워커 제외 확인 (AsyncMock 단독 금지) | pytest | Do |
| Contract | `compile(...)` 호출 지점 AST 검사 | pytest | Do |
| Frontend | 관리자 페이지, 빌더 칩, 채팅 안내 | Vitest + RTL + MSW | Do |

### 8.2 L1: API Test Scenarios

| # | Endpoint | Test | Expected |
|---|----------|------|----------|
| 1 | GET /admin/tool-access/default | 비관리자 | 403 |
| 2 | PUT /admin/tool-access/departments/{id} | 정상 → GET | 교체된 목록 |
| 3 | PUT ... | 없는 tool_id | 400 UNKNOWN_TOOL_IDS |
| 4 | PUT ... | 저장 표기 `excel_export` | `internal:excel_export`로 저장 |
| 5 | GET /admin/tool-access/users/{id} | 부서·기본 상속 | `inherited.sources` 정확 |
| 6 | GET /tool-catalog | 비관리자, 기본 세트 1개만 | 1개 |
| 7 | GET /tool-catalog | 다중 부서 중 한 부서 허용 | 포함 |
| 8 | GET /tool-catalog | 관리자 | 전체 |
| 9 | POST 에이전트 | 불허 신규 도구 | 403 TOOL_ACCESS_DENIED + tool_ids |
| 10 | PUT 에이전트 | 기존 불허 도구 유지 + 프롬프트만 수정 | 200 |
| 11 | PUT 에이전트 | 불허 도구 추가 | 403 |
| 12 | POST 포크 | 원본에 불허 도구 | 200, 복제본에서 제외, excluded_tools |
| 13 | POST 에이전트 | 빌트인이 불허 | 주입되지 않음 |
| 14 | /mcp-registry 전 엔드포인트 | 무인증 / 비관리자 | 401 / 403 |
| 15 | /mcp-registry GET | 관리자 | 200 |
| 16 | /api/v2/agents/{id}/run | 비관리자 | 403 |

### 8.3 실행 경로 시나리오 (Compile 레벨)

| # | 경로 | 주체 | Expected |
|---|------|------|----------|
| R1 | 채팅 REST/WS | auth_ctx | 불허 워커 그래프 미포함, excluded_tools 반환 |
| R2 | 웹훅 | 에이전트 소유자 auth_ctx | 소유자 기준 |
| R3 | 백그라운드 잡 | 등록자 auth_ctx | 등록자 기준 |
| R4 | 스케줄 | `schedule.user_id` | 등록자 기준 (auth_ctx 없음) |
| R5 | 승인 재개 | `approval.requested_by` | 요청자 기준 |
| R6 | RAGAS 에이전트 평가 | 평가 실행자 user_id | 실행자 기준 |
| R7 | 서브에이전트 워커 | 상위 실행자 | 하위 그래프에도 적용 |
| R8 | 전용 노드(document_generator 등) | — | 불허 시 노드 미생성 |
| R9 | `mcp_{srv}` 레거시 참조, 일부 허용 | — | 허용 도구만 바인딩 |
| R10 | `mcp_{srv}`, 전부 불허 | — | 워커 제외 |
| R11 | wiki_read 허용·wiki_list 불허 | — | wiki_read 단독 |
| R12 | 승인 대기 중 권한 회수 후 승인 | 요청자 | 집행 거부(blocked), failed 전이 |
| R13 | 시드 직후 기존 에이전트 | 일반 사용자 | 바인딩 도구 목록 시드 전과 동일 |
| R14 | user 조회 실패 | — | 도구 0개로 실행, 오류 로그 |

### 8.4 L2: UI Action Test Scenarios

| # | Page | Action | Expected |
|---|------|--------|----------|
| 1 | AdminToolAccess | 부서 선택 | 체크리스트 로드, 기본 세트 잠금 |
| 2 | AdminToolAccess | 체크 후 저장 | PUT 요청 body, 성공 토스트 |
| 3 | AdminToolAccess | MCP 서버 전체 선택 | 잠금 제외 전부 체크 |
| 4 | AdminToolAccess | admin 사용자 선택 | 안내 배너, 편집 불가 |
| 5 | AgentBuilder | 카탈로그에 없는 붙은 도구 | 칩 + "권한 없음" |
| 6 | AgentBuilder | 저장 403 | 도구 이름 오류 표시 |
| 7 | Chat | excluded_tools 수신 | 하단 안내 |

### 8.5 L3: E2E (수동, `docs/wiki/ops/e2e-carryover-checklist.md`에 이월 가능)

1. 관리자: 여신부에 도구 X 허용 → 여신부 사용자: 빌더에서 X 선택·저장 → 실행 시 X 호출
2. 관리자: 허용 해제 → 같은 사용자 실행 → 답변 하단 제외 안내, X 미호출
3. MCP 동기화로 새 도구 → 비관리자 카탈로그에 미노출

### 8.6 Seed Data Requirements

| Entity | Minimum | Key Fields |
|--------|:-:|------------|
| departments | 2 | 여신부, 인사부 |
| users | 3 | admin 1, 여신부 user 1, 두 부서 겸직 user 1 |
| tool_catalog | 4 | 내부 2, MCP 2(같은 서버) |
| tool_access_* | 기본 1, 부서 1, 사용자 1 | |

---

## 9. Clean Architecture

### 9.1 Layer Assignment

| Component | Layer | Location |
|-----------|-------|----------|
| ToolAccessPolicy, ToolAccessSet, ToolIdNormalizer, ToolGrantSource, ToolAccessDeniedError | Domain | `idt/src/domain/tool_access/` |
| ToolAccessRepositoryInterface | Domain | `idt/src/domain/tool_access/interfaces.py` |
| ToolAccessResolver, validate_tool_access, Admin*UseCase, schemas | Application | `idt/src/application/tool_access/` |
| SQLAlchemy 모델·Repository | Infrastructure | `idt/src/infrastructure/tool_access/` |
| admin_tool_access_router | Interfaces/API | `idt/src/api/routes/admin_tool_access_router.py` |
| DI 배선 | Composition | `idt/src/api/main.py` (DI 단일 집중) |

### 9.2 Dependency Rules

- Domain은 외부 의존 없음. 정규화는 기존 `domain/tool_catalog/mcp_tool_id.parse_mcp_tool_id`만 사용(같은 레이어).
- `WorkflowCompiler`(application)는 Resolver를 알지 않는다 — 이미 만들어진 `ToolAccessSet`만 인자로 받는다.
- `CompositeActionExecutor`(infrastructure)는 Resolver를 optional 생성자 인자로 받는다(미주입 시 기존 동작, main.py에서 주입 + 배선 계약 테스트).

---

## 10. Coding Convention Reference

| Item | Convention Applied |
|------|-------------------|
| 백엔드 | `idt/CLAUDE.md`, `idt/docs/rules/` — UseCase `execute(..., request_id)`, LOG-001 구조화 로그 |
| 계약 | additive (optional 필드·키워드 인자 마지막 + 기본값) |
| 테스트 | TDD, 회귀는 정렬된 FAILED diff, `uv run python -m pytest` |
| 프론트 상수 | 컴포넌트 파일에서 런타임 상수 export 금지 → `src/types/toolAccess.ts` |
| 프론트 에러 | `ApiError(message,status,code)` — `err.response` 사용 금지 |
| 뮤테이션 버튼 | `LoadingButton` |
| 관리자 메뉴 | `adminNav.ts` 단일 소스, 탭 개수 하드코딩 단언 금지 |
| 주석 | `# Design Ref: tool-access-control §N — 이유` |

---

## 11. Implementation Guide

### 11.1 File Structure

```
idt/
  db/migration/V082__create_tool_access_tables.sql           (신규)
  db/migration/V083__seed_tool_access_default.sql            (신규)
  src/domain/tool_access/{__init__,policy,value_objects,interfaces,exceptions}.py   (신규)
  src/application/tool_access/{resolver,validation,admin_use_cases,schemas}.py      (신규)
  src/infrastructure/tool_access/{models,repository}.py      (신규)
  src/api/routes/admin_tool_access_router.py                 (신규)
  src/api/routes/mcp_registry_router.py                      (수정: 인증)
  src/api/routes/middleware_agent_router.py                  (수정: admin)
  src/api/routes/tool_catalog_router.py                      (수정: user 전달)
  src/api/routes/agent_builder_router.py                     (수정: 403 매핑)
  src/application/tool_catalog/list_tool_catalog_use_case.py (수정: 필터)
  src/application/agent_builder/create_agent_use_case.py     (수정: 검증·빌트인)
  src/application/agent_builder/update_agent_use_case.py     (수정: 신규분 검증, _catalog_tool_id 위임)
  src/application/agent_builder/fork_agent_use_case.py       (수정: 제외 복제)
  src/application/agent_builder/get_agent_use_case.py        (수정: tool_access)
  src/application/agent_builder/schemas.py                   (수정: optional 필드)
  src/application/agent_builder/run_agent_use_case.py        (수정: resolve·전달·응답)
  src/application/agent_builder/workflow_compiler.py         (수정: 필터·안내·재귀·wiki_list)
  src/infrastructure/agent_builder/tool_factory.py           (수정: 서버 단위 필터)
  src/infrastructure/approval/composite_executor.py          (수정: 재확인)
  src/api/main.py                                            (수정: DI·라우터 등록)
idt_front/
  src/types/toolAccess.ts, src/services/toolAccessService.ts, src/hooks/useToolAccess.ts (신규)
  src/pages/AdminToolAccessPage/index.tsx, src/components/admin/tool-access/ToolAccessChecklist.tsx (신규)
  src/constants/api.ts, src/constants/adminNav.ts, src/App.tsx (수정)
  src/types/agentBuilder.ts, LeftConfigPanel.tsx, 채팅 메시지 컴포넌트, 포크 토스트 (수정)
```

### 11.2 Implementation Order

1. [ ] M1 도메인 정책·VO·정규화 → Resolver → 마이그레이션·Repository
2. [ ] M2 관리자 API + MCP 레지스트리·레거시 라우터 인증
3. [ ] M3 카탈로그 필터 → 저장 검증(공용 모듈) → 빌트인 제외 → 포크 → 상세 `tool_access`
4. [ ] M4 compile 필터·안내·재귀 → RunAgentUseCase 전달(2곳) + 응답 → ToolFactory 서버 단위 → 승인 집행 재확인 → AST 계약 테스트
5. [ ] M5 관리자 화면
6. [ ] M6 빌더 칩·403 표시·채팅 안내·포크 안내, `/api-contract-sync`

### 11.3 Session Guide

#### Module Map

| Module | Scope Key | Description | Estimated Turns |
|--------|-----------|-------------|:---------------:|
| 판정 기반 | `module-1` | domain/tool_access, Resolver, V082/V083, Repository + 단위·통합 테스트 | 30-40 |
| 관리 API·인증 | `module-2` | admin_tool_access_router + UseCase, MCP 레지스트리·레거시 라우터 인증 | 25-35 |
| 목록·저장·포크 | `module-3` | 카탈로그 필터, 저장 검증, 빌트인, 포크, 상세 tool_access | 30-40 |
| 실행 필터 | `module-4` | compile 필터, RunAgentUseCase 2곳, ToolFactory, 승인 집행, R1~R14, AST 계약 | 40-50 |
| 관리자 화면 | `module-5` | AdminToolAccessPage + 훅·서비스·타입 + 테스트 | 35-45 |
| 빌더·채팅 표시 | `module-6` | 칩·403·안내, 타입 동기화 | 20-30 |

#### Recommended Session Plan

| Session | Phase | Scope | Turns |
|---------|-------|-------|:-----:|
| Session 1 | Plan + Design | 전체 | 완료 |
| Session 2 | Do | `--scope module-1,module-2` | 55-75 |
| Session 3 | Do | `--scope module-3` | 30-40 |
| Session 4 | Do | `--scope module-4` | 40-50 |
| Session 5 | Do | `--scope module-5,module-6` | 55-75 |
| Session 6 | Check + Report | 전체 | 30-40 |

작업 공간: worktree `wt/tool-access-control`, 브랜치 `feature/tool-access-control`.

---

## 12. Plan FR 추적표

| Plan FR | Design 위치 | 테스트 |
|---------|------------|--------|
| FR-01 규칙 저장 | §3.3 | 통합 |
| FR-02 판정 정책 | §3.5, §1.2 | 단위 |
| FR-03 시드·신규 차단 | §3.3 V083 | R13, L1-6 |
| FR-04 관리자 API | §4.2 | L1-1~5 |
| FR-05 카탈로그 필터 | §4.1 | L1-6~8 |
| FR-06 저장 검증 | §2.2, §4.2 403 | L1-9~11 |
| FR-07 빌트인 | §2.2 | L1-13 |
| FR-08 포크 | §2.2, §4.2 | L1-12 |
| FR-09 실행 필터 | §2.1 ①③ | R1, R7, R8 |
| FR-10 실행 주체 | §0 F1·F3, §8.3 | R2~R6, R14 |
| FR-11 제외 안내 | §2.1 ②, §4.2 실행 응답 | R1, L2-7 |
| FR-12 서버 단위 MCP | §3.2, §2.1 | R9, R10 |
| FR-13 빌더 표시 | §0 F6, §4.2 tool_access | L2-5 |
| FR-14 관리자 화면 | §5 | L2-1~4 |
| FR-15 상태 배지 | §5.4 | L2-1 |
| FR-16 MCP 인증 | §4.1 | L1-14, 15 |
| FR-17 삭제 정리 | §3.3 CASCADE | 통합 |
| (추가) 승인 집행 재확인 | §0 F4 | R12 |
| (추가) 레거시 라우터 잠금 | §0 F5 | L1-16 |
| (추가) wiki_list 동봉 판정 | §2.1 ④ | R11 |
| (추가, Do module-3) 추천 후보 필터 — 파이프라인 셀렉터 후보·자연어 컴포저 후보 | `agent_create_pipeline/use_case.py::_allowed_candidates`, `compose_agent_use_case.py::_collect_candidates` | `tests/application/tool_access/test_candidate_filters.py` |

자동 포크(원본 삭제 시 구독자용, `auto_fork_service.py`)는 도구를 그대로 복제한다. 구독자가 직접 고른 행동이 아니고, 실행 시 필터가 막기 때문이다.

**Do module-3에서 정한 세부 규칙**
- 레거시 서버 단위 참조(`mcp_{srv}`)는 저장·포크·후보 판정에서 "그 서버 도구 중 하나라도 허용"이면 통과한다(`ToolAccessSet.allows_reference`). 서버의 나머지 도구는 실행 시점 필터(module-4)가 거른다.
- 수정 경로는 빌트인을 매번 다시 주입하므로 빌트인도 "기존에 있던 것은 유지, 새로 들어오며 불허면 제외" 규칙을 따른다.
- 포크에서 도구를 뺐으면 프롬프트의 `## Tool Guidelines` 블록을 남은 도구 기준으로 다시 만든다(`update_agent_use_case.sync_tool_guidelines` 공개 함수화).
- 상세 조회의 `tool_access`는 표시용이라 권한 조회 실패 시 `None`으로 강하한다(상세 화면 전체를 막지 않음). 저장 경로의 조회 실패는 저장을 막는다(§6.2 그대로).
- 파이프라인 후보 조회 실패는 후보 리더 포트 계약(예외 금지 → 빈 후보)과 같게 빈 후보로 강하한다. 카탈로그·컴포저는 Resolver가 주입됐는데 조회자를 모르면 빈 결과(Fail-Closed).
- `ExcludedToolInfo`·`ToolAccessInfo`는 `application/tool_access/schemas.py`에 두고 `agent_builder/schemas.py`가 가져다 쓴다.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-11-03 | 초안 — 설계안 C 선택, 코드 대조 사실 F1~F6 반영(auth_ctx 없는 3경로, 전용 노드, 웹훅 주체, 승인 집행, 레거시 라우터, 빌더 칩) | 배상규 |
| 0.2 | 2026-11-04 | Do module-1·2 반영 — MCP 레지스트리 조회도 admin 전용, 레거시 라우터 실제 경로 `/api/v2/agents`, 관리자 PUT은 활성 카탈로그 범위 안에서만 교체(비활성 도구 규칙 보존) | 배상규 |
| 0.3 | 2026-11-04 | Do module-3 반영 — 추천 후보(파이프라인·컴포저) 필터 추가, 서버 단위 참조·빌트인 재주입·포크 프롬프트·상세 강하 세부 규칙 (§12) | 배상규 |
| 0.4 | 2026-11-04 | Do module-4 반영 — compile 첫머리 워커 필터·제외 안내 블록(supervisor·final_answer 공통)·서브에이전트 전달, `available_workers`도 제외 반영, 서버 단위 MCP `allowed_tool_names`, 실행 8경로 단일 주입(`_build_run_agent_uc`), 승인 집행기 `SessionScopedToolAccessChecker`(domain 포트 `ToolAccessCheckerPort`), FR-11 실행 기록은 구조화 로그(run_id)로 한정 | 배상규 |
| 0.5 | 2026-11-04 | Do module-5·6 반영 — 기본 세트 탭의 미허용 표시는 "미지정(차단)" 대신 "기본 세트 아님"(부서 허용이 있을 수 있어 "차단"은 부정확), MCP 서버 이름은 카탈로그에 없어 MCP 레지스트리 목록으로 매핑, `ApiError.detail` optional 추가(TOOL_ACCESS_DENIED tool_ids 표시), 빌더 칩은 tool_access 가 불허라고 답한 도구만(비활성 도구 등은 기존 동작), 채팅 안내는 실시간 답변만(히스토리 재조회 시 없음). 미반영: 빌더 테스트 패널(TestChatView)은 제외 안내를 그리지 않음 | 배상규 |
| 0.6 | 2026-11-04 | Check(Act-1) 반영 — §0 F7(일반 채팅 경로 판정 추가)·F8(자동 빌더 admin 잠금), 강등 답변 excluded_tools, `_catalog_tool_id` 도메인 위임, §3.3 DDL 예시 CHARSET 생략으로 정정. 표시 이름 카탈로그 우선(G-05)은 MCP·내부 모두 카탈로그 이름 = 도구명이라 차이 없음으로 종결, 승인 재개 안내(G-07)는 저장만 되는 경로라 보류 | 배상규 |
