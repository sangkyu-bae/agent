# Gap Analysis: excel-analysis-routing-cleanup

> Analysis Date: 2026-06-06 | Phase: Check (PDCA)
> Design: `docs/02-design/features/excel-analysis-routing-cleanup.design.md`
> Plan: `docs/01-plan/features/excel-analysis-routing-cleanup.plan.md`

---

## Overall Scores

| Category | Score | Status |
|----------|:-----:|:------:|
| Design Match | 100% | OK |
| Architecture Compliance (Thin DDD) | 100% | OK |
| Convention Compliance | 100% | OK |
| **Overall Match Rate** | **100%** | OK |

설계와 구현이 완전히 일치. 7개 검증 포인트 전부 충족, Gap(누락/추가/변경) 없음.

---

## Verification Points (설계 §3, §7 기준)

| # | 검증 포인트 | 결과 | 근거 |
|---|-------------|:----:|------|
| 1 | 코드 생성/실행 경로 완전 제거 | PASS | `excel_analysis_workflow.py`에 `execute_code` 노드, `needs_code_execution`/`code_to_execute`/`code_output` 상태, `_execute_code_node`/`_detect_code_in_response`/`_extract_code` 메서드 모두 부재 |
| 2 | 완료 경로 chart_router 일원화 | PASS | `_should_retry_or_complete`는 `{retry, complete}`만 반환; `execute` 분기 없음. 엣지 `evaluate→{retry:web_search, complete:chart_router}`, `chart_router→END` |
| 3 | structured 검색 판단 전환, [SEARCH] 파싱 제거 | PASS | `_should_search`는 `state["needs_web_search"]` bool만 읽음; `SearchDecisionInterface.decide`로 산출; 전역 `[SEARCH]` 파싱 부재 |
| 4 | 첫 검색 전 1회만 결정 호출 (Q2) | PASS | `if not web_results:` 가드로 `web_search_results` 미존재 시에만 `decide` 호출. 테스트가 `decide.assert_not_awaited()` 검증 |
| 5 | SandboxExecutor/python_code_executor 유지 (Q3) | PASS | `sandbox_executor.py` 존속, `code_executor_tool.py`+`tool_registry.py`에 `python_code_executor` 정식 등록 유지. 워크플로우 의존만 제거 |
| 6 | DDD 레이어 준수 (domain→infra 역참조 없음) | PASS | `domain/search_decision/{schemas,interfaces}.py`는 `abc`/`pydantic`/자기 스키마만 import |
| 7 | 연쇄 정리 누락 여부 | PASS | `src/`·`tests/` 전역 잔여 코드 필드 참조 0건 |

---

## Differences Found

- **Missing (Design O, Impl X)**: 없음
- **Added (Design X, Impl O)**: 없음 (SandboxExecutor 등 §3-6 비변경 항목은 의도적 유지)
- **Changed (Design ≠ Impl)**: 없음

---

## Detailed Verification

**신규 파일 (5/5 일치)**:
- `domain/search_decision/schemas.py` — `WebSearchDecision`(needs_web_search 필수 `...` + reason 기본 "")
- `domain/search_decision/interfaces.py` — `decide(question, analysis_text, request_id)` 시그니처 일치
- `infrastructure/search_decision/adapter.py` — `with_structured_output(WebSearchDecision)` + 예외 시 False graceful + `logger.error(exception=, request_id=)`
- `tests/domain/search_decision/test_schemas.py`, `tests/infrastructure/search_decision/test_adapter.py`

**수정 파일 (8/8 정리 완료)**:
- `excel_analysis_workflow.py` — 코드 노드/상태/메서드 제거, 생성자 `code_executor`→`search_decision` 교체
- `analyze_excel_use_case.py` — initial_state 코드 필드 3개 제거, `_build_result` 코드 인자 제거, langsmith를 use_case로 이동
- `analysis_result.py` — `executed_code`/`code_output` 필드 제거
- `analysis_router.py` — `AnalysisResponse` 코드 필드 제거, langsmith 호출 제거(application으로 이동)
- `main.py` — `LLMSearchDecisionAdapter` DI, SandboxExecutor 제거
- `workflow_compiler.py` — `_run_excel_analysis` initial dict 정리(`viz_decision:""` 추가), 출력 `analysis_text`만 소비(Q4 일치)
- `analysis_policy.py` — `AnalysisStatus`에서 `code_executing` 제거
- 테스트 4종 — `_should_retry_or_complete`, structured 분기, chart_router 통합 테스트 추가, 코드 필드 참조 0건

**잔여 참조 스캔**: `src/`/`tests/` 코드 필드 참조 0건. 잔존 매치 2건은 무관/의도적 — `src/claude/task/task-excel-analysis-agent.md`(구 task 명세 문서, 코드 아님), `sandbox_executor.py`의 `_execute_code`(유지 대상 내부 메서드, Q3).

---

## Architecture & Convention

- **Thin DDD**: domain은 외부 의존 없음, application은 인터페이스에만 의존, infra가 LangChain 구현 — 의존 방향 준수
- **CLAUDE.md §3/§6**: 명시적 타입, config 하드코딩 없음, 어댑터 예외 시 `logger.error(exception=e)` 스택 포함, `print()` 미사용
- **Data Flow §4**: 3개 시나리오 모두 충족, 검색 결정 LLM 호출 시나리오당 최대 1회 (Q2)

---

## Test Results (격리 실행, Windows 이벤트 루프 flakiness 회피)

- search_decision 신규 테스트 5건 PASS
- `test_excel_analysis_workflow.py` 14건 PASS
- `test_analyze_excel_use_case.py` + `test_analysis_router.py` 11건 PASS
- `test_analysis_result.py` PASS
- supervisor 재사용 회귀 `test_workflow_compiler.py` + `test_analysis_node.py` 34건 PASS

---

## Recommended Actions

- **Immediate**: 없음 (Match Rate 100%, Gap 없음)
- **Cross-Project (잔여)**: 프론트(`idt_front`)가 `/api/v1/analysis/excel` 응답의 `executed_code`/`code_output` 참조 여부 — 검증 결과 **미참조 확인**(grep 0건). `/api-contract-sync` 추가 조치 불필요
- **Documentation (선택)**: `src/claude/task/task-excel-analysis-agent.md`는 구 구현 명세로 현 구현과 불일치 — deprecated 표기 권장 (코드 영향 없음)
- **Next**: Match Rate ≥ 90% → `/pdca report excel-analysis-routing-cleanup`. 후속 N1(chart_router → ChartBuilder 실제 빌드)은 별도 Plan

---

## Match Rate 산정

검증 포인트 7/7 PASS = **100%**. 신규 5/5 + 수정 8/8 정리 완료. 누락 0 / 추가 0 / 변경 0. DDD·Convention 위반 0건.
