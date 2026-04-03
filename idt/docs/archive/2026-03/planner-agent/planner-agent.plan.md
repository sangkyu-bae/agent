# Plan: planner-agent

> Feature: 공통 Planner Agent (질문 분석 → 실행 계획 생성)
> Task ID: AGENT-007
> Created: 2026-03-25
> Status: Plan

---

## 1. 목적 (Why)

특정 질문이 들어왔을 때 **다른 Agent/Workflow가 재사용할 수 있는 공통 Planner Agent**를 제공한다.

- 복잡한 질문을 단계별 실행 계획(Plan)으로 분해
- 필요한 도구(Tool) 및 검색 전략 추론
- 다른 Agent(RAG Agent, Research Team, Auto Agent Builder 등)가 Planner를 호출하여 실행 계획을 받아 처리

```
[사용자 질문]
    ↓
[PlannerAgent] ── 질문 분석 → 단계 분해 → 도구 선택 → PlanResult 반환
    ↓
[실행 Agent / Workflow] ── PlanResult를 기반으로 실제 작업 수행
```

---

## 2. 기능 범위 (Scope)

### In Scope
- 자연어 질문 → `PlanResult` (실행 계획) 생성
- 단계(Step) 분해: 각 단계의 목적, 필요 도구, 예상 입출력 명시
- 도구 추론: tool_registry 기반 도구 필요 여부 판단
- 검색 전략 추론: Vector / BM25 / Hybrid 검색 필요 여부 판단
- 신뢰도(confidence) 산출: 계획 생성의 불확실성 반영
- LangGraph StateGraph 기반 단일 노드 또는 재계획(replan) 루프 지원
- `PlannerInterface` 추상화로 교체 가능한 구조 제공

### Out of Scope
- 계획 실행 (Planner는 계획만 생성, 실행은 호출자가 담당)
- 멀티턴 대화 세션 관리 (필요 시 CONV-001 / AGENT-006 재사용)
- 도구 직접 호출
- 사용자에게 결과 직접 반환하는 API 엔드포인트 (standalone API는 선택적)

---

## 3. 기술 의존성

| 모듈 | Task ID | 상태 |
|------|---------|------|
| LoggerInterface | LOG-001 | 구현됨 |
| LangGraph StateGraph | (LangChain 내장) | 사용 가능 |
| ChatOpenAI | (LangChain 내장) | 사용 가능 |
| tool_registry (도구 목록) | AGENT-004 | 구현됨 |
| RedisRepository (optional 캐싱) | REDIS-001 | 구현됨 |

---

## 4. 도메인 설계

### PlanStep (Value Object, frozen)

| 필드 | 타입 | 설명 |
|------|------|------|
| step_index | int | 단계 순서 (0부터) |
| description | str | 이 단계에서 할 일 |
| tool_ids | list[str] | 필요한 도구 ID 목록 (없으면 빈 리스트) |
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
| clarifying_questions | list[str] | 필요 시 보충 질문 목록 |

### PlannerPolicy (Domain Policy)

| 상수 | 값 | 설명 |
|------|----|------|
| CONFIDENCE_THRESHOLD | 0.75 | 이상이면 계획 확정 |
| MAX_STEPS | 10 | 최대 단계 수 |
| MAX_REPLAN_ATTEMPTS | 2 | 재계획 최대 횟수 |

메서드:
- `is_plan_acceptable(result) -> bool`: confidence >= threshold AND steps 있음
- `needs_replan(result) -> bool`: 신뢰도 낮거나 steps 비어있음

### PlannerInterface (Domain Interface)

```python
class PlannerInterface(ABC):
    @abstractmethod
    async def plan(self, query: str, context: dict, request_id: str) -> PlanResult:
        """질문과 컨텍스트를 받아 실행 계획 반환"""
```

---

## 5. 아키텍처 (Thin DDD)

```
domain/planner/
├── schemas.py      # PlanStep, PlanResult (Pydantic frozen BaseModel)
├── policies.py     # PlannerPolicy
└── interfaces.py   # PlannerInterface (ABC)

application/planner/
├── schemas.py          # PlanRequest, PlanResponse (API 스키마)
└── plan_use_case.py    # PlanUseCase (PlannerInterface 주입)

infrastructure/planner/
└── langgraph_planner.py  # LangGraph 기반 PlannerInterface 구현
    # StateGraph: plan_node → (replan? → replan_node) → END
    # ChatOpenAI + JSON 구조화 출력

api/routes/ (선택적)
└── planner_router.py  # POST /api/v1/planner/plan (독립 엔드포인트 필요 시)
```

---

## 6. LangGraph 상태 흐름

```
PlannerState (TypedDict):
  - query: str
  - context: dict
  - plan_result: PlanResult | None
  - attempt_count: int
  - request_id: str

노드:
  plan_node     → LLM 호출하여 PlanResult 생성
  validate_node → PlannerPolicy로 계획 유효성 검사
  replan_node   → 재계획 (MAX_REPLAN_ATTEMPTS 이내)

엣지:
  plan_node → validate_node
  validate_node → END (acceptable)
               → replan_node (needs_replan, attempt < max)
               → END (max attempt 초과, 현재 결과 반환)
  replan_node → validate_node
```

---

## 7. 재사용 시나리오

| 호출 주체 | 사용 방식 |
|----------|----------|
| RAG Agent (RAG-001) | 복잡한 질문 전처리로 PlanResult 생성 후 단계별 검색 |
| Research Team (AGENT-003) | Supervisor가 PlanResult steps를 각 팀원에게 배분 |
| Auto Agent Builder (AGENT-006) | 자연어 요청 분석 시 Planner로 도구 선택 보완 |
| 미래 Orchestrator | 범용 계획 → 실행 파이프라인 구성 |

---

## 8. TDD 계획

```
테스트 파일                                                구현 파일
─────────────────────────────────────────────────────────────────────
tests/domain/planner/test_schemas.py              → domain/planner/schemas.py
tests/domain/planner/test_policies.py             → domain/planner/policies.py
tests/infrastructure/planner/test_langgraph_planner.py → infrastructure/planner/langgraph_planner.py
tests/application/planner/test_plan_use_case.py   → application/planner/plan_use_case.py
tests/api/test_planner_router.py (선택적)          → api/routes/planner_router.py
```

---

## 9. CLAUDE.md 규칙 체크

- [x] domain에 외부 의존성 없음 (인터페이스, Pydantic만 사용)
- [x] LangGraph는 infrastructure 레이어에만 위치
- [x] application은 PlannerInterface만 주입받아 사용
- [x] LOG-001 로깅 적용 (LoggerInterface 주입)
- [x] TDD 순서: 테스트 → 구현
- [x] print() 사용 금지

---

## 10. 완료 기준

- [ ] `PlanStep`, `PlanResult` Pydantic frozen 모델 구현
- [ ] `PlannerPolicy` 도메인 정책 구현
- [ ] `PlannerInterface` 추상 인터페이스 정의
- [ ] `LangGraphPlanner` StateGraph 구현 (plan → validate → [replan] → END)
- [ ] `PlanUseCase` 구현 (PlannerInterface 주입)
- [ ] 단위 테스트 전체 통과
- [ ] LOG-001 로깅 체크리스트 충족
