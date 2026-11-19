# excel-generator-spec-ops Analysis Report

> **Analysis Type**: Gap Analysis (정적 비교 + pytest 런타임)
>
> **Project**: sangplusbot (idt 백엔드)
> **Version**: idt 0.1.x
> **Analyst**: 배상규 (gap-detector 정적 분석 + 직접 재현·diff 확인)
> **Date**: 2026-11-19
> **Design Doc**: [excel-generator-spec-ops.design.md](../02-design/features/excel-generator-spec-ops.design.md)

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

## Strategic Alignment Check

PRD 없음 (Plan부터 시작한 사이클).

| 항목 | 상태 | 근거 |
|------|:---:|------|
| WHY — LLM 재작성 없이 원천 가공 | ✅ | raw+ops 경로가 pandas로 실행, 결과 셀은 원천 값 (`ops_executor.py`, G1) |
| WHY — 업무용 서식 | ✅ | `StyledExcelExporter` (X2~X4, G7) |
| RISK — 문자열 셀 비교·집계 | ⚠️ | 숫자 문자열 처리는 동작(E1·E2·E5). 단 `in` 비교가 float 셀을 놓침 (I-1) |
| RISK — 잘못된 명세 | ✅ | domain 검증 + 위반 사유 첨부 1회 재요청 (G2~G4) |
| RISK — 기존 소비자 회귀 | ✅ | `git diff origin/master --stat`에 `pandas_excel_exporter.py`·`excel_export_tool.py`·REST 라우터 없음, X1 값 동일 |

### Success Criteria Status

| # | Criteria (from Plan) | Status | Evidence |
|---|---------------------|:------:|----------|
| SC-1 | raw+ops 결과가 원천 값 그대로, 300행 넘는 결과 포함 | ✅ | G1 `test_generator.py:306` (500행, `truncated=False`, LLM 1회), E6 |
| SC-2 | groupby+agg가 pandas 기준값과 일치 | ✅ | E5 `test_ops_executor.py:117`, 기준 비교 `:138` |
| SC-3 | number_format·숫자 셀·freeze `A2`·auto_filter 확인 | ✅ | X2~X4 `test_styled_excel_exporter.py:74-99`, G7 |
| SC-4 | 명세 없는 계획 무회귀, REST·Tool 출력 불변 | ✅ | X1, 기존 생성기 테스트 전부 통과, diff에 공용 exporter 없음 |
| SC-5 | 1회 재시도 복구, 2회 실패 시 안내 노옵, LLM ≤ 2 | ✅ | G2·G3·G4·G5 |
| SC-6 | 허용 목록 밖 연산·없는 컬럼·llm 시트 ops 거부 | ✅ | D1·D2·D9 |

**Success Rate**: 6/6

### Decision Record Verification

| Source | Decision | Followed? | Deviation |
|--------|----------|:---------:|-----------|
| [Plan] | 범위 ①연산+②서식+⑥안정성 | ✅ | — |
| [Plan] | 기본 연산 + groupby, join 제외 | ✅ | — |
| [Plan] | 구조화 필터, query/eval 금지 | ✅ | 엑셀 관련 src에 `.query(`/`eval(`/`exec(` 없음 |
| [Plan] | 서식은 생성 노드 opt-in | ✅ | DI 1곳만 교체 (`main.py:3199-3207`) |
| [Design] | Option C (domain 정책 1 + 실행기 1 + exporter 1) | ✅ | Design에 없던 `parse_date_text` 보조 함수 추가 (공개 함수, 실행기·변환 공용) |
| [Design] | JSON 텍스트 + 1회 재시도 | ✅ | — |

---

## 1. Analysis Overview

- **Design Document**: `docs/02-design/features/excel-generator-spec-ops.design.md`
- **Implementation Path**: `src/domain/excel_generator/`, `src/domain/excel_export/schemas.py`, `src/infrastructure/excel_generator/`, `src/infrastructure/excel_export/styled_excel_exporter.py`, `src/api/main.py`
- **Worktree**: `wt/excel-generator-spec-ops` (`feature/excel-generator-spec-ops`, 미커밋)
- **Analysis Date**: 2026-11-19

---

## 2. Gap Analysis

### 2.1 API Endpoints

N/A — 엔드포인트 변경 없음.

### 2.2 Data Model

| Field | Design | Impl | Status |
|-------|--------|------|:---:|
| `RawSourceRef.column_dtypes` | `dict[str,str]`, 기본 `{}` | `schemas.py:22` | ✅ |
| `SheetPlanItem.ops` | `list[dict] \| None` | `schemas.py:34` | ✅ |
| `SheetPlanItem.column_types` | `dict[str,str] \| None` | `schemas.py:35` | ✅ |
| `ExcelSheetData.column_types` | `dict[str,str] \| None = None` | `excel_export/schemas.py:18` | ✅ |

### 2.3 Component Structure

| Design Component | Implementation | Status |
|------------------|----------------|:---:|
| `spec_policies.py` (허용 목록·검증·변환·서식 표) | `src/domain/excel_generator/spec_policies.py` | ✅ |
| `validate_plan(…, catalog_columns)` | `policies.py:29-33` | ✅ |
| `apply_ops` | `ops_executor.py:27` | ✅ |
| `StyledExcelExporter` | `styled_excel_exporter.py:32` | ✅ |
| 생성기 재시도·ops·dtype·프롬프트 | `generator.py` | ✅ |
| DI 교체 | `main.py:3199-3207` | ✅ |

### 2.4 Functional Depth

| 영역 | 결과 |
|------|------|
| ops 계약 §3.2 | 일치 — 5개 연산·비교자·집계 허용 목록, 상한 10, 연산 순서대로 컬럼 추적, groupby 결과명 중복 거부 |
| 셀 변환 §3.3 | 일치 — 통화·천 단위 정리, `%` 문자열만 ÷100, 빈 값 None, 실패 시 원값 |
| 런타임 의미 §6.3 | **부분** — `in`이 문자열 일치만 함 (I-1). 숫자형 문자열 value 처리 확장 (M-1) |
| 오류 처리 §6.1 #1~#8 | 일치 |
| 재요청 메시지 §6.2 | 일치 (assistant 4000자 + 위반 목록, run_name `excel_generator_plan_retry`) |
| 로깅 §6.4 | 일치 (`retried`, `ops_sheet_count` 포함) |
| 프롬프트 §11.3 | 일치 (규칙 1~7, 카탈로그 dtype) |

Shallow 파일 없음.

### 2.6 Contract Verification

| # | 계약 | Status | 근거 |
|---|------|:---:|------|
| 1 | `validate_plan` 하위 호환 | ✅ | D15 `test_policies.py:126` |
| 2 | `ExcelSheetData.column_types` 기본 None | ✅ | `test_schemas.py:41-49` |
| 3 | `ExcelGenerator.generate` 시그니처 불변 | ✅ | `generator.py:84-95`, 노드 호출부 변경 없음 |
| 4 | `PandasExcelExporter` 무변경 | ✅ | `git diff origin/master --stat`에 없음 |
| 5 | REST·`ExcelExportTool` 경로 무변경 | ✅ | 같은 diff에 없음, `main.py:5770`·`excel_export_tool.py:88` 그대로 |

**Contract Match Rate**: 5/5 = 100%

### 2.7 Runtime Verification

L1(HTTP)·L2(UI)·L3(E2E)는 이 기능에 해당하지 않습니다 (엔드포인트·화면 변경 없음). 대신 pytest 묶음을 런타임 검증으로 씁니다.

| 묶음 | 결과 |
|------|------|
| excel_generator·excel_export (domain/infra), infra/excel, 컴파일러 엑셀 노드, 미리보기 API·DI 연결, excel_preview | **273 passed** (`OPENAI_API_KEY=sk-dummy`, 미리보기 API 테스트가 `main.py` import 시 키 필요) |
| Design 테스트 계획 대응 | D1–D15, E1–E8, X1–X7, G1–G8 **38/38** |

**Runtime Match Rate**: 100%

### 2.8 Match Rate Summary

```
┌─────────────────────────────────────────────┐
│  Structural Match Rate:  100%   (22/22)      │
│  Functional Match Rate:  97.6%  (40/41)      │
│  Contract Match Rate:    100%   (5/5)        │
│  Runtime Match Rate:     100%   (pytest 273) │
│  ─────────────────────────────────────────── │
│  Overall = 15 + 24.4 + 25 + 35 = 99.4%       │
└─────────────────────────────────────────────┘
```

---

## 3. Findings

### Critical

없음.

### Important

**I-1. `in` 필터가 원값 일치 없이 문자열 일치만 한다** (Design §6.3 "원값 또는 문자열 일치"와 다름)

- 위치: `src/infrastructure/excel_generator/ops_executor.py:83-85`
- 재현: `apply_ops(['k'], [[5.0],[12.0],[3.0]], [{'op':'filter','col':'k','cmp':'in','value':[5,12]}])` → 결과 `[]`. 같은 데이터에서 `== 5`는 `[[5.0]]`.
- 영향: `PandasExcelParser`는 빈칸이 섞인 정수 컬럼을 float64로 읽습니다. 그래서 첨부 엑셀에서 "지점코드 in [101, 102]" 같은 조건이 오류 없이 빈 시트를 만듭니다.
- 테스트 공백: `test_in_matches_numbers_by_value_or_text`는 int 셀만 써서 이 경로를 확인하지 못합니다.
- 수정안: 셀이 null이 아니고 `숫자 해석값 ∈ value의 숫자 해석값` 또는 `str(셀) ∈ str(value)`이면 통과. float 셀 + int value 테스트 추가.

### Minor

| # | 내용 | 위치 |
|---|------|------|
| M-1 | `==`/`!=`에서 숫자형 문자열 value(`"001"`)도 숫자로 비교 → 앞자리 0 코드 컬럼에서 `"1"`·`"01"`과 일치. Design 문구("value가 숫자면")보다 넓음 | `ops_executor.py:107-114` |
| M-2 | sort 키 `desc` 타입 미검증 — `"desc": "false"`(문자열)면 내림차순 | `spec_policies.py:107-111` |
| M-3 | 비교 연산자에 `value` 누락·null 허용 — `"None"` 문자열과 비교됨 | `spec_policies.py:88-99` |
| M-4 | select 중복 컬럼 허용 — 이후 참조 시 실행 오류(안내 노옵으로는 끝남) | `spec_policies.py:80-85` |
| M-5 | 테스트 누락: 생성기 수준 ops 실행 실패(§6.1 #6)·error 로그, groupby sum 빈 그룹 None, `ops_sheet_count`·재시도 run_name 단언 | `test_generator.py`, `test_ops_executor.py` |
| M-6 | 서식 적용이 중간 실패하면 일부 서식(헤더 bold 등)이 남음 | `styled_excel_exporter.py:91-104` |
| M-7 | `truncated` 주석·요약 문구가 "llm 300행" 기준 — ops 결과가 Excel 행 한도에서 잘려도 같은 문구 (100만 행 초과 시에만 발생, 요약 미변경 결정 범위) | `schemas.py:46`, `workflow_compiler.py:2494-2497` |
| M-8 | Plan §2.1 ⑥·§7.2에 `with_structured_output` 문구 잔존, FR-07 문구가 DI 교체 방식과 다름 | `plan.md:84`, `:222`, `:113` |
| M-9 | `generate` 47줄 (master 48줄의 기존 위반, 1줄 감소) | `generator.py:84-130` |

---

## 4. Carry-over

- **실제 LLM 스모크 미실행**: OpenAI `429 insufficient_quota`. 다른 provider 키 확인은 권한 정책에서 거부됨. 스크립트는 scratchpad `smoke_excel_gen.py` (800행 원본, "연체 30일 이상 + 지점별 합계" 요청). 크레딧 충전 후 실행.
- **성능 NFR** (1만 행 × ops 5단계 + 서식 2초 이내): 측정 테스트 없음.
- **커버리지 80%**: 측정하지 않음.

---

## 5. Recommended Actions

1. I-1 수정 + 테스트 (Functional 100%, Overall 약 99.9%)
2. 선택: M-2·M-3·M-4 검증 보강, M-5 테스트 추가
3. 문서: M-1을 Design §6.3에 반영, M-8 Plan 문구 정리

---

## 6. Act-1 결과 (2026-11-19)

사용자 결정: "I-1 + 검증·테스트 보강". 테스트를 먼저 추가해 Red(5건)를 확인한 뒤 수정했습니다.

| # | 조치 | 위치 | 테스트 |
|---|------|------|--------|
| I-1 | `in`: 문자열 일치 또는 (value에 숫자 타입 원소가 있으면) 셀 숫자 해석값 일치 | `ops_executor.py` `_in_mask` | `test_in_matches_float_cells_with_int_values` |
| M-1 | `==`·`!=`는 value가 숫자 타입일 때만 숫자 비교, 문자열은 글자 그대로. 크기 비교는 숫자 문자열도 숫자로. Design §6.3 갱신 | `ops_executor.py` `_comparison_mode` | `test_eq_text_value_is_text_compare`, `test_eq_number_value_is_numeric_compare`, `test_in_with_text_values_keeps_leading_zero_codes`, `test_range_with_numeric_string_value_is_numeric` |
| M-2 | `sort.by[].desc`는 bool만 허용 | `spec_policies.py` `_validate_sort` | `test_sort_desc_must_be_bool`, `test_sort_desc_optional` |
| M-3 | `==`·`!=`·크기 비교의 value 누락·null 거부 | `spec_policies.py` `_validate_filter` | `test_compare_requires_value` |
| M-4 | select 중복 컬럼 거부 | `spec_policies.py` `_validate_select` | `test_select_duplicate_columns` |
| M-5 | 생성기 ops 실패 래핑·error 로그, groupby 빈 그룹 sum=None, `ops_sheet_count`·재시도 run_name 단언 | 테스트만 추가 (동작은 원래 맞음) | `TestAct1Generator` 3건, `test_groupby_sum_without_numbers_is_none` |
| M-8 | Plan 요약·§2.1·FR-07·Risk·§6.1·§7.2 문구를 Design §1.3 결정에 맞춤 | `plan.md` | — |

**미조치 (수용)**: M-6 (서식 중간 실패 시 일부 서식 잔존, 영향 없음), M-7 (100만 행 초과 시 절단 문구, 요약 미변경 결정 범위), M-9 (`generate` 47줄, 기존 위반).

**재검증**: 관련 묶음 286 passed (Check 시점 273 + 신규 13), ruff 신규 코드 경고 없음, 새 함수 40줄 이하.

```
Structural 100% · Functional 100% (41/41) · Contract 100% · Runtime 100%
Overall = 100%  (잔여 Minor 3건은 설계 불일치가 아닌 수용 항목)
```

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-11-19 | 초기 분석 (Overall 99.4%, Critical 0 · Important 1 · Minor 9) | 배상규 |
| 0.2 | 2026-11-19 | Act-1: I-1·M-1~M-5·M-8 조치, Overall 100% | 배상규 |
