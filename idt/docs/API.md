# IDT API 문서

> 자동 생성 일시: 2026-03-28
> Base URL: `http://localhost:8000`
> FastAPI 내장 문서: http://localhost:8000/docs

---

## 목차

| 태그 | 설명 |
|------|------|
| [documents](#documents) | PDF 문서 업로드 및 처리 |
| [ingest](#ingest) | PDF 파싱 + 청킹 + 벡터 저장 |
| [doc-chunk](#doc-chunk) | 청킹 결과 미리보기 |
| [excel](#excel) | Excel 업로드 / 내보내기 |
| [Excel Analysis](#excel-analysis) | Excel AI 분석 |
| [PDF Export](#pdf-export) | HTML → PDF 변환 |
| [retrieval](#retrieval) | 벡터 유사도 문서 검색 |
| [hybrid-search](#hybrid-search) | BM25 + Vector 하이브리드 검색 |
| [chunk-index](#chunk-index) | 청킹 + ES 키워드 색인 |
| [morph-index](#morph-index) | 형태소 분석 + 이중 색인 |
| [rag-agent](#rag-agent) | ReAct RAG Agent 질의응답 |
| [conversation](#conversation) | Multi-Turn 대화 메모리 |
| [Agent Builder](#agent-builder) | Custom Agent CRUD + 실행 |
| [middleware-agent](#middleware-agent) | Middleware Agent (v2) |
| [auto-agent-builder](#auto-agent-builder) | 자연어 자동 에이전트 빌더 (v3) |
| [MCP Registry](#mcp-registry) | MCP 서버 동적 등록 관리 |

---

## documents

### `POST /api/v1/documents/upload`

**설명**: PDF를 LangGraph 워크플로우로 처리합니다.
파싱 → 카테고리 분류 → Parent/Child 청킹 → Qdrant 벡터 저장

**Content-Type**: `multipart/form-data`

#### Query Parameters
| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|---------|------|------|--------|------|
| user_id | string | ✅ | - | 문서 소유자 ID |
| child_chunk_size | integer | ❌ | 500 | Child 청크 크기 (토큰, 100–4000) |

#### Request Body
| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| file | binary | ✅ | 업로드할 PDF 파일 |

#### Response `200`
```json
{
  "document_id": "doc-uuid-1234",
  "filename": "policy.pdf",
  "category": "finance",
  "category_confidence": 0.92,
  "total_pages": 10,
  "chunk_count": 42,
  "stored_ids": ["id1", "id2"],
  "status": "success",
  "errors": []
}
```

#### 에러 응답
| 코드 | 설명 |
|------|------|
| 500 | 문서 처리 실패 |

---

### `POST /api/v1/documents/upload/async`

**설명**: PDF를 비동기 큐에 등록합니다.

#### Query Parameters
| 파라미터 | 타입 | 필수 | 설명 |
|---------|------|------|------|
| user_id | string | ✅ | 문서 소유자 ID |

#### Response `200`
```json
{
  "task_id": "task-uuid-5678",
  "status": "pending",
  "message": "Document queued for processing"
}
```

---

### `GET /api/v1/documents/upload/status/{task_id}`

**설명**: 비동기 업로드 작업 상태를 조회합니다.

#### Path Parameters
| 파라미터 | 타입 | 설명 |
|---------|------|------|
| task_id | string | 작업 ID |

#### Response `200`
```json
{
  "task_id": "task-uuid-5678",
  "status": "pending",
  "result": null,
  "error": null
}
```

#### 에러 응답
| 코드 | 설명 |
|------|------|
| 404 | 작업을 찾을 수 없음 |

---

## ingest

### `POST /api/v1/ingest/pdf`

**설명**: PDF 파싱 + 청킹 + 임베딩 + Qdrant 저장 통합 API.
파서(pymupdf/llamaparser)와 청킹 전략을 선택할 수 있습니다.

**Content-Type**: `multipart/form-data`

#### Query Parameters
| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|---------|------|------|--------|------|
| user_id | string | ✅ | - | 소유자 ID |
| parser_type | string | ❌ | pymupdf | `pymupdf` (빠름) / `llamaparser` (OCR/AI) |
| chunking_strategy | string | ❌ | full_token | `full_token` / `parent_child` / `semantic` |
| chunk_size | integer | ❌ | 1000 | 토큰 수 (100–8000) |
| chunk_overlap | integer | ❌ | 100 | 청크 간 겹침 (0–500) |

#### Request Body
| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| file | binary | ✅ | 업로드할 PDF 파일 |

---

## doc-chunk

### `POST /api/v1/doc-chunk/upload`

**설명**: 파일을 청킹하고 결과만 반환합니다 (벡터 저장 없음).
지원 형식: `.pdf`, `.xlsx`, `.xls`, `.txt`, `.md`

**Content-Type**: `multipart/form-data`

#### Query Parameters
| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|---------|------|------|--------|------|
| user_id | string | ✅ | - | 사용자 ID |
| strategy_type | string | ❌ | parent_child | `full_token` / `parent_child` / `semantic` |
| chunk_size | integer | ❌ | 500 | 토큰 수 (100–8000) |
| chunk_overlap | integer | ❌ | 50 | 청크 간 겹침 (0–500) |

#### 에러 응답
| 코드 | 설명 |
|------|------|
| 422 | 지원하지 않는 파일 형식 또는 전략 |

---

## excel

### `POST /api/v1/excel/upload`

**설명**: Excel 파일을 업로드하고 벡터 저장소에 색인합니다.

**Content-Type**: `multipart/form-data`

#### Query Parameters
| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|---------|------|------|--------|------|
| user_id | string | ✅ | - | 사용자 ID |
| strategy_type | string | ❌ | full_token | `full_token` / `parent_child` / `semantic` |

---

### `POST /api/v1/excel/export`

**설명**: 테이블 데이터를 Excel 파일(`.xlsx`)로 변환하여 다운로드합니다.

#### Request Body
```json
{
  "filename": "result.xlsx",
  "user_id": "user-001",
  "sheets": [
    {
      "sheet_name": "Sales",
      "columns": ["Name", "Amount", "Date"],
      "rows": [
        ["Alice", 1000, "2026-01-01"],
        ["Bob", 2000, "2026-01-02"]
      ]
    }
  ]
}
```

#### Response `200`
- Content-Type: `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`
- 파일 다운로드 응답

---

## Excel Analysis

### `POST /api/v1/analysis/excel`

**설명**: Excel 파일을 Claude AI로 분석합니다.
파싱 → Claude AI 분석 → 할루시네이션 검증 → (필요 시 웹 검색/코드 실행) → 최대 3회 재시도

**Content-Type**: `multipart/form-data`

#### Request Body
| 필드 | 타입 | 필수 | 기본값 | 설명 |
|------|------|------|--------|------|
| file | binary | ✅ | - | Excel 파일 |
| query | string | ✅ | - | 분석 질문 |
| user_id | string | ❌ | anonymous | 사용자 ID |

#### Response `200`
```json
{
  "request_id": "req-uuid-1234",
  "query": "월별 매출 추이를 분석해주세요",
  "final_answer": "1월 대비 3월 매출이 23% 증가하였으며...",
  "is_successful": true,
  "total_attempts": 2,
  "attempts": [
    {
      "attempt_number": 1,
      "confidence_score": 0.75,
      "hallucination_score": 0.3,
      "used_web_search": false,
      "timestamp": "2026-03-28T10:00:00Z"
    }
  ],
  "executed_code": "import pandas as pd\n...",
  "code_output": {"result": "..."}
}
```

---

## PDF Export

### `POST /api/v1/pdf/export`

**설명**: HTML 콘텐츠를 PDF 파일로 변환하여 다운로드합니다.

#### Request Body
```json
{
  "html_content": "<h1>Report</h1><p>Content here</p>",
  "filename": "report.pdf",
  "user_id": "user-001",
  "css_content": "h1 { color: navy; }",
  "base_url": null
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| html_content | string | ✅ | 변환할 HTML |
| filename | string | ❌ | 다운로드 파일명 (기본: output.pdf) |
| user_id | string | ✅ | 사용자 ID |
| css_content | string | ❌ | 추가 CSS |
| base_url | string | ❌ | 상대 경로 기준 URL |

#### Response `200`
- Content-Type: `application/pdf`
- 파일 다운로드 응답

---

## retrieval

### `POST /api/v1/retrieval/search`

**설명**: RAG 파이프라인으로 문서를 검색합니다.
옵션: 쿼리 재작성, LLM 압축, Parent 문서 컨텍스트 보강

#### Request Body
```json
{
  "query": "금융 규정 위반 시 제재 기준은?",
  "user_id": "user-001",
  "top_k": 10,
  "document_id": null,
  "use_query_rewrite": false,
  "use_compression": true,
  "use_parent_context": true
}
```

| 필드 | 타입 | 필수 | 기본값 | 설명 |
|------|------|------|--------|------|
| query | string | ✅ | - | 검색 쿼리 |
| user_id | string | ✅ | - | 사용자 ID |
| top_k | integer | ❌ | 10 | 최대 반환 문서 수 (1–50) |
| document_id | string | ❌ | null | 특정 문서 필터 |
| use_query_rewrite | boolean | ❌ | false | 쿼리 재작성 여부 |
| use_compression | boolean | ❌ | true | LLM 관련성 압축 여부 |
| use_parent_context | boolean | ❌ | true | Parent 문서 컨텍스트 포함 여부 |

#### Response `200`
```json
{
  "query": "금융 규정 위반 시 제재 기준은?",
  "rewritten_query": null,
  "documents": [
    {
      "id": "chunk-001",
      "content": "제재 기준은 다음과 같습니다...",
      "score": 0.92,
      "metadata": {"source": "policy.pdf", "page": "3"},
      "parent_content": null
    }
  ],
  "total_found": 5,
  "request_id": "req-uuid-1234"
}
```

#### 에러 응답
| 코드 | 설명 |
|------|------|
| 422 | 유효성 검사 실패 |

---

## hybrid-search

### `POST /api/v1/hybrid-search/search`

**설명**: ES BM25 + Qdrant 벡터 검색을 RRF(Reciprocal Rank Fusion)로 병합합니다.

#### Request Body
```json
{
  "query": "연금 수령 조건",
  "top_k": 10,
  "bm25_top_k": 20,
  "vector_top_k": 20,
  "rrf_k": 60
}
```

| 필드 | 타입 | 필수 | 기본값 | 설명 |
|------|------|------|--------|------|
| query | string | ✅ | - | 검색 쿼리 |
| top_k | integer | ❌ | 10 | 최종 반환 수 (1–50) |
| bm25_top_k | integer | ❌ | 20 | BM25 후보 수 (1–100) |
| vector_top_k | integer | ❌ | 20 | 벡터 후보 수 (1–100) |
| rrf_k | integer | ❌ | 60 | RRF 상수 k |

#### Response `200`
```json
{
  "query": "연금 수령 조건",
  "results": [
    {
      "id": "chunk-001",
      "content": "연금 수령 조건은...",
      "score": 0.87,
      "bm25_rank": 2,
      "bm25_score": 12.5,
      "vector_rank": 1,
      "vector_score": 0.93,
      "source": "pension_policy.pdf",
      "metadata": {}
    }
  ],
  "total_found": 10,
  "request_id": "req-uuid-1234"
}
```

---

## chunk-index

### `POST /api/v1/chunk-index/upload`

**설명**: 텍스트를 청킹하고 키워드를 추출하여 Elasticsearch에 색인합니다.
BM25 하이브리드 검색 품질 향상용.

#### Request Body
```json
{
  "document_id": "doc-001",
  "content": "금융투자업자는 투자자의 이익을 최우선으로...",
  "user_id": "user-001",
  "strategy_type": "parent_child",
  "chunk_size": 500,
  "chunk_overlap": 50,
  "top_keywords": 10,
  "metadata": {}
}
```

#### Response `200`
```json
{
  "document_id": "doc-001",
  "user_id": "user-001",
  "total_chunks": 5,
  "indexed_chunks": [
    {
      "chunk_id": "chunk-001",
      "chunk_type": "child",
      "keywords": ["투자자", "이익", "금융"],
      "content": "금융투자업자는..."
    }
  ],
  "request_id": "req-uuid-1234"
}
```

---

## morph-index

### `POST /api/v1/morph-index/upload`

**설명**: Kiwi 형태소 분석(NNG/NNP/VV원형/VA원형) + Qdrant + ES 이중 색인.

#### Request Body
```json
{
  "document_id": "doc-001",
  "content": "한국 금융시장에서 투자자 보호를 위한 규정...",
  "user_id": "user-001",
  "strategy_type": "parent_child",
  "chunk_size": 500,
  "chunk_overlap": 50,
  "source": "financial_policy.pdf",
  "metadata": {}
}
```

#### Response `200`
```json
{
  "document_id": "doc-001",
  "user_id": "user-001",
  "total_chunks": 5,
  "qdrant_indexed": 5,
  "es_indexed": 5,
  "indexed_chunks": [
    {
      "chunk_id": "chunk-001",
      "chunk_type": "child",
      "morph_keywords": ["금융", "투자자", "보호", "규정"],
      "content": "한국 금융시장에서...",
      "char_start": 0,
      "char_end": 120,
      "chunk_index": 0
    }
  ],
  "request_id": "req-uuid-1234"
}
```

---

## rag-agent

### `POST /api/v1/rag-agent/query`

**설명**: LangGraph ReAct 에이전트 기반 내부 문서 질의응답.
BM25(ES) + Vector(Qdrant) 5:5 하이브리드 검색으로 관련 문서를 찾고, ChatOpenAI가 답변을 생성합니다.

#### Request Body
```json
{
  "query": "투자자 보호를 위한 주요 규정은 무엇인가요?",
  "user_id": "user-001",
  "top_k": 5
}
```

| 필드 | 타입 | 필수 | 기본값 | 설명 |
|------|------|------|--------|------|
| query | string | ✅ | - | 질의 내용 (1자 이상) |
| user_id | string | ✅ | - | 사용자 ID |
| top_k | integer | ❌ | 5 | 검색 결과 수 (1–20) |

#### Response `200`
```json
{
  "query": "투자자 보호를 위한 주요 규정은 무엇인가요?",
  "answer": "투자자 보호를 위한 주요 규정으로는...",
  "sources": [
    {
      "content": "제2조 투자자 보호...",
      "source": "financial_policy.pdf",
      "chunk_id": "chunk-001",
      "score": 0.91
    }
  ],
  "used_internal_docs": true,
  "request_id": "req-uuid-1234"
}
```

---

## conversation

### `POST /api/v1/conversation/chat`

**설명**: Multi-Turn 대화 메모리 관리 API.
6턴 초과 시 오래된 히스토리를 LLM으로 요약하고, (요약본 + 최근 3턴)만 컨텍스트로 사용합니다.
대화 기록은 MySQL에 저장됩니다.

#### Request Body
```json
{
  "user_id": "user-001",
  "session_id": "session-abc",
  "message": "금리 인상이 채권 가격에 미치는 영향을 설명해주세요."
}
```

#### Response `200`
```json
{
  "user_id": "user-001",
  "session_id": "session-abc",
  "answer": "금리가 인상되면 기존 채권의 가격은 하락합니다...",
  "was_summarized": false,
  "request_id": "req-uuid-1234"
}
```

| 필드 | 설명 |
|------|------|
| was_summarized | 이번 응답에서 히스토리 요약이 발생했는지 여부 |

---

## Agent Builder

### `GET /api/v1/agents/tools`

**설명**: 사용 가능한 도구 목록을 조회합니다 (내부 도구 + DB 등록 MCP 도구).

#### Response `200`
```json
{
  "tools": [
    {
      "tool_id": "tavily_search",
      "name": "Tavily Web Search",
      "description": "Searches the web using Tavily API"
    }
  ]
}
```

---

### `POST /api/v1/agents`

**설명**: 에이전트를 생성합니다. LLM이 도구 자동 선택 + 시스템 프롬프트 자동 생성.

#### Request Body
```json
{
  "name": "금융 분석 에이전트",
  "goal": "금융 문서를 검색하고 분석하여 답변을 제공한다",
  "tool_ids": ["tavily_search", "code_executor"]
}
```

#### Response `201`
```json
{
  "agent_id": "agent-uuid-1234",
  "name": "금융 분석 에이전트",
  "system_prompt": "당신은 금융 문서 분석 전문가입니다...",
  "tool_ids": ["tavily_search", "code_executor"]
}
```

---

### `GET /api/v1/agents/{agent_id}`

**설명**: 에이전트 정의를 조회합니다.

#### 에러 응답
| 코드 | 설명 |
|------|------|
| 404 | 에이전트를 찾을 수 없음 |

---

### `PATCH /api/v1/agents/{agent_id}`

**설명**: 에이전트 시스템 프롬프트 또는 이름을 수정합니다.

#### Request Body
```json
{
  "name": "업데이트된 에이전트명",
  "system_prompt": "수정된 시스템 프롬프트..."
}
```

---

### `POST /api/v1/agents/{agent_id}/run`

**설명**: 에이전트를 실행합니다. DB에서 워크플로우 로드 → LangGraph 동적 컴파일 → 응답.

#### Request Body
```json
{
  "message": "올해 금융시장 동향을 분석해주세요",
  "session_id": "session-abc"
}
```

---

### `POST /api/v1/agents/interview`

**설명**: 인터뷰 세션을 시작합니다. LLM이 에이전트 설계를 위한 명확화 질문을 생성합니다.

#### Request Body
```json
{
  "goal": "금융 문서를 분석하는 에이전트를 만들고 싶다"
}
```

#### Response `201`
```json
{
  "session_id": "interview-session-uuid",
  "question": "주로 어떤 종류의 금융 문서를 분석하실 예정인가요?"
}
```

---

### `POST /api/v1/agents/interview/{session_id}/answer`

**설명**: 인터뷰 질문에 답변합니다. 추가 질문 또는 에이전트 초안을 반환합니다.

---

### `POST /api/v1/agents/interview/{session_id}/finalize`

**설명**: 에이전트 초안을 확정하고 DB에 저장합니다.

#### Request Body
```json
{
  "system_prompt_override": "수정하고 싶은 시스템 프롬프트 (선택)"
}
```

---

## middleware-agent

### `GET /api/v2/agents/tools`

**설명**: 사용 가능한 도구 목록을 반환합니다 (AGENT-004 tool_registry 재사용).

---

### `POST /api/v2/agents`

**설명**: LangChain Middleware 기반 에이전트를 생성합니다.

지원 미들웨어:
- `SummarizationMiddleware` - 대화 요약
- `PIIMiddleware` - 개인정보 마스킹
- `ToolRetryMiddleware` - 도구 재시도
- `ModelCallLimitMiddleware` - LLM 호출 제한
- `ModelFallbackMiddleware` - 모델 폴백

#### Request Body
```json
{
  "name": "안전한 금융 에이전트",
  "goal": "금융 질의에 답변하되 개인정보를 보호한다",
  "tool_ids": ["tavily_search"],
  "middlewares": ["PIIMiddleware", "ToolRetryMiddleware"]
}
```

---

### `GET /api/v2/agents/{agent_id}`

**설명**: 미들웨어 에이전트 정의를 조회합니다.

---

### `PATCH /api/v2/agents/{agent_id}`

**설명**: 미들웨어 에이전트를 수정합니다.

---

### `POST /api/v2/agents/{agent_id}/run`

**설명**: 미들웨어 에이전트를 실행합니다.

#### Request Body
```json
{
  "message": "삼성전자 최근 실적을 알려주세요",
  "session_id": "session-001"
}
```

---

## auto-agent-builder

### `POST /api/v3/agents/auto`

**설명**: 자연어 요청으로 에이전트를 자동 생성합니다.
LLM이 도구+미들웨어를 자동 추론하며, 보충 질문이 필요하면 세션 ID를 반환합니다.
Redis를 이용한 멀티턴 보충 질문을 지원합니다.

#### Request Body
```json
{
  "user_request": "금융 문서를 검색하고 할루시네이션을 검증하는 에이전트를 만들어줘",
  "user_id": "user-001"
}
```

#### Response `202`
```json
{
  "session_id": "auto-session-uuid",
  "status": "needs_clarification",
  "agent_id": null,
  "clarification_question": "검색할 문서의 언어는 한국어인가요, 영어인가요?"
}
```

또는 바로 생성된 경우:
```json
{
  "session_id": "auto-session-uuid",
  "status": "created",
  "agent_id": "agent-uuid-1234",
  "clarification_question": null
}
```

---

### `POST /api/v3/agents/auto/{session_id}/reply`

**설명**: 보충 질문에 답변하고 재추론하여 에이전트를 생성합니다.

#### Request Body
```json
{
  "answer": "한국어 문서입니다"
}
```

---

### `GET /api/v3/agents/auto/{session_id}`

**설명**: 빌드 세션 상태를 조회합니다.

#### Response `200`
```json
{
  "session_id": "auto-session-uuid",
  "status": "created",
  "attempt_count": 2,
  "user_request": "금융 문서를 검색하고...",
  "created_agent_id": "agent-uuid-1234"
}
```

---

## MCP Registry

### `POST /api/v1/mcp-registry`

**설명**: MCP 서버를 DB에 등록합니다.

#### Request Body
```json
{
  "name": "my-mcp-server",
  "description": "Custom MCP tool server",
  "transport": "stdio",
  "command": "python",
  "args": ["-m", "my_mcp_server"],
  "user_id": "user-001"
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| name | string | ✅ | 서버 이름 |
| transport | string | ✅ | `stdio` / `sse` / `websocket` |
| command | string | ✅ | 실행 명령 |
| args | array | ❌ | 실행 인수 |
| user_id | string | ✅ | 소유자 ID |

#### Response `201`
```json
{
  "id": "mcp-uuid-1234",
  "name": "my-mcp-server",
  "description": "Custom MCP tool server",
  "transport": "stdio",
  "command": "python",
  "args": ["-m", "my_mcp_server"],
  "user_id": "user-001",
  "created_at": "2026-03-28T10:00:00Z"
}
```

---

### `GET /api/v1/mcp-registry`

**설명**: MCP 서버 목록을 조회합니다.

#### Query Parameters
| 파라미터 | 타입 | 필수 | 설명 |
|---------|------|------|------|
| user_id | string | ❌ | 필터 (없으면 전체 조회) |

---

### `GET /api/v1/mcp-registry/{id}`

**설명**: 특정 MCP 서버 정보를 조회합니다.

#### 에러 응답
| 코드 | 설명 |
|------|------|
| 404 | MCP 서버를 찾을 수 없음 |

---

### `PUT /api/v1/mcp-registry/{id}`

**설명**: MCP 서버 정보를 수정합니다.

#### 에러 응답
| 코드 | 설명 |
|------|------|
| 404 | MCP 서버를 찾을 수 없음 |
| 422 | 유효성 검사 실패 |

---

### `DELETE /api/v1/mcp-registry/{id}`

**설명**: MCP 서버를 삭제합니다.

#### Response `204` - 삭제 성공 (본문 없음)

#### 에러 응답
| 코드 | 설명 |
|------|------|
| 404 | MCP 서버를 찾을 수 없음 |

---

## 공통 에러 코드

| 코드 | 설명 |
|------|------|
| 404 | 리소스를 찾을 수 없음 |
| 422 | 유효성 검사 실패 (파라미터/형식 오류) |
| 500 | 서버 내부 오류 |
