# analysis-source-preservation Planning Document

> **Summary**: 분석 스냅샷이 "분석 결과 텍스트(파생 데이터)"만 저장하는 현재 구조를, 엑셀 분기에서 **파싱된 원천 데이터(행/값)**까지 함께 저장하도록 확장한다. 원본 첨부 파일은 임시(TTL 1h)라 다음 턴에 소실되므로, 원천을 스냅샷에 보존해야 후속 턴의 재분석(다른 집계·다른 차트)이 가능해진다.
>
> **Project**: sangplusbot (idt 백엔드)
> **Author**: 배상규
> **Date**: 2026-07-07
> **Status**: Draft
> **선행 기능**: analysis-data-continuity (Check 96%, 스냅샷 인프라 재사용)

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | analysis-data-continuity로 스냅샷은 저장되지만, 엑셀 분기의 스냅샷 내용이 **분석 노드의 출력 텍스트**(예: "남은 연차 5일, 1월 1일 사용...")뿐이다. 원천 표 데이터(행/값)는 워크플로우 내부에서 계산되고도 `_run_excel_analysis`가 `analysis_text`만 반환하며 버려진다. 원본 엑셀 파일마저 임시 업로드(TTL 1시간)라 다음 턴엔 이미 삭제된다. 결과적으로 후속 턴이 "분기별로 다시", "다른 지표로" 같은 **새로운 재분석**을 하려 해도 원천이 없어 파생 요약문에 의존하게 되고, 요약이 누락한 값은 복구 불가다. |
| **Solution** | 엑셀 파싱 결과(`ExcelData.to_dict()` — 시트별 columns/rows/dtypes)를 스냅샷 항목에 `kind="raw_source"`로 추가 저장한다. 기존 `analysis_output`(결과 텍스트)은 표시 연속성용으로 병행 유지한다(사용자 결정: 원천+결과 병행). 재주입·재분석은 이미 구축된 경로(검색결과 규약 → `_analyze_context` context 분기)를 그대로 재사용한다. |
| **Function/UX Effect** | 엑셀 첨부로 1턴 분석한 뒤, 후속 턴에서 **원본 재업로드 없이** 같은 데이터를 다른 방식으로 재분석·재시각화할 수 있다(월별→분기별, 표→차트 유형 변경, 특정 열만 집계 등). "데이터가 소실되어 다시 올려야 한다"는 상황이 제거된다. |
| **Core Value** | 스냅샷이 "무엇을 답했는지(결과)"를 넘어 "무엇으로 답했는지(원천)"를 보존 → 멀티턴 데이터 분석 대화가 1회성 요약이 아니라 **반복 재분석 가능한 워킹셋**이 된다. |

---

## 1. Overview

### 1.1 Purpose

엑셀 분석 스냅샷에 **파싱된 원천 데이터**를 포함시켜, 후속 턴에서 원본 파일 없이도 동일 데이터에 대한 새로운 분석/시각화가 가능하도록 한다.

### 1.2 Background — 코드 확인 결과 (2026-07-07)

**원천 데이터는 계산되지만 버려진다**
- `ExcelAnalysisWorkflow._parse_excel_node`(`excel_analysis_workflow.py:166-180`)가 `parsed_data.to_dict()`를 `state["excel_data"]`에 저장. 이 dict는 시트별 `{sheet_name, data: [행 레코드], columns, dtypes}` — **완전한 원천 표 데이터**(`pandas_excel_parser.py:103-115`, `df.to_dict(orient="records")`).
- 그러나 `WorkflowCompiler._run_excel_analysis`(`workflow_compiler.py:800-832`)는 `final.get("analysis_text", "")`만 반환. `final["excel_data"]`(원천)는 폐기.
- 결과적으로 `analysis_node`가 만드는 AIMessage에는 분석 텍스트만 담기고, 스냅샷도 이 텍스트만 캡처(`run_agent_use_case._snapshot_items`, excel 항목이 `is_worker_output` 텍스트를 수집).

**원본 파일도 소실**
- 첨부는 임시 업로드 디렉토리에 TTL 1시간(`config.agent_attachment_ttl_seconds=3600`). 다음 턴엔 `file_path`가 죽은 경로 → 재파싱 불가.

**검색/MCP는 이미 원천 저장 중 (범위 제외 근거)**
- 검색 워커: `format_search_result(worker, body)`의 body가 retrieved 원문. General Chat: `ToolMessage.content`가 도구 원출력. 둘 다 원천을 이미 스냅샷에 저장 → 이번 변경 대상 아님.

### 1.3 Related Documents

- `docs/02-design/features/analysis-data-continuity.design.md` — 스냅샷 스키마/정책(`AnalysisSnapshotPolicy`)·재주입 경로. 본 기능이 재사용/확장.
- `docs/03-analysis/analysis-data-continuity.analysis.md` — 선행 Gap 분석(96%).
- `docs/rules/conversation-memory.md` — 스냅샷 채널 규칙(개정 대상).

### 1.4 사용자 결정 사항 (2026-07-07 확인)

| 질문 | 결정 |
|------|------|
| 원천 보존 형태 | **파싱된 구조화 데이터**(행/값 JSON) — 파일 durable 보관 아님 |
| 결과 텍스트 처리 | **원천+결과 병행 보관** — items에 `kind`로 구분(`raw_source` vs `analysis_output`) |
| 적용 범위 | **엑셀 분기만** — 검색/MCP는 이미 원천 저장 |
| PII/보존 | **세션 스코프 + 크기상한만** — 마스킹은 pii-masking-integration 후속 |

---

## 2. Scope

### 2.1 In Scope (백엔드 idt/)

**A. 원천 데이터 캡처 채널**
- [ ] `_run_excel_analysis` 반환을 `(analysis_text, raw_source)` 2요소로 확장 (또는 dict). `final.get("excel_data")`를 원천으로 전달.
- [ ] `analysis_node`가 원천 데이터를 SupervisorState 채널로 노출(`charts` 상태 채널 패턴 동형 — 메시지가 아닌 별도 state 키). 채널 이름/리듀서는 Design에서 확정.
- [ ] `run_agent_use_case`가 그 채널을 `_StreamState.charts`처럼 캡처 → `_collect_snapshot`에서 원천 항목(`kind="raw_source"`)으로 스냅샷에 병합.

**B. 스냅샷 스키마 확장 (원천+결과 병행)**
- [ ] `AnalysisSnapshotPolicy.build_snapshot`이 `raw_source`/`analysis_output` 두 kind를 함께 수용. 항목 구조에 원천은 구조화 데이터(dict) 보존 허용 여부 확정(현재는 content: str 전제 — Design에서 str 직렬화 vs dict 필드 분리 결정).
- [ ] 재주입: 원천 항목을 `_analyze_context`가 데이터로 인식하도록 렌더. 기존 `format_search_result` 규약 재사용(원천 JSON을 텍스트로) 우선 검토.

**C. 크기 처리 (핵심 난제)**
- [ ] 표 데이터는 기존 상한(item 4000/total 8000자)을 쉽게 초과 → 원천 전용 상한 또는 행 샘플링/압축 인코딩 전략 확정(Design). 절단 시 "N행 중 M행" 명시.

**D. 재분석 동작 검증**
- [ ] 후속 턴("분기별로 다시")에서 첨부 없음 → `analysis_node`가 context 분기 진입 → 재주입된 원천으로 재집계. 기존 경로로 동작함을 테스트로 보장(신규 배선 최소).

**E. 문서·테스트**
- [ ] `conversation-memory.md` 스냅샷 규칙에 `raw_source` kind 조항 추가.
- [ ] TDD: 원천 캡처/병행 저장/크기 처리/재분석 각각 테스트 선행.

### 2.2 Out of Scope

- 원본 파일 durable 보관 (사용자 결정: 파싱 데이터만)
- 검색/MCP 경로 원천 저장 (이미 저장 중)
- "다른 사용자 휴가" 등 **애초에 없던 데이터** 확보 — 본 기능으로 해결 불가(별도 데이터 소스 필요). 회피성 응답 문구 개선은 analysis-data-continuity의 `DATA_GAP_GUIDE` 범위.
- PII 마스킹 (pii-masking-integration 후속)
- 프론트 변경 (스냅샷은 LLM 컨텍스트 전용, UI 미노출)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | 엑셀 분기 턴 종료 시 파싱된 원천 데이터를 `kind="raw_source"`로 스냅샷에 저장 | High | Pending |
| FR-02 | 기존 분석 결과 텍스트는 선행 그대로(`kind="excel"`)로 병행 저장 | High | Pending |
| FR-03 | 후속 턴에서 원천 스냅샷이 재주입되어 `_analyze_context`가 데이터로 인식 | High | Pending |
| FR-04 | 후속 턴 재분석("분기별/다른 지표") 시 원본 재업로드 없이 원천 기반 응답 | High | Pending |
| FR-05 | 원천 크기 초과 시 상한/샘플링 적용 + 절단 사실 명시(행 수 표기) | High | Pending |
| FR-06 | 원천 캡처 실패/미주입 시 기존 동작(결과 텍스트만)으로 graceful degrade | Medium | Pending |
| FR-07 | `conversation-memory.md`에 raw_source 규칙 반영 | Low | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement |
|----------|----------|-------------|
| 토큰/저장 | 원천 재주입 후 턴 컨텍스트가 상한(원천 전용 cap, Design 확정) 이내 | 상한 테스트 + LangSmith |
| 하위 호환 | 원천 없는 기존 스냅샷/세션은 현행 동일 동작 | 회귀 |
| 아키텍처 | 스키마·상한은 domain, 캡처 흐름은 application, 파싱은 infrastructure | `/verify-architecture` |
| 테스트 | 신규 로직 Red 우선 | pytest |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] 재현: 턴1 엑셀 첨부 "휴가 분석 그래프" → 턴2 "이걸 분기별로 다시 그려줘"(첨부 없음) → 원천 재주입으로 분기 집계 성공(원본 재업로드 불필요)
- [ ] 스냅샷 DB에 `raw_source` + `analysis_output` 두 kind 공존 확인
- [ ] 대용량 시트에서 상한/샘플링 동작 + 절단 표기 확인
- [ ] 원천 캡처 실패 시 결과 텍스트만으로도 후속 동작 정상(회귀 0)
- [ ] 기존 analysis-data-continuity 테스트 + 신규 테스트 통과

### 4.2 Quality Criteria

- [ ] config 하드코딩 없음, logger 규칙 준수
- [ ] 재주입/재분석이 기존 경로 재사용(신규 그래프 배선 최소)

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 원천 표 데이터가 상한 초과 → 절단으로 재분석 부분화 | High | High | 원천 전용 상한 상향 + 행 샘플링/압축(CSV류) 인코딩. 절단 시 총행수 명시로 LLM이 한계 인지. Design에서 전략 확정 |
| 원천 채널(state) 추가가 SupervisorState/스트리밍 캡처에 파급 | Medium | Medium | `charts` 상태 채널·`_StreamState.charts` 캡처 선례 그대로 미러링. 미주입 시 비활성(FR-06) |
| 원천(개인정보) 저장량 증가로 PII 노출면 확대 | Medium | Medium | 세션 스코프(기존 대화와 동일 수명) + 크기 상한. 마스킹은 pii-masking-integration 후속(사용자 결정) |
| dict 원천을 str content 전제 스키마에 억지로 넣어 정보 손실 | Medium | Medium | Design에서 스냅샷 item 스키마 확장(원천은 구조 보존 필드) vs 직렬화 문자열 중 택1. 재주입 렌더와 함께 결정 |
| "다른 사용자" 류 질문이 여전히 안 됨을 기능 실패로 오인 | Low | Medium | Plan/Report에 명시 — 본 기능은 '가진 원천의 재분석'이지 '없는 데이터 확보'가 아님 |

---

## 6. Architecture Considerations

### 6.1 Project Level

기존 구조 유지 — Thin DDD. 신규 레이어 없음. analysis-data-continuity 스냅샷 인프라 확장.

### 6.2 Key Architectural Decisions (Design 확정 대상)

| Decision | Options | 초안 | Rationale |
|----------|---------|------|-----------|
| 원천 전달 채널 | ① SupervisorState 새 키(charts 동형) ② 메시지 임베드 | **①** | charts 상태 채널+`_StreamState` 캡처 선례 재사용, 메시지 오염 방지 |
| 원천 스냅샷 표현 | ① item에 구조화 필드 추가 ② JSON 직렬화 str content | Design 확정 | 재주입 렌더(=`_analyze_context` 입력)와 크기 상한 처리에 함께 좌우됨 |
| 크기 처리 | 원천 전용 상한 / 행 샘플링 / 압축 인코딩 | **상한 상향 + 행 샘플링** | 표는 열 헤더+대표 행이 재분석 대부분 커버. 총행수 표기로 한계 인지 |
| 결과 텍스트 | 유지 / 제거 | **유지(병행)** | 사용자 결정 — 차트 캡션·표시 연속성 유지 |
| 범위 | 엑셀만 / 전 소스 | **엑셀만** | 검색/MCP는 이미 원천 저장(사용자 결정) |

### 6.3 영향 파일 목록 (초안)

```
백엔드 (idt/)
├── src/application/workflows/excel_analysis_workflow.py     [검토] excel_data(원천) 최종 state 노출 확인
├── src/application/agent_builder/workflow_compiler.py       [수정] _run_excel_analysis 원천 반환, analysis_node state 채널
├── src/application/agent_builder/supervisor_state.py        [수정] 원천 state 채널 필드 추가
├── src/application/agent_builder/run_agent_use_case.py      [수정] 원천 채널 캡처 → _collect_snapshot 병합
├── src/domain/conversation/analysis_snapshot_policy.py      [수정] raw_source kind 수용, 크기/렌더 규칙
├── src/config.py                                            [수정] 원천 전용 상한/샘플링 설정
├── docs/rules/conversation-memory.md                        [개정] raw_source 조항
└── tests/ (agent_builder·conversation·workflows)             [신규/수정]
```

---

## 7. Convention Prerequisites

- `idt/CLAUDE.md`: 레이어 규칙, 함수 40줄, logger 필수, config 하드코딩 금지
- 스냅샷 스키마/상한/렌더는 domain(`AnalysisSnapshotPolicy`) 단일 출처 유지
- 신규 환경변수: 없음(config 기본값)
- 프론트 계약: 응답 스키마 불변 → 동기화 불필요

---

## 8. Next Steps

1. [ ] `/pdca design analysis-source-preservation` — 원천 전달 채널·스냅샷 item 스키마·크기 처리 전략 확정
2. [ ] 구현 (TDD: 정책 크기/스키마 → 원천 채널 → 캡처/병합 → 재분석 검증)
3. [ ] `/pdca analyze analysis-source-preservation`

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-07-07 | Initial draft — 원천 데이터 폐기 지점 코드 확인 + 사용자 결정 4건 반영 | 배상규 |
