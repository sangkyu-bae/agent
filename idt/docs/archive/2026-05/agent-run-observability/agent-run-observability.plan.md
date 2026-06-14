# Plan: agent-run-observability

> Feature: Agent Run 운영 관측성 (Run/Step/Tool/Retrieval 영속화)
> Created: 2026-05-18
> Status: Plan
> Task ID: AGENT-OBS-001

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | 현재 LangSmith trace에만 의존하고 우리 DB에는 대화 텍스트(`conversation_message`)만 저장됨. 운영팀이 "이 답변이 어떤 툴로 만들어졌는지, 토큰을 얼마나 썼는지(사용자별·LLM별), RAG 근거 문서가 무엇인지, 왜 실패했는지"를 우리 시스템에서 추적할 수 없다. 특히 Supervisor 패턴에서 **한 run이 여러 LLM(supervisor/worker/summarizer/tool 내부)**을 호출하지만 모델별 분해가 불가하다. LangSmith는 외부 SaaS라 민감정보 흐름·비용·UI 노출 한계가 있다. |
| **Solution** | `ai_run` / `ai_run_step` / `ai_tool_call` / `ai_retrieval_source` / `ai_llm_call` **5개** 신규 테이블 추가. `ai_llm_call`은 실제 LLM API 호출 1건 단위로 `llm_model_id`·provider·토큰·비용을 기록하여 **사용자별·LLM별 토큰/비용 집계**를 SQL 한 줄로 가능하게 한다. 기존 `conversation_message`는 그대로 두고 FK로 연결. `langsmith_trace_id`를 저장해 운영 화면 → LangSmith 점프 지원. |
| **Function / UX Effect** | (1) 어드민 대시보드에서 run별 상태/소요시간/툴 히스토리, (2) **사용자별 토큰·비용 집계 화면** (마이페이지/관리자), (3) **LLM 모델별 사용량·비용 집계** (예: 이번달 gpt-4o 1.2M tok / claude 800K tok), (4) 답변 근거 chunk를 사용자 UI 노출, (5) LangSmith trace 원클릭 점프, (6) 실패 run 재현 및 사후 분석. |
| **Core Value** | **운영 책임이 LangSmith 의존에서 우리 DB로 이전.** "서비스가 책임지는 업무 원장"이 확립되어, 감사·과금·품질평가·디버깅의 단일 진실 공급원(SSoT)이 만들어진다. **사용자별 청구·LLM별 비용 통제**가 가능해져 SaaS화 / 부서 차지백 / 이상 호출 탐지의 토대가 된다. |

---

## 1. 목적 (Why)

### 1-1. 현재 한계

| 현재 상태 | 한계 |
|----------|------|
| `conversation_message`만 저장 | 질문/답변 텍스트는 있으나 "어떤 워커가 어떤 툴을 호출했는지" 알 수 없음 |
| `SupervisorState.token_usage` 인메모리만 | run 종료 시 폐기, 비용 분석 불가 |
| **사용자별 토큰 집계 불가** | `conversation_message.user_id`는 있으나 토큰 정보가 없음. 마이페이지/관리자에서 "이 사용자가 이번달 얼마 썼나" 답 못함 |
| **LLM 모델별 토큰 집계 불가** | Supervisor 패턴에서 한 run에 여러 LLM(supervisor/worker/summarizer/툴 내부)이 호출되지만 식별 불가. "gpt-4o vs claude 사용량 비교" 불가 |
| **LLM 호출 단위 추적 없음** | 비용 청구·이상 호출 탐지의 기본 단위가 없음 |
| `RunAgentResponse.tools_used` 응답에만 포함 | DB 저장 X, 과거 run 조회 불가 |
| Run 상태 추적 테이블 없음 | RUNNING/SUCCESS/FAILED 구분 불가, 실패 원인 추적 어려움 |
| RAG 검색 근거 저장 안됨 | "이 답변이 어떤 chunk를 봤는지" 불명, 환각 추적 곤란 |
| LangSmith trace_id 미저장 | 어드민 화면에서 LangSmith로 점프 불가, 역추적 수동 |

### 1-2. 운영 니즈

- 금융/내부 정책 도메인 → 답변 신뢰성·감사 요구가 높음
- LangSmith는 외부 SaaS → 민감정보 송신 제한·비용 부담
- 어드민 페이지에서 "왜 이 답변이 나왔나"를 우리 데이터로 즉시 보여줘야 함
- 토큰 비용·이상 호출 탐지의 기반 데이터가 필요함

### 1-3. 비목표 (Non-Goals)

- 모든 LLM 토큰 단위 저장 (성능 부담, SSE 스트리밍은 그대로 유지)
- LangGraph checkpoint state 우리 DB 복제 (LangGraph checkpointer 책임)
- LangSmith trace 전체 복제 (중복 저장, 비용 ↑)
- 실시간 알림/대시보드 UI (이번 Plan은 데이터 영속화까지)

---

## 2. 기능 범위 (Scope)

### In Scope (이번 마일스톤 풀세트)

| 영역 | 항목 |
|------|------|
| **테이블** | `ai_run`, `ai_run_step`, `ai_tool_call`, `ai_retrieval_source`, **`ai_llm_call`** 5종 |
| **Run 상태 관리** | RUNNING → SUCCESS / FAILED / CANCELLED 상태 전이, 시작/종료 시각, 에러 메시지·스택 |
| **토큰 사용량 (3-계층)** | (1) Run 단위 합계(prompt/completion/total) + 주력 `llm_model_id`, (2) LLM 호출 1건 단위(`ai_llm_call`) — model_id/provider/tokens/cost, (3) Tool 단위 호출별 token & llm_model_id |
| **사용자별·LLM별 집계** | `ai_run.user_id` × `ai_llm_call.llm_model_id` 조합으로 SQL 집계. 일·주·월 단위 집계 뷰 또는 쿼리 가이드 포함 |
| **비용 계산** | `llm_model` 테이블에 `input_price_per_1k_usd` / `output_price_per_1k_usd` 컬럼 추가, `ai_llm_call`에 호출 시점 가격 스냅샷(`input_cost_usd` / `output_cost_usd` / `total_cost_usd`) 저장 |
| **노드 실행 기록** | Supervisor·Worker·Quality Gate 등 의미 있는 노드의 input/output 요약, 노드별 `llm_model_id` |
| **툴 호출 기록** | tool_name, arguments, result_summary, latency_ms, status, **`llm_model_id`** (툴 내부 LLM 호출 시) |
| **RAG 검색 근거** | collection_name, document_id, chunk_id, score, content_preview |
| **LangSmith 연동** | `ai_run.langsmith_trace_id` 저장 + metadata로 conversation_id/run_id/user_id 송신 |
| **FK 연결** | `ai_run.user_message_id → conversation_message.id`, `ai_run.llm_model_id → llm_model.id`, `ai_llm_call.llm_model_id → llm_model.id` |
| **Repository / UseCase 통합** | `RunAgentUseCase`에 run 생성·갱신 훅 추가, Supervisor·Worker·Summarizer·툴 내부 LLM 호출 지점에서 `record_llm_call()` 호출 |
| **TDD** | Domain entity, Repository, UseCase 통합 테스트 + 사용자별/LLM별 집계 쿼리 테스트 |

### Out of Scope (후속 PDCA에서)

- 어드민 대시보드 UI (조회 API는 본 Plan에서 최소만, 화면은 별도 Plan)
- 실시간 비용 알림·이상 탐지
- 사용자 피드백 테이블(`ai_feedback`) — 별도 기능으로 분리
- LangGraph Postgres checkpointer 도입
- 토큰 단위(token-by-token) 저장
- 평가(evaluation) 시스템 연계 — `evaluation_run` 테이블은 이미 존재, 연계 작업은 별도

---

## 3. 기술 의존성

| 모듈 | Task ID | 상태 |
|------|---------|------|
| LoggerInterface (LOG-001) | LOG-001 | 구현됨 |
| MySQL Persistence (database.py) | - | 구현됨 |
| conversation_message / conversation_summary | - | 구현됨 (V016) |
| RunAgentUseCase / supervisor_nodes | - | 구현됨 |
| LangSmith Adapter (`langsmith.py`) | - | 구현됨 (단순 env 설정) |

외부 라이브러리: 신규 의존성 없음 (SQLAlchemy / langsmith SDK 기존 사용 중)

---

## 4. 아키텍처 설계

### 4-1. 레이어 배치 (Thin DDD 준수)

```
src/domain/agent_run/
├── __init__.py
├── entities.py        # AgentRun, AgentRunStep, ToolCall, RetrievalSource, LlmCall
├── value_objects.py   # RunId, RunStatus, TokenUsage, CostUsd
├── interfaces.py      # AgentRunRepositoryInterface, LlmCallRepositoryInterface
└── policies.py        # Run 상태 전이 규칙, 비용 계산 규칙 (price snapshot)

src/application/agent_run/
├── __init__.py
├── tracker.py         # RunTracker 파사드 (start/complete/fail/record_step/record_tool/record_retrieval/record_llm_call)
├── cost_calculator.py # LLM 모델 가격 × 토큰 → cost_usd 산출
├── aggregator.py      # 사용자별·LLM별·기간별 집계 쿼리
└── schemas.py         # 응답 DTO (UsageSummary, UserUsage, LlmUsage)

src/infrastructure/persistence/models/
└── agent_run.py       # ORM: AgentRunModel, AgentRunStepModel, ToolCallModel, RetrievalSourceModel, LlmCallModel

src/infrastructure/persistence/repositories/
├── agent_run_repository.py     # AgentRunRepositoryInterface 구현
└── llm_call_repository.py      # LlmCallRepositoryInterface 구현 (집계 쿼리 포함)

src/infrastructure/langsmith/
└── trace_extractor.py  # LangSmith run에서 trace_id 추출 (callback)

src/infrastructure/llm/
└── usage_callback.py   # LangChain BaseCallbackHandler — on_llm_end에서 usage_metadata 추출 → tracker.record_llm_call

db/migration/
├── V021__create_agent_run_tables.sql   # 5개 신규 테이블
└── V022__add_llm_model_pricing.sql     # llm_model에 가격 컬럼 추가
```

### 4-2. 호출 흐름

```
1. RunAgentUseCase.execute()
   ↓
2. tracker.start_run(conversation_id, user_message_id, user_id, agent_id, agent_llm_model_id)
     → INSERT ai_run (status=RUNNING, started_at=now, llm_model_id=agent의 주력 LLM)
   ↓
3. LangGraph config에 metadata 주입 (trace_id, conversation_id, run_id, user_id, agent_id)
   + LangChain BaseCallbackHandler(UsageCallback) 등록
   ↓
4. graph.ainvoke() 실행 중:
     - Supervisor 노드: tracker.record_step(node=supervisor, decision=...)
     - Worker 노드: tracker.record_step(node=worker_id, input=, output=)
     - Tool 호출: tracker.record_tool_call(tool_name, args, result, latency, status, llm_model_id?)
     - RAG 검색: tracker.record_retrieval(collection, doc_id, chunk_id, score, preview)
     - ★ LLM 호출 후 (Callback): UsageCallback.on_llm_end()
         → tracker.record_llm_call(
             run_id, step_id, tool_call_id,
             llm_model_id (LangChain model_name으로 매핑),
             provider, prompt_tokens, completion_tokens, total_tokens,
             input_cost_usd, output_cost_usd, total_cost_usd, latency_ms
           )
   ↓
5. (성공) tracker.complete_run(run_id, langsmith_trace_id)
       → SUM(ai_llm_call.total_tokens WHERE run_id) → ai_run.total_tokens 갱신
       → UPDATE ai_run SET status=SUCCESS, ended_at=, prompt/completion/total_tokens=...
   (실패) tracker.fail_run(run_id, exception)
       → UPDATE ai_run SET status=FAILED, error_message=, error_stack=
```

**중요**: Supervisor / Worker / Summarizer / 툴 내부 LLM(rerank / query_rewrite / hallucination check 등)은 **모두 `UsageCallback`이 자동 인터셉트**하므로, 각 호출 지점에 코드를 흩뿌릴 필요가 없다. LangChain `BaseChatModel` 호출은 callback이 일관 수집한다.

### 4-3. 단일 트랜잭션 정책

- `start_run`은 **즉시 commit** (LangGraph가 중간에 죽어도 "요청 흔적"은 남아야 함)
- `record_step/tool/retrieval`은 각 호출마다 별도 트랜잭션 (실패해도 본 흐름은 막지 않음, best-effort)
- `complete_run/fail_run`은 별도 트랜잭션 (최종 상태)
- CLAUDE.md 규칙 준수: Repository 내부에서 `commit()` 호출 금지, UseCase·Tracker 레벨에서 세션 관리

---

## 5. 데이터 모델

### 5-0. llm_model 확장 (V022 — 가격 컬럼 추가)

```sql
ALTER TABLE llm_model
    ADD COLUMN input_price_per_1k_usd  DECIMAL(10, 6) NULL COMMENT '입력 토큰 1000개당 USD',
    ADD COLUMN output_price_per_1k_usd DECIMAL(10, 6) NULL COMMENT '출력 토큰 1000개당 USD',
    ADD COLUMN pricing_updated_at      DATETIME NULL;
```

호출 시점에 이 가격을 읽어 `ai_llm_call`에 스냅샷으로 저장한다 (가격이 바뀌어도 과거 비용 보존).

### 5-1. ai_run (실행 단위 — 사용자 질문 1회 = 1 row)

```sql
CREATE TABLE ai_run (
    id                  VARCHAR(36) PRIMARY KEY,
    conversation_id     VARCHAR(255) NOT NULL,           -- session_id 매핑
    user_id             VARCHAR(255) NOT NULL,
    agent_id            VARCHAR(36) NOT NULL,
    llm_model_id        VARCHAR(36) NULL,                -- Agent의 주력 LLM (FK -> llm_model.id)
    user_message_id     BIGINT NULL,                     -- FK -> conversation_message.id
    status              VARCHAR(20) NOT NULL,            -- RUNNING/SUCCESS/FAILED/CANCELLED
    langgraph_thread_id VARCHAR(150) NOT NULL,
    langsmith_trace_id  VARCHAR(150) NULL,
    langsmith_run_url   VARCHAR(500) NULL,
    prompt_tokens       INT NOT NULL DEFAULT 0,          -- SUM(ai_llm_call.prompt_tokens)
    completion_tokens   INT NOT NULL DEFAULT 0,          -- SUM(ai_llm_call.completion_tokens)
    total_tokens        INT NOT NULL DEFAULT 0,          -- SUM(ai_llm_call.total_tokens)
    total_cost_usd      DECIMAL(12, 6) NOT NULL DEFAULT 0,  -- SUM(ai_llm_call.total_cost_usd)
    llm_call_count      INT NOT NULL DEFAULT 0,          -- COUNT(ai_llm_call)
    started_at          DATETIME NOT NULL,
    ended_at            DATETIME NULL,
    latency_ms          INT NULL,
    error_message       TEXT NULL,
    error_stack         TEXT NULL,
    CONSTRAINT fk_run_user_message
        FOREIGN KEY (user_message_id) REFERENCES conversation_message(id) ON DELETE SET NULL,
    CONSTRAINT fk_run_llm_model
        FOREIGN KEY (llm_model_id) REFERENCES llm_model(id) ON DELETE SET NULL,
    INDEX idx_run_conversation (conversation_id),
    INDEX idx_run_agent (agent_id),
    INDEX idx_run_user_started (user_id, started_at DESC),  -- 사용자별 집계용
    INDEX idx_run_llm_model (llm_model_id),
    INDEX idx_run_status (status),
    INDEX idx_run_started_at (started_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 5-2. ai_run_step (LangGraph 노드 실행)

```sql
CREATE TABLE ai_run_step (
    id            VARCHAR(36) PRIMARY KEY,
    run_id        VARCHAR(36) NOT NULL,
    step_index    INT NOT NULL,                       -- 실행 순서
    node_name     VARCHAR(100) NOT NULL,              -- supervisor / worker_xxx / quality_gate
    node_type     VARCHAR(30) NOT NULL,               -- SUPERVISOR / WORKER / GATE / OTHER
    llm_model_id  VARCHAR(36) NULL,                   -- 이 노드가 LLM을 호출했다면 어떤 모델인지
    status        VARCHAR(20) NOT NULL,               -- STARTED / SUCCESS / FAILED
    input_summary TEXT NULL,                          -- 요약본만, 원문은 LangSmith 참고
    output_summary TEXT NULL,
    started_at    DATETIME NOT NULL,
    ended_at      DATETIME NULL,
    latency_ms    INT NULL,
    error_text    TEXT NULL,
    CONSTRAINT fk_step_run FOREIGN KEY (run_id) REFERENCES ai_run(id) ON DELETE CASCADE,
    CONSTRAINT fk_step_llm_model FOREIGN KEY (llm_model_id) REFERENCES llm_model(id) ON DELETE SET NULL,
    INDEX idx_step_run (run_id, step_index)
);
```

### 5-3. ai_tool_call (툴 호출)

```sql
CREATE TABLE ai_tool_call (
    id              VARCHAR(36) PRIMARY KEY,
    run_id          VARCHAR(36) NOT NULL,
    step_id         VARCHAR(36) NULL,
    tool_name       VARCHAR(100) NOT NULL,
    llm_model_id    VARCHAR(36) NULL,                 -- 툴이 내부적으로 LLM 호출 시 (rerank/query_rewrite 등)
    arguments_json  JSON NULL,
    result_summary  TEXT NULL,                        -- 결과 미리보기 (1KB 컷)
    result_json     JSON NULL,                        -- 구조화된 결과 (옵션)
    prompt_tokens   INT NULL,                         -- 툴 단위 LLM 토큰 합계 (없으면 NULL)
    completion_tokens INT NULL,
    total_tokens    INT NULL,
    total_cost_usd  DECIMAL(12, 6) NULL,
    latency_ms      INT NULL,
    status          VARCHAR(20) NOT NULL,             -- SUCCESS / FAILED
    error_text      TEXT NULL,
    created_at      DATETIME NOT NULL,
    CONSTRAINT fk_tool_run FOREIGN KEY (run_id) REFERENCES ai_run(id) ON DELETE CASCADE,
    CONSTRAINT fk_tool_step FOREIGN KEY (step_id) REFERENCES ai_run_step(id) ON DELETE SET NULL,
    CONSTRAINT fk_tool_llm_model FOREIGN KEY (llm_model_id) REFERENCES llm_model(id) ON DELETE SET NULL,
    INDEX idx_tool_run (run_id),
    INDEX idx_tool_name (tool_name),
    INDEX idx_tool_llm_model (llm_model_id)
);
```

### 5-3-1. ai_llm_call ★ 신규 — LLM API 호출 1건 단위 (사용자별·LLM별 집계의 기준)

```sql
CREATE TABLE ai_llm_call (
    id                VARCHAR(36) PRIMARY KEY,
    run_id            VARCHAR(36) NOT NULL,
    step_id           VARCHAR(36) NULL,                -- 어떤 노드에서 호출됐는지 (있으면)
    tool_call_id      VARCHAR(36) NULL,                -- 툴 내부 LLM 호출이면 어떤 툴 호출인지
    user_id           VARCHAR(255) NOT NULL,           -- 비정규화 (사용자별 집계 성능)
    agent_id          VARCHAR(36) NOT NULL,            -- 비정규화 (에이전트별 집계 성능)
    llm_model_id      VARCHAR(36) NOT NULL,
    provider          VARCHAR(50) NOT NULL,            -- openai / anthropic / ollama / perplexity
    model_name        VARCHAR(150) NOT NULL,           -- 호출 시점 모델명 스냅샷 (gpt-4o 등)
    purpose           VARCHAR(50) NULL,                -- supervisor / worker / summarizer / rerank / query_rewrite / hallucination_check
    prompt_tokens     INT NOT NULL DEFAULT 0,
    completion_tokens INT NOT NULL DEFAULT 0,
    total_tokens      INT NOT NULL DEFAULT 0,
    input_price_per_1k_usd  DECIMAL(10, 6) NULL,       -- 호출 시점 가격 스냅샷
    output_price_per_1k_usd DECIMAL(10, 6) NULL,
    input_cost_usd    DECIMAL(12, 6) NOT NULL DEFAULT 0,
    output_cost_usd   DECIMAL(12, 6) NOT NULL DEFAULT 0,
    total_cost_usd    DECIMAL(12, 6) NOT NULL DEFAULT 0,
    latency_ms        INT NULL,
    status            VARCHAR(20) NOT NULL,            -- SUCCESS / FAILED
    error_text        TEXT NULL,
    created_at        DATETIME NOT NULL,
    CONSTRAINT fk_llm_call_run FOREIGN KEY (run_id) REFERENCES ai_run(id) ON DELETE CASCADE,
    CONSTRAINT fk_llm_call_step FOREIGN KEY (step_id) REFERENCES ai_run_step(id) ON DELETE SET NULL,
    CONSTRAINT fk_llm_call_tool FOREIGN KEY (tool_call_id) REFERENCES ai_tool_call(id) ON DELETE SET NULL,
    CONSTRAINT fk_llm_call_model FOREIGN KEY (llm_model_id) REFERENCES llm_model(id),
    -- 집계용 인덱스
    INDEX idx_llm_call_user_created (user_id, created_at DESC),       -- 사용자별 기간 집계
    INDEX idx_llm_call_model_created (llm_model_id, created_at DESC),  -- LLM별 기간 집계
    INDEX idx_llm_call_user_model (user_id, llm_model_id),             -- 사용자×LLM 매트릭스
    INDEX idx_llm_call_agent (agent_id),
    INDEX idx_llm_call_run (run_id)
);
```

**비정규화 정책**: `user_id`, `agent_id`, `model_name`, `provider`는 `ai_run`/`llm_model`에서도 조회 가능하지만, **집계 쿼리 성능을 위해 `ai_llm_call`에 복사**한다. 사용자별·모델별·일별 집계는 단일 테이블 스캔으로 끝낸다.

**대표 집계 쿼리** (Design 단계에서 확정):

```sql
-- 사용자별 이번달 토큰/비용
SELECT user_id, SUM(total_tokens) AS tokens, SUM(total_cost_usd) AS cost_usd
FROM ai_llm_call
WHERE created_at >= '2026-05-01'
GROUP BY user_id;

-- LLM 모델별 이번달 사용량
SELECT llm_model_id, model_name, provider,
       SUM(total_tokens) AS tokens,
       SUM(total_cost_usd) AS cost_usd,
       COUNT(*) AS call_count
FROM ai_llm_call
WHERE created_at >= '2026-05-01'
GROUP BY llm_model_id, model_name, provider;

-- 사용자 × LLM 매트릭스
SELECT user_id, model_name, SUM(total_tokens) AS tokens, SUM(total_cost_usd) AS cost
FROM ai_llm_call
WHERE created_at >= '2026-05-01'
GROUP BY user_id, model_name;

-- 한 사용자의 일별 사용량
SELECT DATE(created_at) AS d, SUM(total_tokens) AS tokens, SUM(total_cost_usd) AS cost
FROM ai_llm_call
WHERE user_id = ? AND created_at >= ?
GROUP BY DATE(created_at);
```

### 5-4. ai_retrieval_source (RAG 검색 근거)

```sql
CREATE TABLE ai_retrieval_source (
    id              VARCHAR(36) PRIMARY KEY,
    run_id          VARCHAR(36) NOT NULL,
    tool_call_id    VARCHAR(36) NULL,                 -- 어떤 RAG 툴 호출에서 가져왔는지
    collection_name VARCHAR(100) NOT NULL,
    document_id     VARCHAR(150) NULL,
    chunk_id        VARCHAR(150) NULL,
    score           DECIMAL(10, 6) NULL,
    rank_index      INT NULL,                          -- top_k 순위
    content_preview TEXT NULL,                         -- chunk 텍스트 500자 컷
    metadata_json   JSON NULL,
    created_at      DATETIME NOT NULL,
    CONSTRAINT fk_retrieval_run FOREIGN KEY (run_id) REFERENCES ai_run(id) ON DELETE CASCADE,
    CONSTRAINT fk_retrieval_tool FOREIGN KEY (tool_call_id) REFERENCES ai_tool_call(id) ON DELETE SET NULL,
    INDEX idx_retrieval_run (run_id),
    INDEX idx_retrieval_collection (collection_name)
);
```

---

## 6. 마일스톤 (단계 분할)

| M | 범위 | 산출물 | 예상 작업 |
|---|------|--------|----------|
| **M1** | `ai_run` + `ai_llm_call` + `llm_model` 가격 컬럼 + Run 라이프사이클 + LangChain UsageCallback + LangSmith trace_id | V021·V022 마이그레이션 / Run·LlmCall domain & repo / RunTracker.start/complete/fail / UsageCallback / RunAgentUseCase 통합 / **사용자별·LLM별 집계 쿼리 모듈** | 1.5주 |
| **M2** | `ai_tool_call` + Supervisor·Worker 툴 호출 인터셉트 + 툴 내부 LLM 호출과 `ai_llm_call` 연결 (`tool_call_id`) | 툴 호출 hook / arguments·result 직렬화 / 툴 단위 토큰·비용 집계 | 1주 |
| **M3** | `ai_run_step` + LangGraph 노드 실행 기록 + 노드별 `llm_model_id` 매핑 | langgraph callback / `astream` updates 이벤트 수집 / step input/output 요약 / step ↔ llm_call 연결 | 1주 |
| **M4** | `ai_retrieval_source` + RAG 검색 근거 영속화 + 최소 조회 API (run 상세 / 사용자 usage / LLM usage) | RAG 툴 (retrieval/hybrid/web_search) 어댑터에서 source 기록 / `GET /agents/runs/{run_id}` / `GET /admin/usage/users` / `GET /admin/usage/llm-models` | 1주 |

각 마일스톤은 독립적으로 머지·배포 가능하며, **M1만 완료해도** run 상태·**사용자별 토큰·LLM별 토큰·비용 집계·LangSmith 점프** 가치가 즉시 발생한다.

---

## 7. 코드 통합 지점 (변경 예상 위치)

| 파일 | 변경 내용 |
|------|----------|
| `src/application/agent_builder/run_agent_use_case.py` | `RunTracker` 주입, run 시작 시 `agent.llm_model_id`를 `ai_run.llm_model_id`로 기록. LangGraph config에 `UsageCallback` 등록 + metadata 주입 |
| `src/application/agent_builder/supervisor_nodes.py` | 노드 진입/이탈 시 `record_step` 호출 (해당 노드의 `llm_model_id` 포함) |
| `src/application/agent_builder/workflow_compiler.py` | LangGraph 컴파일 시 `UsageCallback`을 모든 LLM 노드에 전파 |
| `src/infrastructure/llm/usage_callback.py` ★ 신규 | `BaseCallbackHandler.on_llm_end(response, run_id, parent_run_id, **kwargs)` 에서 `response.usage_metadata`(또는 provider-specific) 추출 → `tracker.record_llm_call()`. LangChain model_name → `llm_model.id` 매핑 |
| `src/application/agent_run/cost_calculator.py` ★ 신규 | `(model, prompt_tokens, completion_tokens) → (input_cost_usd, output_cost_usd, total_cost_usd)` |
| `src/application/agent_run/aggregator.py` ★ 신규 | 사용자별·LLM별·기간별 집계 — Repository 위 얇은 파사드 |
| `src/application/rag_agent/tools.py` / `src/infrastructure/retriever/*` | 검색 결과 → `tracker.record_retrieval()` 호출. 툴 내부 LLM 호출은 callback이 자동 수집 |
| `src/application/conversation/` (summarizer 어댑터) | Summarizer LLM도 callback으로 자동 수집되도록 LangChain ChatModel 사용 일관성 확인 |
| `src/infrastructure/langsmith/langsmith.py` | trace_id 추출 헬퍼 + metadata 주입 유틸 추가 |
| `src/api/routes/agent_builder_router.py` | `GET /agents/runs/{run_id}` (run 상세) |
| `src/api/routes/admin_router.py` (또는 신규 `usage_router.py`) | `GET /admin/usage/users?from=&to=` (사용자별), `GET /admin/usage/llm-models?from=&to=` (LLM별), `GET /usage/me?from=&to=` (본인 마이페이지) |
| `src/api/routes/llm_model_router.py` | 가격 컬럼 추가에 따라 응답 스키마 확장 (관리자만 수정 권한) |
| `src/main.py` (DI) | Tracker / RunRepo / LlmCallRepo / UsageCallback / CostCalculator / Aggregator 의존성 주입 |

---

## 8. LangSmith 연동 상세

### 8-1. metadata / tags 주입

```python
config = {
    "configurable": {"thread_id": conversation_id},
    "metadata": {
        "conversation_id": conversation_id,
        "run_id": run_id,                  # 우리 ai_run.id
        "user_id": user_id,
        "agent_id": agent_id,
        "environment": "production",
    },
    "tags": ["agent-platform", agent_id, "production"],
}
```

### 8-2. trace_id 회수

- LangSmith Python SDK의 `get_current_run_tree()` 또는 `RunCollector` callback 사용
- run 종료 시점에 `tracker.complete_run(..., langsmith_trace_id=...)` 으로 저장
- 어드민 화면에서 `langsmith_run_url`을 새 탭으로 열어 디버깅

### 8-3. 민감정보 정책

- LangSmith에는 input/output 원문이 그대로 전송됨 → 운영 정책상 PII/내부정보 마스킹 필요시 anonymizer 적용 (별도 Plan)
- 우리 DB에는 `*_summary` 컬럼만 사용해 컷오프 (TEXT, 1KB 권장)

---

## 9. TDD 계획

```
tests/domain/agent_run/
├── test_entities.py            # AgentRun, LlmCall, RunStatus 전이 검증
├── test_value_objects.py       # RunId, TokenUsage, CostUsd 산술
└── test_policies.py            # RUNNING -> SUCCESS/FAILED 전이 / 가격 스냅샷 정책

tests/infrastructure/agent_run/
├── test_agent_run_repository.py    # CRUD, FK 연결, JSON 직렬화
└── test_llm_call_repository.py     # 사용자별/LLM별/기간별 집계 쿼리 정확성

tests/application/agent_run/
├── test_run_tracker.py             # start/complete/fail/record_*  (best-effort)
├── test_cost_calculator.py         # 가격 × 토큰 → cost_usd (반올림·소수점)
└── test_aggregator.py              # UserUsage / LlmUsage / Daily 집계 DTO

tests/infrastructure/llm/
└── test_usage_callback.py
    # on_llm_end → record_llm_call 호출 검증
    # provider별 usage_metadata 파싱 (OpenAI, Anthropic, Ollama)
    # model_name → llm_model.id 매핑 / 미매핑 모델은 NULL FK + 경고 로그

tests/application/agent_builder/
└── test_run_agent_use_case_observability.py
    # RunAgentUseCase 실행 시 ai_run row 생성 확인
    # 실패 시 status=FAILED 기록 확인
    # 한 run에 supervisor + worker + summarizer 호출 시
    #   → ai_llm_call 최소 3 row + 각각 다른 llm_model_id 가능
    # ai_run.total_tokens == SUM(ai_llm_call.total_tokens) 검증
```

테스트 순서: 도메인 → 인프라(MySQL conftest 활용) → 애플리케이션 → API.

---

## 10. CLAUDE.md 규칙 체크

- [x] domain은 entity/VO/interface/policy만 정의 (외부 의존성 없음)
- [x] application에서 흐름 제어 (RunTracker = UseCase 보조)
- [x] infrastructure에서 SQLAlchemy ORM 구현
- [x] Repository 내부에서 commit/rollback 호출 금지 → Tracker에서 세션 단위 관리
- [x] LOG-001 LoggerInterface 적용
- [x] TDD 순서 준수 (테스트 → 실패 → 구현 → 통과)
- [x] config 하드코딩 금지 (요약본 컷오프 크기 등은 config로)
- [x] DB 세션 정책: 한 UseCase 안에서 동일 세션 사용
- [x] 한국어 도메인 용어와 영문 식별자 분리 유지

---

## 11. 위험 요소 및 대응

| 위험 | 영향 | 대응 |
|------|------|------|
| 모든 step/tool 기록 시 DB I/O 부담 | 응답 지연 | step/tool/retrieval 기록은 best-effort, 실패해도 본 흐름 차단 X. 비동기 큐(M2 이후 검토) |
| `arguments_json` / `metadata_json` 비대화 | 스토리지 폭증 | 결과는 `*_summary` (1KB 컷) 우선, 전체 JSON은 옵션 컬럼. retention 정책 별도 |
| LangSmith trace_id 회수 실패 | 점프 기능 일부 동작 안함 | nullable, 실패 시 로그만 남기고 진행 |
| 마이그레이션 중 다운타임 | 운영 중단 | 신규 테이블만 추가 (기존 데이터 변경 없음), Flyway forward-only |
| 토큰 집계 정합성 | 비용 분석 오류 | LangChain `usage_metadata` 기반으로 일관 수집, 단위 테스트로 누적 검증, `ai_run.total_tokens == SUM(ai_llm_call.total_tokens)` 정합성 체크 |
| **LangChain model_name → llm_model.id 매핑 실패** | 미등록 모델의 비용이 0원으로 집계 | 매핑 실패 시 `llm_model_id=NULL` + warning log + 운영자 알림. `model_name` 문자열 자체는 `ai_llm_call`에 스냅샷 저장하여 사후 매핑 가능 |
| **LLM 모델 가격 변동** | 과거 비용 데이터 왜곡 | `ai_llm_call`에 호출 시점 가격 스냅샷(`input_price_per_1k_usd`/`output_price_per_1k_usd`) 저장 — `llm_model`의 가격이 바뀌어도 과거는 보존 |
| **Provider별 usage_metadata 형식 차이** | 토큰 누락 | OpenAI(`completion_tokens` / `prompt_tokens`), Anthropic(`input_tokens` / `output_tokens`), Ollama(`prompt_eval_count` 등) 어댑터별 파서 구현 + 미인식 시 0 + warning log |
| **streaming 응답의 토큰 집계** | streaming 시 usage_metadata가 마지막 청크에만 옴 | LangChain v0.3+ `stream_usage=True` 옵션 활성화, `on_llm_end`에서만 집계 |
| **개인정보(PII) 집계 노출** | 사용자별 사용량 조회 시 권한 누설 | `/admin/usage/*` 는 admin 역할 필수, `/usage/me` 는 본인만 조회 |
| FK 제약으로 conversation_message 삭제 시 영향 | 운영 사고 | `ON DELETE SET NULL` 로 ai_run은 보존 |

---

## 12. 후속 PDCA 후보

- `agent-run-admin-dashboard` — 어드민 UI에서 run 목록/상세 조회·필터·LangSmith 점프
- `agent-usage-dashboard` — 사용자별·LLM별·부서별 사용량/비용 대시보드 (마이페이지 + 관리자)
- `agent-user-quota` — 사용자별 토큰 한도·일일 캡·예산 알림
- `agent-feedback` — 사용자 피드백(`ai_feedback`) 수집·집계
- `agent-cost-anomaly-detection` — 이상 토큰 호출(스파이크) 자동 탐지·알림
- `llm-pricing-sync` — Provider 가격 변동 자동 동기화 (cron + 알림)
- `agent-pii-masking` — LangSmith 송신 전 민감정보 마스킹 anonymizer
- `langgraph-postgres-checkpointer` — LangGraph 공식 Postgres checkpointer 도입 (resume/time-travel)

---

## 13. 완료 기준 (DoD)

### 마일스톤 1 (Run + LlmCall + 사용자별/LLM별 집계 + LangSmith trace)
- [ ] `db/migration/V021__create_agent_run_tables.sql` 작성 (5테이블 모두 포함)
- [ ] `db/migration/V022__add_llm_model_pricing.sql` (llm_model에 가격 컬럼 추가)
- [ ] `src/domain/agent_run/` 도메인 모듈 구현 (entity/VO/interface/policy) — `AgentRun`, `LlmCall` 포함
- [ ] `src/infrastructure/persistence/models/agent_run.py` ORM 모델 (5개)
- [ ] `src/infrastructure/persistence/repositories/agent_run_repository.py` + `llm_call_repository.py`
- [ ] `src/application/agent_run/tracker.py` (`start_run` / `complete_run` / `fail_run` / `record_llm_call`)
- [ ] `src/application/agent_run/cost_calculator.py` (가격 스냅샷 적용)
- [ ] `src/application/agent_run/aggregator.py` (사용자별 / LLM별 / 사용자×LLM / 기간별)
- [ ] `src/infrastructure/llm/usage_callback.py` (LangChain BaseCallbackHandler) — provider별 usage_metadata 파싱
- [ ] LangChain model_name → `llm_model.id` 매핑 테이블/로직 (미등록 모델은 NULL FK + warning log)
- [ ] `RunAgentUseCase` 통합 (start/complete/fail + UsageCallback 등록 + `agent.llm_model_id`를 `ai_run.llm_model_id`에 기록)
- [ ] LangSmith metadata 주입 + `langsmith_trace_id` 저장
- [ ] 토큰 합계 영속화: `ai_run.total_tokens = SUM(ai_llm_call.total_tokens)` 일관성
- [ ] 비용 계산: `ai_run.total_cost_usd = SUM(ai_llm_call.total_cost_usd)`
- [ ] 도메인·인프라·애플리케이션 테스트 통과
- [ ] **수동 검증**: 한 run 실행 후 `SELECT user_id, llm_model_id, SUM(total_tokens) FROM ai_llm_call WHERE run_id = ? GROUP BY ...` 쿼리가 의도대로 동작

### 마일스톤 2 (Tool Call)
- [ ] `record_tool_call` Tracker 메서드 + Workflow callback 연결
- [ ] 툴 단위 토큰·latency·`llm_model_id` 기록 (툴 내부 LLM 호출과 `ai_llm_call.tool_call_id` 연결)
- [ ] 통합 테스트: 한 run 실행 시 ai_tool_call N row 생성 검증

### 마일스톤 3 (Run Step)
- [ ] LangGraph `astream(updates)` 또는 callback으로 노드 실행 hook
- [ ] step input/output 요약 (1KB 컷) 영속화
- [ ] step ↔ `ai_llm_call.step_id` 연결 (노드별 LLM 호출 추적)
- [ ] Supervisor 결정 사유(`SupervisorDecision.reasoning`) step에 기록

### 마일스톤 4 (Retrieval Source + Usage API)
- [ ] RAG 검색 어댑터 (retrieval / hybrid / web_search)에서 source 기록
- [ ] `GET /agents/runs/{run_id}` 최소 조회 API
- [ ] `GET /admin/usage/users?from=&to=` (사용자별 토큰·비용 집계)
- [ ] `GET /admin/usage/llm-models?from=&to=` (LLM별 토큰·비용 집계)
- [ ] `GET /usage/me?from=&to=` (마이페이지: 본인 사용량)
- [ ] e2e 테스트: 질문 1회 → ai_run + ai_llm_call + ai_tool_call + ai_retrieval_source 일관 생성

---

## 14. 참고 자료

- 본 Plan은 `docs/ex/agent_debug.md` (LangSmith vs LangGraph Checkpointer vs Service DB 책임 분리 분석)을 기반으로 한다.
- 핵심 원칙: **"LangSmith는 개발자가 보는 블랙박스 기록, 우리 DB는 서비스가 책임지는 업무 원장"**.
