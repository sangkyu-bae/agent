# CHAT-001 — 채팅 기능

## 상태: 진행 중 (UI 완료 / API 연동 예정)

## 완료된 작업

### 채팅 UI 컴포넌트 (UI Only, Mock 데이터)
- [x] `components/layout/Sidebar.tsx` — 세션 목록, 새 대화, 문서관리/설정 버튼
- [x] `components/layout/ChatHeader.tsx` — 세션 제목, RAG+Agent 뱃지, 내보내기/삭제
- [x] `components/chat/MessageList.tsx` — 메시지 목록, 빈 상태(추천 질문 4개), 자동 스크롤
- [x] `components/chat/MessageBubble.tsx` — user(보라 그라디언트) / assistant(흰 카드+아바타)
- [x] `components/chat/ChatInput.tsx` — 텍스트 입력, RAG 토글, 전송 버튼, 자동 높이
- [x] `components/chat/TypingIndicator.tsx` — 3-dot bounce 애니메이션
- [x] `components/chat/SourceCitation.tsx` — RAG 출처 칩 (문서명 + 유사도 %)
- [x] `pages/ChatPage/index.tsx` — 메인 페이지 조립, Mock 데이터 포함

## 진행 예정 작업

### API 연동
- [ ] `useChat.ts` 훅 구현 (TanStack Query + chatService)
- [ ] `ChatPage` Mock 데이터 제거 → 실제 API 연결
- [ ] SSE 스트리밍 연결 (`useStream` 훅 적용)
- [ ] 세션 생성/목록 조회 연동
