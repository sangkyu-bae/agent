---
title: 시장 분석 모듈(market_analysis) 개요 — 회차 순서·격리 경계·결정론 게이트·비용 상한
status: approved
source_type: conversation
source_refs:
  - docs/archive/2026-11/stock-analysis-agents/stock-analysis-agents.report.md (§1.5 결정, §4.1 이월, §5.2 해결, §6 교훈)
  - 커밋 5dd9a6b · f86a641 (PR #137 — 모듈·화면), 34fdf6e (reference_context opt-in)
  - 커밋 61efbe8 (G6 NaN·Infinity), 78e42c7 (G8 failed 재시도 예산), 437b310 (보통주만) — PR #139·#140
  - idt/src/api/market_analysis_di.py (조립 단일 지점, MARKET_ANALYSIS_ENABLED·TICKER_ENABLED)
  - idt/src/application/market_analysis/round_runner.py · scheduler.py · pipeline.py · evidence.py · judgement.py · positions.py · verdict_parser.py · ports.py
  - idt/src/domain/market_analysis/round.py (RoundCapPolicy, EquityPolicy, is_preferred_code)
  - idt/src/infrastructure/market_analysis/ticker.py (모듈 자체 틱 루프 — DD6)
  - idt/src/application/agent_builder/schemas.py (reference_context 내부 전용, HTTP 본문에서 버림)
  - idt/tests/contracts/test_market_analysis_isolation.py (I1~I6)
  - idt/db/migration/V100__create_market_analysis_tables.sql · V101__seed_market_analysis_permissions.sql
confidence: 0.8
version: 1
created: 2026-11-27
updated: 2026-11-27
verified_at: bcf64b0
reviewer: 배상규
---

# 시장 분석 모듈(market_analysis) 개요

> 읽는 시점: **시장 분석(주식 신호 → 리포트 → 매수·매도 판단 → 가상 계좌) 코드를 처음 고칠 때,
> 회차가 건너뛰어지거나 종목이 후보에서 빠지는 이유를 추적할 때, 분석 비용 상한을 바꿀 때,
> 또는 코어 기능을 "내부 호출자만" 쓰게 열어야 할 때.**

## 문제

KIS MCP 서버는 신호를 사실로만 돌려준다. 신호 종목을 분석하고 판단하고 그 판단이 맞았는지
추적하는 단계는 플랫폼 밖 요구였고, 여신·금융 특화 로직을 코어에 넣지 않는다는 원칙
(`USER-SCENARIOS.md` — 일반화 우선)과 충돌하지 않게 붙여야 했다. 실제 주문은 범위 밖(D1)이다.

## 검증된 사실

### 1. 순서는 코드, 글은 빌더 에이전트 (D3)

회차 1회 순서(`round_runner.py`):

```
① 시장 체제(KOSPI·KOSDAQ, 결정론) — 평일 09:10 이후 오늘 KOSPI 봉이 없으면 skipped(HOLIDAY)
② 보유 관리 — 손절·목표 도달은 에이전트 없이 청산, 나머지는 매도 판단 에이전트(hold·sell·adjust)
③ 후보 수집(순위·조건검색) → EquityPolicy로 보통주만
④ 신호 스캔 → ⑤ RoundCapPolicy(상한·중복·보유 분리)
⑥ 종목별 파이프라인: prefetch(LLM 없음, 근거 블록) → 6섹션(동시) → 전략 → 요약 → 매수 판단
⑦ 성과 스냅샷(마감 회차)
```

- 각 단계의 글·점수는 Agent Builder 에이전트 11개가 만든다(`POST /bootstrap-agents`로 기본 생성).
  운영자는 빌더에서 지침만 바꾸면 다음 분석에 반영된다(SC-7 실측). **단계 순서를 바꾸려면 코드를 고쳐야 한다.**
- 판단 역할(buy_judge·sell_judge) 매핑이 없으면 회차가 시작 전에 failed다.

### 2. 진입·청산은 결정론 — LLM 숫자는 입력일 뿐

- 매수 판단 에이전트는 점수·목표가·손절가만 낸다. 진입 여부는 판단 시점 `get_quote` 현재가로
  **게이트가 손익비·손절폭을 다시 계산**한다. 게이트 미통과·보류는 관심종목(`ma_decision` skip + 사유).
- 마지막 슬롯 경쟁: 시세 조회 → 게이트 → 진입 기록은 잠금 안, 에이전트 실행은 잠금 밖.
- 판단 파서(`verdict_parser.py`): 마지막 ```json 블록 → pydantic → 실패 시 보조 LLM 재구조화 1회 →
  그래도 실패면 매수 skip(PARSE_FAILED)·매도 hold. 가격은 **유한수만** 받는다(아래 §5).
- 시세가 없는 보유 종목은 그 회차에 손대지 않는다(0원으로 보지 않는다).

### 3. 격리 경계 — 포트로만 플랫폼과 연결 (D2·D8)

- 조립은 `api/market_analysis_di.py` 한 곳. `main.py`는 `wire/start/close_market_analysis`와
  `_market_analysis_platform`만 안다. 계약 테스트 I1~I6: 코어는 모듈을 import하지 않음(I1),
  main은 DI 모듈만(I2), domain은 표준 라이브러리+자기 패키지만(I3), application은 자기 domain만(I4),
  infrastructure는 application·web을 import하지 않음(I5), 기본값 off(I6).
- `MARKET_ANALYSIS_ENABLED=false`(기본) → 라우터 미등록(404), 플랫폼 의존성도 만들지 않는다.
  `MARKET_ANALYSIS_TICKER_ENABLED=false` → 조회·관리 API는 살고 회차만 안 돈다. 조립 실패는 warning 후 그 부분만 없음.
- 테이블은 `ma_*` 13개(V100), 권한 `MARKET_ANALYSIS_VIEW/MANAGE`(V101). 권한은 role 기본 권한에 넣지 않아
  **부여받은 사용자와 admin만** 메뉴·API가 보인다(그 외 403 `MA_FORBIDDEN`).

### 4. 코어를 "내부 호출자만" 쓰게 여는 방법 — `reference_context` opt-in

- 섹션 본문·근거 블록을 에이전트 입력에 붙이려고 코어 `RunAgentRequest`에
  `reference_context: str | None`(최대 40,000자)을 추가했다. None이면 기존 동작과 같다.
- HTTP 경로(`POST /agents/{id}/run`)는 `RunAgentHttpRequest`가 이 필드를 OpenAPI에서 빼고
  **보내도 버린다**(Check C1 — 처음엔 HTTP로 들어왔다). 이 필드는 프롬프트 가드(`query`만 검사)를
  거치지 않고 마지막 사용자 메시지 뒤에 붙으므로, HTTP로 열리면 **가드 없는 주입 통로**가 된다
  ([[prompt-injection-guard]]). 넘기는 곳은 시장 분석 어댑터뿐이다.
- 일반화: 코어 UseCase에 내부 전용 입력을 열 때는 **내부 DTO 필드 + HTTP DTO에서 제거 + 계약 테스트**
  (`tests/contracts/test_reference_context_callers`, `tests/api/test_run_agent_reference_context_http`) 3종을 같이 둔다.

### 5. 비용·대상 상한 — 실측으로 고친 3건 (PR #139·#140)

| 결함 | 원인 | 지금 규칙 |
|---|---|---|
| G8 하루 상한 초과 | 하루 예산을 "끝났거나 진행 중인 종목 수"로만 셌다. failed 종목은 재시도 가능하므로 계속 실패하면 상한을 넘겨 토큰을 썼다 | 예산 = `max(분석 종목 수, 그 날 done·analyzing·queued·failed 행 수)`. **중복 판정은 그대로**(failed는 재시도 가능) |
| G6 판단 가격 NaN·Infinity | `Decimal("NaN")` 비교는 `InvalidOperation`(ArithmeticError, ValueError 아님)을 내 pydantic이 검증 오류로 못 바꾸고 판단 경로 밖으로 샜다. `Infinity`는 양수라 통과 | 비교 전 `is_finite()` 확인 → 파싱 실패(매수 skip·매도 hold) |
| 후보에 ETF·우선주 혼입 | 거래량 순위 상위가 레버리지·인버스 ETF·ETN(30 중 24) | 한투 증권그룹 `ST`만(리츠 RT·외국주식 FS·DR 제외), 스팩은 이름, **우선주는 6자리 코드 끝자리 ≠ 0**. 그룹을 모르면 확실한 것(7자리 Q 코드 ETN·스팩·우선주)만 빼고 ETF는 이름 목록으로 추측하지 않는다 |

- 회차 상한: 회차당·하루·동시 종목·동시 실행 4개. 넘친 종목은 버리지 않고 `over_cap`으로 남긴다.
  실측 비용은 종목당 약 6만 토큰·약 $0.21(gpt-5.1) — 기본값(회차 20·하루 50)이면 하루 최대 약 $10.5.

### 6. 주기 실행은 모듈 자체 틱 루프 (플랫폼 워커 미사용, DD6)

- [[architecture-overview]] 적용법 6("오래 걸리는 작업·주기 실행은 백그라운드 잡 큐에 편승", [[db-queue-inprocess-worker]])의 **예외**다.
  플랫폼 워커에는 비에이전트 주기 작업 등록 체계가 없어 `MarketAnalysisTicker`(lifespan 태스크, 30초)를 따로 둔다.
  모듈을 떼어낼 때 같이 옮기기 위해서다.
- 다중 인스턴스 1회 실행은 `ma_round` UNIQUE로 보장한다(슬롯마다 회차 행 선점). 스위치 off는 `skipped(DISABLED)`
  기록 후 LLM 0회, 다른 회차 실행 중이면 `skipped(BUSY)`, 기동 시 `recover()`가 running 회차를 abandoned로 회수.

### 7. 리포트 수치 — 근거 블록 원문 + 파생 수치는 코드가 계산

- prefetch가 도구 결과 원문(JSON)을 근거 블록에 싣고, 에이전트 지침은 "근거 블록에 없는 수치 금지".
  실측 973개 수치 중 근거 없는 수치 0.
- 그러나 원값만 주면 LLM이 증감률을 직접 계산하다 틀렸다(44건 중 4건). 재무 증감을 코드가 계산해 근거 블록에
  넣은 뒤(Act-2 G1) 재실측 오차 0. → [[llm-output-trust-boundary]] §6.

## 다음에 적용하는 법

1. 회차가 안 돈다 → 순서대로 `MARKET_ANALYSIS_ENABLED`·`TICKER_ENABLED` → `ma_setting.enabled` →
   `ma_round` 상태(`skipped` 사유 DISABLED·WEEKEND·HOLIDAY·BUSY) → 판단 역할 매핑.
2. 종목이 분석되지 않았다 → `ma_round_item` 상태(`over_cap`·`duplicate`·held)와 EquityPolicy(보통주·ST 그룹) 확인.
3. 상한·예산 로직을 바꿀 때는 **"실패한 시도도 토큰을 썼다"**를 테스트로 유지한다(`test_round_policy.py`).
4. LLM 판단 숫자를 Decimal로 받는 새 파서는 `is_finite()`를 비교 전에 둔다.
5. 이 모듈에 코어 기능이 더 필요하면 §4 방식(내부 opt-in + HTTP 제거 + 계약 테스트)으로 열고, 모듈 쪽은 포트 Protocol을 추가한다.
6. 배포: V100·V101 + MCP 서버 3종(KIS 재빌드·DART·Perplexity) 등록·키 ([[migration-deploy-deps]]).

## 남은 것 (보고서 §4.1 이월)

G3 리포트 머리 사실에 신호 값, G4 탭 URL화, G5 체제 경계값 테스트, G7 server_finder 예외를 값으로,
G9 `PUT /settings` enabled 기본값, 수급 거래대금 단위 명시, DART·Perplexity 단독 실왕복 기록. (G6·G8은 해결)

## 관련 문서

- [[detachable-module-seam]] · [[ast-source-contract-tests]] — 격리·계약 테스트 패턴
- [[architecture-overview]] §2(g) — 코어에서 본 위치
- [[llm-output-trust-boundary]] — 파생 수치·비유한수
