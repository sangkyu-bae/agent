# Plan: Agent Builder API Integration

## Executive Summary

| 항목 | 내용 |
|------|------|
| Feature | agent-builder-api-integration |
| 작성일 | 2026-05-08 |
| 예상 소요 | 3~4시간 |

### Value Delivered

| 관점 | 설명 |
|------|------|
| **Problem** | Agent Builder 페이지가 MOCK_AGENTS 로컬 state만 사용하여, 에이전트 생성/수정/삭제가 새로고침 시 사라지고 실제 서버에 등록되지 않음 |
| **Solution** | 백엔드 `/api/v1/agents` CRUD API와 연동하여 실제 DB에 에이전트를 저장·조회·수정·삭제 |
| **Function UX Effect** | 에이전트 생성 시 서버에 즉시 반영되어 다른 사용자도 구독/포크 가능, 새로고침 후에도 데이터 유지 |
| **Core Value** | Agent Builder가 실제 운영 가능한 기능이 되어, Agent Store·Agent Chat과 연결되는 완전한 에이전트 라이프사이클 완성 |

---

## 1. 현재 상황 분석

### 1.1 프론트엔드 (AgentBuilderPage)

- `MOCK_AGENTS` 상수 배열을 `useState`에 넣어 로컬에서만 관리
- `handleSave`: 로컬 state에 push (API 호출 없음)
- `handleDelete`: 로컬 state에서 filter (API 호출 없음)
- `handleToggle`: 로컬 state에서 isActive 토글 (API 호출 없음)
- `handleEdit`: 로컬 state 업데이트만 (API 호출 없음)
- 도구 카탈로그(`useToolCatalog`)와 LLM 모델(`useLlmModels`)은 이미 API 연동 완료

### 1.2 백엔드 API (이미 구현됨)

| Method | Endpoint | 용도 | 인증 |
|--------|----------|------|------|
| `GET` | `/api/v1/agents` | 에이전트 목록 조회 (scope 필터) | Bearer Token |
| `POST` | `/api/v1/agents` | 에이전트 생성 (LLM 자동 도구 선택 + 프롬프트 생성) | X-User-Id |
| `GET` | `/api/v1/agents/{agent_id}` | 에이전트 상세 조회 | Bearer Token |
| `PATCH` | `/api/v1/agents/{agent_id}` | 에이전트 수정 (이름, 프롬프트, visibility, temperature) | Bearer Token |
| `DELETE` | `/api/v1/agents/{agent_id}` | 에이전트 삭제 (소프트 삭제) | Bearer Token |

### 1.3 백엔드 스키마

**CreateAgentRequest:**
```
user_request: str (필수, max 1000) — 에이전트 설명/요청 (LLM이 이를 기반으로 도구 자동 선택)
name: str (필수, max 200)
user_id: str (필수)
llm_model_id: str | null
visibility: "private" | "department" | "public" (기본: "private")
department_id: str | null
temperature: float (0.0~2.0, 기본: 0.70)
tool_configs: { [tool_id]: RagToolConfigRequest } | null
```

**CreateAgentResponse:**
```
agent_id, name, system_prompt, tool_ids, workers, flow_hint,
llm_model_id, visibility, visibility_clamped, max_visibility,
department_id, temperature, created_at
```

**UpdateAgentRequest:**
```
system_prompt: str | null (max 4000)
name: str | null (max 200)
visibility: str | null
department_id: str | null
temperature: float | null
```

**ListAgentsResponse:**
```
agents: AgentSummary[] { agent_id, name, description, visibility, department_name,
                          owner_user_id, owner_email, temperature, can_edit, can_delete, created_at }
total, page, size
```

**GetAgentResponse:**
```
agent_id, name, description, system_prompt, tool_ids, workers, flow_hint,
llm_model_id, status, visibility, department_id, department_name, temperature,
owner_user_id, can_edit, can_delete, created_at, updated_at
```

---

## 2. 구현 범위

### 2.1 In-Scope

| # | 항목 | 설명 |
|---|------|------|
| 1 | 타입 정의 | `src/types/agentBuilder.ts` — 백엔드 스키마에 맞는 Request/Response 타입 |
| 2 | API 상수 추가 | `src/constants/api.ts` — Agent Builder 전용 엔드포인트 상수 (기존 AGENT_STORE_*와 구분) |
| 3 | 서비스 레이어 | `src/services/agentBuilderService.ts` — CRUD API 호출 메서드 (authApiClient 사용) |
| 4 | TanStack Query 훅 | `src/hooks/useAgentBuilder.ts` — 목록 조회, 생성, 수정, 삭제 mutation/query |
| 5 | AgentBuilderPage 리팩토링 | MOCK_AGENTS 제거, API 훅으로 교체, 로딩/에러 상태 처리 |
| 6 | 폼 필드 매핑 | 프론트엔드 폼 → CreateAgentRequest 매핑 (description → user_request) |

### 2.2 Out-of-Scope

- Middleware Agent API (v2) 연동 — 별도 기능
- Auto Agent Builder (v3) 연동 — 별도 기능
- Human-in-the-Loop 인터뷰 플로우 — 별도 UX 설계 필요
- Agent 실행 (`POST /api/v1/agents/{id}/run`) — Agent Chat 페이지에서 처리

---

## 3. 프론트-백엔드 필드 매핑

### 3.1 생성 (Create)

| 프론트엔드 폼 필드 | 백엔드 필드 | 비고 |
|-------------------|-----------|------|
| `form.name` | `name` | 그대로 매핑 |
| `form.description` | `user_request` | LLM이 이를 분석하여 도구 자동 선택 + 시스템 프롬프트 생성 |
| `form.model` | `llm_model_id` | 모델명 → model ID 매핑 필요 |
| `form.systemPrompt` | — | 생성 시점에는 전달 불가 (LLM 자동 생성). 생성 후 PATCH로 수정 |
| `form.tools` | — | LLM이 자동 선택. 생성 후 결과에서 확인 |
| `form.temperature` | `temperature` | 그대로 매핑 |
| `form.toolConfigs` | `tool_configs` | RAG 설정 등 그대로 매핑 |
| — | `user_id` | authStore에서 자동 주입 |
| — | `visibility` | 기본값 "private" (향후 UI 추가 가능) |

### 3.2 핵심 설계 결정: 2단계 생성 플로우

현재 백엔드 `POST /api/v1/agents`는 **LLM이 도구를 자동 선택하고 시스템 프롬프트를 자동 생성**하는 구조이다.
프론트엔드에서 사용자가 직접 선택한 도구/프롬프트는 생성 시점에 직접 전달할 수 없다.

**채택 방안: 2단계 생성 (Create → Patch)**

1. **Step 1 — Create**: `name` + `description(→user_request)` + `model` + `temperature` + `tool_configs` 로 생성
   - LLM이 자동으로 도구 선택 + 시스템 프롬프트 생성
2. **Step 2 — Patch (선택적)**: 사용자가 시스템 프롬프트를 직접 입력한 경우, `PATCH`로 덮어쓰기
   - `form.systemPrompt`이 비어있지 않으면 생성 직후 자동으로 PATCH 호출

이 방식으로 기존 UI 폼 구조를 유지하면서 백엔드 API와 호환된다.

### 3.3 수정 (Update)

| 프론트엔드 폼 필드 | 백엔드 필드 | 비고 |
|-------------------|-----------|------|
| `form.name` | `name` | 변경된 경우만 전송 |
| `form.systemPrompt` | `system_prompt` | 변경된 경우만 전송 |
| `form.temperature` | `temperature` | 변경된 경우만 전송 |

### 3.4 목록 조회 → UI 매핑

| 백엔드 AgentSummary 필드 | 프론트 Agent 인터페이스 | 매핑 |
|-------------------------|----------------------|------|
| `agent_id` | `id` | rename |
| `name` | `name` | 그대로 |
| `description` | `description` | 그대로 |
| `visibility` | `visibility` | 새 필드 (기존 isActive 대체 검토) |
| `temperature` | `temperature` | 그대로 |
| `can_edit` | `canEdit` | 새 필드 — 수정 버튼 표시 조건 |
| `can_delete` | `canDelete` | 새 필드 — 삭제 버튼 표시 조건 |
| `created_at` | `createdAt` | 그대로 |
| — | `model` | 상세 조회(GetAgentResponse)에서 `llm_model_id` 확인 |
| — | `systemPrompt` | 상세 조회(GetAgentResponse)에서 확인 |
| — | `tools` (tool_ids) | 상세 조회(GetAgentResponse)에서 확인 |

---

## 4. 구현 순서

### Step 1: 타입 정의 (`src/types/agentBuilder.ts`)

```typescript
// 백엔드 스키마 1:1 매핑
interface CreateAgentRequest { ... }
interface CreateAgentResponse { ... }
interface UpdateAgentRequest { ... }
interface UpdateAgentResponse { ... }
interface AgentBuilderSummary { ... }  // 목록용
interface AgentBuilderDetail { ... }   // 상세용
interface ListAgentsParams { ... }
interface ListAgentsResponse { ... }
```

### Step 2: API 상수 추가 (`src/constants/api.ts`)

```typescript
// 기존 AGENT_STORE_* 와 URL은 동일하지만 의미적으로 분리
// Agent Builder는 authApiClient 사용, owner 권한 기반
AGENT_BUILDER_LIST: '/api/v1/agents',
AGENT_BUILDER_CREATE: '/api/v1/agents',
AGENT_BUILDER_DETAIL: (agentId: string) => `/api/v1/agents/${agentId}`,
AGENT_BUILDER_UPDATE: (agentId: string) => `/api/v1/agents/${agentId}`,
AGENT_BUILDER_DELETE: (agentId: string) => `/api/v1/agents/${agentId}`,
```

> 참고: Agent Store와 URL이 동일하지만 Agent Builder는 `scope=mine` 필터 + owner 권한 기반 CRUD를 담당한다.

### Step 3: 서비스 레이어 (`src/services/agentBuilderService.ts`)

- `authApiClient` 사용 (인증 필요)
- `listMyAgents(params)` — `GET /api/v1/agents?scope=mine`
- `createAgent(data)` — `POST /api/v1/agents`
- `getAgent(agentId)` — `GET /api/v1/agents/{agentId}`
- `updateAgent(agentId, data)` — `PATCH /api/v1/agents/{agentId}`
- `deleteAgent(agentId)` — `DELETE /api/v1/agents/{agentId}`

### Step 4: TanStack Query 훅 (`src/hooks/useAgentBuilder.ts`)

- `useMyAgents(params)` — useQuery (queryKey: `queryKeys.agentBuilder.list(params)`)
- `useAgentDetail(agentId)` — useQuery
- `useCreateAgent()` — useMutation + 목록 invalidate
- `useUpdateAgent()` — useMutation + 목록/상세 invalidate
- `useDeleteAgent()` — useMutation + 목록 invalidate

### Step 5: queryKeys 확장 (`src/lib/queryKeys.ts`)

```typescript
agentBuilder: {
  all: ['agentBuilder'] as const,
  list: (params) => [..., 'list', params] as const,
  detail: (id) => [..., 'detail', id] as const,
},
```

### Step 6: AgentBuilderPage 리팩토링

1. `MOCK_AGENTS` 상수 및 `useState<Agent[]>` 제거
2. `useMyAgents()` 로 목록 조회
3. `handleSave` → `useCreateAgent` mutation + (선택적) `useUpdateAgent` 연쇄 호출
4. `handleEdit` → `useAgentDetail(agentId)` 로 상세 조회 후 폼 채우기
5. `handleDelete` → `useDeleteAgent` mutation + ConfirmDialog
6. `handleToggle` → 제거 또는 visibility 변경으로 대체 (isActive 개념이 백엔드에 없음)
7. 로딩 스켈레톤, 에러 상태, 빈 상태 처리
8. Agent 인터페이스를 `AgentBuilderSummary` 타입으로 교체

---

## 5. UI 변경 사항

### 5.1 목록 뷰 변경

- `isActive` 토글 → 제거 (백엔드에 해당 필드 없음) 또는 `visibility` 표시 배지로 대체
- `runCount` → 제거 (목록 API에 포함 안 됨)
- `can_edit`/`can_delete` 에 따라 수정/삭제 버튼 조건부 표시
- 페이지네이션 추가 (백엔드가 page/size 지원)

### 5.2 폼 뷰 변경

- `systemPrompt` 필드: placeholder에 "비워두면 AI가 자동 생성합니다" 안내 추가
- `tools` 선택: 유지하되, 생성 시에는 LLM 자동 선택임을 안내 (수정 시 반영되지 않는 참고용)
- 저장 버튼 클릭 시 로딩 상태 표시
- 생성 성공 시 토스트 알림 + 목록으로 이동

### 5.3 삭제 확인

- 기존 `ConfirmDialog` 컴포넌트 재사용 (`variant: 'danger'`)

---

## 6. 에러 처리

| 상황 | HTTP Status | 프론트 처리 |
|------|------------|------------|
| 인증 실패 | 401 | authClient interceptor 자동 처리 (토큰 갱신/로그아웃) |
| 권한 없음 (수정/삭제) | 403 | 토스트 "수정/삭제 권한이 없습니다" |
| 에이전트 없음 | 404 | 토스트 "에이전트를 찾을 수 없습니다" + 목록으로 이동 |
| 입력 검증 실패 | 422 | 폼 필드별 에러 메시지 표시 |
| 서버 오류 | 500 | 토스트 "서버 오류가 발생했습니다" |

---

## 7. 테스트 계획

| 대상 | 파일 | 테스트 항목 |
|------|------|-----------|
| 서비스 레이어 | `agentBuilderService.test.ts` | API 호출 URL/메서드/페이로드 검증 |
| TanStack Query 훅 | `useAgentBuilder.test.ts` | 조회/생성/수정/삭제 + 캐시 invalidation |
| 페이지 통합 | `AgentBuilderPage.test.tsx` | 목록 렌더링, 생성 폼 제출, 삭제 확인 |

---

## 8. 의존성

- `authApiClient` (이미 구현됨)
- `useAuthStore` (user_id 조회용, 이미 구현됨)
- `ConfirmDialog` (삭제 확인, 이미 구현됨)
- `queryKeys` 팩토리 (확장 필요)

---

## 9. 리스크 및 대응

| 리스크 | 대응 |
|--------|------|
| 프론트 도구 선택과 백엔드 LLM 자동 선택 불일치 | 생성 결과에서 실제 선택된 도구를 보여주고, UI에 "AI 추천" 레이블 표시 |
| `isActive` 필드 제거로 인한 UX 변화 | `visibility` 배지로 대체 (private/department/public) |
| 2단계 생성 (Create → Patch) 중 Patch 실패 | 생성은 성공했으므로 토스트로 "프롬프트 저장 실패" 알림, 목록에서 수정 가능 |
