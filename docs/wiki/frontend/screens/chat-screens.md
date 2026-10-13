---
title: 화면↔API 지도 — 채팅·계정·설정 화면
status: approved
reviewer: 배상규
source_type: conversation
source_refs:
  - idt_front/src/App.tsx (라우트 선언)
  - idt_front/src/pages/ChatPage/index.tsx
  - idt_front/src/constants/api.ts
  - idt_front/src/store/excelPreviewStore.ts, hooks/useExcelPreview.ts, components/chat/ExcelPreview{Modal,Grid}.tsx, types/excelPreview.ts (v2)
  - idt/docs/archive/2026-10/excel-preview/excel-preview.report.md (v2)
  - docs/archive/2026-10/prompt-guard/prompt-guard.design.md D2 (v2 — guard_blocked 페이로드)
confidence: 0.85
version: 2
created: 2026-07-21
updated: 2026-10-13
verified_at: 3b6353b
---

> v2 (2026-10-13): ChatPage 절에 .xlsx 미리보기 모달과 prompt guard 차단 페이로드 추가. 다른 절은 v1(6cc25656) 그대로.

## 목적

채팅/계정/설정 화면의 세로 절단면(화면→컴포넌트→훅→엔드포인트) 지도.
파라미터·응답 스키마는 코드/OpenAPI가 기록한다 — 여기는 연결 관계만.

## ChatPage — `/chatpage`

메인 대화 화면. 일반 채팅(General Chat)과 에이전트 실행을 모두 이 화면에서 처리한다.

- 진입: `idt_front/src/pages/ChatPage/index.tsx`
- 훅: `useChat`(세션/메시지 조회), `useChatStream`(WS 스트리밍), `useAgentRunStream`, `agentStepToToolEvent`(step→툴 이벤트 변환), `useMessageFeedback`(👍/👎)
- 서비스: `agentAttachmentService`(엑셀 첨부 → file_id)
- 엔드포인트: `WS_CHAT(sessionId)`, `GENERAL_CHAT`, `CONVERSATION_SESSIONS`, `CONVERSATION_SESSION_MESSAGES`, `CONVERSATION_AGENT_SESSIONS`(에이전트별 히스토리), `AGENT_ATTACHMENT_UPLOAD`, `MESSAGE_FEEDBACK(messageId)`
- 백엔드: `general_chat_router` / `ws_router` / `conversation_history_router` / `eval_router` → `conversation_message` 테이블 ([[erd-conversation-eval]])
- 연관: [[streaming-message-action-id]] (스트리밍/히스토리 메시지 id 양방향 해석), [[feedback-toggle-row-delete]] (평가 취소=행 삭제), 차트 렌더링은 General Chat 경로에만 연결됨
- (v2) **.xlsx 산출 미리보기**: `MarkdownRenderer`의 `a` 컴포넌트가 .xlsx 링크 옆에 버튼을 그리고(`EXCEL_PREVIEW_TRIGGER`='button'|'link', `types/excelPreview.ts` 상수 1곳) → `useExcelPreviewStore.open()` → `ChatPage`에 **1회 마운트**된 `ExcelPreviewModal`(memo된 마크다운 트리 밖에서 상태 소유) → `useExcelPreview`(모달 열릴 때만 `enabled`) → `DOCUMENT_EXTRACTOR_FILE_PREVIEW(fileId)` = `GET /api/v1/document-extractor/files/{id}/preview`. 오류 404/403/415·422/빈 시트 + 다운로드 실패 안내를 모달 안에서 처리, 다운로드는 `downloadGeneratedFile` 재사용. 그리드 교체 경계는 `ExcelPreviewGrid` ([[openpyxl-readonly-preview-pitfalls]])
- (v2) **prompt guard 차단 턴**: 백엔드가 막으면 LLM 호출 없이 고정 안내문이 **일반 답변 형태**로 오고 `ANSWER_COMPLETED`/`agent_answer_completed` 페이로드에 `guard_blocked: true`가 참일 때만 붙는다(additive). 현재 프론트는 이 키를 소비하지 않는다 — 배지 등 UI를 붙일 때 이 키를 쓸 것 ([[prompt-injection-guard]])

## SettingsPage — `/settings`

AI 메모리(개인/부서 공유) 관리 화면.

- 진입: `idt_front/src/pages/SettingsPage/index.tsx`
- 훅: `useMemories`, `useAuth`(부서 노출 — expose-user-department)
- 엔드포인트: `MEMORIES`, `MEMORY_APPROVE/REJECT`(추출 후보 게이트), `MEMORY_ORG`, `MEMORY_PROMOTE`, `AUTH_ME`
- 백엔드: `memory_router` → `agent_memory` 테이블 ([[erd-agent]])
- 연관: [[data-exists-exposure-missing]] (`/auth/me` 부서 노출 선례)

## UsageMePage — `/usage`

내 사용량(런/토큰/시계열) 조회 화면.

- 진입: `idt_front/src/pages/UsageMePage/index.tsx`
- 훅: `useUsageMe` → `USAGE_ME`, `USAGE_ME_RUNS`, `USAGE_ME_TIMESERIES`
- 백엔드: `agent_run_router` (ai_run 집계)

## LoginPage / RegisterPage — `/login`, `/register` (공개 라우트)

JWT 로그인·가입 신청(관리자 승인 대기) 화면.

- 훅: `useAuth`(useLogin/useRegister/useInitAuth) → `AUTH_LOGIN/REGISTER/REFRESH/ME`
- 백엔드: `auth_router` → `users`/`refresh_tokens`
- 계약: accessToken은 메모리, refreshToken만 persist (`authStore`)

## 비고 — 미라우팅/Mock 화면

`AgentPage`, `DocumentPage`는 App.tsx에 라우트가 없다(레거시).
`EvalDatasetPage`(/eval-dataset), `ToolConnectionPage`, `ToolAdminPage`, `WorkflowDesignerPage`, `WorkflowBuilderPage`는 라우팅은 되지만 Mock 단계 화면이다 (idt_front/CLAUDE.md Task 표 기준).
