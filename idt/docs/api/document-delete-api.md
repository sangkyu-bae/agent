# document-delete-api API

> 컬렉션 내 문서 삭제 API — Qdrant 청크 + ES 청크 + MySQL 메타데이터 3중 동기 삭제 (단건/일괄)

## 개요

| 항목 | 내용 |
|------|------|
| Base URL | `/api/v1/collections` |
| Auth | `X-User-Id` 헤더 (필수) |

---

## 엔드포인트 목록

| Method | Path | 설명 |
|--------|------|------|
| DELETE | `/{collection_name}/documents/{document_id}` | 단건 문서 삭제 |
| DELETE | `/{collection_name}/documents` | 일괄 문서 삭제 |

---

## 상세 스펙

### DELETE `/{collection_name}/documents/{document_id}`

단건 문서 삭제. 권한 확인 후 Qdrant → ES → MySQL 순서로 삭제하고 Activity Log를 기록한다.

**Headers**

| 이름 | 필수 | 설명 |
|------|------|------|
| X-User-Id | O | 요청 사용자 ID |

**Path Parameters**

| 이름 | 타입 | 설명 |
|------|------|------|
| collection_name | string | 컬렉션명 |
| document_id | string | 삭제할 문서 ID |

**Request**

Body 없음

**Response** `200 OK`

```json
{
  "document_id": "doc-abc-123",
  "collection_name": "finance-reports",
  "filename": "report_2026.pdf",
  "deleted_qdrant_chunks": 15,
  "deleted_es_chunks": 15
}
```

**Error Codes**

| 코드 | 설명 |
|------|------|
| 404 | `{"detail": "Document not found: {document_id}"}` — MySQL 메타데이터 없음 |
| 403 | `{"detail": "No permission to delete document"}` — 삭제 권한 없음 |
| 500 | `{"detail": "Failed to delete vector chunks"}` — Qdrant 삭제 실패 |

---

### DELETE `/{collection_name}/documents`

일괄 문서 삭제. 권한 사전 검증 후 개별 삭제를 수행하며, 부분 실패를 허용한다.

**Headers**

| 이름 | 필수 | 설명 |
|------|------|------|
| X-User-Id | O | 요청 사용자 ID |

**Path Parameters**

| 이름 | 타입 | 설명 |
|------|------|------|
| collection_name | string | 컬렉션명 |

**Request**

```json
{
  "document_ids": ["doc-abc-123", "doc-def-456", "doc-ghi-789"]
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| document_ids | string[] | O | 삭제할 문서 ID 배열 |

**Response** `200 OK`

```json
{
  "total": 3,
  "success_count": 2,
  "failure_count": 1,
  "results": [
    {
      "document_id": "doc-abc-123",
      "status": "deleted",
      "deleted_qdrant_chunks": 15,
      "deleted_es_chunks": 15,
      "filename": "report_2026.pdf",
      "error": null
    },
    {
      "document_id": "doc-def-456",
      "status": "deleted",
      "deleted_qdrant_chunks": 8,
      "deleted_es_chunks": 8,
      "filename": "policy_v2.pdf",
      "error": null
    },
    {
      "document_id": "doc-ghi-789",
      "status": "failed",
      "deleted_qdrant_chunks": 0,
      "deleted_es_chunks": 0,
      "filename": "",
      "error": "Failed to delete vector chunks"
    }
  ]
}
```

**Error Codes**

| 코드 | 설명 |
|------|------|
| 403 | `{"detail": "No permission to delete document"}` — 권한 사전 검증 실패 (하나라도 권한 없으면 전체 거부) |

---

## 삭제 권한 정책

아래 조건 중 하나를 충족하면 삭제가 허용된다 (OR 조건):

| 조건 | 설명 |
|------|------|
| 업로더 본인 | `document_metadata.user_id == user_id` |
| 컬렉션 소유자 | `collection_permission.owner_id == user_id` |
| ADMIN | `user.role == "admin"` |

---

## 삭제 순서 및 실패 처리

| 단계 | 대상 | 실패 시 동작 |
|------|------|-------------|
| 1 | MySQL 메타데이터 조회 | 404 반환 |
| 2 | 권한 검증 | 403 반환 |
| 3 | Qdrant 청크 삭제 | 500 에러 raise |
| 4 | ES 청크 삭제 | warning 로그 후 계속 진행 (ES는 보조 저장소) |
| 5 | MySQL 메타데이터 삭제 | 에러 raise |
| 6 | Activity Log 기록 | warning 로그 후 계속 진행 |
