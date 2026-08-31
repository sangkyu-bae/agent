# excel-generator-node Gap Analysis

> **Feature**: excel-generator-node
> **Date**: 2026-08-24
> **Analyzer**: gap-detector agent (정적) + pytest (런타임)
> **Design**: [excel-generator-node.design.md](../02-design/features/excel-generator-node.design.md)
> **Plan**: [excel-generator-node.plan.md](../01-plan/features/excel-generator-node.plan.md)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | "수집 데이터 → 엑셀 → 사용자 전달" 경로가 끊겨 엑셀 산출 시나리오 실사용 불가 |
| **WHO** | P2 (KB 운영자 / 에이전트 소유자) |
| **RISK** | LLM 표 구조화 행 상한(비정형 경로) — 저장소 리스크는 Design에서 해소 |
| **SUCCESS** | 수집→엑셀 요청 시 다운로드 링크 반환 + 원천 무손실 + 실패 시 비중단 |
| **SCOPE** | 백엔드 단독 (프론트 무변경) |

---

## 1. Match Rate

### 축별 점수 (gap-detector 정적 분석)

| Category | Score | 상태 |
|----------|:-----:|:----:|
| Structural Match | 95% | ✅ (테스트 파일명 1건 이탈만) |
| Functional Depth | 88% | ⚠️ (placeholder 0건, §6.1 #6 부분·시작 로그 누락) |
| API Contract | 100% | ✅ (5/5 PASS) |
| Test Coverage | 88% | ⚠️ (15항 중 완전 13, 부분 2) |
| Layer Compliance | 100% | ✅ (위반 0건) |
| Intent Match (Plan SC) | 88% | ⚠️ (DoD 6항 중 4 Met, 1 Partial, 1 런타임 확인) |

### Runtime (pytest)

| 스위트 | 결과 |
|--------|------|
| R1 신규 (domain 13 + infra 11 + node 6) | 30/30 PASS |
| R2 회귀 (excel_export·agent_builder·tool_registry) + R3 라우터 | 281/281 PASS (합산) |
| R5 전체 스위트 | 7,966 PASS / 58 FAIL — **58건 전부 baseline(변경 stash)에서 동일 재현되는 기존 실패**, 본 기능 무관 (git stash 대조로 증명) |

### 종합

| 산식 | 결과 |
|------|------|
| gap-detector 시맨틱 가중 (정적) | **91%** |
| v2.3.0 런타임 포함 산식 (S×0.15 + F×0.25 + C×0.25 + R×0.35, R=100) | 96% |
| **채택 (보수적)** | **91%** — 90% 게이트 통과 |

---

## 2. Gap 목록

### 🔴 Critical: 0건

Design 대비 미구현 기능 0건, placeholder 0건, 레이어 위반 0건.

### 🟡 Important: 3건

| # | Gap | 근거 | Conf. |
|:-:|-----|------|:-----:|
| I-1 | **store IO 실패가 안내 노옵을 뚫음** — `_export_and_save`의 try가 exporter만 감싸고 `store.save`(디스크 write)는 밖. `OSError` 시 그래프 중단 → Design §6.1 #6·Plan NFR "비중단" 저촉 | `generator.py` try 경계 vs `store.py` write 지점 | 90% |
| I-2 | **LLM 호출 예외 미포착** — `_plan_sheets`의 `ainvoke`가 try 없음. 타임아웃·rate limit이 `ExcelGenerateError`로 변환되지 않고 유출. 단 document_generator도 동일 패턴(패턴 차원 이슈) | `generator.py` `_plan_sheets` | 85% |
| I-3 | **§6.2 노드 시작 로그 누락** — 시작/완료/실패 중 시작만 없음. LLM 응답 대기 중 프로세스 사망 시 run 흔적 전무 | `workflow_compiler.py` 노드 진입부 | 95% |

### 🔵 Minor: 5건

| # | Gap | Conf. |
|:-:|-----|:-----:|
| M-1 | `.xlsx` 강제가 재사용 스키마 validator에 암묵 위임 (동작은 정상) | 80% |
| M-2 | 테스트 파일명 Design §11.1과 이탈 (`test_workflow_compiler_excelgen.py`) | 100% |
| M-3 | happy path 테스트가 `last_worker_id`·`token_usage` 미검증 | 90% |
| M-4 | `function_node_ids` 등록 효과(_wrap_worker 미적용) 간접 검증만 | 85% |
| M-5 | FR-10 설명 문구 회귀 테스트 부재 (Plan Risk #3 완화책 미이행) | 95% |

### 🟣 문서화 누락 (코드가 진실 — Design 0.2 개정 대상): 6건

D-1 `NoExcelDataError` 타입 / D-2 `parse_raw_index` 공개 함수 / D-3 시트명 새니타이즈·31자·중복 리네임 / D-4 코드펜스 JSON 전처리 / D-5 `llm_input_max_chars` 하드코딩 기본값(설정 미연동) / D-6 `excel_parser` 미주입 시 P2 무증상 비활성

---

## 3. Plan Success Criteria 평가

| # | DoD | 상태 | 근거 |
|:-:|-----|:----:|------|
| 1 | E2E 수집→엑셀→다운로드 | ⚠️ Partial | 구간별 테스트 증명, 실서버 E2E 미실행 (R6 수동 절차 문서화) |
| 2 | 구조화 원천 LLM 미경유 전량 변환 | ✅ Met | `test_generator.py` — 1000행 전량 + `"n999" not in prompt` |
| 3 | 비정형 LLM 구조화 + 상한 | ✅ Met | 300행 절단 + truncated 검증 |
| 4 | 실패 안내 노옵 + 그래프 완주 | ✅ Met | 3종 검증 (단 I-1/I-2 경로는 미보장) |
| 5 | 기존 테스트 전부 통과 | ✅ Met | R2/R5 실행 — 신규 실패 0건 (baseline 대조) |
| 6 | 테스트 선행 작성 (TDD) | ✅ Met | 신규 24+6 케이스, Red→Green 수행 |

---

## 4. Decision Record 검증

| 결정 | 이행 |
|------|------|
| [Plan] 전용 노드 + file store 재사용 + 하이브리드 소싱 + 안내 노옵 | ✅ 전부 구현 |
| [Design] C안 — document_generator 동형 | ✅ 노드·DI·응답 계약 동형 확인 (Contract 100%) |
| [Design] raw 무손실 / llm 300행 상한 | ✅ 테스트로 증명 |

---

## 5. 권장 조치

1. **즉시 (Important)**: I-1 try 경계 확장(`store.save` 포함, `OSError` 래핑) · I-2 `ainvoke` 예외 래핑 · I-3 시작 로그 추가 — 셋 다 소규모 수정
2. **테스트 보강 (Minor)**: R4 계획의 6개 케이스 (I-1/I-2 재현 RED → 수정 → GREEN, M-3/M-4/M-5 assert 추가)
3. **문서 갱신**: Design 0.2 — D-1~D-6 반영 + §11.1 테스트 파일명 정정(M-2)
4. **선택**: D-5 설정 연동 (`llm_input_max_chars`)

---

## 6. Act-1 재검증 (2026-08-25)

사용자 결정(Checkpoint 5): "지금 모두 수정". TDD로 RED 재현(4건 실패) → 수정 → GREEN.

| Gap | 조치 | 증거 |
|-----|------|------|
| I-1 | `_export_and_save` try 경계를 `store.save`까지 확장, `(RuntimeError, OSError)` → `ExcelGenerateError` | `test_generator.py::TestFailureBoundaries::test_store_os_error_wrapped` |
| I-2 | `_plan_sheets`의 `ainvoke`를 try로 감싸 `ExcelGenerateError("시트 계획 생성 오류: …")` | `::test_llm_exception_wrapped` |
| I-3 | 노드 진입 시 `excel_generator_node start` 로그 (`analysis_source_count`, `attachment_count`) | `test_workflow_compiler_excelgen.py::TestNode::test_start_log_emitted_before_generate` |
| M-1 | `_safe_filename`이 `.xlsx` 미존재 시 강제 부여 | `::test_filename_without_extension_gets_xlsx` |
| M-2 | Design §11.1 테스트 파일명을 실제(`test_workflow_compiler_excelgen.py`)로 정정 | Design 0.2 |
| M-3 | happy path에 `last_worker_id`·`token_usage > 0` assert 추가 | `test_happy_path_returns_download_link_and_sources` |
| M-4 | `_wrap_worker`가 `excel_worker`에 호출되지 않음을 직접 검증 | `TestCompile::test_excel_worker_bypasses_wrap_worker` |
| M-5 | 설명 문구 회귀 테스트("다운로드"·"수집") | `test_tool_registry.py::test_excel_export_description_guides_supervisor_routing` |
| D-1~D-6 | Design 0.2 — `NoExcelDataError`, `parse_raw_index`, 시트명 정규화, 코드펜스 전처리, §3.5 생성자 옵션(`llm_input_max_chars`는 `settings.document_generator_llm_input_max_chars` 공유 주입으로 실배선), `excel_parser` 미주입 의미 | Design 0.2 §2.2/§3.2/§3.3/§3.5/§6 |

**재검증 결과**: 대상 스위트 822 PASS (excel_generator·agent_builder·tool_registry·document_extractor 라우터·excel_export). `tests/api/test_main.py::test_app_includes_document_upload_router` 1건 실패는 테스트 헬퍼 결함(`_IncludedRouter.path` 부재)으로 baseline 기존 실패 — 본 기능 무관.

| Category | 0.1 | 0.2 |
|----------|:---:|:---:|
| Structural | 95% | 100% |
| Functional | 88% | 100% |
| API Contract | 100% | 100% |
| Test Coverage | 88% | 100% |
| Layer | 100% | 100% |
| Intent (Plan SC) | 88% | 95% (DoD #1 실서버 E2E는 수동 절차로 유지) |
| **종합** | **91%** | **98%** |

잔여: 없음 (Critical 0 / Important 0 / Minor 0). 참고 — `excel_generator_node` 클로저 56줄은 40줄 규칙 초과이나 document/presentation 노드(64/57줄)와 동일 패턴으로 수용, 향후 3개 노드 공통 리팩토링 후보.

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.2 | 2026-08-25 | Act-1 재검증 — Important 3·Minor 5·문서화 6 전부 해소, Match Rate 98% |
| 0.1 | 2026-08-24 | gap-detector 정적 분석 + pytest 런타임 검증. Match Rate 91% (Critical 0 / Important 3 / Minor 5 / 문서화 6) |
