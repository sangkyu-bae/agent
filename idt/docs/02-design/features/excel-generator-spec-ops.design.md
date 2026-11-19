# excel-generator-spec-ops Design Document

> **Summary**: 시트 계획 JSON에 원천 연산 명세(`ops`)와 컬럼 의미 타입(`column_types`)을 추가한다. 검증 규칙은 domain 정책, 연산 실행은 pandas 실행기, 서식은 생성기 전용 `StyledExcelExporter`가 맡는다. 계획은 JSON 텍스트로 받고 파싱·검증 실패 시 1회 재시도한다.
>
> **Project**: sangplusbot (idt 백엔드)
> **Version**: idt 0.1.x
> **Author**: 배상규
> **Date**: 2026-11-19
> **Status**: Draft
> **Planning Doc**: [excel-generator-spec-ops.plan.md](../../01-plan/features/excel-generator-spec-ops.plan.md)

### Pipeline References

N/A — 백엔드 단독 기능, API·UI·DB 변경 없음.

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 원천 가공(정렬·필터·집계)이 LLM 재작성에 의존해 값 오류·300행 절단이 생기고, 산출물이 서식 없는 평면 표라 업무에 바로 쓰기 어렵다 |
| **WHO** | P2 (KB 운영자 / 에이전트 소유자) — 조립 에이전트로 데이터 수집·정리·보고 업무를 자동화하려는 사용자, 그리고 그 파일을 받는 최종 사용자 |
| **RISK** | 원천 셀 값이 문자열로 들어와 비교·집계가 틀어질 수 있음(타입 강제 변환 필요), LLM이 없는 컬럼·잘못된 연산을 명세할 수 있음(검증+재시도), 기존 REST/Tool 소비자 회귀 |
| **SUCCESS** | ops 경로 결과가 pandas 기준값과 행 단위로 일치, ops 결과는 300행 상한 미적용, 서식 명세 적용 파일이 openpyxl 재로드 시 number_format·freeze_panes·auto_filter 확인, 명세 없는 기존 계획은 출력 동일(무회귀), 실패 시 그래프 비중단 |
| **SCOPE** | 백엔드 단독: domain 스키마·정책(ops·column_types 검증) + ExcelGenerator(계획·실행) + 서식 적용 exporter(opt-in). 수식·차트·양식 채우기·프론트 변경은 스코프 밖 |

---

## 1. Overview

### 1.1 Design Goals

- 원천 가공 요청을 **값을 옮겨 쓰지 않는 경로**(`raw` + `ops`)로 처리한다.
- 컬럼 의미 타입 하나로 표시 형식·값 변환·기본 표 서식이 함께 정해지게 한다.
- 잘못된 계획은 **검증 → 위반 사유 첨부 재시도(1회) → 안내 노옵** 순서로 처리한다.
- 명세가 없는 기존 형태 계획은 **지금과 같은 출력**을 낸다.

### 1.2 Design Principles

- **LLM은 명세, 코드는 값**: LLM 출력은 연산·타입 선언까지만. 셀 값은 원천 또는 LLM `llm` 시트에서만 온다.
- **허용 목록**: 연산·비교자·집계 함수·의미 타입은 domain 상수에 있는 것만 통과. 문자열 평가(`eval`/`query`) 없음.
- **규칙은 domain, 실행은 infrastructure**: 검증·셀 변환·서식 문자열은 순수 Python, pandas/openpyxl은 infra에만.
- **opt-in**: `ops`·`column_types` 모두 선택 필드. 없으면 기존 동작.

### 1.3 Plan 대비 변경 (Checkpoint 3 결정)

| Plan 항목 | Design 결정 | 근거 |
|-----------|------------|------|
| FR-08 구조화 출력 + JSON 폴백 | **JSON 텍스트 수신 유지** + 재시도(FR-09)로 안정성 확보 | `collect_pipeline.py` `CollectArguments` 주석: 자유형 dict는 OpenAI strict structured output이 거부하고 provider마다 처리가 갈림. 계획에는 `rows: list[list[Any]]`·`column_types: dict`가 있어 평탄화 시 이중 파싱만 늘어남 (사용자 확정) |
| In Scope "결과 요약에 ops 적용 여부 반영(필요 범위만)" | **반영하지 않음** | 사용자에게 의미 있는 정보(시트 수·행 수·절단 여부)는 이미 요약에 있음. YAGNI |

---

## 2. Architecture Options

### 2.0 Architecture Comparison

| Criteria | Option A: Minimal | Option B: Clean | Option C: Pragmatic |
|----------|:-:|:-:|:-:|
| **Approach** | generator.py에 ops 실행, 공용 PandasExcelExporter에 서식 분기 | 연산별 VO, 실행기 포트/어댑터, FormatSpec VO, 계획 파서·재시도 정책 클래스 | domain 정책 1 + infra 실행기 1 + 생성기 전용 exporter 1 |
| **New Files** | 0 | 7 | 3 (+테스트 3) |
| **Modified Files** | 4 | 5 | 5 |
| **Complexity** | Low | High | Medium |
| **Maintainability** | Low (generator 비대) | High | High |
| **Effort** | Low | High | Medium |
| **Risk** | 공용 exporter 회귀 (REST·Tool) | 과한 추상화 (CLAUDE.md §6) | Low |

**Selected**: Option C — **Rationale**: 공용 exporter를 건드리지 않아 REST·Tool 무회귀가 구조적으로 보장되고, 규칙(domain)과 실행(infra)이 레이어 책임대로 갈린다. 포트/어댑터는 구현체가 하나뿐이라 두지 않는다.

### 2.1 Component Diagram

```
workflow_compiler._create_excel_generator_node   (변경 없음)
        │ generate(...)
        ▼
ExcelGenerator (infrastructure/excel_generator/generator.py)  ◀ 수정
  ├─ _build_catalog ──── RawSourceRef(+column_dtypes)          ◀ domain/schemas.py 수정
  ├─ _plan_sheets ────── LLM 1회 (+재시도 1회)
  │     └─ validate_plan(items, catalog_columns) ─────────────▶ domain/policies.py 수정
  │              └─ validate_ops / validate_column_types ─────▶ domain/spec_policies.py 신규
  ├─ _materialize
  │     └─ raw + ops → apply_ops(columns, rows, ops) ─────────▶ infrastructure/excel_generator/ops_executor.py 신규
  └─ _export_and_save
        └─ StyledExcelExporter.export(request) ───────────────▶ infrastructure/excel_export/styled_excel_exporter.py 신규
              └─ coerce_cell / NUMBER_FORMATS ────────────────▶ domain/spec_policies.py

PandasExcelExporter / ExcelExportTool / REST /excel-export     (변경 없음)
```

### 2.2 Data Flow

```
분석 원천·첨부 → 카탈로그(컬럼·행수·dtype·샘플 5행)
  → LLM 시트 계획 JSON
  → parse → validate ──(위반)──▶ 위반 사유 첨부 재요청 1회 → parse → validate ──(위반)──▶ ExcelGenerateError(안내 노옵)
  → materialize
       raw (ops 없음) : 원천 전량 복사                        (기존)
       raw + ops      : pandas 연산 → 결과 전량 (Excel 행 한도에서만 절단)
       llm            : LLM rows (300행 상한 절단)              (기존)
  → ExcelSheetData(+column_types)
  → StyledExcelExporter: column_types 있는 시트만 값 변환 + 서식
  → AgentAttachmentStore 저장 → 다운로드 링크
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `spec_policies.py` (domain) | 표준 라이브러리만 (`datetime`, `re`) | ops·타입 검증, 셀 변환, 서식 문자열 |
| `policies.py` (domain) | `spec_policies.py` | `validate_plan`에서 ops·column_types 검증 위임 |
| `ops_executor.py` (infra) | pandas, `spec_policies` | 검증된 ops 실행 |
| `styled_excel_exporter.py` (infra) | pandas, openpyxl, `spec_policies`, `ExcelExporterInterface` | 값 변환·서식 적용 |
| `generator.py` (infra) | 위 둘 | 흐름 |
| `api/main.py` | `StyledExcelExporter` | DI: 생성기 exporter 교체 (1줄) |

---

## 3. Data Model

### 3.1 시트 계획 JSON (LLM 출력 계약)

```json
{
  "filename": "연체현황.xlsx",
  "sheets": [
    {
      "source": "raw:0",
      "sheet_name": "연체 상위 20",
      "ops": [
        {"op": "filter", "col": "연체일수", "cmp": ">", "value": 0},
        {"op": "sort", "by": [{"col": "연체일수", "desc": true}]},
        {"op": "top", "n": 20},
        {"op": "select", "columns": ["고객명", "지점", "잔액", "연체일수"]}
      ],
      "column_types": {"잔액": "currency", "연체일수": "integer"}
    },
    {
      "source": "raw:0",
      "sheet_name": "지점별 합계",
      "ops": [
        {"op": "groupby", "by": ["지점"],
         "agg": [{"col": "잔액", "fn": "sum", "as": "잔액 합계"},
                 {"col": "고객명", "fn": "count", "as": "건수"}]},
        {"op": "sort", "by": [{"col": "잔액 합계", "desc": true}]}
      ],
      "column_types": {"잔액 합계": "currency", "건수": "integer"}
    },
    {
      "source": "llm",
      "sheet_name": "요약",
      "columns": ["항목", "내용"],
      "rows": [["기준일", "2026-11-19"]],
      "column_types": {"기준일": "date"}
    }
  ]
}
```

### 3.2 ops 명세

| op | 필드 | 의미 | 결과 컬럼 집합 |
|----|------|------|---------------|
| `select` | `columns: list[str]` (1개 이상) | 컬럼 선택·순서 지정 | `columns` |
| `filter` | `col`, `cmp`, `value` | 행 조건. 여러 filter = AND (순차 적용) | 변화 없음 |
| `sort` | `by: [{col, desc?=false}]` (1개 이상) | 다중 키 정렬 | 변화 없음 |
| `top` | `n: int` (1 이상) | 앞에서 N행 | 변화 없음 |
| `groupby` | `by: list[str]` (1개 이상), `agg: [{col, fn, as?}]` (1개 이상) | 그룹 집계 | `by + [as 또는 "{col}_{fn}"]` |

- `cmp` 허용 목록: `==`, `!=`, `>`, `>=`, `<`, `<=`, `contains`, `in`
  - `in`: `value`는 list. `contains`: `value`는 str (부분 문자열, 대소문자 구분).
- `fn` 허용 목록: `sum`, `mean`, `count`, `min`, `max`
- 시트당 ops 최대 `MAX_OPS_PER_SHEET = 10`
- (Act-1) `select.columns` 중복 금지, `sort.by[].desc`는 bool, `==`·`!=`·크기 비교의 `value`는 null 불가
- OR 조건·join·피벗은 지원하지 않음 (Plan Out of Scope)

### 3.3 column_types 의미 타입 → 서식

| type | 값 변환 (`coerce_cell`) | number_format |
|------|------------------------|---------------|
| `text` | 변환 없음 (문자열화 안 함) | 기본(General) |
| `integer` | `"1,234"`·`"₩1,234"`·`"1,234원"` → 1234 (소수면 반올림 없이 float 유지) | `#,##0` |
| `number` | 위와 같은 정리 후 float | `#,##0.00` |
| `currency` | `integer`와 동일 | `#,##0` |
| `percent` | `"12.5%"` → 0.125. 숫자 값은 **비율로 간주해 그대로** | `0.0%` |
| `date` | `"YYYY-MM-DD"`, `"YYYY.MM.DD"`, `"YYYY/MM/DD"`, ISO datetime, `date`/`datetime` 객체 → `datetime` | `yyyy-mm-dd` |

- 변환 실패 셀은 **원값 그대로** 둔다 (오류로 처리하지 않음). `None`/빈 문자열은 `None`.
- 숫자 정리 규칙: 앞뒤 공백, 천 단위 `,`, 통화 기호 `₩`·`$`, 접미 `원` 제거 후 `float()`. 괄호 음수 `(1,234)`는 지원하지 않음(원값 유지).
- `percent`의 숫자 값 해석은 위험 항목 (§6.3, Plan Risk) — 프롬프트에 "샘플 값이 0~1 비율일 때만 percent" 규칙을 둔다.

### 3.4 도메인 스키마 변경

```python
# domain/excel_generator/schemas.py
@dataclass(frozen=True)
class RawSourceRef:
    catalog_idx: int
    origin: str
    sheet_name: str
    columns: list[str]
    row_count: int
    column_dtypes: dict[str, str] = field(default_factory=dict)  # 신규: SheetData.dtypes

@dataclass(frozen=True)
class SheetPlanItem:
    source: str
    sheet_name: str
    columns: list[str] | None = None
    rows: list[list] | None = None
    ops: list[dict] | None = None              # 신규: raw 시트 전용
    column_types: dict[str, str] | None = None # 신규: raw·llm 공통
```

```python
# domain/excel_export/schemas.py
class ExcelSheetData(BaseModel):
    sheet_name: str = "Sheet1"
    columns: list[str]
    rows: list[list[Any]] = []
    column_types: dict[str, str] | None = None  # 신규 (기본 None → 기존 소비자 무영향)
```

### 3.5 domain 정책 (`domain/excel_generator/spec_policies.py`, 신규)

```python
ALLOWED_OPS = frozenset({"select", "filter", "sort", "top", "groupby"})
ALLOWED_CMPS = frozenset({"==", "!=", ">", ">=", "<", "<=", "contains", "in"})
ALLOWED_AGG_FNS = frozenset({"sum", "mean", "count", "min", "max"})
SEMANTIC_TYPES = frozenset({"text", "integer", "number", "currency", "percent", "date"})
NUMBER_FORMATS: dict[str, str]          # §3.3 표
MAX_OPS_PER_SHEET = 10
EXCEL_MAX_DATA_ROWS = 1_048_575         # 헤더 1행 제외

def validate_ops(ops: list, columns: list[str]) -> tuple[list[str], list[str]]:
    """(위반 사유 목록, 연산 후 결과 컬럼). 컬럼 집합을 연산 순서대로 추적한다."""

def validate_column_types(column_types: dict, columns: list[str]) -> list[str]:
    """허용 타입·존재 컬럼만 통과."""

def agg_output_name(agg: dict) -> str:
    """as 우선, 없으면 '{col}_{fn}'."""

def coerce_cell(value, semantic_type: str):
    """§3.3 값 변환. 실패 시 원값."""

def clean_numeric_text(text: str) -> float | None:
    """ops 실행기·coerce_cell 공용 숫자 정리 규칙."""
```

`policies.validate_plan` 시그니처:

```python
def validate_plan(
    items: list[SheetPlanItem],
    catalog_size: int,
    catalog_columns: list[list[str]] | None = None,  # 신규
) -> list[str]
```

- `catalog_columns`가 None인데 raw 시트에 `ops`·`column_types`가 있으면 위반: `"원천 컬럼 정보 없이 ops/column_types를 검증할 수 없습니다"`. 생성기는 항상 카탈로그 컬럼을 넘긴다.

- `catalog_columns`가 주어지면 raw 시트의 ops·column_types를 원천 컬럼 기준으로 검증한다.
- `ops`가 `llm` 시트에 있으면 위반: `"llm 시트 '<이름>'에는 ops를 쓸 수 없습니다"`.
- `column_types` 검증 기준 컬럼: raw+ops는 ops 결과 컬럼, raw는 원천 컬럼, llm은 `columns`.
- 기존 호출(`validate_plan(items, n)`)과 기존 테스트는 그대로 통과한다 (ops·column_types 없는 계획).

---

## 4. API Specification

N/A — 엔드포인트 변경 없음. 생성 노드의 다운로드 링크 응답 형식도 그대로다.

---

## 5. UI/UX Design

N/A — 프론트 변경 없음. 채팅 미리보기(`preview_reader.py`, `data_only=True`)는 숫자·날짜 셀을 `serialize_cell`로 문자열화하므로 동작한다. 날짜 셀은 `2026-11-19T00:00:00`처럼 보일 수 있다 (§6.3 참고, 이번 범위에서 수정하지 않음).

---

## 6. Error Handling

### 6.1 실패 분류

| # | 상황 | 처리 | LLM 호출 |
|---|------|------|:--:|
| 1 | 1차 응답 JSON 파싱 실패 | 위반 사유 `"JSON 파싱 실패"`로 재요청 | 2 |
| 2 | 1차 계획 `validate_plan` 위반 | 위반 사유 목록으로 재요청 | 2 |
| 3 | 2차도 1·2번 실패 | `ExcelGenerateError("시트 계획이 유효하지 않습니다: …")` → 노드 안내 노옵 | 2 |
| 4 | 계획이 비어 있음 (`sheets: []`) | 재시도 없이 `NoExcelDataError` (데이터 없음은 정상 판단) | 1 |
| 5 | `llm.ainvoke` 예외 | 재시도 없이 `ExcelGenerateError` (기존 동작) | 1 |
| 6 | ops 실행 중 예외 (검증 통과 후 런타임) | `ExcelGenerateError(f"시트 '<이름>' 연산 실패: …")` | — |
| 7 | 서식 적용 중 예외 | 해당 시트는 값만 기록하고 `warning` 로그 (파일 생성은 계속) | — |
| 8 | 변환·저장 실패 | 기존과 동일 (`RuntimeError`/`OSError` → `ExcelGenerateError`) | — |

### 6.2 재요청 메시지

```
messages = [system, user,
            {"role": "assistant", "content": <1차 응답 원문 앞 4000자>},
            {"role": "user", "content": "위 계획에 다음 문제가 있습니다:\n- …\n문제를 고친 시트 계획 JSON만 다시 출력하라."}]
config.run_name = "excel_generator_plan_retry"
```

### 6.3 런타임 의미 규칙 (ops 실행기)

| 연산 | 타입 처리 |
|------|----------|
| `filter` 비교 `>`,`>=`,`<`,`<=` | `value`가 숫자 또는 숫자 문자열(`"1000"`) → 컬럼을 `clean_numeric_text` 기준 숫자로 변환. `value`가 날짜 문자열(`YYYY-MM-DD` 계열) → 컬럼을 날짜로 변환. 변환 실패(NaN/NaT) 행은 **제외**. 그 외 → 문자열 비교 |
| `filter` `==`,`!=` | `value`가 **숫자 타입**이면 숫자 비교(변환 실패 행: `==`는 제외, `!=`는 포함). 문자열이면(숫자처럼 보여도) `str(cell) == str(value)` — 앞자리 0 코드(`"001"`) 보존 (Act-1 M-1) |
| `filter` `contains` / `in` | 문자열 포함 / `str(cell)`이 value 문자열 집합에 있거나, value에 숫자 타입 원소가 있으면 셀 숫자 해석값이 그 숫자 집합에 있음 (float 셀 `5.0` ∈ `[5]`, Act-1 I-1) |
| `sort` | 컬럼의 non-null 값이 **전부** 숫자로 변환되면 숫자 정렬, 아니면 문자열 정렬. null은 항상 뒤 |
| `groupby` `sum`/`mean`/`min`/`max` | 대상 컬럼을 숫자로 변환 후 집계 (변환 실패 값은 제외). `count`는 non-null 개수 |
| groupby 키 | 원값 그대로 (`dropna=False`, null 그룹 유지). 그룹 순서는 원천 등장 순서 (`sort=False` — 키에 숫자·문자 혼합 시 정렬 오류 방지, 순서가 필요하면 뒤에 `sort`) |
| groupby `sum` 빈 그룹 | 숫자로 해석되는 값이 하나도 없는 그룹은 0이 아니라 빈 값 (`min_count=1`, 데이터 없음 ≠ 0) |
| 결과 행 > `EXCEL_MAX_DATA_ROWS` | 절단 + `truncated=True` |

- 결과 셀은 **원천 값 그대로** 기록한다. 숫자 변환은 비교·정렬·집계 판단에만 쓰고, 셀 값 변환은 `column_types`가 있을 때 exporter가 한다.
- 집계 결과(sum 등)는 float. `column_types`로 `integer`/`currency`를 주면 서식으로 표시한다.

### 6.4 로깅

- 재시도: `logger.warning("ExcelGenerator plan retry", request_id, violations=[...])`
- ops 실패: `logger.error("ExcelGenerator ops failed", request_id, sheet_name, exception=e)`
- 서식 실패: `logger.warning("StyledExcelExporter format skipped", request_id, sheet_name, exception=e)`
- 완료 로그에 `retried: bool`, `ops_sheet_count: int` 추가

---

## 7. Security Considerations

- [x] 문자열 평가 없음: `DataFrame.query`·`eval`·`exec` 사용 금지. 비교는 pandas 비교 연산자 메서드로만.
- [x] 허용 목록 밖 `op`/`cmp`/`fn`/`type`은 domain 검증에서 거부.
- [x] 자원 상한: 시트 10개(기존), 시트당 ops 10개, 결과 행 Excel 한도.
- [x] 컬럼명은 원천 컬럼 집합으로 검증되므로 임의 속성 접근 불가.
- [x] 파일명 처리·저장 경로는 기존 `_safe_filename` + store 새니타이즈 유지.

---

## 8. Test Plan

L1~L3(API·UI·E2E)는 해당 없음. 전부 pytest 단위·통합 테스트로 검증한다.

### 8.1 Test Scope

| Type | Target | Tool | Phase |
|------|--------|------|-------|
| Unit (domain) | `spec_policies` 검증·변환, `validate_plan` 확장 | pytest | Do |
| Unit (infra) | `ops_executor`, `StyledExcelExporter` | pytest + pandas/openpyxl 재로드 | Do |
| Integration | `ExcelGenerator.generate` (FakeLLM) | pytest-asyncio | Do |
| Regression | 기존 excel_generator·excel_export·excel_preview 테스트 | pytest | Do/Check |

### 8.2 domain 테스트 (`tests/domain/excel_generator/test_spec_policies.py`, `test_policies.py` 보강)

| # | 케이스 | 기대 |
|---|--------|------|
| D1 | 허용 목록 밖 op `"eval"` | 위반 |
| D2 | filter의 없는 컬럼 | 위반 (컬럼명 포함 사유) |
| D3 | select 후 제외된 컬럼으로 sort | 위반 |
| D4 | groupby 후 결과 컬럼(`as`)으로 sort | 통과 |
| D5 | groupby `as` 생략 → `잔액_sum` 으로 참조 | 통과 |
| D6 | `top` n=0 / 문자열 | 위반 |
| D7 | `in`의 value가 list 아님 | 위반 |
| D8 | ops 11개 | 위반 |
| D9 | llm 시트에 ops | 위반 |
| D10 | column_types 허용 밖 타입 / 없는 컬럼 | 위반 |
| D11 | `coerce_cell("1,234원","currency") == 1234`, `("₩-5","integer") == -5` | 일치 |
| D12 | `coerce_cell("12.5%","percent") == 0.125`, `(0.3,"percent") == 0.3` | 일치 |
| D13 | `coerce_cell("2026.11.19","date")` → datetime(2026,11,19) | 일치 |
| D14 | 변환 실패 `coerce_cell("N/A","number") == "N/A"` | 원값 |
| D15 | 기존 형태 계획 `validate_plan(items, n)` | 기존과 동일 결과 |

### 8.3 ops 실행기 테스트 (`tests/infrastructure/excel_generator/test_ops_executor.py`)

| # | 케이스 | 기대 |
|---|--------|------|
| E1 | 문자열 숫자(`"1,200"`)·숫자 혼합 컬럼 `> 1000` filter | 숫자 기준 결과, 셀 값은 원값 |
| E2 | 변환 불가 셀(`"-"`)이 있는 컬럼 `>` filter | 해당 행 제외 |
| E3 | 다중 키 sort (desc + asc) | pandas 기준과 일치 |
| E4 | 문자열 섞인 컬럼 sort | 문자열 정렬, null 뒤 |
| E5 | groupby sum/mean/count/min/max | 기준 DataFrame과 값 일치 (SC-2) |
| E6 | 1,000행 원천에서 filter → 500행 결과 | 500행 전부 (300 상한 미적용, SC-1) |
| E7 | 날짜 문자열 `>= "2026-01-01"` filter | 날짜 비교 |
| E8 | `in`, `contains`, `!=` | 기대 행 |

### 8.4 exporter 테스트 (`tests/infrastructure/excel_export/test_styled_excel_exporter.py`)

| # | 케이스 | 기대 |
|---|--------|------|
| X1 | column_types 없는 요청 | `PandasExcelExporter`와 셀 값·시트 구성 동일, 서식(freeze·filter) 없음 (SC-4) |
| X2 | currency 컬럼 | 숫자 셀, `number_format == "#,##0"` |
| X3 | percent / date | `0.0%` / `yyyy-mm-dd`, datetime 셀 |
| X4 | 서식 시트 | `ws.freeze_panes == "A2"`, `ws.auto_filter.ref` = 데이터 범위, 헤더 bold (SC-3) |
| X5 | 열 너비 | 한글 긴 값 컬럼 > 짧은 컬럼, 상한 50 |
| X6 | 서식 적용 예외(강제 주입) | 값만 기록된 파일 생성 + warning |
| X7 | `ExcelPreviewReader`로 재로드 | 예외 없이 숫자·날짜 문자열화 |

### 8.5 생성기 통합 테스트 (`tests/infrastructure/excel_generator/test_generator.py` 보강)

| # | 케이스 | 기대 |
|---|--------|------|
| G1 | raw+ops 계획 (1,000행 → filter 500행) | 500행 저장, `truncated=False`, LLM 1회 (SC-1) |
| G2 | 1차 응답 없는 컬럼 참조 → 2차 정상 | 성공, LLM 2회, 2차 메시지에 위반 사유 포함 (SC-5) |
| G3 | 1차 비JSON → 2차 정상 | 성공, LLM 2회 |
| G4 | 2회 모두 위반 | `ExcelGenerateError`, LLM 2회 (SC-5) |
| G5 | 빈 계획 | `NoExcelDataError`, LLM 1회 (재시도 없음) |
| G6 | 카탈로그 프롬프트에 dtype 노출 | 프롬프트에 `int64` 등 포함 |
| G7 | column_types 계획 | 저장 파일 서식 확인 |
| G8 | 기존 테스트 전부 | 통과 (SC-4) |

### 8.6 Seed Data

테스트 내 생성 (원천 dict 픽스처). DB 시드 불필요.

---

## 9. Clean Architecture

### 9.1 This Feature's Layer Assignment

| Component | Layer | Location |
|-----------|-------|----------|
| `SheetPlanItem`, `RawSourceRef` 확장 | Domain | `src/domain/excel_generator/schemas.py` |
| ops·타입 검증, 셀 변환, 서식 표 | Domain | `src/domain/excel_generator/spec_policies.py` (신규) |
| `validate_plan` 확장 | Domain | `src/domain/excel_generator/policies.py` |
| `ExcelSheetData.column_types` | Domain | `src/domain/excel_export/schemas.py` |
| ops 실행기 | Infrastructure | `src/infrastructure/excel_generator/ops_executor.py` (신규) |
| 서식 exporter | Infrastructure | `src/infrastructure/excel_export/styled_excel_exporter.py` (신규) |
| 생성기 흐름 | Infrastructure | `src/infrastructure/excel_generator/generator.py` |
| DI | Interfaces | `src/api/main.py` (`_EgExporter` → `StyledExcelExporter`) |

### 9.2 Import Rules

- `domain/excel_generator/*` → pandas·openpyxl·LangChain import 금지 (`verify-architecture`).
- `domain/excel_generator/spec_policies.py`가 `domain/excel_export`를 참조하지 않는다 (역방향도 없음). exporter가 둘 다 import.

---

## 10. Coding Convention Reference

| Item | Convention Applied |
|------|-------------------|
| 함수 길이 | 40줄 이하. ops 실행기는 op별 함수 분리 (`_apply_filter` 등, dispatch dict) |
| 중첩 | if 2단계 이하. op 분기는 dispatch dict |
| 상수 | 허용 목록·상한은 domain 상수. 환경변수 추가 없음 |
| 로깅 | `LoggerInterface`, `request_id` 필수, 예외는 `exception=` |
| 주석 | `# Design Ref: §x.y` / `# Plan SC-n` |
| 테스트 | TDD (Red → Green → Refactor), `uv run python -m pytest` |

---

## 11. Implementation Guide

### 11.1 File Structure

```
src/domain/excel_generator/
  schemas.py            (수정) RawSourceRef.column_dtypes, SheetPlanItem.ops/column_types
  policies.py           (수정) validate_plan(…, catalog_columns)
  spec_policies.py      (신규) 허용 목록·validate_ops·validate_column_types·coerce_cell·NUMBER_FORMATS
src/domain/excel_export/
  schemas.py            (수정) ExcelSheetData.column_types
src/infrastructure/excel_generator/
  ops_executor.py       (신규) apply_ops(columns, rows, ops) -> (columns, rows, truncated)
  generator.py          (수정) 카탈로그 dtype, 프롬프트 개정, 파싱 확장, 재시도, ops 실행, column_types 전달
src/infrastructure/excel_export/
  styled_excel_exporter.py (신규) StyledExcelExporter(ExcelExporterInterface)
src/api/main.py         (수정) 생성기 exporter 교체

tests/domain/excel_generator/test_spec_policies.py          (신규)
tests/domain/excel_generator/test_policies.py               (보강)
tests/infrastructure/excel_generator/test_ops_executor.py   (신규)
tests/infrastructure/excel_generator/test_generator.py      (보강)
tests/infrastructure/excel_export/test_styled_excel_exporter.py (신규)
```

### 11.2 Implementation Order

1. [ ] domain: `spec_policies.py` + 테스트 (D1~D14)
2. [ ] domain: `schemas.py`·`policies.py` 확장 + 테스트 (D15, 기존 회귀)
3. [ ] infra: `ops_executor.py` + 테스트 (E1~E8)
4. [ ] infra: `StyledExcelExporter` + `ExcelSheetData.column_types` + 테스트 (X1~X7)
5. [ ] infra: `generator.py` 프롬프트·파싱·재시도·ops·서식 전달 + 테스트 (G1~G8)
6. [ ] DI 교체 (`api/main.py`) + 회귀 (`tests/domain/excel_generator`, `tests/infrastructure/excel_generator`, `tests/infrastructure/excel_export`, `tests/infrastructure/excel`, excel_preview, workflow_compiler excel 노드 테스트)
7. [ ] `verify-architecture`, `verify-logging`, `verify-tdd`

### 11.3 계획 프롬프트 개정안 (`_PLAN_GUIDELINES`)

```
규칙:
1. 출력은 JSON 하나: {"filename": "<파일명>.xlsx", "sheets": [...]}
2. [원천 카탈로그]의 데이터를 담을 시트는 {"source": "raw:<번호>", "sheet_name": "..."} 로 참조만 하라.
   카탈로그 데이터를 직접 옮겨 적지 마라.
3. 원천 데이터의 일부만·정렬·상위 N·집계가 필요하면 raw 시트에 "ops"를 붙여라.
   ops: select{columns} / filter{col,cmp,value} (cmp: == != > >= < <= contains in) /
        sort{by:[{col,desc}]} / top{n} / groupby{by:[...], agg:[{col,fn,as}]} (fn: sum mean count min max)
   ops는 적힌 순서대로 실행된다. 여러 filter는 AND다.
4. 검색 결과·대화 등 비정형 재료에서 표를 만들 때만
   {"source": "llm", "sheet_name": "...", "columns": [...], "rows": [[...]]} 를 사용하라.
5. 컬럼 표시 형식이 필요하면 "column_types": {"컬럼명": "text|integer|number|currency|percent|date"} 를 붙여라.
   percent는 값이 0~1 비율일 때만 쓴다.
6. 정리할 데이터가 전혀 없으면 {"filename": "", "sheets": []} 를 출력하라.
7. JSON 외 다른 텍스트를 출력하지 마라.
```

카탈로그 행 형식: `0. (origin=…) 시트 '…' — 컬럼: [...], 타입: {잔액: int64, …}, 행수: N` + 샘플 5행.

### 11.4 Session Guide

#### Module Map

| Module | Scope Key | Description | Estimated Turns |
|--------|-----------|-------------|:---------------:|
| domain 규칙 | `module-1` | `spec_policies.py`, `schemas.py`, `policies.py` 확장 + 테스트 | 15-20 |
| ops 실행기 | `module-2` | `ops_executor.py` + 테스트 | 15-20 |
| 서식 exporter | `module-3` | `StyledExcelExporter`, `ExcelSheetData.column_types` + 테스트 | 15-20 |
| 생성기 통합 | `module-4` | `generator.py` 재시도·프롬프트·ops·서식 전달, DI, 회귀 | 20-25 |

#### Recommended Session Plan

| Session | Phase | Scope | Turns |
|---------|-------|-------|:-----:|
| Session 1 | Plan + Design | 전체 | 완료 |
| Session 2 | Do | `--scope module-1,module-2` | 30-40 |
| Session 3 | Do | `--scope module-3,module-4` | 35-45 |
| Session 4 | Check + Report | 전체 | 20-30 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-11-19 | Initial draft — Option C 선택, 계획 수신은 JSON 텍스트 + 1회 재시도 | 배상규 |
| 0.2 | 2026-11-19 | Act-1: §6.3 비교 규칙(in 숫자 일치, ==는 숫자 타입만), §3.2 검증 보강 | 배상규 |
