# Plan: retrieval-observability

> Feature: 질문별 검색 근거(뽑힌 문서) 기록 — general_chat 배선 + rewrite 쿼리 추적 + 스키마 확장 + 조회 API
> Created: 2026-07-09
> Status: Plan

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | 사용자 질문에 대해 벡터/하이브리드 검색이 어떤 문서(청크)를 뽑았는지 기록이 남지 않아 관측성이 없다. 특히 general_chat 경로는 tracker 미주입으로 완전한 사각지대이며, rewrite(multi_query)로 재작성된 쿼리는 어디에도 남지 않는다. |
| **Solution** | 기존 `ai_retrieval_source` + `RunTracker` 관측성 인프라를 general_chat 경로로 확장(ai_run 생성 + tracker 주입)하고, 실제 검색에 투입된 쿼리(재작성 포함)·검색 모드·BM25/벡터 개별 점수를 신규 컬럼(V046)으로 기록한 뒤, 메시지 기준 조회 API를 제공한다. |
| **Function UX Effect** | "이 질문에서 어떤 문서가 몇 점으로 뽑혔고, 실제로는 어떤 재작성 쿼리로 검색됐는지"를 API 한 번으로 확인 가능. 답변 품질 이슈 발생 시 검색 단계 원인 분석이 즉시 가능해진다. |
| **Core Value** | RAG 파이프라인의 핵심 블랙박스(검색 단계)를 데이터로 열어, 검색 품질 튜닝(threshold, RRF, rewrite 프롬프트)의 근거 데이터를 확보한다. |

---

## 1. 목적 (Why)

현재 "어떤 질문에서 어떤 문서가 검색됐는가"의 기록 상태:

| 경로 | 검색 근거 DB 기록 | 비고 |
|------|:---:|------|
| agent_run (빌더 커스텀 에이전트) | ✅ | `tool_factory.py`에서 tracker 주입 → `ai_retrieval_source` 저장 |
| **general_chat** | ❌ | `src/api/main.py` L1978 tool 생성 시 tracker/logger 미주입 |
| rewrite(multi_query) 재작성 쿼리 | ❌ | 어떤 재작성 쿼리로 검색됐는지 어디에도 안 남음 |

**세부 문제점**

1. **general_chat 사각지대**: 사용자 질문 대부분이 흐르는 general_chat에서 검색 결과가 응답 이벤트(`sources`)로만 나가고 DB에 저장되지 않는다. 대화가 끝나면 근거 추적 불가.
2. **rewrite 쿼리 미기록**: chat에서는 원 질문을 바로 검색하지 않고 rewrite(multi_query)로 쿼리를 재작성해 검색시키는 구조로 가는데, `ai_retrieval_source`에는 쿼리 자체가 없어 "재작성된 쿼리 → 뽑힌 문서" 연결이 끊긴다.
3. **스키마 정보 부족**: `ai_retrieval_source`에 통합 `score` 하나만 있고 BM25/벡터 개별 점수, 검색 모드(hybrid/routed/multi_query), 검색 실행 쿼리가 없어 튜닝 분석이 불가능하다.
4. **조회 수단 부재**: run_id 기준 상세 조회(`GET /agents/runs/{run_id}`)만 있고, "이 대화 메시지에서 뭐가 뽑혔나"로 접근하는 경로가 없다.

**전제 (이미 구축된 것 — 재사용)**

- `ai_retrieval_source` 테이블 (V021): run_id/tool_call_id FK, collection, document_id, chunk_id, score, rank_index, content_preview, metadata_json
- `RunTracker.record_retrieval()` + `InternalDocumentSearchTool._format_results`의 best-effort 기록 호출
- `ai_run.user_message_id → conversation_message(id)` FK — 질문(메시지)과 run 연결 고리
- LangSmith 트레이싱 (`langsmith_trace_id`/`run_url` 저장)

→ **신규 구축이 아니라 기존 관측성의 확장.**

---

## 2. 기능 범위 (Scope)

### In Scope

#### RETOBS-A: general_chat에 ai_run 라이프사이클 + tracker 배선

- general_chat 실행 시 `ai_run` 레코드 생성 (run open → complete/fail), `run_type` 구분값으로 general_chat 표시
- `ai_run.user_message_id`에 사용자 메시지 FK 연결 (질문 ↔ run ↔ 검색 근거 3단 연결 완성)
- `src/api/main.py`의 general_chat용 `InternalDocumentSearchTool` 생성부에 tracker/logger 주입
- agent_run 경로와 동일한 `RunTracker` 재사용 — 조회 방식 통일
- 기록 실패가 채팅 응답을 막지 않도록 best-effort 유지 (기존 `record_retrieval` 패턴 준수)

#### RETOBS-B: 검색 실행 쿼리(rewrite 포함) 기록

- `ai_retrieval_source`에 **실제 검색 엔진에 투입된 쿼리**(`search_query`) 저장
  - 단일 검색: 원 질문 그대로
  - multi_query(rewrite): **재작성된 쿼리별로** 각 hit에 해당 쿼리 기록 — "질문 1개 → 재작성 쿼리 N개 → 쿼리별 문서 M개" 구조가 그대로 남음
  - routed: 라우팅 검색에 투입된 쿼리
- `query_source` 컬럼으로 쿼리 출처 구분: `original` / `multi_query` / `routed`
- 원 질문은 `ai_run.user_message_id` → `conversation_message.content`로 역참조 (중복 저장 안 함)

#### RETOBS-C: ai_retrieval_source 스키마 확장 (V046)

- 신규 nullable 컬럼 추가 (기존 데이터/기록 로직 보존, 새 값만 채움):
  - `search_query` — 실제 검색에 투입된 쿼리 텍스트
  - `query_source` — original / multi_query / routed
  - `search_mode` — hybrid / routed / vector_only 등 검색 방식
  - `bm25_score`, `vector_score` — RRF 병합 전 개별 점수 (`HybridSearchResult`에 이미 존재, 버려지던 값)
  - `bm25_rank`, `vector_rank` — 개별 랭크
  - `fusion_source` — both / bm25_only / vector_only (`HybridSearchResult.source`)
- 기존 컬럼 변경/삭제 없음 — 순수 추가(additive)만

#### RETOBS-D: 메시지 기준 조회 API

- `GET /api/v1/conversations/messages/{message_id}/retrievals` (신설)
  - 해당 메시지에 연결된 run의 검색 근거 목록 반환: 검색 쿼리별 그룹 + 뽑힌 문서(chunk_id, document_id, collection, 점수들, rank, preview)
- 기존 `GET /agents/runs/{run_id}` 응답의 retrievals에 신규 컬럼 반영
- 본인 메시지만 조회 가능 (기존 인증/권한 패턴 준수)

### Out of Scope

- collection_search / wiki-first / hybrid 직접 API 경로 배선 (후속 기능으로 분리)
- 프론트엔드 화면 (메시지별 근거 표시 UI) — 조회 API까지만, UI는 후속
- 검색 품질 분석 대시보드 / 집계 리포트
- LangSmith 트레이싱 구조 변경 (기존 유지)
- 기존 `ai_retrieval_source` 과거 데이터 백필

---

## 3. 기술 의존성

| 모듈 | 출처 | 상태 |
|------|------|------|
| `ai_retrieval_source` / `ai_run` 테이블 | agent-run-observability (V021) | 구현됨 |
| `RunTracker.record_retrieval` | agent-run-observability | 구현됨 |
| `InternalDocumentSearchTool` 기록 훅 | `src/application/rag_agent/tools.py` `_format_results` | 구현됨 (tracker 주입 시 동작) |
| multi_query rewrite | multi-query-rewrite (`src/application/multi_query/`) | 구현됨 (tool opt-in) |
| `ai_run.user_message_id` FK | V021 | 구현됨 (general_chat에선 미사용) |
| `agent_run_router` 조회 API | agent-run-observability M4 | 구현됨 (확장 대상) |

외부 추가 라이브러리: 없음

---

## 4. 아키텍처 방향 (설계 단계에서 상세화)

### 변경 파일 후보

```
db/migration/
└── V046__alter_ai_retrieval_source_add_query_context.sql   # 신규

src/
├── api/
│   ├── main.py                          # general_chat tool 생성부 tracker 주입
│   └── routes/
│       └── conversation_router.py (또는 agent_run_router.py)  # 메시지 기준 조회 엔드포인트
├── application/
│   ├── general_chat/use_case.py         # ai_run open/complete + user_message_id 연결
│   ├── rag_agent/tools.py               # record_retrieval에 search_query/mode/개별점수 전달
│   └── multi_query/                     # 재작성 쿼리별 기록 전달
├── domain/agent_run(관련)/               # record_retrieval 시그니처 확장 (하위호환)
└── infrastructure/agent_builder/         # RunTracker.record_retrieval 확장
```

### 설계 원칙

1. **기존 경로 무변경**: agent_run 경로의 기존 기록 동작은 그대로, 신규 컬럼 값만 추가로 채움 (additive)
2. **best-effort**: 관측성 기록 실패는 WARNING 로그만 남기고 검색/응답 흐름을 절대 막지 않음 (기존 패턴 유지)
3. **레이어 준수**: 기록은 application(UseCase/tool)에서 트리거, 영속화는 infrastructure(RunTracker/Repository), 스키마 규칙은 domain
4. **로깅 규칙(LOG-001)**: request_id 전파, 시작/완료 INFO, 예외 ERROR+스택

### 주의점 (조사에서 확인된 리스크)

- general_chat은 `ai_run`을 여는 라이프사이클이 없음 → run open 위치/트랜잭션 세션 공유 설계 필요 (한 UseCase 안에서 repository별 다른 세션 금지 규칙 준수)
- multi_query는 쿼리별 검색이 병렬/순차 실행될 수 있음 → hit별로 자신을 만든 쿼리를 정확히 태깅해야 함 (배치 단위 기록 시 쿼리-hit 매핑 유실 주의)
- V046은 ALTER ADD COLUMN만 — FK 추가 없음이므로 collation 이슈(errno 3780) 해당 없음

---

## 5. 데이터 모델 초안 (V046)

```sql
-- V046__alter_ai_retrieval_source_add_query_context.sql
ALTER TABLE ai_retrieval_source
    ADD COLUMN search_query   TEXT NULL COMMENT '실제 검색 엔진에 투입된 쿼리(재작성 포함)',
    ADD COLUMN query_source   VARCHAR(20) NULL COMMENT 'original | multi_query | routed',
    ADD COLUMN search_mode    VARCHAR(20) NULL COMMENT 'hybrid | routed | vector_only 등',
    ADD COLUMN bm25_score     DECIMAL(10,6) NULL,
    ADD COLUMN vector_score   DECIMAL(10,6) NULL,
    ADD COLUMN bm25_rank      INT NULL,
    ADD COLUMN vector_rank    INT NULL,
    ADD COLUMN fusion_source  VARCHAR(20) NULL COMMENT 'both | bm25_only | vector_only';
```

- 전 컬럼 nullable → 기존 데이터·기존 기록 코드와 하위호환
- general_chat run 구분은 `ai_run`의 기존 run 유형 컬럼 활용(설계 시 확정; 컬럼 부재 시 V046에 포함)

---

## 6. 테스트 계획 (TDD)

| 테스트 | 검증 내용 |
|--------|-----------|
| `test_general_chat_run_tracking` | general_chat 실행 시 ai_run 생성 + user_message_id 연결 |
| `test_general_chat_retrieval_recorded` | general_chat 검색 시 ai_retrieval_source에 hit 저장 |
| `test_record_retrieval_query_context` | search_query/search_mode/개별 점수 컬럼 저장 |
| `test_multi_query_per_query_tagging` | 재작성 쿼리 N개 → hit별 자기 쿼리 태깅 정확성 |
| `test_record_retrieval_best_effort` | 기록 실패 시 응답 정상 반환 + WARNING 로그 |
| `test_message_retrievals_api` | 메시지 기준 조회 API 응답 스키마 + 권한(본인만) |
| `test_existing_agent_run_path_unchanged` | 기존 agent_run 경로 기록 회귀 없음 |

---

## 7. 완료 조건 (Definition of Done)

- [ ] general_chat에서 검색이 실행되면 `ai_retrieval_source`에 뽑힌 문서가 저장된다
- [ ] `ai_run.user_message_id`로 사용자 질문 메시지와 연결된다
- [ ] multi_query(rewrite) 사용 시 재작성 쿼리별로 어떤 문서가 뽑혔는지 구분 기록된다
- [ ] search_mode / BM25·벡터 개별 점수 / fusion_source가 저장된다
- [ ] 메시지 ID로 검색 근거를 조회하는 API가 동작한다 (본인 권한 검증 포함)
- [ ] 기록 실패가 채팅 응답을 막지 않는다 (best-effort)
- [ ] 기존 agent_run 경로 기록·기존 테스트 회귀 없음
- [ ] V046 마이그레이션이 기존 데이터에 무해하게 적용된다 (nullable additive)

---

## 8. 작업 순서

1. V046 마이그레이션 + SQLAlchemy 모델(`AiRetrievalSource`) 컬럼 추가
2. `RunTracker.record_retrieval` 시그니처 확장 (신규 필드 optional, 하위호환) — 테스트 먼저
3. `InternalDocumentSearchTool` 기록부에 쿼리/모드/개별 점수 전달 (hybrid → multi_query → routed 순)
4. general_chat use_case에 ai_run open/complete + user_message_id 연결 — 테스트 먼저
5. `src/api/main.py` general_chat tool 생성부 tracker/logger 주입
6. 메시지 기준 조회 API + 스키마 (interfaces) — 테스트 먼저
7. `GET /agents/runs/{run_id}` 응답에 신규 필드 반영
8. 회귀 확인 (기존 agent_run 관측성 테스트) + `/pdca analyze retrieval-observability`
