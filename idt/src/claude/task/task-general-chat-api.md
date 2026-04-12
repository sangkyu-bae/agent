# CHAT-001: General Chat API (ReAct + 멀티턴 + MCP)

> 상태: 설계 완료
> 의존성: RAG-001, CONV-001, MCP-001, MCP-REG-001, SEARCH-001, LANGSMITH-001, LOG-001, AUTH-001

---

## 개요

사용자의 일반 질문을 받아 LangGraph ReAct 에이전트가 Tavily 웹 검색 / 내부 문서 검색(BM25+Vector) / MCP 도구를 자율적으로 선택·조합하여 응답하는 단일 채팅 API.  
멀티턴 대화 메모리(6턴 초과 시 자동 요약)와 LangSmith 추적을 포함한다.

---

## API 스펙

```
POST /api/v1/chat
Authorization: Bearer {access_token}

Request Body:
{
    "user_id":    "string",
    "session_id": "string | null",  # null이면 서버에서 UUID 신규 발급
    "message":    "string",
    "top_k":      5                 # optional, 내부 문서 검색 top_k
}

Response:
{
    "user_id":        "string",
    "session_id":     "string",
    "answer":         "string",
    "tools_used":     ["string"],
    "sources":        [{"content": "string", "source": "string", "chunk_id": "string", "score": 0.0}],
    "was_summarized": false,
    "request_id":     "string"
}
```

---

## 동작 흐름

```
POST /api/v1/chat
  │
  ├─ [Router] langsmith(project_name="general-chat") 주입
  │
  └─ [GeneralChatUseCase.execute()]
       ├─ 1. session_id 확보 (None → uuid4 신규)
       ├─ 2. 대화 히스토리 조회 (ConversationMessageRepository)
       ├─ 3. SummarizationPolicy 체크 (threshold=6)
       │       ├─ 6턴 이하 → 전체 히스토리 컨텍스트
       │       └─ 6턴 초과 → LLM 요약 → DB 저장 → (요약 + 최근 3턴) 컨텍스트
       ├─ 4. ChatToolBuilder.build(top_k)
       │       → [TavilySearchTool, InternalDocumentSearchTool, *MCPTools]
       ├─ 5. create_react_agent(llm, tools).ainvoke(messages=context)
       ├─ 6. 응답 파싱 (ToolMessage → tools_used, sources)
       ├─ 7. 사용자 메시지 + AI 응답 DB 저장
       └─ 8. GeneralChatResponse 반환
```

---

## 파일 구조

```
src/
├── domain/general_chat/
│   ├── schemas.py          # GeneralChatRequest, GeneralChatResponse, DocumentSource, ToolUsageRecord
│   └── policies.py         # ChatAgentPolicy (MAX_ITERATIONS, MCP_CACHE_TTL_SECONDS, SUMMARIZATION_THRESHOLD)
├── application/general_chat/
│   ├── tools.py            # MCPToolCache, ChatToolBuilder
│   └── use_case.py         # GeneralChatUseCase
└── api/routes/
    └── general_chat_router.py   # POST /api/v1/chat

tests/
├── domain/general_chat/
│   ├── test_schemas.py     # 6 케이스 (mock 금지)
│   └── test_policies.py    # 4 케이스 (mock 금지)
├── application/general_chat/
│   ├── test_tools.py       # 8 케이스 (AsyncMock)
│   └── test_use_case.py    # 12 케이스 (AsyncMock)
└── api/
    └── test_general_chat_router.py  # 8 케이스 (UseCase mock)
```

---

## 재사용 모듈 (수정 없음)

| 클래스 | Task ID | 용도 |
|--------|---------|------|
| `SummarizationPolicy` | CONV-001 | 6턴 초과 압축 판단 |
| `ConversationMessageRepository` | CONV-001 | 대화 저장/조회 |
| `LangChainSummarizer` | CONV-001 | 오래된 턴 요약 |
| `InternalDocumentSearchTool` | RAG-001 | BM25+Vector 내부 문서 검색 |
| `TavilySearchTool` | SEARCH-001 | 실시간 웹 검색 |
| `MCPToolRegistry` / `MCPClientFactory` | MCP-001 | MCP → LangChain Tool |
| `LoadMCPToolsUseCase` | MCP-REG-001 | DB 등록 MCP 서버 동적 로드 |
| `langsmith()` | LANGSMITH-001 | LangSmith 추적 |
| `StructuredLogger` | LOG-001 | 구조화 로깅 |

---

## 핵심 설계 결정

### MCP 도구 캐시 (MCPToolCache)
매 요청 시 MCP 서버를 DB에서 로드하면 레이턴시 증가 → **10분 TTL 인메모리 캐시** 적용.  
만료 시 자동 재로드, 실패 시 WARNING 로그 + 빈 리스트 반환 (서비스 중단 방지).

### 대화 컨텍스트 구성
```python
context = []
if summary:
    context.append(SystemMessage(content=f"[이전 대화 요약]\n{summary}"))
for msg in recent_turns:    # 최근 3턴
    context.append(HumanMessage(...) or AIMessage(...))
context.append(HumanMessage(content=user_message))
```

### 도구 사용 추적
에이전트 응답의 `ToolMessage`를 파싱하여 `tools_used` 목록 수집.  
`InternalDocumentSearchTool` 결과는 `sources` 필드로 별도 반환.

---

## 환경변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `CHAT_MAX_ITERATIONS` | 10 | ReAct 에이전트 최대 반복 수 |
| `CHAT_MCP_CACHE_TTL` | 600 | MCP Tool 캐시 TTL (초) |

---

## 로깅 체크리스트 (LOG-001)

- [x] `LoggerInterface` 주입 받아 사용
- [x] UseCase 진입/완료 INFO 로그 (request_id 포함)
- [x] 에이전트 예외 시 ERROR 로그 + 스택 트레이스
- [x] MCP 도구 로드 실패 시 WARNING 로그
- [x] 민감 정보 마스킹 (access_token 헤더 제외)

---

## 완료 기준

- [ ] `POST /api/v1/chat` 엔드포인트 정상 동작
- [ ] 전체 38 테스트 통과 (`pytest tests/ -v`)
- [ ] LangSmith 대시보드에서 도구 호출 흐름 추적 확인
- [ ] 6턴 초과 대화 자동 압축 동작 확인
- [ ] `/verify-logging` 통과
- [ ] `/verify-architecture` 통과
- [ ] `/verify-tdd` 통과
