# Wiki Navigation Design Document

> **Summary**: 위키 관리 메뉴 노출(S1) + 정제 폼 드롭다운화(S2) + 채팅 헤더 워크스페이스 링크(S3) 상세 설계 — 프론트엔드 전용, 백엔드 변경 0
>
> **Project**: sangplusbot (idt_front)
> **Version**: 1.0
> **Author**: 배상규
> **Date**: 2026-07-21
> **Status**: Draft
> **Plan Reference**: `docs/01-plan/features/wiki-navigation.plan.md`

---

## 1. Design Overview

세 변경 모두 **기존 완성 화면으로 가는 길을 잇는 additive 변경**이다. 신규 API·신규 타입·마이그레이션 없음.

| Scope | 대상 파일 | 변경 성격 |
|-------|----------|----------|
| S1 | `src/constants/adminNav.ts` | 배열 항목 1건 추가 (맨 뒤) |
| S2 | `src/pages/WikiPage/index.tsx` | 텍스트 입력 2개 → 드롭다운 2개 + 직접 입력 폴백 토글 |
| S3 | `src/components/layout/ChatHeader.tsx`, `src/pages/ChatPage/index.tsx` | optional prop 추가 + 배선 1줄 |

---

## 2. S1 — 관리자 메뉴 '위키 관리' 항목

### 2.1 adminNav.ts 추가 항목

`ADMIN_NAV_ITEMS` 배열 **마지막**(Skill 관리 다음)에 추가:

```ts
{
  label: '위키 관리',
  path: '/admin/wiki',
  // Heroicons outline 'book-open' — AppSidebar '지식베이스' 항목과 동일 계열
  icon: 'M12 6.042A8.967 8.967 0 0 0 6 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 0 1 6 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 0 1 6-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0 0 18 18a8.967 8.967 0 0 0-6 2.292m0-14.25v14.25',
  description: '에이전트 지식 정제 실행·위키 승인 거버넌스',
},
```

### 2.2 파급 확인 (추가 코드 불필요)

- **AdminLayout 사이드바**: `ADMIN_NAV_ITEMS.map` 렌더 → 자동 노출. active 판정은 `startsWith('/admin/wiki/')` 포함 기존 로직 그대로
- **TopNav '관리' 드롭다운**: `ADMIN_MENU.items = ADMIN_NAV_ITEMS` 공유 → 자동 노출
- **기존 테스트 영향**: `TopNav.test.tsx` T2는 개별 항목 존재 단언(개수 단언 아님) → 항목 추가로 깨지지 않음

---

## 3. S2 — WikiPage 정제 폼 드롭다운화

### 3.1 데이터 소스 (Plan 이월 결정 확정)

| 드롭다운 | 훅 (기존 재사용) | 옵션 매핑 |
|----------|-----------------|----------|
| 에이전트 | `useAgentList({ scope: 'all', size: 100 })` — `hooks/useAgentStore.ts`, `GET /api/v1/agents` | `agents.map(a => ({ value: a.agent_id, label: a.name }))` |
| 컬렉션 | `useCollections()` — `hooks/useRagToolConfig.ts`, `GET /api/v1/rag-tools/collections` | `collections.map(c => ({ value: c.name, label: c.display_name }))` |

**AGENT_MY 대신 AGENT_STORE_LIST(scope='all') 선택 근거**: `AGENT_MY`는 소유·구독·포크 에이전트만 반환하지만 관리자는 타인 에이전트의 위키도 관리 대상. `scope='all'`이 기존 API 중 가시 범위가 가장 넓음.

**알려진 한계**: visibility 규칙상 타 사용자의 `private` 에이전트는 스토어 목록에 미포함 → **3.3 직접 입력 폴백**으로 보완 (기존 수동 입력 능력 보존).

### 3.2 컴포넌트 구조 변경

```tsx
// WikiPage/index.tsx — 기존 state 유지 (agentId, collectionName, status)
const [manualInput, setManualInput] = useState(false);          // 신규
const agentList = useAgentList({ scope: 'all', size: 100 });    // 신규
const collections = useCollections();                            // 신규

// 폼 영역:
// manualInput=false (기본) → Dropdown 2개
//   <Dropdown value={agentId} onChange={setAgentId} options={agentOptions}
//             searchable placeholder="에이전트 선택" isLoading={agentList.isLoading}
//             emptyText="에이전트가 없습니다" ariaLabel="에이전트 선택" />
//   <Dropdown value={collectionName} onChange={setCollectionName} options={collectionOptions}
//             searchable placeholder="컬렉션 선택" isLoading={collections.isLoading} ... />
// manualInput=true → 기존 <input> 2개 그대로 렌더
// 토글: "직접 입력" 텍스트 버튼 (폼 우측) — 전환 시 값은 유지 (state 공유)
```

- `canDistill`·`handleDistill`·distill 페이로드(`{agent_id, collection_name}`) **불변** — 입력 UI만 교체
- 목록 API 에러 시: 폼 하단 단일 안내 배너("목록을 불러오지 못했습니다 · 직접 입력으로 전환") → 관리 기능이 목록 API 장애에 종속되지 않음 <!-- Gap G1 정정: 자리별 에러+재시도 → 단일 배너로 실태 반영 -->

- 하단 빈 상태 문구 변경: "에이전트 ID를 입력하면…" → "에이전트를 선택하면 위키 목록이 표시됩니다"
- `WikiArticleTable agentId={agentId.trim()}` 연동은 그대로 → 드롭다운 선택 즉시 목록 조회되는 부수 개선

### 3.3 직접 입력 폴백 (기존 능력 보존)

- 토글 on 시 기존 텍스트 입력 2개를 그대로 노출 (컴포넌트 제거가 아니라 조건부 렌더)
- 목적: 타 사용자 private 에이전트 등 목록에 없는 대상 정제 능력 유지 — 회귀 방지
- 기본값 off (드롭다운 우선)

### 3.4 size=100 제한

스토어 목록은 페이지네이션 API. 1페이지 100건으로 조회하며 검색은 Dropdown 내장 `searchable` 필터로 처리. 에이전트 100개 초과 시나리오는 현 운영 규모에서 미해당 — 초과 시 직접 입력 폴백으로 커버 (한계 명시).

---

## 4. S3 — ChatHeader 워크스페이스 링크

### 4.1 ChatHeader props 확장 (additive)

```tsx
interface ChatHeaderProps {
  title?: string;
  messageCount?: number;
  /** wiki-navigation S3: 사용자 에이전트 선택 시에만 전달. 없으면 링크 미노출 */
  agentId?: string | null;
}
```

- `agentId`가 truthy일 때만 우측 버튼 그룹 **맨 앞**에 링크 렌더:

```tsx
{agentId && (
  <Link
    to={`/agents/${agentId}/workspace`}
    title="에이전트 워크스페이스"
    className="flex h-8 w-8 items-center justify-center rounded-lg text-zinc-400 transition-all hover:bg-zinc-100 hover:text-zinc-600"
  >
    {/* Heroicons outline 'folder-open' */}
  </Link>
)}
```

- 기존 호출부는 무수정 시 동작 동일 (prop optional) — 기존 렌더 테스트 무영향
- `react-router-dom`의 `Link` 사용 → ChatPage는 이미 Router 하위이므로 문제 없음

### 4.2 ChatPage 배선

```tsx
<ChatHeader
  title={selectedAgent?.name ?? 'SUPER AI Agent'}
  messageCount={messages.length}
  agentId={selectedAgent && selectedAgent.id !== 'super' ? selectedAgent.id : undefined}
/>
```

- SUPER 판정은 ChatPage 스트리밍 분기(`index.tsx:286`)와 **동일 조건** 재사용 → 판정 기준 이원화 방지

---

## 5. Test Plan (TDD — 테스트 먼저)

공통: Vitest `--pool=threads`, MSW per-file `server.listen/resetHandlers/close` 3종 훅 직접 선언.

| ID | 파일 | 시나리오 |
|----|------|---------|
| T1 | `TopNav.test.tsx` (확장) | 관리자 드롭다운에 '위키 관리' 노출 (이동은 adminNav 단일 소스 + 기존 라우팅 로직 신뢰) |
| T2 | `AppSidebar.test.tsx` 또는 AdminLayout 신규 | (선택) 사이드바 '위키 관리' 노출 — TopNav와 단일 소스이므로 T1로 갈음 가능 |
| T3 | `WikiPage.test.tsx` (확장) | 에이전트·컬렉션 드롭다운 선택 → 정제 실행 → MSW로 distill 요청 바디 `{agent_id, collection_name}` 검증 |
| T4 | `WikiPage.test.tsx` | 드롭다운 선택 전 정제 버튼 disabled, 선택 후 enabled |
| T5 | `WikiPage.test.tsx` | '직접 입력' 토글 → 텍스트 입력 노출, 수동 입력값으로 정제 가능 (기존 시나리오 보존) |
| T6 | `ChatHeader.test.tsx` (신규) | `agentId` 제공 시 링크 `href="/agents/{id}/workspace"` 존재 (MemoryRouter 래핑) |
| T7 | `ChatHeader.test.tsx` | `agentId` 미제공 시 워크스페이스 링크 부재 |

MSW 핸들러: `AGENT_STORE_LIST`·`RAG_TOOL_COLLECTIONS`는 `__tests__/mocks/handlers.ts` 기존 핸들러 유무 확인 후 재사용/추가.

기존 회귀 기준: 사전 실패 8건(collection 7 + ChatPage 1)은 신규 회귀로 오인하지 않음.

---

## 6. Implementation Order

```
1. [S1] TopNav 테스트 확장 (T1, Red) → adminNav.ts 항목 추가 (Green)
2. [S2] WikiPage 테스트 (T3~T5, Red) → 드롭다운 + 폴백 토글 구현 (Green)
3. [S3] ChatHeader 테스트 (T6~T7, Red) → prop + Link 구현, ChatPage 배선 (Green)
4. 전체 프론트 테스트 회귀 확인 (--pool=threads)
```

---

## 7. 영향 범위 / 주의사항

- 백엔드·스키마·마이그레이션 변경 없음. API 계약 동기화 대상 없음
- `Dropdown` 공용 컴포넌트는 무수정 재사용 (controlled 전용, `isLoading`/`emptyText`/`searchable` 기존 prop으로 충족)
- `adminNav.ts` 항목 추가는 사이드바·TopNav 양쪽에 동시 반영되므로 별도 컴포넌트 수정 금지 (단일 소스 관례 유지)
- WikiPage의 `agentId` state는 폼과 목록 테이블이 공유하므로 드롭다운 전환 시에도 state 이름·타입(string) 유지

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-07-21 | Initial draft — 데이터 소스 확정(useAgentList scope=all + useCollections), 직접 입력 폴백 설계 | 배상규 |
