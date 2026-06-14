# Chart Builder Design Document

> **Summary**: 분석/답변 텍스트(+검색·도구 컨텍스트)에서 LLM으로 수치를 추출해 **Chart.js 네이티브 config(JSON)** 리스트를 생성하는 `chart_builder`. 데이터 추출은 LLM(infra), 색상·축·타이틀 등 **표현 규칙은 domain Policy**가 결정. 1차 연동 대상은 프론트 렌더링이 이미 완료된 **General Chat**(`chat_answer_completed.charts`).
>
> **Project**: sangplusbot (idt)
> **Version**: 0.1
> **Author**: 배상규
> **Date**: 2026-06-06
> **Status**: Draft
> **Planning Doc**: [chart-builder.plan.md](../../01-plan/features/chart-builder.plan.md)
> **선행 설계**: [analysis-chart-router.design.md](../../archive/2026-06/analysis-chart-router/analysis-chart-router.design.md) (router=완료), idt_front chat-chart-rendering (렌더링=완료)

### Design Decisions (Plan §8 확정)

| # | 항목 | 결정 |
|---|------|------|
| D1 | 다중 차트 상한 | **3개 고정**, `settings.chart_max_count`로 config화하여 추후 변경 용이 |
| D2 | options / 색상 | title·축 라벨은 `options`에 포함, **dataset 색상도 백엔드에서 반환** |
| D3 | 추출 컨텍스트 | 답변 텍스트 + **도구 출력/sources 컨텍스트 함께** 빌더에 전달 |
| D4 | DI 조립 위치 | **General Chat 조립부**(`create_general_chat_use_case_factory`, REST+WS 공유)에서 조립 |

---

## 1. Overview

### 1.1 Design Goals

1. **Chart.js 계약 1:1**: 출력은 프론트 `ChartPayload = { type, data, options? }`와 필드·타입이 정확히 일치하는 패스스루 JSON.
2. **추출 ↔ 표현 분리**: LLM은 **데이터 추출만**(type/labels/series/축이름), **색상·options 조립 등 표현 규칙은 domain Policy**가 결정론적으로 수행. LLM에 hex 색상을 맡기지 않아 안정성↑.
3. **Graceful Degradation**: 어떤 실패(LLM 예외, 빈 datasets, 비-visualize)에도 `charts = []`로 떨어뜨려 본 답변 흐름을 막지 않음.
4. **점진 도입**: `GeneralChatUseCase`의 차트 의존성은 모두 Optional → 미주입 시 기존 동작 그대로(하위호환).

### 1.2 Scope

| 구분 | 항목 |
|------|------|
| ✅ In Scope | `ChartConfig` 등 domain 스키마, `ChartStylePolicy`(색상·options), `ChartBuilderInterface`(port), `LangChainChartBuilder`(infra), `GeneralChatUseCase._maybe_build_charts`, `GeneralChatResponse.charts`, config `chart_max_count`, general-chat 팩토리 DI |
| ❌ Out of Scope | Excel 워크플로우 연동, Supervisor 연동 + `agent_answer_completed.charts` 프론트 필드, 프론트 신규 컴포넌트(이미 완료), 차트 상호작용/드릴다운 |

### 1.3 Design Principles

- **Domain Purity**: 색상 팔레트·options 조립 규칙은 외부 의존 없는 domain Policy. LLM 호출은 port 뒤로 격리.
- **Reuse First**: 시각화 판단은 기존 `VisualizationRoutingPolicy` + `VisualizationClassifierInterface` 재사용(신규 판단 로직 금지).
- **No Over-Abstraction**: dataset 옵션 필드는 프론트 렌더에 실제 필요한 최소(`label/data/backgroundColor/borderColor`)만.

---

## 2. Architecture

### 2.1 Position (General Chat)

```
GeneralChatUseCase.stream()
   … astream_events 소비 → _parse_agent_output → (answer, tools_used, sources)
        │
        ▼  _maybe_build_charts(question, answer, context)
   ┌─────────────────────────────────────────────────────────┐
   │ 1) VisualizationRoutingPolicy.decide(question, answer)   │  (재사용)
   │      "text"      → []                                    │
   │      None(애매)  → VisualizationClassifier.classify      │  (재사용)
   │      "visualize" ↓                                       │
   │ 2) ChartBuilderInterface.build(question, answer, context)│  (신규 port)
   │      └ LangChainChartBuilder (infra)                     │
   │          a. LLM.with_structured_output(_ChartDraftList)  │  데이터 추출
   │          b. ChartStylePolicy.to_config(draft)            │  색상/options (domain)
   │          c. cap to chart_max_count, drop empty datasets  │
   └─────────────────────────────────────────────────────────┘
        │  charts: list[dict]  (ChartConfig.model_dump())
        ▼
   ANSWER_COMPLETED payload += {"charts": charts}
        │  ChatEventWsAdapter (payload 패스스루)
        ▼
   프론트 chat_answer_completed.data.charts → MessageBubble → ChartRenderer
```

### 2.2 Layer & Dependencies

| Component | Layer | Location | Depends On |
|-----------|-------|----------|-----------|
| `ChartType`, `ChartDataset`, `ChartData`, `ChartConfig` | Domain | `domain/visualization/chart_schemas.py` | pydantic |
| `ChartStylePolicy`, `ChartDraft`/`ChartSeriesDraft` | Domain | `domain/visualization/chart_policy.py` | chart_schemas |
| `ChartBuilderInterface` | Domain (port) | `domain/visualization/interfaces.py` (추가) | chart_schemas |
| `LangChainChartBuilder` | Infra | `infrastructure/visualization/llm_chart_builder.py` | port, policy, BaseChatModel, Logger |
| `_maybe_build_charts` | Application | `application/general_chat/use_case.py` (수정) | policy, classifier(port), builder(port) |
| `GeneralChatResponse.charts` | Domain (schema) | `domain/general_chat/schemas.py` (수정) | — |
| DI 조립 | Interfaces | `api/main.py::create_general_chat_use_case_factory` | 위 전부 |

> 의존 방향: Infra(builder) → Domain(port·policy·schema), Application → Domain(port). **Domain → Infra/App 참조 없음** (CLAUDE.md 준수).

---

## 3. Data Model

### 3.1 Chart.js 계약 스키마 (`domain/visualization/chart_schemas.py`, 신규)

프론트 `ChartPayload`(`idt_front/src/types/chart.ts`)와 1:1. `model_dump()` 결과가 그대로 `new Chart(ctx, config)` 입력이 된다.

```python
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
    """Chart.js dataset. 색상은 백엔드(ChartStylePolicy)가 채운다 (D2)."""
    label: str
    data: list[float]
    backgroundColor: str | list[str] | None = None   # pie/doughnut는 list[str]
    borderColor: str | None = None


class ChartData(BaseModel):
    labels: list[str]
    datasets: list[ChartDataset]


class ChartConfig(BaseModel):
    """= 프론트 ChartPayload. options에 title·축 라벨 포함 (D2)."""
    type: ChartType
    data: ChartData
    options: dict[str, Any] | None = None
```

> 검증 책임: 프론트 `chartValidator`는 `type ∈ 화이트리스트` + `data.datasets` 비어있지 않음을 요구. 백엔드는 빈 datasets 차트를 결과에서 제거(아래 4.3-c)하여 계약을 보장.

### 3.2 LLM 추출 중간 모델 (`domain/visualization/chart_policy.py`, 신규)

LLM은 **색상/options를 모른 채 데이터만** 뱉는다. structured output은 이 가벼운 Draft로 받는다.

```python
class ChartSeriesDraft(BaseModel):
    name: str = Field(description="시리즈 이름 (예: '매출')")
    data: list[float] = Field(description="labels와 같은 길이의 수치 배열")


class ChartDraft(BaseModel):
    chart_type: ChartType
    title: str = Field(default="", description="차트 제목")
    x_axis_name: str = Field(default="")
    y_axis_name: str = Field(default="")
    labels: list[str] = Field(description="x축 라벨")
    series: list[ChartSeriesDraft] = Field(description="1개 이상 시리즈")


class ChartDraftList(BaseModel):
    charts: list[ChartDraft] = Field(default_factory=list)
```

### 3.3 ChartStylePolicy — 표현 규칙 (domain, 순수)

색상 팔레트·options 조립을 **결정론적으로** 수행 (D2). 외부 의존 0.

```python
class ChartStylePolicy:
    # 카테고리형 팔레트 (Chart.js 권장 톤). 색상 결정 = 도메인 규칙.
    PALETTE: tuple[str, ...] = (
        "#4E79A7", "#F28E2B", "#59A14F", "#E15759",
        "#76B7B2", "#EDC948", "#B07AA1", "#FF9DA7",
    )
    _PER_POINT_TYPES = {ChartType.PIE, ChartType.DOUGHNUT, ChartType.RADAR}

    def to_config(self, draft: ChartDraft) -> ChartConfig:
        """ChartDraft → 색상·options가 채워진 ChartConfig."""
        datasets = [
            self._build_dataset(draft.chart_type, s, idx, n_labels=len(draft.labels))
            for idx, s in enumerate(draft.series)
        ]
        return ChartConfig(
            type=draft.chart_type,
            data=ChartData(labels=draft.labels, datasets=datasets),
            options=self._build_options(draft),
        )

    def _build_dataset(self, ctype, series, idx, n_labels) -> ChartDataset:
        if ctype in self._PER_POINT_TYPES:
            colors = [self.PALETTE[i % len(self.PALETTE)] for i in range(n_labels)]
            return ChartDataset(label=series.name, data=series.data,
                                backgroundColor=colors)
        color = self.PALETTE[idx % len(self.PALETTE)]
        return ChartDataset(label=series.name, data=series.data,
                            backgroundColor=color, borderColor=color)

    def _build_options(self, draft) -> dict:
        opts: dict = {"responsive": True}
        if draft.title:
            opts["plugins"] = {"title": {"display": True, "text": draft.title}}
        # scatter/radar/pie류는 axis title 부적절 → bar/line만 scales 부여
        if draft.chart_type in (ChartType.BAR, ChartType.LINE):
            opts["scales"] = {
                "x": {"title": {"display": bool(draft.x_axis_name),
                                "text": draft.x_axis_name}},
                "y": {"title": {"display": bool(draft.y_axis_name),
                                "text": draft.y_axis_name}},
            }
        return opts
```

### 3.4 응답 스키마 (`domain/general_chat/schemas.py`, 수정)

```python
class GeneralChatResponse(BaseModel):
    ...
    charts: list[dict] = []   # Chart.js config 리스트, 기본 [] (REST 하위호환)
```

WS 경로는 payload 패스스루이므로 스키마 변경 불필요(REST만 추가).

---

## 4. Domain Port & Infrastructure

### 4.1 ChartBuilderInterface (`domain/visualization/interfaces.py`, 추가)

```python
class ChartBuilderInterface(ABC):
    @abstractmethod
    async def build(
        self, question: str, analysis_text: str, context: str = ""
    ) -> list[ChartConfig]:
        """질문+분석텍스트(+컨텍스트)로 Chart.js config 리스트 생성. 실패 시 []."""
        raise NotImplementedError
```

`context`(D3): 도구 출력/sources를 합친 보조 텍스트. 답변 산문에 수치가 부족할 때 근거 제공.

### 4.2 LangChainChartBuilder (`infrastructure/visualization/llm_chart_builder.py`, 신규)

```python
class LangChainChartBuilder(ChartBuilderInterface):
    def __init__(self, llm: BaseChatModel, logger: LoggerInterface,
                 style_policy: ChartStylePolicy, max_count: int) -> None:
        self._llm = llm
        self._logger = logger
        self._style = style_policy
        self._max_count = max_count          # D1: settings.chart_max_count

    async def build(self, question, analysis_text, context="") -> list[ChartConfig]:
        prompt = _build_chart_prompt(question, analysis_text, context)
        try:
            draft_list = await self._llm.with_structured_output(
                ChartDraftList
            ).ainvoke(prompt)
        except Exception as e:
            self._logger.error("chart build failed, fallback []", exception=e)
            return []
        configs: list[ChartConfig] = []
        for draft in draft_list.charts[: self._max_count]:     # D1: 상한
            if not draft.labels or not draft.series:
                continue
            cfg = self._style.to_config(draft)                 # D2: 색상/options
            if cfg.data.datasets:                              # 빈 datasets 제거
                configs.append(cfg)
        return configs
```

### 4.3 추출 프롬프트 (`_build_chart_prompt`)

핵심 지시(요지):
- **명시된 수치만** 사용, 추측·창작 금지. 없으면 빈 배열.
- `labels`와 각 `series.data` **길이 일치**.
- chart_type 선택 가이드: 시계열/추세 → `line`, 카테고리 비교 → `bar`, 비중/구성 → `pie`/`doughnut`, 상관 → `scatter`, 다축 비교 → `radar`.
- 차트로 부적절하면 `charts: []`.
- `context`는 수치 근거 보강용 (D3) — 답변 텍스트와 모순되면 답변 우선.
- 최대 {max_count}개까지만.

> 색상/options는 프롬프트에서 **언급하지 않음** — Draft에는 색상 필드가 없어 LLM이 신경 쓸 필요 없음.

---

## 5. Application 통합 (`application/general_chat/use_case.py`)

### 5.1 생성자 (Optional 의존성 추가)

```python
def __init__(self, ...,
             viz_policy: VisualizationRoutingPolicy | None = None,
             viz_classifier: VisualizationClassifierInterface | None = None,
             chart_builder: ChartBuilderInterface | None = None):
    ...
    self._viz_policy = viz_policy
    self._viz_classifier = viz_classifier
    self._chart_builder = chart_builder
```

### 5.2 `_maybe_build_charts`

```python
async def _maybe_build_charts(
    self, question: str, answer: str, sources, tools_used,
) -> list[dict]:
    if self._chart_builder is None or not answer:
        return []
    policy = self._viz_policy or VisualizationRoutingPolicy()
    decision = policy.decide(question, answer)
    if decision is None:                              # 애매 → classifier
        decision = await self._classify_safe(question, answer)
    if decision != VizDecision.VISUALIZE.value:
        return []
    context = self._build_chart_context(sources, tools_used)   # D3
    try:
        charts = await self._chart_builder.build(question, answer, context)
    except Exception as e:
        self._logger.error("maybe_build_charts failed", exception=e)
        return []
    return [c.model_dump(exclude_none=True) for c in charts]
```

- `_classify_safe`: classifier 미주입/예외 시 `"text"`(보수).
- `_build_chart_context(sources)`(D3): sources의 `content`를 합쳐 길이 제한(2000자) 텍스트로. sources가 없으면 빈 문자열.
  - 정정(2026-06-06, Gap-1): 초안은 `tools_used`(도구 출력)도 합치도록 했으나, General Chat의 `tools_used`는 `_parse_agent_output`상 **도구 이름 문자열 리스트**(출력 아님)라 수치 추출 컨텍스트로 무의미. 실제 데이터는 `sources.content`에 담기므로 **sources-only**로 단순화. 시그니처에서 `tools_used` 제외.
- `model_dump(exclude_none=True)`: `borderColor=None` 등 불필요 키 제거 → 프론트 패스스루 깔끔.

### 5.3 ANSWER_COMPLETED 주입 (stream)

```python
charts = await self._maybe_build_charts(
    request.message, answer, sources, tools_used,
)
yield self._build_event(
    seq, ChatEventType.ANSWER_COMPLETED, session_id_str,
    {
        "answer": answer,
        "tools_used": tools_used,
        "sources": [s.model_dump() for s in sources],
        "was_summarized": was_summarized,
        "charts": charts,                         # 신규
    },
)
```

### 5.4 execute() (REST) 반영

`execute()`는 stream을 소비하므로 ANSWER_COMPLETED 처리부에서 `charts = ev.payload.get("charts", [])`를 읽어 `GeneralChatResponse(..., charts=charts)`로 전달.

---

## 6. DI 조립 (`api/main.py::create_general_chat_use_case_factory`)

REST(`get_general_chat_use_case`)와 WS(`get_ws_general_chat_use_case`)가 **이 팩토리 하나를 공유**하므로 한 곳만 수정하면 양쪽 적용 (D4).

```python
async def _factory(session: AsyncSession = Depends(get_session)) -> GeneralChatUseCase:
    ...
    # ── chart-builder DI ─────────────────────────────────────
    viz_llm = _llm_factory.create(_default_llm_model, temperature=0)
    chart_builder = LangChainChartBuilder(
        llm=viz_llm,
        logger=app_logger,
        style_policy=ChartStylePolicy(),
        max_count=settings.chart_max_count,        # D1
    )
    classifier = LangChainVisualizationClassifier(viz_llm)   # 재사용
    # ─────────────────────────────────────────────────────────

    return GeneralChatUseCase(
        ...,
        viz_policy=VisualizationRoutingPolicy(),
        viz_classifier=classifier,
        chart_builder=chart_builder,
    )
```

### 6.1 Config (`src/config.py`, D1)

```python
class Settings(BaseSettings):
    ...
    chart_max_count: int = 3      # chart-builder 다중 차트 상한
```

---

## 7. Error Handling

| 시나리오 | 처리 | 위치 |
|---------|------|------|
| chart_builder 미주입 | `[]` (하위호환) | `_maybe_build_charts` |
| 답변 빈 문자열 | `[]` | `_maybe_build_charts` |
| 판단 = text / 애매→text | `[]` (LLM 차트 호출 안 함) | policy/classifier |
| classifier 미주입·예외 | `"text"`로 보수 → `[]` | `_classify_safe` |
| LLM 추출 예외 | log.error + `[]`, 본 답변 흐름 유지 | builder / use_case |
| 빈 labels/series/datasets | 해당 차트 제거 | builder 4.2 |
| 차트 개수 초과 | 앞 `max_count`개만 | builder (D1) |
| LLM이 잘못된 chart_type | pydantic Enum 검증 실패 → 추출 예외 → `[]` | structured output |

---

## 8. Test Plan (TDD)

### 8.1 Domain — chart_schemas / ChartStylePolicy (`tests/domain/visualization/`)
- [ ] `ChartType` 값이 프론트 화이트리스트(bar/line/pie/doughnut/scatter/radar)와 정확히 일치
- [ ] `ChartConfig.model_dump(exclude_none=True)`가 `{type, data:{labels,datasets}, options}` 구조
- [ ] `ChartStylePolicy.to_config(bar draft)`: dataset에 `backgroundColor`(단일) + `options.scales.x/y.title` 존재
- [ ] `to_config(pie draft)`: `backgroundColor`가 labels 길이만큼의 **list[str]**
- [ ] `to_config(title 있음)`: `options.plugins.title.text == draft.title`
- [ ] 시리즈 다수 → 팔레트 순환 색상 부여

### 8.2 Infra — LangChainChartBuilder (`tests/infrastructure/visualization/`, AsyncMock)
- [ ] 정상: Fake LLM이 ChartDraftList(1개) 반환 → `build()` 길이 1, 색상/options 채워짐
- [ ] `max_count=3` 초과 draft 5개 → 결과 3개로 절단
- [ ] 빈 labels/series draft → 제거
- [ ] LLM 예외 → `[]` (예외 비전파)
- [ ] context 인자 전달 시 프롬프트에 포함(호출 인자 검증)

### 8.3 Application — `_maybe_build_charts` 분기 (`tests/application/general_chat/`)
- [ ] 명시 키워드 질문 → classifier 미호출, builder 호출 → charts 반환
- [ ] 비수치 답변 → builder 미호출, `[]`
- [ ] 애매 + classifier "visualize" → builder 호출
- [ ] 애매 + classifier "text" → `[]`
- [ ] chart_builder 미주입 → `[]`
- [ ] builder 예외 → `[]`, 예외 비전파

### 8.4 Application — stream/execute 통합
- [ ] visualize 케이스: ANSWER_COMPLETED payload에 `charts`(len≥1), 기존 키 불변
- [ ] text 케이스: `charts == []`
- [ ] execute(): `GeneralChatResponse.charts` 반영
- [ ] builder 예외에도 ANSWER_COMPLETED/CHAT_DONE 정상 발행

### 8.5 회귀
- [ ] 기존 `tests/application/general_chat/test_use_case.py` (charts 미주입 경로) GREEN 유지
- [ ] 기존 `tests/api/test_general_chat_router.py` GREEN

> 모든 신규 모듈 RED→GREEN. LLM은 Fake/AsyncMock, domain은 순수 단위테스트.
> ⚠️ Windows pytest 교차 실행 이벤트 루프 flakiness — 신규 async 테스트는 격리 실행으로 재확인.

---

## 9. Clean Architecture 점검

```
Application(use_case) ──→ Domain(VisualizationRoutingPolicy, ChartBuilderInterface, VizDecision)
Infra(LangChainChartBuilder) ──→ Domain(ChartBuilderInterface, ChartStylePolicy, chart_schemas)
Interfaces(main factory) ──→ Infra 구현체 주입
❌ Domain → App/Infra 참조 없음
```

- 색상·options 규칙(표현)이지만 **결정론적 순수 규칙**이라 domain Policy로 둠(LLM/외부 의존 0) → 레이어 위반 아님.
- LLM 호출만 infra. application은 port에만 의존.

---

## 10. Implementation Guide

### 10.1 File Structure

```
src/
├── domain/visualization/
│   ├── chart_schemas.py      # 신규: ChartType, ChartDataset, ChartData, ChartConfig
│   ├── chart_policy.py       # 신규: ChartDraft*, ChartStylePolicy
│   └── interfaces.py         # 수정: + ChartBuilderInterface
├── infrastructure/visualization/
│   └── llm_chart_builder.py  # 신규: LangChainChartBuilder
├── application/general_chat/
│   └── use_case.py           # 수정: _maybe_build_charts + ANSWER_COMPLETED/execute
├── domain/general_chat/
│   └── schemas.py            # 수정: GeneralChatResponse.charts
├── config.py                 # 수정: chart_max_count
└── api/main.py               # 수정: general-chat 팩토리 DI

idt_front/                    # /api-contract-sync: REST 타입 charts 반영 (WS는 정의됨)
```

### 10.2 Implementation Order (TDD)

1. [ ] `chart_schemas.py` + 테스트 8.1(스키마) → GREEN
2. [ ] `chart_policy.py`(Draft + ChartStylePolicy) + 테스트 8.1(스타일) → GREEN
3. [ ] `interfaces.py` `ChartBuilderInterface` 추가
4. [ ] `llm_chart_builder.py` + 테스트 8.2 → GREEN
5. [ ] `config.py` `chart_max_count`
6. [ ] `general_chat/schemas.py` `charts` 필드
7. [ ] `use_case.py` `_maybe_build_charts` + stream/execute + 테스트 8.3/8.4 → GREEN
8. [ ] `main.py` 팩토리 DI 조립
9. [ ] 회귀 8.5 GREEN
10. [ ] `/api-contract-sync` (REST 타입) → `/pdca analyze chart-builder`

### 10.3 Naming Conventions

| Target | Rule | Example |
|--------|------|---------|
| Pydantic 계약 모델 | PascalCase | `ChartConfig`, `ChartDataset` |
| Domain Policy | PascalCase + Policy | `ChartStylePolicy` |
| Port | PascalCase + Interface | `ChartBuilderInterface` |
| Infra 어댑터 | 기술 prefix | `LangChainChartBuilder` |
| use_case private | `_snake_case` | `_maybe_build_charts`, `_build_chart_context` |

---

## 11. Out of Scope (후속 Plan)

- **Excel 워크플로우**: `chart_router` 뒤 `chart_builder` 노드 부착 → `AnalysisResult`에 charts 노출 (REST).
- **Supervisor(agent_builder)**: analysis 워커 경로 차트 + `agent_answer_completed.charts` 프론트 필드 신설.
- 다중 차트 UX(개수>3, 레이아웃), 차트 색상 테마 사용자 설정, 차트 캐싱.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-06-06 | Initial draft — General Chat 연동, 추출/표현 분리, D1~D4 반영 | 배상규 |
