# Design: chart-context-continuity

> Created: 2026-06-10
> Phase: Design
> Plan: `docs/01-plan/features/chart-context-continuity.plan.md`
> Scope: `idt/` 백엔드 — 차트/분석 데이터의 멀티턴 컨텍스트 연속성

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | 차트는 `conversation_message.charts`에 저장되지만 D7 결정으로 LLM 컨텍스트에 미투입 → "해당 그래프" 후속 지시 해석 불가. 엑셀 분석 데이터는 워크플로우 메모리에만 존재 → 응답 후 소실. |
| **Solution** | ① 컨텍스트에 차트 **캡션 1줄**만 투입(D7-rev1) ② 차트 편집 의도 감지 시 저장된 charts를 로드해 **ChartTransformer**(LLM) 전용 경로로 변환 ③ 분석 결과를 `analysis_artifact` 테이블에 영속화하고 후속 차트 생성에 재사용. |
| **Function UX Effect** | "색 바꿔줘", "파이로 변경", "같은 데이터로 다른 그래프" 등 자연스러운 후속 대화 지원. |
| **Core Value** | 단발성 차트 생성기 → 대화형 데이터 시각화 어시스턴트. 기존 graceful-degrade 원칙(차트 실패가 본 답변을 막지 않음) 유지. |

---

## 1. 설계 결정 (Decisions)

| ID | 결정 | 근거 |
|----|------|------|
| **D1** | 컨텍스트에는 차트 **캡션만** 투입한다. full config(JSON)는 절대 일반 컨텍스트에 넣지 않는다. | 토큰 상한 보호. 요약 정책과의 충돌 회피 |
| **D2** | 차트 편집 의도 감지는 **휴리스틱 도메인 정책**으로 1차 판단하고, 모호하면 **일반 경로로 폴백**(보수적). LLM 분류기는 선택 주입(기존 `VisualizationClassifierInterface` 패턴 동형). | 기존 `VisualizationRoutingPolicy` 2단 패턴과 일관. 오분류 시 피해 최소화 |
| **D3** | 차트 변환은 신규 포트 `ChartTransformerInterface`로 분리한다. 기존 `ChartBuilderInterface`(텍스트→차트)와 책임이 다름(기존 config+지시→새 config). | 단일 책임. 기존 빌더 무변경 |
| **D4** | 편집 경로는 ReAct 에이전트를 **우회**하는 전용 분기. 변환 실패/차트 미발견 시 기존 일반 경로로 폴백. | "색 바꿔줘"는 도구 호출이 불필요. 지연·비용 절감. 실패해도 기존 동작 보장 |
| **D5** | 색상 등 표현은 계속 `ChartStylePolicy`가 결정하되, 변환 draft에 **선택적 색상 오버라이드**를 허용한다(명시 색상 요청 대응). | "LLM은 데이터만, 표현은 도메인 정책" 원칙 유지 + 명시 요청 예외 허용 |
| **D6** | 분석 아티팩트는 신규 `analysis_artifact` 테이블(MySQL JSON)에 세션 스코프로 저장. 스냅샷은 `SnapshotReductionPolicy`로 크기 상한 적용. | Plan §4-2 옵션 A 채택. 대화 엔티티 비침투 |
| **D7-rev1** | 기존 D7("charts LLM 컨텍스트 미투입")을 "**full config 미투입, 캡션은 투입**"으로 개정. 요약 본문에는 여전히 미포함(캡션은 최근 턴 윈도우에서만 유효). | 본 feature의 명시 승인 범위. `docs/rule/conversation-memory.md` 갱신 |
| **D8** | 응답 계약(`charts: list[dict]`, WS `ANSWER_COMPLETED` payload) **무변경**. 프론트 작업 없음. | Plan 비목표 N1, 회귀 방지 |

### 수치 상한 (확정)

| 항목 | 값 | 비고 |
|------|----|------|
| 캡션 길이 | 메시지당 ≤ 200자 (차트 최대 2개 표기, labels 최대 5개 표기) | ≈ 60~100 token/턴 |
| 캡션 적용 범위 | 컨텍스트 윈도우 내 assistant 메시지만 (전체 컨텍스트 시 전부, 요약 시 최근 3턴) | 요약 본문 미포함 |
| Transformer 입력 charts | 최근 assistant 메시지 1건의 charts (최대 3개), 직렬화 ≤ 8KB (초과 시 dataset당 data 앞 100포인트로 절단) | 빌더 산출 차트는 통상 수백 byte |
| 스냅샷 크기 상한 | 직렬화 200KB. 초과 시 시트당 행 50개 + 수치 컬럼 통계(min/max/mean/sum/count)로 축약, 그래도 초과 시 통계만 | `SnapshotReductionPolicy` |
| 차트 생성용 스냅샷 컨텍스트 | ≤ 2,000자 | 기존 `llm_chart_builder._MAX_CONTEXT`와 동일 |

---

## 2. 현재 코드 기준점

| 항목 | 위치 | 활용 |
|------|------|------|
| 세션 히스토리 로드 | `general_chat/use_case.py:171` `find_by_session` | **이미 전체 메시지(charts 포함)를 로드함** → 신규 repo 메서드 불필요, 최근 charts는 history에서 역순 탐색 |
| 컨텍스트 빌드 | `use_case.py:477-527` `_build_summarized_context` / `_build_full_context` | 캡션 주입 지점 |
| 차트 빌드 | `use_case.py:289-314` `_maybe_build_charts` | `chart_new_from_data` 시 artifact 컨텍스트 전달로 재사용 |
| 라우팅 정책 | `domain/visualization/policies.py` `VisualizationRoutingPolicy` | 패턴 참조(신규 `ChartFollowupPolicy` 동형 설계) |
| Draft/Style | `domain/visualization/chart_policy.py` `ChartDraft`/`ChartStylePolicy` | Transformer draft 확장 + 색상 오버라이드 |
| 빌더 구현 | `infrastructure/visualization/llm_chart_builder.py` | Transformer 구현 패턴 참조(structured output + graceful) |
| 엑셀 상태 | `workflows/excel_analysis_workflow.py` `ExcelAnalysisState` | 아티팩트 저장 소스 |
| Supervisor 분석 | `agent_builder/workflow_compiler.py` `_run_excel_analysis` | 아티팩트 저장 훅(Phase 2) |
| 마이그레이션 | `db/migration/V031__...` | 다음 번호 **V032** |

---

## 3. Phase 1 — General Chat 차트 참조 연속성

### 3.1 ChartCaptionPolicy (domain, 신규)

`src/domain/conversation/chart_caption_policy.py` — 순수 함수형 정책 (외부 의존 0).

```python
class ChartCaptionPolicy:
    """저장된 charts(list[dict]) → 컨텍스트용 1줄 캡션. D7-rev1."""

    MAX_CHARTS = 2
    MAX_LABELS = 5
    MAX_LEN = 200

    def build_caption(self, charts: list[dict]) -> str:
        # 예: '[생성된 차트: bar "부서별 대출 건수" (labels: 영업,심사,관리 외 2 | series: 건수)]'
        # charts가 비었거나 형식 오류면 "" 반환 (graceful)
```

- 출력 형식: `[생성된 차트: {type} "{title}"({labels 요약} | series: {시리즈명들})]`, 2개 초과 시 `외 N개` 표기, 전체 200자 절단.
- title은 `options.plugins.title.text`에서, 없으면 생략. dict 파싱 실패는 모두 빈 문자열 폴백.

### 3.2 컨텍스트 주입 (use_case 수정)

`_build_full_context` / `_build_summarized_context`의 assistant 메시지 변환부:

```python
else:
    content = msg.content
    if msg.charts:
        caption = self._caption_policy.build_caption(msg.charts)
        if caption:
            content = f"{content}\n\n{caption}"
    messages.append(AIMessage(content=content))
```

- 요약 경로는 **최근 3턴**에만 적용(요약 본문 생성 입력은 기존대로 content만 — `ConversationSummarizer` 무변경).
- `_SYSTEM_PROMPT`에 1줄 추가: `"이전 턴에 [생성된 차트: ...] 표기가 있으면 해당 차트를 참조한 후속 요청을 이해하세요."`

### 3.3 ChartFollowupPolicy (domain, 신규)

`src/domain/visualization/followup_policy.py` — `VisualizationRoutingPolicy`와 동형의 휴리스틱.

```python
class ChartFollowupDecision(str, Enum):
    EDIT = "chart_edit"            # 기존 차트 수정 (색/타입/시리즈)
    NEW_FROM_DATA = "chart_new_from_data"  # 저장된 분석 데이터로 신규 차트 (Phase 3)
    NONE = "none"

class ChartFollowupPolicy:
    REFERENT_KEYWORDS = ("해당", "이 ", "그 ", "위 ", "방금", "아까", "그걸", "이걸")
    CHART_NOUNS = ("그래프", "차트", "도표", "chart", "graph")
    EDIT_VERBS = ("바꿔", "변경", "수정", "넣어", "추가", "색", "색깔", "나눠", "분리", "합쳐")

    def decide(self, question: str) -> ChartFollowupDecision:
        # EDIT: (지시어 + 차트명사) 또는 (차트명사 + 편집동사)
        # 둘 다 아니면 NONE (보수적 — 애매하면 일반 경로)
```

- "그래프 그려줘"(신규 생성)는 EDIT_VERBS 미충족으로 NONE → 기존 `_maybe_build_charts` 경로 그대로.
- "원으로/파이로 변경" 같은 타입 변경도 (차트명사 + "변경") 조합으로 EDIT 판정.
- **application 가드**: 정책이 EDIT여도 세션에 charts 부속 assistant 메시지가 없으면 일반 경로 (오분류 안전망).

### 3.4 ChartTransformerInterface (domain, 신규)

`src/domain/visualization/interfaces.py`에 추가:

```python
class ChartTransformResult(BaseModel):
    charts: list[ChartConfig]   # 변환/추가된 차트 (빈 리스트 = 변환 실패/불가)
    message: str                # 사용자에게 보여줄 짧은 확인 답변 (한국어)

class ChartTransformerInterface(ABC):
    @abstractmethod
    async def transform(
        self, instruction: str, charts: list[dict], context: str = "",
    ) -> ChartTransformResult:
        """기존 차트 config + 사용자 지시(+분석 데이터 컨텍스트) → 새 차트.

        실패 시 charts=[] 의 결과를 반환해 호출측이 일반 경로로 폴백하게 한다.
        """
```

### 3.5 변환 draft + 색상 오버라이드 (domain 확장)

`chart_policy.py` 확장 — 기존 `ChartDraft`/`ChartStylePolicy` 무변경 원칙, 추가만:

```python
class ChartEditSeriesDraft(ChartSeriesDraft):
    color: str | None = Field(default=None, description="명시 색상 요청 시만 hex (#RRGGBB)")

class ChartEditDraft(ChartDraft):
    series: list[ChartEditSeriesDraft]

class ChartEditDraftList(BaseModel):
    charts: list[ChartEditDraft] = Field(default_factory=list)
    message: str = Field(default="", description="사용자 확인용 1~2문장 한국어 답변")
```

`ChartStylePolicy`에 오버라이드 인지 로직 추가 (기존 `to_config` 시그니처 유지, 내부에서 `ChartEditSeriesDraft.color` 존재 시 해당 시리즈만 오버라이드, 미지정 시리즈는 기존 팔레트):

```python
def _build_dataset(self, chart_type, series, idx, n_labels):
    override = getattr(series, "color", None)
    color = override or self._color(idx)
    ...
```

> "각 사용자마다 색깔" 시나리오: LLM이 단일 시리즈를 사용자별 다중 시리즈로 **재구조화**하면 기존 팔레트가 시리즈별 상이 색상을 자동 부여. 색상 오버라이드는 "빨간색으로" 같은 명시 요청에만 사용.

### 3.6 LangChainChartTransformer (infrastructure, 신규)

`src/infrastructure/visualization/llm_chart_transformer.py` — `llm_chart_builder.py`와 동일 패턴.

```python
_MAX_CHARTS_JSON = 8_000  # 직렬화 상한 (초과 시 dataset.data 앞 100포인트 절단)

def _build_transform_prompt(instruction, charts_json, context) -> str:
    # 규칙:
    # - 아래 [기존 차트]의 데이터를 기반으로 사용자 지시를 적용한 새 차트를 생성하세요.
    # - 데이터 수치를 창작하지 마세요. 재구조화(시리즈 분리/병합, 타입 변경)는 허용.
    # - 색상은 사용자가 명시한 경우에만 series.color에 hex로 지정하세요.
    # - 지시를 적용할 수 없으면 charts를 빈 배열로 두고 message에 사유를 쓰세요.
    # - message는 1~2문장 한국어 확인 답변.

class LangChainChartTransformer(ChartTransformerInterface):
    def __init__(self, llm, logger, style_policy: ChartStylePolicy): ...

    async def transform(self, instruction, charts, context="") -> ChartTransformResult:
        # with_structured_output(ChartEditDraftList) → style_policy.to_config
        # 예외 → logger.error(exception=e) + ChartTransformResult(charts=[], message="")
```

### 3.7 use_case 편집 분기 (D4)

`GeneralChatUseCase.__init__`에 선택 주입 추가(기존 패턴): `chart_transformer: ChartTransformerInterface | None = None`, `followup_policy: ChartFollowupPolicy | None = None`, `caption_policy: ChartCaptionPolicy | None = None`.

`stream()` 내 history 로드 직후:

```python
recent_charts = self._find_recent_charts(history)  # 역순 탐색, 첫 charts 부속 assistant 메시지
if (
    self._chart_transformer is not None
    and recent_charts
    and (self._followup_policy or ChartFollowupPolicy()).decide(request.message)
        == ChartFollowupDecision.EDIT
):
    result = await self._transform_safe(request.message, recent_charts)
    if result.charts:   # 실패(빈 리스트) 시 아래 일반 경로로 폴백
        charts = [c.model_dump(exclude_none=True) for c in result.charts]
        await self._persist_messages(
            user_id, session_id, request.message, result.message,
            len(history), charts=charts,
        )
        yield self._build_event(seq, ChatEventType.ANSWER_COMPLETED, session_id_str, {
            "answer": result.message, "tools_used": ["chart_transformer"],
            "sources": [], "was_summarized": False, "charts": charts,
        })
        yield self._build_event(seq, ChatEventType.CHAT_DONE, ...)
        return
# (이하 기존 일반 경로 그대로)
```

- 이벤트 시퀀스 `CHAT_STARTED → ANSWER_COMPLETED → CHAT_DONE`는 기존 WS 어댑터/프론트 계약과 동일(D8). `tools_used=["chart_transformer"]`로 관측 가능성 확보.
- `_transform_safe`: 예외 → `logger.error(exception=e)` 후 빈 결과 반환(폴백). `_classify_safe`와 동형.
- 함수 40줄 규칙: 분기 본문은 `_try_chart_edit()` 헬퍼로 추출.

### 3.8 DI (main.py)

기존 chart_builder 주입부 인근: `LangChainChartTransformer(llm=차트용 LLM 공유, logger, style_policy)` 생성 후 `GeneralChatUseCase`에 주입. 미주입 시 기능 전체 비활성(하위호환) — 기존 Optional 주입 컨벤션 동일.

---

## 4. Phase 2 — 분석 아티팩트 영속화

### 4.1 도메인 (신규 `src/domain/analysis_artifact/`)

```python
# entities.py
@dataclass
class AnalysisArtifact:
    id: Optional[int]
    user_id: str
    session_id: str
    artifact_type: str          # "excel" | "document"(확장)
    analysis_text: str
    data_snapshot: Optional[dict]   # 축약된 데이터 스냅샷
    charts: Optional[list[dict]]    # 분석 시 생성된 차트 (빈 배열 금지 — None)
    source_filename: Optional[str]
    created_at: datetime
    # __post_init__: artifact_type 화이트리스트, analysis_text 비어있음 금지,
    #                charts 빈 배열 금지(None으로) — ConversationMessage L62-64 컨벤션 동일

# policies.py
class SnapshotReductionPolicy:
    MAX_BYTES = 200_000
    SAMPLE_ROWS = 50
    FALLBACK_ROWS = 20

    def reduce(self, snapshot: dict) -> dict:
        """직렬화 크기 상한 적용. 초과 시 단계 축약:
        ① 시트당 행 50 + 수치 컬럼 통계  ② 행 20  ③ 통계+행/열 수만.
        축약 시 snapshot["_reduced"] = True 마킹."""
```

### 4.2 리포지토리 포트 (application — 기존 컨벤션)

`src/application/repositories/analysis_artifact_repository.py`:

```python
class AnalysisArtifactRepository(ABC):
    @abstractmethod
    async def save(self, artifact: AnalysisArtifact) -> AnalysisArtifact: ...
    @abstractmethod
    async def find_latest_by_session(
        self, user_id: str, session_id: str,
    ) -> Optional[AnalysisArtifact]: ...
```

### 4.3 인프라

- `infrastructure/persistence/models/analysis_artifact.py` — ORM (JSON 컬럼: data_snapshot, charts)
- `infrastructure/persistence/mappers/analysis_artifact_mapper.py`
- `infrastructure/persistence/repositories/analysis_artifact_repository.py` — **commit/rollback 금지**(세션은 UseCase 단위, 기존 규칙)

### 4.4 마이그레이션 — `db/migration/V032__create_analysis_artifact.sql`

```sql
CREATE TABLE analysis_artifact (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id         VARCHAR(64)  NOT NULL,
    session_id      VARCHAR(64)  NOT NULL,
    artifact_type   VARCHAR(20)  NOT NULL,
    analysis_text   MEDIUMTEXT   NOT NULL,
    data_snapshot   JSON         NULL,
    charts          JSON         NULL,
    source_filename VARCHAR(255) NULL,
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_artifact_session (user_id, session_id, created_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 4.5 저장 훅

| 경로 | 위치 | 동작 |
|------|------|------|
| Supervisor 분석 워커 | `workflow_compiler.py::_run_excel_analysis` 완료 후 (또는 analysis 노드 종료부) | `session_id`/`user_id`를 보유한 상위(run_agent_use_case)에서 저장. `analysis_text` + `excel_data`(축약) + 상단 chart_builder 산출 charts |
| Standalone 엑셀 분석 | `AnalyzeExcelUseCase.execute` 말미 | 요청에 `session_id` 있을 때만 저장, 없으면 skip + info 로그 |

- 저장 실패는 **분석 응답을 막지 않는다**(try/except + `logger.error(exception=e)`, graceful).
- 선행 조건: `excel-chart-routing-dedup`(차트 일원화) 완료 후 착수 — charts 소스가 상단 노드로 단일화된 상태를 전제.

---

## 5. Phase 3 — 분석 후속 질문 재사용

### 5.1 General Chat 경로 (`chart_new_from_data`)

- `ChartFollowupPolicy.decide`가 `NEW_FROM_DATA` 판정(차트 생성 요청 + 현재 질문에 수치 신호 부재)이고 세션 최신 아티팩트가 존재하면:
  - `_maybe_build_charts`의 context 인자에 `artifact.analysis_text + 축약 스냅샷 직렬화(≤2,000자)` 전달 → **기존 ChartBuilder 재사용**, 신규 빌더 불필요.
- EDIT 판정 + 아티팩트 존재 시(복합 지시: "원형으로 변경하고 다른 그래프도"): Transformer의 `context` 인자로 아티팩트 컨텍스트를 전달 → 기존 차트 변환 + 추가 차트 생성을 단일 호출로 처리(§3.4 계약에 이미 `context` 포함).

### 5.2 Supervisor(Agent Chat) 경로

엑셀 분석은 주로 Supervisor 세션에서 발생하므로 동일 의도 라우팅이 필요하다:

- supervisor 라우팅(또는 analysis 워커 진입부)에서 `ChartFollowupPolicy` 적용 → EDIT/NEW_FROM_DATA 시 첨부 재파싱 대신 `find_latest_by_session` 아티팩트 + 세션 최근 charts를 로드해 동일 `ChartTransformerInterface` 호출.
- 상세 그래프 노드 설계는 `excel-chart-routing-dedup` 완료 후 별도 Design 증보(§부록 A 확장 포인트). **Phase 3 범위는 General Chat 경로 + Supervisor는 포트 재사용 가능함을 보장하는 계약까지.**

> 의존성: Supervisor 경로의 charts가 conversation_message에 영속되는지(CC 메모리: 차트 퍼시스턴스는 현재 General Chat만) Phase 3 착수 시 재확인. 미영속이면 아티팩트의 `charts` 컬럼이 "최근 차트" 소스 역할을 대신한다(이중 안전망 — 본 설계가 charts를 아티팩트에도 저장하는 이유).

---

## 6. 전체 흐름 (목표 상태)

```
stream(request)
 ├─ history = find_by_session()                      # 기존
 ├─ recent_charts = _find_recent_charts(history)     # 신규 (역순 첫 charts)
 ├─ followup = ChartFollowupPolicy.decide(message)
 │
 ├─ [EDIT & recent_charts & transformer 주입]
 │    └─ transform(instruction, recent_charts, artifact_ctx?) 
 │         ├─ 성공: persist + ANSWER_COMPLETED(charts) + DONE  ← ReAct 우회
 │         └─ 실패(charts=[]): ↓ 일반 경로 폴백
 │
 ├─ [일반 경로] 컨텍스트 빌드 (assistant 메시지에 캡션 부착, D7-rev1)
 │    └─ ReAct agent → answer
 │         └─ _maybe_build_charts(question, answer, sources,
 │                context += [NEW_FROM_DATA면 artifact 컨텍스트])   # Phase 3
 └─ persist(charts) → ANSWER_COMPLETED → DONE        # 기존
```

---

## 7. 테스트 계획 (TDD — Red 먼저)

### 7.1 Domain (Phase 1)

| 테스트 | 검증 |
|--------|------|
| `tests/domain/test_chart_caption_policy.py` | 정상 캡션 포맷 / 2개 초과 `외 N개` / labels 5개 절단 / 200자 상한 / 빈·기형 charts → `""` |
| `tests/domain/test_chart_followup_policy.py` | "해당 그래프에 색 넣어줘"→EDIT / "그래프를 원으로 변경"→EDIT / "그래프 그려줘"→NONE / "이 문서 요약해줘"→NONE / 영어 혼용 |
| `tests/domain/test_chart_policy.py` (확장) | `ChartEditSeriesDraft.color` 오버라이드 적용 / 미지정 시 기존 팔레트 / pie per-point 색상 유지 |

### 7.2 Application (Phase 1)

| 테스트 | 검증 |
|--------|------|
| `tests/application/general_chat/test_use_case.py` (확장) | ① EDIT + 차트 존재 → transformer 호출·ReAct 미호출·ANSWER_COMPLETED에 새 charts ② EDIT + 차트 부재 → 일반 경로 ③ transform 빈 결과 → 일반 경로 폴백 ④ transformer 미주입 → 기존 동작(하위호환) ⑤ 캡션이 agent 입력 AIMessage에 포함 ⑥ 요약 경로 최근 3턴 캡션 ⑦ 차트 무관 질문 회귀 없음 |

### 7.3 Phase 2/3

| 테스트 | 검증 |
|--------|------|
| `tests/domain/test_analysis_artifact.py` | 엔티티 불변식(type 화이트리스트, 빈 charts 금지), `SnapshotReductionPolicy` 단계 축약/`_reduced` 마킹 |
| `tests/infrastructure/test_analysis_artifact_repository.py` | save/find_latest_by_session (세션 격리 포함) |
| `tests/infrastructure/test_llm_chart_transformer.py` | structured output 모킹 → ChartConfig 변환 / LLM 예외 → 빈 결과 / 8KB 절단 |
| `tests/application/.../test_use_case.py` (확장) | 분석 완료 시 artifact 저장 / 저장 실패 graceful / NEW_FROM_DATA → builder에 artifact 컨텍스트 전달 / 복합 지시(타입 변경+추가 차트) |

> 주의: 기존 사전 실패 케이스(tests/api 28건·infra 30건, auth DI)는 본 feature 회귀로 오인하지 않는다.

---

## 8. 구현 순서

**Phase 1** (독립 배포 단위)
1. `ChartCaptionPolicy` (test → impl)
2. `ChartFollowupPolicy` + `ChartFollowupDecision` (test → impl)
3. `ChartTransformerInterface` + `ChartTransformResult` + `ChartEditDraft`/스타일 오버라이드 (test → impl)
4. `LangChainChartTransformer` (test → impl)
5. use_case: 캡션 주입 → 편집 분기(`_try_chart_edit`) → 시스템 프롬프트 1줄 (test → impl)
6. `main.py` DI + `docs/rule/conversation-memory.md` D7-rev1 반영
7. `verify-architecture` / `verify-logging` / `verify-tdd` 스킬 실행

**Phase 2** (선행: excel-chart-routing-dedup 완료 확인)
8. `AnalysisArtifact` 엔티티 + `SnapshotReductionPolicy` → 리포지토리 포트 → ORM/매퍼/리포지토리 구현
9. `db-migration` 스킬로 V032 생성
10. 저장 훅 (Supervisor / Standalone)

**Phase 3**
11. `NEW_FROM_DATA` 판정 + builder 컨텍스트 연결
12. 복합 지시 E2E 시나리오 테스트
13. Supervisor 경로 계약 확인(별도 Design 증보 여부 판단)

---

## 9. 영향 범위 / 회귀 가드

| 영역 | 변경 | 회귀 가드 |
|------|------|----------|
| WS/응답 스키마 | **없음** (charts: list[dict] 유지) | 기존 ws_adapter/프론트 테스트 무변경 통과 |
| 일반 질문 경로 | 캡션 추가만 (charts 없는 메시지는 기존과 동일) | test ⑦ |
| 요약 정책 | 무변경 (요약 입력·본문에 캡션 미포함) | summarizer 기존 테스트 통과 |
| chart_builder | 무변경 (context 인자 활용만) | 기존 빌더 테스트 통과 |
| DB | analysis_artifact 신규 테이블만 (기존 테이블 무변경) | Flyway V032 |
| 프론트 (idt_front) | 작업 없음 | — |
| 문서 | conversation-memory.md(D7-rev1), entities.py 주석 갱신 | design-validator |

## 부록 A — 확장 포인트 (이번 범위 외, 자리만 확보)

- `transform(..., chart_id: str | None)`: 프론트가 특정 차트 지정 시(비목표 N1) — 시그니처 추가 없이 charts 인자 선별로 대응 가능하도록 호출부에서 선택 로직 분리.
- `artifact_type="document"`: 문서 분석(추후) — 테이블/엔티티는 이미 수용.
- 원본 파일 재파싱 경로: 스냅샷 상한 초과 대용량 케이스 — `source_filename` 컬럼이 연결 고리.
