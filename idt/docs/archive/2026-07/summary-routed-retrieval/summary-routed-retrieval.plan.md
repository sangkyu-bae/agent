# summary-routed-retrieval Planning Document

> **Summary**: 문서 등록 3부작(1 rawchunk → 2 섹션 요약 → 3 문서 요약)이 쌓은 3계층 데이터를 **검색에서 소비하는 라우팅 리트리버**를 신규 API로 도입한다. 질의 임베딩 1회 → ① `document_summary` 벡터 검색으로 문서 top-K 선별 → ② 선별 문서 내 `section_summary`를 벡터 + 요약 키워드/텍스트 BM25 RRF 병합으로 top-N 선별 → ③ `section_ref`로 rawchunk(조 parent 본문) 확장. 각 단계는 독립 인터페이스로 분할해 교체·변경이 용이한 구조(사용자 요구)로 만들고, LLM 호출 0회의 결정론적 파이프라인으로 유지한다. 요약 데이터가 없는 문서(기존 적재분·요약 비활성 KB)는 결과 부족 시 기존 하이브리드 검색 폴백으로 보완한다. 기존 검색 경로 무수정 — 에이전트 RAG 도구 연동은 후속 사이클.
>
> **Project**: sangplusbot (idt 백엔드 전용)
> **Author**: 배상규
> **Date**: 2026-07-09
> **Status**: Draft
> **선행**: clause-aware-chunking → card-section-summary → document-summary-routing (전부 완료, `docs/archive/2026-07/`)

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 3계층 요약 데이터는 완성됐지만 검색은 여전히 rawchunk 직접 하이브리드뿐 — 일상어 질의가 조문 표현과 어긋나면 매칭이 약하고, 여러 문서가 섞인 KB에서 후보 공간이 넓어 노이즈가 크다. 쌓아둔 문서/섹션 요약·키워드가 검색에 쓰이지 않고 있다. |
| **Solution** | 신규 라우팅 검색 API: 질의 → 문서 요약 벡터 top-K(1차) → 해당 문서 섹션 요약 벡터+BM25(summary_text/keywords) RRF top-N(2차) → `section_ref`로 조(parent) 본문 확장(3차). 단계별 인터페이스 분리(문서 라우터/섹션 라우터/청크 확장기)로 교체 용이. 결과 부족 시 기존 하이브리드 폴백 + 응답에 라우팅 근거(선별 문서·섹션 요약·점수) 동봉. |
| **Function/UX Effect** | 검증용 신규 엔드포인트 1개 — 기존 검색 API·에이전트 무영향. 응답에 라우팅 경로가 보여 "왜 이 조문이 나왔는지"를 요약 근거로 설명 가능. 요약 없는 문서도 폴백으로 누락되지 않음. |
| **Core Value** | 3부작 데이터의 첫 소비처 — 계층 하강으로 후보 공간을 문서→섹션 순으로 좁혀 rawchunk 노이즈 감소. LLM 0회 결정론적 파이프라인이라 빠르고 비용 없음. 단계 추상화로 이후 개선(문서 단계 BM25 추가, LLM 리랭커 등)이 stage 교체로 흡수됨. |

---

## 1. Overview

### 1.1 Purpose

등록 파이프라인이 만든 3계층을 소비하는 검색 경로를 만든다.

```
질의 (임베딩 1회, LLM 0회)
 └─① 문서 라우팅: chunk_type=document_summary 벡터 top-K → document_id 목록
     └─② 섹션 라우팅: 선별 문서 내 chunk_type=section_summary
         벡터 + BM25(summary_text/summary_keywords) RRF → top-N 섹션(section_ref)
         └─③ rawchunk 확장: section_ref(=parent chunk_id)로 조 본문 반환
[폴백] 최종 결과 < top_k → 기존 하이브리드 검색으로 부족분 보충(dedup, fallback 표시)
```

**이번 범위 = 신규 검색 API + 파이프라인**(사용자 확정). 에이전트 RAG 도구 연동·기존 경로 교체는 후속.

### 1.2 Background — 재사용 자산 (2026-07-09 코드 확인)

- **RRF 병합 즉시 재사용**: `RRFFusionPolicy.merge(bm25_hits, vector_hits, top_k, k, weights)` 순수 도메인 정책(`domain/hybrid_search/policies.py:33`) + `SearchHit`/`HybridSearchResult` 스키마 — 섹션 단계 RRF에 무수정 재사용.
- **폴백 즉시 재사용**: `HybridSearchUseCase`(BM25+벡터 RRF)가 lifespan 싱글턴으로 존재 — 폴백 위임 대상. `HybridSearchRequest.metadata_filter`로 kb_id 필터 지원.
- **가드 통과 설계 완비**: `QdrantVectorStore.search_by_vector`는 명시 `chunk_type` 필터가 요약 타입이면 must_not 가드를 해제(document-summary-routing D12) — 라우팅 검색이 정확히 이 bypass를 위해 설계됨.
- **저장 계약**: `document_summary` payload에 `document_id/kb_id/summary/keywords/section_count`, `section_summary` payload에 `section_ref/clause_title/chunk_index/summary/keywords`. ES에 `summary_text`(nori)/`summary_keywords`(keyword) 매핑 존재 — 섹션 BM25 대상.
- **⚠️ 핵심 주의(2단계 확인 사실)**: rawchunk의 **Qdrant point id ≠ payload `chunk_id`** — `section_ref`는 parent의 payload `chunk_id`다. 조 본문 조회는 point id 조회(`retrieve`)가 아니라 **payload `chunk_id` 필터 검색/scroll**이어야 한다(3자 불일치: point id/chunk_id/ES _id 중 ES만 chunk_id와 동일 — ES `_id` 직조회 `mget`도 대안, Design 확정).
- **다중 값 필터**: 섹션 단계의 "선별 문서 내" 조건은 `document_id` 다중 값(MatchAny) 필터 필요 — 기존 `MetadataFilter`/`SearchFilter`는 단일 값 equality만 지원 → additive 확장 지점.
- **임베딩**: 기존 hybrid_search API는 싱글턴 임베딩(설정 기본 모델) 사용 — 신규 API도 동일 관례(컬렉션별 모델 해석은 Design에서 판단).

### 1.3 사용자 결정 사항 (2026-07-09 확인)

| 질문 | 결정 |
|------|------|
| 적용 지점 | **신규 검색 API만** — 기존 검색·에이전트 무수정, 연동은 후속 |
| 라우팅 방식 | **하이브리드 하강(벡터+키워드 RRF)** — 단, **각 단계를 분할해 변경·교체가 용이한 구조**로 |
| 키워드 활용 | **섹션 단계 BM25 병합** — summary_text/summary_keywords를 벡터와 RRF (문서 단계는 벡터만 시작, 구조상 추가 용이하게) |
| 요약 없는 문서 | **결과 부족 시 기존 하이브리드 폴백** — 누락 방지, 점진 전환 |

---

## 2. Scope

### 2.1 In Scope (백엔드 idt/)

**A. 라우팅 파이프라인 도메인 (단계 분리 — 사용자 요구 핵심)**
- [ ] `domain/routed_retrieval/`(가칭): 단계 인터페이스 3종 — `DocumentRouterInterface`(질의 벡터→문서 후보), `SectionRouterInterface`(문서 후보→섹션 후보), `ChunkExpanderInterface`(섹션 후보→rawchunk 결과). 단계 간 계약은 순수 VO(`DocumentCandidate`/`SectionCandidate`/`RoutedChunk` — id·점수·요약 근거 포함)
- [ ] `RoutedRetrievalPolicy`: 파라미터 검증(doc_top_k/section_top_k/top_k 범위), 폴백 발동 기준(결과 수 < top_k), dedup 규칙(폴백 보충 시 동일 parent 제거)
- [ ] 오케스트레이터는 단계 조립·폴백 판단만 — 각 단계 구현 교체가 다른 단계에 영향 없음

**B. 단계 구현 (infrastructure)**
- [ ] `QdrantDocumentRouter`: `chunk_type=document_summary` (+ kb_id/collection 필터) 벡터 top-K — 가드 bypass 경로 사용
- [ ] `HybridSectionRouter`: 선별 `document_id` 집합 내 ① Qdrant 벡터(chunk_type=section_summary + document_id MatchAny) ② ES BM25(`multi_match` on summary_text/summary_keywords + terms 필터) → `RRFFusionPolicy` 재사용 병합
- [ ] `ParentChunkExpander`: `section_ref` 목록 → 조(parent) 본문 조회(payload chunk_id 기준 — ES `mget` vs Qdrant 필터는 Design 확정) → `RoutedChunk`(본문 + 라우팅 근거: 문서/섹션 요약·점수·clause_title)
- [ ] 다중 값 필터 지원: `SearchFilter`/어댑터에 MatchAny 계열 additive 확장(기존 equality 경로 무수정)

**C. 유스케이스 + 폴백**
- [ ] `RoutedRetrievalUseCase`: 임베딩 1회 → ①→②→③ → 결과 부족 시 기존 `HybridSearchUseCase` 위임 보충(dedup, `fallback_used`/`fallback_count` 표시) — LLM 호출 0회
- [ ] 파라미터: `query`, `collection_name`, `kb_id?`, `doc_top_k`(기본값 Design), `section_top_k`, `top_k`, RRF weights(기본값) — 기본값은 config/상수

**D. 신규 API (라우터 1개)**
- [ ] `POST /api/v1/retrieval/routed`(가칭 — 기존 retrieval/hybrid 라우터 관례 따라 Design 확정): 요청/응답 스키마, 응답에 결과별 라우팅 근거(`routing`: 선별 문서 요약·섹션 요약·단계별 점수)와 `fallback_used` 포함 — 검증·튜닝용 관측 데이터
- [ ] 인증·권한은 기존 hybrid_search 라우터 관례 준용(Design 확인)

**E. 테스트 (TDD — 구현 전 작성)**
- [ ] 단계별 단위: 문서 라우터 필터 조립(chunk_type/kb_id), 섹션 라우터 RRF 병합·document_id 스코핑, 확장기 section_ref→parent 매핑·근거 동봉
- [ ] 오케스트레이터: 정상 하강, 폴백 발동/미발동, dedup, 빈 컬렉션(전부 폴백), LLM 미호출
- [ ] 정책: 파라미터 검증, 폴백 기준, dedup 규칙
- [ ] 라우터: 200/422/(권한), 응답 계약(routing 근거·fallback 플래그)
- [ ] 회귀 가드: 기존 hybrid_search·retrieval 스위트 무수정 통과

### 2.2 Out of Scope (후속 PDCA)

| 항목 | 사유/비고 |
|------|-----------|
| 에이전트 RAG 도구 연동(RagToolConfig 라우팅 모드) | 신규 API 검증 후 rag-routed-integration으로 |
| 기존 하이브리드/retrieval 경로 교체 | 품질 실측 후 판단 |
| LLM 리랭커/라우터 | stage 교체 지점으로 구조만 확보 |
| 문서 단계 BM25 병합 | 섹션 단계만 시작 — DocumentRouter 구현 교체로 추가 가능 |
| 품질 평가(RAGAS 비교 실측) | routing-quality-eval 별도 사이클 |
| 프론트엔드/General Chat 연동 | API 검증 후 |
| 섹션 요약 백필 | 폴백이 커버 — section-summary-backfill 별도 |

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | 요구사항 | 우선순위 |
|----|----------|---------|
| FR-01 | 신규 라우팅 검색 API가 질의를 받아 문서(1차)→섹션(2차)→rawchunk(3차) 하강 결과를 반환한다 | High |
| FR-02 | 1차: `document_summary` 벡터 검색으로 문서 top-K 선별(kb_id/collection 필터 지원) | High |
| FR-03 | 2차: 선별 문서 내 `section_summary`를 벡터 + BM25(summary_text/summary_keywords) RRF 병합으로 top-N 선별 | High |
| FR-04 | 3차: `section_ref`로 조(parent) 본문을 조회해 반환 — point id/chunk_id 불일치를 정확히 처리 | High |
| FR-05 | 최종 결과가 top_k 미만이면 기존 하이브리드 검색으로 부족분을 보충하고 `fallback_used`로 표시한다(동일 parent dedup) | High |
| FR-06 | 응답의 각 결과에 라우팅 근거(선별 문서 요약, 섹션 요약·clause_title, 단계별 점수)가 동봉된다 | High |
| FR-07 | 파이프라인 전체에서 LLM 호출 0회(결정론적) — 임베딩 1회만 | High |
| FR-08 | 각 단계는 독립 인터페이스 뒤에 있으며 다른 단계 수정 없이 구현 교체 가능하다 | High |
| FR-09 | 기존 검색 경로(hybrid/retrieval/에이전트)는 무수정·무영향이다 | High |
| FR-10 | 파라미터(doc_top_k/section_top_k/top_k/weights) 검증 실패는 422 | Medium |
| FR-11 | 검색 실행 로그에 단계별 후보 수·폴백 여부가 request_id와 함께 기록된다 | Medium |

### 3.2 Non-Functional Requirements

| ID | 요구사항 |
|----|----------|
| NFR-01 | additive-only — 신규 라우터/유스케이스/단계 구현만. 기존 코드 수정은 다중 값 필터 additive 확장 등 동작 보존분에 한정 |
| NFR-02 | Thin DDD — 단계 인터페이스·VO·정책은 domain, 구현은 infrastructure, 조립은 application |
| NFR-03 | TDD — 테스트 선작성 (pytest) |
| NFR-04 | 지연 상한 — 외부 IO 5회 내외(임베딩 1 + Qdrant 2 + ES 1 + 본문 조회 1, 폴백 시 +α). 단계 간 순차 의존만 존재 |
| NFR-05 | 함수 40줄, if 중첩 2단계, config 하드코딩 금지(기본 K/N/weights는 상수 또는 설정) |
| NFR-06 | LOG-001 — print 금지, exception= 필수, request_id 전파 |
| NFR-07 | 라우팅 결과의 설명 가능성 — 근거(요약·점수) 동봉은 응답 크기 상한 고려(요약 절단 규칙 Design) |

---

## 4. 핵심 설계 방향 (Plan 레벨 결정, 상세는 Design)

1. **단계 = 인터페이스, 오케스트레이터 = 조립**: 사용자 요구("각각 분할과 변경에 용이하게")를 구조로 — `DocumentRouter`/`SectionRouter`/`ChunkExpander` 3개 포트. 문서 단계 BM25 추가·LLM 리랭커·섹션 단위 변경 전부 "구현 교체"로 흡수, 파이프라인 계약(VO) 불변.
2. **문서 단계는 벡터만, 섹션 단계는 하이브리드로 시작**: 사용자 결정(Q3) — 문서 요약은 표현이 압축적이라 벡터 우선, 전문용어 매칭이 중요한 섹션 단계에 BM25(RRFFusionPolicy 재사용) 배치.
3. **가드 bypass = 명시 chunk_type 필터**: 선행 사이클 D12가 예비해 둔 경로 그대로 — 라우팅 검색만 요약 계층을 보고, 다른 검색은 여전히 격리됨.
4. **section_ref 해석은 ES `_id` 활용 검토**: rawchunk의 ES `_id` = chunk_id(2단계 확인) — parent 본문 조회를 ES `mget`으로 하면 Qdrant payload 필터 scroll(인덱스 없음)보다 저렴할 수 있음. Qdrant 필터 방식과 Design에서 비교 확정.
5. **폴백은 위임이지 재구현이 아님**: 기존 `HybridSearchUseCase` 인스턴스에 그대로 위임 — 요약 없는 문서 커버 + 라우팅 품질 미덥지 않은 초기 운영의 안전망. `fallback_used` 관측으로 백필 필요성 판단 데이터 확보.
6. **관측 우선 응답 설계**: 검증 목적 API이므로 라우팅 근거·단계별 점수·폴백 여부를 응답에 남겨 튜닝(K/N/weights)과 후속 RAGAS 평가의 입력으로 사용.

---

## 5. Risks & Mitigations

| 리스크 | 영향 | 대응 |
|--------|------|------|
| 요약 없는 문서 누락 | 기존 적재분 검색 불가 | 폴백(FR-05) + `fallback_used` 관측 → 백필 우선순위 판단 |
| section_ref→parent 조회 비용(payload 필터 scroll, 인덱스 없음) | 3차 단계 지연 | ES `_id` mget 대안 비교(Design §4) — 최악 시 Qdrant payload 인덱스 후속 |
| document_id 다중 값 필터 미지원 | 섹션 스코핑 불가 | `SearchFilter`/어댑터 MatchAny additive 확장(기존 equality 경로 무수정) + 가드 테스트 |
| 문서 top-K가 작으면 정답 문서 탈락(라우팅 오류 전파) | 재현율 하락 | 기본 K 보수적(예: 5~10) + 폴백 + 응답 근거로 튜닝. 품질 실측은 후속 사이클 |
| 컬렉션별 임베딩 모델 불일치(요약 벡터 vs 질의 벡터) | 유사도 왜곡 | 요약 벡터는 원 업로드 모델 스냅샷으로 생성됨 — 질의 임베딩 모델 결정 규칙(싱글턴 vs 컬렉션 해석)을 Design에서 확정 |
| 섹션은 있는데 문서 요약이 없는 잡(구버전 2단계 적재분) | 1차에서 문서 탈락 | 폴백 커버 + (선택) 문서 단계 결과 부족 시 섹션 직접 검색 완화 규칙 Design 검토 |
| 응답 비대(근거 동봉) | 페이로드 과대 | 근거 요약 절단 상한(NFR-07) |

---

## 6. Acceptance Criteria

- [ ] 요약 3계층이 적재된 문서 질의 → 신규 API가 조(parent) 본문 + 라우팅 근거(문서/섹션 요약·점수) 반환, LLM 호출 0회
- [ ] 섹션 단계에서 벡터 단독으로 놓치는 전문용어 질의가 BM25 병합으로 회수됨(단위 테스트 — RRF 병합 검증)
- [ ] 요약 없는 문서만 있는 컬렉션 질의 → 전량 폴백 결과 + `fallback_used=true`
- [ ] 라우팅+폴백 혼합 시 동일 parent 중복 없음(dedup)
- [ ] 각 단계 구현을 fake로 교체해도 오케스트레이터 테스트 통과(인터페이스 계약 검증)
- [ ] 기존 hybrid_search·retrieval·에이전트 스위트 무수정 통과(회귀 0)
- [ ] `/verify-architecture`, `/verify-tdd`, `/verify-logging` 통과

---

## 7. 후속 로드맵 (참고)

1. **rag-routed-integration**: 에이전트 RAG 도구(RagToolConfig)에 라우팅 모드 opt-in — 실제 사용처 연결
2. **routing-quality-eval**: RAGAS 인프라 재사용 — 라우팅 vs 기존 하이브리드 정확도 실측, K/N/weights 튜닝
3. **section-summary-backfill**: `fallback_used` 관측 데이터 기반 기존 문서 일괄 요약
4. **document-router-hybrid**: 문서 단계 BM25 병합(DocumentRouter 구현 교체)
5. **chunking-default-migration**: 실측 후 기존 검색/업로드 기본 경로 전환 판단
