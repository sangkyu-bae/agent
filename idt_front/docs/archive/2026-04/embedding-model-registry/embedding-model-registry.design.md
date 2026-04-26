# embedding-model-registry Design Document

> **Summary**: 컬렉션 생성 시 임베딩 모델을 서버에서 조회하여 드롭다운 선택 → 벡터 차원 자동 결정
>
> **Project**: IDT Front (React + TypeScript)
> **Author**: 배상규
> **Date**: 2026-04-22
> **Status**: Draft
> **Planning Doc**: [embedding-model-registry.plan.md](../01-plan/features/embedding-model-registry.plan.md)

---

## 1. Overview

### 1.1 Design Goals

- 사용자가 벡터 차원 수를 직접 입력하지 않고, 서버에 등록된 임베딩 모델 목록에서 선택
- 선택된 모델의 `model_name`을 `POST /api/v1/collections`에 `embedding_model` 필드로 전송
- 기존 `vector_size` 직접 입력은 fallback으로 유지 (API 조회 실패 시)

### 1.2 Design Principles

- 기존 컬렉션 관리 레이어 구조와 동일한 패턴 유지 (타입 → 서비스 → 훅 → 컴포넌트)
- `CreateCollectionModal`의 인터페이스 변경 최소화 (onSubmit 시그니처 유지)
- TDD 사이클 준수

---

## 2. Architecture

### 2.1 Data Flow

```
┌──────────────────┐     GET /embedding-models     ┌──────────────┐
│  useEmbedding    │ ─────────────────────────────▶ │   Backend    │
│  ModelList()     │ ◀───── { models, total } ───── │   API        │
└───────┬──────────┘                                └──────────────┘
        │
        ▼
┌──────────────────┐     POST /collections          ┌──────────────┐
│  CreateCollection│ ─── { name, embedding_model, ─▶│   Backend    │
│  Modal           │      distance }                │   API        │
└──────────────────┘ ◀── { name, message } ──────── └──────────────┘
```

### 2.2 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `useEmbeddingModelList` | `embeddingModelService` | 모델 목록 조회 |
| `CreateCollectionModal` | `useEmbeddingModelList` | 드롭다운 데이터 제공 |
| `collectionService.createCollection` | `CreateCollectionRequest` (수정) | 요청 스키마 변경 반영 |

---

## 3. Data Model

### 3.1 신규 타입: `src/types/embeddingModel.ts`

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

### 3.2 변경 타입: `src/types/collection.ts`

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

---

## 4. API Specification

### 4.1 Endpoint List

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/api/v1/embedding-models` | 활성 임베딩 모델 목록 조회 | 없음 |
| POST | `/api/v1/collections` | 컬렉션 생성 (embedding_model 필드 추가) | 없음 |

### 4.2 GET /api/v1/embedding-models

**Request**: 파라미터 없음

**Response (200)**:
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

**Error**: `500` — 서버 내부 오류

### 4.3 POST /api/v1/collections (변경)

**Request** (embedding_model 기반):
```json
{
  "name": "my-collection",
  "embedding_model": "text-embedding-3-small",
  "distance": "Cosine"
}
```

**Request** (fallback — vector_size 직접 지정):
```json
{
  "name": "my-collection",
  "vector_size": 1536,
  "distance": "Cosine"
}
```

**우선순위**: `embedding_model` > `vector_size`. 둘 다 없으면 422.

---

## 5. UI/UX Design

### 5.1 CreateCollectionModal 변경 전/후

**Before**:
```
┌─────────────────────────────────┐
│ 새 컬렉션 생성                    │
├─────────────────────────────────┤
│ 컬렉션 이름  [____________]      │
│ 벡터 차원 수  [1536       ]      │  ← 숫자 직접 입력
│ 거리 메트릭  [Cosine    ▼]      │
│              [취소] [생성]       │
└─────────────────────────────────┘
```

**After (정상)**:
```
┌─────────────────────────────────┐
│ 새 컬렉션 생성                    │
├─────────────────────────────────┤
│ 컬렉션 이름  [____________]      │
│ 임베딩 모델  [모델을 선택하세요 ▼]│  ← 드롭다운 (서버 조회)
│   ┌─────────────────────────┐   │
│   │ OpenAI Embedding 3 Small│   │    display_name 표시
│   │ OpenAI Embedding 3 Large│   │
│   │ OpenAI Ada 002          │   │
│   └─────────────────────────┘   │
│              1536차원            │  ← 선택 시 vector_dimension 참고 표시
│ 거리 메트릭  [Cosine    ▼]      │
│              [취소] [생성]       │
└─────────────────────────────────┘
```

**After (API 실패 fallback)**:
```
┌─────────────────────────────────┐
│ 새 컬렉션 생성                    │
├─────────────────────────────────┤
│ 컬렉션 이름  [____________]      │
│ ⚠ 모델 목록을 불러올 수 없습니다   │
│ 벡터 차원 수  [1536       ]      │  ← 기존 숫자 입력 fallback
│ 거리 메트릭  [Cosine    ▼]      │
│              [취소] [생성]       │
└─────────────────────────────────┘
```

### 5.2 User Flow

```
모달 열림
  ↓
useEmbeddingModelList() 호출 → 로딩 스피너
  ↓ (성공)                           ↓ (실패)
드롭다운 표시                      fallback: vector_size 직접 입력
  ↓                                  ↓
모델 선택 → dimension 참고 표시    숫자 입력
  ↓                                  ↓
[생성] 클릭                        [생성] 클릭
  ↓                                  ↓
{ name, embedding_model, distance } { name, vector_size, distance }
  ↓                                  ↓
POST /api/v1/collections ──────────────┘
```

### 5.3 Component List

| Component | Location | Responsibility |
|-----------|----------|----------------|
| `CreateCollectionModal` | `src/components/collection/` | 컬렉션 생성 폼 (모델 드롭다운으로 변경) |
| `CollectionPage` | `src/pages/CollectionPage/` | 모달 호출부 (변경 없음 — onSubmit 시그니처 동일) |

---

## 6. Error Handling

| 상황 | 에러 코드 | 처리 |
|------|----------|------|
| 모델 목록 조회 실패 | 500 | fallback: vector_size 직접 입력 모드 |
| 컬렉션 이름 중복 | 409 | 에러 메시지 표시 |
| embedding_model + vector_size 둘 다 없음 | 422 | 프론트에서 방지 (필수 선택) |
| DB에 없는 모델명 전송 | 422 | 에러 메시지 표시 |

---

## 7. Clean Architecture — Layer Assignment

| Component | Layer | Location |
|-----------|-------|----------|
| `EmbeddingModel`, `EmbeddingModelListResponse` | Domain | `src/types/embeddingModel.ts` |
| `CreateCollectionRequest` (수정) | Domain | `src/types/collection.ts` |
| `embeddingModelService` | Infrastructure | `src/services/embeddingModelService.ts` |
| `EMBEDDING_MODELS` 상수 | Infrastructure | `src/constants/api.ts` |
| `embeddingModels` 쿼리 키 | Infrastructure | `src/lib/queryKeys.ts` |
| `useEmbeddingModelList` | Application | `src/hooks/useEmbeddingModels.ts` |
| `CreateCollectionModal` | Presentation | `src/components/collection/CreateCollectionModal.tsx` |

---

## 8. Test Plan

### 8.1 Test Scope

| Type | Target | Tool |
|------|--------|------|
| Unit | `useEmbeddingModelList` 훅 | Vitest + MSW |
| Unit | `CreateCollectionModal` 컴포넌트 | Vitest + RTL + MSW |
| Unit | `useCreateCollection` 훅 (embedding_model 케이스) | Vitest + MSW |

### 8.2 Test Cases

#### `useEmbeddingModelList` (`src/hooks/useEmbeddingModels.test.ts`)

- [x] 모델 목록을 성공적으로 조회한다
- [x] 조회 실패 시 isError가 true가 된다

#### `CreateCollectionModal` (`src/components/collection/CreateCollectionModal.test.tsx`)

- [x] 모델 목록 로딩 시 로딩 상태를 표시한다
- [x] 모델 목록 조회 성공 시 드롭다운에 모델이 표시된다
- [x] 모델 선택 시 vector_dimension이 참고 표시된다
- [x] 생성 버튼 클릭 시 embedding_model이 포함된 데이터로 onSubmit이 호출된다
- [x] 모델 목록 조회 실패 시 vector_size 직접 입력 fallback이 표시된다
- [x] fallback 모드에서 생성 시 vector_size가 포함된 데이터로 onSubmit이 호출된다

### 8.3 MSW Handler 추가

```typescript
// src/__tests__/mocks/handlers.ts 에 추가
http.get('*/api/v1/embedding-models', () =>
  HttpResponse.json({
    models: [
      {
        id: 1,
        provider: 'openai',
        model_name: 'text-embedding-3-small',
        display_name: 'OpenAI Embedding 3 Small',
        vector_dimension: 1536,
        description: '가성비 좋은 범용 임베딩 모델',
      },
      {
        id: 2,
        provider: 'openai',
        model_name: 'text-embedding-3-large',
        display_name: 'OpenAI Embedding 3 Large',
        vector_dimension: 3072,
        description: '고품질 임베딩 모델',
      },
    ],
    total: 2,
  })
),
```

---

## 9. Implementation Order

| 순서 | 파일 | 작업 | TDD |
|------|------|------|-----|
| 1 | `src/types/embeddingModel.ts` | 신규 타입 정의 | — |
| 2 | `src/types/collection.ts` | `CreateCollectionRequest` 수정 | — |
| 3 | `src/constants/api.ts` | `EMBEDDING_MODELS` 엔드포인트 추가 | — |
| 4 | `src/services/embeddingModelService.ts` | 서비스 구현 | — |
| 5 | `src/lib/queryKeys.ts` | 쿼리 키 추가 | — |
| 6 | `src/__tests__/mocks/handlers.ts` | MSW 핸들러 추가 | — |
| 7 | `src/hooks/useEmbeddingModels.ts` + `.test.ts` | 훅 구현 | Red → Green |
| 8 | `src/components/collection/CreateCollectionModal.tsx` + `.test.tsx` | UI 변경 | Red → Green |
| 9 | `src/hooks/useCollections.test.ts` | 기존 테스트에 embedding_model 케이스 추가 | Red → Green |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-04-22 | Initial draft | 배상규 |
