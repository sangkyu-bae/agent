# Plan: fix-es-index-not-found

> Created: 2026-04-28
> Status: Draft
> Priority: High (컬렉션 검색 기능 전면 장애)

---

## 1. 문제 정의

### 1-1. 현상

`POST /api/v1/collections/{collection_name}/search` 호출 시 500 에러 발생.

```
elasticsearch.NotFoundError: NotFoundError(404, 'index_not_found_exception',
  'no such index [documents]', documents, index_or_alias)
```

- 엔드포인트: `/api/v1/collections/test4/search`
- BM25(ES) + Vector(Qdrant) 하이브리드 검색 중 ES 검색 단계에서 실패
- Qdrant 벡터 검색은 시도조차 되지 않음 (ES 검색 실패 시 전체 abort)

### 1-2. 근본 원인 (Root Cause)

**원인 1: ES 인덱스 미존재 시 예외 미처리**

- 위치: `src/infrastructure/elasticsearch/es_repository.py:search:128`
- 코드: `resp = await es.search(**kwargs)`
- 문제: ES에 `documents` 인덱스가 존재하지 않을 때 `NotFoundError` 발생하지만,
  `search()` 메서드는 이를 catch 하지 않고 그대로 raise
- `delete()` 메서드(line 102)는 `NotFoundError`를 graceful하게 처리하지만,
  `search()`는 동일한 패턴을 적용하지 않음

**원인 2: HybridSearchUseCase에서 ES 장애 시 전체 검색 실패**

- 위치: `src/application/hybrid_search/use_case.py:_fetch_both:108`
- 문제: BM25(ES)와 Vector(Qdrant) 검색이 순차 실행되며,
  ES 검색 실패 시 Vector 검색 없이 전체 에러로 전파
- 하이브리드 검색의 핵심 가치인 "한쪽 실패 시 다른 쪽으로 fallback" 미구현

**원인 3: ES 인덱스 자동 생성 메커니즘 부재**

- 위치: `src/config.py:37` → `es_index: str = "documents"`
- 문제: 문서 업로드(`unified_upload`)의 `bulk_index`로만 인덱스가 생성됨
- 업로드된 문서가 없거나, ES가 재시작된 경우 인덱스가 존재하지 않음
- 앱 시작 시 인덱스 존재 확인 / 생성 로직 없음

### 1-3. 영향 범위

| 영향 | 범위 |
|------|------|
| 컬렉션 검색 API | `/api/v1/collections/{name}/search` 전면 장애 |
| 문서 검색 API | `/api/v1/collections/{name}/documents/{id}/search` 전면 장애 |
| 하이브리드 검색 | `HybridSearchUseCase` 사용하는 모든 경로 |
| 기존 검색 API | `/api/v1/search` (동일한 `es_index` 사용 시 동일 장애 가능) |

---

## 2. 해결 방안

### 방안 A: ES 검색 Graceful Degradation (권장)

ES 검색 실패 시 빈 결과를 반환하고, Vector 검색 결과만으로 응답.

**변경 파일:**

| 파일 | 변경 내용 |
|------|----------|
| `src/infrastructure/elasticsearch/es_repository.py` | `search()`에서 `NotFoundError` catch → 빈 리스트 반환 + warning 로그 |
| `src/application/hybrid_search/use_case.py` | `_fetch_both()`에서 ES/Vector 독립 실행, 한쪽 실패 시 빈 결과로 대체 |

**장점:** 즉시 적용 가능, Vector 검색으로 서비스 유지
**단점:** BM25 결과 없이 정밀도 저하 가능

### 방안 B: 앱 시작 시 ES 인덱스 자동 생성

`lifespan` 이벤트에서 ES 인덱스 존재 확인 후 없으면 생성.

**변경 파일:**

| 파일 | 변경 내용 |
|------|----------|
| `src/infrastructure/elasticsearch/es_repository.py` | `ensure_index_exists()` 메서드 추가 |
| `src/api/main.py` | `lifespan` 함수에서 인덱스 보장 로직 호출 |

**장점:** 근본적 해결, 인덱스 미존재 상황 자체를 방지
**단점:** ES 매핑(analyzer 등) 정의 필요, 앱 시작 시 ES 의존성 추가

### 선택: A + B 조합

- **즉시 적용(A):** ES 장애/인덱스 미존재 시 graceful degradation으로 서비스 안정성 확보
- **근본 해결(B):** 앱 시작 시 인덱스 자동 생성으로 정상 흐름 보장

---

## 3. 구현 계획

### Phase 1: Graceful Degradation (방안 A)

**3-1. ES Repository — NotFoundError 처리**

```
파일: src/infrastructure/elasticsearch/es_repository.py
메서드: search()
```

- `NotFoundError` catch → warning 로그 + 빈 리스트 반환
- 기존 `delete()` 메서드의 패턴과 동일하게 적용

**3-2. HybridSearchUseCase — 독립 실행 + fallback**

```
파일: src/application/hybrid_search/use_case.py
메서드: _fetch_both()
```

- ES 검색과 Vector 검색을 각각 try-except로 감싸기
- 한쪽 실패 시 빈 리스트로 대체, 다른 쪽은 정상 실행
- 둘 다 실패 시에만 에러 raise

### Phase 2: 인덱스 자동 생성 (방안 B)

**3-3. ES Repository — ensure_index_exists()**

```
파일: src/infrastructure/elasticsearch/es_repository.py
```

- `ensure_index_exists(index: str)` 메서드 추가
- ES `indices.exists()` → `indices.create()` (매핑 포함)
- 매핑: content(text), morph_text(text), morph_keywords(keyword),
  collection_name(keyword), document_id(keyword), user_id(keyword)

**3-4. main.py lifespan에서 인덱스 보장**

```
파일: src/api/main.py
```

- `lifespan` 함수에서 ES 인덱스 존재 확인 + 자동 생성 호출

---

## 4. 테스트 계획

| 테스트 | 파일 | 시나리오 |
|--------|------|----------|
| ES search NotFoundError 처리 | `tests/infrastructure/elasticsearch/test_es_repository.py` | 인덱스 미존재 시 빈 리스트 반환 |
| HybridSearch ES 실패 fallback | `tests/application/hybrid_search/test_hybrid_search_use_case.py` | ES 실패 → Vector 결과만 반환 |
| HybridSearch Vector 실패 fallback | 동일 | Vector 실패 → BM25 결과만 반환 |
| HybridSearch 양쪽 실패 | 동일 | 양쪽 모두 실패 → 에러 raise |
| ensure_index_exists | `tests/infrastructure/elasticsearch/test_es_repository.py` | 인덱스 생성/이미 존재 시 skip |

---

## 5. 작업 순서

1. [TDD] ES Repository `search()` NotFoundError 처리 테스트 작성
2. [TDD] HybridSearchUseCase fallback 테스트 작성
3. [구현] ES Repository `search()` 수정
4. [구현] HybridSearchUseCase `_fetch_both()` 수정
5. [TDD] `ensure_index_exists()` 테스트 작성
6. [구현] `ensure_index_exists()` 메서드 추가
7. [구현] `main.py` lifespan 인덱스 보장 로직 추가
8. [검증] 전체 테스트 실행 + 수동 검증

---

## 6. 주의사항

- `es_repository.py`의 `search()` 변경은 모든 ES 검색 경로에 영향
  → 기존 `/api/v1/search` 엔드포인트도 같은 이점을 받음
- ES 매핑 정의 시 `morph_text` 필드의 analyzer 설정 필요 여부 확인
- `ensure_index_exists()`는 ES 연결 실패 시 앱 시작을 막지 않아야 함 (warning 로그만)
