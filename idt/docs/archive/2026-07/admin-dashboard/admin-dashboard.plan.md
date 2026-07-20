# admin-dashboard Planning Document

> **Summary**: 관리자 페이지에 **운영 현황 대시보드** 신설 — KB/문서/청크/사용자 적재 현황 KPI, 질문·사용량 추이, LLM 토큰/비용, 시스템 상태(Qdrant/ES/MySQL 헬스·에러율)를 한 화면에서 자유 날짜 범위로 조회. 기존 `/admin/usage/*` 관측성 API를 최대 재사용하고, KB/문서 현황·헬스체크 API만 신설
>
> **Project**: sangplusbot (idt 백엔드 + idt_front 풀스택)
> **Author**: 배상규
> **Date**: 2026-07-18
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 관리자가 "지금 문서가 몇 건 적재됐고, KB가 몇 개고, 질문이 하루에 몇 번 들어오는지"를 볼 화면이 없다. 데이터는 이미 DB에 쌓이고 있지만(`knowledge_base`, `document_metadata`, `ai_run`, `ai_llm_call`) 흩어져 있어 운영 현황 파악에 매번 DB 직접 조회가 필요하고, Qdrant/ES 장애나 질문 실패율 급증 같은 이상 징후를 조기에 인지할 방법이 없다. |
| **Solution** | `/admin/dashboard` 페이지 신설. ① 백엔드에 KB/문서/청크/사용자 현황 집계 API(`GET /admin/dashboard/stats`), KB별 현황(`kb-breakdown`), 최근 업로드 문서, 저장소 헬스체크 API를 신설하고 ② 질문 추이·토큰/비용·에러율·최근 질문 목록은 **기존 agent-run 관측성 API**(`/admin/usage/summary·timeseries·users·llm-models`, `/admin/runs`)를 그대로 호출한다. 프론트는 `AdminAgentRunsPage`의 검증된 컴포넌트(SummaryCards, TimeseriesChart)를 재사용해 조립하고, 자유 날짜 범위(from~to) 필터 + 수동 새로고침으로 동작한다. |
| **Function/UX Effect** | 관리자 진입 즉시 ① 스탯 카드로 KB 수·문서 수·청크 수·사용자 수·기간 내 질문 수·총 비용 확인, ② 일별 질문/토큰 추이 차트, ③ KB별 문서·청크 분포 테이블로 빈 KB 식별, ④ 최근 업로드 문서·최근 질문/실패 목록으로 운영 이벤트 추적, ⑤ Qdrant/ES/MySQL 상태 배지로 장애 즉시 인지. |
| **Core Value** | 흩어진 운영 데이터를 **단일 관제 화면**으로 통합 — DB 쿼리 없이 적재량·사용량·비용·장애를 한눈에 파악하고, 신규 API를 최소화(집계·헬스 4종만 신설)하여 기존 관측성 인프라 투자 회수를 극대화한다. |

---

## 1. Overview

### 1.1 Purpose

관리자용 운영 현황 대시보드를 신설한다: 문서 적재량·KB 현황·질문 횟수·LLM 비용·시스템 상태를
자유 날짜 범위로 조회하는 단일 화면. 신규 백엔드는 "현황 집계 + 헬스체크"에 한정하고,
사용량/비용/추이는 기존 관측성 API를 재사용한다.

### 1.2 Background (현재 구조 분석 — 2026-07-18 확인)

| 항목 | 현재 상태 | 근거 코드 |
|------|-----------|----------|
| KB 데이터 | `knowledge_base` 테이블: id/name/scope(PERSONAL·DEPARTMENT·PUBLIC)/status/created_at | `src/infrastructure/persistence/models/knowledge_base.py` |
| 문서/청크 데이터 | `document_metadata`: document_id/collection_name/filename/chunk_count/kb_id(NULL=일반 업로드)/created_at, `idx_dm_created`·`idx_dm_kb` 인덱스 보유 | `src/infrastructure/doc_browse/models.py` |
| 질문 기록 | `ai_run`: 사용자 질문 1회=1행. status/tokens/total_cost_usd/latency_ms/error_message, `idx_run_started_at` 인덱스 | `src/infrastructure/persistence/models/agent_run.py` |
| LLM 호출 집계 | `ai_llm_call`: user_id/agent_id/provider/model 비정규화 — 집계 성능 확보 목적 명시 | 동일 파일 |
| **기존 사용량 API (재사용 대상)** | `GET /admin/usage/summary`, `/admin/usage/timeseries`, `/admin/usage/users`, `/admin/usage/llm-models`, `/admin/usage/by-node`, `/admin/runs` — 모두 `from`/`to` datetime Query 지원 | `src/api/routes/agent_run_router.py:209-332` |
| **기존 프론트 컴포넌트 (재사용 대상)** | `AdminAgentRunsPage`: SummaryCards, TimeseriesChart, UsageTabs, RunListTable — 사용량 화면으로 이미 검증됨 | `idt_front/src/pages/AdminAgentRunsPage/` |
| admin 인증 패턴 | `Depends(require_role("admin"))` — admin_router/agent_run_router 공통 선례 | `src/api/routes/admin_router.py:30` |
| KB/문서 현황 집계 API | **없음** — KB 목록·문서 목록 API는 있으나 전체/KB별 카운트 집계 엔드포인트 부재 | `knowledge_base_router.py` |
| 저장소 헬스체크 API | **없음** — Qdrant/ES/MySQL 연결 상태를 노출하는 admin 엔드포인트 부재 | `src/api/routes/` 전수 확인 |
| 검색 이력 | `search_history` (retrieval 테스트 기록) — 대시보드 1차 범위에서는 미사용 후보 | `src/infrastructure/collection_search/models.py` |

### 1.3 Related Documents

- 관측성 선행 기능: agent-run observability(V021·V022, `ai_run` 시리즈), retrieval-observability — `docs/archive/`
- KB 시리즈 선행: `kb-management-ui`(document_metadata.kb_id), `kb-content-browser`, `kb-excel-upload` — `docs/archive/2026-07/`
- 규칙: `idt/CLAUDE.md`, `docs/rules/db-session.md`, `docs/rules/testing.md`, 루트 `CLAUDE.md` §4-1(API 계약 동기화)

### 1.4 사용자 확정 사항 (Q&A 2026-07-18)

| 질문 | 결정 |
|------|------|
| 지표 범위 | 4개 그룹 전부: 핵심 현황 KPI + 질문/사용량 추이 + LLM 토큰/비용 + 시스템 상태/품질 |
| 기간 필터 | **자유 날짜 범위 선택** (from~to date picker) |
| 상세 위젯 | KB별 현황 테이블 + 최근 업로드 문서 + 최근 질문/에러 목록 (3종 모두) |
| 갱신 방식 | **수동 새로고침** (자동 폴링 없음) |

---

## 2. Scope

### 2.1 In Scope

**백엔드 (idt/) — 신설 (admin 전용, `require_role("admin")`)**
- [ ] `GET /api/v1/admin/dashboard/stats` — 스탯 카드용 단일 응답: KB 수(전체/scope별), 적재 문서 수, 총 청크 수(SUM chunk_count), 사용자 수(전체/승인 상태별), 기간 내 질문 수·실패 수·총 토큰·총 비용(기존 usage summary와 중복되면 Design에서 제외 확정). `from`/`to` 옵션 Query — 기간 무관 항목(KB/문서/사용자 누적)과 기간 항목(질문/비용) 구분은 Design에서 확정
- [ ] `GET /api/v1/admin/dashboard/kb-breakdown` — KB별 행: KB명/scope/status/문서 수/청크 수/최근 업로드 시각 (`document_metadata`를 kb_id로 GROUP BY 후 KB 목록과 조인)
- [ ] `GET /api/v1/admin/dashboard/recent-documents?limit=N` — 최근 적재 문서 N건 (filename/kb/collection/chunk_count/chunk_strategy/created_at)
- [ ] `GET /api/v1/admin/dashboard/health` — MySQL/Qdrant/Elasticsearch 연결 상태(ok/fail + 응답시간 ms). 저장소 미기동 시에도 전체 응답은 200으로 개별 컴포넌트만 fail 표기 (대시보드가 죽으면 안 됨)
- [ ] 대시보드 유스케이스(`application/admin_dashboard/` 신설)와 집계 리포지토리 — 읽기 전용 집계 쿼리, 단일 세션 규칙 준수
- [ ] pytest 선행 작성 (TDD: 집계 유스케이스 단위, 라우터 401/403, 헬스 부분 실패 시 부분 성공 응답)

**백엔드 — 재사용 (무변경)**
- 질문 추이/토큰/비용/모델별·사용자별 분포: `GET /admin/usage/summary`, `/admin/usage/timeseries`, `/admin/usage/users`, `/admin/usage/llm-models`
- 최근 질문/에러 목록: `GET /admin/runs` (status 필터·기간 필터 기존 지원 범위 확인은 Design에서)

**프론트엔드 (idt_front/)**
- [ ] `/admin/dashboard` 라우트 + `AdminDashboardPage` 신설 (admin 가드 — 기존 admin 페이지 라우팅 패턴 준수)
- [ ] 자유 날짜 범위 필터(from~to) — 페이지 전역 상태로 모든 기간 의존 위젯에 전파, 기본값(예: 최근 30일)은 Design에서 확정
- [ ] 상단 KPI 스탯 카드: KB 수/문서 수/청크 수/사용자 수/기간 내 질문 수/기간 내 비용(USD) — `SummaryCards` 패턴 재사용
- [ ] 질문·토큰 추이 차트 — 기존 `TimeseriesChart` 재사용(기존 usage timeseries API 연동)
- [ ] 시스템 상태 배지 영역 — health API 연동 (ok/fail/응답시간)
- [ ] KB별 현황 테이블 / 최근 업로드 문서 / 최근 질문·에러 목록 위젯 3종
- [ ] 수동 새로고침 버튼 (전체 쿼리 invalidate) — 자동 폴링 없음
- [ ] API 계약 동기화: `constants/api.ts` 상수, `types/` 타입, `services/` + 훅 — Vitest+MSW 테스트 선행 (`--pool=threads`)
- [ ] 관리자 메뉴/네비게이션에 대시보드 진입점 추가

### 2.2 Out of Scope

- 자동 폴링/실시간 WebSocket 갱신 (수동 새로고침 확정 — 후속 후보)
- Qdrant/ES의 **벡터 수·인덱스 문서 수 실측 집계** (1차는 MySQL `document_metadata` 기준 + 헬스 ping만. 실측 대사는 후속)
- 기존 `/admin/usage/*` API·`AdminAgentRunsPage` 화면의 변경 (무변경 기준선 — 대시보드는 추가 화면)
- 검색(retrieval) 품질 지표·search_history 통계 (후속 후보)
- 알림/임계치 경보 (에러율 N% 초과 시 통지 등)
- CSV/엑셀 내보내기
- 부서별/사용자별 드릴다운 상세 화면 (기존 AdminAgentRunsPage가 이미 담당)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | admin 권한 사용자만 대시보드 API·화면에 접근 가능하다 (`require_role("admin")`, 비admin 403) | High | Pending |
| FR-02 | 스탯 API가 KB 수, 적재 문서 수, 총 청크 수, 사용자 수를 정확히 반환한다 (DB 실데이터와 일치) | High | Pending |
| FR-03 | 기간 의존 지표(질문 수·실패 수·비용)는 from~to 범위로 필터되며, 프론트 날짜 범위 변경 시 반영된다 | High | Pending |
| FR-04 | KB별 현황 테이블이 KB별 문서 수·청크 수·최근 업로드 시각을 표시한다 — 문서 0건 KB도 행으로 노출(빈 KB 식별) | High | Pending |
| FR-05 | 최근 업로드 문서 위젯이 최신순 N건(파일명/KB/청킹 전략/시각)을 표시한다 | Medium | Pending |
| FR-06 | 최근 질문/에러 목록이 기존 `/admin/runs`를 재사용해 최신 질문과 실패 건(에러 메시지 요약)을 표시한다 | Medium | Pending |
| FR-07 | 헬스 API가 MySQL/Qdrant/ES 각각의 ok/fail·응답시간을 반환하고, 일부 저장소 다운 시에도 HTTP 200으로 나머지 결과를 반환한다 | High | Pending |
| FR-08 | 질문/토큰 추이 차트가 기존 `/admin/usage/timeseries`로 렌더링된다 (백엔드 무변경) | High | Pending |
| FR-09 | 새로고침 버튼 클릭 시 모든 위젯 데이터가 재조회된다. 자동 폴링은 없다 | Medium | Pending |
| FR-10 | 프론트 타입/서비스/훅/엔드포인트 상수가 백엔드 계약과 동기화된다 (루트 CLAUDE.md §4-1) | High | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 아키텍처 | 집계 유스케이스는 application 레이어, 라우터는 위임만. domain→infrastructure 참조 금지, Repository 내 commit 금지, 한 유스케이스 단일 세션 | `/verify-architecture` |
| 성능 | 집계는 COUNT/SUM/GROUP BY 쿼리로 수행(전체 행 로딩 금지). 기존 인덱스(`idx_dm_kb`, `idx_dm_created`, `idx_run_started_at`) 활용 | 쿼리 리뷰 |
| 호환성 | 기존 admin/usage API·화면 회귀 0, DB 스키마 변경 없음(신규 마이그레이션 없음) | pytest (Windows 격리 실행 기준) |
| 가용성 | 헬스체크는 짧은 타임아웃(수 초 내)으로 개별 실패를 격리 — 저장소 1개 다운이 대시보드 전체 로딩을 막지 않음 | 헬스 부분 실패 테스트 |
| TDD | 신규 모듈 테스트 선행 작성 (Red→Green) | `/verify-tdd` |
| 로깅 | 집계/헬스 실패를 request_id 포함 구조화 로그로 기록 (print 금지) | `/verify-logging` |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] FR 전체 구현: 관리자 로그인 → 대시보드 진입 → KPI/차트/테이블/헬스 표시 → 날짜 범위 변경 반영 → 새로고침 동작
- [ ] 스탯 수치가 DB 직접 쿼리 결과와 일치 (교차 검증 테스트)
- [ ] pytest 선행 작성(Red→Green) + 기존 admin API 회귀 0
- [ ] Vitest(MSW 파일별 3종 훅, `--pool=threads`) 통과
- [ ] Gap 분석(Check) ≥ 90%

### 4.2 Quality Criteria

- [ ] 레이어 의존성 규칙 위반 0 (`/verify-architecture`)
- [ ] 신규 함수 40줄 이하, if 중첩 2단계 이하
- [ ] 사전 실패 테스트(백엔드 api 28건·infra 30건, 프론트 8건)는 기존 이슈 — 신규 회귀로 오인 금지
- [ ] E2E(Qdrant/ES 실기동 상태의 헬스 표시·실데이터 집계) 수동 검증 — KB 시리즈 공통 이월 체크리스트에 등재

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| `document_metadata`와 실제 Qdrant/ES 적재량 불일치(삭제 미반영·V047 이전 kb_id NULL) → 수치 신뢰 저하 | Medium | Medium | 1차는 "MySQL 메타 기준" 수치임을 화면에 명시(툴팁). kb_id NULL 문서는 "일반 업로드"로 별도 집계 행 처리. 실측 대사는 후속 |
| 헬스체크가 저장소 타임아웃을 그대로 기다려 대시보드 로딩 블로킹 | High | Medium | 컴포넌트별 짧은 타임아웃 + 병렬 실행 + 부분 실패 격리(FR-07). 헬스는 별도 엔드포인트로 분리해 stats 로딩과 독립 |
| stats와 기존 `/admin/usage/summary`의 질문/비용 수치 이중 구현 → 두 화면 수치 불일치 | Medium | Medium | Design에서 확정: 기간 지표는 기존 usage API를 단일 소스로 재사용하고 stats는 적재/사용자 현황만 담당하는 방향 우선 검토 |
| `ai_run` 데이터가 로컬/신규 환경에서 비어 있어 차트가 빈 화면 | Low | High | 빈 상태 UI(데이터 없음 안내) 명시적 처리 — 컴포넌트 테스트 포함 |
| 집계 쿼리가 데이터 증가 시 느려짐 | Low | Low | COUNT/SUM + 기존 인덱스 활용, 필요 시 후속에서 캐싱(수동 새로고침이라 부담 낮음) |
| 기존 TimeseriesChart/SummaryCards가 AdminAgentRunsPage에 결합돼 재사용 불가 | Low | Medium | Design에서 props 의존 확인 — 결합 시 presentational 분리 또는 경량 신규 컴포넌트 |

---

## 6. Architecture Considerations

### 6.1 Project Level Selection

기존 프로젝트 편입 — Thin DDD(Domain→Application→Infrastructure) 현행 유지.

### 6.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 사용량/비용 지표 소스 | ① 대시보드용 신규 집계 구현 ② 기존 `/admin/usage/*` API 재사용 | ② 재사용 | 수치 단일 소스 유지·구현량 최소화. AdminAgentRunsPage와 수치 일치 보장 |
| 신규 API 위치 | ① admin_router 확장 ② `admin_dashboard_router` 신설 | ② 신설 (prefix `/api/v1/admin/dashboard`) | admin_router는 사용자 승인 전용 — 단일 책임. 라우터 등록 패턴 동일 |
| 적재량 데이터 소스 | ① MySQL `document_metadata` 집계 ② Qdrant/ES 실측 | ① MySQL (1차) | 실측은 저장소 왕복 비용·불일치 처리 복잡 — 헬스 ping만 실측, 카운트는 메타 기준. 후속에서 대사 |
| 헬스 응답 정책 | ① 하나라도 fail 시 5xx ② 200 + 컴포넌트별 상태 | ② 부분 실패 격리 | 대시보드는 장애 상황에서 더 필요한 화면 — 저장소 다운이 화면 다운으로 전파되면 안 됨 |
| 갱신 방식 | ① 자동 폴링 ② 수동 새로고침 | ② 수동 | 사용자 확정. TanStack Query 기본 캐시 + invalidate만 사용 |
| 기간 필터 | ① 고정 프리셋 ② 자유 범위 | ② 자유 범위 (from~to) | 사용자 확정. 기존 usage API가 이미 from/to 지원 — 계약 일치 |

### 6.3 Clean Architecture Approach

domain 무변경(신규 비즈니스 규칙 없음 — 읽기 집계).
`application/admin_dashboard/`에 stats/kb-breakdown/recent-documents/health 유스케이스,
`infrastructure/`에 집계용 읽기 리포지토리(기존 세션 팩토리 DI 패턴)와 저장소 ping 어댑터.
라우터는 `api/routes/admin_dashboard_router.py`에서 위임만. DB 스키마 변경·마이그레이션 없음.

---

## 7. Convention Prerequisites

- [x] `idt/CLAUDE.md` + `docs/rules/testing.md` 준수 (TDD 필수)
- [x] 로깅: LoggerInterface + request_id (print 금지)
- [x] admin 인증: `require_role("admin")` 기존 패턴 재사용
- [x] 프론트: API 상수 `constants/api.ts` 집중, MSW 파일별 3종 훅, Vitest `--pool=threads`
- [x] pytest는 Windows에서 파일 격리 실행 기준으로 판정

신규 환경변수·마이그레이션 없음.

---

## 8. Next Steps

1. [ ] `/pdca design admin-dashboard` — stats 응답 스키마 확정(기간 지표의 usage API 위임 경계), `/admin/runs`의 status 필터 지원 범위 실증, 헬스 ping 어댑터 시그니처, SummaryCards/TimeseriesChart 재사용성 실코드 확인, 페이지 레이아웃 확정
2. [ ] 구현 (TDD: 집계 리포지토리 → 유스케이스 → 라우터 → 프론트 타입/서비스/훅 → 페이지 조립)
3. [ ] `/pdca analyze admin-dashboard`

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-07-18 | Initial draft — 지표 4그룹 전체·자유 날짜 범위·위젯 3종·수동 새로고침 확정 (사용자 Q&A 4건 반영), 기존 usage API 재사용 방향 수립 | 배상규 |
