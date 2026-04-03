# 문서 업로드 API

> **태그**: `documents`
> **Base Path**: `/api/v1/documents`
> **주의**: 이 API는 레거시입니다. 새 프로젝트는 [PDF 인제스트 API](./02-ingest.md)를 사용하세요.

---

## 개요

PDF 파일을 업로드하면 서버가 자동으로:
1. PDF 텍스트를 파싱
2. Parent-Child 전략으로 청크(분할) 생성
3. OpenAI 임베딩으로 벡터화
4. Qdrant 벡터 DB에 저장
5. LLM으로 문서 카테고리 자동 분류

---

## 엔드포인트

### 1. PDF 동기 업로드

**`POST /api/v1/documents/upload`**

파일을 즉시 처리하고 결과를 반환합니다. 처리가 완료될 때까지 대기합니다.

#### 요청

| 위치 | 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|------|---------|------|------|--------|------|
| form-data | `file` | File | ✅ | - | 업로드할 PDF 파일 |
| query | `user_id` | string | ✅ | - | 문서 소유자 ID |
| query | `child_chunk_size` | int | ❌ | 500 | Child 청크 크기 (100~4000 토큰) |

#### 응답 (200 OK)

```json
{
  "document_id": "abc123",
  "filename": "policy_2024.pdf",
  "category": "금융정책",
  "category_confidence": 0.92,
  "total_pages": 15,
  "chunk_count": 47,
  "stored_ids": ["id1", "id2", "..."],
  "status": "completed",
  "errors": []
}
```

| 필드 | 설명 |
|------|------|
| `document_id` | Qdrant에 저장된 문서 고유 ID |
| `category` | LLM이 분류한 문서 카테고리 |
| `category_confidence` | 분류 신뢰도 (0.0~1.0) |
| `chunk_count` | 생성된 청크(벡터) 수 |
| `stored_ids` | Qdrant에 저장된 벡터 ID 목록 |
| `status` | `completed` 또는 `failed` |

#### 오류 응답 (500)

```json
{
  "message": "Document processing failed",
  "errors": ["PDF parsing error: ..."]
}
```

#### 예제

```bash
curl -X POST "http://localhost:8000/api/v1/documents/upload?user_id=user_001&child_chunk_size=500" \
  -F "file=@report.pdf"
```

---

### 2. PDF 비동기 업로드

**`POST /api/v1/documents/upload/async`**

파일을 큐에 등록하고 즉시 `task_id`를 반환합니다. 실제 처리는 백그라운드에서 진행됩니다.

> ⚠️ 현재 구현에서는 큐 등록만 처리되며, 실제 백그라운드 처리 로직은 미완성입니다.

#### 요청

| 위치 | 파라미터 | 타입 | 필수 | 설명 |
|------|---------|------|------|------|
| form-data | `file` | File | ✅ | 업로드할 PDF 파일 |
| query | `user_id` | string | ✅ | 문서 소유자 ID |

#### 응답 (200 OK)

```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "message": "Document queued for processing"
}
```

---

### 3. 비동기 처리 상태 조회

**`GET /api/v1/documents/upload/status/{task_id}`**

비동기 업로드 작업의 현재 상태를 조회합니다.

#### 경로 파라미터

| 파라미터 | 설명 |
|---------|------|
| `task_id` | 비동기 업로드 시 발급된 task ID |

#### 응답 (200 OK)

```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "result": null,
  "error": null
}
```

| status 값 | 의미 |
|-----------|------|
| `pending` | 처리 대기 중 |
| `completed` | 처리 완료 |
| `failed` | 처리 실패 |

#### 오류 응답 (404)

```json
{
  "detail": "Task not found"
}
```
