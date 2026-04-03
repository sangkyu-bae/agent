# IDT Front — Task 관리

## 완료된 작업

### [DONE] 프로젝트 초기 셋업
- [x] CLAUDE.md 작성 (컨벤션, 기술 스택, 개념 정리)
- [x] 폴더 구조 생성 (`src/types`, `constants`, `services`, `store`, `hooks`, `utils`, `components`, `pages`)
- [x] `vite.config.ts` — `@/` 경로 alias 추가
- [x] `tsconfig.app.json` — path alias 추가

### [DONE] 타입 정의 (`src/types/`)
- [x] `chat.ts` — Message, ChatSession, SourceChunk, SendMessageRequest/Response
- [x] `agent.ts` — AgentRun, AgentStep, AgentStatus, RunAgentRequest/Response
- [x] `rag.ts` — Document, DocumentStatus, UploadDocumentRequest/Response, RetrievedChunk
- [x] `api.ts` — ApiResponse, ApiError, PaginatedResponse, StreamEvent

### [DONE] 상수 (`src/constants/`)
- [x] `api.ts` — API_BASE_URL, API_ENDPOINTS (chat / agent / rag)
- [x] `agent.ts` — AGENT_STATUS_LABEL, AGENT_STEP_TYPE_LABEL, MAX_AGENT_STEPS

### [DONE] 서비스 레이어 (`src/services/`)
- [x] `api/client.ts` — axios 인스턴스, request/response interceptor
- [x] `chatService.ts` — getSessions, sendMessage, getStreamUrl
- [x] `agentService.ts` — run, getRunStatus, getStreamUrl
- [x] `ragService.ts` — getDocuments, uploadDocument, deleteDocument, retrieve

### [DONE] 상태 관리 (`src/store/`)
- [x] `chatStore.ts` — sessions, activeSessionId, streaming 상태, appendStreamingContent
- [x] `agentStore.ts` — currentRun, status, history
- [x] `documentStore.ts` — documents, selectedDocumentIds, CRUD 액션

### [DONE] 유틸리티 / 훅
- [x] `utils/formatters.ts` — formatDate, formatFileSize, truncate
- [x] `utils/streamParser.ts` — parseStreamLine, createFetchStream
- [x] `hooks/useStream.ts` — SSE EventSource 연결/해제 훅

### [DONE] 채팅 UI 컴포넌트 (UI Only, Mock 데이터)
- [x] `components/layout/Sidebar.tsx` — 세션 목록, 새 대화, 문서관리/설정 버튼
- [x] `components/layout/ChatHeader.tsx` — 세션 제목, RAG+Agent 뱃지, 내보내기/삭제
- [x] `components/chat/MessageList.tsx` — 메시지 목록, 빈 상태(추천 질문 4개), 자동 스크롤
- [x] `components/chat/MessageBubble.tsx` — user(보라 그라디언트) / assistant(흰 카드+아바타)
- [x] `components/chat/ChatInput.tsx` — 텍스트 입력, RAG 토글, 전송 버튼, 자동 높이
- [x] `components/chat/TypingIndicator.tsx` — 3-dot bounce 애니메이션
- [x] `components/chat/SourceCitation.tsx` — RAG 출처 칩 (문서명 + 유사도 %)
- [x] `pages/ChatPage/index.tsx` — 메인 페이지 조립, Mock 데이터 포함

---

## 진행 예정 작업

### [ ] API 연동 — 채팅
- [ ] `useChat.ts` 훅 구현 (TanStack Query + chatService)
- [ ] `ChatPage` Mock 데이터 제거 → 실제 API 연결
- [ ] SSE 스트리밍 연결 (`useStream` 훅 적용)
- [ ] 세션 생성/목록 조회 연동

### [ ] API 연동 — Agent
- [ ] `useAgent.ts` 훅 구현
- [ ] `AgentPage/index.tsx` 구현
- [ ] `components/agent/` — ThinkingIndicator, ToolCallDisplay, AgentStatus 컴포넌트

### [ ] API 연동 — 문서(RAG)
- [ ] `useDocuments.ts` 훅 구현
- [ ] `DocumentPage/index.tsx` 구현
- [ ] `components/rag/DocumentUploader.tsx` — 드래그앤드롭 파일 업로드
- [ ] `components/rag/RetrievedChunks.tsx` — 검색된 청크 상세 보기

### [ ] 기타
- [ ] `SettingsPage/index.tsx` 구현
- [ ] React Router 라우팅 설정 (`App.tsx`)
- [ ] react-markdown 적용 (MessageBubble 마크다운 렌더링)
- [ ] 에러 바운더리 / 로딩 상태 처리
- [ ] 반응형 대응 (모바일 사이드바 토글)
