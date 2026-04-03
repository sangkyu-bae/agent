# AGENT-004: Custom Agent Builder

> Task ID: AGENT-004
> 의존성: LOG-001 (task-logging.md), MYSQL-001 (task-mysql.md)
> 관련 도구: SEARCH-001 (Tavily), EXCEL-EXPORT-001, CODE-001, AGENT-001

---

## 1. 목적

사용자가 자연어로 에이전트를 설명하면:
1. LLM이 사용할 도구를 자동 선택하고 워크플로우 골격을 생성한다
2. LLM이 Supervisor용 시스템 프롬프트를 자동 생성한다
3. 생성된 에이전트 정의를 MySQL에 저장한다
4. 실행 시 DB에서 워크플로우를 로드하여 LangGraph Supervisor로 동적 컴파일 후 실행한다
5. 사용자는 PATCH API로 시스템 프롬프트를 수정할 수 있다

---

## 2. 아키텍처

```
domain/agent_builder/
├── schemas.py          # ToolMeta, WorkerDefinition, WorkflowSkeleton, WorkflowDefinition, AgentDefinition
├── tool_registry.py    # TOOL_REGISTRY, get_tool_meta(), get_all_tools()
├── policies.py         # AgentBuilderPolicy, UpdateAgentPolicy
└── interfaces.py       # AgentDefinitionRepositoryInterface

application/agent_builder/
├── schemas.py               # Request/Response Pydantic 모델
├── tool_selector.py         # ToolSelector: LLM 구조화 출력으로 도구 선택
├── prompt_generator.py      # PromptGenerator: LLM 시스템 프롬프트 자동 생성
├── workflow_compiler.py     # WorkflowCompiler: WorkflowDefinition → LangGraph CompiledGraph
├── create_agent_use_case.py # CreateAgentUseCase
├── update_agent_use_case.py # UpdateAgentUseCase
├── get_agent_use_case.py    # GetAgentUseCase
└── run_agent_use_case.py    # RunAgentUseCase

infrastructure/agent_builder/
├── models.py                       # AgentDefinitionModel + AgentToolModel (SQLAlchemy ORM)
├── agent_definition_repository.py  # MySQL CRUD (selectinload JOIN)
└── tool_factory.py                 # tool_id → BaseTool 인스턴스 생성

api/routes/
└── agent_builder_router.py  # 5 엔드포인트, DI placeholder → main.py override
```

---

## 3. DB 스키마

### agent_definition
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | VARCHAR(36) PK | UUID |
| user_id | VARCHAR(36) | 소유자 |
| name | VARCHAR(255) | 에이전트 이름 |
| description | TEXT | 사용자 원본 요청 |
| system_prompt | TEXT | LLM 자동 생성, 수정 가능 |
| flow_hint | TEXT | LLM이 생성한 실행 흐름 힌트 |
| model_name | VARCHAR(100) | 사용 LLM 모델명 |
| status | VARCHAR(50) | active / inactive |
| created_at | DATETIME | |
| updated_at | DATETIME | |

### agent_tool (1:N)
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | INT PK AUTO_INCREMENT | |
| agent_id | VARCHAR(36) FK → agent_definition.id CASCADE | |
| tool_id | VARCHAR(100) | 도구 식별자 |
| worker_id | VARCHAR(100) | Worker 노드 이름 |
| description | TEXT | Worker 역할 설명 |
| sort_order | INT | 실행 순서 |

---

## 4. 등록된 도구 (tool_registry)

| tool_id | 설명 |
|---------|------|
| internal_document_search | Qdrant 기반 내부 문서 검색 |
| tavily_search | Tavily 웹 검색 |
| excel_export | pandas 엑셀 파일 생성 |
| python_code_executor | Python 샌드박스 코드 실행 |

---

## 5. API 엔드포인트

| Method | Path | 설명 |
|--------|------|------|
| GET | /api/v1/agents/tools | 사용 가능한 도구 목록 |
| POST | /api/v1/agents | 에이전트 생성 (LLM 자동 선택) |
| GET | /api/v1/agents/{agent_id} | 에이전트 정의 조회 |
| PATCH | /api/v1/agents/{agent_id} | 시스템 프롬프트/이름 수정 |
| POST | /api/v1/agents/{agent_id}/run | 에이전트 실행 |

---

## 6. 에이전트 생성 흐름 (Create)

```
POST /api/v1/agents
  → CreateAgentUseCase.execute()
    → ToolSelector.select(user_request, available_tools)  ← LLM structured output
      → _SkeletonOutput(tool_ids, worker_definitions, flow_hint)
    → AgentBuilderPolicy.validate_tool_count()
    → PromptGenerator.generate(user_request, skeleton)  ← LLM text output
    → AgentDefinition 생성
    → AgentDefinitionRepository.save()
  → CreateAgentResponse
```

---

## 7. 에이전트 실행 흐름 (Run)

```
POST /api/v1/agents/{agent_id}/run
  → RunAgentUseCase.execute()
    → AgentDefinitionRepository.find_by_id()  ← JOIN agent_tool
    → agent.to_workflow_definition()           ← WorkflowDefinition VO 조립
    → WorkflowCompiler.compile(workflow, model_name, api_key)
      → ToolFactory.create(tool_id) × N       ← BaseTool 인스턴스
      → create_react_agent(llm, tools) × N    ← Worker 노드
      → create_supervisor(workers, system_prompt)  ← Supervisor 노드
      → CompiledGraph
    → graph.ainvoke({"messages": [user_query]})
    → _parse_result() → (answer, tools_used)
  → RunAgentResponse
```

---

## 8. LLM 프롬프트 설계

### ToolSelector (structured output → _SkeletonOutput)
```
사용 가능한 도구: {tool_list}
사용자 요청: {user_request}

다음 JSON 형식으로 응답하세요:
- selected_tool_ids: 필요한 도구 ID 목록
- workers: [{tool_id, worker_id, description, sort_order}]
- flow_hint: 실행 흐름 설명 (한국어)
```

### PromptGenerator (text output)
```
에이전트 역할: {user_request}
사용 도구: {tool_descriptions}
실행 흐름: {flow_hint}

위 정보를 바탕으로 Supervisor 에이전트의 시스템 프롬프트를 작성하세요.
```

---

## 9. 도메인 정책

### AgentBuilderPolicy
- `validate_tool_count(tool_ids)`: 1 ≤ 도구 수 ≤ 5
- `validate_system_prompt(prompt)`: 길이 ≤ 4000자
- `validate_name(name)`: 비어있지 않음

### UpdateAgentPolicy
- `validate_update(agent)`: status == "active" 인 경우만 수정 허용

---

## 10. TDD 구현 순서

1. `tests/domain/agent_builder/test_schemas.py` → `src/domain/agent_builder/schemas.py`
2. `tests/domain/agent_builder/test_tool_registry.py` → `src/domain/agent_builder/tool_registry.py`
3. `tests/domain/agent_builder/test_policies.py` → `src/domain/agent_builder/policies.py`
4. `tests/infrastructure/agent_builder/test_tool_factory.py` → `src/infrastructure/agent_builder/tool_factory.py`
5. `tests/infrastructure/agent_builder/test_agent_definition_repository.py` → `src/infrastructure/agent_builder/agent_definition_repository.py`
6. `tests/application/agent_builder/test_create_agent_use_case.py` → `src/application/agent_builder/create_agent_use_case.py`
7. `tests/application/agent_builder/test_update_agent_use_case.py` → `src/application/agent_builder/update_agent_use_case.py`
8. `tests/application/agent_builder/test_run_agent_use_case.py` → `src/application/agent_builder/run_agent_use_case.py`
9. `tests/application/agent_builder/test_get_agent_use_case.py` → `src/application/agent_builder/get_agent_use_case.py`
10. `tests/api/test_agent_builder_router.py` → `src/api/routes/agent_builder_router.py`

**미구현 (Gap):**
- `tool_selector.py` — LLM 도구 자동 선택
- `prompt_generator.py` — LLM 시스템 프롬프트 자동 생성
- `workflow_compiler.py` — LangGraph 동적 컴파일

---

## 11. 로깅 규칙 (LOG-001 준수)

- 모든 UseCase: `logger.info("XxxUseCase start", request_id=..., agent_id=...)`
- 성공 시: `logger.info("XxxUseCase done", request_id=..., agent_id=...)`
- 실패 시: `logger.error("XxxUseCase failed", exception=e, request_id=...)`
- print() 사용 금지
- request_id 없는 로그 금지

---

## 12. 주의사항

- WorkflowCompiler는 infrastructure가 아닌 **application** 레이어에 위치 (LangGraph 조합 로직)
- ToolFactory는 **infrastructure** 레이어 (외부 도구 인스턴스 생성)
- tool_ids JSON 배열 비정규화 금지 → **agent_tool 테이블 분리** 사용
- WorkflowDefinition은 DB에 저장되지 않음 → 실행 시 AgentDefinition에서 조립
