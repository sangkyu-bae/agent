---
title: 백엔드 라우터 지도 — idt/src/api/routes/ 책임과 연결
status: draft
source_type: conversation
source_refs:
  - idt/src/api/routes/ (라우터 prefix/tags 전수 확인, 2026-07-21)
  - idt/docs/archive/2026-07/wiki-user-facing/wiki-user-facing.report.md (tree 선언 순서)
  - idt/docs/archive/2026-07/kb-content-browser/kb-content-browser.report.md (source 토글)
confidence: 0.85
version: 1
created: 2026-07-21
updated: 2026-07-21
verified_at: 6cc25656
---

라우터 파일 단위의 책임 지도. 엔드포인트 상세는 코드/OpenAPI(`/docs`)가 기록한다.
프론트 대응 상수는 `idt_front/src/constants/api.ts` (계약 동기화는 루트 CLAUDE.md §4-1).

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
| `agent_composer_router` | `/api/v1/agents` | 자연어 → 에이전트 초안 조합(무저장, compose) |
| `agent_schedule_router` | `/api/v1/agents` | 에이전트 스케줄 CRUD + 트리거 |
| `agent_run_router` | `/api/v1` | 런 관측(ai_run 계열 집계·상세, admin usage + 내 사용량) |
| `agent_attachment_router` | `/api/v1/agent` | 엑셀 첨부 업로드 → file_id 발급 |
| `middleware_agent_router` | `/api/v2/agents` | Middleware Agent Builder (v2) |
| `auto_agent_builder_router` | `/api/v3/agents/auto` | 자연어 자동 빌더 (v3) |
| `tool_catalog_router` | `/api/v1/tool-catalog` | 도구 카탈로그 조회 |
| `skill_builder_router` | `/api/v1/skills` | 스킬 정의 CRUD/포크 + 에이전트-스킬 attach |
| `mcp_registry_router` | `/api/v1/mcp-registry` | MCP 서버 레지스트리 CRUD + 연결 테스트 |
| `analysis_router` | `/api/v1/analysis` | 엑셀 분석 |

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
