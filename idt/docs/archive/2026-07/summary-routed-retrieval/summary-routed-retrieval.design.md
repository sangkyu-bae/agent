# summary-routed-retrieval Design Document

> **Plan**: `docs/01-plan/features/summary-routed-retrieval.plan.md`
> **Author**: 배상규
> **Date**: 2026-07-09
> **Status**: Draft
> **선행**: 문서 등록 3부작 (clause-aware-chunking / card-section-summary / document-summary-routing — 전부 완료)

---

## 1. 설계 요약

3계층 요약 데이터를 소비하는 라우팅 리트리버를 **신규 경로로만** 추가한다. 4개 블록:

1. **단계 포트 3종**(domain): `DocumentRouterInterface` / `SectionRouterInterface` / `ChunkExpanderInterface` + 단계 간 VO — 구현 교체가 다른 단계에 무영향(사용자 요구)
2. **단계 구현**(infrastructure): Qdrant 문서 라우터(벡터) → 하이브리드 섹션 라우터(벡터+BM25 `RRFFusionPolicy` 재사용) → **ES ids query** 청크 확장기
3. **오케스트레이터 + 폴백**(application): 임베딩 1회 → ①②③ → 부족 시 기존 `HybridSearchUseCase` 위임 보충(dedup) — LLM 0회
4. **신규 API 1개**: `POST /api/v1/retrieval/routed` (hybrid_search_router 관례: 인증 없음·DI placeholder·싱글턴 배선) — **기존 코드 수정은 `SearchFilter.metadata_any` additive 확장 1건뿐**

### 코드 확인으로 확정된 사실 (2026-07-09)

| 확인 항목 | 결과 | 영향 |
|-----------|------|------|
| **요약 계층 ID 3자 일치** | 요약 point는 Qdrant point id = ES `_id` = payload chunk_id = 결정적 uuid5 (2단계 D5) | 섹션 단계 RRF 병합 키가 자연 정합 — 벡터 hit(point id)와 BM25 hit(ES _id)가 같은 키 (D4) |
| **rawchunk ID 불일치** | rawchunk는 point id(uuid4) ≠ chunk_id, **ES `_id` = chunk_id만 일치** (2단계 확인) | `section_ref`(=parent chunk_id) 해석은 **ES ids query** 채택 — Qdrant payload 필터 scroll(인덱스 없음) 기각 (D5) |
| RRF 재사용 | `RRFFusionPolicy.merge(bm25_hits, vector_hits, top_k, k, weights)` 순수 정책 + `SearchHit` (`domain/hybrid_search/policies.py:33`) | 섹션 단계 병합에 무수정 재사용 (D4) |
| 가드 bypass | `search_by_vector`는 명시 `chunk_type`이 요약 타입이면 must_not 해제 (document-summary-routing D12) | 문서/섹션 라우터가 equality 필터로 자연 통과 (D3/D4) |
| `SearchFilter` 한계 | `metadata: Dict[str,str]` equality만 (`domain/vector/value_objects.py:82-103`), `_build_qdrant_filter`는 MatchValue만 (`qdrant_vectorstore.py:193-209`) | 섹션 단계 document_id 다중 값 → `metadata_any` additive 필드 + 어댑터 MatchAny 분기 (D6) |
| ES ids query | `es_repo.search(ESSearchQuery(query=...))`가 임의 Query DSL 수용 (`es_repository.py:110`) — `{"ids": {"values": [...]}}` 가능 | 청크 확장기가 **기존 repo 무수정**으로 단일 호출 조회 (D5) |
| 라우터 관례 | hybrid_search_router: 인증 의존성 없음, DI placeholder + lifespan 싱글턴 override, ValueError→422 (`hybrid_search_router.py:49-84`) | 신규 라우터 동일 관례 (D7) |
| 임베딩 관례 | 검색 싱글턴은 `OpenAIEmbedding(settings.openai_embedding_model)` (`main.py:1074`) | 라우팅 API 동일 — 컬렉션별 해석은 후속 (D9) |
| 폴백 대상 | `HybridSearchRequest`가 `collection_name`/`metadata_filter` 지원 — lifespan 싱글턴 `_hybrid_search_use_case` 존재 | 오케스트레이터가 인스턴스 위임 (D8) |
| 요약 payload | 문서: `document_id/kb_id/summary/keywords/filename/section_count` · 섹션: `section_ref/clause_title/chunk_index/summary/keywords/document_id` (3단계 §4) | 라우팅 근거를 payload에서 그대로 추출 — 추가 조회 없음 (D11) |

---

## 2. 설계 결정 (Decisions)

| ID | 결정 | 근거 |
|----|------|------|
| D1 | **단계 포트 3종 + 순수 VO 계약**: `domain/routed_retrieval/` — `DocumentRouterInterface.route(query_vector, scope, top_k, request_id) -> list[DocumentCandidate]`, `SectionRouterInterface.route(query, query_vector, document_ids, scope, params, request_id) -> list[SectionCandidate]`, `ChunkExpanderInterface.expand(sections, documents_by_id, scope, request_id) -> list[RoutedChunk]` (documents_by_id는 D5 근거 동봉용). VO: `RoutedScope(collection_name, kb_id?)`, `DocumentCandidate(document_id, score, summary, keywords, filename)`, `SectionCandidate(section_ref, document_id, score, vector_rank/bm25_rank/source, summary, clause_title)`, `RoutedChunk(section_ref, document_id, content, clause_title, score, document: DocumentCandidate, section: SectionCandidate, from_fallback=False)` | 사용자 요구 "각각 분할과 변경에 용이하게" — 단계 간 결합은 VO뿐, 구현 교체 자유. 오케스트레이터 테스트는 fake 3개로 완결 |
| D2 | **오케스트레이터**: `RoutedRetrievalUseCase`(application) — `embed_text` 1회 → ① 문서 top-K → (0건이면 즉시 전량 폴백) → ② 섹션 top-N → ③ 확장 → 결과 < top_k면 폴백 보충 → 응답. **LLM 호출 0회**. 파라미터 검증·폴백 판단·병합은 `RoutedRetrievalPolicy`(domain 순수 함수) 위임 | Plan §4-1/FR-07. 흐름 제어만 application, 규칙은 domain |
| D3 | **문서 라우터**: `QdrantDocumentRouter` — `VectorStoreInterface.search_by_vector(vector, doc_top_k, SearchFilter(metadata={"chunk_type": "document_summary"[, "kb_id"]}), collection_name)`. equality 필터만으로 충분(MatchAny 불요), 가드 bypass 자연 통과. 후보의 summary/keywords/filename은 payload에서 추출 | 벡터만으로 시작(사용자 Q3) — BM25 추가는 이 구현 교체로 흡수(후속 document-router-hybrid) |
| D4 | **섹션 라우터**: `HybridSectionRouter` — ⓐ Qdrant 벡터: `SearchFilter(metadata={"chunk_type": "section_summary"}, metadata_any={"document_id": [...]})` ⓑ ES BM25: `bool{must: multi_match(query, ["summary_text^1.5", "summary_keywords"]), filter: [terms document_id, term chunk_type=section_summary(, term kb_id)]}` → `RRFFusionPolicy.merge`로 병합. **병합 키 = 요약 ID(3자 일치)** — 두 소스 hit id가 동일해 RRF가 정확히 겹침을 인식 | Plan FR-03. 기존 RRF 정책·`SearchHit` 무수정 재사용. summary_text^1.5 부스트는 content^1.5 선례 |
| D5 | **청크 확장기**: `EsChunkExpander` — `section_ref` 목록을 **ES ids query 1회**(`{"ids": {"values": refs}}`, rawchunk ES `_id`=chunk_id)로 parent 본문 조회. 누락 ref는 제외+warning(부분 실패 업로드 대비). 섹션 순위 유지, 근거(문서/섹션 후보)를 `RoutedChunk`에 동봉 | Qdrant payload 필터 scroll은 인덱스 부재로 기각(Plan 리스크). 기존 `es_repo.search` 재사용 — repo 무수정 |
| D6 | **다중 값 필터 additive 확장**: `SearchFilter`에 `metadata_any: Dict[str, list[str]] = field(default_factory=dict)` 추가 + `_build_qdrant_filter`에 `MatchAny` 분기 추가. 기존 equality 경로·가드(bypass는 `metadata.get("chunk_type")` equality 기준) 무변경 — 가드 테스트로 회귀 확인 | 섹션 스코핑 필수 기능. frozen dataclass 필드 추가(default)는 기존 생성자 호출 전부 호환 |
| D7 | **API**: 신규 `routed_retrieval_router.py`, `POST /api/v1/retrieval/routed`. 요청: `query`(필수), `collection_name?`(기본 settings), `kb_id?`, `doc_top_k`(1~20, 기본 5), `section_top_k`(1~50, 기본 10), `top_k`(1~30, 기본 5), `rrf_k`(기본 60), `bm25_weight/vector_weight`(기본 0.5). 응답: `results[]`(content·section_ref·document_id·clause_title·score·`from_fallback` + 근거는 **평탄 형제 필드** `document{summary,score,filename,keywords}` / `section{summary,clause_title,keywords,score,vector_rank,bm25_rank,source}` — 폴백 결과는 둘 다 null) + `total_found`/`fallback_used`/`fallback_count`/`document_candidates`/`section_candidates` + `request_id`. 인증 없음·ValueError→422 (hybrid 관례) | Plan §4-6 관측 우선 — 튜닝/RAGAS 입력. 파라미터 범위는 라우터 Field + 정책 이중 검증 |
| D8 | **폴백**: 확장 결과 < top_k → 싱글턴 `HybridSearchUseCase.execute(HybridSearchRequest(query, top_k=top_k, metadata_filter={kb_id?}, collection_name))` 위임 → `RoutedRetrievalPolicy.merge_fallback(routed, fallback_hits, top_k)`(순수 함수)가 dedup 후 보충. **dedup 키 = 라우팅 반환 parent의 `section_ref`(chunk_id)** — 폴백 hit의 `metadata.chunk_id` 또는 `metadata.parent_id`가 집합에 있으면 제외. 폴백 결과는 `from_fallback=True`, routing 근거 없음. 문서 라우팅 0건이면 전량 폴백 | Plan FR-05. 기존 유스케이스 무수정 위임. child hit의 parent_id 매칭으로 조 단위 중복 차단 |
| D9 | **임베딩 = 검색 싱글턴 관례**(`OpenAIEmbedding(settings.openai_embedding_model)`). 요약 벡터는 업로드 모델 스냅샷으로 생성됨 — 운영 전제 "검색 기본 모델 = 업로드 기본 모델"을 API description에 명시. 컬렉션별 모델 해석은 후속 | hybrid/retrieval 기존 관례와 동일 — 이번 사이클에서 새 규칙을 만들지 않음 |
| D10 | **배선**: lifespan에서 `_routed_retrieval_use_case = create_routed_retrieval_use_case(hybrid=_hybrid_search_use_case)` 싱글턴 생성(qdrant/es 클라이언트·임베딩은 함수 내 구성, 폴백만 기존 싱글턴 주입) + DI override. **config 추가 0** — 기본값은 라우터 Field/정책 상수(hybrid 관례) | 마이그레이션 0·설정 0·기존 검색 무수정 (NFR-01) |
| D11 | **근거 동봉 규격**: 문서 요약(5줄)·섹션 요약(3줄)은 저장 시 이미 절단됨 — 추가 절단 없이 그대로 동봉(NFR-07 충족). keywords는 저장분 그대로 | 3부작의 방어 절단이 응답 크기 상한을 이미 보장 |
| D12 | **관측 로그**: 오케스트레이터가 1줄 info — `request_id/collection_name/kb_id/document_candidates/section_candidates/routed_results/fallback_added/fallback_used` (FR-11) | 튜닝·백필 우선순위 판단 데이터 |
| D13 | **파라미터 정책**: `RoutedRetrievalPolicy` 상수 — `DOC_TOP_K 1~20(기본 5)`, `SECTION_TOP_N 1~50(기본 10)`, `TOP_K 1~30(기본 5)`. `validate_params` 위반 ValueError(→422), `need_fallback(result_count, top_k)`, `merge_fallback(...)` 순수 함수 3종 | 규칙의 domain 집약(선행 사이클 IterationLimitPolicy 선례) |

---

## 3. 파일 구조 (신규/수정)

```
idt/
├── src/
│   ├── domain/routed_retrieval/
│   │   ├── __init__.py                                   [신규]
│   │   ├── schemas.py    # RoutedScope·DocumentCandidate·SectionCandidate·RoutedChunk·RoutedRetrievalResult [신규]
│   │   ├── interfaces.py # DocumentRouter/SectionRouter/ChunkExpander 포트 3종 [신규]
│   │   └── policy.py     # RoutedRetrievalPolicy (검증·폴백 판단·병합 dedup) [신규]
│   ├── application/routed_retrieval/
│   │   ├── __init__.py                                   [신규]
│   │   └── use_case.py   # RoutedRetrievalUseCase (오케스트레이터 + 폴백) [신규]
│   ├── infrastructure/routed_retrieval/
│   │   ├── __init__.py                                   [신규]
│   │   ├── qdrant_document_router.py                     [신규: D3]
│   │   ├── hybrid_section_router.py                      [신규: D4 — RRF 재사용]
│   │   └── es_chunk_expander.py                          [신규: D5 — ids query]
│   ├── domain/vector/value_objects.py                    [수정: SearchFilter.metadata_any (D6)]
│   ├── infrastructure/vector/qdrant_vectorstore.py       [수정: _build_qdrant_filter MatchAny 분기 (D6)]
│   ├── api/routes/routed_retrieval_router.py             [신규: D7]
│   └── api/main.py                                       [수정: 싱글턴 배선 + 라우터 등록 (D10)]
└── tests/
    ├── domain/routed_retrieval/test_policy.py            [신규]
    ├── application/routed_retrieval/test_use_case.py     [신규: fake 3포트 오케스트레이션]
    ├── infrastructure/routed_retrieval/
    │   ├── test_qdrant_document_router.py                [신규]
    │   ├── test_hybrid_section_router.py                 [신규]
    │   └── test_es_chunk_expander.py                     [신규]
    ├── infrastructure/vector/test_search_filter_any.py   [신규: D6 + 가드 회귀]
    └── api/test_routed_retrieval_router.py               [신규]
```

**마이그레이션 0 · config 추가 0 · 기존 검색 파일 수정 = vector 필터 additive 1쌍뿐**

---

## 4. 흐름 (§5)

```
POST /api/v1/retrieval/routed {query, collection?, kb_id?, K/N/top_k...}
  1. policy.validate_params (위반 → 422)
  2. vector = embedding.embed_text(query)                        # 유일한 모델 호출
  3. docs = document_router.route(vector, scope, K)              # chunk_type=document_summary (+kb_id)
     └ 0건 → fallback 전량 (routed=[])                           # D8
  4. sections = section_router.route(query, vector, doc_ids, N)  # 벡터(MatchAny)+BM25 → RRF (키=요약ID 3자 일치)
  5. chunks = chunk_expander.expand(sections, scope)             # ES ids query 1회, 누락 warning
  6. policy.need_fallback(len(chunks), top_k)
     → hybrid.execute(...) → policy.merge_fallback(chunks, hits, top_k)  # dedup: section_ref vs chunk_id/parent_id
  7. 응답 (근거 동봉 + fallback/후보 수 관측) + info 로그 1줄 (D12)
외부 IO: 임베딩1 + Qdrant2 + ES2(BM25/ids) (+폴백 시 ES1+Qdrant1) — NFR-04 충족
```

---

## 5. 테스트 계획 (TDD — 구현 전 작성)

| 파일 | 핵심 케이스 |
|------|------------|
| `test_policy.py` | validate_params 범위(경계·422 근거), need_fallback(부족/충족/0), merge_fallback(dedup: chunk_id 겹침·parent_id 겹침 제외, 순서 보존, top_k 절단, from_fallback 표시) |
| `test_use_case.py` | 정상 하강(단계 호출 순서·인자), 문서 0건→전량 폴백, 부족→보충 병합, 충족→폴백 미호출, fake 포트 교체 계약(FR-08), LLM 미호출·임베딩 1회 |
| `test_qdrant_document_router.py` | 필터 조립(chunk_type/kb_id/컬렉션), payload→DocumentCandidate 매핑(summary/keywords/filename) |
| `test_hybrid_section_router.py` | 벡터 필터(MatchAny document_id), ES 쿼리 dict(multi_match 필드·terms 필터), RRF 병합(동일 ID 겹침=both), SectionCandidate 매핑(section_ref/clause_title) |
| `test_es_chunk_expander.py` | ids query 구성, 누락 ref 제외+warning, 섹션 순위 유지, 근거 동봉 |
| `test_search_filter_any.py` | metadata_any→MatchAny 조건, equality와 공존, **기존 가드 must_not 회귀 불변** |
| `test_routed_retrieval_router.py` | 200 응답 계약(routing 근거·fallback 필드), 파라미터 422, 기본값 |
| 기존 스위트 | hybrid_search·retrieval·vector 가드 무수정 통과(회귀 0) |

---

## 6. 구현 순서 (Do 체크리스트)

1. **domain**: schemas(VO 5종) → interfaces(포트 3종) → policy (+ 테스트 선작성)
2. **필터 확장(D6)**: `SearchFilter.metadata_any` + 어댑터 MatchAny (+ 가드 회귀 테스트)
3. **infrastructure**: qdrant_document_router → hybrid_section_router(RRF 재사용) → es_chunk_expander (각 테스트 선작성)
4. **application**: RoutedRetrievalUseCase(오케스트레이터+폴백) (+ fake 포트 테스트)
5. **api**: routed_retrieval_router (+ 테스트) → main.py 배선(hybrid 싱글턴 주입)
6. **검증**: 전체 테스트 + `/verify-architecture` + `/verify-tdd` + `/verify-logging` + 기존 검색 회귀
```
