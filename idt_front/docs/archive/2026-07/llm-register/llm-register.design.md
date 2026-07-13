---
template: design
version: 1.0
feature: llm-register
date: 2026-07-11
author: 배상규
project: idt_front
---

# llm-register Design Document

> **Summary**: 백엔드에 기 구현된 LLM 모델 CRUD + 가격 관리 API 6종(`/api/v1/llm-models/*`)을 프론트에 연동하여 `/admin/llm-models` 어드민 관리 페이지를 신설한다. 목록 테이블 + 등록/수정 모달 + 가격 변경 모달 + 비활성화 확인 다이얼로그, admin 네비게이션 항목 추가.
>
> **Project**: idt_front
> **Author**: 배상규
> **Date**: 2026-07-11
> **Status**: Draft
> **Planning Doc**: [llm-register.plan.md](../../01-plan/features/llm-register.plan.md)
> **API Doc**: [docs/api/llm-register.md](../../api/llm-register.md)

---

## 1. Overview

### 1.1 Design Goals

- 백엔드 6종 엔드포인트를 프론트 서비스/훅 레이어에 1:1로 연동한다 (백엔드 변경 없음).
- 기존 조회 전용 자산(`llmModelService.getLlmModels`, `useLlmModels`)의 **시그니처를 변경하지 않고** 확장한다 — 에이전트 빌더 소비처(`ModelSettingsModal`, `SubAgentManagerModal`, `LeftConfigPanel` 등) 회귀 방지.
- 어드민 UI는 기존 `AdminMcpServersPage` 패턴(공통 `Modal` 폼 + `ConfirmDialog` + 인라인 에러)을 답습해 admin 영역 일관성을 유지한다.
- 뮤테이션 성공 시 `queryKeys.llmModels.all` invalidate → 어드민 목록과 에이전트 빌더 모델 선택이 동시에 갱신된다.

### 1.2 Design Principles

- **API 계약 우선**: 타입은 백엔드 `src/application/llm_model/schemas.py`와 1:1. 가격 필드는 JSON 직렬화 결과인 **문자열**(`"0.0025"`)로 수신, 전송 시 number.
- **Write-only 시크릿**: `api_key_env`는 등록 요청에만 존재(응답 미노출) → 수정 모달에서 미노출.
- **서버가 진실**: `is_default` 자동 해제 등 서버 처리 결과를 낙관적 업데이트 없이 invalidate 재조회로 반영.
- **Soft delete**: 비활성화는 되돌릴 수 있음(수정 모달 `is_active` 토글)을 UI에 명시.

---

## 2. Architecture

### 2.1 Component / Layer Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│ AdminLlmModelsPage (/admin/llm-models, AdminRoute 가드)          │
│  ├─ 헤더: 타이틀 + "비활성 포함" 토글 + [모델 등록] 버튼         │
│  ├─ LlmModelTable (페이지 내 프레젠테이션 분리)                  │
│  ├─ LlmModelFormModal   (등록/수정 겸용, Modal size="lg")        │
│  ├─ LlmModelPricingModal (가격 변경, Modal size="sm")            │
│  └─ ConfirmDialog        (비활성화, variant="danger")            │
└──────┬───────────────────────────────────────────────────────────┘
       │ hooks (TanStack Query)
       ▼
┌──────────────────────────────────────────────────────────────────┐
│ useLlmModels(includeInactive)            [기존 — 불변]           │
│ useCreateLlmModel / useUpdateLlmModel                            │
│ useUpdateLlmModelPricing / useDeactivateLlmModel   [신규 4종]    │
│   onSuccess → invalidateQueries(queryKeys.llmModels.all)         │
└──────┬───────────────────────────────────────────────────────────┘
       │ services
       ▼
┌──────────────────────────────────────────────────────────────────┐
│ llmModelService (authClient — Bearer 주입 + 401 자동 갱신)       │
│   getLlmModels / getLlmModel / createLlmModel /                  │
│   updateLlmModel / updateLlmModelPricing / deactivateLlmModel    │
└──────┬───────────────────────────────────────────────────────────┘
       ▼
  /api/v1/llm-models/*  (백엔드 기 구현 — admin 권한은 서버 검증)
```

### 2.2 Data Flow (대표 시나리오)

```
[등록] 모델 등록 버튼 → FormModal(create 모드) → POST /api/v1/llm-models
  → 201: invalidate(llmModels.all) → 테이블 갱신 + 모달 닫기
  → 409: 모달 내 인라인 에러 "이미 등록된 모델입니다" (detail 표시)
  → 422: 모달 내 인라인 에러 (detail 표시)

[가격] 행 "가격" 버튼 → PricingModal(현재 단가 프리필) → 클라이언트 검증(≥0)
  → PATCH /{id}/pricing → 200: invalidate → pricing_updated_at 갱신 표시

[비활성화] 행 "비활성화" 버튼 → ConfirmDialog(참조 실패 경고)
  → DELETE /{id} → 200(is_active=false): invalidate
  → 비활성 행은 include_inactive=true일 때만 목록에 잔류(흐림 처리)
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `AdminLlmModelsPage` | `useLlmModels`, 뮤테이션 훅 4종, `Modal`, `ConfirmDialog` | 페이지 조립 |
| 뮤테이션 훅 | `llmModelService`, `queryKeys.llmModels` | 서버 상태 갱신 |
| `llmModelService` | `authClient`, `API_ENDPOINTS` | HTTP 호출 |
| `adminNav.ts` | (없음) | 네비 단일 소스 |

---

## 3. Data Model

### 3.1 타입 확장 (`src/types/llmModel.ts`)

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
  // LLM-MODEL-REG-002: self-host 엔드포인트(vLLM 등). null이면 provider 기본값.
  base_url?: string | null;
  // AGENT-OBS M4: 토큰 단가 — 백엔드 Decimal이 JSON 문자열로 직렬화됨 ("0.0025")
  input_price_per_1k_usd?: string | null;
  output_price_per_1k_usd?: string | null;
  pricing_updated_at?: string | null;
}

export interface LlmModelListResponse {
  models: LlmModel[];
}

/** POST /api/v1/llm-models — api_key_env는 등록 시에만 전달(write-only) */
export interface CreateLlmModelRequest {
  provider: string;            // max 50
  model_name: string;          // max 150
  display_name: string;        // max 150
  description?: string | null;
  api_key_env: string;         // max 100, 필수
  max_tokens?: number | null;
  is_active?: boolean;         // 기본 true
  is_default?: boolean;        // 기본 false
  base_url?: string | null;    // max 500
}

/** PATCH /api/v1/llm-models/{id} — provider/model_name/api_key_env 수정 불가 */
export interface UpdateLlmModelRequest {
  display_name?: string;
  description?: string | null;
  max_tokens?: number | null;
  is_active?: boolean;
  is_default?: boolean;
  base_url?: string | null;
}

/** PATCH /api/v1/llm-models/{id}/pricing — 전송은 number, 수신은 string */
export interface UpdateLlmModelPricingRequest {
  input_price_per_1k_usd: number;   // ≥ 0
  output_price_per_1k_usd: number;  // ≥ 0
}

/** 등록 모달 provider 셀렉트 옵션 (as const 패턴) */
export const LLM_PROVIDER = {
  OPENAI: 'openai',
  ANTHROPIC: 'anthropic',
  OLLAMA: 'ollama',
  PERPLEXITY: 'perplexity',
} as const;
export type LlmProvider = (typeof LLM_PROVIDER)[keyof typeof LLM_PROVIDER];
```

> 기존 필드는 optional 추가만 하므로 기존 소비처(빌더)의 타입 호환이 유지된다.

### 3.2 엔드포인트 상수 (`src/constants/api.ts`)

```typescript
// LLM Models
LLM_MODELS: '/api/v1/llm-models',                                        // 기존
LLM_MODEL_DETAIL: (id: string) => `/api/v1/llm-models/${id}`,            // 신규
LLM_MODEL_PRICING: (id: string) => `/api/v1/llm-models/${id}/pricing`,   // 신규
```

### 3.3 쿼리 키 (`src/lib/queryKeys.ts`)

```typescript
llmModels: {
  all: ['llmModels'] as const,
  list: (includeInactive?: boolean) =>
    [...queryKeys.llmModels.all, 'list', { includeInactive }] as const,
  detail: (id: string) => [...queryKeys.llmModels.all, 'detail', id] as const,  // 신규
},
```

---

## 4. API Integration

### 4.1 서비스 (`src/services/llmModelService.ts`)

```typescript
export const llmModelService = {
  getLlmModels: async (includeInactive = false): Promise<LlmModelListResponse> => { /* 기존 불변 */ },

  getLlmModel: async (id: string): Promise<LlmModel> => {
    const { data } = await authApiClient.get<LlmModel>(API_ENDPOINTS.LLM_MODEL_DETAIL(id));
    return data;
  },

  createLlmModel: async (req: CreateLlmModelRequest): Promise<LlmModel> => {
    const { data } = await authApiClient.post<LlmModel>(API_ENDPOINTS.LLM_MODELS, req);
    return data;
  },

  updateLlmModel: async (id: string, req: UpdateLlmModelRequest): Promise<LlmModel> => {
    const { data } = await authApiClient.patch<LlmModel>(API_ENDPOINTS.LLM_MODEL_DETAIL(id), req);
    return data;
  },

  updateLlmModelPricing: async (id: string, req: UpdateLlmModelPricingRequest): Promise<LlmModel> => {
    const { data } = await authApiClient.patch<LlmModel>(API_ENDPOINTS.LLM_MODEL_PRICING(id), req);
    return data;
  },

  deactivateLlmModel: async (id: string): Promise<LlmModel> => {
    const { data } = await authApiClient.delete<LlmModel>(API_ENDPOINTS.LLM_MODEL_DETAIL(id));
    return data;
  },
};
```

### 4.2 뮤테이션 훅 (`src/hooks/useLlmModels.ts`에 추가 — useMcpServers 패턴)

```typescript
export const useCreateLlmModel = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateLlmModelRequest) => llmModelService.createLlmModel(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.llmModels.all }),
  });
};

export const useUpdateLlmModel = () => { /* ({ id, data }) 시그니처, 동일 invalidate */ };
export const useUpdateLlmModelPricing = () => { /* ({ id, data }) 시그니처, 동일 invalidate */ };
export const useDeactivateLlmModel = () => { /* (id) 시그니처, 동일 invalidate */ };
```

> invalidate 키는 `llmModels.all` — `list(false)`(빌더)와 `list(true)`(어드민 토글) 모두 무효화된다.

### 4.3 에러 매핑

| HTTP | 발생 지점 | UI 처리 |
|------|----------|---------|
| 409 | POST (provider+model_name 중복) | FormModal 인라인 에러 — `ApiError.message`(백엔드 detail) 표시 |
| 422 | POST/PATCH pricing (검증 실패) | 해당 모달 인라인 에러 (`ApiError.message`) |
| 404 | 단건/수정/가격/비활성화 | 모달·다이얼로그 인라인 에러 + invalidate(목록 동기화) |
| 401/403 | 전 요청 | `authClient` 공통 처리(갱신/리다이렉트) — 페이지 추가 처리 없음 |

> `authClient` 응답 인터셉터는 FastAPI `detail`을 `ApiError(message, status)`로 정규화한다
> (`src/services/api/authClient.ts:59-67`). 페이지에서는 axios 에러 파싱 없이 아래 유틸을 쓴다:

```typescript
const getErrorMessage = (err: unknown, fallback: string): string =>
  err instanceof Error && err.message ? err.message : fallback;
```

---

## 5. UI/UX Design

### 5.1 페이지 레이아웃

`AdminLayout`의 `<main>`은 자체 스크롤(`overflowY: auto`)을 제공하므로 (AgentChatLayout의 패턴 A 불필요),
기존 admin 페이지(AdminMcpServersPage 등) 관례대로 단순 래퍼를 사용한다.

```
┌─ AdminLayout <main> (overflowY: auto, bg #fff) ─────────────────────┐
│  mx-auto max-w-7xl px-6 py-8                                         │
│ ┌─ 헤더 (mb-6 flex items-start justify-between) ──────────────────┐ │
│ │ Admin (uppercase violet 레이블)                                  │ │
│ │ LLM 모델 관리 (text-3xl font-bold)   [□ 비활성 포함] [+ 모델 등록]│ │
│ │ 보조 설명 (text-[13px] text-zinc-400)                            │ │
│ └──────────────────────────────────────────────────────────────────┘ │
│ ┌─ 테이블 (overflow-hidden rounded-2xl border border-zinc-200) ───┐ │
│ │ 표시명 | Provider | 모델명 | 상태 | 입력단가 | 출력단가 |       │ │
│ │ Base URL | 액션(수정·가격·비활성화)                              │ │
│ └──────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────┘
```

### 5.2 테이블 컬럼 사양

| 컬럼 | 표시 규칙 |
|------|----------|
| 표시명 | `display_name` (font-medium). `is_default=true`면 우측에 violet 배지 `기본` |
| Provider | `provider` 소문자 그대로, `text-[12px]` zinc 칩 |
| 모델명 | `model_name`, `font-mono text-[13px] text-zinc-500` |
| 상태 | `is_active`: emerald 칩 `활성` / zinc 칩 `비활성`. 비활성 행 전체 `opacity-50` |
| 입력 단가 | `input_price_per_1k_usd` — `$0.0025 /1K`. null이면 amber 칩 `미설정` |
| 출력 단가 | 동일 규칙 |
| base_url | 설정 시 `font-mono text-[12px]` 말줄임(`max-w-[160px] truncate`, title 속성으로 전체), null이면 `–` |
| 액션 | Ghost 버튼 3개: `수정` / `가격` / `비활성화`(red hover). 비활성 모델은 `비활성화` 버튼 미노출 |

빈 상태: "등록된 LLM 모델이 없습니다" + 중앙 등록 버튼. 로딩: 스피너. 조회 에러: red 배너 + 재시도 버튼.

### 5.3 LlmModelFormModal (등록/수정 겸용 — McpServerFormModal 패턴)

| 항목 | 등록 모드 | 수정 모드 |
|------|----------|----------|
| 타이틀 | "LLM 모델 등록" | "LLM 모델 수정" |
| provider | 셀렉트 (openai/anthropic/ollama/perplexity), 필수 | 읽기 전용 표시 (zinc-100 배경 비활성 input) |
| model_name | text, 필수, max 150 | 읽기 전용 표시 |
| display_name | text, 필수, max 150 | 편집 가능 |
| api_key_env | text, 필수, max 100, placeholder "예: OPENAI_API_KEY" + 힌트 "키 값이 아닌 서버 환경변수명입니다" | **미노출** (응답에 없음) |
| description | textarea, 선택 | 편집 가능 |
| max_tokens | number, 선택 (빈 값 → null) | 편집 가능 |
| base_url | text, 선택, max 500, 힌트 "self-host(vLLM 등) 엔드포인트. 비우면 provider 기본값" | 편집 가능 |
| is_active | 체크박스 (기본 on) | 편집 가능 — 비활성 모델 재활성화 경로 |
| is_default | 체크박스 + 힌트 "지정 시 기존 기본 모델은 자동 해제됩니다" | 편집 가능 |
| 가격 안내 | 하단 안내문 "가격은 등록 후 '가격' 버튼으로 설정합니다" | (없음) |
| footer | 취소 / 등록(isPending 스피너) | 취소 / 저장 |

- `Modal size="lg"`, `scroll="content"`. 모달 열림 시 1회 초기화 패턴(`initialized` 플래그) 사용.
- 클라이언트 검증: 필수 필드 공백 검사 → 인라인 에러. 제출 시 `setError(null)` 후 뮤테이션.
- 수정 모드 제출 바디는 편집 가능 필드만 포함(`UpdateLlmModelRequest`).

### 5.4 LlmModelPricingModal

- `Modal size="sm"`, 타이틀 "가격 설정", 서브타이틀 `{display_name} · 1,000 토큰당 USD`.
- 필드 2개: 입력 단가 / 출력 단가 — `<input type="number" min="0" step="0.0001">`, 현재값 프리필(문자열 → 그대로 value).
- 하단 메타: `pricing_updated_at` 존재 시 "최종 변경: {formatDate(...)}" (기존 `formatters.ts` 사용).
- 클라이언트 검증: 빈 값·NaN·음수 → 인라인 에러 "0 이상의 숫자를 입력하세요" (전송 차단).
- 전송: `parseFloat` 후 number로 `PATCH /{id}/pricing`. 성공 시 모달 닫기 (비용 캐시 무효화는 서버 처리).
- footer: 취소 / 저장.

### 5.5 비활성화 ConfirmDialog

```tsx
<ConfirmDialog
  isOpen={!!deactivateTarget}
  variant="danger"
  title="모델 비활성화"
  description={
    <>
      <b>{deactivateTarget?.display_name}</b> 모델을 비활성화합니다.
      이 모델을 참조 중인 에이전트 실행·문서 요약 작업은 실행 시점에 실패할 수 있습니다.
      비활성화 후에도 수정에서 다시 활성화할 수 있습니다.
    </>
  }
  confirmLabel="비활성화"
  isPending={deactivateMutation.isPending}
  error={deactivateError}
  onConfirm={...} onClose={...}
/>
```

### 5.6 네비게이션 (`src/constants/adminNav.ts`)

`ADMIN_NAV_ITEMS`에 항목 추가 (배치: "Agent Run 관측" 다음, "MCP 서버" 앞):

```typescript
{
  label: 'LLM 모델',
  path: '/admin/llm-models',
  // Heroicons outline 'cpu-chip'
  icon: 'M8.25 3v1.5M4.5 8.25H3m18 0h-1.5M4.5 12H3m18 0h-1.5m-15 3.75H3m18 0h-1.5M8.25 19.5V21M12 3v1.5m0 15V21m3.75-18v1.5m0 15V21m-9-1.5h10.5a2.25 2.25 0 0 0 2.25-2.25V6.75a2.25 2.25 0 0 0-2.25-2.25H6.75A2.25 2.25 0 0 0 4.5 6.75v10.5a2.25 2.25 0 0 0 2.25 2.25Zm.75-12h9v9h-9v-9Z',
  description: 'LLM 모델 등록·수정·가격·비활성화 관리',
},
```

→ `AdminLayout` 사이드바·`TopNav` "관리" 드롭다운에 자동 반영 (단일 소스).

### 5.7 라우트 (`src/App.tsx`)

```tsx
// AdminRoute > AdminLayout 하위, /admin/mcp-servers 인근
<Route path="/admin/llm-models" element={<AdminLlmModelsPage />} />
```

---

## 6. Error / Edge Cases

| 케이스 | 처리 |
|--------|------|
| 가격 문자열 표시 | `"0.0025"` → `$0.0025` 그대로 표기 (parseFloat 후 toFixed 강제하지 않음 — 백엔드 자릿수 보존) |
| 가격 프리필 후 무변경 저장 | 정상 동작 (동일 값 PATCH 허용, `pricing_updated_at`만 갱신) |
| 기본 모델을 비활성화 | 서버가 `is_default=false` 처리 → invalidate로 반영. 기본 모델 부재 상태 허용(서버 정책) |
| include_inactive 토글 중 로딩 | 토글 즉시 쿼리 키 변경(`list(true)`) → `isFetching` 동안 테이블 유지 + 우측 상단 미세 스피너 |
| 404 (타 관리자가 이미 삭제 등) | 인라인 에러 + invalidate로 목록 재동기화 |
| max_tokens 빈 문자열 | `null`로 정규화 후 전송 |
| base_url 공백 문자열 | `trim()` 후 빈 값이면 `null` 전송 |
| 목록의 비활성 모델 노출 | 기본 조회는 `include_inactive=false`(활성만). 토글 시에만 비활성 포함 |

---

## 7. Security Considerations

- [x] `api_key_env`는 **환경변수명만** 다루며 키 값은 프론트에 존재하지 않음. 힌트 문구로 오입력(실제 키 붙여넣기) 방지 안내.
- [x] admin 권한은 서버 `require_role("admin")`이 최종 방어선. 프론트 `AdminRoute`는 UX 레이어.
- [x] 모든 요청은 `authClient`(Bearer 주입) 경유 — 공개 `client` 사용 금지.

---

## 8. Test Plan

### 8.1 MSW 핸들러 추가 (`src/__tests__/mocks/handlers.ts`)

기존 `GET *${API_ENDPOINTS.LLM_MODELS}` 핸들러의 mock 모델에 가격 필드 3종 추가 + 신규 4종:

| 핸들러 | 응답 |
|--------|------|
| `http.post('*/api/v1/llm-models')` | 201 + 생성 모델. `model_name === 'dup-model'`이면 409 `{detail: '이미 등록된 모델입니다'}` |
| `http.patch('*/api/v1/llm-models/:id')` | 200 + 병합 모델. `id === 'not-found'`면 404 |
| `http.patch('*/api/v1/llm-models/:id/pricing')` | 200 + 가격/`pricing_updated_at` 갱신 모델 |
| `http.delete('*/api/v1/llm-models/:id')` | 200 + `is_active:false` 모델 |

> 경로 매처는 파라미터 사용을 위해 리터럴 패턴(`'*/api/v1/llm-models/:id'`)으로 등록한다.
> 테스트 파일은 MSW 전역 setup이 없으므로 `server.listen/resetHandlers/close` 3종 훅을 파일 내 직접 선언한다.

### 8.2 훅 테스트 (`src/hooks/useLlmModels.test.ts` 확장)

| # | 케이스 | 검증 |
|---|--------|------|
| H1 | (기존) 목록 조회 | 그린 유지 |
| H2 | `useCreateLlmModel` 성공 | 반환 모델 확인 + 목록 쿼리 invalidate(refetch 발생) |
| H3 | `useCreateLlmModel` 409 | `isError` + detail 메시지 접근 가능 |
| H4 | `useUpdateLlmModel` 성공 | 변경 필드 반영 |
| H5 | `useUpdateLlmModelPricing` 성공 | 가격 문자열·`pricing_updated_at` 반영 |
| H6 | `useDeactivateLlmModel` 성공 | `is_active:false` 반환 |

### 8.3 페이지 테스트 (`src/pages/AdminLlmModelsPage/index.test.tsx`)

| # | 케이스 | 검증 |
|---|--------|------|
| P1 | 목록 렌더 | 모델명·상태 칩·기본 배지 표시 |
| P2 | 가격 미설정 표시 | `미설정` 칩 노출 |
| P3 | 등록 플로우 | 등록 버튼 → 모달 → 필수값 입력 → 저장 → POST 바디 검증 + 모달 닫힘 (invalidate는 H2에서 검증) |
| P4 | 등록 필수값 누락 | 인라인 에러, POST 미발생 |
| P5 | 등록 409 | 모달 유지 + "이미 등록된 모델입니다" 표시 |
| P6 | 수정 모달 프리필 | display_name 등 프리필, provider/model_name 편집 불가, api_key_env 필드 부재 |
| P7 | 가격 모달 | 음수 입력 시 인라인 에러·전송 차단 / 정상 저장 시 모달 닫힘 |
| P8 | 비활성화 | ConfirmDialog 경고 노출 → 확인 → 행 상태 변경 |
| P9 | 비활성 포함 토글 | 토글 on 시 `include_inactive=true` 요청(비활성 행 노출) |

### 8.4 기타

- `adminNav.test.ts`(존재 시): 항목 수 +1, `/admin/llm-models` 포함 검증 갱신.
- 실행: `npm run test:run -- --pool=threads` (Windows forks 타임아웃 회피). 사전 실패 8건은 회귀 아님.

---

## 9. Clean Architecture / Convention

| Layer | 이번 기능 매핑 |
|-------|----------------|
| Presentation | `AdminLlmModelsPage` + 내부 모달 컴포넌트 (200줄 초과 시 `components/` 하위 분리) |
| Application | `useLlmModels` 훅 파일 (query + mutation) |
| Infrastructure | `llmModelService` (authClient) |
| Const/Type | `constants/api.ts`, `constants/adminNav.ts`, `types/llmModel.ts` |

컨벤션: Request/Response 접미사, `as const` provider 상수, queryKey는 `queryKeys` 팩토리 전용, 컴포넌트에서 axios 직접 호출 금지.

---

## 10. Implementation Guide (TDD 순서)

```
Phase 1: 계약 레이어 (Red → Green)
  1. types/llmModel.ts 확장 + constants/api.ts 경로 2종
  2. MSW 핸들러 추가 (기존 GET mock에 가격 필드 보강)
  3. Red — llmModelService 신규 메서드 테스트 → Green — 서비스 구현

Phase 2: 훅 레이어 (Red → Green)
  4. lib/queryKeys.ts detail 키 추가
  5. Red — H2~H6 → Green — 뮤테이션 훅 4종 구현

Phase 3: 페이지 (Red → Green)
  6. Red — P1~P9 → Green — AdminLlmModelsPage (테이블 → FormModal → PricingModal → ConfirmDialog 순)

Phase 4: 라우팅/네비
  7. App.tsx 라우트 + adminNav.ts 항목 (+ adminNav 테스트 갱신)

Phase 5: 검증
  8. npm run test:run -- --pool=threads / type-check / lint
  9. 수동: 등록→기본지정→가격설정→비활성화→재활성화 사이클 + 빌더 모델 목록 갱신 확인
```

### 변경 파일 요약

| 구분 | 파일 |
|------|------|
| 신규 | `src/pages/AdminLlmModelsPage/index.tsx`, `index.test.tsx` |
| 수정 | `types/llmModel.ts`, `constants/api.ts`, `services/llmModelService.ts`, `lib/queryKeys.ts`, `hooks/useLlmModels.ts`(+test), `constants/adminNav.ts`, `App.tsx`, `__tests__/mocks/handlers.ts` |

---

## 11. Definition of Done

- [ ] 타입/상수/서비스/쿼리키/훅 — 백엔드 스키마와 1:1, 기존 시그니처 불변
- [ ] `/admin/llm-models` 페이지 — 테이블·등록·수정·가격·비활성화·토글 동작
- [ ] `ADMIN_NAV_ITEMS` "LLM 모델" 항목 + `App.tsx` 라우트
- [ ] 409/422/404 인라인 에러 표시
- [ ] 뮤테이션 후 에이전트 빌더 모델 목록 자동 갱신 (invalidate)
- [ ] 신규 테스트(H2~H6, P1~P9) 통과 + 기존 스위트 그린(사전 실패 8건 제외)
- [ ] `npm run type-check` / `npm run lint` / `npm run build` 통과

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-07-11 | Initial design — Plan 및 API 문서(docs/api/llm-register.md) 기반 | 배상규 |
