# Changelog

All notable changes to sangplusbot project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

---

## [2026-04-12] - General Chat API (CHAT-001)

### Added

- **POST /api/v1/chat**: LangGraph ReAct 에이전트 기반 범용 채팅 API
  - 자동 도구 선택 및 오케스트레이션
  - Tavily 웹 검색 도구 통합 (SEARCH-001 재사용)
  - 내부 문서 BM25+Vector 하이브리드 검색 (RAG-001 재사용)
  - MCP 도구 동적 로드 (MCP-001, MCP-REG-001 재사용)
  - 10분 TTL 인메모리 MCP Tool 캐시

- **멀티턴 대화 메모리 관리** (CONV-001 재사용)
  - 사용자별 세션 기반 대화 히스토리
  - 6턴 초과 시 자동 요약 (오래된 턴 압축)
  - 요약본 + 최근 3턴으로 컨텍스트 구성

- **LangSmith 추적**
  - Request 단위 세션 생성
  - 도구 호출 흐름 실시간 모니터링
  - 에러 디버깅 용이성 향상

- **구조화된 로깅** (LOG-001 규칙)
  - request_id 전체 요청 기반 추적
  - 예외 발생 시 스택 트레이스 자동 기록
  - 사용자 메시지 + AI 응답 모두 로깅

- **도구 사용 추적**
  - tools_used: 실제 호출된 도구명 리스트
  - sources: 내부 문서 검색 출처 메타데이터 (content, source, chunk_id, score)

### Files Created

- `src/domain/general_chat/schemas.py` (43 lines)
  - ToolUsageRecord, DocumentSource, GeneralChatRequest, GeneralChatResponse
- `src/domain/general_chat/policies.py` (19 lines)
  - ChatAgentPolicy (MAX_ITERATIONS, TOOL_TIMEOUT, MCP_CACHE_TTL, SUMMARIZATION_THRESHOLD)
- `src/application/general_chat/tools.py` (~150 lines)
  - MCPToolCache (TTL 기반 캐시), ChatToolBuilder (3종 도구 통합)
- `src/application/general_chat/use_case.py` (~200 lines)
  - GeneralChatUseCase (ReAct 오케스트레이션 + 멀티턴 메모리)
- `src/api/routes/general_chat_router.py` (41 lines)
  - FastAPI 라우터 + JWT 인증 + DI 팩토리

### Tests Added

- `tests/domain/general_chat/test_schemas.py` (6 test cases)
- `tests/domain/general_chat/test_policies.py` (4 test cases)
- `tests/application/general_chat/test_tools.py` (8 test cases)
- `tests/application/general_chat/test_use_case.py` (12 test cases)
- `tests/api/test_general_chat_router.py` (8 test cases)
- **Total**: 38/38 test cases passing (100%)

### Quality Metrics

- **Design Match Rate**: 93% (threshold: 90%) ✅
- **Architecture Compliance**: 95% ✅
- **Convention Compliance**: 100% ✅
- **Test Coverage**: 100% (38/38) ✅

### Documentation

- `docs/01-plan/features/general-chat-api.plan.md` — Feature planning
- `docs/02-design/features/general-chat-api.design.md` — Technical design
- `docs/03-analysis/general-chat-api.analysis.md` — Gap analysis (93% match)
- `docs/04-report/features/general-chat-api.report.md` — Completion report

### Dependency Mapping

| Task ID | Module | Reuse Purpose |
|---------|--------|---------------|
| CONV-001 | Conversation | 멀티턴 메모리 + 자동 압축 |
| RAG-001 | RAG Agent | 내부 문서 BM25+Vector 검색 |
| SEARCH-001 | Tavily | 실시간 웹 검색 도구 |
| MCP-001 | MCP Client | MCP 도구 통합 |
| MCP-REG-001 | MCP Registry | DB 등록 MCP 서버 동적 로드 |
| LANGSMITH-001 | LangSmith | 요청 흐름 추적 |
| LOG-001 | Logging | 구조화된 로깅 |
| AUTH-001 | Authentication | JWT 인증 |

### Configuration

New environment variables:
- `CHAT_MAX_ITERATIONS` (default: 10) — ReAct 에이전트 최대 반복 수
- `CHAT_MCP_CACHE_TTL` (default: 600) — MCP Tool 캐시 TTL (초)

### Key Design Decisions

1. **LangSmith 호출 위치**: Router → UseCase 내부 (verify-architecture 준수)
2. **MCP Tool 캐싱**: 10분 TTL 인메모리 캐시 (레이턴시 + 안정성 최적화)
3. **대화 컨텍스트**: LangGraph messages 파라미터에 직접 주입
4. **도구 추적**: ToolMessage 파싱으로 tools_used, sources 추출
5. **요약 정책**: 6턴 초과 시 자동 압축 + DB 저장

### Breaking Changes

None — greenfield implementation (신규 API)

### Known Issues

None — all 38 tests passing

### Next Steps

- Production deployment preparation
- Streaming response support (Phase 2)
- Tool calling auto-retry logic
- Complexity-based dynamic summarization threshold

---

## Earlier Versions

See `docs/04-report/features/` for completed feature reports.
