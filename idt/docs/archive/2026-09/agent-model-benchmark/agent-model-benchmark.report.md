# agent-model-benchmark 완료 보고서

> **Project**: sangplusbot (idt + idt_front)
> **Version**: 1.0.0
> **Author**: 배상규
> **Date**: 2026-09-02
> **Match Rate**: **97.1%** (88.6% → 94.3% → 97.1%, Act 2회)
> **QA**: **QA_PASS** (최초 FAIL → 결함 2건 해소 후 PASS)

---

## Executive Summary

### 1.1 Project Overview

| 항목 | 내용 |
|---|---|
| **기능** | 동일 에이전트를 여러 LLM 모델로 순차 실행해 품질·비용·지연·도구정확도 4축을 한 표로 비교하는 **모델 스윕** |
| **기간** | 2026-08-31 ~ 2026-09-02 (PDCA 1사이클, Do 4세션 + Act 2회) |
| **선택 설계** | Option C — 실용 균형 (기존 Eval Hub 확장) |
| **레이어** | Thin DDD (domain / application / infrastructure / interfaces) + React 19 프론트 |

### 1.2 Results Summary

| 지표 | 결과 |
|---|---|
| Match Rate | **97.1%** (Structural 100% / Functional 91.4% / Contract 100%) |
| QA 판정 | **QA_PASS** — L1 32 + L2 22 = 54건 실행, 전부 통과 |
| 신규 테스트 | **131건** (백엔드 109 + 프론트 22) |
| 회귀 | **0건** — 전 단계에서 실패 목록 diff로 검증 |
| FR 이행 | **15/15** |
| Decision Record 준수 | **12/12** |

### 1.3 Value Delivered

| Perspective | 계획 | 실제 결과 |
|---|---|---|
| **Problem** | `evaluation_run`에 모델 차원이 없고 `_run_agent()`가 `config.llm_model`을 무시해 모델 비교가 원천 불가 | **두 결핍 모두 제거.** V068로 모델 차원 부여, `_prepare_graph` 단일 지점에서 오버라이드 해석 |
| **Solution** | 오버라이드 + `evaluation_sweep` 부모 테이블 + `ai_run` 조인 + 도구 F1 | 4개 축 전부 코드 경로 완성. judge는 `_attach_judge()`로 RAGAS metric에 실제 주입 |
| **Function/UX** | 예상 비용 확인 후 순차 실행 → 모델×지표 매트릭스 | 구현 완료 + **예상 vs 실제 비용 대조(±30% 초과 시 강조)** 까지 추가 |
| **Core Value** | "싼 모델로 내려도 품질이 유지되는가"를 숫자로 판단 | **판단 도구는 완성됐으나 실측은 아직 없다** — `ragas` 미설치·서버 미기동으로 종단 실행 미수행 |

---

## 1.4 Success Criteria Final Status

| # | 기준 | 상태 | 근거 |
|---|---|:---:|---|
| 1 | FR-01~FR-15 전부 구현 | ✅ Met | 15/15, 분석 §2.4 |
| 2 | 에이전트 1 × 모델 3 × 케이스 10 종단 실행 | ❌ **Not Met** | 백엔드 서버 미기동 — 실행 이력 없음 |
| 3 | 매트릭스에 4축 지표 전부 채워짐 | ⚠️ Partial | 코드 경로 완비·집계 실DB 검증. **품질 축은 `ragas` 부재로 미실행** |
| 4 | 오버라이드 미지정 시 기존 동작 무변경 | ✅ Met | baseline 594 → 607(신규 13), 소비자 8곳 회귀 0 |
| 5 | pytest 통과 | ✅ Met | 신규 109 passed |
| 6 | 프론트 Vitest + MSW 통과 | ✅ Met | 신규 22 passed |
| 7 | 프론트-백엔드 타입 동기화 | ✅ Met | 필드·nullable 100% 일치 |

**5 Met / 1 Partial / 1 Not Met — 달성률 5.5/7 (79%)**

> 미달 2건은 **코드 결함이 아니라 실행 환경 제약**이다. `ragas` 미설치, 백엔드 서버 미기동,
> Playwright 미설치가 겹쳐 종단 검증이 불가능했다.

---

## 1.5 Decision Record Summary

| ID | 결정 | 준수 | 결과 |
|----|---|:---:|---|
| **D1** | 모델 오버라이드 = `_prepare_graph` 단일 지점 | ✅ | 하위 컴포넌트 무변경. 두 줄 수정으로 끝남 |
| **D2** | 평가 실행은 대화 저장 생략 | ✅ | 저장 메서드 내부 게이트 → 강등 경로까지 자동 커버 |
| **D3** | `evaluation_sweep` 부모 테이블 | ✅ | 재현성 스냅샷의 단일 지점 확보 |
| **D4** | judge 호출별 주입 | ✅ | **설계 상정보다 어려웠음** — 기존 `_llm_model`이 죽은 필드였고 RAGAS에 실제 주입이 필요했다 |
| **D5** | per-case JSON + 조회 시 집계 | ✅ | 스키마 변경 최소화 |
| **D6** | 도구 정확도 = 집합 F1 | ✅ | 순서 무시로 대안 경로를 오답 처리하지 않음 |
| **D7** | 순차 실행, 모델 5개 상한 | ✅ | `peak=1` 테스트로 병렬 아님을 고정 |
| **D8** | 대시보드 `sweep_id IS NULL` | ✅ | 실DB 검증. **단 사용자 목록은 놓쳤다가 QA에서 발견(G-11)** |
| **D9** | temperature 0 강제 | ✅ | `is not None` 판정 — `or`였다면 재현성이 조용히 깨졌을 것 |
| **D10** | 비용·지연은 `ai_run` 조인 | ✅ | 중복 계측 없음 |
| **D11** | `ai_run_id`에 FK 없음 | ✅ | dangling id에도 조회 무중단 확인 |
| **D12** | 부분 실패 행 단위 격리 | ✅ | Act 1회차에 방어적 guard + 검증 3건 추가 |

**12/12 준수.**

---

## 2. Related Documents

| 단계 | 문서 |
|---|---|
| Plan | `docs/01-plan/features/agent-model-benchmark.plan.md` |
| Design | `docs/02-design/features/agent-model-benchmark.design.md` |
| Analysis | `docs/03-analysis/agent-model-benchmark.analysis.md` |
| QA | `docs/05-qa/agent-model-benchmark.qa-report.md` |

---

## 3. Completed Items

### 3.1 Functional Requirements

| FR | 요구 | 상태 |
|----|---|:---:|
| FR-01 | `RunAgentRequest` 오버라이드 3필드 (additive) | ✅ |
| FR-02 | 실효 모델이 `ai_run.llm_model_id`에 반영 | ✅ |
| FR-03 | `evaluation_sweep`이 run N건 소유 | ✅ |
| FR-04 | 모델 수만큼 run 순차 실행 | ✅ |
| FR-05 | 사전 비용 추정 (judge 비용 포함) | ✅ |
| FR-06 | judge 실행별 주입 + 기록 | ✅ |
| FR-07 | `ai_run_id` 연결로 토큰·비용·지연 회수 | ✅ |
| FR-08 | 도구 F1 산출·저장 | ✅ |
| FR-09 | 모델별 4축 집계 | ✅ |
| FR-10 | temperature 0 고정 | ✅ |
| FR-11 | 스윕 생성 모달 | ✅ |
| FR-12 | 매트릭스 + 최고값 하이라이트 | ✅ |
| FR-13 | 개별 run 실패가 스윕 미중단 | ✅ |
| FR-14 | 소유권 404 은닉 | ✅ |
| FR-15 | `expected_tools` 미기재 케이스 제외 | ✅ |

### 3.2 Non-Functional Requirements

| 항목 | 기준 | 결과 |
|---|---|:---:|
| 하위 호환 | 소비자 8곳 동작 무변경 | ✅ 회귀 0 |
| 아키텍처 | domain → infra 참조 0 | ✅ AST 검사 |
| DDL 규약 | 테이블·전 컬럼 COMMENT | ✅ V067·V068 |
| 로깅 | `print()` 금지, `request_id` 포함 | ✅ |
| 코드 규칙 | 함수 40줄, if 중첩 2단계 | ✅ 신규 위반 0 |
| TDD | 테스트 선행 | ✅ Red→Green 준수 |
| **재현성** | 재실행 편차 ≤5%p | ❌ **미검증** (L3-2 실행 불가) |
| **비용 안전** | 추정 ±30% 이내 | ❌ **미검증** (측정 수단은 G-1로 확보) |

### 3.3 Deliverables

**DB (2)** — `V067__create_evaluation_sweep.sql`, `V068__alter_evaluation_add_sweep_dimension.sql`

**백엔드 신규 (11)** — `domain/eval_sweep/` 4, `application/eval_sweep/` 4, `infrastructure/eval_sweep/` 3

**백엔드 수정 (17)** — `run_agent_use_case`·`schemas`(agent_builder), `ragas` 도메인 3 / 인프라 4 / 애플리케이션 4, `ragas_router`, `main.py`, `pyproject.toml`, 기존 테스트 1

**프론트 신규 (5)** — `types/sweep.ts`, `services/sweepService.ts`, `hooks/useSweeps.ts`, `CreateSweepModal.tsx`, `SweepMatrixPanel.tsx`

**프론트 수정 (4)** — `constants/api.ts`, `lib/queryKeys.ts`, `types/eval.ts`, `RunsTab.tsx`

**테스트 신규 (11 파일 / 131건)**

| 영역 | 건수 |
|---|---:|
| 도메인 정책 | 31 |
| UseCase·실행기·소유권·상세 | 33 |
| 저장소 통합(SQLite 실DB) | 13 |
| L1 API (TestClient) | 19 |
| 모델 오버라이드 회귀 | 13 |
| 프론트 (L2) | 22 |
| **합계** | **131** |

---

## 4. Incomplete Items

### 4.1 다음 사이클로 이월

| ID | 내용 | 이유 |
|----|---|---|
| **G-8** | `ragas` 실제 설치 및 품질 축 실측 | 설치 시 `openai` 3.3.1 → 2.54.0 **메이저 다운그레이드** 발생. `[eval]` extra로 분리 선언만 하고 보류 |
| **SC-2** | 종단 스윕 실행 검증 | 백엔드 서버 미기동 |
| **SC-3 / NFR** | 재현성(편차 ≤5%p)·비용 추정 정확도(±30%) 실측 | 위 두 항목에 종속 |
| **G-3** | 실행 중 행별 진행 스피너 | Minor UI, 폴링은 동작 |
| **G-4** | 스윕 0건 시 빈 상태 문구 | Minor UI |

### 4.2 취소/보류

| ID | 내용 | 판단 |
|----|---|---|
| **G-6** | 응답을 객체(`{id, display_name}`) 대신 id/name 평면 구조로 반환 | **구현 유지** — Design 문서를 정정하는 편이 맞음 |
| **G-7** | 검증 실패가 400이 아닌 422 | **구현 유지** — 라우터 기존 선례(`_raise_eval_error`) 준수 |
| **G-9** | Design §6.1과 §3.3의 `judge_llm_model_id` 불일치 | **Design 문서 정정 대상** — 구현은 §3.3 준수 |

---

## 5. Quality Metrics

### 5.1 Final Analysis Results

| 축 | Check | Act1 | Act2 |
|---|---:|---:|---:|
| Structural | 100.0% | 100.0% | 100.0% |
| Functional | 82.9% | 91.4% | 91.4% |
| Contract | 88.5% | 96.2% | 100.0% |
| **Overall** | **88.6%** | **94.3%** | **97.1%** |

> Contract 100%는 G-6·G-7을 "Design 문서 정정 대상"으로 분류한 결과다. 이를 계약 미이행으로
> 세면 Contract 96.2% / Overall 94.3%다. 분류 근거는 §4.2에 있다.

### 5.2 Resolved Issues

| ID | 심각도 | 내용 | 해소 시점 |
|----|:---:|---|---|
| G-1 | Important | 실제 비용 미노출 — 추정 정확도 측정 불가 | Act 1 |
| G-2 | Important | 실험 조건(에이전트·테스트셋·케이스 수) 미노출 | Act 1 |
| G-5 | Important | 부분 실패 격리 미검증 | Act 1 |
| G-10 | Minor | `GET /ragas/runs`에 스윕 식별 필드 없음 | Act 2 |
| G-11 | **Important** | 스윕 run이 사용자 '평가 실행' 목록 오염 | Act 2 |

---

## 6. Lessons Learned & Retrospective

### 6.1 잘된 점 (Keep)

**1. 설계 전 코드 조사를 10건까지 밀어붙인 것**
Plan 단계에서 "`config.llm_model`이 agent 대상에 안 먹는다"를 찾아낸 것이 이 사이클 전체의 방향을 정했다. 이걸 못 찾았다면 "모델 파라미터를 넘기면 되겠지"라는 잘못된 전제로 설계했을 것이다.

**2. 회귀 판정을 "실패 목록 diff"로 한 것**
워킹트리에 다른 작업(`mcp-tool-auto-sync`)의 미커밋 변경이 섞여 있어 기존 실패가 34~58건 있었다. 개수만 비교했다면 판단이 흐려졌을 텐데, `git stash` 후 실패 **목록**을 `comm`으로 대조해 매번 "신규 0건"을 명확히 입증했다.

**3. 최대 리스크 모듈을 단독 세션으로 분리한 것**
`module-2`(공유 실행 경로 침습)를 다른 모듈과 섞지 않아 회귀 검증에만 집중할 수 있었다. baseline 594 → 607 대조가 깔끔했다.

**4. `0.0`과 `None`을 타입 수준에서 구분한 것**
"측정 불가"와 "성능 0점"을 섞었다면 매트릭스가 의사결정을 오도했을 것이다. `mean_ignoring_none`과 "—" 렌더를 테스트로 고정했다.

### 6.2 개선할 점 (Problem)

**1. Design 문서에 검증되지 않은 사실을 적었다**
§4.2 API 예시에 `faithfulness`·`context_precision`을 썼는데, `TARGET_METRICS["agent"]`는 이를 허용하지 않는다. Do 단계에서야 발견했다. **설계 시점에 실제 정책 코드를 확인했어야 했다.**

**2. D8을 대시보드에만 적용하고 사용자 목록을 놓쳤다**
"스윕은 실험이니 통계에서 빼자"는 판단은 옳았으나 적용 범위를 관리자 대시보드로만 좁게 봤다. **QA에서야 G-11로 발견**됐다. 같은 원칙이 적용돼야 할 다른 지점을 설계 시점에 열거하지 않은 탓이다.

**3. 환경 전제를 확인하지 않고 설계했다**
`ragas`가 설치조차 안 돼 있다는 걸 module-4 착수 시점에 알았다. 품질 축이 4축 중 1축인데, **이 축이 실행 가능한지를 Plan 단계에서 확인했어야 한다.**

**4. Design 문서 내부에 모순이 있었다(G-9)**
§6.1은 `evaluation_run`에 `judge_llm_model_id`를 추가한다 하고 §3.3 DDL엔 없다. 문서를 길게 쓰면서 교차 검증을 안 했다.

### 6.3 다음에 시도할 것 (Try)

1. **Plan 단계에 "환경 실행 가능성 체크" 항목 추가** — 설계가 의존하는 외부 패키지·서비스가 지금 이 환경에서 동작하는지 먼저 확인한다.
2. **설계 결정에 "적용 범위 열거"를 강제** — D8 같은 정책 결정은 "어디에 적용되는가"를 목록으로 적는다. G-11은 이걸로 예방됐을 것이다.
3. **Design의 API 예시를 실제 정책 코드로 교차 검증** — 예시에 쓰는 값이 실제로 통과하는지 확인한다.
4. **QA를 Check 이전으로 당기기** — G-11은 QA에서 발견됐는데, Check 단계의 정적 분석으로는 잡히지 않는 종류였다. 사용자 화면 영향은 더 일찍 볼 방법이 필요하다.

---

## 7. Process Improvement Suggestions

### 7.1 PDCA 프로세스

| 제안 | 근거 |
|---|---|
| Plan 템플릿에 **"외부 의존성 실행 가능성"** 섹션 추가 | G-8을 module-4에서야 발견 |
| Design 결정 표에 **"적용 범위"** 열 추가 | D8이 대시보드에만 적용돼 G-11 발생 |
| Check 단계에 **"기존 화면 영향"** 축 추가 | 정적 3축(구조·기능·계약)으로는 G-11이 안 잡혔다 |

### 7.2 도구/환경

| 제안 | 근거 |
|---|---|
| 워킹트리에 여러 기능이 섞이지 않게 분리 | 기존 실패 34~58건이 매 단계 판정을 방해 |
| Playwright 도입 검토 | L3 시나리오 3건이 계속 미실행 상태 |
| `ragas` 설치 정책 확정 (별도 venv / CI 전용) | `openai` 메이저 다운그레이드 충돌 |

---

## 8. Next Steps

### 8.1 즉시

1. `ragas` 설치 환경 확정 → 품질 축 실측 (`uv pip install -e ".[eval]"`)
2. 백엔드 기동 후 **종단 스윕 1회 실행** — SC-2, SC-3, 재현성 NFR, 비용 추정 정확도를 한 번에 검증
3. Design 문서 정정 3건 (G-6·G-7·G-9)

### 8.2 다음 PDCA 사이클 후보

| 항목 | 내용 |
|---|---|
| Minor UI 마감 | G-3(행별 스피너), G-4(빈 상태 문구) |
| 비용 추정 정밀화 | `_SECONDS_PER_CASE=14`, `_JUDGE_TOKENS_PER_CASE=1500` 가정치를 실측으로 교정 |
| 스윕 결과 시각화 | 레이더/막대 차트 (이번 스코프에서 제외) |
| 케이스별 답변 비교 | 점수 차이의 원인을 눈으로 확인 (이번 스코프에서 제외) |
| M×N 풀 매트릭스 | 에이전트 여러 개 × 모델 여러 개 |

---

## 9. Changelog

### v1.0.0 (2026-09-02)

**Added**
- `evaluation_sweep` 테이블 및 모델 스윕 도메인·애플리케이션·인프라 계층
- `/api/ragas/sweeps` 5개 엔드포인트 (estimate / create / list / detail / delete)
- `RunAgentRequest` 모델·temperature 오버라이드, 대화 저장 생략 플래그
- 도구 호출 정확도(집합 F1), `ai_run` 조인 기반 비용·지연 회수
- RAGAS judge 실행별 주입 (`_attach_judge`)
- 프론트 스윕 생성 모달 + 모델×지표 매트릭스 (예상 vs 실제 비용 대조 포함)
- `pyproject.toml` `[eval]` extra (`ragas`)

**Changed**
- `TargetExecutorInterface.execute` 반환형: 튜플 → `TargetExecution`
- `AgentRunner`: `str` 반환 → `AgentRunOutcome`(answer/tools_used/ai_run_id)
- 관리자 RAGAS 대시보드 통계에서 스윕 run 제외 (D8)
- 사용자 '평가 실행' 목록에서 스윕 run 제외 (G-11)
- `GET /ragas/runs` 응답에 `sweep_id`·`llm_model_id` 추가 (additive)

**Fixed**
- `_begin_observability`가 원본 모델을 기록해 비용이 잘못된 모델에 귀속되던 문제 (FR-02)
- `RagasEvaluatorAdapter._llm_model` 죽은 필드 — judge가 실제로 주입되지 않던 문제 (D4)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0.0 | 2026-09-02 | 완료 보고서 최초 작성 — Match Rate 97.1%, QA_PASS | 배상규 |
