# agent-edit-entry Planning Document

> **Summary**: 채팅 화면·워크스페이스에서 해당 에이전트의 편집 화면으로 바로 들어가고, 저장·취소 후 원래 화면으로 돌아오게 한다.
>
> **Project**: sangplusbot (idt_front)
> **Author**: 배상규
> **Date**: 2026-11-05
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 채팅 화면에는 에이전트 수정 버튼이 없고, 워크스페이스의 [수정하기]는 agentId 없이 `/agent-builder`로 이동해 빌더 목록이 열린다. 사용자는 목록에서 같은 에이전트를 다시 찾아 편집을 눌러야 하고, 저장 후에는 원래 보던 채팅으로 직접 돌아가야 한다. |
| **Solution** | 빌더에 `?edit={agentId}` 진입을 추가해 해당 에이전트의 편집 스튜디오를 바로 연다. 워크스페이스 [수정하기]와 채팅 헤더의 새 수정 아이콘이 이 URL로 이동하고, `returnTo`로 저장·취소 후 들어온 화면으로 복귀한다. |
| **Function/UX Effect** | 채팅 중 지침·도구를 고치고 싶을 때 클릭 1번으로 편집 화면에 들어가고, 저장 후 같은 대화로 돌아와 바로 결과를 확인한다. 새로고침해도 편집 화면이 유지된다. |
| **Core Value** | P2(에이전트 소유자)의 "써보고 → 고치고 → 다시 써보는" 반복 주기를 짧게 만든다. 백엔드 변경 없이 기존 편집 경로(`handleEdit`·`mapDetailToForm`)를 재사용한다. |

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

### 1.1 Purpose

에이전트를 "쓰는 화면"(채팅·워크스페이스)에서 "고치는 화면"(빌더 편집 스튜디오)으로 바로 이동하고, 고친 뒤 원래 화면으로 돌아오는 경로를 만든다.

### 1.2 Background — 현재 코드 확인 결과

| 위치 | 현재 동작 | 문제 |
|------|----------|------|
| `idt_front/src/pages/AgentWorkspacePage/index.tsx:205-212` | `can_edit`일 때 [수정하기] = `<Link to="/agent-builder">` | agentId를 넘기지 않아 빌더 **목록**이 열린다 |
| `idt_front/src/pages/AgentBuilderPage/index.tsx:142-143` | `view`·`editingId`를 `useState`로만 보관 | URL로 특정 에이전트 편집을 열 수 없다. 새로고침 시 목록으로 돌아간다 |
| `idt_front/src/pages/AgentBuilderPage/index.tsx:240-247` | 편집 진입은 목록 카드의 `handleEdit`뿐 | 외부 화면에서 재사용할 진입점이 없다 |
| `idt_front/src/pages/AgentBuilderPage/index.tsx:598-612` | 취소·저장 확인 후 `setView('list')` (위저드 경유 시만 `/agent-builder/new`) | 채팅에서 왔어도 빌더 목록에 남는다 |
| `idt_front/src/components/layout/ChatHeader.tsx:26-35` | 사용자 에이전트 선택 시 워크스페이스 📁 링크만 노출 | 수정 버튼이 없다 |
| `idt_front/src/services/agentSubscriptionService.ts:14-24` | `toAgentSummary`가 `source_type`을 `category`에만 담는다 | 채팅 화면에서 "내가 고칠 수 있는 에이전트인지" 판단할 명시 필드가 없다 |

권한 근거:
- 백엔드 `VisibilityPolicy.can_edit` = 소유자만 true (`idt/src/domain/agent_builder/policies.py:52`). 상세 응답에 `can_edit` 포함 (`idt/src/application/agent_builder/schemas.py:268`).
- 사이드바 내 에이전트 목록의 `source_type`: `owned`·`forked`는 사용자 소유 목록에서 나오고(`list_my_agents_use_case.py:47-57`), `subscribed`는 남의 에이전트다. 따라서 채팅 화면의 노출 조건은 `source_type ∈ {owned, forked}`로 판단할 수 있다(추가 조회 없음). 최종 권위는 빌더가 상세의 `can_edit`로 다시 확인하고, 서버 update가 403으로 한 번 더 막는다.

### 1.3 Related Documents

- `docs/USER-SCENARIOS.md` — 주인공 P2(KB 운영자/에이전트 소유자)
- `docs/archive/2026-11/sidebar-agent-list/` — 사이드바 에이전트 목록(source_type 그룹)
- 워크스페이스 원 설계: agent-workspace-view (페이지 주석 "편집은 agent-builder 담당")
- 빌더 편집 프라임: agent-builder-edit-mapping (FR-4 1회 프라임 가드)

---

## 2. Scope

### 2.1 In Scope

- [ ] **빌더 `?edit={agentId}` 진입**: `/agent-builder?edit=agent-1`로 열면 해당 에이전트 편집 스튜디오(`view='edit'`)가 바로 열린다. 기존 `handleEdit` 경로·`mapDetailToForm` 프라임 재사용.
- [ ] **복귀 지점 `returnTo`**: `?edit=…&returnTo=/chatpage` 형태로 들어온 화면을 받아, 저장 성공 확인·취소 시 그 경로로 `navigate`. `returnTo`가 없으면 기존대로 목록.
- [ ] **워크스페이스 [수정하기] 수정**: `/agent-builder?edit={agentId}&returnTo=/agents/{agentId}/workspace`로 변경.
- [ ] **채팅 헤더 수정 아이콘**: `ChatHeader`에 연필 아이콘 링크 추가(📁 옆). `canEdit`일 때만 노출. 이동 경로 `/agent-builder?edit={agentId}&returnTo=/chatpage`.
- [ ] **`AgentSummary.canEdit` 필드**: `toAgentSummary`에서 `source_type ∈ {owned, forked}` → `canEdit: true`. SUPER 에이전트·구독 에이전트는 false.
- [ ] **권한 없음·없는 id 처리**: 상세 조회 실패(404/403) 또는 `can_edit=false`면 "이 에이전트를 수정할 권한이 없습니다" 안내 후 목록 뷰. 폼은 열지 않는다.
- [ ] **쿼리 정리**: `?edit` 소비 후 `replace`로 URL에서 제거하지 **않고** 편집 중 유지(새로고침 시 같은 편집 화면 복원). 목록으로 돌아갈 때 제거.
- [ ] 위 항목 전부 Vitest + RTL 테스트 선작성(TDD).

### 2.2 Out of Scope

- 백엔드 API·스키마 변경 (기존 상세·수정 API로 충분).
- 빌더 전체를 URL 기반 라우팅(`/agent-builder/:id/edit`)으로 재구성.
- 사이드바 에이전트 항목 hover 수정 아이콘 (헤더 아이콘으로 결정, 후속 후보).
- 에이전트 스토어 상세 모달(`AgentDetailModal`)의 수정 진입 — 현재 워크스페이스로 이동하므로 워크스페이스 수정으로 자연히 해결된다.
- 저장하지 않은 변경이 있을 때 이탈 경고(현재 빌더에도 없음, 별도 기능).
- 저장 후 채팅에 열린 세션의 실행 설정 즉시 반영 검증 외의 채팅 동작 변경.

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | `/agent-builder?edit={agentId}` 진입 시 목록을 거치지 않고 해당 에이전트 편집 스튜디오를 연다. 폼은 기존 edit 프라임(`mapDetailToForm`, 모델·도구 카탈로그 settled 후 1회)으로 채운다. | High | Pending |
| FR-02 | `?edit` 소비는 마운트 후 1회만 수행하고(ref 가드), 위저드 intent(`consumePendingIntent`)가 있으면 intent가 우선한다(두 진입이 동시에 올 일은 없지만 경합 방지). | High | Pending |
| FR-03 | 상세 조회 실패 또는 `can_edit=false`이면 편집 화면을 열지 않고 "이 에이전트를 수정할 권한이 없습니다." 안내 후 목록 뷰를 보여준다. | High | Pending |
| FR-04 | `returnTo` 파라미터가 있으면 취소 시, 저장 성공 결과 확인 시 해당 경로로 이동한다. 없으면 기존 동작(목록 / 위저드 경유 시 `/agent-builder/new`). | High | Pending |
| FR-05 | `returnTo`는 앱 내부 경로(`/`로 시작, `//`·스킴 불가)만 허용한다. 그 외 값은 무시하고 기존 동작. | High | Pending |
| FR-06 | 워크스페이스 [수정하기]가 `/agent-builder?edit={agentId}&returnTo=/agents/{agentId}/workspace`로 이동한다(노출 조건 `can_edit` 유지). | High | Pending |
| FR-07 | 채팅 헤더에 수정 아이콘 링크(`aria-label="에이전트 수정"`, lucide `Pencil`)를 추가한다. 사용자 에이전트 선택 + `canEdit=true`일 때만 노출, 이동 경로 `/agent-builder?edit={agentId}&returnTo=/chatpage`. | High | Pending |
| FR-08 | `AgentSummary`에 `canEdit?: boolean`을 추가하고 `toAgentSummary`가 `source_type`이 `owned`·`forked`면 true로 채운다. SUPER는 항상 false. | High | Pending |
| FR-09 | 채팅으로 복귀하면 선택 에이전트·활성 세션이 유지된다(`layoutStore` persist 기존 동작 확인). 저장된 변경(이름 등)이 사이드바·헤더에 반영된다(기존 update 뮤테이션의 쿼리 무효화 확인). | Medium | Pending |
| FR-10 | 편집 중 새로고침하면 같은 에이전트 편집 화면이 다시 열린다(`?edit` 유지). 목록으로 돌아갈 때는 `edit`·`returnTo`를 URL에서 제거한다. | Medium | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Security | `returnTo` 오픈 리다이렉트 차단(내부 경로만). 권한 판단은 UI 노출 + 상세 `can_edit` + 서버 403 3중. | 단위 테스트(외부 URL·`//evil` 거부) |
| Accessibility | 아이콘 링크에 `aria-label`·`title`. 키보드 포커스 가능. `text-fg-subtle` 토큰 사용(zinc-400 금지). | RTL `getByRole('link', {name})` |
| Compatibility | 빌더 목록 카드 편집·위저드 진입·[새 에이전트] 기존 흐름 회귀 없음. | 기존 `AgentBuilderPage`·`agentCreateWizard` 테스트 통과 |
| Design | `ChatHeader` 기존 📁 링크와 같은 스타일(h-9 w-9, `hover:bg-surface-sunken`). | 화면 확인 375/1440 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] SC-1: 워크스페이스 [수정하기] 클릭 → 해당 에이전트 편집 스튜디오가 바로 열린다(목록 미경유).
- [ ] SC-2: 채팅 화면에서 내 에이전트(owned·forked) 선택 시 수정 아이콘이 보이고, 구독 에이전트·SUPER에서는 보이지 않는다.
- [ ] SC-3: 채팅에서 진입 → 저장 → 결과 확인 시 `/chatpage`로 돌아가고, 같은 에이전트·세션이 선택돼 있다. 취소도 동일.
- [ ] SC-4: 워크스페이스에서 진입 → 저장/취소 시 워크스페이스로 돌아간다.
- [ ] SC-5: 권한 없는 id·없는 id로 `?edit` 진입 시 안내 후 목록, 편집 폼은 열리지 않는다.
- [ ] SC-6: `returnTo=https://…`·`//…`는 무시된다.
- [ ] SC-7: 기존 빌더 흐름(목록 편집·새 에이전트·위저드 경유 취소) 테스트 회귀 0.

### 4.2 Quality Criteria

- [ ] 신규·변경 로직 테스트 선작성 (`AgentBuilderPage` edit 진입·returnTo, `ChatHeader`, `AgentWorkspacePage`, `toAgentSummary`, returnTo 검증 유틸)
- [ ] `npm run lint`·`npm run type-check`·`npm run build` 통과
- [ ] 프론트 회귀 `--no-file-parallelism`로 전체 실행, 실패는 master 기준 diff로 확인

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| `?edit` 소비 effect가 위저드 intent 소비 effect·edit 프라임 1회 가드(`primedAgentRef`)와 경합해 빈 폼·덮어쓰기 발생 | High | Medium | 소비는 `handleEdit`과 같은 상태 전이(`setEditingId`+`primedAgentRef=null`+`setView('edit')`)만 수행하고 프라임은 기존 effect에 맡긴다. intent가 있으면 `?edit` 무시. 테스트로 순서 고정 |
| 상세 조회 전 스튜디오가 잠깐 빈 폼으로 보임 | Medium | High | 상세 로딩 중에는 스튜디오 대신 로딩 표시(또는 기존 edit 진입과 동일 처리인지 Design에서 확인) |
| `can_edit` 판정 전에 편집 폼이 열려 권한 없는 사용자가 폼을 봄 | Medium | Medium | 상세 응답 `can_edit` 확인 후에만 `view='edit'` 확정. 서버 update 403이 최종 방어 |
| `returnTo` 오픈 리다이렉트 | Medium | Low | 내부 경로 검증 유틸 + 테스트 |
| 채팅 복귀 시 선택 에이전트가 다른 것으로 바뀜(사이드바 목록 refetch 순서) | Medium | Low | `selectedAgentId`는 persist store — 복귀 후 유지되는지 통합 테스트·화면 확인 |
| `canEdit`를 `source_type`으로 추정 — 백엔드 정책 변경(예: 부서 편집 권한) 시 어긋남 | Low | Low | 노출만 추정, 최종 판정은 상세 `can_edit`. 정책 변경 시 목록 응답에 `can_edit` 추가를 후속 과제로 기록 |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `AgentBuilderPage` | Page | `useSearchParams`로 `edit`·`returnTo` 소비, 취소·저장 확인 시 복귀 분기 |
| `AgentWorkspacePage` | Page | [수정하기] 링크 경로 변경 |
| `ChatHeader` | Component | `canEdit` prop + 수정 아이콘 링크 추가 |
| `ChatPage` | Page | `ChatHeader`에 `canEdit` 전달 |
| `AgentSummary` (`types/agent.ts`) | Type | `canEdit?: boolean` 추가 (선택 필드 — 기존 사용처 무영향) |
| `toAgentSummary` (`services/agentSubscriptionService.ts`) | Mapper | `canEdit` 채움 |
| 신규 유틸 (예: `utils/safeReturnTo.ts`) | Util | 내부 경로 검증 |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| `/agent-builder` 진입 | READ | `AgentList.tsx:136`, `AppSidebar.tsx:44`, `TopNav.tsx:46`, `Sidebar.tsx:22`, `AgentStorePage:108,113`, `AgentCreateEntryPage:126` | None — 파라미터 없으면 기존 동작 |
| 빌더 취소/저장 확인 | UPDATE | `handleCancel`·`handleSaveResultConfirm` (`AgentBuilderPage:598-612`) | Needs verification — `fromEntry` 분기와 `returnTo` 우선순위 |
| 위저드 intent 소비 | READ | `AgentBuilderPage:196-222`, `agentCreateWizard.test.tsx` | Needs verification — `?edit`와 경합 없음 테스트 |
| `ChatHeader` props | READ | `ChatPage:521-524`, `ChatHeader.test.tsx` | None — 선택 prop 추가 |
| `AgentSummary` | READ | `AgentChatLayout:127-139`, `ChatPage` 여러 테스트, `layoutStore` | None — 선택 필드 |
| 워크스페이스 [수정하기] | READ | `AgentWorkspacePage/index.test.tsx` | Breaking(테스트) — href 기대값 갱신 |

### 6.3 Verification

- [ ] 위 소비처 테스트 전부 통과
- [ ] 권한 노출 조건(owned·forked만) 테스트
- [ ] 스키마 변경 없음 — API 계약 동기화 대상 아님

---

## 7. Architecture Considerations

### 7.1 Project Level

기존 idt_front 구조(Dynamic 수준, pages/components/hooks/services) 유지. 새 레이어·라이브러리 없음.

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 편집 진입 방식 | 쿼리 `?edit` / 전용 라우트 / navigate state | **쿼리 `?edit={id}`** | 라우트 추가 없이 새로고침·링크 공유 가능. 빌더의 state 기반 구조를 그대로 두고 진입만 추가 |
| 복귀 지점 | 들어온 곳 / 항상 목록 | **`returnTo` 쿼리로 들어온 곳** | 채팅→수정→채팅 반복 주기 단축. `navigate(-1)`은 직접 URL 진입 시 앱 밖으로 나갈 수 있어 명시 경로 사용 |
| 채팅 노출 위치 | 헤더 아이콘 / 헤더+사이드바 | **ChatHeader 아이콘** | 현재 대화 중인 에이전트에 대한 동작이라 헤더가 맞다. 기존 📁 옆 배치 |
| 채팅 권한 판단 | `source_type` / 상세 조회 `can_edit` | **`source_type ∈ {owned, forked}`** | 추가 요청 없음. 최종 판정은 빌더의 상세 `can_edit` |
| 권한 없음 처리 | 안내 후 목록 / 워크스페이스 리다이렉트 | **안내 후 목록** | 빌더 내부에서 완결, 백엔드 무변경 |
| Testing | Vitest + RTL + MSW | 동일 | 프로젝트 표준 |

### 7.3 Folder Structure Preview

```
idt_front/src/
├── pages/AgentBuilderPage/index.tsx        (수정: ?edit·returnTo 소비, 복귀 분기)
├── pages/AgentWorkspacePage/index.tsx      (수정: 링크 경로)
├── pages/ChatPage/index.tsx                (수정: canEdit 전달)
├── components/layout/ChatHeader.tsx        (수정: 수정 아이콘)
├── services/agentSubscriptionService.ts    (수정: canEdit 매핑)
├── types/agent.ts                          (수정: AgentSummary.canEdit)
└── utils/safeReturnTo.ts                   (신규: 내부 경로 검증)
```

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- [x] `idt_front/CLAUDE.md` 코딩 컨벤션·디자인 토큰·TDD 규칙
- [x] ESLint / TypeScript 설정
- [x] 컴포넌트 파일 런타임 상수 export 금지 → 경로 생성 헬퍼는 `utils/`에 둔다

### 8.2 Conventions to Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| URL 쿼리 키 | `?agentId=&sessionId=`(채팅 딥링크) 존재 | 빌더는 `edit`·`returnTo` — Design에서 키 이름 확정 | Medium |
| 아이콘 | lucide-react, 16px, strokeWidth 1.75 | `Pencil` 사용 | Low |

### 8.3 Environment Variables Needed

없음.

---

## 9. Next Steps

1. [ ] `/pdca design agent-edit-entry` — 빌더 소비 effect 순서, 로딩·권한 없음 상태 화면, `returnTo` 우선순위(`returnTo` > `fromEntry` > 목록) 확정
2. [ ] 구현(TDD) — worktree에서 진행
3. [ ] 화면 확인 — 채팅·워크스페이스 왕복, 375/1440 폭

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-11-05 | Initial draft (코드 확인 + 요구사항 4건 확정) | 배상규 |
