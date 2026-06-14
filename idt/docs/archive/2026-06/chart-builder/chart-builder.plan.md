# CHART-BUILDER: 분석 결과 → Chart.js config(JSON) 생성 도구 (General Chat 연동)

> 상태: Plan
> 연관 Task: CHART-BUILD-001
> 작성일: 2026-06-06
> 우선순위: High
> 선행 기능: analysis-chart-router (router 완료, archive), chat-chart-rendering (프론트 렌더링 완료, archive)

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | `chart_router`는 "시각화 vs 텍스트"를 **판단(`viz_decision`)만** 하고 끝난다(analysis-chart-router 설계의 명시적 Out of Scope). 실제로 차트를 그리려면 분석 결과(산문 텍스트)에서 **수치를 추출해 Chart.js가 먹는 config(JSON)** 로 변환하는 도구가 없다. 동시에 프론트(idt_front)는 `chat_answer_completed.charts`를 렌더링할 준비를 **이미 마쳐 두고도**(ChartRenderer/useChart/validator) 백엔드가 `charts`를 안 채워줘서 차트가 화면에 뜨지 않는다. |
| **Solution** | 분석 텍스트 + 질문을 입력받아 **LLM structured output**으로 **Chart.js 네이티브 config(`{type, data, options}`)** 리스트를 생성하는 `chart_builder`(application 노드 + infra LLM 어댑터)를 만든다. 출력 스키마는 프론트가 이미 정의한 계약(`ChartPayload`)과 1:1로 맞춘다. 1차 연동 대상은 **프론트 렌더링이 이미 깔린 General Chat 경로**: `GeneralChatUseCase`가 답변 완료 시점에 시각화 여부를 판단(기존 `VisualizationRoutingPolicy` 재사용)하고 visualize면 차트를 만들어 `ANSWER_COMPLETED.charts`에 실어 보낸다. |
| **Function UX Effect** | 사용자가 "월별 매출 추이 그래프로 보여줘"라고 하면 채팅 답변 말풍선 아래에 **실제 Chart.js 차트**가 즉시 렌더된다. 시각화가 부적절한 질문은 기존처럼 텍스트만. 프론트는 추가 작업 거의 없이(이미 구현됨) 바로 표시된다. |
| **Core Value** | "판단은 되는데 그림이 안 나오던" 죽은 구간을 잇는 **마지막 연결고리**. 백엔드는 Chart.js 계약 JSON 생성만 책임지고 렌더링은 프론트가 담당하는 관심사 분리를 유지하며, RAG/채팅 분석 결과를 의도에 맞는 표현(텍스트/차트)으로 자동 제공한다. |

---

## 1. 문제 정의 (Problem Statement)

선행 기능 두 개가 양 끝에서 완성됐지만 **중간 연결이 비어 있다**.

```
[완료] analysis-chart-router          [이번 작업: 비어있는 중간]        [완료] chat-chart-rendering
 chart_router → viz_decision  ──────▶  ❓ 수치 추출 + Chart.js JSON  ──────▶  ChartRenderer/useChart
 ("visualize"/"text" 판단만)            생성 도구가 없음                       (charts 받으면 렌더 준비완료)
```

구체적 공백:
1. **수치 추출 부재** — 분석 결과는 산문(`"2024년 매출은 130억으로 전년 대비 30% 증가..."`)이라 그대로는 차트가 안 된다. labels/datasets로 구조화하는 단계가 없다.
2. **Chart.js 계약 미충족** — 프론트는 `ChartPayload = { type, data, options? }`(Chart.js 네이티브 config)를 기대하는데(`idt_front/src/types/chart.ts`), 백엔드에 이 형식을 만드는 코드가 전혀 없다.
3. **전달 경로 미연결** — 프론트는 `ChatAnswerCompletedData.charts?: ChartPayload[]`를 이미 정의해 두고 주석으로 *"백엔드 협의 후 연동 — 필드 부재 시 차트 미표시(하위호환)"* 라고 대기 중이지만, 백엔드 `ANSWER_COMPLETED` payload에는 `charts`가 없다.

---

## 2. 현재 구조 분석 (Current State)

### 2-1. 프론트 계약 (이미 구현됨 — 백엔드가 맞춰야 할 기준)

| 항목 | 위치 | 내용 |
|------|------|------|
| 차트 계약 타입 | `idt_front/src/types/chart.ts` | `ChartPayload = { type: ChartType; data: ChartData; options?: ChartOptions }` (Chart.js 네이티브 패스스루) |
| 지원 타입 화이트리스트 | 동상 | `bar, line, pie, doughnut, scatter, radar` |
| 검증 규칙 | `idt_front/src/utils/chartValidator.ts` | `type`이 화이트리스트 포함 + `data.datasets`가 **비어있지 않은 배열** |
| 전달 필드 | `idt_front/src/types/websocket.ts` | `ChatAnswerCompletedData.charts?: ChartPayload[]` (General Chat WS) |
| 렌더 | `MessageBubble.tsx` → `ChartRenderer.tsx` → `useChart.ts` | payload 1개당 차트 1개, 검증 실패 시 fallback UI |

> ⚠️ 주의: 프론트의 `charts` 필드는 **General Chat(`chat_answer_completed`)에만** 있다. Agent run(Supervisor, `agent_answer_completed`)에는 아직 없다 → 이번 범위를 General Chat으로 잡는 핵심 근거.

### 2-2. 백엔드 General Chat 흐름 (`src/application/general_chat/use_case.py`)

```
stream(): CHAT_STARTED → (TOKEN|TOOL_*|STEP_REASONING)* → ANSWER_COMPLETED → CHAT_DONE
                                                              └─ payload: {answer, tools_used, sources, was_summarized}
```

- `ANSWER_COMPLETED` payload 생성 지점: `use_case.py:189-197`
- 답변 텍스트/도구/출처 파싱: `_parse_agent_output()` (line 451)
- `execute()`(REST, line 219)는 `stream()`을 소비해 `GeneralChatResponse` 조립 → 여기에도 `charts` 반영 필요
- WS 변환: `ChatEventWsAdapter.to_ws_message()` (`src/infrastructure/general_chat/ws_adapter.py`)가 **payload를 그대로 `data`로 패스스루** → payload에 `charts`만 넣으면 프론트 `chat_answer_completed.data.charts`로 자동 도달

### 2-3. 재사용 가능한 기존 자산 (analysis-chart-router 산출물)

| 자산 | 위치 | 이번 재사용 |
|------|------|------------|
| `VisualizationRoutingPolicy` | `src/domain/visualization/policies.py` | 시각화/텍스트 1차 판단 (키워드/수치 휴리스틱) — **그대로 재사용** |
| `VisualizationClassifierInterface` | `src/domain/visualization/interfaces.py` | 애매구간 LLM 분류 port — **그대로 재사용** |
| `LangChainVisualizationClassifier` | `src/infrastructure/visualization/llm_classifier.py` | 분류 어댑터 — **그대로 재사용** |
| `VizDecision` | `src/domain/visualization/schemas.py` | "visualize"/"text" enum — 재사용 |

> `chart_router` 노드 자체는 LangGraph용이라 General Chat(ReAct astream_events 경로)에는 노드로 끼우지 않는다. 대신 **판단 로직(Policy + Classifier)을 use_case에서 직접 호출**해 결정하고, 빌더를 돌린다.

---

## 3. 수정 범위 (Scope)

| # | 위치 | 내용 | 레이어 | 우선순위 |
|---|------|------|--------|----------|
| 1 | `src/domain/visualization/chart_schemas.py` (신규) | Chart.js 계약과 1:1인 pydantic 모델: `ChartType`(enum, 프론트 화이트리스트와 동일), `ChartDataset`, `ChartData`, `ChartConfig`(=`ChartPayload`). LLM structured output + 검증용 | domain | High |
| 2 | `src/domain/visualization/interfaces.py` (수정) | `ChartBuilderInterface.build(question, analysis_text) -> list[ChartConfig]` port 추가 | domain | High |
| 3 | `src/infrastructure/visualization/llm_chart_builder.py` (신규) | `LangChainChartBuilder` — `llm.with_structured_output`로 ChartConfig(들) 생성, 실패 시 빈 리스트 graceful | infra | High |
| 4 | `src/application/general_chat/use_case.py` (수정) | 답변 완료 후 `_maybe_build_charts(question, answer)`: Policy→(애매시 Classifier)→visualize면 Builder 호출 → `ANSWER_COMPLETED.charts` + `GeneralChatResponse.charts` 주입 | application | High |
| 5 | `src/domain/general_chat/schemas.py` (수정) | `GeneralChatResponse`에 `charts: list[dict]` 필드 추가 (REST 경로 호환) | domain | Medium |
| 6 | DI 조립부 (`main.py`/general_chat router 의존성) | `GeneralChatUseCase`에 policy/classifier/builder 주입 | interfaces/infra | High |
| 7 | `tests/...` | 스키마/빌더/판단-주입 단위·통합 테스트 (TDD Red→Green) | - | High |
| 8 | `idt_front` | `/api-contract-sync`: WS `charts`는 이미 정의됨(검증만), REST `GeneralChatResponse` 타입에 `charts` 반영 | front | Medium |

**범위 외 (후속 별도 Plan)**:
- **Excel 워크플로우** chart_builder 연동 (REST AnalysisResult 노출) — `chart_router` 노드 뒤 `chart_builder` 노드 부착 (설계 주석 지점 존재)
- **Supervisor(agent_builder)** 연동 + `agent_answer_completed.charts` 프론트 필드 신설
- 차트 + 텍스트 동시 응답의 세부 UX 정책, 다중 차트 개수 상한 튜닝

---

## 4. 설계 (Solution Design)

### 4-1. 전체 흐름 (General Chat)

```
GeneralChatUseCase.stream()
  … astream_events 소비 → _parse_agent_output → (answer, tools_used, sources)
        │
        ▼  _maybe_build_charts(question=request.message, analysis_text=answer)
  VisualizationRoutingPolicy.decide(question, answer)
        ├─ "text"      → charts = []        (LLM 호출 0)
        ├─ "visualize" → ChartBuilder.build → charts = [ChartConfig, ...]
        └─ None(애매)  → Classifier.classify → visualize면 build / text면 []
        │
        ▼
  ANSWER_COMPLETED payload = {answer, tools_used, sources, was_summarized, charts}
        │ (ws_adapter 패스스루)
        ▼
  프론트 chat_answer_completed.data.charts → MessageBubble → ChartRenderer
```

- 실패/예외/빈 결과는 **항상 `charts = []`** 로 떨어뜨려 본 답변 흐름을 절대 막지 않는다(graceful).
- 명시 키워드/비수치 케이스는 휴리스틱에서 끝나 LLM 추가 호출 없음(비용 최적화).

### 4-2. ChartConfig — Chart.js 네이티브 계약 (domain pydantic)

프론트 `ChartPayload`와 **필드/타입 1:1**. LLM이 이 스키마로 직접 structured output을 내도록 한다.

```python
# src/domain/visualization/chart_schemas.py
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class ChartType(str, Enum):
    """프론트 SUPPORTED_CHART_TYPES와 동일 화이트리스트."""
    BAR = "bar"
    LINE = "line"
    PIE = "pie"
    DOUGHNUT = "doughnut"
    SCATTER = "scatter"
    RADAR = "radar"


class ChartDataset(BaseModel):
    label: str = Field(description="시리즈 이름 (예: '매출')")
    data: list[float] = Field(description="labels와 같은 길이의 수치 배열")
    # backgroundColor/borderColor 등은 프론트 기본값에 위임(선택) → 과한 추상화 회피


class ChartData(BaseModel):
    labels: list[str] = Field(description="x축 라벨 (예: ['1월','2월','3월'])")
    datasets: list[ChartDataset] = Field(
        description="1개 이상의 데이터셋 (비어있으면 프론트 검증 실패)"
    )


class ChartConfig(BaseModel):
    """= 프론트 ChartPayload. Chart.js `new Chart(ctx, config)`에 패스스루되는 형태."""
    type: ChartType
    data: ChartData
    options: dict[str, Any] | None = Field(
        default=None, description="Chart.js options (title 등). 생략 가능"
    )
```

> 검증: 프론트 `chartValidator`는 `data.datasets` 비어있지 않음을 요구 → 빌더는 datasets가 비면 해당 차트를 버린다(빈 리스트 반환).

### 4-3. ChartBuilderInterface (domain port) + 어댑터 (infra)

```python
# src/domain/visualization/interfaces.py (추가)
class ChartBuilderInterface(ABC):
    @abstractmethod
    async def build(self, question: str, analysis_text: str) -> list[ChartConfig]:
        """질문+분석 텍스트에서 Chart.js config 리스트 생성. 실패 시 []."""
        raise NotImplementedError
```

```python
# src/infrastructure/visualization/llm_chart_builder.py (신규)
class _ChartList(BaseModel):
    charts: list[ChartConfig] = Field(default_factory=list)

class LangChainChartBuilder(ChartBuilderInterface):
    def __init__(self, llm: BaseChatModel, logger: LoggerInterface) -> None: ...
    async def build(self, question, analysis_text) -> list[ChartConfig]:
        prompt = _build_chart_prompt(question, analysis_text)   # 수치 추출 지시
        try:
            result = await self._llm.with_structured_output(_ChartList).ainvoke(prompt)
        except Exception as e:
            self._logger.error("chart build failed, fallback []", exception=e)
            return []
        return [c for c in result.charts if c.data.datasets]     # 빈 datasets 제거
```

- 프롬프트 핵심 지시: "분석 텍스트에 **명시된 수치만** 사용(추측 금지), labels와 datasets.data 길이 일치, 적절한 chart_type 선택(시계열=line, 카테고리 비교=bar, 비중=pie/doughnut), 차트가 부적절하면 빈 배열."
- 1개 LLM 호출, 다중 차트 허용(리스트). 상한은 후속 튜닝.

### 4-4. GeneralChatUseCase 주입 (application)

```python
# 생성자 의존성 추가 (모두 선택적 → 미주입 시 차트 비활성, 하위호환)
def __init__(self, ..., 
             viz_policy: VisualizationRoutingPolicy | None = None,
             viz_classifier: VisualizationClassifierInterface | None = None,
             chart_builder: ChartBuilderInterface | None = None): ...

async def _maybe_build_charts(self, question: str, answer: str) -> list[dict]:
    if self._chart_builder is None or not answer:
        return []
    policy = self._viz_policy or VisualizationRoutingPolicy()
    decision = policy.decide(question, answer)
    if decision is None:                       # 애매 → classifier
        decision = await self._classify_or_text(question, answer)
    if decision != VizDecision.VISUALIZE.value:
        return []
    charts = await self._chart_builder.build(question, answer)
    return [c.model_dump() for c in charts]
```

`stream()`의 ANSWER_COMPLETED 직전에 호출 → payload에 `"charts": charts` 추가. `execute()`는 이미 stream을 소비하므로 ANSWER_COMPLETED에서 `charts`를 읽어 `GeneralChatResponse.charts`에 채운다.

### 4-5. 응답 스키마 (REST 호환)

```python
# src/domain/general_chat/schemas.py
class GeneralChatResponse(BaseModel):
    ...
    charts: list[dict] = []   # Chart.js config 리스트 (기본 빈 배열 → 하위호환)
```

WS 경로는 payload 패스스루라 스키마 변경 불필요. REST 경로만 필드 추가.

---

## 5. 테스트 계획 (TDD)

### 5-1. ChartConfig 스키마 (domain)
- `ChartType` 값이 프론트 화이트리스트(bar/line/pie/doughnut/scatter/radar)와 정확히 일치
- `ChartConfig.model_dump()` 출력 키가 `{type, data{labels,datasets}, options}` 구조
- datasets 빈 배열도 모델 생성은 가능(검증은 빌더가 필터)

### 5-2. LangChainChartBuilder (infra, FakeLLM/AsyncMock)
- 정상: FakeLLM이 1개 ChartConfig 반환 → `build()`가 길이 1 리스트
- 빈 datasets 차트 → 결과에서 제거됨
- LLM 예외 → `[]` (graceful, 예외 전파 안 함)

### 5-3. _maybe_build_charts 판단 분기 (application, Fake 의존성)
- 명시 키워드 질문 → classifier 호출 없이 builder 호출 → charts 반환
- 비수치 답변 → builder 호출 없이 `[]`
- 애매 + classifier "visualize" → builder 호출 → charts
- 애매 + classifier "text" → `[]`
- chart_builder 미주입 → `[]` (하위호환)

### 5-4. stream() 통합 (application)
- visualize 케이스: ANSWER_COMPLETED payload에 `charts`(비어있지 않음) 포함
- text 케이스: payload `charts == []`, 기존 키(answer/tools_used/sources/was_summarized) 불변
- builder 예외에도 ANSWER_COMPLETED/CHAT_DONE 정상 발행

### 5-5. execute() REST 통합
- visualize 케이스: `GeneralChatResponse.charts` 길이 ≥ 1
- 기존 호출부 시그니처 불변(필드 추가만)

> 모든 신규 모듈 RED → GREEN (CLAUDE.md TDD 필수). LLM은 Fake/AsyncMock, domain은 순수 단위테스트.
> ⚠️ Windows pytest 교차 실행 이벤트 루프 flakiness 주의 — 신규 async 테스트는 격리 실행으로 재확인(메모리 노트).

---

## 6. 영향 범위 / 리스크

| 항목 | 영향 | 비고 |
|------|------|------|
| `ANSWER_COMPLETED` payload | `charts` 키 추가 | ws_adapter 패스스루 → 프론트 자동 도달, 기존 키 불변 |
| `GeneralChatResponse` | `charts` 필드 추가(기본 `[]`) | REST 하위호환, `/api-contract-sync` 필요 |
| `GeneralChatUseCase` 생성자 | 의존성 3개 추가(모두 Optional) | 미주입 시 차트 비활성 → 점진 도입 안전 |
| 토큰 비용 | visualize + 애매구간만 LLM 추가 호출 | 명시/비수치는 휴리스틱에서 종료 |
| 수치 추출 정확도 | 산문→수치 추출 LLM 의존 | 프롬프트로 "명시 수치만/추측 금지", 부정확 시 빈 배열로 안전 fallback |
| 프론트 | 신규 컴포넌트 0 (이미 구현) | REST 타입 sync + WS 검증만 |
| DDD 레이어 | domain(스키마/port) → infra(LLM) → application(조립) | Domain→Infra 참조 없음, 규칙 준수 |

---

## 7. 구현 순서

1. `src/domain/visualization/chart_schemas.py` (ChartConfig 등) + 테스트 5-1
2. `src/domain/visualization/interfaces.py` `ChartBuilderInterface` 추가
3. `src/infrastructure/visualization/llm_chart_builder.py` + 테스트 5-2
4. `src/domain/general_chat/schemas.py` `GeneralChatResponse.charts` + (REST 테스트 토대)
5. `src/application/general_chat/use_case.py` `_maybe_build_charts` + ANSWER_COMPLETED 주입 + 테스트 5-3/5-4/5-5
6. DI 조립부에서 `GeneralChatUseCase`에 policy/classifier/builder 주입 (`main.py`/general_chat router)
7. `/api-contract-sync`로 `idt_front` REST 타입 동기화 + WS `charts` 계약 일치 검증
8. `/pdca analyze chart-builder` (Gap) → `/pdca report chart-builder`

---

## 8. 미해결 / Design에서 확정할 이슈

- **다중 차트 상한**: `build()`가 반환하는 차트 개수 상한(예: 3개) 둘지 — Design에서 결정
- **options 범위**: title/축 라벨을 `options`에 넣을지, dataset 색상을 백엔드가 줄지 프론트 기본값에 맡길지 — 과한 추상화 회피 관점에서 Design 확정
- **수치 추출 컨텍스트 보강**: 답변 텍스트만으로 부족할 때 도구 출력(tool output)/sources를 빌더 컨텍스트로 함께 넣을지
- **DI 주입 위치 확인**: `GeneralChatUseCase`가 조립되는 정확한 지점(main.py 또는 general_chat_router 의존성 팩토리) Do 단계에서 특정
