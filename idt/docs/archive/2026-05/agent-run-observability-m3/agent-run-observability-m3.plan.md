# Plan: agent-run-observability-m3

> Feature: Agent Run 운영 관측성 — **M3 (Run Step Wiring)**
> Created: 2026-05-21
> Status: Plan
> Task ID: AGENT-OBS-003
> Parent: [agent-run-observability.plan.md](./agent-run-observability.plan.md) (M1 — archived, 96%)
> Sibling: [agent-run-observability-m2.plan.md](../../archive/2026-05/agent-run-observability-m2/agent-run-observability-m2.plan.md) (M2 — archived, 98%)

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | M1에서 `ai_run_step` 테이블·`RunTracker.record_step()`·`UsageCallback.enter_step()/exit_step()`·`RunContext.with_step_id()` 모두 만들어 둔 상태에서 **`ai_run_step` 테이블이 비어 있다.** Supervisor → worker → quality_gate → answer 흐름이 LangGraph 노드 단위로 진행되지만 우리 DB에는 "한 run 안에서 어느 노드가 몇 번째로 실행됐고 얼마나 걸렸으며 supervisor가 어떤 워커를 어떤 이유로 골랐는지" 기록 0건. M1의 `_current_step_id`는 항상 None이라 **`ai_tool_call.step_id` / `ai_llm_call.step_id`도 모두 NULL** — 노드 단위 비용/성능 분석 불가. |
| **Solution** | **신규 테이블·도메인·인프라 0건 — 순수 wiring.** `src/application/agent_run/step_tracking.py`(신규)에 `async with track_step(...)` 컨텍스트 매니저 1개 만들고, `WorkflowCompiler`가 `add_node()` 호출 시 모든 노드(supervisor / worker / sub_agent / quality_gate / answer_agent / search)를 자동 wrapping. 컨텍스트 진입 시 `record_step(STARTED)` + `enter_step` + `RunContext.with_step_id` 갱신, 정상 종료 시 `update_step(SUCCESS)` + `exit_step` + 컨텍스트 복원, 예외 시 `update_step(FAILED)` 후 re-raise. step_index는 `UsageCallback._step_index` 단조 증가 카운터로 발급. 노드 함수 시그니처/상태 스키마 변경 0건. |
| **Function / UX Effect** | (1) **한 run의 노드 타임라인 SQL 조회** (`SELECT step_index, node_name, node_type, status, latency_ms FROM ai_run_step WHERE run_id=? ORDER BY step_index`), (2) **`ai_tool_call.step_id` / `ai_llm_call.step_id` 자동 채워짐** → "이 LLM 호출은 worker_finance 노드 안에서 일어났다"가 SQL JOIN으로 확인, (3) **노드별 비용/지연 통계** (`GROUP BY node_name`), (4) Supervisor `route_to_worker` 결정 reasoning이 `output_summary`에 저장 — 어드민이 "왜 이 워커를 골랐나"를 사후 추적 가능, (5) quality_gate retry 흐름도 step row로 분리 기록 → 품질 게이트 효율성 측정 근거. |
| **Core Value** | **"노드 실행 = 실행 원장"의 완성.** M1(LLM 호출 원장) + M2(툴 호출 원장) + M3(노드 실행 원장) = 한 run의 전체 실행 그래프(`ai_run → ai_run_step → ai_tool_call → ai_llm_call`)를 우리 DB만으로 재구성 가능. M4 Retrieval Source + 조회 API 구현 시 step 단위 그래프 노출만 남는다 — 데이터 레이어 단일 진실 공급원이 100% 채워진다. M2와 같이 wiring only로 1~2일 안에 완료 예상. |

---

## 1. 목적 (Why)

### 1-1. M1·M2 완료 후 남은 데이터 갭

| 영역 | M1·M2 상태 | M3에서 채워야 할 것 |
|------|-----------|---------------------|
| `ai_run_step` 테이블 | ✅ V021 생성, FK·인덱스 완비 | INSERT/UPDATE 호출 지점 0건 |
| `RunTracker.record_step()` / `update_step()` | ✅ 구현됨 | **호출자 없음** |
| `UsageCallback.enter_step(step_id)` / `exit_step()` | ✅ 구현됨 | **자동 호출 트리거 없음** (수동 호출 의무) |
| `RunContext.step_id` 필드 / `with_step_id()` | ✅ M1 존재 | 항상 None — 아무도 set 안 함 |
| `ai_tool_call.step_id` FK | ✅ V021 컬럼 + FK | **항상 NULL** (M2가 `_current_step_id`=None을 그대로 record_tool_call에 전달) |
| `ai_llm_call.step_id` FK | ✅ V021 컬럼 + FK | **항상 NULL** (동일 이유) |
| Supervisor decision reasoning 저장 | ❌ 미정의 | `output_summary`에 `decision.reasoning[:1024]` 저장 |
| step_index 발급 정책 | ❌ 미정의 | UsageCallback 단조 카운터 (M3 신규) |

### 1-2. 운영 니즈

- **노드 타임라인 시각화**: 어드민 화면에서 한 run을 "supervisor(45ms) → worker_finance(2.1s) → quality_gate(120ms) → answer_agent(800ms)"로 표시 — 느린 노드 식별
- **Supervisor 결정 추적**: "왜 worker_legal이 아니라 worker_finance를 골랐나?" → `output_summary`(decision.reasoning) 사후 조회
- **노드 단위 비용**: `SELECT node_name, SUM(l.total_cost_usd) FROM ai_llm_call l JOIN ai_run_step s ON l.step_id=s.id GROUP BY s.node_name` — answer_agent와 worker LLM 비용 비중 분리
- **Quality Gate 효율성**: retry가 몇 번 발생하는지, retry 후 통과율은? → `node_name='quality_gate'` row만 집계

### 1-3. 비목표 (Non-Goals)

- 신규 테이블 / 도메인 / VO / Repository 추가 (M1 완성)
- DB 마이그레이션 추가
- LangGraph 노드 함수의 시그니처/상태 스키마 변경
- 노드 함수 본문 비즈니스 로직 수정
- Supervisor `route_to_worker` / `route_after_quality` (조건 분기 함수) 자체는 step으로 기록하지 않음 — 순수 라우팅이라 의미 없음
- LangChain `on_chain_start/end` 광역 콜백 (BaseChainCallback 발화 빈도가 높아 노이즈 큼 — Risk §11 참조)
- 노드 input/output 전체 직렬화 (성능·스토리지 부담, summary 1KB 컷 유지)
- 어드민 UI / 조회 API (M4 범위)
- RAG retrieval source 영속화 (M4 범위)

---

## 2. 기능 범위 (Scope)

### In Scope

| 영역 | 항목 |
|------|------|
| **`step_tracking.py` 신규** | `async with track_step(tracker, callback, run_id, node_name, node_type, ...) as ctx:` 컨텍스트 매니저. enter 시 `record_step(STARTED)` + `enter_step(step_id)` + `RunContext.with_step_id` 갱신. exit 시 `update_step(SUCCESS/FAILED)` + `exit_step()` + 컨텍스트 복원 |
| **WorkflowCompiler 자동 wrapping** | `add_node(name, fn)` 직전에 `fn`을 `_with_step_tracking(name, node_type, fn)`로 감싸서 등록. 5종 노드 모두 자동 커버 (supervisor / worker / sub_agent / quality_gate / answer_agent / search) |
| **step_index 발급** | `UsageCallback._step_index: int` 단조 카운터. `enter_step()` 진입 시 `+= 1` |
| **node_type 매핑** | `supervisor` → SUPERVISOR / `quality_gate` → QUALITY_GATE / `answer_agent` → ANSWER (`NodeType.OTHER` 또는 신규 enum 값) / worker / sub_agent / search → WORKER |
| **Supervisor decision reasoning** | supervisor_node return dict에 `_step_output_summary` 키 추가 → wrapper가 update_step의 output_summary로 사용 (또는 wrapper가 SupervisorState 검사) |
| **input_summary / output_summary** | 1KB 컷 헬퍼. supervisor → state의 last user message[:1024], worker/answer → state messages count, quality_gate → quality_gate_result + retry_counts |
| **best-effort 보장** | record_step 실패 시 step_id=None → 노드는 정상 실행, `_current_step_id`도 None 유지 (M2와 동일 sentinel 패턴) |
| **예외 전파** | 노드가 raise → wrapper가 update_step(FAILED, error_text) 후 re-raise → fail_run에 자연 전파 |
| **TDD** | `tests/application/agent_run/test_step_tracking.py` 신규 + `tests/application/agent_builder/test_workflow_compiler_step_wrapping.py` 신규 + integration 보강 |

### Out of Scope (후속 마일스톤)

- **M4**: `ai_retrieval_source` INSERT — `internal_document_search` 어댑터에서 `record_retrieval()` 호출 (M3가 `RunContext.step_id` 채움 → M4가 이를 활용)
- **M4**: 조회 API (`GET /agents/runs/{run_id}` — step/tool/retrieval/llm 묶음 반환), `/admin/usage/by-node` 등
- **M4**: `PATCH /llm-models/{id}/pricing` + `CostCalculator.invalidate()` (M1 G1 후속)
- 어드민 대시보드 UI / 차지백 화면 (별도 PDCA)
- 노드 input/output 전체 직렬화 (별도 retention 정책 PDCA)
- LangGraph 동적 그래프 수정 (sub-graph 재귀 깊이별 분리 기록 등)
- 노드별 token budget enforcement (현재 SupervisorState `token_limit`은 graph 전역 — node-level 분리는 별도 PDCA)
- Orphan STARTED step row sweep 작업 (M4 운영 dashboard에서 detection 후 별도)

---

## 3. 기술 의존성

| 모듈 | Task ID / 상태 | M3 영향 |
|------|----------------|---------|
| `RunTracker.record_step` / `update_step` | AGENT-OBS-001 (M1) ✅ | **호출자 추가만** (Tracker 자체 변경 없음) |
| `UsageCallback.enter_step` / `exit_step` / `_current_step_id` | AGENT-OBS-001 (M1) ✅ | 단조 카운터 `_step_index` 1개 필드 추가 |
| `RunContext.with_step_id` | AGENT-OBS-001 (M1) ✅ | 활용 (이미 존재) |
| `NodeType` enum (SUPERVISOR / WORKER / GATE / OTHER) | AGENT-OBS-001 (M1) ✅ | ANSWER 값 추가 검토 (or OTHER 사용) |
| `WorkflowCompiler._wrap_worker` / `_wrap_sub_agent` | 기존 | wrapper chain에 `_with_step_tracking` 추가 (외부 호출자는 영향 없음) |
| `RunAgentUseCase` | 기존 | **수정 불요** (M1·M2가 이미 callback/tracker DI 완료) |
| LangChain / LangGraph | 0.3+ | **신규 의존성 없음** |

신규 외부 라이브러리: **없음.**

---

## 4. 아키텍처 결정 (Strategy)

### 4-1. 옵션 비교

| 방식 | 적용 위치 | M2 일관성 | 노이즈 | 노드 단위 정확도 |
|------|----------|----------|--------|----------------|
| ❌ A: 각 노드 함수 안에서 `await tracker.record_step(...)` 명시 호출 | supervisor_nodes.py + workflow_compiler.py 각각 | ❌ (M2가 폐기한 wrapping 패턴 재도입) | None | 100% |
| ❌ B: LangChain `on_chain_start/end` 광역 콜백 (M2 패턴 확장) | UsageCallback 한 곳 | ✅ (M2와 동일) | **매우 큼** — `with_structured_output`, RunnableSequence, 내부 prompt chain 모두 발화 | 메타데이터 필터 복잡, 노드 외 chain은 분리 불가 |
| ✅ **C: `WorkflowCompiler.add_node` 시점 decorator wrapping (M3 채택)** | workflow_compiler.py + 신규 step_tracking.py 한 곳 | ✅ (M2의 "단일 진입점" 정신 유지, 단 진입점이 callback이 아닌 graph 빌드 시점) | None (LangGraph node level만) | 100% + input/output 직접 추출 가능 |

**결정**: 옵션 C. M2가 callback-driven이었던 이유는 BaseTool의 표준 abstraction이 있었기 때문. LangGraph 노드는 함수일 뿐 표준 abstraction이 없으므로 **graph 빌드 시점에 wrapping**이 가장 명확. `WorkflowCompiler` 한 파일에 모든 `add_node` 호출이 모여 있으므로 진입점은 여전히 단일.

### 4-2. 호출 흐름

```
RunAgentUseCase.execute()
  └─ workflow = await compiler.compile(spec, callback=usage_callback, tracker=run_tracker, run_id=...)
       │
       │  WorkflowCompiler.compile() 내부 — 각 add_node 호출 직전 wrapping
       │  ┌─────────────────────────────────────────────────────────────┐
       │  │ supervisor_fn   → _with_step_tracking("supervisor",    SUPERVISOR,    supervisor_fn)
       │  │ worker_agent    → _with_step_tracking(worker_id,       WORKER,        worker_agent)
       │  │ sub_graph_fn    → _with_step_tracking(worker_id,       WORKER,        sub_graph_fn)
       │  │ quality_gate_fn → _with_step_tracking("quality_gate",  QUALITY_GATE,  quality_gate_fn)
       │  │ answer_node     → _with_step_tracking("answer_agent",  ANSWER,        answer_node)
       │  │ search_node     → _with_step_tracking(worker_id,       WORKER,        search_node)
       │  └─────────────────────────────────────────────────────────────┘
       │
       └─ graph.ainvoke(state, config={callbacks: [usage_callback]})
            └─ LangGraph supervisor 노드 진입
                 ↓
            🔔 _with_step_tracking wrapper 진입
                 ├─ async with track_step(tracker, callback, run_id,
                 │                        node_name="supervisor",
                 │                        node_type=NodeType.SUPERVISOR,
                 │                        input_summary=_summarize_state_input(state)) as step:
                 │      ├─ step_id = await tracker.record_step(STARTED, step_index=callback._step_index+1, ...)
                 │      ├─ callback.enter_step(step_id)  # _current_step_id 세팅, _step_index 증가
                 │      ├─ ctx = with_step_id(get_current_run_context(), step_id); set_current_run_context(ctx)
                 │      ↓
                 │      result = await supervisor_fn(state)
                 │      ↓
                 │      [노드 내부의 llm.ainvoke() → on_llm_end → record_llm_call(step_id=_current_step_id)]  ★ M3 자동 효과
                 │      ↓
                 │      ├─ step.output_summary = result.get("_step_output_summary") or _summarize_state_output(result)
                 │      └─ (성공 경로) update_step(SUCCESS, output_summary=step.output_summary)
                 │
                 │  예외 시:
                 │      └─ update_step(FAILED, error_text=str(e)[:1024]) → re-raise
                 │
                 ├─ callback.exit_step()  # _current_step_id = None
                 └─ set_current_run_context(with_step_id(ctx, None))  # 복원
            ↓
            return result → LangGraph 다음 노드 라우팅
```

### 4-3. 동시성·격리 정책

- 한 RunAgentUseCase = 1 UsageCallback 인스턴스 (M1·M2와 동일). LangGraph 노드는 **순차 실행** (Sequential ReAct/Supervisor 패턴)이므로 `_current_step_id`/`_step_index` 단일 슬롯으로 충분
- supervisor → worker → quality_gate 흐름은 명백한 순차 → 동시 step 미발생
- best-effort: `record_step` 실패 시 `step_id=None`, `_current_step_id`는 None 유지, `_step_index`는 증가하지 않음 (실패 step은 시퀀스에서 결손) → 노드는 정상 실행
- 노드 내부의 sub-runnable(LangChain `with_structured_output` 등)에서 `on_chain_start`/`on_chain_end`가 발화해도 M3은 무시 (옵션 B 미채택)

### 4-4. 레이어 배치 (Thin DDD 준수)

```
src/application/agent_run/
├── step_tracking.py    ★ 신규 — async with track_step(...) 컨텍스트 매니저
│                              + _summarize_state_input/output 헬퍼

src/application/agent_builder/
├── workflow_compiler.py  ★ 수정 — _with_step_tracking(name, type, fn) 헬퍼
│                                 + 각 add_node 호출 wrapping

src/application/agent_builder/
├── supervisor_nodes.py   ★ 수정 (최소) — supervisor_node return dict에
│                                       `_step_output_summary` 키 추가 (decision.reasoning[:1024])
│                                       worker 자체는 wrapping만으로 충분 (수정 없음)

src/infrastructure/llm/
├── usage_callback.py     ★ 수정 (최소) — `_step_index: int = 0` 필드 + enter_step 내부 +=1

# 변경 없음:
src/application/agent_run/tracker.py      # M1 완성
src/application/agent_run/context.py      # M1 완성
src/domain/agent_run/                      # M1 완성
src/infrastructure/persistence/            # M1 완성
db/migration/                              # 신규 마이그레이션 없음
```

**도메인 변경 검토**: `NodeType` enum에 `ANSWER` 추가 vs `OTHER` 재활용?
- 권장: `ANSWER` 추가 (조회 시 명시적). 만약 도메인 enum 수정 회피가 더 안전하다면 `OTHER`로 시작하고 M4 archive 시 enum 확장 별도 PDCA. **Design 단계에서 확정**.

---

## 5. 데이터 모델

**변경 없음.** M1 V021의 `ai_run_step` 컬럼을 그대로 사용:

| 컬럼 | M1 정의 | M3 채움 |
|------|---------|---------|
| `id` | PK | `record_step` 내부 uuid4 |
| `run_id` | FK → ai_run | `RunContext.run_id` |
| `step_index` | INT NOT NULL | `UsageCallback._step_index` 단조 증가 (1부터) |
| `node_name` | 100 chars | wrapper에 전달된 add_node 이름 ("supervisor"/"worker_finance"/"quality_gate"/"answer_agent"/...) |
| `node_type` | SUPERVISOR/WORKER/GATE/OTHER (+ ANSWER 검토) | wrapper에 전달된 enum |
| `llm_model_id` | FK → llm_model NULL | **NULL** (노드 자체는 LLM 아님. 노드 *내부* LLM은 `ai_llm_call.step_id`로 잡힘) |
| `status` | STARTED → SUCCESS/FAILED | 단계별 transition |
| `input_summary` | TEXT | `_summarize_state_input(state)[:1024]` |
| `output_summary` | TEXT | supervisor: `decision.reasoning[:1024]` / quality_gate: `quality_gate_result + retry_counts` / worker·answer: `last_ai_message.content[:1024]` |
| `started_at` | DATETIME NOT NULL | `record_step` 시점 |
| `ended_at` | DATETIME NULL | `update_step` 시점 |
| `latency_ms` | INT NULL | `int((perf_counter() - t0) * 1000)` |
| `error_text` | TEXT NULL | `str(e)[:1024]` (FAILED 시) |

**파생 효과** (자동):

```sql
-- M3 완료 후 노드별 비용 1줄 집계
SELECT s.node_name,
       COUNT(*)                          AS step_count,
       SUM(l.total_tokens)               AS tokens,
       SUM(l.total_cost_usd)             AS cost_usd,
       AVG(s.latency_ms)                 AS avg_latency_ms
FROM ai_run_step s
LEFT JOIN ai_llm_call l ON l.step_id = s.id
WHERE s.run_id = ?
GROUP BY s.node_name
ORDER BY s.step_index;
```

---

## 6. 마일스톤 (M3 내부 작업 분할)

| 단계 | 범위 | 산출물 | 예상 |
|------|------|--------|------|
| **M3-1** | `step_tracking.py` 컨텍스트 매니저 + 헬퍼 + 단위 테스트 | step_tracking.py + test_step_tracking.py | 0.3일 |
| **M3-2** | `UsageCallback._step_index` 필드 + enter_step 증가 + 테스트 보강 | usage_callback.py 수정 + test 추가 | 0.2일 |
| **M3-3** | `WorkflowCompiler._with_step_tracking` 헬퍼 + 각 add_node wrapping (6 지점) | workflow_compiler.py 수정 | 0.3일 |
| **M3-4** | `supervisor_node` reasoning을 `_step_output_summary`로 노출 (return dict 1 키 추가) | supervisor_nodes.py 1줄 수정 + 테스트 1건 | 0.1일 |
| **M3-5** | NodeType.ANSWER 결정 (도메인 수정 or OTHER 사용) — Design에서 확정 후 | (Design 종속) | 0.1일 |
| **M3-6** | 통합 테스트: 한 run의 supervisor→worker→quality_gate→answer 흐름이 `ai_run_step` 4 row + `ai_llm_call.step_id` 채워짐 검증 | test_run_agent_use_case_observability.py 4 case 추가 | 0.4일 |
| **M3-7** | 수동 검증 (실 LLM 1회 + SQL) | 검증 로그 캡처 | 0.2일 |

**총 예상**: 1.6일 (M1 견적의 25%, M2와 유사).

---

## 7. 코드 통합 지점

| 파일 | 변경 내용 | 비고 |
|------|----------|------|
| `src/application/agent_run/step_tracking.py` ★ 신규 | `async with track_step(tracker, callback, run_id, node_name, node_type, input_summary=None) as ctx:` 컨텍스트 매니저. enter: `record_step` + `enter_step` + RunContext 갱신. exit: `update_step` + `exit_step` + 복원. `_summarize_state_input(state)` / `_summarize_state_output(result)` 헬퍼 (1KB 컷) | 약 80줄 |
| `src/application/agent_builder/workflow_compiler.py` | `_with_step_tracking(node_name, node_type, async_fn)` 헬퍼 추가 (~15줄). `compile()` 안 6개 `add_node` 호출 직전 각각 wrapping (supervisor / worker_agent / sub_graph / quality_gate / answer_node / search_node) | `_wrap_worker` / `_wrap_sub_agent` 와 chain (외부 wrapper가 step tracking) |
| `src/application/agent_builder/supervisor_nodes.py` | `supervisor_node` return dict에 `_step_output_summary=decision.reasoning[:1024] if decision else None` 키 추가 (1줄) | wrapper가 이 키 발견 시 update_step의 output_summary로 사용 |
| `src/infrastructure/llm/usage_callback.py` | `self._step_index: int = 0` 인스턴스 필드 추가. `enter_step()` 진입 시 `self._step_index += 1`. (M2의 `_current_step_id` 동기화는 이미 존재) | 약 3줄 |
| (선택) `src/domain/agent_run/value_objects.py` | `NodeType.ANSWER` enum 추가 — Design §3에서 확정 (또는 OTHER 재활용 결정) | 1줄 |
| `tests/application/agent_run/test_step_tracking.py` ★ 신규 | 컨텍스트 매니저 단위 테스트 약 10건 | 새 파일 |
| `tests/application/agent_builder/test_workflow_compiler_step_wrapping.py` ★ 신규 | wrapping 단위 테스트 약 6건 (각 노드 타입별) | 새 파일 |
| `tests/application/agent_builder/test_run_agent_use_case_observability.py` | M3 통합 4 cases 추가 (`TestRunStepWiringM3`) | 기존 파일 확장 |
| (보강) `tests/infrastructure/llm/test_usage_callback*.py` | `_step_index` 단조 증가 + best-effort 격리 테스트 1~2건 | 기존 파일 |
| DB 마이그레이션 | **없음** | 0건 |

---

## 8. TDD 계획

### 8-1. `tests/application/agent_run/test_step_tracking.py` (~10 cases)

```
test_track_step_records_started_on_enter
test_track_step_assigns_step_index_from_callback_counter
test_track_step_calls_callback_enter_step
test_track_step_updates_run_context_step_id
test_track_step_records_success_on_normal_exit_with_output_summary
test_track_step_records_failed_on_exception_with_error_text
test_track_step_reraises_exception_after_record_failed
test_track_step_record_step_failure_degrades_gracefully  ★ best-effort
test_track_step_input_summary_truncates_at_1024
test_track_step_concurrent_isolation_in_separate_callbacks
```

### 8-2. `tests/application/agent_builder/test_workflow_compiler_step_wrapping.py` (~6 cases)

```
test_supervisor_node_wrapped_with_node_type_SUPERVISOR
test_worker_agent_wrapped_with_node_type_WORKER
test_sub_agent_wrapped_with_node_type_WORKER
test_quality_gate_wrapped_with_node_type_QUALITY_GATE
test_answer_node_wrapped_with_node_type_ANSWER  # 또는 OTHER (Design 종속)
test_search_node_wrapped_with_node_type_WORKER
```

### 8-3. `tests/application/agent_builder/test_run_agent_use_case_observability.py` 보강 (~4 cases)

```
test_one_run_creates_one_step_row_per_node           ★ 핵심 통합
test_llm_call_inside_node_attaches_step_id           ★ JOIN 검증
test_node_failure_records_step_status_failed         ★ 예외 경로
test_supervisor_step_records_decision_reasoning_in_output_summary  ★ M3 고유
```

**핵심 회귀 가드**: `test_llm_call_inside_node_attaches_step_id` — M3의 단 하나의 가치 보장.

### 8-4. `tests/infrastructure/llm/test_usage_callback*.py` 보강

```
test_step_index_increments_monotonically_on_enter_step
test_step_index_resets_only_on_new_callback_instance
```

---

## 9. CLAUDE.md 규칙 체크

- [x] domain 변경 가능성 (`NodeType.ANSWER`) — Design §3에서 확정. M3 코드에서 import만 하면 됨 (역방향 의존성 없음)
- [x] application 레이어(`step_tracking.py`)는 domain enum + tracker + context + callback만 import — infrastructure 의존 없음
- [x] infrastructure(`usage_callback.py`) 변경 최소 — `_step_index` 1 필드 + enter_step 1 줄
- [x] Repository / commit 정책 (DB-001) 영향 없음 — Tracker는 M1에서 이미 session-per-operation 준수
- [x] LOG-001 LoggerInterface — step_tracking.py 내부 warning log (record_step 실패 / unmatched step) M1·M2 패턴 유지
- [x] TDD 순서 — `test_step_tracking.py` 먼저 작성 → 실패 → 구현
- [x] 함수 ≤40줄 / if 중첩 ≤2단계 — track_step `__aenter__/__aexit__` 각 ≤25줄 목표
- [x] config 하드코딩 금지 — 1024자 컷오프는 M1·M2 상수 일관 적용 (별도 config 분리는 별도 PDCA)
- [x] 한국어 도메인 용어 / 영문 식별자 분리 유지

---

## 10. 위험 요소 및 대응

| 위험 | 영향 | 가능성 | 대응 |
|------|------|--------|------|
| `_wrap_worker` / `_wrap_sub_agent` 와 `_with_step_tracking` 의 wrapping 순서 | step record가 worker 내부 token_usage 집계보다 먼저/늦게 일어남 | Low | step_tracking이 가장 바깥(graph 노드 호출 직전) — worker wrapping은 그 안에 — token_usage 합산은 그 다음. wrapping order 명시 |
| LangGraph가 같은 노드를 재방문 (quality_gate retry → worker 재호출) | step row N건 생성됨 (의도된 동작) | Resolved (Spec) | 정상 동작 — retry마다 step 분리 기록은 quality_gate 효율성 분석의 핵심 |
| `record_step` 실패 시 `_step_index` 증가하면 시퀀스 결손 | step_index 1,2,4,5 (3 누락) | Medium | 실패 시 increment 하지 않음 → 시퀀스 일관성 유지. 단, 본 흐름은 실패해도 안 막힘 |
| `update_step` 실패 (DB 다운 등) | step row가 STARTED로 잔존 (orphan) | Low | warning log. 운영 dashboard에서 detection → M4 sweep 검토 (M2와 동일 정책) |
| supervisor의 reasoning을 노드 함수 return으로 노출하는 것이 노드 함수 결합도 증가 | 향후 supervisor 시그니처 변경 시 영향 | Low | 1 key (`_step_output_summary`)만 추가. 미존재 시 wrapper는 다른 fallback(last_ai_message 등) 사용 |
| `NodeType.ANSWER` enum 추가 시 기존 데이터 마이그레이션 | M1·M2 archived runs에 적용 안 됨 | None | 새 row만 적용. 기존 None 상태로 ai_run_step 비어있음 — 영향 없음 |
| 노드 함수가 동기 (rare) | `async with`이 작동 안 함 | Very Low | 모든 LangGraph 노드는 async 검증됨 (M2와 동일 가정). 발생 시 별도 sync wrapper 분기 |
| ContextVar `step_id` 누수 (예외 시 복원 실패) | 다음 노드의 _current_step_id 오염 | Low | `__aexit__`이 `finally`처럼 보장. token 보존 + reset 패턴 사용 |
| sub_graph 재귀 (worker 안에 또 worker) | step_index 중첩, _current_step_id stack 필요 | Very Low | 현 시스템 패턴 아님. 발생 시 outer step_id 덮어쓰지만 record_step 자체는 정상. M4에서 stack 도입 검토 |
| LangGraph `astream(updates)` 이벤트 누락 (옵션 B 미채택 결정 재검증) | M3 이후 LangGraph가 노드 hook을 공식 API화하면 옵션 B 매력 상승 | Low | 옵션 C 채택 근거 명문화 (§4-1). LangGraph 0.4+ 공식 hook 출시 시 별도 PDCA로 마이그레이션 검토 |

---

## 11. 후속 PDCA (M4 이후)

- **M4** (`agent-run-observability-m4` — Retrieval + API):
  - `internal_document_search` / `tavily_search` 어댑터에서 `record_retrieval()` 호출 — `RunContext.step_id` + `RunContext.tool_call_id` 조합 활용 (M2·M3 사전 완료)
  - `GET /agents/runs/{run_id}` — run 상세 (run + steps + tool_calls + retrievals + llm_calls 트리)
  - `GET /admin/usage/users`, `/admin/usage/llm-models`, `/admin/usage/by-node`(★ M3 효과)
  - `GET /usage/me`
  - `PATCH /llm-models/{id}/pricing` + `CostCalculator.invalidate()` (M1 G1)
- `agent-run-admin-dashboard` — 어드민 UI (별도 PDCA)
- `agent-usage-dashboard` — 사용자/LLM/부서/노드 사용량 시각화 (별도 PDCA)
- M1 Plan §5-3 status enum 표기 동기화 (M2 G3 follow-up — 별도 작업)

---

## 12. 완료 기준 (DoD)

### 12.1 코드
- [ ] `src/application/agent_run/step_tracking.py` 신규 — `track_step` 컨텍스트 매니저 + 헬퍼
- [ ] `WorkflowCompiler.compile()`의 6개 `add_node` 호출 모두 `_with_step_tracking`로 wrapping
- [ ] `UsageCallback._step_index` 단조 카운터 + `enter_step` 진입 시 increment
- [ ] `supervisor_node` return dict에 `_step_output_summary` 키 노출
- [ ] (Design 결정 시) `NodeType.ANSWER` 도메인 enum 추가

### 12.2 테스트
- [ ] `tests/application/agent_run/test_step_tracking.py` 10건 통과
- [ ] `tests/application/agent_builder/test_workflow_compiler_step_wrapping.py` 6건 통과
- [ ] `tests/application/agent_builder/test_run_agent_use_case_observability.py` M3 보강 4건 통과
- [ ] **회귀 가드**: `test_llm_call_inside_node_attaches_step_id` 통과 (M3 핵심 가치)
- [ ] M1·M2 기존 테스트 100% 유지 (~180개 회귀 0건)

### 12.3 수동 검증 (실 운영 환경)
- [ ] 한 사용자 질문 → supervisor + worker + quality_gate + answer 4 노드 흐름 → 어드민 SQL:
  ```sql
  SELECT step_index, node_name, node_type, status, latency_ms, LENGTH(output_summary)
  FROM ai_run_step WHERE run_id = ? ORDER BY step_index;
  ```
  → 4 row, status='SUCCESS', step_index 연속, output_summary ≤ 1024
- [ ] 같은 run의 `ai_llm_call.step_id` 가 채워졌는지:
  ```sql
  SELECT l.purpose, s.node_name, COUNT(*), SUM(l.total_tokens)
  FROM ai_llm_call l JOIN ai_run_step s ON s.id = l.step_id
  WHERE l.run_id = ? GROUP BY l.purpose, s.node_name;
  ```
  → llm_call row의 step_id NOT NULL, 노드별 token 분포 확인
- [ ] `ai_tool_call.step_id` 확인 (M2가 만든 row가 M3 wiring으로 step_id 자동 채움):
  ```sql
  SELECT t.tool_name, s.node_name FROM ai_tool_call t JOIN ai_run_step s ON s.id = t.step_id
  WHERE t.run_id = ?;
  ```
- [ ] Supervisor decision reasoning이 `output_summary` 에 저장됐는지 (text 검사)
- [ ] 노드 강제 예외 주입 → `status='FAILED'` + `error_text` 기록 확인
- [ ] 운영 흐름이 step 기록 실패로 차단되지 않음 (best-effort 검증: record_step에 강제 예외 주입 후 답변 정상 반환)

### 12.4 문서 동기화
- [ ] M3 Design 문서 작성 (`docs/02-design/features/agent-run-observability-m3.design.md`)
- [ ] `NodeType.ANSWER` 결정 사항 Design §3에 명시
- [ ] M2 Plan §12의 "M3 Out of Scope" 항목과 본 Plan §2 In Scope 일치성 검증

---

## 13. 참고 자료

- 부모 Plan (M1): [agent-run-observability.plan.md](../../archive/2026-05/agent-run-observability/agent-run-observability.plan.md)
- M2 Plan: [agent-run-observability-m2.plan.md](../../archive/2026-05/agent-run-observability-m2/agent-run-observability-m2.plan.md) — M3 데이터 레이어 사전 작업 완료 (RunContext.tool_call_id 자동 전파)
- M1 Design §6.1 / §14: [agent-run-observability.design.md](../../archive/2026-05/agent-run-observability/agent-run-observability.design.md) — 노드별 enter_step/exit_step 흐름 원안
- M1 V021 schema: `db/migration/V021__create_agent_run_tables.sql` — `ai_run_step` 컬럼 정의
- 핵심 원칙: **"단일 진입점 인터셉트"** (M2와 동일, 단 진입점은 graph 빌드 시점) + **"best-effort 격리"**

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-05-21 | M3 초안 — Run Step wiring (compiler decorator). 신규 테이블/마이그레이션 0건, wrapping only | 배상규 |
