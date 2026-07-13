# analysis-source-preservation Design Document

> **Summary**: 엑셀 분석 워크플로우가 계산하고도 버리던 파싱 원천 데이터(`ExcelData.to_dict()`)를 SupervisorState 채널(`charts` 동형)로 노출·캡처하고, 스냅샷에 `kind="raw_source"` 항목으로 저장한다. 재주입·재분석은 기존 경로(검색결과 규약 → `_analyze_context` context 분기)를 그대로 재사용한다.
>
> **Project**: sangplusbot (idt 백엔드)
> **Author**: 배상규
> **Date**: 2026-07-07
> **Status**: Draft
> **Planning Doc**: [analysis-source-preservation.plan.md](../../01-plan/features/analysis-source-preservation.plan.md)
> **선행**: analysis-data-continuity (스냅샷 인프라 재사용)

---

## 1. Overview

### 1.1 Design Goals

1. **원천 캡처**: 엑셀 분기 턴에서 `final["excel_data"]`(파싱된 시트/행/값)를 스냅샷에 `kind="raw_source"`로 저장.
2. **병행 보관**: 기존 분석 결과 텍스트는 선행 analysis-data-continuity가 저장하는 그대로
   (`kind="excel"`, `_snapshot_items`의 excel 분기)로 병행 유지(표시 연속성). 본 기능은 원천만 추가.
3. **경로 재사용**: 재주입은 `format_search_result` 규약 AIMessage, 재분석은 `_analyze_context` context 분기 — **신규 그래프 배선 0**.
4. **비회귀 크기 처리**: 원천은 표 데이터라 크므로 **별도 budget**(raw_source 전용 상한)로 처리 → 기존 analysis-data-continuity 상한(item 4000/total 8000) 동작 불변.

### 1.2 Design Principles

- 원천은 메시지가 아니라 **state 채널**로 흐른다(`charts` 상태 채널·`_StreamState.charts` 캡처 선례 미러링).
- 원천의 텍스트 직렬화·행 샘플링·상한은 domain(`AnalysisSnapshotPolicy`) 단일 정의.
- 미주입/파싱 실패/캡처 실패는 graceful degrade — 결과 텍스트만으로 기존 동작 유지(FR-06).
- 스코프는 **엑셀 분기(RunAgentUseCase)만**. General Chat/검색은 무변경.

### 1.3 사전 검증 결과 (코드 확인, 2026-07-07)

| 확인 | 결과 | 반영 |
|------|------|------|
| 원천 데이터 위치 | `_parse_excel_node`가 `state["excel_data"]=parsed_data.to_dict()` 설정(`excel_analysis_workflow.py:176`). 시트별 `{data:[행], columns, dtypes, row_count}`(`sheet_data.py:28`) | `final["excel_data"]`가 원천 |
| 원천 폐기 지점 | `_run_excel_analysis`가 `analysis_text`만 반환(`workflow_compiler.py:832`) | D2에서 원천 병행 반환 |
| state 채널 선례 | `charts`가 노드 output dict → `SupervisorState.charts` → `_map_chain_end`가 `output.get("charts")` 캡처(`run_agent_use_case.py:621`) | `analysis_source` 채널 동형 추가 |
| 재분석 경로 | 후속 턴 첨부 없음 → `analysis_node` context 분기(`workflow_compiler.py:781`) → `_analyze_context`가 검색결과를 데이터로 사용 | 재주입 원천이 그대로 데이터가 됨 |
| 스코프 | 엑셀 워크플로우는 custom agent만 배선, General Chat은 ReAct | GeneralChatUseCase 무변경 |

---

## 2. Architecture

### 2.1 변경 전후 흐름

```
[변경 전 — 엑셀 턴]
parse → excel_data(원천 dict) → analyze → analysis_text
                    │ (버려짐)              └─▶ AIMessage → 스냅샷: analysis_output만
                    ▼
                 폐기

[변경 후 — 엑셀 턴]
parse → excel_data(원천 dict) ──────────────────┐
        │                                        ▼
        └─▶ analyze → analysis_text → AIMessage  analysis_node가 state["analysis_source"]로 노출
                                        │         │
                                        ▼         ▼
              _collect_snapshot: analysis_output + raw_source(직렬화·샘플링) → 스냅샷 저장

[후속 턴 — 첨부 없음]
_build_messages → 스냅샷 재주입(raw_source를 검색결과 규약 AIMessage로)
   → analysis_node context 분기 → _analyze_context가 원천 표를 데이터로 재집계 → 새 차트
```

### 2.2 원천 채널 (charts 동형)

```
analysis_node output {"analysis_source": [{origin, kind:"raw_source", excel: <dict>}]}
   → SupervisorState.analysis_source (replace 리듀서)
   → on_chain_end output → _StreamState.analysis_source 캡처 (_map_chain_end)
   → _collect_snapshot이 raw_source 항목으로 병합
```

---

## 3. Detailed Design

### 3.1 D1 — 원천 전달 채널 (SupervisorState + 캡처)

**`supervisor_state.py`** — 새 필드(charts 동형, replace 시맨틱):

```python
class SupervisorState(TypedDict):
    ...
    charts: list[dict]
    visualization_done: bool
    # analysis-source-preservation: 엑셀 분기 원천 데이터(파싱 dict) 전달 채널.
    # [{"origin": worker_id, "kind": "raw_source", "excel": ExcelData.to_dict()}]
    analysis_source: list[dict]
```

**`build_initial_state`** (`supervisor_nodes.py`)에 `"analysis_source": []` 추가.

**`run_agent_use_case._StreamState`** — 캡처 필드:

```python
@dataclass
class _StreamState:
    ...
    charts: list = field(default_factory=list)
    analysis_source: list = field(default_factory=list)
```

**`_map_chain_end`** — charts 캡처 바로 아래:

```python
if isinstance(output, dict) and output.get("analysis_source"):
    state.analysis_source = list(output["analysis_source"])
```

### 3.2 D2 — `_run_excel_analysis` 원천 병행 반환 (`workflow_compiler.py`)

```python
async def _run_excel_analysis(self, wf, question, excel, logger) -> tuple[str, dict | None]:
    """(analysis_text, raw_excel_dict|None) 반환. 원천은 final['excel_data']."""
    ...
    try:
        final = await wf.run(initial)
    except Exception as e:
        logger.error("analysis_node excel workflow failed", exception=e)
        return (f"엑셀 분석 실패: {e}", None)
    text = final.get("analysis_text", "") or "(엑셀 분석 결과 없음)"
    raw = final.get("excel_data")
    # 파싱 성공분만 원천으로 인정 (sheets 키 존재 = to_dict 결과). 미파싱 {file_path}는 제외.
    raw = raw if isinstance(raw, dict) and "sheets" in raw else None
    return (text, raw)
```

**`analysis_node`** — 엑셀 분기에서만 원천 노출:

```python
async def analysis_node(state):
    ...
    source_items: list[dict] = []
    if wf is not None:
        analysis_text, raw = await self._run_excel_analysis(wf, question, excel, logger)
        if raw is not None:
            source_items = [{"origin": worker_id, "kind": "raw_source", "excel": raw}]
    else:
        analysis_text = await self._analyze_context(...)
    result = {
        "messages": [AIMessage(content=analysis_text, name=worker_id)],
        "last_worker_id": worker_id,
        "token_usage": state["token_usage"] + len(analysis_text)//4,
    }
    if source_items:
        result["analysis_source"] = source_items  # context 분기는 키 미포함 → 빈 배열 유지
    return result
```

> context 분기(후속 턴)는 `analysis_source`를 넣지 않는다 — 원천은 최초 엑셀 턴에만 캡처.

### 3.3 D3 — `AnalysisSnapshotPolicy`: 원천 직렬화·샘플링·kind별 상한

**원천 텍스트 직렬화** (재주입이 텍스트 규약이므로 캡처 시 압축 텍스트로 변환):

```python
def render_raw_source(self, excel: dict) -> str | None:
    """ExcelData.to_dict() → 압축 표 텍스트 (행 샘플링 + 상한). 무효 시 None.

    형식:
      [원천 데이터: vac.xlsx]
      # 시트 Sheet1 (12행 × 3열)
      월,사용일수,잔여
      1월,1,14
      ...
      (총 12행 중 12행)
    """
    # sheets 순회 → columns 헤더 + data 행을 CSV류로. row > max_rows면
    # 앞 K행 샘플 + "(총 N행 중 K행)" 표기. 누적 raw_source_max_chars 절단.
```

**kind별 상한** — 기존 non-raw 항목은 불변, raw_source는 별도 budget:

```python
def __init__(self, item_max_chars=4000, total_max_chars=8000, retention=2,
             raw_source_max_chars=6000, raw_source_total_max_chars=8000,
             raw_source_max_rows=200):
    ...

def build_snapshot(self, question, items) -> dict | None:
    # 두 budget 독립 집계:
    #  - kind != raw_source: item_max_chars 절단, total_max_chars 누적 (기존과 동일)
    #  - kind == raw_source: raw_source_max_chars 절단, raw_source_total_max_chars 누적
    # → analysis-data-continuity 동작 불변(raw_source가 기존 항목 budget을 잠식하지 않음)
```

> **결정 근거**: 별도 budget이라 원천이 결과 텍스트를 밀어내지 않고, 기존 검색/General Chat 스냅샷 크기 특성도 그대로다. `select_recent`의 누적 컷도 kind별로 분리 적용.

### 3.4 D4 — `_collect_snapshot` 병합 (`run_agent_use_case.py`)

```python
def _collect_snapshot(self, request, final_messages, analysis_source) -> Optional[dict]:
    if self._snapshot_policy is None:
        return None
    try:
        items = self._snapshot_items(request, final_messages)  # search/excel analysis_output (기존)
        for src in analysis_source or []:
            body = self._snapshot_policy.render_raw_source(src.get("excel") or {})
            if body:
                items.append({"origin": src.get("origin",""), "kind": "raw_source", "content": body})
        return self._snapshot_policy.build_snapshot(request.query, items)
    except Exception as e:
        self._logger.error("analysis snapshot collect failed", exception=e)
        return None
```

- 호출부: `snapshot = self._collect_snapshot(request, state.final_messages, state.analysis_source)`
- 기존 excel 결과 항목(`kind="excel"`, `_snapshot_items`의 excel 분기)은 그대로 유지 → 원천+결과 병행(사용자 결정).
- 재주입(`_inject_snapshot_messages`)은 **무변경** — raw_source도 item이라 `format_search_result`로 감싸져 검색결과 규약 AIMessage가 됨 → context 분기가 데이터로 인식.

### 3.5 D5 — Config (`config.py`)

```python
# Analysis Source Preservation (analysis-source-preservation)
analysis_snapshot_raw_source_max_chars: int = 6000        # raw 항목당 상한(직렬화 후)
analysis_snapshot_raw_source_total_max_chars: int = 8000  # raw 전용 total budget(비-raw와 독립)
analysis_snapshot_raw_source_max_rows: int = 200          # 행 샘플링 임계
```

- `main.py._make_analysis_snapshot_policy`에서 3개 값 주입.
- 토큰 비용: raw_source ≤ 6000자 × retention(2) 재주입 → 최대 ~12k자 추가. 재분석 활성화의 대가로 수용(사용자 목표). Gap 단계 LangSmith 실측 후 재조정.

### 3.6 D6 — 재분석 경로 재사용 + 규칙 개정

- **신규 배선 0**: 후속 턴 재분석은 `_analyze_context`가 재주입된 raw_source(검색결과 규약)를 데이터로 읽어 재집계. 그래프/노드 변경 없음.
- `conversation-memory.md`에 `raw_source` kind 조항 추가(§4).

---

## 4. 규칙 문서 개정 (`docs/rules/conversation-memory.md` 추가)

```markdown
## 분석 원천 데이터 규칙 (analysis-source-preservation 2026-07-07)

- 엑셀 분기 스냅샷은 `analysis_output`(결과 텍스트)과 `raw_source`(파싱 원천 표)를 병행 저장한다.
- raw_source는 압축 표 텍스트로 직렬화하며, 행 초과 시 샘플링 + 총행수 표기.
- raw_source는 비-raw 항목과 **독립 budget**(config `analysis_snapshot_raw_source_*`)으로 상한한다.
- 재주입/재분석은 기존 검색결과 규약·context 분기를 재사용(신규 경로 없음).
- 검색/MCP는 이미 원천 원문을 저장하므로 대상 아님.
```

---

## 5. Test Plan (TDD — Red 우선)

> 구현 시 테스트는 신규 파일로 분리(`*_raw_source.py`)했다 — 기존 파일 확장 대신.

| # | 파일 | 케이스 |
|---|------|--------|
| T1 | `tests/domain/conversation/test_analysis_snapshot_raw_source.py` (신규) | render_raw_source: 헤더+행 직렬화 / row>max 샘플링+총행수 표기 / 빈·무효 dict→None / build_snapshot raw_source 별도 budget(비-raw 불변) / raw 상한 절단 / **select_recent kind별 budget 분리(G1)** |
| T2 | `tests/application/agent_builder/test_analysis_node_raw_source.py` (신규) | 엑셀 분기 → `analysis_source`에 raw_source 항목 반환 / context 분기 → 키 미포함 / 파싱 실패(raw=None) → 항목 없음 |
| T3 | `tests/application/agent_builder/test_run_agent_raw_source.py` (신규) | `_map_chain_end`가 output.analysis_source 캡처 / `_collect_snapshot`이 raw_source+excel 병합 / analysis_source 없으면 기존과 동일 |
| T4 | 〃 | 재주입: raw_source 스냅샷 → `is_search_result` AIMessage(원천 표 텍스트 포함), user-last |
| T5 | `tests/application/agent_builder/test_analysis_node_raw_source.py` (신규) | `_run_excel_analysis` (text, raw) 튜플 반환 / 미파싱 dict({file_path})→raw=None |
| T6 | 회귀 | analysis-data-continuity 기존 테스트 + agent_builder 전체 — raw budget 분리로 비-raw 불변 |

**시나리오 검증(Do 후)**: 턴1 엑셀 "휴가 분석 그래프" → 턴2 "분기별로 다시"(첨부 없음) → 원천 재집계로 분기 차트 생성(원본 재업로드 불필요).

---

## 6. Implementation Order

1. T1 Red → `render_raw_source` + build_snapshot raw budget (D3) + config (D5)
2. T5 Red → `_run_excel_analysis` 튜플 반환 (D2)
3. T2 Red → `analysis_node` analysis_source 방출 (D1 노드부)
4. T3 Red → SupervisorState/`_StreamState`/`_map_chain_end` 캡처 + `_collect_snapshot` 병합 (D1 상태부, D4)
5. T4 Red → 재주입 확인 (기존 경로, assert only)
6. main.py DI(raw config 주입) → T6 회귀 → `conversation-memory.md` 개정

---

## 7. Plan 리스크 해소 매핑

| Plan §5 리스크 | 설계 해소 |
|----------------|-----------|
| 원천 크기 초과 → 재분석 부분화 | `render_raw_source` 행 샘플링 + raw 전용 budget(6000/8000) + 총행수 표기(§3.3) |
| 원천 채널 파급 | charts 상태 채널·`_StreamState` 캡처 선례 미러링, 미주입 시 빈 배열(§3.1) |
| PII 저장 증가 | 세션 스코프 + 크기 상한. 마스킹은 pii-masking-integration 후속(Plan 유지) |
| dict 원천을 str 스키마에 억지 삽입 | 캡처 시점에 압축 표 텍스트로 직렬화 → item content(str) 규약 유지, 재주입/`_analyze_context` 그대로(§3.3/§3.4) |
| "다른 사용자" 오인 | 본 기능은 보유 원천 재분석 — 없는 데이터 확보 아님(Plan/Report 명시) |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-07-07 | Initial draft — 원천 채널(D1)·튜플 반환(D2)·raw budget 직렬화(D3)·병합(D4) 설계 + 사전검증 5건 | 배상규 |
