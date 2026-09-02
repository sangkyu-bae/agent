# agent-model-benchmark QA Report

> **판정**: **QA_PASS** (재검증) — 최초 QA에서 발견한 G-10·G-11을 Act 2회차에서 해소했다.
> 최초 판정은 QA_FAIL이었다 (아래 §10).
> **Project**: sangplusbot (idt + idt_front)
> **Date**: 2026-09-02
> **Design Test Plan**: `docs/02-design/features/agent-model-benchmark.design.md` §8
> **Match Rate (Act 1회 후)**: 94.3%

---

## 1. 실행 환경

| 항목 | 상태 | 영향 |
|---|:--:|---|
| 백엔드 서버 (`localhost:8000`) | ❌ 미기동 | L1을 라이브 호출 대신 **TestClient(in-process)** 로 수행 |
| 프론트 dev 서버 | ✅ 200 | — |
| Playwright | ❌ 미설치 | **L3 E2E 실행 불가** |
| `ragas` 패키지 | ❌ 미설치 | **품질 축(RAGAS) 실행 불가** — `[eval]` extra로 선언만 된 상태 |
| MySQL | — | 저장소 테스트는 **SQLite + 실세션**으로 대체 |

---

## 2. L1 — API 테스트

`tests/api/test_sweep_router.py` (TestClient + DI 오버라이드) — 라이브 서버 없이 라우팅·인증·검증·상태코드·응답 형태를 검증.
`tests/infrastructure/eval_sweep/test_sweep_repository.py` (SQLite 실세션) — 집계 SQL·대시보드 필터.

| # | 시나리오 | 결과 | 근거 |
|---|---|:--:|---|
| L1-1 | `POST /sweeps/estimate` 정상 | ✅ | 200 + `per_model` + `basis.source` |
| L1-2 | 모델 6개 → 거절 | ✅ | **422** + "최대 5개" |
| L1-3 | 비활성 모델 포함 → 거절 | ✅ | 422 + "비활성" |
| L1-4 | `POST /sweeps` 정상 | ✅ | **202** + `total_runs=2` |
| L1-5 | 미소유 테스트셋 | ✅ | **404**(403 아님 — 존재 여부 은닉) |
| L1-6 | `GET /sweeps/{id}` 4축 | ✅ | rows 2건, quality/cost/latency/tool_f1 전부 존재 |
| L1-7 | 타인 스윕 조회 | ✅ | 404 |
| L1-8 | `DELETE /sweeps/{id}` | ✅ | 204 |
| L1-9 | 대시보드가 스윕 run 제외 | ✅ | **실DB 검증** — `total_runs=1`, 평균 0.5 유지(스윕 1.0 미반영) |
| L1-10 | `GET /ragas/runs`에 `sweep_id`/`llm_model` 추가 | ❌ | **미구현 (G-10)** |
| L1-11 | 미인증 요청 | ✅ | 401/403, UseCase 미도달 |

**추가 검증 (계획 외)**

| 항목 | 결과 |
|---|:--:|
| 추정 API 부수효과 없음 | ✅ |
| 소유자 id가 토큰에서 전달 | ✅ |
| admin scope=None / 일반 scope=본인 id | ✅ |
| 필수 필드 누락 → 422 | ✅ |
| `limit=999` → 422 | ✅ |
| 목록 `items/total/limit/offset` 형태 | ✅ |
| 측정 불가 지표가 `null`로 직렬화 | ✅ |
| G-1·G-2 필드(실제 비용·실험 조건) 응답 반영 | ✅ |
| **집계**: 품질 평균·비용 합·도구 F1 | ✅ 실DB |
| **N/A 제외 평균** (§3.5) | ✅ 실DB |
| **`ai_run` 미연결 시 비용·지연만 N/A** (D11) | ✅ 실DB |
| **dangling `ai_run_id`에도 조회 무중단** (D11) | ✅ 실DB |
| 실패 run의 `failed_cases` 산출 | ✅ 실DB |
| 스윕 간 행 격리 | ✅ 실DB |

**L1: 29 executed / 28 pass / 1 fail(L1-10)**

---

## 3. L2 — UI 액션 테스트

Playwright 미설치로 **Vitest + MSW**로 수행 (동등 수준의 상호작용 검증).

| # | 시나리오 | 결과 |
|---|---|:--:|
| L2-1 | [+ 모델 스윕] → 모달 오픈, temperature 안내 | ✅ |
| L2-2 | 모델 6개째 체크 불가 + 안내 | ✅ |
| L2-3 | 비용 확인 전 [실행] 비활성 | ✅ |
| L2-4 | [예상 비용 확인] → "추정치" 라벨 | ✅ |
| L2-5 | [실행] → POST 페이로드 정확 | ✅ |
| L2-6 | 완료 스윕 → 매트릭스 + 최고값 하이라이트 | ✅ |
| L2-7 | 실패 행 배지 + 나머지 행 정상 | ✅ |
| L2-8 | `null` → "—" (0 아님) | ✅ |
| L2-9 | judge 모델명 상시 병기 | ✅ |

**추가**: 지표 방향성(품질↑/비용↓), 추정 오차율 표시, 실험 조건 표시, 스윕 0건 시 섹션 미렌더, 상한 해제 후 재선택.

**L2: 22 executed / 22 pass**

---

## 4. L3 — E2E

| # | 시나리오 | 결과 | 사유 |
|---|---|:--:|---|
| L3-1 | 로그인 → 스윕 생성 → 폴링 → 매트릭스 | ⏭️ Skipped | 백엔드 미기동 + Playwright 미설치 |
| L3-2 | 동일 조건 2회 실행, 편차 ≤5%p | ⏭️ Skipped | 동일 + `ragas` 미설치로 품질 점수 산출 불가 |
| L3-3 | 미도달 엔드포인트 모델 포함 → 부분 실패 | ⏭️ Skipped | 동일 (단위 수준에서는 검증됨 — `test_sweep_executor`) |

**L3: 0 executed / 3 skipped**

> L3-2는 Plan의 재현성 NFR을 직접 검증하는 유일한 시나리오다. **현재까지 이 NFR은 미검증 상태**다.

---

## 5. L4 / L5

| 레벨 | 상태 | 사유 |
|---|:--:|---|
| L4 성능 | ⏭️ Skipped | 서버 미기동. 순차 실행 설계상 부하 특성은 모델 수 × 케이스 수에 선형 |
| L5 보안 | ✅ 부분 수행 | 인증(L1-11), 소유권 404 은닉(L1-5/L1-7), admin/일반 scope 분리 검증 완료. `api_key_env` 미노출은 기존 스키마상 보장 |

---

## 6. 신규 발견 결함

### G-10 (Minor) — `GET /ragas/runs`에 스윕 식별 필드 없음

Design §4.3은 "응답에 `sweep_id`, `llm_model` 추가(additive)"를 명시했으나 `EvalRunDetailBody`
(`ragas_router.py:128-138`)에 두 필드가 없다.

- 정보 자체는 `config` JSON(`sweep_id`, `llm_model_id`)에 담겨 있어 완전 손실은 아니다.
- 그러나 클라이언트가 최상위 필드로 접근할 수 없다.

### G-11 (Important) — 스윕 하위 run이 사용자 "평가 실행" 목록을 오염시킴

`EvaluationRepository.list_runs`에는 **`sweep_id` 필터가 없다**. D8은 관리자 대시보드
(`get_dashboard_stats`)만 보호했고, 사용자 화면인 `GET /api/ragas/runs`는 그대로다.

**결과**: 모델 5개짜리 스윕 1회를 돌리면 "평가 실행" 목록에 **5행이 추가**된다. G-10 때문에
어떤 행이 스윕 소속인지 구분할 수단조차 없어, 목록이 실험 run으로 뒤덮인다.

이는 이 기능이 **기존 화면에 만든 회귀**다. 코드가 깨지지는 않지만, 스윕을 몇 번만 돌려도
운영자가 실제 평가 실행을 찾기 어려워진다.

> **판정 근거**: 실행한 51건이 전부 통과했음에도 QA_FAIL로 판정한 이유가 G-11이다.
> 새 기능이 기존 기능을 저하시키는 것은 테스트 통과로 상쇄되지 않는다.

---

## 7. 미해결 위험 (테스트로 덮이지 않음)

| 항목 | 성격 |
|---|---|
| **품질 축 미실행** | `ragas` 미설치 — 매트릭스 4축 중 RAGAS 지표는 한 번도 계산된 적이 없다 |
| **재현성 NFR 미검증** | L3-2 미실행. temperature 0 고정은 단위 검증됐으나 실제 편차는 미측정 |
| **종단 실행 미검증** | 생성 → 순차 실행 → 집계 → 화면까지 실제로 흐른 적이 없다 |
| **비용 추정 정확도** | `_SECONDS_PER_CASE=14`, `_JUDGE_TOKENS_PER_CASE=1500` 등 가정치가 실측으로 교정된 적 없음. G-1로 대조 수단은 마련됨 |

---

## 8. 테스트 집계

| 영역 | 파일 | 건수 |
|---|---|---:|
| L1 API | `tests/api/test_sweep_router.py` | 19 |
| L1 저장소(실DB) | `tests/infrastructure/eval_sweep/test_sweep_repository.py` | 10 |
| 도메인 정책 | `tests/domain/eval_sweep/` | 31 |
| UseCase·실행기·소유권 | `tests/application/eval_sweep/` | 33 |
| 모델 오버라이드 | `test_run_agent_model_override.py` | 13 |
| 프론트 (L2) | `SweepMatrixPanel` / `CreateSweepModal` / `SweepFlow` | 22 |
| **합계** | | **128** |

**회귀**: 백엔드 전체 실패 58건 — **전부 기존 실패**이며 신규 QA 테스트 파일에서 발생한 실패는 0건.
프론트 `DatasetsTab` 실패 1건도 baseline 동일.

---

## 9. 판정

**QA_FAIL**

- 실행 51건(L1 29 + L2 22) 전부 통과, 신규 회귀 0
- 그러나 **G-11**(사용자 평가 실행 목록 오염)은 이 기능이 기존 화면에 만든 실질적 저하이며,
  **G-10**(스윕 식별 필드 부재)이 이를 완화할 수단마저 막고 있다
- 두 결함은 `list_runs`에 필터를 더하고 응답에 2필드를 추가하는 **소규모 수정**으로 해소 가능하다

**권장**: `/pdca iterate agent-model-benchmark`로 G-10·G-11을 처리한 뒤 Report로 진행.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1.0 | 2026-09-02 | QA 최초 수행 — L1 29 / L2 22 실행, L3 skip, 신규 결함 2건 | 배상규 |


---

## 10. 재검증 (Act Iteration 2 이후)

QA_FAIL 판정의 원인이던 결함 2건을 처리하고 재검증했다.

### 10.1 처리 결과

| ID | 조치 | 상태 | 근거 |
|----|------|:----:|------|
| **G-11** | `EvaluationRepository.list_runs`에 `sweep_id IS NULL` 필터 추가 — 스윕 하위 run이 '평가 실행' 목록에서 빠진다 | ✅ 해결 | 실DB 테스트 2건: 스윕 5행 생성 후에도 목록 `total=1`, 단독 run 2건은 그대로 노출 |
| **G-10** | `EvalRunDetailResponse`·`EvalRunDetailBody`에 `sweep_id`·`llm_model_id` 추가 (additive). 프론트 `EvalRun` 타입 동기화 | ✅ 해결 | OpenAPI 스키마에 두 필드 확인, 단건 조회로 소속 식별 테스트 |

**설계 판단**: 스윕 run을 목록에서 **무조건 제외**하기로 했다. 조건부 파라미터를 두는 대신
제외를 택한 근거는 두 가지다 — (a) 스윕은 전용 섹션(`GET /sweeps`)에서 보므로 접근성 손실이 없고,
(b) 스윕 run은 이 기능 이전에 존재하지 않았으므로 **제외가 곧 기존 목록 의미의 복원**이다.
숨겨지는 기존 데이터가 없다.

### 10.2 L1 재측정

| # | 시나리오 | 이전 | 이후 |
|---|---|:--:|:--:|
| L1-10 | `GET /ragas/runs`에 스윕 식별 필드 | ❌ | ✅ |

**L1: 32 executed / 32 pass** (기존 29 + 신규 3)

### 10.3 회귀

| 검증 | 결과 |
|---|---|
| 백엔드 실패 목록 diff (QA 시점 대비) | **58 → 58, 완전 동일 (신규 0)** |
| 저장소 통합 테스트 | 13 passed (10 → +3) |
| 프론트 EvalDatasetPage | 35 passed (실패 1건은 baseline 동일) |
| `tsc --noEmit` | 0 errors |
| OpenAPI `EvalRunDetailBody` | `sweep_id`·`llm_model_id` 확인 |

### 10.4 최종 판정

**QA_PASS**

- L1 32 / L2 22 = **54건 실행, 전부 통과**
- 최초 QA에서 발견한 결함 2건 모두 해소, 신규 회귀 0
- 단, §7의 미해결 위험(품질 축 미실행 · 재현성 NFR 미검증 · 종단 실행 미검증)은 **그대로 남아 있다**.
  이는 코드 결함이 아니라 실행 환경(`ragas` 미설치, 서버 미기동, Playwright 미설치)의 제약이다.

### 10.5 Version History 추가

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.2.0 | 2026-09-02 | Act 2회차 반영 — G-10·G-11 해소, QA_FAIL → **QA_PASS** | 배상규 |
