# analysis-source-preservation Completion Report

> **Status**: Complete
>
> **Project**: sangplusbot (idt 백엔드)
> **Author**: 배상규
> **Completion Date**: 2026-07-07
> **PDCA Cycle**: #1
> **Design Match Rate**: 98%

---

## Executive Summary

### 1.1 Project Overview

| Item | Content |
|------|---------|
| Feature | analysis-source-preservation — 엑셀 분석 스냅샷에 파싱된 원천 데이터 병행 저장 |
| Start Date | 2026-07-07 |
| End Date | 2026-07-07 |
| Duration | 1 day |

### 1.2 Results Summary

```
┌──────────────────────────────────────────┐
│  Design Match Rate: 98%                  │
├──────────────────────────────────────────┤
│  ✅ Design Points: 6 / 6 (100%)          │
│  ✅ Requirements: 7 / 7 (100%)           │
│  ✅ Test Cases: 20 new tests (100%)      │
│  ⏳ Live E2E:     1 scenario pending      │
└──────────────────────────────────────────┘
```

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | 엑셀 분석 스냅샷이 분석 결과 텍스트(파생)만 저장하고 파싱된 원천 데이터(행/값)는 workflow 내부에서 계산 후 버림. 원본 파일도 TTL 1h 임시 업로드라 다음 턴엔 소실. 결과적으로 후속 턴이 "분기별로 다시", "다른 지표로" 재분석하려 해도 원천이 없어 재업로드 필수 상황 발생. |
| **Solution** | 엑셀 분기 `_run_excel_analysis`가 (text, raw) 튜플로 파싱된 구조화 데이터 반환 → analysis_node가 `kind="raw_source"`로 SupervisorState 채널(charts 동형)로 노출 → run_agent_use_case가 캡처 → _collect_snapshot이 병합. 원천은 압축 표 텍스트로 직렬화(행 샘플링+총행수 표기) + 6000/8000자 독립 budget. 재주입·재분석은 기존 경로 재사용(신규 배선 0). |
| **Function/UX Effect** | ✅ 턴1 엑셀 첨부로 분석 후 턴2에서 **원본 재업로드 없이** 동일 데이터로 다른 방식 재분석 가능(월별→분기별, 표→차트 유형 변경, 특정 열만 집계). D1~D6 6개 설계 항목 모두 100% 구현. 신규 테스트 20건 통과. Match Rate 98%(라이브 E2E만 pending). |
| **Core Value** | 멀티턴 엑셀 분석이 1회성 요약에서 **반복 재분석 가능한 워킹셋**으로 전환. "데이터가 소실되어 다시 올려야 한다"는 UX 불편 제거. 세션 스코프 + 크기 상한으로 PII 노출면도 제어. 스냅샷 원천+결과 병행으로 기존 표시 연속성 유지하면서 새로운 분석 지원. |

---

## 2. PDCA Cycle Summary

### 2.1 Plan

**Document**: [analysis-source-preservation.plan.md](../01-plan/features/analysis-source-preservation.plan.md)

- **Goal**: 엑셀 분기 스냅샷에 파싱된 원천 데이터(행/값)를 병합 저장해 후속 턴 재분석 가능 구조 설계
- **Key Decisions** (사용자 확인):
  - 원천 보존 형태: **파싱된 구조화 데이터**(행/값 JSON) — 파일 durable 보관 X
  - 결과 텍스트 처리: **원천+결과 병행 보관** — items에 `kind`로 구분(`raw_source` vs 기존)
  - 적용 범위: **엑셀 분기만** — 검색/MCP는 이미 원천 저장
  - PII: **세션 스코프 + 크기상한** — 마스킹은 pii-masking-integration 후속
- **Estimated Duration**: 1 day
- **Status**: ✅ Complete

### 2.2 Design

**Document**: [analysis-source-preservation.design.md](../02-design/features/analysis-source-preservation.design.md)

**Design Points** (모두 구현됨):

| 항목 | 내용 | 상태 |
|------|------|:----:|
| D1 — 원천 전달 채널 | SupervisorState.analysis_source 필드 + build_initial_state [] + _StreamState 캡처 + _map_chain_end 처리 | ✅ |
| D2 — 튜플 반환 | `_run_excel_analysis` → (text, raw\|None), `"sheets" in raw` 게이트 | ✅ |
| D3 — 정책 및 상한 | render_raw_source(압축표+샘플링+총행수) + kind별 독립 budget(raw 6000/8000, 기존 4000/8000) | ✅ |
| D4 — 병합 로직 | _collect_snapshot raw_source 병합, 결과 병행 유지, 재주입 무변경 | ✅ |
| D5 — Config/DI | config 3종(raw_source_max_chars/total/max_rows) + main.py 주입 | ✅ |
| D6 — 경로 재사용 + 규칙 | 신규 배선 0 + conversation-memory.md raw_source 조항 추가 | ✅ |

- **Key Architectural Decision**: charts 상태 채널 패턴 미러링 → state 채널로 data flow 관리, 메시지 오염 X
- **Status**: ✅ Complete

### 2.3 Do

**Implementation Scope**:

- `src/application/agent_builder/supervisor_state.py` — analysis_source 필드 추가
- `src/application/agent_builder/supervisor_nodes.py` — build_initial_state에 `"analysis_source": []`
- `src/application/agent_builder/workflow_compiler.py` — _run_excel_analysis 튜플 반환, analysis_node 방출
- `src/application/agent_builder/run_agent_use_case.py` — _StreamState/_map_chain_end 캡처, _collect_snapshot 병합
- `src/domain/conversation/analysis_snapshot_policy.py` — render_raw_source, build_snapshot kind별 budget, select_recent 분리
- `src/config.py` — analysis_snapshot_raw_source_* 3개 설정값
- `src/api/main.py` — DI: _make_analysis_snapshot_policy에 config 주입
- `docs/rules/conversation-memory.md` — raw_source 규칙 조항 추가
- **Test Files**: 신규 3파일 20건 케이스

**Actual Duration**: 1 day

**Deliverables**: 7 backend files (production) + 1 doc (conversation-memory.md) + 20 test cases

**Status**: ✅ Complete

### 2.4 Check

**Document**: [analysis-source-preservation.analysis.md](../03-analysis/analysis-source-preservation.analysis.md)

**Gap Analysis Results**:

| Metric | Initial | Final | Change |
|--------|---------|-------|--------|
| Design Match Rate | 93% | 98% | +5% |
| Design Point Coverage | 6/6 | 6/6 | 100% |
| Architecture Validation | 100% | 100% | ✅ |
| Test Coverage | 90% | 100% | +10% |

**Gap Resolution**:

| # | Gap | Severity | Resolution | Status |
|---|-----|----------|------------|:------:|
| G1 | `select_recent` kind별 budget 미분리 | Medium | `_snapshot_sizes` 추가, 이중 누적으로 수정 | ✅ |
| G2 | 결과 텍스트 kind 라벨 불일치 (analysis_output vs excel) | Low | 코드(excel) 기준으로 설계/계획 문서 정정 | ✅ |
| G3 | 테스트 파일 배치 (기존 확장 vs 신규 파일) | Low | Design 명세를 실제(`*_raw_source.py`)로 정정 | ✅ |

**Data Contract Validation**: ExcelData.to_dict() 키 정합(file_id, filename, sheets[name].columns/data/row_count) ✅

**Status**: ✅ Complete (98% match rate, 라이브 E2E pending)

### 2.5 Act

**Gap-Driven Improvements**:

- G1: `select_recent` 메서드가 kind별 budget을 분리하지 않던 문제 → `_snapshot_sizes()` helper 추가로 (non_raw_chars, raw_chars) 튜플 반환, 누적 로직 이중 처리
- G2/G3: 문서 정정으로 Design-Implementation 정합 확보

**Quality Assurance**:

- ✅ Thin DDD 아키텍처: 스키마/상한=domain, 캡처=application, 파싱=infrastructure 명확 분리
- ✅ Config 하드코딩 제거: raw_source 상한 3종 settings 경유
- ✅ Logger 규칙: 실패 시 logger.error(exception=e), print() 0건
- ✅ Graceful Degrade (FR-06): 실패 시 None 반환으로 기존 동작 유지

**Status**: ✅ Complete

---

## 3. Completed Items

### 3.1 Functional Requirements

| ID | Requirement | Status | Notes |
|----|----|--------|----|
| FR-01 | 엑셀 분기 턴 종료 시 파싱된 원천 데이터를 `kind="raw_source"`로 스냅샷에 저장 | ✅ | D2/D4 구현, T1/T2 테스트 |
| FR-02 | 기존 분석 결과 텍스트 선행 그대로(`kind="excel"`)로 병행 저장 | ✅ | analysis-data-continuity 동작 불변 |
| FR-03 | 후속 턴에서 원천 스냅샷이 재주입되어 `_analyze_context`가 데이터로 인식 | ✅ | T4 재주입 확인, 기존 경로 재사용 |
| FR-04 | 후속 턴 재분석("분기별/다른 지표") 시 원본 재업로드 없이 원천 기반 응답 | ✅ | context 분기 동작 검증 (라이브 E2E pending) |
| FR-05 | 원천 크기 초과 시 상한/샘플링 적용 + 절단 사실 명시 | ✅ | render_raw_source 행 샘플링, 총행수 표기 |
| FR-06 | 원천 캡처 실패/미주입 시 기존 동작으로 graceful degrade | ✅ | None 반환 시 스냅샷 비포함, 회귀 0 |
| FR-07 | `conversation-memory.md`에 raw_source 규칙 반영 | ✅ | 규칙 문서 개정 완료 |

### 3.2 Non-Functional Requirements

| Category | Criteria | Achieved | Status |
|----------|----------|----------|--------|
| 토큰/저장 | 원천 재주입 후 context ≤ raw budget(6000/8000) | ✅ | LangSmith 실측 후 재조정 가능 |
| 하위 호환 | 원천 없는 기존 스냅샷/세션은 현행 동일 | ✅ | analysis-data-continuity 회귀 통과 |
| 아키텍처 | Thin DDD: 스키마·상한=domain, 캡처=application, 파싱=infra | ✅ | 명확 분리, config 하드코딩 0 |
| 테스트 | 신규 로직 Red-first TDD | ✅ | 신규 20건 케이스, 모두 Green |

### 3.3 Deliverables

| 구분 | 항목 | 상태 |
|------|------|:----:|
| **Design** | D1~D6 설계 항목 (6/6) | ✅ |
| **Code** | Backend 7 files + config/DI | ✅ |
| **Tests** | 신규 20건(T1~T6) + 회귀 | ✅ |
| **Docs** | Plan + Design + Analysis + conversation-memory.md 개정 | ✅ |

---

## 4. Incomplete Items

### 4.1 Carried Over / Pending

| Item | Reason | Priority | Expected Effort |
|------|--------|----------|-----------------|
| **라이브 E2E 시나리오 (턴1 엑셀 → 턴2 재분석)** | 단위/통합으로 로직 보증. 실 LLM + 엑셀 첨부 필요 — 마이그레이션 불필요(V039 재사용) | High | 1 turn (배포 후) |

### 4.2 Out of Scope (Plan에서 제외)

| Item | Reason | Note |
|------|--------|------|
| 원본 파일 durable 보관 | 사용자 결정: 파싱 데이터만 | 세션 스코프 + 크기 상한으로 충분 |
| 검색/MCP 원천 저장 | 이미 저장 중 | analysis-data-continuity 기존 기능 |
| "다른 사용자" 데이터 확보 | 구조적 불가 | 본 기능은 보유 원천 재분석, 없는 데이터 확보 X |
| PII 마스킹 | pii-masking-integration 후속 | 세션 스코프 + 상한으로 현단계 대응 |
| 프론트엔드 변경 | 스냅샷은 LLM 컨텍스트 전용 | API 응답 스키마 불변 |

---

## 5. Quality Metrics

### 5.1 Final Analysis Results

| Metric | Target | Final | Status |
|--------|--------|-------|:------:|
| **Design Match Rate** | ≥ 90% | **98%** | ✅ |
| Design Point Coverage | 6/6 | 6/6 | ✅ |
| Test Coverage (신규) | 100% | **20/20 cases** | ✅ |
| Code Quality | config 하드코딩 0 | **0** | ✅ |
| Logger 규칙 | print() 없음 | **0 violations** | ✅ |
| Graceful Degrade | FR-06 검증 | **None 반환 시 비포함** | ✅ |
| Regression Tests | analysis-data-continuity + agent_builder | **All passing (격리 실행)** | ✅ |

### 5.2 Architecture Validation

| Component | Validation | Result |
|-----------|-----------|:------:|
| **Domain Layer** | AnalysisSnapshotPolicy: render_raw_source, build_snapshot (kind별 budget), select_recent (이중 누적) | ✅ Fully implemented |
| **Application Layer** | supervisor_state, supervisor_nodes, workflow_compiler, run_agent_use_case (캡처/병합) | ✅ Fully implemented |
| **Infrastructure Layer** | config.py (3개 설정값), main.py DI | ✅ Fully implemented |
| **State Channel Pattern** | charts 미러링: SupervisorState.analysis_source → _StreamState → _map_chain_end → _collect_snapshot | ✅ Complete |

### 5.3 Test Coverage Summary

| Test File | Suite | Cases | Coverage |
|-----------|-------|-------|:--------:|
| `test_analysis_snapshot_raw_source.py` (신규) | policy: render_raw_source, build_snapshot(raw budget), select_recent(kind별 분리) | 10 | ✅ |
| `test_analysis_node_raw_source.py` (신규) | analysis_node: excel 분기 방출, context 분기 미포함 / _run_excel_analysis 튜플 반환 | 6 | ✅ |
| `test_run_agent_raw_source.py` (신규) | _map_chain_end 캡처, _collect_snapshot 병합, 재주입 | 4 | ✅ |
| Regression | analysis-data-continuity, agent_builder, general_chat (격리 실행) | all passing | ✅ |
| **Total (신규)** | | **20** | **100%** |

> 교차 실행 시 나타나는 Windows 이벤트 루프 teardown 산발 error는 격리 실행으로 전부 통과 확인(알려진 환경 이슈, 실제 회귀 아님).

---

## 6. Lessons Learned & Retrospective

### 6.1 What Went Well (Keep)

- **Design-first approach**: Plan에서 사용자 결정 4건을 먼저 확보 → Design이 명확하고 구현이 신속함
- **State channel 패턴 재사용**: charts 동형으로 미러링 → 신규 그래프 배선 0으로 낮은 리스크
- **Kind별 budget 분리**: raw_source가 기존 상한을 잠식하지 않도록 설계 → analysis-data-continuity 회귀 안전
- **Gap-detector + 협업 정정**: 초기 93% → 실질 불일치(G1) 코드로 해소, 문서 정합(G2/G3) 빠른 정정 → 최종 98%
- **Graceful degrade 우선**: 캡처/파싱 실패 시 None 반환 → 기존 동작 유지(FR-06)

### 6.2 What Needs Improvement (Problem)

- **라이브 E2E만 pending**: 단위/통합 테스트로는 완전히 보증하기 어려운 LLM+엑셀 첨부 시나리오 → 배포 후 실 서버에서 1턴 검증 필수
- **PII 마스킹 미흡**: 원천 데이터에 민감 정보가 포함될 수 있으나 현단계는 세션 스코프+상한만 적용 → pii-masking-integration 의존

### 6.3 What to Try Next (Try)

- **멀티시트 대용량 데이터 실험**: render_raw_source의 샘플링 임계(max_rows=200)가 실제 분석 복구에 충분한지 라이브 데이터로 검증
- **재분석 패턴 수집**: 턴2 이상에서 사용자가 어떤 재분석을 요청하는지(월별→분기별, 특정 열만 등) 메트릭 수집 → 향후 UX 개선
- **성능 프로파일링**: 원천 직렬화/재주입 후 context 크기 증가 → 실제 토큰 비용 LangSmith로 추적

---

## 7. Next Steps

### 7.1 Immediate (배포 직전)

- [ ] **라이브 E2E 시나리오 검증** (1턴): 실 서버 턴1 엑셀 첨부 분석 → 턴2 "분기별로 다시"(첨부 X) → 원천 재집계 확인 + LangSmith context/토큰 측정
- [ ] **배포**: V039 마이그레이션은 이미 적용됨(선행 analysis-data-continuity). 본 기능은 추가 마이그레이션 불필요

### 7.2 Next PDCA Cycles

| Item | Priority | Trigger |
|------|----------|---------|
| **pii-masking-integration** | High | 원천 데이터 PII 노출 가능성 → 세션 가시성 문제 발생 시 |
| **멀티시트 성능 최적화** | Medium | 대용량 엑셀(1000+ 행)에서 토큰 비용 초과 발생 시 |
| **재분석 UX 패턴 수집** | Medium | 2주 운영 후 사용자 재분석 요청 패턴 분석 → UI/가이드 개선 |

---

## 8. Related Features & Dependencies

### 8.1 Upstream Dependencies

| Feature | Status | Impact |
|---------|--------|--------|
| **analysis-data-continuity** | ✅ Complete (96% match) | 스냅샷 인프라 및 재주입 경로 재사용 — 본 기능의 기반. V039 컬럼 공유 |

### 8.2 Downstream / Co-Dependent

| Feature | Status | Impact |
|---------|--------|--------|
| **pii-masking-integration** | 📋 Pending | 원천 데이터 보호 강화 (선택적) |

---

## 9. Changelog

### v1.0.0 (2026-07-07)

**Added:**
- 엑셀 분기 원천 데이터(`ExcelData.to_dict()`) → 스냅샷 `kind="raw_source"` 저장
- SupervisorState.analysis_source 채널 (charts 동형 state pattern)
- `_run_excel_analysis` (text, raw) 튜플 반환 및 analysis_node 방출
- `AnalysisSnapshotPolicy.render_raw_source()` — 압축 표 텍스트 직렬화(행 샘플링 + 총행수 표기)
- 원천 전용 budget (raw_source_max_chars/total_max_chars/max_rows)
- `_snapshot_sizes()` helper — kind별 budget 이중 누적 (기존 상한 불변)
- `_collect_snapshot()` 원천 병합 로직
- config 3개 설정값 (analysis_snapshot_raw_source_*)
- main.py DI: _make_analysis_snapshot_policy에 raw 설정값 주입
- 신규 테스트 20건 (policy, analysis_node, run_agent)
- conversation-memory.md raw_source 규칙 조항

**Changed:**
- `AnalysisSnapshotPolicy` 초기화: raw 관련 파라미터 추가
- `supervisor_state.py` SupervisorState: analysis_source 필드
- `run_agent_use_case._StreamState`: analysis_source 캡처 필드 + `_map_chain_end` 캡처 로직

**Fixed:**
- (G1) `select_recent`의 kind별 budget 미분리 → `_snapshot_sizes` 추가로 이중 누적

---

## 10. Verification Checklist

- [x] **Design Point Coverage**: D1~D6 모두 구현 (6/6 = 100%)
- [x] **Requirement Coverage**: FR-01~FR-07 모두 만족 (7/7 = 100%)
- [x] **Test Coverage**: 신규 테스트 20건 + 회귀 모두 통과(격리 실행)
- [x] **Architecture**: Thin DDD 명확 분리 (domain/application/infrastructure)
- [x] **Code Quality**: config 하드코딩 0, logger.error 규칙, graceful degrade
- [x] **Backward Compatibility**: 원천 없는 기존 세션/스냅샷 동작 불변
- [x] **Documentation**: Plan/Design/Analysis/Report/conversation-memory.md 완성
- [x] **Data Contract**: ExcelData.to_dict() 키 정합 검증
- [ ] **Live E2E**: 라이브 서버 턴2 재분석 시나리오 (배포 후)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-07-07 | Feature Completion Report: analysis-source-preservation (98% match, 20 tests, D1~D6 완성) | 배상규 |
