# Plan: LLM 모델 동적 조회 (llm-model)

## 1. 개요

| 항목 | 내용 |
|------|------|
| Feature ID | LLM-MODEL-FRONT-001 |
| 우선순위 | P1 |
| 난이도 | Low |
| 예상 소요 | 1~2시간 |

### 배경
AgentBuilderPage에서 모델 선택 UI가 하드코딩된 상수(`MODEL_LABELS`, `MODEL_COLORS`)로 구현되어 있다.
백엔드에 `GET /api/v1/llm-models` API가 구현되어 있으므로, 이를 활용하여 모델 목록을 동적으로 가져오도록 변경한다.

### 목표
- AgentBuilderPage의 모델 선택을 API 기반 동적 조회로 전환
- 모델 추가/비활성화 시 프론트엔드 코드 변경 없이 즉시 반영

---

## 2. API 스펙 (백엔드 참조)

### GET `/api/v1/llm-models`

| 항목 | 내용 |
|------|------|
| Method | GET |
| Auth | CurrentUser (인증 필요) |
| Query Param | `include_inactive` (boolean, 선택, 기본 `false`) |

**Response 200 OK:**
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

## 3. 구현 범위

### 3-1. 신규 파일

| 파일 | 설명 |
|------|------|
| `src/types/llmModel.ts` | `LlmModel`, `LlmModelListResponse` 타입 정의 |
| `src/services/llmModelService.ts` | `getLlmModels()` API 호출 함수 |
| `src/hooks/useLlmModels.ts` | TanStack Query 기반 `useLlmModels()` 훅 |

### 3-2. 수정 파일

| 파일 | 변경 내용 |
|------|----------|
| `src/constants/api.ts` | `LLM_MODELS: '/api/v1/llm-models'` 엔드포인트 추가 |
| `src/lib/queryKeys.ts` | `llmModels` 도메인 키 추가 |
| `src/pages/AgentBuilderPage/index.tsx` | 하드코딩된 `AgentModel` 타입, `MODEL_LABELS`, `MODEL_COLORS` 제거 → `useLlmModels()` 훅으로 대체 |

### 3-3. 테스트 파일

| 파일 | 설명 |
|------|------|
| `src/hooks/useLlmModels.test.ts` | 훅 단위 테스트 (MSW 기반) |
| `src/__tests__/mocks/handlers.ts` | LLM Models 핸들러 추가 |

---

## 4. 상세 구현 계획

### Step 1: 타입 정의 (`src/types/llmModel.ts`)

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

### Step 2: API 엔드포인트 등록 (`src/constants/api.ts`)

```typescript
// LLM Models
LLM_MODELS: '/api/v1/llm-models',
```

### Step 3: 쿼리 키 등록 (`src/lib/queryKeys.ts`)

```typescript
llmModels: {
  all: ['llmModels'] as const,
  list: (includeInactive?: boolean) =>
    [...queryKeys.llmModels.all, 'list', { includeInactive }] as const,
},
```

### Step 4: 서비스 함수 (`src/services/llmModelService.ts`)

- `getLlmModels(includeInactive?: boolean)` → axios GET 호출
- 인증 필요 시 `authClient` 사용, 공개 시 `client` 사용 (API 문서상 CurrentUser → `authClient`)

### Step 5: TanStack Query 훅 (`src/hooks/useLlmModels.ts`)

- `useLlmModels(includeInactive?: boolean)` → `useQuery` 래핑
- staleTime: 5분 (모델 목록은 자주 변경되지 않음)
- 반환: `{ data, isLoading, isError, refetch }`

### Step 6: AgentBuilderPage 수정

**제거 대상:**
- `type AgentModel` 유니온 타입
- `MODEL_LABELS` 상수
- `MODEL_COLORS` 상수

**변경 사항:**
- `AgentFormData.model` 타입: `AgentModel` → `string` (서버에서 `model_name` 사용)
- 모델 선택 UI: 하드코딩 버튼 → `useLlmModels()` 데이터 기반 동적 렌더링
- 로딩/에러 상태 처리 (도구 연결 섹션과 동일한 패턴)
- `is_default` 모델을 기본 선택으로 사용
- 모델 카드에 `provider` 기반 색상 매핑 (동적)

### Step 7: AgentCard 모델 배지 수정

- `MODEL_COLORS[agent.model]` → provider 기반 동적 색상 또는 모델 목록에서 lookup
- `MODEL_LABELS[agent.model]` → `display_name` 사용

---

## 5. UI/UX 고려사항

| 상태 | 처리 방식 |
|------|----------|
| 로딩 중 | 모델 선택 영역에 스켈레톤 UI (4칸 그리드) |
| 에러 | "모델 목록을 불러올 수 없습니다" + 재시도 버튼 |
| 빈 목록 | "등록된 모델이 없습니다" 안내 |
| 기본 모델 | `is_default: true`인 모델을 폼 초기값으로 설정 |

---

## 6. Provider 기반 색상 매핑

하드코딩된 `MODEL_COLORS`를 대체하기 위해 provider 기반 동적 색상을 사용한다.

```typescript
const PROVIDER_COLORS: Record<string, string> = {
  openai: 'bg-emerald-100 text-emerald-700',
  anthropic: 'bg-violet-100 text-violet-700',
};
const DEFAULT_COLOR = 'bg-zinc-100 text-zinc-700';
```

---

## 7. 구현 순서 (TDD)

```
1. types/llmModel.ts          → 타입 정의
2. constants/api.ts            → 엔드포인트 추가
3. lib/queryKeys.ts            → 쿼리 키 추가
4. __tests__/mocks/handlers.ts → MSW 핸들러 추가
5. hooks/useLlmModels.test.ts  → 훅 테스트 작성 (Red)
6. services/llmModelService.ts → 서비스 구현
7. hooks/useLlmModels.ts       → 훅 구현 (Green)
8. AgentBuilderPage/index.tsx  → 페이지 수정 (Refactor)
```

---

## 8. 범위 외 (Out of Scope)

- 모델 CRUD (등록/수정/삭제) — Admin 전용, 별도 기능으로 분리
- 모델별 max_tokens 제한 적용 — 추후 Agent 실행 시 적용
- 모델 사용 통계/요금 표시
