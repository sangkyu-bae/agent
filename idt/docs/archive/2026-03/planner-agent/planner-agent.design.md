# Design: planner-agent

> Feature: 공통 Planner Agent (질문 분석 → 실행 계획 생성)
> Created: 2026-03-25
> Status: Design
> Depends-On: planner-agent.plan.md

---

## 1. 레이어별 파일 구조

```
src/
├── domain/
│   └── planner/
│       ├── __init__.py
│       ├── schemas.py      # PlanStep, PlanResult (frozen Pydantic VO)
│       ├── policies.py     # PlannerPolicy
│       └── interfaces.py   # PlannerInterface (ABC)
│
├── application/
│   └── planner/
│       ├── __init__.py
│       ├── schemas.py          # PlanRequest, PlanResponse
│       └── plan_use_case.py    # PlanUseCase
│
├── infrastructure/
│   └── planner/
│       ├── __init__.py
│       └── langgraph_planner.py   # LangGraphPlanner (PlannerInterface 구현)
│
└── api/
    └── routes/
        └── planner_router.py  # POST /api/v1/planner/plan (선택적)

tests/
├── domain/planner/
│   ├── test_schemas.py
│   └── test_policies.py
├── infrastructure/planner/
│   └── test_langgraph_planner.py
├── application/planner/
│   └── test_plan_use_case.py
└── api/
    └── test_planner_router.py  (선택적)
```

---

## 2. Domain Layer

### 2-1. `src/domain/planner/schemas.py`

```python
from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, Field


class PlanStep(BaseModel):
    """단일 실행 단계 (Value Object, immutable)."""

    model_config = {"frozen": True}

    step_index: int = Field(..., ge=0, description="단계 순서 (0부터)")
    description: str = Field(..., min_length=1, description="이 단계에서 할 일")
    tool_ids: List[str] = Field(default_factory=list, description="필요한 도구 ID 목록")
    search_strategy: Optional[str] = Field(
        default=None,
        description="vector | bm25 | hybrid | None",
    )
    expected_output: str = Field(..., min_length=1, description="이 단계의 예상 출력")


class PlanResult(BaseModel):
    """전체 실행 계획 (Value Object, immutable)."""

    model_config = {"frozen": True}

    query: str = Field(..., min_length=1)
    steps: List[PlanStep] = Field(default_factory=list)
    confidence: float = Field(..., ge=0.0, le=1.0)
    reasoning: str = Field(default="")
    requires_clarification: bool = Field(default=False)
    clarifying_questions: List[str] = Field(default_factory=list)
```

### 2-2. `src/domain/planner/policies.py`

```python
from src.domain.planner.schemas import PlanResult


class PlannerPolicy:
    CONFIDENCE_THRESHOLD: float = 0.75
    MAX_STEPS: int = 10
    MAX_REPLAN_ATTEMPTS: int = 2

    @classmethod
    def is_plan_acceptable(cls, result: PlanResult) -> bool:
        """계획이 실행 가능한 품질인지 판정."""
        return (
            result.confidence >= cls.CONFIDENCE_THRESHOLD
            and len(result.steps) > 0
            and not result.requires_clarification
        )

    @classmethod
    def needs_replan(cls, result: PlanResult) -> bool:
        """재계획이 필요한지 판정."""
        return not cls.is_plan_acceptable(result)

    @classmethod
    def is_max_attempts_reached(cls, attempt_count: int) -> bool:
        return attempt_count >= cls.MAX_REPLAN_ATTEMPTS
```

### 2-3. `src/domain/planner/interfaces.py`

```python
from abc import ABC, abstractmethod
from src.domain.planner.schemas import PlanResult


class PlannerInterface(ABC):
    @abstractmethod
    async def plan(
        self,
        query: str,
        context: dict,
        request_id: str,
    ) -> PlanResult:
        """질문과 컨텍스트를 받아 실행 계획 반환."""
```

---

## 3. Application Layer

### 3-1. `src/application/planner/schemas.py`

```python
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from src.domain.planner.schemas import PlanResult


class PlanRequest(BaseModel):
    query: str = Field(..., min_length=1)
    context: Dict[str, Any] = Field(default_factory=dict)
    request_id: str


class PlanResponse(BaseModel):
    query: str
    steps: List[dict]           # PlanStep.model_dump() 목록
    confidence: float
    reasoning: str
    requires_clarification: bool
    clarifying_questions: List[str]
    request_id: str

    @classmethod
    def from_domain(cls, result: PlanResult, request_id: str) -> "PlanResponse":
        return cls(
            query=result.query,
            steps=[s.model_dump() for s in result.steps],
            confidence=result.confidence,
            reasoning=result.reasoning,
            requires_clarification=result.requires_clarification,
            clarifying_questions=result.clarifying_questions,
            request_id=request_id,
        )
```

### 3-2. `src/application/planner/plan_use_case.py`

**의존성 주입:**
- `planner: PlannerInterface`
- `logger: LoggerInterface`

**실행 흐름:**
```
execute(request: PlanRequest) → PlanResponse

1. logger.info("Planner started", ...)
2. planner.plan(query, context, request_id) 호출
3. PlanResponse.from_domain(result, request_id) 변환
4. logger.info("Planner completed", ...)
5. PlanResponse 반환
```

```python
class PlanUseCase:
    def __init__(self, planner: PlannerInterface, logger: LoggerInterface) -> None:
        self._planner = planner
        self._logger = logger

    async def execute(self, request: PlanRequest) -> PlanResponse:
        self._logger.info(
            "Planner started",
            request_id=request.request_id,
            query_len=len(request.query),
        )
        try:
            result = await self._planner.plan(
                query=request.query,
                context=request.context,
                request_id=request.request_id,
            )
            self._logger.info(
                "Planner completed",
                request_id=request.request_id,
                steps=len(result.steps),
                confidence=result.confidence,
            )
            return PlanResponse.from_domain(result, request.request_id)
        except Exception as e:
            self._logger.error(
                "Planner failed",
                exception=e,
                request_id=request.request_id,
            )
            raise
```

---

## 4. Infrastructure Layer

### `src/infrastructure/planner/langgraph_planner.py`

#### PlannerState (TypedDict)

```python
from typing import Optional, TypedDict
from src.domain.planner.schemas import PlanResult


class PlannerState(TypedDict):
    query: str
    context: dict
    plan_result: Optional[PlanResult]
    attempt_count: int
    request_id: str
```

#### LangGraphPlanner

```python
class LangGraphPlanner(PlannerInterface):
    def __init__(self, llm: BaseChatModel, logger: LoggerInterface) -> None:
        self._llm = llm
        self._logger = logger
        self._graph = self._build_graph()

    def _build_graph(self) -> CompiledGraph:
        graph = StateGraph(PlannerState)
        graph.add_node("plan_node", self._plan_node)
        graph.add_node("validate_node", self._validate_node)
        graph.add_node("replan_node", self._replan_node)

        graph.set_entry_point("plan_node")
        graph.add_edge("plan_node", "validate_node")
        graph.add_conditional_edges(
            "validate_node",
            self._route_after_validate,
            {"end": END, "replan": "replan_node"},
        )
        graph.add_edge("replan_node", "validate_node")
        return graph.compile()

    async def plan(self, query: str, context: dict, request_id: str) -> PlanResult:
        initial_state = PlannerState(
            query=query,
            context=context,
            plan_result=None,
            attempt_count=0,
            request_id=request_id,
        )
        final_state = await self._graph.ainvoke(initial_state)
        return final_state["plan_result"]
```

#### 노드 메서드

```python
async def _plan_node(self, state: PlannerState) -> PlannerState:
    """LLM 호출하여 초기 PlanResult 생성."""
    prompt = self._build_prompt(state["query"], state["context"], replan=False)
    raw = await self._llm.ainvoke(prompt)
    plan_result = self._parse_llm_response(raw.content, state["query"])
    return {**state, "plan_result": plan_result, "attempt_count": 1}

async def _validate_node(self, state: PlannerState) -> PlannerState:
    """PlannerPolicy로 유효성 검사 (상태 변경 없음, 라우팅용)."""
    return state

async def _replan_node(self, state: PlannerState) -> PlannerState:
    """재계획 프롬프트로 LLM 재호출."""
    prompt = self._build_prompt(state["query"], state["context"], replan=True,
                                 prev_result=state["plan_result"])
    raw = await self._llm.ainvoke(prompt)
    plan_result = self._parse_llm_response(raw.content, state["query"])
    return {**state, "plan_result": plan_result, "attempt_count": state["attempt_count"] + 1}

def _route_after_validate(self, state: PlannerState) -> str:
    result = state["plan_result"]
    if PlannerPolicy.is_plan_acceptable(result):
        return "end"
    if PlannerPolicy.is_max_attempts_reached(state["attempt_count"]):
        return "end"   # 최대 시도 초과 → 현재 결과 반환
    return "replan"
```

#### LLM 프롬프트 구조

**초기 계획 프롬프트:**
```
System:
당신은 복잡한 질문을 단계별 실행 계획으로 분해하는 전문가입니다.
다음 JSON 형식으로만 응답하세요:
{
  "steps": [
    {
      "step_index": 0,
      "description": "...",
      "tool_ids": [],
      "search_strategy": "hybrid|vector|bm25|null",
      "expected_output": "..."
    }
  ],
  "confidence": 0.0~1.0,
  "reasoning": "...",
  "requires_clarification": false,
  "clarifying_questions": []
}

사용 가능한 도구: {tool_ids_from_registry}

User:
질문: {query}
컨텍스트: {context}
```

**재계획 프롬프트 추가 내용:**
```
이전 계획의 문제점:
- confidence: {prev_confidence} (0.75 미만)
- 부족한 부분: {prev_reasoning}

더 구체적이고 신뢰도 높은 계획을 다시 작성하세요.
```

#### JSON 파싱 전략

```python
def _parse_llm_response(self, content: str, query: str) -> PlanResult:
    """LLM JSON 응답 → PlanResult 변환. 파싱 실패 시 저신뢰 fallback 반환."""
    try:
        data = json.loads(content)
        steps = [PlanStep(**s) for s in data.get("steps", [])]
        return PlanResult(
            query=query,
            steps=steps,
            confidence=float(data.get("confidence", 0.0)),
            reasoning=data.get("reasoning", ""),
            requires_clarification=data.get("requires_clarification", False),
            clarifying_questions=data.get("clarifying_questions", []),
        )
    except (json.JSONDecodeError, ValueError) as e:
        self._logger.warning("LLM response parse failed", exception=e, request_id="")
        # fallback: 저신뢰 PlanResult → replan 유도
        return PlanResult(
            query=query,
            steps=[],
            confidence=0.0,
            reasoning="JSON parse failed",
            requires_clarification=False,
        )
```

---

## 5. API Layer (선택적)

### `src/api/routes/planner_router.py`

**Endpoint:**
```
POST /api/v1/planner/plan
```

**Request Schema:**
```python
class PlanRequestSchema(BaseModel):
    query: str
    context: Dict[str, Any] = Field(default_factory=dict)
    request_id: str = Field(default_factory=lambda: str(uuid4()))
```

**Response Schema:**
```python
class PlanResponseSchema(BaseModel):
    query: str
    steps: List[Dict[str, Any]]
    confidence: float
    reasoning: str
    requires_clarification: bool
    clarifying_questions: List[str]
    request_id: str
```

**DI 패턴:**
```python
def get_plan_use_case() -> PlanUseCase:
    raise NotImplementedError  # create_app()에서 override
```

---

## 6. main.py 변경사항 (선택적 엔드포인트 등록 시)

```python
# lifespan: planner use case 초기화
def create_plan_use_case() -> PlanUseCase:
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    planner = LangGraphPlanner(llm=llm, logger=logger)
    return PlanUseCase(planner=planner, logger=logger)

# create_app()에 라우터 등록
app.include_router(planner_router)
app.dependency_overrides[get_plan_use_case] = lambda: _plan_use_case
```

---

## 7. 테스트 설계

### `tests/domain/planner/test_schemas.py`

| 케이스 | 설명 |
|--------|------|
| test_plan_step_is_frozen | frozen=True, 수정 불가 |
| test_plan_step_tool_ids_default_empty | tool_ids 기본값 빈 리스트 |
| test_plan_result_is_frozen | frozen=True, 수정 불가 |
| test_plan_result_confidence_range | confidence 0.0~1.0 범위 검증 |
| test_plan_result_steps_default_empty | steps 기본값 빈 리스트 |

### `tests/domain/planner/test_policies.py`

| 케이스 | 설명 |
|--------|------|
| test_is_plan_acceptable_true | confidence≥0.75, steps 있음 → True |
| test_is_plan_acceptable_false_low_confidence | confidence<0.75 → False |
| test_is_plan_acceptable_false_empty_steps | steps 비어있음 → False |
| test_is_plan_acceptable_false_requires_clarification | requires_clarification=True → False |
| test_needs_replan_mirrors_is_plan_acceptable | needs_replan = not is_plan_acceptable |
| test_is_max_attempts_reached | attempt_count >= MAX_REPLAN_ATTEMPTS → True |

### `tests/infrastructure/planner/test_langgraph_planner.py`

| 케이스 | 설명 |
|--------|------|
| test_plan_returns_plan_result | 정상 LLM 응답 → PlanResult 반환 |
| test_plan_triggers_replan_on_low_confidence | 저신뢰 응답 → replan_node 실행 |
| test_plan_stops_at_max_attempts | MAX_REPLAN_ATTEMPTS 도달 시 현재 결과 반환 |
| test_plan_parse_failure_fallback | JSON 파싱 실패 → 저신뢰 fallback PlanResult |
| test_plan_logs_on_parse_failure | WARNING 로그 기록 확인 |

> 주의: `LangGraphPlanner` 테스트는 `BaseChatModel` Mock을 사용한다.
> 도메인 테스트(`test_schemas`, `test_policies`)는 Mock 금지.

### `tests/application/planner/test_plan_use_case.py`

| 케이스 | 설명 |
|--------|------|
| test_execute_returns_response | PlannerInterface Mock → PlanResponse 반환 |
| test_execute_logs_start_and_complete | INFO 로그 2회 기록 확인 |
| test_execute_logs_error_on_exception | exception 발생 시 ERROR 로그 + 재발생 |
| test_execute_propagates_request_id | request_id가 planner.plan()에 전달됨 |

### `tests/api/test_planner_router.py` (선택적)

| 케이스 | 설명 |
|--------|------|
| test_plan_returns_200 | 정상 응답 |
| test_plan_empty_query_returns_422 | 빈 query 검증 |
| test_plan_response_schema | 응답 스키마 일치 확인 |

---

## 8. 로깅 (LOG-001)

```python
# PlanUseCase - 시작
logger.info("Planner started", request_id=request_id, query_len=len(query))

# PlanUseCase - 완료
logger.info("Planner completed", request_id=request_id, steps=n, confidence=c)

# PlanUseCase - 실패
logger.error("Planner failed", exception=e, request_id=request_id)

# LangGraphPlanner - 재계획
logger.info("Replanning", request_id=request_id, attempt=n, confidence=prev_confidence)

# LangGraphPlanner - JSON 파싱 실패
logger.warning("LLM response parse failed", exception=e, request_id=request_id)

# LangGraphPlanner - 최대 시도 초과
logger.warning("Max replan attempts reached", request_id=request_id, attempt=n)
```

---

## 9. 의존성 그래프

```
planner_router.py (선택적)
    └── PlanUseCase (application)
            └── PlannerInterface
                    └── LangGraphPlanner (infrastructure)
                            ├── BaseChatModel (ChatOpenAI)
                            ├── PlannerPolicy (domain) ← 라우팅 판정
                            └── LoggerInterface
```

---

## 10. CLAUDE.md 규칙 체크

- [x] domain → schemas, policies, interfaces만 (외부 의존성 없음)
- [x] LangGraph / LangChain은 infrastructure에만 위치
- [x] application은 PlannerInterface 주입받아 사용 (구현체 미참조)
- [x] LOG-001: LoggerInterface 주입, request_id 전파, exception= 포함
- [x] TDD: 테스트 파일이 구현 파일보다 먼저 작성됨
- [x] 함수 길이 40줄 이하, if 중첩 2단계 이하
- [x] print() 사용 금지