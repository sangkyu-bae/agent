# Custom RAG Tool - Frontend Implementation Guide

> Feature: CUSTOM-RAG-TOOL-001 Phase 7  
> Created: 2026-04-21  
> Backend Design: `docs/02-design/features/custom-rag-tool.design.md` (Section 6)  
> Target Directory: `idt_front/`

---

## 1. 구현 개요

에이전트 빌더에서 `internal_document_search` 도구를 선택했을 때 **RAG 설정 패널**을 노출하여,
검색 범위(컬렉션/메타데이터 필터)와 검색 파라미터(top_k, search_mode)를 커스텀할 수 있게 한다.

### 최종 UI 구조

```
AgentBuilderPage (FormView)
  └─ 도구 연결 섹션 (기존)
       ├─ ToolButton (internal_document_search) ← 선택 시 아래 패널 노출
       ├─ ToolButton (tavily_search)
       └─ ...
  └─ RagConfigPanel (신규) ← tool_id === "internal_document_search" 선택 시에만 표시
       ├─ CollectionSelect        — Qdrant 컬렉션 드롭다운
       ├─ MetadataFilterEditor    — key-value 필터 입력 (동적 추가/삭제)
       ├─ SearchParamsControl     — top_k 슬라이더 + search_mode 라디오
       └─ ToolIdentityEditor      — tool_name, tool_description 입력
```

---

## 2. 구현 파일 목록

| # | 파일 경로 | 유형 | 설명 |
|---|----------|------|------|
| 1 | `src/types/ragToolConfig.ts` | 타입 | RAG config 관련 TypeScript 인터페이스 |
| 2 | `src/constants/api.ts` | 상수 | RAG Tool 엔드포인트 추가 |
| 3 | `src/services/ragToolService.ts` | 서비스 | RAG Tool API 호출 |
| 4 | `src/lib/queryKeys.ts` | 쿼리 키 | ragTools 도메인 키 추가 |
| 5 | `src/hooks/useRagToolConfig.ts` | 훅 | 컬렉션/메타데이터 키 조회 훅 |
| 6 | `src/components/agent-builder/RagConfigPanel.tsx` | 컴포넌트 | RAG 설정 패널 (메인) |
| 7 | `src/pages/AgentBuilderPage/index.tsx` | 페이지 | RagConfigPanel 통합 |
| 8 | `src/__tests__/mocks/handlers.ts` | 테스트 | MSW 핸들러 추가 |
| 9 | `src/hooks/useRagToolConfig.test.ts` | 테스트 | 훅 테스트 |

---

## 3. 상세 구현 명세

### 3-1. 타입 정의

**파일**: `src/types/ragToolConfig.ts` (신규)

```typescript
/** RAG 도구 커스텀 설정 — 에이전트 생성 시 tool_configs에 포함 */
export interface RagToolConfig {
  collection_name?: string;
  es_index?: string;
  metadata_filter: Record<string, string>;
  top_k: number;
  search_mode: 'hybrid' | 'vector_only' | 'bm25_only';
  rrf_k: number;
  tool_name: string;
  tool_description: string;
}

/** GET /api/v1/rag-tools/collections 응답 항목 */
export interface CollectionInfo {
  name: string;
  display_name: string;
  vectors_count?: number;
}

/** GET /api/v1/rag-tools/collections 응답 */
export interface CollectionsResponse {
  collections: CollectionInfo[];
}

/** GET /api/v1/rag-tools/metadata-keys 응답 항목 */
export interface MetadataKeyInfo {
  key: string;
  sample_values: string[];
  value_count: number;
}

/** GET /api/v1/rag-tools/metadata-keys 응답 */
export interface MetadataKeysResponse {
  keys: MetadataKeyInfo[];
}
```

**기본값 상수** (같은 파일 하단):

```typescript
export const DEFAULT_RAG_CONFIG: RagToolConfig = {
  metadata_filter: {},
  top_k: 5,
  search_mode: 'hybrid',
  rrf_k: 60,
  tool_name: '내부 문서 검색',
  tool_description: '내부 문서에서 관련 정보를 검색합니다. 질문에 대한 내부 문서 정보가 필요할 때 사용하세요.',
};
```

---

### 3-2. API 상수 추가

**파일**: `src/constants/api.ts`

기존 `API_ENDPOINTS` 객체에 추가:

```typescript
  // RAG Tools (Custom RAG Tool for Agent Builder)
  RAG_TOOL_COLLECTIONS: '/api/v1/rag-tools/collections',
  RAG_TOOL_METADATA_KEYS: '/api/v1/rag-tools/metadata-keys',
```

**위치**: `TOOL_CATALOG` 아래에 배치 (도구 관련 엔드포인트 그룹)

---

### 3-3. 서비스 레이어

**파일**: `src/services/ragToolService.ts` (신규)

```typescript
import apiClient from './api/client';
import { API_ENDPOINTS } from '@/constants/api';
import type { CollectionsResponse, MetadataKeysResponse } from '@/types/ragToolConfig';

export const ragToolService = {
  /** 사용 가능한 Qdrant 컬렉션 목록 조회 */
  getCollections: () =>
    apiClient.get<CollectionsResponse>(API_ENDPOINTS.RAG_TOOL_COLLECTIONS),

  /** 필터링 가능한 메타데이터 키 + 샘플 값 조회 */
  getMetadataKeys: (collectionName?: string) =>
    apiClient.get<MetadataKeysResponse>(API_ENDPOINTS.RAG_TOOL_METADATA_KEYS, {
      params: collectionName ? { collection_name: collectionName } : undefined,
    }),
};
```

**패턴 참고**: `src/services/toolCatalogService.ts` — 동일한 object literal 패턴

---

### 3-4. 쿼리 키 추가

**파일**: `src/lib/queryKeys.ts`

기존 `queryKeys` 객체에 추가:

```typescript
  // ── RAG Tools ──────────────────────────────────────────
  ragTools: {
    all: ['ragTools'] as const,
    collections: () => [...queryKeys.ragTools.all, 'collections'] as const,
    metadataKeys: (collectionName?: string) =>
      [...queryKeys.ragTools.all, 'metadataKeys', collectionName] as const,
  },
```

**위치**: `toolCatalog` 아래에 배치

---

### 3-5. 커스텀 훅

**파일**: `src/hooks/useRagToolConfig.ts` (신규)

```typescript
import { useQuery } from '@tanstack/react-query';
import { ragToolService } from '@/services/ragToolService';
import { queryKeys } from '@/lib/queryKeys';

/** Qdrant 컬렉션 목록 조회 */
export const useCollections = () =>
  useQuery({
    queryKey: queryKeys.ragTools.collections(),
    queryFn: () =>
      ragToolService.getCollections().then((r) => r.data.collections),
    staleTime: 5 * 60 * 1000, // 5분 캐시 (컬렉션은 자주 변하지 않음)
  });

/** 메타데이터 키 목록 조회 (컬렉션 선택 시 연동) */
export const useMetadataKeys = (collectionName?: string) =>
  useQuery({
    queryKey: queryKeys.ragTools.metadataKeys(collectionName),
    queryFn: () =>
      ragToolService.getMetadataKeys(collectionName).then((r) => r.data.keys),
    enabled: !!collectionName, // 컬렉션 선택 전에는 비활성
    staleTime: 3 * 60 * 1000,
  });
```

**패턴 참고**: `src/hooks/useToolCatalog.ts`, `src/hooks/useLlmModels.ts`

---

### 3-6. RagConfigPanel 컴포넌트

**파일**: `src/components/agent-builder/RagConfigPanel.tsx` (신규)

이 컴포넌트는 `internal_document_search` 도구가 선택되었을 때 폼 영역 아래에 표시된다.

#### Props 인터페이스

```typescript
interface RagConfigPanelProps {
  config: RagToolConfig;
  onChange: (config: RagToolConfig) => void;
}
```

#### 내부 구조 (4개 섹션)

**섹션 1: CollectionSelect**

```
┌────────────────────────────────────────┐
│  검색 대상 컬렉션                        │
│  ┌──────────────────────────────────┐  │
│  │ ▼ 전체 문서 (기본)               │  │
│  │   금융 문서 (200)                │  │
│  │   기술 매뉴얼 (150)              │  │
│  └──────────────────────────────────┘  │
└────────────────────────────────────────┘
```

- `useCollections()` 훅으로 목록 로딩
- 선택 시 `config.collection_name` 업데이트
- 선택 변경 시 메타데이터 필터 초기화
- "전체 문서 (기본)" 옵션 = `collection_name: undefined`
- 로딩 중: skeleton (`animate-pulse`)
- 에러 시: "컬렉션 목록을 불러올 수 없습니다" + 재시도 버튼

**섹션 2: MetadataFilterEditor**

```
┌────────────────────────────────────────┐
│  메타데이터 필터                         │
│  ┌──────────┐  ┌──────────┐  [삭제]   │
│  │ department│  │ finance  │    ✕     │
│  └──────────┘  └──────────┘          │
│  ┌──────────┐  ┌──────────┐  [삭제]   │
│  │ category │  │ policy   │    ✕     │
│  └──────────┘  └──────────┘          │
│                                       │
│  [+ 필터 추가]                         │
│                                       │
│  💡 사용 가능한 키: department, category │
│     (키를 선택하면 샘플 값이 표시됩니다) │
└────────────────────────────────────────┘
```

- `useMetadataKeys(config.collection_name)` 훅으로 키/값 제안
- 키 입력: `<select>` 또는 자동완성 (사용 가능한 키 목록에서 선택)
- 값 입력: `<select>` (sample_values에서 선택) 또는 직접 입력
- "필터 추가" 버튼: 빈 key-value 행 추가
- "삭제" 버튼: 해당 행 제거
- 최대 10개 제한 (Policy 규칙)
- `config.metadata_filter` = `Record<string, string>` 업데이트

**섹션 3: SearchParamsControl**

```
┌────────────────────────────────────────┐
│  검색 파라미터                           │
│                                        │
│  검색 모드                              │
│  (●) 하이브리드  ( ) 벡터 전용  ( ) BM25 전용 │
│                                        │
│  결과 수 (top_k)                  [5]  │
│  ├──●──────────────────────────────┤   │
│  1                                20   │
└────────────────────────────────────────┘
```

- search_mode: 3개 라디오 버튼 (`hybrid` / `vector_only` / `bm25_only`)
- top_k: range 슬라이더 (min=1, max=20, step=1), 현재 값 표시
- 기존 Temperature 슬라이더와 동일한 스타일링 사용

**섹션 4: ToolIdentityEditor**

```
┌────────────────────────────────────────┐
│  도구 이름 및 설명 (LLM이 도구 선택 시 참고) │
│                                        │
│  도구 이름                              │
│  ┌──────────────────────────────────┐  │
│  │ 금융 정책 검색                    │  │
│  └──────────────────────────────────┘  │
│                                        │
│  도구 설명                              │
│  ┌──────────────────────────────────┐  │
│  │ 금융 관련 내부 정책 문서를 검색합니다. │  │
│  │ 금융 규제, 투자 정책 관련 질문에     │  │
│  │ 이 도구를 사용하세요.              │  │
│  └──────────────────────────────────┘  │
│  0/500                                 │
└────────────────────────────────────────┘
```

- tool_name: text input (maxLength=100)
- tool_description: textarea (maxLength=500), 글자 수 표시
- placeholder로 기본값 안내

#### 스타일링 규칙

- 기존 FormView의 스타일 패턴 준수:
  - 레이블: `text-[13px] font-semibold text-zinc-700`
  - 입력: `rounded-xl border border-zinc-300 ... focus:border-violet-400 focus:ring-2 focus:ring-violet-100`
  - 버튼(primary): `bg-violet-600 text-white rounded-xl`
  - 섹션 구분: `space-y-6`
- 전체 패널은 `rounded-2xl border border-violet-200 bg-violet-50/30 p-5` 으로 감싸서 일반 폼 필드와 구분

---

### 3-7. AgentBuilderPage 통합

**파일**: `src/pages/AgentBuilderPage/index.tsx`

#### 변경 1: import 추가

```typescript
import RagConfigPanel from '@/components/agent-builder/RagConfigPanel';
import type { RagToolConfig } from '@/types/ragToolConfig';
import { DEFAULT_RAG_CONFIG } from '@/types/ragToolConfig';
```

#### 변경 2: AgentFormData 확장

```typescript
interface AgentFormData {
  name: string;
  description: string;
  model: string;
  systemPrompt: string;
  tools: string[];
  temperature: number;
  toolConfigs: Record<string, RagToolConfig>;  // ← 추가
}

const DEFAULT_FORM: AgentFormData = {
  // ... 기존 필드 ...
  toolConfigs: {},  // ← 추가
};
```

#### 변경 3: 도구 토글 핸들러 확장

```typescript
const handleToolToggle = (toolId: string) => {
  setForm((prev) => {
    const isRemoving = prev.tools.includes(toolId);
    const newTools = isRemoving
      ? prev.tools.filter((t) => t !== toolId)
      : [...prev.tools, toolId];

    // RAG 도구 제거 시 config도 제거
    const newConfigs = { ...prev.toolConfigs };
    if (isRemoving && toolId === 'internal_document_search') {
      delete newConfigs[toolId];
    }
    // RAG 도구 추가 시 기본 config 설정
    if (!isRemoving && toolId === 'internal_document_search') {
      newConfigs[toolId] = { ...DEFAULT_RAG_CONFIG };
    }

    return { ...prev, tools: newTools, toolConfigs: newConfigs };
  });
};
```

#### 변경 4: FormView에서 RagConfigPanel 렌더링

`FormView`의 "도구 연결" 섹션 바로 아래에 조건부 렌더링:

```tsx
{/* 도구 연결 */}
<div>
  {/* ... 기존 도구 목록 ... */}
</div>

{/* RAG 도구 설정 — internal_document_search 선택 시에만 표시 */}
{form.tools.includes('internal_document_search') && (
  <RagConfigPanel
    config={form.toolConfigs['internal_document_search'] ?? DEFAULT_RAG_CONFIG}
    onChange={(config) =>
      onChange({
        ...form,
        toolConfigs: { ...form.toolConfigs, internal_document_search: config },
      })
    }
  />
)}
```

#### 변경 5: 저장 시 tool_configs 전달

`handleSave` (또는 실제 API 호출 시) `form.toolConfigs`를 `CreateAgentRequest.tool_configs`에 매핑:

```typescript
// API 요청 body 구성 시
const requestBody = {
  user_request: form.description,
  name: form.name,
  user_id: currentUser.id,
  llm_model_id: selectedModelId,
  temperature: form.temperature,
  tool_configs: Object.keys(form.toolConfigs).length > 0
    ? form.toolConfigs
    : undefined,
};
```

---

### 3-8. MSW 핸들러

**파일**: `src/__tests__/mocks/handlers.ts`

기존 handlers 배열에 추가:

```typescript
// RAG Tools — Collections
http.get(`*${API_ENDPOINTS.RAG_TOOL_COLLECTIONS}`, () =>
  HttpResponse.json({
    collections: [
      { name: 'documents', display_name: '전체 문서', vectors_count: 500 },
      { name: 'finance_docs', display_name: '금융 문서', vectors_count: 200 },
      { name: 'tech_manuals', display_name: '기술 매뉴얼', vectors_count: 150 },
    ],
  })
),

// RAG Tools — Metadata Keys
http.get(`*${API_ENDPOINTS.RAG_TOOL_METADATA_KEYS}`, () =>
  HttpResponse.json({
    keys: [
      { key: 'department', sample_values: ['finance', 'tech', 'hr'], value_count: 3 },
      { key: 'category', sample_values: ['policy', 'manual', 'report'], value_count: 3 },
      { key: 'year', sample_values: ['2024', '2025', '2026'], value_count: 3 },
    ],
  })
),
```

---

### 3-9. 훅 테스트

**파일**: `src/hooks/useRagToolConfig.test.ts` (신규)

```typescript
import { renderHook, waitFor } from '@testing-library/react';
import { beforeAll, afterEach, afterAll, describe, it, expect } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '@/__tests__/mocks/server';
import { useCollections, useMetadataKeys } from '@/hooks/useRagToolConfig';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import { API_ENDPOINTS } from '@/constants/api';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('useCollections', () => {
  it('컬렉션 목록을 반환한다', async () => {
    const { result } = renderHook(() => useCollections(), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(3);
    expect(result.current.data?.[0].name).toBe('documents');
  });

  it('API 실패 시 isError가 true가 된다', async () => {
    server.use(
      http.get(`*${API_ENDPOINTS.RAG_TOOL_COLLECTIONS}`, () =>
        HttpResponse.json({ detail: 'error' }, { status: 500 })
      )
    );
    const { result } = renderHook(() => useCollections(), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});

describe('useMetadataKeys', () => {
  it('컬렉션명 제공 시 메타데이터 키를 반환한다', async () => {
    const { result } = renderHook(() => useMetadataKeys('finance_docs'), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const keys = result.current.data?.map((k) => k.key);
    expect(keys).toContain('department');
    expect(keys).toContain('category');
  });

  it('컬렉션명 미제공 시 쿼리가 비활성된다', () => {
    const { result } = renderHook(() => useMetadataKeys(undefined), {
      wrapper: createWrapper(),
    });
    expect(result.current.fetchStatus).toBe('idle');
  });

  it('sample_values가 포함된다', async () => {
    const { result } = renderHook(() => useMetadataKeys('documents'), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const dept = result.current.data?.find((k) => k.key === 'department');
    expect(dept?.sample_values).toContain('finance');
  });
});
```

---

## 4. 백엔드 API 참조

### 4-1. GET /api/v1/rag-tools/collections

사용 가능한 Qdrant 컬렉션 목록.

**Response** `200`:
```json
{
  "collections": [
    { "name": "documents", "display_name": "전체 문서", "vectors_count": 500 },
    { "name": "finance_docs", "display_name": "금융 문서", "vectors_count": 200 }
  ]
}
```

### 4-2. GET /api/v1/rag-tools/metadata-keys

필터링 가능한 메타데이터 키 + 샘플 값.

**Query Params**: `collection_name` (optional)

**Response** `200`:
```json
{
  "keys": [
    { "key": "department", "sample_values": ["finance", "tech"], "value_count": 2 },
    { "key": "category", "sample_values": ["policy", "manual"], "value_count": 2 }
  ]
}
```

### 4-3. POST /api/v1/agents (기존 — tool_configs 추가)

에이전트 생성 시 `tool_configs` 필드로 RAG 설정 전달.

**Request body** (tool_configs 부분만):
```json
{
  "user_request": "...",
  "name": "...",
  "user_id": "...",
  "tool_configs": {
    "internal_document_search": {
      "collection_name": "finance_docs",
      "metadata_filter": { "department": "finance" },
      "top_k": 10,
      "search_mode": "vector_only",
      "rrf_k": 60,
      "tool_name": "금융 정책 검색",
      "tool_description": "금융 관련 내부 정책 문서를 검색합니다."
    }
  }
}
```

### 4-4. GET /api/v1/agents/tools (기존 — configurable 추가)

도구 목록에 `configurable`과 `config_schema` 필드가 추가됨.

**Response** (internal_document_search 항목):
```json
{
  "tool_id": "internal_document_search",
  "name": "내부 문서 검색",
  "description": "...",
  "configurable": true,
  "config_schema": {
    "collection_name": { "type": "string", "nullable": true },
    "metadata_filter": { "type": "object", "additionalProperties": { "type": "string" } },
    "top_k": { "type": "integer", "minimum": 1, "maximum": 20, "default": 5 },
    "search_mode": { "type": "string", "enum": ["hybrid", "vector_only", "bm25_only"], "default": "hybrid" },
    "rrf_k": { "type": "integer", "minimum": 1, "default": 60 },
    "tool_name": { "type": "string", "maxLength": 100 },
    "tool_description": { "type": "string", "maxLength": 500 }
  }
}
```

---

## 5. 구현 순서 (Checklist)

TDD 원칙: 각 단계에서 테스트를 먼저 작성한다.

### Step 1: 타입 + 상수 (의존성 없음)

- [ ] `src/types/ragToolConfig.ts` — 타입 + `DEFAULT_RAG_CONFIG`
- [ ] `src/constants/api.ts` — `RAG_TOOL_COLLECTIONS`, `RAG_TOOL_METADATA_KEYS` 추가
- [ ] `src/lib/queryKeys.ts` — `ragTools` 도메인 추가

### Step 2: 서비스 + 훅 (Step 1 이후)

- [ ] `src/services/ragToolService.ts` — API 호출
- [ ] `src/hooks/useRagToolConfig.ts` — `useCollections`, `useMetadataKeys`
- [ ] `src/__tests__/mocks/handlers.ts` — RAG Tools 핸들러 2개 추가
- [ ] `src/hooks/useRagToolConfig.test.ts` — 훅 테스트 (5개)

### Step 3: 컴포넌트 (Step 2 이후)

- [ ] `src/components/agent-builder/RagConfigPanel.tsx`
  - [ ] CollectionSelect 섹션
  - [ ] MetadataFilterEditor 섹션
  - [ ] SearchParamsControl 섹션
  - [ ] ToolIdentityEditor 섹션

### Step 4: 페이지 통합 (Step 3 이후)

- [ ] `AgentBuilderPage/index.tsx` — `AgentFormData.toolConfigs` 확장
- [ ] `AgentBuilderPage/index.tsx` — `handleToolToggle` 수정
- [ ] `AgentBuilderPage/index.tsx` — FormView에 `RagConfigPanel` 조건부 렌더링
- [ ] `AgentBuilderPage/index.tsx` — 저장 시 `tool_configs` 전달

### Step 5: 검증

- [ ] `npm run dev`로 개발 서버 실행
- [ ] 에이전트 생성 폼에서 `internal_document_search` 선택 → RagConfigPanel 표시 확인
- [ ] 컬렉션 드롭다운 로딩/선택 확인
- [ ] 메타데이터 필터 추가/삭제 동작 확인
- [ ] search_mode 라디오 전환 확인
- [ ] top_k 슬라이더 동작 확인
- [ ] tool_name/tool_description 입력 확인
- [ ] 도구 선택 해제 시 패널 숨김 + config 초기화 확인
- [ ] 저장 API 호출 시 `tool_configs` 포함 확인 (Network 탭)

---

## 6. 유의사항

### 6-1. 하위 호환

- `tool_configs`는 Optional — 기존 에이전트 생성 flow에 영향 없음
- RAG 도구 미선택 시 `tool_configs = undefined` (요청에 포함하지 않음)

### 6-2. 에러 처리

- 컬렉션 API 실패 → 드롭다운 대신 "불러올 수 없습니다" + 재시도 버튼
- 메타데이터 키 API 실패 → 수동 입력 모드로 전환 (자동완성 없이 자유 입력)

### 6-3. 스타일 일관성

- 기존 `AgentBuilderPage`의 FormView 스타일 100% 준수
- Tailwind 클래스명 규칙 유지 (violet 계열 accent, zinc 계열 neutral)
- 라디오/슬라이더는 Temperature 섹션과 동일한 패턴

### 6-4. 다중 RAG 도구 (향후 확장)

현재는 `internal_document_search` 1개만 config 지원.
다중 RAG 도구(같은 tool_id로 여러 개)는 Phase 2에서 구현 예정이므로,
`toolConfigs` 타입을 `Record<string, RagToolConfig>`으로 유지하되 UI에서는 1개만 표시.
