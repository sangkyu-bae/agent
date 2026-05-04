# Agent Store — Design Document

> Plan 참조: `docs/01-plan/features/agent-store.plan.md`

## 1. 파일 구조

```
src/
├── types/agentStore.ts                          # 타입 정의
├── constants/api.ts                             # (수정) 엔드포인트 추가
├── services/agentStoreService.ts                # API 호출 레이어
├── lib/queryKeys.ts                             # (수정) 쿼리 키 추가
├── hooks/useAgentStore.ts                       # TanStack Query 훅
├── pages/AgentStorePage/index.tsx                # 메인 페이지
├── components/agent-store/
│   ├── AgentStoreCard.tsx                       # 에이전트 카드
│   ├── AgentDetailModal.tsx                     # 상세 팝업 카드뷰
│   ├── PublishAgentModal.tsx                    # 내 에이전트 등록 모달
│   └── AgentStoreTab.tsx                        # 탭 네비게이션
├── components/layout/TopNav.tsx                 # (수정) 메뉴 항목 추가
└── App.tsx                                      # (수정) 라우트 추가
```

---

## 2. 타입 정의 — `src/types/agentStore.ts`

```typescript
// ── 에이전트 목록 (GET /api/v1/agents) ──────────────────

export type AgentScope = 'all' | 'public' | 'department' | 'mine';

export interface AgentListParams {
  scope: AgentScope;
  search?: string;
  page?: number;
  size?: number;
}

export interface StoreAgentSummary {
  agent_id: string;
  name: string;
  description: string;
  visibility: 'private' | 'department' | 'public';
  department_name: string | null;
  owner_user_id: string;
  owner_email: string | null;
  temperature: number;
  can_edit: boolean;
  can_delete: boolean;
  created_at: string;
}

export interface AgentListResponse {
  agents: StoreAgentSummary[];
  total: number;
  page: number;
  size: number;
}

// ── 에이전트 상세 (GET /api/v1/agents/{id}) ─────────────

export interface WorkerInfo {
  tool_id: string;
  worker_id: string;
  description: string;
  sort_order: number;
  tool_config: Record<string, unknown> | null;
}

export interface AgentDetail {
  agent_id: string;
  name: string;
  description: string;
  system_prompt: string;
  tool_ids: string[];
  workers: WorkerInfo[];
  flow_hint: string;
  llm_model_id: string;
  status: string;
  visibility: 'private' | 'department' | 'public';
  department_id: string | null;
  department_name: string | null;
  temperature: number;
  owner_user_id: string;
  can_edit: boolean;
  can_delete: boolean;
  created_at: string;
  updated_at: string;
}

// ── 구독 ────────────────────────────────────────────────

export interface SubscribeResponse {
  subscription_id: string;
  agent_id: string;
  agent_name: string;
  is_pinned: boolean;
  subscribed_at: string;
}

export interface UpdateSubscriptionRequest {
  is_pinned: boolean;
}

// ── 포크 ────────────────────────────────────────────────

export interface ForkAgentRequest {
  name?: string;
}

export interface ForkAgentResponse {
  agent_id: string;
  name: string;
  forked_from: string;
  forked_at: string;
  system_prompt: string;
  workers: WorkerInfo[];
  visibility: string;
  temperature: number;
  llm_model_id: string;
}

// ── 내 에이전트 (GET /api/v1/agents/my) ──────────────────

export type MyAgentFilter = 'all' | 'owned' | 'subscribed' | 'forked';

export interface MyAgentListParams {
  filter: MyAgentFilter;
  search?: string;
  page?: number;
  size?: number;
}

export interface MyAgentSummary {
  agent_id: string;
  name: string;
  description: string;
  source_type: 'owned' | 'subscribed' | 'forked';
  visibility: 'private' | 'department' | 'public';
  temperature: number;
  owner_user_id: string;
  forked_from: string | null;
  is_pinned: boolean;
  created_at: string;
}

export interface MyAgentListResponse {
  agents: MyAgentSummary[];
  total: number;
  page: number;
  size: number;
}

// ── 포크/구독 통계 ───────────────────────────────────────

export interface ForkStatsResponse {
  agent_id: string;
  fork_count: number;
  subscriber_count: number;
}

// ── 에이전트 공개 등록 (PATCH visibility) ────────────────

export interface PublishAgentRequest {
  visibility: 'public' | 'department';
  department_id?: string;
}
```

---

## 3. API 엔드포인트 — `src/constants/api.ts` (추가분)

```typescript
// Agent Store
AGENT_STORE_LIST: '/api/v1/agents',
AGENT_STORE_DETAIL: (agentId: string) => `/api/v1/agents/${agentId}`,
AGENT_STORE_SUBSCRIBE: (agentId: string) => `/api/v1/agents/${agentId}/subscribe`,
AGENT_STORE_FORK: (agentId: string) => `/api/v1/agents/${agentId}/fork`,
AGENT_STORE_MY: '/api/v1/agents/my',
AGENT_STORE_FORK_STATS: (agentId: string) => `/api/v1/agents/${agentId}/forks`,
```

---

## 4. 서비스 — `src/services/agentStoreService.ts`

```typescript
import authApiClient from './api/authClient';
import { API_ENDPOINTS } from '@/constants/api';
import type {
  AgentListParams,
  AgentListResponse,
  AgentDetail,
  SubscribeResponse,
  UpdateSubscriptionRequest,
  ForkAgentRequest,
  ForkAgentResponse,
  MyAgentListParams,
  MyAgentListResponse,
  ForkStatsResponse,
  PublishAgentRequest,
} from '@/types/agentStore';

export const agentStoreService = {
  /** 에이전트 목록 (scope 필터) */
  getAgents: (params: AgentListParams) =>
    authApiClient.get<AgentListResponse>(API_ENDPOINTS.AGENT_STORE_LIST, { params }),

  /** 에이전트 상세 */
  getAgent: (agentId: string) =>
    authApiClient.get<AgentDetail>(API_ENDPOINTS.AGENT_STORE_DETAIL(agentId)),

  /** 구독 */
  subscribe: (agentId: string) =>
    authApiClient.post<SubscribeResponse>(API_ENDPOINTS.AGENT_STORE_SUBSCRIBE(agentId)),

  /** 구독 해제 */
  unsubscribe: (agentId: string) =>
    authApiClient.delete(API_ENDPOINTS.AGENT_STORE_SUBSCRIBE(agentId)),

  /** 구독 설정 변경 (pin) */
  updateSubscription: (agentId: string, body: UpdateSubscriptionRequest) =>
    authApiClient.patch<SubscribeResponse>(API_ENDPOINTS.AGENT_STORE_SUBSCRIBE(agentId), body),

  /** 포크 */
  fork: (agentId: string, body?: ForkAgentRequest) =>
    authApiClient.post<ForkAgentResponse>(API_ENDPOINTS.AGENT_STORE_FORK(agentId), body ?? {}),

  /** 내 에이전트 목록 */
  getMyAgents: (params: MyAgentListParams) =>
    authApiClient.get<MyAgentListResponse>(API_ENDPOINTS.AGENT_STORE_MY, { params }),

  /** 포크/구독 통계 */
  getForkStats: (agentId: string) =>
    authApiClient.get<ForkStatsResponse>(API_ENDPOINTS.AGENT_STORE_FORK_STATS(agentId)),

  /** 에이전트 공개 등록 (visibility 변경) */
  publishAgent: (agentId: string, body: PublishAgentRequest) =>
    authApiClient.patch(API_ENDPOINTS.AGENT_STORE_DETAIL(agentId), body),
};
```

---

## 5. 쿼리 키 — `src/lib/queryKeys.ts` (추가분)

```typescript
agentStore: {
  all: ['agentStore'] as const,
  list: (params: import('@/types/agentStore').AgentListParams) =>
    [...queryKeys.agentStore.all, 'list', params] as const,
  detail: (agentId: string) =>
    [...queryKeys.agentStore.all, 'detail', agentId] as const,
  my: (params: import('@/types/agentStore').MyAgentListParams) =>
    [...queryKeys.agentStore.all, 'my', params] as const,
  forkStats: (agentId: string) =>
    [...queryKeys.agentStore.all, 'forkStats', agentId] as const,
},
```

---

## 6. TanStack Query 훅 — `src/hooks/useAgentStore.ts`

```typescript
import { useQuery, useMutation } from '@tanstack/react-query';
import { agentStoreService } from '@/services/agentStoreService';
import { queryKeys } from '@/lib/queryKeys';
import { queryClient } from '@/lib/queryClient';
import type {
  AgentListParams,
  AgentListResponse,
  AgentDetail,
  SubscribeResponse,
  ForkAgentRequest,
  ForkAgentResponse,
  MyAgentListParams,
  MyAgentListResponse,
  ForkStatsResponse,
  PublishAgentRequest,
} from '@/types/agentStore';

/** 에이전트 목록 (scope 기반) */
export const useAgentList = (params: AgentListParams) =>
  useQuery<AgentListResponse>({
    queryKey: queryKeys.agentStore.list(params),
    queryFn: () => agentStoreService.getAgents(params).then((r) => r.data),
  });

/** 에이전트 상세 */
export const useAgentDetail = (agentId: string | null) =>
  useQuery<AgentDetail>({
    queryKey: queryKeys.agentStore.detail(agentId ?? ''),
    queryFn: () => agentStoreService.getAgent(agentId!).then((r) => r.data),
    enabled: !!agentId,
  });

/** 내 에이전트 목록 */
export const useMyAgents = (params: MyAgentListParams) =>
  useQuery<MyAgentListResponse>({
    queryKey: queryKeys.agentStore.my(params),
    queryFn: () => agentStoreService.getMyAgents(params).then((r) => r.data),
  });

/** 구독 */
export const useSubscribeAgent = () =>
  useMutation<SubscribeResponse, Error, string>({
    mutationFn: (agentId) =>
      agentStoreService.subscribe(agentId).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.agentStore.all });
    },
  });

/** 구독 해제 */
export const useUnsubscribeAgent = () =>
  useMutation<void, Error, string>({
    mutationFn: (agentId) =>
      agentStoreService.unsubscribe(agentId).then(() => undefined),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.agentStore.all });
    },
  });

/** 구독 설정 변경 (pin) */
export const useUpdateSubscription = () =>
  useMutation<SubscribeResponse, Error, { agentId: string; isPinned: boolean }>({
    mutationFn: ({ agentId, isPinned }) =>
      agentStoreService.updateSubscription(agentId, { is_pinned: isPinned }).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.agentStore.all });
    },
  });

/** 포크 */
export const useForkAgent = () =>
  useMutation<ForkAgentResponse, Error, { agentId: string; name?: string }>({
    mutationFn: ({ agentId, name }) =>
      agentStoreService.fork(agentId, name ? { name } : undefined).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.agentStore.all });
    },
  });

/** 에이전트 공개 등록 */
export const usePublishAgent = () =>
  useMutation<void, Error, { agentId: string; body: PublishAgentRequest }>({
    mutationFn: ({ agentId, body }) =>
      agentStoreService.publishAgent(agentId, body).then(() => undefined),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.agentStore.all });
    },
  });

/** 포크/구독 통계 */
export const useForkStats = (agentId: string | null) =>
  useQuery<ForkStatsResponse>({
    queryKey: queryKeys.agentStore.forkStats(agentId ?? ''),
    queryFn: () => agentStoreService.getForkStats(agentId!).then((r) => r.data),
    enabled: !!agentId,
  });
```

---

## 7. 컴포넌트 설계

### 7-1. AgentStoreTab

```
Props:
  activeTab: 'public' | 'department' | 'my'
  onTabChange: (tab) => void

UI:
  ┌──────────────────────────────────────┐
  │  [전체 공개]  [부서별]  [내 에이전트]  │
  └──────────────────────────────────────┘

  - 활성 탭: border-b-2 border-violet-600 text-violet-600
  - 비활성 탭: text-zinc-500 hover:text-zinc-700
```

### 7-2. AgentStoreCard

```
Props:
  agent: StoreAgentSummary
  onClick: (agentId: string) => void
  onSubscribe: (agentId: string) => void
  onFork: (agentId: string) => void
  isSubscribing?: boolean
  isForking?: boolean

UI:
  ┌──────────────────────────────────────┐
  │ [아바타 2글자] 에이전트 이름           │
  │                @owner · visibility    │
  │                                      │
  │ 설명 (line-clamp-2)                  │
  │                                      │
  │ [부서명 뱃지]  temp 0.7              │
  │                                      │
  │ ── border-t ──                       │
  │ [구독] [포크]                        │
  └──────────────────────────────────────┘

  - 카드 전체 클릭 → onClick (상세 팝업)
  - 구독/포크 버튼 → stopPropagation + 각각 콜백
  - 그라디언트 아바타 (agent_id 기반 색상 선택)
  - hover:-translate-y-0.5 hover:shadow-lg 트랜지션
```

### 7-3. AgentDetailModal

```
Props:
  agentId: string | null
  isOpen: boolean
  onClose: () => void

내부 상태:
  useAgentDetail(agentId) → 상세 데이터
  useForkStats(agentId) → 통계 (can_edit일 때만)
  useSubscribeAgent() → 구독 뮤테이션
  useForkAgent() → 포크 뮤테이션
  forkName: string → 포크 시 이름 입력 (선택)
  showForkInput: boolean → 포크 이름 입력 토글

UI (모달 오버레이):
  ┌─────────────────────────────────────────┐
  │                              [X 닫기]   │
  │                                         │
  │  [아바타]  에이전트 이름                  │
  │            @소유자 · visibility           │
  │            부서: OO부서                   │
  │                                         │
  │  ── 설명 ──                              │
  │  에이전트 설명 전문                       │
  │                                         │
  │  ── 시스템 프롬프트 ──                   │
  │  (max-h-48 overflow-y-auto)             │
  │  프롬프트 전문                           │
  │                                         │
  │  ── 연결된 도구 ──                       │
  │  [도구1] [도구2] [도구3]                 │
  │                                         │
  │  ── 설정 ──                              │
  │  모델: llm_model_id  Temperature: 0.7   │
  │                                         │
  │  ── 통계 (소유자만) ──                   │
  │  구독 12명 · 포크 5회                    │
  │                                         │
  │  [구독하기]       [포크하기]              │
  └─────────────────────────────────────────┘

  - 배경: fixed inset-0 bg-black/50
  - 모달: max-w-2xl mx-auto bg-white rounded-2xl
  - 스켈레톤 로딩 (isLoading 시)
  - 에러: 404 → "에이전트를 찾을 수 없습니다"
  - 본인 에이전트: 구독/포크 버튼 비노출, "내 에이전트입니다" 표시
```

### 7-4. PublishAgentModal

```
Props:
  isOpen: boolean
  onClose: () => void

내부 상태:
  useMyAgents({ filter: 'owned' }) → 내 private 에이전트 목록
  usePublishAgent() → visibility 변경 뮤테이션
  selectedAgentId: string | null
  visibility: 'public' | 'department'
  departmentId: string (department 선택 시)

UI (모달):
  ┌─────────────────────────────────────────┐
  │  내 에이전트 스토어 등록         [X]     │
  │                                         │
  │  ── 등록할 에이전트 선택 ──              │
  │  (private 에이전트만 표시)               │
  │  ○ 문서 분석가                          │
  │  ○ 코드 리뷰어                          │
  │                                         │
  │  ── 공개 범위 ──                         │
  │  ○ 전체 공개 (public)                   │
  │  ○ 부서 공개 (department)               │
  │     └─ 부서 선택: [드롭다운]            │
  │                                         │
  │  [취소]  [등록하기]                      │
  └─────────────────────────────────────────┘

  - private 에이전트만 필터: agents.filter(a => a.visibility === 'private')
  - department 선택 시 부서 목록 필요 → GET /api/v1/departments 활용
  - 등록 후 queryClient.invalidateQueries
```

### 7-5. AgentStorePage

```
내부 상태:
  activeTab: 'public' | 'department' | 'my' (기본: 'public')
  search: string (디바운스 300ms)
  page: number (기본: 1)
  myFilter: MyAgentFilter (내 에이전트 탭 서브필터, 기본: 'all')
  selectedAgentId: string | null (상세 팝업용)
  showPublishModal: boolean

데이터 흐름:
  activeTab === 'public'     → useAgentList({ scope: 'public', search, page, size: 20 })
  activeTab === 'department' → useAgentList({ scope: 'department', search, page, size: 20 })
  activeTab === 'my'         → useMyAgents({ filter: myFilter, search, page, size: 20 })

레이아웃 (패턴 A: 고정 헤더 + 스크롤 바디):
  ┌─────────────────────────────────────────────────┐
  │ 헤더 (shrink-0, border-b)                       │
  │  [아이콘] 에이전트 스토어 / Agent Store           │
  │  [검색바]                          [등록 버튼]   │
  ├─────────────────────────────────────────────────┤
  │ 탭 (shrink-0, border-b)                         │
  │  [전체 공개] [부서별] [내 에이전트]               │
  │  (내 에이전트 탭: 서브필터 [전체|소유|구독|포크])  │
  ├─────────────────────────────────────────────────┤
  │ 스크롤 영역 (flex-1, overflow-y: auto)           │
  │  max-w-7xl mx-auto px-4 py-8                    │
  │                                                 │
  │  카드 그리드 (grid-cols-3 lg / 2 md / 1 sm)     │
  │                                                 │
  │  페이지네이션 (하단)                             │
  │  [ < ] 1 / 3 [ > ]                              │
  └─────────────────────────────────────────────────┘

  + AgentDetailModal (selectedAgentId)
  + PublishAgentModal (showPublishModal)
```

---

## 8. 라우팅 — `src/App.tsx` 변경

```tsx
// ProtectedRoute 내부, AgentChatLayout 내부에 추가
<Route path="agent-store" element={<AgentStorePage />} />
```

---

## 9. 네비게이션 — `src/components/layout/TopNav.tsx` 변경

`NAV_MENUS`의 "에이전트" 그룹에 항목 추가:

```typescript
{
  label: '에이전트 스토어',
  path: '/agent-store',
  icon: '...', // Store/Shop 아이콘 SVG path
  description: '공개 에이전트 탐색 및 구독',
}
```

---

## 10. 에러 처리 매핑

| API 상태 코드 | 상황 | UI 처리 |
|-------------|------|---------|
| 400 | 자신의 에이전트 구독/포크 시도 | toast: "자신의 에이전트는 구독/포크할 수 없습니다" |
| 403 | 접근 권한 없음 | toast: "접근 권한이 없습니다" |
| 404 | 에이전트 없음 / 구독 없음 | toast: "에이전트를 찾을 수 없습니다" |
| 409 | 이미 구독 중 | toast: "이미 구독 중인 에이전트입니다" |

에러 메시지는 `ApiError.message` 그대로 표시 (백엔드에서 한글 메시지 제공).

---

## 11. 상태별 UI

### 로딩 상태
- 카드 스켈레톤: `animate-pulse` 3x2 그리드
- 모달 스켈레톤: 섹션별 `animate-pulse` 블록

### 빈 상태

| 탭 | 메시지 | 액션 |
|----|--------|------|
| 전체 공개 | "공개된 에이전트가 없습니다" | "에이전트 만들기" 링크 → /agent-builder |
| 부서별 | "부서에 공개된 에이전트가 없습니다" | — |
| 내 에이전트 | "에이전트가 없습니다" | "에이전트 만들기" 링크 → /agent-builder |

### 검색 결과 없음
- "'{검색어}'에 대한 결과가 없습니다"

---

## 12. 구현 순서 (TDD)

```
Step 1: 타입 + 상수 + 서비스 + 쿼리키
  ├── src/types/agentStore.ts
  ├── src/constants/api.ts (엔드포인트 추가)
  ├── src/services/agentStoreService.ts
  └── src/lib/queryKeys.ts (agentStore 키 추가)

Step 2: TanStack Query 훅 + 테스트
  ├── src/hooks/useAgentStore.ts
  └── src/hooks/useAgentStore.test.ts

Step 3: 컴포넌트 + 테스트
  ├── AgentStoreTab.tsx
  ├── AgentStoreCard.tsx + AgentStoreCard.test.tsx
  ├── AgentDetailModal.tsx + AgentDetailModal.test.tsx
  └── PublishAgentModal.tsx

Step 4: 페이지 + 라우팅 + 네비게이션
  ├── AgentStorePage/index.tsx
  ├── App.tsx (라우트 추가)
  └── TopNav.tsx (메뉴 추가)

Step 5: MSW 핸들러 + 통합 테스트
  └── src/__tests__/mocks/handlers.ts (agent-store 핸들러)
```

---

## 13. 비기능 요구사항

| 항목 | 설계 |
|------|------|
| 인증 | `authApiClient` 사용 (Bearer 토큰 자동 주입) |
| 페이지네이션 | 서버 사이드, page/size 파라미터 |
| 검색 디바운스 | 300ms `setTimeout` (useRef + cleanup) |
| 반응형 | `grid-cols-1 md:grid-cols-2 lg:grid-cols-3` |
| 접근성 | 모달 `role="dialog"`, 카드 `role="article"`, 키보드 ESC 닫기 |
| 캐시 | TanStack Query 기본 staleTime 1분, 뮤테이션 성공 시 invalidate |
