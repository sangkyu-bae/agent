# Design: LLM 모델 동적 조회 (llm-model)

## 1. 개요

| 항목 | 내용 |
|------|------|
| Feature ID | LLM-MODEL-FRONT-001 |
| Plan 참조 | `docs/01-plan/features/llm-model.plan.md` |
| 백엔드 API 참조 | `docs/api/llm_model.md` |
| 난이도 | Low |

### 목적
AgentBuilderPage의 하드코딩된 모델 목록(`AgentModel`, `MODEL_LABELS`, `MODEL_COLORS`)을 제거하고,
백엔드 `GET /api/v1/llm-models` API를 통해 동적으로 모델을 조회하도록 전환한다.

---

## 2. API 스펙

### GET `/api/v1/llm-models`

| 항목 | 값 |
|------|-----|
| Method | GET |
| Auth | CurrentUser (인증 필요 → `authClient` 사용) |
| Query Param | `include_inactive?: boolean` (기본 `false`) |

**Response 200:**
```json
{
  "models": [
    {
      "id": "uuid-string",
      "provider": "openai",
      "model_name": "gpt-4o",
      "display_name": "GPT-4o",
      "description": "OpenAI GPT-4o model",
      "max_tokens": null,
      "is_active": true,
      "is_default": true
    }
  ]
}
```

---

## 3. 타입 설계

### 3-1. `src/types/llmModel.ts`

```typescript
export interface LlmModel {
  id: string;
  provider: string;
  model_name: string;
  display_name: string;
  description: string | null;
  max_tokens: number | null;
  is_active: boolean;
  is_default: boolean;
}

export interface LlmModelListResponse {
  models: LlmModel[];
}
```

---

## 4. 상수/키 설계

### 4-1. API 엔드포인트 (`src/constants/api.ts`)

```typescript
// LLM Models
LLM_MODELS: '/api/v1/llm-models',
```

### 4-2. 쿼리 키 (`src/lib/queryKeys.ts`)

```typescript
llmModels: {
  all: ['llmModels'] as const,
  list: (includeInactive?: boolean) =>
    [...queryKeys.llmModels.all, 'list', { includeInactive }] as const,
},
```

---

## 5. 서비스 설계

### 5-1. `src/services/llmModelService.ts`

```typescript
import { authClient } from '@/services/api/authClient';
import { API_ENDPOINTS } from '@/constants/api';
import type { LlmModelListResponse } from '@/types/llmModel';

export const llmModelService = {
  getLlmModels: async (includeInactive = false): Promise<LlmModelListResponse> => {
    const { data } = await authClient.get<LlmModelListResponse>(
      API_ENDPOINTS.LLM_MODELS,
      { params: { include_inactive: includeInactive } }
    );
    return data;
  },
};
```

**설계 결정:**
- 인증 필요 API이므로 `authClient` 사용 (Bearer 토큰 자동 주입)
- `includeInactive` 파라미터는 기본 `false`로 활성 모델만 조회

---

## 6. 훅 설계

### 6-1. `src/hooks/useLlmModels.ts`

```typescript
import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { llmModelService } from '@/services/llmModelService';

export const useLlmModels = (includeInactive = false) => {
  return useQuery({
    queryKey: queryKeys.llmModels.list(includeInactive),
    queryFn: () => llmModelService.getLlmModels(includeInactive),
    staleTime: 5 * 60 * 1000,
    select: (data) => data.models,
  });
};
```

**설계 결정:**
- `staleTime: 5분` — 모델 목록은 자주 변경되지 않음
- `select: (data) => data.models` — 컴포넌트에서 `data`로 바로 `LlmModel[]` 접근

---

## 7. Provider 색상 매핑

하드코딩된 `MODEL_COLORS`를 provider 기반 동적 색상으로 대체한다.

```typescript
const PROVIDER_COLORS: Record<string, string> = {
  openai: 'bg-emerald-100 text-emerald-700',
  anthropic: 'bg-violet-100 text-violet-700',
};
const DEFAULT_PROVIDER_COLOR = 'bg-zinc-100 text-zinc-700';

const getProviderColor = (provider: string): string =>
  PROVIDER_COLORS[provider] ?? DEFAULT_PROVIDER_COLOR;
```

**위치:** `AgentBuilderPage/index.tsx` 내부 상수 (별도 파일 분리 불필요)

---

## 8. AgentBuilderPage 변경 설계

### 8-1. 제거 대상

| 항목 | 현재 위치 |
|------|----------|
| `type AgentModel` | `AgentBuilderPage/index.tsx:7` |
| `MODEL_LABELS` | `AgentBuilderPage/index.tsx:31-36` |
| `MODEL_COLORS` | `AgentBuilderPage/index.tsx:38-43` |

### 8-2. 타입 변경

```diff
 interface AgentFormData {
   name: string;
   description: string;
-  model: AgentModel;
+  model: string;        // model_name from API
   systemPrompt: string;
   tools: string[];
   temperature: number;
 }
```

### 8-3. 모델 선택 UI 변경

**현재:** 하드코딩된 4개 모델 버튼
**변경 후:** `useLlmModels()` 훅으로 동적 렌더링

```tsx
const { data: models, isLoading: modelsLoading, isError: modelsError } = useLlmModels();

// 기본 모델 설정 (초기값)
useEffect(() => {
  if (models && !formData.model) {
    const defaultModel = models.find(m => m.is_default);
    if (defaultModel) {
      setFormData(prev => ({ ...prev, model: defaultModel.model_name }));
    }
  }
}, [models]);
```

### 8-4. 상태별 UI 처리

| 상태 | UI |
|------|-----|
| 로딩 중 | 스켈레톤 블록 (4칸 그리드, `animate-pulse`) |
| 에러 | "모델 목록을 불러올 수 없습니다" + 재시도 버튼 |
| 빈 목록 | "등록된 모델이 없습니다" 안내 |
| 정상 | provider 기반 색상의 모델 카드 그리드 |

### 8-5. AgentCard 모델 배지

```diff
- <span className={`... ${MODEL_COLORS[agent.model]}`}>
-   {MODEL_LABELS[agent.model]}
+ <span className={`... ${getProviderColor(modelInfo?.provider ?? '')}`}>
+   {modelInfo?.display_name ?? agent.model}
```

- `models` 배열에서 `agent.model`(= `model_name`)로 lookup하여 `display_name`, `provider` 획득
- lookup 실패 시 `agent.model` 문자열을 fallback으로 표시

---

## 9. 테스트 설계

### 9-1. MSW 핸들러 (`src/__tests__/mocks/handlers.ts`)

```typescript
http.get(`*${API_ENDPOINTS.LLM_MODELS}`, () =>
  HttpResponse.json({
    models: [
      {
        id: 'uuid-1',
        provider: 'openai',
        model_name: 'gpt-4o',
        display_name: 'GPT-4o',
        description: 'OpenAI GPT-4o model',
        max_tokens: null,
        is_active: true,
        is_default: true,
      },
      {
        id: 'uuid-2',
        provider: 'anthropic',
        model_name: 'claude-sonnet-4-6',
        display_name: 'Claude Sonnet 4.6',
        description: 'Anthropic Claude Sonnet',
        max_tokens: null,
        is_active: true,
        is_default: false,
      },
    ],
  })
),
```

### 9-2. 훅 테스트 (`src/hooks/useLlmModels.test.ts`)

| 테스트 케이스 | 검증 내용 |
|-------------|----------|
| 모델 목록 조회 성공 | `data` 배열 반환, `isSuccess === true` |
| `select`로 `models` 추출 | `data`가 `LlmModel[]` 형태인지 확인 |
| 로딩 상태 | 초기 `isLoading === true` |
| 에러 처리 | 500 응답 시 `isError === true` |

---

## 10. 구현 순서 (TDD)

```
1. src/types/llmModel.ts              → 타입 정의
2. src/constants/api.ts               → LLM_MODELS 엔드포인트 추가
3. src/lib/queryKeys.ts               → llmModels 쿼리 키 추가
4. src/__tests__/mocks/handlers.ts    → MSW 핸들러 추가
5. src/hooks/useLlmModels.test.ts     → 훅 테스트 작성 (Red)
6. src/services/llmModelService.ts    → 서비스 구현
7. src/hooks/useLlmModels.ts          → 훅 구현 (Green)
8. src/pages/AgentBuilderPage/index.tsx → 페이지 리팩토링 (Refactor)
```

---

## 11. 파일 변경 매트릭스

| 파일 | 작업 | 신규/수정 |
|------|------|----------|
| `src/types/llmModel.ts` | 타입 정의 | 신규 |
| `src/constants/api.ts` | `LLM_MODELS` 추가 | 수정 |
| `src/lib/queryKeys.ts` | `llmModels` 키 추가 | 수정 |
| `src/services/llmModelService.ts` | API 호출 함수 | 신규 |
| `src/hooks/useLlmModels.ts` | TanStack Query 훅 | 신규 |
| `src/hooks/useLlmModels.test.ts` | 훅 단위 테스트 | 신규 |
| `src/__tests__/mocks/handlers.ts` | MSW 핸들러 추가 | 수정 |
| `src/pages/AgentBuilderPage/index.tsx` | 하드코딩 제거 + 동적 조회 | 수정 |

---

## 12. 범위 외 (Out of Scope)

- 모델 CRUD 관리 (Admin 전용, 별도 기능)
- 모델별 `max_tokens` 제한 적용
- 모델 사용 통계/요금 표시
- 다른 페이지에서의 모델 선택 (현재 AgentBuilderPage만 대상)
