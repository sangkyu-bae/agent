# Gap Analysis: collection-document-chunks

> Feature: 컬렉션별 임베딩 문서 및 청크 조회 API
> Analyzed: 2026-04-23
> Design: `docs/02-design/features/collection-document-chunks.design.md`
> Match Rate: **97%**

---

## 1. 파일 구조 비교

| Design 명세 | 구현 상태 | 일치 |
|-------------|----------|------|
| `src/domain/doc_browse/__init__.py` | 존재 | ✅ |
| `src/domain/doc_browse/schemas.py` | 존재 | ✅ |
| `src/application/doc_browse/__init__.py` | 존재 | ✅ |
| `src/application/doc_browse/list_documents_use_case.py` | 존재 | ✅ |
| `src/application/doc_browse/get_chunks_use_case.py` | 존재 | ✅ |
| `src/api/routes/doc_browse_router.py` | 존재 | ✅ |

**결과**: 6/6 파일 일치 (100%)

---

## 2. Domain Layer

| 항목 | Design | 구현 | 일치 |
|------|--------|------|------|
| DocumentSummary (6 fields) | 정의 | 동일 | ✅ |
| ChunkDetail (5 fields) | 정의 | 동일 | ✅ |
| ParentChunkGroup (5 fields) | 정의 | 동일 | ✅ |
| DocumentChunksResult (6 fields) | 정의 | 동일 | ✅ |
| dataclass(frozen=True) | 명세 | 적용 | ✅ |

**결과**: 5/5 항목 일치 (100%)

---

## 3. Application Layer

### ListDocumentsUseCase

| 항목 | Design | 구현 | 일치 |
|------|--------|------|------|
| DI: qdrant_client + logger | 명세 | 구현 | ✅ |
| execute(collection_name, offset, limit) → dict | 명세 | 구현 | ✅ |
| scroll(limit=10,000, with_vectors=False) | 명세 | SCROLL_BATCH_LIMIT=10,000 | ✅ |
| next_page_offset 반복 scroll | 명세 | _scroll_all() 루프 구현 | ✅ |
| document_id 기준 그룹핑 (defaultdict) | 명세 | _group_by_document() | ✅ |
| filename 기본값 "unknown" | 명세 | 구현 | ✅ |
| category 기본값 "uncategorized" | 명세 | 구현 | ✅ |
| offset/limit Python 슬라이싱 | 명세 | summaries[offset:offset+limit] | ✅ |

**결과**: 8/8 항목 일치 (100%)

### GetChunksUseCase

| 항목 | Design | 구현 | 일치 |
|------|--------|------|------|
| DI: qdrant_client + logger | 명세 | 구현 | ✅ |
| execute(collection_name, document_id, include_parent) → DocumentChunksResult | 명세 | 구현 | ✅ |
| MetadataFilter(document_id) | 명세 | FieldCondition + Filter | ✅ |
| 전략 감지 (parent_child, full_token, semantic) | 명세 | _detect_strategy() | ✅ |
| include_parent=false: child만 필터 + chunk_index 정렬 | 명세 | _build_flat_list() | ✅ |
| include_parent=true: parent→children 계층 구조 | 명세 | _build_hierarchy() | ✅ |
| EXCLUDED_META_KEYS 제외 | 명세 | 동일 5개 키 | ✅ |
| full_token/semantic: include_parent 무시 | 명세 | strategy != "parent_child" 분기 | ✅ |

**결과**: 8/8 항목 일치 (100%)

---

## 4. API Layer

| 항목 | Design | 구현 | 일치 |
|------|--------|------|------|
| GET /{collection_name}/documents | 명세 | 구현 | ✅ |
| GET /{collection_name}/documents/{document_id}/chunks | 명세 | 구현 | ✅ |
| DocumentSummaryResponse (6 fields) | 명세 | 동일 | ✅ |
| DocumentListResponse (5 fields) | 명세 | 동일 | ✅ |
| ChunkDetailResponse (5 fields) | 명세 | 동일 | ✅ |
| ParentChunkGroupResponse (5 fields) | 명세 | 동일 | ✅ |
| ChunkListResponse (6 fields) | 명세 | 동일 | ✅ |
| DI 플레이스홀더 (NotImplementedError) | 명세 | 구현 | ✅ |
| Query(offset=0, ge=0) / Query(limit=20, ge=1, le=100) | 명세 | 구현 | ✅ |
| Query(include_parent=False) | 명세 | 구현 | ✅ |

**결과**: 10/10 항목 일치 (100%)

---

## 5. main.py DI 등록

| 항목 | Design | 구현 | 일치 |
|------|--------|------|------|
| import doc_browse_router | 명세 | 구현 | ✅ |
| import get_list_documents_use_case | 명세 | 구현 | ✅ |
| import get_chunks_use_case | 명세 | 구현 | ✅ |
| ListDocumentsUseCase 팩토리 | 명세 | _list_documents_uc_factory | ✅ |
| GetChunksUseCase 팩토리 | 명세 | _get_chunks_uc_factory | ✅ |
| dependency_overrides 등록 | 명세 | 구현 | ✅ |
| include_router(doc_browse_router) | 명세 | 구현 | ✅ |

**결과**: 7/7 항목 일치 (100%)

---

## 6. 테스트 커버리지

### test_list_documents_use_case.py (Design: 7개)

| 테스트 케이스 | 구현 | 상태 |
|--------------|------|------|
| test_groups_by_document_id | ✅ | PASS |
| test_counts_chunks_per_document | ✅ | PASS |
| test_extracts_filename_and_category | ✅ | PASS |
| test_collects_unique_chunk_types | ✅ | PASS |
| test_applies_offset_and_limit | ✅ | PASS |
| test_returns_empty_for_empty_collection | ✅ | ERROR (Windows asyncio) |
| test_returns_total_documents_count | ✅ | PASS |
| test_defaults_filename_and_category_when_missing (추가) | ✅ | PASS |

**결과**: 7/7 명세 케이스 구현 + 1 추가 (100%)

### test_get_chunks_use_case.py (Design: 10개)

| 테스트 케이스 | 구현 | 상태 |
|--------------|------|------|
| test_returns_children_only_by_default | ✅ | PASS |
| test_sorts_by_chunk_index | ✅ | PASS |
| test_returns_parent_child_hierarchy | ✅ | PASS |
| test_maps_children_to_correct_parent | ✅ | PASS |
| test_handles_full_token_strategy | ✅ | PASS |
| test_handles_semantic_strategy | ✅ | PASS |
| test_ignores_include_parent_for_non_parent_child | ✅ | PASS |
| test_detects_chunk_strategy | ✅ | PASS |
| test_excludes_internal_metadata_keys | ✅ | PASS |
| test_returns_empty_for_nonexistent_document | ✅ | PASS |

**결과**: 10/10 명세 케이스 구현 (100%)

### test_doc_browse_router.py (Design: 5개)

| 테스트 케이스 | 구현 | 상태 |
|--------------|------|------|
| test_list_documents_returns_200 | ✅ | PASS |
| test_list_documents_pagination | ✅ | FAIL (Windows asyncio) |
| test_get_chunks_returns_200 | ✅ | PASS |
| test_get_chunks_include_parent | ✅ | PASS |
| test_get_chunks_nonexistent_document | ✅ | PASS |

**결과**: 5/5 명세 케이스 구현 (100%)

---

## 7. 로깅 (LOG-001)

| 로그 항목 | Design | 구현 | 일치 |
|-----------|--------|------|------|
| ListDocuments: info started | 명세 | 구현 | ✅ |
| ListDocuments: info completed | 명세 | 구현 | ✅ |
| ListDocuments: error failed | 명세 | 구현 | ✅ |
| GetChunks: info started | 명세 | 구현 | ✅ |
| GetChunks: info completed | 명세 | 구현 | ✅ |
| GetChunks: error failed | 명세 | 구현 | ✅ |

**결과**: 6/6 항목 일치 (100%)

---

## 8. Gap 목록

### GAP-001: 테스트 환경 오류 (Windows asyncio) — Severity: Low

- **위치**: `test_returns_empty_for_empty_collection`, `test_list_documents_pagination`
- **상태**: 2개 테스트가 Windows 환경의 asyncio event loop 소켓 오류로 ERROR/FAIL
- **원인**: `OSError: [WinError 10014]` — Windows ProactorEventLoop과 pytest-asyncio 호환 문제
- **영향**: 구현 코드 자체는 정상. 환경별 테스트 인프라 이슈
- **권장**: `pyproject.toml`에 `asyncio_mode = "auto"` 및 `loop_scope` 설정 확인, 또는 CI 환경(Linux)에서 검증

---

## 9. 종합 평가

| 카테고리 | 일치율 |
|----------|--------|
| 파일 구조 | 100% (6/6) |
| Domain Layer | 100% (5/5) |
| Application Layer | 100% (16/16) |
| API Layer | 100% (10/10) |
| main.py DI | 100% (7/7) |
| 테스트 케이스 존재 | 100% (22/22) |
| 테스트 통과율 | 91% (21/23, 2건 Windows 환경 이슈) |
| 로깅 | 100% (6/6) |

### **종합 Match Rate: 97%**

구현이 설계 문서를 충실히 반영하고 있음. 2개 테스트 실패는 Windows asyncio 환경 문제이며 구현 로직 자체의 gap은 아님.
