# 아키텍처 개요 (Architecture Overview)

> 신규 개발자를 위한 한 페이지 요약.
> RAG(검색 증강 생성) 기반 문서 질의응답 + AI Agent 대화 플랫폼인 **sangplusbot**의 전체 그림을 빠르게 잡는 것이 목적이다.
> 레이어별 상세 규칙은 각 디렉토리의 `CLAUDE.md`를 참조한다.

---

## 1. 한눈에 보기

```
┌─────────────────────────────┐         ┌─────────────────────────────────┐
│   idt_front/  (React SPA)    │  HTTP   │        idt/  (FastAPI)          │
│  React 19 + TS + Vite        │ ──────▶ │  Thin DDD 백엔드 API 서버        │
│  Zustand · TanStack Query    │  SSE /  │  LangGraph / LangChain 기반      │
│  :5173 (Vite dev)            │   WS    │  :8000 (uvicorn)                 │
└─────────────────────────────┘         └───────────────┬─────────────────┘
                                                         │
                                   ┌─────────────────────┼─────────────────────┐
                                   ▼                     ▼                     ▼
                              MySQL (RDB)          Qdrant (Vector)        OpenAI / LLM
                          대화·에이전트·메타       문서 임베딩 검색        응답·임베딩 생성
```

- **통신 방식**: 일반 요청은 REST(JSON), 토큰 스트리밍은 **SSE**, 실시간 양방향은 **WebSocket**.
- **데이터 저장**: 정형 데이터(대화 기록, 에이전트 정의, 사용자/부서)는 **MySQL**, 문서 임베딩은 **Qdrant**.
- **외부 의존**: OpenAI(LLM·임베딩), Tavily/Perplexity(웹 검색), MCP 서버 레지스트리(외부 도구 연동).

---

## 2. 백엔드 (`idt/`) — Thin DDD 4-레이어

백엔드는 **도메인 → 애플리케이션 → 인프라스트럭처 → 인터페이스**로 나뉜 얇은 DDD 구조다.
의존성은 항상 안쪽(domain)을 향하며, **domain → infrastructure 역참조는 금지**된다.

| 레이어 | 디렉토리 | 책임 | 하지 말 것 |
|--------|----------|------|-----------|
| **Domain** | `src/domain/` | Entity·VO·Policy 등 순수 비즈니스 규칙, 인터페이스 정의 | 외부 API·DB·LangChain 직접 사용 |
| **Application** | `src/application/` | UseCase, Workflow, LangGraph 그래프 — 흐름 제어 | 비즈니스 규칙 직접 구현 |
| **Infrastructure** | `src/infrastructure/` | MySQL·Qdrant·OpenAI 어댑터, 영속성, 로거 구현 | 비즈니스 규칙 포함 |
| **Interfaces** | `src/interfaces/` + `src/api/` | FastAPI 라우터, 요청/응답 스키마, 미들웨어 | 비즈니스 로직 작성 |

### 요청이 흐르는 경로

```
HTTP 요청
  → src/api/routes/*_router.py        (라우터: 입출력 스키마 검증)
  → src/interfaces/schemas/           (Pydantic 요청/응답 모델)
  → src/application/<feature>/        (UseCase·Workflow가 흐름 조율)
  → src/domain/<feature>/             (규칙·정책 판단)
  → src/infrastructure/<feature>/     (DB·벡터·LLM 실제 호출)
  → 응답 (JSON / SSE 스트림 / WS 메시지)
```

> 도메인은 기능별로 동일한 이름의 폴더가 `domain/`·`application/`·`infrastructure/`에 나란히 존재한다
> (예: `rag_agent`, `conversation`, `mcp_registry`, `research_agent`). 한 기능을 따라갈 때 세 레이어를 함께 본다.

### 핵심 기능 도메인

- **RAG 파이프라인**: `ingest`(PDF 파싱·청킹·임베딩) → `retrieval`/`hybrid_search`(BM25 + Vector) → `rag_agent`(ReAct 검색 응답).
- **Agent 빌더**: `agent_builder`(v1) · `middleware_agent`(v2) · `auto_agent_builder`(자연어 자동 생성, v3).
- **대화/메모리**: `conversation` (멀티턴, user_id + session_id 기반 요약 메모리). 대화 기록은 **벡터 DB에 저장하지 않는다**.
- **플랫폼 관리**: `auth`(JWT + 관리자 승인), `department`/`permission`(RBAC), `mcp_registry`(외부 도구 등록), `ragas`(평가).

### 진입점 & DB

- **앱 엔트리**: `idt/src/api/main.py` (라우터 등록), 실행 래퍼는 `idt/run_server.py`.
- **마이그레이션**: Flyway 형식 SQL이 루트 `db/migration/` (`V001__...sql` …)에, SQLAlchemy 마이그레이션은 `idt/alembic/`에 위치.

---

## 3. 프론트엔드 (`idt_front/`) — React SPA

| 항목 | 선택 |
|------|------|
| 프레임워크 | **React 19 + TypeScript** |
| 빌드 도구 | **Vite 8** |
| 스타일링 | **Tailwind CSS v4** (`@tailwindcss/vite`) + shadcn/ui |
| 서버 상태 | **TanStack Query v5** (`useQuery`/`useMutation`) |
| 전역 상태 | **Zustand** (슬라이스 팩토리 조합) |
| 라우팅 | **React Router** |
| HTTP | **Axios** (`services/api/`의 공개/인증 클라이언트 분리) |
| 스트리밍 | **SSE**(`useStream`) + **WebSocket**(`useWebSocket`) |
| 테스트 | **Vitest + React Testing Library + MSW** |

### 레이어 흐름

```
pages/        라우트 단위 페이지 (ChatPage, AgentStorePage, Admin*Page …)
  └─ components/   재사용 UI (chat · agent · rag · admin · common · layout)
       └─ hooks/        도메인 훅 (useChat · useAgent · useDocuments · useAuth)
            └─ services/     API 호출 계층 (컴포넌트에서 직접 axios 호출 금지)
                 └─ types/        백엔드 스키마와 동기화된 TS 타입
```

- **상태 원칙**: 서버 상태는 TanStack Query, 클라이언트 전역은 Zustand, 로컬은 `useState`. 쿼리 키는 `lib/queryKeys.ts` 팩토리에서만 생성.
- **API 상수**: 모든 엔드포인트는 `src/constants/api.ts`에 중앙 관리.

---

## 4. 디렉토리 맵

```
sangplusbot/
├── idt/                         # 백엔드 (FastAPI · Thin DDD)
│   └── src/
│       ├── api/                 #   라우터(routes/) + main.py 엔트리
│       ├── interfaces/          #   요청/응답 스키마, 의존성 주입
│       ├── application/         #   UseCase · Workflow · LangGraph 그래프
│       ├── domain/              #   Entity · VO · Policy (순수 규칙)
│       ├── infrastructure/      #   MySQL · Qdrant · OpenAI 어댑터
│       └── config.py            #   설정 로딩
│   └── alembic/                 # SQLAlchemy 마이그레이션
│
├── idt_front/                   # 프론트엔드 (React 19 SPA)
│   └── src/
│       ├── pages/               #   라우트 페이지
│       ├── components/          #   UI 컴포넌트 (도메인별)
│       ├── hooks/               #   커스텀 훅 (비즈니스 로직)
│       ├── services/            #   API 통신 계층
│       ├── store/               #   Zustand 전역 상태
│       ├── types/               #   TS 타입 (백엔드 스키마 동기화)
│       ├── constants/           #   API 엔드포인트 등 상수
│       └── lib/                 #   QueryClient · queryKeys
│
├── db/migration/                # Flyway 형식 SQL 마이그레이션 (V001__…)
├── docs/                        # PDCA 설계 문서 (01-plan ~ 04-report)
└── CLAUDE.md                    # 루트 내비게이터 (서브프로젝트 규칙 링크)
```

---

## 5. 개발 서버 실행

전제: 백엔드 `idt/.env`, 프론트 `idt_front/.env.local` 환경변수가 채워져 있어야 한다.

```bash
# 터미널 1 — 백엔드 (idt/ 에서)
uvicorn src.main:app --reload --port 8000
#   → API:    http://localhost:8000
#   → Swagger: http://localhost:8000/docs

# 터미널 2 — 프론트엔드 (idt_front/ 에서)
npm install      # 최초 1회
npm run dev
#   → 웹 UI:  http://localhost:5173
```

### 주요 환경변수

```
idt/.env
  OPENAI_API_KEY
  MYSQL_HOST / MYSQL_PORT / MYSQL_USER / MYSQL_PASS / MYSQL_DB
  QDRANT_URL / QDRANT_API_KEY
  TAVILY_API_KEY / PERPLEXITY_API_KEY

idt_front/.env.local
  VITE_API_BASE_URL=http://localhost:8000
  VITE_WS_URL=ws://localhost:8000
```

### 자주 쓰는 프론트 스크립트

```bash
npm run dev          # 개발 서버
npm run build        # 프로덕션 빌드 (tsc -b && vite build)
npm run test         # 테스트 (watch)
npm run type-check   # 타입 검사
npm run lint         # ESLint
```

---

## 6. 핵심 규칙 (반드시 기억)

1. **API 계약 동기화** — 백엔드 스키마(`idt/src/interfaces/schemas/`)를 바꾸면 프론트 타입(`idt_front/src/types/`)·서비스·훅도 함께 수정한다. 엔드포인트 상수는 `idt_front/src/constants/api.ts`.
2. **TDD 우선** — 두 프로젝트 모두 테스트 없이 구현 코드를 먼저 작성하지 않는다 (백엔드 pytest, 프론트 Vitest, Red → Green → Refactor).
3. **레이어 경계 준수** — 백엔드는 domain → infrastructure 역참조 금지, 라우터에 비즈니스 로직 금지. 프론트는 컴포넌트에서 직접 axios 호출 금지.
4. **대화 메모리 정책** — 대화 기록은 MySQL에만 저장하며 벡터 DB에 넣지 않는다.

> 더 깊은 규칙: 백엔드는 `idt/CLAUDE.md`와 `idt/docs/rules/`, 프론트는 `idt_front/CLAUDE.md`를 참조.
