# Plan: collection-document-chunks

> Feature: 컬렉션별 임베딩 문서 및 청크 조회 API
> Created: 2026-04-23
> Status: Plan

---

## 1. 목적 (Why)

컬렉션에 저장된 임베딩 데이터를 **문서 단위로 탐색**할 수 있는 API 제공.

현재 시스템은 문서를 업로드하면 청킹 전략에 따라 여러 청크로 분할하여 Qdrant에 저장한다.
하지만 "이 컬렉션에 어떤 문서가 들어있는지", "해당 문서의 청크가 어떤 순서로 구성되어 있는지"를
확인할 방법이 없다.

**사용자 흐름**: 컬렉션 선택 → 문서 목록 조회 → 문서 클릭 → 청크 순서대로 상세 보기

---

## 2. 기능 범위 (Scope)

### In Scope

| # | 기능 | 설명 |
|---|------|------|
| 1 | **컬렉션 내 문서 목록 API** | `document_id` 기준 그룹핑, `filename` 함께 표시, 청크 수 포함 |
| 2 | **문서별 청크 상세 조회 API** | `chunk_index` 순서 정렬, 기본 child만 반환 |
| 3 | **parent-child 계층 모드** | 쿼리 파라미터(`include_parent=true`)로 parent → children 계층 구조 반환 |

### Out of Scope

- 청크 내용 수정/삭제 (별도 기능)
- 임베딩 벡터 값 반환 (용량 문제로 제외)
- 페이지네이션 커서 기반 무한스크롤 (v1에서는 offset/limit)

---

## 3. 현재 메타데이터 구조 분석

### 청킹 시 저장되는 메타데이터

| 전략 | 메타데이터 키 | 설명 |
|------|-------------|------|
| **공통** (chunk_node) | `document_id` | 파이프라인에서 생성된 문서 고유 ID |
| **공통** (chunk_node) | `category` | 문서 분류 (policy, faq 등) |
| **공통** (store_node) | `user_id` | 업로드한 사용자 ID |
| **full_token** | `chunk_type: "full"` | 단순 토큰 분할 |
| **full_token** | `chunk_index`, `total_chunks` | 순서 및 전체 청크 수 |
| **parent_child** | `chunk_type: "parent"/"child"` | 계층 구분 |
| **parent_child** | `parent_id` | child → parent 참조 ID |
| **parent_child** | `chunk_id` | 청크 고유 ID |
| **parent_child** | `chunk_index`, `total_chunks` | 순서 및 전체 수 |
| **semantic** | `chunk_type: "semantic"` | 의미 기반 분할 |
| **semantic** | `chunk_index` | 순서 |

> **참고**: `filename`은 parser 단계에서 metadata에 포함되며, chunk 시 `merge_metadata`로 전파됨.

---

## 4. API 설계 개요

### 4-1. 컬렉션 내 문서 목록 조회

```
GET /api/v1/collections/{collection_name}/documents
```

**Query Parameters**:
| Param | Type | Default | 설명 |
|-------|------|---------|------|
| `offset` | int | 0 | 건너뛸 문서 수 |
| `limit` | int | 20 | 반환할 문서 수 |

**Response**:
```json
{
  "collection_name": "documents",
  "documents": [
    {
      "document_id": "abc-123-def",
      "filename": "금융정책_2026.pdf",
      "category": "policy",
      "chunk_count": 6,
      "chunk_types": ["child", "parent"],
      "user_id": "user_001"
    }
  ],
  "total_documents": 15,
  "offset": 0,
  "limit": 20
}
```

**구현 방식**: Qdrant `scroll` API로 전체 포인트를 조회 후 `document_id` 기준 그룹핑.
청크 내용/벡터는 제외하고 payload 메타데이터만 가져온다.

---

### 4-2. 문서별 청크 상세 조회

```
GET /api/v1/collections/{collection_name}/documents/{document_id}/chunks
```

**Query Parameters**:
| Param | Type | Default | 설명 |
|-------|------|---------|------|
| `include_parent` | bool | false | true 시 parent → children 계층 구조 반환 |

**Response (기본 — child만, chunk_index 순서)**:
```json
{
  "document_id": "abc-123-def",
  "filename": "금융정책_2026.pdf",
  "chunk_strategy": "parent_child",
  "total_chunks": 6,
  "chunks": [
    {
      "chunk_id": "point-uuid-1",
      "chunk_index": 0,
      "chunk_type": "child",
      "content": "금리가 상승하면 채권 가격은...",
      "metadata": {
        "parent_id": "parent-uuid-1",
        "category": "policy"
      }
    },
    {
      "chunk_id": "point-uuid-2",
      "chunk_index": 1,
      "chunk_type": "child",
      "content": "통화정책 완화 시...",
      "metadata": {
        "parent_id": "parent-uuid-1",
        "category": "policy"
      }
    }
  ]
}
```

**Response (include_parent=true — parent → children 계층)**:
```json
{
  "document_id": "abc-123-def",
  "filename": "금융정책_2026.pdf",
  "chunk_strategy": "parent_child",
  "total_chunks": 8,
  "parents": [
    {
      "chunk_id": "parent-uuid-1",
      "chunk_index": 0,
      "chunk_type": "parent",
      "content": "금리와 채권의 관계에 대한 전체 내용...",
      "children": [
        {
          "chunk_id": "point-uuid-1",
          "chunk_index": 0,
          "chunk_type": "child",
          "content": "금리가 상승하면 채권 가격은..."
        },
        {
          "chunk_id": "point-uuid-2",
          "chunk_index": 1,
          "chunk_type": "child",
          "content": "통화정책 완화 시..."
        }
      ]
    }
  ]
}
```

> full_token/semantic 전략의 경우 parent가 없으므로 `include_parent` 무시, flat list 반환.

---

## 5. 레이어별 설계

| Layer | 파일 | 역할 |
|-------|------|------|
| **domain** | `src/domain/doc_browse/schemas.py` | DocumentSummary, ChunkDetail VO |
| **application** | `src/application/doc_browse/list_documents_use_case.py` | 문서 목록 그룹핑 로직 |
| **application** | `src/application/doc_browse/get_chunks_use_case.py` | 청크 상세 조회 + 정렬/계층화 |
| **infrastructure** | 기존 `QdrantVectorStore` / Qdrant client 활용 | scroll API 호출 |
| **interfaces** | `src/api/routes/doc_browse_router.py` | REST 엔드포인트 2개 |

---

## 6. 기술 의존성

| 모듈 | 상태 | 비고 |
|------|------|------|
| Qdrant AsyncClient | 구현됨 | `scroll()` API 활용 |
| QdrantRetriever.retrieve_by_metadata | 구현됨 | metadata 필터 + scroll |
| MetadataFilter | 구현됨 | document_id 필터링 |
| 기존 컬렉션 목록 API (`/api/v1/rag-tools/collections`) | 구현됨 | UI 1단계에서 사용 |

---

## 7. TDD 계획

| 테스트 파일 | 테스트 항목 |
|------------|------------|
| `tests/application/doc_browse/test_list_documents_use_case.py` | document_id 그룹핑, 청크 수 집계, 빈 컬렉션 |
| `tests/application/doc_browse/test_get_chunks_use_case.py` | chunk_index 정렬, child-only 필터, parent-child 계층화 |
| `tests/api/test_doc_browse_router.py` | 엔드포인트 통합 테스트 |

---

## 8. CLAUDE.md 규칙 체크

- [x] domain에 외부 의존성 없음 (VO/schema만 정의)
- [x] application은 domain 규칙 조합 (그룹핑, 정렬 로직)
- [x] infrastructure 기존 어댑터 재사용 (Qdrant client)
- [x] LOG-001 로깅 적용
- [x] TDD 순서: 테스트 → 구현

---

## 9. 완료 기준

- [ ] `GET /api/v1/collections/{collection_name}/documents` — 문서 목록 반환 (document_id + filename)
- [ ] `GET /api/v1/collections/{collection_name}/documents/{document_id}/chunks` — 청크 상세 반환
- [ ] 기본 모드: child만 chunk_index 순서 정렬
- [ ] `include_parent=true`: parent → children 계층 구조 반환
- [ ] full_token/semantic 전략 문서도 정상 조회
- [ ] 테스트 커버리지 (use_case + router)
- [ ] LOG-001 로깅 적용
