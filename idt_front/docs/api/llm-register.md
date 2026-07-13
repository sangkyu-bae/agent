# llm-model-registry API

> LLM 모델을 중앙 관리하는 CRUD API (등록, 수정, 비활성화, 조회, 목록, 가격 관리)
> 설계: LLM-MODEL-REG-001 §7, LLM-MODEL-REG-002 (base_url), AGENT-OBS M4 (pricing)

## 개요

| 항목 | 내용 |
|------|------|
| Base URL | `/api/v1/llm-models` |
| Auth | `CurrentUser` (조회), `require_role("admin")` (생성/수정/비활성화/가격) |
| 구현 | `src/api/routes/llm_model_router.py`, `src/application/llm_model/schemas.py` |

여기 등록된 모델은 에이전트 실행(`llm_model_id`), 문서 요약 모델 지정
(→ `section-summary-model-config.md`), 비용 계산(AGENT-OBS) 등에서 참조된다.

---

## 엔드포인트 목록

| Method | Path | Auth | 설명 |
|--------|------|------|------|
| GET | `/api/v1/llm-models` | user | LLM 모델 목록 조회 |
| GET | `/api/v1/llm-models/{id}` | user | LLM 모델 단건 조회 |
| POST | `/api/v1/llm-models` | admin | LLM 모델 등록 |
| PATCH | `/api/v1/llm-models/{id}` | admin | LLM 모델 수정 |
| PATCH | `/api/v1/llm-models/{id}/pricing` | admin | 모델 가격 변경 (+비용 캐시 무효화) |
| DELETE | `/api/v1/llm-models/{id}` | admin | LLM 모델 비활성화 (soft delete) |

---

## 공통 응답 스키마 (`LlmModelResponse`)

```json
{
  "id": "uuid-string",
  "provider": "openai",
  "model_name": "gpt-4o",
  "display_name": "GPT-4o",
  "description": "OpenAI GPT-4o model",
  "max_tokens": null,
  "is_active": true,
  "is_default": true,
  "input_price_per_1k_usd": "0.0025",
  "output_price_per_1k_usd": "0.0100",
  "pricing_updated_at": "2026-07-11T00:00:00",
  "base_url": null
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | string (UUID) | 모델 ID |
| `provider` | string | 제공사 (`openai`, `anthropic`, `ollama`, `perplexity`) |
| `model_name` | string | API 호출용 모델명 |
| `display_name` | string | UI 표시명 |
| `description` | string \| null | 설명 |
| `max_tokens` | int \| null | 최대 토큰 수 |
| `is_active` | boolean | 활성 여부 |
| `is_default` | boolean | 기본 모델 여부 |
| `input_price_per_1k_usd` | decimal \| null | 입력 토큰 1,000개당 USD (미설정 시 null) |
| `output_price_per_1k_usd` | decimal \| null | 출력 토큰 1,000개당 USD (미설정 시 null) |
| `pricing_updated_at` | datetime \| null | 가격 최종 변경 시각 |
| `base_url` | string \| null | self-host 엔드포인트 (vLLM/OpenAI 호환). null이면 provider 기본값 |

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
  "models": [ { /* LlmModelResponse */ } ]
}
```

---

### GET `/api/v1/llm-models/{id}`

ID로 LLM 모델 단건을 조회한다.

**Request**

| 파라미터 | 위치 | 타입 | 필수 | 설명 |
|----------|------|------|------|------|
| `id` | path | string (UUID) | Y | 모델 ID |

**Response** `200 OK` — `LlmModelResponse`

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
  "is_default": false,
  "base_url": null
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
| `base_url` | string (max 500) | N | self-host 엔드포인트. `null`이면 provider 기본값 |

**Response** `201 Created` — `LlmModelResponse`

가격 필드는 등록 시점에는 설정할 수 없다 (`null`로 생성). 등록 후
`PATCH /{id}/pricing`으로 별도 설정한다.

**Error Codes**

| 코드 | 설명 |
|------|------|
| 409 | `provider` + `model_name` 조합이 이미 등록됨 |
| 422 | 검증 실패 (빈 `model_name` 등 정책 위반) |

---

### PATCH `/api/v1/llm-models/{id}`

기존 LLM 모델 정보를 수정한다 (부분 수정 — 전달한 필드만 반영).
`is_default=true` 지정 시 기존 기본 모델은 자동 해제된다.

**Request**
```json
{
  "display_name": "GPT-4o (Updated)",
  "description": "Updated description",
  "max_tokens": 4096,
  "is_active": true,
  "is_default": true,
  "base_url": "http://vllm.internal:8000/v1"
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `display_name` | string (max 150) | N | UI 표시명 |
| `description` | string | N | 설명 |
| `max_tokens` | int | N | 최대 토큰 수 |
| `is_active` | boolean | N | 활성 여부 |
| `is_default` | boolean | N | 기본 모델 여부 |
| `base_url` | string (max 500) | N | self-host 엔드포인트 |

`provider`, `model_name`, `api_key_env`는 수정 불가(식별자 성격).
가격은 이 엔드포인트가 아니라 `PATCH /{id}/pricing`으로 변경한다.

**Response** `200 OK` — `LlmModelResponse`

**Error Codes**

| 코드 | 설명 |
|------|------|
| 404 | 해당 ID의 모델이 존재하지 않음 |

---

### PATCH `/api/v1/llm-models/{id}/pricing`

모델의 토큰 단가를 변경한다 (AGENT-OBS M4). 변경 시 비용 계산기의
가격 캐시(`cost_calculator`)가 해당 모델에 대해 즉시 무효화되어,
이후 에이전트 실행 비용 집계에 새 단가가 반영된다.

**Request**
```json
{
  "input_price_per_1k_usd": 0.0025,
  "output_price_per_1k_usd": 0.0100
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `input_price_per_1k_usd` | decimal (≥ 0) | Y | 입력 토큰 1,000개당 USD |
| `output_price_per_1k_usd` | decimal (≥ 0) | Y | 출력 토큰 1,000개당 USD |

**Response** `200 OK` — `LlmModelResponse` (`pricing_updated_at` 갱신됨)

**Error Codes**

| 코드 | 설명 |
|------|------|
| 404 | 해당 ID의 모델이 존재하지 않음 |
| 422 | 음수 가격 등 검증 실패 |

---

### DELETE `/api/v1/llm-models/{id}`

LLM 모델을 비활성화한다 (soft delete). `is_active=false`, `is_default=false`로 변경된다.

**Request**

| 파라미터 | 위치 | 타입 | 필수 | 설명 |
|----------|------|------|------|------|
| `id` | path | string (UUID) | Y | 모델 ID |

**Response** `200 OK` — `LlmModelResponse` (`is_active: false`)

**Error Codes**

| 코드 | 설명 |
|------|------|
| 404 | 해당 ID의 모델이 존재하지 않음 |

---

## 주의사항

- **비활성화 영향 범위**: 비활성 모델을 참조 중인 곳은 실행 시점에 실패한다.
  - 에이전트 실행: 연결된 `llm_model_id`가 비활성이면 실행 오류
  - 문서 요약: 청킹 프로파일의 `summary_llm_model_id`가 비활성이면 요약 잡 `failed`
    (→ `section-summary-model-config.md` 참조)
- **가격 미설정 모델**: `input/output_price_per_1k_usd`가 `null`이면 해당 모델의
  호출 비용은 집계되지 않는다 (usage 토큰 수는 기록됨).
- **API 키**: `api_key_env`는 키 자체가 아니라 서버 환경변수명이다. 응답에는 노출되지 않는다.
