# BASE-001 — 프로젝트 기반 설정

## 상태: DONE

## 완료된 작업

### 프로젝트 초기 셋업
- [x] CLAUDE.md 작성 (컨벤션, 기술 스택, 개념 정리)
- [x] 폴더 구조 생성 (`src/types`, `constants`, `services`, `store`, `hooks`, `utils`, `components`, `pages`)
- [x] `vite.config.ts` — `@/` 경로 alias 추가
- [x] `tsconfig.app.json` — path alias 추가

### 타입 정의 (`src/types/`)
- [x] `chat.ts` — Message, ChatSession, SourceChunk, SendMessageRequest/Response
- [x] `agent.ts` — AgentRun, AgentStep, AgentStatus, RunAgentRequest/Response
- [x] `rag.ts` — Document, DocumentStatus, UploadDocumentRequest/Response, RetrievedChunk
- [x] `api.ts` — ApiResponse, ApiError, PaginatedResponse, StreamEvent

### 상수 (`src/constants/`)
- [x] `api.ts` — API_BASE_URL, API_ENDPOINTS (chat / agent / rag)
- [x] `agent.ts` — AGENT_STATUS_LABEL, AGENT_STEP_TYPE_LABEL, MAX_AGENT_STEPS

### 서비스 레이어 (`src/services/`)
- [x] `api/client.ts` — axios 인스턴스, request/response interceptor
- [x] `chatService.ts` — getSessions, sendMessage, getStreamUrl
- [x] `agentService.ts` — run, getRunStatus, getStreamUrl
- [x] `ragService.ts` — getDocuments, uploadDocument, deleteDocument, retrieve

### 상태 관리 (`src/store/`)
- [x] `chatStore.ts` — sessions, activeSessionId, streaming 상태, appendStreamingContent
- [x] `agentStore.ts` — currentRun, status, history
- [x] `documentStore.ts` — documents, selectedDocumentIds, CRUD 액션

### 유틸리티 / 훅
- [x] `utils/formatters.ts` — formatDate, formatFileSize, truncate
- [x] `utils/streamParser.ts` — parseStreamLine, createFetchStream
- [x] `hooks/useStream.ts` — SSE EventSource 연결/해제 훅
