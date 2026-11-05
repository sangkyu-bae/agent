# agent-edit-entry Design Document

> **Summary**: 빌더에 `?edit={agentId}&returnTo={path}` 진입을 추가하고, 워크스페이스·채팅 헤더가 이 경로로 편집 화면을 열며, 저장·취소 후 들어온 화면으로 돌아간다.
>
> **Project**: sangplusbot (idt_front)
> **Author**: 배상규
> **Date**: 2026-11-05
> **Status**: Draft
> **Planning Doc**: [agent-edit-entry.plan.md](../../01-plan/features/agent-edit-entry.plan.md)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 수정 진입점이 빌더 목록 하나뿐이라, 채팅·워크스페이스에서 고치려면 목록을 거쳐 다시 찾아야 하고 저장 후 복귀도 수동이다. |
| **WHO** | P2 — 자기 에이전트(owned·forked)를 운영하며 채팅으로 결과를 확인하는 소유자. 구독자(subscribed)는 대상이 아니다. |
| **RISK** | 빌더의 기존 진입 흐름(위저드 intent 소비, edit 프라임 1회 가드)과 `?edit` 소비가 경합해 폼이 덮어써지거나 빈 폼이 뜰 수 있다. |
| **SUCCESS** | 워크스페이스·채팅에서 클릭 1번으로 해당 에이전트 편집 스튜디오가 열리고, 저장·취소 후 들어온 화면으로 돌아간다. 권한 없는 id는 안내 후 목록. |
| **SCOPE** | 프론트 단일. ① 빌더 `?edit` 진입 ② 워크스페이스 링크 수정 ③ 채팅 헤더 수정 아이콘 ④ 복귀 처리 ⑤ 권한 없음 처리. 백엔드 무변경. |

---

## 1. Overview

### 1.1 Design Goals

- 외부 화면이 "이 에이전트를 편집하고, 끝나면 여기로 돌아와"를 URL 하나로 표현한다.
- 빌더의 기존 편집 경로(`handleEdit`과 같은 상태 전이 → 기존 프라임 effect → `mapDetailToForm`)를 그대로 쓴다. 폼 채우기 로직을 새로 만들지 않는다.
- 진입 소비 지점을 하나로 둔다. 위저드 intent와 `?edit`는 같은 1회 소비 effect 안에서 우선순위로 처리한다.

### 1.2 Design Principles

- **단일 소비 지점**: 기존 `consumedIntentRef` effect를 확장한다. 별도 effect를 두지 않아 실행 순서 경합이 생기지 않는다.
- **경로 규칙 한 곳**: 편집 URL 생성과 `returnTo` 검증은 순수 유틸(`utils/agentEditLink.ts`)에만 둔다.
- **권한 3중**: 채팅 노출은 `source_type` 추정, 빌더 진입은 상세 `can_edit`, 저장은 서버 403.

### 1.3 추가 확인 사항 (Plan 이후 코드 확인)

| 확인 | 결과 | 설계 반영 |
|------|------|----------|
| 저장 후 사이드바·채팅 헤더 갱신 | `useUpdateBuilderAgent`(`hooks/useAgentBuilder.ts`)는 `agentBuilder.all`·`agentStore.detail(id)`만 무효화. 사이드바·채팅이 쓰는 `useMyAgents`(`hooks/useAgentSubscription.ts`, 키 `agent.my`)는 무효화되지 않음 | §2.4 — `queryKeys.agent.all` 무효화 추가 (구독 뮤테이션과 같은 범위) |
| 상세 응답 권한 | 빌더 상세(`AgentDetail`, `types/agentStore.ts:67`)에 `can_edit` 포함. 볼 수 없는 에이전트는 404, 공개 에이전트는 200 + `can_edit=false` | §6 — 둘 다 "권한 없음" 배너로 처리 |
| 채팅 세션 유지 | `/chatpage`·`/agent-builder`는 같은 `AgentChatLayout` 아래 라우트. 레이아웃이 언마운트되지 않아 `activeSessionId`(레이아웃 `useState`)와 `selectedAgentId`(persist store)가 유지됨 | `returnTo=/chatpage`만으로 복귀. 세션 딥링크 불필요 |
| 편집 진입 직후 화면 | 현재 `handleEdit` 후 상세·카탈로그 로딩 동안 스튜디오가 이전 폼(기본값)으로 그려짐 | §5 — 프라임 전에는 로딩 화면 표시 (목록 카드 편집에도 동일 적용) |

---

## 2. Architecture

### 2.0 Architecture Comparison

| Criteria | Option A: Minimal | Option B: Clean | Option C: Pragmatic |
|----------|:-:|:-:|:-:|
| **Approach** | 각 파일에 경로 문자열·검증 직접 작성 | 전용 훅 `useBuilderEditEntry` + 상태 컴포넌트 분리 | 경로 유틸 1개 분리, 빌더 소비는 기존 effect 확장 |
| **New Files** | 0 | 3 (+테스트) | 1 (+테스트) |
| **Modified Files** | 7 | 7 | 7 |
| **Complexity** | Low | High | Medium |
| **Maintainability** | Medium (경로 규칙 3곳 중복) | High | High |
| **Effort** | Low | High | Medium |
| **Risk** | Medium (검증 누락 가능) | Medium (intent 소비와 흐름이 둘로 나뉨) | Low |

**Selected**: Option C — **Rationale**: 경로 규칙(인코딩·오픈 리다이렉트 차단)은 세 화면이 공유하므로 한 곳에 두고 테스트한다. 빌더 진입은 기존 위저드 intent 소비 effect와 같은 자리에서 처리해야 경합이 없으므로, 훅으로 떼어내지 않는다.

### 2.1 Component Diagram

```
┌──────────────────────┐        ┌───────────────────────────┐
│ ChatHeader (📁 ✏️)    │──┐     │ utils/agentEditLink.ts     │
│  canEdit ← ChatPage  │  ├────▶│  buildAgentEditPath()      │
└──────────────────────┘  │     │  parseSafeReturnTo()       │
┌──────────────────────┐  │     └─────────────┬─────────────┘
│ AgentWorkspacePage   │──┘                   │
│  [수정하기] can_edit  │                      ▼
└──────────────────────┘        ┌───────────────────────────┐
                                │ AgentBuilderPage           │
  /agent-builder?edit=&returnTo │  consume effect (1회)      │
 ──────────────────────────────▶│   intent > ?edit           │
                                │  prime effect (기존)       │
                                │  denied effect (신규)      │
                                │  cancel/confirm → returnTo │
                                └───────────────────────────┘
```

### 2.2 Data Flow

```
[채팅] ✏️ 클릭
  → /agent-builder?edit=agent-1&returnTo=%2Fchatpage
  → 소비 effect: 카탈로그·모델 settled → intent 없음 → editId 채택
      setEditingId(agent-1), primedAgentRef=null, setFromEntry(false),
      returnToRef = parseSafeReturnTo(raw), setView('edit')
  → useBuilderAgentDetail(agent-1) 조회
      ├ 성공 + can_edit → 기존 프라임 effect → mapDetailToForm → 스튜디오
      └ 실패 또는 can_edit=false → denied effect → 목록 + 배너, URL 파라미터 제거
  → [저장] 성공 → 결과 다이얼로그 [확인] → navigate(returnTo)
  → [취소] → navigate(returnTo)
  → /chatpage: 같은 에이전트·세션 유지, agent.my 무효화로 이름·오프너 갱신
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `AgentBuilderPage` | `useSearchParams`, `parseSafeReturnTo`, `useBuilderAgentDetail` | 진입 파라미터 소비·권한 확인·복귀 |
| `ChatHeader` | `buildAgentEditPath` | 수정 링크 |
| `AgentWorkspacePage` | `buildAgentEditPath` | 수정 링크 |
| `ChatPage` | `AgentSummary.canEdit` | 노출 조건 전달 |
| `toAgentSummary` | `MyAgent.source_type` | `canEdit` 계산 |
| `useUpdateBuilderAgent` | `queryKeys.agent.all` | 사이드바·채팅 목록 갱신 |

### 2.4 쿼리 무효화 변경

```ts
// hooks/useAgentBuilder.ts — useUpdateBuilderAgent.onSuccess
queryClient.invalidateQueries({ queryKey: queryKeys.agentBuilder.all });
queryClient.invalidateQueries({ queryKey: queryKeys.agentStore.detail(agentId) });
// agent-edit-entry §2.4: 채팅 사이드바·헤더(useMyAgents, agent.my)도 갱신
queryClient.invalidateQueries({ queryKey: queryKeys.agent.all });
```

`agent.all`은 구독·구독 해제 뮤테이션(`useAgentSubscription.ts`)이 이미 쓰는 범위와 같다.

---

## 3. Data Model

### 3.1 타입 변경

```ts
// types/agent.ts
export interface AgentSummary {
  id: string;
  name: string;
  description: string;
  category: string;
  isDefault?: boolean;
  openers?: string[];
  llmModelId?: string;
  // agent-edit-entry FR-08: 채팅 헤더 수정 아이콘 노출 조건 (owned·forked). 최종 판정은 빌더의 상세 can_edit
  canEdit?: boolean;
}
```

```ts
// services/agentSubscriptionService.ts — toAgentSummary
canEdit: agent.source_type === 'owned' || agent.source_type === 'forked',
```

SUPER 에이전트(`AgentChatLayout`이 직접 만드는 요약)는 `canEdit`을 넣지 않는다(undefined = 미노출).

### 3.2 URL 파라미터

| 키 | 값 | 사용처 | 수명 |
|----|----|--------|------|
| `edit` | agentId | 빌더 진입 | 편집 중 유지(새로고침 복원). 목록 복귀 시 제거 |
| `returnTo` | 앱 내부 경로(URL 인코딩) | 빌더 복귀 | 소비 시 ref에 저장. 목록 복귀 시 제거 |

### 3.3 유틸 명세 — `utils/agentEditLink.ts`

```ts
export const AGENT_EDIT_PARAM = 'edit';
export const RETURN_TO_PARAM = 'returnTo';

/** 편집 진입 URL. returnTo 생략 시 파라미터도 생략 */
export const buildAgentEditPath = (agentId: string, returnTo?: string): string => {
  const params = new URLSearchParams({ [AGENT_EDIT_PARAM]: agentId });
  if (returnTo) params.set(RETURN_TO_PARAM, returnTo);
  return `/agent-builder?${params.toString()}`;
};

/** 앱 내부 경로만 통과. 그 외(null·빈 값·외부 URL·프로토콜 상대·역슬래시)는 null */
export const parseSafeReturnTo = (raw: string | null): string | null => {
  if (!raw) return null;
  if (!raw.startsWith('/')) return null;          // 'chatpage', 'https://…', 'javascript:…'
  if (raw.startsWith('//') || raw.startsWith('/\\')) return null; // 프로토콜 상대 URL
  return raw;
};
```

컴포넌트 파일에서 런타임 상수를 export하지 않는 규칙에 따라 상수는 이 유틸 파일에 둔다.

---

## 4. API Specification

변경 없음. 기존 API만 사용한다.

| Method | Path | 용도 |
|--------|------|------|
| GET | `API_ENDPOINTS.AGENT_BUILDER_DETAIL(agentId)` | 편집 프라임 + `can_edit` 확인 |
| PATCH/PUT | 기존 빌더 update | 저장 (서버가 소유자 아닌 경우 403) |
| GET | 내 에이전트 목록(`useMyAgents`) | 채팅 `canEdit` 계산 근거 (`source_type`) |

API 계약 동기화 대상 아님.

---

## 5. UI/UX Design

### 5.1 채팅 헤더

```
┌──────────────────────────────────────────────────────────┐
│ 여신 상담봇  (12)              ✏️  📁  [● RAG · Agent] ⬇ 🗑 │
└──────────────────────────────────────────────────────────┘
  ✏️ = 에이전트 수정 (canEdit일 때만)   📁 = 워크스페이스 (기존)
```

- 위치: 📁 링크 **앞**. 수정이 더 자주 쓰이는 동작이고, 📁 링크의 기존 테스트 순서에 영향이 없다.
- 요소: `<Link>` + lucide `Pencil`(h-4 w-4, strokeWidth 1.75, `aria-hidden`).
- 스타일: 📁 링크와 같은 클래스(`inline-flex h-9 w-9 items-center justify-center rounded-md text-fg-subtle transition-colors duration-150 hover:bg-surface-sunken hover:text-fg`).
- 접근성: `aria-label="에이전트 수정"`, `title="에이전트 수정"`.

### 5.2 워크스페이스 헤더

기존 [수정하기] 버튼의 모양·노출 조건(`agent.can_edit`)은 그대로 두고 `to`만 바꾼다.

```tsx
to={buildAgentEditPath(agent.agent_id, `/agents/${agent.agent_id}/workspace`)}
```

### 5.3 빌더 — 편집 로딩 상태

`view === 'edit'`이고 프라임 전(`!editDetail`)이면 `StudioLayout` 대신 아래를 그린다.

```tsx
<div style={{ display: 'flex', height: '100%', alignItems: 'center', justifyContent: 'center' }}>
  <p className="text-sm text-fg-subtle" role="status">에이전트를 불러오는 중…</p>
</div>
```

> 판정은 `!editDetail`로 한다. 상세는 왔지만 카탈로그가 아직이면 프라임이 늦어질 수 있으나, 소비 effect 자체가 카탈로그·모델 settled 후에 실행되므로 `?edit` 진입에서는 상세 도착 직후 프라임된다. 목록 카드 편집은 목록 화면에서 이미 카탈로그가 로드돼 있다.

### 5.4 빌더 — 권한 없음 배너

목록 뷰 헤더 바로 아래, 스크롤 영역 위에 표시한다.

```
┌────────────────────────────────────────────────────────┐
│ ⚠ 이 에이전트를 수정할 권한이 없거나 찾을 수 없습니다.  [닫기] │
└────────────────────────────────────────────────────────┘
```

- `role="alert"`, `rounded-xl border border-warning-border bg-warning-bg px-4 py-3 text-sm text-warning`.
- [닫기]는 `IconButton aria-label="안내 닫기"` (X 아이콘). 다른 편집·새 에이전트 진입 시에도 자동으로 지운다.

### 5.5 User Flow

```
채팅(에이전트 A 대화 중) → ✏️ → 편집 스튜디오(A) → 지침 수정 → [저장]
  → "에이전트 수정 완료" 다이얼로그 [확인] → 채팅(A, 같은 세션) → 바로 재질문

워크스페이스(A) → [수정하기] → 편집 스튜디오(A) → [취소] → 워크스페이스(A)

URL 직접 입력 /agent-builder?edit=남의에이전트 → 목록 + 권한 없음 배너
```

### 5.6 Component List

| Component | Location | Responsibility |
|-----------|----------|----------------|
| `ChatHeader` | `components/layout/` | `canEdit` prop → 수정 링크 |
| `AgentWorkspacePage` | `pages/AgentWorkspacePage/` | 수정 링크 경로 |
| `AgentBuilderPage` | `pages/AgentBuilderPage/` | `?edit` 소비, 로딩·권한 없음, 복귀 |
| `agentEditLink` | `utils/` | URL 생성·`returnTo` 검증 |

### 5.7 Page UI Checklist

#### ChatPage / ChatHeader
- [ ] Link: "에이전트 수정" (`aria-label`), Pencil 아이콘, href `/agent-builder?edit={id}&returnTo=%2Fchatpage`
- [ ] 노출: 사용자 에이전트 + `canEdit=true`(owned·forked)
- [ ] 미노출: SUPER 에이전트, 구독(subscribed) 에이전트, `agentId` 없음
- [ ] 기존 Link "에이전트 워크스페이스" 유지

#### AgentWorkspacePage
- [ ] Link: "수정하기", href `/agent-builder?edit={id}&returnTo=%2Fagents%2F{id}%2Fworkspace`
- [ ] 노출 조건 `can_edit` 유지

#### AgentBuilderPage
- [ ] `?edit` 진입 시 편집 스튜디오(목록 미경유), 이름 필드에 해당 에이전트 이름 프라임
- [ ] 프라임 전 로딩 문구 "에이전트를 불러오는 중…" (`role="status"`)
- [ ] 권한 없음·없는 id: 목록 + 경고 배너 "이 에이전트를 수정할 권한이 없거나 찾을 수 없습니다." + [안내 닫기]
- [ ] [취소] → `returnTo` 경로 (없으면 기존: 위저드 경유 `/agent-builder/new`, 그 외 목록)
- [ ] 저장 성공 다이얼로그 [확인] → `returnTo` 경로 (없으면 목록)
- [ ] 목록으로 돌아갈 때 URL의 `edit`·`returnTo` 제거

---

## 6. Error Handling

| 상황 | 감지 | 처리 |
|------|------|------|
| 없는 id / 볼 수 없는 에이전트 | 상세 쿼리 `isError` (404, `ApiError.status`) | denied: 목록 + 배너, URL 정리 |
| 공개 에이전트(남의 것) | 상세 성공 + `can_edit === false` | denied 동일 |
| 저장 시 403 (권한 변경 등) | update `onError` | 기존 `saveErrorMessage` 다이얼로그 (변경 없음) |
| `returnTo` 비정상 | `parseSafeReturnTo` → null | 기존 복귀 동작 |
| 상세 조회 일시 실패 | queryClient retry 1회 후 `isError` | denied로 처리. 배너 문구가 "찾을 수 없습니다"를 포함해 오해 최소화 |

denied effect:

```ts
// agent-edit-entry FR-03: 상세 실패 또는 can_edit=false면 편집을 열지 않는다
useEffect(() => {
  if (view !== 'edit' || !editingId) return;
  const denied = isEditDetailError || (editDetail && !editDetail.can_edit);
  if (!denied) return;
  /* eslint-disable react-hooks/set-state-in-effect -- 서버 판정 결과를 1회 반영, 목록 전환으로 재실행 없음 */
  setEditingId(null);
  setView('list');
  setEditEntryNotice('이 에이전트를 수정할 권한이 없거나 찾을 수 없습니다.');
  returnToRef.current = null;
  /* eslint-enable react-hooks/set-state-in-effect */
  clearEditParams();
}, [view, editingId, editDetail, isEditDetailError]);
```

프라임 effect는 `editDetail.can_edit === false`이면 프라임하지 않도록 조건을 추가한다(배너 전환 전 한 프레임 동안 폼이 채워지는 것 방지).

---

## 7. Security Considerations

- [x] 오픈 리다이렉트 차단: `parseSafeReturnTo` — `/`로 시작, `//`·`/\` 거부. `navigate()`는 내부 라우터 경로만 다루지만 검증을 이중으로 둔다.
- [x] 권한: UI 노출(추정) → 상세 `can_edit`(서버 판정) → update 403(최종). 프론트 판정만으로 저장되지 않는다.
- [x] `edit` 값은 API 경로 파라미터로만 쓰이고(`API_ENDPOINTS.AGENT_BUILDER_DETAIL`) HTML에 그대로 삽입되지 않는다.

---

## 8. Test Plan

> API 변경이 없어 L1은 없다. 프로젝트 표준(Vitest + RTL + MSW)으로 L2 수준을 컴포넌트 테스트에서 검증하고, L3은 화면 확인으로 대신한다.

### 8.1 Test Scope

| Type | Target | Tool | Phase |
|------|--------|------|-------|
| Unit | `agentEditLink`, `toAgentSummary`, `useUpdateBuilderAgent` 무효화 | Vitest | Do |
| Component | `ChatHeader`, `AgentWorkspacePage`, `AgentBuilderPage` | Vitest + RTL + MSW | Do |
| 화면 확인 | 채팅↔빌더, 워크스페이스↔빌더 왕복 (375 / 1440) | Chrome DevTools MCP | Check |

### 8.2 Unit

| # | 대상 | 케이스 | 기대 |
|---|------|--------|------|
| U1 | `buildAgentEditPath` | `('agent-1', '/chatpage')` | `/agent-builder?edit=agent-1&returnTo=%2Fchatpage` |
| U2 | `buildAgentEditPath` | returnTo 생략 | `/agent-builder?edit=agent-1` |
| U3 | `parseSafeReturnTo` | `/chatpage`, `/agents/a-1/workspace` | 그대로 반환 |
| U4 | `parseSafeReturnTo` | `null`, `''`, `chatpage`, `https://evil.com`, `//evil.com`, `/\evil.com`, `javascript:alert(1)` | `null` |
| U5 | `toAgentSummary` | `source_type` owned / forked / subscribed | `canEdit` true / true / false |
| U6 | `useUpdateBuilderAgent` | 성공 시 | `invalidateQueries`에 `queryKeys.agent.all` 포함 |

### 8.3 Component

| # | 화면 | 동작 | 기대 |
|---|------|------|------|
| C1 | ChatHeader | `agentId` + `canEdit` | "에이전트 수정" 링크 href = U1 결과 |
| C2 | ChatHeader | `canEdit` false/undefined, 또는 `agentId` 없음 | 수정 링크 없음, 워크스페이스 링크 조건은 기존대로 |
| C3 | AgentWorkspacePage | `can_edit=true` | "수정하기" href = `/agent-builder?edit=agent-1&returnTo=%2Fagents%2Fagent-1%2Fworkspace` |
| C4 | AgentBuilderPage | `?edit=agent-1` 진입 | 목록 헤더 없이 스튜디오, 이름 필드 = 상세 이름 |
| C5 | AgentBuilderPage | 상세 로딩 지연 | "에이전트를 불러오는 중…" 표시 후 스튜디오 |
| C6 | AgentBuilderPage | 상세 `can_edit=false` | 목록 + 경고 배너, 스튜디오 미표시 |
| C7 | AgentBuilderPage | 상세 404 | C6과 동일 |
| C8 | AgentBuilderPage | `returnTo=/chatpage` + [취소] | 현재 경로 `/chatpage` |
| C9 | AgentBuilderPage | `returnTo=/chatpage` + 저장 성공 + [확인] | 현재 경로 `/chatpage` |
| C10 | AgentBuilderPage | `returnTo` 없음 + [취소] | 목록 뷰, URL 검색어 비어 있음 |
| C11 | AgentBuilderPage | `returnTo=https://evil.com` + [취소] | 목록 뷰 (외부 이동 없음) |
| C12 | AgentBuilderPage | 위저드 intent 적재 + `?edit` 동시 | intent 우선 — create 뷰, 위저드 값 프라임 |
| C13 | AgentBuilderPage | 기존 describe 전체 | 회귀 0 (목록 카드 편집은 C5 로딩 화면을 거쳐 동일 결과) |

테스트 헬퍼: `renderPage(initialEntry?)` — `MemoryRouter initialEntries={[initialEntry ?? '/agent-builder']}` + `Routes`(`/agent-builder`, `/chatpage`, `/agents/:agentId/workspace`) + 경로 표시용 `LocationDisplay`(`data-testid="location"`, pathname+search). 기존 호출부 `renderPage()`는 인자 없이 그대로 동작한다.

### 8.4 화면 확인 시나리오 (Check)

| # | Scenario | Success Criteria |
|---|----------|-----------------|
| E1 | 채팅에서 내 에이전트로 대화 → ✏️ → 지침 수정 → 저장 → 확인 | 같은 에이전트·세션의 채팅으로 복귀, 사이드바 이름 반영 |
| E2 | 워크스페이스 → 수정하기 → 취소 | 워크스페이스 복귀 |
| E3 | 구독 에이전트 선택 | ✏️ 미노출 |
| E4 | 편집 중 새로고침 | 같은 에이전트 편집 화면 |
| E5 | 375px 폭 채팅 헤더 | 아이콘 겹침·줄바꿈 없음 |

### 8.5 Seed Data

MSW 픽스처: 상세(`can_edit` true / false), 404 응답, 내 에이전트 목록(owned 1·forked 1·subscribed 1). 로컬 화면 확인은 기존 로컬 DB의 owned 에이전트 1개 + 구독 1개.

---

## 9. Layer Assignment

| Component | Layer | Location |
|-----------|-------|----------|
| `ChatHeader`, `AgentWorkspacePage`, `AgentBuilderPage`, `ChatPage` | Presentation | `src/components/layout/`, `src/pages/` |
| `useUpdateBuilderAgent` | Application (hooks) | `src/hooks/useAgentBuilder.ts` |
| `toAgentSummary` | Application (service mapper) | `src/services/agentSubscriptionService.ts` |
| `AgentSummary` | Domain (types) | `src/types/agent.ts` |
| `agentEditLink` | Util (순수 함수) | `src/utils/agentEditLink.ts` |

---

## 10. Coding Convention Reference

| Item | Convention Applied |
|------|-------------------|
| Component | Arrow function, props `interface`, `export default` 하단 |
| 상수 위치 | URL 파라미터 키는 `utils/agentEditLink.ts` (컴포넌트 파일 상수 export 금지) |
| State | URL = `useSearchParams`, 복귀 경로 = `useRef`(리렌더 불필요), 배너 = `useState` |
| Query | 키는 `queryKeys` 팩토리만 사용 |
| 스타일 | 디자인 토큰(`text-fg-subtle`, `warning-*`), `zinc-400`·hex 금지, 아이콘 lucide 16px/1.75 |
| 주석 | `// agent-edit-entry FR-xx:` / `// Design Ref: §x` |
| Test | 소스 옆 배치, 기존 describe 뒤에 `describe('AgentBuilderPage 편집 진입 (agent-edit-entry)')` 추가 |

---

## 11. Implementation Guide

### 11.1 File Structure

```
idt_front/src/
├── utils/agentEditLink.ts                      (신규)
├── utils/agentEditLink.test.ts                 (신규)
├── types/agent.ts                              (수정: AgentSummary.canEdit)
├── services/agentSubscriptionService.ts        (수정: toAgentSummary)
├── hooks/useAgentBuilder.ts                    (수정: agent.all 무효화)
├── pages/AgentBuilderPage/index.tsx            (수정)
├── pages/AgentBuilderPage/index.test.tsx       (수정: 헬퍼 + describe 추가)
├── pages/AgentWorkspacePage/index.tsx          (수정: 링크)
├── pages/AgentWorkspacePage/index.test.tsx     (수정: href 기대값)
├── components/layout/ChatHeader.tsx            (수정)
├── components/layout/ChatHeader.test.tsx       (수정)
└── pages/ChatPage/index.tsx                    (수정: canEdit 전달)
```

### 11.2 Implementation Order (TDD: 각 단계 테스트 먼저)

1. [ ] `agentEditLink` 유틸 + 테스트 (U1–U4)
2. [ ] `AgentSummary.canEdit` + `toAgentSummary` + 테스트 (U5)
3. [ ] `useUpdateBuilderAgent` 무효화 + 테스트 (U6)
4. [ ] `AgentBuilderPage`
   1. 테스트 헬퍼 `renderPage(initialEntry?)` 확장
   2. `useSearchParams`, `returnToRef`, `editEntryNotice` 상태, `clearEditParams()`
   3. 소비 effect 확장: intent 없을 때 `edit` 채택 (C4, C12)
   4. 로딩 화면 (C5) · 프라임 effect `can_edit` 조건 · denied effect + 배너 (C6, C7)
   5. `handleCancel` / `handleSaveResultConfirm` 복귀 우선순위 `returnTo > fromEntry > 목록` + 목록 복귀 시 URL 정리 (C8–C11)
   6. `handleEdit`·`handleNew`에서 배너 해제
5. [ ] `AgentWorkspacePage` 링크 + 테스트 (C3)
6. [ ] `ChatHeader` `canEdit` + 테스트 (C1, C2) → `ChatPage` 전달
7. [ ] 전체 회귀: `npx vitest run --no-file-parallelism`, `npm run lint`, `npm run type-check`, `npm run build`

복귀 분기 의사 코드:

```ts
const goBackAfterEdit = () => {
  const target = returnToRef.current;
  if (target) { navigate(target); return true; }
  return false;
};

const handleCancel = () => {
  if (goBackAfterEdit()) return;
  if (fromEntry) { navigate('/agent-builder/new'); return; }
  clearEditParams();
  setView('list');
};

const handleSaveResultConfirm = () => {
  if (saveResult?.type === 'success') {
    setSaveResult(null);
    if (goBackAfterEdit()) return;
    setFromEntry(false);
    clearEditParams();
    setView('list');
    return;
  }
  setSaveResult(null);
};
```

> `returnTo`는 `?edit` 진입에서만 채워진다. 생성(create) 저장 후에는 `returnToRef`가 null이므로 기존 동작이 유지된다.

### 11.3 Session Guide

#### Module Map

| Module | Scope Key | Description | Estimated Turns |
|--------|-----------|-------------|:---------------:|
| 기반 (유틸·타입·매퍼·무효화) | `module-1` | 구현 순서 1–3 | 8-10 |
| 빌더 진입·권한·복귀 | `module-2` | 구현 순서 4 | 20-25 |
| 진입 버튼 (워크스페이스·채팅 헤더) | `module-3` | 구현 순서 5–6 + 전체 회귀 | 10-12 |

#### Recommended Session Plan

| Session | Phase | Scope | Turns |
|---------|-------|-------|:-----:|
| Session 1 | Do | `--scope module-1,module-2` | 30-35 |
| Session 2 | Do + Check | `--scope module-3` + 화면 확인·gap 분석 | 25-30 |

규모가 작아 한 세션(`/pdca do agent-edit-entry`)으로 진행해도 된다.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-11-05 | Initial draft — Option C 선택, 사이드바 무효화 누락·로딩 상태 추가 | 배상규 |
