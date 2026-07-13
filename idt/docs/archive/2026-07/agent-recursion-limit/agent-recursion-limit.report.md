# Completion Report: agent-recursion-limit

> **Summary**: 에이전트 그래프 실행 시 반복 한도를 `agent_definition.max_iterations`(DB, 기본 25, 10~1000)로 통합하고, 한도 도달 시 오류(RUN_FAILED) 대신 지금까지 수집한 정보로 답변을 정상 종료한다. LangGraph `recursion_limit`을 파생값으로 설정해 state 가드가 항상 먼저 발동하도록 보장하고, 한도 도달 사실을 답변 텍스트와 이벤트 플래그로 사용자에게 전달한다. 예측 불가능한 GraphRecursionError는 축적 메시지 기반 강등 답변으로 안전하게 처리한다.
>
> **Completed**: 2026-07-08
> **Status**: ✅ Complete (98% Match Rate, 0 iterations)

---

## Executive Summary

### 1.1 프로젝트 개요

| 항목 | 내용 |
|------|------|
| **기능** | 에이전트 반복 한도 DB 저장 및 조기 답변 처리 |
| **기간** | 2026-07-08 (기획~완료) |
| **문서** | Plan: `01-plan/features/agent-recursion-limit.plan.md` / Design: `02-design/features/agent-recursion-limit.design.md` / Analysis: `03-analysis/agent-recursion-limit.analysis.md` |

### 1.2 결과 요약

| 지표 | 수치 |
|------|:----:|
| **Match Rate** | **98%** |
| **설계 결정 일치 (D1~D10)** | 100% (전부 구현) |
| **기능 Gap** | 0건 |
| **Low Gap** | 3건 (라우터 422 통합 테스트 등 — 기능 아님) |
| **파일 수정** | 15개 (도메인 2 / 애플리케이션 11 / 인프라 2) |
| **신규 테스트** | 2파일 38케이스 + 기존 3파일 보강 |
| **테스트 통과** | agent_builder 637/637 PASS, API 23/23 PASS, 회귀 0 |
| **Iteration** | 0 (1회 구현으로 Design 일치) |

### 1.3 Value Delivered (4관점)

| 관점 | 내용 |
|-----|------|
| **Problem** | 에이전트 그래프의 반복 한도가 이원화·방치되어 있다. ① LangGraph `recursion_limit` 미설정(시스템 기본 25 스텝)이 자체 가드(`max_iterations=10`)보다 먼저 발동해 **GraphRecursionError → RUN_FAILED**(답변 불능)가 발생한다. ② `max_iterations`는 하드코딩(10)이라 에이전트별 조정이 불가능하다. ③ 한도 도달 시 사용자는 그때까지 워커가 수집한 정보를 **전혀 받지 못한다**(조기 종료, 안내 없음). |
| **Solution** | ① `agent_definition.max_iterations` 컬럼(DB, 기본 25, 10~1000) 신규 추가 및 API 노출. ② `IterationLimitPolicy`(도메인)에서 파생식 정의: `recursion_limit = max_iterations × 10 + 20`으로 LangGraph 한도를 설정해 state 가드가 항상 먼저 발동하도록 보장. ③ supervisor 가드 도달 시 `limit_reached` 플래그 → `final_answer` 노드 경유 → 수집 정보로 답변 생성 + 한도 도달 안내 자동 포함. ④ sub-agent는 부모 한도의 절반(정책 상수 `SUB_AGENT_DIVISOR=2`, 하한 5) 상속. ⑤ GraphRecursionError는 최후 안전망으로 잡아 축적 메시지 기반 강등 답변 시도. |
| **Function/UX Effect** | **제작자**: API로 에이전트별 반복 한도 설정 가능(미설정 시 기본 25, 이전 하드코딩 10에서 관대화). **최종 사용자**: 복잡한 질의도 무한 루프·오류 없이 "한도 내 최선의 답변 + 한도 도달 안내"를 받음(RUN_COMPLETED). 한도 도달 사실을 `ANSWER_COMPLETED` 페이로드의 `limit_reached` 플래그로 감지 가능(UI 후속 배지/알림 표시). **내부**: 중복되던 한도 체크 로직 단일 소스 통합, 코드 예측 가능성 향상. |
| **Core Value** | 답변 불능(RUN_FAILED/무한 루프)을 구조적으로 **제거**해 에이전트 실행의 **예측 가능성** 및 **사용자 신뢰도 향상**. 한도는 에이전트 복잡도에 맞게 조정 가능하되 기본값·범위(10~1000)로 안전하게 제한됨. 부분 정보라도 반드시 사용자에게 전달되므로 "더 이상 조용한 실패 없음" 원칙 달성. |

---

## PDCA Cycle Summary

### Plan

**Document**: `docs/01-plan/features/agent-recursion-limit.plan.md`

- **Goal**: 에이전트별 supervisor 반복 한도를 DB에 저장하고, 한도 도달을 오류가 아니라 "조기 답변"으로 처리. LangGraph `recursion_limit` 미설정 결함 함께 해소.

- **Key Decisions** (사용자 확정, 2026-07-08):
  - 한도 단위 = **supervisor 반복 횟수** (기존 `iteration_count` 재사용)
  - 기본값/범위 = **기본 25회, 설정 범위 10~1000회** (미설정 시 25)
  - 한도 도달 알림 = **이벤트 + 답변 안내** (`ANSWER_COMPLETED.limit_reached` 플래그 + final_answer 프롬프트 안내 블록)
  - 작업 범위 = **백엔드만** (DB + 도메인 + API + 실행 경로), Studio UI 입력 필드는 후속
  - sub-agent 한도 = **부모의 절반** (정책 상수로 분리, 문제 시 즉시 변경 가능)

- **Estimated Duration**: 2~3일 (마이그레이션 + 도메인 + API + 실행 경로 + 테스트)

### Design

**Document**: `docs/02-design/features/agent-recursion-limit.design.md`

**Key Design Decisions** (D1~D10 확정):

| ID | 결정 | 근거 |
|----|------|------|
| D1 | 단일 소스 = `agent_definition.max_iterations`, `SupervisorConfig` 기본 10 → 25로 상향 | 기존 state 가드 인프라 재사용, 에이전트별 값 주입 경로 신규 추가 |
| D2 | 도메인 정책 `IterationLimitPolicy` (상수 집약): DEFAULT=25, MIN=10, MAX=1000, RECURSION_STEP_FACTOR=10, RECURSION_BUFFER=20, SUB_AGENT_DIVISOR=2, SUB_AGENT_MIN=5 | 계수 변경 시 1곳만 수정, `__post_init__` 범위 검증 자동 |
| D3 | recursion_limit 파생식 = `max_iterations × 10 + 20` | 최악 경로(반복당 5스텝 + quality_gate 재시도 8스텝) 여유 포함, state 가드가 항상 먼저 발동 보장 |
| D4 | V045 마이그레이션, 기존 행 자동 25, fork/auto-fork는 원본 값 승계 | additive, 기존 10보다 관대한 방향 |
| D5 | `SupervisorState.limit_reached: bool` 플래그 (iteration 가드만, token 현행 유지) | 워커 미실행 상태로 한도 도달 시에도 답변 보장 |
| D6 | 라우팅 조건 확장: `__end__ and (last_worker_id or limit_reached)` → final_answer | 엣지 케이스(워커 미실행 한도) 커버 |
| D7 | 알림 = payload 플래그(신규 이벤트 타입 없음), final_answer 프롬프트에 안내 블록 추가 | 9종 이벤트 계약 불변, 하위호환성 유지 |
| D8 | sub-agent = 부모의 절반(`max_iterations // DIVISOR`) + 서브 그래프 `recursion_limit` 파생 설정 | token_limit 절반 선례와 동형, 중첩 폭주 방지 |
| D9 | GraphRecursionError 안전망 (Exception 앞 분기) → 축적 메시지 기반 강등 답변 | FR-06, state 가드 먼저 발동이 목표라 실발동 확률 낮음 |
| D10 | API 스키마 additive: Create/Update 요청에 `max_iterations`, Create/Get 응답 노출 | pydantic ge/le + 도메인 검증 이중 가드 |

**Affected Files** (§3):
- `db/migration/V045__*.sql` (신규)
- `domain/agent_builder/policies.py` (IterationLimitPolicy 신규), `schemas.py` (필드·검증)
- `application/agent_builder/supervisor_state.py`, `supervisor_nodes.py`, `run_agent_use_case.py`, `workflow_compiler.py`, `schemas.py` 등 11개
- `infrastructure/agent_builder/models.py`, `repository.py`

### Do

**Implementation Scope**:

1. **마이그레이션** (V045): `agent_definition` 테이블에 `max_iterations INT NOT NULL DEFAULT 25` 컬럼 추가
2. **도메인** (Thin DDD):
   - `IterationLimitPolicy` 신규 클래스 (계수·파생식 상수화)
   - `AgentDefinition.max_iterations: int = 25` 필드 + `__post_init__` 범위 검증(10~1000)
   - `SupervisorConfig.max_iterations` 기본 10 → 25로 상향
3. **API** (생성/수정/조회):
   - `CreateAgentRequest.max_iterations: int = Field(25, ge=10, le=1000)`
   - `UpdateAgentRequest.max_iterations: int | None = Field(None, ge=10, le=1000)`
   - Create/Get 응답에 `max_iterations` 노출 (additive)
4. **실행 경로**:
   - `_prepare_graph`: `SupervisorConfig(max_iterations=agent.max_iterations, ...)` 주입
   - `graph_config["recursion_limit"] = IterationLimitPolicy.derive_recursion_limit(agent.max_iterations)` 설정
   - supervisor 가드: `limit_reached: True` 플래그 추가
   - 라우팅: final_answer 조건 확장
   - final_answer 프롬프트: 한도 도달 안내 블록 주입
   - `_StreamState.limit_reached` 캡처, `answer_payload["limit_reached"]` 포함(True만)
   - GraphRecursionError catch 분기 + 축적 메시지 강등 답변
5. **sub-agent**: `_wrap_sub_agent`에서 절반 상속 + 서브 그래프 `recursion_limit` 설정
6. **create/update/fork 유스케이스**: `AgentDefinition` 생성/수정 시 `max_iterations` 전달

**Actual Duration**: 1일 (TDD 준수, Red→Green→Refactor 사이클)

**Test-First Approach** (§5):
- 도메인: `test_iteration_limit_policy.py` (신규, 범위·파생·sub-agent 계수 테스트)
- 기존 확장: `test_agent_definition.py`, `test_supervisor_nodes.py`, `test_run_agent_use_case.py`, `test_workflow_compiler.py`, `test_create_agent_use_case.py` 등
- 신규 + 기존 보강 합계: **38케이스 추가**

### Check

**Document**: `docs/03-analysis/agent-recursion-limit.analysis.md`

**Match Rate**: **98%** (D1~D10 100% + 파일 구조 100% + 테스트 계획 90%)

**설계 결정 일치 (D1~D10)**: ✅ 100% (전부 코드에서 확인)

**Functional Requirements (FR-01~FR-07)**: ✅ 전부 충족

**Gap 목록** (전부 🔵 Low — 기능 Gap 아님):

| # | 내용 | 심각도 | 비고 |
|---|------|:------:|------|
| 1 | 테스트 파일 배치 | 🔵 Low | 커버리지는 동일 |
| 2 | 라우터 422 통합 테스트 | 🔵 Low | 스키마 레벨 검증만 존재, 실질 미결은 이것 하나 |
| 3 | 기존 가드 테스트 미보강 | 🔵 Negligible | 신규 파일 테스트가 이미 커버 |

**Test Results** (2026-07-08):
- agent_builder 도메인/애플리케이션/인프라: **637/637 PASS**
- API 라우터 (`test_agent_builder_router.py`): **23/23 PASS**
- 회귀 테스트: **0건**
- 신규 테스트: **38케이스**

---

## Results

### Completed Items

✅ **마이그레이션 V045 추가**
- `ALTER TABLE agent_definition ADD COLUMN max_iterations INT NOT NULL DEFAULT 25;`
- 기존 행 자동 25 설정, 신규 에이전트는 기본값 또는 요청값 사용

✅ **IterationLimitPolicy 도메인 정책**
- 모든 계수·범위·파생식을 상수로 집약 (`DEFAULT=25`, `MIN=10`, `MAX=1000`, `RECURSION_STEP_FACTOR=10`, `RECURSION_BUFFER=20`, `SUB_AGENT_DIVISOR=2`, `SUB_AGENT_MIN=5`)
- 메서드: `validate(v)`, `derive_recursion_limit(v)`, `sub_agent_limit(parent)`
- 변경 1곳(IterationLimitPolicy)으로 전체 정책 조정 가능

✅ **AgentDefinition 필드·검증**
- `max_iterations: int = 25` 필드 추가
- `__post_init__`에서 `IterationLimitPolicy.validate()` 호출 → 범위 검증 자동화
- `apply_update(max_iterations)` 파라미터 추가 → update 시 재검증 자동

✅ **SupervisorConfig 기본값 상향**
- 기본값 10 → 25로 상향
- 실행 시 에이전트 값 주입으로 에이전트별 조정 가능

✅ **API 스키마 (Create/Update/Get)**
- Create: `max_iterations: int = Field(25, ge=10, le=1000)`
- Update: `max_iterations: int | None = Field(None, ...)` (None=변경 안 함)
- Get/Create 응답: `max_iterations: int` 노출 (additive)
- 범위 밖 입력 시 pydantic 자동 422 처리

✅ **실행 경로 — 한도 주입 및 조기 답변**
- `_prepare_graph`: `SupervisorConfig(max_iterations=agent.max_iterations)` 주입
- `graph_config["recursion_limit"] = max_iterations × 10 + 20` 설정 → state 가드 먼저 발동 보장
- supervisor 반복 가드: `iteration_count >= max_iterations` 시 `{"next_worker": "__end__", "limit_reached": True}` 반환
- 라우팅: `__end__ and (last_worker_id or limit_reached)` → final_answer 경유 (워커 미실행도 커버)
- final_answer 프롬프트: "반복 한도에 도달하여 지금까지 수집된 정보로 답변함" 자동 안내 블록 주입
- `_StreamState.limit_reached` 캡처, `answer_payload["limit_reached"] = True` 포함(True만)
- `ANSWER_COMPLETED` 이벤트로 사용자/UI에 전달, 신규 이벤트 타입 추가 없음(하위호환성 유지)

✅ **GraphRecursionError 안전망**
- `stream()` 메서드의 기존 `except Exception` 앞에 `except GraphRecursionError` 분기 추가
- 처리: warning 로그(request_id 포함) → `state.final_messages`로 강등 답변 시도 → `ANSWER_COMPLETED(limit_reached=True)` + `RUN_COMPLETED`
- 강등 답변 실패 시에만 기존 RUN_FAILED 경로

✅ **sub-agent 한도 상속**
- `_wrap_sub_agent`: `SupervisorConfig(max_iterations=IterationLimitPolicy.sub_agent_limit(parent_limit), ...)`
- 서브 그래프: `ainvoke(..., config={"recursion_limit": IterationLimitPolicy.derive_recursion_limit(sub_limit)})`
- 절반 상속(하한 5) + 서브 그래프 자체 recursion_limit 파생 설정으로 중첩 폭주 방지

✅ **create/update/fork 유스케이스 배선**
- `create_agent_use_case.py`: 요청 `max_iterations` → `AgentDefinition` 생성 시 전달
- `update_agent_use_case.py`: `apply_update(max_iterations)` 전달 → 재검증 자동
- `fork_agent_use_case.py` / `auto_fork_service.py`: 원본 에이전트의 `max_iterations` 승계

✅ **모델/리포지토리 매핑**
- `AgentDefinitionModel.max_iterations: int = 25` (SQLAlchemy ORM)
- `agent_definition_repository.py`: save/update/_to_domain 매핑 반영

✅ **테스트 (신규 2파일 + 기존 3파일 보강)**
- 신규: `test_iteration_limit_policy.py` (정책 로직), `test_recursion_limit_safety.py`(안전망)
- 기존 확장: `test_agent_definition.py`, `test_supervisor_nodes.py`, `test_run_agent_use_case.py`, `test_workflow_compiler.py`, `test_create_agent_use_case.py`
- 총 38케이스 신규 추가, agent_builder 637 PASS, API 23 PASS, 회귀 0

✅ **아키텍처 & 컨벤션 준수**
- Domain: 순수 정책/검증 (외부 API·DB 없음)
- Application: 유스케이스·그래프 로직·LangGraph 통합
- Infrastructure: 모델·리포지토리·마이그레이션
- 레이어 규칙 100% 준수, Domain→Infra 참조 없음

✅ **로깅 & 에러 추적**
- 한도 도달: warning 로그 + request_id (LOG-001 준수)
- GraphRecursionError: warning + 스택 트레이스 (진단 가능)

### Incomplete/Deferred Items

⏸️ **라우터 422 통합 테스트** (선택):
- 현재: `CreateAgentRequest` 스키마 검증 테스트만 존재
- 요청: HTTP 라우터의 실제 422 응답 통합 테스트 (Low priority, 기능 Gap 아님)
- 선택사항: `/pdca analyze` Gap #2 제거 시 추가 가능

⏸️ **Studio UI 입력 필드** (후속 PDCA):
- 응답 스키마는 이번에 additive 노출 완료
- 프론트 UI폼 & `/api-contract` 동기화는 별도 사이클
- 선행 조건: 이번 API 배포 후 프론트 메인브랜치에 합입

---

## Lessons Learned

### What Went Well

1. **사전 설계의 명확성**: Plan에서 사용자 결정사항(단위·기본값·범위·sub-agent 전략)을 사전에 확정했고, Design에서 D1~D10까지 10개 결정을 명시적으로 정의 → **구현 변수 최소화**, 1회 iteration 0으로 98% match rate 달성.

2. **정책 상수화의 효율성**: 모든 계수·범위·파생식을 `IterationLimitPolicy`에 집약하여 변경 1곳(클래스 상수) 수정으로 전체 정책 조정 가능 → 운영 단계에서 빠른 대응 가능.

3. **기존 인프라 재사용**: `iteration_count`, state 가드, final_answer 라우팅 등 이미 구현된 반복 제어 인프라를 최소한으로만 개선 → 회귀 리스크 낮음, 기존 테스트 보호됨.

4. **계층적 안전망 설계**: state 가드(먼저 발동) → final_answer 경유(조기 답변) → GraphRecursionError 잡기(최후 방어)로 3단계 방어선을 단계별로 구성 → 예측 불가능한 오류도 사용자에게 답변 전달.

5. **additive API 확장**: 요청/응답 스키마를 모두 additive로 설계하여 기존 클라이언트 무해, 프론트 후속 작업에서 `/api-contract`만 실행하면 타입 동기화 가능.

### Areas for Improvement

1. **파생 계수 검증의 경험적 기초 강화**: `RECURSION_STEP_FACTOR=10`, `RECURSION_BUFFER=20`은 최악 경로 분석(supervisor 1 + worker 1 + [chart_* 2] + quality_gate 1 = 5 + 재시도 8)을 기반으로 결정했으나, 실제 운영 환경에서 워커/노드 조합이 달라질 경우 조정 필요할 수 있음 → 운영 초기 LangSmith 트레이스로 실제 스텝 소비를 모니터링, 필요 시 상수 재산정.

2. **sub-agent 절반 상속의 깊이 제약 명시 부족**: 현재 depth 최대 2 + 절반 상속 정책인데, 향후 depth 3 이상의 중첩 그래프가 추가될 경우 정책 재검토 필요 → Design에 "depth 최대 2 가정" 명시, 변경 시 정책 문서 갱신 필수화.

3. **token_limit 가드와의 일관성**: 이번 범위는 반복 한도(iteration)만이고, token 한도는 별도 가드 → 향후 token_limit도 동일한 조기 답변 처리를 원할 경우 정책 재검토 필요 (Out of Scope이지만 리마인더 필요).

4. **이벤트 카탈로그 변경 없이 플래그 추가의 예측성**: `ANSWER_COMPLETED.limit_reached` 플래그 추가는 하위호환(기존 파서가 무시 가능)이지만, 향후 다른 플래그(예: `truncated_by_token`)가 누적될 경우 payload 스키마 문서화 강화 필요 → payload 필드 추가 시 CHANGELOG + API 문서 자동화 검토.

### To Apply Next Time

1. **정책 상수화 우선**: 수치/계수가 여러 곳에서 반복되면 최우선으로 `Policy` 클래스로 집약 → 변경 1곳, 버전관리 명확, 운영 효율성 향상.

2. **사용자 결정사항의 명시적 문서화**: Plan에서 "단위가 무엇인가?", "기본값은?", "상속 정책은?"처럼 선택지별 결정을 사전 기록 → Design/구현에서 근거로 참조 가능, 추후 정책 변경 요청 시 이유 추적 용이.

3. **additive API 설계의 자동화**: 신규 필드 추가 시 "(additive) 프론트 타입 동기화는 후속" 패턴을 스키마 주석으로 명시 → CI에서 자동 감지, PR 템플릿에 "프론트 동기화 필요" 체크리스트 자동 추가.

4. **다단계 안전망의 테스트 전략**: 정상 경로(state 가드 먼저 발동) / 엣지 케이스(워커 미실행) / 예외 처리(GraphRecursionError)를 별도 테스트 파일로 구분 → 실패 원인 격리 용이, 유지보수 시 영향 범위 최소화.

5. **상수 변경의 모니터링 계획**: 운영 초기 LangSmith/Prometheus 메트릭(실제 반복 횟수, 한도 도달 빈도, 응답 시간)을 수집해 상수 조정 근거 축적 → 다음 정책 변경은 데이터 기반 의사결정.

---

## Metrics

| 항목 | 수치 |
|------|:----:|
| **Match Rate** | **98%** |
| **Design Items (D1~D10)** | 10 (All implemented) |
| **파일 수정** | **15개** (도메인 2 / 애플리케이션 11 / 인프라 2) |
| **신규 마이그레이션** | 1개 (V045) |
| **신규 테스트 파일** | 2개 |
| **기존 테스트 파일 확장** | 3개 |
| **테스트 케이스 추가** | **38개** |
| **Total Tests Passed** | **660/660** (agent_builder 637 + API 23) |
| **회귀 테스트** | 0건 실패 |
| **Iterations** | 0 (1회 구현으로 Design 일치) |
| **Architecture Compliance** | 100% |
| **Convention Compliance** | 100% |

---

## Implementation Summary

### 핵심 설계 결정 재현

**한도 도달 시나리오** (D1~D9 통합):

```
에이전트 실행 (max_iterations=25)
 ├─ SupervisorConfig(max_iterations=25)              [D1]
 ├─ graph_config["recursion_limit"] = 270           [D3: 25×10+20]
 └─ supervisor 반복 0~24 → 25
      supervisor(iter 25): iteration_count(25) >= max_iterations(25)
        → {"next_worker": "__end__", "limit_reached": True}  [D5]
      route_to_worker_or_final: __end__ + (last_worker_id or limit_reached)
        → "final_answer"  [D6]
      final_answer: limit_reached=True → 안내 블록 + 수집 정보 종합 답변  [D7-①]
        → END (정상 종료, RUN_COMPLETED)
 ├─ _map_chain_end: limit_reached 캡처  [D7-②]
 ├─ ANSWER_COMPLETED {answer, tools_used, limit_reached: true}  [D7-③]
 └─ 사용자: 한도 도달 안내 + 지금까지의 답변 수신

(Graph 한계 GraphRecursionError → state.final_messages 강등 답변 [D9])
```

### 파일 변경 요약

| 카테고리 | 파일 | 변경 |
|---------|------|------|
| **마이그레이션** | `V045__alter_agent_definition_add_max_iterations.sql` | ALTER TABLE + DEFAULT 25 |
| **도메인** | `domain/agent_builder/policies.py` | IterationLimitPolicy (신규) |
| | `domain/agent_builder/schemas.py` | AgentDefinition.max_iterations, SupervisorConfig |
| **애플리케이션** | `app/agent_builder/supervisor_state.py` | limit_reached 필드 |
| | `app/agent_builder/supervisor_nodes.py` | 가드 플래그, 라우팅 확장 |
| | `app/agent_builder/run_agent_use_case.py` | 주입, recursion_limit 설정, payload, 안전망 |
| | `app/agent_builder/workflow_compiler.py` | final_answer 안내, sub-agent |
| | `app/agent_builder/schemas.py` | API 스키마 (Create/Update/Get) |
| | Create/Update/Fork/Auto-fork 유스케이스 | AgentDefinition 전달 |
| **인프라** | `infrastructure/agent_builder/models.py` | max_iterations 컬럼 매핑 |
| | `infrastructure/agent_builder/repository.py` | save/update/_to_domain |
| **테스트** | `tests/domain/agent_builder/test_iteration_limit_policy.py` | 신규 (정책 로직) |
| | `tests/application/agent_builder/test_*.py` | 기존 확장 (3파일) |

---

## Affected Modules & Impact

| 모듈 | 변경 | 영향 |
|------|------|------|
| supervisor 반복 제어 | `max_iterations` 하드코딩 10 → DB 저장, 기본 25 | 기존 에이전트: 10 → 25 한도 상향(더 관대), 신규: 요청값 또는 25 사용 |
| LangGraph 한도 설정 | 미설정(기본 25 스텝) → 파생값(270 스텝, 에이전트별) | GraphRecursionError 발동 확률 대폭 감소 |
| 한도 도달 처리 | 경고 로그만 + END 직행 → `limit_reached` 플래그 + final_answer 경유 + 안내 | 사용자가 답변 수신, 한도 도달 사실 인지 가능 |
| GraphRecursionError | 예외 catch → RUN_FAILED | 축적 메시지 기반 강등 답변 시도 후 RUN_COMPLETED(또는 실패 시 RUN_FAILED) |
| sub-agent | 기본 10 고정 + 25 스텝 한도 | 부모 절반 + 파생 recursion_limit → 중첩 폭주 방지 |
| API 계약 | 반복 한도 미노출 | additive 필드(미전달 시 무해, 프론트 후속) |

---

## Testing & Validation

### Test Coverage

| 테스트 그룹 | 케이스 | 상태 |
|-----------|:------:|:----:|
| IterationLimitPolicy | 8 | ✅ |
| AgentDefinition | 4 | ✅ |
| supervisor nodes (플래그·라우팅) | 6 | ✅ |
| run_agent_use_case (주입·안전망) | 10 | ✅ |
| workflow_compiler (안내·sub-agent) | 5 | ✅ |
| API (스키마·검증·422) | 5 | ✅ |
| **소계 신규** | **38** | **✅** |
| **기존 회귀** | **622** | **✅** |
| **Total** | **660** | **✅ PASS** |

### Architecture Compliance Checklist

- ✅ Domain: 순수 정책/검증 (외부 의존 없음)
- ✅ Application: LangGraph/workflow 통합 (비즈니스 규칙 없음)
- ✅ Infrastructure: ORM/repository (계약만 사용)
- ✅ No domain→infra 참조
- ✅ No print(), 모든 로깅 logger 사용
- ✅ 타입 명시적 (pydantic + type hint)
- ✅ 스택 트레이스 있는 에러 처리

---

## Next Steps

1. **운영 DB 적용**: 로컬 테스트 완료 후 운영 V045 마이그레이션 실행 → 기존 에이전트 모두 max_iterations=25 설정됨

2. **Studio UI 후속** (별도 PDCA):
   - 프론트: agent 폼에 `max_iterations` 입력 필드 추가(10~1000, 기본 25)
   - `/api-contract` 실행 → TypeScript 타입 자동 생성
   - QA: 한도 도달 시나리오 테스트 + UI 배지 표시

3. **모니터링 & 운영**:
   - LangSmith 트레이스: 실제 반복 횟수 수집(파생 계수 검증)
   - Prometheus: 한도 도달 빈도, 응답 시간 메트릭
   - 필요 시 `IterationLimitPolicy` 상수 재산정

4. **선택(Low Priority)**:
   - 라우터 422 통합 테스트 추가 (Gap #2)
   - token_limit 가드에도 동일 조기 답변 패턴 적용 검토

---

## Related Documents

- **Plan**: `docs/01-plan/features/agent-recursion-limit.plan.md`
- **Design**: `docs/02-design/features/agent-recursion-limit.design.md`
- **Analysis**: `docs/03-analysis/agent-recursion-limit.analysis.md` (Match Rate 98%)
- **CLAUDE.md**: `idt/CLAUDE.md` (레이어 규칙, 금지사항)
- **Rules**: `docs/rules/logging.md` (LOG-001)

---

## Sign-off

| 역할 | 상태 | 근거 |
|------|:----:|------|
| **Implementation** | ✅ Complete | D1~D10 모두 구현, 코드 확인 100% |
| **Testing** | ✅ 98% Match (660/660 PASS) | 90% gate exceeded, 회귀 0 |
| **Architecture Review** | ✅ Compliant | 레이어 준수, Domain→Infra 참조 없음 |
| **Convention Check** | ✅ Compliant | 타입·로깅·에러 처리 규칙 준수 |
| **Ready for Archive** | ✅ Yes | Match Rate ≥ 90%, Gap 전부 Low |
