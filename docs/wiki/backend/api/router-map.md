---
title: 백엔드 라우터 지도 — idt/src/api/routes/ 책임과 연결
status: approved
reviewer: 배상규
source_type: conversation
source_refs:
  - idt/src/api/routes/ (라우터 prefix/tags 전수 확인, 2026-07-21)
  - idt/docs/archive/2026-07/wiki-user-facing/wiki-user-facing.report.md (tree 선언 순서)
  - idt/docs/archive/2026-07/kb-content-browser/kb-content-browser.report.md (source 토글)
  - idt/docs/archive/2026-08/builtin-tools/builtin-tools.report.md (PATCH /builtin)
  - idt/docs/archive/2026-07/wiki-tree-performance/wiki-tree-performance.report.md (인증 선행·싱글턴)
  - idt_front/docs/archive/2026-08/utility-page/utility-page.report.md (skills/list POST)
  - docs/archive/2026-08/fix-agent-planner-hitl/fix-agent-planner-hitl.report.md (compose HITL)
  - idt/src/api/routes/prompt_composer_router.py (v4 — 신규 라우터)
  - idt/tests/api/test_prompt_composer_router.py:342-350 (라우트 등록 검증법)
  - idt/src/api/routes/agent_pipeline_router.py (v5 — 신규 라우터, ⚠️ 미커밋)
  - idt/src/api/main.py "Agent Create Pipeline DI" 블록 (등록 순서·조건부 include, ⚠️ 미커밋)
  - docs/archive/2026-08/agent-create-pipeline/agent-create-pipeline.report.md (§3.3 Deliverables)
  - idt/src/api/routes/intent_router.py + idt/src/api/main.py:4793-4798,5193 (v6 — intent 라우터 등록 확인)
  - docs/archive/2026-08/intent-slot-elicitation/intent-slot-elicitation.report.md (v6 — answers/round 확장)
confidence: 0.85
version: 6
created: 2026-07-21
updated: 2026-08-20
verified_at: 7c3ffdd
---

> ⚠️ `verified_at: 7c3ffdd` 에서 재확인한 것은 **prompt-composer 행·agent_pipeline 행·
> intent 행(v6)과 아래 "라우트 등록 검증" 절뿐**이다. 나머지 행은 `18fd521e` 시점
> 확인분이 그대로 남아 있다. agent_pipeline 근거 코드와 intent의 answers/round 확장은
> 미커밋 — 커밋 후 재확인 필요.

라우터 파일 단위의 책임 지도. 엔드포인트 상세는 코드/OpenAPI(`/docs`)가 기록한다.
프론트 대응 상수는 `idt_front/src/constants/api.ts` (계약 동기화는 루트 CLAUDE.md §4-1).

## 라우트 등록 검증 — `app.routes` 순회 금지 (v4)

새 라우터의 "등록됐는지" 테스트는 **정적으로 쓰면 안 된다.** 현 FastAPI 버전은
`include_router()` 를 `_IncludedRouter` 로 지연 보관하므로 `app.routes` 를 돌며
`route.path` 를 읽으면 `'_IncludedRouter' object has no attribute 'path'` 로 깨진다
(기존 실패 `tests/api/test_main.py:23` 이 같은 원인). `TestClient` 로 실제 요청을
보내 **404가 아님**(인증 가드가 살아 있으면 401)을 확인한다 —
[[ast-source-contract-tests]] §4.

## 대화·채팅

| 라우터 | prefix | 책임 |
|---|---|---|
| `general_chat_router` | `/api/v1` | General Chat(차트 렌더링이 붙는 유일한 경로) |
| `conversation_router` | `/api/v1/conversation` | 멀티턴 대화 (user_id+session_id) |
| `conversation_history_router` | `/api/v1/conversations` | 세션/메시지 히스토리 조회 (에이전트 스코프 포함) |
| `ws_router` | `/ws/*` | WebSocket (echo/agent run/chat 스트리밍). 스키마는 `ws_schemas.py` |
| `eval_router` | `/api/v1` | 메시지 👍/👎 피드백 + admin 평가 집계 → [[feedback-toggle-row-delete]] |
| `memory_router` | `/api/v1/memories` | 사용자/부서 메모리 CRUD·승인 게이트·승격 (scope 가드 필수) |

## 에이전트

| 라우터 | prefix | 책임 |
|---|---|---|
| `agent_builder_router` | `/api/v1/agents` | 에이전트 CRUD + 스토어(구독/포크) + 실행 |
| `agent_composer_router` | `/api/v1/agents` | 자연어 → 에이전트 초안 조합(무저장, compose) + stateless HITL 질문 왕복(`needs_clarification`) — [[stateless-hitl-clarification]] |
| `prompt_composer_router` | `/api/v1/prompt-composer` | 자연어 → 시스템 프롬프트 생성(세션/버전 영속, V061·V062). LLM 실패는 **200 + `degraded=true`**, DB 실패는 5xx, 타인 세션은 403이 아니라 **404** — [[degradation-vs-failure-boundary]] |
| `agent_pipeline_router` | `/api/v1/agents/pipeline` | 의도 판정→도구 추천→프롬프트 생성→에이전트 실생성+세션 바인딩 단일 호출 (`POST` 동기 + `POST /stream` SSE) — stateless 되묻기 왕복([[stateless-hitl-clarification]]), 동기/SSE 공유 제너레이터([[sync-sse-dual-exposure]]) |
| `intent_router` | `/api/v1/intent` | 의도 판정 + 슬롯 되묻기 왕복(`POST /analyze`, `answers`/`round` 에코백) — **독립 모듈, hot path 미배선**(그래프에 안 붙음). UseCase는 DI 섹션의 앱 수명 싱글턴(`dependency_overrides`), include는 일괄 대열 — [[declared-slot-elicitation]] |
| `agent_schedule_router` | `/api/v1/agents` | 에이전트 스케줄 CRUD + 트리거 |
| `agent_run_router` | `/api/v1` | 런 관측(ai_run 계열 집계·상세, admin usage + 내 사용량) |
| `agent_attachment_router` | `/api/v1/agent` | 엑셀 첨부 업로드 → file_id 발급 |
| `middleware_agent_router` | `/api/v2/agents` | Middleware Agent Builder (v2) |
| `auto_agent_builder_router` | `/api/v3/agents/auto` | 자연어 자동 빌더 (v3) — 세션 기반 질문 루프 보유하나 **Fix 탭(compose)과 무관한 별개 경로** (혼동 주의) |
| `tool_catalog_router` | `/api/v1/tool-catalog` | 도구 카탈로그 조회 + 빌트인 지정/해제(`PATCH /builtin`, admin) — is_builtin은 upsert 보존 계약 ([[builtin-tools-optout-channel]]) |
| `skill_builder_router` | `/api/v1/skills` | 스킬 정의 CRUD/포크 + 에이전트-스킬 attach — **목록 조회 `/skills/list`는 GET이 아니라 POST** (프론트 MSW 핸들러 작성 시 함정) |
| `mcp_registry_router` | `/api/v1/mcp-registry` | MCP 서버 레지스트리 CRUD + 연결 테스트 |
| `analysis_router` | `/api/v1/analysis` | 엑셀 분석 |

**계약 주의 (등록 순서·조건부 등록)**: `agent_pipeline_router`는 main.py 상단의 일괄
`include_router` 대열이 아니라 **DI 섹션에서 조건부로 include** 된다 — (1) 킬스위치
`AGENT_PIPELINE_ENABLED` off 또는 prompt-composer 미가동이면 라우터 자체가 앱에 안 붙고
(404), (2) DI 섹션에서의 include가 곧 우선순위여서 `agent_builder_router`의
`/{agent_id}` 와일드카드 계열보다 **먼저 등록되어야** `/pipeline`이 삼켜지지 않는다
(main.py 주석에 명문). 이 라우터를 일괄 등록 대열로 옮기면 두 계약이 동시에 깨진다.

**계약 주의**: 도구 ID는 이중 네임스페이스다 — 카탈로그/폼 표기(`internal:{id}`, `mcp:{srv}:{tool}`)와 저장 표기(`{id}`, `mcp_{srv}`)가 다르며 라우터 경계에서 변환한다. MCP 오류 "Session terminated"는 세션 만료가 아니라 HTTP 404(주로 빈 api_key)다.

## 지식베이스·검색·인제스트

| 라우터 | prefix | 책임 |
|---|---|---|
| `knowledge_base_router` | `/api/v1/knowledge-bases` | 논리 KB CRUD·문서·청킹 설정·콘텐츠 브라우저·kb_id 격리 검색 |
| `collection_router` | `/api/v1/collections` | 물리 컬렉션 CRUD·권한·활동로그 |
| `collection_search_router` | `/api/v1/collections` | 컬렉션 하이브리드 검색 + search_history |
| `doc_browse_router` | `/api/v1/collections` | 컬렉션 문서/청크 열람 (document_metadata) |
| `retrieval_router` | `/api/v1/retrieval` | RAG 검색 |
| `routed_retrieval_router` | `/api/v1/retrieval` | 요약 계층 라우팅 검색 (`/routed`) — ID 3자 일치 계약 (routing-pipeline-id-contract) |
| `hybrid_search_router` | `/api/v1/hybrid-search` | BM25+Vector 하이브리드 검색 |
| `ingest_router` / `advanced_ingest_router` | `/api/v1/ingest(/pdf)` | PDF 파싱+청킹+벡터 저장 |
| `unified_upload_router` / `document_upload` | `/api/v1/documents` | 통합 업로드 (`upload-all`) |
| `excel_upload` | `/api/v1/excel` | 엑셀 업로드 — 확장자 라우팅 파서, ValueError 편승 422 (kb-excel-upload) |
| `chunk_index_router` / `morph_index_router` / `doc_chunk_router` | 각 prefix | 청크 인덱싱·형태소 인덱스·청크 유틸 |
| `chunking_profile_router` | `/api/v1/chunking` | 청킹 프로파일 조회 (일반) |
| `rag_agent_router` | `/api/v1/rag-agent` | ReAct RAG Agent |
| `rag_tool_router` | `/api/v1/rag-tools` | RAG 도구 설정(컬렉션/메타데이터 키) |
| `embedding_model_router` | `/api/v1/embedding-models` | 임베딩 모델 조회 |

**계약 주의**: KB 콘텐츠 브라우저는 `source` 쿼리 토글로 ES/Qdrant 저장소를 선택해 저장 결과를 검증한다 (kb-content-browser). KB 검색 히스토리는 `search_history.kb_id`(V049)로 기록.

## 문서 생산·내보내기

| 라우터 | prefix | 책임 |
|---|---|---|
| `document_extractor_router` | `/api/v1/document-extractor` | 템플릿 기반 문서 추출/정제 (LLM 입력 20000자 절단 — 429 방지) |
| `excel_export_router` / `pdf_export_router` | `/api/v1/excel`, `/api/v1/pdf` | 산출물 내보내기 (PDF 한글 폰트 이슈: doc-convert-korean-font 이월) |
| `preview_router` | `/api/v1/preview` | 미리보기 |

## 인증·조직·운영

| 라우터 | prefix | 책임 |
|---|---|---|
| `auth_router` | `/api/v1/auth` | JWT 로그인/갱신/me (me에 department 포함 — expose-user-department) |
| `admin_user_router` | `/api/v1/admin/users` | 가입 승인/거절/직접 등록 |
| `department_router` | `/api/v1` | 부서 CRUD + 사용자 배정 |
| `admin_router` | `/api/v1/admin` | admin 공통 (usage 집계 등) |
| `admin_dashboard_router` | `/api/v1/admin/dashboard` | 운영 대시보드 4 API (stats/kb-breakdown/recent-documents/health) |
| `admin_collection_router` | `/api/v1/admin/collections` | admin 컬렉션 운영 |
| `admin_chunking_router` | `/api/v1/admin/chunking` | 청킹 프로파일 관리 (PUT 전체 교체) |
| `admin_ragas_router` / `ragas_router` | `/api/v1/admin/ragas`, `/api/ragas` | RAGAS 평가 |
| `llm_model_router` | `/api/v1/llm-models` | LLM 모델 관리 |

## 위키

| 라우터 | prefix | 책임 |
|---|---|---|
| `wiki_router` | `/api/v1/wiki` | 제품 위키 distill/승인 라이프사이클 + 트리 + 소유자 작성 |

**계약 주의**: `/tree`는 `/{id}`보다 먼저 선언해야 한다(선언 순서 의존). `agent_id` 예약석: `HUMAN`, `CONVERSATION`. 상세는 [[wiki-screens]]·[[erd-wiki]].

**계약 주의 (성능)**: wiki 전 엔드포인트는 (1) 인증 의존성을 use_case보다 **앞에** 선언하고, (2) 임베딩·Qdrant는 `get_wiki_vector_stack()` 앱 수명 싱글턴을 쓴다. per-request 생성으로 되돌리면 요청당 ~6.5초 회귀 ([[app-lifetime-client-singleton]]).
