# Plan: Dynamic MCP Tool Registry

> Feature ID: MCP-REG-001
> 작성일: 2026-03-21
> 작성자: AI Assistant
> 상태: Draft

---

## 1. 배경 및 목적

### 현황

현재 Agent Builder(`AGENT-004`)에서 사용 가능한 도구는 코드에 하드코딩된 내부 도구 4개(`TOOL_REGISTRY` dict)만 존재한다.

```python
# src/domain/agent_builder/tool_registry.py (현재)
TOOL_REGISTRY: dict[str, ToolMeta] = {
    "excel_export": ...,
    "internal_document_search": ...,
    "python_code_executor": ...,
    "tavily_search": ...,
}
```

### 문제

- 새로운 도구 추가 시 코드 배포 필요
- 외부 MCP 서버를 동적으로 연결할 수단이 없음
- 사용자별 커스텀 도구 등록 불가

### 목표

사용자가 MCP 서버 정보(`name`, `description`, `input`, `endpoint`)를 DB에 등록하면,
기존 내부 도구 목록과 합쳐져 Agent Builder에서 즉시 사용 가능하도록 한다.

---

## 2. 요구사항

### 2.1 기능 요구사항

| ID | 요구사항 | 우선순위 |
|----|----------|----------|
| FR-01 | 사용자는 MCP 서버를 name/description/input_schema/endpoint로 등록할 수 있다 | Must |
| FR-02 | 등록된 MCP 서버 목록을 조회할 수 있다 (전체/사용자별) | Must |
| FR-03 | 등록된 MCP 서버 정보를 수정하고 삭제할 수 있다 | Must |
| FR-04 | Agent Builder의 도구 목록 조회 시 내부 도구 + DB 등록 MCP 도구가 함께 반환된다 | Must |
| FR-05 | 등록된 MCP 서버는 SSE transport로 연결되어 LangChain BaseTool로 래핑된다 | Must |
| FR-06 | MCP 서버 연결 실패 시 해당 도구는 목록에서 제외되고 로그로 기록된다 | Must |
| FR-07 | 등록 시 endpoint 포맷 유효성 검증을 수행한다 | Should |
| FR-08 | is_active 플래그로 도구를 임시 비활성화할 수 있다 | Should |

### 2.2 비기능 요구사항

| ID | 요구사항 |
|----|----------|
| NFR-01 | TDD: 테스트 먼저 작성 → 실패 확인 → 구현 순서 준수 |
| NFR-02 | LOG-001: 모든 모듈에 LoggerInterface 주입, request_id 전파 |
| NFR-03 | DDD 레이어 규칙 준수 (domain → application → infrastructure) |
| NFR-04 | MCP 서버 연결 오류는 전체 도구 로드를 중단시키지 않음 (부분 실패 허용) |
| NFR-05 | endpoint URL, API 토큰 등 민감 정보 마스킹 로깅 |

---

## 3. 아키텍처 개요

### 3.1 레이어 구성

```
domain/mcp_registry/
├── schemas.py          # MCPServerRegistration (Entity), MCPRegistrationPolicy
└── interfaces.py       # MCPServerRegistryRepositoryInterface

application/mcp_registry/
├── register_mcp_server_use_case.py     # 등록
├── update_mcp_server_use_case.py       # 수정
├── delete_mcp_server_use_case.py       # 삭제
├── list_mcp_servers_use_case.py        # 조회
└── load_mcp_tools_use_case.py          # DB → LangChain BaseTool 변환

infrastructure/mcp_registry/
├── models.py                           # MCPServerModel (SQLAlchemy ORM)
├── mcp_server_repository.py            # MySQLBaseRepository 상속
└── mcp_tool_loader.py                  # MCPClientFactory를 활용한 Tool 로드

api/routes/
└── mcp_registry_router.py             # CRUD 5 엔드포인트
```

### 3.2 기존 모듈과의 통합

```
AGENT-004 (Agent Builder)
  └── GET /api/v1/agents/tools
        ├── 기존: get_all_tools() → TOOL_REGISTRY (내부 도구)
        └── 변경: get_all_tools() + LoadMcpToolsUseCase.list() → 내부 + DB 등록 도구

MCP-001 (MCPClientFactory)
  └── 재사용: MCPToolAdapter, SSEServerConfig
        ← MCPToolLoader가 DB 설정으로 SSEServerConfig 조립
```

---

## 4. DB 스키마

### mcp_server_registry

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | VARCHAR(36) PK | UUID |
| user_id | VARCHAR(36) | 등록한 사용자 ID |
| name | VARCHAR(255) NOT NULL | 도구 표시 이름 |
| description | TEXT NOT NULL | LLM용 도구 설명 |
| input_schema | JSON | 입력 파라미터 스키마 (JSON Schema) |
| endpoint | VARCHAR(512) NOT NULL | MCP 서버 SSE 엔드포인트 URL |
| transport | VARCHAR(20) DEFAULT 'sse' | 연결 방식 (현재: sse) |
| is_active | BOOLEAN DEFAULT TRUE | 활성화 여부 |
| created_at | DATETIME | 등록일 |
| updated_at | DATETIME | 수정일 |

---

## 5. API 엔드포인트

| Method | Path | 설명 |
|--------|------|------|
| POST | /api/v1/mcp-registry | MCP 서버 등록 |
| GET | /api/v1/mcp-registry | 등록된 MCP 서버 목록 조회 |
| GET | /api/v1/mcp-registry/{id} | 특정 MCP 서버 조회 |
| PUT | /api/v1/mcp-registry/{id} | MCP 서버 정보 수정 |
| DELETE | /api/v1/mcp-registry/{id} | MCP 서버 삭제 |

---

## 6. 의존성

| Task ID | 모듈 | 의존 이유 |
|---------|------|-----------|
| LOG-001 | task-logging.md | 모든 모듈 LoggerInterface 필수 |
| MYSQL-001 | task-mysql.md | MCPServerModel CRUD (MySQLBaseRepository 상속) |
| MCP-001 | task-mcp-client.md | MCPClientFactory, MCPToolAdapter, SSEServerConfig 재사용 |
| AGENT-004 | task-custom-agent-builder.md | GET /api/v1/agents/tools 확장 통합 |

---

## 7. TDD 구현 순서

1. `tests/domain/mcp_registry/test_schemas.py` → `src/domain/mcp_registry/schemas.py`
2. `tests/infrastructure/mcp_registry/test_mcp_server_repository.py` → `src/infrastructure/mcp_registry/mcp_server_repository.py`
3. `tests/infrastructure/mcp_registry/test_mcp_tool_loader.py` → `src/infrastructure/mcp_registry/mcp_tool_loader.py`
4. `tests/application/mcp_registry/test_register_use_case.py` → `src/application/mcp_registry/register_mcp_server_use_case.py`
5. `tests/application/mcp_registry/test_list_use_case.py` → `src/application/mcp_registry/list_mcp_servers_use_case.py`
6. `tests/application/mcp_registry/test_load_mcp_tools_use_case.py` → `src/application/mcp_registry/load_mcp_tools_use_case.py`
7. `tests/application/mcp_registry/test_update_delete_use_case.py` → update/delete use cases
8. `tests/api/test_mcp_registry_router.py` → `src/api/routes/mcp_registry_router.py`
9. AGENT-004 `GET /api/v1/agents/tools` 통합 테스트 수정

---

## 8. 주요 설계 결정

| 결정 | 이유 |
|------|------|
| transport는 현재 SSE만 지원 | 사용자가 등록하는 MCP는 원격 서버이므로 SSE가 기본; stdio는 로컬 프로세스 실행이 필요해 사용자 등록 불가 |
| MCP 연결 실패 시 부분 실패 허용 | 하나의 외부 MCP 서버 장애가 전체 도구 목록 로드를 막지 않아야 함 |
| MCPClientFactory 재사용 (MCP-001) | 중복 구현 방지; SSEServerConfig로 DB 설정 조립 |
| input_schema는 JSON으로 저장 | LangChain args_schema 동적 생성 또는 메타데이터로 LLM에 전달 |
| 도구 ID는 `mcp_{id}` 형태로 네이밍 | 내부 도구와 충돌 방지 |

---

## 9. 완료 기준

- [ ] MCP 서버 CRUD API 동작 (5 엔드포인트)
- [ ] `GET /api/v1/agents/tools` 응답에 내부 도구 + DB 등록 MCP 도구 포함
- [ ] MCP 서버 연결 실패 시 부분 실패 처리 (로그 기록 후 나머지 도구 반환)
- [ ] 전체 테스트 통과 (TDD 순서 준수)
- [ ] LOG-001 로깅 적용 (request_id 전파, 스택 트레이스)
- [ ] DDD 레이어 의존성 규칙 위반 없음

---

## 10. 참고 문서

- `src/claude/task/task-mcp-client.md` (MCP-001)
- `src/claude/task/task-mysql.md` (MYSQL-001)
- `src/claude/task/task-custom-agent-builder.md` (AGENT-004)
- `src/claude/task/task-logging.md` (LOG-001)
