# agent-recursion-limit Design Document

> **Plan**: `docs/01-plan/features/agent-recursion-limit.plan.md`
> **Author**: 배상규
> **Date**: 2026-07-08
> **Status**: Draft

---

## 1. 설계 요약

에이전트별 supervisor 반복 한도를 DB(`agent_definition.max_iterations`, 기본 25, 10~1000)에 저장하고, 실행 시 이 값을 단일 소스로 삼아 ① state 가드(`iteration_count`) ② LangGraph `recursion_limit`(파생값) ③ sub-agent 한도(절반 상속)를 모두 결정한다. 한도 도달은 오류가 아니라 **`limit_reached` 플래그 → final_answer 경유 → 안내 포함 답변 → RUN_COMPLETED**로 처리하고, `GraphRecursionError`는 최후 안전망으로 잡아 축적 메시지 기반 강등 답변을 시도한다.

5개 블록:

1. **도메인 규칙**: `IterationLimitPolicy`(기본/범위/파생식/sub-agent 계수 — 상수 1곳) + `AgentDefinition.max_iterations` 필드·검증
2. **DB**: `V045` additive 컬럼 + 모델/리포지토리 매핑
3. **API**: create/update 요청 + create/get 응답에 `max_iterations` additive 노출
4. **실행 경로**: `SupervisorConfig` 주입, `graph_config["recursion_limit"]` 파생 설정, supervisor 가드의 `limit_reached` 기록, 라우팅 보완, final_answer 안내 주입, `ANSWER_COMPLETED` payload 플래그, `GraphRecursionError` 안전망
5. **sub-agent**: 부모 한도 절반(정책 상수) + 서브 그래프 자체 `recursion_limit` 파생 설정

### 코드 확인으로 확정된 사실 (2026-07-08)

| 확인 항목 | 결과 | 영향 |
|-----------|------|------|
| state 가드 | `supervisor_node`가 `iteration_count >= max_iterations`면 `{"next_worker": "__end__"}`만 반환 — 플래그·안내 없음 (`supervisor_nodes.py:168-171`) | 반환 dict에 `limit_reached: True` 추가만 하면 됨 (D5) |
| final_answer 경유 | `route_to_worker_or_final`: `__end__` + `last_worker_id` 존재 시 final_answer (`supervisor_nodes.py:331-340`). LLM 결정 실패 폴백도 `__end__` 반환 (`:226-231`) | 한도 도달 + 워커 미실행이면 END 직행 → 라우팅 조건에 `limit_reached` 추가 (D6). LLM 실패 폴백은 `limit_reached` 미설정이라 동작 불변 |
| recursion_limit | `_build_graph_config`(`run_agent_use_case.py:539-581`)에 `recursion_limit` 없음 → 기본 25 슈퍼스텝 | `config["recursion_limit"] = 파생값` 1줄 추가 (D3) |
| 1회 반복의 스텝 소비 | supervisor(1)+worker(1)+[chart_router(1)+chart_builder(1)]+quality_gate(1) = 3~5. quality_gate 재시도(기본 비활성, 최대 2회)는 supervisor 미경유로 반복당 최대 +8 스텝 (`workflow_compiler.py:399-436`, `supervisor_nodes.py:295-322`) | 파생 계수 K는 최악 경로 여유 포함 10으로 산정 (D3) |
| sub-agent 실행 | `_wrap_sub_agent`가 `SupervisorConfig(token_limit=부모//2)`로 초기화, `sub_graph.ainvoke(sub_initial)`에 **config 미전달** (`workflow_compiler.py:926-939`) | max_iterations도 기본 10 고정 + 서브 그래프도 기본 recursion_limit 25 → 둘 다 파생 설정 필요 (D8) |
| ANSWER_COMPLETED 조립 | `answer_payload = {"answer", "tools_used"}` + charts 조건부 (`run_agent_use_case.py:278-283`). `_StreamState`가 chain_end에서 누적 (`:111-121`) | payload·_StreamState 모두 additive 확장 (D7) |
| 이벤트 카탈로그 | `AgentRunEventType` 9종 고정, SSE/WS에 그대로 매핑 (`domain/agent_run/value_objects.py:121-136`) | 신규 타입 없이 payload 플래그로 전달 (D7) |
| execute() 경로 | `execute()`는 `stream()`을 내부 소비 (`run_agent_use_case.py:326-372`) | stream 수정만으로 양 경로 커버 |
| 도메인 검증 선례 | `AgentDefinition.__post_init__` temperature 범위 검증, `apply_update()`가 끝에 `__post_init__()` 재실행 (`domain/agent_builder/schemas.py:102-135`) | max_iterations 검증을 동형으로 추가, update 경로 자동 검증 (D2) |
| AgentDefinition 생성처 | `create_agent_use_case.py:144`, `fork_agent_use_case.py:59`, `auto_fork_service.py:55`, `agent_definition_repository.py:331`(_to_domain) | 4곳 모두 max_iterations 전달 필요. fork는 원본 값 승계 (D4) |
| SupervisorConfig | frozen dataclass, `max_iterations: int = 10` (`domain/agent_builder/schemas.py:12-18`), 실행 시 무인자 생성 (`run_agent_use_case.py:480`) | 기본값 25로 상향 + 에이전트 값 주입 (D1) |
| 마이그레이션 | 최신 V044 | V045 |

---

## 2. 설계 결정 (Decisions)

| ID | 결정 | 근거 |
|----|------|------|
| D1 | **단일 소스 = `agent_definition.max_iterations`** (supervisor 반복 횟수 단위). `SupervisorConfig.max_iterations` 기본값 10 → `IterationLimitPolicy.DEFAULT`(25)로 상향, `_prepare_graph`에서 `SupervisorConfig(max_iterations=agent.max_iterations)` 주입 | 사용자 결정(반복 횟수 단위, 기본 25). 기존 state 가드 인프라 그대로 재사용 |
| D2 | **도메인 정책 `IterationLimitPolicy`** (`policies.py` 신규 클래스, 전부 클래스 상수): `DEFAULT=25`, `MIN=10`, `MAX=1000`, `RECURSION_STEP_FACTOR=10`, `RECURSION_BUFFER=20`, `SUB_AGENT_DIVISOR=2`, `SUB_AGENT_MIN=5`. 메서드: `validate(v)`(범위 밖 ValueError), `derive_recursion_limit(v) -> v*FACTOR+BUFFER`, `sub_agent_limit(parent) -> max(parent//DIVISOR, SUB_AGENT_MIN)`. `AgentDefinition.max_iterations: int = 25` 필드 추가, `__post_init__`에서 `IterationLimitPolicy.validate()` 호출 | 계수·범위를 상수 1곳에 집약 — 사용자 결정("문제 시 바로 변경"). `apply_update()`가 `__post_init__` 재실행하므로 update 검증 자동 |
| D3 | **recursion_limit 파생식 = `max_iterations × 10 + 20`**: `_build_graph_config`에 `config["recursion_limit"] = IterationLimitPolicy.derive_recursion_limit(agent.max_iterations)` 추가 | 최악 경로(반복당 5스텝 + quality_gate 재시도 8스텝) 대비 여유. recursion_limit은 단순 카운터라 큰 값의 비용 없음 — state 가드가 항상 먼저 발동하는 것이 목적. 25회 기본 → 270 스텝 |
| D4 | **DB/매핑**: `V045__alter_agent_definition_add_max_iterations.sql` — `ALTER TABLE agent_definition ADD COLUMN max_iterations INT NOT NULL DEFAULT 25;` (FK 아님, 콜레이션 무관). `AgentDefinitionModel.max_iterations`(default=25) + repository save/update/_to_domain 매핑. fork/auto-fork는 원본 값 승계 | additive — 기존 행 자동 25. 기존 하드코딩 10보다 관대해지는 방향이라 회귀 위험 낮음 |
| D5 | **가드 플래그**: `SupervisorState.limit_reached: bool` additive 필드(`build_initial_state`에서 False). supervisor의 **iteration 가드**는 `{"next_worker": "__end__", "limit_reached": True}` 반환. **token_limit 가드는 현행 유지**(플래그 없음) | 이번 범위는 반복 한도. token 한도 동일 처리 여부는 별도 판단(Out of Scope). LLM 결정 실패 폴백(`:231`)과 구분됨 — 실패 폴백은 조기 답변 대상 아님 |
| D6 | **라우팅 보완**: `route_to_worker_or_final`의 final_answer 조건을 `next_worker == "__end__" and (last_worker_id or limit_reached)`로 확장 | 워커 미실행 상태로 한도 도달해도(이론상 forced_worker 루프 등) 답변 없이 END 직행하지 않게 보장 (FR-04). 워커 산출물이 없으면 final_answer가 "(수집된 결과 없음)" + 대화 맥락으로 답변 — 기존 동작 재사용 |
| D7 | **알림 = payload 플래그(신규 이벤트 타입 없음)**: ① final_answer 노드가 `state.get("limit_reached")`면 answer_prompt에 안내 지시 1블록 추가 — "반복 한도에 도달하여 지금까지 수집된 정보만으로 답변함을 자연스럽게 언급하고, 부족한 부분은 부족하다고 명시하라". ② `_StreamState.limit_reached: bool` 추가, `_map_chain_end`에서 노드 출력 dict의 `limit_reached=True` 감지 시 세팅. ③ `answer_payload["limit_reached"] = True`를 **True일 때만** 포함(charts 선례와 동형) | 사용자 결정(이벤트+답변 안내). 9종 이벤트 카탈로그 계약 불변 — SSE/WS/프론트 파서 무수정으로 하위호환. 프론트 후속 작업은 `ANSWER_COMPLETED.payload.limit_reached`만 읽으면 됨 |
| D8 | **sub-agent**: `_wrap_sub_agent`에서 `SupervisorConfig(max_iterations=IterationLimitPolicy.sub_agent_limit(state["max_iterations"]), token_limit=state["token_limit"] // 2)` + `sub_graph.ainvoke(sub_initial, config={"recursion_limit": derive_recursion_limit(sub_limit)})` | token_limit 절반 선례와 동형. 서브 그래프도 config 미전달 시 기본 25 스텝에 걸리는 동일 결함 보유(코드 확인) — 함께 해소. depth 최대 2 + 절반 상속으로 중첩 폭주 방지 |
| D9 | **GraphRecursionError 안전망**: `stream()`의 기존 `except Exception` **앞에** `except GraphRecursionError`(from `langgraph.errors`) 분기 추가. 처리: warning 로그 → `_parse_result({"messages": state.final_messages})`로 강등 답변 시도 → 답변이 비어있지 않으면 assistant 메시지 저장 + `ANSWER_COMPLETED`(payload에 `limit_reached: True`) + tracker `complete_run` + `RUN_COMPLETED` / 비어있으면 기존 RUN_FAILED 경로 | FR-06. D3 파생식으로 실제 발동 확률은 낮지만, 발동 시에도 "오류 대신 답변" 원칙 유지. 정상 경로와 동일한 저장·이벤트 시퀀스 준수(계약 위반 없음) |
| D10 | **API 스키마(additive)**: `CreateAgentRequest.max_iterations: int = Field(25, ge=10, le=1000)` / `UpdateAgentRequest.max_iterations: int \| None = Field(None, ge=10, le=1000)`(None=변경 안 함) / `CreateAgentResponse`·`GetAgentResponse`에 `max_iterations: int` 추가. `AgentDefinition.apply_update`에 `max_iterations: int \| None = None` 파라미터 추가 | pydantic ge/le로 422 자동 처리 + 도메인 `__post_init__` 이중 가드. 응답 노출은 후속 Studio UI 폼 프라임용. `UpdateAgentResponse`·`AgentSummary`는 미변경(YAGNI — 목록에 불필요) |

---

## 3. 파일 구조 (신규/수정)

```
idt/
├── db/migration/
│   └── V045__alter_agent_definition_add_max_iterations.sql   [신규] ALTER + DEFAULT 25
├── src/
│   ├── domain/agent_builder/
│   │   ├── policies.py            [수정] IterationLimitPolicy 추가 (D2)
│   │   └── schemas.py             [수정] AgentDefinition.max_iterations + __post_init__ 검증
│   │                                     + apply_update 파라미터 (D2, D10)
│   │                                     + SupervisorConfig 기본 10→25 (D1)
│   ├── application/agent_builder/
│   │   ├── supervisor_state.py    [수정] limit_reached: bool 필드 (D5)
│   │   ├── supervisor_nodes.py    [수정] build_initial_state 초기값 / iteration 가드 플래그 (D5)
│   │   │                                 / route_to_worker_or_final 조건 확장 (D6)
│   │   ├── workflow_compiler.py   [수정] final_answer 안내 블록 (D7) / _wrap_sub_agent 한도·config (D8)
│   │   ├── run_agent_use_case.py  [수정] SupervisorConfig 주입 (D1) / recursion_limit (D3)
│   │   │                                 / _StreamState.limit_reached + _map_chain_end 캡처
│   │   │                                 / answer_payload 플래그 (D7) / GraphRecursionError 안전망 (D9)
│   │   ├── schemas.py             [수정] Create/Update 요청 + Create/Get 응답 (D10)
│   │   ├── create_agent_use_case.py [수정] AgentDefinition 생성 시 전달
│   │   ├── update_agent_use_case.py [수정] apply_update 전달
│   │   ├── fork_agent_use_case.py   [수정] 원본 값 승계 (D4)
│   │   └── auto_fork_service.py     [수정] 원본 값 승계 (D4)
│   └── infrastructure/agent_builder/
│       ├── models.py                        [수정] 컬럼 매핑 (default=25)
│       └── agent_definition_repository.py   [수정] save/update/_to_domain 매핑
└── tests/ (§5)
```

프론트(idt_front)는 이번 범위 밖 — 응답 additive 필드라 기존 파서 무해. 후속 UI 작업 시 `/api-cotract` 실행.

---

## 4. 실행 흐름 (한도 도달 시나리오)

```
run(agent)                                          agent.max_iterations = 25 (DB)
 ├─ SupervisorConfig(max_iterations=25)             ← D1
 ├─ graph_config["recursion_limit"] = 270           ← D3 (25×10+20)
 └─ astream_events(...)
      supervisor(iter 0..24) → worker → [chart_*] → quality_gate → supervisor ...
      supervisor(iter 25): iteration_count(25) >= max_iterations(25)
        → {"next_worker": "__end__", "limit_reached": True}       ← D5
      route_to_worker_or_final: __end__ + (last_worker_id or limit_reached)
        → "final_answer"                                          ← D6
      final_answer: limit_reached → 안내 지시 블록 + 수집 결과 종합 답변  ← D7-①
        → END (정상 종료)
 ├─ _map_chain_end: supervisor 출력에서 limit_reached 캡처            ← D7-②
 ├─ ANSWER_COMPLETED {answer, tools_used, limit_reached: true}      ← D7-③
 └─ RUN_COMPLETED

(만에 하나 GraphRecursionError → state.final_messages로 강등 답변 → 동일 시퀀스, 실패 시에만 RUN_FAILED)  ← D9
```

---

## 5. 테스트 설계 (TDD — 구현 전 작성)

| 파일 | 케이스 |
|------|--------|
| `tests/domain/agent_builder/test_iteration_limit_policy.py` [신규] | validate: 9→에러/10/1000 통과/1001→에러 · derive_recursion_limit(25)=270 · sub_agent_limit(25)=12, (10)=5, 하한 보장 |
| `tests/domain/agent_builder/test_agent_definition.py`(기존 확장) | 기본값 25 · 범위 밖 생성 에러 · apply_update(max_iterations) 반영+재검증 |
| `tests/application/agent_builder/test_supervisor_nodes.py`(기존 확장) | iteration 가드 반환에 `limit_reached: True` · token 가드는 플래그 없음(현행) · route_to_worker_or_final: `__end__`+limit_reached(워커 미실행)→final_answer, LLM 실패 폴백(플래그 없음)→기존 동작 |
| `tests/application/agent_builder/test_run_agent_use_case.py`(기존 확장) | agent.max_iterations → SupervisorConfig·initial_state 반영 · graph_config에 recursion_limit=파생값 · 한도 도달 스트림 → ANSWER_COMPLETED.limit_reached=True + RUN_COMPLETED(RUN_FAILED 없음) · GraphRecursionError → 강등 답변 성공/실패 두 분기 |
| `tests/application/agent_builder/test_workflow_compiler.py`(기존 확장) | final_answer: limit_reached 시 프롬프트에 안내 지시 포함 · _wrap_sub_agent: 절반 한도 + ainvoke config recursion_limit 전달 |
| `tests/application/agent_builder/test_create_agent_use_case.py` 등(기존 확장) | 요청 max_iterations 저장 · 미전달 시 25 · 범위 밖 422(라우터) · fork 승계 |

**사전 실패분 주의**: tests/api 28건·infra 30건은 기존 실패(2026-06-10 확인) — 신규 회귀로 오인 금지.

## 6. 구현 순서

1. V045 마이그레이션 + models.py + repository 매핑 (D4)
2. IterationLimitPolicy + AgentDefinition/SupervisorConfig (D1, D2)
3. API 스키마 + create/update/fork 유스케이스 배선 (D10)
4. supervisor_state/nodes — 플래그·라우팅 (D5, D6)
5. run_agent_use_case — 주입·recursion_limit·payload·안전망 (D1, D3, D7, D9)
6. workflow_compiler — final_answer 안내·sub-agent (D7, D8)
7. 전체 테스트 + `/pdca analyze agent-recursion-limit`

## 7. 영향 범위 / 주의사항

- **동작 변화**: 기존 에이전트의 실효 한도가 "recursion 25스텝(≈5~8회)에서 오류" → "25회 반복 후 조기 답변"으로 완화·안정화. 의도된 변경(Plan FR-03/04)
- **금지사항 준수**: 레이어 이동 없음, 대화 메모리 정책·Parent/Child 구조 무관, 스키마 변경은 additive 마이그레이션
- **로깅**: 한도 도달(기존 warning 유지)·안전망 발동(warning, request_id 포함) — 스택 트레이스 있는 에러 처리(LOG-001)
- **프론트 계약**: 응답·payload 모두 additive. Studio UI 후속 작업에서 `/api-cotract`로 타입 동기화 필수
