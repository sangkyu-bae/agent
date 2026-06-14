# admin-ragas-dashboard Planning Document

> **Summary**: 관리자 전용 RAGAS 평가 대시보드 API 및 프론트엔드 페이지 구현
>
> **Project**: sangplusbot (idt)
> **Version**: -
> **Author**: AI Assistant
> **Date**: 2026-05-18
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | RAGAS 평가 데이터(evaluation_run, evaluation_result, evaluation_testset)가 DB에 축적되고 있으나, 관리자가 이를 한눈에 확인할 수 있는 전용 API와 화면이 없음 |
| **Solution** | `/api/v1/admin/ragas/` 하위에 admin 권한 보호된 대시보드 통계 + 조회 API를 신설하고, 프론트엔드에 `AdminRagasPage` 대시보드 페이지를 추가 |
| **Function/UX Effect** | 관리자가 Admin 화면에서 평가 실행 현황, 메트릭 평균 점수, target_type별 비교, 개별 결과 상세까지 한 곳에서 확인 가능 |
| **Core Value** | RAG 시스템의 품질 모니터링을 관리자가 직접 수행하여, 검색 품질 저하를 조기에 발견하고 대응할 수 있는 관리 체계 확보 |

---

## 1. Overview

### 1.1 Purpose

RAGAS 평가 결과를 관리자가 전용 대시보드에서 확인할 수 있도록 한다.
현재 평가 실행/결과 데이터는 DB에 쌓이고 있고 내부 API(`/api/ragas/`)도 존재하지만,
관리자 권한 보호가 없고 통계/집계 엔드포인트가 없어 관리자가 활용하기 어렵다.

### 1.2 Background

- **기존 RAGAS API** (`/api/ragas/`): 배치 평가 실행, 실시간 평가, 테스트셋 CRUD 제공. 그러나 admin role 보호 없음.
- **기존 Admin API** (`/api/v1/admin/`): 사용자 승인/거절만 존재.
- **기존 Admin 프론트엔드**: `AdminUsersPage`, `AdminDepartmentsPage`만 존재. RAGAS 관련 페이지 없음.
- DB 테이블 3개: `evaluation_run`, `evaluation_result`, `evaluation_testset`

### 1.3 Related Documents

- 기존 RAGAS 라우터: `src/api/routes/ragas_router.py`
- 기존 Admin 라우터: `src/api/routes/admin_router.py`
- RAGAS 도메인 인터페이스: `src/domain/ragas/interfaces.py`
- 프론트엔드 Admin 레이아웃: `idt_front/src/components/layout/AdminLayout.tsx`

---

## 2. Scope

### 2.1 In Scope

- [ ] Admin 전용 RAGAS API 신설 (`/api/v1/admin/ragas/`)
  - 대시보드 통계 요약 (전체 평가 횟수, 평균 점수, 상태별 분포)
  - 평가 실행 목록 조회 (필터링 + 페이지네이션)
  - 평가 실행 상세 + 개별 결과 조회
  - 테스트셋 목록/상세 조회
- [ ] 프론트엔드 `AdminRagasPage` 페이지 구현
  - 통계 카드 (총 평가 횟수, 평균 점수, 성공/실패 비율)
  - 평가 실행 목록 테이블 (필터, 정렬, 페이지네이션)
  - 실행 상세 모달/드릴다운 (개별 Q&A 결과 + 메트릭 점수)
  - 테스트셋 목록 확인
- [ ] Admin 사이드바에 "RAGAS 평가" 메뉴 항목 추가
- [ ] API 계약 동기화 (타입, 서비스, 엔드포인트 상수)

### 2.2 Out of Scope

- 기존 `/api/ragas/` API 수정 (그대로 유지)
- 평가 실행/삭제 기능 (기존 API로 충분)
- 시계열 추이 차트 (v2에서 고려)
- 테스트셋 생성/편집 UI (기존 API 활용)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | **대시보드 통계 API**: 전체 평가 실행 수, 상태별(pending/running/completed/failed) 수, target_type별 수, 최근 N건 평균 메트릭 점수 반환 | High | Pending |
| FR-02 | **평가 실행 목록 API**: target_type, eval_type, status 필터 + created_at 정렬 + 페이지네이션. 각 Run에 메트릭 요약(평균 점수) 포함 | High | Pending |
| FR-03 | **평가 실행 상세 API**: run_id로 실행 정보 + 전체 개별 결과(question, answer, contexts, ground_truth, metrics) 조회 | High | Pending |
| FR-04 | **테스트셋 목록 API**: 페이지네이션 포함 테스트셋 리스트 조회 | Medium | Pending |
| FR-05 | **프론트엔드 대시보드**: 통계 카드(총 실행 수, 완료율, 평균 faithfulness/answer_relevancy 점수) 표시 | High | Pending |
| FR-06 | **프론트엔드 실행 목록 테이블**: 필터(target_type, status), 페이지네이션, 행 클릭 시 상세로 이동 | High | Pending |
| FR-07 | **프론트엔드 실행 상세**: 실행 메타 정보 + 개별 결과 테이블(질문/답변/점수). 메트릭별 점수 색상 표시(높음=녹색, 낮음=빨강) | High | Pending |
| FR-08 | **Admin 권한 보호**: 모든 API에 `require_role("admin")` 적용 | High | Pending |
| FR-09 | **Admin 사이드바 메뉴 추가**: AdminLayout 사이드바에 "RAGAS 평가" 항목 추가 | Medium | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Performance | 대시보드 통계 API 응답 < 500ms (1만 건 기준) | 로컬 테스트 |
| Security | Admin role 필수. 일반 사용자 접근 시 403 반환 | 테스트 케이스 |
| Usability | 테이블 목록 20건 기본, 최대 100건 페이지네이션 | UI 검증 |

---

## 4. API Design

### 4.1 신규 엔드포인트

```
GET  /api/v1/admin/ragas/dashboard     → 대시보드 통계 요약
GET  /api/v1/admin/ragas/runs          → 평가 실행 목록 (필터, 페이지네이션)
GET  /api/v1/admin/ragas/runs/{run_id} → 평가 실행 상세 + 결과 포함
GET  /api/v1/admin/ragas/testsets      → 테스트셋 목록
```

### 4.2 응답 스키마 설계

#### `GET /api/v1/admin/ragas/dashboard`

```json
{
  "total_runs": 42,
  "status_counts": {
    "pending": 1,
    "running": 0,
    "completed": 38,
    "failed": 3
  },
  "target_type_counts": {
    "rag": 30,
    "agent": 10,
    "retrieval": 2
  },
  "avg_metrics": {
    "faithfulness": 0.82,
    "answer_relevancy": 0.75,
    "context_precision": 0.68
  },
  "recent_runs": [
    {
      "id": "uuid",
      "eval_type": "batch",
      "target_type": "rag",
      "status": "completed",
      "total_cases": 50,
      "created_at": "2026-05-18T10:00:00",
      "completed_at": "2026-05-18T10:05:00",
      "summary": {"faithfulness": 0.85, "answer_relevancy": 0.78}
    }
  ]
}
```

#### `GET /api/v1/admin/ragas/runs`

Query params: `target_type`, `eval_type`, `status`, `limit`(default 20), `offset`(default 0)

```json
{
  "items": [
    {
      "id": "uuid",
      "eval_type": "batch",
      "target_type": "rag",
      "status": "completed",
      "total_cases": 50,
      "created_at": "...",
      "completed_at": "...",
      "summary": {"faithfulness": 0.85}
    }
  ],
  "total": 42,
  "limit": 20,
  "offset": 0
}
```

#### `GET /api/v1/admin/ragas/runs/{run_id}`

```json
{
  "id": "uuid",
  "eval_type": "batch",
  "target_type": "rag",
  "status": "completed",
  "total_cases": 50,
  "config": {},
  "created_at": "...",
  "completed_at": "...",
  "summary": {"faithfulness": 0.85},
  "results": [
    {
      "id": "uuid",
      "question": "...",
      "answer": "...",
      "ground_truth": "...",
      "contexts": ["..."],
      "scores": {"faithfulness": 0.9, "answer_relevancy": 0.8},
      "created_at": "..."
    }
  ],
  "results_total": 50
}
```

#### `GET /api/v1/admin/ragas/testsets`

Query params: `limit`, `offset`

```json
{
  "items": [
    {
      "id": "uuid",
      "name": "금융상품 테스트셋",
      "description": "...",
      "case_count": 30,
      "created_at": "..."
    }
  ],
  "total": 5,
  "limit": 20,
  "offset": 0
}
```

---

## 5. Implementation Plan

### 5.1 백엔드 (idt/)

| Step | Task | Files |
|------|------|-------|
| 1 | Admin RAGAS UseCase 생성 | `src/application/ragas/admin_eval_use_case.py` |
| 2 | Repository에 통계 집계 메서드 추가 | `src/domain/ragas/interfaces.py`, `src/infrastructure/ragas/repository.py` |
| 3 | Admin RAGAS 라우터 생성 | `src/api/routes/admin_ragas_router.py` |
| 4 | main.py에 라우터 등록 + DI 연결 | `src/api/main.py` |
| 5 | 테스트 작성 | `tests/application/ragas/test_admin_eval_use_case.py`, `tests/api/test_admin_ragas_router.py` |

### 5.2 프론트엔드 (idt_front/)

| Step | Task | Files |
|------|------|-------|
| 1 | API 엔드포인트 상수 추가 | `src/constants/api.ts` |
| 2 | 타입 정의 | `src/types/adminRagas.ts` |
| 3 | API 서비스 함수 | `src/services/adminRagasService.ts` |
| 4 | TanStack Query 훅 | `src/hooks/useAdminRagas.ts` |
| 5 | AdminRagasPage 구현 (대시보드 + 목록 + 상세) | `src/pages/AdminRagasPage/index.tsx` |
| 6 | AdminLayout 사이드바 메뉴 추가 | `src/components/layout/AdminLayout.tsx` |
| 7 | App.tsx 라우트 추가 | `src/App.tsx` |

---

## 6. Architecture Considerations

### 6.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| **Starter** | Simple structure | Static sites, portfolios | |
| **Dynamic** | Feature-based modules, BaaS | Web apps with backend | |
| **Enterprise** | Strict layer separation, DI | High-traffic systems | **X** |

### 6.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| API 구조 | 기존 API 수정 / Admin 전용 신설 | Admin 전용 신설 | 기존 API(평가 실행용)와 관리자 조회용 분리. 권한 모델이 다름 |
| UseCase 재사용 | 기존 EvalResultUseCase 확장 / 별도 UseCase | 별도 UseCase | 통계 집계 로직은 조회 UseCase와 관심사가 다름 |
| Repository 메서드 | 새 Repository / 기존에 메서드 추가 | 기존에 메서드 추가 | 동일 테이블 접근이므로 Interface에 통계 메서드만 추가 |
| 프론트엔드 페이지 구조 | 단일 페이지 / 탭 분리 | 단일 페이지 + 섹션 | 대시보드 카드 → 실행 목록 → 클릭 시 상세 모달. 간결한 UX |

### 6.3 Clean Architecture Approach

```
Enterprise Level:

Backend (idt/):
  domain/ragas/interfaces.py        ← get_dashboard_stats 등 인터페이스 추가
  application/ragas/admin_eval_use_case.py  ← 신규 UseCase
  infrastructure/ragas/repository.py ← 통계 쿼리 구현
  api/routes/admin_ragas_router.py   ← 신규 라우터

Frontend (idt_front/):
  types/adminRagas.ts               ← 응답 타입 정의
  services/adminRagasService.ts     ← API 호출
  hooks/useAdminRagas.ts            ← TanStack Query 훅
  pages/AdminRagasPage/index.tsx    ← 대시보드 페이지
```

---

## 7. Convention Prerequisites

### 7.1 Existing Project Conventions

- [x] `CLAUDE.md` has coding conventions section
- [x] `docs/rules/` 세부 규칙 존재 (db-session, logging, testing 등)
- [x] Thin DDD 아키텍처 (domain → application → infrastructure)
- [x] TDD 필수 (테스트 먼저 작성)
- [x] Admin 권한: `require_role("admin")` 패턴 확립됨

### 7.2 Conventions to Follow

| Category | Rule |
|----------|------|
| 레이어 의존성 | domain ← application ← infrastructure ← interfaces |
| Repository | commit/rollback 호출 금지 (세션 외부 관리) |
| 로깅 | LoggerInterface 사용, print() 금지 |
| 라우터 | DI 플레이스홀더 패턴 (main.py에서 override) |
| 프론트 API 상수 | `idt_front/src/constants/api.ts`에 추가 |
| 프론트 타입 | `idt_front/src/types/`에 별도 파일 |

### 7.3 Environment Variables Needed

신규 환경변수 불필요. 기존 MySQL 연결 설정 그대로 사용.

---

## 8. Success Criteria

### 8.1 Definition of Done

- [ ] 4개 Admin RAGAS API 엔드포인트 구현 완료
- [ ] 모든 API에 admin role 보호 적용
- [ ] AdminRagasPage 대시보드 + 목록 + 상세 UI 구현
- [ ] Admin 사이드바에 메뉴 추가
- [ ] 백엔드 UseCase + Router 테스트 작성 및 통과
- [ ] API 계약 동기화 (타입, 서비스, 상수)

### 8.2 Quality Criteria

- [ ] 백엔드 테스트 커버리지 80% 이상
- [ ] lint 에러 0건
- [ ] 관리자 로그인 후 대시보드 접근 가능 확인
- [ ] 일반 사용자 접근 시 403 반환 확인

---

## 9. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 대시보드 통계 쿼리 성능 (데이터 증가 시) | Medium | Low | 현재 데이터 규모에서는 문제 없음. 추후 필요시 캐싱 또는 materialized view 고려 |
| 기존 RAGAS API와 역할 혼동 | Low | Medium | URL prefix 명확히 분리 (`/api/ragas/` vs `/api/v1/admin/ragas/`) |
| 프론트엔드 Admin 라우트 보호 우회 | Medium | Low | 서버 측 `require_role("admin")` + 프론트 `AdminRoute` 이중 보호 |

---

## 10. Next Steps

1. [ ] Design 문서 작성 (`admin-ragas-dashboard.design.md`)
2. [ ] 백엔드 구현 (TDD: 테스트 먼저)
3. [ ] 프론트엔드 구현
4. [ ] Gap Analysis

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-05-18 | Initial draft | AI Assistant |
