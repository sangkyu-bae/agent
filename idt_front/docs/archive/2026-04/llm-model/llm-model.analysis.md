# Gap Analysis: LLM 모델 동적 조회 (llm-model)

## 분석 정보

| 항목 | 값 |
|------|-----|
| Feature ID | LLM-MODEL-FRONT-001 |
| 분석 일시 | 2026-04-21 |
| Design 문서 | `docs/02-design/features/llm-model.design.md` |
| Match Rate | **100%** |

---

## 체크리스트

### 1. 타입 정의 (`src/types/llmModel.ts`)

| 항목 | Design | 구현 | 일치 |
|------|--------|------|:----:|
| `LlmModel` 인터페이스 | id, provider, model_name, display_name, description, max_tokens, is_active, is_default | 동일 | ✅ |
| `LlmModelListResponse` 인터페이스 | `{ models: LlmModel[] }` | 동일 | ✅ |

### 2. API 엔드포인트 (`src/constants/api.ts`)

| 항목 | Design | 구현 | 일치 |
|------|--------|------|:----:|
| `LLM_MODELS` 상수 | `'/api/v1/llm-models'` | `'/api/v1/llm-models'` (line 52) | ✅ |

### 3. 쿼리 키 (`src/lib/queryKeys.ts`)

| 항목 | Design | 구현 | 일치 |
|------|--------|------|:----:|
| `llmModels.all` | `['llmModels'] as const` | 동일 (line 74) | ✅ |
| `llmModels.list()` | `[...all, 'list', { includeInactive }]` | 동일 (line 75-76) | ✅ |

### 4. 서비스 (`src/services/llmModelService.ts`)

| 항목 | Design | 구현 | 일치 |
|------|--------|------|:----:|
| `authClient` 사용 | `authClient.get<LlmModelListResponse>` | `authApiClient.get<LlmModelListResponse>` (동일 인스턴스) | ✅ |
| `includeInactive` 파라미터 | `params: { include_inactive }` | 동일 (line 9) | ✅ |
| 반환 타입 | `Promise<LlmModelListResponse>` | 동일 (line 6) | ✅ |

### 5. 훅 (`src/hooks/useLlmModels.ts`)

| 항목 | Design | 구현 | 일치 |
|------|--------|------|:----:|
| `queryKey` | `queryKeys.llmModels.list(includeInactive)` | 동일 (line 7) | ✅ |
| `queryFn` | `llmModelService.getLlmModels(includeInactive)` | 동일 (line 8) | ✅ |
| `staleTime` | `5 * 60 * 1000` | 동일 (line 9) | ✅ |
| `select` | `(data) => data.models` | 동일 (line 10) | ✅ |

### 6. Provider 색상 매핑 (`AgentBuilderPage/index.tsx`)

| 항목 | Design | 구현 | 일치 |
|------|--------|------|:----:|
| `PROVIDER_COLORS` | openai, anthropic 매핑 | 동일 (line 32-35) | ✅ |
| `DEFAULT_PROVIDER_COLOR` | `'bg-zinc-100 text-zinc-700'` | 동일 (line 36) | ✅ |
| `getProviderColor()` | nullish coalescing fallback | 동일 (line 38-39) | ✅ |

### 7. AgentBuilderPage 변경

| 항목 | Design | 구현 | 일치 |
|------|--------|------|:----:|
| `AgentModel` 타입 제거 | 삭제 | 삭제됨 | ✅ |
| `MODEL_LABELS` 제거 | 삭제 | 삭제됨 | ✅ |
| `MODEL_COLORS` 제거 | 삭제 | 삭제됨 | ✅ |
| `model` 타입 → `string` | `model: string` | 동일 (line 27) | ✅ |
| `useLlmModels()` 훅 사용 | 동적 조회 | 동일 (line 95) | ✅ |
| 기본 모델 자동 선택 (`useEffect`) | `is_default` 모델 자동 선택 | 동일 (line 97-104) | ✅ |
| 로딩 상태 UI | 스켈레톤 4칸 `animate-pulse` | 동일 (line 504-509) | ✅ |
| 에러 상태 UI | "불러올 수 없습니다" + 재시도 | 동일 (line 510-519) | ✅ |
| 빈 목록 UI | "등록된 모델이 없습니다" | 동일 (line 536-539) | ✅ |
| 정상 모델 카드 그리드 | provider 색상 기반 | 동일 (line 520-535) | ✅ |
| AgentCard 모델 배지 | `modelInfo?.display_name ?? agent.model` | 동일 (line 381) | ✅ |

### 8. MSW 핸들러 (`src/__tests__/mocks/handlers.ts`)

| 항목 | Design | 구현 | 일치 |
|------|--------|------|:----:|
| GET LLM_MODELS 핸들러 | 2개 모델 (gpt-4o, claude-sonnet-4-6) | 동일 (line 53-78) | ✅ |
| 응답 스키마 | `{ models: [...] }` | 동일 | ✅ |

### 9. 훅 테스트 (`src/hooks/useLlmModels.test.ts`)

| 테스트 케이스 | Design | 구현 | 일치 |
|-------------|--------|------|:----:|
| 모델 목록 조회 성공 | `data` 배열 반환 | 동일 (line 14-23) | ✅ |
| `select`로 `models` 추출 | `LlmModel[]` 형태 확인 | 동일 (line 25-34) | ✅ |
| 로딩 상태 | `isLoading === true` | 동일 (line 36-42) | ✅ |
| 에러 처리 | 500 → `isError === true` | 동일 (line 44-56) | ✅ |

### 10. 테스트 실행 결과

```
✓ 4 tests passed (useLlmModels.test.ts)
  - 모델 목록을 조회한다
  - select로 models 배열을 추출한다
  - 초기 상태는 로딩이다
  - 서버 에러 시 isError가 true이다
```

---

## 요약

| 구분 | 항목 수 | 일치 | 불일치 |
|------|---------|------|--------|
| 타입 | 2 | 2 | 0 |
| 상수/키 | 3 | 3 | 0 |
| 서비스 | 3 | 3 | 0 |
| 훅 | 4 | 4 | 0 |
| UI 변경 | 12 | 12 | 0 |
| MSW | 2 | 2 | 0 |
| 테스트 | 4 | 4 | 0 |
| **합계** | **30** | **30** | **0** |

### Match Rate: **100%**

모든 Design 명세가 구현에 정확히 반영되었습니다. 갭이 없습니다.
