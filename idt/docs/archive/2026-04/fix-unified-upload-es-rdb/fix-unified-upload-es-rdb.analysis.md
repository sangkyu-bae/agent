# Gap Analysis: fix-unified-upload-es-rdb

> Date: 2026-04-28
> Feature: fix-unified-upload-es-rdb
> Design Doc: `docs/02-design/features/fix-unified-upload-es-rdb.design.md`
> Match Rate: **100%**

---

## 1. 파일별 설계-구현 비교

| # | 파일 | 설계 요구사항 | 구현 상태 | 일치 |
|---|------|-------------|----------|------|
| 1 | `src/application/unified_upload/schemas.py` | `top_keywords` 필드 삭제 | 필드 없음 확인 | ✅ |
| 2 | `src/application/unified_upload/use_case.py` | 의존성 교체(morph_analyzer, document_metadata_repo), `_store_to_es()` 변경, `_extract_morph_keywords()` 추가, morph_text 필드, RDB 저장 | 모두 구현 완료 | ✅ |
| 3 | `src/api/routes/unified_upload_router.py` | `top_keywords` 파라미터 삭제 | 파라미터 없음 확인 | ✅ |
| 4 | `src/api/main.py` | DI: KiwiMorphAnalyzer + DocumentMetadataRepository 주입, keyword_extractor 제거 | `create_unified_upload_factories()`에 정확히 반영 | ✅ |
| 5 | `src/application/hybrid_search/use_case.py` | BM25 쿼리를 `multi_match` on `["content", "morph_text^1.5"]`로 변경 | 필터 유/무 모두 multi_match 적용 | ✅ |
| 6 | `tests/application/unified_upload/test_use_case.py` | mock 변경 + 신규 테스트 3개 | 11개 테스트 모두 통과 | ✅ |
| 7 | `tests/application/hybrid_search/test_hybrid_search_use_case.py` | multi_match 쿼리 검증 | 12개 테스트 모두 통과 | ✅ |

## 2. 기능 요구사항(FR) 검증

| FR | 설명 | 검증 결과 |
|----|------|----------|
| FR-01 | Kiwi 형태소 기반 ES 키워드 추출 (NNG/NNP/VV/VA) | ✅ `_extract_morph_keywords()` 구현, `_KEYWORD_TAGS`/`_VERB_ADJ_TAGS` 상수 정의 |
| FR-02 | RDB 문서 메타데이터 등록 (실패 시 경고 후 계속) | ✅ `try/except` + `logger.warning` 패턴 적용 |
| FR-03 | `top_keywords` 파라미터 제거 | ✅ schema, router 모두에서 제거 완료 |

## 3. ES 저장 구조 검증

| 필드 | 설계 | 구현 | 일치 |
|------|------|------|------|
| `content` | 원문 텍스트 유지 | `chunk.page_content` | ✅ |
| `keywords` | 삭제 | body에 없음 | ✅ |
| `morph_keywords` | Kiwi 형태소 리스트 | `self._extract_morph_keywords(morph_result)` | ✅ |
| `morph_text` | morph_keywords 공백 결합 | `" ".join(morph_keywords)` | ✅ |
| `chunk_id`, `chunk_type`, `chunk_index`, `total_chunks`, `document_id`, `user_id`, `collection_name`, `parent_id` | 기존 유지 | 모두 유지 | ✅ |

## 4. BM25 검색 쿼리 검증

| 케이스 | 설계 | 구현 | 일치 |
|--------|------|------|------|
| 필터 없음 | `{"multi_match": {"query": q, "fields": ["content", "morph_text^1.5"], "type": "most_fields"}}` | 동일 | ✅ |
| 필터 있음 | `{"bool": {"must": [multi_match], "filter": [...]}}` | 동일 | ✅ |

## 5. DI 등록 검증

| 항목 | 설계 | 구현 | 일치 |
|------|------|------|------|
| `KiwiMorphAnalyzer` 싱글턴 | 팩토리 레벨 생성 | `create_unified_upload_factories()` 내 1회 생성 | ✅ |
| `DocumentMetadataRepository` 요청 스코프 | `session` 의존 | `use_case_factory()` 내 `Depends(get_session)` 주입 | ✅ |
| `keyword_extractor` 제거 | 삭제 | UseCase 생성자에 없음 | ✅ |

## 6. 테스트 검증

### 6-1. UnifiedUpload 테스트 (11/11 PASSED)

| 테스트 | 설계 요구 | 결과 |
|--------|----------|------|
| `test_execute_success_both_stores` | morph_analyzer mock 적용 | ✅ |
| `test_execute_collection_not_found_raises` | 기존 유지 | ✅ |
| `test_execute_no_create_log_raises` | 기존 유지 | ✅ |
| `test_execute_embedding_model_not_registered_raises` | 기존 유지 | ✅ |
| `test_execute_qdrant_fails_returns_partial` | morph_analyzer mock 적용 | ✅ |
| `test_execute_es_fails_returns_partial` | morph_analyzer mock 적용 | ✅ |
| `test_execute_both_fail_returns_failed` | morph_analyzer mock 적용 | ✅ |
| `test_execute_custom_chunk_params` | top_keywords 제거, morph mock | ✅ |
| `test_execute_saves_document_metadata` | **신규** — RDB 저장 검증 | ✅ |
| `test_execute_metadata_save_failure_does_not_fail` | **신규** — RDB 실패 시 계속 | ✅ |
| `test_store_to_es_uses_morph_keywords_and_morph_text` | **신규** — ES body 검증 | ✅ |

### 6-2. HybridSearch 테스트 (12/12 PASSED)

| 테스트 | 설계 요구 | 결과 |
|--------|----------|------|
| `test_execute_calls_bm25_search_with_query` | multi_match 쿼리 검증 | ✅ |
| `test_metadata_filter_applied_to_es_query` | 필터 시 multi_match 검증 | ✅ |
| `test_no_metadata_filter_uses_simple_match_query` | 필터 없을 때 multi_match 검증 | ✅ |
| 기타 9개 기존 테스트 | 기존 동작 유지 | ✅ |

## 7. 수용 기준 체크리스트

- [x] ES에 저장되는 키워드가 `morph_keywords` 리스트 + `morph_text` 문자열
- [x] BM25 검색 쿼리가 `multi_match`로 `content` + `morph_text` 동시 검색
- [x] morph_text 없는 기존 문서도 content 기반 검색 가능 (하위 호환)
- [x] `document_metadata` 테이블에 업로드 문서 정보 등록
- [x] `top_keywords` 파라미터 제거 후 기존 기능 정상 동작
- [x] TDD: UseCase 단위 테스트 갱신 완료

## 8. Gap 목록

**없음.** 설계 문서의 모든 요구사항이 구현에 정확히 반영되었다.

## 9. 결론

| 항목 | 값 |
|------|-----|
| Match Rate | **100%** |
| 총 검증 항목 | 7개 파일, 3개 FR, 23개 테스트 |
| Gap 수 | 0 |
| 테스트 결과 | 23/23 PASSED |
| 권장 다음 단계 | `/pdca report fix-unified-upload-es-rdb` |
