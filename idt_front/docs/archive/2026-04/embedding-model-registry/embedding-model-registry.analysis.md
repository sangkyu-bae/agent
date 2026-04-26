# embedding-model-registry Analysis Report

> **Analysis Type**: Gap Analysis (Design vs Implementation)
>
> **Project**: IDT Front (React + TypeScript)
> **Analyst**: gap-detector agent
> **Date**: 2026-04-23
> **Design Doc**: `docs/02-design/features/embedding-model-registry.design.md`

---

## 1. Analysis Overview

### 1.1 Analysis Purpose

Verify that the "embedding-model-registry" feature implementation matches the design document across all layers: data model, API integration, UI/UX, clean architecture, and test coverage.

### 1.2 Analysis Scope

- **Design Document**: `docs/02-design/features/embedding-model-registry.design.md`
- **Implementation Paths**: `src/types/`, `src/constants/`, `src/services/`, `src/lib/`, `src/hooks/`, `src/components/collection/`, `src/__tests__/`

---

## 2. Gap Analysis (Design vs Implementation)

### 2.1 Data Model (Section 3)

#### EmbeddingModel interface (`src/types/embeddingModel.ts`)

| Field | Design Type | Impl Type | Status |
|-------|-------------|-----------|--------|
| id | number | number | MATCH |
| provider | string | string | MATCH |
| model_name | string | string | MATCH |
| display_name | string | string | MATCH |
| vector_dimension | number | number | MATCH |
| description | string | string | MATCH |

#### EmbeddingModelListResponse

| Field | Design Type | Impl Type | Status |
|-------|-------------|-----------|--------|
| models | EmbeddingModel[] | EmbeddingModel[] | MATCH |
| total | number | number | MATCH |

#### CreateCollectionRequest (`src/types/collection.ts`)

| Field | Design | Implementation | Status |
|-------|--------|----------------|--------|
| name | string (required) | string (required) | MATCH |
| embedding_model | string? (optional) | string? (optional) | MATCH |
| vector_size | number? (optional) | number? (optional) | MATCH |
| distance | string (required) | string (required) | MATCH |

**Data Model Score: 12/12 (100%)**

### 2.2 API Endpoints (Section 4)

| Design Endpoint | Implementation Constant | Status |
|-----------------|------------------------|--------|
| GET /api/v1/embedding-models | API_ENDPOINTS.EMBEDDING_MODELS | MATCH |
| POST /api/v1/collections (embedding_model field) | API_ENDPOINTS.COLLECTIONS | MATCH |

**API Score: 2/2 (100%)**

### 2.3 Service Layer

| Design | Implementation | Status |
|--------|----------------|--------|
| embeddingModelService.getEmbeddingModels() | Present in src/services/embeddingModelService.ts | MATCH |
| Return type EmbeddingModelListResponse | Correct | MATCH |
| Uses API_ENDPOINTS.EMBEDDING_MODELS | Correct | MATCH |
| Uses apiClient | Imports from ./api/client | MATCH |

**Service Score: 4/4 (100%)**

### 2.4 Query Keys

| Design | Implementation | Status |
|--------|----------------|--------|
| embeddingModels domain key | embeddingModels: { all, list() } | MATCH |

### 2.5 Hook

| Design | Implementation | Status |
|--------|----------------|--------|
| useEmbeddingModelList hook | Exported from src/hooks/useEmbeddingModels.ts | MATCH |
| Uses queryKeys.embeddingModels.list() | Correct | MATCH |
| Uses embeddingModelService.getEmbeddingModels | Correct | MATCH |

### 2.6 UI/UX (Section 5)

| Design Requirement | Implementation | Status |
|--------------------|----------------|--------|
| Dropdown with display_name from server | select with modelData.models.map | MATCH |
| vector_dimension displayed after selection | {selectedModelInfo.vector_dimension}차원 | MATCH |
| Loading state while fetching models | "모델 목록을 불러오는 중..." | MATCH |
| Fallback to vector_size input on API error | useFallback triggers number input | MATCH |
| Fallback warning message | "모델 목록을 불러올 수 없습니다" | MATCH |
| onSubmit with embedding_model in normal mode | Correct | MATCH |
| onSubmit with vector_size in fallback mode | Correct | MATCH |
| onSubmit signature preserved | Props interface compatible | MATCH |

**UI/UX Score: 8/8 (100%)**

### 2.7 Test Cases (Section 8.2)

| Test Case | Status |
|-----------|--------|
| useEmbeddingModelList: 모델 목록을 성공적으로 조회한다 | MATCH |
| useEmbeddingModelList: 조회 실패 시 isError가 true가 된다 | MATCH |
| CreateCollectionModal: 모델 목록 로딩 시 로딩 상태를 표시한다 | MATCH |
| CreateCollectionModal: 모델 목록 조회 성공 시 드롭다운에 모델이 표시된다 | MATCH |
| CreateCollectionModal: 모델 선택 시 vector_dimension이 참고 표시된다 | MATCH |
| CreateCollectionModal: 생성 버튼 클릭 시 embedding_model이 포함된 데이터로 onSubmit이 호출된다 | MATCH |
| CreateCollectionModal: 모델 목록 조회 실패 시 vector_size 직접 입력 fallback이 표시된다 | MATCH |
| CreateCollectionModal: fallback 모드에서 생성 시 vector_size가 포함된 데이터로 onSubmit이 호출된다 | MATCH |
| useCollections: embedding_model 기반 생성 성공 | MATCH |

**Test Score: 9/9 (100%)**

### 2.8 Clean Architecture Compliance (Section 7)

| Component | Designed Layer | Actual Location | Status |
|-----------|---------------|-----------------|--------|
| EmbeddingModel types | Domain | src/types/embeddingModel.ts | MATCH |
| CreateCollectionRequest | Domain | src/types/collection.ts | MATCH |
| embeddingModelService | Infrastructure | src/services/embeddingModelService.ts | MATCH |
| EMBEDDING_MODELS constant | Infrastructure | src/constants/api.ts | MATCH |
| embeddingModels query key | Infrastructure | src/lib/queryKeys.ts | MATCH |
| useEmbeddingModelList | Application | src/hooks/useEmbeddingModels.ts | MATCH |
| CreateCollectionModal | Presentation | src/components/collection/CreateCollectionModal.tsx | MATCH |

No dependency violations found.

**Architecture Score: 7/7 (100%)**

### 2.9 Implementation Order (Section 9)

All 9 steps complete. (9/9)

---

## 3. Overall Scores

| Category | Score | Status |
|----------|:-----:|:------:|
| Data Model | 100% | PASS |
| API Spec | 100% | PASS |
| UI/UX | 100% | PASS |
| Test Plan | 100% | PASS |
| Architecture Compliance | 100% | PASS |
| Implementation Completeness | 100% | PASS |
| **Overall Match Rate** | **100%** | **PASS** |

---

## 4. Gaps Found

None.

---

## 5. Recommended Actions

Match Rate >= 90% — no corrective actions required. Proceed to `/pdca report`.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-04-23 | Initial gap analysis | gap-detector |
