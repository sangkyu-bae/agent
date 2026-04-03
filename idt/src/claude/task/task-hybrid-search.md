# HYBRID-001: BM25 + 벡터 하이브리드 검색 모듈

> Task ID: HYBRID-001
> 의존성: ES-001, LOG-001
> 상태: Done
> Plan 문서: docs/01-plan/features/hybrid-search.plan.md

---

## 목적

Elasticsearch BM25 전문 검색과 Qdrant 벡터 유사도 검색을 결합하여
**RRF(Reciprocal Rank Fusion)** 알고리즘으로 최적의 검색 결과를 제공한다.
금융/정책 문서의 키워드 매칭 강점(BM25)과 의미적 유사도 강점(벡터)을 함께 활용한다.

---

## 아키텍처

```
POST /api/v1/hybrid-search/search
         │
         ▼
HybridSearchRouter (interfaces/api)
         │
         ▼
HybridSearchUseCase (application)
    ├── ElasticsearchRepository.search()  ← BM25
    ├── EmbeddingInterface.embed_text()   ← 쿼리 임베딩
    ├── VectorStoreInterface.search_by_vector()  ← 코사인 유사도
    └── RRFFusionPolicy.merge()           ← 랭킹 병합 (domain)
```

---

## 구현 대상

### Domain Layer
| 파일 | 설명 |
|------|------|
| `src/domain/hybrid_search/schemas.py` | `HybridSearchRequest`, `SearchHit`, `HybridSearchResult`, `HybridSearchResponse` |
| `src/domain/hybrid_search/policies.py` | `RRFFusionPolicy` — 순수 RRF 병합 로직 |

### Application Layer
| 파일 | 설명 |
|------|------|
| `src/application/hybrid_search/use_case.py` | `HybridSearchUseCase` — BM25 + 벡터 오케스트레이션 |

### API Layer
| 파일 | 설명 |
|------|------|
| `src/api/routes/hybrid_search_router.py` | `POST /api/v1/hybrid-search/search` 엔드포인트 |

---

## RRF 알고리즘

```
score(d) = Σ 1 / (k + rank_i(d))
```

- `k = 60` (표준값, Cormack et al. 2009)
- BM25 결과와 벡터 결과 각각에서 순위(rank) 기준으로 점수 산출
- 동일 문서 ID가 양쪽에 모두 존재하면 점수 합산 (`source = "both"`)

| 출처 | source 값 |
|------|-----------|
| BM25만 | `"bm25_only"` |
| 벡터만 | `"vector_only"` |
| 양쪽 모두 | `"both"` |

---

## 인터페이스

```python
# API 요청
POST /api/v1/hybrid-search/search
{
    "query": "금융 정책 문서",
    "top_k": 10,          # 최종 반환 수 (기본 10, 최대 50)
    "bm25_top_k": 20,     # BM25 후보 수 (기본 20)
    "vector_top_k": 20,   # 벡터 후보 수 (기본 20)
    "rrf_k": 60           # RRF 상수 (기본 60)
}

# API 응답
{
    "query": "금융 정책 문서",
    "results": [
        {
            "id": "doc-uuid",
            "content": "문서 내용...",
            "score": 0.032,        # RRF 점수
            "bm25_rank": 1,
            "bm25_score": 12.5,    # ES TF-IDF 원본 점수
            "vector_rank": 3,
            "vector_score": 0.85,  # 코사인 유사도
            "source": "both",
            "metadata": {"type": "pdf", "user_id": "u1"}
        }
    ],
    "total_found": 10,
    "request_id": "uuid"
}
```

---

## 환경 변수 (신규)

```env
# src/config.py에 추가됨
ES_HOST=localhost
ES_PORT=9200
ES_SCHEME=http
ES_INDEX=documents
```

---

## 테스트 파일

| 테스트 파일 | 대상 | mock |
|------------|------|------|
| `tests/domain/hybrid_search/test_schemas.py` | Value Object 생성/검증 | ❌ |
| `tests/domain/hybrid_search/test_rrf_policy.py` | RRF 병합 로직 (10 케이스) | ❌ |
| `tests/application/hybrid_search/test_hybrid_search_use_case.py` | UseCase 오케스트레이션 (9 케이스) | ✅ |
| `tests/api/test_hybrid_search_router.py` | API 엔드포인트 (8 케이스) | ✅ |

총 37 테스트 케이스 (+ schemas 10 = 47 total).

---

## LOG-001 로깅 체크리스트

- [x] `LoggerInterface` 주입 (HybridSearchUseCase)
- [x] 검색 시작/완료 INFO 로그 (`request_id`, `query`, `bm25_top_k`, `vector_top_k`)
- [x] 예외 발생 시 ERROR 로그 + `exception=e` (스택 트레이스)
- [x] `request_id` 컨텍스트 전파

---

## 완료 기준

- [x] `HybridSearchRequest/Result/Response` Value Object 정의
- [x] `RRFFusionPolicy` 순수 도메인 로직 구현
- [x] `HybridSearchUseCase` BM25 + 벡터 오케스트레이션
- [x] `POST /api/v1/hybrid-search/search` API 엔드포인트
- [x] `src/api/main.py` 라우터 등록 및 의존성 주입
- [x] `src/config.py` ES 설정 항목 추가
- [x] 전체 38 테스트 통과
- [x] LOG-001 로깅 적용

---

## 확장 포인트

| 확장 | 설명 |
|------|------|
| 메타데이터 필터 | user_id, document_type 등으로 양쪽 검색 필터링 |
| 병렬 실행 | `asyncio.gather()`로 BM25 + 벡터 동시 실행 (성능) |
| 가중치 조정 | BM25/벡터 각각 가중치 α/β 파라미터 |
| 쿼리 재작성 | QueryRewriter 연동으로 검색 품질 향상 |
