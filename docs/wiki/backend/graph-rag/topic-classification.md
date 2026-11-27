---
title: Graph RAG 문서 주제 분류 — 2단계 주제·슬롯 판정·검색 범위·topic_ids 복사
status: approved
source_type: conversation
source_refs:
  - idt/src/domain/graph_rag/topic.py (TopicPolicy, MAX_TOPIC_CANDIDATES=30, TOPIC_EXCERPT_CHUNKS=3, TOPIC_EXCERPT_CHARS=3000, 상태·출처)
  - idt/src/application/graph_rag/topic/classifier.py (classify, _resolve_slot, _secondary_names, _new)
  - idt/src/application/graph_rag/topic/review.py (TopicReviewer)
  - idt/src/application/graph_rag/extraction/use_case.py (_classify_topics, _copy_topics)
  - idt/src/infrastructure/graph_rag/topic/proposer.py, topic/prompts.py
  - idt/src/infrastructure/graph_rag/topic_store.py, neo4j/cypher.py (SET_DOCUMENT_TOPICS)
  - idt/db/migration/V090__create_graph_topic.sql, V091__create_graph_document_topic.sql
  - docs/02-design/features/graph-rag-foundation.design.md (§11.9 module-4b)
confidence: 0.85
version: 1
created: 2026-11-21
updated: 2026-11-27
verified_at: 49b0970
reviewer: 배상규
---

# Graph RAG 문서 주제 분류

## 문제

문서 제목 엔티티가 모든 조항과 `포함` 관계로 이어지면 2단계 탐색이 문서 전체로 퍼진다(Design §11.9).
그래서 module-4b에서 "주제"를 도입했다. 주제는 **탐색 경로가 아니라 검색 범위**다 — 엔티티처럼
관계로 잇지 않고, 질문 주제와 같은 주제의 청크·관계로 탐색을 좁히는 데만 쓴다.

## 검증된 사실

### 1. 주제 구조

- 2단계: 대분류(level 1, parent 없음) > 소분류(level 2, parent 필수).
- 이름 1~64자(공백 정리), 정규화는 `NameNormalizer` 결과 앞 64자. 유일 키 `(parent_key, normalized_name)` — 대분류 parent_key는 `''`.
- 상태 active · pending(자동 생성, **검토 전에도 usable**) · retired. 출처 admin · auto.
- 원본은 MySQL(`graph_topic`, `graph_document_topic`). Neo4j의 `Chunk.topic_ids`·관계 `topic_ids`는 복사본.

### 2. 언제 분류하나

추출 잡 안에서 **잡당 1회**:
- 문서에 이미 주제 연결이 있고 rebuild가 아니면 **기존 주제를 그대로 쓴다(재분류 안 함)**.
- rebuild이거나 연결이 없으면 분류. 예외는 경고 후 기존 주제 id로 계속 — 주제 실패가 추출을 막지 않는다.
- 분류의 LLM·Jev 호출 수는 잡 카운터에 더해진다.

### 3. 분류 흐름

1. 문서 앞부분: `chunk_index` 순 앞 3개 단위를 이어 최대 3,000자.
2. LLM 제안(추출 모델): `major{name,description}`, `minor|null`, `secondary[이름]`(최대 3개 받음). 프롬프트는 문서 제목을 그대로 쓰지 말고, 조항 번호·날짜·숫자를 넣지 말고, **다른 문서에도 붙일 수 있는 일반적 이름**을 고르라고 지시.
3. 대분류 슬롯 판정(새로 만들기 허용) → 결과 없으면 종료.
4. 소분류 슬롯: 정해진 대분류 아래만 후보(새로 만들기 허용).
5. 보조 대분류 최대 2개(대표와 같은 이름 제외): **기존 주제에만 연결**(새로 만들기 금지).
6. 판정 기록 MySQL upsert(V089 재사용, `chunk_id="__document__"`, `mention_type="주제:대분류"/"주제:소분류"`), 문서↔주제 연결 통째로 교체.

### 4. 슬롯 판정 — 엔티티 판정과 같은 골격

| 순서 | 조건 | 결과 |
|------|------|------|
| 1 | 제안 이름이 비었거나 64자 초과 | 슬롯 건너뜀 |
| 2 | 같은 수준·같은 상위의 usable 주제(최대 30) 중 정규화 이름 정확 일치 | 연결(rule, 검토 없음) |
| 3 | 후보 0개 | 생성 허용이면 새 주제, 아니면 없음 |
| 4 | Jev 사용 가능 | 3구간. 보조 슬롯은 연결 구간만 쓰고 나머지는 없음 |
| 5 | Jev 불가·실패 | 보조 슬롯은 없음(LLM 안 부름), 대표 슬롯은 LLM 선택(high 아니면 검토 대기) |
| 6 | LLM 실패 | 새 주제 + 검토 대기 |

- Jev·LLM 문구는 주제용(`JEV_TOPIC_*`, `LLM_TOPIC_*`)이지만 판정자 클래스는 엔티티용 재사용.
- 판정 id `uuid5(document_id, slot)`(slot = major·minor·secondary0·secondary1) → 재분류해도 같은 id.
- Jev 연속 실패 수는 엔티티 판정과 같은 `ResolveRunState`를 공유.

### 5. 자동 주제와 검토

- 자동 생성 주제는 `status=pending, origin=auto`, 그 판정은 **항상 검토 대기**. 이름이 같은 retired 주제가 있으면(유일 키 충돌) 그 주제를 pending으로 되살린다.
- pending도 usable이라 다음 문서 분류·질문 주제 후보에 바로 들어간다.
- 승인: 새로 만든 판정이면 주제를 active로.
- 거절 + 대상: 그 판정의 문서↔주제 연결을 대상으로 옮김(이미 있으면 합치고 대표 여부 OR).
- 거절 + 대상 없음(연결 판정만): 언급 이름으로 새 주제(active, admin) — 소분류면 원래 상위를 따름, retired 동명 주제는 되살림.
- 옮긴 뒤 문서 수 0인 자동 주제는 retired. 이후 Neo4j topic_ids 재복사(실패는 경고 — 다음 잡이 다시 복사).

### 6. topic_ids 복사

`SET_DOCUMENT_TOPICS`: 문서의 모든 `Chunk.topic_ids`와 그 문서 근거의 모든 `RELATES`·`REFERS_TO.topic_ids`를 같은 목록으로 덮어쓴다.
복사 시점은 **잡 끝과 주제 검토 후**뿐이다. 잡 진행 중 새로 쓴 청크·관계에는 topic_ids가 없고, 잡이 예외로 failed면 복사 단계까지 가지 않는다.

## 다음에 적용하는 법

1. 주제를 탐색 경로(관계)로 쓰자는 제안은 이 설계가 피하려던 "문서 전체로 퍼짐"을 되살린다. 범위 필터로만 쓴다.
2. 주제 분류 프롬프트·로직을 바꿔도 **기존 문서는 rebuild 전까지 재분류되지 않는다**(resume은 기존 주제 유지).
3. 주제 원본은 MySQL이다. Neo4j topic_ids가 어긋나 보이면 MySQL `graph_document_topic`을 먼저 확인하고, 재복사는 검토 동작이나 다음 잡으로 일어난다.
4. 주제 이름에 업무 고유 용어를 하드코딩하지 않는다 — 주제 목록은 데이터(관리자 탭·자동 생성)다.

## 관련 문서

- [[overview]] · [[retrieval-path]] (질문 주제 판정·범위 필터) · [[entity-resolution]] · [[erd-graph-rag]]
