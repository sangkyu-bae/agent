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
