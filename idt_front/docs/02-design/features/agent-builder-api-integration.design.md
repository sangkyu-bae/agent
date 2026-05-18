# Design: Agent Builder API Integration

## Executive Summary

| 항목 | 내용 |
|------|------|
| Feature | agent-builder-api-integration |
| Plan 참조 | `docs/01-plan/features/agent-builder-api-integration.plan.md` |
| 작성일 | 2026-05-08 |

### Value Delivered

| 관점 | 설명 |
|------|------|
| **Problem** | Agent Builder 페이지가 MOCK_AGENTS 로컬 state만 사용 — 서버 미등록, 새로고침 시 데이터 소실 |
| **Solution** | 백엔드 `/api/v1/agents` CRUD API 연동 + 2단계 생성(Create→Patch) 패턴 |
| **Function UX Effect** | 에이전트 생성 즉시 서버 반영, 목록 실시간 갱신, 권한 기반 수정/삭제 |
| **Core Value** | Agent Builder → Agent Store → Agent Chat 전체 라이프사이클 연결 완성 |

---

## 1. 아키텍처 개요

```
AgentBuilderPage
  ├── useMyBuilderAgents()  ← TanStack Query (GET /api/v1/agents?scope=mine)
  ├── useBuilderAgentDetail()  ← TanStack Query (GET /api/v1/agents/{id})
  ├── useCreateBuilderAgent()  ← useMutation (POST /api/v1/agents + PATCH)
  ├── useUpdateBuilderAgent()  ← useMutation (PATCH /api/v1/agents/{id})
  └── useDeleteBuilderAgent()  ← useMutation (DELETE /api/v1/agents/{id})
        │
        ▼
  agentBuilderService.ts  ← authApiClient (Bearer Token + X-User-Id 자동 주입)
        │
        ▼
  Backend: /api/v1/agents (agent_builder_router.py)
```

### 핵심 설계 결정: 기존 agentStore 타입 재사용

Agent Builder와 Agent Store는 동일한 백엔드 `/api/v1/agents` 엔드포인트를 사용한다.
응답 스키마도 동일하므로 **기존 `src/types/agentStore.ts`의 타입을 재사용**하고, Agent Builder 전용 Request 타입만 새로 정의한다.

| 구분 | 타입 | 출처 |
|------|------|------|
| 목록 응답 | `StoreAgentSummary`, `AgentListResponse` | 기존 `agentStore.ts` 재사용 |
| 상세 응답 | `AgentDetail` | 기존 `agentStore.ts` 재사용 |
| 생성 요청 | `CreateBuilderAgentRequest` | **신규** `agentBuilder.ts` |
| 생성 응답 | `CreateBuilderAgentResponse` | **신규** `agentBuilder.ts` |
| 수정 요청 | `UpdateBuilderAgentRequest` | **신규** `agentBuilder.ts` |
| 수정 응답 | `UpdateBuilderAgentResponse` | **신규** `agentBuilder.ts` |

---

## 2. 상세 설계

### 2.1 타입 정의 — `src/types/agentBuilder.ts`

```typescript
import type { RagToolConfig } from './ragToolConfig';

// ── Create ─────────────────────────────────────

export interface CreateBuilderAgentRequest {
  user_request: string;       // 에이전트 설명 (LLM이 도구 자동 선택에 사용)
  name: string;               // 에이전트 이름
  llm_model_id?: string;      // 선택한 LLM 모델 ID
  visibility?: 'private' | 'department' | 'public';
  department_id?: string;
  temperature?: number;       // 0.0~2.0
  tool_configs?: Record<string, RagToolConfig>;
}

export interface WorkerInfo {
  tool_id: string;
  worker_id: string;
  description: string;
  sort_order: number;
  tool_config: Record<string, unknown> | null;
}

export interface CreateBuilderAgentResponse {
  agent_id: string;
  name: string;
  system_prompt: string;
  tool_ids: string[];
  workers: WorkerInfo[];
  flow_hint: string;
  llm_model_id: string;
  visibility: string;
  visibility_clamped: boolean;
  max_visibility: string | null;
  department_id: string | null;
  temperature: number;
  created_at: string;
}

// ── Update ─────────────────────────────────────

export interface UpdateBuilderAgentRequest {
  system_prompt?: string;
  name?: string;
  visibility?: 'private' | 'department' | 'public';
  department_id?: string;
  temperature?: number;
}

export interface UpdateBuilderAgentResponse {
  agent_id: string;
  name: string;
  system_prompt: string;
  updated_at: string;
}

// ── Form (프론트엔드 전용) ─────────────────────

export interface AgentBuilderFormData {
  name: string;
  description: string;        // → CreateBuilderAgentRequest.user_request로 매핑
  model: string;              // model_name (UI 표시용) — llm_model_id로 변환 필요
  systemPrompt: string;
  tools: string[];            // 참고용 (생성 시 LLM 자동 선택, 수정 시 변경 불가)
  temperature: number;
  toolConfigs: Record<string, RagToolConfig>;
}
```

### 2.2 API 상수 — `src/constants/api.ts` (추가분)

```typescript
// Agent Builder (CRUD — authApiClient 사용)
AGENT_BUILDER_CREATE: '/api/v1/agents',
AGENT_BUILDER_DETAIL: (agentId: string) => `/api/v1/agents/${agentId}`,
AGENT_BUILDER_UPDATE: (agentId: string) => `/api/v1/agents/${agentId}`,
AGENT_BUILDER_DELETE: (agentId: string) => `/api/v1/agents/${agentId}`,
```

> `AGENT_STORE_LIST` (`/api/v1/agents`)를 목록 조회에 재사용한다 (`scope=mine` 파라미터로 필터링).
> URL이 동일하므로 별도 `AGENT_BUILDER_LIST` 상수는 추가하지 않는다.

### 2.3 서비스 레이어 — `src/services/agentBuilderService.ts`

```typescript
import authApiClient from './api/authClient';
import { API_ENDPOINTS } from '@/constants/api';
import type { AgentListResponse, AgentDetail } from '@/types/agentStore';
import type {
  CreateBuilderAgentRequest,
  CreateBuilderAgentResponse,
  UpdateBuilderAgentRequest,
  UpdateBuilderAgentResponse,
} from '@/types/agentBuilder';

export const agentBuilderService = {
  /** 내가 만든 에이전트 목록 조회 (scope=mine) */
  listMine: (params?: { search?: string; page?: number; size?: number }) =>
    authApiClient.get<AgentListResponse>(API_ENDPOINTS.AGENT_STORE_LIST, {
      params: { scope: 'mine', ...params },
    }),

  /** 에이전트 상세 조회 */
  getDetail: (agentId: string) =>
    authApiClient.get<AgentDetail>(API_ENDPOINTS.AGENT_BUILDER_DETAIL(agentId)),

  /** 에이전트 생성 */
  create: (data: CreateBuilderAgentRequest) =>
    authApiClient.post<CreateBuilderAgentResponse>(
      API_ENDPOINTS.AGENT_BUILDER_CREATE,
      data,
    ),

  /** 에이전트 수정 */
  update: (agentId: string, data: UpdateBuilderAgentRequest) =>
    authApiClient.patch<UpdateBuilderAgentResponse>(
      API_ENDPOINTS.AGENT_BUILDER_UPDATE(agentId),
      data,
    ),

  /** 에이전트 삭제 */
  delete: (agentId: string) =>
    authApiClient.delete(API_ENDPOINTS.AGENT_BUILDER_DELETE(agentId)),
};
```

### 2.4 Query Keys — `src/lib/queryKeys.ts` (추가분)

```typescript
// ── Agent Builder ────────────────────────────────
agentBuilder: {
  all: ['agentBuilder'] as const,
  list: (params?: { search?: string; page?: number; size?: number }) =>
    [...queryKeys.agentBuilder.all, 'list', params] as const,
  detail: (agentId: string) =>
    [...queryKeys.agentBuilder.all, 'detail', agentId] as const,
},
```

### 2.5 TanStack Query 훅 — `src/hooks/useAgentBuilder.ts`

```typescript
import { useQuery, useMutation } from '@tanstack/react-query';
import { agentBuilderService } from '@/services/agentBuilderService';
import { queryKeys } from '@/lib/queryKeys';
import { queryClient } from '@/lib/queryClient';
import type { AgentListResponse, AgentDetail } from '@/types/agentStore';
import type {
  CreateBuilderAgentRequest,
  CreateBuilderAgentResponse,
  UpdateBuilderAgentRequest,
  UpdateBuilderAgentResponse,
} from '@/types/agentBuilder';

// ── 목록 조회 ──────────────────────────────────

interface ListParams {
  search?: string;
  page?: number;
  size?: number;
}

export const useMyBuilderAgents = (params?: ListParams) =>
  useQuery<AgentListResponse>({
    queryKey: queryKeys.agentBuilder.list(params),
    queryFn: () => agentBuilderService.listMine(params).then((r) => r.data),
  });

// ── 상세 조회 ──────────────────────────────────

export const useBuilderAgentDetail = (agentId: string | null) =>
  useQuery<AgentDetail>({
    queryKey: queryKeys.agentBuilder.detail(agentId ?? ''),
    queryFn: () => agentBuilderService.getDetail(agentId!).then((r) => r.data),
    enabled: !!agentId,
  });

// ── 생성 ────────────────────────────────────────

export const useCreateBuilderAgent = () =>
  useMutation<CreateBuilderAgentResponse, Error, CreateBuilderAgentRequest>({
    mutationFn: (data) =>
      agentBuilderService.create(data).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.agentBuilder.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.agentStore.all });
    },
  });

// ── 수정 ────────────────────────────────────────

interface UpdateVars {
  agentId: string;
  data: UpdateBuilderAgentRequest;
}

export const useUpdateBuilderAgent = () =>
  useMutation<UpdateBuilderAgentResponse, Error, UpdateVars>({
    mutationFn: ({ agentId, data }) =>
      agentBuilderService.update(agentId, data).then((r) => r.data),
    onSuccess: (_data, { agentId }) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.agentBuilder.all });
      queryClient.invalidateQueries({
        queryKey: queryKeys.agentStore.detail(agentId),
      });
    },
  });

// ── 삭제 ────────────────────────────────────────

export const useDeleteBuilderAgent = () =>
  useMutation<void, Error, string>({
    mutationFn: (agentId) =>
      agentBuilderService.delete(agentId).then(() => undefined),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.agentBuilder.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.agentStore.all });
    },
  });
```

---

## 3. AgentBuilderPage 리팩토링 상세

### 3.1 제거 항목

| 항목 | 이유 |
|------|------|
| `MOCK_AGENTS` 상수 | 서버 데이터로 대체 |
| `useState<Agent[]>(MOCK_AGENTS)` | `useMyBuilderAgents()` 로 대체 |
| 로컬 `Agent` 인터페이스 | `StoreAgentSummary` + `AgentDetail` 재사용 |
| `handleToggle` (isActive 토글) | 백엔드에 `isActive` 필드 없음 → visibility 배지로 대체 |
| `activeCount` / 활성 에이전트 요약 섹션 | `isActive` 제거에 따라 불필요 |

### 3.2 유지 항목

| 항목 | 상태 |
|------|------|
| `ViewMode` ('list' / 'create' / 'edit') | 유지 |
| `AgentBuilderFormData` (폼 state) | `AgentBuilderFormData` 타입으로 교체 |
| `useToolCatalog()` | 유지 (이미 API 연동) |
| `useLlmModels()` | 유지 (이미 API 연동) |
| `RagConfigPanel` | 유지 |
| `FormView` 컴포넌트 | 유지 (폼 UI 동일) |

### 3.3 변경 흐름

#### 목록 조회

```
[기존] useState<Agent[]>(MOCK_AGENTS)
[변경] const { data, isLoading, isError } = useMyBuilderAgents();
       const agents = data?.agents ?? [];
```

#### 에이전트 생성 (`handleSave` in create mode)

```
[기존] setAgents(prev => [newAgent, ...prev]); setView('list');

[변경]
1. form → CreateBuilderAgentRequest 변환
   {
     user_request: form.description,
     name: form.name,
     llm_model_id: selectedModel?.id,  // model_name → id 변환
     temperature: form.temperature,
     tool_configs: form.toolConfigs (RAG 설정이 있는 경우),
   }

2. createMutation.mutate(request, {
     onSuccess: (response) => {
       // Step 2: 사용자가 시스템 프롬프트를 입력한 경우 PATCH
       if (form.systemPrompt.trim()) {
         updateMutation.mutate({
           agentId: response.agent_id,
           data: { system_prompt: form.systemPrompt },
         });
       }
       setView('list');
     },
   });
```

#### 에이전트 수정 진입 (`handleEdit`)

```
[기존] form에 agent 필드 직접 복사 → setView('edit')

[변경]
1. setEditingId(agent.agent_id);
2. setView('edit');
3. useBuilderAgentDetail(editingId) 로 상세 조회
4. useEffect에서 detail 로드 완료 시 form 채우기:
   {
     name: detail.name,
     description: detail.description,
     model: detail.llm_model_id,
     systemPrompt: detail.system_prompt,
     tools: detail.tool_ids,
     temperature: detail.temperature,
     toolConfigs: {},  // 기존 tool_config 파싱
   }
```

#### 에이전트 수정 저장 (`handleSave` in edit mode)

```
[기존] setAgents(prev => prev.map(...))

[변경]
updateMutation.mutate({
  agentId: editingId,
  data: {
    name: form.name,
    system_prompt: form.systemPrompt,
    temperature: form.temperature,
  },
}, {
  onSuccess: () => setView('list'),
});
```

#### 에이전트 삭제 (`handleDelete`)

```
[기존] setAgents(prev => prev.filter(a => a.id !== id))

[변경]
1. ConfirmDialog 표시 (variant: 'danger')
2. 확인 시: deleteMutation.mutate(agentId, {
     onSuccess: () => { /* 자동 invalidate됨 */ },
   });
```

### 3.4 AgentCard 변경

| 기존 | 변경 |
|------|------|
| `agent.isActive` 토글 스위치 | visibility 배지 (`private`/`department`/`public`) |
| `agent.runCount` 표시 | 제거 |
| `agent.model` (문자열) | `agent.temperature` + visibility 표시 |
| 수정/삭제 버튼 항상 표시 | `can_edit`/`can_delete` 에 따라 조건부 렌더링 |

### 3.5 Visibility 배지 디자인

```typescript
const VISIBILITY_STYLES = {
  private: 'bg-zinc-100 text-zinc-500',
  department: 'bg-amber-100 text-amber-700',
  public: 'bg-emerald-100 text-emerald-700',
} as const;

const VISIBILITY_LABELS = {
  private: '비공개',
  department: '부서',
  public: '공개',
} as const;
```

### 3.6 로딩/에러 상태

**목록 로딩:**
```tsx
// 3열 그리드 스켈레톤 카드 6개
<div className="grid grid-cols-3 gap-4">
  {Array.from({ length: 6 }).map((_, i) => (
    <div key={i} className="h-[220px] animate-pulse rounded-2xl border border-zinc-200 bg-zinc-100" />
  ))}
</div>
```

**목록 에러:**
```tsx
<div className="flex flex-col items-center py-20">
  <p className="text-[13px] text-zinc-500">에이전트 목록을 불러올 수 없습니다</p>
  <button onClick={() => refetch()} className="mt-3 ...">다시 시도</button>
</div>
```

**생성/수정/삭제 중:** 저장/삭제 버튼에 `disabled` + 스피너 표시

---

## 4. 파일 변경 목록

| # | 파일 | 액션 | 설명 |
|---|------|------|------|
| 1 | `src/types/agentBuilder.ts` | **신규** | Create/Update Request/Response + FormData 타입 |
| 2 | `src/constants/api.ts` | **수정** | `AGENT_BUILDER_*` 상수 4개 추가 |
| 3 | `src/services/agentBuilderService.ts` | **신규** | CRUD 5개 메서드 |
| 4 | `src/lib/queryKeys.ts` | **수정** | `agentBuilder` 도메인 추가 |
| 5 | `src/hooks/useAgentBuilder.ts` | **신규** | Query/Mutation 5개 훅 |
| 6 | `src/pages/AgentBuilderPage/index.tsx` | **수정** | MOCK 제거, API 훅 연동, UI 변경 |

### 변경 라인 수 추정

| 파일 | 추가 | 수정 | 삭제 |
|------|------|------|------|
| `agentBuilder.ts` (타입) | ~65줄 | - | - |
| `api.ts` (상수) | ~5줄 | - | - |
| `agentBuilderService.ts` | ~35줄 | - | - |
| `queryKeys.ts` | ~8줄 | - | - |
| `useAgentBuilder.ts` | ~75줄 | - | - |
| `AgentBuilderPage/index.tsx` | ~80줄 | ~120줄 | ~60줄 |
| **합계** | **~268줄** | **~120줄** | **~60줄** |

---

## 5. 구현 순서 (Implementation Order)

```
[1] src/types/agentBuilder.ts         ← 의존성 없음
[2] src/constants/api.ts              ← 의존성 없음
[3] src/lib/queryKeys.ts              ← 의존성 없음
    ────────── (위 3개 병렬 가능) ──────────
[4] src/services/agentBuilderService.ts  ← [1], [2] 필요
[5] src/hooks/useAgentBuilder.ts         ← [1], [3], [4] 필요
    ────────── (순차) ──────────
[6] src/pages/AgentBuilderPage/index.tsx ← [5] 필요
```

---

## 6. 에러 처리 매트릭스

| API 호출 | 성공 시 | 실패 시 |
|----------|--------|--------|
| `listMine` | agents 렌더링 | 에러 UI + "다시 시도" 버튼 |
| `create` | 토스트 "에이전트가 생성되었습니다" + 목록 이동 | 토스트 에러 메시지 + 폼 유지 |
| `create` → `update` (2단계) | 무음 (이미 생성 성공) | 토스트 "시스템 프롬프트 저장 실패" (목록 이동은 진행) |
| `getDetail` | 폼 채우기 | 토스트 "에이전트 정보를 불러올 수 없습니다" + 목록 이동 |
| `update` | 토스트 "수정되었습니다" + 목록 이동 | 토스트 에러 메시지 + 폼 유지 |
| `delete` | 토스트 "삭제되었습니다" + 목록 갱신 | 토스트 에러 메시지 |

---

## 7. model_name → llm_model_id 변환

현재 폼에서는 `model_name` (예: `"claude-sonnet-4-6"`)을 저장하지만, 백엔드 `CreateAgentRequest`는 `llm_model_id`를 받는다.

**변환 방법:**
```typescript
// useLlmModels()에서 이미 모델 목록을 가져오고 있음
// models 배열에서 model_name으로 찾아 id를 매핑
const selectedModel = models?.find(m => m.model_name === form.model);
const llm_model_id = selectedModel?.id;
```

`LlmModel` 타입에 `id` 필드가 포함되어 있으므로 추가 API 호출 없이 변환 가능하다.

---

## 8. 캐시 무효화 전략

| 이벤트 | 무효화 대상 | 이유 |
|--------|-----------|------|
| 에이전트 생성 | `agentBuilder.all` + `agentStore.all` | 목록 갱신 + Agent Store에도 반영 |
| 에이전트 수정 | `agentBuilder.all` + `agentStore.detail(id)` | 목록 + Store 상세 갱신 |
| 에이전트 삭제 | `agentBuilder.all` + `agentStore.all` | 목록 갱신 + Store에서도 사라짐 |

Agent Builder에서 CRUD 하면 Agent Store 캐시도 함께 무효화하여, 두 페이지 간 데이터 일관성을 보장한다.
