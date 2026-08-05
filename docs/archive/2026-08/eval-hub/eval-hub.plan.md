# eval-hub Planning Document

> **Summary**: 목데이터뿐인 `/eval-dataset` 페이지를 revlu.png 시안(데이터셋/평가 실행/평가기/대시보드 4탭)의 실제 동작하는 평가 허브로 전환 — 기존 RAGAS 백엔드 스택에 연결하고, 소유권(본인/관리자) 모델과 문서→QA 자동 생성 API를 신설
>
> **Project**: sangplusbot (idt + idt_front)
> **Author**: 배상규
> **Date**: 2026-08-03
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | `/eval-dataset`는 파일을 올리면 2초 뒤 하드코딩된 목데이터 5건을 보여주는 데모 화면이다. 반면 백엔드에는 RAGAS 평가 스택(테스트셋 CRUD·배치 평가·실행 이력·관리자 대시보드)이 이미 완전히 배선되어 있으나 이를 쓰는 화면이 없다. 평가 API에는 인증·소유권 개념도 없다. |
| **Solution** | 페이지를 4탭 평가 허브(데이터셋/평가 실행/평가기/대시보드)로 재구축해 기존 `/api/ragas/*` API에 실제 연결한다. 데이터셋 생성은 수동 입력·CSV/Excel 업로드·문서 LLM 자동 생성(신규 API) 3종을 지원하고, 테스트셋/실행에 user_id 소유권(V055)을 도입해 본인 것만 보이되 관리자는 전체를 본다. |
| **Function/UX Effect** | 운영자가 화면에서 QA 데이터셋을 만들고(3가지 방법), 대상(agent/rag/retrieval)·메트릭을 골라 배치 평가를 실행하고, 진행 상태와 케이스별 점수를 확인한다. 평가기 탭은 사용 가능한 RAGAS 메트릭 카탈로그를 읽기전용으로 보여준다. |
| **Core Value** | P2(에이전트 소유자/KB 운영자)가 자기 에이전트·KB의 품질을 **수치로 검증하는 셀프서비스 루프** 완성 — 지금까지 만든 평가 인프라(V020)가 처음으로 사용자에게 노출된다. |

---

## 1. Overview

### 1.1 Purpose

`/eval-dataset` 목업 페이지를 실제 기능하는 평가 허브로 전환한다. 시안(`idt_front/docs/img/revlu.png`)의 4탭 구조를 따르되, 이번 범위는 **3탭 완전 구현 + 평가기 탭 읽기전용 카탈로그**다.

### 1.2 Background — 현황 조사 (완료)

| # | 확인 지점 | 결과 |
|---|-----------|------|
| 1 | `idt_front/src/pages/EvalDatasetPage/index.tsx` | 문서 업로드 → `setTimeout(2000)` → `MOCK_ITEMS` 5건 표시 → CSV 다운로드. **API 호출 없음** |
| 2 | `idt_front/src/services/evalService.ts` → `/api/eval/extract` | 서비스는 있으나 페이지가 사용하지 않고, **해당 엔드포인트가 백엔드에 없음** (dead constant) |
| 3 | `idt/src/api/routes/ragas_router.py` (`/api/ragas`) | 테스트셋 CRUD, 배치 평가(202+BackgroundTasks, rag/agent/retrieval), 실행 목록/상세/결과/삭제, 실시간 평가 — **main.py에 DI 배선 완료, 그러나 인증 없음** |
| 4 | `idt/src/api/routes/admin_ragas_router.py` (`/api/v1/admin/ragas`) | 대시보드 통계·실행 목록·상세·테스트셋 목록, `require_role("admin")` |
| 5 | `idt/src/infrastructure/ragas/models.py` + `V020__create_evaluation_tables.sql` | `evaluation_run` / `evaluation_result` / `evaluation_testset` — **user_id(소유자) 컬럼 없음** |
| 6 | `GET /api/ragas/testsets/{id}` 응답 | `case_count`만 반환, **cases(QA 쌍 목록) 미반환** → 시안의 "QA 쌍 검색·열람" 불가 |
| 7 | 배치 평가 요청 | `testcases`를 인라인 배열로만 받음 — **testset_id로 실행하는 경로 없음** |

결론: 프론트 재구축이 중심이고, 백엔드는 (a) 소유권 도입, (b) 테스트셋 cases 반환, (c) testset_id 기반 배치 실행, (d) 문서→QA LLM 생성, (e) 메트릭 카탈로그 5건의 보강이 필요하다.

### 1.3 사용자 결정 사항 (확정)

1. **탭 범위**: 데이터셋·평가 실행·대시보드는 완전 구현, **평가기 탭은 읽기전용 메트릭 카탈로그**
2. **데이터셋 생성 3종 모두**: 수동 QA 입력 + CSV/Excel 업로드 + 문서 업로드→LLM 자동 생성(신규 API)
3. **권한**: 일반 사용자는 **본인이 만든 테스트셋·실행만** 접근, 관리자는 전체 열람
4. **평가 대상**: rag / agent / retrieval **3종 모두 노출**

### 1.4 Related Documents

- 시안: `idt_front/docs/img/revlu.png`
- 평가 테이블: `idt/db/migration/V020__create_evaluation_tables.sql`
- RAGAS 도메인 정책(허용 메트릭): `idt/src/domain/ragas/policies.py`
- 소유권 404 은닉 선례: `idt/src/api/routes/eval_router.py` (agent-eval-gate)
- 문서 파싱 선례: kb-excel-upload(확장자 라우팅 파서), doc-extractor(LLM 입력 20,000자 절단으로 429 방지)
- DDL 규칙: 테이블·전 컬럼 COMMENT 필수 (`tests/db/test_migration_ddl_comments.py`, V054 이후 검사)

---

## 2. Scope

### 2.1 In Scope

**백엔드 (idt/)**

- [ ] **V055 마이그레이션**: `evaluation_testset`·`evaluation_run`에 `user_id VARCHAR(36) NULL` 추가 (COMMENT 필수, SQLAlchemy `comment=` 동일 반영). 기존 행은 NULL(레거시) 유지
- [ ] **인증·소유권**: `/api/ragas/*` 전 엔드포인트에 `get_current_user` 적용. 목록은 본인 것만(관리자는 전체), 타인/미존재 자원은 404 은닉 (eval_router 패턴)
- [ ] **테스트셋 상세에 cases 포함**: `GET /api/ragas/testsets/{id}` 응답 확장 (QA 쌍 열람용)
- [ ] **testset_id 기반 배치 실행**: `POST /api/ragas/batch`에 `testset_id` 옵션 추가 — 백엔드가 케이스 로드 (인라인 `testcases`는 하위호환 유지)
- [ ] **CSV/Excel 테스트셋 업로드**: `POST /api/ragas/testsets/upload` (multipart) — question/ground_truth 컬럼 파싱 후 저장 (kb-excel-upload 파서 패턴 재사용)
- [ ] **문서→QA 자동 생성**: `POST /api/ragas/testsets/generate` (multipart, PDF/DOCX) — 문서 파싱 후 LLM이 QA 쌍 생성, **저장 전 검토용 draft 반환** → 사용자가 확인 후 기존 create API로 저장. LLM 입력 상한 적용(20,000자 절단 선례)
- [ ] **메트릭 카탈로그**: `GET /api/ragas/metrics` — 메트릭 key·이름·설명·적용 가능 target_type (SoT는 `domain/ragas/policies.py`)

**프론트엔드 (idt_front/)**

- [ ] `EvalDatasetPage` → **4탭 평가 허브로 재구축** (경로 `/eval-dataset` 유지, 메뉴 라벨 "평가")
- [ ] **데이터셋 탭**: 테스트셋 목록·상세(QA 쌍 테이블+클라이언트 검색)·삭제, 생성 모달 3종(수동/파일 업로드/문서 자동 생성→검토→저장), 샘플 CSV 템플릿 다운로드, 빈 상태 UI(시안 준수)
- [ ] **평가 실행 탭**: 실행 생성 폼(target_type 3종 → agent/컬렉션 선택, 테스트셋 선택, 메트릭 체크박스, llm_model·top_k·sample_ratio), 실행 목록(상태 폴링), 실행 상세(요약 점수+케이스별 결과)
- [ ] **평가기 탭**: 메트릭 카탈로그 읽기전용 카드 목록
- [ ] **대시보드 탭**: **admin에게만 탭 표시** — 기존 `/api/v1/admin/ragas/dashboard` 연결(통계·상태별 카운트·평균 메트릭·최근 실행)
- [ ] 타입·서비스·훅 신설(`types/eval.ts` 재작성, `evalService` 재작성, TanStack Query 훅), dead constant `EVAL_DATASET_EXTRACT` 제거
- [ ] 테스트: 백엔드 pytest(TDD), 프론트 Vitest+MSW(파일별 server.listen 3종 훅, `--pool=threads`)

### 2.2 Out of Scope

- **평가기(커스텀 평가 기준) CRUD** — 백엔드 대응 개념 없음, 읽기전용 카탈로그만. 커스텀 평가기는 후속 PDCA
- **일반 사용자용 개인 대시보드** — 대시보드 탭은 admin 전용(기존 API 재사용). 본인 통계 집계는 후속
- **실시간 평가 UI** (`/realtime/evaluate`) — API는 존재하나 이번 화면 범위 아님
- **평가 실행 결과의 자동 환류**(낮은 점수 → 위키/메모리 연계) — 후속
- **기존 V020 데이터 소급 소유권 부여** — 레거시 행은 user_id NULL로 두고 admin만 열람
- **eval_router(답변 👍/👎 피드백)와의 통합** — 별개 축, 변경 없음

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | 데이터셋 탭에서 본인 테스트셋 목록·상세(QA 쌍)·삭제가 실제 API로 동작한다 | High | Pending |
| FR-02 | 수동 QA 쌍 입력으로 테스트셋을 생성할 수 있다 | High | Pending |
| FR-03 | CSV/Excel 업로드로 테스트셋을 생성할 수 있고, 샘플 템플릿을 다운로드할 수 있다 | High | Pending |
| FR-04 | PDF/DOCX 업로드 시 LLM이 QA 쌍 초안을 생성하고, 사용자가 검토 후 저장한다 | High | Pending |
| FR-05 | 평가 실행 폼에서 대상(agent/rag/retrieval)·테스트셋·메트릭을 선택해 배치 평가를 시작한다 (testset_id 기반) | High | Pending |
| FR-06 | 실행 목록에서 진행 상태(pending/running/completed/failed)를 폴링으로 갱신하고, 상세에서 요약·케이스별 점수를 본다 | High | Pending |
| FR-07 | `/api/ragas/*`는 인증 필수이며, 일반 사용자는 본인 소유 자원만 접근(타인 것 404 은닉), 관리자는 전체 접근 | High | Pending |
| FR-08 | 평가기 탭이 백엔드 메트릭 카탈로그를 읽기전용으로 표시하고, 같은 소스가 실행 폼 메트릭 선택지로 재사용된다 | Medium | Pending |
| FR-09 | 대시보드 탭은 admin에게만 보이고 기존 admin dashboard API 데이터를 표시한다 | Medium | Pending |
| FR-10 | 인라인 `testcases` 배치 요청 등 기존 API 소비 방식은 하위호환을 유지한다 | Medium | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 아키텍처 | Thin DDD 준수 — 소유권 검증은 use case, 파서·LLM은 infrastructure, 라우터는 스키마 변환만 | verify-architecture |
| DB | V055 전 컬럼 COMMENT + 모델 `comment=` 동기화, Repository 내 commit 금지 | `test_migration_ddl_comments` 통과 |
| API 계약 | 백엔드 스키마 변경분을 `idt_front/src/types/` `services/` `hooks/`에 동기화 | /api-contract-sync 체크리스트 |
| LLM 비용 | 문서→QA 생성 입력 20,000자 절단, 생성 개수 상한(기본 10~20쌍) | 설정값, 하드코딩 금지 |
| 테스트 | TDD 선행 — backend pytest / frontend Vitest+MSW+threads pool | Red→Green 확인 |
| UX | 시안(revlu.png)의 탭·빈 상태·버튼 배치 준수, 이중 클릭 방지(LoadingButton 재사용) | 수동 확인 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] 4탭 모두 실제 API 데이터로 렌더 (목데이터·setTimeout 완전 제거)
- [ ] 3가지 생성 경로로 만든 테스트셋이 DB에 저장되고 목록·상세에서 확인됨
- [ ] 테스트셋 선택→배치 평가 실행→상태 완료→케이스별 점수 확인의 E2E 흐름 동작 (수동 검증)
- [ ] 일반 계정으로 타인 테스트셋/실행 접근 시 404, admin 계정으로 전체 열람 확인
- [ ] 백엔드·프론트 테스트 전체 무회귀 (사전 실패분 제외)

### 4.2 Quality Criteria

- [ ] 마이그레이션 V055 1건 (COMMENT 검사 통과), 그 외 스키마 변경 없음
- [ ] lint/빌드 통과, 함수 40줄·if 중첩 2단계 규칙 준수
- [ ] API 응답 스키마와 프론트 타입 일치 (camelCase 변환 규칙 포함)

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 문서→QA LLM 생성 품질·비용 편차 | Medium | Medium | draft 반환 후 사용자 검토·수정을 거쳐 저장(자동 저장 금지), 입력 절단+생성 개수 상한 |
| `/api/ragas/*` 인증 추가로 기존 무인증 소비자 파손 | Medium | Low | 전수 조사 결과 프론트 소비자 없음(dead constant뿐). 테스트 픽스처만 인증 주입으로 갱신 |
| 배치 평가가 BackgroundTasks라 서버 재시작 시 실행 유실 | Medium | Medium | 이번 범위에선 status=failed 노출·재실행 버튼으로 완화, 큐 도입은 후속 |
| user_id NULL 레거시 행 처리 모호 | Low | Medium | NULL은 admin만 목록 노출로 정책 고정, 일반 사용자 쿼리는 `user_id = :me`만 |
| Excel 파싱 의존성(프론트 vs 백엔드) 중복 | Low | Low | 백엔드 파싱으로 단일화 (kb-excel-upload 확장자 라우팅 파서 재사용) |
| 폴링 주기·중복 실행으로 UX 저하 | Low | Medium | TanStack Query refetchInterval(완료 시 중단), LoadingButton으로 이중 제출 가드 |
| RAGAS 평가 자체 실패(외부 LLM 429 등) | Medium | Medium | run.error_message를 상세 화면에 표면화 (에러 은닉 금지 선례 준수) |

---

## 6. 구현 순서 (Design 단계에서 상세화)

1. **백엔드 기반**: V055 + 모델 + 인증·소유권 (TDD) → 테스트셋 cases 반환·testset_id 배치
2. **백엔드 신규**: upload(CSV/Excel) → metrics 카탈로그 → generate(문서→QA LLM)
3. **프론트 기반**: 타입·서비스·훅 → 4탭 레이아웃·라우팅
4. **프론트 탭별**: 데이터셋 → 평가 실행 → 평가기 → 대시보드
5. **통합**: api-contract-sync 점검 → E2E 수동 검증

---

## Next Step

`/pdca design eval-hub` — 엔드포인트별 요청/응답 스키마, 소유권 쿼리 조건, LLM 생성 프롬프트·상한 설정, 탭별 컴포넌트 트리를 확정한다.
