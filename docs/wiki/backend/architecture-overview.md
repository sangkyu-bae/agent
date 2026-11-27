---
title: 백엔드 아키텍처 조감도 — 요청→응답 전체 경로
status: approved
source_type: conversation
source_refs:
  - idt/src/api/main.py (컴포지션 루트, 라우터 52 등록, lifespan)
  - idt/src/application/background_job/worker.py (v2 추가 — lifespan 워커 싱글턴)
  - idt/src/application/general_chat/use_case.py (v2 추가 — tool_filter optional 이음매) — ⚠️ 12c69b4 시점 미커밋
  - idt/src/api/routes/ws_router.py (/ws/chat, /ws/agent 와이어 프로토콜)
  - idt/src/api/routes/agent_builder_router.py (SSE text/event-stream)
  - idt/src/application/general_chat/use_case.py (stream() transport-독립 설계)
  - idt/src/application/agent_builder/run_agent_use_case.py, workflow_compiler.py, supervisor_nodes.py
  - idt/src/application/hybrid_search/use_case.py, multi_query/workflow.py
  - idt/src/application/ingest/ingest_use_case.py
  - idt/src/application/eval/use_cases.py (_kickoff_feedback_fanout)
  - docs/SOURCE-OF-TRUTH.md (2026-07-23, 커밋 6cc25656 기준 전면 갱신본)
  - 커밋 72b3632 (v4 — 게이트 워커 조건부 END, GroundedGenerator 배선)
  - 커밋 fe184dd, 49b2f41 (v4 — 서브에이전트 런타임 저장소 DI, function_node_ids)
  - idt/src/application/agent_builder/supervisor_nodes.py (route_after_gated_worker) — v4
  - idt/src/api/main.py get_prompt_guard() + run_agent_use_case.py·general_chat/use_case.py 가드 배선 (v5, 커밋 ded7e74)
  - idt/src/application/agent_run/step_tracking.py (v5 — parent_step_id·depth, monotonic latency, V079)
  - idt/src/infrastructure/parser/extension_routing_parser.py + parser/hwp/ (v5 — .hwp/.hwpx 라우팅, 커밋 02677d0)
  - idt/src/domain/extension_hooks/ + idt/src/api/graph_rag_di.py (v6 — 확장 훅 4슬롯, wire_graph_rag, PR #113 7b4113d)
  - idt/src/application/rag_agent/tools.py _merge_supplemental (v6 — 보조 검색 가중 RRF)
  - idt/src/api/firewall_admin_di.py · market_analysis_di.py · main.py wire_*/start/close 호출부 (v7 — 독립 모듈 2종, PR #131·#137)
  - idt/src/infrastructure/market_analysis/ticker.py (v7 — 모듈 자체 틱 루프 DD6)
  - idt/src/application/agent_alert/receive_alert_use_case.py · agent_automation/busy_checker.py (v7 — 알림 수신 경로·바쁨 판정, PR #133)
  - docs/archive/2026-11/firewall-admin-console · firewall-agent · stock-analysis-agents 보고서 (v7)
confidence: 0.9
version: 7
created: 2026-07-23
updated: 2026-11-27
reviewer: 배상규
verified_at: bcf64b0
---

> v7 (2026-11-27): §2(e)에 **알림 수신(Alertmanager) 경로와 스케줄 건너뜀**, §2(g) **기본 off 독립 모듈 2종**(firewall_admin·market_analysis) 추가, 적용법 6에 예외 1건. v6과 함께 재승인 대기. 다른 절은 재검증하지 않았다.
>
> v6 (2026-11-21): §2(c)에 **보조 검색(supplemental) 결합 지점**, §2(f) **Graph RAG 확장 훅 경로**(업로드 후 비동기 추출·대화 중 보조 검색·삭제 훅) 추가, 적용법 8번. 에이전트 갱신이므로 approved → draft 강등. 다른 절은 재검증하지 않았다.
>
> v5 (2026-10-13): §2(a)(b)에 **prompt guard 검사 지점**(그래프 생성 전, LLM 분기 전), §2(b) RunTracker에
> step 계층·latency(V079), §2(d) 파서 라우팅에 한글(.hwp/.hwpx) 추가. 에이전트 갱신이므로 approved → draft 강등 → 2026-10-13 재승인(배상규).
> 다른 절은 v4(ae12fc4) 기준 그대로이며 이번에 재검증하지 않았다.
>
> v4 (2026-10-06): §2(b)에 게이트/서브에이전트 조건부 간선·근거 판정 루프·서브에이전트 DI 3항목 추가.

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
  → [prompt_guard.inspect]  ← (v5) 이력 조회 직후·차트 편집 분기 전. enforced면 LLM 미호출, 안내문 저장+CHAT_DONE
  → create_react_agent (단일 ReAct, ChatToolBuilder가 웹검색·문서검색·MCP 도구 조립)
  → astream_events(v2) → ChatEvent → ChatEventWsAdapter → WS 송신 + cache.record(재접속 replay)
```
- `stream()`은 **transport-독립** AsyncIterator[ChatEvent]. HTTP용 `execute()`는
  stream()을 내부 소비하는 래퍼다 — 스트리밍/논스트리밍이 한 구현을 공유한다.
- 차트 렌더링·메모리 상주 주입은 이 경로에만 배선되어 있다 (Supervisor 경로 아님).
- **도구 선별 이음매**(v2): `ChatToolBuilder.build()` 직후, 에이전트 생성 직전에
  optional `tool_filter`가 질의 기준으로 도구를 좁힌다. `tool_filter=None`(기본,
  `tool_selector_enabled=False`)이면 이 단계가 없던 것과 동일 — [[detachable-module-seam]].
  ⚠️ **이 항목만 `verified_at: 12c69b4` 시점 미커밋**이라 표류 검사 사각지대다
  (문서의 나머지 절은 커밋된 코드에 정박). `tool_selection/` 커밋 후 재확인 필요.

**(b) Agent 실행 — Supervisor 그래프** (POST `/api/v1/agents/.../run` SSE + `/ws/agent/{run_id}`)
```
agent_builder_router → RunAgentUseCase
  → [prompt_guard.inspect + ai_run 스텝 'prompt_guard']  ← (v5) RUN_STARTED 직후·compile 전. enforced면 그래프 미생성
  → WorkflowCompiler.compile()  ← 요청마다 DB의 WorkflowDefinition으로 동적 컴파일 (그래프 캐시 없음)
  → StateGraph: supervisor → (route_to_worker) → worker들(각각 create_react_agent)
       → [chart_router → chart_builder]? → quality_gate → (route_after_quality: 재시도 or final_answer) → END
  → astream_events(v2) → AgentRunEvent → SSE/WS
```
- 그래프는 **정적 자산이 아니다**. agent_definition 테이블의 정의가 곧 그래프 구조이며,
  워커 추가·수정은 코드 배포 없이 DB 변경으로 반영된다.
- (v4) **간선 예외 2종**: 승인 게이트 워커·서브에이전트 워커 직후는 `route_after_gated_worker`
  조건부 간선 — `approval_pending` 이면 supervisor·quality_gate 재진입 없이 END, 답변은 결정적
  템플릿으로 교체([[approval-gate-run-contract]]). 그 외 워커 간선은 위 그림 그대로.
- (v4) **final_answer·action 초안은 근거 판정 재작성 루프**(`GroundedGenerator`, gpt-4o 판정,
  `grounding_check_enabled` 기본 True)를 통과하며, 루프 중 토큰은 채팅에 흘리지 않는다
  ([[grounding-rewrite-loop]]).
- (v4) **서브에이전트 워커**는 자식 정의를 런타임에 읽으므로 컴파일러(앱 싱글톤)에
  `SessionScopedAgentDefinitionRepository`·`SessionScopedLlmModelRepository` 가 main.py에서 주입돼야
  동작한다(2026-10 이전엔 미주입이라 한 번도 동작한 적 없음). 입력 계약은 [[supervisor-graph-contracts]] §5.
- RunTracker(관측)가 노드/도구/LLM 호출 단위로 ai_run_* 5테이블에 기록한다 (V021+V046).
  (v5) `ai_run_step`은 `parent_step_id`·`depth`(V079)로 서브에이전트 자식 그래프 step을 계층화하며,
  latency는 DB 시각 차가 아니라 `track_step`의 monotonic 측정값이다([[run-step-hierarchy-and-latency]]).
  WS 실시간 이벤트에는 아직 계층이 없다.
- (v5) **두 채팅 경로 공통 입력 가드**: `prompt_guard_enabled` 기본 True, `get_prompt_guard()` None 팩토리가
  킬스위치. 규칙 1차 → REVIEW만 LLM 판정 → fail-open. 차단 턴은 저장되지만 다음 턴 컨텍스트에서 제외
  ([[prompt-injection-guard]]).

**(c) RAG 검색 — 하이브리드 vs 라우팅 (별도 경로 2개)**
```
하이브리드: HybridSearchUseCase — BM25(ES) + 벡터(Qdrant) 병렬 fetch → RRFFusionPolicy 병합
멀티쿼리:   MultiQueryRewriteWorkflow(LangGraph) — classify → simple_rewrite | generate_queries
            → parallel_search(내부에서 하이브리드 재사용) → fuse_results
라우팅:     /api/v1/retrieval (routed) — 카드/섹션/문서 3계층 요약 기반, 독립 opt-in
```
- 멀티쿼리는 하이브리드를 **감싸는** 상위 그래프다. 검색 개선 작업 시 어느 층을 고치는지 먼저 정할 것.
- (v6) **보조 검색 결합은 하이브리드 내부가 아니라 RAG 도구(`InternalDocumentSearchTool`) 최종 결과**에서
  일어난다: 단일/멀티쿼리 결과에 `supplemental` 슬롯 공급자(현재 그래프) 결과를 가중 RRF(`merge_many`)로
  한 번 더 합친다. 라우팅 결과에는 합치지 않는다. 상세 [[retrieval-path]].
- 인증 필터는 ES(쿼리 절)·Qdrant(SearchFilter) **양 축 대칭**으로 걸어야 한다
  (한쪽만 걸면 0건 — rag-auth-filter-fix 선례).

**(d) 문서 인제스트** (`/api/v1/ingest`, `/ingest/pdf`)
```
IngestDocumentUseCase: 파서 레지스트리에서 선택(pymupdf/pymupdf4llm/llamaparse)
  → ChunkingStrategyFactory로 청킹 → 임베딩 → Qdrant 저장
KB 업로드·/doc-chunk: ExtensionRoutingParser — pdf는 기존 파서, xlsx/xls는 엑셀 어댑터,
  (v5) .hwp/.hwpx는 HwpDocumentParser(optional 마지막 인자, main.py DI 2곳) → 같은 청킹 경로
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
  (v7: 예외 1건 — §2(g) market_analysis는 자기 틱 루프를 갖는다.)
- `background_worker_enabled` 기본 **True** (성장 루프 플래그들과 반대).
- (v7) **잡을 만드는 입구가 3개**다: 채팅·API 등록, 스케줄 tick, **알림 수신**
  `POST /api/v1/alert-hooks/agents/{agent_id}`(Alertmanager 웹훅 형식, Bearer 토큰 sha256 해시 대조).
  수신 UseCase는 실행하지 않고 잡만 등록하며, 인증 뒤에는 깨진 본문·꺼짐·중복도 **202 + 이력 1행**으로 받는다
  (Grafana는 실패 응답을 재전송하므로). 결과값: enqueued·duplicate·resolved_only·disabled·skipped_busy·invalid_payload.
- (v7) 스케줄(`skip_when_busy`, 기본 off)과 알림 수신(기본 on)은 같은 `AgentBusyChecker`로
  "승인 대기·실행 중이면 건너뜀"을 판정한다. 조회 실패는 바쁨(`check_failed`)으로 본다(fail-closed).
- 상세: [[db-queue-inprocess-worker]], 테이블은 [[erd-execution-triggers]]

**(f) Graph RAG — 확장 훅으로 붙은 부가 모듈** (v6 추가, 기본 off)
```
코어는 domain/extension_hooks 레지스트리 슬롯 4개만 호출 (None이면 즉시 반환, 예외는 삼킴)
  post_ingest  : KB 업로드 완료 → 조건 충족 시 추출 잡 INSERT + asyncio.create_task (외부 큐 없음)
                 → ES에서 청크 재조회 → 주제 분류 → 규칙/LLM 추출 → 판정 → MySQL 판정 기록 → Neo4j
  supplemental : RAG 도구 → 그래프 검색(기존 검색과 동시 시작, 6초 하드 상한) → 가중 RRF
  deletion     : 문서 삭제 후 → MySQL 주제·판정 정리 → Neo4j 문서 그래프 정리
  exposure     : 에이전트 저장 시 비노출 사용자의 use_graph 제거
조립: api/graph_rag_di.py wire_graph_rag + lifespan start/close_graph_rag (main.py 3줄)
```
- 실행 조건은 `use_graph` AND 대화 라우트 grant AND 노출 단계(off/admin_only/general) 3중 게이트.
  웹훅·스케줄·백그라운드 잡은 grant가 없어 그래프 검색을 쓰지 않는다.
- 저장소가 하나 더 늘어난다: Neo4j(엔티티·관계·청크 참조) + MySQL V086~V091. 청크 본문 원본은 여전히 ES.
- 입구 문서: [[overview]] (backend/graph-rag/overview.md).

**(g) 기본 off 독립 모듈 — 조립 파일 1개로 붙는 기능** (v7 추가)
```
main.py ── wire_firewall_admin(app) / close_firewall_admin()          ← api/firewall_admin_di.py
       └── wire_market_analysis(app, platform_factory) / start / close ← api/market_analysis_di.py
FIREWALL_ADMIN_ENABLED=false   → 조립 안 함, 라우터 미등록(404). 켰는데 URL·토큰 없음 → configured=false
MARKET_ANALYSIS_ENABLED=false  → 조립 안 함, 플랫폼 의존성도 안 만듦. TICKER_ENABLED=false면 회차만 정지
조립 실패 → warning 1회, 그 기능만 없음 — 앱 기동은 계속
```
- 둘 다 **코어가 모듈을 import하지 않는다**(AST 계약 테스트). Graph RAG(f)가 코어 슬롯에 끼는 방식이라면,
  (g)는 코어를 **호출하는 쪽**이다: firewall_admin은 fwctl·Grafana를 직접 부르고 승인 API는 무변경,
  market_analysis는 포트 Protocol 뒤에서 `RunAgentUseCase`·MCP 도구를 쓴다.
- market_analysis는 코어에 내부 전용 입력 `reference_context` 1개를 열었고 HTTP 본문에서는 버린다 — 상세 [[market-analysis/overview]].
- firewall_admin은 마이그레이션 0(이력은 fwctl 감사 로그), market_analysis는 `ma_*` 13테이블(V100·V101).

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
   (v7) 예외: 에이전트 실행이 아닌 모듈 전용 주기 작업은 워커에 등록 체계가 없어 lifespan 태스크로 둔 선례가 있다(market_analysis DD6) — 다중 인스턴스 1회 실행은 DB UNIQUE 선점으로 보장할 것.
7. **실험적 모듈을 기존 경로에 끼울 때는 optional 협력자 + `None` 킬스위치**로
   ([[detachable-module-seam]]). 미주입 = 기능이 없던 상태가 되도록.
8. (v6) **업로드 후처리·삭제 후처리·보조 검색 공급자를 추가할 때는 `extension_hooks` 슬롯**을 쓴다.
   슬롯당 owner 하나(충돌 시 기동 실패)라 두 번째 공급자는 슬롯 설계부터 — [[extension-hooks-boundary]].

## 관련 문서

- 라우터별 책임: `backend/api/router-map.md`
- 테이블 상세: `backend/db/erd-*.md` (v6: Graph RAG는 `erd-graph-rag.md`)
- Graph RAG 모듈: `backend/graph-rag/*.md`
- 시장 분석 모듈: `backend/market-analysis/overview.md` (v7)
- 화면에서 본 절단면: `frontend/screens/*.md` 5종
- 사실 기준점(수치·버전): `docs/SOURCE-OF-TRUTH.md`
