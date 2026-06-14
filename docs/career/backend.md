# 경력기술서 — 백엔드 (AI Platform)

> 초안 / 작성일: 2026-05-26

---

## 인적사항

| 항목 | 내용 |
|------|------|
| 이름 | 배상규 |
| 이메일 | tkdrb136@gmail.com |
| 경력 | 저축은행 여신 시스템 개발 약 3년 10개월 |
| 포지션 지원 | AI / 백엔드 엔지니어 |

---

## 한 줄 요약

> **금융/정책 문서 도메인에서 RAG 파이프라인과 LangGraph 기반 멀티 에이전트 시스템을 Thin DDD 아키텍처 위에 TDD로 1인 설계/구현한 백엔드 엔지니어.**

---

## 프로젝트 — sangplusbot (Intelligent Document Toolkit)

| 항목 | 내용 |
|------|------|
| 기간 | 2026.04 ~ 현재 (진행 중) |
| 역할 | 백엔드 단독 설계/개발 (1인) |
| 도메인 | 금융/정책 문서 특화 RAG · AI Agent 플랫폼 |
| 코드베이스 | Python 3.11 / FastAPI / LangGraph / 백엔드 단독 약 676 소스 파일, 398 테스트 파일, 22개 DB 마이그레이션 |

### 프로젝트 개요

금융·정책 문서를 업로드하면 자동으로 파싱·청킹·이중 색인(Vector + BM25)하고, 사용자가 자연어로 질의하면 출처 기반으로 답변하는 RAG 시스템.
GUI에서 정의한 사양을 백엔드에서 LangGraph 그래프로 동적 컴파일해 실행하는 **Custom Agent Builder** 및 자연어 한 줄로 에이전트를 자동 생성하는 **Auto Agent Builder**를 핵심 차별 기능으로 구현했다.

---

## 1. 기술 스택 (백엔드)

| 영역 | 기술 |
|------|------|
| 언어 / 프레임워크 | Python 3.11, FastAPI, SQLAlchemy (Async), Pydantic v2 |
| AI · LLM | LangChain, LangGraph, LangSmith, OpenAI / Anthropic / Ollama |
| 벡터 / 검색 | Qdrant, Elasticsearch 8 (BM25), Kiwipiepy (한국어 형태소) |
| 저장소 | MySQL (RDB) + Flyway 마이그레이션 22 버전, Redis (세션/캐시) |
| 외부 도구 | MCP (Model Context Protocol), Tavily Search |
| 비동기 / 통신 | asyncio, SSE (스트리밍), WebSocket |
| 품질 도구 | pytest / pytest-asyncio, Ruff, mypy strict, Custom Verify Skills (architecture/logging/tdd) |

---

## 2. 백엔드 아키텍처

### 2-1. Thin DDD 4계층

```
interfaces (FastAPI Router, Pydantic 스키마, Middleware)
        ↓ 요청/응답 변환만 수행
application (UseCase / Workflow / LangGraph Graph)
        ↓ 흐름 제어 · 오케스트레이션
domain (Entity / Value Object / Policy / Interface)
        ↑ 의존성 역전 (DIP)
infrastructure (MySQL / Qdrant / Elasticsearch / OpenAI / Redis Adapter)
```

**설계 원칙**

- Domain 레이어는 외부 의존성(DB, LangChain, LLM API) 참조를 **완전 금지**, Protocol/Interface만 정의
- Infrastructure가 Domain Interface를 구현하여 의존성 역전(DIP) 강제
- UseCase는 비즈니스 규칙을 직접 구현하지 않고 Domain Policy에 위임
- FastAPI `Depends` + `dependency_overrides`로 의존성 주입 → 라우터/유스케이스 테스트 시 어댑터를 가짜 구현으로 치환

**규모**

- Domain 서브모듈: 54개 (entities / policies / interfaces 등)
- Application UseCase 서브모듈: 39개
- Infrastructure 어댑터 서브모듈: 48개
- API Router: 36개

### 2-2. 트랜잭션·세션 정책

- Repository 내부에서 `commit()` / `rollback()` 호출 금지 — UseCase가 트랜잭션 경계 보유
- 한 UseCase 안에서는 단일 세션 공유 (서로 다른 Repository가 다른 세션을 쓰지 못하도록 강제)
- `get_session_factory()()` 패턴 금지 (검증 스킬로 정적 차단)

### 2-3. 자체 정의 검증 스킬 (Architecture-as-Code)

규칙을 문서로만 두지 않고 검증 스크립트로 자동화:

- `verify-architecture`: 레이어 의존성 위반(`domain → infrastructure` 등) 검출
- `verify-logging`: LOG-001(구조화 로깅 / `request_id` 전파 / 스택 트레이스) 위반 검출
- `verify-tdd`: 프로덕션 모듈 대비 테스트 파일 누락 검출

---

## 3. AI / LLM 엔지니어링

### 3-1. 문서 인제스트 파이프라인 (LangGraph StateGraph)

PDF 업로드 → 벡터/BM25 저장까지 전 과정을 **LangGraph StateGraph**로 노드 분리:

| 노드 | 책임 |
|------|------|
| Parse | LlamaParse / PyMuPDF 추상화 (표·수식 포함 추출) |
| Classify | LLM 기반 카테고리 자동 분류 (금융 / 정책 / 일반) |
| Chunk | Strategy 패턴으로 청킹 전략 다형 (Full-Token / Parent-Child / Semantic) |
| Store | Qdrant 벡터 + Elasticsearch BM25 **이중 색인** |

청킹 전략은 Domain의 `ChunkStrategy` 인터페이스 1개 + Infra 구현 N개로 분리해, 새 전략 추가 시 Application 코드 변경 없이 확장 가능.

### 3-2. 하이브리드 검색 + 출처 기반 RAG

```
사용자 질의
    ├─ Qdrant 벡터 검색 (의미 유사도 top-k)
    └─ Elasticsearch BM25 (키워드 일치 top-k)
            ↓
    RRF (Reciprocal Rank Fusion) 병합 랭킹
            ↓
    LLM 문서 압축기 (관련/무관 binary 필터링)
            ↓
    Supervisor + Multi-Worker LangGraph (3-3 참조)
            ↓
    할루시네이션 평가기 (binary) → 실패 시 재검색/재생성
```

- **한국어 품질 보강**: Kiwipiepy 형태소 분석으로 NNG/NNP/VV·VA 추출 후 BM25 색인 — 영어 위주 임베딩이 놓치는 키워드 보강
- **할루시네이션 평가 모듈(EVAL-001)**: 응답의 문서 근거성 여부를 Domain Policy로 정의, Infrastructure에서 LLM 호출 구현 (DIP)
- **대화 메모리 정책**: 6턴 초과 시 자동 요약, 대화 기록은 **MySQL에만 저장 / Vector DB 금지** (의도치 않은 문서-대화 교차 검색 방지)

### 3-3. Multi-Agent LangGraph — Supervisor + Worker 아키텍처

> 초기에는 LangGraph `create_react_agent` 한 개로 동작하던 RAG Agent를, **자체 `StateGraph` 기반 Supervisor + Multi-Worker 그래프**로 전면 재설계. Prebuilt Supervisor 대신 비즈니스 정책(품질 게이트·재시도·서브에이전트·관측성)을 직접 제어할 수 있는 커스텀 그래프로 구현했다.

#### 그래프 토폴로지

```
                ┌─────────────────┐
                │   supervisor    │  (LLM with_structured_output)
                │  next / reason  │
                └────────┬────────┘
        ┌──────────┬─────┴─────┬──────────┬───────────┐
        ▼          ▼           ▼          ▼           ▼
  search_worker  action_w.  sub_agent  answer_agent  __end__
  (LLM 미사용,  (create_   (재귀     (검색결과
   tool 직접   react_agent)  컴파일)   종합)
   호출)          │            │          │
        └─────────┴────────────┴──────────┘
                       ▼
              ┌─────────────────┐
              │  quality_gate   │  (Domain Policy 평가 + 재시도 라우팅)
              └────────┬────────┘
                       ▼  pass: supervisor / fail: 같은 worker 재호출
```

#### 핵심 구성 요소

| 노드 | 역할 | 구현 포인트 |
|------|------|------------|
| **supervisor** | 다음 워커 결정 + 직접 종료/답변 | LLM `with_structured_output(SupervisorDecision)` — `next` / `reasoning` / `answer` 세 필드를 한 번에 추출. `iteration_count` / `token_usage` 예산을 노드 진입 시 검사 |
| **search worker** | 검색 도구 직접 호출 | **LLM 호출 없이** `tool.ainvoke(query)` 직접 실행 → 토큰·지연 절감 |
| **action worker** | 일반 도구 사용 워커 | LangGraph `create_react_agent` 사용 |
| **sub_agent worker** | 다른 에이전트를 워커처럼 임베드 | `WorkflowCompiler.compile()` 재귀 호출, `NestingDepthPolicy` + `CircularReferencePolicy`로 깊이·순환 차단 |
| **answer_agent (virtual)** | 검색 결과 종합 응답 | 검색 워커가 1개 이상이면 자동 추가. 검색 결과 메시지(`name=worker_id`)와 대화 맥락을 분리해 멀티턴에서도 첫 user 메시지 누락 없이 답변 |
| **quality_gate** | 응답 품질 검증 + 재시도 | `QualityGatePolicy.check_response()`. 실패 시 동일 워커에 피드백 메시지 주입해 `max_retries_per_worker`까지 재시도 |

#### Supervisor 의사결정 — 구조화 출력으로 무한루프·환각 방지

```python
class SupervisorDecision(BaseModel):
    next: str          # 다음 worker_id 또는 'FINISH'
    reasoning: str     # 선택 이유 (관측성 자동 기록)
    answer: str = ""   # FINISH 시 워커 호출 없이 직접 응답
```

- LLM이 자유 텍스트로 워커명을 뱉어도 무방하게 → Pydantic 스키마로 강제, 알 수 없는 worker_id는 즉시 `__end__`로 안전 종료
- `reasoning`을 추출 부담 없이(필수 필드라 비용 미증가) **AGENT-OBS-003 step output_summary로 자동 영속화** → 사후 디버깅 가능
- 워커 호출이 불필요한 잡담성 질의는 `FINISH + answer`로 단축 종료 → 검색 토큰 소비 제거

#### 비즈니스 정책을 코드로 강제 (Hooks)

```python
class SupervisorHooks(Protocol):
    def force_worker(self, state) -> str | None   # 특정 워커 강제 호출
    def skip_workers(self, state) -> list[str]    # 워커 후보에서 제외
```

- 정책 변경을 그래프 재컴파일 없이 외부 주입으로 가능
- 예: 권한 없는 사용자에게는 외부 검색 워커 스킵, 특정 의도 분류 시 답변 워커 강제

#### 관측성 자동 연결 (AGENT-OBS-001/003)

- 모든 노드를 `track_step` 컨텍스트 매니저로 래핑 → `ai_run_step` 영속화 + `ai_tool_call.step_id` / `ai_llm_call.step_id` FK 자동 연결
- `RunPurpose`를 `ContextVar`로 전파해 어떤 LLM/도구 호출이 어느 노드에서 발생했는지 사후 추적
- `tracker / callback / run_id` 중 하나라도 None이면 원본 함수 그대로 반환 → **관측성 OFF 시 zero-overhead**

### 3-4. Agent Builder — 3세대 아키텍처

위 Supervisor 그래프 위에서 **"에이전트를 어떻게 정의·생성하느냐"**를 3세대로 점진 확장. 각 세대는 이전 세대 소스를 일절 수정하지 않는 **Zero-Modification** 원칙으로 누적:

| 세대 | 모듈 | 핵심 |
|------|------|------|
| **v1** | Custom Agent Builder | GUI 사양 → LLM이 도구 자동 선택 + 시스템 프롬프트 생성 → **WorkflowCompiler가 Supervisor 그래프(3-3)로 동적 컴파일** |
| **v2** | Middleware Agent Builder | LangChain `create_agent` API + 횡단 관심사를 미들웨어로 선언적 조합 |
| **v3** | Auto Agent Builder | 자연어 한 문장 → LLM이 도구·미들웨어 자동 추론, confidence < 0.8 시 보충 질문 (최대 3라운드), confidence ≥ 0.8 시 즉시 v2로 생성 |

**WorkflowCompiler**: `WorkflowDefinition` (Domain Value Object) → 위 3-3의 Supervisor + Worker 그래프로 동적 변환하는 컴파일러. Multi-LLM(OpenAI / Anthropic / Ollama)을 LLM Model Registry에서 런타임 선택.

**적용 미들웨어 (LangChain)**

| 미들웨어 | 효과 |
|---------|------|
| SummarizationMiddleware | 장문 컨텍스트 자동 압축 |
| PIIMiddleware | 개인정보 자동 마스킹 |
| ToolRetryMiddleware | 도구 실패 시 자동 재시도 |
| ModelCallLimitMiddleware | LLM 호출 횟수 상한 |
| ModelFallbackMiddleware | 기본 모델 실패 시 폴백 모델 자동 전환 |

### 3-5. Dynamic MCP (Model Context Protocol) Registry

- MCP 서버 CRUD를 DB로 관리 → **배포 없이 런타임에 새 외부 도구 등록**
- `MCPToolLoader`가 stdio / SSE / WebSocket 채널로 연결, LangChain `BaseTool`로 어댑팅
- 부분 실패 격리: MCP 서버 1개 다운이 나머지 도구의 가용성에 영향 주지 않도록 설계
- Agent Builder UI에서 등록된 MCP 도구를 선택해 Agent에 바인딩

### 3-6. Agent Run Observability (최근 완료 피처, Match Rate 98%)

- 에이전트 실행 1회당 비용·지연·토큰 사용량을 집계해 별도 테이블에 저장
- 라우팅/에이전트별 일/주/월 집계 + 검색 인덱스 (`V023__add_agent_run_aggregate_indexes.sql`)
- LangSmith 트레이스 연동으로 디버깅·평가 자동화

---

## 4. 검색 / 데이터 인프라

| 컴포넌트 | 책임 | 비고 |
|---------|------|------|
| **Qdrant** | 임베딩 저장 / 의미 검색 | 단일 컬렉션 + tenant_id 필터 전략 |
| **Elasticsearch** | BM25 키워드 검색 / 형태소 색인 | Kiwi 형태소 + 위치 메타데이터(offset, sentence_index) |
| **MySQL** | Agent 정의, 대화 히스토리, 사용자 데이터 | Async SQLAlchemy, Flyway 마이그레이션 22 버전(V002~V023) |
| **Redis** | 세션·캐시·분산 잠금 | Auto Agent Builder 인터뷰 세션(TTL 24h) |

### MySQL Generic Repository

Domain Interface 1개 + Infra `MySQLBaseRepository` 1개 + 도메인별 Repository를 얇게 상속하는 형태로 boilerplate 제거. 필터링은 8가지 연산자(`eq`, `in`, `gt`, `lt`, `like`, ...)를 지원하는 공통 쿼리 빌더로 추상화.

### 부서 기반 권한 + 컬렉션 권한 (RBAC)

- 부서 → 컬렉션 → 문서 3단계 권한 모델
- 컬렉션 단위 `owner / editor / viewer` 역할 분리
- 활동 로그를 Fire-and-Forget 비동기 큐로 적재해 본 흐름의 지연을 만들지 않음

---

## 5. 테스트 / 품질 전략

| 영역 | 적용 |
|------|------|
| TDD 사이클 | 모든 신규 모듈에 Red → Green → Refactor 강제 (verify-tdd 스킬로 정적 검사) |
| 레이어별 테스트 | Router(통합) / UseCase(AsyncMock) / Domain Policy(순수 유닛, Mock 금지) / Infrastructure(TestContainer 또는 Mock) |
| 비동기 코드 | pytest-asyncio + AsyncMock |
| API 통합 | FastAPI TestClient + `dependency_overrides`로 어댑터 치환 |
| 정적 검증 | Ruff / mypy strict / 자체 verify-architecture·verify-logging 스킬 |
| 로깅 | 구조화 로깅 + `request_id` 전파 + 예외 시 스택 트레이스 필수 (LOG-001) |

**규모 — 백엔드 단독**

| 지표 | 값 |
|------|-----|
| 소스 파일 수 | 676 |
| 테스트 파일 수 | 398 |
| DB 마이그레이션 버전 | 22 |
| API 라우터 | 36 |
| Domain 서브모듈 | 54 |
| Application UseCase | 39 |
| Infrastructure 어댑터 | 48 |

---

## 6. 개발 프로세스

- **PDCA 사이클**: Plan → Design → Do → Check(Gap 분석) → Act(Iterate). 직전 피처(Agent Run Observability)는 Match Rate 98%로 완료.
- **Feature Branch + PR**: 모든 변경은 PR 단위로 머지, 컨벤션·금지 규칙은 `CLAUDE.md`로 코드 옆에 명문화.
- **DB 변경**: Flyway 형식 SQL 마이그레이션만 허용, ORM auto-migrate 금지.
- **AI 보조 개발 활용**: bkit / Claude Code 기반 자체 스킬(verify-architecture / verify-logging / verify-tdd / api-contract)로 규칙을 자동화하여 1인 개발 환경에서도 일관된 품질 유지.

---

## 7. 이 프로젝트에서 입증한 백엔드 역량

| 역량 | 입증 사례 |
|------|----------|
| **AI / LLM 시스템 설계** | LangGraph StateGraph로 인제스트·RAG·Multi-Agent 파이프라인 구축, Agent Builder 3세대 진화(Zero-Modification) |
| **RAG / 검색 엔지니어링** | Vector + BM25 + RRF 하이브리드, Kiwi 형태소 이중 색인, 할루시네이션 평가 루프 |
| **백엔드 아키텍처** | Thin DDD 4계층 + DIP를 코드와 자체 검증 스킬로 강제, 트랜잭션 경계 정책 명문화 |
| **확장 가능한 설계** | Strategy(청킹), Policy(평가/비밀번호/대화), Generic Repository, Dynamic MCP Registry — 모두 "수정 없이 추가"가 가능한 구조 |
| **테스트 주도 개발** | 백엔드 소스 676 vs 테스트 398 (테스트 코드 라인 비율 130% 이상), 레이어별 테스트 전략 차별화 |
| **운영·관측성** | 구조화 로깅 + request_id 전파 + LangSmith 연동 + Agent Run 비용/지연 집계 |
| **1인 풀사이클 개발** | 1인 환경에서 PDCA + Feature Branch + 자체 검증 스킬로 대규모 코드베이스(676 파일) 일관성 유지 |

---

## 8. 향후 개선 계획 (백엔드)

| 항목 | 계획 |
|------|------|
| 배포 인프라 | Docker Compose → Kubernetes 기반 배포로 확장 |
| CI/CD | GitHub Actions로 테스트·verify 스킬·마이그레이션 검증 자동화 |
| 관측성 | OpenTelemetry 도입, LangSmith + 자체 로그를 통합 대시보드화 |
| 검색 품질 | 리랭커(Cross-Encoder) 도입, 쿼리 재작성 평가 지표화 |
| 평가 자동화 | RAGAS 기반 지속 평가 파이프라인을 nightly job으로 정착 |

---

*작성일: 2026-05-26 (초안)*
