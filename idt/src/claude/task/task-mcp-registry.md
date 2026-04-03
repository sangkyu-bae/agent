# Task: Dynamic MCP Tool Registry

> Task ID: MCP-REG-001
> 의존성: LOG-001, MYSQL-001, MCP-001, AGENT-004
> 최종 수정: 2026-03-21
> 상태: Done

---

## 1. 목적

사용자가 외부 MCP 서버를 `name`, `description`, `input_schema`, `endpoint`로 DB에 등록하면,
기존 내부 도구(TOOL_REGISTRY)와 함께 Agent Builder에서 동적으로 로드되어 사용 가능하도록 한다.

---

## 2. 아키텍처 레이어

| 레이어 | 구성요소 | 역할 |
|--------|----------|------|
| domain | `MCPServerRegistration`, `MCPRegistrationPolicy`, `MCPServerRegistryRepositoryInterface` | 엔티티, 정책, 저장소 추상화 |
| application | `RegisterMCPServerUseCase`, `ListMCPServersUseCase`, `UpdateMCPServerUseCase`, `DeleteMCPServerUseCase`, `LoadMCPToolsUseCase` | 5개 유스케이스 |
| infrastructure | `MCPServerModel`, `MCPServerRepository`, `MCPToolLoader` | ORM, CRUD, MCP 연결 |
| api | `mcp_registry_router.py` | CRUD 5 엔드포인트 |

---

## 3. DB 스키마

```sql
CREATE TABLE mcp_server_registry (
    id           VARCHAR(36)   NOT NULL PRIMARY KEY,
    user_id      VARCHAR(100)  NOT NULL,
    name         VARCHAR(255)  NOT NULL,
    description  TEXT          NOT NULL,
    endpoint     VARCHAR(512)  NOT NULL,
    transport    VARCHAR(20)   NOT NULL DEFAULT 'sse',
    input_schema JSON          NULL,
    is_active    BOOLEAN       NOT NULL DEFAULT TRUE,
    created_at   DATETIME      NOT NULL,
    updated_at   DATETIME      NOT NULL,
    INDEX idx_mcp_server_registry_user_id (user_id),
    INDEX idx_mcp_server_registry_is_active (is_active)
);
```

---

## 4. API 엔드포인트

| Method | Path | 설명 |
|--------|------|------|
| POST | /api/v1/mcp-registry | MCP 서버 등록 |
| GET | /api/v1/mcp-registry | 목록 조회 (user_id 필터 선택) |
| GET | /api/v1/mcp-registry/{id} | 단건 조회 |
| PUT | /api/v1/mcp-registry/{id} | 정보 수정 |
| DELETE | /api/v1/mcp-registry/{id} | 삭제 |

---

## 5. 핵심 설계 결정

| 결정 | 이유 |
|------|------|
| transport는 SSE만 지원 | 사용자 등록 MCP는 원격 서버 전제 (stdio는 로컬 프로세스 실행 필요) |
| `tool_id = mcp_{uuid}` | 내부 도구와 네임스페이스 충돌 방지 |
| 부분 실패 허용 | 하나의 MCP 서버 장애가 전체 도구 로드를 막지 않음 |
| MCP-001 MCPClientFactory 재사용 | 중복 구현 방지; SSEServerConfig로 DB 설정 조립 |
| `GET /api/v1/agents/tools` 메타만 반환 | 목록 조회 시 MCP 연결 없음 — 에이전트 실행 시에만 실제 연결 |

---

## 6. AGENT-004 통합 변경

`GET /api/v1/agents/tools` 엔드포인트에 `get_load_mcp_tools_use_case` DI 추가:

```python
# 변경 전: 내부 도구만 반환
tools = [ToolMetaResponse(...) for t in get_all_tools()]

# 변경 후: 내부 + DB 등록 MCP 도구 합산
internal = [ToolMetaResponse(...) for t in get_all_tools()]
mcp_metas = await load_mcp_use_case.list_meta(request_id)
mcp = [ToolMetaResponse(tool_id=r.tool_id, ...) for r in mcp_metas]
return AvailableToolsResponse(tools=internal + mcp)
```

---

## 7. 파일 구조

```
src/
├── domain/mcp_registry/
│   ├── schemas.py       # MCPServerRegistration, MCPTransportType
│   ├── policies.py      # MCPRegistrationPolicy (name/desc/endpoint 검증)
│   └── interfaces.py    # MCPServerRegistryRepositoryInterface
├── application/mcp_registry/
│   ├── schemas.py
│   ├── register_mcp_server_use_case.py
│   ├── list_mcp_servers_use_case.py
│   ├── load_mcp_tools_use_case.py
│   ├── update_mcp_server_use_case.py
│   └── delete_mcp_server_use_case.py
├── infrastructure/mcp_registry/
│   ├── models.py
│   ├── mcp_server_repository.py
│   └── mcp_tool_loader.py
└── api/routes/
    └── mcp_registry_router.py

tests/ (78개 테스트 통과)
├── domain/mcp_registry/
├── application/mcp_registry/
├── infrastructure/mcp_registry/
└── api/test_mcp_registry_router.py
```

---

## 8. 로깅 체크리스트 (LOG-001 준수)

- [x] 모든 UseCase: `LoggerInterface` 주입
- [x] UseCase 시작/완료 INFO 로그 (`request_id` 포함)
- [x] MCP 서버 로드 실패 시 ERROR 로그 + `exception=e`
- [x] `MCPToolLoader`: 로드 시작/완료 INFO 로그
- [x] `print()` 사용 금지

---

## 9. 완료 기준

- [x] `mcp_server_registry` DDL 작성
- [x] Domain (schemas, policies, interfaces) 구현 + 테스트 통과
- [x] Infrastructure (models, repository, tool_loader) 구현 + 테스트 통과
- [x] Application (5 use cases) 구현 + 테스트 통과
- [x] API Router (5 endpoints) 구현 + 테스트 통과
- [x] `GET /api/v1/agents/tools` 내부+MCP 통합
- [x] 부분 실패 처리 (LoadMCPToolsUseCase)
- [x] 전체 78개 테스트 통과
