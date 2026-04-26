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
