# analysis-source-preservation Gap Analysis

> **Summary**: 엑셀 분기 원천 데이터(`ExcelData.to_dict()`) 보존 기능의 설계-구현 대조. gap-detector 초기 판정 93% → G1(코드) 수정 + G2/G3(문서) 정합 반영 후 **98%**.
>
> **Project**: sangplusbot (idt 백엔드)
> **Date**: 2026-07-07
> **Phase**: Check
> **Design**: [analysis-source-preservation.design.md](../02-design/features/analysis-source-preservation.design.md)
> **Match Rate**: **98%**

---

## 1. 요약

gap-detector(정적 대조)가 초기 93%와 Gap 3건을 산출했다. 이 중 G1(설계-구현 실질 불일치)은
`select_recent`의 kind별 budget 분리를 구현해 해소했고, G2/G3(문서-코드 정합)는 문서를 코드에
맞춰 정정했다. 핵심 기능(D1~D6)은 완전 구현·테스트 커버되며, 남은 2%는 라이브 E2E 검증(마이그레이션
불필요, 실 LLM 필요)이다.

---

## 2. Scores

| Category | 초기 | 조치 후 |
|----------|:---:|:---:|
| Design Match (D1~D6, §4) | 93% | 100% |
| Architecture (Thin DDD) | 100% | 100% |
| Test Coverage (T1~T6) | 90% | 100% |
| **Overall** | **93%** | **98%** |

---

## 3. D1~D6 대조

| 항목 | 설계 명제 | 구현 | 결과 |
|------|-----------|------|:----:|
| D1 원천 채널 | SupervisorState 필드 + build_initial_state `[]` + _StreamState 캡처 + _map_chain_end | `supervisor_state.py:48` / `supervisor_nodes.py` / `run_agent_use_case.py`(_StreamState, _map_chain_end) | ✅ |
| D1 노드부 | 엑셀 분기만 방출, context 분기 키 미포함 | `workflow_compiler.py` analysis_node | ✅ |
| D2 튜플 반환 | (text, raw\|None), `"sheets" in raw` 게이트 | `workflow_compiler.py` `_run_excel_analysis` | ✅ |
| D3 정책 | render_raw_source(압축표+샘플링+총행수+상한) / kind별 독립 budget(build+select) | `analysis_snapshot_policy.py` | ✅ (G1 조치 후) |
| D4 병합 | _collect_snapshot raw_source 병합, 결과 병행, 재주입 무변경 | `run_agent_use_case.py` `_collect_snapshot` | ✅ |
| D5 config/DI | config 3종 + main.py 주입 | `config.py` / `main.py` | ✅ |
| D6 경로 재사용 + 규칙 | 신규 배선 0 + conversation-memory.md 조항 | `_inject_snapshot_messages` 무변경 / 규칙 개정 | ✅ |

### 데이터 계약 정합 (gap-detector 검증)
- `ExcelData.to_dict()` = {file_id, filename, sheets:{name: SheetData.to_dict()}, metadata}
- `SheetData.to_dict()` = {sheet_name, data, columns, dtypes, row_count, column_count}
- `render_raw_source` 기대 키(filename, sheets[name].columns/data/row_count)와 정확히 일치 ✅

---

## 4. 핵심 설계 명제 검증

| 명제 | 판정 | 근거 |
|------|:----:|------|
| (a) charts 상태 채널 미러링 | ✅ | analysis_source도 리듀서 없는 list[dict](replace), _map_chain_end가 charts와 동형 캡처 |
| (b) raw budget 독립 → 기존 상한 불변 | ✅ (G1 조치 후) | build_snapshot 이중 budget(초기 성립) + **select_recent도 `_snapshot_sizes` kind별 분리(G1 수정)**. raw 없는 세션 완전 불변 |
| (c) 재주입/재분석 신규 배선 0 | ✅ | `_inject_snapshot_messages` 무변경, raw_source도 format_search_result→is_search_result→context 분기 재사용(T4) |

---

## 5. Gap 처리 결과

| # | Gap | 심각도 | 조치 | 상태 |
|---|-----|--------|------|:----:|
| G1 | `select_recent`이 raw+non-raw를 합산해 단일 `total_max_chars`로 컷 → Design §3.3 "kind별 분리" 불일치 | Medium | `_snapshot_sizes`(비-raw/raw 튜플) 추가 + select_recent 이중 budget 누적으로 수정. 회귀 테스트 2건 추가 | ✅ 해소 |
| G2 | 결과 텍스트 kind 라벨: 설계 `analysis_output` vs 코드 `excel` | Low | 코드가 진실(선행 analysis-data-continuity 유지) — Design/Plan/규칙 문서를 `kind="excel"`로 정정 | ✅ 해소 |
| G3 | 테스트 파일 배치가 Design §5(기존 파일 확장)와 상이 | Low | 커버리지 완전 — Design §5 파일명을 실제(`*_raw_source.py`)로 정정 | ✅ 해소 |

---

## 6. Plan §5 리스크 → Design §7 해소

| Plan 리스크 | 해소 | 결과 |
|-------------|------|:----:|
| 원천 크기 초과 | 행 샘플링 + raw 전용 budget + 총행수 표기 | ✅ |
| 원천 채널 파급 | charts 미러링, 미주입 시 `[]` | ✅ |
| PII 저장 증가 | 세션 스코프 + 크기 상한(마스킹은 후속) | ✅ |
| dict→str 억지 삽입 | 캡처 시점 압축 표 직렬화 | ✅ |
| "다른 사용자" 오인 | Plan/Report 명시 | ✅ |

---

## 7. Quality Metrics

- 아키텍처(Thin DDD): 스키마/상한/직렬화=domain, 캡처=application, 파싱=domain/infra ✅
- config 하드코딩 0: raw 상한 3종 settings 경유 ✅
- logger 규칙: 실패 시 logger.error(exception=e), print 없음 ✅
- graceful degrade(FR-06): 실패 시 None 반환 비중단 ✅

---

## 8. 잔여 (2%)

| 항목 | 사유 |
|------|------|
| 라이브 E2E 시나리오(턴1 엑셀 분석 → 턴2 "분기별로 다시" 재집계) | 단위/통합으로 로직 보증. 실 LLM+엑셀 첨부 필요 — 마이그레이션은 불필요(V039 재사용) |

---

## 9. 결론

Match Rate **98%** (Report 진행 가능). gap-detector가 짚은 G1(실질 불일치)을 코드로 해소하고
G2/G3(문서 정합)를 정정했다. 핵심 설계 명제 3건 모두 성립. 남은 것은 배포 후 실행 검증 1건.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-07-07 | gap-detector 93% + Gap 3건 | 배상규 |
| 0.2 | 2026-07-07 | G1 코드 수정(select_recent kind별 budget) + G2/G3 문서 정정 → 98% | 배상규 |
