# Design: fix-unified-upload-es-rdb

> Created: 2026-04-28
> Updated: 2026-04-28 (v2 — BM25 검색 연동 반영)
> Feature: fix-unified-upload-es-rdb
> Phase: Design
> Plan Reference: `docs/01-plan/features/fix-unified-upload-es-rdb.plan.md`

---

## 0. 핵심 설계 원칙

ES에 문서를 저장하는 최종 목적은 **BM25 하이브리드 검색에 걸리게 하기 위함**이다.

현재 문제의 전체 흐름:

```
[저장 시 문제]
UnifiedUploadUseCase._store_to_es()
  → SimpleKeywordExtractor(정규식 기반)로 keywords 추출
  → ES body에 "keywords" 필드로 저장
  → 전체 단어를 bulk로 넣어 오류 발생 + 한국어 접두어/접미사 분리 불가

[검색 시 문제]
HybridSearchUseCase._fetch_both()
  → BM25 쿼리: {"match": {"content": query}}
  → content 필드만 검색, keywords 필드는 전혀 사용 안 함
  → ES 기본 분석기는 한국어 형태소 분석 불가
  → "한국은행은" ≠ "한국은행" (접미사 "은" 때문에 매칭 실패)
  → BM25 recall 저조
```

해결 방향:

```
[저장 개선]
Kiwi 형태소 분석 → morph_keywords 리스트 + morph_text(공백 결합) 저장

[검색 개선]
BM25 쿼리: multi_match on ["content", "morph_text"]
→ content로 원문 매칭 + morph_text로 형태소 기반 매칭
→ 한국어 BM25 recall 대폭 향상
```

## 1. 시스템 흐름 (End-to-End)

### 1-1. 저장 흐름 (UnifiedUpload)

```
Client
  │
  ▼
[POST /api/v1/documents/upload-all]
  │  file (PDF), user_id, collection_name,
  │  child_chunk_size?, child_chunk_overlap?
  │  (top_keywords 파라미터 제거됨)
  │
  ▼
UnifiedUploadUseCase.execute()
  │
  ├─ 1. 컬렉션 존재 확인 (기존 동일)
  ├─ 2. 임베딩 모델 조회 (기존 동일)
  ├─ 3. PDF 파싱 (기존 동일)
  ├─ 4. Parent-Child 청킹 (기존 동일)
  │
  ├─ 5. 병렬 저장 (asyncio.gather)
  │     ├─ 5-A. Qdrant 벡터 저장 (기존 동일)
  │     └─ 5-B. ES BM25 저장 ★ 변경
  │           각 chunk에 대해:
  │             Kiwi analyze(chunk.page_content)
  │             → morph_keywords = ["한국은행", "기준금리", "동결하다"]
  │             → morph_text = "한국은행 기준금리 동결하다"  ★ 신규
  │             → ES body: { content, morph_keywords, morph_text, ... }
  │
  ├─ 6. RDB 문서 메타데이터 등록 ★ 신규
  │     DocumentMetadataRepositoryInterface.save(metadata)
  │
  ├─ 7. 활동 로그 기록 (기존 동일)
  └─ 8. UnifiedUploadResult 반환
```

### 1-2. 검색 흐름 (HybridSearch) — BM25 개선

```
Client
  │  query = "한국은행 금리 동결"
  │
  ▼
HybridSearchUseCase._fetch_both()
  │
  ├─ BM25 검색 ★ 변경
  │   Before: {"match": {"content": "한국은행 금리 동결"}}
  │   After:  {"multi_match": {
  │              "query": "한국은행 금리 동결",
  │              "fields": ["content", "morph_text^1.5"],
  │              "type": "most_fields"
  │           }}
  │   → content: 원문 기반 매칭 (기존 동작 유지)
  │   → morph_text: Kiwi 추출 키워드 매칭 (한국어 recall 향상)
  │   → morph_text에 ^1.5 boost: 형태소 매칭 가중치
  │
  └─ Vector 검색 (기존 동일)
```

**BM25 검색 개선 예시:**

```
저장된 원문: "한국은행은 2024년 기준금리를 동결하기로 결정하였다."

ES 기본 분석기로 content 토큰화:
  → ["한국은행은", "2024년", "기준금리를", "동결하기로", "결정하였다"]

Kiwi morph_text:
  → "한국은행 기준금리 동결하다 결정하다"

검색 쿼리: "한국은행 기준금리"
  → content match: "한국은행" ≠ "한국은행은" (ES 기본 분석기로는 부분 매칭 불가)
  → morph_text match: "한국은행" = "한국은행" ✅, "기준금리" = "기준금리" ✅
```

## 2. API Contract 변경

### 2-1. Upload API — Request 변경

```
POST /api/v1/documents/upload-all
Content-Type: multipart/form-data
```

| 파라미터 | 위치 | 타입 | 필수 | 제약 | 기본값 | 변경 |
|----------|------|------|------|------|--------|------|
| file | Body (File) | UploadFile | O | PDF만 | - | 유지 |
| user_id | Query | str | O | - | - | 유지 |
| collection_name | Query | str | O | 기존 컬렉션만 | - | 유지 |
| child_chunk_size | Query | int | X | 100~4000 | 500 | 유지 |
| child_chunk_overlap | Query | int | X | 0~500 | 50 | 유지 |
| ~~top_keywords~~ | ~~Query~~ | ~~int~~ | ~~X~~ | ~~1~50~~ | ~~10~~ | **삭제** |

### 2-2. Upload API — Response 변경 없음

기존 `UnifiedUploadResponse` 스키마 유지.

### 2-3. Hybrid Search API — 변경 없음

`HybridSearchAPIRequest`/`HybridSearchAPIResponse`는 변경 없음. 내부 BM25 쿼리 구조만 변경.

## 3. ES 저장 구조 변경

### 3-1. ES Document Body 필드 비교

| 필드 | Before | After | 역할 |
|------|--------|-------|------|
| `content` | 원문 텍스트 | 원문 텍스트 (동일) | BM25 원문 매칭용 |
| `keywords` | SimpleKeywordExtractor 결과 | **삭제** | - |
| `morph_keywords` | - | Kiwi 형태소 리스트 ★ 신규 | 메타데이터/필터링용 |
| `morph_text` | - | morph_keywords 공백 결합 ★ 신규 | **BM25 형태소 매칭용** |
| `chunk_id` | 동일 | 동일 | 청크 식별 |
| `chunk_type` | 동일 | 동일 | parent/child 구분 |
| `chunk_index` | 동일 | 동일 | 순서 |
| `total_chunks` | 동일 | 동일 | 전체 수 |
| `document_id` | 동일 | 동일 | 문서 식별 |
| `user_id` | 동일 | 동일 | 소유자 |
| `collection_name` | 동일 | 동일 | 컬렉션 |
| `parent_id` | 동일 | 동일 | 부모 청크 |

### 3-2. morph_text가 필요한 이유

- `morph_keywords`는 ES에서 keyword array로 저장됨 → `term` 쿼리에 적합, `match`(BM25)에는 부적합
- `morph_text`는 공백 결합된 문자열 → ES 기본 분석기가 공백으로 토큰화 → BM25 `match` 쿼리에서 각 형태소가 개별 토큰으로 매칭됨
- 예: `"한국은행 기준금리 동결하다"` → ES 토큰: `["한국은행", "기준금리", "동결하다"]` → 검색 쿼리 "한국은행"에 정확 매칭

## 4. Application Layer 변경 설계

### 4-1. UnifiedUploadUseCase 생성자 변경

```python
# Before
class UnifiedUploadUseCase:
    def __init__(
        self,
        ...
        keyword_extractor: KeywordExtractorInterface,  # 제거
        ...
    ) -> None:

# After
class UnifiedUploadUseCase:
    def __init__(
        self,
        ...
        morph_analyzer: MorphAnalyzerInterface,        # 추가
        document_metadata_repo: DocumentMetadataRepositoryInterface,  # 추가
        ...
    ) -> None:
```

### 4-2. _store_to_es() 변경

```python
async def _store_to_es(self, chunks, document_id, request, request_id) -> EsStoreResult:
    es_docs = []
    for chunk in chunks:
        morph_result = self._morph_analyzer.analyze(chunk.page_content)
        morph_keywords = self._extract_morph_keywords(morph_result)
        morph_text = " ".join(morph_keywords)  # BM25 검색용 텍스트

        chunk_id = chunk.metadata.get("chunk_id", str(uuid.uuid4()))
        body = {
            "content": chunk.page_content,
            "morph_keywords": morph_keywords,    # 메타데이터/필터용 리스트
            "morph_text": morph_text,             # BM25 매칭용 텍스트
            "chunk_id": chunk_id,
            "chunk_type": chunk.metadata.get("chunk_type", "full"),
            "chunk_index": chunk.metadata.get("chunk_index", 0),
            "total_chunks": chunk.metadata.get("total_chunks", 1),
            "document_id": document_id,
            "user_id": request.user_id,
            "collection_name": request.collection_name,
        }
        if "parent_id" in chunk.metadata:
            body["parent_id"] = chunk.metadata["parent_id"]
        es_docs.append(ESDocument(id=chunk_id, body=body, index=self._es_index))

    count = await self._es_repo.bulk_index(es_docs, request_id)
    return EsStoreResult(indexed_count=count)
```

### 4-3. _extract_morph_keywords() 추가

MorphAndDualIndexUseCase에서 검증된 로직을 동일하게 사용:

```python
_KEYWORD_TAGS = frozenset({"NNG", "NNP", "VV", "VA"})
_VERB_ADJ_TAGS = frozenset({"VV", "VA"})

def _extract_morph_keywords(self, analysis: MorphAnalysisResult) -> list[str]:
    seen: set[str] = set()
    keywords: list[str] = []
    for tok in analysis.tokens:
        if tok.pos not in _KEYWORD_TAGS:
            continue
        form = tok.surface + "다" if tok.pos in _VERB_ADJ_TAGS else tok.surface
        if form not in seen:
            seen.add(form)
            keywords.append(form)
    return keywords
```

| 품사 | 처리 | 예시 |
|------|------|------|
| NNG (일반명사) | 표면형 그대로 | "금리" → "금리" |
| NNP (고유명사) | 표면형 그대로 | "한국은행" → "한국은행" |
| VV (동사) | 표면형 + "다" | "결정" → "결정하다" |
| VA (형용사) | 표면형 + "다" | "안정" → "안정하다" |

### 4-4. RDB 문서 메타데이터 저장 추가

execute() 내 병렬 저장 후, 활동 로그 기록 전에 호출:

```python
try:
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
except Exception:
    self._logger.warning(
        "Document metadata save failed, continuing",
        request_id=request_id,
        document_id=document_id,
    )
```

- RDB 저장 실패 시 전체 업로드를 실패시키지 않음 (warning 로그 후 계속)

### 4-5. Schemas (DTO) 변경

```python
# src/application/unified_upload/schemas.py
@dataclass(frozen=True)
class UnifiedUploadRequest:
    file_bytes: bytes
    filename: str
    user_id: str
    collection_name: str
    child_chunk_size: int = 500
    child_chunk_overlap: int = 50
    # top_keywords 삭제
```

### 4-6. HybridSearchUseCase BM25 쿼리 변경

```python
# src/application/hybrid_search/use_case.py — _fetch_both()

# Before
es_query_body: dict = {"match": {"content": request.query}}

# After
es_query_body: dict = {
    "multi_match": {
        "query": request.query,
        "fields": ["content", "morph_text^1.5"],
        "type": "most_fields",
    }
}

# metadata_filter 있을 때도 동일하게 변경:
# Before
"must": [{"match": {"content": request.query}}],
# After
"must": [{
    "multi_match": {
        "query": request.query,
        "fields": ["content", "morph_text^1.5"],
        "type": "most_fields",
    }
}],
```

**설계 결정:**
- `type: "most_fields"`: content와 morph_text 모두에서 점수를 계산하고 합산 → 두 필드 중 하나에만 매칭되어도 결과에 포함
- `morph_text^1.5`: 형태소 분석된 텍스트에 1.5배 가중치 → 정확한 형태소 매칭이 원문 매칭보다 약간 우선
- 기존 `content`만 사용하던 쿼리도 유지되므로 `morph_text` 필드가 없는 기존 문서도 검색 가능 (하위 호환)

## 5. Interface Layer 변경 설계

### 5-1. Router 파라미터 변경

```python
# unified_upload_router.py
# top_keywords 파라미터 삭제, domain_request 생성에서도 삭제
```

## 6. DI 등록 변경 (main.py)

```python
def create_unified_upload_factories():
    from src.infrastructure.morph.kiwi_morph_analyzer import KiwiMorphAnalyzer
    from src.infrastructure.doc_browse.document_metadata_repository import DocumentMetadataRepository
    ...
    morph_analyzer = KiwiMorphAnalyzer()   # 싱글턴 (Kiwi 인스턴스 생성 비용 높음)
    ...
    def use_case_factory(session: AsyncSession = Depends(get_session)):
        ...
        document_metadata_repo = DocumentMetadataRepository(
            session=session, logger=app_logger
        )
        return UnifiedUploadUseCase(
            ...
            morph_analyzer=morph_analyzer,
            document_metadata_repo=document_metadata_repo,
            ...  # keyword_extractor 제거
        )
```

## 7. 파일별 변경 상세

| # | 파일 | 변경 내용 |
|---|------|----------|
| 1 | `src/application/unified_upload/schemas.py` | `top_keywords` 필드 삭제 |
| 2 | `src/application/unified_upload/use_case.py` | 의존성 교체(morph_analyzer, document_metadata_repo), `_store_to_es()` 변경, `_extract_morph_keywords()` 추가, morph_text 필드 추가, RDB 저장 추가 |
| 3 | `src/api/routes/unified_upload_router.py` | `top_keywords` 파라미터 삭제 |
| 4 | `src/api/main.py` | DI 변경: KiwiMorphAnalyzer + DocumentMetadataRepository 주입 |
| 5 | `src/application/hybrid_search/use_case.py` | BM25 쿼리를 `multi_match` on `["content", "morph_text^1.5"]`로 변경 |
| 6 | `tests/application/unified_upload/test_use_case.py` | mock 변경 + 신규 테스트 |
| 7 | `tests/application/hybrid_search/test_hybrid_search_use_case.py` | BM25 쿼리 변경 검증 |

## 8. 구현 순서

| 순서 | 파일 | 작업 | TDD |
|------|------|------|-----|
| 1 | `schemas.py` | `top_keywords` 필드 삭제 | - |
| 2 | `test_use_case.py` | mock 변경: morph_analyzer, document_metadata_repo (RED) | RED |
| 3 | `use_case.py` | 의존성 교체, `_store_to_es()` 변경, `_extract_morph_keywords()` + morph_text, RDB 저장 | GREEN |
| 4 | `test_use_case.py` | 신규 테스트: RDB 저장 + morph_text ES body 검증 (RED → GREEN) | RED→GREEN |
| 5 | `unified_upload_router.py` | `top_keywords` 파라미터 삭제 | - |
| 6 | `main.py` | DI 변경 | - |
| 7 | `test_hybrid_search_use_case.py` | multi_match 쿼리 검증 (RED) | RED |
| 8 | `hybrid_search/use_case.py` | BM25 쿼리 multi_match 변경 | GREEN |

## 9. 테스트 전략

### 9-1. UnifiedUpload 기존 테스트 수정

| 테스트 | 변경 |
|--------|------|
| `test_execute_success_both_stores` | morph_analyzer mock, document_metadata_repo.save 호출 검증 |
| `test_execute_qdrant_fails_returns_partial` | morph_analyzer mock |
| `test_execute_es_fails_returns_partial` | morph_analyzer mock |
| `test_execute_both_fail_returns_failed` | morph_analyzer mock |
| `test_execute_custom_chunk_params` | top_keywords 제거, morph mock |

### 9-2. UnifiedUpload 신규 테스트

```python
async def test_execute_saves_document_metadata(self):
    """성공 시 document_metadata RDB에 저장되는지 검증."""

async def test_execute_metadata_save_failure_does_not_fail(self):
    """RDB 저장 실패해도 전체 결과는 정상 반환되는지 검증."""

async def test_store_to_es_uses_morph_keywords_and_morph_text(self):
    """ES body에 morph_keywords 리스트 + morph_text 문자열이 올바르게 들어가는지 검증."""
```

### 9-3. HybridSearch 테스트 수정

```python
async def test_bm25_query_uses_multi_match_on_content_and_morph_text(self):
    """BM25 쿼리가 multi_match로 content + morph_text를 검색하는지 검증."""
    # es_repo.search 호출 시 전달된 ESSearchQuery.query 검증
    # fields에 "content"와 "morph_text^1.5"가 포함되어야 함

async def test_bm25_query_with_filter_uses_multi_match(self):
    """metadata_filter가 있을 때도 multi_match가 사용되는지 검증."""
```

## 10. 영향 범위

| 항목 | 영향 |
|------|------|
| 기존 `/documents/upload` (IngestDocumentUseCase) | 없음 |
| 기존 `/chunk-index/upload` | 없음 (SimpleKeywordExtractor 그대로) |
| 기존 `/morph-index/upload` | 없음 (독립적 UseCase) |
| `GET /collections/{name}/documents` | **개선**: 통합 업로드 문서도 조회 가능 |
| **하이브리드 검색** | **개선**: morph_text 필드가 있는 문서에 대해 한국어 BM25 recall 향상 |
| ES 기존 데이터 (morph_text 없음) | **하위 호환**: multi_match의 `most_fields` 타입은 morph_text 필드가 없어도 content만으로 매칭 — 기존 문서 검색에 영향 없음 |
| 프론트엔드 | `top_keywords` 파라미터 전송 제거 필요 (optional이었으므로 즉시 영향 없음) |

## 11. 위험 요소 및 완화

| 위험 | 완화 |
|------|------|
| Kiwi 초기화 지연 | 팩토리 레벨 싱글턴 — 앱 시작 시 1회만 생성 |
| morph_text 없는 기존 문서 | `most_fields` multi_match는 존재하는 필드만으로 점수 계산 → 기존 문서도 content 기반으로 검색됨 |
| morph_text boost 값(1.5) 최적화 | 초기 1.5로 시작, 검색 품질 모니터링 후 조정 가능 (config 분리는 비목표) |
| ES bulk 오류 지속 가능성 | morph_keywords + morph_text는 정규화된 짧은 단어들이므로 안정화 기대 |
