# embedding-model-registry API

> DB 기반 임베딩 모델 레지스트리 조회 및 컬렉션 생성 시 벡터 차원 자동 결정

## 개요

| 항목 | 내용 |
|------|------|
| Base URL | `/api/v1` |
| Auth | 없음 (내부 API) |

---

## 엔드포인트 목록

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/v1/embedding-models` | 활성 임베딩 모델 목록 조회 |
| POST | `/api/v1/collections` | 컬렉션 생성 (embedding_model 필드 추가) |

---

## 상세 스펙

### GET /api/v1/embedding-models

활성화된(`is_active=True`) 임베딩 모델 목록을 반환한다. provider, model_name 순 정렬.

**Request**
```
파라미터 없음
```

**Response 200**
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
    },
    {
      "id": 3,
      "provider": "openai",
      "model_name": "text-embedding-ada-002",
      "display_name": "OpenAI Ada 002",
      "vector_dimension": 1536,
      "description": "이전 세대 범용 임베딩 모델"
    }
  ],
  "total": 3
}
```

**Error Codes**

| 코드 | 설명 |
|------|------|
| 500 | DB 접근 실패 등 서버 내부 오류 |

---

### POST /api/v1/collections

컬렉션을 생성한다. `embedding_model` 지정 시 DB에서 `vector_dimension`을 자동 조회하여 적용한다.

**우선순위 규칙:**
- `embedding_model`과 `vector_size` 중 최소 하나 필수
- 둘 다 있으면 `embedding_model` 우선 (DB 조회 dimension 사용)
- 둘 다 없으면 422 에러

**Request (모델명 기반 - 신규)**
```json
{
  "name": "my-collection",
  "embedding_model": "text-embedding-3-small",
  "distance": "Cosine"
}
```

**Request (직접 지정 - 하위 호환)**
```json
{
  "name": "my-collection",
  "vector_size": 1536,
  "distance": "Cosine"
}
```

| 필드 | 타입 | 필수 | 기본값 | 설명 |
|------|------|------|--------|------|
| name | string | O | - | 컬렉션 이름 |
| embedding_model | string \| null | 조건부 | null | 임베딩 모델명 (DB 등록된 모델) |
| vector_size | int \| null | 조건부 | null | 벡터 차원 수 (>= 1) |
| distance | string | X | "Cosine" | 거리 메트릭 (Cosine, Euclid, Dot) |

**Response 201**
```json
{
  "name": "my-collection",
  "message": "Collection created successfully"
}
```

**Error Codes**

| 코드 | 설명 |
|------|------|
| 409 | 동일 이름의 컬렉션이 이미 존재 |
| 422 | `vector_size`와 `embedding_model` 모두 없음 |
| 422 | `embedding_model`에 해당하는 모델이 DB에 없음 |
| 422 | 유효하지 않은 distance 메트릭 |
| 500 | 서버 내부 오류 |
