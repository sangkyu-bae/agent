# unified-pdf-upload-api API

> PDF 업로드 시 컬렉션의 임베딩 모델을 자동 조회하여 Qdrant(벡터) + Elasticsearch(BM25) 동시 저장하는 통합 API

## 개요

| 항목 | 내용 |
|------|------|
| Base URL | `/api/v1/documents` |
| Auth | 없음 (추후 JWT 연동 예정) |

---

## 엔드포인트 목록

| Method | Path | 설명 |
|--------|------|------|
| POST | `/api/v1/documents/upload-all` | PDF 통합 업로드 (Qdrant + ES 동시 저장) |

---

## 상세 스펙

### POST `/api/v1/documents/upload-all`

PDF 파일을 업로드하면 지정된 컬렉션의 임베딩 모델로 벡터를 생성하고, Qdrant(시맨틱) + Elasticsearch(BM25) 양쪽에 병렬 저장한다. 기존 2회 API 호출(documents/upload + chunk-index/upload)을 1회로 통합한다.

**Request**

```
Content-Type: multipart/form-data
```

| 파라미터 | 위치 | 타입 | 필수 | 제약 | 기본값 | 설명 |
|----------|------|------|:----:|------|--------|------|
| file | Body (File) | UploadFile | O | PDF만 허용 | - | 업로드할 PDF 파일 |
| user_id | Query | string | O | - | - | 문서 소유자 ID |
| collection_name | Query | string | O | 기존 컬렉션만 | - | 대상 Qdrant 컬렉션명 |
| child_chunk_size | Query | integer | X | 100 ~ 4000 | 500 | 자식 청크 크기 (토큰) |
| child_chunk_overlap | Query | integer | X | 0 ~ 500 | 50 | 자식 청크 오버랩 (토큰) |
| top_keywords | Query | integer | X | 1 ~ 50 | 10 | ES 저장 시 추출할 키워드 수 |

> Parent 청크 크기는 2000 토큰 고정 (사용자 입력 불가)

**cURL 예시**

```bash
curl -X POST "http://localhost:8000/api/v1/documents/upload-all?user_id=user-1&collection_name=my-collection&child_chunk_size=500&child_chunk_overlap=50&top_keywords=10" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@document.pdf"
```

**Response (200 OK)**

```json
{
  "document_id": "550e8400-e29b-41d4-a716-446655440000",
  "filename": "document.pdf",
  "total_pages": 10,
  "chunk_count": 25,
  "qdrant": {
    "collection_name": "my-collection",
    "stored_ids": ["id-1", "id-2", "..."],
    "embedding_model": "text-embedding-3-small",
    "status": "success",
    "error": null
  },
  "es": {
    "index_name": "idt-documents",
    "indexed_count": 25,
    "status": "success",
    "error": null
  },
  "chunking_config": {
    "strategy": "parent_child",
    "parent_chunk_size": 2000,
    "child_chunk_size": 500,
    "child_chunk_overlap": 50
  },
  "status": "completed"
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| document_id | string | 생성된 문서 UUID |
| filename | string | 업로드된 파일명 |
| total_pages | integer | PDF 전체 페이지 수 |
| chunk_count | integer | 생성된 청크 수 |
| qdrant | QdrantResult | Qdrant 저장 결과 |
| qdrant.collection_name | string | 저장된 컬렉션명 |
| qdrant.stored_ids | string[] | 저장된 벡터 ID 목록 |
| qdrant.embedding_model | string | 사용된 임베딩 모델명 |
| qdrant.status | string | `"success"` \| `"failed"` |
| qdrant.error | string \| null | 실패 시 에러 메시지 |
| es | EsResult | Elasticsearch 저장 결과 |
| es.index_name | string | ES 인덱스명 |
| es.indexed_count | integer | 인덱싱된 문서 수 |
| es.status | string | `"success"` \| `"failed"` |
| es.error | string \| null | 실패 시 에러 메시지 |
| chunking_config | ChunkingConfig | 적용된 청킹 설정 |
| chunking_config.strategy | string | `"parent_child"` 고정 |
| chunking_config.parent_chunk_size | integer | Parent 청크 크기 (2000 고정) |
| chunking_config.child_chunk_size | integer | 요청한 자식 청크 크기 |
| chunking_config.child_chunk_overlap | integer | 요청한 오버랩 크기 |
| status | string | `"completed"` \| `"partial"` \| `"failed"` |

**status 값 설명**

| status | 조건 |
|--------|------|
| `"completed"` | Qdrant + ES 모두 성공 |
| `"partial"` | 한쪽만 성공 (실패 쪽 `error` 필드에 사유 기재) |
| `"failed"` | 양쪽 모두 실패 |

**부분 성공 응답 예시 (Qdrant 실패, ES 성공)**

```json
{
  "document_id": "550e8400-e29b-41d4-a716-446655440000",
  "filename": "document.pdf",
  "total_pages": 10,
  "chunk_count": 25,
  "qdrant": {
    "collection_name": "my-collection",
    "stored_ids": [],
    "embedding_model": "text-embedding-3-small",
    "status": "failed",
    "error": "Connection refused: Qdrant server unavailable"
  },
  "es": {
    "index_name": "idt-documents",
    "indexed_count": 25,
    "status": "success",
    "error": null
  },
  "chunking_config": {
    "strategy": "parent_child",
    "parent_chunk_size": 2000,
    "child_chunk_size": 500,
    "child_chunk_overlap": 50
  },
  "status": "partial"
}
```

**Error Codes**

| 코드 | 조건 | body.detail |
|------|------|-------------|
| 422 | 컬렉션 미존재 | `"Collection '{name}' not found"` |
| 422 | 임베딩 모델 조회 불가 | `"Cannot determine embedding model for collection '{name}'"` |
| 422 | 등록되지 않은 임베딩 모델 | `"Embedding model '{model}' not registered"` |
| 422 | PDF 파싱 실패 | `"Failed to parse PDF: {reason}"` |
| 500 | 양쪽 저장 모두 실패 | `"Both Qdrant and ES storage failed"` |

**에러 응답 예시 (422)**

```json
{
  "detail": "Collection 'nonexistent-collection' not found"
}
```

---

## 전제조건

- 대상 Qdrant 컬렉션이 **사전 생성**되어 있어야 함
- 컬렉션 생성 시 `collection_activity_log`에 `embedding_model` 정보가 기록되어 있어야 함
- `embedding_model` 테이블에 해당 모델이 등록되어 있어야 함
- Qdrant / Elasticsearch 서버가 가동 중이어야 함

## 내부 처리 흐름

```
1. 컬렉션 존재 확인 (Qdrant)
2. 임베딩 모델 자동 조회 (activity_log → embedding_model 테이블)
3. PDF 파싱 (PDFParserInterface)
4. Parent-Child 청킹 (parent=2000 고정, child=파라미터)
5. 병렬 저장 (asyncio.gather)
   ├─ 5-A. Qdrant: 임베딩 벡터 생성 → 컬렉션에 저장
   └─ 5-B. ES: 키워드 추출 → BM25 인덱싱
6. 활동 로그 기록 (ADD_DOCUMENT)
7. 통합 응답 반환
```
