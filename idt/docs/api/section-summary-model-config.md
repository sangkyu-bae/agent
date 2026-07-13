# section-summary-model-config API

> 문서(섹션/문서 단위) 요약에 사용할 LLM 모델을 관리자가 지정하는 API.
> 요약 모델은 **청킹 프로파일의 `summary_llm_model_id` 필드**로 관리하며,
> 업로드 시 KB에 연결된 프로파일을 통해 요약 잡에 전파된다.

## 개요

| 항목 | 내용 |
|------|------|
| 설정 위치 | 청킹 프로파일 (`summary_llm_model_id`) — `/api/v1/admin/chunking/profiles` |
| 모델 출처 | LLM 모델 레지스트리 (`/api/v1/llm-models`, → `llm-model-registry.md`) |
| Auth | 프로파일 CRUD: `require_role("admin")` / 요약 잡 상태·재시도: `CurrentUser` |
| 관련 설계 | card-section-summary (D2/D14/D15/D16), document-summary-routing (D1/D3/D4) |

### 요약 모델 결정 흐름

```
관리자: LLM 모델 등록 (/api/v1/llm-models)
   ↓
관리자: 청킹 프로파일에 summary_llm_model_id 지정
        (None이면 해당 프로파일로 업로드해도 요약 비활성)
   ↓
KB: use_clause_chunking=true + chunking_profile_id 로 프로파일 참조
        (프로파일 미지정/삭제 시 default 프로파일 폴백)
   ↓
문서 업로드 → 프로파일의 summary_llm_model_id 로 섹션 요약 잡 생성
   ↓
잡 실행 시 모델 존재+활성 재검증 → 섹션별 요약 → 문서 단위 요약 체이닝
```

- 프로파일에 `summary_llm_model_id`가 **없으면(null)** 요약 파이프라인 자체가 실행되지 않는다 (업로드 응답 `section_summary: null`).
- 프로파일 저장 시점과 잡 실행 시점 **양쪽에서** 모델의 존재 + `is_active`를 검증한다. 실행 시점에 모델이 비활성화되어 있으면 잡은 `failed` 처리된다.
- 요약 잡 생성 실패는 업로드 결과에 영향을 주지 않는다 (업로드는 성공, `section_summary: null`).

---

## 엔드포인트 목록

### 관리자 — 요약 모델 설정 (청킹 프로파일 CRUD)

Base: `/api/v1/admin/chunking` · Auth: `admin`

| Method | Path | 설명 |
|--------|------|------|
| POST | `/profiles` | 프로파일 생성 (요약 모델 지정 가능) |
| GET | `/profiles` | 활성 프로파일 목록 |
| GET | `/profiles/{profile_id}` | 프로파일 단건 조회 |
| PUT | `/profiles/{profile_id}` | 프로파일 수정 (요약 모델 변경/해제) |
| PUT | `/profiles/{profile_id}/default` | 기본 프로파일 지정 |
| DELETE | `/profiles/{profile_id}` | 프로파일 삭제 (soft delete) |

### 사용자 — 요약 잡 상태 조회/재시도

Base: `/api/v1/knowledge-bases` · Auth: `CurrentUser`

| Method | Path | 설명 |
|--------|------|------|
| GET | `/{kb_id}/documents/{document_id}/section-summary` | 요약 잡 상태 조회 |
| POST | `/{kb_id}/documents/{document_id}/section-summary/retry` | 실패/stale 잡 재실행 |

---

## 상세 스펙

### POST `/api/v1/admin/chunking/profiles`

청킹 프로파일을 생성한다. `summary_llm_model_id`를 지정하면 이 프로파일로
업로드되는 문서에 대해 해당 LLM 모델로 섹션/문서 요약이 실행된다.

**Request**
```json
{
  "name": "policy-docs",
  "description": "정책 문서용 프로파일",
  "boundary_rules": [
    { "pattern": "^제\\d+조", "priority": 1, "level": "parent" }
  ],
  "parent_chunk_size": 2000,
  "chunk_size": 500,
  "chunk_overlap": 50,
  "is_default": false,
  "summary_llm_model_id": "uuid-of-llm-model"
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `name` | string | Y | 프로파일 이름 (활성 프로파일 내 유일) |
| `description` | string | N | 설명 |
| `boundary_rules` | array | Y | 경계 규칙 목록 (`pattern`, `priority`, `level: "parent"\|"child"`) |
| `parent_chunk_size` | int | N | 부모 청크 크기 (기본 2000) |
| `chunk_size` | int | N | 자식 청크 크기 (기본 500) |
| `chunk_overlap` | int | N | 청크 오버랩 (기본 50) |
| `is_default` | boolean | N | 기본 프로파일 여부 (`true` 시 기존 기본 자동 해제) |
| `summary_llm_model_id` | string (UUID) | N | **요약용 LLM 모델 ID. `null`이면 요약 비활성** |

**Response** `201 Created`
```json
{
  "profile_id": "uuid-string",
  "name": "policy-docs",
  "description": "정책 문서용 프로파일",
  "boundary_rules": [
    { "pattern": "^제\\d+조", "priority": 1, "level": "parent" }
  ],
  "parent_chunk_size": 2000,
  "chunk_size": 500,
  "chunk_overlap": 50,
  "is_default": false,
  "summary_llm_model_id": "uuid-of-llm-model",
  "created_at": "2026-07-11T00:00:00",
  "updated_at": "2026-07-11T00:00:00"
}
```

**Error Codes**

| 코드 | 설명 |
|------|------|
| 409 | 동일 이름의 활성 프로파일이 이미 존재 |
| 422 | `summary_llm_model_id`가 존재하지 않거나 비활성 모델 (`... is not an active LLM model`) |
| 422 | 이름/경계 규칙/청크 크기 정책 위반 |

---

### GET `/api/v1/admin/chunking/profiles`

활성 청킹 프로파일 목록을 조회한다. 각 항목에 `summary_llm_model_id`가 포함되므로
프로파일별 요약 모델 설정 현황을 확인할 수 있다.

**Response** `200 OK`
```json
{
  "profiles": [
    {
      "profile_id": "uuid-string",
      "name": "policy-docs",
      "description": null,
      "boundary_rules": [ { "pattern": "^제\\d+조", "priority": 1, "level": "parent" } ],
      "parent_chunk_size": 2000,
      "chunk_size": 500,
      "chunk_overlap": 50,
      "is_default": true,
      "summary_llm_model_id": "uuid-of-llm-model",
      "created_at": "2026-07-11T00:00:00",
      "updated_at": "2026-07-11T00:00:00"
    }
  ],
  "total": 1
}
```

---

### GET `/api/v1/admin/chunking/profiles/{profile_id}`

프로파일 단건 조회. 응답 스키마는 목록 항목과 동일.

**Error Codes**

| 코드 | 설명 |
|------|------|
| 404 | 프로파일이 없거나 삭제됨 |

---

### PUT `/api/v1/admin/chunking/profiles/{profile_id}`

프로파일을 수정한다. 요약 모델 관점의 주요 사용처:

- **요약 모델 변경**: `summary_llm_model_id`에 다른 활성 모델 ID 지정
- **요약 비활성화**: `summary_llm_model_id: null` (이후 업로드부터 요약 미실행)

요청/응답 스키마는 POST와 동일 (전체 필드 교체 방식 — 부분 수정 아님).

**Error Codes**

| 코드 | 설명 |
|------|------|
| 404 | 프로파일이 없거나 삭제됨 |
| 409 | 변경한 이름이 다른 활성 프로파일과 충돌 |
| 422 | `summary_llm_model_id`가 존재하지 않거나 비활성 모델 |

---

### PUT `/api/v1/admin/chunking/profiles/{profile_id}/default`

기본 프로파일로 지정한다 (기존 기본은 자동 해제).
KB가 프로파일을 명시하지 않거나 참조 프로파일이 삭제된 경우 이 기본 프로파일의
`summary_llm_model_id`가 요약 모델로 사용된다.

**Response** `200 OK`
```json
{ "profile_id": "uuid-string", "message": "Default profile updated" }
```

---

### DELETE `/api/v1/admin/chunking/profiles/{profile_id}`

프로파일 soft delete. 삭제된 프로파일을 참조하던 KB는 default 프로파일로 폴백하며,
default도 없으면 legacy 청킹 경로로 폴백된다 (요약 미실행).

**Response** `200 OK`
```json
{ "profile_id": "uuid-string", "message": "Chunking profile deleted" }
```

---

## 요약 잡 API (설정된 모델이 실제 쓰이는 곳)

### 업로드 응답의 `section_summary` 필드

`POST /api/v1/knowledge-bases/{kb_id}/documents` 업로드 성공 시,
요약이 활성인 프로파일이면 응답에 킥오프 정보가 포함된다.

```json
{
  "kb_id": "...",
  "document_id": "...",
  "chunking_strategy": "clause_aware",
  "section_summary": { "job_id": "uuid-string", "status": "pending" }
}
```

- 요약 비활성 프로파일(`summary_llm_model_id: null`) 또는 legacy 경로: `section_summary: null`
- 잡은 프로파일의 `summary_llm_model_id`를 스냅샷으로 보유 — 이후 프로파일을 수정해도 **진행 중인 잡의 모델은 바뀌지 않는다**

### GET `/api/v1/knowledge-bases/{kb_id}/documents/{document_id}/section-summary`

문서의 요약 잡 상태를 조회한다. `completed`는 섹션 전량 + 문서 단위 요약까지 성공을 의미한다.

**Response** `200 OK`
```json
{
  "job_id": "uuid-string",
  "document_id": "doc-id",
  "status": "processing",
  "total_sections": 42,
  "done_sections": 30,
  "failed_sections": 0,
  "is_stale": false,
  "error": null,
  "created_at": "2026-07-11T00:00:00",
  "updated_at": "2026-07-11T00:05:00"
}
```

| 필드 | 설명 |
|------|------|
| `status` | `pending` / `processing` / `completed` / `failed` |
| `is_stale` | 서버 재시작으로 고아가 된 잡 여부 (재시도 대상) |
| `error` | 실패 사유. 모델이 비활성화된 경우 `summary LLM model unavailable or inactive: {id}` |

**Error Codes**

| 코드 | 설명 |
|------|------|
| 403 | KB 접근 권한 없음 |
| 404 | 요약 비활성 프로파일로 업로드된 문서 (잡 없음) |

### POST `/api/v1/knowledge-bases/{kb_id}/documents/{document_id}/section-summary/retry`

실패했거나 stale한 잡을 재실행한다. 완료된 섹션은 재처리하지 않고(멱등),
문서 단위 요약은 재생성한다. 재시도 역시 잡에 저장된 `llm_model_id`를 사용한다.

**Response** `202 Accepted` — 상태 조회와 동일 스키마

**Error Codes**

| 코드 | 설명 |
|------|------|
| 403 | KB 접근 권한 없음 |
| 404 | 잡 없음 |
| 409 | 잡이 이미 실행 중 |

---

## 주의사항

- 모델 등록/비활성화 자체는 `llm-model-registry.md`의 `/api/v1/llm-models` API를 사용한다. 요약 모델로 지정된 모델을 비활성화(DELETE)하면 **이후 실행되는 요약 잡이 실패**하므로, 비활성화 전 해당 모델을 참조하는 프로파일을 먼저 다른 모델로 변경해야 한다.
- 프로파일 수정은 이후 업로드부터 적용된다. 기존 문서의 요약을 새 모델로 다시 만들려면 문서 재업로드가 필요하다 (retry는 기존 잡의 모델을 사용).
- 요약 실행 조건: KB `use_clause_chunking=true` **그리고** 해석된 프로파일에 `summary_llm_model_id` 존재.

**구현 위치**

| 역할 | 파일 |
|------|------|
| 프로파일 CRUD 라우터 | `src/api/routes/admin_chunking_router.py` |
| 프로파일 유스케이스 (모델 검증 D16) | `src/application/chunking_profile/use_case.py` |
| 요약 스펙 해석 (KB→프로파일→모델) | `src/application/knowledge_base/chunking_resolver.py` |
| 요약 잡 러너 (모델 활성 재검증) | `src/application/section_summary/use_case.py` |
| 잡 상태/재시도 라우터 | `src/api/routes/knowledge_base_router.py` |
