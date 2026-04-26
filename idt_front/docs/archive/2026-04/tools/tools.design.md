# Design: tools

> AgentBuilderPage 도구 카탈로그 API 연동 — 상세 설계

## 1. 설계 개요

| 항목 | 내용 |
|------|------|
| Plan 참조 | `docs/01-plan/features/tools.plan.md` |
| API 스펙 | `docs/api/tools.md` |
| 변경 범위 | 타입 1개 + 상수 1줄 + 서비스 1개 + 쿼리키 1개 + 훅 1개 + 페이지 수정 1개 |

---

## 2. 데이터 모델 (타입 정의)

### 2-1. `src/types/toolCatalog.ts`

```typescript
export interface CatalogTool {
  tool_id: string;
  source: 'internal' | 'mcp';
  name: string;
  description: string;
  mcp_server_id: string | null;
  mcp_server_name: string | null;
  requires_env: string[];
}

export interface ToolCatalogResponse {
  tools: CatalogTool[];
}
```

---

## 3. API 레이어

### 3-1. 엔드포인트 상수 추가

**파일**: `src/constants/api.ts`

```typescript
// Tool Catalog (TOOL-CATALOG-001)
TOOL_CATALOG: '/api/v1/tool-catalog',
```

`API_ENDPOINTS` 객체의 Tools 섹션 아래에 추가.

### 3-2. 서비스 함수

**파일**: `src/services/toolCatalogService.ts`

```typescript
import authApiClient from '@/services/api/authClient';
import { API_ENDPOINTS } from '@/constants/api';
import type { ToolCatalogResponse } from '@/types/toolCatalog';

export const toolCatalogService = {
  getToolCatalog: () =>
    authApiClient.get<ToolCatalogResponse>(API_ENDPOINTS.TOOL_CATALOG),
};
```

- `authClient` 사용 (Bearer Token 자동 주입 + 401 갱신 처리)
- GET 요청, Request Body 없음

---

## 4. 상태 관리 (TanStack Query)

### 4-1. 쿼리 키 추가

**파일**: `src/lib/queryKeys.ts`

```typescript
// ── Tool Catalog ─────────────────────────────────────────
toolCatalog: {
  all: ['toolCatalog'] as const,
  list: () => [...queryKeys.toolCatalog.all, 'list'] as const,
},
```

### 4-2. 커스텀 훅

**파일**: `src/hooks/useToolCatalog.ts`

```typescript
import { useQuery } from '@tanstack/react-query';
import { toolCatalogService } from '@/services/toolCatalogService';
import { queryKeys } from '@/lib/queryKeys';
import type { CatalogTool } from '@/types/toolCatalog';

export const useToolCatalog = () =>
  useQuery<CatalogTool[]>({
    queryKey: queryKeys.toolCatalog.list(),
    queryFn: () =>
      toolCatalogService.getToolCatalog().then((r) => r.data.tools),
  });
```

- `staleTime`: QueryClient 기본값 사용 (1분)
- 에러/로딩: TanStack Query 기본 반환값 활용 (`isLoading`, `isError`, `error`)

---

## 5. UI 변경 사항

### 5-1. `AgentBuilderPage/index.tsx` 수정

#### 제거 항목
- `AVAILABLE_TOOLS` 하드코딩 배열 전체 삭제

#### 추가 항목
- `useToolCatalog()` 훅 호출
- 로딩 상태: 도구 영역에 스켈레톤 UI (2x3 그리드 placeholder)
- 에러 상태: 인라인 에러 메시지 + 재시도 버튼
- 정상 상태: 서버 데이터로 도구 선택 렌더링

#### FormView 도구 선택 변경

| 기존 | 변경 후 |
|------|---------|
| `AVAILABLE_TOOLS.map(...)` | `tools?.map(...)` (서버 데이터) |
| `tool.id` | `tool.tool_id` |
| `tool.label` | `tool.name` |
| `tool.icon` (SVG path) | 기본 아이콘 + source 뱃지 |

#### AgentCard 도구 태그 변경

```typescript
// 기존: AVAILABLE_TOOLS에서 label 조회
const tool = AVAILABLE_TOOLS.find((t) => t.id === toolId);

// 변경: 서버 도구 목록에서 name 조회
const tool = catalogTools?.find((t) => t.tool_id === toolId);
```

### 5-2. UI 상태별 렌더링

```
┌─────────────────────────────────────┐
│ [로딩 중]                            │
│  ┌──────────┐  ┌──────────┐        │
│  │ ░░░░░░░░ │  │ ░░░░░░░░ │        │
│  └──────────┘  └──────────┘        │
│  ┌──────────┐  ┌──────────┐        │
│  │ ░░░░░░░░ │  │ ░░░░░░░░ │        │
│  └──────────┘  └──────────┘        │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│ [에러]                               │
│  ⚠ 도구 목록을 불러올 수 없습니다     │
│  [다시 시도]                         │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│ [정상 — 도구 없음]                    │
│  등록된 도구가 없습니다               │
└─────────────────────────────────────┘
```

---

## 6. 컴포넌트 의존성 그래프

```
AgentBuilderPage
├── useToolCatalog()  ← NEW
│   ├── toolCatalogService.getToolCatalog()
│   │   └── authApiClient (Bearer Token)
│   └── queryKeys.toolCatalog.list()
├── FormView
│   └── tools (from useToolCatalog) → 도구 선택 렌더링
└── AgentCard
    └── catalogTools (prop) → 도구 이름 표시
```

---

## 7. 구현 순서 (Do Phase 가이드)

| 순서 | 파일 | 작업 |
|------|------|------|
| 1 | `src/types/toolCatalog.ts` | CatalogTool, ToolCatalogResponse 타입 정의 |
| 2 | `src/constants/api.ts` | TOOL_CATALOG 엔드포인트 추가 |
| 3 | `src/services/toolCatalogService.ts` | getToolCatalog 서비스 함수 |
| 4 | `src/lib/queryKeys.ts` | toolCatalog 쿼리 키 추가 |
| 5 | `src/hooks/useToolCatalog.ts` | useToolCatalog 훅 작성 |
| 6 | `src/pages/AgentBuilderPage/index.tsx` | AVAILABLE_TOOLS 제거, 훅 연동, 로딩/에러 UI |

---

## 8. 테스트 설계

### 8-1. MSW 핸들러

**파일**: `src/__tests__/mocks/handlers.ts`에 추가

```typescript
http.get('*/api/v1/tool-catalog', () =>
  HttpResponse.json({
    tools: [
      { tool_id: 'internal:excel_export', source: 'internal', name: 'Excel 파일 생성', description: '...', mcp_server_id: null, mcp_server_name: null, requires_env: [] },
      { tool_id: 'mcp:srv1:search', source: 'mcp', name: 'search', description: '...', mcp_server_id: 'srv1', mcp_server_name: 'Search', requires_env: [] },
    ],
  })
),
```

### 8-2. 훅 테스트 (`useToolCatalog.test.ts`)

| 시나리오 | 검증 항목 |
|----------|----------|
| 성공 | `data`에 CatalogTool[] 반환, `isSuccess === true` |
| 401 에러 | `isError === true`, 토큰 갱신 시도 확인 |
| 빈 목록 | `data`가 빈 배열 `[]` |

### 8-3. 컴포넌트 테스트 (FormView)

| 시나리오 | 검증 항목 |
|----------|----------|
| 로딩 중 | 스켈레톤 UI 렌더링 |
| 도구 목록 표시 | 서버 데이터의 tool.name이 화면에 표시 |
| 도구 선택 | 클릭 시 form.tools에 tool_id 추가 |
| 도구 선택 해제 | 재클릭 시 form.tools에서 tool_id 제거 |

---

## 9. 에러 처리

| 상황 | 처리 |
|------|------|
| 401 Unauthorized | authClient interceptor가 토큰 갱신 후 재시도 |
| 네트워크 에러 | TanStack Query retry 1회 (QueryClient 기본값) |
| API 서버 500 | `isError` 상태 → 인라인 에러 메시지 표시 |

---

## 10. 마이그레이션 노트

- `Agent.tools` 필드 타입: `string[]` — 기존 Mock 데이터의 tool id와 서버의 `tool_id` 포맷이 다름
  - 기존 Mock: `'web-search'`, `'code-exec'` 등
  - 서버: `'internal:excel_export'`, `'mcp:server-uuid:search'`
- 기존 Mock 에이전트 데이터(`MOCK_AGENTS`)도 함께 제거하거나 서버 응답으로 교체 필요
  - 이번 스코프에서는 도구 카탈로그만 API 연동하고, Agent CRUD는 추후 별도 작업
  - `MOCK_AGENTS`의 `tools` 필드는 빈 배열로 리셋하거나, 서버에 존재하는 tool_id로 매핑

---

## 11. 영향 범위

| 파일 | 변경 유형 |
|------|----------|
| `src/types/toolCatalog.ts` | 신규 |
| `src/constants/api.ts` | 1줄 추가 |
| `src/services/toolCatalogService.ts` | 신규 |
| `src/lib/queryKeys.ts` | 섹션 추가 |
| `src/hooks/useToolCatalog.ts` | 신규 |
| `src/pages/AgentBuilderPage/index.tsx` | 수정 (AVAILABLE_TOOLS 제거, 훅 연동) |
| `src/__tests__/mocks/handlers.ts` | 핸들러 추가 |
