---
title: Graph RAG 개요 — 전체 흐름·문서 지도·용어집
status: approved
source_type: conversation
source_refs:
  - idt/src/domain/extension_hooks/ (registry.py, ports.py, events.py)
  - idt/src/api/graph_rag_di.py (wire_graph_rag, start_graph_rag)
  - idt/src/application/graph_rag/ (hooks.py, extraction/, resolution/, topic/, retrieval/, admin/)
  - idt/src/application/rag_agent/tools.py (보조 검색 결합)
  - docs/02-design/features/graph-rag-foundation.design.md
  - docs/04-report/graph-rag-foundation.report.md
  - 커밋 7b4113d (PR #113 머지), 87d4d3c (PR #115 머지)
confidence: 0.85
version: 1
created: 2026-11-21
updated: 2026-11-27
verified_at: 49b0970
reviewer: 배상규
---

# Graph RAG 개요 — 전체 흐름·문서 지도·용어집

## 문제

graph-rag-foundation은 `domain/extension_hooks`·`application/graph_rag`·`infrastructure/graph_rag`·
`api/graph_rag_di.py`에 걸쳐 60개 가까운 파일로 들어왔다. 코어(업로드·삭제·RAG 도구)에는
그래프 용어가 거의 없어서, 코어 코드만 읽으면 그래프가 어디에 붙는지 보이지 않는다.
세부 문서로 들어가기 전 전체 그림과 용어를 여기서 잡는다.

## 검증된 사실

### 1. 전체 흐름 (세 갈래)

```
[적재 — 업로드 후 비동기]
KB 업로드 완료 → hooks.post_ingest(GraphIngestHook) → 조건 통과 시 잡 INSERT(pending) + create_task
  → ExtractGraphUseCase: ES에서 document_id 청크 재조회 → 문서 주제 분류(잡당 1회)
  → 청크마다 규칙 추출 + LLM 구조화 추출(동시) → EntityResolver 판정(잠금으로 직렬)
  → MySQL 판정 기록 upsert → Neo4j 청크 1개분 한 트랜잭션 쓰기
  → 잡 끝: 문서 Chunk·관계에 topic_ids 복사 → completed / partial / failed

[검색 — 대화 중 RAG 도구 호출]
InternalDocumentSearchTool → (use_graph AND grant AND supplemental 등록) 이면
  기존 검색과 동시에 GraphRetrievalSource.retrieve 시작
  → RolloutPolicy(stage × caller_is_admin) → 질문 주제 판정 ∥ 씨앗 후보 연결
  → 범위 우선 씨앗 5개 → 최대 N단계 경로 탐색(허브 경유 금지) → 근거 청크 점수
  → ES ids + 도구와 같은 권한 필터로 재조회 → 도구 최종 결과에 가중 RRF 결합
  실패·시간 초과는 예외 대신 skip_reason → 기존 결과만 사용

[노출 단계 — 관리자]
off ⇄ admin_only ⇄ general  (general 진입만 RAGAS 끔/켬 근거 2건 또는 강제 사유 10자+)
```

### 2. 주제별 문서 지도

| 주제 | 문서 |
|------|------|
| 코어가 그래프를 모르는 구조(확장 훅 4슬롯·조립·계약 테스트) | [[extension-hooks-boundary]] |
| 언제 그래프 검색이 실행되나(3중 게이트·노출 단계·설정·관리자 API) | [[execution-gates-and-rollout]] |
| 추출 잡(시작 조건·순서·규칙/LLM 추출·쓰기 순서·상태) | [[extraction-pipeline]] |
| 언급↔엔티티 동일성 판정(Jev 3구간·LLM·별칭·검토 큐) | [[entity-resolution]] |
| 문서 주제 분류와 검색 범위 | [[topic-classification]] |
| 그래프 검색 경로(씨앗·경로·점수·RRF·타임아웃·skip_reason) | [[retrieval-path]] |
| 저장소 스키마(MySQL V086~V091, Neo4j)와 삭제 훅 | [[erd-graph-rag]] |
| 장애 동작과 로컬 운영 함정 | [[failure-and-ops]] |

### 3. 용어집

| 용어 | 뜻 |
|------|----|
| 확장 훅(ExtensionHooks) | 코어가 아는 유일한 연결점. 슬롯 4개(post_ingest, deletion, supplemental, exposure)를 가진 앱 수명 레지스트리 |
| 보조 검색(supplemental) | 도구의 기존 검색 결과에 RRF로 한 번 더 합치는 추가 목록. 그래프 검색이 이 자리를 쓴다 |
| grant(`SupplementalGrant`) | 실행별 "보조 검색 허용" 표시. 객체가 있으면 opt-in, `caller_is_admin`을 담는다 |
| 노출 단계(rollout_stage) | off·admin_only·general. 누구에게 그래프 기능을 열지 정하는 전역 값 |
| 3중 게이트 | `use_graph` AND grant AND 노출 단계. 셋 다 열려야 실행 |
| 추출 단위 | 추출에 쓰는 청크. parent가 있으면 parent만, 없으면 그 청크. 요약 청크 제외 |
| 언급(Mention) | 한 청크에서 뽑은 엔티티 후보(이름·타입·설명) |
| 엔티티(Entity) | 판정을 거쳐 그래프에 저장된 개념 노드. 여러 언급이 하나에 연결된다 |
| 정규화 키 | NFKC → 공백 정리 → 양끝 구두점·괄호 제거 → casefold. 값은 `{chunk_id}::이름`, 조문은 `{document_id}::제N조` |
| 별칭(Alias) | 다른 표기로 기존 엔티티에 연결될 때 남기는 정규화 키 노드 |
| 값 엔티티(리터럴) | 숫자·단위를 지우면 2자 이하만 남는 이름. 청크 밖과 합치지 않는다 |
| 3구간 | Jev 후보 최대 확률 p\*로 나누는 auto_link(≥link)·auto_new(<new)·rejudge(사이) |
| 재판정(rejudge) / 대체 판정(fallback) | Jev 가운데 구간을 LLM이 다시 판정(항상 검토 대기) / Jev를 못 쓸 때 LLM 판정(high가 아니면 검토 대기) |
| Jev | `JudgmentPort` 뒤의 판정 모델. `ChoiceQuestion`에 라벨별 확률을 돌려준다 |
| 주제(Topic) / 범위(QueryScope) | 문서 분류용 2단계 목록(대분류>소분류) / 질문 주제 판정 결과. 씨앗·경로·근거 청크를 그 주제로 좁힌다 |
| 씨앗(seed) / 허브 | 경로 탐색 시작 엔티티(최대 5) / 관계 15개 초과 엔티티. 경로 중간 노드가 될 수 없다 |
| 근거 청크 | 관계의 `evidence_chunk_id`, 또는 씨앗이 언급된 청크 |
| skip_reason | 그래프 검색을 실행하지 않았거나 결과를 버린 이유 |
| resume / rebuild | 추출 모드. resume은 같은 추출기 버전으로 끝난 청크를 건너뜀, rebuild는 문서 그래프를 지우고 처음부터 |
| 추출기 버전 | `EXTRACTOR_VERSION`(현재 `"v3"`). 추출 규칙이 바뀌면 올린다 |

## 다음에 적용하는 법

1. 그래프 관련 작업은 이 문서의 지도에서 해당 주제 문서를 먼저 연다. 코어 파일에서 그래프 동작을 찾지 않는다.
2. "그래프 검색이 안 돈다"는 먼저 [[execution-gates-and-rollout]]의 3중 게이트, 다음 [[retrieval-path]]의 skip_reason 순으로 본다.
3. 줄 번호를 인용할 때는 `verified_at` 이후 코드가 바뀌었는지 `git diff 49b0970..HEAD -- idt/src/application/graph_rag` 로 확인한다.

## 관련 문서

- 상위 조감도: [[architecture-overview]] §2(f)
- 같은 이음매 계열 선례: [[detachable-module-seam]]
