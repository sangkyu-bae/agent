---
template: design
version: 1.2
feature: agent-subscription
date: 2026-05-04
author: 배상규
project: idt_front
version_project: 0.0.0
---

# agent-subscription Design Document

> **Summary**: 사이드바 에이전트 목록을 `MOCK_AGENTS` 하드코딩에서 `GET /api/v1/agents/my` 실제 API로 전환하고, 구독/해제/핀 mutation 훅을 연동한다.
>
> **Project**: idt_front
> **Version**: 0.0.0
> **Author**: 배상��
> **Date**: 2026-05-04
> **Status**: Draft
> **Planning Doc**: [agent-subscription.plan.md](../../01-plan/features/agent-subscription.plan.md)

### Pipeline References

| Phase | Document | Status |
|-------|----------|--------|
| Phase 4 | [API Spec](../../api/agnet-subscription.md) | ✅ |
| Phase 6 | UI Integration (this design) | 🔄 |

---

## 1. Overview

### 1.1 Design Goals

- 백엔드 응답(snake_case)을 **그대로 타입으로 수용** (camelCase 변환 없이 사용 — API 계약 충실)
- 에이전트 목록은 **TanStack Query 캐시**를 Single Source of Truth로 삼는다
- `AppSidebar`는 `source_type`별 그룹핑 + `is_pinned` 우선 정렬을 제공한다
- 기존 `AgentSummary` 타입은 유지하되, `MyAgent`에서 `AgentSummary`로의 변환 어댑터를 서비스 레이어에 둔다
- `selectedAgentId`가 API 응답에 없는 경우(삭제/해제) 첫 번째 에이전트로 자동 폴백

### 1.2 Design Principles

- **Adapter at Boundary**: snake_case → camelCase 변환은 서비스 레이어에서 종결. 훅/컴포넌트는 도메인 모델만 다룬다.
- **Backward Compatibility**: `AgentChatOutletContext.selectedAgent`의 기존 `AgentSummary` 타입을 유지하여 `ChatPage` 등 하류 컴포넌트 변경 최소화
- **Fail Gracefully**: API 실패 시 빈 목록 + 재시도 UI 표시 (앱 전체 크래시 방지)

---

## 2. Architecture

### 2.1 Component Diagram

```
┌──────────────────────────────────────────────────────────────┐
│ Presentation                                                  │
│   AgentChatLayout → AppSidebar (에이전트 목록)                │
│                   → ChatPage (selectedAgent 사용)             │
└──────┬──────────────────────────────────────────────▲────────┘
       │ useMyAgents() / useSubscribe/Unsubscribe/Pin │
       ▼                                              │
┌─────────────────────��───────────────────────────────��────────┐
│ Application Hooks (hooks/useAgent.ts)                        │
│   - useMyAgents(params?)          → query                    │
│   - useSubscribeAgent()           → mutation                 │
│   - useUnsubscribeAgent()         → mutation                 │
│   - useTogglePin()                → mutation                 │
│   - useForkAgent()                → mutation                 │
└──────┬──────────────────────────────────────────────▲────────┘
       │ agentSubscriptionService.*                    │
       ▼                                              │
┌───────────────────��──────────────────────────────────────────┐
│ Service Layer (services/agentSubscriptionService.ts)          │
│   - getMyAgents(params) → MyAgentsResponse                   │
│   - subscribe(agentId) → SubscriptionResponse                │
│   - unsubscribe(agentId) → void                              │
│   - updateSubscription(agentId, data) → SubscriptionResponse │
│   - forkAgent(agentId, data) → ForkAgentResponse             │
│   - toAgentSummary(agent: MyAgent) → AgentSummary  (adapter) ���
└──────┬──────────────────────────────────────────────▲────────┘
       │ authApiClient (Bearer token auto-inject)      │
       ▼                                              │
┌──────────────────���─────────────────────────���─────────────────┐
│ Backend API (idt — agent-subscription)                        │
│   GET  /api/v1/agents/my                                     │
│   POST /api/v1/agents/{id}/subscribe                         │
│   DELETE /api/v1/agents/{id}/subscribe                       │
│   PATCH  /api/v1/agents/{id}/subscribe                       │
│   POST /api/v1/agents/{id}/fork                              │
└──────────────────────────────────────────────────────────────┘
```

### 2.2 Data Flow

```
[AppSidebar 마운트]
  → useMyAgents() → GET /api/v1/agents/my
  → TanStack Query 캐시에 저장
  → agents[] 렌더링 (source_type 그룹핑)

[에이전트 선택]
  → layoutStore.selectAgent(agent_id)
  → AgentChatLayout outletContext.selectedAgent 갱신
  → ChatPage 헤더/빈 상태에 에이전트 정보 반영

[구독/해제/핀 액션]
  → mutation 호출 → API 요청
  → onSuccess: invalidateQueries(queryKeys.agent.my())
  → 목록 자동 갱신
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `useMyAgents` | `authApiClient`, `queryKeys.agent` | 인증 필수 에이전트 목록 조회 |
| `AgentChatLayout` | `useMyAgents`, `layoutStore` | 데이터 페칭 + 선택 상태 관리 |
| `AppSidebar` | `MyAgent[]` (props) | 에이전트 목록 렌더링 |
| `ChatPage` | `AgentChatOutletContext` | 선택된 에이전트 정보 소비 |

---

## 3. Data Model

### 3.1 API 응답 타입 (snake_case — 백엔드 계약)

```typescript
// src/types/agent.ts에 추가

export type AgentSourceType = 'owned' | 'subscribed' | 'forked';
export type AgentVisibility = 'private' | 'public';

/** GET /api/v1/agents/my → agents[] 각 항목 */
export interface MyAgent {
  agent_id: string;
  name: string;
  description: string;
  source_type: AgentSourceType;
  visibility: AgentVisibility;
  temperature: number;
  owner_user_id: string;
  forked_from: string | null;
  is_pinned: boolean;
  created_at: string;
}

/** GET /api/v1/agents/my 전체 응�� */
export interface MyAgentsResponse {
  agents: MyAgent[];
  total: number;
  page: number;
  size: number;
}

/** GET /api/v1/agents/my 쿼리 파라미터 */
export interface MyAgentsParams {
  filter?: 'all' | AgentSourceType;
  search?: string;
  page?: number;
  size?: number;
}

/** POST /api/v1/agents/{id}/subscribe 응답 */
export interface SubscriptionResponse {
  subscription_id: string;
  agent_id: string;
  agent_name: string;
  is_pinned: boolean;
  subscribed_at: string;
}

/** PATCH /api/v1/agents/{id}/subscribe 요청 */
export interface UpdateSubscriptionRequest {
  is_pinned: boolean;
}

/** POST /api/v1/agents/{id}/fork 요청 */
export interface ForkAgentRequest {
  name?: string;
}

/** POST /api/v1/agents/{id}/fork 응��� */
export interface ForkAgentResponse {
  agent_id: string;
  name: string;
  forked_from: string;
  forked_at: string;
  system_prompt: string;
  workers: Array<{
    name: string;
    tool_type: string;
    config: Record<string, unknown>;
  }>;
  visibility: AgentVisibility;
  temperature: number;
  llm_model_id: string;
}
```

### 3.2 어댑터: MyAgent → AgentSummary

기존 `AgentSummary` 인터페이스를 하류 컴포넌트(`ChatPage`, `ChatHeader`)가 사용하고 있으므로, 서비스 레이어에서 변환한다.

```typescript
// services/agentSubscriptionService.ts 내부
export const toAgentSummary = (agent: MyAgent): AgentSummary => ({
  id: agent.agent_id,
  name: agent.name,
  description: agent.description,
  category: agent.source_type,    // 'owned' | 'subscribed' | 'forked' → category로 매핑
  isDefault: false,
});
```

### 3.3 기존 타입 변경 사항

```typescript
// AgentChatOutletContext — selectedAgent 타입 유지 (변경 없음)
export interface AgentChatOutletContext {
  selectedAgent: AgentSummary | null;   // ← 유지
  activeSessionId: string | null;
  setActiveSessionId: (id: string) => void;
  handleNewChat: () => void;
  sessions: ChatSession[];
}
```

---

## 4. API Specification

### 4.1 Endpoint List

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/api/v1/agents/my` | 내 에이전트 통합 목록 | Required |
| POST | `/api/v1/agents/{agent_id}/subscribe` | 에이전트 구독 | Required |
| DELETE | `/api/v1/agents/{agent_id}/subscribe` | 구독 해제 | Required |
| PATCH | `/api/v1/agents/{agent_id}/subscribe` | 구독 설정 변경 (pin) | Required |
| POST | `/api/v1/agents/{agent_id}/fork` | 에이전트 포크 | Required |

### 4.2 API 엔드포인트 상수

```typescript
// src/constants/api.ts에 추가
  // Agent Subscription
  AGENT_MY: '/api/v1/agents/my',
  AGENT_SUBSCRIBE: (agentId: string) => `/api/v1/agents/${agentId}/subscribe`,
  AGENT_FORK: (agentId: string) => `/api/v1/agents/${agentId}/fork`,
  AGENT_FORK_STATS: (agentId: string) => `/api/v1/agents/${agentId}/forks`,
```

### 4.3 에러 처리 매핑

| API | Status | 에러 | UI 처리 |
|-----|--------|------|---------|
| GET /agents/my | 401 | 인증 만료 | authApiClient 인터셉터 → 토큰 갱신 또는 로그인 리다이렉트 |
| POST .../subscribe | 400 | 자기 에이전트 구독 불가 | toast 알림 |
| POST .../subscribe | 409 | 이미 구독 중 | toast 알림 (목록 갱신 불필요) |
| DELETE .../subscribe | 404 | 구독 없음 | 목록 갱신 (이미 해제됨) |
| POST .../fork | 403 | 접근 권한 없음 | toast 알림 |

---

## 5. UI/UX Design

### 5.1 AppSidebar 에이전트 섹션 레이아웃

```
┌──────────────────────────────┐
│ (a) Logo                      │
│ (b) 새 에이전트 버튼           │
│ (d) Navigation (고정 메뉴)     │
├──────────────────────────────┤ ← border-t
│ (e) 에이전트 섹션 (스크롤)      │
│                              │
│  ┌─ 📌 고정됨 (N) ──────────┐ │   ← is_pinned: true (source_type 무관)
│  │  [Agent A] subscribed    │ │
│  │  [Agent B] owned         │ │
│  └──────────────────────────┘ │
│                              │
│  ┌─ 🔧 내 에이전트 (N) ─────┐ │   ← source_type: 'owned', is_pinned: false
│  │  [Agent C]               │ │
│  │  [Agent D]               │ │
│  └──────────────���───────────┘ │
│                              │
│  ┌─ ⭐ 구독 (N) ────────────┐ │   ← source_type: 'subscribed', is_pinned: false
│  │  [Agent E]               │ │
│  └──────────────────────────┘ ��
│                              │
│  ┌─ 🔀 포크 (N) ────────────┐ │   ← source_type: 'forked', is_pinned: false
│  │  [Agent F]               │ │
│  └──────────────────────────┘ │
│                              │
├──────────────────────────────┤ ← border-t
│ (f) Bottom menu               │
│ (g) User profile + logout     │
└──────────────────────────────┘
```

### 5.2 에이전트 아이템 UI

```
┌──────────────────────────────────┐
│ 에이전트명                    📌  │  ← 핀 아이콘 (is_pinned 시 표시)
│ 설명 텍스트 (truncate)            │
└──────────────────────────────────┘
  - 선택: bg-white/[0.12] text-white
  - 비선택: text-white/45 hover:bg-white/[0.06]
  - 기존 스타일 패턴 유지
```

### 5.3 상태별 UI

| 상태 | UI |
|------|-----|
| **로딩** | 스켈레톤 3줄 (기존 Sidebar 로딩 패턴 재사용) |
| **에러** | 경고 박스 + "다시 시도" 버튼 (기존 패턴 재사용) |
| **빈 목록** | "등록된 에이전트가 없습니다" + "에이전트 만들기" CTA |
| **정상** | source_type 그룹핑 렌더링 |

### 5.4 User Flow

```
[앱 로드] → useMyAgents() 호출 → 목록 렌더링
  ├─ 에이전트 클릭 → selectAgent(agent_id) → ChatPage 전환
  ├─ 그룹 헤더의 숨기기/필터 버튼 → (v2 추후)
  └─ 빈 목록 → "에이전트 만들기" 클릭 → /agent-builder 이동
```

### 5.5 Component List

| Component | Location | Responsibility |
|-----------|----------|----------------|
| `AgentChatLayout` | `src/components/layout/AgentChatLayout.tsx` | `useMyAgents` 호출, 데이터를 AppSidebar에 전달 |
| `AppSidebar` | `src/components/layout/AppSidebar.tsx` | 에이전트 그룹핑 렌더링, 선택 이벤트 |
| `ChatPage` | `src/pages/ChatPage/index.tsx` | 변경 없음 (AgentSummary 타입 유지) |

---

## 6. Service Layer

### 6.1 새 파일: `src/services/agentSubscriptionService.ts`

기존 `agentService.ts`는 Agent 실행(run/status/stream) 관련이므로, 구독 관련은 **별도 서비스 파일**로 분리한다.

```typescript
import authApiClient from './api/authClient';
import { API_ENDPOINTS } from '@/constants/api';
import type {
  MyAgentsParams,
  MyAgentsResponse,
  SubscriptionResponse,
  UpdateSubscriptionRequest,
  ForkAgentRequest,
  ForkAgentResponse,
  MyAgent,
  AgentSummary,
} from '@/types/agent';

export const toAgentSummary = (agent: MyAgent): AgentSummary => ({
  id: agent.agent_id,
  name: agent.name,
  description: agent.description,
  category: agent.source_type,
  isDefault: false,
});

export const agentSubscriptionService = {
  getMyAgents: (params?: MyAgentsParams) =>
    authApiClient.get<MyAgentsResponse>(API_ENDPOINTS.AGENT_MY, { params }),

  subscribe: (agentId: string) =>
    authApiClient.post<SubscriptionResponse>(
      API_ENDPOINTS.AGENT_SUBSCRIBE(agentId),
    ),

  unsubscribe: (agentId: string) =>
    authApiClient.delete(API_ENDPOINTS.AGENT_SUBSCRIBE(agentId)),

  updateSubscription: (agentId: string, data: UpdateSubscriptionRequest) =>
    authApiClient.patch<SubscriptionResponse>(
      API_ENDPOINTS.AGENT_SUBSCRIBE(agentId),
      data,
    ),

  forkAgent: (agentId: string, data?: ForkAgentRequest) =>
    authApiClient.post<ForkAgentResponse>(
      API_ENDPOINTS.AGENT_FORK(agentId),
      data,
    ),
};
```

---

## 7. Query Keys & Hooks

### 7.1 Query Keys 추���

```typescript
// src/lib/queryKeys.ts — agent 섹션 확장
agent: {
  all: ['agent'] as const,
  run: (runId: string) =>
    [...queryKeys.agent.all, 'run', runId] as const,
  my: (params?: MyAgentsParams) =>
    [...queryKeys.agent.all, 'my', params] as const,
},
```

### 7.2 커스텀 훅: `src/hooks/useAgentSubscription.ts`

기존 `useAgent.ts`는 Agent 실행 훅이므로, 구독 훅은 **별도 파일**로 분리한다.

```typescript
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { agentSubscriptionService } from '@/services/agentSubscriptionService';
import { queryKeys } from '@/lib/queryKeys';
import type {
  MyAgentsParams,
  ForkAgentRequest,
} from '@/types/agent';

/** 내 에이전트 통합 목록 조회 */
export const useMyAgents = (params?: MyAgentsParams) =>
  useQuery({
    queryKey: queryKeys.agent.my(params),
    queryFn: () =>
      agentSubscriptionService.getMyAgents(params).then((r) => r.data),
  });

/** 에이전트 구독 */
export const useSubscribeAgent = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (agentId: string) =>
      agentSubscriptionService.subscribe(agentId).then((r) => r.data),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: queryKeys.agent.all }),
  });
};

/** 에이전트 구독 해제 */
export const useUnsubscribeAgent = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (agentId: string) =>
      agentSubscriptionService.unsubscribe(agentId),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: queryKeys.agent.all }),
  });
};

/** 구독 핀(즐겨찾기) 토글 */
export const useTogglePin = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ agentId, is_pinned }: { agentId: string; is_pinned: boolean }) =>
      agentSubscriptionService
        .updateSubscription(agentId, { is_pinned })
        .then((r) => r.data),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: queryKeys.agent.all }),
  });
};

/** �����전트 포크 */
export const useForkAgent = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ agentId, data }: { agentId: string; data?: ForkAgentRequest }) =>
      agentSubscriptionService.forkAgent(agentId, data).then((r) => r.data),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: queryKeys.agent.all }),
  });
};
```

---

## 8. Layout & Sidebar 변경

### 8.1 AgentChatLayout 변경 상세

```typescript
// 변경 전
import { MOCK_AGENTS } from '@/types/agent';
const selectedAgent = MOCK_AGENTS.find(a => a.id === selectedAgentId) ?? MOCK_AGENTS[0];
<AppSidebar agents={MOCK_AGENTS} ... />

// 변경 후
import { useMyAgents } from '@/hooks/useAgentSubscription';
import { toAgentSummary } from '@/services/agentSubscriptionService';

const { data: myAgentsData, isLoading: agentsLoading, isError: agentsError, refetch: refetchAgents } = useMyAgents();
const myAgents = myAgentsData?.agents ?? [];

// selectedAgentId가 API 응답에 없으면 첫 번째로 폴백
useEffect(() => {
  if (myAgents.length > 0 && !myAgents.find(a => a.agent_id === selectedAgentId)) {
    selectAgent(myAgents[0].agent_id);
  }
}, [myAgents, selectedAgentId, selectAgent]);

const selectedAgent: AgentSummary | null =
  myAgents.find(a => a.agent_id === selectedAgentId)
    ? toAgentSummary(myAgents.find(a => a.agent_id === selectedAgentId)!)
    : myAgents.length > 0
      ? toAgentSummary(myAgents[0])
      : null;

<AppSidebar
  agents={myAgents}
  selectedAgentId={selectedAgentId}
  onSelectAgent={selectAgent}
  isLoading={agentsLoading}
  isError={agentsError}
  onRetry={() => refetchAgents()}
/>
```

### 8.2 AppSidebar Props 변경

```typescript
// 변경 전
interface AppSidebarProps {
  agents: AgentSummary[];
  selectedAgentId: string | null;
  onSelectAgent: (id: string) => void;
}

// 변경 후
interface AppSidebarProps {
  agents: MyAgent[];
  selectedAgentId: string | null;
  onSelectAgent: (id: string) => void;
  isLoading?: boolean;
  isError?: boolean;
  onRetry?: () => void;
}
```

### 8.3 AppSidebar 그룹핑 로직

```typescript
// 에이전트 섹션 내부 그룹핑 유틸
const pinnedAgents = agents.filter(a => a.is_pinned);
const ownedAgents = agents.filter(a => a.source_type === 'owned' && !a.is_pinned);
const subscribedAgents = agents.filter(a => a.source_type === 'subscribed' && !a.is_pinned);
const forkedAgents = agents.filter(a => a.source_type === 'forked' && !a.is_pinned);

const groups = [
  { key: 'pinned', label: '고정됨', agents: pinnedAgents },
  { key: 'owned', label: '내 에이전트', agents: ownedAgents },
  { key: 'subscribed', label: '구독', agents: subscribedAgents },
  { key: 'forked', label: '��크', agents: forkedAgents },
].filter(g => g.agents.length > 0);
```

---

## 9. Store 변경

### 9.1 layoutStore 변경 없음

`layoutStore`의 `selectedAgentId` 기본값은 `'super-ai'`이지만, `AgentChatLayout`의 `useEffect`에서 API 데이터 기반으로 자동 폴백하므로 store 자체는 변경 불필요.

---

## 10. Test Plan

### 10.1 Test Scope

| Type | Target | Tool |
|------|--------|------|
| Unit Test | `useMyAgents`, `useSubscribeAgent` 등 훅 | Vitest + MSW |
| Unit Test | `toAgentSummary` 어댑터 | Vitest |
| Unit Test | AppSidebar 그룹핑 렌더링 | Vitest + RTL |
| Integration | AgentChatLayout → AppSidebar 데이터 플로우 | Vitest + RTL + MSW |

### 10.2 MSW 핸들러

```typescript
// src/__tests__/mocks/handlers.ts에 추가
import { http, HttpResponse } from 'msw';

const mockMyAgents = {
  agents: [
    {
      agent_id: 'agent-1',
      name: '사내 문서 RAG',
      description: '사내 문서 검색',
      source_type: 'owned',
      visibility: 'private',
      temperature: 0.7,
      owner_user_id: 'user-1',
      forked_from: null,
      is_pinned: false,
      created_at: '2026-05-01T00:00:00Z',
    },
    {
      agent_id: 'agent-2',
      name: '트레이딩 봇',
      description: '투자 분석',
      source_type: 'subscribed',
      visibility: 'public',
      temperature: 0.5,
      owner_user_id: 'user-2',
      forked_from: null,
      is_pinned: true,
      created_at: '2026-05-02T00:00:00Z',
    },
  ],
  total: 2,
  page: 1,
  size: 20,
};

// 핸들러
http.get('*/api/v1/agents/my', () => HttpResponse.json(mockMyAgents)),
http.post('*/api/v1/agents/:agentId/subscribe', () =>
  HttpResponse.json({ subscription_id: 'sub-1', agent_id: 'agent-1', agent_name: 'test', is_pinned: false, subscribed_at: new Date().toISOString() }, { status: 201 })
),
http.delete('*/api/v1/agents/:agentId/subscribe', () =>
  new HttpResponse(null, { status: 204 })
),
```

### 10.3 Key Test Cases

- [ ] `useMyAgents`: 정상 응답 시 `agents` 배열 반환
- [ ] `useMyAgents`: 에러 시 `isError: true`
- [ ] `useSubscribeAgent`: 성공 후 `agent.all` 캐시 무효화
- [ ] `useUnsubscribeAgent`: 204 응답 정상 처리
- [ ] `useTogglePin`: `is_pinned` 토글 후 캐시 무효화
- [ ] `toAgentSummary`: MyAgent → AgentSummary 올바른 매핑
- [ ] `AppSidebar`: 그룹핑 (pinned / owned / subscribed / forked) 정상 렌더링
- [ ] `AppSidebar`: 로딩 상태 스켈레톤 표시
- [ ] `AppSidebar`: 에러 상태 재시도 버튼 표시
- [ ] `AppSidebar`: 빈 목록 안내 메시지 표시
- [ ] `AgentChatLayout`: selectedAgentId 폴백 동작

---

## 11. Implementation Order

### 11.1 구현 순서 (의존성 기반)

```
1. [타입]      src/types/agent.ts          — MyAgent, Response 타입 추가
2. [상수]      src/constants/api.ts        — 엔드포인트 상수 추가
3. [서비스]    src/services/agentSubscriptionService.ts — 새 파일 생성
4. [쿼리키]    src/lib/queryKeys.ts        — agent.my() 키 추가
5. [훅]        src/hooks/useAgentSubscription.ts — 새 파일 생성
6. [레이아웃]  src/components/layout/AgentChatLayout.tsx — MOCK→API 전환
7. [사이드바]  src/components/layout/AppSidebar.tsx — 그룹핑 + 상태 UI
8. [정리]      src/types/agent.ts          — MOCK_AGENTS 제거
```

### 11.2 File-Level Checklist

| # | File | Action | Lines Est. |
|---|------|--------|:----------:|
| 1 | `src/types/agent.ts` | ADD types (MyAgent, MyAgentsResponse, etc.) | +50 |
| 2 | `src/constants/api.ts` | ADD 4 endpoints | +6 |
| 3 | `src/services/agentSubscriptionService.ts` | NEW file | +40 |
| 4 | `src/lib/queryKeys.ts` | ADD agent.my key | +3 |
| 5 | `src/hooks/useAgentSubscription.ts` | NEW file | +55 |
| 6 | `src/components/layout/AgentChatLayout.tsx` | MODIFY (MOCK→API) | ~30 changed |
| 7 | `src/components/layout/AppSidebar.tsx` | MODIFY (grouping + states) | ~60 changed |
| 8 | `src/types/agent.ts` | DELETE MOCK_AGENTS | -25 |
| T1 | `src/hooks/useAgentSubscription.test.ts` | NEW test file | +80 |
| T2 | `src/services/agentSubscriptionService.test.ts` | NEW test file | +40 |
| T3 | `src/__tests__/mocks/handlers.ts` | ADD agent handlers | +20 |

---

## 12. Security Considerations

- [x] 모든 API 호출은 `authApiClient` 사용 → Bearer 토큰 자동 주입
- [x] 401 응답 시 토큰 갱신 → 실패 시 로그인 페이지 리다이렉트 (기존 인터셉터)
- [x] `agent_id`는 UUID → URL injection 위험 낮음
- [ ] 에이전트 목록에 다른 유저의 private 에이전트가 노출되지 않는지 백엔드에서 검증 (프론트 scope 외)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-05-04 | Initial draft | 배상규 |
