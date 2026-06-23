# sangplusbot — Source of Truth (SOT)

> **목적**: 프로젝트의 단일 진실 공급원(Single Source of Truth). 아키텍처·기술스택·API·데이터 모델·도메인 기능의 사실 기준점.
> **갱신 기준일**: 2026-06-18 (브랜치 `feature/agent-platform-enhancements`, 최신 마이그레이션 V032)
> **작성 방식**: 코드/설정/마이그레이션 직접 조사 기반. 추정이 아닌 실제 파일 근거.

---

## 0. 한눈에 보기

RAG(검색 증강 생성) 기반 문서 질의응답 + 멀티 에이전트 대화 플랫폼. 금융/정책 문서에 특화된 보수적 동작과 예측 가능한 Agent 확장을 목표로 한다.

| 구분 | 내용 |
|------|------|
| **백엔드** | Python 3.11+ / FastAPI / LangGraph·LangChain / Thin DDD |
| **프론트엔드** | React 19 / TypeScript / Zustand / TanStack Query / Vite |
| **RDB** | MySQL (SQLAlchemy 2.0 async + asyncmy), Flyway 마이그레이션 (V002~V032) |
| **Vector DB** | Qdrant |
| **검색엔진** | Elasticsearch 8.10.1 (전문 검색) |
| **캐시/세션** | Redis |
| **LLM** | OpenAI / Anthropic / Ollama (provider 추상화) |
| **API 라우터 수** | 39개 |
| **프론트 화면 수** | 22개 페이지 |

---

## 1. 워크스페이스 구조

```
sangplusbot/
├── idt/           → 백엔드 API 서버 (FastAPI + LangGraph, Thin DDD)
│   ├── src/
│   │   ├── domain/          # Entity, VO, Policy, 규칙 (외부 의존 금지)
│   │   ├── application/     # UseCase, Workflow, LangGraph graph
│   │   ├── infrastructure/  # MySQL, Qdrant, ES, Redis, LLM, MCP adapter
│   │   ├── interfaces/      # request/response schema, DI factory
│   │   └── api/             # FastAPI router, main.py, middleware
│   ├── db/migration/        # Flyway SQL (V002~V032) ← 스키마 진실 기준
│   ├── alembic/             # 레거시(conversation 테이블 1건)
│   ├── tests/
│   ├── run_server.py        # Windows 친화 ASGI 진입점
│   └── pyproject.toml
├── idt_front/     → React SPA
│   └── src/{pages,components,hooks,services,store,constants,lib,types}/
└── docs/          → PDCA 문서 + 본 SOT
    ├── 01-plan / 02-design / 03-analysis / 04-report / archive
    └── SOURCE-OF-TRUTH.md  ← 본 문서
```

**레이어 책임 (idt/CLAUDE.md 기준)**

| Layer | 역할 | 금지 |
|-------|------|------|
| domain/ | Entity, VO, Policy, 규칙, LoggerInterface | 외부 API·DB·LangChain 사용 |
| application/ | UseCase, Workflow, LangGraph graph, 흐름 제어 | 비즈니스 규칙 직접 구현 |
| infrastructure/ | MySQL·Qdrant·OpenAI Adapter, StructuredLogger | 비즈니스 규칙 포함 |
| interfaces/api | FastAPI router, schema, Middleware | 비즈니스 로직 작성 |

---

## 2. 기술 스택 (버전 고정 기준)

### 2-1. 백엔드 (`idt/pyproject.toml`)

| 영역 | 패키지 | 버전 |
|------|--------|------|
| 런타임 | Python | >= 3.11 |
| 프레임워크 | fastapi / uvicorn[standard] | >= 0.109 / >= 0.27 |
| 설정 | pydantic / pydantic-settings | >= 2.5 / >= 2.1 |
| LLM | langchain-core/openai/community/anthropic/ollama | >= 0.3 |
| 오케스트레이션 | langgraph | >= 0.2 |
| RDB | sqlalchemy / asyncmy / alembic | >= 2.0 / >= 0.2.9 / >= 1.13 |
| Vector | qdrant-client | >= 1.13 |
| 검색 | elasticsearch[async] | == 8.10.1 |
| PDF | pymupdf / pymupdf4llm / llama-parse | >= 1.24 / >= 0.0.17 / >= 0.4 |
| 토크나이저 | tiktoken | >= 0.5 |
| MCP | mcp / langchain-mcp-adapters | >= 1.0 / >= 0.1 |
| 한국어 NLP | kiwipiepy | >= 0.17 |
| 웹검색 | tavily-python | >= 0.3 |
| 캐시 | redis | >= 5.0 |
| 인증 | python-jose[cryptography] / passlib[bcrypt] | >= 3.3 / >= 1.7.4 |
| 암호화 | cryptography (Fernet) | >= 42.0 |
| 내보내기 | xhtml2pdf / pandas / openpyxl | >= 0.2.17 / >= 2.0 / >= 3.1 |
| 개발도구 | pytest, pytest-asyncio, pytest-cov, ruff, mypy | `[dev]` |

### 2-2. 프론트엔드 (`idt_front/package.json`)

| 영역 | 패키지 | 버전 |
|------|--------|------|
| UI | react | 19.2.4 |
| 데이터 fetching | @tanstack/react-query | 5.90.21 |
| 상태관리 | zustand | 5.0.12 |
| 라우팅 | react-router | 7.13.1 |
| 빌드 | vite | 8.0.0 |
| 스타일 | tailwindcss | 4.2.1 |
| HTTP | axios | 1.13.6 |
| 마크다운 | react-markdown | 10.1.0 |
| 차트 | chart.js 4.5.1 / recharts 3.8.1 | — |
| 아이콘 | lucide-react | 0.577.0 |
| 테스트 | vitest 4.1.4 / @testing-library/react 16.3.2 / msw 2.13.2 | — |
| 타입 | typescript | 5.9.3 |

---

## 3. 핵심 도메인 / 기능 영역

| # | 기능 | 설명 | 주요 라우터 prefix |
|---|------|------|-------------------|
| 1 | **RAG 검색** | 하이브리드(벡터+키워드) 검색, 형태소 인덱싱(Kiwi), Qdrant + Elasticsearch | `/api/v1/hybrid-search`, `/api/v1/retrieval`, `/api/v1/morph-index` |
| 2 | **문서 인제스트** | PDF/Excel 업로드, 파서 라우팅, 청킹(parent-child), 통합 업로드 | `/api/v1/ingest`, `/api/v1/ingest/pdf`, `/api/v1/documents` |
| 3 | **컬렉션 관리** | 멀티 컬렉션(네임스페이스), 권한(RBAC), 문서 브라우징·삭제, 활동 로그 | `/api/v1/collections` |
| 4 | **Agent Builder** | 에이전트 CRUD·실행·구독·포크·자동생성(인터뷰), 도구 부착 | `/api/v1/agents`, `/api/v3/agents/auto`, `/api/v2/agents` |
| 5 | **멀티 에이전트 Supervisor** | LangGraph 기반 supervisor/worker 그래프 오케스트레이션 | (general_chat / agent_builder 내부) |
| 6 | **MCP 통합** | MCP 서버 레지스트리, 도구 동적 로딩, Fernet 시크릿 암호화, 도구 카탈로그 | `/api/v1/mcp-registry`, `/api/v1/tool-catalog` |
| 7 | **General Chat** | 웹검색·문서검색·MCP 도구 통합 대화, WebSocket 스트리밍 | `/api/v1` (chat), `/ws/*` |
| 8 | **대화 이력** | 세션·메시지 저장, 요약 정책, 차트 영속화(V031) | `/api/v1/conversation(s)` |
| 9 | **Excel 분석** | Pandas 파싱, 환각 탐지, 재시도 정책, 차트 시각화 | `/api/v1/excel`, `/api/v1/analysis` |
| 10 | **시각화/차트** | LLM 기반 차트 빌더·분류·변환 (General Chat 경로 한정) | (general_chat 내부) |
| 11 | **인증/인가 (AUTH-001)** | 가입 승인 워크플로우, JWT, RBAC, 부서 기반 접근제어 | `/api/v1/auth`, `/api/v1/admin/*` |
| 12 | **부서 관리** | 부서 CRUD, 사용자-부서 배정 | `/api/v1` (department) |
| 13 | **Agent Run 관측 (AGENT-OBS-001)** | 실행·노드·도구·LLM 호출·검색근거 추적, 비용/사용량 집계 | `/api/v1` (agent-run-observability) |
| 14 | **모델 레지스트리** | LLM 모델(가격 포함)·임베딩 모델 등록·관리 | `/api/v1/llm-models`, `/api/v1/embedding-models` |
| 15 | **RAGAS 평가** | 배치·실시간 평가, 테스트셋 관리, Admin 대시보드 | `/api/ragas`, `/api/v1/admin/ragas` |
| 16 | **내보내기** | Excel(Pandas)·PDF(xhtml2pdf) 변환 | `/api/v1/excel`, `/api/v1/pdf` |
| 17 | **사용자 프로필** | 확장 사용자 메타데이터(V024/V030) | (admin/user 경로) |

---

## 4. API 표면 (Router 등록 — `src/api/main.py`)

총 **39개 라우터**. 주요 prefix 기준 (전체는 `main.py` include 블록 참조):

```
/api/v1/auth                  인증(가입/로그인/refresh/logout/me)
/api/v1/admin                 가입 승인 등 관리
/api/v1/admin/users           사용자/권한 관리
/api/v1/admin/ragas           RAGAS 평가 관리
/api/v1/documents             문서/통합 업로드
/api/v1/ingest, /ingest/pdf   인제스트 / 고급 PDF 인제스트
/api/v1/retrieval             검색
/api/v1/hybrid-search         하이브리드 검색
/api/v1/morph-index           형태소 인덱싱
/api/v1/chunk-index           청크 인덱싱
/api/v1/doc-chunk             문서 청킹
/api/v1/collections           컬렉션 / 문서 브라우징 / 검색
/api/v1/agents                Agent Builder (CRUD/실행)
/api/v3/agents/auto           자동 에이전트 생성
/api/v2/agents                Middleware(상태유지) 에이전트
/api/v1/rag-agent             RAG 에이전트
/api/v1/rag-tools             RAG 도구 설정
/api/v1/tool-catalog          도구 카탈로그
/api/v1/mcp-registry          MCP 서버 레지스트리
/api/v1/llm-models            LLM 모델 레지스트리
/api/v1/embedding-models      임베딩 모델 레지스트리
/api/v1/conversation(s)       대화 / 대화 이력
/api/v1/excel, /pdf           내보내기
/api/v1/analysis              Excel 분석
/api/v1/preview               문서 미리보기
/api/ragas                    RAGAS 평가
/api/v1 (department, chat, agent-run-observability)
/ws/*                         WebSocket 스트리밍
GET /health                   헬스체크 → {"status":"ok"}
```

**미들웨어 스택** (적용 순):
1. `CORSMiddleware` — 허용 origin: `localhost:5173`, `127.0.0.1:5173`
2. `RequestLoggingMiddleware` — request_id 생성, 요청/응답 로깅
3. `ExceptionHandlerMiddleware` — 예외 처리, DEBUG 모드 지원

**진입점**
- 권장: `python run_server.py` (Windows 소켓 패치 포함)
- 직접: `uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload`
- 앱 생성: `create_app()` → lifespan에서 UseCase 초기화, 모델 시드(LLM/임베딩), ES 인덱스 보장

> **Cross-Project 규칙**: 백엔드 스키마/엔드포인트 변경 시 프론트 타입·서비스·훅 동기화 필수.
> 엔드포인트 상수: `idt_front/src/constants/api.ts` / 스킬: `/api-contract-sync`

---

## 5. 데이터 모델 (MySQL — Flyway 기준 진실)

마이그레이션 위치: `idt/db/migration/V###__*.sql` (엔진: InnoDB, utf8mb4)

### 5-1. 마이그레이션 이력 (V002 → V032)

| 버전 | 내용 | 핵심 테이블 |
|------|------|-------------|
| V002 | 인증 테이블 | `users`, `refresh_tokens` |
| V003/V004 | LLM 모델 + FK | `llm_model` |
| V005 | 부서 | `departments`, `user_departments` |
| V006/V008 | 도구 카탈로그 + 내부도구 시드 | `tool_catalog` |
| V007/V009/V010 | agent 공유·도구 설정·유니크 | `agent_definition`, `agent_tool` |
| V011 | 컬렉션 활동 로그 | `collection_activity_log` |
| V012 | 임베딩 모델 | `embedding_model` |
| V013 | 컬렉션 권한 | `collection_permissions` |
| V014 | 문서 메타데이터 | document metadata |
| V015 | 검색 이력 | `collection_search_history` |
| V016 | 대화에 agent_id | `conversation_message` |
| V017 | 구독/포크 | `user_agent_subscription` |
| V018/V019 | 도구 worker_type·category | `agent_tool` |
| V020 | 평가 테이블 | `evaluation_run/result/testset` |
| V021 | **Agent Run 관측 5테이블** | `ai_run` 외 4종 (아래 5-3) |
| V022/V023 | LLM 가격·집계 인덱스 | `llm_model` |
| V024/V030 | 사용자 프로필 + 백필 | `user_profiles` |
| V025~V027/V029 | RBAC 권한 + 시드 | `permissions`, `role_permissions`, `user_permissions` |
| V028 | agent user_context 플래그 | `agent_definition` |
| V031 | 메시지 차트 영속화 | `conversation_message.charts` |
| V032 | **MCP 시크릿 암호화** | `mcp_server_registry` (auth/server config) |

### 5-2. SQLAlchemy 모델 위치 (`src/infrastructure/*/models.py`)

| 모듈 | 파일 | 테이블 |
|------|------|--------|
| auth | `auth/models.py` | `users`, `refresh_tokens` |
| agent_builder | `agent_builder/models.py`, `subscription_model.py` | `agent_definition`, `agent_tool`, `user_agent_subscription` |
| llm_model | `llm_model/models.py` | `llm_model` |
| embedding_model | `embedding_model/models.py` | `embedding_model` |
| tool_catalog | `tool_catalog/models.py` | `tool_catalog` |
| mcp_registry | `mcp_registry/models.py` | `mcp_server_registry` |
| department | `department/models.py` | `departments`, `user_departments` |
| permission | `permission/models.py` | `permissions`, `role_permissions`, `user_permissions` |
| user_profile | `user_profile/models.py` | `user_profiles` |
| collection | `collection/models.py`, `permission_models.py` | `collection_activity_log`, `collection_permissions` |
| ragas | `ragas/models.py` | `evaluation_run/result/testset` |
| persistence | `persistence/models/conversation.py` | `conversation_message`, `conversation_summary` |
| persistence | `persistence/models/agent_run.py` | `ai_run`, `ai_run_step`, `ai_tool_call`, `ai_llm_call`, `ai_retrieval_source` |

### 5-3. Agent Run 관측 스키마 (V021 / AGENT-OBS-001)

`src/infrastructure/persistence/models/agent_run.py`

```
ai_run              질문 1건당 1행. status(RUNNING/SUCCESS/FAILED/CANCELLED),
                    langgraph_thread_id, langsmith_trace_id/url, 토큰·비용·지연
  └─ ai_run_step    LangGraph 노드 실행. node_type(SUPERVISOR/WORKER/GATE/OTHER)
       └─ ai_tool_call   도구 호출. arguments_json, result_json, 토큰·비용
            └─ ai_llm_call   LLM API 호출(과금 단위). provider/model/purpose,
                             user_id·agent_id 비정규화(집계 성능)
  └─ ai_retrieval_source   RAG 검색 근거. collection_name, document_id, chunk_id, score
```

### 5-4. 주요 엔티티 관계 요약

```
users ─< refresh_tokens / user_departments / user_profiles
        / user_permissions / user_agent_subscription
departments ─< user_departments / collection_permissions / agent_definition
llm_model ─< agent_definition / ai_run / ai_run_step / ai_tool_call / ai_llm_call
agent_definition ─< agent_tool / user_agent_subscription / ai_run
tool_catalog ─< agent_tool        mcp_server_registry ─< tool_catalog
ai_run ─< ai_run_step / ai_tool_call / ai_llm_call / ai_retrieval_source
permissions ─< role_permissions / user_permissions
evaluation_run ─< evaluation_result
```

---

## 6. 프론트엔드 구조 (`idt_front/src/`)

### 6-1. 화면 (22 페이지 — `src/pages/`)

**사용자**: ChatPage, AgentBuilderPage, AgentStorePage, AgentPage, AgentRunDetailPage, CollectionPage, CollectionDocumentsPage, DocumentPage, ToolConnectionPage, ToolAdminPage, EvalDatasetPage, UsageMePage, SettingsPage, WorkflowDesignerPage, WorkflowBuilderPage

**관리자** (`/admin/*`): AdminUsersPage, AdminDepartmentsPage, AdminRagasPage, AdminAgentRunsPage, AdminMcpServersPage

**인증**: LoginPage, RegisterPage

### 6-2. 라우팅 (`src/App.tsx`)
- 공개: `/login`, `/register`
- 보호(`ProtectedRoute` + `AgentChatLayout`): 사용자 화면 전체
- 관리자(`AdminRoute` + `AdminLayout`): `/admin/*`, 진입점 `/admin/users`
- 관리자 내비: `src/constants/adminNav.ts` (5개 섹션)

### 6-3. 상태관리 (Zustand — `src/store/`)
`authStore`(유저·토큰), `chatStore`, `chatPreferencesStore`, `agentStore`, `documentStore`, `layoutStore`, `commonSlices`

### 6-4. API 연동
- 엔드포인트 상수: `src/constants/api.ts` (`API_BASE_URL=http://localhost:8000`, `WS_BASE_URL=ws://localhost:8000`)
- HTTP: `src/services/api/client.ts` (axios + interceptor), 에러: `ApiError.ts`
- 쿼리키: `src/lib/queryKeys.ts` (계층형 TanStack Query 키)
- 서비스 28+개 / 훅 35+개 (도메인별 분리)
- WebSocket: `/ws/agent/{runId}`, `/ws/chat/{sessionId}`, `/ws/echo`

---

## 7. 환경변수 / 외부 연동

설정 로딩: `idt/src/config.py` / 템플릿: `idt/.env.example`

| 서비스 | 핵심 env | 용도 |
|--------|----------|------|
| MySQL | `DATABASE_URL` (mysql+asyncmy://) | RDB. pool 5 / overflow 10 / pre-ping |
| Qdrant | `QDRANT_HOST/PORT`, `QDRANT_COLLECTION_NAME` | 벡터 저장 |
| OpenAI | `OPENAI_API_KEY`, `OPENAI_EMBEDDING_MODEL`(기본 text-embedding-3-small), `OPENAI_LLM_MODEL`(기본 gpt-4o-mini) | LLM/임베딩 |
| Anthropic | `ANTHROPIC_API_KEY` | Claude 에이전트 |
| Ollama | `OLLAMA_BASE_URL`(기본 :11434), `OLLAMA_DEFAULT_MODEL`(llama3.2) 등 | 로컬 LLM |
| Elasticsearch | `ES_HOST/PORT/SCHEME`, `ES_INDEX`(기본 documents), 인증·재시도 옵션 | 전문 검색 |
| Redis | `REDIS_HOST/PORT/PASSWORD/DB`, `REDIS_MAX_CONNECTIONS`(20) | 세션/자동빌드 상태 |
| PDF | `PARSER_TYPE`(pymupdf/pymupdf4llm/llamaparser), `LLAMA_PARSE_API_KEY` | 파서 선택 |
| 청킹 | `DEFAULT_CHUNK_SIZE`(1000), `DEFAULT_CHUNK_OVERLAP`(100) | 토큰 청킹 |
| RAG | `RAG_VECTOR_SCORE_THRESHOLD`(0=비활성) | 벡터 임계값 |
| 웹검색 | `TAVILY_API_KEY` | Tavily |
| Excel분석 | `ANALYSIS_MAX_RETRIES`(3), `ANALYSIS_MIN_CONFIDENCE_SCORE`(0.7), `ANALYSIS_MAX_HALLUCINATION_SCORE`(0.3) 등 | 재시도/환각 정책 |
| 차트 | `CHART_MAX_COUNT`(3, 0=비활성) | 응답당 최대 차트 |
| 검색파이프라인 | `SEARCH_PIPELINE_PROVIDER/MODEL_NAME`(openai/gpt-4o-mini), `SEARCH_COMPRESS_THRESHOLD`(4000) | 경량 LLM |
| MCP | `MCP_SECRET_KEY` (Fernet, 빈 값이면 SSE 전용) | 시크릿 암호화 |
| 인증 | `JWT_SECRET_KEY`(필수, 32B+), `JWT_ALGORITHM`(HS256), access 15분 / refresh 7일 | JWT |
| 관측 | `LANGSMITH_TRACING`, `LANGCHAIN_ENDPOINT/API_KEY` | LangSmith(선택) |
| 앱 | `DEBUG`(false) | 디버그 모드 |

**프론트 (`idt_front/.env.local`)**: `VITE_API_BASE_URL`, `VITE_WS_URL`

---

## 8. 개발/운영 규칙 (요약)

- **TDD 필수** (양 프로젝트): 테스트 먼저 → 실패 확인 → 구현 → 통과. 백엔드 pytest / 프론트 Vitest+RTL+MSW.
- **DDD 의존성 금지**: domain → infrastructure 참조 금지. router에 비즈니스 로직 금지.
- **세션/트랜잭션**: 요청 스코프 AsyncSession(`Depends(get_session)`), Repository 내부 commit/rollback 금지, 한 UseCase 내 단일 세션.
- **로깅**: `print()` 금지, StructuredLogger 사용, 스택 트레이스 포함 에러 처리.
- **금지**: 대화 기록을 vector DB에 저장, spec에 없는 기능 구현, 임의 스키마 변경, Parent/Child 문서 구조 변경.
- **세부 규칙**: `idt/docs/rules/` (db-session / logging / conversation-memory / rag-retrieval / testing).

### 개발 서버
```bash
# 백엔드 (idt/)
uvicorn src.api.main:app --reload --port 8000   # 또는 python run_server.py
# 프론트 (idt_front/)
npm run dev
```

---

## 9. 알려진 이슈 / 주의사항 (테스트 환경)

> 신규 회귀로 오인 금지 — 환경 기인 사전 실패.

- **백엔드 pytest**: Windows 이벤트 루프 teardown 산발 실패 → 격리 실행으로 검증.
- **프론트 vitest**: 기본 forks 풀이 Windows에서 워커 기동 타임아웃 → `--pool=threads` 사용.
- **프론트 npm install**: `--legacy-peer-deps` 필요.
- **차트 렌더링**: 프론트/백엔드 모두 General Chat 경로에만 연결됨 (Excel/Supervisor는 후속).

---

## 10. 참조 문서

| 문서 | 위치 |
|------|------|
| 루트 내비게이터 / 규칙 | `CLAUDE.md`, `idt/CLAUDE.md` |
| 백엔드 세부 규칙 | `idt/docs/rules/*.md` |
| Task 레지스트리 | `idt/docs/task-registry.md` |
| PDCA 문서 | `docs/01-plan ~ 04-report`, `docs/archive/` |
| 기능 계획(예: Naver Search MCP) | `docs/01-plan/features/` |

---

*본 문서는 코드/마이그레이션/설정 직접 조사로 작성됨. 스키마(Flyway), API(main.py), 모델(models.py)은 코드가 최종 진실이며, 변경 시 본 SOT의 갱신 기준일과 해당 섹션을 함께 갱신할 것.*
