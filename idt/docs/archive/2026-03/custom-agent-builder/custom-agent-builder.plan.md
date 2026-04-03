# Plan: Custom Agent Builder (AGENT-004)

> Created: 2026-03-20 (Revised v2 — system prompt 자동생성 + 수정 기능 추가)
> Feature ID: AGENT-004
> Task ID: task-custom-agent-builder.md (예정)
> Phase: Plan

---

## 1. 개요 (Overview)

사용자가 자연어로 에이전트를 설명하면, **LLM이 자동으로 필요한 도구와 실행 플로우를 결정**하고 이를 DB에 저장한다. 이후 저장된 워크플로우를 불러와 **LangGraph Supervisor 패턴으로 동적 컴파일**하여 에이전트를 실행하는 시스템이다.

### 핵심 가치

> "에이전트를 코드 없이 자연어로 만들고, LLM이 자동 생성한 시스템 프롬프트를 사용자가 원하는 대로 다듬어 반복 실행한다."

---

## 2. 세 가지 핵심 API Flow

### Flow 1 — 에이전트 생성 (Agent Creation)

```
POST /api/v1/agents
{
  "user_request": "AI 관련 뉴스 검색하고 엑셀로 저장하는 에이전트 만들어줘",
  "name": "AI 뉴스 수집기",
  "user_id": "user-123"
}
```

```
[사용자 요청]
     ↓
[LLM Step 1: 도구 선택 + 플로우 결정]
  - 필요한 tool_ids 결정: ["tavily_search", "excel_export"]
  - 실행 플로우 결정: search_worker → export_worker
  - flow_hint 생성
     ↓
[LLM Step 2: 시스템 프롬프트 자동 생성]
  - 선택된 도구 + 사용자 요청 기반으로 supervisor_prompt 생성
  - 예: "당신은 AI 뉴스 수집 전문 에이전트입니다.
         Tavily 검색으로 최신 AI 뉴스를 수집하고,
         수집된 데이터를 Excel로 저장합니다.
         항상 한국어로 응답하세요."
     ↓
[AgentDefinition 도메인 객체 생성 + Policy 검증]
     ↓
[MySQL agent_definition 테이블에 저장]
     ↓
응답: { agent_id, name, tool_ids, system_prompt, workflow_definition }
      ※ system_prompt는 응답 최상위에 명시적으로 반환 (사용자가 확인/편집 가능)
```

### Flow 1-B — 시스템 프롬프트 수정 (System Prompt Update)

```
PATCH /api/v1/agents/{agent_id}
{
  "system_prompt": "당신은 AI 뉴스 수집 에이전트입니다.\n뉴스 제목, URL, 요약을 포함하여 저장하세요.\n영문 뉴스는 한국어로 번역하세요.",
  "name": "AI 뉴스 수집기 v2"   ← 선택적 (name도 함께 수정 가능)
}
```

```
[agent_id로 기존 에이전트 로드]
     ↓
[UpdateAgentPolicy 검증]
  - system_prompt 최대 길이: 4000자
  - status가 active인 경우만 수정 가능
     ↓
[system_prompt → workflow_definition.supervisor_prompt 동기화]
     ↓
[MySQL update (updated_at 갱신)]
     ↓
응답: { agent_id, name, system_prompt, updated_at }
```

### Flow 2 — 에이전트 실행 (Agent Execution)

```
POST /api/v1/agents/{agent_id}/run
{
  "query": "오늘 AI 뉴스 5개 수집해서 엑셀 저장해줘",
  "user_id": "user-123"
}
```

```
[agent_id로 MySQL에서 workflow_definition 로드]
     ↓
[WorkflowCompiler: JSON → LangGraph 그래프 동적 컴파일]
  - tool_ids → BaseTool 인스턴스 생성
  - 각 tool을 Worker 에이전트로 래핑
  - Supervisor 노드 생성 (worker들 오케스트레이션)
  - StateGraph 컴파일
     ↓
[LangGraph Supervisor 실행]
  supervisor → worker(tavily_search) → supervisor → worker(excel_export) → END
     ↓
응답: { answer, tools_used, agent_id }
```

---

## 3. LangGraph Supervisor 패턴

```
                    ┌─────────────────┐
                    │   Supervisor    │  ← "다음에 어떤 worker를 호출할지 결정"
                    │  (ChatOpenAI)   │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              ↓              ↓              ↓
    ┌─────────────────┐  ┌──────────────┐  ┌──────────────────┐
    │ tavily_worker   │  │ excel_worker │  │  code_worker     │
    │ (search agent)  │  │(export agent)│  │(executor agent)  │
    └─────────────────┘  └──────────────┘  └──────────────────┘
```

- Supervisor는 어떤 Worker를 다음에 호출할지, 언제 FINISH할지 결정
- Worker는 각 도구 하나를 전담하는 ReAct 에이전트
- 워크플로우 정의에서 로드된 tool_ids만으로 Worker 동적 생성

---

## 4. DB 데이터 모델

### 테이블 구조 (정규화)

`tool_ids`를 JSON으로 저장하면 정규화 위반이고 "특정 도구를 쓰는 에이전트 조회" 같은 쿼리가 불가능하다. 따라서 **별도 테이블로 분리하고 JOIN으로 조회**한다.

```
agent_definition  1────N  agent_tool
(에이전트 메타)            (에이전트-도구 매핑 + 워커 정보)
```

---

### agent_definition 테이블

```sql
CREATE TABLE agent_definition (
    id                  VARCHAR(36)  PRIMARY KEY,    -- UUID
    user_id             VARCHAR(100) NOT NULL,
    name                VARCHAR(200) NOT NULL,
    description         TEXT,                        -- 사용자 원문 요청
    system_prompt       TEXT         NOT NULL,       -- 사용자 수정 가능한 시스템 프롬프트
    flow_hint           TEXT,                        -- LLM이 생성한 실행 순서 힌트
    model_name          VARCHAR(100) NOT NULL DEFAULT 'gpt-4o-mini',
    status              VARCHAR(20)  NOT NULL DEFAULT 'active',
    created_at          DATETIME     NOT NULL,
    updated_at          DATETIME     NOT NULL
);
```

> `tool_ids JSON` 컬럼 제거 → `agent_tool` 테이블로 분리
> `workflow_definition JSON` 컬럼 제거 → 구조화된 컬럼(`system_prompt`, `flow_hint`) + `agent_tool` 테이블로 대체

---

### agent_tool 테이블 (분리된 도구 매핑)

```sql
CREATE TABLE agent_tool (
    id          VARCHAR(36)  PRIMARY KEY,    -- UUID
    agent_id    VARCHAR(36)  NOT NULL,
    tool_id     VARCHAR(100) NOT NULL,       -- TOOL_REGISTRY 키 (e.g. "tavily_search")
    worker_id   VARCHAR(100) NOT NULL,       -- LangGraph Worker 식별자 (e.g. "search_worker")
    description TEXT,                        -- 워커 역할 설명
    sort_order  INT          NOT NULL DEFAULT 0,  -- 실행 순서 힌트

    CONSTRAINT fk_agent_tool_agent FOREIGN KEY (agent_id)
        REFERENCES agent_definition(id) ON DELETE CASCADE,
    UNIQUE KEY uq_agent_tool (agent_id, tool_id)
);
```

---

### JOIN 조회 예시

```sql
-- 에이전트 전체 정보 조회 (tool 포함)
SELECT
    ad.id, ad.name, ad.system_prompt, ad.flow_hint,
    at.tool_id, at.worker_id, at.description, at.sort_order
FROM agent_definition ad
LEFT JOIN agent_tool at ON ad.id = at.agent_id
WHERE ad.id = ?
ORDER BY at.sort_order;

-- 특정 도구를 사용하는 에이전트 목록 조회
SELECT ad.id, ad.name
FROM agent_definition ad
JOIN agent_tool at ON ad.id = at.agent_id
WHERE at.tool_id = 'tavily_search';
```

---

### 도메인 객체 ↔ DB 매핑

```python
# 조회 시: JOIN 결과 → AgentDefinition 도메인 객체로 조립
@dataclass
class AgentDefinition:
    id: str
    user_id: str
    name: str
    description: str
    system_prompt: str          # agent_definition.system_prompt
    flow_hint: str              # agent_definition.flow_hint
    workers: list[WorkerDefinition]  # agent_tool rows 조합
    model_name: str
    status: str

@dataclass
class WorkerDefinition:
    tool_id: str       # agent_tool.tool_id
    worker_id: str     # agent_tool.worker_id
    description: str   # agent_tool.description
    sort_order: int    # agent_tool.sort_order
```

---

### WorkflowDefinition (컴파일용 Value Object)

DB 조회 후 LangGraph 컴파일에 필요한 형태로 조립하는 Value Object (DB 저장 없음):

```python
@dataclass
class WorkflowDefinition:
    """AgentDefinition에서 조립. LangGraph 컴파일 전용."""
    supervisor_prompt: str           # = agent_definition.system_prompt
    workers: list[WorkerDefinition]  # = agent_tool rows (sort_order 순)
    flow_hint: str                   # = agent_definition.flow_hint
```

---

## 5. 아키텍처 설계

```
domain/agent_builder/
  ├── schemas.py              # AgentDefinition, WorkerDefinition, WorkflowDefinition
  ├── tool_registry.py        # TOOL_REGISTRY: 사용 가능한 도구 목록 + 메타데이터
  └── policies.py             # AgentBuilderPolicy + UpdateAgentPolicy

application/agent_builder/
  ├── schemas.py              # CreateAgentRequest/Response, UpdateAgentRequest/Response,
  │                           #   RunAgentRequest/Response
  ├── tool_selector.py        # LLM Step1: 도구 선택 + 플로우 결정
  ├── prompt_generator.py     # LLM Step2: 시스템 프롬프트 자동 생성 ★ NEW
  ├── workflow_compiler.py    # JSON workflow_definition → LangGraph 그래프
  ├── create_agent_use_case.py  # 에이전트 생성 (도구선택 + 프롬프트생성 + DB저장)
  ├── update_agent_use_case.py  # 시스템 프롬프트 수정 + name 수정 ★ NEW
  └── run_agent_use_case.py     # 에이전트 실행 오케스트레이션

infrastructure/agent_builder/
  ├── agent_definition_repository.py  # MySQL CRUD
  │                                   #   save()      → INSERT agent_definition + agent_tool (bulk)
  │                                   #   find_by_id()→ SELECT + JOIN agent_tool
  │                                   #   update()    → UPDATE agent_definition (system_prompt, name)
  │                                   #   list_by_user() → SELECT + JOIN
  └── tool_factory.py                 # tool_id → BaseTool 인스턴스

api/routes/
  └── agent_builder_router.py  # POST /agents, GET /agents/{id}, PATCH /agents/{id},
                               #   POST /agents/{id}/run, GET /agents/tools
```

---

## 6. 핵심 컴포넌트 상세

### 6.1 ToolSelector (application)

LLM이 사용자 요청을 분석하여 필요한 도구와 워크플로우 골격을 결정한다.

```
입력: "AI 관련 뉴스 검색하고 엑셀로 저장하는 에이전트 만들어줘"
      + TOOL_REGISTRY 정보 (각 도구 설명)
출력: WorkflowSkeleton (workers[], flow_hint)   ← supervisor_prompt 제외
```

- LLM에게 TOOL_REGISTRY 목록을 제공
- Structured Output (Pydantic) 으로 WorkflowSkeleton 강제 추출
- 모르는 tool_id는 선택하지 않도록 프롬프트 엔지니어링

### 6.2 PromptGenerator (application) ★ NEW

선택된 도구와 사용자 요청을 바탕으로 Supervisor용 시스템 프롬프트를 자동 생성한다.

```
입력: user_request + selected_tools (ToolMeta 목록)
출력: system_prompt (str)
```

**생성 원칙**:
- 에이전트의 목적을 1~2문장으로 명시
- 각 Worker(도구)의 역할과 사용 시점 안내
- 응답 언어, 포맷, 주의사항 포함
- 사용자가 수정하기 쉬운 구조화된 프롬프트 형태

**예시 출력**:
```
당신은 AI 뉴스 수집 전문 에이전트입니다.

[역할]
- Tavily 검색 워커: 최신 AI 관련 뉴스를 웹에서 검색합니다.
- Excel 내보내기 워커: 수집된 뉴스를 Excel 파일로 저장합니다.

[동작 원칙]
1. 항상 검색을 먼저 수행한 뒤 Excel 저장을 진행하세요.
2. 최소 5개 이상의 뉴스를 수집하세요.
3. 한국어로 응답하세요.
```

### 6.3 WorkflowCompiler (application)

DB에서 가져온 WorkflowDefinition JSON을 실제 LangGraph 그래프로 변환한다.

```
입력: WorkflowDefinition (JSON)
출력: CompiledGraph (실행 가능한 LangGraph)
```

```python
# 동작 방식
for worker_def in workflow.workers:
    tool = tool_factory.create(worker_def.tool_id)  # BaseTool 생성
    worker_agent = create_react_agent(llm, [tool])  # Worker ReAct 에이전트
    workers[worker_def.worker_id] = worker_agent

supervisor = create_supervisor(llm, workers, workflow.supervisor_prompt)
graph = supervisor.compile()
```

### 6.4 CreateAgentUseCase (application)

```
1. ToolSelector → workers[], flow_hint 결정 (LLM 호출 #1)
2. PromptGenerator → system_prompt 자동 생성 (LLM 호출 #2)
3. WorkflowDefinition 조립 (workers + flow_hint + supervisor_prompt=system_prompt)
4. AgentDefinition 도메인 객체 생성 (Policy 검증)
5. AgentDefinitionRepository.save() → MySQL
6. CreateAgentResponse 반환 (system_prompt 포함)
```

### 6.5 UpdateAgentUseCase (application) ★ NEW

```
1. AgentDefinitionRepository.find_by_id(agent_id) → 존재 확인
2. UpdateAgentPolicy 검증 (system_prompt 길이, status 확인)
3. 변경 필드 반영:
   - system_prompt → agent.system_prompt 갱신
   - system_prompt → workflow_definition.supervisor_prompt 동기화
   - name (optional) → agent.name 갱신
4. AgentDefinitionRepository.update() → MySQL
5. UpdateAgentResponse 반환
```

### 6.6 RunAgentUseCase (application)

```
1. AgentDefinitionRepository.find_by_id(agent_id) → MySQL에서 로드
   ※ DB의 system_prompt (사용자 최신 수정본) 사용
2. WorkflowCompiler.compile(workflow_definition) → LangGraph 그래프
   ※ workflow_definition.supervisor_prompt = 최신 system_prompt
3. graph.ainvoke(query) → 실행
4. RunAgentResponse 반환
```

---

## 7. 구현 순서 (TDD 엄수)

```
Phase 1 - Domain (No Mock)
  1. domain/agent_builder/schemas.py      (AgentDefinition, WorkflowDefinition,
                                           WorkerDefinition, WorkflowSkeleton)
  2. domain/agent_builder/tool_registry.py (TOOL_REGISTRY with 4 tools)
  3. domain/agent_builder/policies.py     (AgentBuilderPolicy, UpdateAgentPolicy)
  4. tests/domain/agent_builder/

Phase 2 - Infrastructure (Mock DB)
  5. infrastructure/agent_builder/tool_factory.py
  6. infrastructure/agent_builder/agent_definition_repository.py
     (save, find_by_id, update, list_by_user)
  7. tests/infrastructure/agent_builder/

Phase 3 - Application (Mock Infra)
  8. application/agent_builder/schemas.py
     (CreateAgentRequest/Response, UpdateAgentRequest/Response, RunAgentRequest/Response)
  9. application/agent_builder/tool_selector.py      (LLM Step1: 도구 선택)
 10. application/agent_builder/prompt_generator.py   (LLM Step2: 시스템 프롬프트 생성) ★
 11. application/agent_builder/workflow_compiler.py  (LangGraph 동적 컴파일)
 12. application/agent_builder/create_agent_use_case.py
 13. application/agent_builder/update_agent_use_case.py  ★
 14. application/agent_builder/run_agent_use_case.py
 15. tests/application/agent_builder/

Phase 4 - Interface
 16. api/routes/agent_builder_router.py
 17. tests/api/test_agent_builder_router.py
 18. main.py 라우터 등록
```

---

## 8. API 스펙 (5개 엔드포인트)

### POST /api/v1/agents — 에이전트 생성

**Request**
```json
{
  "user_request": "AI 관련 뉴스 검색하고 엑셀로 저장하는 에이전트 만들어줘",
  "name": "AI 뉴스 수집기",
  "user_id": "user-123",
  "model_name": "gpt-4o-mini"
}
```

**Response 200**
```json
{
  "agent_id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "AI 뉴스 수집기",
  "tool_ids": ["tavily_search", "excel_export"],
  "system_prompt": "당신은 AI 뉴스 수집 전문 에이전트입니다.\n\n[역할]\n- Tavily 검색 워커: ...\n- Excel 워커: ...",
  "workflow_definition": {
    "supervisor_prompt": "...",
    "workers": [...],
    "flow_hint": "..."
  },
  "created_at": "2026-03-20T10:00:00Z"
}
```
> `system_prompt`가 응답 최상위에 노출되어 사용자가 즉시 확인하고 수정 여부 결정 가능

---

### PATCH /api/v1/agents/{agent_id} — 에이전트 수정 ★ NEW

**Request** (모든 필드 optional — 변경할 필드만 전송)
```json
{
  "system_prompt": "당신은 AI 뉴스 수집 에이전트입니다.\n뉴스 제목, URL, 요약을 포함하여 저장하세요.\n영문 뉴스는 한국어로 번역하세요.",
  "name": "AI 뉴스 수집기 v2"
}
```

**Response 200**
```json
{
  "agent_id": "...",
  "name": "AI 뉴스 수집기 v2",
  "system_prompt": "당신은 AI 뉴스 수집 에이전트입니다.\n뉴스 제목, URL, 요약을 포함하여 저장하세요...",
  "updated_at": "2026-03-20T10:30:00Z"
}
```

**Error Cases**
- `404`: agent_id 없음
- `422`: system_prompt 4000자 초과
- `422`: status가 active가 아닌 경우

---

### GET /api/v1/agents/{agent_id} — 에이전트 조회

**Response 200**
```json
{
  "agent_id": "...",
  "name": "AI 뉴스 수집기 v2",
  "description": "AI 관련 뉴스 검색하고 엑셀로 저장하는 에이전트 만들어줘",
  "tool_ids": ["tavily_search", "excel_export"],
  "system_prompt": "당신은 AI 뉴스 수집 에이전트입니다...",
  "workflow_definition": { ... },
  "status": "active",
  "created_at": "2026-03-20T10:00:00Z",
  "updated_at": "2026-03-20T10:30:00Z"
}
```

---

### POST /api/v1/agents/{agent_id}/run — 에이전트 실행

**Request**
```json
{
  "query": "오늘 AI 뉴스 5개 수집해서 엑셀 저장해줘",
  "user_id": "user-123"
}
```

**Response 200**
```json
{
  "agent_id": "...",
  "query": "오늘 AI 뉴스 5개 수집해서 엑셀 저장해줘",
  "answer": "AI 뉴스 5개를 수집하여 /tmp/ai_news.xlsx에 저장했습니다.",
  "tools_used": ["tavily_search", "excel_export"],
  "request_id": "uuid"
}
```

---

### GET /api/v1/agents/tools — 사용 가능한 도구 목록

**Response 200**
```json
{
  "tools": [
    { "tool_id": "tavily_search",           "name": "Tavily 웹 검색",    "description": "최신 웹 정보 검색" },
    { "tool_id": "excel_export",            "name": "Excel 파일 생성",   "description": "데이터를 Excel 파일로 저장" },
    { "tool_id": "internal_document_search","name": "내부 문서 검색",    "description": "내부 벡터 DB에서 관련 문서 검색" },
    { "tool_id": "python_code_executor",    "name": "Python 코드 실행",  "description": "샌드박스에서 Python 코드 실행" }
  ]
}
```

---

## 9. 의존성 (Dependencies)

| 모듈 | 역할 |
|------|------|
| `MYSQL-001` | agent_definition + agent_tool 테이블 저장/조회 (JOIN) |
| `InternalDocumentSearchTool` | hybrid_search_use_case DI 필요 |
| `TavilySearchTool` | TAVILY_API_KEY 환경변수 필요 |
| `ExcelExportTool` | 별도 의존성 없음 |
| `CodeExecutorToolFactory` | LoggerInterface DI 필요 |
| `LangGraph Supervisor` | `langgraph-supervisor` 또는 `create_supervisor` 패턴 |
| `LOG-001` | 모든 서비스 로깅 필수 |

---

## 10. 테스트 계획

| 테스트 | 대상 | 방법 |
|--------|------|------|
| TOOL_REGISTRY 정합성 | domain | mock 없이 직접 |
| AgentBuilderPolicy 규칙 | domain | mock 없이 직접 |
| UpdateAgentPolicy 규칙 (길이, status) | domain | mock 없이 직접 |
| ToolFactory 도구 생성 | infra | Mock DI |
| AgentDefinitionRepository CRUD + update | infra | Mock DB |
| ToolSelector (LLM 도구 선택) | application | Mock LLM |
| PromptGenerator (프롬프트 생성) | application | Mock LLM ★ |
| WorkflowCompiler (그래프 생성) | application | Mock LangGraph |
| CreateAgentUseCase | application | Mock Infra |
| UpdateAgentUseCase | application | Mock Repo ★ |
| RunAgentUseCase | application | Mock Compiler + Repo |
| POST /agents API | interface | TestClient + Mock UseCase |
| PATCH /agents/{id} API | interface | TestClient + Mock UseCase ★ |
| GET /agents/{id} API | interface | TestClient + Mock UseCase |
| POST /agents/{id}/run API | interface | TestClient + Mock UseCase |

---

## 11. 완료 기준 (Definition of Done)

**에이전트 생성**
- [ ] POST /agents → LLM이 도구 자동 선택 + 시스템 프롬프트 자동 생성, DB 저장, agent_id + system_prompt 반환

**시스템 프롬프트 수정**
- [ ] PATCH /agents/{id} → system_prompt 수정 후 DB + workflow_definition 동기화
- [ ] PATCH /agents/{id} → name만 수정 가능
- [ ] system_prompt 4000자 초과 → 422 반환
- [ ] 존재하지 않는 agent_id PATCH → 404 반환

**에이전트 실행**
- [ ] POST /agents/{id}/run → DB에서 (수정된) system_prompt 로드, LangGraph 동적 컴파일, 실행, 응답 반환

**조회**
- [ ] GET /agents/tools → 4개 도구 목록 반환
- [ ] GET /agents/{id} → 저장된 에이전트 정의 + system_prompt 반환

**공통**
- [ ] 존재하지 않는 agent_id → 404 반환
- [ ] 전체 테스트 통과 (단위 + API)
- [ ] LOG-001 로깅 적용
- [ ] verify-architecture 통과

---

## 12. 관련 Task 파일

생성 예정: `src/claude/task/task-custom-agent-builder.md` (AGENT-004)
