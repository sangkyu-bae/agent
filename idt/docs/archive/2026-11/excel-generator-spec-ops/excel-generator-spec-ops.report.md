# excel-generator-spec-ops Completion Report

> **Status**: Complete (실 LLM 스모크 통과 — Claude Opus 5.5)
>
> **Project**: sangplusbot (idt 백엔드)
> **Version**: idt 0.1.x
> **Author**: 배상규
> **Completion Date**: 2026-11-19
> **PDCA Cycle**: Plan → Design → Do(module-1~4) → Check → Act-1

---

## Executive Summary

### 1.1 Project Overview

| Item | Content |
|------|---------|
| Feature | excel-generator-spec-ops — 엑셀 생성 노드의 원천 연산 명세·서식 명세·계획 재시도 |
| Start Date | 2026-11-19 |
| End Date | 2026-11-19 |
| Branch / Worktree | `feature/excel-generator-spec-ops` / `wt/excel-generator-spec-ops` (미커밋) |

### 1.2 Results Summary

```
┌─────────────────────────────────────────────┐
│  Match Rate: 99.4% → 100% (Act-1)            │
├─────────────────────────────────────────────┤
│  ✅ FR 완료:      10 / 11  (FR-08 설계 변경)  │
│  ✅ SC 충족:       6 / 6                      │
│  ✅ 실 LLM 스모크: Claude Opus 5.5 통과       │
│  ⏳ 이월:          성능·커버리지               │
└─────────────────────────────────────────────┘
```

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | 원천 데이터의 정렬·필터·상위 N·집계는 LLM이 행을 `llm` 시트로 다시 써야 했다. 그래서 옮겨 쓰기 오류와 300행 절단이 생겼다. 산출 파일은 값만 든 평면 표였고, 계획 JSON이 깨지면 재시도 없이 실패했다. |
| **Solution** | LLM은 `raw` 시트에 연산 명세(`ops`)와 컬럼 의미 타입(`column_types`)만 쓴다. 검증은 domain 허용 목록이 맡고, 실행은 pandas(`ops_executor`), 서식은 openpyxl(`StyledExcelExporter`)이 맡는다. 계획이 깨지거나 검증에 걸리면 위반 사유를 붙여 1회 다시 요청한다. |
| **Function/UX Effect** | 1,000행 원천을 필터한 500행이 원천 값 그대로 저장된다(이전 경로라면 300행 절단). groupby 합계는 pandas 기준값과 일치한다. column_types 시트는 `#,##0`·`0.0%`·`yyyy-mm-dd` 형식과 헤더 고정·자동 필터가 적용된 상태로 열린다. 잘못된 계획은 LLM 호출 2회 안에 복구되거나 안내 메시지로 끝난다. |
| **Core Value** | 금융 수치를 LLM이 옮겨 쓰거나 계산하지 않는다. 문자열 평가(`query`·`eval`)를 쓰지 않고 허용 목록으로만 실행한다. 서식은 생성 노드에만 적용되어 REST `/excel-export`와 `ExcelExportTool`은 바뀌지 않는다. |

---

## 1.4 Success Criteria Final Status

| # | Criteria | Status | Evidence |
|---|---------|:------:|----------|
| SC-1 | raw+ops 결과가 원천 값 그대로, 300행 넘는 결과 포함 | ✅ Met | `test_generator.py` `test_raw_ops_not_capped` (500행, `truncated=False`, LLM 1회), `test_ops_executor.py` E6 |
| SC-2 | groupby+agg가 pandas 기준값과 일치 | ✅ Met | `test_ops_executor.py` `test_aggregates_match_pandas`, `test_matches_pandas_reference_on_numeric_data` |
| SC-3 | number_format·숫자 셀·freeze `A2`·auto_filter | ✅ Met | `test_styled_excel_exporter.py` X2~X4, `test_column_types_applied` |
| SC-4 | 명세 없는 계획 무회귀, REST·Tool 출력 불변 | ✅ Met | X1 (PandasExcelExporter와 셀 값 동일), 기존 생성기 테스트 전부 통과, `git diff origin/master`에 공용 exporter·Tool·REST 없음 |
| SC-5 | 1회 재시도 복구, 2회 실패 시 안내 노옵, LLM ≤ 2 | ✅ Met | `TestPlanRetry` G2~G5, 재시도 run_name 단언 |
| SC-6 | 허용 목록 밖 연산·없는 컬럼·llm 시트 ops 거부 | ✅ Met | `test_spec_policies.py` D1·D2, `test_policies.py` D9 |

**Success Rate**: 6/6 (100%)

## 1.5 Decision Record Summary

| Source | Decision | Followed? | Outcome |
|--------|----------|:---------:|---------|
| [Plan] | 범위 ①연산+②서식+⑥안정성, 수식·차트·양식 채우기 제외 | ✅ | 수식은 미리보기 리더 `data_only=True`(계산값 없음) 문제로 다음 사이클 |
| [Plan] | 기본 연산 + groupby, join 제외 | ✅ | 키 불일치·행 폭증 위험 없이 요약 시트 지원 |
| [Plan] | 구조화 필터 `{col, cmp, value}`, `query`/`eval` 금지 | ✅ | 엑셀 관련 src에 문자열 평가 없음 |
| [Plan] | 서식은 생성 노드 opt-in | ✅ | DI 1곳 교체, 공용 exporter 무변경 |
| [Design] | Option C (domain 정책 1 + 실행기 1 + 생성기 전용 exporter 1) | ✅ | 신규 파일 3개, 포트/어댑터 없이 레이어 규칙 준수 |
| [Design] | 계획 수신을 구조화 출력 대신 JSON 텍스트 + 1회 재시도 (Plan FR-08 변경) | ✅ | `collect_pipeline.py` 선례대로 strict structured output의 자유형 dict 거부 문제를 피함. 기존 FakeLLM 테스트 구조 유지 |
| [Design] | 숫자 해석은 판단에만, 셀은 원천 값 | ✅ | 필터·정렬 후에도 `"1,200"` 같은 원값 유지, 변환은 column_types가 있을 때만 |
| [Do] | groupby `sort=False`, 빈 그룹 sum은 None(`min_count=1`) | ✅ | 혼합 키 정렬 오류 방지, "데이터 없음"이 0원으로 보이지 않음. Design §6.3에 반영 |
| [Act-1] | `==`·`!=`·`in`은 value가 숫자 타입일 때만 숫자 비교 | ✅ | float 셀 `5.0 ∈ [5]` 해결(I-1), 앞자리 0 코드 `"001"` 보존(M-1) |

---

## 2. Related Documents

| Phase | Document | Status |
|-------|----------|--------|
| Plan | [excel-generator-spec-ops.plan.md](../01-plan/features/excel-generator-spec-ops.plan.md) | ✅ Finalized (Act-1에서 FR-07·FR-08 문구 정리) |
| Design | [excel-generator-spec-ops.design.md](../02-design/features/excel-generator-spec-ops.design.md) | ✅ v0.2 |
| Check | [excel-generator-spec-ops.analysis.md](../03-analysis/excel-generator-spec-ops.analysis.md) | ✅ v0.2 (Act-1 포함) |
| 선행 사이클 | `docs/archive/2026-08/excel-generator-node/` | 참고 |

---

## 3. Completed Items

### 3.1 Functional Requirements

| ID | Requirement | Status | Notes |
|----|-------------|--------|-------|
| FR-01 | `SheetPlanItem.ops`·`column_types` (domain) | ✅ | 선택 필드, 기본 None |
| FR-02 | ops 검증 (허용 목록, 컬럼 추적, top·agg·raw 전용) | ✅ | Act-1에서 desc bool, value 필수, select 중복 추가 |
| FR-03 | column_types 검증 | ✅ | raw+ops는 연산 결과 컬럼 기준 |
| FR-04 | ops 실행기 + 타입 해석 | ✅ | `ops_executor.apply_ops` |
| FR-05 | ops 결과 300행 상한 미적용, Excel 행 한도 절단 | ✅ | |
| FR-06 | 서식 적용 (number_format·값 변환·헤더·열 너비·freeze·filter) | ✅ | `StyledExcelExporter` |
| FR-07 | 명세 없는 계획은 기존과 같은 셀 값·시트 구성 | ✅ | X1 |
| FR-08 | 구조화 출력 수신 | 🔄 Changed | Design §1.3: JSON 텍스트 유지 (사용자 확정) |
| FR-09 | 파싱·검증 실패 시 1회 재시도 | ✅ | |
| FR-10 | 프롬프트 개정 + 카탈로그 dtype 노출 | ✅ | `SheetData.dtypes` 재사용 |
| FR-11 | ops 런타임 예외 → 안내 노옵 | ✅ | error 로그 + `ExcelGenerateError` |

### 3.2 Non-Functional Requirements

| Item | Target | Achieved | Status |
|------|--------|----------|--------|
| 정확도 | pandas 기준값과 일치 | 일치 (E5 기준 비교) | ✅ |
| 안전성 | 문자열 평가 없음, 허용 목록 | 확인 | ✅ |
| 비용 | LLM 호출 정상 1회, 최대 2회 | 테스트로 단언 | ✅ |
| 아키텍처 | domain에 pandas·openpyxl·langchain 없음 | 확인 | ✅ |
| 로깅 | request_id·`exception=` 포함 | 재시도 warning, ops error, 서식 warning, 완료 로그 `retried`·`ops_sheet_count` | ✅ |
| 성능 | 1만 행 × ops 5단계 + 서식 2초 이내 | 미측정 | ⏳ |
| 커버리지 | 80% | 미측정 | ⏳ |

### 3.3 Deliverables

| Deliverable | Location | Status |
|-------------|----------|--------|
| domain 정책 | `src/domain/excel_generator/spec_policies.py` (신규), `policies.py`, `schemas.py` | ✅ |
| 시트 스키마 | `src/domain/excel_export/schemas.py` (`column_types`) | ✅ |
| ops 실행기 | `src/infrastructure/excel_generator/ops_executor.py` (신규) | ✅ |
| 서식 exporter | `src/infrastructure/excel_export/styled_excel_exporter.py` (신규) | ✅ |
| 생성기 | `src/infrastructure/excel_generator/generator.py` | ✅ |
| DI | `src/api/main.py` (생성 노드 exporter 교체) | ✅ |
| 테스트 | `test_spec_policies.py`·`test_ops_executor.py`·`test_styled_excel_exporter.py` (신규), 기존 4개 보강 | ✅ |

---

## 4. Incomplete Items

### 4.1 Carried Over

| Item | Reason | Priority |
|------|--------|----------|
| 성능 NFR 측정 (1만 행) | 측정 테스트 없음 | Medium |
| 커버리지 측정 | 미실행 | Low |
| ③ Excel 수식·합계 행 | Plan Out of Scope (미리보기 계산값 처리 필요) | 다음 사이클 후보 |
| ⑤ 사내 양식(xlsx) 채우기 | Plan Out of Scope | 다음 사이클 후보 |

### 4.2 Accepted (수용)

| Item | Reason |
|------|--------|
| M-6 서식 중간 실패 시 일부 서식 잔존 | 값에 영향 없음 |
| M-7 100만 행 초과 절단 시 "300행" 안내 문구 | 실발생 가능성 낮음, 요약 미변경 결정 범위 |
| M-9 `generate` 47줄 | master 48줄의 기존 위반 (1줄 감소) |

---

## 5. Quality Metrics

### 5.1 Final Analysis Results

| Metric | Target | Final |
|--------|--------|-------|
| Design Match Rate | 90% | 100% (Check 99.4% → Act-1) |
| 관련 테스트 묶음 | 전부 통과 | 286 passed |
| Design 테스트 계획 대응 | 전부 | 38/38 (+ Act-1 13건) |
| ruff (신규 코드) | 경고 0 | 0 |
| Critical | 0 | 0 |

### 5.2 Resolved Issues

| Issue | Resolution | Result |
|-------|------------|--------|
| I-1 `in` 필터가 float 셀(`5.0`)을 `[5]`로 못 찾음 → 빈 시트 | 문자열 일치 또는 숫자 타입 원소 숫자 일치 | ✅ |
| M-1 `== "001"`이 `"1"`과 일치 | `==`·`!=`·`in`은 숫자 타입 value만 숫자 비교 | ✅ |
| M-2 `desc: "false"` → 내림차순 | bool만 허용 | ✅ |
| M-3 value 누락 시 `"None"` 문자열 비교 | 검증에서 거부 | ✅ |
| M-4 select 중복 컬럼 | 검증에서 거부 | ✅ |
| M-5 실패 경로·로그 필드 테스트 누락 | 테스트 4건 추가 | ✅ |
| M-8 Plan 문구와 Design 결정 불일치 | Plan 정리 | ✅ |

---

## 5.3 실 LLM 스모크 (2026-11-19, Claude Opus 5.5)

OpenAI 크레딧 소진으로 gpt-4o-mini 대신 `ChatAnthropic(model="claude-opus-5-5")`로 실행했습니다.

- 입력: 800행 원천(고객명·지점·잔액 `"1,010,000원"` 문자열·연체일수), 요청 "연체일수 30일 이상인 고객만 연체일수 큰 순서로, 지점별 잔액 합계 시트도, 금액은 원 단위로 보기 좋게"
- 결과: 재시도 없이 1회 성공, 시트 2개
  - 연체 30일 이상: **546행** (원천에서 직접 센 값과 일치, 300행 절단 없음), 연체일수 내림차순, 잔액은 숫자 + `#,##0`, 틀 고정 `A2`
  - 지점별 잔액 합계: 강남 1,104,000,000 / 서초 1,097,000,000 / 분당 1,092,000,000 / 송파 — 원천 직접 합산과 일치
- **발견한 결함 (수정함)**: thinking이 항상 켜진 모델은 응답 `content`가 문자열이 아니라 블록 리스트(thinking + text)라서 `_parse_plan`의 `.strip()`에서 `AttributeError`가 났습니다. 이 예외는 노드가 잡는 `ExcelGenerateError`·`ValueError`가 아니어서 그래프가 멈춥니다. master에도 있던 기존 결함입니다. domain 공용 헬퍼 `coerce_message_text`로 text 블록만 이어 붙이도록 고치고 테스트(`TestBlockListContent`)를 추가했습니다.
- 같은 패턴이 남은 곳 (이번 범위 밖, 미수정):
  - `src/infrastructure/document_generator/generator.py:152` — `getattr(response, "content", ...)`를 그대로 사용
  - `LLMFactory._create_anthropic`는 항상 `temperature`를 넘깁니다. Claude Opus 5.5 등 최신 모델은 `temperature`를 400으로 거부하므로, 모델 레지스트리에 이 모델을 등록하면 호출이 실패할 수 있습니다 (실호출로는 확인하지 않음).

---

## 6. Lessons Learned

### 6.1 Keep

- 공용 exporter를 고치지 않고 생성기 전용 exporter를 DI로 바꿨다. 덕분에 REST·Tool 무회귀가 `git diff` 한 줄로 확인됐다.
- 기존 코드의 선례(`collect_pipeline.py` 주석)를 Design 전에 확인해 구조화 출력 채택을 피했다. 평탄화·이중 파싱 비용이 생기기 전에 결정을 바꿀 수 있었다.
- Gap 분석 결과를 직접 재현했다(`in [5,12]` → `[]`). 에이전트 보고만 믿지 않고 실제 동작으로 확인한 것이 I-1의 심각도 판단 근거가 됐다.

### 6.2 Problem

- 테스트 픽스처가 int 셀만 써서 I-1을 놓쳤다. 실제 원천은 `PandasExcelParser`가 빈칸 섞인 정수 컬럼을 float64로 읽는다. 테스트 데이터가 실제 파서 출력 형태를 따르지 않았다.
- 실제 LLM 확인을 Do 마지막으로 미뤘다가 크레딧 소진으로 막혔다. 프롬프트를 바꾸는 기능은 LLM 호출 가능 여부를 Plan 단계에서 확인해야 한다.

### 6.3 Try

- 엑셀 관련 테스트 픽스처에 "빈칸 섞인 정수 컬럼(float64)"과 "숫자 문자열" 케이스를 기본으로 넣는다.
- 프롬프트 변경 사이클은 Plan의 Risk에 "실 LLM 확인 수단"을 적는다.

---

## 7. Next Steps

1. PR #117 머지
2. `/pdca archive excel-generator-spec-ops`
3. 별도 수정 후보: document_generator 블록 리스트 응답, `LLMFactory._create_anthropic`의 temperature
4. 다음 사이클 후보: ③ 수식·합계 행 (미리보기 계산값 처리 포함), ⑤ 사내 양식 채우기

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-11-19 | 완료 보고서 | 배상규 |
| 1.1 | 2026-11-19 | 실 LLM 스모크(Claude Opus 5.5) 통과, 블록 리스트 응답 결함 수정 | 배상규 |
