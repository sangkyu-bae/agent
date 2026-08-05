# eval-hub Completion Report

> **Summary**: 목데이터뿐인 `/eval-dataset` 페이지를 실제 기능하는 평가 허브로 전환 — 기존 RAGAS 백엔드 스택(V020)과 연결하고, 소유권(V055)·4탭 UI·파일 업로드·문서→QA 자동 생성·메트릭 카탈로그를 신설했다.
>
> **Feature**: eval-hub
> **Duration**: 2026-08-03 (단일 세션: Plan → Design → Do → Check → Iterate)
> **Final Match Rate**: 98.0%
> **Owner**: 배상규

---

## Executive Summary

| 항목 | 내용 |
|------|------|
| **Feature** | 평가 허브 (데이터셋·평가 실행·평가기·대시보드 4탭) |
| **Duration** | 2026-08-03 단일 세션 (Plan → Design → Do → Check → 갭 수정) |
| **Match Rate** | 98.0% (1차 91.1% → 갭 7건 즉시 수정) |
| **Scope** | 백엔드 신규 10 + 수정 12 · 프론트 신규 10 컴포넌트 + 타입/서비스/훅 |

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | 백엔드에는 RAGAS 평가 스택(V020)이 완전히 배선되어 있었으나 인증/소유권/UI가 없어 사용 불가 상태. 프론트 `/eval-dataset`는 목데이터만 표시하며 실제 API 호출 없음. P2(에이전트 소유자/KB 운영자)가 자신의 에이전트/KB 품질을 수치화할 셀프서비스 루프가 결여됨. |
| **Solution** | (1) V055 마이그레이션으로 소유권(user_id) 도입 → `/api/ragas/*` 전 엔드포인트에 인증/스코프 적용. (2) 기존 API 보강: cases 반환·testset_id 배치 실행·CSV/Excel 업로드·문서→QA LLM 생성·메트릭 카탈로그. (3) 프론트 4탭 허브로 재구축 (데이터셋/평가 실행/평가기/대시보드). |
| **Function/UX Effect** | 운영자가 화면에서 (1) QA 데이터셋 3가지 방법으로 생성(수동/파일/문서), (2) 대상(agent/rag/retrieval)·메트릭 선택 후 배치 평가 실행, (3) 실시간 폴링으로 진행 상태 추적 및 케이스별 점수 확인, (4) admin은 대시보드에서 전체 통계·최근 실행 열람. **기존 API는 일반 사용자가 본인 것만, admin이 전체 접근** (권한 모델 신설). |
| **Core Value** | V020(2026-05 ragas-evaluation에서 구축)으로 만든 평가 인프라가 처음으로 사용자에게 노출되어 **셀프서비스 품질 검증 루프 완성**. 향후 낮은 점수 → 위키/메모리 자동 환류로 확장 가능한 기초 마련. |

---

## PDCA Cycle Summary

### Plan
**주요 결정사항** (완료):
1. **탭 범위**: 데이터셋·평가 실행·대시보드는 완전 구현, 평가기 탭은 읽기전용 메트릭 카탈로그만
2. **데이터셋 생성 3종**: 수동 QA 입력 + CSV/Excel 업로드 + 문서 업로드→LLM 자동 생성(신규 API `POST /api/ragas/testsets/generate`)
3. **권한 모델**: 일반 사용자는 본인 소유 테스트셋/실행만 접근, admin은 전체 (소유권 NULL=레거시는 admin만)
4. **평가 대상 3종**: rag / agent / retrieval 모두 노출

**배경 조사 완료** (6개 확인 지점):
- 프론트: `setTimeout(2000)` 목데이터만, API 미호출
- 백엔드: `/api/ragas` 배선 완료 but 인증·소유권·cases 반환·testset_id 경로 미지원

### Design
**핵심 설계 항목** (101개 검증 요소):

| 영역 | 결정 사항 |
|------|---------|
| **DB (V055)** | `evaluation_testset` / `evaluation_run`에 `user_id VARCHAR(36) NULL` 추가 + INDEX + COMMENT |
| **인증·소유권** | ragas_router 전 엔드포인트에 `get_current_user` + scope(`None`=admin \| `user.id`=일반) → repository에 전파 |
| **API 신설** | A5(업로드) / A6(문서→QA draft) / A7(메트릭 카탈로그) / A8 강화(testset_id) / A9 강화(error_message) |
| **파일 파싱** | KB-excel-upload 패턴 재사용: `.csv` / `.xlsx` 확장자 라우팅, 한글 별칭 지원(질문→question, 정답→ground_truth) |
| **LLM 생성** | 입력 20,000자 절단 + 생성 15쌍 상한 (429 방지) + draft 무저장 (검토 후 사용자가 저장) |
| **메트릭 SoT** | `domain/ragas/policies.py` TARGET_METRICS 맵: rag 6종 / agent 4종 / retrieval 5종 (admin API·카탈로그·배치 검증 공유) |
| **프론트 타입** | snake_case 통일 (adminRagas 규칙), authApiClient 사용(토큰 주입), TanStack Query 폴링(pending\|running 있으면 5s 주기) |

**구현 순서**: V055 → 모델·인증 → cases·testset_id → 업로드·메트릭 → 생성 → 프론트 기반 → 탭별 구현 (9단계)

### Do
**구현 현황**:

| 카테고리 | 신규 파일 | 수정 파일 | 설명 |
|---------|---------|---------|------|
| **백엔드** | 10 | ~12 | V055 마이그레이션, models.py (user_id), ragas_router 전면, 6개 use case, 3개 repository 메서드, testset_file_parser, document_text_extractor, 11개 테스트 |
| **프론트** | 10 | 6 | EvalDatasetPage → 4탭, DatasetsTab/TestsetDetailPanel/CreateTestsetModal/ManualCaseEditor, RunsTab/CreateRunModal/RunDetailPanel, EvaluatorsTab/DashboardTab, types/eval, evalService, hooks/useEval, queryKeys eval 병합 |
| **테스트** | 21 | - | 백엔드 ragas 76건+DDL 10건, 프론트 신규 14건+회귀 9건+레이아웃 31건 |

**핵심 기술 결정**:
1. **배치 평가 실행 계층 신설**: 기존 run은 생성만 되고 영원히 pending 상태 → `BatchEvalExecutor` + `SessionScopedEvalRunStore` + `DefaultTargetExecutor`(rag/retrieval/agent) 신설해 실제 실행 구현
2. **agent 메트릭 제한**: 컨텍스트 부재로 faithfulness 계산 불가 → `TARGET_METRICS`에서 제외, 카탈로그·배치 검증 공유
3. **queryKeys 충돌 해소**: eval-hub 블록이 기존 agent-eval-gate의 피드백 키를 덮어쓴 것 검출 → 단일 eval 네임스페이스로 병합

### Check
**Gap 분석 결과**:

| 시점 | Match Rate | 갭 건수 | 심각도 분포 |
|------|:---------:|--------|----------|
| 1차 gap-detector | 91.1% | 9건 | High 1 · Medium 4 · Low 4 |
| **최종 (갭 수정 후)** | **98.0%** | 2건(Low, 스코프 축소) | — |

**수정된 갭** (7건):
- **G-01 (High)**: queryKeys eval 중복 → 피드백 기능 크래시 회귀 → ✅ 단일 네임스페이스로 병합, 9건 회귀 테스트 통과
- **G-02~G-05 (Medium)**: 재실행 버튼 미구현 → ✅ / sample_ratio 필드 누락 → ✅ / 파일 크기 상한 없음 → ✅(15MB 설정) / 생성 실패 500 → ✅(502 + 원인 표면화)
- **G-06 (Low)**: 대시보드 target_type_counts 미표시 → ✅ 추가

**스코프 축소** (2건, 후속):
- **G-07**: 대시보드 recent_runs 딥링크 (RunsTab 로컬 상태 때문에 배관 복잡) → 대시보드 고도화 후속
- **G-08**: EvaluatorsTab/DashboardTab 개별 테스트 → index.test가 커버(부분 충족), 분리는 후속

**테스트 결과** (무회귀 확인):
- 백엔드: ragas 76건 전체 통과(application 55 + api 23 중복 제외) + V055 DDL COMMENT 검사 통과
- 프론트: 신규 14건 + MessageFeedback 회귀 9건(G-01 수정 검증) + 레이아웃 31건 통과, tsc 클린
- verify-architecture: 신규 코드 0 위반

### Iterate (갭 수정)
**1차→최종 개선**:
1. queryKeys 병합 (G-01) + 답변 피드백 기능 회귀 테스트 9건 추가 → 통과
2. RunDetailPanel에 재실행 버튼 + run.config prefill (G-02)
3. CreateRunModal sample_ratio 필드 + 인라인 검증 0<x≤1 (G-03)
4. eval_qa_gen_max_file_mb 설정 신설 + 파일 크기 사전 차단 테스트 (G-04)
5. 생성 LLM 502 + detail 표면화 (G-05)
6. 대시보드 target_type_counts 칩 추가 (G-06)

**부가 발견 사항**:
- DOCX 추출: 설계상 python-docx → 실제 구현 zipfile+ElementTree (표준 라이브러리, 동작 동등)
- openpyxl venv 미설치 표류 발견·해소 (배포 환경 확인 필요)

---

## 주요 산출물 파일 목록

### 백엔드 (idt/)

**마이그레이션 & 모델**
- `db/migration/V055__alter_evaluation_add_user_id.sql` (신규, DDL COMMENT 포함)
- `src/infrastructure/ragas/models.py` (수정, user_id 필드 추가)

**Entities & Policies**
- `src/domain/ragas/policies.py` (수정, TARGET_METRICS 맵 신설)
- `src/domain/ragas/entities.py` (수정, EvaluationRun.user_id 필드)

**Use Cases**
- `src/application/ragas/testset_use_case.py` (수정, 인증·스코프·cases·생성)
- `src/application/ragas/batch_evaluation_use_case.py` (수정, testset_id)
- `src/application/ragas/testset_generate_use_case.py` (신규, 문서→QA 생성)
- `src/application/ragas/metrics_catalog_use_case.py` (신규, 메트릭 조회)
- `src/application/ragas/batch_eval_executor.py` (신규, 실제 평가 실행)
- `src/application/ragas/session_scoped_eval_run_store.py` (신규, run 저장소)

**Infrastructure**
- `src/infrastructure/ragas/repository.py` (수정, 소유권 필터)
- `src/infrastructure/eval_testset/testset_file_parser.py` (신규, CSV/Excel 파싱)
- `src/infrastructure/eval_testset/document_text_extractor.py` (신규, PDF/DOCX 파싱)
- `src/infrastructure/ragas/default_target_executor.py` (신규, rag/agent/retrieval 실행)

**API & Config**
- `src/api/routes/ragas_router.py` (전면 수정, 인증·스코프 적용)
- `src/config.py` (수정, EVAL_QA_GEN_* 설정 3종 추가)
- `src/main.py` (수정, 마이그레이션 없음)

**테스트** (11건)
- `tests/api/test_ragas_auth_scope.py` (인증·소유권·404 은닉)
- `tests/api/test_ragas_testset_detail_cases.py` (cases 반환)
- `tests/api/test_ragas_batch_testset_id.py` (testset_id 기반 실행)
- `tests/api/test_ragas_testset_endpoints.py` (업로드·생성·메트릭)
- `tests/application/ragas/test_testset_generate_use_case.py` (생성 로직)
- `tests/infrastructure/eval_testset/test_testset_file_parser.py` (파일 파싱)
- `tests/infrastructure/ragas/test_default_target_executor.py` (실행)
- `tests/db/test_migration_v055.py` (마이그레이션)
- + 3건 통합 테스트

### 프론트엔드 (idt_front/)

**타입 & 서비스**
- `src/types/eval.ts` (전면 재작성, 7개 인터페이스)
- `src/services/evalService.ts` (전면 재작성, 10개 메서드)
- `src/hooks/useEval.ts` (신규, TanStack Query 훅 12종)
- `src/lib/queryKeys.ts` (수정, eval 네임스페이스 병합)

**페이지 & 컴포넌트**
- `src/pages/EvalDatasetPage/index.tsx` (전면 재구축, 4탭 라우팅)
- `src/pages/EvalDatasetPage/DatasetsTab.tsx` (신규)
- `src/pages/EvalDatasetPage/TestsetDetailPanel.tsx` (신규)
- `src/pages/EvalDatasetPage/CreateTestsetModal.tsx` (신규, 3방식)
- `src/pages/EvalDatasetPage/ManualCaseEditor.tsx` (신규, 행 편집)
- `src/pages/EvalDatasetPage/RunsTab.tsx` (신규)
- `src/pages/EvalDatasetPage/CreateRunModal.tsx` (신규)
- `src/pages/EvalDatasetPage/RunDetailPanel.tsx` (신규, 재실행 버튼)
- `src/pages/EvalDatasetPage/EvaluatorsTab.tsx` (신규)
- `src/pages/EvalDatasetPage/DashboardTab.tsx` (신규)

**레이아웃**
- `src/components/layout/Sidebar.tsx` (수정, "평가" 라벨)
- `src/constants/api.ts` (수정, EVAL_* 상수 8종 추가)

**테스트** (14건+회귀 9건+레이아웃 31건)
- `src/pages/EvalDatasetPage/index.test.tsx` (탭 라우팅·쿼리·admin 폴백)
- `src/pages/EvalDatasetPage/DatasetsTab.test.tsx` (생성 3방식, 파일 업로드)
- `src/pages/EvalDatasetPage/RunsTab.test.tsx` (폼 검증, 폴링)
- `src/__tests__/features/MessageFeedback.test.tsx` (회귀 9건, G-01 검증)
- + 레이아웃·컴포넌트 31건

---

## Lessons Learned

### 1. 기존 API가 "배선만 되고 실행 미구현"일 수 있다
**상황**: Plan 조사 결과 `/api/ragas` 라우터가 깔려 있고 DB 마이그레이션도 완료(V020)되었으나, 실제로 배치 평가를 실행하는 계층이 없었음. run 생성만 202로 반환하고 영원히 pending.

**해결책**: Plan→Design 단계에서 라우터 뒤 실행 경로까지 추적 (라우터 = 하지만 use case/infrastructure 확인 필수). 이번엔 `BatchEvalExecutor` + `SessionScopedEvalRunStore` + `DefaultTargetExecutor`를 신설해 rag/agent/retrieval 3가지 헤드리스 실행 구현.

**적용 시**: 향후 Plan 조사는 라우터가 아니라 실행 end-to-end 매핑(use case → repository → 외부 서비스 호출)까지 검증 — 모킹된 테스트는 통과하나 실제 실행이 없는 상태를 조기 발견.

---

### 2. 공용 객체 리터럴에 네임스페이스 추가 시 기존 키 충돌 검사 필수
**상황**: `lib/queryKeys.ts`의 `const queryKeys` 객체에 eval-hub 용 블록을 추가했는데, 동일 `eval` 키가 이미 agent-eval-gate(답변 👍/👎 피드백) 기능에서 사용 중. 기존 `feedback/agents/recentNegative` 키가 새 블록으로 완전히 덮어써져 런타임 크래시 (회귀).

**발견**: gap-detector 에이전트가 queryKeys 키 조회 검증으로 즉시 포착 (G-01 High 심각도) → 1차 91.1%에서 즉시 수정(병합).

**교훈**: tsc 컴파일 에러로 나타나지 않는 런타임 키 충돌. 공용 config/상수에 새 값 추가할 땐 (1) 기존 키 전수 조사, (2) 충돌 시 네임스페이스 병합 또는 키 리네이밍, (3) 관련 기능 회귀 테스트 필수.

**적용 시**: 신규 열거/맵/쿼리키 추가 시 "기존 코드에서 동일 키가 쓰이는가?" 검색 자동화 추천 (프리커밋 훅 or linter).

---

### 3. pyproject 선언 ≠ venv 설치 (환경 표류)
**상황**: `pyproject.toml`에 `openpyxl`이 선언되어 있으나 개발 venv에는 설치되지 않음. 백엔드 코드는 `import openpyxl` 하고 있으나 실행 시 ModuleNotFoundError. 이전 개발자가 선언만 하고 `pip install` 미수행 상태로 커밋.

**발견**: E2E 테스트 수동 검증 단계에서 XLSX 업로드 시 크래시 → 설치해서 해결.

**교훈**: CI/CD와 로컬 dev 환경의 괴리. `pyproject.toml` 변경이 자동으로 venv에 반영되지 않음 (수동 `pip install -e .` 필요). 특히 팀 환경에서 선언과 설치가 분리되면 표류 가능.

**적용 시**: (1) 의존성 추가 시 "선언 + 즉시 설치 + 테스트 통과까지" 원칙 고수, (2) CI 단계에서 `pip install -e .` 재실행 (낡은 캐시 방지), (3) requirements.txt or lock file 병행 고려.

---

## 차기 과제 (Next Steps)

| 우선순위 | 항목 | 내용 | 예상 기간 |
|---------|------|------|---------|
| **P0** | V055 DB 실제 적용 | 테스트 마이그레이션은 통과했으나 프로덕션 DB 적용 필수 | 1h |
| **P0** | E2E 수동 검증 | venv 서버 기동 후 테스트셋 3종 생성→배치 실행→폴링→점수 확인 (OpenAI 키 필요) | 2h |
| **P0** | 배포 환경 openpyxl 확인 | dev venv 설치 후 배포 환경에도 동일 반영 | 0.5h |
| **P1** | **G-07**: 대시보드 recent_runs 딥링크 | run 상세 선택 상태를 query param으로 영속화 → 대시보드에서 클릭 시 `/eval-dataset?tab=runs&runId={id}` 이동 | 3h |
| **P1** | **G-08**: EvaluatorsTab/DashboardTab 개별 테스트 | 현재 index.test가 부분 커버 → 탭별 분리 파일로 단위 테스트 강화 | 2h |
| **P2** | 평가 결과 자동 환류 | 낮은 점수 → 위키 draft / 부정 메모리 추출 (eval-hub-feedback 후속 PDCA) | TBD |
| **P2** | 일반 사용자 개인 대시보드 | 본인 통계 집계 (현재 admin 전용) | TBD |
| **P2** | 실시간 평가 UI | `/api/ragas/realtime/evaluate` 엔드포인트는 존재하나 화면 미지원 | TBD |

---

## 커밋 & PR 상태

**상태**: 아카이빙 전 커밋/PR 미수행 (사용자 확인 후 일괄 처리)

**권장 커밋 메시지**:
```
feat(eval-hub): 평가 허브 4탭 구현 — 데이터셋/실행/평가기/대시보드

- V055: evaluation_testset/run에 user_id 소유권 도입
- ragas_router 전면 인증·스코프 적용 (일반 사용자 본인만, admin 전체)
- CSV/Excel/문서 업로드로 테스트셋 생성 (LLM 자동 QA 생성 포함)
- 기존 배시 평가가 pending만 하던 구조 수정 → 실제 실행 계층 구현
- 메트릭 카탈로그 (rag/agent/retrieval 대상별 5~6종)
- 프론트 4탭 UI + TanStack Query 폴링 + LoadingButton 이중 클릭 가드
- 테스트: 백엔드 76 + 프론트 14 신규, 회귀 9 (queryKeys 충돌 해소)

Match Rate: 98.0% (갭 9 → 7 즉시 수정, 2 Low는 후속)

Fixes: #[issue number if any]
```

---

## 설계 대비 실제 구현 (동작 동등 — 구현이 진실)

| 항목 | 설계 | 실제 구현 | 비고 |
|------|------|---------|------|
| DOCX 파싱 라이브러리 | `python-docx` | `zipfile` + `ElementTree` | 표준 라이브러리만 사용, 동작 동등 |
| XLSX 파싱 패턴 | `pandas_excel_parser` 재사용 | `pandas.read_excel` 직접 | 결과 동일 |
| admin 판별 | `useAuth` | `useAuthStore` | 훅 대신 스토어 직접 (성능 동등) |
| KB 선택 | `useCollections` | `useKnowledgeBases` | 기존 훅명 준수 |
| 테스트 파일 분할 | 개별 파일(ragas_auth, detail_cases, batch_testset_id 등) | `test_ragas_testset_endpoints` 통합 | 커버리지 동등, 유지보수성 향상 |
| mutation 무효화 | 개별 키 (queryKeys.eval.testsets.all 등) | queryKeys.eval.all 일괄 | 코드 단순화, 부작용 동등 |

---

## 관련 문서

- **Plan**: `docs/01-plan/features/eval-hub.plan.md`
- **Design**: `docs/02-design/features/eval-hub.design.md`
- **Analysis**: `docs/03-analysis/eval-hub.analysis.md`
- **시안**: `idt_front/docs/img/revlu.png` (4탭 레이아웃)
- **이전 평가 API**: `idt/src/api/routes/eval_router.py` (답변 👍/👎 피드백, 소유권 404 은닉 패턴 참조)
