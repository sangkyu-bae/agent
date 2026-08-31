# Deep Search Pipeline Completion Report

> **Feature**: deep-search-pipeline
> **Project**: sangplusbot (idt 백엔드)
> **Period**: 2026-08-25 ~ 2026-08-26
> **Match Rate**: 97% (목표 90%)
> **Status**: ✅ 구현·검증 완료 / ⚠️ 실운영 품질 미측정
> **Author**: 배상규

---

## Executive Summary

### 1.1 Project Overview

기존 search 워커는 복잡한 질문도 **검색 쿼리 1개**로 압축하고, 재시도 루프가 근거를 **누적이 아닌 교체**로 처리해 다축 질문에서 일부 축의 근거가 구조적으로 유실됐다. 이를 해결하기 위해 `요구 분해 → 병렬 검색 → 근거 누적 → 커버리지 검증 → 부족분만 선택적 재검색` 상태머신을 **독립 모듈**로 신설하고, 기존 파이프라인은 손대지 않은 채 config 플래그로 교체 가능하게 배선했다.

### 1.2 Results Summary

| 지표 | 값 |
|------|-----|
| Match Rate | **97%** (Act 전 93%) |
| PDCA 반복 | 1회 (Important 2건 해소) |
| 신규 프로덕션 코드 | 1,078줄 (9개 파일) |
| 기존 파일 수정 | **36줄** (3개 파일) |
| `search_pipeline.py` 변경 | **0줄** |
| 신규 테스트 | **136 passed** |
| 전체 회귀 | **0** (FAILED 목록 4회 측정 불변) |
| 설계 결정 준수 | **20/20** |

### 1.3 Value Delivered

| 관점 | 결과 |
|------|------|
| **Problem** | "A와 B의 X" 질문이 `"A B X"` 한 줄로 뭉개지고, validate 루프가 `text`를 덮어써(`search_pipeline.py:269`) 이전 근거를 폐기하던 결함을 해소 |
| **Solution** | 5노드 LangGraph 서브그래프. 루프 기준을 "검색 횟수"에서 **"채워진 fact slot 수"**로 전환. `test_l3_1`이 "1회차에 r1만 충족 → 2회차는 r2만 검색"을 코드로 고정 |
| **Function/UX Effect** | 각 축의 근거가 독립 확보되고 확보분은 재검색하지 않는다. `single` 질문은 LLM 3콜로 legacy(≤4) 이하 유지 |
| **Core Value** | LLM 자유 재귀가 아닌 **상태머신 + 4중 종료 + 예산 상한**이라 최악 비용이 정적으로 계산된다(iterative 최악 LLM 9콜·검색 6회). 롤백은 환경변수 한 줄 |

---

## 1.4 Success Criteria Final Status

| # | 기준 | 상태 | 근거 |
|---|------|:----:|------|
| 1 | `mode=legacy`에서 기존 테스트 전량 통과 (FAILED diff 0) | ✅ | 4회 측정 전부 58건 동일, 8,180 → 8,255 passed |
| 2 | "A와 B의 X"에서 requirement 2개·독립 쿼리 2개 | ✅ | `test_l2_1_decomposes_comparison_question` |
| 3 | 2회차에 충족 requirement 쿼리 미발행 | ✅ | `test_l3_1`, `test_l3_1b` |
| 4 | 4중 종료 조건 독립 단위 테스트 | ✅ | `test_l1_1`~`test_l1_5` + 우선순위 3건 |
| 5 | `single` 경로 LLM 호출 ≤ legacy(4) | ✅ | `test_l3_2`(3콜) + **코드 가드** `_cap_single_strategy` (D20) |
| 6 | Analyzer/Planner 실패 시 폴백, 예외 미전파 | ✅ | `test_l2_3`, `test_plan_failure_still_searches_once` |
| 7 | `is_search_result()` 식별 + `final_answer` 소비 | ⚠️ | 식별 검증(`test_l3_4`). **`final_answer` 통합 테스트 없음** → 이월 |
| 8 | 미충족 requirement 본문 표시 | ✅ | `test_l2_13_marks_missing_requirements` |
| 9 | `verify-architecture`/`logging`/`tdd` 통과 | ⚠️ | 동등 grep 검사로 대체. 스킬 미실행 → 이월 |

**7/9 완전 충족 (78%), 2/9 부분 충족, 0 미충족.**

---

## 1.5 Decision Record Summary

| 출처 | 결정 | 준수 | 결과 |
|------|------|:----:|------|
| [Plan] | 배선을 **config 전역 플래그**로 (AD-2) | ✅ | 기존 파일 변경 36줄로 억제. 롤백 한 줄 |
| [Plan] | 1단계 **웹검색 한정** (AD-3) | ✅ | 컴파일러 분기가 강제 — `internal_document_search`는 플래그 무관 legacy |
| [Plan] | **Evidence만 반환**, 답변은 `final_answer` (AD-4) | ✅ | 이중 답변 위험 회피 |
| [Plan] | **일반형 스키마** `description + constraints` (AD-5) | ✅ | 코어 분기문에 도메인 어휘 0건 |
| [Design] | **Option C** 5노드 (Analyzer+Planner, Evaluator+Replanner 통합) | ✅ | iterative 최악 9콜 — Option B(14콜) 대비 36% 절감 |
| [Design] | EvidenceStore를 **노드가 아닌 reducer**로 (D5) | ✅ | 빈 홉 제거. 단 리듀서 2-arg 계약 제약 발견(D14) |
| [Design] | `NO_GAIN`은 **iteration≥2부터** (D3) | ✅ | 1회차 무수확에서 전략 전환 기회 보존 |
| [Design] | extract 실패 시 **Evidence 미생성** (D6) | ✅ | 환각 방지 우선. E6 raw 폴백으로 legacy 수준 보장 |
| [Check] | `single`을 **코드로 강제** (D20) | ✅ | Gap G-01 대응 — 프롬프트 의존 제거 |

**설계 이탈 0건.** 구현 중 확정된 결정 8건(D12~D19)은 전부 문서에 역반영했다.

---

## 2. Related Documents

| 문서 | 경로 | 버전 |
|------|------|------|
| Plan | `docs/01-plan/features/deep-search-pipeline.plan.md` | v1.2 |
| Design | `docs/02-design/features/deep-search-pipeline.design.md` | v1.3 |
| Analysis | `docs/03-analysis/deep-search-pipeline.analysis.md` | v1.1 |
| PRD | 없음 (PM 단계 미수행) | — |

---

## 3. Completed Items

### 3.1 Functional Requirements

| FR | 요구 | 상태 |
|----|------|:----:|
| FR-01 | strategy `single/parallel/iterative` 판정 | ✅ |
| FR-02 | `single` 시 분해 생략, legacy 이하 비용 | ✅ (D20 코드 가드) |
| FR-03 | Requirement[]·SearchQuery[] 분리 산출, 일반형 스키마 | ✅ |
| FR-04 | 병렬 검색 + 개별 예외 격리 | ✅ |
| FR-05 | Evidence 구조화, source 필수 | ✅ |
| FR-06 | iteration 간 누적·병합·중복 제거 | ✅ |
| FR-07 | requirement별 충족 판정 + constraints 검증 | ✅ |
| FR-08 | 미충족만 재쿼리, 전략 전환, `can_retry` | ✅ |
| FR-09 | 4중 종료 조건 | ✅ |
| FR-10 | 예산 상한 4종 | ⚠️ 3/4 (토큰 상한 미구현) |
| FR-11 | 전 LLM 단계 graceful fallback | ✅ |
| FR-12 | 반환 계약 동일 | ✅ |
| FR-13 | config 플래그 + 안전 폴백 | ✅ |
| FR-14 | step summary 관측 | ✅ |
| FR-15 | requirement별 그룹 + source 보존 | ✅ |
| FR-16 | 미확보 표시 | ✅ |

**15/16 완전 충족 (94%).**

### 3.2 Non-Functional Requirements

| NFR | 기준 | 실측 | 상태 |
|-----|------|------|:----:|
| NFR-01 | domain에 LangChain/LLM 참조 금지 | import 0건 | ✅ |
| NFR-02 | iterative 최악 LLM ≤12, 검색 ≤10 | 9 / 6 | ✅ |
| NFR-03 | `legacy` 모드 무회귀 | FAILED diff 0 | ✅ |
| NFR-04 | 함수 40줄 / if 중첩 2단계 / `print()` 금지 | 위반 0건 | ✅ |
| NFR-05 | 구조화 로깅 + 스택 트레이스 | `logger.error(exception=e)` 3/3 | ✅ |
| NFR-06 | TDD 선행 | 4개 모듈 전부 Red→Green 확인 | ✅ |
| NFR-07 | 도메인 어휘 코어 하드코딩 금지 | 분기문 0건 | ✅ |

### 3.3 Deliverables

| 계층 | 파일 | 줄 |
|------|------|----|
| domain | `schemas.py`, `policies.py`, `__init__.py` | 269 |
| application | `llm_schemas.py`, `prompts.py`, `rendering.py`, `nodes.py`, `workflow.py`, `__init__.py` | 809 |
| 배선(수정) | `config.py` +6, `main.py` +2, `workflow_compiler.py` +31 | 39 |
| 테스트 | 6개 파일 (L0 16 / L1 38 / L2 47 / L3 35) | 1,779 |

**활성화**: `.env`에 `SEARCH_PIPELINE_MODE=deep` (기본값 `legacy`)

---

## 4. Incomplete Items

### 4.1 Carried Over to Next Cycle

| ID | 항목 | 사유 | 권고 |
|----|------|------|------|
| **G-05** | FR-10 토큰 상한 미구현 | 예산 4종 중 3종만 구현. supervisor `token_limit`이 런 전체는 방어하나 서브그래프 내부 폭주는 못 막음 | `DeepSearchBudgetPolicy`에 추가하거나 FR-10에서 항목 제거 후 위임 명시 |
| **G-03** | `final_answer` 통합 테스트 부재 | 반환 계약 동일성으로 추론했을 뿐 실제 소비 경로 미검증 | 통합 테스트 1건 |
| **G-04** | `verify-*` 스킬 3종 미실행 | 동등 grep 검사로 대체 | 절차상 실행 |

### 4.2 Cancelled/On Hold Items

| 항목 | 사유 |
|------|------|
| `internal_document_search` 적용 | 결과 포맷(청크)이 웹(XML)과 달라 Extractor 검증 부담 2배. 웹 실측 후 별도 사이클 |
| 모듈 내 AnswerGenerator | `final_answer`와 책임 중복 → 이중 답변 위험 (AD-4) |
| `multi_query` 모듈 통합·폐기 | 별개 자산. 본 사이클 범위 밖 |

---

## 5. Quality Metrics

### 5.1 Final Analysis Results

| 축 | Act 전 | Act 후 |
|----|:------:|:------:|
| Structural | 100% | 100% |
| Functional | 90% | 94% |
| Contract | 96% | 99% |
| **Overall** | **93%** | **97%** |

### 5.2 Resolved Issues

| ID | 심각도 | 내용 | 해결 |
|----|--------|------|------|
| **D19** | **운영 장애** | OpenAI 400 — `dict[str,str]`이 strict structured outputs와 비호환 | LLM 경계를 key/value 목록으로 교체. 도메인 타입 불변 |
| **G-01** | Important | `strategy="single"`인데 requirement N개면 그대로 팬아웃 | `_cap_single_strategy` 코드 가드 (D20) |
| **G-02** | Important | Plan §4.2 `≤10줄` 기준과 실측 `+31줄` 충돌 | 실측 기반 `≤35줄`로 정정 |
| **D14** | 구현 차단 | LangGraph 리듀서가 3-arg 시그니처 거부 | `merge_evidence` 2-arg 고정 |
| **D16** | 계약 파손 위험 | `runtime-datetime-context`가 legacy 시그니처 변경 | `datetime_block` 수용 + `inspect.signature` 비교 테스트 |

---

## 6. Lessons Learned & Retrospective

### 6.1 What Went Well (Keep)

- **교체 대기 전략이 유효했다.** `search_pipeline.py` 0줄 수정을 최우선 기준으로 잡은 덕에, 4번의 전체 회귀에서 FAILED 목록이 한 건도 변하지 않았다. 롤백이 환경변수 한 줄이라 실운영 투입 부담이 낮다.
- **기준선(baseline)을 먼저 찍은 것.** 저장소에 기존 실패 58건이 있어 "몇 개 실패"로는 회귀를 판단할 수 없었다. FAILED **목록 diff**로 비교하니 판정이 명확했다.
- **종료 조건을 domain 순수 정책으로 분리한 것.** LLM·네트워크 없이 4중 조건과 우선순위를 전부 단위 테스트로 고정할 수 있었다.
- **시그니처 동일성을 테스트로 심은 것.** `runtime-datetime-context`가 legacy 팩토리를 바꿨을 때 문서 약속만 있었다면 module-4 배선에서 `TypeError`로 터졌을 것이다.

### 6.2 What Needs Improvement (Problem)

- **Fake 기반 테스트의 맹점이 두 번 드러났다.** 136개 테스트를 통과했는데도 (1) OpenAI가 스키마를 거부했고(D19), (2) `single` 전략이 강제되지 않고 있었다(G-01). 두 경우 모두 **테스트가 픽스처를 검증하고 있었지 규칙을 검증하지 않았다.** `test_l3_2`의 "single = 3콜"은 Fake LLM이 요구를 1개만 내도록 짜여 있어서 통과한 것이었다.
- **provider 계약을 설계 단계에서 고려하지 않았다.** AD-5(일반형 `constraints: dict`)를 정할 때 "이걸 LLM이 구조화 출력으로 낼 수 있는가"를 묻지 않았다. 실운영 400을 맞고 나서야 알았다.
- **Plan의 정량 기준이 근거 없이 낙관적이었다.** `workflow_compiler.py ≤10줄`은 헬퍼 4개가 필요한 설계에서 애초에 불가능했다. 세우는 시점에 근거가 없었다.
- **Design 조정 사항을 즉시 반영하지 않고 누적시켰다.** module-1~4를 진행하며 6건이 쌓였고, 사용자가 지적하기 전까지 Check 단계 오탐 위험이 남아 있었다.

### 6.3 What to Try Next (Try)

- **안전 규칙은 코드가 보증한다.** 비용 상한·권한·한도처럼 위반 시 손해가 큰 규칙을 프롬프트에 맡기지 않는다. G-01이 정확히 그 사례였다.
- **구조화 출력에는 provider 계약 테스트를 필수로 둔다.** Design §8.1에 신설한 **L0 레벨**(provider 스키마 계약)을 다음 사이클부터 기본 항목으로 가져간다.
- **Fake 테스트를 쓸 때 "이 테스트가 픽스처를 검증하는가, 코드를 검증하는가"를 묻는다.** 최소한 안전 규칙에 대해서는 Fake가 규칙을 **위반하는** 입력을 내도록 짜서 코드가 막는지 본다.
- **정량 기준은 측정 후 확정하거나 범위로 둔다.** 착수 전 추정치를 DoD에 박으면 나중에 문서 충돌이 된다.

---

## 7. Process Improvement Suggestions

### 7.1 PDCA Process

| 제안 | 근거 |
|------|------|
| Design 단계에 **"외부 계약 검토"** 항목 추가 | provider 스키마 제약(D19)을 설계 시점에 걸렀다면 실운영 400을 피할 수 있었다 |
| Do 각 모듈 종료 시 **Design 즉시 반영** | 6건 누적 후 일괄 갱신은 Check 오탐 위험을 만든다 |
| Plan DoD의 정량 기준에 **근거 명시 또는 범위 표기** | G-02는 근거 없는 추정치를 기준으로 박은 결과 |

### 7.2 Tools/Environment

| 제안 | 근거 |
|------|------|
| 회귀 판정을 **FAILED 목록 diff**로 표준화 | 기존 실패가 있는 저장소에서 "N개 실패"는 무의미 |
| 테스트 기준선 스냅샷을 사이클 시작 시 자동 저장 | 본 사이클에서 수동으로 했고 한 번 누락(출력 파일 잘림)이 있었다 |

---

## 8. Next Steps

### 8.1 Immediate

1. **실운영 관측** — `SEARCH_PIPELINE_MODE=deep`으로 실제 비교형 질의 실행 후 `_step_output_summary` 확인

   | 신호 | 의미 |
   |------|------|
   | `stop=no_gain` / `stop=exhausted` 빈발 | Replanner가 전략을 못 바꾸는 중 (R3) |
   | `coverage` 계속 부분 충족 | Evaluator 과엄격 또는 constraints 과다 |
   | `degraded=True` 빈발 | 경량 모델이 추출 스키마를 감당 못 함 |
   | `fallback=True` 빈발 | plan LLM이 계획 스키마를 못 맞춤 |

2. 이월 3건(G-03/04/05) 처리 여부 판단

### 8.2 Next PDCA Cycle

| 후보 | 내용 |
|------|------|
| `deep-search-internal` | 내부 하이브리드 검색으로 확장. Extractor가 청크 포맷 흡수 필요 |
| `deep-search-budget` | 토큰 상한(G-05) + 예산의 config 노출 |
| `multi-query-consolidation` | 미배선 `multi_query` 모듈을 폐기하거나 deep 파이프라인에 흡수 |

---

## 9. Changelog

### v1.0.0 (2026-08-26)

**Added**
- `src/domain/deep_search/` — Requirement/Evidence/SearchQuery/StopReason, `merge_evidence` reducer, 예산·커버리지 정책
- `src/application/deep_search/` — 5노드 LangGraph 서브그래프, 3종 프롬프트, Evidence 렌더
- `config.search_pipeline_mode` (`legacy` | `deep`, 기본 `legacy`)
- 테스트 136건 (L0 provider 계약 / L1 도메인 / L2 노드 / L3 통합·배선)

**Changed**
- `workflow_compiler.py` — `category=="search"` 분기에서 모드별 팩토리 선택 (+31줄)
- `config.py` (+6줄), `main.py` (+2줄)

**Unchanged**
- `search_pipeline.py` — **0줄** (교체 대기 전제 유지)

---

## Version History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-08-26 | 배상규 | 최초 완료 보고서 — Match Rate 97%, FR 15/16, 이월 3건 |
