# market-index-ytd-chart 완료 보고서

> **Summary**: 시장 분석 대시보드에 KOSPI·KOSDAQ 올해 등락률 차트를 추가했다. 지수 확정 일봉은 새 테이블(V102)에 저장하고, 화면을 열 때 비어 있는 날만 KIS에서 채운다.
>
> **Project**: sangplusbot (Agent Builder)
> **Author**: 배상규
> **Date**: 2026-11-27
> **Status**: Completed (미커밋, worktree `../wt/market-index-ytd-chart`)
> **Match Rate**: 95.3% (Check) → 약 97.7% (Act-1 뒤 추정)

---

## Executive Summary

### 1.1 Project Overview

| 항목 | 내용 |
|------|------|
| 기능 | 시장 분석 대시보드 "올해 시장" 카드 (KOSPI·KOSDAQ YTD 등락률) |
| 기간 | 2026-11-27 (Plan → Design → Do module-1~4 → Check → Act-1 → Report) |
| 범위 | 백엔드: V102·domain 규칙·서비스·저장소·`GET /market-analysis/index-chart` / 프론트: 타입·훅·차트·카드 |
| 설계안 | Option C 실용 균형 |

### 1.2 Results Summary

| 항목 | 결과 |
|------|------|
| Success Criteria | 6/6 충족 (실데이터·브라우저 확인) |
| FR | 12/12 충족 (FR-12는 Act-1에서 보완) |
| Match Rate | 95.3% → 약 97.7% |
| 테스트 | 백엔드 신규 36, market_analysis 회귀 395 통과 / 프론트 시장 분석 화면·util·훅 40 통과 |
| 갭 | Critical 0, Important 1(수정), Minor 6(5 처리, 1 이월) |

### 1.3 Value Delivered

| 관점 | 내용 |
|------|------|
| **Problem** | 시장 분석 화면에 올해 지수 흐름이 없었다. 기존 차트는 가상 계좌 첫 회차부터만 있었고, 지수 값도 회차가 돈 날에만 쌓였다. |
| **Solution** | `ma_index_daily`에 확정 일봉을 저장하고, 차트 API가 마지막 저장일 이후 구간만 KIS에서 183일씩 나눠 받는다. 장중 봉은 5분 캐시에만 둔다. |
| **Function/UX Effect** | 대시보드에서 KOSPI +13.66%·KOSDAQ −25.87%(11/27 장중) 같은 올해 흐름과, 시장 체제가 기록된 날(점·툴팁)을 함께 본다. 첫 조회 7.5초(연초 222거래일 적재), 이후 86ms. |
| **Core Value** | 자동 분석 스위치가 꺼져 있어도 올해 시장 흐름이 보이고, "strong_bear로 매수 보류" 같은 에이전트 판단을 사용자가 지수 흐름과 대조해 검증할 수 있다. |

---

## 1.4 Success Criteria Final Status

| SC | 기준 | 결과 | 근거 |
|----|------|:----:|------|
| SC-1 | 빈 테이블 첫 조회로 연초~최근 확정 봉 적재·차트 표시 | ✅ | 실측 KIS 4회(지수당 122+100봉), 지수당 221행 저장, 화면 표시 |
| SC-2 | 캐시 5분 안 재조회 KIS 0회, 마감 뒤 오늘 봉 저장되면 더 부르지 않음 | ✅ | 실측 0회·86ms, 서비스 테스트 2건 |
| SC-3 | 첫 점 0%, 이후 종가 계산값과 일치 | ✅ | 실측 444점 오차 0 |
| SC-4 | 장중 점 미확정 표시·미저장 | ✅ | 테이블 11/26까지, 화면 "(11/27 미확정)"·툴팁 "미확정 (장중)" |
| SC-5 | KIS 장애 시 저장분 + 안내 | ✅ | KIS 실패를 프로세스 안에서 흉내 냄 → `stale`·`SERVER_UNAVAILABLE`, 복구 뒤 하루치 1회 |
| SC-6 | 체제 기록일에 점 | ✅ | 11/26·11/27 점, 툴팁 "시장 체제: 강한 하락" |

**Overall: 6/6 (100%)**

---

## 1.5 Decision Record Summary

| 단계 | 결정 | 따름 | 결과 |
|------|------|:----:|------|
| Plan | 일봉 테이블 적재 (사용자 결정) | ✅ | KIS가 꺼져도 저장분으로 차트가 나온다(SC-5) |
| Plan | 조회 때 꼬리만 적재 (자동 분석 스위치 기본 꺼짐) | ✅ | 스위치와 무관하게 첫 조회에 연초분이 채워졌다 |
| Plan | 장중 봉은 응답에만 | ✅ | 테이블에 미확정 값이 남지 않는다 |
| Plan | % 겹침 / 체제는 있는 날만 점 / YTD | ✅ | 수준이 다른 두 지수를 한 그래프로 비교 |
| Design | Option C, 183일 구간, TTL 300초, 상태 3단계 | ✅ | KIS 200봉 상한 아래로 지수당 2회, 재조회 0회 |
| Design | 별도 엔드포인트 | ✅ | 차트 조회가 실패해도 KPI·누적 수익률은 표시(화면 테스트) |
| Design | 등락률 백엔드 결정론 계산 | ✅ | 444점 오차 0 |

---

## 2. Related Documents

| 단계 | 문서 |
|------|------|
| Plan | `docs/01-plan/features/market-index-ytd-chart.plan.md` (v0.2) |
| Design | `docs/02-design/features/market-index-ytd-chart.design.md` (v0.2) |
| Check | `docs/03-analysis/market-index-ytd-chart.analysis.md` (v0.2, Act-1 포함) |
| Report | 이 문서 |

---

## 3. Completed Items

### 3.1 Functional Requirements

| ID | 내용 | 상태 |
|----|------|:----:|
| FR-01 | `ma_index_daily` (지수+거래일 PK, 덮어쓰기) | ✅ |
| FR-02 | 마지막 저장일 다음 날 ~ 오늘 구간만 KIS 호출 (확정 봉만 저장) | ✅ |
| FR-03 | 한 호출 200봉 이하 (183일 분할) | ✅ |
| FR-04 | 장중 봉 미저장, 응답 마지막 점으로만 | ✅ |
| FR-05 | 거래일·종가·연초 대비 등락률 | ✅ |
| FR-06 | 같은 기간 체제 기록 포함 | ✅ |
| FR-07 | KIS 미설정·실패 시 저장분 + `source_status` | ✅ |
| FR-08 | 오늘 확정 봉까지 저장되면 KIS 미호출 | ✅ |
| FR-09 | 동시 조회 멱등 (Lock + 덮어쓰기) | ✅ |
| FR-10 | % 겹침 차트, 툴팁에 날짜·지수 값·등락률 | ✅ |
| FR-11 | 체제 점·라벨 | ✅ |
| FR-12 | 미확정·빈 상태·안내 문구 (빠진 지수 안내 포함) | ✅ (Act-1) |

### 3.2 Non-Functional Requirements

| 항목 | 기준 | 결과 |
|------|------|:----:|
| 적재 후 조회 | < 300ms | 86ms ✅ |
| 첫 백필 | 지수당 2회 이내 | 2회 ✅ |
| 권한 | VIEW 없으면 403 | ✅ (API 테스트) |
| 모듈 격리 | infra→application import 없음, 플랫폼 FK 없음 | ✅ (격리 계약 테스트) |
| 접근성 | role·aria-label, 미확정·체제 텍스트 병행 | ✅ |
| 화면 폭 | 375·768·1440 넘침 없음 | 375(사이드바 접힘)·768 ✅, 1536 창 ✅ |

### 3.3 Deliverables

| 구분 | 파일 |
|------|------|
| DB | `idt/db/migration/V102__create_ma_index_daily.sql` |
| 백엔드 신규 | `idt/src/domain/market_analysis/index_chart.py`, `idt/src/application/market_analysis/index_chart.py`, `idt/src/infrastructure/market_analysis/index_daily_repository.py` |
| 백엔드 수정 | `ports.py`(IndexDailyStore), `models.py`(MaIndexDailyModel), `market_analysis_di.py`(runtime.index_chart), `market_analysis_router.py`(GET /index-chart) |
| 백엔드 테스트 | `test_index_chart.py`(13), `test_index_chart_service.py`(16), `test_index_daily_repository.py`(6), `test_models_match_migration.py`(V102 포함), `test_market_analysis_api.py`·`test_market_analysis_runtime_wiring.py` 보강 |
| 프론트 신규 | `idt_front/src/utils/marketIndexChart.ts`(+test), `idt_front/src/pages/MarketAnalysisPage/IndexYtdChart.tsx` |
| 프론트 수정 | `types/marketAnalysis.ts`, `constants/api.ts`, `lib/queryKeys.ts`, `services/marketAnalysisService.ts`, `hooks/useMarketAnalysis.ts`(+test), `DashboardTab.tsx`(IndexYtdCard), `parts.tsx`(Card `label`), `__tests__/mocks/marketAnalysisMocks.ts`, `MarketAnalysisPage/index.test.tsx` |
| 문서 | Plan·Design v0.2, 분석, 이 보고서 |

---

## 4. Incomplete Items

### 4.1 Carried Over to Next Cycle

| 항목 | 이유 |
|------|------|
| G-M4 차트 카드 요청 순서 | 카드가 대시보드 조회 성공 뒤 그려져 요청이 늦게 나가고, 대시보드 실패 시 카드도 안 보인다. 이번 수정 범위에서 제외 |
| 범례 순서 화면 확인 | `itemSorter={null}`로 고쳤으나 jsdom이 범례를 그리지 않고, 확인 시점에 8000이 master 서버라 화면 확인 못 함 |
| 1440 정확 폭 확인 | 1536 창에서만 확인 |
| 커버리지 수치 측정 | 측정하지 않음 |
| 운영 배포 | **V100·V101 다음 V102 적용** 필요 (로컬은 적용됨) |

### 4.2 Cancelled/On Hold Items

- 기간 선택(3개월·1년), 지수 값 토글, 회차 ① 경로 적재, 중간 구멍 보수: Plan에서 범위 밖으로 둠.

---

## 5. Quality Metrics

### 5.1 Final Analysis Results

| 항목 | 점수 |
|------|:----:|
| Structural | 100% |
| Functional | 95% |
| API Contract | 100% |
| Behavioral (Act-1 뒤 추정) | 98% |
| UX (Act-1 뒤 추정) | 95% |
| Runtime | 95% |
| **Overall** | **95.3% → 약 97.7%** |

### 5.2 Resolved Issues

| ID | 내용 | 처리 |
|----|------|------|
| G-I1 | 한쪽 지수만 데이터가 있으면 안내 없음 | 빠진 지수 이름을 밝히는 안내 + 화면 테스트 |
| G-M3 | 설정 읽기 실패 시 500 | 저장분 + `STORE_FAILED` + 서비스 테스트 |
| G-M5 | 로딩 테스트 없음 | 화면 테스트 추가 |
| G-M6 | stale 안내 날짜가 미확정 날짜 | 마지막 확정 점 날짜 + util 테스트 |
| 범례 | KOSDAQ 먼저(이름순 기본 정렬) | `itemSorter={null}` |
| G-M1·G-M2 | Plan 문구가 Design과 어긋남 | Plan v0.2 |

---

## 6. Lessons Learned & Retrospective

### 6.1 What Went Well (Keep)

- 구간 계산·등락률을 domain 순수 함수로 두어, 시각을 주입한 서비스 테스트로 SC-1~5를 서버 없이 확인했다.
- 인프로세스 실데이터 실행(TestClient + KIS 호출 계수 래퍼)으로 서버 재기동 없이 SC를 실측했다.
- 실패를 예외 대신 `source_status`로 다뤄 차트 카드가 대시보드 나머지를 막지 않았다.

### 6.2 What Needs Improvement (Problem)

- 서버 실행 안내 명령을 틀리게 줬다(`src.main` → 실제는 `src.api.main`). Windows 경로의 `\.`가 화면 표시에서 사라져 경로도 깨졌다.
- 8000번에 PyCharm(master)과 worktree 서버가 동시에 떠서 요청이 master로 가는 것을 늦게 알아챘다.
- 키 이름을 확인하다가 정규식이 KIS 모의 키 값의 앞부분을 출력했다(값 출력 금지 규칙 위반).
- gap-detector가 본문을 앞 메시지에 두고 마지막에 요약만 보내 재요청이 필요했다.

### 6.3 What to Try Next (Try)

- 사용자에게 줄 명령은 실제 모듈 경로를 확인한 뒤, `/` 경로와 인라인 코드로 준다.
- 화면 확인 전 `netstat`으로 포트 점유 프로세스가 하나인지 먼저 확인한다.
- `.env` 확인은 `grep -c`나 키 이름만 뽑는 패턴(`cut -d= -f1`)으로 한다.

---

## 7. Process Improvement Suggestions

### 7.1 PDCA Process

| 단계 | 제안 |
|------|------|
| Plan | 경계 표현("어제"/"오늘")을 Design에서 바꾸면 같은 턴에 Plan도 고친다 |
| Check | 분석 에이전트에는 "최종 메시지에 본문 전체"를 명시한다 |

### 7.2 Tools/Environment

| 항목 | 제안 |
|------|------|
| worktree 실행 | `uv run`은 worktree에 dev 의존성 없는 `.venv`를 만든다 → 메인 venv python 사용 |
| 화면 확인 | 5175 프록시 런처(`VITE_API_BASE_URL=''` + `/api` 프록시)로 CORS 없이 worktree 프론트 확인 |

---

## 8. Next Steps

### 8.1 Immediate

- [ ] 커밋·PR (worktree `feature/market-index-ytd-chart`)
- [ ] PR 리뷰 때 범례 순서 화면 확인
- [ ] 머지 확인(`gh pr view` MERGED) 후 archive, worktree 정리 (**`idt_front/node_modules` junction 먼저 제거**)

### 8.2 Next PDCA Cycle

| 후보 | 비고 |
|------|------|
| G-M4 카드 요청 순서 | 훅 호출을 대시보드 로딩 분기 밖으로 |
| 체제 띠 표시·기간 선택 | 체제 기록이 쌓인 뒤 |
| KIS 지수 데이터 점검 | 하루 ±12~18% 변동이 KIS 원본에 있음. 데이터 원천(모의/실전) 확인 |

---

## 9. Changelog

### v1.0.0 (2026-11-27)

**Added**
- `ma_index_daily` 테이블(V102), `GET /api/v1/market-analysis/index-chart`
- 대시보드 "올해 시장" 카드: KOSPI·KOSDAQ 연초 대비 % 겹침, 체제 점, 미확정·stale·빠진 지수 안내

**Changed**
- `parts.tsx` `Card`에 선택 prop `label`(영역 이름)

**Fixed**
- (Act-1) 빠진 지수 안내, 설정 읽기 실패 처리, stale 기준일, 범례 순서

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-11-27 | 완료 보고서 | 배상규 |
