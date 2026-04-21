# AGENT-SHARE-001: 사용자 커스텀 에이전트 공유 빌더

> 상태: Plan
> Task ID: AGENT-SHARE-001
> 의존성: AGENT-004, AGENT-005, AGENT-006, LLM-MODEL-REG-001, AUTH-001, MCP-REG-001, LOG-001
> 작성일: 2026-04-20
> 우선순위: High

---

## 1. 문제 정의 (Problem Statement)

현재 AGENT-004/005/006로 사용자는 자신만의 에이전트를 생성할 수 있지만 다음이 불가능하다.

1. **공유 불가**: 생성한 에이전트는 `user_id`로 격리되어 다른 사용자가 사용할 수 없다. 부서 내 전문가가 만든 우수한 에이전트를 조직 전체가 활용할 수 없다.
2. **Temperature 설정 불가**: LLM의 창의성/결정성을 조절하는 `temperature` 파라미터가 코드 기본값(0.0~0.3)으로 고정되어 있다. 창의적 글쓰기 vs 금융 질의 같은 상이한 유스케이스에 대응하지 못한다.
3. **도구 목록이 코드에 하드코딩**: `TOOL_REGISTRY`(내부 4종)는 Python 모듈에, 외부 MCP 서버는 DB에 분리 저장되어 있다. UI에서 "체크박스로 도구 선택"을 구현하려면 두 소스를 별도 호출 후 클라이언트에서 병합해야 한다.
4. **MCP 도구 메타 부족**: `mcp_server_registry` 테이블은 서버 단위 메타만 가지며, 개별 도구의 이름/설명이 없어 사용자가 "이 MCP에 어떤 도구가 있는지" 알 수 없다.
5. **부서 개념 부재**: `users` 테이블에 부서 정보가 없어 "부서 내부 공개" 수준의 중간 공유가 불가능하다.

---

## 2. 목표 (Goal)

1. `agent_definition`에 **visibility**, **temperature**, **department_id** 컬럼을 추가하여 공유 가능한 커스텀 에이전트를 만든다.
2. `departments` + `user_departments` 정규화 테이블을 신설하고, users의 department 소속 관리 API를 제공한다.
3. 내부 도구(`TOOL_REGISTRY`)와 외부 MCP 도구를 **단일 통합 테이블**로 DB화하여 체크박스 UI를 한 번의 API로 렌더링 가능하게 한다.
4. 가시성(private/department/public) 기반 접근 제어(실행/조회는 접근 가능, 편집/삭제는 소유자 or admin)를 구현한다.
5. AGENT-004 계열 Create/Run UseCase가 새 필드를 읽고 쓰도록 확장한다.

---

## 3. Non-Goals

- 에이전트 **Fork(복제)** 기능 (이번 iteration에서는 제외, 실행만 공유)
- 에이전트 사용 통계/랭킹/즐겨찾기
- 버전 관리(이력 스냅샷)
- AGENT-005(Middleware), AGENT-006(Auto)의 별도 공유 UI (동일 테이블 확장으로 자동 적용)

---

## 4. 핵심 유스케이스

| # | 액터 | 시나리오 | 결과 |
|---|------|----------|------|
| UC-1 | 일반 사용자 | 에이전트 생성 시 visibility=`private` | 본인만 조회/실행 |
| UC-2 | 부서원 | visibility=`department`, department_id=기획팀 | 기획팀 소속 사용자 전체가 조회/실행 |
| UC-3 | 사용자 | visibility=`public` | 인증된 모든 사용자가 조회/실행 |
| UC-4 | 다른 부서 사용자 | department 에이전트 접근 시도 | 403 Forbidden |
| UC-5 | 소유자 | 자신의 에이전트 수정/삭제 | 정상 |
| UC-6 | admin | 타인의 공개 에이전트 강제 삭제 | 정상 (감사 로그 기록) |
| UC-7 | 사용자 | 체크박스 UI용 도구 목록 조회 | 내부 도구 + 활성 MCP 도구 통합 목록 |
| UC-8 | 사용자 | 생성 시 temperature=0.7 입력 | RunAgent 실행 시 LLM에 0.7 적용 |

---

## 5. DB 스키마 설계

### 5-1. 신규 테이블: `departments`

| 컬럼 | 타입 | 제약 | 설명 |
|------|------|------|------|
| id | VARCHAR(36) | PK | UUID |
| name | VARCHAR(100) | NOT NULL, UNIQUE | 부서명 (e.g. "기획팀") |
| description | VARCHAR(255) | NULL | |
| created_at | DATETIME | NOT NULL | |
| updated_at | DATETIME | NOT NULL | |

### 5-2. 신규 테이블: `user_departments`

> 다중 부서 소속 허용 (겸직 대응)

| 컬럼 | 타입 | 제약 |
|------|------|------|
| user_id | BIGINT | PK, FK → users.id ON DELETE CASCADE |
| department_id | VARCHAR(36) | PK, FK → departments.id ON DELETE CASCADE |
| is_primary | TINYINT(1) | DEFAULT 0 (주 부서 표시, 사용자당 최대 1개 — 앱 레벨 정책) |
| created_at | DATETIME | NOT NULL |

**인덱스**: `INDEX (user_id, is_primary)`

### 5-3. 신규 테이블: `tool_catalog` (내부+MCP 통합)

> 내부 `TOOL_REGISTRY`와 외부 MCP 도구를 단일 테이블로 저장하여 체크박스 UI의 단일 API 응답을 가능케 한다.

| 컬럼 | 타입 | 제약 | 설명 |
|------|------|------|------|
| id | VARCHAR(36) | PK | UUID |
| tool_id | VARCHAR(150) | NOT NULL, UNIQUE | 전역 식별자 (`internal:excel_export`, `mcp:{server_id}:{tool_name}`) |
| source | ENUM('internal','mcp') | NOT NULL | |
| mcp_server_id | VARCHAR(36) | NULL, FK → mcp_server_registry.id ON DELETE CASCADE | source='mcp' 시 필수 |
| name | VARCHAR(200) | NOT NULL | UI 표시명 |
| description | TEXT | NOT NULL | 체크박스 툴팁/설명 |
| requires_env | JSON | NULL | 내부 도구 환경변수 목록 (e.g. `["TAVILY_API_KEY"]`) |
| is_active | TINYINT(1) | DEFAULT 1 | 0=비활성 (카탈로그 제외) |
| created_at | DATETIME | NOT NULL | |
| updated_at | DATETIME | NOT NULL | |

**인덱스**: `INDEX (source, is_active)`, `INDEX (mcp_server_id)`

### 5-4. 기존 테이블 변경: `agent_definition`

| 변경 | 내용 |
|------|------|
| 추가 | `visibility ENUM('private','department','public') NOT NULL DEFAULT 'private'` |
| 추가 | `department_id VARCHAR(36) NULL, FK → departments.id ON DELETE SET NULL` |
| 추가 | `temperature DECIMAL(3,2) NOT NULL DEFAULT 0.70 CHECK (temperature BETWEEN 0 AND 2)` |
| 인덱스 | `INDEX idx_agent_visibility (visibility)` |
| 인덱스 | `INDEX idx_agent_department (department_id, visibility)` |

### 5-5. 기존 테이블 변경: `mcp_server_registry`

> 서버 단위 메타만으로는 개별 도구 설명을 제공할 수 없어 보조로만 사용. 개별 도구는 `tool_catalog`에 저장.

| 변경 | 내용 |
|------|------|
| 유지 | 기존 컬럼 그대로 사용 (서버 자체 메타는 변경 없음) |
| 신규 연계 | MCP 서버 활성화 시 서버의 tools를 스캔하여 `tool_catalog`에 upsert (애플리케이션 레벨 sync job) |

### 5-6. `agent_tool` 변경 (최소)

| 변경 | 내용 |
|------|------|
| 유지 | `tool_id VARCHAR(100)` — 단 값을 `tool_catalog.tool_id` 전역 식별자로 사용 |
| 추가 (선택) | 후속 리팩토링 시 `tool_catalog_id` FK로 전환 가능 (이번 범위 아님) |

---

## 6. API 설계

### 6-1. 엔드포인트 목록

| Method | Path | 설명 | 권한 |
|--------|------|------|------|
| GET | `/api/v1/tool-catalog` | 통합 도구 목록 (내부+활성 MCP 도구) | 인증 사용자 |
| POST | `/api/v1/tool-catalog/sync` | MCP 서버의 도구를 카탈로그에 동기화 | admin |
| GET | `/api/v1/departments` | 부서 목록 | 인증 사용자 |
| POST | `/api/v1/departments` | 부서 등록 | admin |
| PATCH | `/api/v1/departments/{id}` | 부서 수정 | admin |
| DELETE | `/api/v1/departments/{id}` | 부서 삭제 | admin |
| POST | `/api/v1/users/{user_id}/departments` | 사용자 부서 배정 | admin |
| DELETE | `/api/v1/users/{user_id}/departments/{dept_id}` | 배정 해제 | admin |
| POST | `/api/v1/agents` (확장) | 에이전트 생성 (visibility/temperature/department_id 포함) | 인증 사용자 |
| GET | `/api/v1/agents` (확장) | 접근 가능 에이전트 목록 (visibility 필터) | 인증 사용자 |
| GET | `/api/v1/agents/{id}` (확장) | 단일 조회 (가시성 체크) | 인증 사용자 |
| PATCH | `/api/v1/agents/{id}` (확장) | 수정 | 소유자 |
| DELETE | `/api/v1/agents/{id}` (확장) | 삭제 | 소유자 or admin |
| POST | `/api/v1/agents/{id}/run` (확장) | 실행 (가시성 체크) | 접근 권한자 |

### 6-2. 주요 Request/Response

**GET /api/v1/tool-catalog (응답)**
```json
{
  "tools": [
    {
      "tool_id": "internal:excel_export",
      "source": "internal",
      "name": "Excel 파일 생성",
      "description": "pandas로 데이터를 Excel 파일로 저장합니다.",
      "requires_env": []
    },
    {
      "tool_id": "mcp:7f3a...:get_weather",
      "source": "mcp",
      "mcp_server_id": "7f3a...",
      "mcp_server_name": "Weather MCP",
      "name": "get_weather",
      "description": "특정 도시의 현재 날씨 조회"
    }
  ]
}
```

**POST /api/v1/agents (확장된 Request)**
```json
{
  "name": "분기 실적 분석봇",
  "description": "분기별 실적 데이터를 분석하고 Excel 보고서를 생성합니다",
  "system_prompt": "당신은 재무 분석 전문가입니다...",
  "llm_model_id": "uuid-gpt-4o",
  "temperature": 0.3,
  "visibility": "department",
  "department_id": "uuid-finance-team",
  "tool_ids": [
    "internal:excel_export",
    "internal:internal_document_search",
    "mcp:7f3a...:get_weather"
  ]
}
```

**GET /api/v1/agents (쿼리 파라미터)**
| 파라미터 | 타입 | 설명 |
|----------|------|------|
| `scope` | `mine` / `department` / `public` / `all` | 기본 `all` (접근 가능한 전부) |
| `search` | string | name/description LIKE 검색 |
| `page`, `size` | int | 페이징 |

응답에 각 레코드의 `owner_user_id`, `owner_email`, `visibility`, `department_name`, `can_edit`, `can_delete` 플래그 포함.

### 6-3. 접근 제어 규칙 (조회)

```python
def can_access(agent: AgentDefinition, viewer: User) -> bool:
    if agent.owner_user_id == viewer.id:
        return True
    if agent.visibility == "public":
        return True
    if agent.visibility == "department":
        return viewer.is_member_of(agent.department_id)
    return False  # private and not owner

def can_edit(agent, viewer) -> bool:
    return agent.owner_user_id == viewer.id

def can_delete(agent, viewer) -> bool:
    return agent.owner_user_id == viewer.id or viewer.role == "admin"
```

---

## 7. 아키텍처 설계

```
domain/
├── agent_builder/
│   ├── schemas.py          # AgentDefinition에 visibility/temperature/department_id 추가
│   ├── policies.py         # VisibilityPolicy (can_access/can_edit/can_delete)
│   └── tool_registry.py    # (DEPRECATED 예정) → tool_catalog 조회로 대체
├── department/              (NEW)
│   ├── entity.py           # Department, UserDepartment
│   └── interfaces.py       # DepartmentRepositoryInterface
└── tool_catalog/            (NEW)
    ├── entity.py           # ToolCatalogEntry
    ├── policies.py         # tool_id 포맷 검증 (internal:/mcp:)
    └── interfaces.py       # ToolCatalogRepositoryInterface

application/
├── agent_builder/
│   ├── create_agent_use_case.py   # visibility/temperature 파라미터 추가
│   ├── update_agent_use_case.py   # visibility/temperature/department_id 수정 지원
│   ├── list_agents_use_case.py    # (NEW) scope별 필터링
│   ├── run_agent_use_case.py      # temperature 전달, 접근 제어
│   └── delete_agent_use_case.py   # (NEW) 소유자/admin 권한 검증
├── department/              (NEW)
│   ├── create_department_use_case.py
│   ├── assign_user_department_use_case.py
│   └── list_departments_use_case.py
└── tool_catalog/            (NEW)
    ├── list_tool_catalog_use_case.py
    └── sync_mcp_tools_use_case.py

infrastructure/
├── agent_builder/models.py        # 컬럼 추가
├── department/              (NEW)
│   ├── models.py
│   └── department_repository.py
└── tool_catalog/            (NEW)
    ├── models.py
    └── tool_catalog_repository.py

interfaces/routes/
├── agent_builder_router.py  # 확장
├── department_router.py     (NEW)
└── tool_catalog_router.py   (NEW)

db/migration/
├── V005__create_departments.sql
├── V006__create_tool_catalog.sql
├── V007__alter_agent_definition_add_sharing.sql
└── V008__seed_internal_tools.sql
```

---

## 8. Run 시 Temperature 적용

AGENT-004 `RunAgentUseCase`에서 LLM 인스턴스 생성 지점:
```python
# 변경 전
llm = ChatOpenAI(model=llm_model.model_name, api_key=os.getenv(llm_model.api_key_env))

# 변경 후
llm = ChatOpenAI(
    model=llm_model.model_name,
    api_key=os.getenv(llm_model.api_key_env),
    temperature=agent_definition.temperature,  # 0.00 ~ 2.00
)
```

Ollama/Anthropic도 동일 파라미터 명칭 → 일괄 적용 가능.

---

## 9. 시드 데이터 마이그레이션 (V008)

현재 `TOOL_REGISTRY` 4개를 `tool_catalog`에 초기 등록:

| tool_id | source | name |
|---------|--------|------|
| `internal:excel_export` | internal | Excel 파일 생성 |
| `internal:internal_document_search` | internal | 내부 문서 검색 |
| `internal:python_code_executor` | internal | Python 코드 실행 |
| `internal:tavily_search` | internal | Tavily 웹 검색 |

기존 `agent_tool.tool_id` (예: `excel_export`) 레코드는 `internal:` prefix가 붙도록 일괄 UPDATE (V008 내).

---

## 10. TDD 계획

### 도메인 테스트 (mock 금지)
| 테스트 | 설명 |
|--------|------|
| `test_visibility_policy_private_owner_access` | private은 소유자만 통과 |
| `test_visibility_policy_department_same_dept` | department는 같은 부서원 통과 |
| `test_visibility_policy_department_other_dept_denied` | 타 부서는 차단 |
| `test_visibility_policy_public_all_authenticated` | public은 인증된 모든 사용자 통과 |
| `test_tool_id_format_valid` | `internal:` / `mcp:{uuid}:{name}` 포맷 검증 |
| `test_temperature_range_validation` | 0.0 ~ 2.0 범위 외 ValueError |

### Application UseCase 테스트
| 테스트 | 설명 |
|--------|------|
| `test_create_agent_with_visibility_and_temperature` | 신규 필드 저장 확인 |
| `test_create_department_agent_requires_dept_id` | department 선택 시 department_id 필수 |
| `test_list_agents_scope_mine` | scope=mine은 owner 본인 것만 |
| `test_list_agents_scope_department` | scope=department는 소속 부서 것만 |
| `test_list_agents_scope_all_merges` | scope=all은 private(본인)+dept(소속)+public 병합 |
| `test_update_agent_non_owner_forbidden` | 비소유자 수정 시 403 |
| `test_delete_agent_admin_allowed` | admin은 타인 에이전트 삭제 가능 |
| `test_run_agent_respects_temperature` | RunAgent가 LLM에 temperature 전달 |
| `test_sync_mcp_tools_upsert` | MCP 도구 동기화 시 중복 없이 upsert |

### 통합 테스트
| 테스트 | 설명 |
|--------|------|
| `test_tool_catalog_returns_internal_plus_mcp` | /tool-catalog가 두 소스 통합 반환 |
| `test_department_agent_execution_other_dept_403` | 타 부서 사용자의 실행 요청 403 |
| `test_public_agent_execution_any_authenticated` | public 에이전트는 아무나 실행 가능 |

---

## 11. 완료 기준 (Definition of Done)

- [ ] V005~V008 Flyway 마이그레이션 파일 작성 및 로컬 DB 적용 확인
- [ ] `departments` / `user_departments` 도메인/레포지토리/UseCase/라우터 구현
- [ ] `tool_catalog` 도메인/레포지토리/UseCase/라우터 구현
- [ ] `agent_definition` ORM + 도메인 엔티티에 visibility/temperature/department_id 반영
- [ ] `VisibilityPolicy` 도메인 정책 구현
- [ ] `CreateAgentUseCase` / `UpdateAgentUseCase` / `RunAgentUseCase` / `ListAgentsUseCase` / `DeleteAgentUseCase` 확장 및 신규 구현
- [ ] MCP 서버 등록 시 도구 자동 sync (또는 수동 sync API)
- [ ] 내부 `TOOL_REGISTRY` → `tool_catalog` 시드 이관 및 기존 `agent_tool.tool_id` prefix 마이그레이션
- [ ] `/api/v1/tool-catalog` 단일 호출로 체크박스 UI가 렌더링 가능함을 계약 테스트로 검증
- [ ] 모든 TDD 테스트 통과 (Red → Green)
- [ ] `/verify-architecture` / `/verify-logging` / `/verify-tdd` 통과
- [ ] 프론트엔드 타입(`idt_front/src/types/`) 동기화 (API-Contract 규칙 §4-1)

---

## 12. 리스크 & 대응

| 리스크 | 영향 | 대응 |
|--------|------|------|
| MCP 서버의 도구 목록이 런타임에 변경됨 | 카탈로그 stale | 서버 재등록 시 재sync + 수동 sync API 제공 |
| 기존 `agent_tool.tool_id` prefix 마이그레이션 실패 | 기존 에이전트 실행 불가 | V008 이전에 백업 덤프 필수, UPDATE는 단일 트랜잭션 |
| Temperature 기본값 변경이 기존 에이전트 행동 변화 유발 | 출력 품질 변동 | 기본 0.70 적용 전 기존 레코드는 0.00으로 명시 UPDATE (이전 코드 기본값 유지) |
| department 테이블이 비어있을 때 dept 공개 옵션 UX | UI에서 선택 불가 | admin이 최소 1개 부서 등록하지 않으면 UI에서 department 옵션 disabled |
| admin이 공개 에이전트 삭제 시 참조 무결성 | 실행 중 세션 오류 | soft delete(`status='deleted'`)로 처리, 목록/실행에서 제외 |

---

## 13. 참고 문서

- `src/claude/task/task-custom-agent-builder.md` (AGENT-004)
- `src/claude/task/task-middleware-agent-builder.md` (AGENT-005)
- `src/claude/task/task-auto-agent-builder.md` (AGENT-006)
- `docs/01-plan/features/llm-model-registry.plan.md` (LLM-MODEL-REG-001)
- `src/claude/task/task-auth.md` (AUTH-001)
- `src/claude/task/task-mcp-registry.md` (MCP-REG-001)
- `src/claude/task/task-logging.md` (LOG-001)

---

## 14. Open Questions (설계 단계에서 확정)

- [ ] **sync 전략**: MCP 서버 등록/수정 시 자동 sync vs 관리자 수동 버튼 vs 스케줄러 — 설계 단계에서 확정
- [ ] **is_primary department 정책**: 사용자당 주 부서 1개 강제 여부, 기본 배정 로직
- [ ] **기존 에이전트의 temperature 초기값**: 0.00 보존 vs 0.70 일괄 적용 — 마이그레이션 정책 결정
- [ ] **tool_catalog의 내부 도구 수정 권한**: admin이 내부 도구의 name/description을 바꿀 수 있는지, 코드 고정인지
- [ ] **MCP 서버 단위 on/off**: 서버 비활성화 시 tool_catalog의 해당 도구도 자동 비활성화 여부
