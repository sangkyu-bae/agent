# market-index-ytd-chart 갭 분석 (PDCA Check)

> **요약**: 설계(Option C)대로 구현됐고 Success Criteria 6개를 모두 실데이터로 확인했다. Important 갭은 1건이다. 두 지수 중 한쪽에만 데이터가 있으면 화면에 안내 문구가 나오지 않는다.
>
> **대상**: worktree `../wt/market-index-ytd-chart` (미커밋)
> **Plan**: `docs/01-plan/features/market-index-ytd-chart.plan.md` v0.1
> **Design**: `docs/02-design/features/market-index-ytd-chart.design.md` v0.1 (Option C)
> **분석일**: 2026-11-27 · **분석**: gap-detector (주 세션이 저장, 백엔드 ruff 항목은 주 세션 실행 기록으로 보정)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 리포트·매수 판단을 해석할 올해 시장 흐름 기준이 화면에 없다 |
| **WHO** | 시장 분석 열람 권한자(MARKET_ANALYSIS_VIEW) |
| **RISK** | KIS 한 번 호출 200봉 상한·호출 한도, 첫 조회 백필 지연, 동시 조회 중복 적재 |
| **SUCCESS** | 테이블이 비어 있어도 첫 조회에 연초~최근 확정 봉이 채워지고, 캐시 시간 안의 재조회는 KIS를 부르지 않는다 |
| **SCOPE** | 백엔드(V102·적재·API) → 프론트(대시보드 카드·차트·체제 점) |

---

## 1. 요약

| 항목 | 점수 |
|------|:----:|
| Structural Match | 100% |
| Functional Depth | 95% |
| API Contract (Design §4.2 ↔ 라우터 ↔ 프론트) | 100% |
| Architecture Compliance | 100% |
| Convention Compliance | 98% |
| Intent Match | 95% |
| Behavioral Completeness | 92% |
| UX Fidelity | 90% |
| Runtime | 95% |

```
Overall = Structural 100×0.10 + Functional 95×0.15 + Contract 100×0.15
        + Intent 95×0.20 + Behavioral 92×0.15 + UX 90×0.10 + Runtime 95×0.15
        = 95.3%
```

**Overall Match Rate 95.3%** (기준 90% 통과) · 갭: Critical 0, Important 1, Minor 6

---

## 2. Success Criteria

| SC | 내용 | 상태 | 근거 |
|----|------|:----:|------|
| SC-1 | 빈 테이블 첫 조회로 연초~최근 확정 봉 적재·차트 표시 | ✅ | `application/market_analysis/index_chart.py` tail_range→split_ranges→KIS→upsert. 테스트 `test_index_chart_service.py` 2구간·limit 200. 실측 KIS 4회(122+100봉), 지수당 221행 |
| SC-2 | TTL 5분 안 재조회 KIS 0회, 마감 뒤 오늘 봉 저장되면 더 부르지 않음 | ✅ | TTL 캐시·tail_range None. 테스트 2건. 실측 0회 86ms |
| SC-3 | 첫 점 0%, 이후 종가 계산값과 일치 | ✅ | `domain/market_analysis/index_chart.py` ytd_points(Decimal, ROUND_HALF_UP). 실측 444점 일치 |
| SC-4 | 장중 점은 미확정 표시, 테이블 미저장 | ✅ | 저장소 확정 봉만 저장, 서비스 캐시에서만 붙임, 화면 "(MM/DD 미확정)". 실측 미저장 |
| SC-5 | KIS 꺼져도 저장분으로 차트 + 안내 | ✅ | stale 판정·안내 문구. 실측은 KIS 실패를 프로세스 안에서 흉내 냄(컨테이너 무접촉) |
| SC-6 | 체제 기록일에 점 | ✅ | 저장소 regimes, `RegimeDot`, 툴팁 "시장 체제: 강한 하락" 브라우저 확인 |

**품질 기준 (Plan §4.2)**

| 항목 | 상태 | 비고 |
|------|:----:|------|
| 신규 application/domain 커버리지 80% 이상 | ⚠️ | 측정 기록 없음 |
| ruff·eslint·type-check 신규 오류 0 | ✅ | 백엔드 ruff(신규·수정 파일) All checks passed, 프론트 type-check·eslint 통과 |
| 375·768·1440 폭 넘침 없음 | ⚠️ | 768·375(사이드바 접힘) 확인, 1440은 1536 창에서만 확인 |

---

## 3. FR 충족

| ID | 상태 | 근거 |
|----|:----:|------|
| FR-01 테이블·PK·덮어쓰기 | ✅ | V102, `MaIndexDailyModel`, 저장소 `session.get` 후 add/setattr |
| FR-02 꼬리 구간 | ✅* | 구간 끝은 Plan "어제"가 아니라 Design §2.2 "오늘"(장중 봉 확보). Plan 문구 미갱신(G-M1) |
| FR-03 200봉 이하 분할 | ✅ | 183일·limit 200 |
| FR-04 장중 봉 미저장 | ✅ | 저장소·서비스 |
| FR-05 점 필드 | ✅ | date·close·rate·provisional |
| FR-06 체제 포함 | ✅ | `regimes` |
| FR-07 source_status | ✅ | NOT_CONFIGURED·is_error·나쁜 쪽 상태 |
| FR-08 KIS 재호출 없음 | ✅ | tail_range None, 장중엔 TTL마다 하루 구간(Design §2.2 의도) |
| FR-09 동시 조회 | ✅ | asyncio.Lock + 덮어쓰기, gather 테스트 |
| FR-10 % 겹침·툴팁 | ✅ | `IndexYtdChart.tsx`, `describeIndexRow` |
| FR-11 체제 점·라벨 | ✅ | `RegimeDot` |
| FR-12 미확정·빈 상태·안내 | ⚠️ | 일부 데이터 + unavailable 안내 누락(G-I1) |

비기능: 조회 86ms(<300ms) ✅, 백필 지수당 2회 ✅, VIEW 403 ✅, 모듈 격리 ✅, 접근성 ✅.

---

## 4. 구조·기능·계약

- **구조**: Design §11.1 파일 전부 존재. 백엔드 신규 4·수정 4로 Option C 표와 일치. `parts.tsx` `Card.label` prop은 Design에 없던 추가(선택 prop, 기존 호출 영향 없음).
- **기능 깊이**: 미완성 흔적 없음. 서비스의 설정 읽기 예외 미처리(G-M3), `IndexYtdCard` 분기 누락(G-I1).
- **API 계약**: `GET /api/v1/market-analysis/index-chart` 1건 3방향 일치 100%. year·series(두 키 항상)·base_date/base_close(null 가능)·points·regimes·source_status union·source_error·as_of. MSW 픽스처와 백엔드 테스트 픽스처 형태 같음.
- **아키텍처·규약**: domain 표준 라이브러리만, application은 ports·domain만, infra는 domain·models만 import. Design Ref 독스트링, Decimal 계산 후 직렬화 시 float, KST 변환 재사용, `as const`는 types에만, 색은 토큰 변수만.

---

## 5. UI 체크리스트 (Design §5.4)

13개 중 충족 11, 부분 2 (92%).

- 부분 #9 `unavailable` 문구: 행이 0개일 때만 나온다(G-I1).
- 부분 #13 폭: 1440 정확 폭 미확인.
- 알려진 작은 문제: 범례 순서 KOSDAQ→KOSPI(요약 줄과 반대), 좁은 폭에서 차트-범례 간격 넓음(기존 `EquityChart`도 같음).

---

## 6. Gap 목록

### 6.1 Critical
없음.

### 6.2 Important

**G-I1. 한쪽 지수만 데이터가 있고 응답이 `unavailable`이면 안내 문구가 없다 (신뢰도 85%)**

- 서버는 지수별 상태 중 나쁜 쪽을 응답 상태로 쓴다. KOSPI는 저장분 있음(stale)·KOSDAQ은 없음(unavailable)이면 응답은 `unavailable`이다(서비스 테스트 `test_not_configured_does_not_call_kis` 후반부가 이 경우를 확인).
- 화면은 행이 0개일 때만 unavailable 문구를 보이고, 행이 있으면 `stale`일 때만 안내한다. 결과적으로 한쪽 선만 있는 차트가 설명 없이 나온다.
- 발생: 첫 백필에서 한 지수 호출만 `RATE_LIMITED`·`SERVER_UNAVAILABLE`로 실패할 때. 실패도 TTL 동안 캐시되어 5분 유지된다.
- 수정: `IndexYtdCard`에서 행이 있고 `source_status !== 'ok'`면 안내, 점 0개 지수는 이름을 밝혀 알림. 화면 테스트 1건 추가. 백엔드 변경 없음.

### 6.3 Minor

| ID | 내용 |
|----|------|
| G-M1 | Plan FR-02·FR-08·SUCCESS의 "어제" → Design 기준 "오늘(확정 봉만 저장)"으로 문구 갱신 필요 |
| G-M2 | Plan §5 휴장일 대응 문구가 "마지막 확인일 기록"으로 남음. 실제는 TTL 방식(5분마다 하루 구간 1회) |
| G-M3 | `chart()`의 설정 읽기 예외를 잡지 않아 설정 DB 실패 시 500 |
| G-M4 | `IndexYtdCard`가 대시보드 조회 성공 뒤 그려져 차트 요청이 늦게 나가고, 대시보드 실패 시 카드도 안 보임 |
| G-M5 | 로딩 상태 화면 테스트 없음 |
| G-M6 | stale인데 한쪽에 장중 봉이 있으면 "MM/DD까지의 저장 데이터"에 오늘 날짜가 들어감 |

### 6.4 Design에 없던 추가

- 오류 코드 `STORE_FAILED` → Design §4.2 목록에 추가 권장
- 실패 결과도 TTL 동안 캐시 → Design §2.2에 기록 권장
- 표시용 순수 함수 `latestIndexPoint`·`describeIndexRow`·`formatMonthDay`
- `Card.label` prop

---

## 7. 결정 기록 준수

데이터 원천(일봉 테이블)·적재 시점(조회 시 꼬리)·장중 봉(응답에만)·표시(% 겹침)·체제(있는 날만 점)·기간(YTD)·별도 엔드포인트·recharts·백엔드 결정론 계산·Option C·183일/300초/3단계 상태·Lock+덮어쓰기·기존 구조 불변 — 모두 준수. 벗어난 곳 없음. Plan 문구 2곳(G-M1·G-M2)만 Design 갱신이 반영되지 않았다.

---

## 8. 권고

1. **G-I1 수정** (Important): 카드 안내 분기 + 화면 테스트 1건.
2. **문서 갱신**: Plan G-M1·G-M2, Design §4.2 `STORE_FAILED`·§2.2 실패 캐시.
3. **선택**: G-M3 설정 읽기 예외 처리, G-M5 로딩 테스트, 범례 순서 맞춤.
4. **남은 확인**: 1440 정확 폭, 커버리지 수치.
5. **Report**에 배포 체크리스트 "V100·V101 다음 V102" 포함.

---

## 9. Act-1 (2026-11-27, 사용자 선택: 지금 모두 수정)

| Gap | 처리 | 근거 |
|-----|------|------|
| G-I1 | ✅ 수정 | `IndexYtdCard`가 점 0개 지수를 "KOSDAQ 시세를 받지 못했습니다. 잠시 후 다시 확인하세요."로 밝힘. 화면 테스트 추가 |
| G-M6 | ✅ 수정 | 저장 데이터 기준일을 마지막 확정 점(`lastConfirmedDate`)으로. stale 테스트 기대값 11/27→11/26, util 테스트 추가 |
| G-M3 | ✅ 수정 | `chart()`가 설정 읽기 실패를 잡아 KIS 호출 없이 저장분 + `STORE_FAILED`. 서비스 테스트 추가 |
| G-M5 | ✅ 수정 | 로딩 문구 화면 테스트 추가 |
| 범례 순서 | ✅ 수정 | recharts Legend 기본 `itemSorter: "value"`(이름순) → `itemSorter={null}`로 선언 순서 KOSPI→KOSDAQ. jsdom이 범례를 그리지 않아 화면 확인은 남음 |
| G-M1·G-M2 | ✅ 문서 | Plan v0.2 — 구간 끝 "오늘(확정 봉만 저장)", 휴장일 TTL 방식 |
| §6.4 추가분 | ✅ 문서 | Design v0.2 — `STORE_FAILED`, 실패 결과 TTL 캐시, 설정 읽기 실패, 화면 체크리스트 3줄 |
| G-M4 | ⏭ 이월 | 차트 카드가 대시보드 조회 뒤에 그려지는 순서. 이번 수정 범위에 넣지 않음 |

검증: 백엔드 market_analysis 회귀 395 통과(+1), ruff 통과. 프론트 시장 분석 화면·util·훅 40 통과, type-check·eslint 통과.

수정 뒤 Match Rate(추정): Behavioral 92→98, UX 90→95, Intent 95→97 → **약 97.7%**.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.2 | 2026-11-27 | Act-1 — G-I1·G-M3·G-M5·G-M6·범례 순서 수정, Plan·Design 문구 갱신, G-M4 이월 | 주 세션 |
| 0.1 | 2026-11-27 | 첫 Check. Match Rate 95.3%, Important 1건 | gap-detector (주 세션 저장·ruff 항목 보정) |
