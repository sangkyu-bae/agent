---
title: Graph RAG 추출 파이프라인 — 잡 시작 조건·실행 순서·규칙/LLM 추출·쓰기 순서
status: approved
source_type: conversation
source_refs:
  - idt/src/application/graph_rag/hooks.py (GraphIngestHook.on_document_ingested 시작 조건)
  - idt/src/application/graph_rag/admin/jobs_use_case.py (수동 trigger 검사 순서)
  - idt/src/application/graph_rag/extraction/launcher.py (_running_docs, create_task)
  - idt/src/application/graph_rag/extraction/use_case.py (run, _execute, _process, _extract, _write, _relations, _final_status)
  - idt/src/infrastructure/graph_rag/es_chunk_reader.py (document_id term 필터, MAX_CHUNKS_PER_DOCUMENT=5000)
  - idt/src/infrastructure/graph_rag/job_store.py (find_active, fail_interrupted)
  - idt/src/domain/graph_rag/extraction.py (ExtractionUnitPolicy, EvidencePolicy, DocumentEligibilityPolicy, LiteralValuePolicy, NameNormalizer, EXTRACTOR_VERSION, 결정적 ID)
  - idt/src/infrastructure/graph_rag/extract/rule_extractor.py, llm_extractor.py (MAX_INPUT_CHARS=12000), prompts.py
  - idt/src/infrastructure/graph_rag/decision_store.py (재실행 upsert 시 검토 결과 보존)
  - docs/02-design/features/graph-rag-foundation.design.md (M3-1 parent 단위, M3-8)
confidence: 0.85
version: 1
created: 2026-11-21
updated: 2026-11-27
verified_at: 49b0970
reviewer: 배상규
---

# Graph RAG 추출 파이프라인

## 문제

업로드는 추출을 기다리지 않고, 추출 잡은 업로드 결과가 아니라 ES를 다시 읽는다. 잡은 외부 큐 없이
인프로세스 태스크로 돈다. 그래서 "추출했는데 0건", "실행 버튼이 409", "partial" 같은 현상의 원인이
업로드 코드나 잡 코드 한쪽만 봐서는 보이지 않는다.

## 검증된 사실

### 1. 시작 조건

**자동(업로드 훅)** — 아래 중 하나라도면 아무것도 안 함(로그 없음):
stage=off · `extraction_enabled=false` · 추출 모델 없음 · 업로드 status=`failed` · `chunk_count ≤ 0` ·
파일명이 `.xlsx/.xls/.csv`(`DocumentEligibilityPolicy` — 표 행이 값 자체를 엔티티로 만들어 품질 저하, 표 분석은 엑셀 기능 몫).
통과하면 `mode=resume, trigger=upload`. **자동 경로는 진행 중 잡을 확인하지 않는다.**

**수동(관리자 `POST /documents/{id}/extract`)** — 검사 순서:

| 순서 | 검사 | 오류 |
|------|------|------|
| 1 | stage=off | 409 `GRAPH_STAGE_OFF` |
| 2 | 추출 모델 없음 | 422 `GRAPH_EXTRACTION_MODEL_MISSING` |
| 3 | 그래프 저장소 없음 | 503 `GRAPH_BACKEND_UNAVAILABLE` |
| 4 | 문서 메타 없음 | 404 |
| 5 | 엑셀·CSV | 422 `GRAPH_UNSUPPORTED_DOCUMENT` |
| 6 | MySQL에 같은 문서 pending·processing 잡 있음 **또는** 이 프로세스에서 실행 중 | 409 `GRAPH_JOB_BUSY` |

수동 경로는 `extraction_enabled`를 보지 않는다(자동 추출을 꺼도 관리자는 실행 가능).

**런처**: 잡 행 `pending` INSERT → `_running_docs`에 문서 id → `asyncio.create_task`(태스크 참조 보관해 GC 방지).
업로드 응답은 잡 INSERT까지만 기다린다. 앱 수명 싱글턴이고 외부 큐가 없다 — [[db-queue-inprocess-worker]]의 큐 테이블을 쓰지 않는 별도 구조다.

### 2. 실행 순서 (`ExtractGraphUseCase`)

1. 잡 조회 → 설정 → 사전 조건(stage off면 `stage_off`, 모델 없으면 failed 마감).
2. **ES에서 청크 → 추출 단위**.
3. rebuild면 Neo4j 문서 그래프 삭제, resume이면 같은 추출기 버전으로 이미 저장된 청크 id 조회. ← **Neo4j 첫 호출 지점**
4. 처리할 단위 = 전체 − 완료. 잡 `processing`, `total_chunks` = 전체 단위 수.
5. 문서 주제 분류(잡당 1회, [[topic-classification]]).
6. 단위별 처리: `asyncio.gather` + `Semaphore(concurrency)`.
7. 주제 id를 문서 Chunk·관계에 복사.
8. 최종 상태 마감.

`_execute` 전체가 예외면 failed + 메시지 앞 500자, **카운터는 0으로 덮인다**.

최종 상태: 처리할 단위가 있고 전부 실패 → failed(`all chunks failed`) / 호출 상한 도달 → partial / 일부 실패 → partial(`N chunks failed`) / 그 외 → completed. **처리할 단위 0개도 completed.**

### 3. ES에서 청크 읽기·추출 단위

- 업로드 결과가 청크 목록을 주지 않으므로 ES를 `document_id` term 필터로 다시 읽는다(최대 5,000건). **Qdrant가 아니라 ES다.**
- `ExtractionUnitPolicy.select`: `section_summary`·`document_summary`·빈 본문 제외 → parent가 하나라도 있으면 child 제외(parent만) → `chunk_index` 정렬.
- parent 단위인 이유: 문맥이 넓고 LLM 호출 수가 적다(Design M3-1). 그래서 그래프 근거 `chunk_id`는 parent id이고, 하이브리드 결과의 child id와 다를 수 있다.

### 4. 단위별 처리 — 추출은 동시, 판정·쓰기는 직렬

```
async with semaphore:
    if llm_calls >= max_llm_calls_per_doc: budget_hit = True; return   # 건너뜀(실패로 안 셈)
    result = _extract(unit)        # 규칙 → LLM. 예외면 failed_chunks+1
async with state.lock:             # 같은 새 엔티티를 두 청크가 동시에 만드는 경합 방지
    _write(...)                    # 예외면 failed_chunks+1
    processed_chunks += 1; save_progress(...)   # 청크마다 카운터 저장
```

- `llm_calls`에는 추출·판정 LLM·주제 제안/판정 LLM이 모두 들어가고, `judge_calls`는 Jev 호출 수다.
- 상한은 추출 호출 전 1회 예약 방식이라 대체로 지켜지지만 판정 LLM 호출은 `_write`에서 따로 더해지므로 최종 합계는 상한을 넘을 수 있다.
- `_extract`는 규칙 → LLM 순으로 실행하고 언급은 **LLM 것을 앞에** 둔다. 판정기가 정규화 키 중복을 앞쪽 우선으로 제거하므로 같은 이름이면 LLM이 붙인 타입이 남는다.

### 5. 규칙 추출(조문 참조, LLM 없음)

- 조문 `제\s*N\s*조(의M)?`, 참조 대상 조문|`별표 N`|`부칙`, 조문 머리 = 줄 첫머리 조문 + 선택 `(제목)`(1~40자).
- 조문 엔티티 키는 **문서 단위** `"{document_id}::제N조"`(별표·부칙도 동일) — 다른 문서의 같은 번호와 섞이지 않는다. 표시 이름은 "제N조".
- 머리에 제목이 있으면 제목을 `용어` 언급으로 추가 + `조문 -[정의]-> 제목`(RELATES).
- 본문 속 참조는 그 위치 앞의 마지막 조문 머리를 소유자로 `REFERS_TO`. 소유자 없음·자기 참조·중복은 버림. 근거는 매치 앞뒤 20자.
- LLM 프롬프트는 조문 번호를 엔티티로 뽑지 말라고 지시한다(규칙 추출과 중복 방지).

### 6. LLM 구조화 추출

- 모델 `extraction_llm_model_id`(모델 id별 캐시), temperature 0, `with_structured_output`. 입력은 청크 앞 12,000자. 섹션 요약 잡과 같은 `LLMFactory`이며 PII 가드 미적용.
- 출력 `entities[{name,type,description}]`, `relations[{source,target,type,evidence}]`.
- 후처리: 타입이 설정 목록 밖이면 '기타', 빈 이름 버림, 관계 끝점이 이 청크 엔티티에 없으면 버림. 근거 검증은 여기서 안 하고 유스케이스 한 곳에서.
- 프롬프트 요점: 문서에 실제로 나온 대상만·표기 그대로·evidence는 원문 그대로·조문 번호 제외·방향 규칙(개념→값·기준, 상위→하위, 규정·요건→적용 대상).

### 7. 값(리터럴) 엔티티

`LiteralValuePolicy`: 숫자가 있고 `제N조`로 시작하지 않으며, 단위(`%p, bp, 억원, 만원, 천원, 개월, 개년, 시간, %원억만천년월일주배건명회분초`)와 숫자·공백·구두점을 지운 나머지가 **2자 이하**면 값.
예: "연 4.2%" → 값, "감정가의 60%" → 값 아님(문맥 있는 기준).
값이면 저장 키가 `"{chunk_id}::{정규화 이름}"`, 후보 검색·이름 임베딩 없이 항상 새 엔티티 — 이름만으로 다른 문서와 합쳐져 잘못된 경로가 생기는 것을 막는다. 타입 이름이 아니라 이름 모양으로 판단(일반화 원칙).

### 8. 쓰기 순서: 판정 → 판정 기록(MySQL) → 그래프(Neo4j)

1. `EntityResolver.resolve_chunk`([[entity-resolution]]).
2. 관계 변환: 끝점을 판정 결과에서 찾고(없으면 정규화 재조회), 없거나 같은 엔티티면 버림. `EvidencePolicy.is_grounded` — 근거가 공백 정규화 후 **4자 이상**이고 청크 원문에 부분 문자열로 있어야 함. 타입 밖이면 '기타'.
3. **판정 기록을 MySQL에 먼저 upsert** — Neo4j 쓰기가 실패해도 무엇을 판정했는지 감사 가능.
4. Neo4j에 청크 1개분을 **한 트랜잭션**으로(실패 시 그 청크 전체 롤백, 판정 기록은 남음).
5. 카운터: `entities_linked` = 언급 수 − 새 엔티티 수(같은 잡에서 앞서 만든 엔티티로의 연결 포함).

코드 기준 동작: Design은 "근거 검증 후 판정"이었지만 코드는 판정을 먼저 하고 관계 변환 단계에서 근거를 검증한다.

결정적 ID — 판정 `uuid5("decision:{chunk_id}:{lookup_key}:{type}")`, 관계 `uuid5("relation:{chunk_id}:{source_entity_id}:{kind}:{type}:{target_entity_id}")`, 주제 판정 `uuid5("topic:{document_id}:{slot}")`, 엔티티는 새로 만들 때만 uuid4.
재실행 시 같은 판정 id면 MySQL 행을 덮어쓰되, **이미 승인·거절된 행은 검토 결과와 연결 엔티티를 유지**한다.
resume 판단은 `Chunk.extractor_version == EXTRACTOR_VERSION("v3")` — 버전을 올리면 resume도 이전 버전 청크를 다시 추출한다.

### 9. 함정·주의 (실측 확인)

- **ES에 청크가 없는 문서**(ES 색인 이전의 옛 업로드 등)는 추출해도 `total_chunks 0`으로 **completed**가 된다. 오류가 아니므로 잡 상태만 보면 성공처럼 보인다.
- **추출을 띄운 프로세스가 죽으면** pending/processing 잡이 MySQL에 남고, 서버 재기동 정리(`fail_interrupted` → `interrupted`) 전까지 같은 문서 수동 추출이 `GRAPH_JOB_BUSY`(409)로 막힌다.
- **표 머리글**('구분', '합계', '비중' 등)이 `용어` 엔티티로 추출되는 경향이 있다. 표가 많은 문서는 엔티티 목록·허브 후보를 확인한다.

## 다음에 적용하는 법

1. "추출 completed인데 그래프가 비었다" → 먼저 ES에 해당 `document_id` 청크가 있는지 확인한다. 없으면 문서를 다시 업로드(ES 색인)해야 한다.
2. "실행이 409 BUSY" → 진행 중 잡이 정말 도는지(`/jobs/{id}` 카운터 변화) 확인하고, 멈춘 고아 잡이면 서버 재기동으로 정리한 뒤 resume.
3. 추출 규칙·프롬프트를 바꾸면 `EXTRACTOR_VERSION`을 올린다(안 올리면 resume이 옛 결과를 건너뛰어 반영 안 됨).
4. 단계 순서(판정 기록 → Neo4j)와 판정·쓰기 직렬 잠금은 감사·경합 방지 계약이다. 성능 때문에 병렬화하려면 엔티티 생성 경합 대책부터 설계한다.

## 관련 문서

- [[overview]] · [[entity-resolution]] · [[topic-classification]] · [[erd-graph-rag]] · [[failure-and-ops]]
