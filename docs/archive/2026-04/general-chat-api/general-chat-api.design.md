# Design: General Chat API (ReAct + 멀티턴 + MCP)

> Feature: general-chat-api
> Task ID: CHAT-001
> Created: 2026-04-12
> Phase: Design
> Reference Plan: docs/01-plan/features/general-chat-api.plan.md
> 의존성: RAG-001, CONV-001, MCP-001, MCP-REG-001, SEARCH-001, LANGSMITH-001, LOG-001

---

## 1. 생성/수정할 파일 목록

| 파일 경로 | 작업 | 우선순위 |
|-----------|------|----------|
| `src/domain/general_chat/schemas.py` | 신규 생성 | 필수 |
| `src/domain/general_chat/policies.py` | 신규 생성 | 필수 |
| `src/application/general_chat/tools.py` | 신규 생성 | 필수 |
| `src/application/general_chat/use_case.py` | 신규 생성 | 필수 |
| `src/api/routes/general_chat_router.py` | 신규 생성 | 필수 |
| `src/api/main.py` | 라우터 등록 (수정) | 필수 |
| `src/claude/task/task-general-chat-api.md` | 신규 생성 | 필수 |
| `tests/domain/general_chat/test_schemas.py` | 신규 생성 | 필수 |
| `tests/domain/general_chat/test_policies.py` | 신규 생성 | 필수 |
| `tests/application/general_chat/test_tools.py` | 신규 생성 | 필수 |
| `tests/application/general_chat/test_use_case.py` | 신규 생성 | 필수 |
| `tests/api/test_general_chat_router.py` | 신규 생성 | 필수 |

---

## 2. 파일별 상세 설계

---

### 파일 1: `src/domain/general_chat/schemas.py`

**목적**: GeneralChatAPI의 요청/응답 타입 정의 (Pydantic 기반)

**설계 원칙**:
- domain 레이어 → 외부 의존성 없음
- Pydantic BaseModel 사용

**클래스 설계**:

```python
class ToolUsageRecord(BaseModel):
    tool_name: str
    tool_input: dict
    tool_output: str

class DocumentSource(BaseModel):
    content: str
    source: str
    chunk_id: str
    score: float

class GeneralChatRequest(BaseModel):
    user_id: str
    session_id: str | None = None   # None이면 서버에서 UUID 신규 발급
    message: str
    top_k: int = 5

class GeneralChatResponse(BaseModel):
    user_id: str
    session_id: str
    answer: str
    tools_used: list[str]
    sources: list[DocumentSource]
    was_summarized: bool
    request_id: str
```

---

### 파일 2: `src/domain/general_chat/policies.py`

**목적**: 에이전트 동작 정책 상수 정의

**설계 원칙**:
- 하드코딩 금지 → 환경변수 우선, 기본값 fallback

```python
import os

class ChatAgentPolicy:
    MAX_ITERATIONS: int = int(os.getenv("CHAT_MAX_ITERATIONS", "10"))
    TOOL_TIMEOUT_SECONDS: int = 30
    MCP_CACHE_TTL_SECONDS: int = int(os.getenv("CHAT_MCP_CACHE_TTL", "600"))
    SUMMARIZATION_THRESHOLD: int = 6   # CONV-001 정책 동일
    RECENT_TURNS_CONTEXT: int = 3       # 요약 후 최근 N턴만 사용
```

---

### 파일 3: `src/application/general_chat/tools.py`

**목적**: ReAct 에이전트에 주입할 LangChain Tool 목록 빌드

**설계 원칙**:
- 3종 도구 통합: Tavily, InternalDoc, MCP
- MCP Tool은 10분 TTL 인메모리 캐시 적용
- 기존 모듈 수정 없음 — 래핑 전략

**클래스 설계**:

```python
class MCPToolCache:
    """MCP Tool 목록을 TTL 기반으로 캐시"""
    _cache: dict[str, tuple[list, float]] = {}   # server_id → (tools, expires_at)

    @classmethod
    async def get_or_load(
        cls,
        load_mcp_use_case: LoadMCPToolsUseCase,
        ttl: int = ChatAgentPolicy.MCP_CACHE_TTL_SECONDS,
    ) -> list:
        """캐시 미스 시 DB에서 MCP 서버 목록 로드"""
        ...

class ChatToolBuilder:
    """도구 빌더 — 재사용 모듈 조합"""

    def __init__(
        self,
        tavily_tool: TavilySearchTool,              # SEARCH-001
        internal_doc_tool: InternalDocumentSearchTool,  # RAG-001
        mcp_cache: MCPToolCache,
        load_mcp_use_case: LoadMCPToolsUseCase,     # MCP-REG-001
    ):
        ...

    async def build(self, top_k: int) -> list:
        """[TavilyTool, InternalDocTool, *MCPTools] 반환"""
        ...
```

---

### 파일 4: `src/application/general_chat/use_case.py`

**목적**: ReAct 에이전트 오케스트레이션 + 대화 메모리 관리

**설계 원칙**:
- `GeneralChatUseCase.execute(request)` 단일 진입점
- CONV-001 재사용 → `SummarizationPolicy`, `ConversationMessageRepository`, `LangChainSummarizer`
- 도구 추적 → ToolMessage 파싱으로 `tools_used`, `sources` 추출

**실행 흐름**:

```
execute(request: GeneralChatRequest) → GeneralChatResponse
  │
  ├─ 1. session_id 확보 (None이면 uuid4 신규 발급)
  │
  ├─ 2. 대화 히스토리 조회
  │       ConversationMessageRepository.find_by_session(user_id, session_id)
  │
  ├─ 3. SummarizationPolicy.should_summarize(turn_count)
  │       True  → LangChainSummarizer.summarize(old_turns) 후 DB 저장
  │               context = [SystemMessage(summary)] + recent_3_turns
  │       False → context = all_turns
  │
  ├─ 4. ChatToolBuilder.build(top_k) → tools
  │
  ├─ 5. create_react_agent(llm, tools).ainvoke({"messages": context + [HumanMessage]})
  │
  ├─ 6. 응답 파싱
  │       - 최종 AIMessage → answer
  │       - ToolMessage 목록 → tools_used, sources
  │
  ├─ 7. 사용자 메시지 + AI 응답 DB 저장
  │       ConversationMessageRepository.save_turn(user_msg, ai_msg)
  │
  └─ 8. GeneralChatResponse 반환
```

**메서드 시그니처**:

```python
class GeneralChatUseCase:
    def __init__(
        self,
        chat_tool_builder: ChatToolBuilder,
        message_repo: ConversationMessageRepository,   # CONV-001
        summarizer: ConversationSummarizerInterface,   # CONV-001
        summarization_policy: SummarizationPolicy,     # CONV-001
        llm: ChatOpenAI,
        logger: LoggerInterface,                        # LOG-001
    ): ...

    async def execute(self, request: GeneralChatRequest) -> GeneralChatResponse: ...

    def _build_context_messages(
        self, history: list, summary: str | None
    ) -> list: ...

    def _parse_agent_output(
        self, messages: list
    ) -> tuple[str, list[str], list[DocumentSource]]: ...
```

---

### 파일 5: `src/api/routes/general_chat_router.py`

**목적**: FastAPI 라우터 — LangSmith 주입 + DI 연결

**설계 원칙**:
- 비즈니스 로직 없음 (인터페이스 레이어 규칙)
- LangSmith 주입 위치: 엔드포인트 함수 진입 직후
- JWT 인증: AUTH-001 `get_current_user` Dependency 사용

```python
router = APIRouter(prefix="/api/v1", tags=["chat"])

@router.post("/chat", response_model=GeneralChatResponse)
async def general_chat(
    body: GeneralChatRequest,
    current_user: User = Depends(get_current_user),    # AUTH-001
    use_case: GeneralChatUseCase = Depends(get_general_chat_use_case),
):
    langsmith(project_name="general-chat")             # LANGSMITH-001
    return await use_case.execute(body)
```

**DI 팩토리** (`get_general_chat_use_case`):

```python
def get_general_chat_use_case() -> GeneralChatUseCase:
    return GeneralChatUseCase(
        chat_tool_builder=ChatToolBuilder(...),
        message_repo=ConversationMessageRepository(...),
        summarizer=LangChainSummarizer(...),
        summarization_policy=SummarizationPolicy(),
        llm=ChatOpenAI(model="gpt-4o"),
        logger=StructuredLogger(__name__),
    )
```

---

## 3. 재사용 모듈 매핑 (수정 없음)

| 모듈 클래스 | Task ID | 위치 |
|------------|---------|------|
| `SummarizationPolicy` | CONV-001 | `src/application/conversation/` |
| `ConversationMessageRepository` | CONV-001 | `src/infrastructure/conversation/` |
| `ConversationSummarizerInterface` / `LangChainSummarizer` | CONV-001 | `src/infrastructure/conversation/` |
| `InternalDocumentSearchTool` | RAG-001 | `src/application/rag/` |
| `TavilySearchTool` | SEARCH-001 | `src/infrastructure/search/` |
| `MCPToolRegistry` / `MCPClientFactory` | MCP-001 | `src/infrastructure/mcp/` |
| `LoadMCPToolsUseCase` | MCP-REG-001 | `src/application/mcp_registry/` |
| `langsmith()` | LANGSMITH-001 | `src/infrastructure/langsmith/` |
| `StructuredLogger` | LOG-001 | `src/infrastructure/logging/` |

---

## 4. 테스트 설계

### `tests/domain/general_chat/test_schemas.py` (6 케이스)

| # | 케이스 | 검증 포인트 |
|---|--------|------------|
| 1 | GeneralChatRequest 기본값 검증 | top_k=5, session_id=None |
| 2 | GeneralChatRequest 필수 필드 누락 | ValidationError 발생 |
| 3 | DocumentSource 필드 타입 검증 | score: float |
| 4 | GeneralChatResponse 직렬화 | JSON 변환 정상 |
| 5 | ToolUsageRecord 빈 dict 허용 | tool_input={} 가능 |
| 6 | GeneralChatResponse tools_used 빈 리스트 | 정상 허용 |

### `tests/domain/general_chat/test_policies.py` (4 케이스)

| # | 케이스 | 검증 포인트 |
|---|--------|------------|
| 1 | ChatAgentPolicy.MAX_ITERATIONS 기본값 | 10 |
| 2 | 환경변수 CHAT_MAX_ITERATIONS 오버라이드 | int 변환 정상 |
| 3 | ChatAgentPolicy.MCP_CACHE_TTL_SECONDS 기본값 | 600 |
| 4 | SUMMARIZATION_THRESHOLD 값 | 6 |

### `tests/application/general_chat/test_tools.py` (8 케이스)

| # | 케이스 | 검증 포인트 |
|---|--------|------------|
| 1 | MCPToolCache 캐시 미스 → load 호출 | AsyncMock |
| 2 | MCPToolCache 캐시 히트 → load 미호출 | AsyncMock |
| 3 | MCPToolCache TTL 만료 → 재로드 | time.time() 패치 |
| 4 | ChatToolBuilder.build() 도구 3종 반환 | 타입 검증 |
| 5 | MCP 도구 0개일 때 Tavily+InternalDoc 반환 | 2개 도구 |
| 6 | InternalDocTool top_k 파라미터 전달 | kwargs 검증 |
| 7 | MCP 로드 예외 시 로그 WARNING + 빈 리스트 | logger mock |
| 8 | ChatToolBuilder 도구 순서 | Tavily→InternalDoc→MCP |

### `tests/application/general_chat/test_use_case.py` (12 케이스)

| # | 케이스 | 검증 포인트 |
|---|--------|------------|
| 1 | session_id=None → uuid4 신규 발급 | str 타입 |
| 2 | 히스토리 조회 후 컨텍스트 구성 | message_repo.find_by_session 호출 |
| 3 | 6턴 이하 → 요약 미실행 | summarizer.summarize 미호출 |
| 4 | 6턴 초과 → 요약 실행 + DB 저장 | summarizer.summarize 호출 |
| 5 | 요약 후 컨텍스트 = SystemMessage + 최근 3턴 | context 길이 검증 |
| 6 | ReAct 에이전트 ainvoke 호출 | AsyncMock |
| 7 | tools_used 파싱 (ToolMessage 포함) | 도구명 리스트 |
| 8 | sources 파싱 (InternalDoc 결과) | DocumentSource 리스트 |
| 9 | 사용자 메시지 DB 저장 확인 | message_repo.save 호출 |
| 10 | AI 응답 DB 저장 확인 | message_repo.save 호출 |
| 11 | was_summarized=True 시 응답 필드 | True 반환 |
| 12 | 에이전트 예외 시 ERROR 로그 + 재발생 | logger.error 호출 |

### `tests/api/test_general_chat_router.py` (8 케이스)

| # | 케이스 | 검증 포인트 |
|---|--------|------------|
| 1 | POST /api/v1/chat 200 정상 응답 | UseCase mock |
| 2 | 인증 헤더 누락 → 401 | get_current_user 의존성 |
| 3 | 필수 필드 message 누락 → 422 | Pydantic 검증 |
| 4 | LangSmith langsmith() 호출 확인 | mock 패치 |
| 5 | top_k 기본값 5 사용 | UseCase 인자 검증 |
| 6 | session_id 응답 포함 확인 | response body |
| 7 | tools_used 빈 배열 응답 | 정상 직렬화 |
| 8 | sources 빈 배열 응답 | 정상 직렬화 |

---

## 5. 구현 순서 (TDD)

```
Step 1. Domain Layer (Mock 금지)
  → test_schemas.py 작성 → 실패 확인 → schemas.py 구현 → 통과 확인
  → test_policies.py 작성 → 실패 확인 → policies.py 구현 → 통과 확인

Step 2. Application Tools Builder
  → test_tools.py 작성 → 실패 확인 → tools.py 구현 → 통과 확인

Step 3. Application Use Case
  → test_use_case.py 작성 → 실패 확인 → use_case.py 구현 → 통과 확인

Step 4. API Router
  → test_general_chat_router.py 작성 → 실패 확인
  → general_chat_router.py 구현
  → src/api/main.py 라우터 등록
  → 통과 확인

Step 5. /verify-implementation 실행 (통합 검증)
```

---

## 6. 환경변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `CHAT_MAX_ITERATIONS` | 10 | ReAct 에이전트 최대 반복 수 |
| `CHAT_MCP_CACHE_TTL` | 600 | MCP Tool 캐시 TTL (초) |

> 기존 `TAVILY_API_KEY`, `OPENAI_API_KEY`, `LANGCHAIN_API_KEY` 변경 없음

---

## 7. 검증 기준 (완료 조건)

| 항목 | 검증 방법 |
|------|----------|
| POST /api/v1/chat 엔드포인트 동작 | uvicorn 실행 후 curl 테스트 |
| 전체 38 테스트 통과 | `pytest tests/ -v` |
| LangSmith 흐름 추적 확인 | LangSmith 대시보드 |
| 6턴 초과 대화 압축 동작 | 통합 테스트 |
| LOG-001 로깅 규칙 준수 | `/verify-logging` |
| DDD 레이어 의존성 준수 | `/verify-architecture` |
| TDD 테스트 파일 존재 | `/verify-tdd` |
