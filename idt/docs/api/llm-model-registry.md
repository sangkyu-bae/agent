# llm-model-registry API

> LLM 모델을 중앙 관리하는 CRUD API (등록, 수정, 비활성화, 조회, 목록)

## 개요

| 항목 | 내용 |
|------|------|
| Base URL | `/api/v1/llm-models` |
| Auth | `CurrentUser` (조회), `AdminUser` (생성/수정/삭제) |

---

## 엔드포인트 목록

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/v1/llm-models` | LLM 모델 목록 조회 |
| GET | `/api/v1/llm-models/{id}` | LLM 모델 단건 조회 |
| POST | `/api/v1/llm-models` | LLM 모델 등록 |
| PATCH | `/api/v1/llm-models/{id}` | LLM 모델 수정 |
| DELETE | `/api/v1/llm-models/{id}` | LLM 모델 비활성화 (soft delete) |

---

## 상세 스펙

### GET `/api/v1/llm-models`

LLM 모델 목록을 조회한다. 기본적으로 활성 모델만 반환하며, 쿼리 파라미터로 전체 조회 가능.

**Request**

| 파라미터 | 위치 | 타입 | 필수 | 설명 |
|----------|------|------|------|------|
| `include_inactive` | query | boolean | N | `true` 시 비활성 모델 포함 (기본 `false`) |

**Response** `200 OK`
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

### GET `/api/v1/llm-models/{id}`

ID로 LLM 모델 단건을 조회한다.

**Request**

| 파라미터 | 위치 | 타입 | 필수 | 설명 |
|----------|------|------|------|------|
| `id` | path | string (UUID) | Y | 모델 ID |

**Response** `200 OK`
```json
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
```

**Error Codes**

| 코드 | 설명 |
|------|------|
| 404 | 해당 ID의 모델이 존재하지 않음 |

---

### POST `/api/v1/llm-models`

새 LLM 모델을 등록한다. `is_default=true` 지정 시 기존 기본 모델은 자동 해제된다.

**Request**
```json
{
  "provider": "openai",
  "model_name": "gpt-4o",
  "display_name": "GPT-4o",
  "description": "OpenAI GPT-4o model",
  "api_key_env": "OPENAI_API_KEY",
  "max_tokens": null,
  "is_active": true,
  "is_default": false
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `provider` | string (max 50) | Y | 제공사 (`openai`, `anthropic`, `ollama`, `perplexity`) |
| `model_name` | string (max 150) | Y | API 호출용 모델명 |
| `display_name` | string (max 150) | Y | UI 표시명 |
| `description` | string | N | 설명 |
| `api_key_env` | string (max 100) | Y | API 키 환경변수명 |
| `max_tokens` | int | N | 최대 토큰 수 |
| `is_active` | boolean | N | 활성 여부 (기본 `true`) |
| `is_default` | boolean | N | 기본 모델 여부 (기본 `false`) |

**Response** `201 Created`
```json
{
  "id": "uuid-string",
  "provider": "openai",
  "model_name": "gpt-4o",
  "display_name": "GPT-4o",
  "description": "OpenAI GPT-4o model",
  "max_tokens": null,
  "is_active": true,
  "is_default": false
}
```

**Error Codes**

| 코드 | 설명 |
|------|------|
| 400 | `model_name`이 빈 문자열 |
| 409 | `provider` + `model_name` 조합이 이미 존재 |

---

### PATCH `/api/v1/llm-models/{id}`

기존 LLM 모델 정보를 수정한다. `is_default=true` 지정 시 기존 기본 모델은 자동 해제된다.

**Request**
```json
{
  "display_name": "GPT-4o (Updated)",
  "description": "Updated description",
  "max_tokens": 4096,
  "is_active": true,
  "is_default": true
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `display_name` | string (max 150) | N | UI 표시명 |
| `description` | string | N | 설명 |
| `max_tokens` | int | N | 최대 토큰 수 |
| `is_active` | boolean | N | 활성 여부 |
| `is_default` | boolean | N | 기본 모델 여부 |

**Response** `200 OK`
```json
{
  "id": "uuid-string",
  "provider": "openai",
  "model_name": "gpt-4o",
  "display_name": "GPT-4o (Updated)",
  "description": "Updated description",
  "max_tokens": 4096,
  "is_active": true,
  "is_default": true
}
```

**Error Codes**

| 코드 | 설명 |
|------|------|
| 404 | 해당 ID의 모델이 존재하지 않음 |

---

### DELETE `/api/v1/llm-models/{id}`

LLM 모델을 비활성화한다 (soft delete). `is_active=false`, `is_default=false`로 변경된다.

**Request**

| 파라미터 | 위치 | 타입 | 필수 | 설명 |
|----------|------|------|------|------|
| `id` | path | string (UUID) | Y | 모델 ID |

**Response** `200 OK`
```json
{
  "id": "uuid-string",
  "provider": "openai",
  "model_name": "gpt-4o",
  "display_name": "GPT-4o",
  "description": "OpenAI GPT-4o model",
  "max_tokens": null,
  "is_active": false,
  "is_default": false
}
```

**Error Codes**

| 코드 | 설명 |
|------|------|
| 404 | 해당 ID의 모델이 존재하지 않음 |
