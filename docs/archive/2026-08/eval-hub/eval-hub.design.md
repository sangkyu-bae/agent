# eval-hub Design Document

> **Summary**: `/eval-dataset`를 4탭 평가 허브(데이터셋/평가 실행/평가기/대시보드)로 재구축 — 기존 `/api/ragas/*` 연결 + 소유권(V055)·cases 반환·testset_id 배치·파일 업로드·문서→QA 생성·메트릭 카탈로그 백엔드 보강
>
> **Project**: sangplusbot (idt + idt_front)
> **Author**: 배상규
> **Date**: 2026-08-03
> **Status**: Draft
> **Plan**: `docs/01-plan/features/eval-hub.plan.md`

---

## 1. 아키텍처 개요

```
[EvalDatasetPage(4탭)] ─ authApiClient(Bearer)
   │
   ├─ 데이터셋 탭 ──→ /api/ragas/testsets*            (목록·상세(cases)·생성·업로드·생성초안·삭제)
   ├─ 평가 실행 탭 ─→ /api/ragas/batch, /runs*        (testset_id 실행·목록 폴링·상세·삭제)
   ├─ 평가기 탭 ───→ /api/ragas/metrics              (읽기전용 카탈로그, 실행 폼과 공유)
   └─ 대시보드 탭 ──→ /api/v1/admin/ragas/dashboard   (admin 전용, 기존 adminRagasService 재사용)

백엔드 레이어 (Thin DDD):
  interfaces: ragas_router (스키마 변환 + user→scope 계산만)
  application: TestsetUseCase(확장)·BatchEvaluationUseCase(확장)·TestsetGenerateUseCase(신규)·MetricCatalog(신규 조회)
  domain: policies.py에 TARGET_METRICS 맵 추가 (메트릭 SoT)
  infrastructure: repository(소유권 필터)·testset_file_parser(신규)·document_text_extractor(신규)
```

**소유권 모델**: `user_id VARCHAR(36) NULL` (V055). 일반 사용자는 `user_id = 본인`만, admin은 전체(레거시 NULL 포함). 라우터가 `scope = None(admin) | user.id(일반)`을 계산해 use case에 전달하고, use case→repository로 내려보낸다. 타인 자원 접근은 404 은닉(`eval_router` 선례).

---

## 2. 백엔드 설계

### 2.1 DB — V055 마이그레이션

파일: `idt/db/migration/V055__alter_evaluation_add_user_id.sql`

```sql
ALTER TABLE evaluation_testset
    ADD COLUMN user_id VARCHAR(36) NULL COMMENT '소유자 사용자 ID (NULL=소유권 도입 이전 레거시, admin만 열람)',
    ADD INDEX ix_evaluation_testset_user_id (user_id);

ALTER TABLE evaluation_run
    ADD COLUMN user_id VARCHAR(36) NULL COMMENT '실행자 사용자 ID (NULL=소유권 도입 이전 레거시, admin만 열람)',
    ADD INDEX ix_evaluation_run_user_id (user_id);
```

- COMMENT 필수 (`test_migration_ddl_comments`가 V054 이후 검사) — ALTER ADD 포함
- FK 없음 (V052 message_feedback 선례와 동일하게 느슨한 참조)
- `infrastructure/ragas/models.py`의 `TestsetModel`·`EvaluationRunModel`에 `user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True, comment="...")` 동일 반영

### 2.2 인증·소유권 배선 (ragas_router 전체)

```python
# ragas_router.py — 모든 엔드포인트 공통
user: User = Depends(get_current_user)
scope_user_id = None if user.role.value == "admin" else str(user.id)
```

| 연산 | 소유권 규칙 |
|------|-------------|
| 목록(list_testsets/list_runs) | `scope_user_id`가 있으면 `WHERE user_id = :scope`, None(admin)이면 무필터 |
| 상세/결과/삭제 | 조회 후 `scope_user_id`와 불일치(또는 미존재) → **404** (403 금지, 존재 은닉) |
| 생성(create/upload/batch/realtime) | `user_id = str(user.id)` 저장 |
| 레거시 NULL 행 | admin 목록에만 노출, 일반 사용자 쿼리엔 절대 미포함 |

변경 시그니처(예): `TestsetUseCase.list_all(limit, offset, request_id, scope_user_id: str | None)` — 기존 파라미터 뒤에 추가. `EvaluationRepository.list_testsets`·`list_runs`·`get_testset`·`get_run`·`delete_*`에 동일 전파. `EvaluationRun` 도메인 엔티티에 `user_id: str | None = None` 필드 추가.

admin_ragas_router는 변경 없음(이미 `require_role("admin")`).

기존 ragas 라우트 테스트는 `app.dependency_overrides[get_current_user]` 픽스처 주입으로 갱신한다.

### 2.3 API 변경·신설 총람

| # | Method | Path | 변경 | 요청 | 응답 |
|---|--------|------|------|------|------|
| A1 | GET | `/api/ragas/testsets` | 인증+스코프 | `limit, offset` | 기존 + `user_id` 필드 |
| A2 | GET | `/api/ragas/testsets/{id}` | **cases 포함** | — | `TestsetDetailResponseBody` (기존 필드 + `cases: list[{question, ground_truth}]`) |
| A3 | POST | `/api/ragas/testsets` | 인증, user_id 저장 | 기존 동일 | 기존 동일 |
| A4 | DELETE | `/api/ragas/testsets/{id}` | 인증+소유권 404 | — | 204 |
| A5 | POST | `/api/ragas/testsets/upload` | **신규** | multipart: `file`(.csv/.xlsx), `name`(form), `description`(form) | `TestsetResponseBody` (201) |
| A6 | POST | `/api/ragas/testsets/generate` | **신규** | multipart: `file`(.pdf/.docx), `max_pairs`(form, 기본 10) | `{source_filename, items: [{question, ground_truth}]}` — **저장 안 함(draft)** |
| A7 | GET | `/api/ragas/metrics` | **신규** | — | `[{key, name, description, target_types, requires_ground_truth}]` |
| A8 | POST | `/api/ragas/batch` | **testset_id 지원** | `testset_id: str \| None` 추가, `testcases` 기본 `[]` | 기존 동일 (202) |
| A9 | GET | `/api/ragas/runs`(+상세/결과/삭제) | 인증+스코프 | 기존 동일 | 기존 + run에 `error_message` 노출 |

**A8 검증**: `testset_id`와 `testcases` 중 정확히 하나만 제공 → 아니면 422. `testset_id`는 소유권 스코프로 로드(타인 것 404), 로드된 cases로 기존 경로 진행. run의 `config`에 `testset_id` 기록(상세 화면 표시용).

**A9 error_message**: `EvalRunDetailBody`에 `error_message: str | None` 추가 — 실패 run의 원인을 화면에 표면화(에러 은닉 금지 규칙).

### 2.4 신규 use case / infrastructure

**(1) 파일 업로드 파싱** — `infrastructure/eval_testset/testset_file_parser.py`

- 확장자 라우팅(kb-excel-upload 패턴): `.csv` → `csv` 모듈(utf-8-sig), `.xlsx` → `pandas_excel_parser` 재사용 경로(pandas)
- 컬럼 매핑: `question`(필수) / `ground_truth`(선택). 한글 별칭 허용: `질문`→question, `정답`·`답변`→ground_truth
- 검증: question 빈 행 스킵, 유효 행 0건이면 `ValueError` → 라우터에서 422 편승(kb-excel-upload 패턴)
- `TestsetUseCase.create_from_file(name, description, file_bytes, filename, request_id, user_id)` 추가 — 파싱 후 기존 `create` 경로 재사용

**(2) 문서→QA 생성** — `application/ragas/testset_generate_use_case.py` + `infrastructure/eval_testset/document_text_extractor.py`

```
흐름: 파일 검증(.pdf/.docx, 크기 상한) → 텍스트 추출(pdf: pymupdf 재사용, docx: python-docx)
     → config.EVAL_QA_GEN_MAX_INPUT_CHARS(기본 20000)로 절단 (doc-extractor 429 방지 선례)
     → LLM structured output으로 QA 쌍 생성 (개수 = min(max_pairs, EVAL_QA_GEN_MAX_PAIRS 기본 15))
     → draft 반환, DB 저장 없음 (사용자 검토 후 A3로 저장)
```

- LLM 호출은 기존 OpenAI 어댑터 경유, 프롬프트는 infrastructure 레이어에 상수로 배치
- 실패(파싱 불가·LLM 오류)는 detail에 원인 포함 422/502로 표면화, 스택 트레이스 로깅
- config 값 하드코딩 금지: `EVAL_QA_GEN_MAX_INPUT_CHARS`, `EVAL_QA_GEN_MAX_PAIRS`, `EVAL_QA_GEN_MODEL`(기본 gpt-4o-mini)을 `src/config.py`에 추가

**(3) 메트릭 카탈로그** — `domain/ragas/policies.py`에 SoT 추가

```python
TARGET_METRICS: dict[str, list[MetricType]] = {
    "rag":       [FAITHFULNESS, ANSWER_RELEVANCY, CONTEXT_PRECISION, CONTEXT_RECALL,
                  ANSWER_CORRECTNESS, ANSWER_SIMILARITY],
    "agent":     [FAITHFULNESS, ANSWER_RELEVANCY, ANSWER_CORRECTNESS, ANSWER_SIMILARITY],
    "retrieval": [HIT_RATE, MRR, NDCG, CONTEXT_PRECISION, CONTEXT_RECALL],
}
```

- 라우터 A7은 이 맵 + `METRICS_REQUIRING_GROUND_TRUTH`를 응답으로 직렬화(한글 name·description은 라우터 레벨 상수 테이블)
- **구현 시 확인**: `ragas_adapter`·`retrieval_metric_calculator`가 실제 지원하는 조합과 대조 후 맵 확정 — 불일치 발견 시 어댑터가 진실
- 배치 실행 검증에도 동일 맵 사용: 대상에 안 맞는 메트릭 요청 → 422

### 2.5 백엔드 테스트 (TDD, 선행 작성)

| 파일 | 검증 |
|------|------|
| `tests/api/test_ragas_auth_scope.py` | 무토큰 401 / 일반 사용자 본인 것만 목록 / 타인 상세·삭제 404 / admin 전체+레거시 NULL 열람 |
| `tests/api/test_ragas_testset_detail_cases.py` | A2 cases 포함 응답 |
| `tests/api/test_ragas_batch_testset_id.py` | testset_id 실행 / 둘 다·둘 다 없음 422 / 타인 testset 404 / 인라인 하위호환 |
| `tests/infrastructure/eval_testset/test_testset_file_parser.py` | csv·xlsx 파싱, 한글 별칭, 빈 파일 ValueError |
| `tests/application/ragas/test_testset_generate_use_case.py` | 절단·개수 상한·draft 무저장 (LLM 모킹) |
| `tests/api/test_ragas_metrics.py` | 카탈로그 스키마·대상-메트릭 검증 422 |
| `tests/db/test_migration_ddl_comments.py` | V055 COMMENT (기존 테스트가 자동 검사) |

주의: Windows 이벤트 루프 teardown 산발 실패(기존 이슈) — 신규 파일은 격리 실행으로 검증.

---

## 3. 프론트엔드 설계

### 3.1 라우팅·네비

- 경로 `/eval-dataset` 유지, `AppSidebar`·`Sidebar`의 메뉴 라벨을 "평가"로 변경
- 페이지 내부 탭은 URL 쿼리 `?tab=datasets|runs|evaluators|dashboard` (새로고침·공유 유지). 기본 `datasets`
- `dashboard` 탭은 `useAuth`의 role이 admin일 때만 탭 버튼 렌더 (직접 URL 진입 시 admin 아니면 datasets로 폴백)

### 3.2 타입 — `types/eval.ts` 전면 재작성 (snake_case, adminRagas 타입과 동일 규칙)

```ts
export interface TestCaseItem { question: string; ground_truth: string | null; }
export interface Testset { id: string; name: string; description: string; case_count: number; created_at: string; }
export interface TestsetDetail extends Testset { cases: TestCaseItem[]; }
export interface GeneratedDraft { source_filename: string; items: TestCaseItem[]; }
export interface MetricInfo { key: string; name: string; description: string;
  target_types: EvalTargetType[]; requires_ground_truth: boolean; }
export type EvalTargetType = 'rag' | 'agent' | 'retrieval';
export type EvalRunStatus = 'pending' | 'running' | 'completed' | 'failed';
export interface EvalRun { id: string; eval_type: string; target_type: EvalTargetType;
  status: EvalRunStatus; total_cases: number; created_at: string;
  completed_at: string | null; summary: Record<string, number>; error_message?: string | null; }
export interface EvalResultItem { id: string; question: string; answer: string;
  ground_truth: string | null; contexts: string[]; scores: Record<string, number>; created_at: string; }
export interface BatchEvalPayload { target_type: EvalTargetType; metrics: string[];
  testset_id: string; top_k?: number; sample_ratio?: number; llm_model?: string;
  agent_id?: string; collection_name?: string; }
export interface Paginated<T> { items: T[]; total: number; limit: number; offset: number; }
```

- 기존 `EvalDatasetItem`·`EvalDatasetResponse`·`EvalExtractRequest` 삭제, `constants/api.ts`의 `EVAL_DATASET_EXTRACT` 제거 후 `RAGAS_TESTSETS`·`RAGAS_TESTSET_DETAIL(id)`·`RAGAS_TESTSET_UPLOAD`·`RAGAS_TESTSET_GENERATE`·`RAGAS_METRICS`·`RAGAS_BATCH`·`RAGAS_RUNS`·`RAGAS_RUN_DETAIL(id)`·`RAGAS_RUN_RESULTS(id)` 추가

### 3.3 서비스·훅

- `evalService.ts` 전면 재작성: **authApiClient** 경유 (현 apiClient는 토큰 미주입), 목록·상세·생성·업로드(multipart)·생성초안(multipart)·삭제·메트릭·배치·runs 목록/상세/결과/삭제
- `hooks/useEval.ts` 신설 (TanStack Query):
  - `useTestsets(params)` / `useTestsetDetail(id)` / `useCreateTestset()` / `useUploadTestset()` / `useGenerateDraft()` / `useDeleteTestset()`
  - `useEvalMetrics()` (staleTime 길게 — 정적 카탈로그)
  - `useStartBatchEval()` / `useEvalRuns(params)` / `useEvalRunDetail(id)` / `useEvalRunResults(id, page)` / `useDeleteEvalRun()`
  - **폴링**: `useEvalRuns`는 `refetchInterval: (q) => 목록에 pending|running 있으면 5000, 없으면 false`. 상세도 동일 규칙
  - mutation 성공 시 `queryKeys` prefix 무효화 (`['eval','testsets']`, `['eval','runs']`) — `lib/queryKeys.ts`에 `eval` 네임스페이스 추가
- 대시보드 탭은 **기존 `adminRagasService` + `types/adminRagas.ts` 재사용** (현재 미사용 상태로 존재) + `useAdminRagasDashboard()` 훅 신설

### 3.4 컴포넌트 트리

```
pages/EvalDatasetPage/
  index.tsx              — 헤더("평가") + 탭바 + 탭 라우팅 (레이아웃만, 로직 없음)
  DatasetsTab.tsx        — 검색인풋 + 샘플 다운로드 + 생성 버튼 + 목록/빈상태
  TestsetDetailPanel.tsx — 선택 테스트셋 QA 테이블 (검색어로 클라이언트 필터)
  CreateTestsetModal.tsx — 생성 방식 3종 세그먼트: 직접 입력 | 파일 업로드 | 문서에서 생성
  ManualCaseEditor.tsx   — QA 행 추가/삭제/편집 (직접 입력 + 생성 draft 검토 공용)
  RunsTab.tsx            — 실행 목록 테이블(상태 배지·폴링) + "평가 실행" 버튼
  CreateRunModal.tsx     — 대상/테스트셋/메트릭/모델/top_k/sample_ratio 폼
  RunDetailPanel.tsx     — 요약 점수 카드 + error_message + 케이스별 결과 테이블(페이지네이션)
  EvaluatorsTab.tsx      — 메트릭 카드 그리드 (읽기전용)
  DashboardTab.tsx       — admin 위젯: 총 실행·상태/대상 분포·평균 메트릭·최근 실행
```

### 3.5 탭별 상세 스펙

**데이터셋 탭** (시안 revlu.png 준수)
- 상단: 좌측 검색 인풋("QA 쌍 검색...") / 우측 `샘플 데이터셋 다운로드`(보조 버튼) + `+ 데이터셋 생성`(주 버튼)
- 빈 상태: DB 아이콘 + "사용 가능한 데이터셋이 없습니다." + "+ 시작하려면 첫 번째 데이터셋을 생성하세요." (클릭 시 생성 모달)
- 목록: 테스트셋 카드/행(이름·설명·케이스 수·생성일·삭제) → 클릭 시 상세 패널에 QA 테이블
- 검색: 테스트셋 이름 + 열린 상세의 question/ground_truth 클라이언트 필터 (백엔드 검색 API 없음 — 케이스는 상세에 전량 포함)
- 샘플 다운로드: 프론트 생성 CSV(BOM 포함) — 헤더 `question,ground_truth` + 예시 2행
- **생성 모달 3방식**:
  1. 직접 입력: `ManualCaseEditor`로 행 편집 → `useCreateTestset`
  2. 파일 업로드: .csv/.xlsx 드래그&드롭 → `useUploadTestset` (A5) → 성공 시 목록 무효화
  3. 문서에서 생성: .pdf/.docx 업로드 → `useGenerateDraft` (A6, 로딩 표시) → **draft를 ManualCaseEditor에 프리필** → 사용자가 수정/삭제 후 저장(`useCreateTestset`) — 검토 없이는 저장되지 않음
- 모든 제출 버튼은 `LoadingButton`(isPending) — 이중 클릭 가드

**평가 실행 탭**
- 폼 필드: ① target_type 라디오 3종 → ② agent 선택(`useMyBuilderAgents`, target=agent일 때) / 컬렉션 선택(`useCollections`, rag·retrieval일 때) → ③ 테스트셋 셀렉트(`useTestsets`) → ④ 메트릭 체크박스(`useEvalMetrics`를 target_types로 필터, ground_truth 필요 메트릭엔 배지) → ⑤ 고급: llm_model(`useLlmModels`, 기본 gpt-4o-mini)·top_k·sample_ratio
- 검증: 메트릭 1개 이상, 대상별 필수 선택(agent_id/collection_name) — 미충족 시 제출 비활성 대신 인라인 에러(jsdom noValidate 선례 준수)
- 실행 → 202 응답 후 목록 무효화, 새 run이 pending으로 나타나고 폴링으로 진행 갱신
- 목록: 상태 배지(pending=회색·running=파랑·completed=초록·failed=빨강), failed 행 클릭 시 상세에서 `error_message` 표시 + 동일 조건 재실행 버튼(폼 프리필)

**평가기 탭**: `useEvalMetrics` 카드 그리드 — 이름·설명·적용 대상 칩(rag/agent/retrieval)·"ground truth 필요" 배지. CTA 없음(읽기전용)

**대시보드 탭**(admin): 총 실행 수 / status_counts·target_type_counts 칩 / avg_metrics 바 / recent_runs 테이블(클릭 → 평가 실행 탭 상세)

### 3.6 프론트 테스트 (Vitest + MSW + RTL)

- 파일별 `server.listen/resetHandlers/close` 3종 훅 직접 선언(전역 setup 없음), 실행은 `--pool=threads`
- `DatasetsTab.test.tsx`: 빈 상태 → 생성 모달 3방식 전환, 수동 생성 POST 페이로드 검증, 업로드 성공 후 목록 갱신, draft 프리필 흐름
- `RunsTab.test.tsx`: 폼 검증(메트릭 0개 시 인라인 에러), 배치 202 → 목록 무효화, failed run error_message 노출
- `EvaluatorsTab.test.tsx` / `DashboardTab.test.tsx`: 렌더·admin 탭 가시성(useAuth 모킹)
- `index.test.tsx`: 탭 전환·URL 쿼리 동기화·비admin dashboard 폴백

---

## 4. 구현 순서

| 단계 | 작업 | 산출물 |
|------|------|--------|
| 1 | V055 + 모델 comment + 인증·스코프 (TDD) | 마이그레이션, models.py, ragas_router, use case·repo 시그니처 |
| 2 | A2 cases 반환 + A8 testset_id 배치 + A9 error_message | 라우터·스키마·use case |
| 3 | A5 업로드 파서 + A7 메트릭 카탈로그 | testset_file_parser, policies.TARGET_METRICS |
| 4 | A6 문서→QA 생성 (config 3종 추가) | document_text_extractor, generate use case |
| 5 | 프론트 기반: constants·types·evalService·useEval·queryKeys | 타입/서비스/훅 |
| 6 | 데이터셋 탭 (빈상태→목록→생성 3방식) | DatasetsTab 외 4컴포넌트 |
| 7 | 평가 실행 탭 (폼→폴링→상세) | RunsTab 외 2컴포넌트 |
| 8 | 평가기·대시보드 탭 + 사이드바 라벨 | EvaluatorsTab, DashboardTab |
| 9 | /api-contract-sync 점검 + E2E 수동 검증 (venv 서버 기동 주의) | 검증 체크리스트 |

---

## 5. 설계 결정 기록

| 결정 | 근거 |
|------|------|
| draft 반환 후 검토 저장 (자동 저장 금지) | LLM 생성 품질 편차 — 사용자 확인이 게이트 (Plan 리스크 1) |
| snake_case 타입 유지 | adminRagas 등 기존 타입 규칙과 통일, 케이스 변환 계층 없음 |
| authApiClient 사용 (apiClient 아님) | apiClient는 토큰 미주입 — 인증 신설된 ragas API와 불일치 |
| 케이스 검색은 클라이언트 필터 | 상세 응답에 cases 전량 포함되므로 백엔드 검색 API 불요 (YAGNI) |
| testset_id·testcases 배타 검증 | 하위호환(FR-10) 유지하면서 화면은 testset_id만 사용 |
| dashboard 탭 admin 전용 + 기존 서비스 재사용 | adminRagasService·types/adminRagas가 이미 존재(미사용) — 신규 코드 최소화 |
| TARGET_METRICS를 domain policies에 배치 | 메트릭 SoT 단일화 — 카탈로그 API와 배치 검증이 같은 맵 사용 |
| user_id FK 없음 | V052 message_feedback 선례, 사용자 삭제 시 평가 이력 보존 |

---

## Next Step

`/pdca do eval-hub` — 구현 순서 1단계(V055 + 인증·스코프 TDD)부터 착수.
