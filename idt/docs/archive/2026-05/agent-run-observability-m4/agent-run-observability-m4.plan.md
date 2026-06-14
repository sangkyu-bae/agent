# Plan: agent-run-observability-m4

> Feature: Agent Run 운영 관측성 — **M4 (Retrieval Wiring + Query API + Pricing PATCH)**
> Created: 2026-05-21
> Status: Plan
> Task ID: AGENT-OBS-004
> Parent: [agent-run-observability.plan.md](../../archive/2026-05/agent-run-observability/agent-run-observability.plan.md) (M1 — archived, 96%)
> Sibling: [agent-run-observability-m2.plan.md](../../archive/2026-05/agent-run-observability-m2/agent-run-observability-m2.plan.md) (M2 — archived, 98%)
> Sibling: [agent-run-observability-m3.plan.md](../../archive/2026-05/agent-run-observability-m3/agent-run-observability-m3.plan.md) (M3 — archived, 99%)

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | M1·M2·M3 완료로 **데이터 레이어는 100%**(`ai_run / ai_run_step / ai_tool_call / ai_llm_call`) 채워지지만, 운영자가 데이터를 **읽을 길이 없다.** (1) `ai_retrieval_source` 테이블은 V021부터 존재하지만 INSERT 호출 0건 — RAG 답변의 근거 chunk 추적 불가. (2) 어드민/사용자가 "한 run의 실행 트리"를 화면에서 볼 API 부재 — DB SQL 콘솔 외 접근 불가. (3) 사용자별/LLM별/**노드별** 사용량 집계 (M3가 만든 `step_id` JOIN 효과)가 API화 안 됨. (4) 관리자가 LLM 가격을 변경할 PATCH API 부재 — M1 G1 carry-over (가격 캐시 invalidate 의무 미충족). |
| **Solution** | **wiring + 5 신규 router endpoint + 1 패치 router.** (a) `InternalDocumentSearchTool._format_results`에 `record_retrieval` best-effort 호출 추가 + `RunContext.step_id/tool_call_id` 자동 활용 (M3가 set/reset 완료). (b) 신규 `GET /api/v1/agents/runs/{run_id}` (run 상세 트리) + `GET /api/v1/admin/usage/users` + `GET /api/v1/admin/usage/llm-models` + `GET /api/v1/admin/usage/by-node` (★ M3 효과) + `GET /api/v1/usage/me`. 모든 read는 기존 Repository (`AgentRunRepository.find_*`) + `UsageAggregator` 재사용 — 도메인/인프라 변경 0. (c) `PATCH /api/v1/llm-models/{id}/pricing` 신규 + `UpdateLlmModelPricingUseCase` (가격 2 컬럼 + `pricing_updated_at` 업데이트 + `CostCalculator.invalidate(model_id)` 호출 의무). |
| **Function / UX Effect** | (1) **RAG 답변 근거 추적**: "이 답변에 인용된 chunk가 무엇인가?" → `ai_retrieval_source` SQL JOIN, (2) **Run 상세 트리 API**: 어드민이 한 run의 supervisor→worker→quality_gate→answer + 노드별 LLM/툴/검색 결과를 JSON으로 받음, (3) **노드별 사용량 차지백**: `GET /admin/usage/by-node?from=&to=` → `[{node_name, total_tokens, total_cost_usd}]` — "answer_agent가 비용 70% 차지" 같은 인사이트, (4) **사용자 셀프 사용량**: `GET /usage/me` → 본인의 누적 토큰/비용, (5) **가격 인플레/할인 즉시 반영**: 관리자가 PATCH 후 다음 LLM 호출부터 새 단가 적용 (캐시 무효화), (6) M2 tool_call의 step_id × M3 step_index 와 결합되어 어드민이 **3-tier 트리(run → step → tool/retrieval/llm)** 를 화면 1회 호출로 구성 가능. |
| **Core Value** | **"실행 원장 → 운영 가시성"의 완성.** M1·M2·M3는 DB에 데이터를 쌓는 파이프라인이었고, M4는 그 데이터를 외부로 노출하는 첫 인터페이스다. 이 후 `agent-run-admin-dashboard` / `agent-usage-dashboard`가 모두 M4 API만 호출하면 됨 — 화면 PDCA들이 백엔드 변경 없이 진행 가능. 신규 테이블·도메인·마이그레이션 0건, 신규 router 1개(+ 기존 llm_model_router 패치 1), 신규 use case 5건, 예상 2~3일. |

---

## 1. 목적 (Why)

### 1-1. M1·M2·M3 완료 후 남은 데이터 갭

| 영역 | M1·M2·M3 상태 | M4에서 채워야 할 것 |
|------|--------------|---------------------|
| `ai_retrieval_source` 테이블 | ✅ V021 생성, FK·인덱스 완비 | INSERT 호출 0건 |
| `RunTracker.record_retrieval()` | ✅ 구현됨 (M1) | **호출자 없음** — 모든 RAG 응답에서 근거 chunk 추적 불가 |
| `RunContext.tool_call_id` | ✅ M2 (callback-driven set/reset) | RAG 어댑터가 활용 안 함 |
| `RunContext.step_id` | ✅ M3 (graph-wrapping set/reset) | RAG 어댑터가 활용 안 함 |
| `GET /agents/runs/{run_id}` (run 상세) | ❌ 미정의 | run + steps + tool_calls + retrievals + llm_calls 트리 반환 |
| `GET /admin/usage/users` | ❌ 미정의 | `UsageAggregator.by_user()` 노출 |
| `GET /admin/usage/llm-models` | ❌ 미정의 | `UsageAggregator.by_llm_model()` 노출 |
| `GET /admin/usage/by-node` | ❌ 미정의 (★ M3 효과) | `SELECT s.node_name, SUM(l.*) FROM ai_llm_call l JOIN ai_run_step s ON s.id=l.step_id GROUP BY s.node_name` |
| `GET /usage/me` | ❌ 미정의 | `UsageAggregator.for_user(self_user_id)` |
| `PATCH /llm-models/{id}/pricing` | ❌ 미정의 (M1 G1 carry-over) | 가격 2 컬럼 + `pricing_updated_at` + `CostCalculator.invalidate(id)` 의무 호출 |

### 1-2. 운영 니즈

- **RAG 답변 책임 추적**: 금융/정책 도메인 — "이 답변이 인용한 문서가 무엇이고 어느 chunk였나"를 사후 1회 SQL로 확인. 현재 답변 텍스트에 `[출처: file.pdf]`만 박혀 있고 chunk_id/score/rank를 DB에서 끌어올 길 없음
- **실패 run 디버깅**: 어드민이 한 run의 노드별 latency/status/error를 한 API 호출로 받아 UI에 표시 — 현재는 DB 4개 테이블 JOIN 수동 작성 필요
- **부서별 차지백 준비**: 사용자 → user_id → department 매핑을 거쳐 부서별 비용 산출 (M4는 사용자/LLM/노드 분리까지 — 부서 mapping은 후속)
- **노드별 비용 최적화**: "answer_agent 비용이 worker 합보다 큰가?" → `/admin/usage/by-node` 로 5초 안에 확인. answer prompt 줄이기 / 모델 다운그레이드 의사결정 근거
- **셀프 서비스 가시성**: 사용자가 본인 토큰 사용량을 직접 확인 → 무리한 사용 사전 자제
- **가격 변동 반영**: OpenAI 가격 인하/인상 발표 시 관리자가 즉시 반영 + 캐시 무효화 — 현재 가격은 DB만 보고 cache는 5분 TTL 동안 stale

### 1-3. 비목표 (Non-Goals)

- 신규 테이블 / 도메인 entity / VO / Repository interface 추가 (M1 완성)
- DB 마이그레이션 추가
- 어드민 UI / 사용자 대시보드 화면 (별도 PDCA `agent-run-admin-dashboard` / `agent-usage-dashboard`)
- 부서별 집계 / 차지백 화면 (별도 PDCA)
- WebSocket / Server-Sent Event 기반 실시간 run 스트리밍 (별도)
- `tavily_search` 결과의 retrieval 영속화 (M4 In Scope 후보 — Design 단계에서 우선순위 확정)
- Excel export of usage reports (별도)
- 다중 조건 필터 (검색어 / 부서 / 모델 family 등) — M4는 기본 from/to + 페이지네이션만
- Retention/anonymization 정책 (별도 컴플라이언스 PDCA)
- LangSmith trace URL 통합 노출 (이미 M1에서 ai_run에 컬럼 존재 — M4에서 응답에 포함만)

---

## 2. 기능 범위 (Scope)

### In Scope

| 영역 | 항목 |
|------|------|
| **RAG retrieval wiring** | `InternalDocumentSearchTool._format_results` 마지막에 best-effort `record_retrieval(run_id, tool_call_id=RunContext.tool_call_id, collection_name, document_id, chunk_id, score, rank_index, content_preview[:500])` 루프. RunContext가 None이면 skip (graph 외 호출용). RAGToolConfig·SearchMode 분기와 무관하게 동작 |
| **Run 상세 조회 API** | `GET /api/v1/agents/runs/{run_id}` → `{run, steps[], tool_calls[], retrievals[], llm_calls[]}` 트리. 권한: 본인 run 또는 admin. 404 if not found, 403 if 본인 아님 + non-admin |
| **사용량 집계 API (admin)** | `GET /api/v1/admin/usage/users?from=&to=` / `/llm-models?from=&to=` / `/by-node?from=&to=` — 모두 `UsageAggregator` 또는 신규 `aggregate_by_node()` 호출. ISO8601 datetime, default = 최근 30일 |
| **사용자 셀프 사용량** | `GET /api/v1/usage/me?from=&to=` — `UsageAggregator.for_user(current_user.id, from, to)` |
| **노드별 집계 (★ M3 효과)** | `LlmCallRepositoryInterface.aggregate_by_node(from, to)` 추가 — `SELECT s.node_name, SUM(l.total_tokens), SUM(l.total_cost_usd), COUNT(*) FROM ai_llm_call l JOIN ai_run_step s ON s.id=l.step_id WHERE l.created_at BETWEEN ? AND ? GROUP BY s.node_name`. `NodeUsageRow` dataclass 도메인에 추가 (UserUsageRow/LlmUsageRow와 동급) |
| **LLM 가격 변경 API** | `PATCH /api/v1/llm-models/{id}/pricing` → `{input_price_per_1k_usd, output_price_per_1k_usd}` body. `UpdateLlmModelPricingUseCase`가 DB 갱신 + `pricing_updated_at=NOW()` + `CostCalculator.invalidate(model_id)` 호출. 권한 admin |
| **응답 schema** | `RunDetailResponse` / `UsageByUserResponse` / `UsageByLlmResponse` / `UsageByNodeResponse` / `UpdatePricingRequest` / `LlmModelResponse` (가격 필드 노출 확장) — interfaces/schemas 또는 application/schemas 배치 |
| **TDD** | router 단위 + use case 단위 + Repository (`aggregate_by_node`) SQL 검증 |

### Out of Scope (후속 PDCA)

- 어드민 UI / 차지백 화면 (`agent-run-admin-dashboard`, `agent-usage-dashboard`)
- 부서별 집계 (`user_id → department` 조인 필요 — 별도 mapping 정책)
- `tavily_search` retrieval 영속화 — Design 단계에서 우선순위 결정 (Tavily 결과의 "근거 chunk" 의미가 RAG vs Web Search에서 다름)
- run/step/tool/retrieval/llm row의 TTL/정리 정책
- 페이지네이션 (M4는 기본 limit/offset 또는 무한 정렬 — admin은 from/to 좁히면 충분 가정)
- Excel/CSV export
- Cost calculator의 통화 변환 / KRW 표시
- LLM 가격 history 테이블 (현재는 `pricing_updated_at` 1 컬럼만 — 변경 이력 보존 별도)

---

## 3. 기술 의존성

| 모듈 | Task ID / 상태 | M4 영향 |
|------|----------------|---------|
| `RunTracker.record_retrieval` | AGENT-OBS-001 (M1) ✅ | **호출자 추가만** (Tracker 자체 변경 없음) |
| `RunContext.tool_call_id` / `step_id` | AGENT-OBS-002·003 ✅ | 활용 (이미 set/reset) |
| `AgentRunRepository.find_run / find_steps / find_tool_calls / find_retrievals` | AGENT-OBS-001 (M1) ✅ | 활용 (이미 존재) |
| `LlmCallRepository.find_by_run / aggregate_by_user / aggregate_by_llm_model / aggregate_user_x_llm` | AGENT-OBS-001 (M1) ✅ | 활용 + **`aggregate_by_node` 신규 추가** |
| `UsageAggregator` | AGENT-OBS-001 (M1) ✅ | **`by_node()` 메서드 1개 추가** |
| `CostCalculator.invalidate` | AGENT-OBS-001 (M1) ✅ | 활용 (이미 존재 — M4가 첫 호출자) |
| `LlmModelRepository.update` (가격 컬럼) | LLM-MODEL-REG-001 ✅ | 활용 (이미 갱신 가능, schema에 PATCH 추가만) |
| `get_current_user` / `require_role("admin")` | 기존 | 활용 |
| `InternalDocumentSearchTool` | 기존 (RAG 모듈) | `_format_results` 안에 best-effort hook 1군데 추가 |
| 신규 외부 라이브러리 | — | **없음** |

---

## 4. 아키텍처 결정 (Strategy)

### 4-1. RAG retrieval 영속화 진입점 선택

| 옵션 | 위치 | 장점 | 단점 |
|------|------|------|------|
| A: `InternalDocumentSearchTool._arun` | 도구 함수 본문 직접 호출 | 명확 (RAG 결과 즉시 INSERT) | tool 인스턴스가 tracker DI 받아야 함 → ToolFactory 시그니처 확장 |
| ✅ **B: `_format_results` 안 best-effort 호출 (M4 채택)** | 동일 도구, 호출 지점만 results 루프 안 | tool 인스턴스가 `RunContext`에서 자동으로 run_id/tool_call_id 획득 → **factory/spec 변경 0건** | 결과 포맷팅과 영속화가 동일 메서드에 혼재 (10줄 추가) |
| C: callback-driven (`on_tool_end`) | UsageCallback hook | M2와 일관 | tool result string 파싱이 필요 → 깨지기 쉽고 RAG-specific |
| D: HybridSearchUseCase 안에서 영속화 | application layer 깊은 곳 | 모든 호출 경로 캐치 | UseCase가 Tracker 알게 됨 (계층 책임 혼재), RunContext 없는 path도 INSERT 시도 |

**결정**: 옵션 B. M2가 callback-driven으로 동작했던 이유는 LangChain BaseTool standard hook 활용 가능했기 때문. retrieval 결과는 RAG-specific 구조이므로 도구 안에서 직접 처리하는 게 명확. `RunContext.get_current_run_context()` 활용으로 ToolFactory/spec 변경 0건 — M3에서 `RunContext.step_id`, M2에서 `tool_call_id`가 이미 자동 채워져 있으므로 도구는 read만 하면 된다. **tavily_search retrieval은 Design 단계에서 우선순위 결정**.

### 4-2. Run 상세 조회 응답 구조

```jsonc
GET /api/v1/agents/runs/{run_id}
{
  "run": { "id": "...", "status": "SUCCESS", "started_at": "...", "ended_at": "...",
           "latency_ms": 12340, "token_usage": {...}, "cost_usd": {...},
           "llm_call_count": 4, "user_id": "...", "agent_id": "...",
           "langsmith_trace_id": "...", "langsmith_run_url": "..." },
  "steps": [
    { "id": "...", "step_index": 1, "node_name": "supervisor", "node_type": "SUPERVISOR",
      "status": "SUCCESS", "input_summary": "...", "output_summary": "...",
      "started_at": "...", "ended_at": "...", "latency_ms": 45,
      "llm_calls": [ { "id": "...", "purpose": "supervisor", "total_tokens": 234, "total_cost_usd": "0.0012" } ],
      "tool_calls": [],
      "retrievals": [] },
    { ... worker step with llm_calls + tool_calls + retrievals ... }
  ]
}
```

**서버측 조립 정책**: `AgentRunRepository.find_run` + `find_steps` + `find_tool_calls` + `find_retrievals` + `LlmCallRepository.find_by_run` 5회 DB 조회. application 레이어 `GetRunDetailUseCase`가 step_id/tool_call_id 키로 client-side join (성능 충분 — 한 run row ≤ ~20개). N+1 회피 — 모두 `find_*(run_id)`로 batch fetch.

### 4-3. 권한 정책

| 엔드포인트 | 권한 |
|-----------|------|
| `GET /agents/runs/{run_id}` | run.user_id == current_user.id **또는** current_user.role == admin. 그 외 403 |
| `GET /admin/usage/users` | admin only |
| `GET /admin/usage/llm-models` | admin only |
| `GET /admin/usage/by-node` | admin only |
| `GET /usage/me` | 인증된 사용자 본인 (current_user) |
| `PATCH /llm-models/{id}/pricing` | admin only |

`get_current_user` / `require_role("admin")` 의존성 재사용. **403/404 분기 명확화** — run not found → 404, run 존재하나 권한 없음 → 403 (information leak 방지 차원에서 404 통일 검토 — Design §11에서 확정).

### 4-4. 가격 변경 API 흐름

```
PATCH /api/v1/llm-models/{id}/pricing  body={input_price_per_1k_usd, output_price_per_1k_usd}
  ↓
UpdateLlmModelPricingUseCase.execute(id, request)
  ├─ repo.find_by_id(id) → 없으면 ValueError → 404
  ├─ model.input_price_per_1k_usd = req.input
  │  model.output_price_per_1k_usd = req.output
  │  model.pricing_updated_at = NOW(UTC)
  ├─ repo.update(model)
  └─ cost_calculator.invalidate(id)  ★ M1 G1 의무 충족
  ↓
return LlmModelResponse (가격 필드 포함)
```

**Design 결정 포인트**: `LlmModelResponse`에 가격 노출할지 — 현재 schema는 비노출. M4에서 `LlmModelWithPricingResponse` 별도 추가 vs 기존 schema 확장 — Design §5에서 확정.

### 4-5. 레이어 배치 (Thin DDD 준수)

```
src/domain/agent_run/
└── interfaces.py            ★ 수정 — LlmCallRepositoryInterface.aggregate_by_node + NodeUsageRow dataclass

src/application/agent_run/
├── aggregator.py            ★ 수정 — by_node() 메서드 1개 추가
├── schemas.py               ★ 수정 (선택) — RunDetailDto / UsageByNodeRow 등 application DTO (또는 interfaces/schemas)
└── use_cases/               ★ 신규 디렉토리
    ├── get_run_detail_use_case.py    ★ 신규
    ├── get_usage_by_user_use_case.py ★ 신규 (얇은 wrapper)
    ├── get_usage_by_llm_use_case.py  ★ 신규
    ├── get_usage_by_node_use_case.py ★ 신규
    └── get_usage_me_use_case.py      ★ 신규
※ 또는 use case 5개를 1개 파일 `query_use_cases.py`로 합치는 안 — Design §3에서 확정

src/application/llm_model/
└── update_llm_model_pricing_use_case.py  ★ 신규

src/infrastructure/persistence/repositories/
└── llm_call_repository.py   ★ 수정 — aggregate_by_node SQL 추가

src/api/routes/
├── agent_run_router.py      ★ 신규 — GET /agents/runs/{run_id}, GET /usage/me, GET /admin/usage/*
└── llm_model_router.py      ★ 수정 — PATCH /{id}/pricing 추가

src/interfaces/schemas/      또는  src/api/schemas/
└── agent_run_schemas.py     ★ 신규 — RunDetailResponse, UsageByXxxResponse, UpdatePricingRequest

src/api/main.py              ★ 수정 — 신규 router 등록 + use case DI 등록

# 변경 없음
src/domain/agent_run/entities.py / value_objects.py / policies.py
src/application/agent_run/tracker.py / context.py / cost_calculator.py
db/migration/                                  # 신규 0
```

**도메인 변경**: `NodeUsageRow` dataclass 1개 추가 (UserUsageRow/LlmUsageRow와 동급, 외부 의존 없음).

---

## 5. 데이터 모델

**변경 없음.** 모든 read는 M1 V021의 기존 컬럼만 사용. 신규 INSERT는 M1 V021의 `ai_retrieval_source` 빈 테이블에만 발생.

### 5-1. `record_retrieval` 호출 시 채워질 컬럼

| 컬럼 | 값 |
|------|-----|
| `id` | uuid4 (`record_retrieval` 내부) |
| `run_id` | `RunContext.run_id` |
| `tool_call_id` | `RunContext.tool_call_id` (M2가 set) |
| `collection_name` | `InternalDocumentSearchTool.collection_name` 또는 검색 결과 metadata에서 추출 |
| `document_id` | hit.metadata.get("document_id") (있으면) |
| `chunk_id` | `hit.id` (chunk PK) |
| `score` | `hit.score` |
| `rank_index` | results enumerate index (1-based) |
| `content_preview` | `hit.content[:500]` (config: `retrieval_preview_max_bytes`) |
| `metadata_json` | `hit.metadata` 전체 (source/page/section 등) |
| `created_at` | `record_retrieval` 시점 |

### 5-2. `aggregate_by_node` SQL

```sql
SELECT s.node_name,
       COUNT(*)                  AS call_count,
       SUM(l.prompt_tokens)      AS prompt_tokens,
       SUM(l.completion_tokens)  AS completion_tokens,
       SUM(l.total_tokens)       AS total_tokens,
       SUM(l.total_cost_usd)     AS total_cost_usd
FROM ai_llm_call l
JOIN ai_run_step s ON s.id = l.step_id
WHERE l.created_at >= :from AND l.created_at < :to
GROUP BY s.node_name
ORDER BY total_cost_usd DESC;
```

**중요**: `l.step_id` IS NULL인 행은 자연 제외 (M2 이전 row들, 또는 M3 wrapping 외 경로). 운영 정상.

### 5-3. `NodeUsageRow` 도메인 dataclass

```python
@dataclass(frozen=True)
class NodeUsageRow:
    node_name: str
    call_count: int
    total_tokens: int
    total_cost_usd: Decimal
```

---

## 6. 마일스톤 (M4 내부 작업 분할)

| 단계 | 범위 | 산출물 | 예상 |
|------|------|--------|------|
| **M4-1** | `InternalDocumentSearchTool._format_results`에 `record_retrieval` best-effort 호출 + 테스트 | tools.py 수정 + tests/.../test_internal_document_search_retrieval.py | 0.3일 |
| **M4-2** | `LlmCallRepositoryInterface.aggregate_by_node` + `NodeUsageRow` 도메인 추가 | interfaces.py + 단위 dataclass 테스트 | 0.2일 |
| **M4-3** | `SqlAlchemyLlmCallRepository.aggregate_by_node` SQL 구현 + 통합 테스트 (SQLite/mysql) | repository SQL + tests/.../test_aggregate_by_node.py | 0.3일 |
| **M4-4** | `UsageAggregator.by_node` 메서드 + 단위 테스트 | aggregator.py + 단위 1건 | 0.1일 |
| **M4-5** | `GetRunDetailUseCase` (5회 repo fetch + client-side join) + 단위 테스트 | use case + 단위 3건 | 0.4일 |
| **M4-6** | Usage 4개 use case (by_user / by_llm / by_node / me) — 얇은 wrapper | 1~4개 파일 + 단위 4건 | 0.2일 |
| **M4-7** | `UpdateLlmModelPricingUseCase` + cost_calculator.invalidate 호출 + 단위 테스트 | use case + 단위 3건 (정상/404/invalidate 호출 검증) | 0.3일 |
| **M4-8** | `agent_run_router.py` 신규 + 5 endpoint + Pydantic schemas + router 테스트 (FastAPI TestClient) | router 1개 + 통합 5건 | 0.4일 |
| **M4-9** | `llm_model_router.py` PATCH /pricing 추가 + 통합 테스트 | router 패치 + 통합 2건 | 0.2일 |
| **M4-10** | `api/main.py` DI 와이어링 (use case factory 6개) | main.py 수정 | 0.2일 |
| **M4-11** | 수동 검증 (실 LLM 1회 + 5 endpoint curl 라운드) | 검증 로그 캡처 | 0.4일 |

**총 예상**: 3.0일 (M3 견적의 약 2배 — M4는 wiring 1건 + read API 5건 + 가격 PATCH 1건).

---

## 7. 코드 통합 지점

| 파일 | 변경 내용 | 비고 |
|------|----------|------|
| `src/application/rag_agent/tools.py` | `_format_results` 안에 `record_retrieval` best-effort 루프 추가 (~10줄). `RunContext.get_current_run_context()`로 run_id/tool_call_id 획득, None이면 skip | RAG tool에 tracker DI 필요 — `tool_factory.py` 시그니처 1줄 확장 |
| `src/infrastructure/agent_builder/tool_factory.py` | `tracker` 파라미터 추가 + `internal_document_search` case에서 InternalDocumentSearchTool에 tracker 주입 | factory 호출자 (graph compile) 도 tracker 전달 |
| `src/application/agent_builder/workflow_compiler.py` | tool_factory 호출 시 tracker 전달 (M3가 이미 tracker DI 받음) | 1줄 |
| `src/domain/agent_run/interfaces.py` | `NodeUsageRow` dataclass + `LlmCallRepositoryInterface.aggregate_by_node(from, to) -> List[NodeUsageRow]` 추가 | abc method 1개 |
| `src/infrastructure/persistence/repositories/llm_call_repository.py` | `aggregate_by_node` SQL 구현 (UserUsageRow/LlmUsageRow 패턴 동일) | ~25줄 |
| `src/application/agent_run/aggregator.py` | `by_node(from, to)` 메서드 1개 추가 | 3줄 |
| `src/application/agent_run/use_cases/get_run_detail_use_case.py` ★ 신규 | run_id → AgentRunRepo.find_run/find_steps/find_tool_calls/find_retrievals + LlmCallRepo.find_by_run → 트리 dict 조립 | ~80줄. 권한 분기는 router에서 |
| `src/application/agent_run/use_cases/usage_query_use_cases.py` ★ 신규 | `GetUsageByUserUseCase / GetUsageByLlmUseCase / GetUsageByNodeUseCase / GetUsageMeUseCase` — 모두 aggregator wrapper | 4 class, 각 ~10줄 |
| `src/application/llm_model/update_llm_model_pricing_use_case.py` ★ 신규 | id + UpdatePricingRequest → repo.find_by_id → model 갱신 → repo.update → cost_calculator.invalidate(id) | ~40줄. cost_calc DI 필수 |
| `src/api/routes/agent_run_router.py` ★ 신규 | `prefix=/api/v1`, 5 endpoint, Pydantic schemas | ~150줄 (5 endpoint + DI placeholders + response models) |
| `src/api/routes/llm_model_router.py` | PATCH /{id}/pricing endpoint 추가 + DI placeholder | ~20줄 |
| `src/application/llm_model/schemas.py` | `UpdatePricingRequest` + `LlmModelWithPricingResponse` (또는 기존 schema에 가격 필드 추가 — Design 결정) | ~10줄 |
| `src/api/main.py` | 6 use case factory + 신규 router include + `UpdateLlmModelPricingUseCase` cost_calc DI | ~30줄 |
| `tests/api/test_agent_run_router.py` ★ 신규 | run detail + 4 usage endpoint 통합 테스트 (~8건) | TestClient + override_get_session |
| `tests/api/test_llm_model_router_pricing.py` ★ 신규 | PATCH /pricing 통합 테스트 (~3건: 정상 200 / 권한 403 / not found 404) | |
| `tests/application/rag_agent/test_internal_document_search_retrieval.py` ★ 신규 | `record_retrieval` 호출 검증 (~4건) | mock tracker |
| `tests/application/agent_run/test_aggregate_by_node.py` ★ 신규 | repository SQL 결과 검증 (~3건) | SQLite or testcontainer |
| `tests/application/agent_run/test_get_run_detail_use_case.py` ★ 신규 | tree assembly + N+1 회피 + empty branch | ~5건 |
| `tests/application/llm_model/test_update_pricing_use_case.py` ★ 신규 | DB 갱신 + invalidate 호출 검증 + not-found | ~3건 |
| DB 마이그레이션 | **없음** | 0건 |

---

## 8. TDD 계획

### 8-1. RAG retrieval wiring (~4 cases)

```
test_format_results_records_retrieval_per_hit_with_rank_index
test_format_results_skips_retrieval_when_runcontext_none
test_format_results_uses_tool_call_id_from_runcontext
test_record_retrieval_failure_does_not_break_tool_output  ★ best-effort
```

### 8-2. `aggregate_by_node` repository (~3 cases)

```
test_aggregate_by_node_returns_rows_grouped_by_node_name
test_aggregate_by_node_excludes_null_step_id
test_aggregate_by_node_respects_from_to_window
```

### 8-3. `GetRunDetailUseCase` (~5 cases)

```
test_returns_run_with_steps_tool_calls_retrievals_llm_calls
test_returns_404_when_run_not_found             ★ raises ValueError → router 404
test_tree_assembly_uses_5_repo_calls_max        ★ N+1 가드
test_step_with_no_llm_calls_returns_empty_array
test_retrievals_are_grouped_under_tool_call_step
```

### 8-4. Usage query use cases (~4 cases — 각 1)

```
test_get_usage_by_user_delegates_to_aggregator
test_get_usage_by_llm_delegates_to_aggregator
test_get_usage_by_node_delegates_to_aggregator
test_get_usage_me_uses_current_user_id
```

### 8-5. `UpdateLlmModelPricingUseCase` (~3 cases)

```
test_updates_pricing_columns_and_pricing_updated_at
test_calls_cost_calculator_invalidate_with_model_id  ★ M1 G1 핵심
test_raises_value_error_when_model_not_found
```

### 8-6. Router 통합 테스트 (~10 cases)

```
test_get_run_detail_returns_200_for_owner
test_get_run_detail_returns_403_for_other_user_non_admin
test_get_run_detail_returns_200_for_admin
test_get_run_detail_returns_404_when_not_found
test_get_admin_usage_users_requires_admin_role
test_get_admin_usage_llm_models_returns_200_for_admin
test_get_admin_usage_by_node_returns_200_for_admin
test_get_usage_me_returns_current_user_usage
test_patch_pricing_returns_200_and_invalidates_cache  ★ E2E 검증
test_patch_pricing_requires_admin_role
```

**핵심 회귀 가드**:
- `test_record_retrieval_failure_does_not_break_tool_output` — RAG 답변이 retrieval 실패로 깨지지 않음
- `test_calls_cost_calculator_invalidate_with_model_id` — M1 G1 명시 의무
- `test_get_run_detail_returns_403_for_other_user_non_admin` — 권한 안전성

---

## 9. CLAUDE.md 규칙 체크

- [x] domain 변경 최소 (`NodeUsageRow` dataclass 1개, abc method 1개) — application/infra는 의존 가능
- [x] application use case 5개 — repository / aggregator / cost_calc만 import. Tracker 직접 의존 없음
- [x] router는 비즈니스 로직 0 — use case 호출 + 권한 분기 + Pydantic 변환만
- [x] `InternalDocumentSearchTool`이 `RunContext` (application) import — 도구는 RAG application 모듈이므로 가능
- [x] Repository 내부 commit 금지 (DB-001) — `aggregate_by_node`는 read-only, session per use case 가정
- [x] LOG-001 LoggerInterface — RAG record_retrieval 실패 시 warning (M2 패턴 동일)
- [x] TDD 순서 — 8-1 ~ 8-6 모두 테스트 먼저
- [x] 함수 ≤40줄 — `GetRunDetailUseCase.execute` 약 30줄 목표 (조립 로직), 5 repo call은 직렬
- [x] if 중첩 ≤2 — 권한 분기는 early return으로 평탄화
- [x] config 하드코딩 금지 — `retrieval_preview_max_bytes`/`summary_text_max_bytes`는 M1 `RunObservabilityConfig` 재사용
- [x] DTO와 Pydantic schema 분리 — domain dataclass(NodeUsageRow) ≠ Pydantic Response (계층 책임 분리)
- [x] 한국어 도메인 / 영문 식별자 분리 유지

---

## 10. 위험 요소 및 대응

| 위험 | 영향 | 가능성 | 대응 |
|------|------|--------|------|
| `RunContext.tool_call_id`가 정확히 set되어 있어야 함 (M2 의존) | retrieval row가 tool_call_id NULL로 영속화 | Low | M2 wrapping이 모든 `BaseTool.ainvoke`에 set/reset. RAG 도구가 BaseTool 상속이므로 자동 적용. 통합 테스트로 검증 |
| `aggregate_by_node`에서 `l.step_id IS NULL` row 누락 | M3 이전 데이터·외부 LLM 호출이 집계 안 됨 | Resolved (Spec) | 정상 동작. 어드민 화면에 "step_id 없는 호출 N건"을 별도 footer로 표기는 후속 PDCA |
| `GetRunDetailUseCase`의 5회 repo 호출이 N+1 우려 | 한 화면 호출이 10+ DB query | Medium | `find_*(run_id)`로 한 번에 batch fetch (M1 repo 이미 그렇게 설계). step_id/tool_call_id join은 메모리 dict로 |
| `record_retrieval` 안에서 `metadata_json`이 비정상적으로 큰 경우 | TEXT 컬럼 길이 폭증 | Low | `metadata`는 dict 그대로 — 1KB 컷 적용 검토 (Design §5 결정). 현재 V021 `metadata_json` 컬럼이 JSON/TEXT인지 확인 |
| `record_retrieval`이 동기 코드 안에서 호출 | 도구가 async지만 일부 동기 path? | Low | `_format_results`는 호출 컨텍스트 async (`_arun` 안). asyncio task로 fire-and-forget 가능 |
| 가격 invalidate를 router에서 빼먹는 case 재발 (M1 G1 원인) | 캐시가 stale → cost 계산 오류 | Medium | use case 안에 `invalidate` 호출을 캡슐화 — router는 모름. 단위 테스트로 호출 검증 (8-5) |
| Run 상세에서 본인 아닌 run 정보 leak | 권한 우회 | Medium | `run.user_id == current_user.id` early return 패턴 + integration test (8-6) |
| Admin usage 집계 from/to 누락 시 무한 스캔 | DB 부하 | Medium | default = 최근 30일 (router level) + 1년 초과 시 422. ai_llm_call.created_at 인덱스 활용 |
| LlmModelResponse에 가격 필드 추가 시 기존 ListResponse 호환성 | API consumer 변화 가능 | Low | additive — 기존 필드 보존. front 변경 0 (옵셔널 필드) |
| `UpdateLlmModelPricingUseCase`가 cost_calc DI 받으면 layer 순환 | application→application | Low | cost_calc는 같은 application 레이어. M1 tracker가 cost_calc DI 받는 것과 동일 패턴 |
| 어드민 화면 PDCA가 응답 schema 변경 요구 | M4 API → 어드민 PDCA 손빔 | Medium | Design 단계에서 어드민이 필요로 할 필드 추론 (latency_ms, error_text, langsmith URL 등 모두 포함) |
| RetrievalSource.metadata_json 직렬화 오류 | JSON 컬럼 vs Python dict | Low | M1 repository가 이미 처리 — 회귀 가드만 |

---

## 11. 후속 PDCA (M4 이후)

- `agent-run-admin-dashboard`: 어드민 UI 화면 — Run list / Run detail (트리 시각화) / Usage 차트 (Recharts/D3). M4 API만 호출
- `agent-usage-dashboard`: 사용자 셀프 사용량 화면 + 부서 mapping (department_id) 화면. `/usage/me` + 부서 집계 API (별도)
- `agent-run-retention-policy`: ai_run / ai_run_step / ai_tool_call 등의 TTL / GDPR anonymization (별도 컴플라이언스)
- `agent-run-langsmith-link`: ai_run.langsmith_run_url을 어드민 UI에서 deep-link로 렌더
- `tavily_search` retrieval 영속화 (M4 In Scope 후보 — 결과 의미가 RAG와 달라 별도 검토)
- LLM 가격 history 테이블 (`ai_llm_pricing_history` — 변경 audit trail)
- 부서별 차지백 (`user → department` join + GROUP BY department_id)
- Excel/CSV export of usage reports
- M1 Plan §5-3 status enum 표기 동기화 (M3 carry-over)

---

## 12. 완료 기준 (DoD)

### 12.1 코드
- [ ] `InternalDocumentSearchTool._format_results` retrieval best-effort 호출
- [ ] `tool_factory.py` tracker 파라미터 + DI
- [ ] `LlmCallRepositoryInterface.aggregate_by_node` + `NodeUsageRow` 도메인 추가
- [ ] `SqlAlchemyLlmCallRepository.aggregate_by_node` SQL 구현
- [ ] `UsageAggregator.by_node` 메서드
- [ ] `GetRunDetailUseCase` + 4 usage use case + `UpdateLlmModelPricingUseCase`
- [ ] `agent_run_router.py` 신규 + 5 endpoint
- [ ] `llm_model_router.py` PATCH /{id}/pricing 추가
- [ ] `api/main.py` DI 와이어링
- [ ] Pydantic schemas (RunDetailResponse / UsageByXxxResponse / UpdatePricingRequest)

### 12.2 테스트
- [ ] retrieval wiring 4건 통과
- [ ] aggregate_by_node 3건 통과
- [ ] GetRunDetailUseCase 5건 통과
- [ ] 4 usage use case 단위 4건 통과
- [ ] UpdateLlmModelPricingUseCase 3건 통과 (**invalidate 호출 검증 포함**)
- [ ] router 통합 10건 통과
- [ ] M1·M2·M3 기존 테스트 100% 유지 (~200+ 회귀 0건)

### 12.3 수동 검증 (실 운영 환경)
- [ ] RAG 질문 1회 → `ai_retrieval_source` row N건 (top_k와 일치) + `tool_call_id` NOT NULL
  ```sql
  SELECT rs.rank_index, rs.collection_name, rs.score, LENGTH(rs.content_preview),
         tc.tool_name, s.node_name
    FROM ai_retrieval_source rs
    JOIN ai_tool_call tc ON tc.id = rs.tool_call_id
    JOIN ai_run_step s ON s.id = tc.step_id
   WHERE rs.run_id = ? ORDER BY rs.rank_index;
  ```
- [ ] `GET /api/v1/agents/runs/{run_id}` 응답: run / steps[] / 각 step 안 llm_calls/tool_calls/retrievals 트리 구성 확인
- [ ] `GET /api/v1/admin/usage/users?from=2026-05-01&to=2026-05-22` 응답: 사용자별 token/cost 정렬 확인
- [ ] `GET /api/v1/admin/usage/by-node` 응답: supervisor / worker_* / quality_gate / answer_agent 별 분리 — ★ M3 효과 첫 확인
- [ ] `GET /api/v1/usage/me` 응답: 본인 row만 반환 (다른 사용자 row 안 보임)
- [ ] `PATCH /api/v1/llm-models/{gpt-4o-id}/pricing` body={input_price_per_1k_usd: "0.005", output_price_per_1k_usd: "0.015"} → 200 + 다음 LLM 호출에서 새 단가 적용 확인 (서버 로그)
- [ ] 비-admin이 `/admin/*` 호출 → 403
- [ ] 다른 사용자의 run 조회 → 403
- [ ] retrieval 강제 예외 주입 → RAG 답변 정상 반환 (best-effort 검증)

### 12.4 문서 동기화
- [ ] M4 Design 문서 작성 (`docs/02-design/features/agent-run-observability-m4.design.md`)
- [ ] M3 §7.3 "M4 scope"와 본 Plan §2 In Scope 일치성 검증
- [ ] `tavily_search` retrieval 포함 여부를 Design §2에서 명시 결정
- [ ] `LlmModelResponse` 가격 필드 노출 여부 Design §5에서 확정
- [ ] 404 vs 403 통일 정책 Design §11에서 확정

---

## 13. 참고 자료

- 부모 Plan (M1): [agent-run-observability.plan.md](../../archive/2026-05/agent-run-observability/agent-run-observability.plan.md)
- M2 Plan: [agent-run-observability-m2.plan.md](../../archive/2026-05/agent-run-observability-m2/agent-run-observability-m2.plan.md) — `ai_tool_call.step_id` FK 사전 작업
- M3 Plan: [agent-run-observability-m3.plan.md](../../archive/2026-05/agent-run-observability-m3/agent-run-observability-m3.plan.md) — `ai_run_step` wiring + step_id context propagation
- M3 Report §7.3 (M4 scope 명시): [agent-run-observability-m3.report.md](../../archive/2026-05/agent-run-observability-m3/agent-run-observability-m3.report.md)
- M1 V021 schema: `db/migration/V021__create_agent_run_tables.sql`
- 핵심 원칙: **"읽기 전용 첫 노출"** (M4가 외부 API의 첫 표면 — 권한·페이로드 신중) + **"가격 변경 = invalidate 의무"** (M1 G1)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-05-21 | M4 초안 — Retrieval wiring + Run 상세 API + 4 usage API + 가격 PATCH. 신규 테이블/마이그레이션/도메인 entity 0건 | 배상규 |
