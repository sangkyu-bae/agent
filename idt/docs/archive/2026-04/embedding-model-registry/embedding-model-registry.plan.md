# Plan: embedding-model-registry

> Feature: 임베딩 모델 레지스트리 — DB 기반 벡터 차원 관리 및 컬렉션 자동 생성
> Created: 2026-04-22
> Status: Plan

---

## 1. 목적 (Why)

### 현재 문제

1. **하드코딩된 모델 정보**: `embedding_factory.py`의 `MODEL_DIMENSIONS` 딕셔너리에 OpenAI 3개 모델만 정적으로 존재
2. **사용자 UX 부재**: 컬렉션 생성 시 `vector_size`를 숫자(1536, 3072 등)로 직접 입력해야 함 — 일반 사용자는 이 값을 모름
3. **확장성 부족**: 새 임베딩 모델(Ollama, Cohere, HuggingFace 등) 추가 시 코드 수정·재배포 필요

### 목표

- 임베딩 모델 메타정보(provider, model_name, vector_dimension 등)를 **MySQL DB 테이블**로 관리
- 컬렉션 생성 시 사용자는 **모델만 선택**하면 `vector_size`가 자동 결정됨
- 관리자가 새 모델을 **코드 수정 없이** DB에 등록 가능

---

## 2. 기능 범위 (Scope)

### In Scope

| # | 기능 | 설명 |
|---|------|------|
| F-01 | 임베딩 모델 레지스트리 테이블 | MySQL에 `embedding_model` 테이블 생성 |
| F-02 | 모델 목록 조회 API | `GET /api/v1/embedding-models` — 사용 가능한 모델 + 차원 정보 반환 |
| F-03 | 컬렉션 생성 API 개선 | `vector_size` 대신 `embedding_model` 필드로 변경, 자동 차원 결정 |
| F-04 | 시드 데이터 | 기존 `MODEL_DIMENSIONS`의 3개 모델을 초기 데이터로 등록 |
| F-05 | EmbeddingFactory 연동 | DB에서 차원 조회 → `EmbeddingFactory`에서 하드코딩 제거 |

### Out of Scope

- 임베딩 모델 관리 UI (프론트엔드) — 별도 task로 분리
- 모델별 API key 관리 — 기존 `.env` 방식 유지
- 실제 임베딩 실행 로직 변경 — `EmbeddingFactory.create()` 자체는 유지
- Ollama/HuggingFace 등 새 프로바이더 임베딩 어댑터 구현

---

## 3. 기술 의존성

| 모듈 | 위치 | 상태 |
|------|------|------|
| EmbeddingFactory | `src/infrastructure/embeddings/embedding_factory.py` | 구현됨 (하드코딩) |
| EmbeddingInterface | `src/domain/vector/interfaces.py` | 구현됨 |
| CollectionManagementUseCase | `src/application/collection/use_case.py` | 구현됨 |
| CreateCollectionRequest | `src/domain/collection/schemas.py` | 구현됨 |
| collection_router | `src/api/routes/collection_router.py` | 구현됨 |
| SQLAlchemy Base (MySQL) | `src/infrastructure/persistence/models/base.py` | 구현됨 |

---

## 4. 도메인 모델 설계

### 4-1. embedding_model 테이블 (MySQL)

```
embedding_model
├── id              : BIGINT, PK, AUTO_INCREMENT
├── provider        : VARCHAR(50), NOT NULL        -- "openai", "ollama", "cohere"
├── model_name      : VARCHAR(100), NOT NULL, UNIQUE
├── display_name    : VARCHAR(200), NOT NULL        -- UI 표시용 이름
├── vector_dimension: INT, NOT NULL                 -- 1536, 3072 등
├── is_active       : BOOLEAN, DEFAULT TRUE         -- 비활성화 가능
├── description     : TEXT, NULLABLE                -- 모델 설명
├── created_at      : DATETIME, NOT NULL
├── updated_at      : DATETIME, NOT NULL
```

### 4-2. 시드 데이터

| provider | model_name | display_name | vector_dimension |
|----------|-----------|--------------|-----------------|
| openai | text-embedding-3-small | OpenAI Embedding 3 Small | 1536 |
| openai | text-embedding-3-large | OpenAI Embedding 3 Large | 3072 |
| openai | text-embedding-ada-002 | OpenAI Ada 002 | 1536 |

---

## 5. API 설계 개요

### 5-1. 모델 목록 조회

```
GET /api/v1/embedding-models
```

**Response:**
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
    },
    {
      "id": 2,
      "provider": "openai",
      "model_name": "text-embedding-3-large",
      "display_name": "OpenAI Embedding 3 Large",
      "vector_dimension": 3072,
      "description": "고품질 임베딩 모델 (정확도 우선)"
    }
  ],
  "total": 2
}
```

### 5-2. 컬렉션 생성 API 변경

**Before (현재):**
```json
POST /api/v1/collections
{
  "name": "my-collection",
  "vector_size": 1536,       // 사용자가 직접 입력
  "distance": "Cosine"
}
```

**After (변경):**
```json
POST /api/v1/collections
{
  "name": "my-collection",
  "embedding_model": "text-embedding-3-small",  // 모델명 선택
  "distance": "Cosine"
}
```

- `embedding_model`로 DB 조회 → `vector_dimension` 자동 결정
- **하위 호환**: `vector_size` 직접 입력도 허용 (둘 다 있으면 `embedding_model` 우선)

---

## 6. 레이어별 구현 계획

### Domain Layer

| 파일 | 내용 |
|------|------|
| `src/domain/embedding_model/schemas.py` | `EmbeddingModelInfo` dataclass |
| `src/domain/embedding_model/interfaces.py` | `EmbeddingModelRepositoryInterface` |
| `src/domain/collection/schemas.py` | `CreateCollectionRequest`에 `embedding_model` 필드 추가 |

### Application Layer

| 파일 | 내용 |
|------|------|
| `src/application/embedding_model/use_case.py` | `EmbeddingModelUseCase` — 모델 목록 조회 |
| `src/application/collection/use_case.py` | 컬렉션 생성 시 모델 레지스트리에서 dimension 조회 로직 추가 |

### Infrastructure Layer

| 파일 | 내용 |
|------|------|
| `src/infrastructure/embedding_model/models.py` | SQLAlchemy `EmbeddingModelTable` |
| `src/infrastructure/embedding_model/repository.py` | `EmbeddingModelRepository` (MySQL) |
| `src/infrastructure/embeddings/embedding_factory.py` | `MODEL_DIMENSIONS` 제거, DB 조회로 대체 |

### Interface Layer (API)

| 파일 | 내용 |
|------|------|
| `src/api/routes/embedding_model_router.py` | `GET /api/v1/embedding-models` |
| `src/api/routes/collection_router.py` | `CreateCollectionBody` 스키마 변경 |
| `src/api/main.py` | 라우터 등록 + DI 설정 |

### Migration

| 파일 | 내용 |
|------|------|
| `db/migration/V00X__create_embedding_model.sql` | 테이블 생성 + 시드 데이터 |

---

## 7. TDD 계획

| 테스트 파일 | 검증 대상 |
|-------------|-----------|
| `tests/domain/embedding_model/test_schemas.py` | `EmbeddingModelInfo` 생성·검증 |
| `tests/application/embedding_model/test_use_case.py` | 모델 목록 조회 UseCase |
| `tests/application/collection/test_use_case.py` | 모델명 기반 컬렉션 생성 (dimension 자동 결정) |
| `tests/infrastructure/embedding_model/test_repository.py` | DB CRUD |
| `tests/api/test_embedding_model_router.py` | API 엔드포인트 |
| `tests/api/test_collection_router.py` | 변경된 컬렉션 생성 API |

---

## 8. 구현 순서

```
1. Domain: EmbeddingModelInfo + Interface 정의
2. Infrastructure: SQLAlchemy Model + Repository
3. Migration: 테이블 생성 + 시드 데이터
4. Application: EmbeddingModelUseCase
5. API: embedding_model_router (모델 목록)
6. Domain: CreateCollectionRequest 수정
7. Application: CollectionManagementUseCase에 dimension 자동 결정 로직
8. API: collection_router 스키마 변경
9. Infrastructure: EmbeddingFactory에서 하드코딩 제거
```

---

## 9. CLAUDE.md 규칙 체크

- [x] domain → infrastructure 참조 없음 (interface만 정의)
- [x] application은 domain 규칙 조합 + UseCase 패턴
- [x] infrastructure 어댑터 패턴 (SQLAlchemy Repository)
- [x] config 값 하드코딩 금지 → DB 관리로 전환
- [x] TDD 필수: 테스트 → 실패 → 구현 → 통과
- [x] 함수 40줄 초과 금지

---

## 10. 완료 기준

- [ ] `embedding_model` MySQL 테이블 생성 + 시드 데이터 적재
- [ ] `GET /api/v1/embedding-models` — 활성 모델 목록 반환
- [ ] `POST /api/v1/collections` — `embedding_model` 필드로 컬렉션 생성 가능
- [ ] `vector_size` 직접 입력 하위 호환 유지
- [ ] `EmbeddingFactory`에서 하드코딩 `MODEL_DIMENSIONS` 제거
- [ ] 전체 테스트 통과 (unit + integration)
- [ ] LOG-001 로깅 적용

---

## 11. 위험 요소 및 대응

| 위험 | 영향 | 대응 |
|------|------|------|
| 기존 컬렉션과의 호환성 | 기존 `vector_size`로 만든 컬렉션 영향 없음 | 하위 호환 유지 (vector_size 직접 입력 허용) |
| DB 장애 시 모델 정보 조회 불가 | 컬렉션 생성 실패 | 코드 내 fallback 딕셔너리 유지 (선택적) |
| 프론트엔드 연동 | 컬렉션 생성 UI 변경 필요 | Out of Scope — 별도 task로 분리 |
