# Analysis Chart Router Design Document

> **Summary**: 분석 노드 직후 "시각화(visualize) vs 텍스트(text)"를 판단**만** 하는 라우팅 노드 설계.
> 판단 결과(`viz_decision`)를 상태에 기록하는 것까지가 이 설계의 범위. ChartSpec 생성·차트 빌드·프론트 렌더링은 **라우팅 이후 별도 노드**가 담당(Out of Scope).
>
> **Project**: sangplusbot (idt)
> **Version**: 0.1
> **Author**: 배상규
> **Date**: 2026-06-05
> **Status**: Draft
> **Planning Doc**: [analysis-chart-router.plan.md](../../01-plan/features/analysis-chart-router.plan.md)

---

## 1. Overview

### 1.1 Design Goals

1. **단일 책임 라우터**: 분석 결과를 받아 `visualize` / `text` 둘 중 하나로 **판단만** 한다. 차트 생성/렌더링은 하지 않는다.
2. **하이브리드 판단**: 키워드·데이터 휴리스틱(도메인 정책)으로 1차 결정, 애매한 구간만 LLM 분류로 보강.
3. **양쪽 워크플로우 공용**: `ExcelAnalysisWorkflow`와 `agent_builder` Supervisor 양쪽에서 동일 라우터를 재사용.
4. **다운스트림 무결합(Seam)**: 라우터는 `viz_decision`만 상태에 남긴다. 차트 처리 노드는 이후 이 값을 읽어 분기·처리한다. 라우터는 차트 노드의 존재를 모른다.

### 1.2 Scope (이번 설계 범위)

| 구분 | 항목 |
|------|------|
| ✅ In Scope | `VisualizationRoutingPolicy`(domain), `VisualizationClassifierInterface`(domain port), `chart_router` 노드(application), LLM 분류 어댑터(infra), 상태 필드 `viz_decision`, 두 그래프에 라우터 삽입 배선 |
| ❌ Out of Scope (후속 노드) | `ChartSpec` 스키마, `chart_builder` 노드, 차트 데이터 추출, 프론트 타입 동기화(`idt_front`), 응답 직렬화에 차트 노출 |

### 1.3 Design Principles

- **Domain Purity**: 휴리스틱 판단 규칙은 domain Policy, 외부 의존성 없음. LLM 호출은 port(interface)로 분리.
- **Graceful Fallback**: LLM 분류 실패/미주입 시 보수적으로 `text`로 떨어뜨려 본 답변 흐름을 막지 않는다.
- **Minimal Wiring Now**: 지금은 라우터가 상태만 기록하고 기존 후속(quality_gate/END)으로 그대로 진행. 실제 분기 엣지는 후속 노드 도입 시 부착(부착 지점만 설계에 명시).

---

## 2. Architecture

### 2.1 Routing-Only Position

```
            (분석 결과 AIMessage / analysis_text)
                          │
                          ▼
                 ┌──────────────────┐
                 │   chart_router   │   ← 이번 설계 대상 (판단만)
                 │ ─ 1차: Policy    │
                 │ ─ 2차: LLM(애매) │
                 └────────┬─────────┘
                          │  state["viz_decision"] = "visualize" | "text"
                          ▼
            (현재) 기존 후속 노드로 그대로 진행
            (후속) route_after_chart_router 로 분기 → [차트 처리 노드] / [텍스트 종료]
                          ▲
                          └─ 이 분기 부착은 별도 노드 작업(Out of Scope)
```

### 2.2 Decision Flow (chart_router 내부)

```
question(최근 user) + analysis_text(직전 분석)
        │
        ▼
VisualizationRoutingPolicy.decide(question, analysis_text)
        │
   ┌────┼─────────────────────────┐
   ▼    ▼                         ▼
"visualize"  "text"            None(애매)
   │          │                   │
   │          │                   ▼
   │          │        classifier 주입됨?
   │          │            │            │
   │          │           yes          no
   │          │            ▼            ▼
   │          │   classifier.classify  "text"(보수적)
   │          │     → "visualize"/"text"
   ▼          ▼            ▼
  state["viz_decision"] 확정 → 반환
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| chart_router 노드 | VisualizationRoutingPolicy | 1차 휴리스틱 판단 |
| chart_router 노드 | VisualizationClassifierInterface (optional) | 애매구간 LLM 분류 |
| LLMVisualizationClassifier | BaseChatModel / ClaudeClient | LLM 호출 구현 |
| WorkflowCompiler / ExcelAnalysisWorkflow | chart_router | 그래프에 노드 삽입 |

---

## 3. Data Model

### 3.1 Domain Schemas (`src/domain/visualization/schemas.py`)

```python
from enum import Enum


class VizDecision(str, Enum):
    """라우팅 판단 결과 (2분기)."""
    VISUALIZE = "visualize"
    TEXT = "text"
```

> 참고: `ChartSpec` 등 차트 데이터 스키마는 이 설계에 **포함하지 않는다**. 후속 노드 설계에서 정의.

### 3.2 Domain Policy (`src/domain/visualization/policies.py`)

```python
import re


class VisualizationRoutingPolicy:
    """시각화 라우팅 1차 판단 규칙 (휴리스틱, LLM 의존 없음)."""

    VISUALIZE_KEYWORDS: tuple[str, ...] = (
        "그래프", "차트", "시각화", "그려", "도표", "추이",
        "plot", "chart", "graph", "visualize",
    )

    # 데이터 신호: 숫자 토큰이 이 개수 이상이면 차트 후보로 간주
    NUMERIC_TOKEN_THRESHOLD: int = 4

    _NUMERIC_RE = re.compile(r"\d+(?:[.,]\d+)?%?")

    def explicit_request(self, question: str) -> bool:
        """질문에 시각화 명시 키워드가 있는가."""
        q = (question or "").lower()
        return any(kw.lower() in q for kw in self.VISUALIZE_KEYWORDS)

    def data_suggests_chart(self, analysis_text: str) -> bool:
        """분석 텍스트에 수치 신호가 충분한가 (간단 휴리스틱)."""
        if not analysis_text:
            return False
        numeric_count = len(self._NUMERIC_RE.findall(analysis_text))
        return numeric_count >= self.NUMERIC_TOKEN_THRESHOLD

    def decide(self, question: str, analysis_text: str) -> str | None:
        """1차 판단.

        Returns:
            "visualize"  : 명시 요청 → 즉시 시각화 (LLM 불필요)
            "text"       : 시각화 신호 없음 → 즉시 텍스트 (LLM 불필요)
            None         : 데이터 신호는 있으나 명시 없음 → LLM 위임(애매구간)
        """
        if self.explicit_request(question):
            return VizDecision.VISUALIZE.value
        if self.data_suggests_chart(analysis_text):
            return None
        return VizDecision.TEXT.value
```

### 3.3 Domain Port (`src/domain/visualization/interfaces.py`)

```python
from abc import ABC, abstractmethod


class VisualizationClassifierInterface(ABC):
    """애매구간 LLM 분류 포트. application은 이 인터페이스에만 의존."""

    @abstractmethod
    async def classify(self, question: str, analysis_text: str) -> str:
        """질문+분석 텍스트로 'visualize' 또는 'text' 반환."""
        raise NotImplementedError
```

### 3.4 State 필드 추가

라우터는 결과를 상태에 기록한다. **`viz_decision` 한 필드만** 추가한다.

**Supervisor** (`src/application/agent_builder/supervisor_state.py`):
```python
class SupervisorState(TypedDict):
    ...
    attachments: list[dict]
    # analysis-chart-router
    viz_decision: str   # "visualize" | "text" | ""(미판단)
```
`build_initial_state()`에 `"viz_decision": ""` 기본값 추가.

**Excel** (`ExcelAnalysisState` in `excel_analysis_workflow.py`):
```python
class ExcelAnalysisState(TypedDict):
    ...
    viz_decision: str   # "visualize" | "text" | ""
```
초기 state dict(`analyze_excel_use_case.py`)에 `"viz_decision": ""` 추가.

---

## 4. Application — chart_router 노드

### 4.1 노드 팩토리 (`src/application/visualization/chart_router.py`)

```python
from src.domain.visualization.policies import VisualizationRoutingPolicy
from src.domain.visualization.interfaces import VisualizationClassifierInterface
from src.domain.visualization.schemas import VizDecision
from src.domain.logging.interfaces.logger_interface import LoggerInterface


def create_chart_router_node(
    policy: VisualizationRoutingPolicy,
    logger: LoggerInterface,
    classifier: VisualizationClassifierInterface | None = None,
):
    """분석 직후 시각화/텍스트를 판단만 하는 라우터 노드 팩토리.

    - state에서 최근 질문과 직전 분석 텍스트를 뽑아 Policy로 1차 판단.
    - 애매(None)하고 classifier가 있으면 LLM 분류, 없으면 'text' 보수 처리.
    - state["viz_decision"]만 갱신하고 반환 (차트 생성 X).
    """

    async def chart_router(state: dict) -> dict:
        question = _extract_question(state)
        analysis_text = _extract_analysis_text(state)

        decision = policy.decide(question, analysis_text)

        if decision is None:
            if classifier is not None:
                try:
                    decision = await classifier.classify(question, analysis_text)
                except Exception as e:
                    logger.error("chart_router classify failed, fallback=text",
                                 exception=e)
                    decision = VizDecision.TEXT.value
            else:
                decision = VizDecision.TEXT.value

        if decision not in (VizDecision.VISUALIZE.value, VizDecision.TEXT.value):
            decision = VizDecision.TEXT.value

        logger.info("chart_router decided", decision=decision)
        return {"viz_decision": decision}

    return chart_router


def route_after_chart_router(state: dict) -> str:
    """후속 분기용 순수 라우팅 함수 (지금은 미사용, 후속 노드 부착 시 사용).

    Returns "visualize" | "text".
    """
    return (
        "visualize"
        if state.get("viz_decision") == VizDecision.VISUALIZE.value
        else "text"
    )
```

### 4.2 state 추출 헬퍼

- `_extract_question(state)`: 최근 user/human 메시지 content. Supervisor는 `messages`, Excel은 `user_query` 사용 → 두 형태 모두 지원.
- `_extract_analysis_text(state)`: Supervisor는 마지막 AIMessage content, Excel은 `analysis_text` 사용.

```python
def _extract_question(state: dict) -> str:
    if state.get("user_query"):                 # Excel state
        return state["user_query"]
    for msg in reversed(state.get("messages", [])):   # Supervisor state
        role = msg.get("role") if isinstance(msg, dict) else getattr(msg, "type", "")
        if role in ("user", "human"):
            return msg.get("content", "") if isinstance(msg, dict) else getattr(msg, "content", "")
    return ""


def _extract_analysis_text(state: dict) -> str:
    if state.get("analysis_text"):              # Excel state
        return state["analysis_text"]
    for msg in reversed(state.get("messages", [])):   # Supervisor state
        if not isinstance(msg, dict) and getattr(msg, "type", "") == "ai":
            return getattr(msg, "content", "")
    return ""
```

> 두 state 형태를 한 함수가 모두 다루게 하여 노드를 공용으로 유지. (Excel은 `user_query`/`analysis_text` 키, Supervisor는 `messages` 기반.)

---

## 5. Infrastructure — LLM 분류 어댑터

### 5.1 LangChain 기반 (`src/infrastructure/visualization/llm_classifier.py`)

Supervisor는 `LLMFactory.create()`가 `BaseChatModel`을 반환하므로 이를 그대로 사용.

```python
from typing import Literal
from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel, Field

from src.domain.visualization.interfaces import VisualizationClassifierInterface


class _VizLabel(BaseModel):
    decision: Literal["visualize", "text"] = Field(
        description="차트로 보여주는 게 적절하면 visualize, 텍스트로 충분하면 text"
    )


class LangChainVisualizationClassifier(VisualizationClassifierInterface):
    def __init__(self, llm: BaseChatModel) -> None:
        self._llm = llm

    async def classify(self, question: str, analysis_text: str) -> str:
        prompt = (
            "다음 분석 결과를 사용자에게 보여줄 때 차트/그래프가 더 적절한지, "
            "텍스트로 충분한지 판단하세요.\n\n"
            f"[질문]\n{question}\n\n[분석 결과]\n{analysis_text[:2000]}"
        )
        structured = self._llm.with_structured_output(_VizLabel)
        result = await structured.ainvoke(prompt)
        return result.decision
```

### 5.2 Excel(ClaudeClient) 경로

`ExcelAnalysisWorkflow`는 `ClaudeClient`(`self._claude.complete`)를 쓴다. 두 가지 선택지:

- **(A, 권장)** Excel 라우터에도 `LLMFactory`로 만든 `BaseChatModel`을 별도 주입 → 동일 어댑터 재사용.
- (B) `ClaudeVisualizationClassifier(claude_client)` 별도 어댑터 작성.

이번 범위에서는 (A)를 기본으로 한다(어댑터 1개 유지). 주입 비용이 부담되면 Excel은 classifier=None으로 시작(휴리스틱만, 애매→text)해도 동작은 보장된다.

---

## 6. Graph Wiring (라우터 삽입)

> 원칙: **지금은 분기 없이 라우터를 끼워 상태만 남기고**, 기존 후속으로 그대로 흐른다. 분기 엣지(`route_after_chart_router`)는 후속 차트 노드가 생길 때 부착한다. 부착 지점을 주석/문서로 명시.

### 6.1 Supervisor (`workflow_compiler.py`)

```python
# compile() 워커 루프에서 analysis 워커 id 수집
analysis_worker_ids: set[str] = set()
if category == "analysis":
    ...
    analysis_worker_ids.add(worker_def.worker_id)

# 라우터 노드 등록
chart_router_fn = create_chart_router_node(
    policy=VisualizationRoutingPolicy(),
    logger=self._logger,
    classifier=LangChainVisualizationClassifier(llm),
)
graph.add_node("chart_router", _wrap_step("chart_router", NodeType.OTHER, chart_router_fn))

# 워커 → 후속 엣지: analysis 워커만 라우터 경유
for worker_id in worker_map:
    if worker_id in analysis_worker_ids:
        graph.add_edge(worker_id, "chart_router")
    else:
        graph.add_edge(worker_id, "quality_gate")

# 지금: 라우터 후 그대로 quality_gate (분기 없음, viz_decision만 보존)
graph.add_edge("chart_router", "quality_gate")

# ── 후속 노드 부착 지점(이번 범위 아님) ───────────────────────
# graph.add_conditional_edges("chart_router", route_after_chart_router,
#     {"visualize": "chart_builder", "text": "quality_gate"})
# ────────────────────────────────────────────────────────────
```

핵심: `analysis` 카테고리 워커 직후에만 라우터로 진입(답변 ①), 그 외 워커 흐름·멀티워커 오케스트레이션은 불변.

### 6.2 Excel (`excel_analysis_workflow.py`)

```python
workflow.add_node("chart_router", chart_router)

# 품질 통과(complete) 시 END 대신 라우터로
workflow.add_conditional_edges(
    "evaluate_hallucination",
    self._should_retry_or_route,   # 기존 _should_retry_or_execute 개명
    {"retry": "web_search", "route": "chart_router", "complete": END},
)

# 지금: 라우터 후 그대로 END (viz_decision만 기록)
workflow.add_edge("chart_router", END)

# ── 후속 부착 지점 ──
# workflow.add_conditional_edges("chart_router", route_after_chart_router,
#     {"visualize": "chart_builder", "text": END})
```

- 기존 `execute_code` / `_detect_code_in_response` 경로는 **사용 중단**(SandboxExecutor가 차트를 못 그려 죽은 경로). 후속 차트 노드가 대체. 코드는 남기되 그래프에서 분리.

---

## 7. Error Handling

| 시나리오 | 처리 | 위치 |
|---------|------|------|
| classifier 미주입 + 애매구간 | `text`로 보수 처리 | chart_router |
| LLM 분류 예외 | log.error + `text` fallback (본 흐름 비중단) | chart_router |
| LLM이 비정상 라벨 반환 | 화이트리스트 검증 후 `text` | chart_router |
| question/analysis_text 빈 값 | 휴리스틱이 `text` 반환 | policy |

---

## 8. Test Plan (TDD)

### 8.1 Domain — VisualizationRoutingPolicy (`tests/domain/visualization/test_policies.py`)
- [ ] `explicit_request("매출 그래프 그려줘")` → True
- [ ] `explicit_request("매출 알려줘")` → False
- [ ] `decide(명시 키워드, _)` → "visualize"
- [ ] `decide("요약", "내용 텍스트만")` → "text"
- [ ] `decide("추세 알려줘 아님", "2023 100, 2024 130, 2025 160, 12% 증가")` 숫자≥4 → None
- [ ] `data_suggests_chart` 임계값 경계 테스트

### 8.2 Application — chart_router 노드 (`tests/application/visualization/test_chart_router.py`)
- [ ] 명시 요청 → classifier **호출 없이** `viz_decision=="visualize"`
- [ ] 비수치 텍스트 → classifier 호출 없이 `"text"`
- [ ] 애매 + Fake classifier "visualize" → `"visualize"`
- [ ] 애매 + classifier=None → `"text"`
- [ ] 애매 + classifier 예외 → `"text"` (graceful)
- [ ] Supervisor state(messages 기반) / Excel state(user_query 기반) 둘 다에서 질문·분석 추출 정상
- [ ] `route_after_chart_router`: viz_decision별 "visualize"/"text" 반환

### 8.3 Wiring (그래프 구조)
- [ ] Supervisor: analysis 워커의 다음 노드가 `chart_router`
- [ ] Supervisor: 비-analysis 워커는 여전히 `quality_gate` 직결
- [ ] Excel: evaluate complete 경로가 `chart_router` 경유 후 END

> 모든 신규 모듈 RED → GREEN (CLAUDE.md TDD 필수). domain은 순수 단위테스트, LLM은 Fake/AsyncMock.

---

## 9. Clean Architecture

### 9.1 Layer Assignment

| Component | Layer | Location |
|-----------|-------|----------|
| VizDecision | Domain | `src/domain/visualization/schemas.py` |
| VisualizationRoutingPolicy | Domain | `src/domain/visualization/policies.py` |
| VisualizationClassifierInterface | Domain | `src/domain/visualization/interfaces.py` |
| create_chart_router_node, route_after_chart_router | Application | `src/application/visualization/chart_router.py` |
| LangChainVisualizationClassifier | Infrastructure | `src/infrastructure/visualization/llm_classifier.py` |
| 상태 필드 viz_decision | Application(state) | supervisor_state.py / excel_analysis_workflow.py |

### 9.2 Dependency Rules

```
Application(chart_router) ──→ Domain(policy, interface, schema)
Infrastructure(llm_classifier) ──→ Domain(interface)
Application ──→ Domain(interface)  (구현체는 DI로 주입, 컴파일 시점에 infra 주입)
❌ Domain → Application / Infrastructure 금지
```

- application은 `VisualizationClassifierInterface`(domain)에만 의존, 구체 LLM 어댑터(infra)는 `WorkflowCompiler` DI 시점에 주입 → 레이어 규칙 준수.

---

## 10. Implementation Guide

### 10.1 File Structure (신규)

```
src/
├── domain/visualization/
│   ├── __init__.py
│   ├── schemas.py        # VizDecision
│   ├── policies.py       # VisualizationRoutingPolicy
│   └── interfaces.py     # VisualizationClassifierInterface
├── application/visualization/
│   ├── __init__.py
│   └── chart_router.py   # create_chart_router_node, route_after_chart_router, 헬퍼
└── infrastructure/visualization/
    ├── __init__.py
    └── llm_classifier.py # LangChainVisualizationClassifier
```

수정: `supervisor_state.py`(+필드), `supervisor_nodes.py::build_initial_state`(+기본값),
`workflow_compiler.py`(라우터 배선), `excel_analysis_workflow.py`(라우터 배선),
`analyze_excel_use_case.py`(초기 state +필드).

### 10.2 Implementation Order

#### Step 1: Domain (테스트 먼저)
1. [ ] `tests/domain/visualization/test_policies.py` (8.1)
2. [ ] `schemas.py`, `policies.py`, `interfaces.py`
3. [ ] GREEN 확인

#### Step 2: Application 노드 (테스트 먼저)
4. [ ] `tests/application/visualization/test_chart_router.py` (8.2)
5. [ ] `chart_router.py` (노드 + 라우팅 함수 + 헬퍼)
6. [ ] GREEN 확인

#### Step 3: Infrastructure 어댑터
7. [ ] `tests/infrastructure/visualization/test_llm_classifier.py` (AsyncMock)
8. [ ] `llm_classifier.py`
9. [ ] GREEN 확인

#### Step 4: Wiring
10. [ ] `supervisor_state.py` / `build_initial_state` 필드 추가
11. [ ] `workflow_compiler.py` analysis 워커 → chart_router 배선 (6.1)
12. [ ] `excel_analysis_workflow.py` + `analyze_excel_use_case.py` 배선 (6.2)
13. [ ] 그래프 구조 테스트(8.3) + 기존 supervisor/excel 회귀 테스트 GREEN

### 10.3 Naming Conventions

| Target | Rule | Example |
|--------|------|---------|
| LangGraph 노드 | `_xxx_node` / 팩토리 `create_xxx_node` | `create_chart_router_node` |
| 라우팅 함수 | `route_after_xxx` | `route_after_chart_router` |
| Policy | PascalCase + Policy | `VisualizationRoutingPolicy` |
| Enum | PascalCase | `VizDecision` |

---

## 11. Out of Scope (후속 노드에서 진행)

- **ChartSpec 스키마 / chart_builder 노드**: `viz_decision == "visualize"`를 받아 차트 데이터(JSON)를 생성하는 노드. 별도 Design.
- **분기 엣지 부착**: `route_after_chart_router`를 conditional edge로 연결(6.1/6.2 주석 지점).
- **응답 직렬화**: 차트 결과를 API 응답에 노출 + `idt_front` 타입 동기화(`/api-contract-sync`).
- **차트+텍스트 동시 응답 정책**.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-06-05 | Initial draft — 라우팅 노드 only 범위 | 배상규 |
