# Plan: General Chat API (ReAct + 멀티턴 + MCP)

> Feature: general-chat-api
> Task ID: CHAT-001
> Created: 2026-04-12
> Status: Plan
> 의존성: RAG-001, CONV-001, MCP-001, MCP-REG-001, SEARCH-001, LANGSMITH-001, LOG-001

---

## 1. 목표

사용자의 일반 질문 채팅을 받아 LangGraph ReAct 에이전트가 자율적으로 도구를 선택·조합하여 응답하는 단일 채팅 API.

### 핵심 요구사항

| # | 요구사항 | 구현 방식 |
|---|---------|-----------|
| 1 | LangGraph ReAct 에이전트 오케스트레이션 | `create_react_agent` + 도구 목록 동적 주입 |
| 2 | 웹 검색 도구 | SEARCH-001 `TavilySearchTool` 재사용 |
| 3 | 내부 문서 검색 도구 | RAG-001 `InternalDocumentSearchTool` (BM25+Vector 5:5) 재사용 |
| 4 | MCP 도구 | MCP-REG-001 DB 등록 서버 → MCP-001 `MCPToolRegistry` 동적 로드 |
| 5 | 멀티턴 대화 메모리 | user_id + session_id 기반, CONV-001 `SummarizationPolicy` 재사용 |
| 6 | 대화 압축 | 6턴 초과 시 오래된 턴 요약 (CONV-001 정책 동일) |
| 7 | LangSmith 추적 | 컨트롤러 진입 시점에 `langsmith()` 주입 (LANGSMITH-001) |

---

## 2. API 스펙

```
POST /api/v1/chat
Content-Type: application/json
Authorization: Bearer {access_token}   ← AUTH-001 의존

Request Body:
{
    "user_id":    "string",       # 사용자 ID
    "session_id": "string",       # 대화 세션 ID (없으면 신규 세션)
    "message":    "string",       # 사용자 질문
    "top_k":      5               # 내부 문서 검색 top_k (optional, default 5)
}

Response:
{
    "user_id":        "string",
    "session_id":     "string",
    "answer":         "string",    # 에이전트 최종 응답
    "tools_used":     ["string"],  # 실제 호출된 도구 이름 목록
    "sources":        [            # 내부 문서 출처 (used_internal_docs=true 시)
        {
            "content":  "string",
            "source":   "string",
            "chunk_id": "string",
            "score":    0.032
        }
    ],
    "was_summarized": false,       # 대화 압축 여부
    "request_id":     "string"
}
```

---

## 3. 동작 흐름

```
POST /api/v1/chat
         │
         ▼
[Controller] langsmith(project_name="general-chat") 주입
         │
         ▼
[GeneralChatUseCase]
    │
    ├─ 1. 대화 히스토리 조회 (user_id + session_id)
    │       └─ ConversationMessageRepository (CONV-001 인프라 재사용)
    │
    ├─ 2. SummarizationPolicy 체크 (threshold=6)
    │       ├─ 6턴 이하 → 전체 히스토리 사용
    │       └─ 6턴 초과 → LLM 요약 → ConversationSummary 저장
    │                    → (요약본 + 최근 3턴)으로 컨텍스트 구성
    │
    ├─ 3. 도구 목록 동적 빌드
    │       ├─ TavilyWebSearchTool          (SEARCH-001)
    │       ├─ InternalDocumentSearchTool   (RAG-001)
    │       └─ MCP Tools                    (MCP-REG-001 DB → MCP-001 MCPToolRegistry)
    │
    ├─ 4. LangGraph ReAct 에이전트 실행
    │       └─ create_react_agent(llm, tools, messages=context_messages)
    │
    ├─ 5. 사용자 메시지 + 에이전트 응답 DB 저장
    │       └─ ConversationMessageRepository
    │
    └─ 6. GeneralChatResponse 반환
```

---

## 4. 아키텍처 (Thin DDD)

```
domain/general_chat/
├── schemas.py          # GeneralChatRequest, GeneralChatResponse, ToolUsageRecord
└── policies.py         # ChatAgentPolicy (max_iterations=10, tool_timeout=30s)

application/general_chat/
├── tools.py            # 도구 빌더 (Tavily + InternalDoc + MCP 통합)
└── use_case.py         # GeneralChatUseCase (ReAct 오케스트레이션 + 대화 메모리)

api/routes/
└── general_chat_router.py   # POST /api/v1/chat (LangSmith 주입 포함)
```

### 재사용 모듈 (수정 없음)

| 모듈 | Task ID | 재사용 방식 |
|------|---------|------------|
| `SummarizationPolicy` | CONV-001 | 6턴 초과 압축 판단 |
| `ConversationMessageRepository` | CONV-001 | 대화 저장/조회 |
| `ConversationSummarizerInterface` / `LangChainSummarizer` | CONV-001 | 오래된 턴 요약 |
| `InternalDocumentSearchTool` | RAG-001 | 내부 문서 BM25+Vector 검색 |
| `TavilySearchTool` | SEARCH-001 | 실시간 웹 검색 |
| `MCPToolRegistry` / `MCPClientFactory` | MCP-001 | MCP Tool → LangChain Tool 변환 |
| `LoadMCPToolsUseCase` | MCP-REG-001 | DB 등록 MCP 서버 동적 로드 |
| `langsmith()` | LANGSMITH-001 | LangSmith 추적 활성화 |

---

## 5. 핵심 설계 결정

### 5-1. LangSmith 주입 위치: 컨트롤러

```python
# api/routes/general_chat_router.py
@router.post("/chat")
async def chat(request: GeneralChatRequest):
    langsmith(project_name="general-chat")   # ← 여기서 주입
    return await use_case.execute(request)
```

요청마다 LangSmith 세션이 열리므로 실제 도구 호출 흐름을 추적 가능.

### 5-2. 도구 목록 빌드 전략

매 요청 시 MCP 도구를 DB에서 로드하면 레이턴시 증가 → **10분 TTL 인메모리 캐시** 적용.
- `MCPToolCache`: 서버별 Tool 목록, 10분 만료 시 재로드
- `ChatAgentPolicy.MCP_CACHE_TTL_SECONDS = 600`

### 5-3. 대화 컨텍스트 → ReAct 에이전트 주입 방식

LangGraph `create_react_agent`의 `messages` 파라미터에 직접 주입.

```python
# 컨텍스트 메시지 구성
context_messages = []
if summary:
    context_messages.append(SystemMessage(content=f"[이전 대화 요약]\n{summary}"))
for msg in recent_turns:
    context_messages.append(HumanMessage(content=msg.content) if msg.role == "user"
                            else AIMessage(content=msg.content))
context_messages.append(HumanMessage(content=user_message))

agent = create_react_agent(llm, tools)
result = await agent.ainvoke({"messages": context_messages})
```

### 5-4. 도구 사용 추적

에이전트 응답의 중간 메시지(`ToolMessage`)를 파싱하여 `tools_used` 목록 수집.
내부 문서 검색 결과가 있으면 `sources` 필드로 반환.

---

## 6. 구현 순서 (TDD)

### Step 1. Domain Schema & Policy (Mock 금지)
- `tests/domain/general_chat/test_schemas.py` → `src/domain/general_chat/schemas.py`
- `tests/domain/general_chat/test_policies.py` → `src/domain/general_chat/policies.py`

### Step 2. Application Tools Builder
- `tests/application/general_chat/test_tools.py` → `src/application/general_chat/tools.py`
  - TavilyTool, InternalDocTool, MCPTools 통합 빌더

### Step 3. GeneralChatUseCase
- `tests/application/general_chat/test_use_case.py` → `src/application/general_chat/use_case.py`
  - 대화 히스토리 조회/저장
  - 압축 정책 적용
  - ReAct 에이전트 실행
  - 응답 파싱

### Step 4. API Router
- `tests/api/test_general_chat_router.py` → `src/api/routes/general_chat_router.py`
  - LangSmith 주입
  - DI 연결
  - `src/api/main.py` 라우터 등록

---

## 7. 테스트 계획

| 파일 | 케이스 수 | 비고 |
|------|----------|------|
| `tests/domain/general_chat/test_schemas.py` | 6 | mock 금지 |
| `tests/domain/general_chat/test_policies.py` | 4 | mock 금지 |
| `tests/application/general_chat/test_tools.py` | 8 | AsyncMock |
| `tests/application/general_chat/test_use_case.py` | 12 | AsyncMock |
| `tests/api/test_general_chat_router.py` | 8 | UseCase mock |
| **합계** | **38** | |

---

## 8. 의존성 Task 매핑

| Task ID | 파일 | 사용 목적 |
|---------|------|----------|
| CONV-001 | task-conversation.md | 대화 메모리 (엔티티, 정책, 저장소) |
| RAG-001 | task-rag-agent-api.md | InternalDocumentSearchTool |
| SEARCH-001 | task-tavily-search.md | TavilySearchTool |
| MCP-001 | task-mcp-client.md | MCPToolRegistry, MCPClientFactory |
| MCP-REG-001 | task-mcp-registry.md | DB 등록 MCP 서버 동적 로드 |
| LANGSMITH-001 | task-langsmith.md | langsmith() 추적 함수 |
| LOG-001 | task-logging.md | LoggerInterface, 로깅 규칙 |

---

## 9. 환경변수

```env
# 기존 변수 (변경 없음)
TAVILY_API_KEY=...
OPENAI_API_KEY=...
LANGCHAIN_API_KEY=...      # LangSmith 추적용

# 신규
CHAT_MCP_CACHE_TTL=600     # MCP Tool 캐시 TTL (초), 기본 600
CHAT_MAX_ITERATIONS=10     # ReAct 에이전트 최대 반복 수
```

---

## 10. 완료 기준

- [ ] `POST /api/v1/chat` 엔드포인트 동작
- [ ] Tavily 웹 검색 도구 정상 호출
- [ ] 내부 문서 하이브리드 검색 (BM25+Vector) 정상 호출
- [ ] MCP 도구 동적 로드 및 정상 호출
- [ ] 6턴 초과 시 대화 자동 압축 후 응답
- [ ] LangSmith 대시보드에서 도구 호출 흐름 추적 확인
- [ ] 전체 38 테스트 통과
- [ ] LOG-001 로깅 규칙 준수
