# Task Files Registry

> 원본: CLAUDE.md §13  
> **모든 새 task.md는 LOG-001을 의존성으로 참조해야 한다.**

---

| Task ID | 파일명 | 설명 |
|---------|--------|------|
| VEC-001 | src/claude/task/task-qdrant.md | Qdrant 벡터 저장소 |
| DOC-001 | src/claude/task/task-pdfparser.md | PDF 파서 모듈 |
| CHUNK-001 | src/claude/task/task-chunk.md | 청킹 모듈 |
| RET-001 | src/claude/task/task-retriever.md | 리트리버 모듈 |
| COMP-001 | src/claude/task/task-compressor.md | 문서 압축기 모듈 |
| EXCEL-001 | src/claude/task/task-excel.md | 엑셀 처리 모듈 |
| PIPELINE-001 | src/claude/task/task-pipeline.md | 문서 처리 파이프라인 |
| LOG-001 | src/claude/task/task-logging.md | 로깅 & 에러 추적 (필수 참조) |
| EVAL-001 | src/claude/task/task-hallucination-evaluator.md | 할루시네이션 평가기 모듈 |
| QUERY-001 | src/claude/task/task-query-rewriter.md | 쿼리 재작성기 모듈 |
| SEARCH-001 | src/claude/task/task-tavily-search.md | Tavily 웹 검색 도구 |
| AGENT-001 | src/claude/task/task-research-agent.md | Self-Corrective RAG 에이전트 |
| CODE-001 | src/claude/task/task-code-executor.md | Python 코드 실행 도구 |
| LLM-001 | src/claude/task/task-claude-client.md | Claude LLM 클라이언트 모듈 |
| AGENT-002 | src/claude/task/task-excel-analysis-agent.md | 엑셀 분석 에이전트 (Self-Corrective) |
| AGENT-003 | src/claude/task/task-research-team.md | Research Team 에이전트 (Supervisor + Web/Document Search 팀) |
| LANGSMITH-001 | src/claude/task/task-langsmith.md | LangSmith 모듈 |
| RETRIEVAL-001 | src/claude/task/task-retrieval-api.md | 문서 검색 API (RAG Retrieval) |
| REDIS-001 | src/claude/task/task-redis.md | Redis DB 모듈 (키-값 CRUD, Hash, List, 분산 잠금) |
| MCP-001 | src/claude/task/task-mcp-client.md | LangChain MCP 공통 클라이언트 모듈 (stdio/SSE/WebSocket) |
| ES-001 | src/claude/task/task-elasticsearch.md | Elasticsearch 공통 Repository 모듈 (index/search/CRUD) |
| HYBRID-001 | src/claude/task/task-hybrid-search.md | BM25 + 벡터 하이브리드 검색 (RRF 병합, API 포함) |
| CHUNK-IDX-001 | src/claude/task/task-chunk-index.md | 청킹 + BM25 키워드 추출 색인 API (ES 저장) |
| KIWI-001 | src/claude/task/task-kiwi-analyzer.md | Kiwi 한국어 형태소 분석기 모듈 |
| MORPH-IDX-001 | src/claude/task/task-morph-index.md | Kiwi 형태소 분석 + Qdrant + ES 이중 색인 API |
| RAG-001 | src/claude/task/task-rag-agent-api.md | ReAct RAG Agent API (하이브리드 검색 + LangGraph 에이전트) |
| MYSQL-001 | src/claude/task/task-mysql.md | MySQL 공통 Repository (Generic Base CRUD) |
| CONV-001 | src/claude/task/task-conversation.md | Multi-Turn 대화 메모리 관리 UseCase |
| PARSE-001 | src/claude/task/task-pdf-parse-service.md | PDF 파싱 공통 서비스 |
| INGEST-001 | src/claude/task/task-ingest-api.md | PDF 파싱+청킹+Vector 저장 통합 API |
| HTML-TO-PDF-001 | src/claude/task/task-html-to-pdf.md | HTML → PDF 변환 공통 모듈 |
| EXCEL-EXPORT-001 | src/claude/task/task-excel-export.md | pandas Excel 파일 생성 공통 모듈 + LangChain Tool |
| AGENT-004 | src/claude/task/task-custom-agent-builder.md | Custom Agent Builder (LLM 도구 자동 선택 + LangGraph Supervisor) |
| MCP-REG-001 | src/claude/task/task-mcp-registry.md | Dynamic MCP Tool Registry |
| OLLAMA-001 | src/claude/task/task-ollama-client.md | Ollama LLM 클라이언트 모듈 |
| AGENT-005 | src/claude/task/task-middleware-agent-builder.md | LangChain Middleware 기반 에이전트 빌더 |
| AGENT-006 | src/claude/task/task-auto-agent-builder.md | 자연어 기반 자동 에이전트 빌더 |
| AGENT-007 | src/claude/task/task-planner-agent.md | 공통 Planner Agent |
| AUTH-001 | src/claude/task/task-auth.md | 인증/인가 시스템 (JWT, RBAC) |
| CHAT-001 | src/claude/task/task-general-chat-api.md | General Chat API (ReAct + 검색 + MCP + 멀티턴) |
| CHAT-HIST-001 | src/claude/task/task-chat-history-api.md | 대화 히스토리 조회 API |
| LLM-MODEL-REG-001 | docs/archive/2026-04/llm-model-registry/ | LLM 모델 레지스트리 (llm_model 테이블 CRUD) |
| AGENT-SHARE-001 | docs/archive/2026-04/shared-custom-agent/ | 사용자 커스텀 에이전트 공유 빌더 |
| DI-WIRING-001 | docs/archive/2026-04/missing-di-wiring/ | main.py 누락 DI 배선 일괄 수정 |
| CUSTOM-RAG-TOOL-001 | docs/archive/2026-04/custom-rag-tool/ | 커스텀 RAG 도구 (에이전트별 검색 범위/파라미터 설정) |
| EMB-REG-001 | docs/archive/2026-04/embedding-model-registry/ | 임베딩 모델 레지스트리 (embedding_model 테이블 + 컬렉션 자동 차원 결정) |
| DOC-BROWSE-001 | docs/01-plan/features/collection-document-chunks.plan.md | 컬렉션별 임베딩 문서 및 청크 조회 API (문서 목록 + 청크 상세) |
| UNIFIED-UPLOAD-001 | docs/archive/2026-04/unified-pdf-upload-api/ | 통합 PDF 업로드 API (Qdrant 벡터 + ES BM25 동시 저장 단일 엔드포인트) |
| UNIFIED-UPLOAD-FIX-001 | docs/01-plan/features/fix-unified-upload-es-rdb.plan.md | 통합 업로드 ES/RDB 수정 (Kiwi 형태소 분석 + morph_text BM25 연동 + 문서 메타데이터 RDB 등록) |
| DOC-DELETE-001 | docs/01-plan/features/document-delete-api.plan.md | 문서 삭제 API (Qdrant 청크 + ES 청크 + MySQL 메타데이터 3중 동기 삭제, 단건/일괄) |
| AGENT-CHAT-001 | docs/01-plan/features/agent-chat-history.plan.md | 에이전트별 채팅 기록 관리 (conversation_message에 agent_id 추가, 에이전트별 세션 조회 API) |
| PDF-ANALYZER-001 | docs/archive/2026-05/pdf-analyzer/ | PDF 유형 분류기 (앞 N페이지 샘플링 → text/ocr/table/multimodal 분류, 라우팅 계층용 결과 반환) |
| PYMUPDF4LLM-001 | docs/archive/2026-05/pymupdf4llm-parser/ | pymupdf4llm 기반 Markdown PDF 파서 (구조 보존 파싱, 테이블 포함/제외 옵션, 전체 문서 단일 MD 출력) |
| RERANKER-001 | docs/archive/2026-05/reranker-module/ | Reranker 모듈 (Lost in the Middle 대응 PositionalReranker 양끝 배치 + RerankerInterface 전략 패턴) |
| PDF-ROUTING-001 | docs/archive/2026-05/pdf-routing/ | PDF 라우팅 모듈 (PDFDocumentType 기반 파서 자동 선택, Policy Pattern + string 매핑, graceful fallback) |
| PYMUPDF4LLM-META-001 | docs/archive/2026-05/pymupdf4llm-page-metadata/ | pymupdf4llm 페이지별 메타데이터 보존 (page_chunks=True, section_title/has_table 추출) |
| ADV-PARSER-001 | docs/archive/2026-05/advanced-document-parser/ | 고도화 문서 파서 (좌표 기반 요소 추출 → 7단계 레이아웃 분석 → 품질 점수 → fallback → section-aware 청킹) |
| RAGAS-001 | docs/archive/2026-05/ragas-evaluation/ | RAGAS 평가 모듈 (배치/실시간 평가, 테스트셋 CRUD, 9개 지표, 13 API 엔드포인트) |
| TABLE-FLAT-001 | docs/archive/2026-05/table-retrieval-enhancer/ | 표 검색 향상 모듈 (Parent-Child 청킹 표 플래트닝, 부모=원본 markdown 보존, 자식=의미 문장 변환, Strategy Pattern) |
| FIX-TOOL-BYPASS-001 | docs/archive/2026-05/fix-agent-creation-tool-bypass/ | Agent 생성 시 tool_configs 바이패스 수정 (명시적 도구 선택 경로 + prefix 정규화 + ValueError→422 분류) |
| MULTI-AGENT-001 | docs/archive/2026-05/multi-agent-composition/ | 멀티 에이전트 조합 (Sub-Agent 재귀 컴파일, 순환참조/중첩깊이/접근권한 3대 정책, Task 위임 방식) |
| AGENT-CHAT-MT-001 | docs/archive/2026-05/agent-chat-multiturn/ | Agent Multi-turn 대화 (RunAgentUseCase에 session_id 기반 히스토리 로드/저장/요약 통합, 하위호환 100%) |
| SEARCH-PIPE-001 | docs/archive/2026-05/search-pipeline-refactor/ | 검색 파이프라인 리팩터 (ToolMeta.category 기반 워커 분기 + Search Node 직접 실행 + Answer Agent 자동 주입) |
| NORI-001 | docs/archive/2026-05/nori-analyzer-integration/ | ES Nori 한국어 분석기 (mixed decompound + 18 stoptags POS filter, content^1.5 부스트, Zero-downtime 마이그레이션) |
| ADV-INGEST-001 | docs/archive/2026-05/advanced-ingest-pipeline/ | 고도화 PDF Ingest 파이프라인 (9노드 LangGraph, 5모듈 통합, Qdrant+ES 이중 색인, POST /api/v1/ingest/pdf/advanced) |
| ADMIN-RAGAS-001 | docs/archive/2026-05/admin-ragas-dashboard/ | Admin RAGAS 대시보드 (통계 카드+실행 목록+상세, 4 Admin API, AdminRagasPage 프론트엔드, 95% Match Rate) |
| AGENT-OBS-001 | docs/archive/2026-05/agent-run-observability/ | Agent Run 운영 관측성 M1 (5개 신규 테이블 ai_run/step/tool/retrieval/llm_call + llm_model 가격 컬럼, LangChain UsageCallback 단일 인터셉트, 사용자×LLM 토큰/비용 집계, LangSmith trace_id 영속화, 96% Match Rate, 118 tests) |
| AGENT-OBS-002 | docs/archive/2026-05/agent-run-observability-m2/ | Agent Run 운영 관측성 M2 (Tool Call Wiring — BaseTool callback-driven `on_tool_start/end` 후킹, `RunContext.tool_call_id` ContextVar 자동 set/reset, `ai_tool_call` 자동 INSERT + `ai_llm_call.tool_call_id` FK 자동 연결, 1 new + 1 modified prod file, 0 migrations, 98% Match Rate, 61 tests) |
| AGENT-OBS-003 | docs/archive/2026-05/agent-run-observability-m3/ | Agent Run 운영 관측성 M3 (Run Step Wiring — `WorkflowCompiler.add_node` 시점 decorator wrapping, `track_step` async 컨텍스트 매니저, `ai_run_step` 자동 채움 + `ai_tool_call.step_id` / `ai_llm_call.step_id` FK 자동 연결, SupervisorDecision.reasoning free win, 1 new + 4 modified prod files, 0 migrations, 99% Match Rate, 28 unit + 29 regression tests) |
| AGENT-OBS-004 | docs/archive/2026-05/agent-run-observability-m4/ | Agent Run 운영 관측성 M4 (Retrieval Wiring + Read APIs + Pricing PATCH — `InternalDocumentSearchTool._format_results` async + best-effort `record_retrieval`, 5 read APIs (`GET /agents/runs/{id}` + `/admin/usage/{users,llm-models,by-node}` + `/usage/me`), `PATCH /llm-models/{id}/pricing` + `cost_calculator.invalidate` use case 캡슐화로 M1 G1 영구 해소, `NodeUsageRow` + `aggregate_by_node` INNER JOIN, ★ /admin/usage/by-node 노드별 차지백 첫 노출, 9 new + 8 modified prod files, 0 migrations, 98% Match Rate, 42 new + 121 regression = 163/163 tests) |
| AGENT-OBS-005 | docs/archive/2026-05/agent-run-observability-m5/ | Agent Run 운영 관측성 M5 (Tavily Retrieval + Admin Run List + Aggregate Index — `TavilySearchTool._arun` 재구성 + best-effort `record_retrieval` with `collection_name="tavily_web"` + URL `[:150]` truncate + `metadata_json.url_full` 보존, `GET /api/v1/admin/runs?from=&to=&user_id=&agent_id=&status=&limit=&offset=` + `RunListFilters` 도메인 + `asyncio.gather(list, count)` 정합 캡슐화, V023 `idx_llm_call_created` 단독 인덱스로 집계 API 슬로우 사전 방지, ★ ai_retrieval_source 컬럼 재사용으로 internal+tavily 한 트리 자동 통합 (M4 RunDetailResponse 변경 0), 2 new + 7 modified prod files, 1 migration (인덱스만), 98% Match Rate, 19 new + 136 regression = 155/155 tests) |
| AUTH-CTX-001 | docs/archive/2026-05/agent-user-context/ | Agent User Context (사용자 신원·권한을 `AuthContext` frozen ValueObject + ContextVar로 Agent 런타임에 전파, `user_profiles` + permissions 마스터 3종 테이블 신설, LLM에는 whitelist prepend 블록(이름/부서/권한 라벨)만 노출, Tool/Repository 명시 권한 검증, 회원가입 schema 확장, 관리자 `/admin/users/{id}/permissions` 부여·회수 API, ★ "LLM은 의도 해석, 백엔드는 권한 집행" 원칙 확립 → 사내 데이터(연차/공지/HR 등) 도구 안전 확장 기반 마련 + 기존 `RunContext` 책임 분리로 관측성 계층 보존, 7 migrations V024–V030, 19/20 FR (FR-19 deferred), 초기 78%→Act 후 95% Match Rate, ~83 tests + 1872 passed 0 new failures) |
| AUTH-USER-REG-001 | docs/archive/2026-05/admin-user-registration/ | 관리자 사용자 등록 (프론트 `admin/users`에서 "사용자 등록" 버튼→모달로 직원 직접 등록, `POST /api/v1/admin/users` 즉시 `approved` + 전체 프로필(이름/직급/사번/입사일) + role + 부서, **단일 트랜잭션** `Depends(get_session)` 단일 세션을 User/Profile/Department 3 repo 공유 → 부서 검증 실패 시 전체 롤백, `GET /api/v1/admin/users` 전체 목록(부서명 포함, status/q/limit/offset), `AdminCreateUserUseCase` + `ListUsersUseCase` 신설 + `UserRepository.find_all`, 프론트 전체/승인대기 탭 + `UserRegisterModal`(8필드 + 부서 드롭다운 + 검증 + 백드롭 비차단/X버튼/Esc 닫기), ★ agent-user-context 자산 재사용으로 마이그레이션 0·신규 도메인 0·무회귀(register/승인/권한 미변경) + `list_all` id→name 맵으로 부서명 N+1 선제 제거, 34 tests(BE 23 + FE 11), FR 12.5/13 (FR-11 목록 필터 UI 후속), Check 1회 97% Match Rate) |
| ANALYSIS-NODE-001 | docs/archive/2026-06/analysis-node-agent/ | 분석 전용 노드 에이전트 (Supervisor 그래프 `category="analysis"` 전용 노드 — 엑셀 첨부 시 기존 `ExcelAnalysisWorkflow` 래핑, 없으면 검색결과/전체 대화 문맥 LLM 분석 후 결과만 반환→supervisor 복귀, `ToolCategory+="analysis"` + `SupervisorState.attachments` + `Callable` getter DI 역의존(None graceful fallback) + `function_node_ids`로 함수노드 판별 개선, Check 95%→Act-1 100%, 소스 9 + 테스트 12 케이스, 0 migrations, 엑셀 HTTP 업로드 계약은 후속) |
| CHART-BUILD-001 | docs/archive/2026-06/chart-builder/ | Chart Builder (분석/답변 텍스트 → LLM `with_structured_output` 수치 추출 → **Chart.js 네이티브 config(JSON)** 생성, General Chat `chat_answer_completed.charts`에 주입(프론트 `chat-chart-rendering` 이미 wired), `ChartConfig`=프론트 `ChartPayload`(`{type,data,options}`, 화이트리스트 bar/line/pie/doughnut/scatter/radar), 핵심 **추출↔표현 분리** — LLM은 데이터(`ChartDraft`)만·색상/options는 domain `ChartStylePolicy` 결정론적 조립(LLM hex 위임 회피), `_maybe_build_charts`가 기존 `VisualizationRoutingPolicy`/`Classifier` 재사용해 visualize 판정시만 빌드·실패/비-visualize/미주입 시 `charts=[]` graceful, DI REST+WS 공유 팩토리 1곳·상한 `settings.chart_max_count=3`, DDD domain→infra 참조 0, gap-detector 98%→설계 정정 100%, 소스 3 신규+5 수정+테스트 4 신규(25 pass) 0 migrations, 프론트 REST 타입 `/api-contract-sync`·Excel/Supervisor 연동은 후속) |
| WS-EXCEL-ATTACH-001 | docs/archive/2026-06/ws-agent-excel-attachment/ | WS Agent 엑셀 첨부 (`/ws/agent/{run_id}` 입구 단절 해소 — 다운스트림 `RunAgentRequest.attachments`+분석 노드는 이미 준비됨, **입구 한 곳만 연결**, 분석 노드 수정 0건. HTTP 업로드 `POST /api/v1/agent/attachments`→`file_id` 발급→WS subscribe `attachments:[{type,file_id}]` 참조→`AttachmentResolver` 소유자 검증 후 `file_path` 해석→기존 attachments로 전달→run 종료(정상/예외/disconnect) `finally` 자동 삭제 + `store.purge_expired` TTL 백업 정리(누수 방지), Thin DDD 4레이어 신설(domain `AttachmentType`/`AttachmentPolicy`/`StoredAttachment`/exceptions·infra `AgentAttachmentStore` tmp dir+사이드카 메타·app `UploadAttachmentUseCase`/`AttachmentResolver`·interfaces router+`ws_schemas`+`ws_router`), 보안 file_id uuid4·소유자(업로더==뷰어) 검증·경로 traversal 차단·확장자 allowlist·크기 제한, excel 우선·`AttachmentType` Enum OCP 확장 구조, 풀스택(프론트 `agentAttachmentService`+`useAgentRunStream` subscribe+`ChatInput` 엑셀 첨부 UI+`ChatPage` 연동) `/api-contract-sync`, gap-detector 97%→TTL sweep 보완 후 99% Match Rate, 레이어 위반 0·print 0, 백엔드 57+프론트 20=77 tests, 0 migrations) |
| MCP-REG-UI-001 | docs/archive/2026-06/mcp-registry-admin-ui/ | MCP 서버 등록/관리 Admin UI + 연결 테스트 (기존 백엔드 CRUD `/api/v1/mcp-registry` 재사용 + 연결 테스트 엔드포인트 `POST /{id}/test` 1개만 신규 — `MCPConnectionTestUseCase`가 `MCPCallClient.list_tools` 직접 호출로 실패 표면화·미존재 None→404·예외 ok=False+logger, 프론트 Admin 전용 `/admin/mcp-servers` 신규 화면(목록+SSE/Streamable HTTP 동적 폼+시크릿 병합+연결 테스트 패널+삭제) AdminRoute 보호, ★ 시크릿 병합 정책 — 수정 시 빈 시크릿 필드는 PUT 본문에서 제외해 기존 암호화 시크릿 보존·마스킹 `****` 재전송 안 함(P-3 요청바디 레벨 검증), DDD domain·infrastructure 무변경(application+interfaces+frontend만), gap-detector 98%→페이지 테스트 추가 100% Match Rate, 백엔드 5(1신규/4수정)+프론트 11(8신규/3수정), 0 migrations, 백엔드 23+프론트 17 tests, R1 백엔드 RBAC·저장전 테스트·사용자별 화면은 후속) |
| AGENT-STREAM-001 | docs/archive/2026-05/agent-run-streaming-sse/ | Agent Run SSE Streaming (transport-독립 단일 코어 — `RunAgentUseCase.stream()`이 `AsyncIterator[AgentRunEvent]`만 yield + LangGraph `astream_events(version="v2")` 9 이벤트 매핑(`run_started`/`node_*`/`tool_*`/`token`/`answer_completed`/`run_completed`/`run_failed`), `execute()`는 stream() 소비자로 재구성 (Breaking change 0), 신규 `GET /api/v1/agents/{id}/run/stream` SSE 엔드포인트 + `get_current_user_from_query_token` 쿼리 토큰 인증 + heartbeat 15s + `request.is_disconnected()` cancellation + `tracker.fail_run(CancelledError)` 마감, `AgentRunEventSseFormatter` (format/format_error/format_heartbeat) wire bytes 직렬화, SSE 헤더 3종(Cache-Control/Connection/X-Accel-Buffering), ★ 어댑터 fixture 패턴(`astream_events` → 내부 `ainvoke` 호출)으로 기존 13 observability 테스트 코드 변경 0건 회귀 보존, ★ `main.py` 변경 0줄 (기존 `JWTAdapterInterface`/`UserRepositoryInterface` DI placeholder 재사용), 8 new + 5 modified files, 0 migrations, 0 domain 영속화 변경, 96% Match Rate, 58 new (Domain 8 + Formatter 11 + Auth 4 + Stream 26 + Router 9) + 154 regression = 212/212 tests) |
