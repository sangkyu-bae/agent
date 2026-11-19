# excel-generator-spec-ops Planning Document

> **Summary**: 엑셀 생성 노드의 시트 계획에 원천 연산 명세(ops)와 컬럼 의미 타입 서식 명세를 추가하고, 계획 파싱·검증 실패 시 1회 재시도로 안정화한다. LLM은 명세만 쓰고 값·서식은 코드(pandas·openpyxl)가 만든다.
>
> **Project**: sangplusbot (idt 백엔드)
> **Version**: idt 0.1.x
> **Author**: 배상규
> **Date**: 2026-11-19
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 원천 데이터를 정렬·필터·상위 N·집계하려면 LLM이 행을 `llm` 시트로 다시 받아 써야 해서 옮겨 쓰기 오류와 300행 절단이 생긴다. 산출 파일은 값만 든 평면 표라 숫자 형식·열 너비·필터가 없고, 시트 계획 JSON 파싱이 실패하면 재시도 없이 실패한다. |
| **Solution** | `raw:` 시트에 허용 목록 기반 연산 명세(`ops`: select·filter·sort·top·groupby/agg)를 추가해 pandas가 실행한다. 컬럼 의미 타입(`column_types`) 명세로 openpyxl이 표시 형식·열 너비·틀 고정·자동 필터를 적용한다. 계획은 JSON 텍스트로 받고(Design §1.3), 파싱·검증 실패 시 위반 사유를 붙여 1회 재시도한다. |
| **Function/UX Effect** | "연체 상위 20건만 엑셀로", "지점별 잔액 합계 시트 추가" 같은 요청이 원천 값 그대로, 행 수 제한 없이 처리된다. 내려받은 파일은 천 단위 구분·%·날짜 형식이 적용되고 헤더 고정·필터가 걸린 상태로 열린다. |
| **Core Value** | 금융 데이터를 다루는 산출물에서 LLM이 값을 옮겨 쓰거나 계산하지 않으므로 수치 오류 가능성이 줄어든다. 기존 하이브리드 소싱 구조를 확장하는 변경이라 아키텍처 변경 없이 보수적 동작 원칙을 유지한다. |

---

## Context Anchor

> Design/Do 문서로 전파되는 컨텍스트 앵커.

| Key | Value |
|-----|-------|
| **WHY** | 원천 가공(정렬·필터·집계)이 LLM 재작성에 의존해 값 오류·300행 절단이 생기고, 산출물이 서식 없는 평면 표라 업무에 바로 쓰기 어렵다 |
| **WHO** | P2 (KB 운영자 / 에이전트 소유자) — 조립 에이전트로 데이터 수집·정리·보고 업무를 자동화하려는 사용자, 그리고 그 파일을 받는 최종 사용자 |
| **RISK** | 원천 셀 값이 문자열로 들어와 비교·집계가 틀어질 수 있음(타입 강제 변환 필요), LLM이 없는 컬럼·잘못된 연산을 명세할 수 있음(검증+재시도), 기존 REST/Tool 소비자 회귀 |
| **SUCCESS** | ops 경로 결과가 pandas 기준값과 행 단위로 일치, ops 결과는 300행 상한 미적용, 서식 명세 적용 파일이 openpyxl 재로드 시 number_format·freeze_panes·auto_filter 확인, 명세 없는 기존 계획은 출력 동일(무회귀), 실패 시 그래프 비중단 |
| **SCOPE** | 백엔드 단독: domain 스키마·정책(ops·column_types 검증) + ExcelGenerator(계획·실행) + 서식 적용 exporter(opt-in). 수식·차트·양식 채우기·프론트 변경은 스코프 밖 |

---

## 1. Overview

### 1.1 Purpose

엑셀 생성 노드(excel-generator-node)가 만드는 파일의 **정확도**와 **업무 사용성**을 높인다.

- 정확도: 원천 데이터 가공을 LLM 재작성이 아니라 코드 연산으로 처리한다.
- 사용성: 컬럼 의미에 맞는 표시 형식과 기본 표 서식을 적용한다.
- 안정성: 시트 계획 출력 형식을 강제하고, 실패 시 한 번 재시도한다.

### 1.2 Background

- excel-generator-node 사이클(2026-08, archive)에서 하이브리드 소싱을 도입했다.
  - `raw:<idx>`: 구조화 원천을 코드가 원본 그대로 복사 (LLM은 컬럼·행 수·샘플 5행만 봄)
  - `llm`: 비정형 재료를 LLM이 표로 작성 (300행·10시트 상한)
- 당시 Out of Scope로 둔 "셀 서식"과, 계획 프롬프트 규칙 4("정렬·상위 N·필터 의도는 llm 시트로 반영")가 현재 한계의 원인이다.
  - 규칙 4 때문에 원천 가공 요청은 결국 LLM이 행을 다시 써야 한다 → 옮겨 쓰기 오류, 300행 절단.
- 산출은 `PandasExcelExporter`의 `df.to_excel()` 값 출력뿐이다. LLM이 숫자를 문자열로 주면 문자열 셀로 저장된다.
- `_parse_plan`은 자유 형식 JSON을 `json.loads`로 파싱하며, 실패 시 즉시 `ExcelGenerateError`로 끝난다.
- 프로젝트에는 `with_structured_output` 사용 선례가 있다 (`collect_pipeline.py`, `search_pipeline.py`, `action_pipeline.py`).

### 1.3 Related Documents

- 선행 사이클: `idt/docs/archive/2026-08/excel-generator-node/` (plan·design·analysis·report)
- 구현 위치: `src/infrastructure/excel_generator/generator.py`, `src/domain/excel_generator/{schemas,policies}.py`
- 변환기: `src/infrastructure/excel_export/pandas_excel_exporter.py`
- 노드: `src/application/agent_builder/workflow_compiler.py` `_create_excel_generator_node`
- 미리보기: `src/infrastructure/excel/preview_reader.py` (`data_only=True` — 수식 제외 근거)

---

## 2. Scope

### 2.1 In Scope

- [ ] **① 원천 연산 명세 (ops)** — `raw:<idx>` 시트에 선택적 `ops` 배열
  - `select`(컬럼 선택·순서), `filter`(구조화 조건), `sort`(컬럼·방향, 다중), `top`(N), `groupby`+`agg`(sum·mean·count·min·max)
  - 실행 순서는 명세 순서. 연산 종류·연산자는 domain 허용 목록으로 제한
  - ops 결과 행에는 `MAX_LLM_STRUCTURED_ROWS`(300) 상한을 적용하지 않음 (Excel 시트 하드 리밋만 적용)
  - 비교·집계 전 대상 컬럼 숫자/날짜 강제 변환 (실패 셀은 원값 유지·비교 제외)
- [ ] **② 서식 명세 (column_types)** — 시트별 선택적 `{컬럼명: 의미 타입}`
  - 의미 타입: `text`, `integer`, `number`, `currency`, `percent`, `date`
  - 타입별 number_format 적용 + 문자열 숫자/날짜의 값 변환 (`"1,234"` → 1234)
  - 서식 명세가 있는 시트에 기본 표 서식: 헤더 스타일, 열 너비 자동, 헤더 틀 고정, 자동 필터
  - `raw`·`llm` 시트 모두 적용 가능
- [ ] **⑥ 계획 안정성**
  - ~~시트 계획을 `with_structured_output`으로 수신~~ → Design §1.3: JSON 텍스트 수신 유지
  - 파싱 실패 또는 `validate_plan` 위반 시 위반 사유를 메시지에 붙여 **1회 재시도**, 재실패 시 기존과 같이 안내 노옵
- [ ] 계획 프롬프트 규칙 개정: "원천 가공은 `raw` + `ops`로, `llm` 시트는 비정형 재료에만"
- [ ] 결과 요약(`ExcelGenerateResult`·노드 응답)에 ops 적용 여부 반영 (필요 범위만)

### 2.2 Out of Scope

- ③ Excel 수식·합계 행 (미리보기 `data_only=True` 계산값 처리 필요 → 다음 사이클)
- ④ 차트·조건부 서식
- ⑤ 사내 양식(xlsx 템플릿) 채우기 (별도 기능)
- 원천 간 join·피벗(열 전개)
- pandas `query`/`eval` 문자열 조건 (코드 실행 위험 — 구조화 조건만 허용)
- REST `/api/v1/excel-export`, `ExcelExportTool`(ToolFactory 경로)의 출력 변경 — 서식은 생성 노드 opt-in에만 적용
- 프론트엔드 변경, 위저드 설정 UI, DB 스키마 변경

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | `SheetPlanItem`에 선택적 `ops`·`column_types` 필드 추가 (domain, 외부 의존 없음) | High | Pending |
| FR-02 | domain 정책: ops 검증 — 허용 연산·연산자 목록, 참조 컬럼 존재(원천 컬럼 기준, groupby 이후는 결과 컬럼 기준), `top` 양의 정수, `agg` 함수 허용 목록, ops는 `raw` 시트에만 허용 | High | Pending |
| FR-03 | domain 정책: column_types 검증 — 허용 타입 목록, 시트 컬럼에 존재하는 키만 허용 | High | Pending |
| FR-04 | infrastructure: ops 실행기 — pandas로 명세 순서대로 실행, 비교·집계 전 대상 컬럼 타입 강제 변환, 결과를 `(columns, rows)`로 반환 | High | Pending |
| FR-05 | ops 결과에는 300행 상한 미적용. Excel 시트 행 한도(1,048,575 데이터 행) 초과 시 절단 + `truncated` | High | Pending |
| FR-06 | 서식 적용: column_types가 있는 시트에 number_format·값 변환·헤더 스타일·열 너비·freeze_panes·auto_filter 적용 | High | Pending |
| FR-07 | 서식 명세가 없는 계획은 기존과 같은 셀 값·시트 구성 (생성기 exporter는 `StyledExcelExporter`로 교체하되 명세 없는 시트는 값만 기록 — Design §2.1, 테스트 X1) | High | Pending |
| FR-08 | ~~시트 계획을 구조화 출력으로 수신, 미지원 시 JSON 파싱 폴백~~ → Design §1.3: JSON 텍스트 수신 유지 (자유형 dict·rows는 strict structured output과 호환 불가, `collect_pipeline.py` 선례) | Medium | Changed |
| FR-09 | 파싱 실패·검증 위반 시 위반 사유 포함 1회 재시도, 재실패는 `ExcelGenerateError` → 안내 노옵 | Medium | Pending |
| FR-10 | 계획 프롬프트 개정 + 카탈로그에 컬럼별 추정 타입 노출 (LLM의 filter·column_types 작성 근거) | Medium | Pending |
| FR-11 | ops 실행 중 예외(타입 불일치 등)는 해당 시트 실패 사유로 `ExcelGenerateError` — 그래프 비중단 | High | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 정확도 | ops 시트 결과가 동일 연산의 pandas 기준값과 행·값 단위로 일치 | 단위 테스트 (기준 DataFrame 비교) |
| 안전성 | 문자열 조건 평가(`eval`/`query`) 미사용, 허용 목록 밖 연산은 검증 단계에서 거부 | 정책 테스트 + 코드 검색 |
| 성능 | 원천 1만 행 × ops 5단계 + 서식 적용이 2초 이내 (LLM 호출 제외) | 단위 테스트 시간 측정 |
| 비용 | LLM 호출: 정상 1회, 실패 시 최대 2회 | 테스트에서 호출 횟수 단언 |
| 아키텍처 | domain 계층에 pandas·openpyxl·LangChain import 없음 | `verify-architecture` |
| 로깅 | 재시도·ops 실패·서식 적용 실패를 request_id와 함께 기록, 예외는 `exception=` 포함 | `verify-logging` |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] SC-1: "상위 N·필터·정렬" 요청이 `raw`+`ops`로 계획되고, 결과가 원천 값 그대로 기록된다 (300행 넘는 결과 포함)
- [ ] SC-2: `groupby`+`agg` 시트의 합계·평균이 pandas 기준값과 일치한다
- [ ] SC-3: column_types 적용 파일을 openpyxl로 다시 열었을 때 타입별 number_format, 숫자 셀 타입, `freeze_panes == "A2"`, auto_filter 범위가 확인된다
- [ ] SC-4: ops·column_types가 없는 기존 형태 계획은 기존 테스트 전부 통과 (무회귀), REST `/excel-export`·`ExcelExportTool` 출력 불변
- [ ] SC-5: 첫 계획이 검증에 실패하면 1회 재시도로 복구되고, 두 번 실패하면 안내 노옵으로 끝난다 (LLM 호출 ≤ 2)
- [ ] SC-6: 허용 목록 밖 연산·없는 컬럼 참조·llm 시트의 ops는 검증에서 거부된다
- [ ] 단위 테스트 작성·통과 (TDD: Red → Green → Refactor)

### 4.2 Quality Criteria

- [ ] 신규·변경 모듈 테스트 커버리지 80% 이상
- [ ] 함수 40줄·if 중첩 2단계 규칙 준수
- [ ] `verify-architecture`, `verify-logging`, `verify-tdd` 통과
- [ ] 백엔드 관련 회귀 테스트 통과 (`uv run python -m pytest tests/... `, master 상시 실패 목록 제외)

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 원천 셀 값이 문자열(`"1,234"`, `"2026-11-19"`)이라 비교·정렬·집계가 문자열 기준으로 틀어짐 | High | High | ops 실행 전 대상 컬럼 강제 변환(쉼표·통화기호 제거 후 숫자, ISO 날짜). 변환 실패 셀은 원값 유지·필터 비교에서 제외. 테스트로 혼합 타입 케이스 고정 |
| LLM이 없는 컬럼·잘못된 연산·타입을 명세 | Medium | Medium | domain 정책 검증 → 위반 사유를 붙여 1회 재시도 → 재실패 시 안내 노옵 |
| 구조화 출력 미지원 모델·provider 차이 | Medium | Medium | Design §1.3: 구조화 출력을 쓰지 않고 JSON 텍스트 + 1회 재시도로 대응 |
| ops 결과가 매우 커서 메모리·시간 증가 | Medium | Low | 원천은 이미 메모리에 있는 데이터이므로 증가분 제한적. Excel 행 한도에서 절단 |
| 서식 적용 경로가 기존 exporter 출력·테스트를 바꿈 | High | Low | 서식 명세가 있을 때만 새 경로 사용(opt-in). 명세 없음 = 기존 exporter 그대로 |
| 프롬프트 규칙 개정으로 기존 llm 시트 동작 변화 | Medium | Medium | 규칙 변경을 "원천이 있을 때 가공은 ops"로 한정. 비정형 재료 표 작성 규칙은 유지 |
| 집계 결과 컬럼명 규칙(`잔액_sum` 등)이 이후 select·sort 참조와 어긋남 | Low | Medium | 결과 컬럼명 규칙을 Design에서 고정하고 검증이 groupby 이후 컬럼 집합을 기준으로 수행 |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `domain/excel_generator/schemas.py` `SheetPlanItem` | Domain Schema | 선택적 `ops`, `column_types` 필드 추가 (기본값 None) |
| `domain/excel_generator/policies.py` | Domain Policy | ops·column_types 검증 추가, 허용 목록 상수 |
| `infrastructure/excel_generator/generator.py` | Infrastructure | 계획 수신(JSON + 재시도), `_materialize`에 ops 실행, 서식 경로 분기 |
| 신규: ops 실행기 / 서식 적용기 (infrastructure) | Infrastructure | pandas 연산 실행, openpyxl 서식 적용 (위치는 Design에서 확정) |
| `domain/excel_export/schemas.py` `ExcelSheetData` | Domain Schema | (선택) 서식 명세 전달 필드 — Design에서 별도 스키마와 비교해 결정 |
| `ExcelGenerateResult` / `_render_excel_summary` | Schema / Node | (필요 시) ops 적용 여부 표시 |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| `SheetPlanItem` | CREATE | `ExcelGenerator._parse_plan` | Needs verification — 새 필드 파싱 |
| `SheetPlanItem` | READ | `policies.validate_plan`, `ExcelGenerator._materialize` | Needs verification |
| `ExcelGenerator.generate` | CALL | `workflow_compiler._create_excel_generator_node` (`excel_export` tool_id 분기) | None — 시그니처 유지 |
| `ExcelGenerator` | CREATE | `api/main.py:3202` DI 배선 | Needs verification — 새 협력 객체 주입 시 |
| `PandasExcelExporter` | CALL | `ExcelGenerator._export_and_save` | None — 서식 명세 없을 때 그대로 사용 |
| `PandasExcelExporter` | CALL | `ExcelExportTool._run` (ToolFactory `excel_export`, 미들웨어 에이전트 등) | None — 변경 없음 |
| `PandasExcelExporter` | CALL | `excel_export_use_case` / `excel_export_router` (REST) | None — 변경 없음 |
| `ExcelSheetData` | READ | exporter 3개 소비자 | None (필드 추가 시 기본값으로 호환) |
| 산출 .xlsx | READ | `infrastructure/excel/preview_reader.py` (채팅 미리보기) | Needs verification — 서식·숫자 셀이 미리보기 직렬화에 문제 없는지 |
| `MAX_LLM_STRUCTURED_ROWS` | READ | `_materialize`, `_render_excel_summary` | None — llm 시트에만 계속 적용 |

### 6.3 Verification

- [ ] 위 소비자 전부 기존 테스트로 무회귀 확인
- [ ] 미리보기 리더로 서식 적용 파일을 읽어 숫자·날짜 셀 표시 확인
- [ ] 권한·인증 경로 변경 없음

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| **Starter** | Simple structure | Static sites | ☐ |
| **Dynamic** | Feature-based modules | Web apps with backend | ☐ |
| **Enterprise** | Strict layer separation, DI | Complex architectures | ☑ (Thin DDD: domain → application → infrastructure) |

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 원천 가공 방식 | LLM 재작성 / 연산 명세 + 코드 실행 / LLM 코드 생성·샌드박스 실행 | 연산 명세 + 코드 실행 | 값이 바뀌지 않음, 결과 예측 가능, 코드 실행 위험 없음 |
| 지원 연산 | 기본 / 기본+groupby / +join | 기본 + groupby/agg | 요약 시트 수요 충족, join의 키 불일치·행 폭증 위험 회피 (사용자 확정) |
| 필터 형식 | 구조화 조건 / pandas query 문자열 | 구조화 조건 `{col, op, value}` | 허용 목록 검증 가능, eval 미사용 (사용자 확정) |
| 서식 적용 범위 | 생성 노드 opt-in / 공용 exporter 기본값 | 생성 노드 opt-in | 기존 REST·Tool 소비자 무회귀 (사용자 확정) |
| 서식 엔진 | pandas Styler / openpyxl 직접 | openpyxl 직접 | number_format·freeze_panes·auto_filter 직접 제어, 이미 의존성 있음 |
| 계획 수신 | 자유 JSON / 구조화 출력 + 폴백 | JSON 텍스트 + 1회 재시도 (Design §1.3에서 변경) | 자유형 dict·rows는 strict structured output과 호환 불가 (`collect_pipeline.py` 선례) |
| 재시도 | 없음 / 1회 / N회 | 1회 (위반 사유 첨부) | 비용 상한 2회 호출로 고정 |
| 검증 위치 | infrastructure / domain policy | domain policy | 규칙은 domain (CLAUDE.md 레이어 책임) |

### 7.3 Clean Architecture Approach

```
domain/excel_generator/
  schemas.py    ← SheetPlanItem(+ops, +column_types), 연산 VO
  policies.py   ← 허용 목록 상수, validate_plan 확장 (순수 로직)

infrastructure/excel_generator/
  generator.py  ← 계획 수신(구조화+재시도) → 검증 → 실행 → 내보내기
  (신규) ops 실행기     ← pandas 연산 실행 + 타입 강제 변환
  (신규) 서식 적용기    ← openpyxl number_format·표 서식

application/agent_builder/workflow_compiler.py ← 변경 없음 (generate 시그니처 유지)
```

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- [x] `CLAUDE.md` (루트·idt) 코딩 규칙
- [x] `idt/docs/rules/testing.md`, `logging.md`, `tool-and-mcp.md`
- [x] 선행 사이클 Design (excel-generator-node) 패턴

### 8.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| ops JSON 형태 | missing | 연산별 필드·결과 컬럼명 규칙 (Design §3) | High |
| 의미 타입 → number_format 표 | missing | 타입별 서식 문자열 (Design §3) | High |
| 강제 변환 규칙 | missing | 숫자·날짜 파싱 허용 패턴, 실패 처리 | High |
| 에러 처리 | exists | 안내 노옵 (기존 §6.1 동형) | Medium |

### 8.3 Environment Variables Needed

없음. 상한값은 domain 정책 상수로 둔다 (기존 `MAX_LLM_STRUCTURED_ROWS`와 동일 방식).

---

## 9. Next Steps

1. [ ] Design 문서 작성 (`/pdca design excel-generator-spec-ops`) — ops·column_types 스키마, 결과 컬럼명 규칙, 서식 표, 재시도 흐름, 3안 비교
2. [ ] 구현 (TDD, worktree)
3. [ ] Gap 분석

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-11-19 | Initial draft (범위 ①+②+⑥, 기본+groupby, 구조화 필터, 생성 노드 opt-in 확정) | 배상규 |
