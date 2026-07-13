# agent-recursion-limit Gap Analysis

> **Design**: `docs/02-design/features/agent-recursion-limit.design.md` (D1~D10)
> **Plan**: `docs/01-plan/features/agent-recursion-limit.plan.md` (FR-01~FR-07)
> **Analyzer**: gap-detector agent
> **Date**: 2026-07-08
> **Match Rate**: **98%** (구현만 기준 100% — 감점은 테스트 배치/커버리지 뉘앙스)

---

## 1. 종합 점수

| 항목 | 점수 | 상태 |
|------|:----:|:----:|
| 설계 결정 일치 (D1~D10) | 100% | ✅ |
| 파일 구조 (§3) | 100% | ✅ |
| 테스트 계획 (§5) | 90% | ⚠️ |
| 레이어 규칙 준수 | 100% | ✅ |
| **종합** | **98%** | ✅ |

Match Rate 산식: D1~D10 (가중 0.70) 100% + 파일 구조 (0.15) 100% + 테스트 계획 (0.15) 90% = 98.5% ≈ 98%

## 2. 설계 결정별 판정 (D1~D10 전부 구현됨)

| ID | 결정 | 판정 | 근거 |
|----|------|:----:|------|
| D1 | 단일 소스 + SupervisorConfig 기본 25 + 주입 | ✅ | `domain/schemas.py:16`, `run_agent_use_case.py:558` |
| D2 | IterationLimitPolicy (상수 집약) + 필드 검증 | ✅ | `policies.py:150-186`, `schemas.py:98,109` |
| D3 | recursion_limit 파생 (×10+20) | ✅ | `run_agent_use_case.py:658-660` |
| D4 | V045 + 모델/리포지토리 매핑 + fork 승계 | ✅ | `V045.sql`, `models.py:35`, `repository.py:38,112,358` |
| D5 | limit_reached 플래그 (iteration만, token 현행 유지) | ✅ | `supervisor_state.py:30`, `supervisor_nodes.py:129,174-179` |
| D6 | 라우팅 확장 (`last_worker_id or limit_reached`) | ✅ | `supervisor_nodes.py:344-346` |
| D7 | 안내 블록 + 캡처 + payload 플래그(True만) | ✅ | `workflow_compiler.py:565-584`, `run_agent_use_case.py:124,287-288,727-728` |
| D8 | sub-agent 절반 + 서브 그래프 recursion_limit | ✅ | `workflow_compiler.py:946-966` |
| D9 | GraphRecursionError 안전망 (Exception 앞 분기) | ✅ | `run_agent_use_case.py:319-327,393-449` |
| D10 | API 스키마 additive + apply_update | ✅ | `app/schemas.py:66,92,104,137`, `domain/schemas.py:128,141-142` |

## 3. FR 충족 (FR-01~FR-07 전부 ✅)

pydantic `Field(ge=10, le=1000)` + 도메인 `__post_init__` 이중 가드, `derive(25)=270 > 25` state 가드 선발동, 조기 답변 체인(D5→D6→D7), 안전망(D9), sub-agent 절반(D8) 모두 확인.

## 4. 레이어 준수 / 추가 구현

- **위반 없음**: domain은 순수(dataclass/enum만), 주입=application, 컬럼=infrastructure.
- **설계 외 추가 구현 없음**. `middleware_agent`의 `MiddlewareAgentDefinition`은 별도 도메인 객체 — 범위 밖 확인.

## 5. Gap 목록 (전부 🔵 Low — 기능 Gap 아님)

| # | 항목 | 내용 | 심각도 |
|---|------|------|:------:|
| 1 | 테스트 파일 배치 | AgentDefinition 테스트가 §5의 `test_agent_definition.py`(기존 확장) 대신 `test_iteration_limit_policy.py`에 위치 — 커버리지는 동일 | 🔵 Low |
| 2 | 라우터 422 통합 테스트 | 스키마 레벨 검증 테스트만 존재, HTTP 422 라우터 통합 테스트 미작성 | 🔵 Low |
| 3 | 기존 가드 테스트 미보강 | `test_supervisor_nodes.py::test_max_iterations_reached`가 `limit_reached` 단언 미포함 — 신규 파일 테스트가 동일 케이스 커버 | 🔵 Negligible |

## 6. 판정

**Match Rate 98% ≥ 90% → iterate 불필요, Report 진행 가능.**
권고(선택): 라우터 422 통합 테스트 1건 추가로 §5 항목 완전 종결.

테스트 실행 결과 (2026-07-08): agent_builder 도메인/앱/인프라 637 passed, `tests/api/test_agent_builder_router.py` 23 passed. 신규 테스트 38건 포함, 회귀 0.
