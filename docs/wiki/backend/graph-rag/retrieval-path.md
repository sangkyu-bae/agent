---
title: Graph RAG 검색 경로 — 주제 범위·씨앗·경로 탐색·점수·가중 RRF·타임아웃·skip_reason
status: approved
source_type: conversation
source_refs:
  - idt/src/application/rag_agent/tools.py (_start_supplemental, _primary_with_supplemental, _merge_supplemental, _SUPPLEMENTAL_HARD_TIMEOUT_S=6.0)
  - idt/src/domain/hybrid_search/policies.py (RRFFusionPolicy.merge_many, _fused_source)
  - idt/src/application/graph_rag/retrieval/source.py (retrieve, search_trace, _route, _link, _traverse, _ROUTE_BUDGET_SHARE=0.5)
  - idt/src/application/graph_rag/retrieval/router.py (QueryTopicRouter, CACHE_TTL_SECONDS=600, CACHE_MAX_ENTRIES=1000)
  - idt/src/domain/graph_rag/retrieval.py (MAX_SEEDS=5, LINK_CANDIDATES=20, MAX_GRAPH_CHUNKS=50, MAX_PATHS=200, HUB_DEGREE_LIMIT=15, phrases, chunk_scores, pick_seeds)
  - idt/src/infrastructure/graph_rag/neo4j/cypher.py (FIND_PATHS, LINK_NAMES, LINK_VECTOR, ENTITIES_IN_SCOPE), neo4j/store.py (link_entities)
  - idt/src/infrastructure/graph_rag/es_evidence_fetcher.py (ids + hard/lenient + collection 필터)
  - idt/src/application/graph_rag/admin/search_test_use_case.py (retrieval_timeout_ms=MAX 5000 고정)
  - docs/02-design/features/graph-rag-foundation.design.md (M5-1 동시 실행, M5-6, M5-12)
confidence: 0.85
version: 1
created: 2026-11-21
updated: 2026-11-27
verified_at: 49b0970
reviewer: 배상규
---

# Graph RAG 검색 경로

## 문제

그래프 검색은 RAG 도구 안의 보조 공급자로 동작하고, 실패·시간 초과를 예외 없이 `skip_reason`으로
삼킨다. 그래서 답변은 늘 정상이고 "그래프가 실제로 기여했는가"는 로그·관리자 검색 테스트로만 보인다.
검색 품질이나 지연을 다루려면 단계별로 무엇이 일어나는지 알아야 한다.

## 검증된 사실

### 1. 도구 쪽 흐름 (`InternalDocumentSearchTool`)

1. 권한 확인·부서 visibility 필터 합성.
2. 라우팅 검색이 결과를 내면 그대로 반환(보조 결합 없음, `routed_path` 로그).
3. 단일/멀티쿼리 경로에서 **보조 검색 태스크를 기존 검색보다 먼저 시작**하고 기존 검색을 await. 기존 검색이 예외면 보조 태스크를 취소하고 재전파.
4. 보조 태스크는 `asyncio.wait_for(retrieve, 6.0초)`로 한 번 더 감싼다 — 공급자가 설정 상한을 못 지켜도 답변이 막히지 않게 하는 최후 방어선.
5. 결과 대기: 시간 초과·예외·`skip_reason`·빈 hits면 로그만 남기고 기존 결과 그대로. hits가 있으면 결합.
6. 결합 결과의 hit `source`가 `ai_retrieval_source.fusion_source`로 기록된다.

`SupplementalQuery`에는 도구가 계산한 hard/lenient 필터·collection·es_index·top_k가 그대로 들어간다.

### 2. 결합: 도구 최종 결과에 가중 RRF

`RRFFusionPolicy.merge_many([RankedList("primary", 기존, 1.0), RankedList("graph", hits, graph_rrf_weight)])`
- 점수 = Σ `weight / (k + r)`(r은 1부터, k는 도구 `rrf_k`). 겹치는 청크는 primary의 본문·메타 유지.
- source: primary에만 → 원래 값, graph에만 → `graph`, 둘 다 → `"{원래}+graph"`.
- 최종 상위 `top_k`만 남으므로 그래프 결과가 들어오면 기존 결과 일부가 밀려난다.

코드 기준 동작: Plan은 "하이브리드 RRF의 세 번째 입력"이었지만 코드는 **하이브리드 내부(BM25·벡터 RRF)를 건드리지 않고** 도구 최종 결과에 한 번 더 합친다.

### 3. `GraphRetrievalSource.retrieve`

설정 → `RolloutPolicy.skip_reason` → `asyncio.wait_for(search_trace, retrieval_timeout_ms/1000)` →
`TimeoutError`→`timeout`, `GraphBackendUnavailableError`→`backend_unavailable`, 그 밖→경고+`error` →
trace의 skip_reason(`no_entity`) → 성공 로그(hits·씨앗 수·scope·scope_by·단계별 ms) + `SupplementalResult("graph", hits, weight)`.

### 4. `search_trace` 단계 (관리자 검색 테스트도 같은 함수)

**① 질문 주제 판정 ∥ 씨앗 후보 연결 (`asyncio.gather`)** — 주제 판정을 기다리지 않으려고 동시 실행(Design M5-1).

- 주제 판정(`QueryTopicRouter`), 예산 = `retrieval_timeout_ms × 0.5`(넘으면 `route_timeout`, 범위 없이 계속):
  - 캐시: 정규화 질문 키, TTL 600초, 최대 1,000개(가득 차면 가장 오래 넣은 것 제거), 꺼내면 `decided_by=cache`. `jev_error`·`llm_error`는 캐시 안 함.
  - usable 대분류(최대 30) 없으면 `no_topics`. Jev 가능하면 `ChoiceQuestion`, 최대 후보 확률 ≥ link면 그 주제, 아니면 `jev_unsure`/`jev_error`로 LLM에 넘김. LLM: 예외 `llm_error`, 후보 아님(NEW 포함) `no_matching_topic`, confidence가 high·medium 아님 `llm_unsure`.
  - 범위 = 고른 **대분류 id 하나**. 질문 단계에서 새 주제는 만들지 않는다.
  - 코드 기준 동작: 라우터의 Jev 연속 실패 카운터는 **앱 수명**이라 5회 연속 실패 후에는 재기동 전까지 Jev를 다시 시도하지 않는다(추출 쪽은 잡마다 리셋).
- 씨앗 후보 연결: Kiwi 명사 → 연속 명사 3·2·1개 묶음을 붙여 쓴/띄어 쓴 형태로 정규화(1글자 단독 명사 제외) + 질문 전체 임베딩(실패 시 벡터 없이). 정확·별칭 쿼리와 벡터 쿼리(k=80, score ≥ 0.875)를 동시에 → 정확 > 별칭 > 벡터로 합쳐 상위 20. **이 단계엔 주제 범위를 걸지 않는다.**
- 후보 0개 → `skip_reason="no_entity"`.

**② 범위 우선 씨앗**: 범위가 있으면 후보 중 범위 주제 청크에 언급된 엔티티를 찾고, 없으면 범위 해제(`no_entity_in_scope`). `pick_seeds`: 범위 안 후보 먼저, **남는 자리는 범위 밖 후보로 채워** 최대 5개.
코드 기준 동작: Plan FR-29는 "고른 주제 문서 안에서만 시작"이었지만 코드는 범위 밖으로 채운다(Design M5-12).

**③ 경로 탐색과 점수** (씨앗 언급 청크 쿼리 ∥ 경로 쿼리)

```cypher
MATCH (s:Entity) WHERE s.id IN $ids
MATCH p = (s)-[:RELATES|REFERS_TO*1..{hops}]-(:Entity)            -- 방향 무시
WHERE all(n IN nodes(p)[1..-1] WHERE COUNT { (n)-[:RELATES|REFERS_TO]-() } <= $hub_limit)
  AND ($topic_ids IS NULL OR all(r IN relationships(p)
        WHERE any(t IN coalesce(r.topic_ids, []) WHERE t IN $topic_ids)))
RETURN names, types, chunks LIMIT $limit    -- 200, ORDER BY 없음
```

- 허브: 관계 15개 초과 엔티티는 **경로 중간 노드 불가**(시작·끝은 허용). 관계 수는 전 문서 합산.
- 범위가 있으면 경로의 모든 관계가 범위 topic_ids를 가져야 한다. 방향은 무시 — 추출 방향 규칙은 표시 일관성용.
- 점수: 씨앗 언급 청크 1.0(언급 수 무관) + 경로 d번째 관계의 근거 청크에 `1/(1+d)`(0.5, 0.333, 0.25) 누적.

**④ 범위 필터**: 점수 청크 중 범위 안 청크만. 0개면 범위 해제(`no_chunk_in_scope`) 후 같은 씨앗으로 재탐색 — 주제를 잘못 골라도 답을 놓치지 않게. 점수 내림차순(동점 청크 id) 상위 50.

**⑤ 근거 본문 ES 조회**: `ids` + hard(term) + lenient(값 일치 OR 필드 부재) + collection — 하이브리드 BM25와 같은 규칙. **그래프 탐색은 전역이지만 반환 직전 청크 단위로 권한을 다시 건다.** 결과는 `HybridSearchResult(source="graph")`, 그래프 점수 순서 유지, 빠진 수는 `filtered_out`, 상위 `top_k`.

### 5. 타임아웃 층

| 층 | 값 | 넘으면 |
|----|----|--------|
| 질문 주제 판정 | retrieval_timeout_ms × 0.5 | 범위 없이 계속(`route_timeout`) |
| Jev 1회 | judgment_timeout_seconds + 0.5초 | LLM으로 |
| 그래프 검색 전체 | retrieval_timeout_ms (기본 800, 최대 5000) | `timeout` skip |
| 도구 하드 상한 | 6.0초 | 도구 로그 `timeout`, 기존 결과만 |
| 관리자 검색 테스트 | 5000ms 고정 | 이 요청만 최대값 |

### 6. skip_reason과 범위 사유

- skip_reason: `stage_off`, `grant_not_admin`, `timeout`, `backend_unavailable`, `error`, `no_entity`(소스) / `not_wired`, `routed_path`, `empty`, `timeout`·`error`(도구 로그).
- 범위 사유(`QueryScope.reason`)는 skip이 아니라 trace에만: `no_topics`, `jev_unsure`, `jev_error`, `jev_unavailable`, `llm_error`, `no_matching_topic`, `llm_unsure`, `route_timeout`, `route_error`, `no_entity_in_scope`, `no_chunk_in_scope`. 운영 경로 로그에는 `scope`·`scope_by`만 남고 사유는 없다 → 사유는 **관리자 검색 테스트 응답**에서 본다.

### 7. 관리자 검색 테스트

stage off면 409, 그 외는 관리자 grant로 실행. 필터는 관리자 본인 기준 `kb_id`만(일반 사용자 권한 흉내 안 냄). 그래프 trace + 하이브리드(첫 호출 때 만드는 싱글턴) + RRF k=60 결합을 나란히 반환. 하이브리드 실패는 `hybrid_error`로 내고 그래프 결과는 그대로 보여 준다.

### 8. 함정·주의 (실측 확인)

- **`retrieval_timeout_ms` 기본 800이면 그래프 보조 검색이 대개 `timeout`으로 빠진다.** 지연의 대부분은 질문 주제 LLM 판정이다. 관리자 테스트·평가 시 3000~5000으로 올린다. (기본 800에서 주제 판정 예산은 400ms다.)
- 관리자 검색 테스트는 5000ms 고정이라 **테스트에서 보인 결과가 운영(설정값) 대화에서는 timeout일 수 있다.**

## 다음에 적용하는 법

1. "그래프가 결과에 안 섞인다" → 도구 로그 `Supplemental retrieval skipped`의 reason → 소스 로그 `graph retrieval done`의 hits/seeds → 관리자 검색 테스트로 범위 사유 확인 순서.
2. 끔/켬 효과 비교 전 `retrieval_timeout_ms`를 올렸는지 확인한다(800이면 켬이 사실상 끔과 같다).
3. 탐색 상수(씨앗 5·후보 20·허브 15·경로 200·청크 50)는 도메인 상수이고 설정이 아니다. 조정 시 `domain/graph_rag/retrieval.py` 하나만 바꾼다.
4. 권한 필터는 ES 재조회 한 곳에 있다. 그래프에서 본문을 직접 반환하는 경로를 만들면 권한 우회가 된다 — 반드시 `EsEvidenceFetcher`를 거친다.
5. 다른 보조 공급자를 만들 때도 "예외 대신 skip_reason, 도구 하드 상한" 계약을 따른다([[degradation-vs-failure-boundary]]).

## 관련 문서

- [[overview]] · [[execution-gates-and-rollout]] · [[topic-classification]] · [[failure-and-ops]] · [[architecture-overview]] §2(c)
