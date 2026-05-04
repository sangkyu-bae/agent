# agent-subscription Planning Document

> **Summary**: 사이드바 에이전트 목록을 MOCK_AGENTS에서 실제 API(`GET /api/v1/agents/my`)로 전환하고, 구독/해제/핀/포크 기능 연동
>
> **Project**: idt_front (React 19 + TypeScript)
> **Author**: 배상규
> **Date**: 2026-05-04
> **Status**: Draft

---

## 1. Overview

### 1.1 Purpose

현재 사이드바(`AppSidebar`)는 `MOCK_AGENTS` 하드코딩 데이터를 사용한다.
유저별 에이전트 목록(소유/구독/포크)을 실제 백엔드 API로부터 받아와 렌더링해야 한다.

### 1.2 Background

- 백엔드에 에이전트 구독/포크 API가 이미 구현되어 있음 (`/api/v1/agents/*`)
- 프론트엔드는 MOCK 데이터만 사용 중 → 실제 서버 연동 필요
- 사이드바에서 유저가 자신의 에이전트를 선택하여 대화해야 하는 핵심 UX 흐름

### 1.3 Related Documents

- API 스펙: `docs/api/agnet-subscription.md`
- 에이전트 빌더: `src/claude/task/task-agent-builder.md`

---

## 2. Scope

### 2.1 In Scope

- [ ] **타입 정의**: API 응답에 맞는 `MyAgent`, `MyAgentsResponse` 타입 추가
- [ ] **API 엔드포인트 상수**: 6개 엔드포인트 `constants/api.ts`에 추가
- [ ] **서비스 레이어**: `agentService.ts`에 구독 관련 API 호출 메서드 추가
- [ ] **Query Keys**: `queryKeys.ts`에 에이전트 구독 도메인 키 추가
- [ ] **커스텀 훅**: `useMyAgents` (목록 조회) + mutation 훅 (구독/해제/핀)
- [ ] **AgentChatLayout**: `MOCK_AGENTS` → `useMyAgents()` 훅 데이터로 전환
- [ ] **AppSidebar**: `source_type` 기반 그룹핑 + 로딩/에러 상태 처리
- [ ] **layoutStore**: 동적 에이전트 ID 선택 로직 개선 (첫 번째 에이전트 자동 선택)

### 2.2 Out of Scope

- 에이전트 빌더 페이지 (별도 task: AGENT-001)
- 에이전트 상세 설정 편집 UI
- 포크 통계 페이지 (`GET /api/v1/agents/{agent_id}/forks`)
- 에이전트 검색 UI (추후 검색바 추가 시)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | 사이드바에 유저의 에이전트 통합 목록 표시 (`GET /api/v1/agents/my`) | High | Pending |
| FR-02 | `source_type`별 그룹핑 (owned / subscribed / forked) | High | Pending |
| FR-03 | 에이전트 선택 시 해당 에이전트로 대화 세션 연결 | High | Pending |
| FR-04 | 에이전트 구독 (`POST .../subscribe`) | Medium | Pending |
| FR-05 | 에이전트 구독 해제 (`DELETE .../subscribe`) | Medium | Pending |
| FR-06 | 에이전트 핀(즐겨찾기) 토글 (`PATCH .../subscribe`) | Medium | Pending |
| FR-07 | 에이전트 포크 (`POST .../fork`) | Low | Pending |
| FR-08 | 로딩/에러/빈 상태 UI 처리 | High | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Performance | 에이전트 목록 로딩 < 500ms | Network waterfall |
| UX | 로딩 중 스켈레톤 UI 표시 | 수동 확인 |
| 에러 복구 | API 실패 시 재시도 버튼 제공 | 수동 확인 |

---

## 4. Implementation Plan

### 4.1 변경 파일 목록

| 순서 | 파일 | 작업 내용 |
|------|------|-----------|
| 1 | `src/types/agent.ts` | `MyAgent`, `MyAgentsResponse`, `AgentSourceType` 등 타입 추가 |
| 2 | `src/constants/api.ts` | `AGENT_MY`, `AGENT_SUBSCRIBE`, `AGENT_FORK`, `AGENT_FORK_STATS` 엔드포인트 추가 |
| 3 | `src/services/agentService.ts` | `getMyAgents`, `subscribe`, `unsubscribe`, `updateSubscription`, `forkAgent` 메서드 추가 (authApiClient 사용) |
| 4 | `src/lib/queryKeys.ts` | `agent.my()`, `agent.myFiltered(filter)` 키 추가 |
| 5 | `src/hooks/useAgent.ts` | `useMyAgents`, `useSubscribeAgent`, `useUnsubscribeAgent`, `useTogglePin` 훅 추가 |
| 6 | `src/components/layout/AgentChatLayout.tsx` | `MOCK_AGENTS` 제거 → `useMyAgents()` 데이터 전달 |
| 7 | `src/components/layout/AppSidebar.tsx` | props 타입 변경, `source_type` 그룹핑 렌더링, 로딩/에러 상태 |
| 8 | `src/store/layoutStore.ts` | `selectedAgentId` 기본값 로직 개선 (API 데이터 기반) |
| 9 | `src/types/agent.ts` | `MOCK_AGENTS` 상수 제거 (또는 deprecated 처리) |

### 4.2 API → 타입 매핑

```typescript
// GET /api/v1/agents/my 응답의 agents[] 각 항목
interface MyAgent {
  agent_id: string;
  name: string;
  description: string;
  source_type: AgentSourceType;  // 'owned' | 'subscribed' | 'forked'
  visibility: 'private' | 'public';
  temperature: number;
  owner_user_id: string;
  forked_from: string | null;
  is_pinned: boolean;
  created_at: string;
}

type AgentSourceType = 'owned' | 'subscribed' | 'forked';

interface MyAgentsResponse {
  agents: MyAgent[];
  total: number;
  page: number;
  size: number;
}

interface MyAgentsParams {
  filter?: 'all' | AgentSourceType;
  search?: string;
  page?: number;
  size?: number;
}
```

### 4.3 API 엔드포인트 상수

```typescript
// constants/api.ts에 추가
AGENT_MY: '/api/v1/agents/my',
AGENT_SUBSCRIBE: (agentId: string) => `/api/v1/agents/${agentId}/subscribe`,
AGENT_FORK: (agentId: string) => `/api/v1/agents/${agentId}/fork`,
AGENT_FORK_STATS: (agentId: string) => `/api/v1/agents/${agentId}/forks`,
```

### 4.4 서비스 메서드 (authApiClient 사용)

```typescript
// agentService.ts에 추가
getMyAgents: (params?: MyAgentsParams) =>
  authApiClient.get<MyAgentsResponse>(API_ENDPOINTS.AGENT_MY, { params }),

subscribe: (agentId: string) =>
  authApiClient.post(API_ENDPOINTS.AGENT_SUBSCRIBE(agentId)),

unsubscribe: (agentId: string) =>
  authApiClient.delete(API_ENDPOINTS.AGENT_SUBSCRIBE(agentId)),

updateSubscription: (agentId: string, data: { is_pinned: boolean }) =>
  authApiClient.patch(API_ENDPOINTS.AGENT_SUBSCRIBE(agentId), data),

forkAgent: (agentId: string, data?: { name?: string }) =>
  authApiClient.post(API_ENDPOINTS.AGENT_FORK(agentId), data),
```

### 4.5 Query Keys

```typescript
// queryKeys.ts agent 섹션에 추가
agent: {
  all: ['agent'] as const,
  run: (runId: string) => [...queryKeys.agent.all, 'run', runId] as const,
  my: (params?: MyAgentsParams) => [...queryKeys.agent.all, 'my', params] as const,
},
```

### 4.6 커스텀 훅

```typescript
// useMyAgents: GET /api/v1/agents/my
export const useMyAgents = (params?: MyAgentsParams) =>
  useQuery({
    queryKey: queryKeys.agent.my(params),
    queryFn: () => agentService.getMyAgents(params).then(r => r.data),
  });

// useSubscribeAgent: POST /api/v1/agents/{id}/subscribe
export const useSubscribeAgent = () =>
  useMutation({
    mutationFn: (agentId: string) => agentService.subscribe(agentId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.agent.my() }),
  });

// useUnsubscribeAgent: DELETE /api/v1/agents/{id}/subscribe
export const useUnsubscribeAgent = () =>
  useMutation({
    mutationFn: (agentId: string) => agentService.unsubscribe(agentId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.agent.my() }),
  });

// useTogglePin: PATCH /api/v1/agents/{id}/subscribe
export const useTogglePin = () =>
  useMutation({
    mutationFn: ({ agentId, is_pinned }: { agentId: string; is_pinned: boolean }) =>
      agentService.updateSubscription(agentId, { is_pinned }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.agent.my() }),
  });
```

### 4.7 AgentChatLayout 변경

```diff
- import { MOCK_AGENTS } from '@/types/agent';
+ import { useMyAgents } from '@/hooks/useAgent';

  const AgentChatLayout = () => {
+   const { data, isLoading, isError, refetch } = useMyAgents();
+   const agents = data?.agents ?? [];

-   const selectedAgent = MOCK_AGENTS.find(a => a.id === selectedAgentId) ?? MOCK_AGENTS[0];
+   const selectedAgent = agents.find(a => a.agent_id === selectedAgentId) ?? agents[0] ?? null;

    return (
      <AppSidebar
-       agents={MOCK_AGENTS}
+       agents={agents}
+       isLoading={isLoading}
+       isError={isError}
+       onRetry={() => refetch()}
        selectedAgentId={selectedAgentId}
        onSelectAgent={selectAgent}
      />
    );
  };
```

### 4.8 AppSidebar 그룹핑 전략

```
에이전트 섹션:
├── 📌 고정 (is_pinned: true)
│   └── Agent A (subscribed)
├── 🔧 내 에이전트 (source_type: 'owned')
│   ├── Agent B
│   └── Agent C
├── ⭐ 구독 (source_type: 'subscribed')
│   └── Agent D
└── 🔀 포크 (source_type: 'forked')
    └── Agent E
```

---

## 5. Success Criteria

### 5.1 Definition of Done

- [ ] `MOCK_AGENTS` 참조가 코드베이스에서 완전히 제거됨
- [ ] 사이드바에서 실제 API 에이전트 목록이 렌더링됨
- [ ] 에이전트 선택 후 대화 화면에서 해당 에이전트 정보 표시
- [ ] 로딩/에러/빈 상태 UI가 올바르게 동작
- [ ] 커스텀 훅에 대한 단위 테스트 작성

### 5.2 Quality Criteria

- [ ] 훅/서비스 테스트 커버리지 80% 이상
- [ ] TypeScript strict 타입 에러 0건
- [ ] `npm run lint` 에러 0건

---

## 6. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 백엔드 API 미완성/스펙 불일치 | High | Medium | API 문서 기반으로 구현, 실패 시 fallback UI 제공 |
| 에이전트가 0개인 신규 유저 | Medium | High | 빈 상태 UI + "에이전트 둘러보기" CTA |
| selectedAgentId persist 문제 | Medium | Medium | API 응답에 해당 ID 없으면 첫 번째로 폴백 |

---

## 7. Architecture Considerations

### 7.1 Project Level

| Level | Selected |
|-------|:--------:|
| **Dynamic** | ✅ |

### 7.2 Key Decisions

| Decision | Selected | Rationale |
|----------|----------|-----------|
| HTTP Client | authApiClient (axios) | 인증 필수 API → Bearer 토큰 자동 주입 |
| State (서버) | TanStack Query | 기존 패턴 준수 |
| State (클라이언트) | Zustand (layoutStore) | 선택된 에이전트 ID persist |
| 캐시 무효화 | mutation onSuccess → invalidate | 구독/해제 후 목록 자동 갱신 |

---

## 8. Convention Prerequisites

### 8.1 Existing Conventions (확인 완료)

- [x] `CLAUDE.md` 코딩 컨벤션 섹션
- [x] ESLint + TypeScript strict 설정
- [x] Tailwind CSS v4 설정
- [x] TanStack Query 패턴 (`queryKeys` 팩토리)
- [x] authApiClient 인증 인터셉터 패턴

### 8.2 Environment Variables

기존 환경변수로 충분함. 추가 불필요.

---

## 9. Next Steps

1. [ ] Design 문서 작성 (`/pdca design agent-subscription`)
2. [ ] 구현 시작 (`/pdca do agent-subscription`)
3. [ ] Gap 분석 (`/pdca analyze agent-subscription`)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-05-04 | Initial draft | 배상규 |
