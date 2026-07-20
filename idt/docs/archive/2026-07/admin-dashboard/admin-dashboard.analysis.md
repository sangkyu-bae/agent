# admin-dashboard Gap Analysis Report

> **Feature**: admin-dashboard (관리자 운영 현황 대시보드)
> **Analysis Date**: 2026-07-18
> **Design Reference**: `docs/02-design/features/admin-dashboard.design.md`
> **Match Rate**: **94.4%** (63개 체크포인트, 부분=0.5 가중)
> **Analyzer**: gap-detector agent

---

## 1. 결론 요약

백엔드는 설계 대비 **완전 구현·테스트 완료**(D1~D9 9/9, API 계약 4/4, 에러 처리, 테스트 §5.1~5.2 전체).
프론트 구현체도 레이아웃 7/7·계약 동기화·에러 격리까지 설계에 충실.
**유일한 실질 갭은 프론트 테스트 커버리지 3건** — 기능 결함이 아닌 검증 자산 부족.

## 2. 항목별 매칭 결과

| 영역 | 결과 |
|------|------|
| Design Decisions D1~D9 | 9/9 완전 일치 |
| API 계약 §3.2 (4 엔드포인트 경로/파라미터/응답 필드) | 4/4 일치, `require_role("admin")` 전체 적용 |
| §3.3 신규/변경 파일 (백엔드 11 + main.py 배선) | 전부 실존 |
| §3.3 신규/변경 파일 (프론트) | 전부 실존 — 파일명 편차 1건(아래 Gap-4) |
| §3.4 페이지 레이아웃 | 7/7 존재, "저장소 실측 아님" 툴팁 포함(Plan 리스크 대응) |
| §4 에러 처리 | 4/5 완전 + 위젯 에러 UI 부분(아래 Gap-5) |
| §5 테스트 | 백엔드 완전, 프론트 페이지 테스트 존재 — services/hooks·컴포넌트 3종·회귀 명시 테스트 갭 |
| 계약 동기화 (루트 CLAUDE.md §4-1) | 완전 일치 (상수/타입/서비스/훅) |

## 3. Gap 목록

| # | 심각도 | Gap | 근거 |
|---|--------|-----|------|
| 1 | 🟡 Medium | `adminDashboardService`/`useAdminDashboard` 전용 Vitest+MSW 테스트 부재 (§5.3-1) — 페이지 통합 테스트가 간접 커버 중 | `*adminDashboard*.test.*` 0건 |
| 2 | 🟡 Medium | StatCardsRow / RecentDocumentsTable / RecentRunsPanel 컴포넌트 테스트 부재 (§5.3-2, 5개 중 2개만 존재) | `AdminDashboardPage/components/` |
| 3 | 🟡 Medium | SummaryCards Card export additive 무회귀 **명시** 테스트 부재 (§5.3-4) — 기존 테스트 8건 통과로 간접 확인됨 | `SummaryCards.test.tsx` |
| 4 | 🔵 Low | Design §3.3 파일명 `adminDashboard.ts` vs 실제 `adminDashboardService.ts` — 실제 명명이 기존 관례(`agentRunAdminService`)와 일관, 문서 수정 권장 | Design line 157 |
| 5 | 🔵 Low | 위젯이 `loading \|\| !data` 분기만 있어 쿼리 에러 시 스켈레톤 지속 — 에러 상태 UI 미구분 (§4 취지 부분 충족) | `HealthBadges.tsx:16` 외 |

> §5.4 수동 E2E(Qdrant/ES 실기동 검증)는 기존 KB 시리즈 공통 이월 체크리스트 항목으로 계산에서 제외.

## 4. Match Rate 계산 근거

- 완전 일치 57 + 부분 5(×0.5 = 2.5) + 누락 1 → (57 + 2.5) / 63 = **94.4%**

## 5. 권고사항

1. **(선택, ≈99% 도달)** 프론트 테스트 3종 보강 — services/hooks MSW 테스트 + 컴포넌트 렌더 테스트 3개
2. **(문서)** Design §3.3 service 파일명 정정
3. **(개선 후보)** 위젯 `isError` 분기 추가 — "불러오기 실패" UI
4. 90% 기준 통과 — `/pdca report admin-dashboard` 진행 가능

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-07-18 | gap-detector 분석 — 94.4%, 갭 5건(Medium 3 프론트 테스트, Low 2) | gap-detector |
