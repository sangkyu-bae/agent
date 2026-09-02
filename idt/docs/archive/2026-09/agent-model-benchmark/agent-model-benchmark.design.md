# agent-model-benchmark Design Document

> **Summary**: `evaluation_sweep` 부모 테이블로 재현성 스냅샷을 박제하고, `_prepare_graph` 단일 지점의 모델 오버라이드로 에이전트 정의를 건드리지 않은 채 모델만 갈아끼워 순차 실행한 뒤, `ai_run` 조인과 `tools_used` 대조로 4축 지표를 회수해 모델 × 지표 매트릭스로 제시한다.
>
> **Project**: sangplusbot (idt + idt_front)
> **Version**: 0.1.0
> **Author**: 배상규
> **Date**: 2026-08-31
> **Status**: Draft
> **Planning Doc**: [agent-model-benchmark.plan.md](../../01-plan/features/agent-model-benchmark.plan.md)
> **선택 설계안**: **C — 실용 균형** (Checkpoint 3)

### Pipeline References

| Phase | Document | Status |
|-------|----------|--------|
| Phase 1 | 스키마 — 기존 평가/관측 스키마 확장 | N/A (신규 문서 불필요) |
| Phase 2 | 코딩 규약 — `idt/CLAUDE.md` + `idt/docs/rules/` | ✅ |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 평가 스택에 모델 차원이 없어 모델 간 성능·비용 트레이드오프를 수치로 비교할 수 없다 |
| **WHO** | P2 — 자기 에이전트의 품질과 운영비를 스스로 검증해야 하는 에이전트 소유자 / KB 운영자 |
| **RISK** | 모델 오버라이드가 `RunAgentRequest` 소비자 8곳(웹소켓·스케줄·웹훅·백그라운드잡 등)이 공유하는 실행 경로를 침습한다 |
| **SUCCESS** | 에이전트 1개 × 모델 N개 스윕 실행 → 4축 지표가 채워진 매트릭스 표가 뜨고, 같은 조건 재실행 시 품질 점수 편차 ≤ 5%p |
| **SCOPE** | 백엔드: 모델 오버라이드 + sweep 도메인 + 지표 수집 3종 / 프론트: 스윕 생성 모달 + 매트릭스 표. 에이전트 생성·테스트셋 생성·차트 시각화는 제외 |

---

## 1. Overview

### 1.1 Design Goals

| ID | 목표 | 근거 |
|----|------|------|
| G1 | 에이전트 정의를 **수정하지 않고** 모델만 교체해 실행한다 | Plan FR-01, 사용자 결정 #9 |
| G2 | `RunAgentRequest` 소비자 8곳의 동작이 **1바이트도 바뀌지 않는다** | Plan NFR 하위호환, R-1 |
| G3 | 실행 조건(judge·temperature·모델목록·테스트셋)을 **한 곳에 박제**해 재현 가능하게 한다 | Plan NFR 재현성 |
| G4 | 비용·지연은 **새로 계측하지 않고** 기존 `ai_run`에서 회수한다 | Plan §7.2 결정 |
| G5 | 개별 모델 실패가 **스윕 전체를 죽이지 않는다** | Plan FR-13 |
| G6 | 측정 불가 지표는 **0이 아니라 N/A**로 구분된다 | Plan R-4, §8.2 규약 |

### 1.2 Design Principles

1. **오버라이드는 additive로만 한다** — `RunAgentRequest`에 Optional 필드를 더할 뿐, 기존 필드·시그니처·기본 동작을 제거하거나 바꾸지 않는다. 미지정 시 분기는 `or` / `is not None` 한 줄로 끝난다.
2. **주입 지점은 한 곳으로 모은다** — 모델·temperature 해석은 `_prepare_graph`에서만 일어난다. 그래프 컴파일러·워커·툴은 오버라이드의 존재를 모른다.
3. **실행 인프라를 새로 만들지 않는다** — 순차 오케스트레이션은 검증된 `BatchEvalExecutor.kickoff` 패턴을 재사용한다 (선택안 C의 핵심).
4. **관측은 이미 있는 것을 읽는다** — 토큰·비용·지연은 `ai_run`이 진실원이다. 중복 계측 금지 (`idt/CLAUDE.md` 금지 항목).
5. **얇은 도메인** — Policy 2개(스윕 제약, 도구 정확도)만 도메인에 둔다. 도메인 서비스 남발 금지.
6. **N/A는 실패가 아니다** — 측정 불가와 성능 0점을 타입 수준에서 구분한다(`None` vs `0.0`).

---

## 2. Architecture Options

### 2.0 Architecture Comparison

| 기준 | A: 최소 변경 | B: 완전 분리 | **C: 실용 균형 ★선택** |
|---|:-:|:-:|:-:|
| **접근** | 컬럼만 추가, 프론트가 N회 호출 | `eval_sweep` 바운디드 컨텍스트 풀세트 | 부모 테이블 + 얇은 도메인 + 기존 Executor 재사용 |
| **신규 파일** | 3 | 17 | **11** |
| **수정 파일** | 11 | 12 | **11** |
| **복잡도** | 낮음 | 높음 | 중간 |
| **유지보수성** | 낮음 | 높음 | 높음 |
| **공수** | 낮음 | 높음 | 중간 |
| **치명적 약점** | 재현성 스냅샷 저장 위치 없음, 브라우저 닫으면 중단 | `idt/CLAUDE.md` "과도한 추상화(두꺼운 DDD)" 저촉 | — |

**Selected**: **Option C** — **Rationale**: 재현성 스냅샷을 담을 부모 테이블은 NFR상 필수라 A는 탈락한다. 반면 실행기는 `BatchEvalExecutor`가 이미 `kickoff → _run → _evaluate_case` 흐름을 검증해뒀으므로 B처럼 새 실행 인프라와 도메인 서비스를 세우면 순수 중복이다. 부모 테이블 + Policy 2개 + 기존 실행기 재사용이 최소 비용으로 모든 NFR을 만족한다.

### 2.1 Component Diagram

```
┌─────────────────────────── idt_front ────────────────────────────┐
│  EvalDatasetPage / RunsTab                                        │
│    ├── CreateSweepModal   (에이전트·테스트셋·모델N·judge 선택)    │
│    │        └─ 실행 전 POST /sweeps/estimate → 예상비용 표시      │
│    └── SweepMatrixPanel   (행=모델 / 열=지표 매트릭스)            │
└───────────────────────────────┬───────────────────────────────────┘
                                │ REST (/api/ragas/sweeps*)
┌───────────────────────────────▼───────────────────────────────────┐
│ interfaces  ragas_router  (+ sweeps 4 endpoints)                  │
├───────────────────────────────────────────────────────────────────┤
│ application/eval_sweep                                            │
│   CreateSweepUseCase ── SweepExecutor(순차) ──┐                   │
│   EstimateSweepCostUseCase                    │                   │
│   GetSweepDetailUseCase (모델별 집계)         │                   │
├───────────────────────────────────────────────┼───────────────────┤
│ domain/eval_sweep                             │                   │
│   EvaluationSweep(Entity) · SweepPolicy       │                   │
│   ToolAccuracyPolicy(집합 F1)                 │                   │
├───────────────────────────────────────────────┼───────────────────┤
│ infrastructure                                ▼                   │
│   SweepRepository        BatchEvalExecutor(재사용)                │
│                            └─ DefaultTargetExecutor._run_agent    │
│                                 └─ RunAgentUseCase.execute        │
│                                      └─ _prepare_graph ◀ 오버라이드│
│   RagasEvaluatorAdapter(judge 호출별 주입)                        │
└───────────────────────────────────────────────────────────────────┘
                                │
┌───────────────────────────────▼───────────────────────────────────┐
│ MySQL   evaluation_sweep(신규) ─1:N─ evaluation_run ─1:N─ result  │
│         evaluation_result.ai_run_id ──▶ ai_run (토큰·비용·지연)   │
│         llm_model (단가·활성)                                     │
└───────────────────────────────────────────────────────────────────┘
```

### 2.2 Data Flow

**스윕 생성 → 실행 → 조회**

```
[1] POST /sweeps/estimate
      agent_id + testset_id + model_ids[] + judge_model_id
      → ai_run 최근 실행 평균 토큰 조회 (없으면 상수 fallback)
      → Σ(모델별 예상비용) + judge 채점비용
      → { estimated_usd, estimated_minutes, basis }          ← 사용자에게 표시

[2] POST /sweeps  (사용자 확인 후)
      → SweepPolicy 검증 (모델 ≤5 / 활성 / testset 소유)
      → evaluation_sweep INSERT (status=pending, 스냅샷 박제)
      → evaluation_run × N INSERT (status=pending, llm_model_id 각각, sweep_id)
      → SweepExecutor.kickoff()  ──asyncio task──▶ 202 Accepted 즉시 반환

[3] SweepExecutor (백그라운드, 순차)
      for model in models:                       ← 병렬 아님(지연 오염·rate limit)
        run.status = running
        for case in testcases:                   ← 순차
          answer, tools_used, ai_run_id =
              RunAgentUseCase.execute(
                  RunAgentRequest(
                      query=case.question,
                      llm_model_id_override=model.id,      ◀ D1
                      temperature_override=0.0,            ◀ D9
                      persist_conversation=False))         ◀ D2
          ragas_scores = RagasEvaluator.evaluate(..., judge_model=judge)  ◀ D4
          tool_scores  = ToolAccuracyPolicy.score(case.expected_tools, tools_used)  ◀ D6
          result.metrics = {**ragas_scores, **tool_scores}
          result.ai_run_id = ai_run_id           ◀ D10 (비용·지연 회수 키)
        run.status = completed | failed          ← 실패해도 다음 모델로 계속 ◀ G5
      sweep.status = completed

[4] GET /sweeps/{id}
      evaluation_run(sweep_id) ⋈ evaluation_result ⋈ ai_run
      → 모델별 집계: 품질 평균 / Σcost / latency p50·p95 / tool F1
      → 매트릭스 렌더
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `CreateSweepUseCase` | `SweepRepository`, `LlmModelRepository`, `EvaluationRepository`, `SweepPolicy` | 검증 + sweep/run 생성 |
| `EstimateSweepCostUseCase` | `LlmModelRepository`, `AiRunRepository`(읽기), `EvaluationRepository` | 단가 × 실측 평균토큰 |
| `SweepExecutor` | `BatchEvalExecutor` 구성요소 재사용, `SweepRepository` | 순차 오케스트레이션 |
| `GetSweepDetailUseCase` | `SweepRepository` | 모델별 4축 집계 |
| `DefaultTargetExecutor._run_agent` | `AgentRunner`(확장 시그니처) | 오버라이드 전달 + tools_used/ai_run_id 회수 |
| `RunAgentUseCase._prepare_graph` | `LlmModelRepository` | **모델·temperature 오버라이드 해석 단일 지점** |
| `RagasEvaluatorAdapter.evaluate` | judge 모델명(호출 인자) | 실행별 judge 주입 |

---

## 3. Data Model

### 3.1 Entity Definition

```python
# domain/eval_sweep/entity.py
@dataclass
class EvaluationSweep:
    id: str
    name: str
    agent_id: str
    testset_id: str
    judge_llm_model_id: str          # 실행 시점 judge 박제 (D4)
    model_ids: list[str]             # 피평가 모델 목록 스냅샷
    metrics: list[str]               # 선택된 RAGAS 메트릭 스냅샷
    temperature: float               # 항상 0.0 (D9)
    status: str                      # pending | running | completed | failed
    total_runs: int
    completed_runs: int
    estimated_cost_usd: Decimal | None
    user_id: str | None              # 소유자
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None


# domain/eval_sweep/policies.py
class SweepPolicy:
    MAX_MODELS = 5                   # 사용자 결정 #8
    FIXED_TEMPERATURE = 0.0          # D9

    @staticmethod
    def validate(model_ids, judge_model_id, testset_case_count) -> list[str]: ...


class ToolAccuracyPolicy:
    """expected_tools ∩ tools_used 집합 비교 (D6, 순서 무시)."""

    @staticmethod
    def score(expected: list[str] | None, actual: list[str]) -> dict[str, float | None]:
        # expected 미기재 → 전부 None (N/A). 0.0 아님 (G6 / Plan FR-15)
        if not expected:
            return {"tool_precision": None, "tool_recall": None, "tool_f1": None}
        e, a = set(expected), set(actual)
        tp = len(e & a)
        precision = tp / len(a) if a else 0.0
        recall = tp / len(e)
        f1 = 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)
        return {"tool_precision": precision, "tool_recall": recall, "tool_f1": f1}
```

### 3.2 Entity Relationships

```
[evaluation_sweep] 1 ──── N [evaluation_run]        (sweep_id, ON DELETE CASCADE)
                                   │
                                   └── 1 ──── N [evaluation_result]
                                                      │
                                                      └── 0..1 ▶ [ai_run]   (ai_run_id, 비용·지연)

[llm_model] 1 ──── N [evaluation_run.llm_model_id]        (피평가 모델)
[llm_model] 1 ──── N [evaluation_sweep.judge_llm_model_id] (채점 모델)
[evaluation_testset] 1 ──── N [evaluation_sweep]
```

### 3.3 Database Schema

**`db/migration/V067__create_evaluation_sweep.sql`**

> V054 이후 파일이므로 테이블 + 전 컬럼 COMMENT 필수 (`tests/db/test_migration_ddl_comments.py`)

```sql
-- agent-model-benchmark Design §3.3: 모델 스윕 = evaluation_run N건의 부모.
-- 재현성 스냅샷(judge/temperature/모델목록/테스트셋)을 여기 한 곳에 박제한다.

CREATE TABLE evaluation_sweep (
    id                  VARCHAR(36)    NOT NULL COMMENT '스윕 ID (UUID)',
    name                VARCHAR(200)   NOT NULL COMMENT '스윕 표시 이름',
    agent_id            VARCHAR(36)    NOT NULL COMMENT '피평가 에이전트 ID — 스윕 내내 고정',
    testset_id          VARCHAR(36)    NOT NULL COMMENT '평가에 사용한 테스트셋 ID',
    judge_llm_model_id  VARCHAR(36)    NULL     COMMENT 'RAGAS 채점 judge 모델 ID — 실행 시점 박제',
    model_ids           JSON           NOT NULL COMMENT '피평가 모델 ID 배열 스냅샷 (최대 5개)',
    metrics             JSON           NOT NULL COMMENT '선택된 RAGAS 메트릭 이름 배열 스냅샷',
    temperature         DECIMAL(3,2)   NOT NULL DEFAULT 0.00 COMMENT '실행 temperature — 재현성 위해 항상 0',
    status              VARCHAR(20)    NOT NULL DEFAULT 'pending' COMMENT '진행 상태: pending/running/completed/failed',
    total_runs          INT            NOT NULL DEFAULT 0 COMMENT '생성된 하위 run 총 개수 (= 모델 수)',
    completed_runs      INT            NOT NULL DEFAULT 0 COMMENT '완료된 하위 run 개수 (진행률 산출용)',
    estimated_cost_usd  DECIMAL(12,6)  NULL     COMMENT '실행 전 추정 비용(USD) — 실제값과 대조용',
    user_id             VARCHAR(255)   NULL     COMMENT '스윕 소유자 — 미소유자는 404 은닉',
    error_message       TEXT           NULL     COMMENT '스윕 수준 실패 사유 (개별 run 실패는 run에 기록)',
    created_at          DATETIME       NOT NULL COMMENT '생성 시각',
    completed_at        DATETIME       NULL     COMMENT '전체 완료 시각',
    PRIMARY KEY (id),
    CONSTRAINT fk_sweep_judge_model
        FOREIGN KEY (judge_llm_model_id) REFERENCES llm_model (id) ON DELETE SET NULL,
    INDEX idx_sweep_user_created (user_id, created_at DESC),
    INDEX idx_sweep_agent (agent_id),
    INDEX idx_sweep_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='모델 스윕 — 동일 에이전트를 여러 LLM 모델로 순차 평가한 실험 1건';
```

**`db/migration/V068__alter_evaluation_add_sweep_dimension.sql`**

```sql
-- agent-model-benchmark Design §3.3: evaluation_run에 모델 차원을,
-- evaluation_result에 관측 연결 키와 도구 호출 기록을 추가한다. 전부 nullable(기존 row 무영향).

ALTER TABLE evaluation_run
    ADD COLUMN sweep_id VARCHAR(36) NULL
        COMMENT '소속 스윕 ID — NULL이면 단독 실행(기존 배치 평가)' AFTER target_id,
    ADD COLUMN llm_model_id VARCHAR(36) NULL
        COMMENT '이 run에서 사용한 피평가 LLM 모델 ID — 모델 비교의 축' AFTER sweep_id,
    ADD CONSTRAINT fk_eval_run_sweep
        FOREIGN KEY (sweep_id) REFERENCES evaluation_sweep (id) ON DELETE CASCADE,
    ADD CONSTRAINT fk_eval_run_llm_model
        FOREIGN KEY (llm_model_id) REFERENCES llm_model (id) ON DELETE SET NULL,
    ADD INDEX idx_eval_run_sweep (sweep_id);

ALTER TABLE evaluation_result
    ADD COLUMN ai_run_id VARCHAR(36) NULL
        COMMENT '이 케이스 실행의 ai_run.id — 토큰·비용·지연 회수 조인 키' AFTER run_id,
    ADD COLUMN tools_used JSON NULL
        COMMENT '실제 호출된 도구 이름 배열 — expected_tools와 집합 비교',
    ADD INDEX idx_eval_result_ai_run (ai_run_id);
```

> **주의**: `ai_run_id`에 FK를 걸지 **않는다**. `ai_run`은 관측 데이터라 보존정책상 선삭제될 수 있고, 삭제가 평가 결과를 지우면 안 된다. 조인 실패 시 해당 지표만 N/A로 낙하한다.

### 3.4 테스트셋 케이스 확장 (무DDL)

`evaluation_testset.cases`는 JSON이므로 키 추가만으로 끝난다.

```jsonc
{
  "question": "2024년 3분기 여신 잔액 추이를 차트로 보여줘",
  "ground_truth": "…",
  "expected_contexts": ["…"],
  "expected_tools": ["search_kb", "chart_builder"],   // ← 신규(선택). 없으면 도구 지표 N/A
  "metadata": {}
}
```

### 3.5 지표 키 규약 (Plan §8.2 미결 해소)

| 키 | 출처 | 타입 | N/A 조건 |
|---|---|---|---|
| `faithfulness` / `answer_relevancy` / `context_precision` / `context_recall` | RAGAS judge | `float` | judge 실패 시 `null` |
| `latency_ms` | `ai_run.latency_ms` | `int` | `ai_run_id` 없음 |
| `cost_usd` | `ai_run.total_cost_usd` | `float` | `ai_run_id` 없음 / 단가 미등록 |
| `prompt_tokens` / `completion_tokens` | `ai_run` | `int` | 동일 |
| `tool_precision` / `tool_recall` / `tool_f1` | `ToolAccuracyPolicy` | `float` | `expected_tools` 미기재 |

**규약**: 측정 불가는 `null`이며 **집계 시 분모에서 제외**한다. `0.0`은 "측정했고 0점"이라는 뜻으로만 쓴다 (G6).

---

## 4. API Specification

### 4.1 Endpoint List

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| POST | `/api/ragas/sweeps/estimate` | 예상 비용·소요시간 추정 (부수효과 없음) | Required |
| POST | `/api/ragas/sweeps` | 스윕 생성 + 순차 실행 시작 (202) | Required |
| GET | `/api/ragas/sweeps` | 스윕 목록 (본인 것, 관리자는 전체) | Required |
| GET | `/api/ragas/sweeps/{sweep_id}` | 스윕 상세 + **모델별 4축 집계** | Required |
| DELETE | `/api/ragas/sweeps/{sweep_id}` | 스윕 삭제 (하위 run CASCADE) | Required |

### 4.2 Detailed Specification

#### `POST /api/ragas/sweeps/estimate`

**Request**
```json
{
  "agent_id": "ag-001",
  "testset_id": "ts-001",
  "model_ids": ["m-gpt4o", "m-gpt4o-mini", "m-qwen-npu"],
  "judge_llm_model_id": "m-gpt4o",
  "metrics": ["faithfulness", "answer_relevancy"]
}
```

**Response (200)**
```json
{
  "case_count": 20,
  "model_count": 3,
  "total_calls": 60,
  "estimated_cost_usd": "1.842000",
  "estimated_minutes": 14,
  "basis": {
    "source": "ai_run_recent_avg",
    "avg_prompt_tokens": 2400,
    "avg_completion_tokens": 480,
    "sample_size": 37,
    "judge_cost_usd": "0.312000"
  },
  "per_model": [
    { "llm_model_id": "m-gpt4o", "display_name": "GPT-4o", "estimated_cost_usd": "1.104000" },
    { "llm_model_id": "m-gpt4o-mini", "display_name": "GPT-4o mini", "estimated_cost_usd": "0.066000" },
    { "llm_model_id": "m-qwen-npu", "display_name": "Qwen (NPU)", "estimated_cost_usd": "0.000000" }
  ]
}
```

> `basis.source`는 `ai_run_recent_avg`(해당 에이전트 최근 실행 평균) 또는 `fallback_constant`(실행 이력 없음). 프론트는 항상 **"추정치"** 라벨과 함께 렌더한다 (Plan R-3).

#### `POST /api/ragas/sweeps`

**Request**
```json
{
  "name": "여신심사봇 모델 비교 2026-08",
  "agent_id": "ag-001",
  "testset_id": "ts-001",
  "model_ids": ["m-gpt4o", "m-gpt4o-mini", "m-qwen-npu"],
  "judge_llm_model_id": "m-gpt4o",
  "metrics": ["faithfulness", "answer_relevancy", "context_precision"]
}
```

**Response (202 Accepted)**
```json
{
  "sweep_id": "sw-001",
  "status": "pending",
  "total_runs": 3,
  "estimated_cost_usd": "1.842000",
  "message": "스윕이 시작되었습니다. 모델 3개를 순차 실행합니다."
}
```

**Error Responses**
- `400` — 모델 6개 이상 / 모델 미활성 / judge 미활성 / 테스트셋 케이스 0건
- `401` — 인증 필요
- `404` — 에이전트·테스트셋 미존재 **또는 미소유(은닉)**

#### `GET /api/ragas/sweeps/{sweep_id}`

**Response (200)**
```json
{
  "id": "sw-001",
  "name": "여신심사봇 모델 비교 2026-08",
  "agent_id": "ag-001",
  "agent_name": "여신심사봇",
  "testset_id": "ts-001",
  "testset_name": "여신 골든셋 v3",
  "case_count": 20,
  "judge_llm_model": { "id": "m-gpt4o", "display_name": "GPT-4o" },
  "temperature": 0.0,
  "status": "completed",
  "total_runs": 3,
  "completed_runs": 3,
  "estimated_cost_usd": "1.842000",
  "actual_cost_usd": "1.611200",
  "created_at": "2026-08-31T10:00:00Z",
  "completed_at": "2026-08-31T10:13:22Z",
  "rows": [
    {
      "run_id": "er-001",
      "llm_model": { "id": "m-gpt4o", "display_name": "GPT-4o" },
      "status": "completed",
      "quality": { "faithfulness": 0.91, "answer_relevancy": 0.88, "context_precision": 0.84 },
      "cost_usd": "1.104000",
      "latency_p50_ms": 4210,
      "latency_p95_ms": 8740,
      "tool_f1": 0.92,
      "measured_cases": 20,
      "failed_cases": 0
    },
    {
      "run_id": "er-003",
      "llm_model": { "id": "m-qwen-npu", "display_name": "Qwen (NPU)" },
      "status": "failed",
      "quality": null,
      "cost_usd": null,
      "latency_p50_ms": null,
      "latency_p95_ms": null,
      "tool_f1": null,
      "measured_cases": 0,
      "failed_cases": 20,
      "error_message": "connection refused: http://npu-host:8000/v1"
    }
  ]
}
```

> **집계 규칙**: `quality`의 각 메트릭은 `null`이 아닌 케이스만의 평균. `latency_p50/p95`는 `ai_run` 조인 성공 케이스만. `tool_f1`은 `expected_tools`가 있는 케이스만. 유효 표본이 0이면 해당 필드는 `null`(N/A).

### 4.3 기존 API 변경 (하위호환)

| 엔드포인트 | 변경 | 호환성 |
|---|---|---|
| `GET /api/ragas/runs` | 응답에 `sweep_id`, `llm_model` 추가 | additive — 기존 필드 유지 |
| `GET /api/v1/admin/ragas/dashboard` | 집계 쿼리에 **`sweep_id IS NULL`** 필터 추가 (D8) | 통계 정의 변경 — 스윕 run 제외 |
| `POST /api/ragas/batch` | 변경 없음 | 무영향 |

---

## 5. UI/UX Design

### 5.1 Screen Layout

`/eval-dataset` → **평가 실행** 탭 안에 스윕 섹션을 추가한다 (신규 탭 만들지 않음).

```
┌───────────────────────────────────────────────────────────────┐
│  데이터셋  │ ▸평가 실행 │  평가기  │  대시보드                │
├───────────────────────────────────────────────────────────────┤
│  [+ 단일 평가]   [+ 모델 스윕]                    ← 버튼 2개  │
├───────────────────────────────────────────────────────────────┤
│  ▼ 모델 스윕                                                  │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │ 여신심사봇 모델 비교 2026-08     완료   3/3   $1.6112   │  │
│  │ judge: GPT-4o · temp 0.0 · 여신 골든셋 v3 (20건)        │  │
│  └─────────────────────────────────────────────────────────┘  │
│                                                               │
│  ▼ 매트릭스 (행=모델 / 열=지표)                               │
│  ┌────────────┬───────┬───────┬───────┬────────┬──────┬─────┐│
│  │ 모델       │ faith │ relev │ ctx-p │ 비용   │ p50  │ 도구││
│  ├────────────┼───────┼───────┼───────┼────────┼──────┼─────┤│
│  │ GPT-4o     │ 0.91★│ 0.88★│ 0.84★│ $1.104 │ 4.2s │0.92★││
│  │ GPT-4o mini│ 0.86  │ 0.85  │ 0.83  │$0.066★│2.1s★│0.79 ││
│  │ Qwen (NPU) │  실패 │  —    │  —    │  —     │  —   │  —  ││
│  └────────────┴───────┴───────┴───────┴────────┴──────┴─────┘│
│  ★ = 지표별 최고값   — = N/A(측정 불가)                       │
└───────────────────────────────────────────────────────────────┘
```

### 5.2 User Flow

```
평가 실행 탭 → [+ 모델 스윕] → 모달
  → 에이전트 선택 → 테스트셋 선택 → 모델 다중선택(≤5) → judge 선택 → 메트릭 선택
  → [예상 비용 확인]  (POST /sweeps/estimate)
  → "예상 $1.84 · 약 14분 (추정치)" 표시
  → [실행]  (POST /sweeps, 202)
  → 목록에 pending 행 추가 → 3초 폴링으로 진행률 갱신
  → 완료 시 매트릭스 표 렌더
```

### 5.3 Component List

| Component | Location | Responsibility |
|-----------|----------|----------------|
| `CreateSweepModal` | `idt_front/src/pages/EvalDatasetPage/` | 스윕 생성 폼 + 예상비용 확인 게이트 |
| `SweepMatrixPanel` | `idt_front/src/pages/EvalDatasetPage/` | 모델 × 지표 매트릭스 + 최고값 하이라이트 + N/A 렌더 |
| `useSweeps` | `idt_front/src/hooks/` | 목록·상세·생성·추정·삭제 (TanStack Query, 진행 중 3초 폴링) |
| `sweepService` | `idt_front/src/services/` | REST 호출 |
| `types/sweep.ts` | `idt_front/src/types/` | `Sweep`, `SweepRow`, `SweepEstimate` 타입 + `as const` 상수 |

> 프로젝트 규약상 컴포넌트 파일에서 런타임 상수를 export하지 않는다. 지표 컬럼 정의·라벨은 `src/types/sweep.ts`에 `as const`로 둔다.

### 5.4 Page UI Checklist

**CreateSweepModal**

- [ ] 에이전트 선택 드롭다운 (본인 접근 가능 에이전트만)
- [ ] 테스트셋 선택 드롭다운 (케이스 수 병기)
- [ ] 모델 **다중선택** 체크박스 목록 (활성 모델만, **6개째 선택 시 비활성화 + "최대 5개" 안내**)
- [ ] judge 모델 선택 드롭다운 (활성 모델만)
- [ ] RAGAS 메트릭 다중선택 체크박스
- [ ] temperature **0.0 고정 표시(읽기전용)** + "재현성을 위해 고정됩니다" 안내
- [ ] [예상 비용 확인] 버튼 → 추정 결과 영역
- [ ] 추정 결과: 총 예상 USD, 예상 소요 분, **"추정치" 라벨**, 모델별 내역
- [ ] [실행] 버튼 — **예상 비용을 확인하기 전에는 비활성화**
- [ ] 검증 에러 메시지 표시 영역 (400 응답)

**SweepMatrixPanel**

- [ ] 스윕 헤더: 이름 / 상태 배지 / 진행률(completed/total) / 실제 비용
- [ ] **judge 모델명 상시 병기** (Plan R-2 완화)
- [ ] temperature·테스트셋명·케이스 수 표시
- [ ] 매트릭스 표 — 행=모델, 열=선택 메트릭 + 비용 + p50 + p95 + 도구 F1
- [ ] 지표별 **최고값 하이라이트**(★ 또는 배경색)
- [ ] `null` 지표는 **"—"(N/A)** 로 렌더 (0으로 표시 금지)
- [ ] 실패한 run 행: `실패` 배지 + `error_message` 툴팁, **다른 행은 정상 렌더**
- [ ] 실행 중: 행별 진행 스피너 + 3초 폴링
- [ ] 예상 비용 vs 실제 비용 대조 표시
- [ ] 빈 상태: "아직 스윕이 없습니다" 안내

---

## 6. Error Handling

### 6.1 Error Code Definition

| 상황 | HTTP | 처리 |
|---|---|---|
| 모델 6개 이상 선택 | 400 | `SweepPolicy.validate` → `ValueError` → `_raise_eval_error` (기존 패턴) |
| 선택 모델 중 비활성 포함 | 400 | 모델명 명시한 메시지 |
| judge 모델 비활성/미존재 | 400 | 동일 |
| 테스트셋 케이스 0건 | 400 | 동일 |
| 에이전트/테스트셋 미소유 | 404 | **403 아닌 404로 은닉** (`eval_router.py` 선례) |
| 개별 case 실행 실패 | — | 해당 result 저장 스킵 + `failed_cases` 증가, **run 계속** |
| 개별 run(모델) 실패 | — | `run.status=failed` + `error_message`, **스윕 계속** (G5) |
| judge 채점 실패 | — | 품질 지표만 `null`, 비용·지연·도구 지표는 유지 |
| `ai_run` 조회 실패 | — | 비용·지연만 `null`, 품질·도구 지표는 유지 |
| 스윕 전체 실패 | — | `sweep.status=failed` + `error_message` |

### 6.2 Error Response Format

기존 `ragas_router._raise_eval_error` 형식을 그대로 따른다.

```json
{ "detail": "스윕당 모델은 최대 5개입니다 (선택: 7개)" }
```

### 6.3 부분 실패 원칙

**전부 아니면 전무(all-or-nothing)를 채택하지 않는다.** 스윕의 가치는 비교이고, 5개 중 4개만 성공해도 4개 비교는 성립한다. 실패는 행 단위로 격리하고 매트릭스에 그대로 노출한다 — 실패 사실 자체가 그 모델에 대한 평가 정보다.

---

## 7. Security Considerations

| 항목 | 설계 |
|---|---|
| **소유권** | 스윕 조회·삭제는 `user_id` 일치 시에만. 관리자는 전체. 미소유 시 **404 은닉**(존재 여부 노출 금지) |
| **에이전트 접근** | 스윕 생성 시 `RunAgentUseCase._authorize_and_load`의 기존 권한 검사를 그대로 통과해야 한다 — 스윕이 권한 우회 경로가 되면 안 된다 |
| **비용 남용** | 모델 수 ≤5 + 테스트셋 케이스 수 상한(기존 정책 준수) + 사전 비용 표시로 완화. 실행 전 확인은 UI 게이트 |
| **API 키** | `llm_model.api_key_env`는 write-only 유지 — 스윕 응답에 절대 포함하지 않는다 |
| **judge 주입** | judge는 **모델 ID**로만 받는다. 모델명 문자열을 그대로 LLM 팩토리에 흘리지 않아 임의 엔드포인트 호출을 차단한다 |
| **PII** | 테스트셋·답변은 기존 평가와 동일한 취급. 신규 노출면 없음 |

---

## 8. Test Plan

### 8.1 Test Scope

| 레벨 | 범위 |
|---|---|
| 단위 | `SweepPolicy`, `ToolAccuracyPolicy`, 비용 추정 계산, 집계(N/A 제외) 로직 |
| 통합 | `CreateSweepUseCase`, `SweepExecutor` 순차·부분실패, 오버라이드 반영 |
| **회귀** | `RunAgentRequest` 소비자 8곳 무변경 (**최우선**) |
| L1 API | 5개 엔드포인트 |
| L2 UI | 스윕 생성 모달 · 매트릭스 |
| L3 E2E | 생성 → 폴링 → 매트릭스 전체 여정 |

### 8.2 L1: API Test Scenarios

| # | 시나리오 | 기대 |
|---|---|---|
| L1-1 | `POST /sweeps/estimate` 정상 | 200 + `estimated_cost_usd` > 0 + `per_model` 길이 = 모델 수 |
| L1-2 | `POST /sweeps` 모델 6개 | 400 + "최대 5개" |
| L1-3 | `POST /sweeps` 비활성 모델 포함 | 400 |
| L1-4 | `POST /sweeps` 정상 | 202 + `total_runs` = 모델 수 + `evaluation_run` N행 생성 |
| L1-5 | `POST /sweeps` 미소유 테스트셋 | **404** (403 아님) |
| L1-6 | `GET /sweeps/{id}` 완료 스윕 | 200 + `rows` 길이 = 모델 수 + 각 행에 4축 |
| L1-7 | `GET /sweeps/{id}` 타인 스윕 | 404 |
| L1-8 | `DELETE /sweeps/{id}` | 204 + 하위 `evaluation_run` CASCADE 삭제 확인 |
| L1-9 | `GET /admin/ragas/dashboard` | **스윕 run이 통계에서 제외됨** (D8) |
| L1-10 | `GET /ragas/runs` | 기존 필드 전부 유지 + `sweep_id`/`llm_model` 추가 |
| L1-11 | 미인증 요청 | 401 |

### 8.3 L2: UI Action Test Scenarios

| # | 액션 | 기대 |
|---|---|---|
| L2-1 | [+ 모델 스윕] 클릭 | 모달 오픈, temperature 0.0 읽기전용 표시 |
| L2-2 | 모델 6개째 체크 시도 | 체크 불가 + "최대 5개" 안내 |
| L2-3 | 예상 비용 확인 전 [실행] | 버튼 비활성 |
| L2-4 | [예상 비용 확인] | `/sweeps/estimate` 호출 + "추정치" 라벨 렌더 |
| L2-5 | [실행] | `/sweeps` POST + 목록에 pending 행 |
| L2-6 | 완료 스윕 선택 | 매트릭스 렌더 + 지표별 최고값 하이라이트 |
| L2-7 | 실패 run 포함 스윕 | 실패 행은 배지+에러, **나머지 행은 정상 렌더** |
| L2-8 | `null` 지표 | **"—"** 렌더 (0 아님) |
| L2-9 | judge 모델명 | 매트릭스 헤더에 상시 표시 |

### 8.4 L3: E2E Scenario Test Scenarios

| # | 여정 | 기대 |
|---|---|---|
| L3-1 | 로그인 → 평가 실행 탭 → 스윕 생성(모델 2개, 케이스 2건) → 폴링 → 매트릭스 확인 | 끝까지 오류 없이 완료, 두 모델 행 모두 지표 채워짐 |
| L3-2 | 동일 조건 스윕 2회 실행 | 품질 평균 편차 ≤ 5%p (재현성 NFR) |
| L3-3 | 존재하지 않는 엔드포인트 모델 포함 스윕 | 해당 행만 실패, 나머지 정상 완료 |

### 8.5 Seed Data Requirements

| 데이터 | 내용 |
|---|---|
| 에이전트 | 도구 1개 이상 부착된 에이전트 1개 |
| 테스트셋 | 케이스 3건 — 그중 2건은 `expected_tools` 포함, 1건은 미포함(N/A 검증용) |
| LLM 모델 | 활성 3개(단가 등록 2개 + 단가 미등록 1개) + 비활성 1개(400 검증용) |
| 실패 유발 모델 | `base_url`이 닿지 않는 self-host 모델 1개 (L3-3용) |

---

## 9. Clean Architecture

### 9.1 Layer Structure

```
idt/src/
├── domain/eval_sweep/
│   ├── entity.py          EvaluationSweep, SweepRow(집계 VO)
│   ├── policies.py        SweepPolicy, ToolAccuracyPolicy
│   └── interfaces.py      SweepRepositoryInterface
├── application/eval_sweep/
│   ├── schemas.py         Create/Estimate/Detail DTO
│   ├── use_cases.py       CreateSweep / EstimateSweepCost / GetSweepDetail / ListSweeps / DeleteSweep
│   └── sweep_executor.py  순차 오케스트레이션 (BatchEvalExecutor 구성요소 재사용)
├── infrastructure/eval_sweep/
│   ├── models.py          EvaluationSweepModel
│   └── repository.py      SweepRepository (집계 쿼리 포함)
└── api/routes/ragas_router.py   (+ /sweeps 5개 엔드포인트)
```

### 9.2 Dependency Rules

```
interfaces ──▶ application ──▶ domain
                    │
infrastructure ─────┘  (interfaces 구현으로만 역방향 연결)

domain ──✗──▶ infrastructure     (금지)
domain ──✗──▶ LangChain          (금지)
```

`ToolAccuracyPolicy`는 순수 집합 연산이라 도메인에 안전하게 놓인다. 비용 추정은 `llm_model` 단가 조회가 필요하므로 **application**에 둔다(도메인이 리포지토리를 직접 부르지 않도록).

### 9.3 This Feature's Layer Assignment

| 파일 | 레이어 | 책임 | 금지 |
|---|---|---|---|
| `domain/eval_sweep/policies.py` | domain | 모델 수 제한, 도구 F1 계산 | DB·LLM 접근 |
| `application/eval_sweep/use_cases.py` | application | 흐름 제어, 검증 호출, 트랜잭션 경계 | 비즈니스 규칙 직접 구현 |
| `application/eval_sweep/sweep_executor.py` | application | 순차 실행 오케스트레이션 | 규칙 판단 |
| `infrastructure/eval_sweep/repository.py` | infrastructure | ORM·집계 SQL | commit/rollback 호출 |
| `api/routes/ragas_router.py` | interfaces | 요청/응답 변환, 인증 | 비즈니스 로직 |

### 9.4 DB 세션 규약 (`docs/rules/db-session.md`)

- Repository 내부에서 `commit()`/`rollback()` **호출 금지** — UseCase가 트랜잭션 경계를 잡는다.
- 한 UseCase 안에서 repository별 서로 다른 세션 사용 **금지**.
- `SweepExecutor`는 백그라운드 태스크이므로 `SessionScopedEvalRunStore`와 동일하게 **run 단위로 세션을 새로 연다** (장기 실행 세션 점유 금지).

---

## 10. Coding Convention Reference

### 10.1 Naming Conventions

| 대상 | 규칙 | 예 |
|---|---|---|
| 테이블 | snake_case 단수 | `evaluation_sweep` |
| 컬럼 | snake_case | `judge_llm_model_id` |
| UseCase | `{동사}{대상}UseCase` | `CreateSweepUseCase` |
| Policy | `{대상}Policy` | `ToolAccuracyPolicy` |
| 프론트 컴포넌트 | PascalCase | `SweepMatrixPanel` |
| 프론트 훅 | `use{복수명}` | `useSweeps` |
| 지표 키 | snake_case | `tool_f1`, `latency_ms` |

### 10.2 This Feature's Conventions

- 함수 40줄 초과 금지 → `SweepExecutor._run`은 모델 루프와 케이스 루프를 별도 메서드로 분리한다.
- if 중첩 2단계 초과 금지 → N/A 판정은 조기 반환으로 처리한다.
- `print()` 금지, `logger` 필수. 스윕/런 상태 전이마다 `request_id` 포함 구조화 로그.
- 스택 트레이스 없는 에러 처리 금지 → `logger.exception` 사용.
- DDL COMMENT 필수 (V067·V068).
- 프론트: 컴포넌트 파일에서 런타임 상수 export 금지 → `src/types/sweep.ts`에 `as const`.

### 10.3 Environment Variables

신규 환경변수 **없음**. 모델·단가·judge는 전부 DB `llm_model`에서 조회한다.

> ⚠️ **`UTILITY_LLM_MODEL_NAME` 확인 사항**: 이 환경변수가 설정돼 있으면 `UtilityLLMProvider`가 관리자 기본 모델을 무시한다. 스윕의 judge는 **요청 파라미터로 명시 주입**되므로 이 경로를 타지 않아야 한다 — `RagasEvaluatorAdapter.evaluate(judge_model=...)`가 `UtilityLLMProvider`를 경유하지 않는지 Do 단계에서 반드시 확인할 것.

---

## 11. Implementation Guide

### 11.1 File Structure

**신규 (11)**

```
idt/
├── db/migration/V067__create_evaluation_sweep.sql
├── db/migration/V068__alter_evaluation_add_sweep_dimension.sql
├── src/domain/eval_sweep/{__init__,entity,policies,interfaces}.py     (4)
├── src/application/eval_sweep/{__init__,schemas,use_cases,sweep_executor}.py  (4)
└── src/infrastructure/eval_sweep/{__init__,models,repository}.py      (3)
   ※ __init__.py 3개 제외 시 실질 신규 8

idt_front/src/
├── pages/EvalDatasetPage/CreateSweepModal.tsx
├── pages/EvalDatasetPage/SweepMatrixPanel.tsx
├── hooks/useSweeps.ts
├── services/sweepService.ts
└── types/sweep.ts
```

**수정 (11)**

```
idt/src/
├── application/agent_builder/schemas.py          RunAgentRequest +3 Optional 필드
├── application/agent_builder/run_agent_use_case.py
│      ├─ _prepare_graph        모델·temperature 오버라이드 해석 (D1)
│      ├─ _begin_observability  agent_llm_model_id → 실효 모델 (FR-02)
│      └─ stream                persist_conversation=False 분기 (D2)
├── infrastructure/ragas/target_executor.py       AgentRunner 시그니처 확장
├── infrastructure/ragas/ragas_adapter.py         evaluate(judge_model=...) (D4)
├── infrastructure/ragas/models.py                sweep_id/llm_model_id/ai_run_id/tools_used
├── infrastructure/ragas/repository.py            dashboard 집계에 sweep_id IS NULL (D8)
├── application/ragas/batch_executor.py           judge 전달 + tools_used/ai_run_id 저장
├── api/routes/ragas_router.py                    /sweeps 5개 엔드포인트
├── api/main.py                                   DI 배선 + _run_agent_headless 확장
idt_front/src/
├── constants/api.ts                              RAGAS_SWEEPS* 상수
└── pages/EvalDatasetPage/RunsTab.tsx             [+ 모델 스윕] 버튼 + 스윕 섹션
```

### 11.2 Implementation Order

1. **DB** — V067·V068 작성 → ORM 모델 반영 → DDL COMMENT 테스트 통과
2. **오버라이드** — `RunAgentRequest` 필드 추가 → `_prepare_graph`/`_begin_observability`/`stream` 수정 → **소비자 8곳 회귀 테스트** (여기서 막히면 이후 전부 무의미)
3. **도메인** — `SweepPolicy`, `ToolAccuracyPolicy` + 단위 테스트 (순수 함수라 TDD 가장 쉬움)
4. **지표 수집** — `AgentRunner` 확장 → `batch_executor`에서 `tools_used`/`ai_run_id` 저장 → judge 주입
5. **스윕** — repository → use_cases → sweep_executor → router
6. **프론트** — types → service → hook → CreateSweepModal → SweepMatrixPanel → RunsTab 연결
7. **대시보드 필터** — `sweep_id IS NULL` 적용 + 회귀 확인

### 11.3 Session Guide

**Module Map**

| Scope Key | 모듈 | 산출물 | 선행 |
|---|---|---|---|
| `module-1` | DB 스키마 | V067, V068, ORM 모델 | — |
| `module-2` | 모델 오버라이드 | `RunAgentRequest` + `run_agent_use_case` 3개 메서드 + 회귀 테스트 | module-1 |
| `module-3` | 도메인 정책 | `SweepPolicy`, `ToolAccuracyPolicy` + 단위 테스트 | — (병행 가능) |
| `module-4` | 지표 수집 | `AgentRunner` 확장, `batch_executor`, judge 주입 | module-2, module-3 |
| `module-5` | 스윕 백엔드 | repository, use_cases, sweep_executor, router, DI | module-4 |
| `module-6` | 프론트 | types, service, hook, 모달, 매트릭스, RunsTab | module-5 |
| `module-7` | 대시보드 필터 | `sweep_id IS NULL` + 회귀 | module-1 |

**Recommended Session Plan**

| 세션 | Scope | 근거 |
|---|---|---|
| 1 | `--scope module-1,module-3` | DB와 순수 정책은 의존이 없어 함께 끝내기 좋다 |
| 2 | `--scope module-2` | **최대 리스크 구간.** 회귀 테스트에 집중하려면 단독 세션이 옳다 |
| 3 | `--scope module-4,module-5` | 지표 수집과 스윕 백엔드는 결합도가 높다 |
| 4 | `--scope module-6,module-7` | 프론트 + 대시보드 마무리 |

---

## 12. Key Design Decisions (Decision Record)

| ID | 결정 | 대안 | 근거 |
|---|---|---|---|
| **D1** | 모델 오버라이드는 `_prepare_graph` **단일 지점** | 그래프 컴파일러 / LLM 팩토리 / 에이전트 복제 | `_prepare_graph`가 `find_by_id(agent.llm_model_id)`와 `temperature=agent.temperature`를 모두 쥔 유일한 지점(`run_agent_use_case.py:547-562`). 두 줄 수정으로 끝나고 하위 컴포넌트는 오버라이드를 몰라도 된다 |
| **D2** | 평가 실행은 `persist_conversation=False`로 **대화 저장 생략** | 저장 후 필터링 / 현상 유지 | 스윕은 세션 100개를 만든다. `ai_run.user_message_id`는 nullable(V021)이라 관측은 그대로 남는다 |
| **D3** | `evaluation_sweep` **부모 테이블 신설** | run에 컬럼만 추가 | judge·temperature·모델목록 스냅샷을 run마다 중복 저장하지 않고 한 곳에 박제 — 재현성 기록의 단일 지점 |
| **D4** | judge 모델은 **호출별 주입** + run에 기록 | DI 고정 / is_default 추종 | 사용자 결정 #5. 기본값 유지로 실시간 평가 경로는 무영향 |
| **D5** | 지표는 **per-case JSON 저장 + 조회 시 집계** | run에 집계 컬럼 신설 | 기존 `evaluation_result.metrics` 패턴 재사용, 스키마 변경 최소화. 집계 정의가 바뀌어도 재적재 불필요 |
| **D6** | 도구 정확도는 **집합 F1**(순서 무시) | 시퀀스 일치 | 사용자 결정 #6. 동등한 대안 경로를 오답 처리하지 않는다 |
| **D7** | **순차 실행**, 모델 5개 상한 | 병렬 | 병렬은 지연 측정을 서로 오염시키고 rate limit에 걸린다 (사용자 결정 #7·#8) |
| **D8** | 관리자 대시보드는 **`sweep_id IS NULL` 필터** | 포함 / 토글 | 스윕은 실험이라 운영 품질 통계에 섞이면 평균이 왜곡된다 (Plan R-8 해소) |
| **D9** | temperature **0.0 강제** | 에이전트 설정 추종 / 사용자 선택 | 재현성 NFR(편차 ≤5%p)의 최소 조건 |
| **D10** | 비용·지연은 **`ai_run` 조인**으로 회수 | 자체 계측 | V021이 이미 정확히 적재 중. 중복 계측은 `idt/CLAUDE.md` 금지 |
| **D11** | `ai_run_id`에 **FK 걸지 않음** | FK + CASCADE | `ai_run`은 보존정책상 선삭제 가능. 관측 삭제가 평가 결과를 지우면 안 된다 |
| **D12** | 부분 실패 허용 (행 단위 격리) | all-or-nothing | 5개 중 4개 성공해도 4개 비교는 성립한다. 실패 사실 자체가 평가 정보다 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1.0 | 2026-08-31 | 최초 작성 — 설계안 C 선택, Decision Record 12건, Checkpoint 3 결정 4건 반영 | 배상규 |
