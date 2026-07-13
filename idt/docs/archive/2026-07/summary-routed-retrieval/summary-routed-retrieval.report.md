# summary-routed-retrieval 완료 리포트

> **Feature**: summary-routed-retrieval (3계층 하강 라우팅 리트리버 — 검색 파이프라인 4부작 완결)
> **Project**: sangplusbot (idt 백엔드)
> **Author**: 배상규
> **Period**: 2026-07-09 (Plan → Report, 단일 세션)
> **Final Match Rate**: **99%** (최초 95% → Medium 1 + Low 3 즉시 해소)
> **Status**: ✅ Completed — **원 목표(청킹→섹션 요약→문서 요약→라우팅 검색) 전 구간 완성**

---

## Executive Summary

### 1.1 개요

| 항목 | 내용 |
|------|------|
| Feature | summary-routed-retrieval |
| 기간 | 2026-07-09 (Plan·Design·Do·Check·Report) |
| PDCA 흐름 | Plan ✅ → Design ✅ → Do ✅ → Check ✅ (99%) → Report ✅ |
| 아키텍처 | Thin DDD |
| 시리즈 | clause-aware-chunking(1) → card-section-summary(2) → document-summary-routing(3) → **본 기능(4) — 4부작 완결** |

### 1.2 결과 요약

| 지표 | 값 |
|------|-----|
| Match Rate | 99% (D1~D13 반영, 흐름/IO 상한 완전 일치, 테스트 계획 100%) |
| 신규 프로덕션 파일 | 12개 (776 LOC — domain 4·application 2·infrastructure 5·api 1) |
| 수정(additive) 파일 | 3개 (SearchFilter/어댑터 필터 확장 + main.py 배선) |
| **마이그레이션 / config / 기존 검색 수정** | **0 / 0 / 동작 보존 필터 확장 1쌍뿐** |
| 신규 테스트 | 43건 (667 LOC) 전부 통과 — 회귀: 기존 검색·요약 파이프라인 237+74건 그린 |
| High 잔여 Gap | 0건 (Medium 1·Low 3은 Check 중 즉시 해소) |

### 1.3 Value Delivered

| Perspective | 전달된 가치 (실측) |
|-------------|---------------------|
| **Problem** | 3계층 요약 데이터가 검색에 쓰이지 않던 문제 — 일상어 질의와 조문 표현의 괴리, 다문서 KB의 넓은 후보 공간 노이즈 → 요약 계층으로 후보를 좁히는 라우팅 검색 부재 해소. |
| **Solution** | `POST /api/v1/retrieval/routed` — 임베딩 1회 → 문서 요약 벡터 top-K(1차) → 섹션 요약 벡터+BM25(`summary_text^1.5`/`summary_keywords`) RRF top-N(2차) → `section_ref` ES ids query로 조 본문 확장(3차). 부족 시 기존 하이브리드 폴백(조 단위 dedup). **LLM 0회 결정론적**. |
| **Function/UX Effect** | 응답에 라우팅 근거(문서/섹션 요약·단계별 점수·source)와 `fallback_used` 관측 동봉 — "왜 이 조문인지" 설명 가능 + 튜닝/RAGAS 입력 확보. 요약 없는 기존 문서도 폴백으로 누락 없음. 기존 검색·에이전트 무영향. |
| **Core Value** | **원 요청의 최종 그림 완성** — 업로드 한 번으로 3계층 자동 적재, 질의 한 번으로 계층 하강 검색. 단계 3포트 추상화로 후속 개선(문서 BM25·LLM 리랭커)이 구현 교체로 흡수. 선행 사이클의 결정적 ID(3자 일치)·가드 bypass 설계가 이번 구현을 그대로 받쳐줌. |

---

## 2. 구현 범위

### 2.1 신규 (12개, 776 LOC)

| 레이어 | 파일 | 역할 |
|--------|------|------|
| domain | `routed_retrieval/schemas.py` | VO 6종 — 단계 간 계약(Scope/Params/후보 2종/RoutedChunk/Result) |
| domain | `routed_retrieval/interfaces.py` | 포트 3종 (FR-08 단계 교체) |
| domain | `routed_retrieval/policy.py` | 범위 검증·폴백 판단·`merge_fallback`(chunk_id/parent_id 조 단위 dedup) |
| application | `routed_retrieval/use_case.py` | 오케스트레이터 — `_descend` 하강 + 폴백 getter 위임(실패 격리) |
| infra | `qdrant_document_router.py` | 1차 — document_summary 벡터 top-K(kb_id 필터, 가드 bypass) |
| infra | `hybrid_section_router.py` | 2차 — 벡터 MatchAny + ES BM25 → `RRFFusionPolicy` 재사용, 소스별 graceful 강등 |
| infra | `es_chunk_expander.py` | 3차 — ES ids query 1회(point id≠chunk_id 함정 회피), 누락 warning |
| infra | `payload_utils.py` | payload 문자열 캐스팅 keywords 복원 |
| api | `routed_retrieval_router.py` | `POST /api/v1/retrieval/routed` — 근거·관측 동봉 응답 |

### 2.2 수정 (additive, 3개)

- `domain/vector/value_objects.py` — `SearchFilter.metadata_any`(다중 값, default 빈 dict — 기존 생성자 전부 호환)
- `infrastructure/vector/qdrant_vectorstore.py` — `_build_qdrant_filter` MatchAny 분기(equality·요약 가드 무변경, 회귀 테스트 고정)
- `api/main.py` — 팩토리·getter·lifespan 싱글턴·DI override·include_router (hybrid 관례 동일)

---

## 3. 핵심 설계 결정 이행 (D1~D13: 13/13)

- **D1 포트 3종**: fake 3포트로 오케스트레이터 테스트 완결 — "각각 분할과 변경에 용이하게" 요구를 구조로 검증.
- **D4 RRF 병합 키 = 요약 ID 3자 일치**: 2단계 D5의 결정적 uuid5가 Qdrant point id = ES `_id`를 보장 → 벡터/BM25 hit가 같은 키로 병합(source="both" 테스트 검증). **선행 사이클 설계의 배당**.
- **D5 ES ids query**: rawchunk의 point id ≠ chunk_id 함정(2단계 확인 사실)을 ES `_id` 직조회로 회피 — 단일 호출·기존 repo 무수정.
- **D8 폴백**: getter 주입(lifespan 순서 무관) + 실패 시 라우팅 결과 보존 + 조 단위 dedup(child의 parent_id 매칭 포함).
- **D6 additive 필터**: 가드 bypass·equality 경로 불변을 회귀 테스트 2종으로 고정 — FR-09(기존 경로 무영향) 충족.

## 4. Gap 처리 (Check 95% → 99%)

| # | Gap | 심각도 | 조치 |
|---|-----|:------:|------|
| G1 | D7 응답 구조 편차(설계 `routing{}` 래퍼 vs 구현 평탄 필드) | Medium | 신규 API·소비자 부재 → 코드=진실로 설계 갱신(+total_found/keywords 반영) |
| G2 | D1 포트 시그니처 편차(documents_by_id 등) | Low | 설계를 실제 시그니처로 갱신 |
| G3 | D12 로그 `fallback_used` 누락 | Low | 로그 필드 추가 |
| G4 | `execute` 40줄 초과 소지(NFR-05) | Low | `_descend` 헬퍼 분리 리팩터 + 74건 재통과 |

## 5. 검증 결과

- **테스트**: 신규 43건(정책 17·오케스트레이터 6·단계 구현 11·필터 5·라우터 4) 통과. 회귀: 기존 검색(hybrid/retrieval/collection_search)·retriever·vector·요약 파이프라인 237+74건 그린, 회귀 0.
- **verify 핵심 검사**: print 0, domain→infra 0, infra Policy 0, routes→infra 0, error 로그 전건 `exception=`.
- **배선**: `import src.api.main` OK.
- **FR 전량 충족**: LLM 0회(FR-07)·단계 교체(FR-08)·기존 무영향(FR-09) 포함 11/11.

## 6. 후속 과제

1. **E2E 실측 (즉시 권장)**: 요약 활성 KB에 실제 규정 PDF 업로드 → `POST /api/v1/retrieval/routed` 호출 — routing 근거·fallback_used로 품질 관찰, K/N/weights 튜닝.
2. **rag-routed-integration**: 에이전트 RAG 도구(RagToolConfig)에 라우팅 모드 opt-in — 실 사용처 연결.
3. **routing-quality-eval**: RAGAS 인프라 재사용 — 라우팅 vs 기존 하이브리드 정확도 실측.
4. **section-summary-backfill**: `fallback_used` 관측 기반 기존 문서 일괄 요약.
5. **document-router-hybrid / LLM 리랭커**: DocumentRouter/SectionRouter 구현 교체 지점 활용.

## 7. 학습 노트

- **선행 설계가 후행 구현을 값싸게 만든다**: 결정적 ID(2단계)→RRF 키 자연 정합, 가드 bypass(3단계)→라우터 필터 그대로 통과, ES `_id`=chunk_id 확인(2단계)→확장기 1호출. 4번째 사이클의 구현 비용은 앞선 세 사이클의 계약 정밀도가 결정했다.
- **포트가 요구사항인 기능**: "변경에 용이하게"라는 비기능 요구는 문서가 아니라 인터페이스 개수로 구현된다 — fake 교체 테스트가 그 요구의 수용 기준이 됐다.
- **폴백은 신뢰 전환 장치**: 신규 검색을 기본 경로로 밀어넣지 않고 관측(`fallback_used`)과 함께 병행 — 데이터가 전환 시점을 알려주는 구조.
- **점수 체계 주의(후속 참고)**: 라우팅 결과의 score는 RRF(1/(k+rank)) 스케일이라 폴백 hit의 RRF 점수와 절대 비교 불가 — 혼합 정렬이 필요해지면 정규화 재설계 필요.
