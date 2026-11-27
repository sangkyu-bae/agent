---
title: Graph RAG 엔티티 판정 — 후보 검색·Jev 3구간·LLM 재판정·별칭·검토 큐
status: approved
source_type: conversation
source_refs:
  - idt/src/application/graph_rag/resolution/resolver.py (resolve_chunk, _resolve_one, _judge, _jev_usable, _from_jev, _from_llm, MAX_CONSECUTIVE_JEV_FAILURES=5, _CONTEXT_PAD=300)
  - idt/src/domain/graph_rag/resolution.py (MIN_VECTOR_SIMILARITY=0.75, ResolutionPolicy, types_compatible, unambiguous_exact)
  - idt/src/domain/graph_rag/extraction.py (NameNormalizer, GLOBAL_SCOPE)
  - idt/src/infrastructure/graph_rag/neo4j/store.py (find_candidates, reassign_decision), neo4j/cypher.py
  - idt/src/infrastructure/graph_rag/resolution/jev_chooser.py, llm_chooser.py, embedder.py
  - idt/src/application/graph_rag/admin/review_use_case.py
  - idt/src/infrastructure/graph_rag/models.py (graph_resolution_decision), idt/db/migration/V089__create_graph_resolution_decision.sql
confidence: 0.85
version: 1
created: 2026-11-21
updated: 2026-11-27
verified_at: 49b0970
reviewer: 배상규
---

# Graph RAG 엔티티 판정

## 문제

LLM이 청크마다 뽑은 언급("주담대", "주택담보대출")을 기존 엔티티와 합칠지 새로 만들지 정해야 한다.
잘못 합치면 무관한 개념 사이에 경로가 생기고, 너무 쪼개면 그래프가 연결되지 않는다.
판정기를 고치거나 임계값을 조정하기 전에 어떤 순서로 무엇이 결정되는지 알아야 한다.

## 검증된 사실

### 1. 입력 준비

1. 정규화 키 기준 언급 중복 제거(먼저 나온 것 유지 → LLM 언급이 규칙 언급보다 앞).
2. 이름 임베딩 대상: 키 지정 없음(조문 아님) + 값 아님. 청크 단위 배치 임베딩(`graph_entity_embedding_dimensions` 지정). **임베딩 실패는 경고 후 벡터 없이 진행** → 후보가 정확·별칭 일치만 남는다.
3. 언급마다 `_resolve_one`을 순차 실행.

정규화(`NameNormalizer`): NFKC → 연속 공백 1칸 → 양끝 공백·구두점·괄호 제거 → `casefold()`.
코드 기준 동작: **조사 제거는 없다**(클래스 주석·Plan은 "Kiwi로 조사 제거"라 적었지만 Kiwi는 검색 질문 명사 추출에만 쓰인다). 타입이 설정 목록 밖이면 '기타'.

### 2. 판정 순서 (`_resolve_one`)

| 순서 | 조건 | 결과 | decided_by / band |
|------|------|------|-------------------|
| 1 | 같은 잡에서 이미 만든 (저장 키, 타입) | 그 엔티티에 연결 | rule / auto_link |
| 2 | 값 이름이거나 키 지정(조문·별표·부칙) | 새 엔티티 | rule / auto_new |
| 3 | 후보 검색 후 타입 호환 후보 0개 | 새 엔티티 | rule / auto_new |
| 4 | 정확·별칭 일치 + **타입 완전 동일** 후보가 정확히 1개 | 그 후보에 연결 | rule / auto_link |
| 5 | 그 밖 | `_judge` (Jev 또는 LLM) | 아래 |

- 1번 캐시(`ResolveRunState.known`)는 새 엔티티를 만들 때만 채워지고 잡마다 비워진다.
- 2번 때문에 조문 엔티티는 **잡마다 새로** 만들어진다.
- 타입 호환: 같거나 둘 중 하나가 '기타'. 비호환 후보는 제외(이름이 같아도 다른 종류는 안 합침). 단 4번 "명확한 정확 일치"는 '기타' 호환을 인정하지 않는다 — 같은 이름·같은 타입이 둘 이상이어도 판정으로 넘어간다.

### 3. 후보 검색 (`find_candidates`)

1. 정확: `(:Entity {scope_key, normalized_name})` — similarity 1.0.
2. 별칭: `(:Alias {scope_key, normalized})-[:ALIAS_OF]->(e)` — 1.0.
3. 벡터: `db.index.vector.queryNodes('entity_name_vec', k=candidate_top_k, ...)`. Neo4j cosine score는 `(1+cos)/2` 정규화 값이라 코사인 하한 0.75를 **score 0.875**로 환산해 거르고, 기록용 similarity는 `2·score−1`로 되돌린다.
4. 같은 엔티티는 먼저 들어온 것 유지(정확 > 별칭 > 벡터) → similarity 내림차순 `candidate_top_k`개.

벡터 k도 `candidate_top_k`(기본 5)라 상위 5개 중 하한을 넘은 것만 남는다. `scope_key`는 항상 `"global"` — **엔티티는 KB 구분 없이 전역 공유**다(권한은 검색 반환 직전 ES에서 다시 건다).

### 4. Jev 3구간

Jev 사용 조건: 판정자 조립됨(`JUDGMENT_BACKEND`로 `JudgmentPort` 생성) AND `jev_enabled` AND 이 잡의 Jev 연속 실패 < 5.

- 질문: `ChoiceQuestion` 라벨 `C1..Ck`(이름·타입·설명 200자) + `NEW`. state = 언급 이름·타입·설명·문맥(언급 위치 앞뒤 300자, 못 찾으면 앞 600자). 지시: 표기·띄어쓰기·약칭이 달라도 같은 대상이면 그 후보, 비슷해도 다르면 NEW.
- 외부 타임아웃 `judgment_timeout_seconds + 0.5`초. 예외는 그대로 올리고 대체는 resolver 한 곳에서.
- p\* = **NEW를 뺀** 후보 확률 최댓값(NEW 확률은 구간 판정에 직접 안 씀).
  - p\* ≥ link(0.8) → auto_link (jev)
  - p\* < new(0.4) → auto_new (jev)
  - 사이 → rejudge: LLM 재판정(`llm_rejudge`), **결과와 무관하게 검토 대기**
- Jev 예외 → 실패 수 +1, LLM 대체로. 성공하면 실패 수 0으로 리셋.

### 5. LLM 재판정·대체

- 모델 `effective_rejudge_model_id`(재판정 모델 없으면 추출 모델), temperature 0, 구조화 출력 `{label, confidence(high|medium|low), reason}`.
- 응답 라벨이 후보도 NEW도 아니면 `NEW + low + "unknown label"`.

| 상황 | 결과 | 검토 |
|------|------|------|
| LLM 예외 | **새 엔티티**(사유 `llm error`) | pending |
| 라벨=후보 / NEW | 연결 / 새 엔티티 | 재판정이면 항상 pending. 대체(`llm_fallback`)는 confidence high면 none, 아니면 pending |

LLM 실패 시 합치지 않고 새로 만든다 — **잘못 합치기보다 쪼개지는 쪽**을 택한 설계.
코드 기준 동작: Plan의 band 값(`llm_rejudge`, `none`)과 달리 코드 enum은 band = auto_link·auto_new·rejudge·fallback, decided_by = rule·jev·llm_rejudge·llm_fallback이다.

### 6. 별칭

연결 대상의 정규화 이름이 언급의 정규화 키와 다르면 `(:Alias {scope_key:"global", normalized, surface})-[:ALIAS_OF]->(:Entity)`를 남긴다. 다음 판정·검색에서 정확 일치로 잡힌다. 같은 잡 캐시나 이름이 같은 정확 일치로 연결되면 별칭은 안 생긴다.

### 7. 검토 큐 (`ReviewUseCase`)

검토 대기(pending)가 되는 것: 재판정 전부 · high가 아닌 대체 판정 · LLM 실패 · 자동 생성 주제([[topic-classification]]).

- 목록: review_status별 생성 시각 내림차순. stage off면 409.
- 승인: pending이 아니면 409 `GRAPH_REVIEW_ALREADY_DONE`. 엔티티 판정은 그래프 그대로 두고 행만 approved.
- 거절:
  - 대상 지정 시 **판정 당시 후보 중 하나**이고 현재 연결 엔티티와 달라야 함 — 아니면 422 `GRAPH_REVIEW_TARGET_INVALID`. 임의 엔티티 병합 기능은 없다.
  - 대상 없음(분리)은 원래 연결 판정일 때만 — 언급 이름으로 새 엔티티 생성(이 엔티티는 **이름 임베딩이 없음**).
  - 재연결: 그 decision_id가 붙은 `MENTIONED_IN`과 그 판정을 source/target으로 둔 `RELATES`·`REFERS_TO`를 대상으로 옮긴다(관계는 끝점 변경이 불가해 같은 속성으로 새로 만들고 지움). 옮긴 뒤 언급 0개 엔티티는 별칭과 함께 삭제.
  - 행을 rejected로 바꾸고 entity_id를 최종 대상으로 갱신.
- 코드 기준 동작: Design의 `422 GRAPH_TYPE_MISMATCH`는 없다(후보가 이미 타입 호환으로 걸러짐).

## 다음에 적용하는 법

1. **임계값 조정은 `graph_rag_setting`에서**(link·new, 0 < new < link). 코드 상수를 바꾸지 않는다. 0.875 score 환산처럼 Neo4j score 정규화를 잊지 말 것.
2. **판정 경로를 추가·변경할 때** 검토 대기 규칙(재판정=항상, 대체=high 아니면, 실패=항상)을 유지한다. "LLM 실패 → 새 엔티티"는 의도된 보수 정책이다.
3. **Jev를 쓰려면** `JUDGMENT_BACKEND` 조립 + 설정 `jev_enabled=true` 둘 다 필요. 하나만 켜면 조용히 LLM만 쓴다.
4. **정규화를 바꾸면**(예: 조사 제거 도입) 기존 엔티티·별칭의 `normalized_name`과 어긋나므로 rebuild 재추출 계획과 함께 한다.

## 관련 문서

- [[overview]] · [[extraction-pipeline]] · [[erd-graph-rag]] (graph_resolution_decision 필드) · [[grounding-rewrite-loop]] (판정 모델 선택 교훈)
