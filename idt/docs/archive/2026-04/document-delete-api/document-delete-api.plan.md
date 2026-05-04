# Plan: document-delete-api

> Feature: 컬렉션 내 문서 삭제 API (Qdrant + MySQL + Elasticsearch 동시 정리)
> Created: 2026-04-29
> Status: Plan
> Priority: High
> Related: `collection-document-browser` (completed), `qdrant-mysql-data-migration` (plan)

---

## 1. 목적 (Why)

컬렉션에 업로드된 문서를 관리하려면 **삭제 기능**이 필수다.
현재 문서 업로드(Ingest/Unified Upload)와 조회(doc_browse) 기능은 있지만,
**특정 문서의 청크 데이터를 삭제하고 관련 DB 레코드를 정리하는 API가 없다.**

사용자가 컬렉션 관리 화면에서:
1. 특정 문서를 선택하여 **단건 삭제**할 수 있어야 하고
2. 여러 문서를 선택하여 **일괄 삭제**할 수 있어야 한다

삭제 시 정리 대상:
- **Qdrant**: `document_id` 기준으로 해당 문서의 모든 청크(벡터 포인트) 삭제
- **MySQL**: `document_metadata` 테이블에서 해당 레코드 삭제
- **Elasticsearch**: 해당 `document_id`의 인덱싱된 청크 삭제
- **Activity Log**: `DELETE_DOCUMENT` 액션 기록

---

## 2. 현재 상태 분석 (As-Is)

### 이미 구축된 인프라

| 구분 | 상태 | 파일 |
|------|------|------|
| Qdrant `delete_by_metadata()` | ✅ | `src/infrastructure/vector/qdrant_vectorstore.py:132` |
| MySQL `delete_by_document_id()` | ✅ | `src/infrastructure/doc_browse/document_metadata_repository.py` |
| MySQL `find_by_document_id()` | ✅ | `src/infrastructure/doc_browse/document_metadata_repository.py` |
| ES `delete_by_query()` | ✅ | `src/infrastructure/elasticsearch/es_repository.py:185` |
| `ActionType.DELETE_DOCUMENT` enum | ✅ | `src/domain/collection/schemas.py` |
| `ActivityLogRepository.save()` | ✅ | `src/infrastructure/collection/activity_log_repository.py` |
| `CollectionPermissionService` | ✅ | `src/application/collection/permission_service.py` |
| `doc_browse_router` (문서 목록/청크 조회) | ✅ | `src/api/routes/doc_browse_router.py` |

### 누락된 부분

| 구분 | 상태 |
|------|------|
| 문서 삭제 UseCase | ❌ 없음 |
| 문서 삭제 API 엔드포인트 (단건) | ❌ 없음 |
| 문서 일괄 삭제 API 엔드포인트 | ❌ 없음 |
| 삭제 권한 정책 (업로더 + 컬렉션 소유자) | ❌ 없음 |
| 삭제 요청/응답 스키마 | ❌ 없음 |

---

## 3. 기능 범위 (Scope)

### In Scope

**A. 단건 삭제 API**
- `DELETE /api/v1/collections/{collection_name}/documents/{document_id}`
- 처리 순서: 권한 확인 → Qdrant 청크 삭제 → ES 청크 삭제 → MySQL 메타데이터 삭제 → Activity Log 기록
- 응답: 삭제된 청크 수, 삭제된 ES 문서 수

**B. 일괄 삭제 API**
- `DELETE /api/v1/collections/{collection_name}/documents`
- Request Body: `{ "document_ids": ["doc-1", "doc-2", ...] }`
- 각 document_id 별로 동일한 삭제 로직 수행
- 응답: 전체/성공/실패 건수, 개별 결과 상세

**C. 삭제 권한 정책**
- **업로더 본인**: 문서의 `user_id`와 요청자 일치 시 삭제 허용
- **컬렉션 소유자**: `CollectionPermission.owner_id`와 요청자 일치 시 삭제 허용
- **ADMIN 역할**: 항상 삭제 허용

**D. 삭제 대상 정리 (3중 동기 삭제)**
- Qdrant: `delete_by_metadata({"document_id": "..."})` (collection_name 스코프 내)
- MySQL: `document_metadata.delete_by_document_id()`
- Elasticsearch: `delete_by_query(index, {"match": {"document_id": "..."}})` (index = collection_name)

**E. Activity Log 기록**
- `ActionType.DELETE_DOCUMENT` 사용
- detail에 `document_id`, `filename`, `deleted_chunks_count` 포함

### Out of Scope
- 프론트엔드 UI (별도 feature로 계획)
- search_history 레코드 정리 (검색 이력은 분석 용도로 유지)
- 소프트 삭제 (물리 삭제만 수행)
- 삭제 취소/복원 기능

---

## 4. 아키텍처 설계 (Where)

### 레이어별 신규/수정 파일

```
src/
├── domain/
│   └── doc_browse/
│       ├── schemas.py              ← (수정) DeleteDocumentResult 추가
│       ├── interfaces.py           ← (수정) delete 메서드 인터페이스 확인 (이미 있음)
│       └── policies.py             ← (신규) DocumentDeletePolicy — 삭제 권한 판단
│
├── application/
│   └── doc_browse/
│       └── delete_document_use_case.py   ← (신규) 핵심 UseCase
│
├── interfaces/
│   └── schemas/
│       └── doc_browse/
│           └── request.py          ← (신규 또는 수정) 삭제 요청 스키마
│
└── api/
    └── routes/
        └── doc_browse_router.py    ← (수정) DELETE 엔드포인트 2개 추가
```

### 의존성 흐름

```
Router (DELETE endpoint)
  → DeleteDocumentUseCase
      → DocumentDeletePolicy (권한 판단)
      → DocumentMetadataRepository (MySQL find + delete)
      → QdrantVectorStore (delete_by_metadata)
      → ElasticsearchRepository (delete_by_query)
      → ActivityLogService (DELETE_DOCUMENT 기록)
```

---

## 5. API 스펙

### 5-1. 단건 삭제

```
DELETE /api/v1/collections/{collection_name}/documents/{document_id}

Headers:
  X-User-Id: string (required)

Response 200:
{
  "document_id": "doc-abc123",
  "collection_name": "finance-reports",
  "deleted_qdrant_chunks": 42,
  "deleted_es_chunks": 42,
  "filename": "보고서.pdf"
}

Response 403: 권한 없음
Response 404: 문서 없음
```

### 5-2. 일괄 삭제

```
DELETE /api/v1/collections/{collection_name}/documents

Headers:
  X-User-Id: string (required)

Body:
{
  "document_ids": ["doc-abc123", "doc-def456"]
}

Response 200:
{
  "total": 2,
  "success_count": 2,
  "failure_count": 0,
  "results": [
    {
      "document_id": "doc-abc123",
      "status": "deleted",
      "deleted_qdrant_chunks": 42,
      "deleted_es_chunks": 42,
      "filename": "보고서.pdf"
    },
    {
      "document_id": "doc-def456",
      "status": "deleted",
      "deleted_qdrant_chunks": 15,
      "deleted_es_chunks": 15,
      "filename": "정책안.pdf"
    }
  ]
}

Response 403: 권한 없음 (하나라도 권한 없으면 전체 실패)
```

---

## 6. 구현 순서

| 단계 | 내용 | 예상 파일 |
|------|------|----------|
| 1 | Domain: `DocumentDeletePolicy` 생성 (권한 판단 로직) | `domain/doc_browse/policies.py` |
| 2 | Domain: 삭제 결과 스키마 추가 | `domain/doc_browse/schemas.py` |
| 3 | Application: `DeleteDocumentUseCase` 구현 | `application/doc_browse/delete_document_use_case.py` |
| 4 | Interface: 요청/응답 스키마 정의 | `interfaces/schemas/doc_browse/` |
| 5 | API: `doc_browse_router`에 DELETE 엔드포인트 추가 | `api/routes/doc_browse_router.py` |
| 6 | DI: UseCase 의존성 주입 설정 | `api/dependencies/` 또는 DI 설정 파일 |
| 7 | 테스트: 단위 테스트 + 통합 테스트 | `tests/` |

---

## 7. 리스크 및 주의사항

| 리스크 | 대응 |
|--------|------|
| Qdrant 삭제 후 MySQL 삭제 실패 시 데이터 불일치 | UseCase에서 순서 보장: Qdrant → ES → MySQL. MySQL 실패 시 에러 반환하되 Qdrant/ES는 이미 삭제됨 → 로그에 기록하여 수동 복구 가능하게 |
| ES 인덱스가 없는 경우 (Qdrant만 사용한 문서) | ES 삭제 시 NotFoundError는 무시하고 진행 |
| 일괄 삭제 시 부분 실패 | 개별 document_id 별로 try-except 처리, 전체 결과 반환 |
| 대량 청크 삭제 시 Qdrant 부하 | 현재 규모에서는 문제 없음. 향후 필요 시 batch 삭제 도입 |

---

## 8. 성공 기준

- [x] 단건 삭제 API가 Qdrant + MySQL + ES 데이터를 모두 정리함
- [x] 일괄 삭제 API가 여러 문서를 한 번에 삭제하고 개별 결과를 반환함
- [x] 업로더 본인 또는 컬렉션 소유자만 삭제 가능 (ADMIN은 항상 허용)
- [x] Activity Log에 DELETE_DOCUMENT 기록이 남음
- [x] 존재하지 않는 document_id에 대해 404 응답
- [x] 권한 없는 사용자의 삭제 시도에 403 응답
