---
title: Graph RAG 실행 조건 — 3중 게이트·노출 단계·설정·관리자 API
status: approved
source_type: conversation
source_refs:
  - idt/src/domain/graph_rag/policies.py (RolloutPolicy, StageTransitionPolicy, FORCE_REASON_MIN_LEN=10)
  - idt/src/domain/graph_rag/value_objects.py (GraphRagSettings.__post_init__ 검증, defaults, effective_rejudge_model_id)
  - idt/src/domain/graph_rag/eval_evidence.py, idt/src/infrastructure/graph_rag/eval_evidence.py (general 전환 근거)
  - idt/src/application/rag_agent/tools.py (_supplemental_requested, 라우팅 경로 skip)
  - idt/src/application/agent_builder/supplemental_flag.py (strip_unexposed_graph_flag)
  - idt/src/application/agent_builder/create_agent_use_case.py, update_agent_use_case.py, fork_agent_use_case.py
  - idt/src/application/agent_builder/schemas.py (RagToolConfigRequest.use_graph — 커밋 eb91f95, PR #115)
  - idt/src/application/graph_rag/hooks.py (GraphExposure, capabilities_for)
  - idt/src/application/graph_rag/admin/stage_use_case.py, settings_use_case.py
  - idt/src/infrastructure/graph_rag/settings_reader.py (TTL 30초 캐시, 실패=닫힌 기본값)
  - idt/src/api/routes/admin_graph_rag_router.py, graph_rag_router.py
  - idt/src/api/routes/ragas_router.py (allow_supplemental, 비관리자 403), idt/src/api/main.py _run_agent_headless
  - idt/src/domain/ragas/policies.py (TARGET_METRICS — agent 대상 지표 3종)
  - idt/src/config.py (graph_backend·neo4j_*·graph_entity_embedding_*)
  - idt/db/migration/V086__create_graph_rag_setting.sql
  - idt_front/src/types/graphRag.ts, idt_front/src/pages/AdminGraphRagPage/
confidence: 0.85
version: 1
created: 2026-11-21
updated: 2026-11-27
verified_at: 49b0970
reviewer: 배상규
---

# Graph RAG 실행 조건 — 3중 게이트·노출 단계·설정·관리자 API

## 문제

그래프 검색은 에이전트 설정·호출 경로·전역 노출 단계가 모두 맞아야 실행된다. 하나라도 닫히면
조용히 기존 검색만 쓰기 때문에 "켰는데 안 돈다"를 추적하기 어렵다. 또 에이전트 저장 단계에서
플래그가 조용히 꺼지는 경로가 두 가지(비노출 정리, 요청 스키마 누락) 있다.

## 검증된 사실

### 1. 3중 게이트

| # | 조건 | 확인 위치 | 닫혔을 때 |
|---|------|-----------|-----------|
| 1 | 에이전트 RAG 도구 `tool_config.use_graph=True` | `RagToolConfig` → `ToolFactory` → `tools.py _supplemental_requested` | 보조 검색 미시작, **로그 없음** |
| 2 | 호출자 grant 존재 | 같음 | 같음 |
| 3 | 노출 단계가 호출자를 허용 | `GraphRetrievalSource.retrieve` → `RolloutPolicy.skip_reason` | `stage_off` / `grant_not_admin` (도구 info 로그 `Supplemental retrieval skipped`) |

`RolloutPolicy.skip_reason`

| stage | 관리자 grant | 일반 사용자 grant |
|-------|-------------|------------------|
| off | stage_off | stage_off |
| admin_only | 실행 | grant_not_admin |
| general | 실행 | 실행 |

추가로 실행 안 하는 경우: supplemental 슬롯 미등록(`not_wired` 로그), `use_routed_search`가 결과를 냄(`routed_path` 로그 — 라우팅 결과에는 결합하지 않음, 라우팅이 강등되면 단일/멀티쿼리 경로에서 결합됨).

### 2. 호출 경로별 grant

| 경로 | grant |
|------|-------|
| WS 대화, REST `POST .../{agent_id}/run`, SSE `GET` 스트림 | `SupplementalGrant.for_role(auth_ctx.role)` — **일반 사용자도 받는다**(`caller_is_admin=False`) |
| 웹훅·백그라운드 워커·스케줄·승인 결정/실행 스케줄러 | 없음 (계약 테스트 C3) |
| RAGAS 배치 평가(agent 대상) | 요청 `allow_supplemental=True`일 때만 `SupplementalGrant(caller_is_admin=True)`. 비관리자가 true → 403, agent 대상이 아니면 거절 |
| 관리자 검색 테스트 | 항상 관리자 grant |

코드 기준 동작: Plan FR-20은 "admin_only에서는 admin인 대화 라우트만 grant를 넘김"이었지만, 코드는 모든
대화 사용자에게 grant를 만들고 **막는 것은 조건 3(단계 정책)** 이다. general로 바꾸는 순간 일반 사용자 대화에서도 실행된다.

### 3. 저장 시 `use_graph`가 꺼지는 두 경로

1. **비노출 정리** — `strip_unexposed_graph_flag`: `internal_document_search` 워커의 `use_graph=True`를, `exposure.is_visible("graph_rag", caller_is_admin)`이 거짓이면 `False`로 바꾼 사본을 돌려준다(오류 없음, info 로그).
   - 생성·수정: `viewer_role == admin`으로 판정. 포크: **항상 `caller_is_admin=False`** → 관리자가 포크해도 꺼진다.
   - 실행 시 3중 게이트와 이중 방어. 관리자가 켜 저장한 에이전트를 일반 사용자가 돌려도 admin_only면 조건 3에서 막힌다.
2. **요청 스키마 누락**(PR #115로 수정됨) — `RagToolConfigRequest`에 `use_graph` 필드가 없어 빌더 토글 값이 pydantic 단계에서 조용히 버려졌다(관리자 저장 포함). 도메인 `RagToolConfig`에 필드를 추가해도 **요청 스키마에 같은 필드가 없으면 저장되지 않는다**.

### 4. 설정 두 층

| 층 | 위치 | 내용 |
|----|------|------|
| 접속·인프라 | 환경변수(`config.py`) | `graph_backend`(기본 `off`), `neo4j_uri/user/password/database`, 풀 10, 연결 타임아웃 5s, `graph_entity_embedding_model`(없으면 `openai_embedding_model`), `graph_entity_embedding_dimensions`(512). Jev 판정 타임아웃은 공용 `judgment_timeout_seconds` |
| 운영값 | MySQL `graph_rag_setting` 단일 행(V086, 고정 id) | 아래 |

| 필드 | 기본 | 범위 | 의미 |
|------|------|------|------|
| rollout_stage | off | off·admin_only·general | PUT 불가, `/stage`로만 변경 |
| extraction_enabled | false | | 업로드 후 **자동** 추출. 관리자 수동 실행에는 무관 |
| jev_enabled | false | | Jev 사용. `JUDGMENT_BACKEND` 미조립이면 켜도 무효 |
| link_threshold / new_threshold | 0.8 / 0.4 | 0 < new < link ≤ 1 | 판정 3구간 경계. 질문 주제 판정에도 link 사용 |
| extraction_llm_model_id | null | llm_model.id | 추출·주제 제안 모델. **없으면 자동·수동 추출 모두 막힘** |
| rejudge_llm_model_id | null | | 재판정·대체·질문 주제 LLM. null이면 추출 모델 |
| concurrency | 3 | 1~8 | 잡 안 청크 추출 동시 수 |
| max_llm_calls_per_doc | 300 | 1~2000 | 문서당 LLM 호출 상한 → 닿으면 partial |
| candidate_top_k | 5 | 1~8 | 판정 후보 수(Jev 라벨 k+1) |
| max_hops | 2 | 1~3 | 검색 탐색 단계 |
| graph_rrf_weight | 0.5 | 0~1 | 결합 시 그래프 목록 가중치 |
| retrieval_timeout_ms | 800 | 100~5000 | 그래프 검색 전체 상한, 질문 주제 판정은 이 중 50% |
| entity_types / relation_types | 10개 / 9개 | 1~30개, 각 1~32자, 중복 금지, '기타' 필수 | 허용 타입. **데이터이지 코드 상수가 아님**(코드 기본 목록은 행 없을 때 안전값) |

- 검증 단일 출처는 `GraphRagSettings.__post_init__`. 기본값은 `defaults()`와 V086 시드가 같다.
- DB 단계 값이 알 수 없는 문자열이면 off로 읽는다. 행이 없으면 닫힌 기본값으로 행을 만든다.
- `CachedGraphSettingsReader`: 앱 수명 싱글턴, TTL 30초, `asyncio.Lock`으로 동시 로드 1회, **읽기 실패는 닫힌 기본값(stage off)을 돌려주고 캐시하지 않음**. PUT·단계 변경 시 `invalidate()`.
  → DB가 잠깐 실패하면 그 순간 그래프 기능이 꺼진 것처럼 동작한다.

### 5. 단계 전환

- 같은 단계로의 전환은 no-op. off·admin_only로의 전환, general에서 내려가기는 조건 없음.
- general 진입: RAGAS 근거 검증 통과 **또는** 강제 사유(공백 제거 후 10자 이상). 둘 다 아니면 409 `GRAPH_STAGE_EVAL_REQUIRED`. 코드 기준 동작: Plan은 "경고"였으나 코드는 **차단**.
- 이력 INSERT(`graph_rag_stage_change`)와 설정 UPDATE는 같은 요청 세션. 근거로 통과하면 사유는 기록하지 않는다.
- 근거 정책(`EvalEvidencePolicy`)은 두 `evaluation_run`에 대해 순서대로: 둘 다 존재 → 서로 다른 id → 둘 다 completed → 둘 다 target_type agent → 같은 에이전트 → 같은 testset → 기준 실행 `allow_supplemental` 거짓 → 비교 실행 참. `testset_id`·`allow_supplemental`은 `evaluation_run.config` JSON에서 읽고 없으면 끔으로 본다. 거절 사유는 로그로만.
- **점수는 비교하지 않는다** — 켬 쪽 점수가 낮아도 근거로 인정. 점수 판단은 관리자 몫.
- **지표 함정**: 근거는 agent 대상 실행만 인정하는데, agent 대상 RAGAS 허용 지표는 `answer_relevancy`·`answer_correctness`·`answer_similarity` 3개뿐이다(`TARGET_METRICS["agent"]`). `context_recall`·`faithfulness`는 agent 대상에서 거절된다. 그래프 끔/켬 비교 지표는 이 3개 안에서 고른다.

### 6. 노출 판단 API·관리자 API·프론트 탭

- `GET /api/v1/graph-rag/capabilities`: 비허용 `{"visible": false}`, 일반 사용자 허용 `{"visible": true}`(stage 없음), 관리자 `{"visible": true, "stage": ...}`. 모듈 미등록이면 라우터가 없어 404 → 프론트는 숨김 처리. 빌더의 그래프 토글(`RagConfigPanel` 고급 설정)은 visible일 때만 그린다.
- 관리자 API(`/api/v1/admin/graph-rag`, 전부 `require_role("admin")`, 오류 `{"detail": {"code","message"}}`):

| 경로 | stage off일 때 | 비고 |
|------|:--------------:|------|
| GET·PUT `/settings`, POST `/stage`, GET `/stage-history`, GET `/health`, GET `/kbs/{kb_id}/documents`, GET `/jobs/{job_id}` | 동작 | health는 연결 실패도 200 + error 필드 |
| POST `/documents/{id}/extract` (202) | 409 `GRAPH_STAGE_OFF` | 상세 오류는 [[extraction-pipeline]] |
| `/review`·approve·reject, `/topics` GET·POST·PATCH | 409 | |
| `/entities`, `/entities/{id}`, POST `/search-test`, GET `/integrity` | 409 | Neo4j 없으면 503 |

  코드 기준 동작: Design은 "off에서 허용은 설정·health뿐"이었지만 코드는 단계 변경·이력·KB 문서 목록·잡 상세도 허용한다.
- 프론트 `AdminGraphRagPage` 6탭: 설정 · 추출(정합성 점검 버튼 포함) · 엔티티·관계 · 주제 · 검색 테스트 · 검토 큐. 단계 변경·health는 헤더(`StageChangeDialog`).

## 다음에 적용하는 법

1. **"그래프가 안 돈다" 진단 순서**: 에이전트 `tool_config.use_graph` 실제 저장값(DB) → 호출 경로가 grant를 넘기는 경로인가(웹훅·스케줄은 영원히 안 돈다) → stage와 호출자 역할 → 이후는 [[retrieval-path]]의 skip_reason. 조건 1·2는 로그가 없으니 DB·경로로 확인한다.
2. **RagToolConfig에 필드를 추가할 때** `application/agent_builder/schemas.py`의 `RagToolConfigRequest`에도 같은 필드를 넣고, 저장 후 `tool_config`에 남는지 테스트한다(PR #115 사례).
3. **general 전환 준비**: 같은 에이전트·같은 testset으로 `allow_supplemental` 끔/켬 RAGAS 2회를 agent 대상, 위 3개 지표로 돌린다. 점수 비교는 사람이 한다.
4. **새 운영값 추가** 시 `GraphRagSettings` 검증·`defaults()`·V 시드·관리자 PUT 스키마를 함께 바꾸고, 소비 지점을 docstring에 적는다([[config-single-source-at-consumption]]).

## 관련 문서

- [[overview]] · [[extension-hooks-boundary]] · [[retrieval-path]] · [[erd-evaluation]] (evaluation_run.config)
