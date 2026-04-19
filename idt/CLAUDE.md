# CLAUDE.md - AI Assistant Guide

> Last Updated: 2026-04-18
> Purpose: Define strict rules for AI-assisted development  
> Scope: FastAPI + LangGraph/LangChain 기반 RAG & Agent 시스템

---

## 1. Project Overview

This project is a backend service built with:

- Language: **Python 3.11+**
- Framework: **FastAPI**
- Agent Framework: **LangGraph / LangChain**
- Architecture: **Thin DDD**
  - Domain → Application → Infrastructure
- RDB: **MySQL**
- Vector DB: **Qdrant**

Primary goals:
- 빠른 실험이 가능한 얇은 도메인 설계
- 안정적인 문서 기반 질의응답(RAG)
- 예측 가능한 확장 (Agent / Tool / Retriever)
- 금융/정책 문서에 적합한 보수적 동작
- TDD로 개발한다
- 테스트 없이 구현코드를 먼저 작성하면 안된다
- 테스트 실패를 확인하지 않고 구현하지 않는다
- 구현중에 테스트를 수정하지 않는다

---

## 2. Architecture Rules

### Layer Responsibilities

### domain/
- Entity, ValueObject, DomainPolicy
- 문서 규칙, 청킹 규칙, 라우팅 규칙, 템플릿 규칙 정의
- LoggerInterface, LogContext 정의 (로깅 추상화)
- ❌ 외부 API 호출 금지 (LLM, Qdrant, Web Search 등)
- ❌ DB 접근 금지
- ❌ LangChain / LangGraph 사용 금지

### application/
- UseCase, Workflow, Orchestrator
- LangGraph graph 정의
- Retriever → Compression → Parent Requery 흐름 담당
- 트랜잭션 및 실행 흐름 제어
- domain 규칙 "조합만" 담당

### infrastructure/
- MySQL, Qdrant, OpenAI, Tavily, Perplexity, LlamaParse
- 외부 시스템 연동 및 Adapter
- **StructuredLogger, Middleware 구현**
- ❌ 비즈니스 규칙 포함 금지

### interfaces/
- FastAPI router, request/response schema
- **RequestLoggingMiddleware, ExceptionHandlerMiddleware 적용**
- ❌ 비즈니스 로직 작성 금지

---

## 3. Coding Conventions

- 클래스/모듈은 단일 책임
- 함수 길이 40줄 초과 금지
- if 중첩 2단계 초과 금지
- 명시적 타입 사용 (pydantic / typing)
- config 값 하드코딩 금지

---

## 4. AI Behavior Rules

AI는 다음만 자율적으로 수행 가능:
- 코드 리팩토링
- 네이밍 개선
- 테스트 추가
- 성능/가독성 개선

AI는 다음을 **절대 수행하면 안 됨**:
- 아키텍처 변경
- 레이어 이동
- DB 스키마 임의 변경
- 대화 메모리 정책 변경
- Parent/Child 문서 구조 변경

---

## 5. Common Tasks

### 새로운 기능 추가
1. domain 정책 존재 여부 확인
2. application use-case/workflow 추가
3. infrastructure adapter 연결
4. 테스트 작성
5. **로깅 적용 (LOG-001 참고)**

### 버그 수정
- 재현 테스트 우선
- 최소 변경 원칙
- **에러 로그로 스택 트레이스 확인**

---

## 6. Testing Rules

- 모든 use-case는 테스트 필수
- domain 테스트는 mock 금지
- infrastructure 테스트는 mock 또는 test container 사용
- Retriever / Chunking / Parent Requery는 케이스 테스트 필수

---

## 7. Multi-Turn Conversation Memory Rules (중요)

### 7.1 기본 원칙

- 모든 대화는 **user_id + session_id** 기준으로 관리한다
- 대화 기록은 **MySQL(RDB)** 에 저장한다
- Vector DB에 대화 원문 저장 ❌ (문서용과 분리)

---

### 7.2 Conversation Table (개념 설계)

**conversation_message**
- id (pk)
- user_id
- session_id
- role (user | assistant)
- content
- created_at
- turn_index

**conversation_summary**
- user_id
- session_id
- summary_content
- summarized_until_turn
- updated_at

---

### 7.3 요약 트리거 규칙 (강제)

- 한 세션에서 **대화 턴이 6개를 초과하면**
  → 반드시 **요약을 수행한다**

요약 방식:
1. turn_index 1 ~ N-3 까지 요약
2. 요약 결과를 `conversation_summary`에 저장
3. 기존 메시지는 유지하되,
   - 다음 질의 시 **요약본 + 최근 3턴만 컨텍스트로 사용**

❌ 전체 대화를 그대로 LLM에 전달 금지  
❌ 요약 없이 무한 누적 금지

---

### 7.4 요약 정책

- 요약은 사실 중심
- 결정사항 / 사용자 의도 / 중요한 제약 포함
- 질문/답변 스타일 요약 금지

요약은 다음 질문의 **system/context**로만 사용한다.

---

## 8. RAG & Document Rules (요약)

- Retrieval은 **Child-first**
- 기본 top-k = 10 (configurable)
- LLM 기반 true/false 문서 압축 수행
- 불충분 시 **Parent Page Requery** 필수
- Parent/Child 메타데이터 누락 ❌

---

## 9. Logging & Error Tracking Rules (신규)

### 9.1 기본 원칙

모든 모듈은 **LOG-001 (task-logging.md)** 규칙을 따른다.

- 모든 API 요청/응답은 **자동 로깅**된다
- 에러 발생 시 **스택 트레이스 필수 기록**
- **request_id**로 요청 전체 흐름 추적 가능

---

### 9.2 로깅 필수 항목

#### API 요청 로그
```json
{
    "request_id": "uuid",
    "method": "POST",
    "endpoint": "/api/v1/documents/upload",
    "query_params": {},
    "body": {"user_id": "..."},
    "headers": {"content-type": "..."}
}
```

#### API 응답 로그
```json
{
    "request_id": "uuid",
    "status_code": 200,
    "process_time_ms": 1500
}
```

#### 에러 로그 (스택 트레이스 필수)
```json
{
    "request_id": "uuid",
    "error": {
        "type": "ValueError",
        "message": "Invalid PDF format",
        "stacktrace": "Traceback (most recent call last):..."
    }
}
```

---

### 9.3 로깅 적용 규칙

| 상황 | 로그 레벨 | 필수 포함 |
|------|----------|-----------|
| API 요청 수신 | INFO | request_id, method, endpoint |
| API 정상 응답 | INFO | request_id, status_code, process_time_ms |
| 비즈니스 에러 | WARNING | request_id, error_type, message |
| 시스템 에러 | ERROR | request_id, error_type, message, **stacktrace** |
| 치명적 에러 | CRITICAL | 위 전부 + 알림 트리거 |

---

### 9.4 새 모듈 개발 시 로깅 체크리스트

새로운 task.md 작성 시 다음을 포함:

- [ ] LoggerInterface 주입 받아 사용
- [ ] 주요 처리 시작/완료 INFO 로그
- [ ] 예외 발생 시 ERROR 로그 + 스택 트레이스
- [ ] request_id 컨텍스트 전파
- [ ] 민감 정보 마스킹 (password, token, api_key)
```python
# 모든 서비스/노드에서 로깅 패턴
class SomeService:
    def __init__(self, logger: LoggerInterface):
        self._logger = logger
    
    async def process(self, request_id: str, data: dict):
        self._logger.info("Processing started", request_id=request_id, data_keys=list(data.keys()))
        
        try:
            result = await self._do_work(data)
            self._logger.info("Processing completed", request_id=request_id)
            return result
        except Exception as e:
            self._logger.error("Processing failed", exception=e, request_id=request_id)
            raise
```

---

### 9.5 금지 사항

- ❌ print() 사용 금지 (logger 사용)
- ❌ 스택 트레이스 없는 에러 로그 금지
- ❌ request_id 없는 로그 금지 (API 컨텍스트 내)
- ❌ 민감 정보 평문 로깅 금지

---

## 10. Database Session & Transaction Rules (DB-001)

### 10.1 핵심 원칙

> **요청 1건 = AsyncSession 1개 = 트랜잭션 1건**

- 하나의 HTTP 요청은 **단 하나의** `AsyncSession` 을 사용한다.
- 하나의 세션은 **단 하나의** 트랜잭션 경계 안에서 실행된다.
- UseCase 내부의 모든 Repository 는 **동일한 세션**을 공유한다.

이 원칙을 위반하면 (1) 커넥션 풀 고갈, (2) 원자성 붕괴, (3) `flush()` greenlet 실패가 발생한다.

---

### 10.2 세션 주입 규칙

- FastAPI Dependency `get_session` 을 통해서만 세션을 얻는다.
- `get_session` 은 `async with factory() as session: async with session.begin(): yield session` 패턴으로 **자동 commit/rollback** 을 보장한다.
- `session_factory()` 를 팩토리/서비스 코드에서 직접 호출하여 세션을 만들지 않는다.
- UseCase 팩토리는 `session: AsyncSession = Depends(get_session)` 을 받아 repository 를 조립한다.

```python
# ✅ 권장
async def _factory(
    session: AsyncSession = Depends(get_session),
) -> SomeUseCase:
    repo_a = RepoA(session)    # 공유
    repo_b = RepoB(session)    # 공유
    return SomeUseCase(repo_a, repo_b)

# ❌ 금지 — 팩토리 내부에서 세션 생성 금지
async def _factory() -> SomeUseCase:
    factory = get_session_factory()
    repo_a = RepoA(factory())   # 세션 누수
    repo_b = RepoB(factory())   # 세션 분리 → 원자성 붕괴
    return SomeUseCase(repo_a, repo_b)
```

---

### 10.3 Repository 트랜잭션 규칙

- Repository 는 `session.add`, `session.flush`, `session.execute`, `session.scalar` 만 사용한다.
- ❌ Repository 내부에서 `session.commit()` / `session.rollback()` 호출 금지
- ❌ Repository 내부에서 `async with session.begin():` 중첩 금지
- 트랜잭션 경계는 **`get_session` dependency** 가 책임진다 (요청 단위).

| 작업 | Repository | Dependency (`get_session`) |
|------|-----------|----------------------------|
| add / execute DML | ✅ | |
| flush (id 확보) | ✅ | |
| commit | ❌ 금지 | ✅ `session.begin()` 종료 시 자동 |
| rollback | ❌ 금지 | ✅ 예외 전파 시 자동 |

---

### 10.4 lifespan-scoped UseCase 금지

- 앱 시작 시점(lifespan) 에 세션을 가진 UseCase 를 `singleton` 으로 만들지 않는다.
- lifespan-scoped UseCase 가 DB 가 필요한 다른 UseCase 를 필요로 한다면,
  **`execute(*, injected_uc)`** 형태로 요청 시점에 주입받는다.
- 이유: lifespan 싱글턴이 세션을 영구 점유하면 앱 전체가 풀 고갈의 원인이 된다.

---

### 10.5 금지 사항 요약

- ❌ 팩토리/서비스에서 `get_session_factory()()` 로 세션 직접 생성
- ❌ 동일 UseCase 안에서 repository 별 서로 다른 세션 사용
- ❌ Repository 내부에서 `commit()` / `rollback()` 호출
- ❌ `async with session.begin():` 중첩 호출 (dependency 에서만 사용)
- ❌ lifespan singleton UseCase 가 AsyncSession 을 보유

---

## 11. Output Format (AI Response Contract)

AI 응답은 항상 다음 순서를 따른다:

1. 요약 (What changed / Answer)
2. 설계 설명 (Why / Policy Mapping)
3. 코드 (필요한 범위만)
4. 주의사항 / 영향 범위

---

## 12. Forbidden Actions (절대 금지)

- domain → infrastructure 참조
- controller/router에 비즈니스 로직 작성
- 대화 기록을 vector db에 저장
- 요약 규칙 무시
- spec에 없는 기능 구현
- 과도한 추상화 (두꺼운 DDD)
- **print() 사용 (logger 사용 필수)**
- **스택 트레이스 없는 에러 처리**
- **Repository 내부에서 `commit()` / `rollback()` 호출 (DB-001 §10.3)**
- **팩토리/서비스에서 `get_session_factory()()` 로 세션 직접 생성 (DB-001 §10.2)**
- **한 UseCase 안에서 repository 별 서로 다른 세션 사용 (DB-001 §10.1)**

---

## 13. Task Files Reference

모든 task.md 파일은 다음 규칙을 따른다:

| Task ID | 파일명 | 설명 |
|---------|--------|------|
| VEC-001 | src/claude/task/task-qdrant.md | Qdrant 벡터 저장소 |
| DOC-001 | src/claude/task/task-pdfparser.md | PDF 파서 모듈 |
| CHUNK-001 | src/claude/task/task-chunk.md | 청킹 모듈 |
| RET-001 | src/claude/task/task-retriever.md | 리트리버 모듈 |
| COMP-001 | src/claude/task/task-compressor.md | 문서 압축기 모듈 |
| EXCEL-001 | src/claude/task/task-excel.md | 엑셀 처리 모듈 |
| PIPELINE-001 | src/claude/task/task-pipeline.md | 문서 처리 파이프라인 |
| **LOG-001** | **src/claude/task/task-logging.md** | **로깅 & 에러 추적 (필수 참조)** |
| EVAL-001 | src/claude/task/task-hallucination-evaluator.md | 할루시네이션 평가기 모듈 |
| QUERY-001 | src/claude/task/task-query-rewriter.md | 쿼리 재작성기 모듈 |
| SEARCH-001 | src/claude/task/task-tavily-search.md | Tavily 웹 검색 도구 |
| AGENT-001 | src/claude/task/task-research-agent.md | Self-Corrective RAG 에이전트 |
| CODE-001 | src/claude/task/task-code-executor.md | Python 코드 실행 도구 |
| LLM-001 | src/claude/task/task-claude-client.md | Claude LLM 클라이언트 모듈 |
| AGENT-002 | src/claude/task/task-excel-analysis-agent.md | 엑셀 분석 에이전트 (Self-Corrective) |
| AGENT-003 | src/claude/task/task-research-team.md | Research Team 에이전트 (Supervisor + Web/Document Search 팀) |
| LANGSMITH-001| src/claude/task/task-langsmith.md | LangSmith 모듈 |
| RETRIEVAL-001 | src/claude/task/task-retrieval-api.md | 문서 검색 API (RAG Retrieval) |
| REDIS-001 | src/claude/task/task-redis.md | Redis DB 모듈 (키-값 CRUD, Hash, List, 분산 잠금) |
| MCP-001 | src/claude/task/task-mcp-client.md | LangChain MCP 공통 클라이언트 모듈 (stdio/SSE/WebSocket) |
| **ES-001** | **src/claude/task/task-elasticsearch.md** | **Elasticsearch 공통 Repository 모듈 (index/search/CRUD)** |
| **HYBRID-001** | **src/claude/task/task-hybrid-search.md** | **BM25 + 벡터 하이브리드 검색 (RRF 병합, API 포함)** |
| **CHUNK-IDX-001** | **src/claude/task/task-chunk-index.md** | **청킹 + BM25 키워드 추출 색인 API (ES 저장)** |
| **KIWI-001** | **src/claude/task/task-kiwi-analyzer.md** | **Kiwi 한국어 형태소 분석기 모듈 (MorphAnalyzerInterface, KiwiMorphAnalyzer)** |
| **MORPH-IDX-001** | **src/claude/task/task-morph-index.md** | **Kiwi 형태소 분석 + Qdrant + ES 이중 색인 API (NNG/NNP/VV원형/VA원형 + 위치 메타데이터)** |
| **RAG-001** | **src/claude/task/task-rag-agent-api.md** | **ReAct RAG Agent API (BM25+Vector 5:5 하이브리드 검색 + ChatOpenAI LangGraph 에이전트 + 출처 메타데이터)** |
| **MYSQL-001** | **src/claude/task/task-mysql.md** | **MySQL 공통 Repository (Generic Base CRUD: save/find_by_id/find_all/find_by_conditions/delete/count/exists + 8가지 연산자)** |
| **CONV-001** | **src/claude/task/task-conversation.md** | **Multi-Turn 대화 메모리 관리 UseCase (6턴 초과 요약, LangChain ChatOpenAI, POST /api/v1/conversation/chat)** |
| **PARSE-001** | **src/claude/task/task-pdf-parse-service.md** | **PDF 파싱 공통 서비스 (PDFParseUseCase: LlamaParse/PyMuPDF 공통 추상화, asyncio.to_thread, ParseDocumentRequest/Result)** |
| **INGEST-001** | **src/claude/task/task-ingest-api.md** | **PDF 파싱+청킹+Vector 저장 통합 API (POST /api/v1/ingest/pdf, 파서 선택: pymupdf/llamaparser, 청킹 전략 선택, Qdrant 저장)** |
| **HTML-TO-PDF-001** | **src/claude/task/task-html-to-pdf.md** | **HTML → PDF 변환 공통 모듈 (xhtml2pdf, HtmlToPdfConverterInterface, asyncio.to_thread, POST /api/v1/pdf/export)** |
| **EXCEL-EXPORT-001** | **src/claude/task/task-excel-export.md** | **pandas Excel 파일 생성 공통 모듈 + LangChain Tool (ExcelExportTool, ExcelExporterInterface, 다중 시트, POST /api/v1/excel/export)** |
| **AGENT-004** | **src/claude/task/task-custom-agent-builder.md** | **Custom Agent Builder (LLM 도구 자동 선택 + LangGraph Supervisor 동적 컴파일 + 시스템 프롬프트 자동생성/수정, POST /api/v1/agents)** |
| **MCP-REG-001** | **src/claude/task/task-mcp-registry.md** | **Dynamic MCP Tool Registry (사용자 MCP 서버 등록/조회/수정/삭제, DB 동적 로드, GET /api/v1/agents/tools 통합, POST /api/v1/mcp-registry)** |
| **OLLAMA-001** | **src/claude/task/task-ollama-client.md** | **Ollama LLM 클라이언트 모듈 (LangChain ChatOllama, 로컬 모델 호출, 스트리밍, OllamaRequest/Response, 연결/타임아웃/모델없음 에러 처리)** |
| **AGENT-005** | **src/claude/task/task-middleware-agent-builder.md** | **LangChain Middleware 기반 에이전트 빌더 (create_agent + SummarizationMiddleware/PIIMiddleware/ToolRetryMiddleware/ModelCallLimitMiddleware/ModelFallbackMiddleware, POST /api/v2/agents, AGENT-004 tool_registry 재사용)** |
| **AGENT-006** | **src/claude/task/task-auto-agent-builder.md** | **자연어 기반 자동 에이전트 빌더 (LLM 자동 도구+미들웨어 추론, Redis 멀티턴 보충 질문, AGENT-005 CreateMiddlewareAgentUseCase 재사용, POST /api/v3/agents/auto)** |
| **AGENT-007** | **src/claude/task/task-planner-agent.md** | **공통 Planner Agent (질문 분석 → 단계별 실행 계획 생성, PlanResult/PlanStep, LangGraph StateGraph replan 루프, PlannerInterface 추상화, 타 Agent 재사용 공통 모듈)** |
| **AUTH-001** | **src/claude/task/task-auth.md** | **인증/인가 시스템 (이메일+비밀번호 회원가입→관리자 승인 흐름, Access+Refresh JWT, RBAC role 기반 Dependency, UserStatus(pending/approved/rejected), users+refresh_tokens MySQL 저장, POST /api/v1/auth/* + POST /api/v1/admin/users/{id}/approve|reject)** |
| **CHAT-001** | **src/claude/task/task-general-chat-api.md** | **General Chat API (LangGraph ReAct 에이전트 + Tavily 웹검색 + 내부문서 BM25+Vector 검색 + MCP 도구 동적 로드 + 멀티턴 6턴 압축 + LangSmith 추적, POST /api/v1/chat)** |
| **CHAT-HIST-001** | **src/claude/task/task-chat-history-api.md** | **대화 히스토리 조회 API (user_id+session_id 기준 저장된 대화 메시지 UI 제공, 세션 목록 GET /api/v1/conversations/sessions + 메시지 전체 조회 GET /api/v1/conversations/sessions/{session_id}/messages, ConversationMessageRepository 확장)** |
**모든 새 task.md는 LOG-001을 의존성으로 참조해야 한다.**
```

---

## 14. Skills

AI가 사용할 수 있는 검증 스킬 목록입니다.

| 스킬 | 설명 |
|------|------|
| `chunk` | 문서 청킹 모듈 TDD 개발 (청킹, 분할, 토큰 전략 구현 시 사용) |
| `tdd` | TDD 방식으로 새 기능 개발. 테스트 먼저 작성 → 실패 확인 → 구현 → 통과 확인 사이클 강제 |
| `langgraph` | LangChain/LangGraph 기반 AI 에이전트 및 그래프 워크플로우 개발 (StateGraph, 멀티에이전트, MCP 연동 등) |
| `langchain-middleware` | LangChain 미들웨어 추가/설정 (SummarizationMiddleware, HumanInTheLoopMiddleware, PIIMiddleware 등) |
| `verify-architecture` | DDD 레이어 의존성 규칙 준수 검증 (domain→infra 금지 등) |
| `verify-logging` | LOG-001 로깅 규칙 준수 검증 (print() 금지, exception= 필수 등) |
| `verify-tdd` | 프로덕션 모듈 테스트 파일 존재 여부 검증 |
| `verify-implementation` | 모든 verify 스킬을 순차 실행하여 통합 검증 보고서 생성. PR 전, 코드 리뷰 시 사용 |
| `manage-skills` | 세션 변경사항 분석으로 검증 스킬 누락 탐지, 스킬 생성/업데이트 및 CLAUDE.md 관리 |