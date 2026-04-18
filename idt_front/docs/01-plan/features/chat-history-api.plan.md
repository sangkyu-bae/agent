---
template: plan
version: 1.2
feature: chat-history-api
date: 2026-04-17
author: 배상규
project: idt_front
version_project: 0.0.0
---

# chat-history-api Planning Document

> **Summary**: 백엔드 `CHAT-HIST-001` API (`/api/v1/conversations/sessions`, `/api/v1/conversations/sessions/{session_id}/messages`)를 프론트엔드에 연동하여 `/chat` 페이지 사이드바의 "최근 대화" 목록을 실데이터로 채우고, 목록 항목 클릭 시 해당 세션의 이전 메시지를 채팅 영역에 복원한다.
>
> **Project**: idt_front
> **Version**: 0.0.0
> **Author**: 배상규
> **Date**: 2026-04-17
> **Status**: Draft

---

## 1. Overview

### 1.1 Purpose

현재 `ChatPage`의 세션 목록과 메시지는 **프론트 메모리(useState)에만 존재**하여 새로고침·로그인 전환 시 모두 사라진다. 백엔드 `conversation_messages` 테이블에는 이미 대화가 영구 저장되고 있으므로, 이를 조회하는 신규 REST API (`CHAT-HIST-001`)에 UI를 연결하여:

1. 사이드바 "최근 대화" 목록을 `user_id` 기준 서버 데이터로 표시한다.
2. 목록의 대화를 클릭하면 해당 `session_id`의 이전 user/assistant 메시지를 모두 로드해 대화창에 렌더링한다.
3. 새 메시지를 전송해 대화가 갱신되면 세션 목록이 자동으로 재정렬되도록 한다.

### 1.2 Background

- 기존 `General Chat` (CHAT-001) 통합 시 `session_id`를 백엔드가 발급/유지하도록 이미 연동되어 있음 (`ChatPage.syncSessionId`).
- 백엔드에서 `chat-history-api` 플랜/디자인/라우터/유즈케이스/테스트까지 구현 완료 상태 (`../idt/src/api/routes/conversation_history_router.py`, `../idt/src/application/conversation/history_use_case.py`).
- 프론트는 여전히 `sessions` state를 `createSession()`으로 로컬 생성 중 → 서버 데이터로 치환 필요.
- 인증은 API 레벨에서 미적용이지만, 프론트는 `useAuthStore`의 로그인 사용자 `id`를 `user_id`로 사용한다 (이미 `useGeneralChat` 호출에 동일 패턴 적용).

### 1.3 Related Documents

- API 스펙: `docs/api/chat-history-api.md`
- 백엔드 Plan: `../idt/docs/01-plan/features/chat-history-api.plan.md`
- 백엔드 Design: `../idt/docs/02-design/features/chat-history-api.design.md`
- 백엔드 Task: `../idt/src/claude/task/task-chat-history-api.md`
- 연관 API: CHAT-001 (`POST /api/v1/chat`) — 대화 생성, session_id 발급
- 참조 구현: `src/pages/ChatPage/index.tsx`, `src/components/layout/Sidebar.tsx`, `src/hooks/useChat.ts`

---

## 2. Scope

### 2.1 In Scope

- [ ] `src/constants/api.ts` 에 `CONVERSATION_SESSIONS`, `CONVERSATION_SESSION_MESSAGES(sessionId)` 엔드포인트 추가
- [ ] `src/types/chat.ts` 에 서버 응답 타입 추가 (`SessionSummary`, `SessionSummaryListResponse`, `HistoryMessageItem`, `SessionMessagesResponse`)
- [ ] `src/services/chatService.ts` 에 `getConversationSessions(userId)`, `getSessionMessages(sessionId, userId)` 메서드 추가
- [ ] `src/lib/queryKeys.ts` 에 `queryKeys.chat.history(userId)`, `queryKeys.chat.sessionMessages(sessionId, userId)` 키 추가
- [ ] `src/hooks/useChat.ts` 에 `useConversationSessions(userId)`, `useSessionMessages(sessionId, userId)` 훅 추가 (TanStack Query)
- [ ] `ChatPage`에서 로컬 `sessions` state를 서버 데이터로 대체, `SessionSummary[]` → `ChatSession[]` 어댑터 매핑 구현
- [ ] `ChatPage`에서 세션 클릭 시 `useSessionMessages`로 이전 메시지 fetch 후 `messagesBySession[sessionId]` 주입 (1회 캐싱, 재선택 시 재요청 안 함)
- [ ] 새 메시지 전송 성공 시 `queryKeys.chat.history(userId)` 무효화 → 사이드바 재정렬
- [ ] 새 메시지 전송 성공 시 현재 세션의 `sessionMessages` 캐시에 assistant 응답 append (또는 무효화)
- [ ] `Sidebar` 에 로딩/빈 상태 처리 (이미 빈 상태 있음; 로딩 스피너 추가)
- [ ] MSW 핸들러 추가 (`src/__tests__/mocks/handlers.ts`) — sessions 목록 / session messages
- [ ] `useConversationSessions.test.ts`, `useSessionMessages.test.ts` 훅 단위 테스트 (TDD Red → Green)
- [ ] `ChatPage.integration.test.tsx` 통합 테스트: 사이드바 클릭 → 이전 메시지 렌더링 검증

### 2.2 Out of Scope

- 세션 **삭제/제목 변경** API 및 UI (백엔드 API 미제공)
- 메시지 단위 편집·재전송
- 세션 검색·필터링 UI
- 페이지네이션 / 무한스크롤 (초기 버전은 전체 조회, 100자 truncate된 `last_message`만 표시)
- 비로그인 사용자 히스토리 보기 (user_id 없으면 호출 생략)
- 세션 pin/즐겨찾기, 그룹핑 (오늘/어제/이번주 등)
- 스트리밍 히스토리 (이전 메시지는 정적 텍스트만)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | 로그인 상태에서 `/chat` 진입 시 `GET /api/v1/conversations/sessions?user_id={me}` 호출해 사이드바에 렌더링 | High | Pending |
| FR-02 | 세션 목록은 `last_message_at` 내림차순(서버 정렬 그대로), 각 항목에 `last_message`(최대 100자)와 상대시간 표시 | High | Pending |
| FR-03 | 사이드바의 세션을 클릭하면 `GET /api/v1/conversations/sessions/{session_id}/messages?user_id={me}` 호출하여 이전 메시지를 채팅 영역에 출력 | High | Pending |
| FR-04 | 한 번 로드한 세션 메시지는 TanStack Query 캐시(`staleTime` 1분)에 보관하고, 같은 세션을 재클릭해도 네트워크 재요청이 발생하지 않음 | High | Pending |
| FR-05 | 새 메시지 전송 성공(`useGeneralChat.onSuccess`) 시 `queryKeys.chat.history(userId)` 와 `queryKeys.chat.sessionMessages(sessionId, userId)` 를 invalidate → 사이드바 재정렬 + 서버 기준 재조회 | High | Pending |
| FR-06 | 응답 `messages: []` 또는 `sessions: []` 일 때 빈 상태 UI ("대화 내역이 없습니다") 유지 | Medium | Pending |
| FR-07 | "새 대화" 버튼 클릭 시 서버 호출 없이 클라이언트 임시 세션 생성, 첫 메시지 전송 성공 후 서버 `session_id`로 치환 (기존 `syncSessionId` 로직 유지) | High | Pending |
| FR-08 | `user_id`가 없는 경우(비로그인) 히스토리 쿼리는 `enabled: false` 로 비활성, 사이드바에 "로그인이 필요합니다" 또는 기존 빈 상태 노출 | Medium | Pending |
| FR-09 | API 에러(5xx/네트워크) 발생 시 사이드바 상단에 경량 에러 배지 + 재시도 버튼 노출 (기존 채팅 영역 중단 없음) | Medium | Pending |
| FR-10 | `ChatSession` 도메인 모델과 서버 `SessionSummary`를 어댑터 함수로 매핑 (`id`←`session_id`, `title`←`last_message` truncate, `updatedAt`←`last_message_at`, `messages`는 lazy-load) | High | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Performance | 사이드바 초기 로드 < 400ms (세션 50개 기준), 메시지 로드 < 600ms (메시지 100개 기준) | Chrome DevTools Network 탭 |
| Caching | 동일 세션 재선택 시 네트워크 재요청 0회 (5분 이내) | MSW 핸들러 호출 카운트 |
| UX | 세션 클릭 → 메시지 렌더 간 스피너/스켈레톤 표시 (loading 상태 시각화) | 수동 QA |
| Accessibility | 세션 버튼 `aria-current="true"` (선택 시), 키보드 포커스 이동 가능 | 수동 + axe-core |
| Reliability | API 500 시 화면 깨짐 없이 에러 UI 노출, 대화 전송은 계속 가능 | MSW 5xx 시나리오 테스트 |
| Type Safety | 백엔드 응답 스키마와 프론트 타입 100% 일치 (필드명 snake_case 유지 또는 명시적 어댑터) | TypeScript strict + 타입 테스트 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] FR-01~FR-10 전 항목 구현 완료
- [ ] 훅 단위 테스트 (`useConversationSessions`, `useSessionMessages`) 통과
- [ ] `ChatPage` 통합 테스트: "사이드바에서 기존 세션 클릭 시 이전 메시지가 렌더링된다" 케이스 통과
- [ ] MSW 핸들러로 2가지 엔드포인트 모킹 완료 (success / empty / 500)
- [ ] `npm run type-check`, `npm run lint`, `npm run test:run` 모두 통과
- [ ] 백엔드 로컬 서버와 E2E 수동 검증: 새 대화 → 메시지 몇 개 전송 → 새로고침 → 사이드바에서 해당 대화 클릭 → 이전 메시지가 그대로 보임

### 4.2 Quality Criteria

- [ ] 훅 커버리지 ≥ 80%, 어댑터 유틸 커버리지 ≥ 90%
- [ ] Zero lint errors
- [ ] 빌드 성공 (`npm run build`)
- [ ] `ChatPage` 컴포넌트 200줄 초과 시 책임 분리 (`useChatPageSessions` 등 커스텀 훅으로 추출)

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 클라이언트 임시 세션 id와 서버 `session_id` 동기화 충돌 (목록에 2개로 보임) | High | Medium | 기존 `syncSessionId` 로직을 유지하되, 성공 후 `history` invalidate 전에 낙관적으로 임시 세션을 목록에서 제거 |
| TanStack Query 캐시와 로컬 `messagesBySession` state 이중 소스로 인한 불일치 | Medium | High | 로컬 `messagesBySession` 은 "현재 세션 스트리밍/신규 추가 중" 버퍼로만 쓰고, 메시지 원천은 쿼리 캐시를 단일 소스(SoT)로 채택 |
| `user_id` 변경(로그아웃→재로그인) 시 이전 사용자 캐시가 남아 교차 노출 | High | Low | queryKey 에 `userId` 포함 + 로그아웃 시 `queryClient.removeQueries({ queryKey: queryKeys.chat.all })` 트리거 |
| 대화량 많을 때(메시지 수백 개) 초기 렌더 지연 | Medium | Low | 초기 버전은 전체 조회 허용 (API가 페이지네이션 미지원), MVP 이후 가상 스크롤 검토 항목으로 분리 |
| 서버 응답 필드명(snake_case)과 프론트 도메인(camelCase) 혼용 | Low | High | 서비스 레이어에서 어댑터 함수로 일괄 변환, 타입은 응답 원본 (`HistoryMessageItem`)과 도메인 (`Message`) 분리 |
| CHAT-001 응답이 `session_id`를 새로 발급하는 경우 목록에 없는 세션 클릭 시 빈 응답 | Low | Low | 200 OK + `messages: []` 를 그대로 UI 처리 (빈 채팅 영역), 다음 invalidate 사이클에서 자동 반영 |

---

## 6. Architecture Considerations

### 6.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| **Starter** | Simple structure (`components/`, `lib/`, `types/`) | Static sites, portfolios, landing pages | ☐ |
| **Dynamic** | Feature-based modules, BaaS integration (bkend.ai) | Web apps with backend, SaaS MVPs, fullstack apps | ☑ |
| **Enterprise** | Strict layer separation, DI, microservices | High-traffic systems, complex architectures | ☐ |

> 기존 프로젝트가 Dynamic 레벨로 운영되고 있으므로 동일 레벨 유지. 신규 레이어 도입 없음.

### 6.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| HTTP Client | apiClient (public) / authClient (bearer) | **apiClient** | 해당 API는 `user_id` 쿼리 파라미터 기반이며 현재 인증 미적용 — General Chat(`authClient`)과 달리 공개 클라이언트 재사용 |
| State Management | React state / Zustand / TanStack Query | **TanStack Query** | 서버 캐시 + 자동 리페치 + invalidate 패턴이 기존 컨벤션과 일치 (`useDocuments`, `useChatSessions` 패턴) |
| Session List Source | Local state / React Query | **React Query** | FR-05 invalidation 요구사항 충족 |
| Message Load Trigger | Prefetch all / Lazy on click | **Lazy on click** | 성능 최적화 — 수십 개 세션 메시지 전부 prefetch 지양 |
| Adapter Location | 서비스 레이어 / 컴포넌트 | **서비스 레이어** (`chatService`) | 도메인 모델 변환은 UI 진입 전에 끝내 UI 단순화 |
| 기존 로컬 state 제거 | 완전 제거 / 하이브리드 | **하이브리드** | 전송 중 낙관적 업데이트와 UUID 임시 세션은 로컬 필요, 서버 캐시는 SoT |

### 6.3 Clean Architecture Approach

```
Selected Level: Dynamic

레이어별 책임:
┌────────────────────────────────────────────────────────┐
│ UI  (pages/ChatPage, components/layout/Sidebar)         │
│  ↓ read queries + dispatch mutations                    │
│ Hooks (hooks/useChat)                                   │
│  - useConversationSessions(userId)                      │
│  - useSessionMessages(sessionId, userId)                │
│  ↓ wrap TanStack Query                                  │
│ Services (services/chatService)                         │
│  - getConversationSessions / getSessionMessages         │
│  - toChatSession / toMessage 어댑터                      │
│  ↓ HTTP                                                 │
│ Backend (CHAT-HIST-001)                                 │
└────────────────────────────────────────────────────────┘
```

---

## 7. Convention Prerequisites

### 7.1 Existing Project Conventions

- [x] `CLAUDE.md` 코딩 컨벤션 섹션 존재 (`idt_front/CLAUDE.md`)
- [x] ESLint / TypeScript 설정 존재
- [x] Vitest + RTL + MSW 테스트 스택 구성 완료
- [x] `queryKeys` 팩토리 중앙 관리 (`src/lib/queryKeys.ts`)
- [x] `API_ENDPOINTS` 상수 중앙 관리 (`src/constants/api.ts`)

### 7.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| **서버 응답 타입 네이밍** | camelCase 도메인 / snake_case 응답 혼재 | `XxxResponse` 접미사 + snake_case 필드 유지 (기존 `GeneralChatResponse` 와 동일 패턴) | High |
| **어댑터 함수 위치** | 관습 없음 | `services/chatService.ts` 파일 내 private 함수로 정의 (`toChatSession`, `toMessage`) | Medium |
| **queryKey 확장 규칙** | 도메인별 팩토리 존재 | `chat.history(userId)`, `chat.sessionMessages(sessionId, userId)` 추가 | High |
| **Sidebar 로딩 UX** | 현재는 빈 상태만 | 로딩 중 스켈레톤 3행 / 에러 시 inline banner | Medium |

### 7.3 Environment Variables Needed

| Variable | Purpose | Scope | To Be Created |
|----------|---------|-------|:-------------:|
| `VITE_API_BASE_URL` | 백엔드 API 엔드포인트 (기존) | Client | ☑ (이미 존재) |

> 신규 환경변수 없음.

### 7.4 Pipeline Integration

해당 기능은 Phase 6 (UI Integration) 범주. 별도 Phase 문서 생성 없이 PDCA 단일 기능 플랜으로 진행.

---

## 8. Next Steps

1. [ ] `/pdca design chat-history-api` — Design 문서 작성 (엔드포인트 ↔ 타입 ↔ 훅 ↔ 컴포넌트 매핑 상세)
2. [ ] 타입/상수/서비스/훅 추가 순서로 TDD Red → Green 구현
3. [ ] `ChatPage` 리팩터링 및 통합 테스트 추가
4. [ ] 백엔드 로컬 서버 기동 후 E2E 수동 검증
5. [ ] `/pdca analyze chat-history-api` 로 Gap 검증 → Match Rate ≥ 90% 목표

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-04-17 | Initial draft (API 문서 기반, 추가 요구사항: 사이드바 최근 대화 세팅 + 클릭 시 이전 메시지 로드) | 배상규 |
