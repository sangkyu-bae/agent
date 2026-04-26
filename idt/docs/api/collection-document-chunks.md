# collection-document-chunks API

> 컬렉션별 임베딩 문서 목록 및 청크 상세 조회 API

## 개요

| 항목 | 내용 |
|------|------|
| Base URL | `/api/v1/collections` |
| Auth | 없음 (현재 버전) |

---

## 엔드포인트 목록

| Method | Path | 설명 |
|--------|------|------|
| GET | `/{collection_name}/documents` | 컬렉션 내 문서 목록 조회 |
| GET | `/{collection_name}/documents/{document_id}/chunks` | 문서별 청크 상세 조회 |

---

## 상세 스펙

### GET /{collection_name}/documents

컬렉션에 포함된 문서 목록을 document_id 기준으로 그룹핑하여 반환한다.

**Path Parameters**

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| collection_name | string | Y | Qdrant 컬렉션명 |

**Query Parameters**

| 파라미터 | 타입 | 기본값 | 제약 | 설명 |
|----------|------|--------|------|------|
| offset | int | 0 | >= 0 | 문서 목록 시작 위치 |
| limit | int | 20 | 1 ~ 100 | 한 번에 반환할 문서 수 |

**Request**

```
GET /api/v1/collections/my_collection/documents?offset=0&limit=20
```

**Response**

```json
{
  "collection_name": "my_collection",
  "documents": [
    {
      "document_id": "doc-abc-123",
      "filename": "금융정책_2026.pdf",
      "category": "finance",
      "chunk_count": 15,
      "chunk_types": ["parent", "child"],
      "user_id": "user-001"
    }
  ],
  "total_documents": 42,
  "offset": 0,
  "limit": 20
}
```

**Response Fields**

| 필드 | 타입 | 설명 |
|------|------|------|
| collection_name | string | 조회한 컬렉션명 |
| documents | DocumentSummary[] | 문서 요약 목록 |
| documents[].document_id | string | 문서 고유 ID |
| documents[].filename | string | 파일명 (없으면 "unknown") |
| documents[].category | string | 카테고리 (없으면 "uncategorized") |
| documents[].chunk_count | int | 해당 문서의 총 청크 수 |
| documents[].chunk_types | string[] | 고유 청크 타입 목록 |
| documents[].user_id | string | 문서 소유자 ID |
| total_documents | int | 전체 문서 수 (페이지네이션 전) |
| offset | int | 현재 offset |
| limit | int | 현재 limit |

**Error Codes**

| 코드 | 설명 |
|------|------|
| 422 | 파라미터 유효성 검증 실패 (offset < 0, limit 범위 초과 등) |
| 500 | Qdrant 연결 실패 등 서버 내부 오류 |

---

### GET /{collection_name}/documents/{document_id}/chunks

특정 문서의 청크를 상세 조회한다. 청크 전략(parent_child, full_token, semantic)을 자동 감지하여 적절한 형태로 반환한다.

**Path Parameters**

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| collection_name | string | Y | Qdrant 컬렉션명 |
| document_id | string | Y | 조회할 문서 ID |

**Query Parameters**

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| include_parent | bool | false | true 시 parent-child 계층 구조로 반환 (parent_child 전략에서만 유효) |

**Request**

```
GET /api/v1/collections/my_collection/documents/doc-abc-123/chunks?include_parent=false
```

**Response (기본 모드: include_parent=false)**

```json
{
  "document_id": "doc-abc-123",
  "filename": "금융정책_2026.pdf",
  "chunk_strategy": "parent_child",
  "total_chunks": 10,
  "chunks": [
    {
      "chunk_id": "chunk-001",
      "chunk_index": 0,
      "chunk_type": "child",
      "content": "청크 텍스트 내용...",
      "metadata": {
        "filename": "금융정책_2026.pdf",
        "category": "finance",
        "parent_id": "parent-001"
      }
    }
  ],
  "parents": null
}
```

**Response (include_parent=true, parent_child 전략)**

```json
{
  "document_id": "doc-abc-123",
  "filename": "금융정책_2026.pdf",
  "chunk_strategy": "parent_child",
  "total_chunks": 10,
  "chunks": [],
  "parents": [
    {
      "chunk_id": "parent-001",
      "chunk_index": 0,
      "chunk_type": "parent",
      "content": "부모 청크 텍스트...",
      "children": [
        {
          "chunk_id": "chunk-001",
          "chunk_index": 0,
          "chunk_type": "child",
          "content": "자식 청크 텍스트...",
          "metadata": {
            "filename": "금융정책_2026.pdf",
            "parent_id": "parent-001"
          }
        }
      ]
    }
  ]
}
```

**Response Fields**

| 필드 | 타입 | 설명 |
|------|------|------|
| document_id | string | 문서 ID |
| filename | string | 파일명 |
| chunk_strategy | string | 감지된 청크 전략 (`parent_child`, `full_token`, `semantic`) |
| total_chunks | int | 총 청크 수 |
| chunks | ChunkDetail[] | 청크 상세 목록 (기본 모드) |
| chunks[].chunk_id | string | 청크 고유 ID |
| chunks[].chunk_index | int | 청크 순서 인덱스 |
| chunks[].chunk_type | string | 청크 타입 (`parent`, `child`, `full`, `semantic`) |
| chunks[].content | string | 청크 텍스트 내용 |
| chunks[].metadata | dict | 메타데이터 (내부용 키 제외) |
| parents | ParentChunkGroup[] \| null | 계층 구조 (include_parent=true 시) |
| parents[].chunk_id | string | 부모 청크 ID |
| parents[].chunk_index | int | 부모 청크 순서 |
| parents[].chunk_type | string | "parent" |
| parents[].content | string | 부모 청크 텍스트 |
| parents[].children | ChunkDetail[] | 해당 부모에 매핑된 자식 청크 목록 |

**제외되는 내부 메타데이터 키**

`content`, `chunk_id`, `chunk_index`, `chunk_type`, `total_chunks`

**청크 전략 자동 감지 규칙**

| chunk_type 값 | 감지 전략 |
|---------------|-----------|
| `parent` 또는 `child` | parent_child |
| `full` | full_token |
| `semantic` | semantic |

**Error Codes**

| 코드 | 설명 |
|------|------|
| 422 | 파라미터 유효성 검증 실패 |
| 500 | Qdrant 연결 실패 등 서버 내부 오류 |

> **참고**: 존재하지 않는 document_id 조회 시 에러가 아닌 빈 결과(total_chunks=0, chunks=[])를 반환한다.
