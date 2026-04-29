# Plan: fix-unified-upload-es-rdb

> Created: 2026-04-28
> Updated: 2026-04-28
> Feature: fix-unified-upload-es-rdb
> Phase: Plan

---

## 1. 배경 및 동기

`UnifiedUploadUseCase`(통합 PDF 업로드)에 두 가지 문제가 있다:

### 문제 1: ES 키워드 추출 방식의 한계

현재 `_store_to_es()`는 `SimpleKeywordExtractor`(정규식 기반 빈도 추출)를 사용한다.

- 정규식 `[가-힣]{2,}|[a-zA-Z]{2,}`로 토큰화 → 한국어 접두어/접미사 분리 불가
- 예: "한국은행은" → "한국은행은"(전체가 하나의 토큰) 또는 부정확한 분할
- 대량 chunk를 전체 키워드로 ES bulk 색인 시 오류 발생
- 동일 프로젝트에 이미 **Kiwi 형태소 분석기 기반의 MorphAndDualIndexUseCase**가 존재하며, NNG/NNP/VV/VA 태그로 정확한 키워드를 추출하는 검증된 패턴이 있음

### 문제 2: RDB 문서 메타데이터 미등록

현재 `UnifiedUploadUseCase`는 Qdrant + ES에만 저장하고, MySQL의 `document_metadata` 테이블에 등록하지 않는다.

- `IngestDocumentUseCase`는 `DocumentMetadataRepositoryInterface.save()`를 호출하여 등록함
- `document_metadata` 테이블에 없으면 `GET /api/v1/collections/{collection_name}/documents` 문서 목록에 표시 안 됨
- 프론트엔드에서 업로드 후 문서를 확인할 방법이 없음

### 문제 3: BM25 검색에서 형태소 키워드 미활용

현재 BM25 검색은 `{"match": {"content": query}}`로 content 필드만 검색한다.

- ES 기본 분석기는 한국어 형태소 분석 불가 → "한국은행은" ≠ "한국은행"
- `keywords` 필드는 저장만 되고 검색 쿼리에서 사용하지 않음
- Kiwi로 형태소 키워드를 정확히 추출해도, 검색 시 활용하지 않으면 의미 없음

## 2. 목표

### 2-1. 핵심 목표

1. **ES 키워드 품질 개선**: `SimpleKeywordExtractor` → `MorphAnalyzerInterface`(Kiwi) 기반으로 교체하여, morph_index와 동일한 형태소 키워드(NNG, NNP, VV원형, VA원형) 추출
2. **BM25 검색 연동**: 형태소 키워드를 `morph_text` 필드(공백 결합)로 저장하고, BM25 쿼리를 `multi_match`로 변경하여 `content` + `morph_text` 동시 검색 → 한국어 검색 recall 향상
3. **RDB 문서 등록 추가**: 업로드 완료 시 `document_metadata` 테이블에 문서 메타데이터 저장, 문서 목록 API에서 조회 가능하게 함

### 2-2. 비목표 (Scope 외)

- `MorphAndDualIndexUseCase` 수정 (기존 API 그대로 유지)
- `SimpleKeywordExtractor` 삭제 (기존 chunk-index API에서 계속 사용)
- ES 인덱스 매핑 변경 (동적 매핑으로 morph_text 필드 자동 인식)
- 프론트엔드 수정

## 3. 변경 범위

### 3-1. UnifiedUploadUseCase 의존성 변경

**Before:**
```
UnifiedUploadUseCase
  ├── keyword_extractor: KeywordExtractorInterface  ← SimpleKeywordExtractor
  └── (document_metadata_repo 없음)
```

**After:**
```
UnifiedUploadUseCase
  ├── morph_analyzer: MorphAnalyzerInterface        ← KiwiMorphAnalyzer
  ├── document_metadata_repo: DocumentMetadataRepositoryInterface
  └── (keyword_extractor 제거)
```

### 3-2. _store_to_es() 키워드 추출 방식 변경

**Before (SimpleKeywordExtractor):**
```python
keyword_result = self._keyword_extractor.extract(chunk.page_content, top_n=request.top_keywords)
body["keywords"] = keyword_result.keywords
```

**After (MorphAnalyzerInterface — Kiwi 패턴 적용):**
```python
morph_result = self._morph_analyzer.analyze(chunk.page_content)
morph_keywords = self._extract_morph_keywords(morph_result)
body["morph_keywords"] = morph_keywords
```

키워드 추출 로직은 `MorphAndDualIndexUseCase._extract_morph_keywords()`와 동일:
- NNG(일반명사), NNP(고유명사): 표면형 그대로
- VV(동사), VA(형용사): 표면형 + "다" (원형 복원)
- 중복 제거, 순서 보존

### 3-3. RDB 문서 등록 추가

`IngestDocumentUseCase`의 패턴을 따라, execute() 완료 시:

```python
await self._document_metadata_repo.save(
    DocumentMetadata(
        document_id=document_id,
        collection_name=request.collection_name,
        filename=request.filename,
        category="uncategorized",
        user_id=request.user_id,
        chunk_count=len(chunks),
        chunk_strategy="parent_child",
    ),
    request_id=request_id,
)
```

### 3-4. ES body 필드명 변경

| 필드 | Before | After | 이유 |
|------|--------|-------|------|
| 키워드 필드명 | `keywords` | `morph_keywords` | morph_index와 필드명 통일 |

## 4. 수정 파일 목록

| 파일 | 변경 내용 |
|------|----------|
| `src/application/unified_upload/use_case.py` | MorphAnalyzerInterface 주입, _store_to_es() 키워드 추출 변경 + morph_text 추가, DocumentMetadata 저장 추가 |
| `src/application/unified_upload/schemas.py` | top_keywords 파라미터 제거 (형태소 분석은 top_n 불필요) |
| `src/api/routes/unified_upload_router.py` | top_keywords 파라미터 제거 |
| `src/api/main.py` | DI 등록 변경: KiwiMorphAnalyzer 주입, DocumentMetadataRepository 주입 |
| `src/application/hybrid_search/use_case.py` | BM25 쿼리를 multi_match(content + morph_text)로 변경 |
| `tests/application/unified_upload/test_use_case.py` | 테스트 mock 변경 + 신규 테스트 |
| `tests/application/hybrid_search/test_hybrid_search_use_case.py` | multi_match 쿼리 검증 |

## 5. 기능 요구사항

### FR-01: Kiwi 형태소 기반 ES 키워드 추출

- `MorphAnalyzerInterface.analyze()` → `MorphAnalysisResult` 에서 NNG/NNP/VV/VA 추출
- VV/VA는 표면형 + "다"로 원형 복원
- 중복 키워드 제거, 순서 보존
- ES body에 `morph_keywords` 필드로 저장

### FR-02: RDB 문서 메타데이터 등록

- `DocumentMetadataRepositoryInterface.save()` 호출
- document_id, collection_name, filename, user_id, chunk_count, chunk_strategy 저장
- Qdrant/ES 저장 성공 여부와 무관하게 등록 (문서가 업로드된 사실 자체를 기록)
- 등록 실패 시 전체 업로드 실패 처리하지 않음 (로그 경고 후 계속)

### FR-03: top_keywords 파라미터 제거

- Kiwi 형태소 분석은 텍스트 내 모든 키워드 태그를 추출하므로 top_n 제한 불필요
- API request에서 `top_keywords` 파라미터 제거
- `UnifiedUploadRequest` 스키마에서 `top_keywords` 필드 제거

## 6. 수용 기준

- [ ] ES에 저장되는 키워드가 `morph_keywords` 리스트 + `morph_text` 문자열로 Kiwi 형태소 분석 결과 포함
- [ ] "한국은행은 기준금리를 동결" → `morph_keywords: ["한국은행", "기준금리", "동결하다"]`, `morph_text: "한국은행 기준금리 동결하다"`
- [ ] BM25 검색 쿼리가 `multi_match`로 `content` + `morph_text` 동시 검색
- [ ] "한국은행" 검색 시 "한국은행은"이 포함된 문서가 morph_text 매칭으로 검색됨
- [ ] morph_text 없는 기존 문서도 content 기반으로 검색 가능 (하위 호환)
- [ ] `document_metadata` 테이블에 업로드 문서 정보가 등록됨
- [ ] `GET /api/v1/collections/{name}/documents`에서 업로드한 문서가 조회됨
- [ ] `top_keywords` 파라미터 제거 후 기존 기능 정상 동작
- [ ] 기존 morph-index API (`/api/v1/morph-index/upload`) 영향 없음
- [ ] 기존 chunk-index API (`/api/v1/chunk-index/upload`) 영향 없음
- [ ] TDD: UseCase 단위 테스트 갱신 (Red → Green → Refactor)

## 7. 의존성 및 전제조건

- `kiwipiepy` 패키지 이미 설치됨 (pyproject.toml에 등록 확인)
- `KiwiMorphAnalyzer` 구현체 이미 존재 (`src/infrastructure/morph/kiwi_morph_analyzer.py`)
- `DocumentMetadataRepositoryInterface` + 구현체 이미 존재
- `document_metadata` 테이블 이미 생성됨 (`V014__create_document_metadata.sql`)

## 8. 예상 작업 규모

| 항목 | 예상 |
|------|------|
| 수정 파일 | 7개 |
| 신규 파일 | 0개 |
| 테스트 파일 수정 | 2개 |
| 난이도 | 낮음 (기존 패턴 재사용, 의존성 교체 + BM25 쿼리 변경) |

## 9. 참조

- 기존 Kiwi 형태소 패턴: `src/application/morph_index/use_case.py`
- 기존 RDB 등록 패턴: `src/application/ingest/ingest_use_case.py:141-153`
- 문서 메타데이터 스키마: `src/domain/doc_browse/schemas.py:DocumentMetadata`
- 문서 메타데이터 테이블: `src/infrastructure/doc_browse/models.py:DocumentMetadataModel`
