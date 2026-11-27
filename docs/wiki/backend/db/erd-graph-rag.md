---
title: 미니 ERD — Graph RAG (MySQL V086~V091 + Neo4j) 와 문서 삭제 훅
status: approved
source_type: conversation
source_refs:
  - idt/db/migration/V086__create_graph_rag_setting.sql ~ V091__create_graph_document_topic.sql
  - idt/src/infrastructure/graph_rag/models.py
  - idt/src/infrastructure/graph_rag/repositories.py, job_store.py, decision_store.py, topic_store.py (세션 방식)
  - idt/src/infrastructure/graph_rag/neo4j/cypher.py (SCHEMA_STATEMENTS, VECTOR_INDEX_CREATE, WRITE_*, DELETE_*)
  - idt/src/infrastructure/graph_rag/neo4j/store.py (build_driver, _query 예외 변환, ensure_schema, _write_chunk_tx)
  - idt/src/infrastructure/graph_rag/resolution/embedder.py (dimensions 지정)
  - idt/src/application/graph_rag/hooks.py (GraphDeletionHook)
  - idt/src/application/doc_browse/delete_document_use_case.py (_notify_deleted)
confidence: 0.85
version: 1
created: 2026-11-21
updated: 2026-11-27
verified_at: 49b0970
reviewer: 배상규
---

# 미니 ERD — Graph RAG (MySQL V086~V091 + Neo4j)

## 문제

그래프 RAG 데이터는 MySQL 6테이블(설정·이력·잡·판정·주제)과 Neo4j(엔티티·청크·관계)로 나뉜다.
"원본이 어느 쪽인가", "삭제 시 어디까지 지워지나"를 모르면 정합성 작업에서 한쪽만 고치게 된다.

## 검증된 사실

### 1. MySQL (V086~V091) — FK 없음, 전 컬럼 COMMENT

| V | 테이블 | 키·인덱스 | 요점 |
|---|--------|-----------|------|
| V086 | `graph_rag_setting` | PK 고정 id(시드 1행) | 운영값 15개([[execution-gates-and-rollout]] §4). 갱신은 UPDATE |
| V087 | `graph_rag_stage_change` | idx(created_at) | from/to_stage, changed_by, eval_baseline_run_id, eval_graph_run_id, force_reason(500) |
| V088 | `graph_extraction_job` | idx(document_id, created_at), idx(status) | status pending·processing·completed·partial·failed, mode resume·rebuild, trigger_source upload·admin, extractor_version, 카운터 8종, error_message TEXT, requested_by, started/finished_at |
| V089 | `graph_resolution_decision` | idx(review_status, created_at), idx(document_id), idx(entity_id) | 아래 |
| V090 | `graph_topic` | **UNIQUE(parent_key, normalized_name)**, idx(level, status) | name·normalized_name(64), level 1·2, parent_id, parent_key(대분류 ''), status active·pending·retired, origin admin·auto |
| V091 | `graph_document_topic` | PK(document_id, topic_id), idx(topic_id) | is_primary, probability(5,4; rule·LLM은 NULL), decision_id |

`graph_resolution_decision` 주요 컬럼: id(uuid5, Neo4j `MENTIONED_IN.decision_id`와 같음) · job_id · document_id · chunk_id(주제 판정은 `__document__`) · mention_text(255) · mention_type(주제는 `주제:대분류`/`주제:소분류`) · candidates JSON(label·entity_id·name·type·match·similarity) · probabilities JSON(Jev) · chosen_label(`C1..`/`NEW`) · entity_id · created_new · decided_by · band · probability(5,4; Jev 경로만) · llm_confidence · llm_reason(500) · review_status none·pending·approved·rejected · reviewed_by/at · review_note.
→ **엔티티 판정과 주제 판정이 한 테이블**이며 `mention_type`·`chunk_id`로 구분한다.

세션 방식(두 계열):
- 설정·단계 이력: 요청 세션 주입, 저장소 안에서 commit 안 함. 단계 변경은 이력 INSERT + 설정 UPDATE가 한 세션.
- 잡·판정·주제·문서↔주제: **앱 수명 싱글턴 + 호출마다 짧은 독립 세션**. LLM·Neo4j 호출은 트랜잭션 밖. (백그라운드 잡이라 요청 세션이 없다.)

### 2. Neo4j

| 라벨 | 속성 |
|------|------|
| `Entity` | id(uuid4), scope_key(`global`), name, normalized_name(값 `{chunk_id}::이름`, 조문 `{document_id}::제N조`), type, description, name_embedding(값·조문은 없음), created_at, updated_at — 이름·타입·임베딩은 **ON CREATE에서만** 씀 |
| `Chunk` | chunk_id, document_id, kb_id, collection_name, extractor_version, extracted_at, topic_ids |
| `Alias` | scope_key, normalized, surface |

| 관계 | 방향 | 속성 |
|------|------|------|
| `MENTIONED_IN` | Entity→Chunk | decision_id, document_id (판정 1건 = 엣지 1개) |
| `RELATES` | Entity→Entity | id, type(업무 관계 타입), evidence_chunk_id, document_id, kb_id, evidence_text, source/target_decision_id, extractor_version, topic_ids |
| `REFERS_TO` | Entity→Entity | RELATES와 같음(규칙 추출 조문 참조) |
| `ALIAS_OF` | Alias→Entity | 없음 |

- 관계 라벨(`RELATES` 등)은 코드 상수, 업무 관계 타입(적용대상·예외…)은 `type` 속성 값. Cypher 값은 전부 파라미터 — 예외는 경로 단계 수·벡터 차원(둘 다 검증된 int를 문자열로 삽입).
- **관계는 근거 청크마다 별도 엣지**다(같은 두 엔티티 사이에도 청크별). 그래서 document_id로 지우면 그 문서 근거 관계만 정확히 사라진다.
- 제약·인덱스: `entity_id`·`chunk_id` 유일, `entity_norm(scope_key, normalized_name)`, `alias_norm`, `chunk_doc(document_id)`, 벡터 `entity_name_vec`(cosine, 차원 = `GRAPH_ENTITY_EMBEDDING_DIMENSIONS` 기본 512).
- 벡터 인덱스가 있으면 `SHOW INDEXES`로 차원을 읽어 설정과 비교, 다르면 `GraphEmbeddingDimMismatchError`로 **모듈 비활성**(차원 다른 벡터로 조용히 검색하지 않기). 512는 Aura Free 용량 때문에 줄인 값이고 OpenAI `dimensions` 파라미터로 맞춘다.
- 드라이버 `AsyncGraphDatabase.driver` 앱 수명 싱글턴. Aura(`neo4j+s://`)와 자체 호스팅(`bolt://`)은 주소만 다르다. **모든 드라이버 예외는 `GraphBackendUnavailableError`로 변환**된다 — Cypher 문법 오류도 "백엔드 불가"로 보일 수 있다.
- 청크 쓰기 트랜잭션: Chunk MERGE → 새 Entity → MENTIONED_IN → RELATES → REFERS_TO → Alias, `execute_write` 하나(실패 시 전체 롤백).

### 3. 원본은 어디인가

| 데이터 | 원본 | 복사본 |
|--------|------|--------|
| 문서↔주제 | MySQL `graph_document_topic` | Neo4j `Chunk.topic_ids`·관계 `topic_ids` |
| 판정 이력·검토 상태 | MySQL `graph_resolution_decision` | Neo4j `MENTIONED_IN.decision_id` |
| 청크 본문 | ES | Neo4j에는 본문 없음(근거 텍스트만), 검색 시 ES에서 재조회 |

### 4. 문서 삭제 훅

코어 `DeleteDocumentUseCase._notify_deleted`(단건·검증·일괄 공통)가 저장소(Qdrant·ES·메타) 삭제 후 호출, 예외는 삼킨다. `GraphDeletionHook`은 **노출 단계와 무관하게** 정리한다:

1. 문서↔주제 연결 삭제(MySQL)
2. 그 문서의 판정 기록 전부 삭제(검토 큐에 남지 않게, MySQL)
3. Neo4j: 문서 근거 `RELATES`·`REFERS_TO` 삭제 → 문서 `Chunk` DETACH DELETE(`MENTIONED_IN` 함께) → 언급 0개 엔티티와 그 별칭 삭제
4. Neo4j 불가(`GraphBackendUnavailableError`)면 경고 후 종료

- MySQL을 먼저 정리하므로 Neo4j가 꺼져 있어도 MySQL 쪽은 깨끗해지고, Neo4j 고아 근거는 관리자 `/integrity`(그래프 청크 표본을 ES와 대조)로 찾는다.
- 고아 엔티티 정리 쿼리는 문서와 무관하게 **전체 엔티티를 훑는다** — 그래프가 커지면 삭제 비용이 커진다.
- 다른 문서에서도 언급된 엔티티와 그 별칭은 남는다.
- KB 삭제 훅은 없다(KB는 soft delete, 결과 청크는 ES 재조회에서 걸러짐).

## 다음에 적용하는 법

1. 그래프 테이블은 [[mysql-fk-collation]] 규칙대로 FK·CHARSET 없이 만들어졌다. 다른 테이블에서 이 테이블을 참조할 때도 소프트 참조로 둔다.
2. 판정 테이블을 조회할 때 엔티티/주제 판정을 `mention_type LIKE '주제:%'` 또는 `chunk_id='__document__'`로 구분한다.
3. `GRAPH_ENTITY_EMBEDDING_DIMENSIONS`를 바꾸면 기존 Neo4j 벡터 인덱스와 불일치해 **기동 시 모듈이 꺼진다** — 인덱스·임베딩 재구축 계획과 같이 바꾼다.
4. "백엔드 불가"(503·`backend_unavailable`)가 보이면 연결 문제만이 아니라 Cypher 오류일 가능성도 서버 로그의 원 예외 이름으로 확인한다.
5. 새 저장소 삭제 경로를 만들면 `_notify_deleted`를 지나게 해 그래프 정리가 같이 일어나게 한다.

## 관련 문서

- [[overview]] (Graph RAG 개요) · [[extraction-pipeline]] · [[entity-resolution]] · [[topic-classification]] · [[erd-kb]] · [[erd-evaluation]]
