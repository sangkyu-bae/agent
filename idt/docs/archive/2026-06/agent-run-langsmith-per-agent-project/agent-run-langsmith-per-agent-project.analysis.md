# agent-run-langsmith-per-agent-project — Gap Analysis (Check Phase)

> **Match Rate: 100% (8/8 자동 검증 가능 기준 Met, 9번째는 수동 검증 항목)**
>
> **Feature**: agent-run-langsmith-per-agent-project
> **Project**: sangplusbot (idt)
> **Analysis Date**: 2026-06-03
> **Design Doc**: [../02-design/features/agent-run-langsmith-per-agent-project.design.md](../02-design/features/agent-run-langsmith-per-agent-project.design.md)
> **Plan Doc**: [../01-plan/features/agent-run-langsmith-per-agent-project.plan.md](../01-plan/features/agent-run-langsmith-per-agent-project.plan.md)

---

## 1. Overview

| Item | Value |
|------|-------|
| Impl Paths | `src/infrastructure/langsmith/langsmith.py`, `src/application/agent_builder/run_agent_use_case.py` |
| Tests | `tests/infrastructure/langsmith/test_langsmith_helpers.py`, `tests/application/agent_builder/test_run_agent_graph_config.py` |
| Method | Design §8 Acceptance Criteria + §3 Detailed Design ↔ 구현 대조 |

| Category | Score | Status |
|----------|:-----:|:------:|
| Design Match | 100% | Pass |
| Architecture (DDD) Compliance | 100% | Pass |
| Convention Compliance | 100% | Pass |
| **Overall** | **100%** | Pass |

---

## 2. Acceptance Criteria (§8) Verification

| # | Criterion | Verdict | Evidence |
|---|-----------|:-------:|----------|
| 1 | `make_agent_run_tracer` 키 없으면 None, 있으면 `LangChainTracer(project_name="agent-{정규화}")` | Met | `langsmith.py:67-78` (키 가드 None, tracer 생성). Tests `test_none_without_key`, `test_returns_tracer_with_project` |
| 2 | `normalize_agent_project_name` 정규화/fallback("agent-run")/절단(128) | Met | `langsmith.py:43-52`. Tests collapse/empty/truncate |
| 3 | `_build_graph_config`가 `run_name=agent.name`, `tags`에 `agent.name`, `metadata["agent_name"]` (항상) | Met | `run_agent_use_case.py:486/497/506`. Test `test_has_run_name_tags_and_agent_name` |
| 4 | tracer 존재 시 `callbacks`에 포함 (tracer 먼저, UsageCallback 다음); 전역 auto-tracer 억제 | Met | `run_agent_use_case.py:487-493/510-511`. Test가 `[tracer, usage_cb]` 순서 검증 |
| 5 | 전역 `os.environ["LANGSMITH_PROJECT"]` per-agent 미변경 (race 없음) | Met | `_build_graph_config`에 os.environ 쓰기 없음. 기존 `langsmith(project_name="agent-run")`는 Design §2.4/§3.2.3대로 의도적 유지 — gap 아님 |
| 6 | 공통 `stream()`/`_prepare_graph` 경유 → HTTP/SSE/WS 일괄 | Met | `_prepare_graph`가 `_build_graph_config` 호출, `stream()` 단일 진입점 |
| 7 | application이 `langchain_core` tracer 직접 import 안 함 (infra 헬퍼 경유) | Met | application의 `langchain_core` 등장은 docstring뿐. `LangChainTracer` import는 infra `langsmith.py:73` |
| 8 | metadata `run_id`는 run_id 있을 때만 | Met | `run_agent_use_case.py:501-502` 가드. Test 부재/존재 검증 |
| 9 | (수동) dev에서 `agent-{이름}` 프로젝트 + run_name 확인 | N/A | Design §6 Step 5 — 정적 분석 범위 밖 |

---

## 3. Test Coverage (§4)

모든 설계 테스트 존재. graph-config 스위트는 `test_callbacks_and_run_id_with_observability`로 callback 순서(`[tracer, usage_cb]`)까지 추가 검증(설계보다 강함).

### 격리 실행 결과
| Test file | Result |
|-----------|--------|
| `test_langsmith_helpers.py` + `test_run_agent_graph_config.py` | 9 passed |
| 회귀 `test_ws_agent_router.py` + `test_run_agent_use_case_stream.py` | 통과 (총 41 passed) |

---

## 4. Gaps Found

**없음.** Missing/Added/Changed 항목 0.

### 비차단 관찰 (Info)
- Design §3.2.2는 graph_config를 `_prepare_graph` 인라인으로 스케치했으나, 구현은 `_build_graph_config` staticmethod로 추출(테스트성·40줄 규칙). 설계 의도와 일치 — 이탈 아님.
- 테스트 이름 분할/추가(커버리지 동일 이상).
- **사전 존재 이슈(이 feature 무관)**: `tests/api/test_agent_builder_router_stream.py`가 SSE 라우트의 `get_auth_context_from_query_token` DI를 override하지 않아 `AssembleAuthContextUseCase not initialized`로 실패. 의존성 해석 단계에서 발생(본 변경의 graph 코드 실행 전). auth-context 리팩터 이후 stale된 테스트로, 별도 정리 권장.

---

## 5. Layer / Convention Compliance (CLAUDE.md)

| Rule | Status | Evidence |
|------|:------:|----------|
| DDD: application이 langchain_core import 안 함 | Pass | tracer import는 infra에 격리 |
| domain → infra 미참조 | Pass | infra+application만 변경 |
| 함수 ≤40줄 | Pass | make_tracer ~14, normalize ~10, _build_graph_config ~27 |
| if 중첩 ≤2 | Pass | 단일 가드만 |
| print 금지 | Pass | `logger.warning` 사용 |
| 명시적 타입 | Pass | Optional/-> dict |
| config 하드코딩 회피 | Pass | `_PROJECT_NAME_MAX=128` 상수 |

---

## 6. Recommended Actions

1. 코드 변경 불필요 — Design ↔ 구현 100% 일치.
2. 수동 기준 #9: dev에서 WS/SSE/HTTP 실행 → LangSmith에 `agent-{이름}` 프로젝트 + run_name 확인 (Design §6 Step 5).
3. Match Rate ≥ 90% → `/pdca report agent-run-langsmith-per-agent-project` 진행. Act 반복 불필요.
