---
title: 백엔드 아키텍처 조감도 — 요청→응답 전체 경로
status: draft
source_type: conversation
source_refs:
  - idt/src/api/main.py (컴포지션 루트, 라우터 52 등록, lifespan)
  - idt/src/application/background_job/worker.py (v2 추가 — lifespan 워커 싱글턴)
  - idt/src/application/general_chat/use_case.py (v2 추가 — tool_filter optional 이음매)
  - idt/src/api/routes/ws_router.py (/ws/chat, /ws/agent 와이어 프로토콜)
  - idt/src/api/routes/agent_builder_router.py (SSE text/event-stream)
  - idt/src/application/general_chat/use_case.py (stream() transport-독립 설계)
  - idt/src/application/agent_builder/run_agent_use_case.py, workflow_compiler.py, supervisor_nodes.py
  - idt/src/application/hybrid_search/use_case.py, multi_query/workflow.py
  - idt/src/application/ingest/ingest_use_case.py
  - idt/src/application/eval/use_cases.py (_kickoff_feedback_fanout)
  - docs/SOURCE-OF-TRUTH.md (2026-07-23, 커밋 6cc25656 기준 전면 갱신본)
confidence: 0.9
version: 2
created: 2026-07-23
updated: 2026-08-14
verified_at: 12c69b4
---

> v2에서 실행 경로 (e) 백그라운드 잡과 §2-(a)의 도구 선별 이음매를 추가하며
> approved → draft로 강등했다 (재승인 필요). 나머지 절은 v1 그대로.

# 백엔드 아키텍처 조감도 — 요청→응답 전체 경로

> 미니 ERD(`backend/db/erd-*.md`)·화면↔API 지도(`frontend/screens/*.md`)의 **한 단계 위** 문서.
> "어느 레이어의 어느 모듈을 지나는가"를 한 번에 잡을 때 읽는다. 세부 계약은 하위 문서로.

## 문제

idt/는 라우터 52개·application 모듈 40+개 규모라, 개별 파일을 아무리 읽어도
"요청이 어디를 거쳐 응답이 되는가"의 전체 그림이 보이지 않는다. 특히
(1) DI가 어디서 일어나는지, (2) LangGraph 그래프가 언제 만들어지는지,
(3) 성장 루프가 어느 레이어에 붙어 있는지는 코드 산책만으로는 조립되지 않는다.

## 검증된 사실

### 1. 표준 경로 (모든 HTTP 요청 공통)

```
FastAPI router (src/api/routes/*, 52 등록)
  → interfaces 스키마 (request/response pydantic)
  → application UseCase / Workflow   ← 흐름 제어만, 규칙은 domain Policy에 위임
  → (필요 시) LangGraph 그래프        ← application 레이어 안에서 조립
  → infrastructure 어댑터 (MySQL/Qdrant/ES/Redis/LLM/MCP)
  → 응답: JSON | SSE(text/event-stream) | WebSocket
```

- **DI는 main.py 한 곳에 집중**: `src/api/main.py`가 4,000줄+ 컴포지션 루트다.
  라우터 등록·UseCase 생성·lifespan 초기화(모델 시드, tool_catalog 동기화, ES 인덱스 보장)가
  전부 여기 있다. "이 UseCase에 뭐가 주입되나"는 각 모듈이 아니라 main.py에서 찾아야 한다.
- 미들웨어 3층(적용 순): CORS → RequestLogging(request_id 생성) → ExceptionHandler.

### 2. 실행 경로 절단면 4종

**(a) General Chat — WS 스트리밍** (`/ws/chat/{session_id}`)
```
ws_router.ws_chat → JWT 검증 → GeneralChatUseCase.stream()
  → create_react_agent (단일 ReAct, ChatToolBuilder가 웹검색·문서검색·MCP 도구 조립)
  → astream_events(v2) → ChatEvent → ChatEventWsAdapter → WS 송신 + cache.record(재접속 replay)
```
- `stream()`은 **transport-독립** AsyncIterator[ChatEvent]. HTTP용 `execute()`는
  stream()을 내부 소비하는 래퍼다 — 스트리밍/논스트리밍이 한 구현을 공유한다.
- 차트 렌더링·메모리 상주 주입은 이 경로에만 배선되어 있다 (Supervisor 경로 아님).
- **도구 선별 이음매**(v2): `ChatToolBuilder.build()` 직후, 에이전트 생성 직전에
  optional `tool_filter`가 질의 기준으로 도구를 좁힌다. `tool_filter=None`(기본,
  `tool_selector_enabled=False`)이면 이 단계가 없던 것과 동일 — [[detachable-module-seam]].

**(b) Agent 실행 — Supervisor 그래프** (POST `/api/v1/agents/.../run` SSE + `/ws/agent/{run_id}`)
```
agent_builder_router → RunAgentUseCase
  → WorkflowCompiler.compile()  ← 요청마다 DB의 WorkflowDefinition으로 동적 컴파일 (그래프 캐시 없음)
  → StateGraph: supervisor → (route_to_worker) → worker들(각각 create_react_agent)
       → [chart_router → chart_builder]? → quality_gate → (route_after_quality: 재시도 or final_answer) → END
  → astream_events(v2) → AgentRunEvent → SSE/WS
```
- 그래프는 **정적 자산이 아니다**. agent_definition 테이블의 정의가 곧 그래프 구조이며,
  워커 추가·수정은 코드 배포 없이 DB 변경으로 반영된다.
- RunTracker(관측)가 노드/도구/LLM 호출 단위로 ai_run_* 5테이블에 기록한다 (V021+V046).

**(c) RAG 검색 — 하이브리드 vs 라우팅 (별도 경로 2개)**
```
하이브리드: HybridSearchUseCase — BM25(ES) + 벡터(Qdrant) 병렬 fetch → RRFFusionPolicy 병합
멀티쿼리:   MultiQueryRewriteWorkflow(LangGraph) — classify → simple_rewrite | generate_queries
            → parallel_search(내부에서 하이브리드 재사용) → fuse_results
라우팅:     /api/v1/retrieval (routed) — 카드/섹션/문서 3계층 요약 기반, 독립 opt-in
```
- 멀티쿼리는 하이브리드를 **감싸는** 상위 그래프다. 검색 개선 작업 시 어느 층을 고치는지 먼저 정할 것.
- 인증 필터는 ES(쿼리 절)·Qdrant(SearchFilter) **양 축 대칭**으로 걸어야 한다
  (한쪽만 걸면 0건 — rag-auth-filter-fix 선례).

**(d) 문서 인제스트** (`/api/v1/ingest`, `/ingest/pdf`)
```
IngestDocumentUseCase: 파서 레지스트리에서 선택(pymupdf/pymupdf4llm/llamaparse)
  → ChunkingStrategyFactory로 청킹 → 임베딩 → Qdrant 저장
  → document_metadata 저장(MySQL) + collection_activity_log 기록
```
- 벡터는 Qdrant, 메타는 MySQL, 전문검색은 ES — **한 문서가 3곳에 흩어진다**.
  삭제·정합성 작업 시 세 저장소를 모두 추적해야 한다 (KB 콘텐츠 브라우저의 source 토글이 이 검증용).

**(e) 백그라운드 잡 — HTTP 요청 밖의 다섯 번째 경로** (V060, v2 추가)
```
POST 등록 → 202 + job_id 즉시 반환 (agent_background_job 테이블 = 큐)
lifespan 워커 싱글턴(BackgroundJobWorker)
  ├─ 기동 시 reconcile: 고아 running → failed
  ├─ poll 5s: claim_queued(FOR UPDATE SKIP LOCKED) → running → RunAgentUseCase 실행
  │            → 결과를 세션 메시지로 저장 + 웹훅 outbound(source="job")
  └─ tick 30s: 스케줄 트리거 (single-flight, 외부 cron 불필요)
```
- **요청→응답 모델을 벗어나는 유일한 경로**다. 브로커·cron 프로세스는 없다.
- `background_worker_enabled` 기본 **True** (성장 루프 플래그들과 반대).
- 상세: [[db-queue-inprocess-worker]]

### 3. 성장 루프 배선 (평가 → 메모리/위키 환류)

```
POST eval → SubmitFeedbackUseCase (application/eval/use_cases.py)
  ├─ 트리거 판정: 👎 AND 이유(comment) 있음 — bare 👎는 통계만 (추측 추출 금지)
  └─ _kickoff_feedback_fanout: Q/A 복원 1회를 두 소비자가 공유
       ├─ memory_on → extraction.kickoff_feedback (부정 맥락 메모리 추출)
       └─ wiki_on   → wiki_feedback.kickoff_draft (위키 draft 생성/반복 시 빈도 강화)
```
- **전부 opt-in 기본 off**: `MEMORY_EXTRACTION_ENABLED`, `EVAL_FEEDBACK_EXTRACTION_ENABLED`,
  `WIKI_FEEDBACK_DRAFT_ENABLED`, `WIKI_FEEDBACK_REINFORCE_ENABLED` 전부 false가 기본.
  로컬에서 "환류가 안 돈다"는 대부분 버그가 아니라 플래그다.
- off 경로는 Q/A 복원 조회조차 0회 — 기존 경로 성능에 영향 없음이 설계 계약(FR-05).
- 환류 서비스는 fire-and-forget(kickoff)이므로 평가 저장 자체는 환류 실패와 무관하게 성공한다.

## 다음에 적용하는 법

1. **새 기능의 진입 레이어 결정**: 단순 CRUD면 UseCase까지, 분기·반복이 있으면 LangGraph
   그래프(application 내)로. 그래프를 새로 만들기 전에 (b)(c)의 기존 그래프 확장 가능성부터 확인.
2. **의존성 추적은 main.py부터**: 모듈 내부를 뒤지기 전에 main.py에서 해당 UseCase 생성부를 찾으면
   주입 그래프가 한눈에 보인다. 새 UseCase도 main.py에 등록해야 동작한다 (lifespan 초기화 포함 여부 확인).
3. **스트리밍 기능 추가 시** General Chat의 transport-독립 stream() 패턴을 따른다 —
   UseCase는 이벤트 스트림만 내고, WS/SSE 변환은 라우터·어댑터가 담당.
4. **검색/삭제 기능 작업 시** 저장소 3곳(Qdrant/ES/MySQL 메타) 중 어디를 건드리는지 명시하고,
   인증 필터는 반드시 양 축 대칭으로.
5. **성장 루프에 새 소비자 추가 시** `_kickoff_feedback_fanout`에 enabled 가드 + kickoff 패턴으로
   편승한다 (Q/A 복원 공유, 독립 opt-in env 플래그 신설).
6. **오래 걸리는 작업·주기 실행은 (e) 큐에 편승**한다 — 새 브로커/cron 도입 금지.
7. **실험적 모듈을 기존 경로에 끼울 때는 optional 협력자 + `None` 킬스위치**로
   ([[detachable-module-seam]]). 미주입 = 기능이 없던 상태가 되도록.

## 관련 문서

- 라우터별 책임: `backend/api/router-map.md`
- 테이블 상세: `backend/db/erd-*.md` 4종
- 화면에서 본 절단면: `frontend/screens/*.md` 5종
- 사실 기준점(수치·버전): `docs/SOURCE-OF-TRUTH.md`
