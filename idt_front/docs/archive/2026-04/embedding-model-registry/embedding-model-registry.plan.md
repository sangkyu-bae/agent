# Plan: embedding-model-registry

> 컬렉션 생성 시 임베딩 모델을 서버에서 조회하여 벡터 차원을 자동 결정

## 1. 배경 및 목적

현재 `CreateCollectionModal`에서 사용자가 `vector_size`를 직접 숫자로 입력한다.
이를 서버의 **임베딩 모델 레지스트리 API** (`GET /api/v1/embedding-models`)에서
모델 목록을 가져와 드롭다운으로 선택하도록 변경하고,
선택된 모델의 `model_name`을 `POST /api/v1/collections` 요청에 `embedding_model` 필드로 전송한다.

## 2. 참조 API 스펙

### GET /api/v1/embedding-models

활성 임베딩 모델 목록 조회. 파라미터 없음.

```json
{
  "models": [
    {
      "id": 1,
      "provider": "openai",
      "model_name": "text-embedding-3-small",
      "display_name": "OpenAI Embedding 3 Small",
      "vector_dimension": 1536,
      "description": "가성비 좋은 범용 임베딩 모델"
    }
  ],
  "total": 3
}
```

### POST /api/v1/collections (변경)

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| name | string | O | 컬렉션 이름 |
| embedding_model | string \| null | 조건부 | 임베딩 모델명 (신규) |
| vector_size | int \| null | 조건부 | 벡터 차원 수 (하위 호환) |
| distance | string | X | 거리 메트릭 (기본 Cosine) |

- `embedding_model` 우선, `vector_size`는 하위 호환용으로 유지

## 3. 구현 범위

### 3-1. 타입 정의 (`src/types/`)

| 파일 | 변경 내용 |
|------|----------|
| `src/types/embeddingModel.ts` (신규) | `EmbeddingModel`, `EmbeddingModelListResponse` 인터페이스 |
| `src/types/collection.ts` | `CreateCollectionRequest`에 `embedding_model?: string` 추가, `vector_size`를 optional로 변경 |

#### EmbeddingModel 타입

```typescript
export interface EmbeddingModel {
  id: number;
  provider: string;
  model_name: string;
  display_name: string;
  vector_dimension: number;
  description: string;
}

export interface EmbeddingModelListResponse {
  models: EmbeddingModel[];
  total: number;
}
```

#### CreateCollectionRequest 변경

```typescript
// Before
export interface CreateCollectionRequest {
  name: string;
  vector_size: number;
  distance: string;
}

// After
export interface CreateCollectionRequest {
  name: string;
  embedding_model?: string;
  vector_size?: number;
  distance: string;
}
```

### 3-2. API 상수 (`src/constants/api.ts`)

```typescript
EMBEDDING_MODELS: '/api/v1/embedding-models',
```

### 3-3. 서비스 레이어 (`src/services/`)

| 파일 | 변경 내용 |
|------|----------|
| `src/services/embeddingModelService.ts` (신규) | `getEmbeddingModels()` API 호출 |

### 3-4. 쿼리 키 (`src/lib/queryKeys.ts`)

```typescript
embeddingModels: {
  all: ['embeddingModels'] as const,
  list: () => [...queryKeys.embeddingModels.all, 'list'] as const,
},
```

### 3-5. 커스텀 훅 (`src/hooks/`)

| 파일 | 변경 내용 |
|------|----------|
| `src/hooks/useEmbeddingModels.ts` (신규) | `useEmbeddingModelList()` — TanStack Query 훅 |

### 3-6. 컴포넌트 변경 (`src/components/collection/`)

| 파일 | 변경 내용 |
|------|----------|
| `CreateCollectionModal.tsx` | 벡터 차원 숫자 입력 → 임베딩 모델 드롭다운 선택으로 변경 |

#### UI 변경 상세

- 기존: `<input type="number" />` (벡터 차원 수 직접 입력)
- 변경: `<select>` 드롭다운 (서버에서 조회한 임베딩 모델 목록)
  - 각 옵션: `display_name` 표시, `model_name` 값으로 전송
  - 선택 시 해당 모델의 `vector_dimension` 참고 표시 (e.g., "1536차원")
- `onSubmit` 시 `{ name, embedding_model: selectedModel, distance }` 형태로 전송
- 모델 목록 로딩 중: 스피너 또는 "로딩 중..." 표시
- 모델 목록 조회 실패 시: 에러 메시지 + 기존 `vector_size` 직접 입력 fallback

### 3-7. 테스트

| 파일 | 테스트 내용 |
|------|-----------|
| `src/hooks/useEmbeddingModels.test.ts` (신규) | 모델 목록 조회 성공/실패 |
| `src/hooks/useCollections.test.ts` (수정) | `createCollection`에 `embedding_model` 전달 케이스 추가 |
| `src/components/collection/CreateCollectionModal.test.tsx` (신규) | 드롭다운 렌더링, 모델 선택 시 submit 데이터 검증 |

## 4. 구현 순서

| 단계 | 작업 | TDD |
|------|------|-----|
| 1 | `src/types/embeddingModel.ts` 타입 정의 | - |
| 2 | `src/types/collection.ts` — `CreateCollectionRequest` 수정 | - |
| 3 | `src/constants/api.ts` — 엔드포인트 추가 | - |
| 4 | `src/services/embeddingModelService.ts` 서비스 구현 | - |
| 5 | `src/lib/queryKeys.ts` — 쿼리 키 추가 | - |
| 6 | `src/hooks/useEmbeddingModels.ts` 훅 구현 | Red → Green |
| 7 | `src/hooks/useCollections.test.ts` 수정 | Red → Green |
| 8 | `CreateCollectionModal.tsx` UI 변경 | Red → Green |
| 9 | MSW 핸들러 추가 (`handlers.ts`) | - |

## 5. 영향도 분석

| 영향 파일 | 이유 |
|----------|------|
| `CreateCollectionModal.tsx` | 입력 UI 변경 (숫자 → 드롭다운) |
| `CollectionPage/index.tsx` | `onSubmit` 데이터 형태 변경 가능성 확인 필요 |
| `useCollections.ts` | `CreateCollectionRequest` 타입 변경 반영 (자동) |
| `collectionService.ts` | `CreateCollectionRequest` 타입 변경 반영 (자동) |

## 6. 제외 사항

- 백엔드 구현 (이미 완료 가정)
- 임베딩 모델 CRUD 관리 UI (조회만 사용)
- `vector_size` 직접 입력 UI 완전 제거 (fallback으로 유지)
