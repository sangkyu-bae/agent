---
template: analysis
version: 1.2
feature: chat-history-api
date: 2026-04-17
author: 배상규
project: idt_front
version_project: 0.0.0
---

# chat-history-api Gap Analysis Report

> **PDCA Phase**: Check (Gap Analysis)
> **Match Rate**: **96%** (meets 90% DoD threshold — iterated from 82%)
> **Analysis date**: 2026-04-17 (v0.2)
> **Recommended action**: `/pdca report chat-history-api`

---

## 1. Summary

| Category | Score | Status |
|---|:---:|:---:|
| Functional Requirements (FR-01 ~ FR-10) | 10/10 | ✅ Full |
| Design Conformance (types/hooks/adapters/UI) | 12/12 | ✅ Full |
| Architecture / Import rules | 5/5 | ✅ Full |
| Security — cache isolation on logout | 1/1 | ✅ (`useLogout` hook removes `queryKeys.chat.all`) |
| Test coverage vs Design §8.2 | 18/18 | ✅ Full (C1-C5, H1-H4, M1-M4, I1-I5) |
| **Overall** | — | **96%** |

## 2. Functional Requirements Coverage

| ID | Requirement | Status | Evidence |
|---|---|:---:|---|
| FR-01 | `GET /api/v1/conversations/sessions?user_id={me}` on `/chat` mount | ✅ | `src/hooks/useChat.ts:55-61` + `src/pages/ChatPage/index.tsx:32-37` |
| FR-02 | Server order preserved, `last_message` truncation | ✅ | `src/services/chatService.ts:20-26` |
| FR-03 | Session click → `GET .../sessions/{id}/messages` → render | ✅ | `src/pages/ChatPage/index.tsx:47-57` |
| FR-04 | Cache reuse, `staleTime: 60_000` | ✅ | `src/hooks/useChat.ts:60, 74` |
| FR-05 | `useGeneralChat.onSuccess` invalidates `history(userId)` + `sessionMessages(serverId, userId)` | ✅ | `src/hooks/useChat.ts:35-44` |
| FR-06 | Empty states UI | ✅ | `Sidebar.tsx:154-158` |
| FR-07 | "새 대화" draft → `syncSessionId` after send | ✅ | `ChatPage/index.tsx:14-20, 70-82, 129-133` |
| FR-08 | No-login → query disabled (`enabled: !!userId`) | ✅ | `useChat.ts:59, 73` |
| FR-09 | Error → Sidebar banner + retry | ✅ | `Sidebar.tsx:92-103` + `ChatPage/index.tsx:146-148` |
| FR-10 | Adapter mapping (`session_id→id`, title truncate, `updatedAt←last_message_at`) | ✅ | `chatService.ts:20-33` |

**FR coverage: 10/10 = 100%**

## 3. Design Conformance (per Design §3, §4, §5, §11)

| Design spec | Actual file | Status |
|---|---|:---:|
| §3.1 Server response types (`SessionSummary`, etc.) | `src/types/chat.ts:83-111` | ✅ |
| §3.4 queryKey extension (userId in key) | `src/lib/queryKeys.ts:22-27` | ✅ |
| §4.1 Endpoint constants | `src/constants/api.ts:15-18` | ✅ |
| §4.2 Service methods | `src/services/chatService.ts:54-72` | ✅ |
| §4.3 Adapters (`toChatSession`, `toMessage`) | `src/services/chatService.ts:20-33` | ✅ |
| §4.4 Hook signatures (`enabled: !!userId`, `staleTime: 60_000`) | `src/hooks/useChat.ts:55-75` | ✅ |
| §4.5 Invalidation policy (both keys on onSuccess) | `src/hooks/useChat.ts:35-44` | ✅ |
| §4.5 Logout → `removeQueries({ queryKey: queryKeys.chat.all })` | `src/hooks/useAuth.ts:67-70` | ✅ (placed in `useLogout` hook — preserves layer separation) |
| §5.3 Sidebar props (`isLoading`, `isError`, `onRetry`) | `Sidebar.tsx:5-13` | ✅ |
| §5 Sidebar UI (skeleton 3 rows, error banner + retry) | `Sidebar.tsx:92-120` | ✅ |
| §11.3 ChatPage refactor (draft + server merge, enabled guard) | `ChatPage/index.tsx:27-57` | ✅ |
| §9.2 Import rules (Presentation → Application only) | 전 파일 | ✅ |

## 4. Test Coverage vs Design §8.2

Expected per DoD §12: **Unit 5 + Hook 8 + Integration 5 = 18 tests**

| Test group | Expected | Actual | Status | Location |
|---|:---:|:---:|:---:|---|
| §8.2.1 Adapter unit tests (cases 1-5) | 5 | 5 | ✅ | `src/services/chatService.test.ts` |
| §8.2.2 `useConversationSessions` (H1-H4) | 4 | 4 | ✅ | `useChat.test.ts:74-123` |
| §8.2.2 `useSessionMessages` (M1-M4) | 4 | 4 | ✅ | `useChat.test.ts:125-205` (M3 now spec-aligned cache reuse) |
| §8.2.3 Integration tests (I1-I5) | 5 | 5 | ✅ | `src/__tests__/components/ChatPageIntegration.test.tsx` |
| **Total** | **18** | **18** | ✅ | **100%** |

All 23 tests pass (`npx vitest run`) — including pre-existing 5 `useGeneralChat` tests.

## 5. Gaps & Issues (post-iteration)

### 🔴 Blocker — All resolved

| # | Gap | Resolution |
|---|---|---|
| B1 | Integration tests I1-I5 부재 | `src/__tests__/components/ChatPageIntegration.test.tsx` 5개 시나리오 구현됨. I3은 `useGeneralChat` 를 `useQueryClient()` 기반으로 바꿔 실제 invalidation 을 테스트한다. I4는 mutable `mockAuthState.user = null` 패턴 사용. |
| B2 | Adapter unit tests 부재 | `src/services/chatService.test.ts` 5개 케이스 (C1-C5) 구현됨. 어댑터는 private 유지, service method + MSW 를 통한 간접 검증. |

### 🟡 Major — All resolved

| # | Gap | Resolution |
|---|---|---|
| M1 | Logout 시 chat 캐시 미삭제 | `src/hooks/useAuth.ts:66-72` `useLogout` onSettled 에서 `removeQueries({ queryKey: queryKeys.chat.all })` + `queryClient.clear()` 수행 — Store 는 React-Query import 없음 (레이어 분리). |
| M2 | M3 테스트가 spec 와 다름 | `useChat.test.ts:147-181` 가 spec §8.2.2 M3 "캐시 재사용 (fetch count === 1)" 로 교체됨. |

### 🔵 Minor — unchanged

| # | Gap | Remediation |
|---|---|---|
| m1 | 테스트 파일명 — design 에서 허용된 대안 (`useChat.test.ts` 확장) 선택됨 | 조치 불필요 |
| m2 | `createDraftSession` 의 `useState(() => ...)` 패턴이 비관용적 | 리팩토링 대상; 기존 `randomUUID` 1회 호출 invariant 는 `ChatPage.test.tsx` TC-FE-1 에서 enforce 중 |

### ⚙️ Side-effect fix (not in original gap list)

During integration, `useGeneralChat` (and `useSendMessage`) were switched from the module-singleton `queryClient` import to the `useQueryClient()` hook. This was required because `QueryClientProvider` in tests creates a fresh client, and invalidations on the singleton would not reach subscribed queries. The production behavior is unchanged because the singleton is still installed at the app root via `QueryClientProvider`.

## 6. Clean Architecture Check

| Rule | Verdict |
|---|:---:|
| `pages/ChatPage` → `hooks/useChat` | ✅ |
| `hooks/useChat` → `services/chatService` | ✅ |
| `services/chatService` → `types/chat` | ✅ |
| `components/Sidebar` 가 `services/*` 직접 import 하지 않음 | ✅ |
| Adapter 위치 (services 레이어 private const) | ✅ |

**레이어링 위반 없음.**

## 7. Remediation Plan — Completed

| # | 작업 | Status |
|---|---|:---:|
| 1 | `ChatPageIntegration.test.tsx` (I1-I5) 생성 | ✅ |
| 2 | `chatService.test.ts` (5개 adapter 테스트) 생성 | ✅ |
| 3 | Logout 시 chat 캐시 제거 (`useAuth.ts` `useLogout`) | ✅ |
| 4 | `useChat.test.ts` M3 를 "캐시 재사용" 으로 교체 | ✅ |

모두 적용 완료. 신규 side-effect 수정: `useGeneralChat` / `useSendMessage` → `useQueryClient()` 기반 (invalidation 이 provider context 를 따르도록).

## 8. Recommended Next Step

```
/pdca report chat-history-api
```

Match Rate 96% ≥ 90% 달성. 남은 minor (m1, m2) 는 문서화만 하고 보고서 작성 단계로 진입.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-04-17 | Initial gap analysis (Match Rate 82%) | 배상규 (via gap-detector) |
| 0.2 | 2026-04-17 | Iteration applied — B1/B2/M1/M2 closed; side-effect fix `useGeneralChat` → `useQueryClient()`; 23/23 tests green, type-check clean. Match Rate 96%. | 배상규 (via /pdca iterate) |
