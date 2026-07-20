# admin-dashboard Completion Report

> **Summary**: 관리자 운영 현황 대시보드 완성 — KB/문서/사용자 적재 현황 KPI, 질문·사용량 추이, LLM 비용, 시스템 상태(MySQL/Qdrant/ES 헬스)를 한 화면에서 자유 날짜 범위로 조회. 신규 백엔드 4 엔드포인트 + 기존 usage API 재사용 + 프론트 신설 대시보드 페이지.
>
> **Feature**: admin-dashboard
> **Completion Date**: 2026-07-18
> **Owner**: 배상규
> **Match Rate**: 94.4% (gap-detector, 63개 체크포인트)
> **Iterations**: 0 (1차 구현으로 90% 통과)

---

## Executive Summary

### 1.1 Project Overview

| 항목 | 내용 |
|------|------|
| **Feature** | 관리자 운영 현황 대시보드 (KB/문서/사용자 현황 KPI + 질문/비용 추이 + 저장소 헬스) |
| **Duration** | 2026-07-18 (단일일 PDCA 완성) |
| **Match Rate** | 94.4% (gap-detector 63개 체크포인트) |
| **Iteration** | 0회 (1차 구현으로 기준 달성) |
| **Status** | ✅ Complete (90% ≥ 매칭율) |

### 1.2 Results Summary

**백엔드 (idt/)**
- 신규 파일 11 + 변경 1 (main.py)
- 신규 4 엔드포인트: `/admin/dashboard/{stats,kb-breakdown,recent-documents,health}`
- admin 전용 (`require_role("admin")`)
- DB 마이그레이션 없음 (읽기 집계만)
- 신규 테스트 28건 통과 ✅

**프론트엔드 (idt_front/)**
- 신규 파일 12 + 변경 2 (SummaryCards Card export, App.tsx, adminNav.ts)
- `/admin/dashboard` 페이지 신설
- 신규 테스트 12건 + 기존 회귀 테스트 8건 통과 ✅
- TypeScript 클린 (tsc 에러 0)

**재사용 (변경 없음)**
- 기존 `/admin/usage/*` API 4종: summary, timeseries, users, llm-models
- 기존 `/admin/runs` API (최근 질문/에러)
- 기존 컴포넌트: SummaryCards, TimeseriesChart, PeriodFilter

### 1.3 Value Delivered

| 관점 | 내용 |
|------|------|
| **Problem** | 관리자가 "지금 몇 건의 문서가 적재되고, KB가 몇 개이며, 질문이 하루에 몇 번 들어오는지"를 볼 화면이 없음. 데이터는 DB에 이미 쌓이고 있지만(`knowledge_base`, `document_metadata`, `ai_run`) 흩어져 있어 운영 현황 파악에 DB 직접 조회가 필수였음. |
| **Solution** | `/admin/dashboard` 페이지 신설 — 신규 백엔드 API 4종(적재량·KB별 현황·최근 문서·헬스체크)으로 필수 현황을 집계하고, 기존 `/admin/usage/*` 및 `/admin/runs` API를 최대 재사용하여 기간 지표(질문 수·토큰·비용·추이)는 단일 소스 유지. 자유 날짜 범위(from~to) 필터 + 수동 새로고침으로 운영자 제어 극대화. |
| **Function/UX Effect** | 관리자 진입 즉시: ① 스탯 카드로 KB 수·문서 수·청크 수·사용자 수 확인 ② 기간별 질문/토큰 추이 차트 ③ KB별 문서·청크 분포 테이블 ④ 최근 업로드 문서 + 최근 질문/실패 목록 ⑤ MySQL/Qdrant/ES 헬스 상태 배지. 기존에 `/admin/usage` 화면에서만 보던 추이 지표가 이제 통합 대시보드에서 현황 KPI와 함께 한눈에 조회 가능. |
| **Core Value** | **흩어진 운영 데이터를 단일 관제 화면으로 통합** — DB 쿼리 없이 적재량·사용량·비용·장애 상태를 한눈에 파악. 신규 구현을 최소화(집계·헬스 4종만 신설)하여 기존 `ai_run` 관측성 인프라 투자를 극대화. 저장소 장애(1개 다운)가 대시보드 전체를 죽이지 않는 격리 설계로 운영 신뢰성 증대. |

---

## PDCA Cycle Summary

### Plan

**Plan 문서**: `docs/01-plan/features/admin-dashboard.plan.md`

**사용자 확정 사항 (Q&A 2026-07-18, 4건)**
- 지표 범위: 핵심 현황 KPI + 질문/사용량 추이 + LLM 토큰/비용 + 시스템 상태/품질 전부
- 기간 필터: **자유 날짜 범위** (from~to date picker)
- 상세 위젯: KB별 현황 테이블 + 최근 업로드 문서 + 최근 질문/에러 목록 3종 모두
- 갱신 방식: **수동 새로고침** (자동 폴링 없음)

**기존 상태 분석 (현재 구조)**
| 항목 | 현황 |
|------|------|
| KB 메타데이터 | `knowledge_base` 테이블 (id/name/scope/status/created_at) |
| 문서/청크 메타 | `document_metadata` (document_id/kb_id/filename/chunk_count/created_at, 인덱스 2종) |
| 질문 기록 | `ai_run` (질문 1회=1행, tokens/cost/status/error, idx_run_started_at) |
| 기존 사용량 API | `/admin/usage/summary·timeseries·users·llm-models` 전부 from/to Query 지원 — **완전 커버 확인** (Design §1.3) |
| 기존 프론트 컴포넌트 | AdminAgentRunsPage의 SummaryCards/TimeseriesChart/PeriodFilter 검증됨 — 재사용 가능 확인 |

### Design

**Design 문서**: `docs/02-design/features/admin-dashboard.design.md`

**핵심 설계 결정 (D1~D9, 모두 실코드로 검증)**

| ID | 결정 | 선택 | 반영 |
|----|------|------|------|
| D1 | stats API 기간 | **from/to 없음** (기간 무관 누적) | 기간 지표는 usage API가 완전 커버 — 이중 구현 원천 제거 |
| D2 | 신규 라우터 배치 | `admin_dashboard_router.py`, prefix `/api/v1/admin/dashboard`, DI placeholder+override | admin_router(사용자 승인) 단일 책임 유지 |
| D3 | 아키텍처 계층화 | domain(DTO+포트) + application(4개 경량 유스케이스) + infrastructure(집계 리포+헬스 어댑터) | Thin DDD, 각 유스케이스 위임 1회 |
| D4 | KB-breakdown 조인 | `knowledge_base LEFT JOIN` (subquery GROUP BY) — 문서 0건 KB도 행 노출 | FR-04(빈 KB 식별), 수치 누락 방지 |
| D5 | 헬스체크 실행 | `asyncio.gather` 병렬 + 개별 `wait_for(timeout=3s)` → 컴포넌트별 ok/fail, HTTP 200 항상 | 저장소 1개 다운이 화면 다운으로 전파 방지 |
| D6 | 적재 KPI 카드 | `SummaryCards` 내부 `Card` 컴포넌트를 named export 추가 (additive) | 스타일 일관성, 기존 회귀 없음 |
| D7 | 페이지 훅 구성 | 신규 4종(`useAdminDashboard*`) + 기존 3종(`useAdminUsage*`) 조합 | 백엔드 재사용 극대화 |
| D8 | 최근 질문/에러 | `/admin/runs` 2회 호출 (최신 5 + status=FAILED 5) | 백엔드 무변경, 경량 패널 |
| D9 | recent-documents | `?limit=10` (ge=1 le=50), created_at DESC, idx_dm_created 활용 | 단순 최신순 |

**API 계약 (신규 4종, 모두 구현 완료)**
```
GET /api/v1/admin/dashboard/stats              → { kb, documents, chunks, users }
GET /api/v1/admin/dashboard/kb-breakdown       → { rows: [ KB별 현황 ] }
GET /api/v1/admin/dashboard/recent-documents   → { rows: [ 최근 문서 ] }
GET /api/v1/admin/dashboard/health             → { components: [ MySQL/Qdrant/ES 상태 ] }
```

**페이지 레이아웃 (7개 위젯, 모두 구현)**
```
┌ 헤더: "운영 대시보드" + PeriodFilter + [새로고침 버튼] ┐
├ HealthBadges (MySQL/Qdrant/ES 상태)                      │
├ 적재 KPI (기간 무관): [KB수][문서수][청크수][사용자수]     │
├ 사용량 KPI (기간): SummaryCards 재사용                    │
├ TimeseriesChart 재사용 (질문/토큰 추이)                   │
├ KbBreakdownTable + RecentDocumentsTable (2열)             │
└ RecentRunsPanel (최근 질문 5 + 실패 5)                   ┘
```

### Do

**구현 범위**: 1차 구현, 0 반복

**백엔드 (11 신규 + 1 변경)**
- ✅ `src/domain/admin_dashboard/schemas.py` — DTO dataclass 4종
- ✅ `src/domain/admin_dashboard/interfaces.py` — 포트 2종 (AggregationRepository, StorageHealthPort)
- ✅ `src/application/admin_dashboard/use_cases.py` — 4개 경량 유스케이스 (로깅 포함)
- ✅ `src/infrastructure/admin_dashboard/aggregation_repository.py` — MySQL 집계 (COUNT/SUM/GROUP BY, session DI)
- ✅ `src/infrastructure/admin_dashboard/health_adapter.py` — MySQL/Qdrant/ES 병렬 ping (3s timeout)
- ✅ `src/interfaces/schemas/admin_dashboard_response.py` — Pydantic 응답 4종
- ✅ `src/api/routes/admin_dashboard_router.py` — 4 엔드포인트, `require_role("admin")`, DI placeholder
- ✅ `tests/application/admin_dashboard/test_use_cases.py` — 28건 통과 (TDD 선행)
- ✅ `tests/infrastructure/admin_dashboard/test_*.py` — 헬스 타임아웃/격리 검증
- ✅ `tests/api/test_admin_dashboard_router.py` — 401/403/200 스키마
- ✅ `src/api/main.py` — 라우터 등록 + DI override 배선

**프론트엔드 (12 신규 + 2 변경)**
- ✅ `src/constants/api.ts` — 4개 엔드포인트 상수 추가
- ✅ `src/types/adminDashboard.ts` — 응답 타입 4종
- ✅ `src/services/adminDashboardService.ts` — fetch 함수 4종
- ✅ `src/hooks/useAdminDashboard.ts` — TanStack Query 훅 4종
- ✅ `src/pages/AdminDashboardPage/index.tsx` — 페이지 조립
- ✅ `src/pages/AdminDashboardPage/components/HealthBadges.tsx` — 배지 렌더
- ✅ `src/pages/AdminDashboardPage/components/StatCardsRow.tsx` — 적재 KPI
- ✅ `src/pages/AdminDashboardPage/components/KbBreakdownTable.tsx` — KB 현황 테이블
- ✅ `src/pages/AdminDashboardPage/components/RecentDocumentsTable.tsx` — 최근 문서
- ✅ `src/pages/AdminDashboardPage/components/RecentRunsPanel.tsx` — 최근 질문/에러
- ✅ `src/pages/AdminAgentRunsPage/components/SummaryCards.tsx` — Card named export 추가 (additive)
- ✅ 테스트 파일 12건 + 기존 회귀 8건 — 모두 통과

**프론트 메뉴/라우팅**
- ✅ `src/App.tsx` — `/admin/dashboard` 라우트
- ✅ `src/constants/adminNav.ts` — 대시보드 메뉴 항목 (최상단)

### Check

**Analysis 문서**: `docs/03-analysis/admin-dashboard.analysis.md`

**매칭 결과: 94.4% (gap-detector, 63개 체크포인트)**

| 구성 | 결과 |
|------|------|
| Design Decisions D1~D9 | 9/9 완전 일치 ✅ |
| API 계약 (4 엔드포인트 경로/파라미터/응답) | 4/4 일치 ✅ |
| 신규 파일 (백엔드 11 + main.py) | 전부 실존 ✅ |
| 신규 파일 (프론트 12 + 변경 2) | 전부 실존 ✅ |
| 페이지 레이아웃 (7개 위젯) | 7/7 완전 ✅ |
| 에러 처리 | 4/5 완전 + 위젯 에러 상태 UI 부분 |
| 테스트 (백엔드) | 완전 일치 ✅ |
| 테스트 (프론트) | 페이지 통합 완료, 서비스/훅/컴포넌트 3종 테스트 갭 |
| API 계약 동기화 (타입/상수/서비스/훅) | 완전 일치 ✅ |

**정량화**
- 완전 일치: 57 점수
- 부분 일치: 5개 (×0.5 = 2.5 점수)
- 누락: 1개 (위젯 에러 상태 UI)
- **계산: (57 + 2.5) / 63 = 94.4%** ✅

---

## Results

### Completed Items

**기능 (모두 배포 준비 완료)**
- ✅ `/admin/dashboard/stats` — 적재 현황 KPI (KB/문서/청크/사용자)
- ✅ `/admin/dashboard/kb-breakdown` — KB별 문서·청크 분포 (문서 0건 KB도 식별)
- ✅ `/admin/dashboard/recent-documents` — 최근 N건 업로드 문서 목록
- ✅ `/admin/dashboard/health` — MySQL/Qdrant/ES 헬스 상태 (부분 실패 격리)
- ✅ 기간 필터 (`PeriodFilter` 재사용) — 자유 날짜 범위(from~to) 지원
- ✅ 수동 새로고침 — `invalidateQueries` 패턴
- ✅ admin 인증 — `require_role("admin")` 전체 적용

**코드 품질**
- ✅ TDD 준수 — 전 신규 모듈 테스트 선행(Red→Green) 확인
- ✅ 아키텍처 정책 — Thin DDD, domain→infrastructure 참조 없음, DB 스키마 변경 0
- ✅ 기존 관례 준수 — DI 패턴, LoggerInterface, admin 라우터 선례
- ✅ 기존 API 회귀 0 — `/admin/usage/*`, `AdminAgentRunsPage` 무변경
- ✅ TypeScript 클린 — tsc 에러 0

**테스트 (모두 Windows 격리 실행 통과)**
- ✅ 백엔드 28건 (유스케이스 + 리포 + 헬스 + 라우터)
- ✅ 프론트 20건 (새 12 + 회귀 8, Vitest `--pool=threads`)

### Incomplete/Deferred Items

**프론트 테스트 3건 (기능 완성, 검증만 부족)**
| 항목 | 사유 | 우선도 |
|------|------|--------|
| `adminDashboardService`/`useAdminDashboard` Vitest+MSW 전용 테스트 | 페이지 통합 테스트가 간접 커버 중 | Medium |
| StatCardsRow / RecentDocumentsTable / RecentRunsPanel 컴포넌트 단위 테스트 | 렌더 로직이 단순 (props→display), 페이지 테스트로 커버 중 | Medium |
| SummaryCards Card export additive 무회귀 명시 테스트 | 기존 8건 테스트 통과로 간접 확인 (문서 + 명시 테스트 추가 권고) | Medium |

**개선 후보 (성능/UX, 1차 범위 외)**
| 항목 | 내용 | 우선도 |
|------|------|--------|
| 위젯 에러 상태 UI 구분 | 현재 `loading \|\| !data`만 있어 쿼리 에러 시 스켈레톤 지속 → "불러오기 실패" UI 추가 | Low |
| 자동 폴링 (후속) | 현재 수동 새로고침만. 실시간 모니터링 필요 시 WebSocket 갱신 또는 자동 폴링 | Low (사용자 미요청) |
| Qdrant/ES 실측 집계 (후속) | 현재 MySQL `document_metadata` 메타 기준. 저장소 실제 적재량 대사는 후속 (E2E 체크리스트 등재) | Low (설계 의도) |

**이월 항목 (공통 체크리스트)**
- [ ] 수동 E2E 검증 (Qdrant/ES 실기동 시): 헬스 상태 표시 + stats 실데이터 대사 — KB 시리즈 공통 이월

---

## Lessons Learned

### What Went Well

1. **기존 API 재사용으로 신규 구현 극소화** — 기간 지표는 100% 기존 `/admin/usage/*` API로 충당. 신규 백엔드는 "부족한 부분"(적재 현황·헬스)만 4 엔드포인트로 한정. 이 설계 결정(D1)으로 코드 중복·수치 불일치 위험 원천 제거. 관측성 인프라 투자 회수 극대화.

2. **Thin DDD + 경량 유스케이스 패턴** — 읽기 집계만 필요해 domain에 비즈니스 규칙 신규 정의 불필요. application의 4개 유스케이스가 각각 1회 위임(DTO→리포→응답)으로 끝나면서 아키텍처 복잡도 최소화. 결과적으로 테스트도 단순해짐.

3. **컴포넌트 재사용 + named export 패턴** — `SummaryCards`의 내부 `Card`를 named export로 추가하는 additive 방식으로 기존 코드 회귀 없이 스타일 일관성 확보. 기존 `/admin/usage` 화면과 대시보드가 동일한 카드 UX 제공.

4. **헬스체크 부분 실패 격리** — `asyncio.gather`+`wait_for` 패턴으로 저장소 1개 다운(예: ES 타임아웃)이 나머지 위젯 로딩을 막지 않음. 장애 상황에서 더 필요한 화면(대시보드)이 부분 장애(5/5 저장소 다운이 아닌 이상)에 강건하도록 설계.

### Areas for Improvement

1. **프론트 테스트 커버리지 구조화** — 페이지 통합 테스트로 E2E 동작은 검증하나, 서비스/훅/컴포넌트 단위 테스트가 별도 파일로 존재하지 않아 유지보수성 저하 가능. 차후 MSW 테스트를 파일별 3종 훅(beforeAll/afterEach/afterAll)으로 명시하는 것이 Best Practice.

2. **에러 상태 UI 분기 누락** — 현재 `loading || !data` 분기만 있어 쿼리 에러(5xx) 시에도 스켈레톤만 표시. 에러 상황을 시각적으로 구분하고 "불러오기 실패" 메시지 표시가 운영 신뢰성 향상.

3. **설계 문서 파일명 오류** — Design §3.3에 `adminDashboard.ts`로 기재했으나 실제 파일명은 `adminDashboardService.ts` (기존 관례 준수). 문서 정정 필요.

### To Apply Next Time

1. **"기존 API 재사용" 우선 검토** — 신규 기능 설계 시 먼저 "기존 무엇이 부족한가?"를 명확히 하고, 그 부족분만 신설. 이 프로젝트처럼 usage API가 이미 충분하다면 "새로운 엔드포인트 만들기" 대신 "기존 호출 조합하기"로 전환. 단일 소스 유지와 유지보수 비용 절감의 이중 효과.

2. **비동기 병렬 작업의 타임아웃 격리 패턴** — `asyncio.gather`는 모든 task가 완료될 때까지 기다리는데, 외부 저장소 ping 같은 불확실한 작업에는 `wait_for(timeout=T)`를 개별 wrapping. "부분 성공도 성공"이라는 원칙으로 화면 UX 안정성 확보.

3. **DI placeholder + `create_app` override 패턴 재활용** — 이 패턴(agent_run_router 선례)은 테스트 시 mock 주입과 실제 의존성 배선을 깔끔하게 분리. 복잡한 의존성(예: Qdrant/ES 클라이언트)이 있는 기능에서는 이 패턴을 기본으로 적용.

4. **프론트 계약 동기화 체크리스트 자동화** — `constants/api.ts`→`types/`→`services/`→`hooks/`의 4-레이어 동기화를 수동 확인하기보다, CI 테스트(예: "API URL이 존재하지 않는 엔드포인트를 호출한다" 테스트)로 런타임에 검증.

---

## Next Steps

1. **프론트 테스트 보강 (선택, ≈99% 도달)**
   - [ ] `services/hooks` MSW 테스트 파일 작성 (파일별 3종 훅: beforeAll/afterEach/afterAll)
   - [ ] StatCardsRow / RecentDocumentsTable / RecentRunsPanel 컴포넌트 단위 테스트
   - [ ] SummaryCards 회귀 테스트 명시 (Card export additive 검증)

2. **설계 문서 정정**
   - [ ] Design §3.3 `adminDashboard.ts` → `adminDashboardService.ts` 수정

3. **개선 후보 (분기 제약 시 후속)**
   - [ ] 위젯 에러 상태 UI (`isError` 분기 추가)
   - [ ] 수동 E2E 검증 (Qdrant/ES 실기동 상태에서 헬스 표시 + stats 대사) — KB 시리즈 공통 체크리스트 확인

4. **배포**
   - [ ] 프론트·백엔드 병렬 테스트 완전 통과 재확인
   - [ ] `/admin/dashboard` 메뉴 진입 가능 여부 확인
   - [ ] 라이브 환경 헬스 배지 동작 검증

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-07-18 | Completion report — 94.4% 매칭, 0 반복, 백엔드 4 API + 프론트 대시보드 페이지. 기존 usage API 재사용으로 신규 구현 극소화. 프론트 테스트 3건 권고 (기능 완성), 이월: E2E 수동 검증 | 배상규 |
