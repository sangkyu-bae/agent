# Document Soft Delete Design Document

> **Summary**: 문서 삭제를 3-store(RDB·Qdrant·ES) 물리 삭제에서 플래그 기반 soft delete로 전환. 검색 제외 필터를 **최저 레이어(es_repo.search / qdrant 읽기 빌더 / RDB 쿼리)에 단일 주입**하여 누락 위험을 최소화하고, 백엔드 복구 API를 제공한다.
>
> **Project**: sangplusbot (idt)
> **Version**: 0.1
> **Author**: 배상규
> **Date**: 2026-06-04
> **Status**: Draft
> **Planning Doc**: [document-soft-delete.plan.md](../../01-plan/features/document-soft-delete.plan.md)

### Pipeline References (if applicable)

| Phase | Document | Status |
|-------|----------|--------|
| Phase 1 | Schema Definition | ✅ (본 문서 §3) |
| Phase 4 | API Spec | ✅ (본 문서 §4) |

---

## 1. Overview

### 1.1 Design Goals

1. **데이터 보존 + 복구**: 3-store 모두 플래그 기반 soft delete로 전환, 백엔드 restore API로 검색까지 완전 복원.
2. **검색 정합성 무누락**: 삭제 문서가 어떤 RAG 검색·조회에도 노출되지 않도록, 제외 필터를 **최저 레이어에 단일 주입**.
3. **무회귀**: 기존 문서(플래그 부재)는 정상 노출 — `must_not is_deleted=true` / `deleted_at IS NULL` 방식으로 백필 불필요.
4. **부분 실패 내성 + 멱등성**: 3-store 비원자성 환경에서 RDB를 source of truth로, 저장소별 best-effort, 재시도 가능한 멱등 설계.

### 1.2 Design Principles

- **Inject at lowest layer**: 검색 제외 필터를 호출부마다 산발 주입하지 않고, 각 저장소의 단일 choke point에 주입 → 누락 구조적 차단.
- **Single source of truth**: RDB `document_metadata.deleted_at`이 문서 삭제 상태의 정본. Qdrant/ES는 검색 제외용 보조 플래그.
- **Idempotent soft ops**: soft delete / restore는 여러 번 호출해도 동일 결과 (set 연산).
- **기존 코드 최소 변경**: 삭제는 동작만 hard→soft 교체, 읽기는 필터만 추가.

### 1.3 핵심 전략 — 9개 경로 → 소수 주입 지점으로 축소

Plan §1.3의 9개 read 경로를 코드 감사한 결과, **대부분 저수준 컴포넌트로 수렴**한다:

| 상위 경로 | 실제 수렴 지점 | 주입 필요? |
|-----------|---------------|:---------:|
| collection_search | → `HybridSearchUseCase` → `es_repo.search` + `QdrantVectorStore` | 위임 (자동 커버) |
| InternalDocumentSearchTool(RAG Agent) | → `HybridSearchUseCase` → 동일 | 위임 (자동 커버) |
| hybrid `_fetch_bm25` | → `es_repo.search` | ★ ES 단일 지점 |
| hybrid `_fetch_vector` | → `QdrantVectorStore.search_by_vector` | ★ Qdrant 빌더 |
| 벡터스토어 직접 | `QdrantVectorStore._build_qdrant_filter` | ★ Qdrant 빌더 |
| 리트리버 | `QdrantRetriever.retrieve_with_scores`/`retrieve_by_metadata` | ★ Qdrant 빌더 |
| Parent-Child | `ParentChildRetriever`(상속) + `_fetch_parents` | ★ 상속 + parents fetch |
| 청크 조회 | `GetChunksUseCase._scroll_filtered` | ★ Qdrant scroll |
| 목록 조회 | `DocumentMetadataRepository.find_by_collection` | ★ RDB |

**→ 실제 주입 지점 (6곳)**:
1. **ES**: `es_repository.search` 1곳 (모든 ES 검색이 통과) — `bool.must_not term(is_deleted=true)` 래핑
2. **Qdrant 벡터검색**: `QdrantVectorStore.search_by_vector` (`_build_qdrant_filter`)
3. **Qdrant 리트리버**: `QdrantRetriever.retrieve_with_scores` + `retrieve_by_metadata`
4. **Qdrant parents**: `ParentChildRetriever._fetch_parents`
5. **Qdrant scroll**: `GetChunksUseCase._scroll_filtered`
6. **RDB**: `DocumentMetadataRepository.find_by_collection` + `find_by_document_id`

> ★ collection_search·RAG Agent는 HybridSearch 경유라 1·2번으로 자동 커버됨. 이것이 핵심 — 검증 표면이 9 → 6으로 축소.

---

## 2. Architecture

### 2.1 Component Diagram

```
┌────────────────────────────────────────────────────────────────────┐
│  [WRITE — Soft Delete / Restore]                                    │
│                                                                     │
│  DELETE /collections/{c}/documents/{id}                             │
│  POST   /collections/{c}/documents/{id}/restore                    │
│  GET    /collections/{c}/documents/deleted   (휴지통 목록)          │
│         │                                                           │
│   ┌─────▼──────────────┐     ┌──────────────────────┐              │
│   │ DeleteDocumentUC   │     │ RestoreDocumentUC     │ (신규)       │
│   │  (hard→soft)       │     │                       │              │
│   └─────┬──────────────┘     └──────────┬───────────┘              │
│         │ mark deleted=true             │ mark deleted=false        │
│   ┌─────▼─────┬──────────┬──────────────▼────┐                     │
│   │ RDB       │ Qdrant   │ ES                 │                     │
│   │ deleted_at│set_payload│ update_by_query   │                     │
│   │  =now     │ is_deleted│  is_deleted=true  │                     │
│   └───────────┴──────────┴────────────────────┘                    │
└────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────┐
│  [READ — 삭제 제외 필터 단일 주입]                                   │
│                                                                     │
│  RAG/검색/조회 → 6개 주입 지점에서 삭제 제외                         │
│   ES   : es_repo.search → must_not term(is_deleted=true)            │
│   Qdrant: search_by_vector / retriever / scroll / parents          │
│           → must_not FieldCondition(is_deleted=true)                │
│   RDB  : find_by_collection / find_by_document_id                  │
│           → WHERE deleted_at IS NULL                                │
└────────────────────────────────────────────────────────────────────┘
```

### 2.2 Data Flow — Soft Delete

```
DeleteDocumentUseCase.execute_single (수정)
  ├─ find_by_document_id (deleted_at IS NULL)  → 없으면 NotFound
  ├─ 권한 검증 (DocumentDeletePolicy, 기존)
  ├─ Qdrant: client.set_payload(payload={is_deleted:true}, points=Filter(document_id))
  ├─ ES:     es_repo.update_by_query(index, term(document_id), set is_deleted=true)
  ├─ RDB:    repo.soft_delete_by_document_id(document_id) → UPDATE deleted_at=now
  └─ ActivityLog(DELETE_DOCUMENT)   ← 기존 유지
```

### 2.3 Data Flow — Restore

```
RestoreDocumentUseCase.execute_single (신규)
  ├─ find_deleted_by_document_id (deleted_at IS NOT NULL)  → 없으면 NotFound
  ├─ 권한 검증 (DocumentDeletePolicy 재사용)
  ├─ RDB:    repo.restore_by_document_id → UPDATE deleted_at=NULL   (source of truth 우선)
  ├─ Qdrant: client.set_payload(payload={is_deleted:false}, points=Filter(document_id))
  ├─ ES:     es_repo.update_by_query(term(document_id), set is_deleted=false)
  └─ ActivityLog(RESTORE_DOCUMENT)
```

### 2.4 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| DeleteDocumentUseCase | metadata_repo, qdrant_client, es_repo, policy | soft 마킹 |
| RestoreDocumentUseCase | 동일 | soft 해제 |
| es_repository.search | (내부) deleted 제외 래핑 | 모든 ES 검색 정합성 |
| QdrantVectorStore/Retriever | (내부) deleted 제외 필터 | 모든 Qdrant 검색 정합성 |

---

## 3. Data Model

### 3.1 RDB — `document_metadata` 확장

```python
# src/infrastructure/doc_browse/models.py
class DocumentMetadataModel(Base):
    __tablename__ = "document_metadata"
    # ... 기존 컬럼 유지 ...
    deleted_at = Column(DateTime, nullable=True, default=None)  # NULL=정상, 값=삭제시각

    __table_args__ = (
        Index("idx_dm_collection", "collection_name"),
        Index("idx_dm_user", "user_id"),
        Index("idx_dm_created", "created_at"),
        Index("idx_dm_deleted_at", "deleted_at"),  # 신규 — 제외 필터 성능
    )
```

**Flyway 마이그레이션** (`/db-migration` 스킬로 생성):
```sql
-- db/migration/Vxxx__add_deleted_at_to_document_metadata.sql
ALTER TABLE document_metadata
    ADD COLUMN deleted_at DATETIME NULL DEFAULT NULL;
CREATE INDEX idx_dm_deleted_at ON document_metadata (deleted_at);
```

### 3.2 ES — `is_deleted` 매핑

```json
// 인덱스 매핑 추가 (ensure_index_exists mappings 또는 put_mapping)
{ "properties": { "is_deleted": { "type": "boolean" } } }
```

- 기존 색인 문서는 `is_deleted` 부재 → `must_not term(is_deleted=true)`에 자연 통과 (정상 취급)
- 신규 색인 시 `is_deleted: false` 기본 부여 권장 (ingest 경로) — 단 미부여라도 검색 정합성엔 무영향
- **배포**: dynamic mapping이 boolean 자동 추가 가능하나, 명시적 `put_mapping`으로 안정화 (reindex 불요 — 필드 추가만)

### 3.3 Qdrant — `is_deleted` 페이로드

- soft delete 시 `set_payload(is_deleted=true)` — 포인트 보존, 페이로드만 갱신
- 검색 제외: `must_not=[FieldCondition(key="is_deleted", match=MatchValue(value=True))]`
- 기존 포인트는 키 부재 → must_not 미매칭 → 통과 (정상)
- **성능**: `create_payload_index(field="is_deleted", field_schema=BOOL)` 권장 (선택, 대용량 시)

### 3.4 Domain Schema 확장

```python
# src/domain/doc_browse/schemas.py
@dataclass(frozen=True)
class DocumentMetadata:
    document_id: str
    collection_name: str
    filename: str
    category: str
    user_id: str
    chunk_count: int
    chunk_strategy: str
    deleted_at: Optional[str] = None  # ISO8601 | None (신규, 하위호환 기본 None)


@dataclass(frozen=True)
class RestoreDocumentResult:        # 신규
    document_id: str
    collection_name: str
    filename: str
    restored_qdrant: bool
    restored_es: bool
    status: str                     # "restored"
    error: Optional[str] = None
```

### 3.5 상태 의미표

| RDB deleted_at | Qdrant is_deleted | ES is_deleted | 의미 |
|:---:|:---:|:---:|------|
| NULL | (부재/false) | (부재/false) | 정상 (검색·목록 노출) |
| 값 | true | true | soft deleted (휴지통, 검색 제외) |
| NULL | true | true | 복구 중 부분실패 → 재복구 대상 (RDB 기준 정상) |

---

## 4. API Specification

### 4.1 Endpoint List (추가/변경)

| Method | Path | Description | Auth | 변경 |
|--------|------|-------------|------|------|
| DELETE | `/collections/{c}/documents/{id}` | 단건 soft delete | Required | 동작 변경 |
| DELETE | `/collections/{c}/documents` (batch body) | 배치 soft delete | Required | 동작 변경 |
| GET | `/collections/{c}/documents/deleted` | 삭제 문서(휴지통) 목록 | Required | 신규 |
| POST | `/collections/{c}/documents/{id}/restore` | 단건 복구 | Required | 신규 |
| POST | `/collections/{c}/documents/restore` (batch body) | 배치 복구 | Required | 신규 |

### 4.2 상세 — 복구

#### `POST /collections/{c}/documents/{id}/restore`

**Response (200 OK):**
```json
{
  "document_id": "doc-123",
  "collection_name": "policy_docs",
  "filename": "약관.pdf",
  "restored_qdrant": true,
  "restored_es": true,
  "status": "restored"
}
```

**Errors**: `404` 삭제 문서 없음 / `403` 권한 없음

#### `GET /collections/{c}/documents/deleted?offset=0&limit=20`

**Response (200 OK):**
```json
{
  "collection_name": "policy_docs",
  "documents": [
    { "document_id": "doc-123", "filename": "약관.pdf", "category": "policy",
      "chunk_count": 12, "user_id": "u-1", "deleted_at": "2026-06-04T05:00:00Z" }
  ],
  "total_documents": 1, "offset": 0, "limit": 20
}
```

> 기존 목록(`GET /documents`)은 `deleted_at IS NULL`만 반환하도록 변경 (삭제 문서 제외).

---

## 5. UI/UX Design

N/A — 백엔드 API만. 프론트 휴지통 UI는 후속 PDCA (API 계약 동기화 필요: `idt_front/src/types`, `src/services`).

---

## 6. Error Handling

### 6.1 부분 실패 시나리오 (3-store 비원자성)

| 시나리오 | 처리 | 비고 |
|---------|------|------|
| RDB soft delete 성공, Qdrant 실패 | RDB 정본 유지(삭제됨). Qdrant warning 로그, 검색엔 Qdrant 포인트 잔존 가능 | 재삭제로 멱등 복구. ★ Qdrant 잔존 포인트는 RDB 기준 삭제라 목록엔 없으나 RAG엔 노출 위험 → 6.2 보완 |
| ES update_by_query 실패 | warning 후 계속 (기존 `_delete_es_chunks` 패턴 유지) | 재삭제 멱등 |
| 복구 중 RDB만 성공 | 상태표 3행(NULL/true/true) → 검색 제외 유지(과보수). 재복구로 정합 | fail-safe: 안 보이는 쪽이 안전 |
| 삭제 문서 재삭제 | find(deleted_at IS NULL) → NotFound | 멱등 |
| 미삭제 문서 복구 | find_deleted → NotFound | 멱등 |

### 6.2 정합성 보강 정책

- **삭제 순서**: Qdrant → ES → RDB. RDB(정본)를 마지막에 마킹하여, RDB가 삭제됐는데 검색엔 남는 최악(노출)을 줄임. 단 RDB 실패 시 앞단계는 이미 마킹됨 → 재삭제 멱등으로 수렴.
- **복구 순서**: RDB → Qdrant → ES. 정본 먼저 복구.
- 부분 실패는 모두 **재시도 가능(멱등 set)** + warning 로그로 운영 가시성 확보. (분산 트랜잭션은 도입하지 않음 — 기존 정책 유지)

---

## 7. Security Considerations

- [x] 복구 권한: `DocumentDeletePolicy.can_delete`와 동일 기준 재사용 (삭제 권한자 = 복구 권한자). 별도 정책 불필요.
- [x] 휴지통 목록도 컬렉션 read 권한 + 소유/관리자 범위 검증 (기존 `_check_permission` 패턴).
- [x] soft delete 데이터는 권한 없는 사용자에게 휴지통/검색 모두 노출 안 됨.
- [x] 입력 검증: document_id 형식, batch 크기 상한(기존 패턴).

---

## 8. Test Plan

### 8.1 Test Scope

| Type | Target | Tool |
|------|--------|------|
| Unit | RDB repo: soft_delete/restore/find_deleted/find(IS NULL) | pytest + AsyncSession |
| Unit | es_repo.search deleted 제외 래핑 | pytest + mock client |
| Unit | Qdrant 빌더 must_not 주입 (vectorstore/retriever/scroll) | pytest |
| Unit | DeleteDocumentUseCase soft 전환 | pytest + AsyncMock |
| Unit | RestoreDocumentUseCase | pytest + AsyncMock |
| Integration | 삭제→검색제외→복구→재노출 e2e | pytest |
| Regression | 기존 문서(플래그 부재) 정상 노출 | pytest |

### 8.2 Test Cases (Key)

**RDB repo** (`tests/infrastructure/doc_browse/test_document_metadata_repository.py`):
- [ ] `test_soft_delete_sets_deleted_at` — UPDATE deleted_at, 물리 행 유지
- [ ] `test_find_by_collection_excludes_deleted` — deleted_at 있는 문서 미포함
- [ ] `test_find_by_document_id_excludes_deleted` — 삭제 문서 None
- [ ] `test_find_deleted_by_collection_returns_only_deleted` — 휴지통
- [ ] `test_restore_clears_deleted_at`

**ES repo** (`tests/infrastructure/elasticsearch/test_es_repository.py`):
- [ ] `test_search_wraps_query_with_must_not_is_deleted`
- [ ] `test_search_keeps_docs_without_is_deleted_field` (회귀)
- [ ] `test_update_by_query_soft_delete` / `_restore`

**Qdrant 읽기** (`tests/infrastructure/...`):
- [ ] `test_vectorstore_filter_excludes_is_deleted`
- [ ] `test_retriever_excludes_is_deleted`
- [ ] `test_get_chunks_scroll_excludes_is_deleted`

**UseCase**:
- [ ] `test_delete_soft_marks_all_three_stores`
- [ ] `test_delete_continues_on_es_failure` (부분 실패 내성)
- [ ] `test_restore_clears_all_three_stores`
- [ ] `test_restore_not_found_when_not_deleted`

**Regression (검색 정합성)**:
- [ ] `test_hybrid_search_excludes_deleted_doc` — 삭제 문서가 RAG 결과에 미등장
- [ ] `test_existing_docs_unaffected` — 플래그 부재 문서 정상

---

## 9. Clean Architecture

### 9.1 Layer Structure

| Layer | Responsibility | Location |
|-------|---------------|----------|
| **Domain** | deleted_at 스키마, 복구 결과 VO, 복구 권한(재사용) | `domain/doc_browse/` |
| **Application** | soft delete/restore 흐름, 부분 실패 오케스트레이션 | `application/doc_browse/` |
| **Infrastructure** | RDB soft 쿼리, Qdrant set_payload/필터, ES update_by_query/검색 래핑 | `infrastructure/{doc_browse,vector,retriever,elasticsearch}/` |
| **Interfaces** | 복구/휴지통 엔드포인트 | `api/routes/doc_browse_router.py` |

### 9.2 Dependency Rules

```
Interfaces → Application → Domain ← Infrastructure
✅ application/doc_browse → domain/doc_browse
✅ infrastructure/* → domain/doc_browse (interface 구현)
✅ application/collection_search·rag_agent → HybridSearch (변경 없음, 자동 커버)
❌ domain → infrastructure/application (금지)
❌ 검색 제외 필터를 domain에 두지 않음 (저장소별 구현 세부 → infrastructure)
```

### 9.3 This Feature's Layer Assignment

| Component | Layer | Location | 변경 |
|-----------|-------|----------|------|
| `DocumentMetadata.deleted_at` / `RestoreDocumentResult` | Domain | `domain/doc_browse/schemas.py` | 확장/신규 |
| repo interface (soft_delete/restore/find_deleted) | Domain | `domain/doc_browse/interfaces.py` | 확장 |
| es_repo interface (update_by_query) | Domain | `domain/elasticsearch/interfaces.py` | 확장 |
| `DeleteDocumentUseCase` (soft 전환) | Application | `application/doc_browse/delete_document_use_case.py` | 수정 |
| `RestoreDocumentUseCase` | Application | `application/doc_browse/restore_document_use_case.py` | 신규 |
| list (deleted 제외) + trash list | Application | `application/doc_browse/list_documents_use_case.py` | 수정/확장 |
| `DocumentMetadataModel.deleted_at` | Infra | `infrastructure/doc_browse/models.py` | 수정 |
| RDB repo soft/restore/find_deleted/필터 | Infra | `infrastructure/doc_browse/document_metadata_repository.py` (+ session_scoped) | 수정 |
| ES search 래핑 + update_by_query | Infra | `infrastructure/elasticsearch/es_repository.py` | 수정 |
| Qdrant 검색 제외 (vectorstore/retriever/scroll/parents) | Infra | `infrastructure/vector/qdrant_vectorstore.py`, `infrastructure/retriever/*.py`, `application/doc_browse/get_chunks_use_case.py` | 수정 |
| 라우터 (restore/trash) | Interface | `api/routes/doc_browse_router.py` | 수정 |
| Flyway 마이그레이션 | Infra | `db/migration/Vxxx__*.sql` | 신규 |

---

## 10. Coding Convention Reference

### 10.1 Naming

| Target | Rule | Example |
|--------|------|---------|
| RDB 플래그 | snake_case 시각 | `deleted_at` |
| Qdrant/ES 플래그 | snake_case boolean | `is_deleted` |
| repo 메서드 | 동사_명사 | `soft_delete_by_document_id`, `restore_by_document_id`, `find_deleted_by_collection` |
| UseCase | PascalCase + UseCase | `RestoreDocumentUseCase` |
| Activity action | UPPER | `RESTORE_DOCUMENT` (ActionType 확장) |

### 10.2 Conventions Applied

| Item | Convention |
|------|-----------|
| DB 세션 | UseCase 단일 세션, repo 내부 commit/rollback 금지 (db-session.md) |
| 로깅 | request_id 포함 구조화 로깅, 부분 실패는 warning (LOG-001) |
| 멱등성 | set 기반 soft/restore — 재호출 안전 |
| 하위호환 | `deleted_at` 기본 NULL, `is_deleted` 부재 = 정상 |
| 필터 위치 | 검색 제외는 infrastructure(저장소별), domain 오염 금지 |

---

## 11. Implementation Guide

### 11.1 Implementation Order (TDD: Red→Green→Refactor)

#### Phase 1: 스키마 & 마이그레이션
1. `db/migration/Vxxx__add_deleted_at_to_document_metadata.sql` (`/db-migration`)
2. `infrastructure/doc_browse/models.py` — `deleted_at` + 인덱스
3. ES 매핑 `is_deleted` 추가 (ensure_index_exists mappings / put_mapping 스크립트)

#### Phase 2: Domain
4. `domain/doc_browse/schemas.py` — `deleted_at`, `RestoreDocumentResult`
5. `domain/doc_browse/interfaces.py` — soft_delete/restore/find_deleted 시그니처
6. `domain/elasticsearch/interfaces.py` — `update_by_query` 시그니처
7. `domain/collection/schemas.py` — `ActionType.RESTORE_DOCUMENT`

#### Phase 3: Infra — 읽기 제외 필터 (테스트 먼저)
8. `es_repository.search` — `must_not term(is_deleted=true)` 래핑 헬퍼
9. `qdrant_vectorstore._build_qdrant_filter`/`search_by_vector` — must_not 주입
10. `qdrant_retriever` `retrieve_with_scores`/`retrieve_by_metadata` — must_not
11. `parent_child_retriever._fetch_parents` — must_not
12. `get_chunks_use_case._scroll_filtered` — must_not
13. RDB `find_by_collection`/`find_by_document_id` — `deleted_at IS NULL`

#### Phase 4: Infra — 쓰기(soft mark)
14. RDB repo: `soft_delete_by_document_id`/`restore_by_document_id`/`find_deleted_by_collection`/`find_deleted_by_document_id`
15. `es_repository.update_by_query` (soft delete/restore)
16. (Qdrant set_payload는 UseCase에서 client 직접 호출 — 기존 패턴)

#### Phase 5: Application & Interface
17. `delete_document_use_case.py` — hard→soft (set_payload/update_by_query/soft_delete)
18. `restore_document_use_case.py` — 신규
19. `list_documents_use_case.py` — 휴지통 목록 메서드
20. ActivityLog RESTORE_DOCUMENT
21. `doc_browse_router.py` — restore(단건/배치) + trash list 엔드포인트

#### Phase 6: Verification
22. e2e: 삭제→검색제외→복구→재노출
23. 회귀: 기존 문서 정상, RAG 검색에 삭제 문서 미등장
24. `/verify-architecture`, `/verify-logging`, `/verify-tdd`, `/db-migration` 검증

### 11.2 핵심 코드 스케치

#### ES 검색 제외 래핑 (`es_repository.search`)
```python
def _wrap_exclude_deleted(self, query: dict[str, Any]) -> dict[str, Any]:
    return {
        "bool": {
            "must": [query],
            "must_not": [{"term": {"is_deleted": True}}],
        }
    }

async def search(self, query: ESSearchQuery, request_id: str) -> list[ESSearchResult]:
    ...
    kwargs = {
        "index": query.index,
        "query": self._wrap_exclude_deleted(query.query),  # ◄── 단일 주입
        "size": query.size, "from_": query.from_,
    }
    ...
```
> 기존 `is_deleted` 부재 문서는 `must_not term(true)`에 미매칭 → 통과(회귀 없음).

#### Qdrant 제외 필터 헬퍼 (공통 패턴)
```python
NOT_DELETED = models.FieldCondition(
    key="is_deleted", match=models.MatchValue(value=True)
)
# 각 빌더: models.Filter(must=[...기존...], must_not=[NOT_DELETED])
```

#### Soft delete (UseCase, `_delete_qdrant_chunks` 대체)
```python
async def _soft_delete_qdrant(self, collection, document_id) -> int:
    flt = models.Filter(must=[models.FieldCondition(
        key="document_id", match=models.MatchValue(value=document_id))])
    cnt = (await self._qdrant_client.count(collection, count_filter=flt, exact=True)).count
    await self._qdrant_client.set_payload(
        collection_name=collection, payload={"is_deleted": True},
        points=models.FilterSelector(filter=flt),
    )
    return cnt
```

### 11.3 주의사항

- **삭제 시 필터 vs 검색 시 필터 구분**: soft delete의 Qdrant/ES 대상 선택 필터는 `is_deleted`를 **포함**해야 한다(이미 삭제된 것도 재마킹 멱등). 반면 RAG 검색 필터는 `is_deleted=true`를 **제외**. 두 필터를 혼동 금지.
- **ES reindex 불요**: boolean 필드 추가는 매핑만 갱신, 기존 문서 재색인 불필요.
- **collection_search/RAG Agent 무수정**: HybridSearch 경유라 8·9번 주입으로 자동 커버됨 — 별도 변경 없음 확인.
- **ingest 경로**: 신규 색인 시 `is_deleted=false` 부여는 선택(미부여라도 정합성 무영향). 일관성 위해 권장.
- **배치 복구**: `execute_batch`는 단건 반복 + 사전 권한검증 패턴(기존 delete와 동일).

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-06-04 | Initial draft | 배상규 |
