# market-index-ytd-chart Design Document

> **Summary**: 지수 확정 일봉 테이블(V102)과 조회 시 꼬리 적재 서비스, `GET /market-analysis/index-chart`, 대시보드 "올해 시장" 카드를 설계한다.
>
> **Project**: sangplusbot (Agent Builder)
> **Author**: 배상규
> **Date**: 2026-11-27
> **Status**: Draft
> **Planning Doc**: [market-index-ytd-chart.plan.md](../../01-plan/features/market-index-ytd-chart.plan.md)
> **Architecture**: Option C — 실용 균형 (사용자 선택)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 리포트·매수 판단을 해석할 올해 시장 흐름 기준이 화면에 없다 |
| **WHO** | 시장 분석 열람 권한자(MARKET_ANALYSIS_VIEW) — 리포트·판단을 읽고 검증하는 사람 |
| **RISK** | KIS 한 번 호출 200봉 상한·호출 한도, 첫 조회 백필 지연, 동시 조회 중복 적재 |
| **SUCCESS** | 테이블이 비어 있어도 첫 조회에 연초~최근 확정 봉이 채워지고, 캐시 시간 안의 재조회는 KIS를 부르지 않는다 |
| **SCOPE** | 백엔드(V102 테이블·적재·API) → 프론트(대시보드 카드·차트·체제 점) |

---

## 1. Overview

### 1.1 Design Goals

- 자동 분석 스위치와 무관하게 대시보드에서 KOSPI·KOSDAQ YTD 등락률을 본다.
- KIS 호출은 "아직 저장 안 된 꼬리 구간"만, 한 번에 200봉을 넘지 않게.
- 등락률은 백엔드에서 결정론으로 계산한다(LLM·프론트 계산 없음).
- 기존 대시보드 API·`EquityChart`·`ma_market_regime` 은 바꾸지 않는다.

### 1.2 Design Principles

- 구간 계산·등락률은 domain 순수 함수 — 시각(`today_kst`)은 인자로 받는다.
- 실패는 예외가 아니라 `source_status` 로 — 저장된 데이터가 있으면 그것으로 그린다.
- market_analysis 모듈 경계 유지: infra→application import 금지, 플랫폼 FK 없음, 포트 값 타입은 domain.

---

## 2. Architecture

### 2.0 Architecture Comparison

| Criteria | A: 최소 변경 | B: 클린 | **C: 실용 균형** |
|----------|:-:|:-:|:-:|
| 접근 | `MarketAnalysisQueries`·`QueryRepository` 확장 | C + KIS 봉 파서 어댑터·캐시 포트·별도 라우터 | domain 규칙 + 새 서비스 + 새 저장소 |
| 신규 파일(백엔드) | 1 (V102) | ~7 | 4 |
| 수정 파일(백엔드) | 4 | 4 | 4 |
| 복잡도 | 낮음 | 높음 | 중간 |
| 유지보수 | 중간 — 조회 저장소가 쓰기를 맡음 | 높음 | 높음 |
| 위험 | queries.py 비대 | 과설계 | 낮음 |

**Selected**: C — 쓰기를 하는 조회라 기존 읽기 전용 `QueryRepository` 와 분리하고, 순수 규칙은 테스트하기 쉬운 domain 에 둔다.

### 2.1 Component Diagram

```
DashboardTab ──▶ IndexYtdChart ◀── useIndexChart ──▶ marketAnalysisService.getIndexChart
                                                          │ GET /api/v1/market-analysis/index-chart
                                                          ▼
router.get_index_chart (require_view)
   └─▶ runtime.index_chart : IndexChartService.chart(request_id)
          ├─ SettingReader.get()                    (KIS 서버 id · 실행 사용자)
          ├─ IndexDailyStore  ◀─ infra/index_daily_repository.py (ma_index_daily, ma_market_regime 읽기)
          ├─ MarketTools.call("get_index_history")  (KIS MCP, 허용목록에 이미 있음)
          └─ domain/index_chart.py                  (tail_range · split_ranges · ytd_points)
```

### 2.2 Data Flow (chart 1회)

```
1. today = KST 오늘, year_start = date(today.year, 1, 1)
2. 지수별(KOSPI, KOSDAQ):
   a. 메모리 캐시가 TTL(300초) 안이면 → KIS 건너뜀, 캐시된 장중 봉 사용
   b. 아니면 last = store.last_date(index, year)
      rng = tail_range(last, year_start, today)     # None 이면 KIS 불필요
      rng 를 split_ranges(rng, 183일) 로 나눠 오래된 구간부터 KIS 호출
        - 확정 봉(provisional=false)만 store.upsert
        - 장중 봉은 캐시에만
        - 한 구간이라도 실패하면 거기서 멈춤(앞 구간 저장분은 유지), error_code 기록
      캐시 갱신(fetched_at, provisional_bar)
3. bars = store.bars(index, year_start, today)  (+ 장중 봉을 끝에 붙임)
4. regimes = store.regimes(year_start, today)
5. ytd_points(bars) 로 등락률 계산 → 응답
```

- 동시 요청: 서비스 인스턴스의 `asyncio.Lock` 으로 2단계(적재)를 직렬화한다. 두 번째 요청은 락을 얻은 뒤 캐시가 갱신돼 있으므로 KIS를 다시 부르지 않는다. 다중 프로세스면 중복 호출될 수 있으나 upsert 라 결과는 같다(FR-09).
- 장 마감 뒤 첫 조회는 오늘 봉이 `provisional=false` 로 와서 저장되고, 이후 `tail_range` 가 `None` 을 돌려 KIS 호출이 없다.
- 휴장일·주말: 구간에 봉이 0개여도 정상(캐시 TTL 동안 재호출 없음, TTL 뒤엔 하루치 소구간 1회).
- 실패 결과도 TTL 동안 캐시한다(같은 오류 코드를 돌려줌) — `RATE_LIMITED` 상황에서 재호출 폭주를 막는다.
- 설정을 읽지 못하면 KIS를 부르지 않고 저장분으로 응답한다(`STORE_FAILED`).

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| IndexChartService | SettingReader, IndexDailyStore, MarketTools, LoggerInterface, now_utc | 적재·조회 조립 |
| index_daily_repository | session_factory | `ma_index_daily` 읽기·upsert, `ma_market_regime` 읽기 |
| KIS `get_index_history` | agent_mcp mcp-kis-server | 지수 일봉 (`start`·`end`·`limit≤200`) |

---

## 3. Data Model

### 3.1 Entity / 값 타입 (domain)

```python
# src/domain/market_analysis/index_chart.py
INDEXES = ("KOSPI", "KOSDAQ")
CHUNK_DAYS = 183           # 반기 ≈ 125거래일 < KIS limit 200
FETCH_LIMIT = 200

@dataclass(frozen=True)
class IndexBar:            # 포트 값 타입 (infra·application 공용)
    index: str
    day: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    provisional: bool = False

@dataclass(frozen=True)
class IndexPoint:
    day: date
    close: Decimal
    rate: Decimal          # 연초 첫 봉 종가 대비 %, 소수 2자리 ROUND_HALF_UP
    provisional: bool

def tail_range(last: date | None, year_start: date, today: date) -> tuple[date, date] | None:
    """last 가 None 이면 (year_start, today). last >= today 면 None. 그 외 (last+1, today)."""

def split_ranges(start: date, end: date, days: int = CHUNK_DAYS) -> list[tuple[date, date]]:
    """오래된 순, 각 구간 길이 ≤ days, 빈틈·겹침 없음."""

def ytd_points(bars: list[IndexBar]) -> list[IndexPoint]:
    """날짜순 정렬·중복 제거(같은 날은 확정 봉 우선). 기준 = 첫 봉 종가. 기준이 0 이하면 빈 목록."""
```

### 3.2 Entity Relationships

`ma_index_daily` 는 독립 테이블. `ma_market_regime` 과는 `trade_date` 로만 맞춰 읽는다(FK 없음).

### 3.3 Database Schema — `V102__create_ma_index_daily.sql`

```sql
CREATE TABLE ma_index_daily (
    index_code VARCHAR(8) NOT NULL COMMENT '지수 (KOSPI·KOSDAQ)',
    trade_date DATE NOT NULL COMMENT '거래일 (KST)',
    open_price DECIMAL(12,2) NOT NULL COMMENT '시가',
    high_price DECIMAL(12,2) NOT NULL COMMENT '고가',
    low_price DECIMAL(12,2) NOT NULL COMMENT '저가',
    close_price DECIMAL(12,2) NOT NULL COMMENT '종가',
    created_at DATETIME NOT NULL COMMENT '적재 시각 (UTC)',
    PRIMARY KEY (index_code, trade_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='시장 분석 지수 확정 일봉';
```

- 확정 봉만 저장. 다시 쓰면 덮어쓴다(기존 `save_regime` 과 같은 `session.get` → add/setattr 패턴).
- 모델: `infrastructure/market_analysis/models.py` 에 `MaIndexDailyModel` 추가.

### 3.4 포트 (application/market_analysis/ports.py)

```python
class IndexDailyStore(Protocol):
    async def last_date(self, index: str, since: date, request_id: str) -> date | None: ...
    async def upsert(self, bars: list[IndexBar], request_id: str) -> int: ...
    async def bars(self, index: str, start: date, end: date, request_id: str) -> list[IndexBar]: ...
    async def regimes(self, start: date, end: date, request_id: str) -> list[tuple[date, str]]: ...
```

---

## 4. API Specification

### 4.1 Endpoint List

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/api/v1/market-analysis/index-chart` | KOSPI·KOSDAQ YTD 등락률 + 체제 기록 (필요 시 꼬리 적재) | `require_view` |

### 4.2 Detailed Specification

**Response 200** (dict 응답 — 기존 조회 API 관례):

```json
{
  "year": 2026,
  "series": {
    "KOSPI": {
      "base_date": "2026-01-02",
      "base_close": 2510.33,
      "points": [
        {"date": "2026-01-02", "close": 2510.33, "rate": 0.0, "provisional": false},
        {"date": "2026-11-27", "close": 2601.10, "rate": 3.62, "provisional": true}
      ]
    },
    "KOSDAQ": {"base_date": "2026-01-02", "base_close": 701.2, "points": []}
  },
  "regimes": [{"date": "2026-11-26", "value": "strong_bear"}],
  "source_status": "ok",
  "source_error": null,
  "as_of": "2026-11-27T05:12:00Z"
}
```

| 필드 | 규칙 |
|------|------|
| `series.<IDX>.points` | 날짜 오름차순. 장중 봉은 마지막 1개만 `provisional: true` |
| `base_date`·`base_close` | 올해 첫 봉. 봉이 없으면 `null` |
| `rate` | `(close / base_close − 1) × 100`, 소수 2자리 |
| `source_status` | `ok`: KIS 성공 또는 호출 불필요 · `stale`: KIS 실패/미설정이지만 저장 데이터 있음 · `unavailable`: KIS 실패/미설정이고 저장 데이터 없음 |
| `source_error` | KIS 오류 코드(`SERVER_UNAVAILABLE`·`KIS_AUTH_FAILED`·`RATE_LIMITED`…) 또는 `KIS_NOT_CONFIGURED`, DB·설정 읽기/쓰기 실패는 `STORE_FAILED`. 정상이면 `null` |

**Errors**: 403 (권한 없음, 기존 `require_view`), 503 `MA_UNAVAILABLE` (런타임 조립 실패, 기존 라우터 규칙), 404 (기능 플래그 꺼짐, 기존 규칙). KIS 실패는 200 + `source_status`.

---

## 5. UI/UX Design

### 5.1 Screen Layout (DashboardTab)

```
[KPI 8칸 그리드]                       ← 기존
┌ 올해 시장 ─────────────────────────┐ ← 신규 Card (누적 수익률 카드 위)
│ KOSPI +3.62%   KOSDAQ −1.20%  (11/27 미확정) │  요약 한 줄
│ ┌ LineChart h-64 ───────────────┐ │
│ │ 0% 기준선, KOSPI·KOSDAQ 선     │ │
│ │ ● 체제 기록일 (KOSPI 선 위)     │ │
│ └───────────────────────────────┘ │
│ 연초 첫 거래일 종가 대비 등락률입니다. 점은 시장 체제가 기록된 날입니다. │
│ [stale 이면] 최신 시세를 받지 못해 MM/DD까지의 저장 데이터로 표시합니다. │
└───────────────────────────────────┘
┌ 누적 수익률 ┐                         ← 기존 그대로
```

### 5.2 User Flow

대시보드 탭 진입 → 기존 대시보드와 별개로 `useIndexChart` 로딩(카드 안 로딩 문구) → 차트 표시 → 점·선에 마우스 올리면 툴팁(날짜, KOSPI 값·%, KOSDAQ 값·%, 미확정 여부, 체제 라벨).

### 5.3 Component List

| Component | Location | Responsibility |
|-----------|----------|----------------|
| `IndexYtdChart` | `src/pages/MarketAnalysisPage/IndexYtdChart.tsx` | recharts LineChart, 0% ReferenceLine, 체제 점(dot 렌더 함수), 커스텀 툴팁 |
| `IndexYtdCard` (DashboardTab 안 작은 함수 컴포넌트 또는 별도 파일) | `DashboardTab.tsx` | 로딩·오류·빈 상태·요약 줄·안내 문구 |
| `toIndexChartRows` | `src/utils/marketIndexChart.ts` | 응답 → 날짜 기준 행 `{date, kospi, kosdaq, kospi_close, kosdaq_close, provisional, regime}` 병합 (순수 함수) |
| `useIndexChart` | `src/hooks/useMarketAnalysis.ts` | `queryKeys.marketAnalysis.indexChart()`, staleTime 5분 |

### 5.4 Page UI Checklist

- [ ] 카드 제목 "올해 시장"
- [ ] 요약 줄: 지수명 + 마지막 점 등락률(부호·색 + 텍스트), 마지막 점이 미확정이면 "(MM/DD 미확정)" 텍스트
- [ ] 선 2개: KOSPI(`--color-fg-muted` 계열, EquityChart 와 같은 색 규칙), KOSDAQ(`--color-info`)
- [ ] Y축 단위 `%`, 0% 기준선
- [ ] 체제 기록일에 KOSPI 선 위 점, 툴팁에 `REGIME_LABELS` 라벨
- [ ] 툴팁: 날짜, 지수 값(천 단위 구분), 등락률, "미확정" 텍스트
- [ ] 로딩: 카드 안 "지수 흐름을 불러오는 중…" (첫 조회는 연초 적재로 수 초 걸릴 수 있음)
- [ ] 오류(HTTP): `ErrorBox` (기존 컴포넌트)
- [ ] `unavailable`: Empty "지수 시세를 받을 수 없습니다. KIS 서버 설정을 확인하세요."
- [ ] `stale`: 차트 + 안내 문구(warning 텍스트). 기준일은 마지막 확정 점 날짜
- [ ] 한쪽 지수만 점이 있으면: 차트 + "KOSDAQ 시세를 받지 못했습니다. 잠시 후 다시 확인하세요." (빠진 지수 이름)
- [ ] 범례 순서는 요약 줄과 같게 KOSPI→KOSDAQ
- [ ] 두 지수 모두 points 0개(1월 첫 거래일 전): Empty "올해 첫 거래일 이후에 표시됩니다."
- [ ] `role="img"` + aria-label "올해 KOSPI·KOSDAQ 등락률"
- [ ] 375·768·1440 폭 넘침 없음

---

## 6. Error Handling

| 상황 | 처리 | 응답 |
|------|------|------|
| KIS 서버 id·실행 사용자 미설정 | KIS 호출 안 함, `source_error=KIS_NOT_CONFIGURED` | 저장 데이터 유무로 `stale`/`unavailable` |
| KIS 호출 실패(`is_error`) | 해당 지수 적재 중단(앞 구간 저장분 유지), warning 로그 | 저장 데이터 유무로 `stale`/`unavailable` |
| KIS 응답 `truncated: true` | warning 로그(구간 크기 재검토 신호), 받은 봉은 저장 | `ok` |
| 봉 값 파싱 실패(숫자 아님·0 이하) | 그 봉만 버림 | — |
| DB upsert 실패 | warning 로그, 조회는 계속(저장된 것만) | `stale` |
| 기준 종가 없음/0 이하 | points 빈 목록 | — |

두 지수 결과가 다르면 나쁜 쪽(`unavailable` > `stale` > `ok`)을 응답 상태로 쓰고, `source_error` 는 처음 만난 오류 코드.

---

## 7. Security Considerations

- [x] 권한: 기존 `require_view` (MARKET_ANALYSIS_VIEW)
- [x] KIS 호출은 기존 `MarketTools` 허용목록 경유(주문 도구 차단 정책 그대로)
- [x] 실행 사용자는 `ma_setting.run_as_user_id` — 요청자 권한으로 KIS를 부르지 않는다(기존 quotes 와 같음)
- [x] 입력 파라미터 없음(쿼리스트링 없음) → 주입 경로 없음

---

## 8. Test Plan

### 8.1 Test Scope

| Type | Target | Tool |
|------|--------|------|
| domain unit | `tail_range`·`split_ranges`·`ytd_points` | pytest |
| application | `IndexChartService` (가짜 store·tools·clock) | pytest |
| infra | `index_daily_repository` (기존 market_analysis infra 테스트 방식 따름) | pytest |
| API | `GET /index-chart` 200 형태·403 | pytest + TestClient |
| front util | `toIndexChartRows` | Vitest |
| front component | `IndexYtdChart`·카드 상태별 | Vitest + RTL + MSW |
| front hook | `useIndexChart` | Vitest + MSW |

### 8.2 핵심 테스트 케이스

**domain**
- `tail_range(None, 1/1, 11/27)` = (1/1, 11/27); `(11/26, …)` = (11/27, 11/27); `(11/27, …)` = None
- `split_ranges(1/1, 11/27, 183)` → 2구간, 빈틈·겹침 없음, 마지막 끝 = 11/27
- `ytd_points`: 첫 점 rate 0.00, 계산값 일치(SC-3), 같은 날 확정·장중 중복 시 확정 우선, 기준 0 → 빈 목록

**application**
- 빈 테이블: 지수당 KIS 2회(1/1~7/2, 7/3~11/27), `start`·`end`·`limit=200` 인자 확인, 확정 봉만 upsert (SC-1)
- TTL 안 재호출: KIS 0회 (SC-2)
- 장중 봉: 저장 안 됨, 응답 마지막 점 provisional (SC-4)
- 마감 뒤 오늘 확정 봉 저장 → 다음 호출(TTL 뒤) `tail_range` None → KIS 0회
- KIS 실패 + 저장 데이터 있음 → `stale` (SC-5), 없음 → `unavailable`
- 미설정 → KIS 0회, `KIS_NOT_CONFIGURED`
- 두 번째 구간 실패 → 첫 구간 저장분 유지, 다음 호출이 이어서 채움
- 동시 2요청(gather) → KIS 호출 지수당 1세트
- 체제 기록 포함 (SC-6 데이터 측)

**front**
- 응답 병합: 한쪽 지수만 있는 날짜도 행 생성, regime 매칭
- 상태별 렌더: 로딩·unavailable·stale 안내·빈 연초·정상(요약 줄 텍스트, 미확정 텍스트)

### 8.3 E2E (module-4, 실데이터)

1. 로컬 DB에 V102 적용 → `ma_index_daily` 비어 있음 확인
2. 대시보드 진입 → 차트 표시, 테이블에 KOSPI·KOSDAQ 각 ~225행 (SC-1)
3. 새로고침 → 백엔드 로그에 KIS 호출 없음 (SC-2)
4. 장중이면 마지막 점 미확정 표시, 테이블에 오늘 행 없음 (SC-4)
5. KIS 컨테이너 정지 후 TTL 경과 조회 → 차트 + stale 안내 (SC-5)
6. 11/26 등 체제 기록일에 점 (SC-6)
7. 375·768·1440 폭 캡처

---

## 9. Clean Architecture

### 9.4 This Feature's Layer Assignment

| Component | Layer | Location |
|-----------|-------|----------|
| `IndexBar`·`IndexPoint`·`tail_range`·`split_ranges`·`ytd_points` | Domain | `idt/src/domain/market_analysis/index_chart.py` |
| `IndexDailyStore` 포트 | Application | `idt/src/application/market_analysis/ports.py` |
| `IndexChartService` | Application | `idt/src/application/market_analysis/index_chart.py` |
| `MaIndexDailyModel` | Infrastructure | `idt/src/infrastructure/market_analysis/models.py` |
| `IndexDailyRepository` | Infrastructure | `idt/src/infrastructure/market_analysis/index_daily_repository.py` |
| 조립 | API(DI) | `idt/src/api/market_analysis_di.py` (`MarketAnalysisRuntime.index_chart`) |
| 라우트 | API | `idt/src/api/routes/market_analysis_router.py` |

infra 는 domain 의 `IndexBar` 만 import 하고 application 을 import 하지 않는다(기존 격리 계약 테스트로 확인).

---

## 10. Coding Convention Reference

- 파일 머리 독스트링에 `Design Ref: market-index-ytd-chart §N`
- Decimal 로 계산, 응답 직렬화 때만 float (기존 `_f`·`_num` 관례)
- 시각은 `now_utc` 주입 → KST 변환은 `RoundSchedulePolicy.to_kst` 재사용
- 프론트 상수(`as const`)는 `src/types/marketAnalysis.ts`, 컴포넌트 파일에서 런타임 상수 export 금지
- 프론트 색은 토큰 CSS 변수만(`EquityChart` 와 같은 방식)

---

## 11. Implementation Guide

### 11.1 File Structure

```
idt/
  db/migration/V102__create_ma_index_daily.sql                 (신규)
  src/domain/market_analysis/index_chart.py                    (신규)
  src/application/market_analysis/index_chart.py               (신규)
  src/application/market_analysis/ports.py                     (수정: IndexDailyStore)
  src/infrastructure/market_analysis/models.py                 (수정: MaIndexDailyModel)
  src/infrastructure/market_analysis/index_daily_repository.py (신규)
  src/api/market_analysis_di.py                                (수정: index_chart 조립)
  src/api/routes/market_analysis_router.py                     (수정: GET /index-chart)
  tests/... (domain·application·infra·api)
idt_front/src/
  constants/api.ts                       (수정: MARKET_ANALYSIS_INDEX_CHART)
  lib/queryKeys.ts                       (수정: marketAnalysis.indexChart)
  types/marketAnalysis.ts                (수정: IndexChartResponse 등)
  services/marketAnalysisService.ts      (수정: getIndexChart)
  hooks/useMarketAnalysis.ts             (수정: useIndexChart)
  utils/marketIndexChart.ts              (신규)
  pages/MarketAnalysisPage/IndexYtdChart.tsx (신규)
  pages/MarketAnalysisPage/DashboardTab.tsx  (수정: 카드)
  + 테스트·MSW 핸들러
```

### 11.2 Implementation Order

1. [ ] domain 규칙 + 테스트 (Red→Green)
2. [ ] V102 + 모델 + 저장소 + 테스트
3. [ ] 서비스 + 테스트 (가짜 store·tools)
4. [ ] DI·라우터 + API 테스트, 격리 계약 회귀
5. [ ] 프론트 타입·상수·서비스·훅·util + 테스트
6. [ ] 차트·카드 + 컴포넌트 테스트
7. [ ] 로컬 V102 적용, 실데이터 E2E (§8.3)

### 11.3 Session Guide

#### Module Map

| Module | Scope Key | Description | Estimated |
|--------|-----------|-------------|:---------:|
| 백엔드 데이터 | `module-1` | domain `index_chart.py` + V102 + 모델 + `IndexDailyRepository` + 테스트 | ~300줄 |
| 백엔드 서비스·API | `module-2` | `IndexChartService` + 포트 + DI + 라우터 + 테스트 | ~400줄 |
| 프론트 | `module-3` | 타입·서비스·훅·util·`IndexYtdChart`·카드 + 테스트 | ~450줄 |
| 실측 | `module-4` | 로컬 V102 적용, 실데이터 E2E·화면 폭 확인 | — |

#### Recommended Session Plan

| Session | Scope | 비고 |
|---------|-------|------|
| 1 | `--scope module-1,module-2` | 백엔드 완료 후 TestClient 로 응답 형태 확인 |
| 2 | `--scope module-3` | 응답 형태를 프론트 타입으로 |
| 3 | `--scope module-4` | 서버는 사용자가 기동, 브라우저만 조작 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.2 | 2026-11-27 | Check 반영 — `STORE_FAILED`·실패 캐시·설정 읽기 실패 처리 기록, 화면: 빠진 지수 안내(G-I1)·저장 기준일은 마지막 확정 점(G-M6)·범례 선언 순서 | 배상규 |
| 0.1 | 2026-11-27 | 초안 — 설계안 C 선택, 구간 183일·TTL 300초·source_status 3단계 확정 | 배상규 |
