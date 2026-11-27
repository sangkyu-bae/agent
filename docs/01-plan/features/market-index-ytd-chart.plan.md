# market-index-ytd-chart Planning Document

> **Summary**: 시장 분석 대시보드에 KOSPI·KOSDAQ 올해(YTD) 등락률 차트를 추가한다. 지수 일봉은 새 테이블에 적재하고, 조회할 때 비어 있는 날만 KIS에서 받아 채운다.
>
> **Project**: sangplusbot (Agent Builder)
> **Author**: 배상규
> **Date**: 2026-11-27
> **Status**: Draft
> **선행 기능**: stock-analysis-agents (PR #137~#141 머지, archived)

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 시장 분석 화면에는 올해 지수 흐름이 없다. 기존 누적 수익률 차트는 가상 계좌가 처음 돈 날부터 시작하고, 지수 값도 회차가 돈 날에만 쌓여 리포트·매수 판단을 해석할 기준이 없다. |
| **Solution** | 지수 일봉 테이블(`ma_index_daily`)을 새로 두고, 차트 API가 테이블을 먼저 읽은 뒤 마지막 저장일 이후만 KIS `get_index_history`로 받아 저장한다. 오늘 장중 봉은 저장하지 않고 응답에만 붙인다. |
| **Function/UX Effect** | 대시보드에서 KOSPI·KOSDAQ의 연초 대비 등락률(%)을 한 그래프로 비교하고, 시장 체제가 기록된 날은 점으로 표시해 체제 라벨의 근거를 함께 본다. |
| **Core Value** | 자동 분석 스위치가 꺼져 있어도 올해 시장 흐름을 볼 수 있고, 에이전트의 판단(예: strong_bear로 매수 보류)을 사용자가 직접 검증할 수 있다. |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 리포트·매수 판단을 해석할 올해 시장 흐름 기준이 화면에 없다 |
| **WHO** | 시장 분석 열람 권한자(MARKET_ANALYSIS_VIEW) — 리포트·판단을 읽고 검증하는 사람 |
| **RISK** | KIS 한 번 호출 200봉 상한·호출 한도, 첫 조회 백필 지연, 동시 조회 중복 적재 |
| **SUCCESS** | 테이블이 비어 있어도 첫 조회에 연초~최근 확정 봉이 채워지고, 캐시 시간(5분) 안의 재조회는 KIS를 부르지 않는다 |
| **SCOPE** | 백엔드(V102 테이블·적재·API) → 프론트(대시보드 카드·차트·체제 점) |

---

## 1. Overview

### 1.1 Purpose

시장 분석 대시보드에 KOSPI·KOSDAQ 올해 등락률 차트를 추가해, 리포트의 종목 수익률과 에이전트의 시장 체제 판정을 올해 시장 흐름과 비교할 수 있게 한다.

### 1.2 Background

- 현재 대시보드 `EquityChart.tsx`는 가상 계좌 누적 실현 수익률을 KOSPI·KOSDAQ과 비교한다. 출발점은 가상 계좌 첫 회차이고, 지수 값은 회차마다 `ma_market_regime`에 한 줄씩 쌓인 값이다. 회차가 없던 날은 비고, 연초부터의 흐름은 없다.
- 시장 체제는 회차 ①에서 KOSPI 80봉으로 판정하지만(`application/market_analysis/regime.py`), 화면에는 최신 라벨만 나온다.
- 자동 분석 스위치(`ma_setting.enabled`)는 기본 꺼짐이라 회차에 기대는 적재는 스위치를 끈 동안 멈춘다. 그래서 조회 경로에서 채운다(사용자 결정).
- KIS `get_index_history`(agent_mcp `mcp-kis-server`)는 날짜 범위를 받아 페이지를 이어 받지만, 결과는 `limit` 최대 200봉(`KIS_BARS_MAX_ROWS`)·페이지 3개(`KIS_HISTORY_MAX_PAGES`)까지다. 11월 말 기준 YTD는 약 225거래일이라 한 번에 받을 수 없다.

### 1.3 Related Documents

- 선행 설계: `docs/archive/2026-11/stock-analysis-agents/` (Design §2.2 ①, §6 RegimePolicy, §9.4 대시보드)
- KIS 도구: `agent_mcp/mcp-kis-server/src/mcp_kis_server/application/indexes.py`
- 조회 경로 KIS 호출 선례: `idt/src/application/market_analysis/quotes.py`

---

## 2. Scope

### 2.1 In Scope

- [ ] Flyway `V102__create_ma_index_daily.sql` — 지수 확정 일봉 테이블 (지수·거래일 PK, 시가·고가·저가·종가)
- [ ] 적재 서비스: 테이블의 지수별 마지막 거래일 다음 날 ~ 오늘(KST) 범위만 KIS에서 받아 확정 봉만 upsert. 테이블이 비어 있으면 올해 1월 1일부터
- [ ] 200봉 상한 대응: 요청 범위를 반기 이하 구간으로 나눠 호출
- [ ] 오늘 장중 봉(`provisional`)은 저장하지 않고, 조회 응답 끝에 `provisional: true` 로만 붙임
- [ ] 캐시 시간(5분) 안의 재조회는 KIS 호출 없음. 장 마감 뒤 오늘 봉이 저장되면 그날은 더 부르지 않음. 장중 봉은 메모리 캐시
- [ ] 조회 API `GET /api/v1/market-analysis/index-chart` (VIEW 권한) — 지수별 일봉 + 연초 대비 등락률 + 해당 기간 `ma_market_regime` 기록
- [ ] KIS 미설정·호출 실패 시 저장된 데이터만 돌려주고 상태 플래그로 알림 (예외 없음)
- [ ] 프론트: 대시보드 탭에 "올해 시장" 카드 + `IndexYtdChart` (recharts LineChart, % 겹침, 툴팁에 지수 값)
- [ ] 체제가 기록된 날은 KOSPI 선 위에 점으로 표시 (툴팁에 체제 라벨)
- [ ] 미확정 봉 표시, 데이터 없음·KIS 불가 빈 상태 문구

### 2.2 Out of Scope

- 기간 선택(3개월·1년 등) — YTD 하나만
- 지수 값 보기 토글, 지수별 분리 차트
- 회차 ① 지수 조회 결과를 테이블에 쓰는 경로 (조회 경로 적재로 충분, 필요 시 후속)
- 중간 구멍 보수(마지막 저장일 이전의 빠진 날) — 확정 봉은 되돌아가 바뀌지 않으므로 꼬리만 채운다
- KOSPI200 등 다른 지수, 해외 지수
- 기존 `EquityChart`·`ma_market_regime` 구조 변경
- agent_mcp KIS 서버 수정 (`KIS_BARS_MAX_ROWS` 상향 포함)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | `ma_index_daily` 테이블에 지수(KOSPI·KOSDAQ)별 확정 일봉을 거래일 단위로 저장한다 (PK 지수+거래일, 다시 쓰면 덮어씀) | High | Pending |
| FR-02 | 차트 조회 시 지수별 마지막 저장일 다음 날 ~ 오늘(KST) 구간만 KIS에서 받는다(확정 봉만 저장, Design §2.2). 비어 있으면 올해 1월 1일부터 | High | Pending |
| FR-03 | 한 번의 KIS 호출이 200봉을 넘지 않도록 구간을 나눠 요청한다 | High | Pending |
| FR-04 | `provisional` 봉은 저장하지 않고 응답 마지막 점으로만 돌려준다 | High | Pending |
| FR-05 | 응답의 각 점은 거래일·종가·연초 첫 거래일 종가 대비 등락률(%)을 가진다 | High | Pending |
| FR-06 | 응답에 같은 기간 `ma_market_regime` 기록(거래일·체제)을 함께 넣는다 | Medium | Pending |
| FR-07 | KIS 서버 미설정·실행 사용자 없음·호출 실패면 저장된 데이터만 돌려주고 `source_status`(ok·stale·unavailable)로 표시한다 | High | Pending |
| FR-08 | 오늘 확정 봉까지 저장됐으면 KIS를 부르지 않고, 그 전에는 캐시 시간(5분)마다 꼬리 구간만 부른다 | Medium | Pending |
| FR-09 | 동시 조회로 같은 구간을 두 번 받아도 upsert라 결과가 같다 | Medium | Pending |
| FR-10 | 대시보드에 KOSPI·KOSDAQ 연초 대비 % 겹침 차트를 표시한다. 툴팁에 날짜·지수 값·등락률 | High | Pending |
| FR-11 | 체제 기록이 있는 날은 점으로 표시하고 툴팁에 체제 라벨을 보인다 | Medium | Pending |
| FR-12 | 미확정 점은 "미확정"으로, 데이터 없음·KIS 불가는 빈 상태/안내 문구로 표시한다 (색만으로 구분하지 않음) | Medium | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Performance | 적재 후 조회(KIS 미호출) 응답 < 300ms | 로컬 TestClient 측정 |
| Performance | 첫 백필은 지수당 KIS 호출 2회 이내 | 어댑터 호출 횟수 테스트 |
| Security | VIEW 권한 없으면 403, 기존 `require_view` 재사용 | API 테스트 |
| Isolation | market_analysis 모듈 경계 유지 (infra→application import 금지, 플랫폼 FK 없음) | 기존 격리 계약 테스트 |
| Accessibility | 차트 `role="img"` + aria-label, 미확정·체제는 텍스트 병행 | 컴포넌트 테스트 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] SC-1: 테이블이 빈 상태에서 첫 조회가 올해 첫 거래일~최근 KOSPI·KOSDAQ 확정 봉을 채우고 차트가 그려진다 (실데이터 확인)
- [ ] SC-2: 캐시 시간(5분) 안의 재조회는 KIS 호출 0회, 장 마감 뒤 오늘 봉이 저장되면 그날은 더 부르지 않음 (Design §2.2)
- [ ] SC-3: 첫 거래일 등락률 0%, 이후 점의 등락률이 종가로 계산한 값과 일치 (결정론 계산 테스트)
- [ ] SC-4: 장중 조회 시 마지막 점이 미확정으로 표시되고 테이블에는 저장되지 않는다
- [ ] SC-5: KIS 서버를 끈 상태에서도 저장된 데이터로 차트가 나오고 안내 문구가 보인다
- [ ] SC-6: 체제 기록이 있는 날짜에 점이 찍힌다
- [ ] 백엔드 pytest·프론트 Vitest 신규 테스트 통과, 기존 market_analysis 회귀 통과

### 4.2 Quality Criteria

- [ ] 신규 application/domain 코드 테스트 커버리지 80% 이상
- [ ] ruff·eslint·type-check 신규 오류 0
- [ ] 375·768·1440 폭에서 카드 넘침 없음

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| KIS 200봉 상한으로 YTD가 잘림 | High | High | 구간을 반기 이하로 나눠 호출 (FR-03), `truncated` 응답이면 경고 로그 |
| 첫 조회 백필이 느려 대시보드가 늦게 뜸 | Medium | Medium | 차트를 별도 API·별도 쿼리로 분리해 기존 대시보드 응답과 독립. 카드만 로딩 상태 |
| KIS 호출 한도(RATE_LIMITED) | Medium | Low | 같은 날 재호출 없음(FR-08), 장중 봉 메모리 캐시, 실패 시 저장 데이터로 응답 |
| 동시 조회 중복 적재 | Low | Medium | PK upsert로 멱등 (FR-09) |
| 휴장일을 "빈 날"로 보고 매번 재호출 | Medium | Medium | 결과가 0봉이어도 캐시 시간(5분) 동안 다시 묻지 않고, 그 뒤엔 하루치 소구간 1회만 부른다 (Design §2.2, Check G-M2로 문구 갱신) |
| KIS 봉 날짜·장중 판정이 KST 기준과 어긋남 | Medium | Low | KIS 응답의 `provisional`·`date`를 그대로 신뢰, 서버 시각은 KST로 계산 (기존 round 시각 규칙 재사용) |
| 운영 배포 시 V102 누락 | Medium | Medium | 배포 체크리스트에 V100·V101 다음 V102 명시 |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `ma_index_daily` | DB 테이블 (신규) | V102 신규 생성 |
| `GET /api/v1/market-analysis/index-chart` | API (신규) | 차트 조회 + 꼬리 적재 |
| `market_analysis/ports.py` | 포트 | 지수 일봉 저장소 포트 추가 |
| `market_analysis/di` | 조립 | 신규 서비스·저장소 배선 |
| `DashboardTab.tsx` | 프론트 화면 | 카드 1개 추가 |
| `types/marketAnalysis.ts`·service·hooks·`queryKeys` | 프론트 | 신규 타입·호출·훅 추가 |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| `ma_market_regime` | READ (추가) | 신규 차트 조회 | None — 읽기만 |
| `MarketTools.call` (`get_index_history`) | CALL (추가) | 신규 적재 서비스 | None — 허용목록에 이미 있음 (`domain/market_analysis/tool_policy.py`) |
| `GET /market-analysis/dashboard` | READ | `DashboardTab` | None — 응답 변경 없음 |
| `EquityChart` | RENDER | `DashboardTab` | None — 그대로 두고 카드만 추가 |

### 6.3 Verification

- [ ] 기존 대시보드 응답 스키마 변경 없음
- [ ] 권한: 신규 API는 VIEW 권한, 비권한자 403
- [ ] 격리 계약 테스트 통과

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Selected |
|-------|:--------:|
| **Enterprise** (domain/application/infrastructure 레이어 분리, DI) | ✅ — 기존 `market_analysis` 모듈 구조를 따른다 |

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 데이터 원천 | 조회 시 KIS+메모리 캐시 / 일봉 테이블 | 일봉 테이블 | 사용자 결정. KIS 장애 때도 차트 유지 |
| 적재 시점 | 조회 시 꼬리만 / 회차 ① / ticker 1일 1회 | 조회 시 꼬리만 | 사용자 결정. 자동 분석 스위치와 무관하게 동작 |
| 장중 봉 | 응답에만 / 확정만 | 응답에만 붙임 | 사용자 결정 |
| 표시 | % 겹침 / 지수 값 2개 / 토글 | % 겹침, 툴팁에 지수 값 | 사용자 결정 |
| 체제 | 제외 / 있는 날만 점 | 있는 날만 점 | 사용자 결정 |
| 기간 | YTD / YTD+1년 | YTD | 사용자 결정 |
| API | 대시보드 응답 확장 / 별도 엔드포인트 | 별도 엔드포인트 | 첫 백필 지연이 기존 대시보드를 막지 않게 |
| 차트 | recharts / chart.js | recharts | `EquityChart`와 같은 라이브러리, 신규 의존성 없음 |
| 등락률 계산 | LLM·프론트 / 백엔드 결정론 | 백엔드 결정론 계산 | 기존 G1(재무 증감 결정론 계산) 원칙과 같게 |

### 7.3 Clean Architecture Approach

```
idt/
  db/migration/V102__create_ma_index_daily.sql
  src/domain/market_analysis/index_chart.py        # 구간 나누기·등락률 계산 (순수)
  src/application/market_analysis/index_chart.py   # 꼬리 적재 + 조회 조립 유스케이스
  src/application/market_analysis/ports.py         # IndexDailyStore 포트 추가
  src/infrastructure/market_analysis/models.py     # MaIndexDailyModel
  src/infrastructure/market_analysis/index_daily_repository.py
  src/api/routes/market_analysis_router.py          # GET /index-chart
idt_front/
  src/types/marketAnalysis.ts                       # IndexChartResponse 등
  src/services/marketAnalysisService.ts             # getIndexChart
  src/hooks/useMarketAnalysis.ts                    # useIndexChart
  src/pages/MarketAnalysisPage/IndexYtdChart.tsx
  src/pages/MarketAnalysisPage/DashboardTab.tsx     # 카드 추가
```

(실제 파일 위치는 Design에서 기존 파일 배치에 맞춰 확정)

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- [x] `CLAUDE.md` 3종 + `idt/docs/rules/`
- [x] ESLint / TypeScript 설정 (`idt_front`)
- [x] ruff (`idt`)

### 8.2 Conventions to Follow

| Category | Rule |
|----------|------|
| DB | Flyway `V102__...sql`, 테이블 접두 `ma_`, 컬럼 comment 필수, 플랫폼 FK 없음 |
| 레이어 | infra→application import 금지, 포트 값 타입은 domain |
| 테스트 | TDD (pytest Red→Green, Vitest+RTL+MSW) |
| 프론트 | 토큰 클래스만, `queryKeys` 팩토리, 상수는 `src/types/*.ts` |
| 실행 | `uv run python -m pytest` |

### 8.3 Environment Variables Needed

없음 (기존 KIS 서버 설정·`ma_setting` 실행 사용자 재사용)

---

## 9. Next Steps

1. [ ] `/pdca design market-index-ytd-chart` — 테이블 DDL·API 응답 형태·구간 나누기 규칙·장중 캐시 TTL 확정
2. [ ] 구현 (worktree `../wt/market-index-ytd-chart`, 브랜치 `feature/market-index-ytd-chart`)
3. [ ] 로컬 DB에 V102 적용 후 실데이터 확인 (SC-1·SC-4·SC-5)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.2 | 2026-11-27 | Check G-M1·G-M2 반영 — 구간 끝 "어제"→"오늘(확정 봉만 저장)", 휴장일 대응을 TTL 방식으로 | 배상규 |
| 0.1 | 2026-11-27 | 초안 — 사용자 결정 6건 반영 (테이블 적재·조회 시 꼬리 적재·장중 봉 응답만·% 겹침·체제 점·YTD) | 배상규 |
