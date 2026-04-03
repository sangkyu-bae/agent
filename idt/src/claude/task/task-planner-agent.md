# AGENT-007: Planner Agent

> Task ID: AGENT-007
> 의존성: LOG-001, AGENT-004
> 선택적 의존성: REDIS-001
> 관련 스킬: langgraph, tdd
> Plan 문서: docs/01-plan/features/planner-agent.plan.md

---

## 개요

특정 질문이 들어왔을 때 다른 Agent/Workflow가 **공통으로 재사용**할 수 있는 Planner Agent 모듈.

자연어 질문을 받아 실행 단계(Steps), 필요 도구(Tools), 검색 전략(Search Strategy)으로 구성된
`PlanResult`를 반환한다. **계획 생성만 담당하며 실행은 호출자가 담당한다.**

---

## 아키텍처

```
domain/planner/
├── schemas.py      # PlanStep, PlanResult (frozen Pydantic)
├── policies.py     # PlannerPolicy (threshold=0.75, max_steps=10)
└── interfaces.py   # PlannerInterface (ABC)

application/planner/
├── schemas.py          # PlanRequest, PlanResponse
└── plan_use_case.py    # PlanUseCase

infrastructure/planner/
└── langgraph_planner.py  # LangGraphPlanner (PlannerInterface 구현)

api/routes/ (선택적)
└── planner_router.py  # POST /api/v1/planner/plan
```

---

## 도메인 스키마

### PlanStep (Value Object, frozen)

| 필드 | 타입 | 설명 |
|------|------|------|
| step_index | int | 단계 순서 (0부터) |
| description | str | 이 단계에서 할 일 |
| tool_ids | list[str] | 필요한 도구 ID 목록 |
| search_strategy | str \| None | "vector" \| "bm25" \| "hybrid" \| None |
| expected_output | str | 이 단계의 예상 출력 |

### PlanResult (Value Object, frozen)

| 필드 | 타입 | 설명 |
|------|------|------|
| query | str | 원본 질문 |
| steps | list[PlanStep] | 실행 단계 목록 |
| confidence | float | 0.0~1.0, 계획 신뢰도 |
| reasoning | str | 계획 수립 근거 |
| requires_clarification | bool | 추가 정보 필요 여부 |
| clarifying_questions | list[str] | 보충 질문 목록 |

---

## 도메인 정책 (PlannerPolicy)

| 상수 | 값 | 설명 |
|------|----|------|
| CONFIDENCE_THRESHOLD | 0.75 | 이상이면 계획 확정 |
| MAX_STEPS | 10 | 최대 단계 수 |
| MAX_REPLAN_ATTEMPTS | 2 | 재계획 최대 횟수 |

메서드:
- `is_plan_acceptable(result: PlanResult) -> bool`
- `needs_replan(result: PlanResult) -> bool`

---

## PlannerInterface (Domain)

```python
class PlannerInterface(ABC):
    @abstractmethod
    async def plan(self, query: str, context: dict, request_id: str) -> PlanResult:
        """질문과 컨텍스트를 받아 실행 계획 반환"""
```

---

## LangGraph 상태 흐름 (infrastructure)

```
PlannerState (TypedDict):
  query: str
  context: dict
  plan_result: PlanResult | None
  attempt_count: int
  request_id: str

노드:
  plan_node     → ChatOpenAI 호출, JSON → PlanResult 변환
  validate_node → PlannerPolicy.is_plan_acceptable() 판정
  replan_node   → 재계획 프롬프트로 재시도

엣지:
  plan_node → validate_node
  validate_node → END                    (acceptable)
               → replan_node             (needs_replan & attempt < max)
               → END                    (max attempt 초과)
  replan_node → validate_node
```

---

## PlanUseCase (application)

```python
class PlanUseCase:
    def __init__(self, planner: PlannerInterface, logger: LoggerInterface):
        ...

    async def execute(self, request: PlanRequest) -> PlanResponse:
        # 1. 로깅 시작
        # 2. planner.plan() 호출
        # 3. PlanResponse 변환 후 반환
```

---

## 재사용 시나리오

| 호출 주체 | 사용 방식 |
|----------|----------|
| RAG Agent (RAG-001) | 복잡한 질문 전처리 → 단계별 검색 |
| Research Team (AGENT-003) | Supervisor가 steps를 팀원에게 배분 |
| Auto Agent Builder (AGENT-006) | 자연어 요청 분석 보완 |
| 미래 Orchestrator | 범용 계획 → 실행 파이프라인 |

---

## LOG-001 적용 체크리스트

- [ ] LoggerInterface 주입 (PlanUseCase, LangGraphPlanner)
- [ ] 계획 시작/완료/재계획/실패 INFO/WARNING/ERROR 로그
- [ ] request_id 전파 (모든 메서드 signature)
- [ ] exception= 포함 에러 로그
- [ ] print() 사용 금지

---

## TDD 구현 순서

1. `tests/domain/planner/test_schemas.py` → `domain/planner/schemas.py`
2. `tests/domain/planner/test_policies.py` → `domain/planner/policies.py`
3. `tests/infrastructure/planner/test_langgraph_planner.py` → `infrastructure/planner/langgraph_planner.py`
4. `tests/application/planner/test_plan_use_case.py` → `application/planner/plan_use_case.py`
5. (선택) `tests/api/test_planner_router.py` → `api/routes/planner_router.py`
