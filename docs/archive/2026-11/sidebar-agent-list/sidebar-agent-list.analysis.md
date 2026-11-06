# sidebar-agent-list Gap Analysis

> **Feature**: sidebar-agent-list
> **Date**: 2026-11-04
> **Plan**: [sidebar-agent-list.plan.md](sidebar-agent-list.plan.md)
> **Design**: [sidebar-agent-list.design.md](sidebar-agent-list.design.md)
> **Worktree**: `wt/sidebar-agent-list` (branch `feature/sidebar-agent-list`, 미커밋)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 에이전트 목록의 가시성이 낮고 세로 공간이 하단 메뉴에 밀린다 |
| **WHO** | 사이드바로 에이전트를 골라 대화하는 모든 로그인 사용자, 특히 에이전트를 여러 개 가진 P2 |
| **RISK** | 하단 메뉴를 아이콘만 남기면 메뉴 이름을 알아보기 어려워짐 → 툴팁·aria-label 유지, 기존 테스트의 이름 기반 조회 보존 |
| **SUCCESS** | 1440×900 기준 보이는 에이전트 수 증가, 이름 `sidebar-fg` 적용, 그룹 접기 상태 새로고침 후 유지, 기존 AppSidebar 테스트 통과 |
| **SCOPE** | 프론트 단일 컴포넌트(AppSidebar) + layoutStore 필드 1개. 백엔드·API 변경 없음 |

---

## 1. Match Rate

| Axis | Score | 근거 |
|------|:-----:|------|
| Structural | 100% | 설계한 소스 6개·테스트 3개 모두 지정 경로에 존재. 소비자 `AgentChatLayout.tsx:154-161` 변경 없음 |
| Functional | 96% | §5.4 체크리스트 11/11, FR 12/12, 테스트 ID 17/17. §6 오류 처리 중 저장값 타입 손상 1건 미방어(G1), 테스트 미작성 2건(G2·G3) |
| Contract | 100% | props·store 필드·타입·상수·persist 키·접근 가능한 이름 모두 설계와 일치 |
| Runtime | 100% | Vitest 관련 76개 통과, 브라우저 확인 항목 전부 통과 (§3) |

**Overall (runtime 포함)** = 100×0.15 + 96×0.25 + 100×0.25 + 100×0.35 = **99.0%**

---

## 2. Strategic Alignment

- **WHY 해결 여부**: 해결. 같은 예시 데이터·같은 화면 높이(735px)에서 목록 영역이 49px → 270px, 완전히 보이는 에이전트가 0개 → 3개로 늘었다 (master는 관리자 계정 기준).
- **결정 준수**: 설계안 C(목록·도크 2개 컴포넌트 분리), `collapsedAgentGroups` persist, `SHOW_AGENT_AVATAR` 상수, 2줄 항목, 하단 도크 — 전부 그대로 구현.

### Plan Success Criteria

| 기준 | 상태 | 근거 |
|------|:----:|------|
| FR-01 ~ FR-12 구현 | ✅ | gap-detector 12/12 |
| 새 테스트(접기·persist·도크·아바타·선택) | ✅ | `layoutStore.test.ts` ST1-4, `AgentList.test.tsx` AL1-9+AL7b, `SidebarDock.test.tsx` SD1-5 |
| 기존 AppSidebar 테스트 통과 | ✅ | C1~C3, A1~A4, S1~S2 수정 없이 통과 |
| 1440에서 보이는 에이전트 수 증가 | ✅ | 0 → 3 (브라우저 측정) |
| lint·type-check·build | ⚠️ | 수정 파일 lint 0 error, `type-check` 통과, `vite build` 통과. `npm run build`의 `tsc -b`는 기존 오류 210건으로 실패 — master도 동일 210건 |
| 관련 테스트 통과 | ✅ | `src/components/layout`·`src/store` 13 파일 76 테스트 |
| 콘솔 오류 없음 | ✅ | 새로고침 후 오류 0 |

전체 회귀: 1724 중 9건 실패 — master에서 같은 9건(ChatPage TC-FE-2, CreateCollectionModal, UpdateScopeModal 6, DatasetsTab) 실패, 신규 실패 없음.

---

## 3. Runtime Verification

| 항목 | 결과 |
|------|------|
| 1440: 2줄 항목·아바타·별·설명 말줄임 | ✅ |
| 그룹 접기 → 새로고침 후 유지 (`["owned"]`) | ✅ |
| 항목 클릭 → 선택 배경 + 좌측 바, 채팅 헤더 전환 | ✅ |
| 하단 도크: 일반 사용자 5개, 사용자 1줄 | ✅ |
| 접힌 레일: 도크 세로 한 열 | ✅ |
| 768: 펼친 사이드바에서 목록·도크 정상 | ✅ (같은 출처 iframe 768px) |
| 375: 저장값 없을 때 첫 진입 레일로 접힘 | ✅ (같은 출처 iframe 375px) |

데이터: 로그인 계정의 에이전트가 0개라 `queryClient.setQueryData`로 예시 데이터를 캐시에만 주입했다(DB 변경 없음). 확인 후 `layout-preferences` 값은 원래대로 복구.

---

## 4. Gaps

| # | Severity | 위치 | 내용 |
|---|----------|------|------|
| G1 | Minor | `layoutStore.ts` persist 옵션, `AgentList.tsx` `collapsedGroups.includes` | Design §6의 "persist 값 손상 → []"가 필드 누락·JSON 파싱 실패만 막는다. `collapsedAgentGroups: null`처럼 타입이 틀린 저장값은 얕은 merge로 초기값을 덮어써 `.includes`에서 사이드바가 깨진다 |
| G2 | Minor | `AgentList.test.tsx` | 빈 이름 → 아바타 `?` 테스트 없음 (코드는 처리) |
| G3 | Minor | `AgentList.test.tsx` | 비어 있는 그룹의 접힘 키가 저장된 경우 테스트 없음 (코드는 처리) |
| G4 | Minor | `AgentList.tsx` ChevronDown | `strokeWidth={2}` — 규칙은 1.75 |
| G5 | Minor | `AgentList.tsx`, `SidebarDock.tsx` | 하위 컴포넌트 props interface가 파일 중간에 선언됨 (스타일) |

Critical·Important 없음.

### 4.1 Act-1 (2026-11-04) — G1~G4 수정

| # | 조치 | 검증 |
|---|------|------|
| G1 | `layoutStore` persist에 `merge` 추가 — `collapsedAgentGroups`가 배열이 아니면 초기값, 배열이면 유효한 그룹 키만 남김 | ST5 (null·문자열·`['owned','bogus',3]` → `[]`·`[]`·`['owned']`), Red 확인 후 Green |
| G2 | 테스트 추가 | AL10 (이름 공백 → 아바타 `?`) |
| G3 | 테스트 추가 | AL11 (`['subscribed']` 저장 + 구독 그룹 없음 → 다른 그룹 펼침 유지) |
| G4 | ChevronDown `strokeWidth` 2 → 1.75 | 코드 확인 |
| G5 | 유지 (스타일, 사용자 결정) | - |

재검증: `src/components/layout`·`src/store` 13 파일 79 테스트 통과, `type-check` 통과, 수정 파일 lint 0건.

**Act-1 후 Match Rate**: Functional 96 → 99 (G5만 남음) → Overall = 15 + 24.75 + 25 + 35 = **99.8%**

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2026-11-04 | Initial analysis (gap-detector 정적 분석 + 런타임 확인) |
| 0.2 | 2026-11-04 | Act-1: G1~G4 수정, 99.0% → 99.8% |
