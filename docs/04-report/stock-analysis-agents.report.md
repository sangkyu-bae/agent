# stock-analysis-agents Completion Report

> **Status**: Complete
>
> **Project**: sangplusbot (idt + idt_front) · 연동 agent_mcp
> **Author**: 배상규
> **Completion Date**: 2026-11-26
> **PDCA Cycle**: Plan → Design(v1.3) → Do(module-1~10) → Check(94.6%) → Act-1·Act-2

---

## Executive Summary

### 1.1 Project Overview

| Item | Content |
|------|---------|
| Feature | stock-analysis-agents — KIS 신호 → 종목별 다중 에이전트 리포트 → 매수·매도 판단 → 10슬롯 가상 계좌 → 청산 저널·원칙 |
| Start Date | 2026-11-26 |
| End Date | 2026-11-26 |
| 범위 | 국내(KRX). 실제 주문 없음(D1). 독립 모듈 `market_analysis` + `ma_*` 테이블(D8) |

### 1.2 Results Summary

```
┌──────────────────────────────────────────────┐
│  Match Rate: 94.6% (실측 포함) / 정적 96.2%   │
├──────────────────────────────────────────────┤
│  ✅ 기능 요구 FR-01~17:   17 / 17             │
│  ✅ Success Criteria:      8 / 8              │
│  ✅ Critical Gap:          0                   │
│  ⏳ 후속 기록 Minor:       7 (G3~G9)           │
└──────────────────────────────────────────────┘
```

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | KIS 서버는 신호를 사실로만 돌려준다. 신호가 난 종목을 분석하고, 매수 여부를 판단하고, 그 판단이 맞았는지 추적하는 단계와 결과를 볼 화면이 없었다. |
| **Solution** | 회차(장중·마감)가 후보 수집 → 신호 스캔 → 종목별 6섹션·전략·요약 리포트 → 매수 판단(LLM 점수 + 결정론 게이트) → 가상 계좌 → 보유 종목 결정론 청산·매도 판단 → 청산 저널·원칙 후보 순서를 코드로 고정했다. 각 단계의 글과 점수는 Agent Builder 에이전트 11개가 만들고, 운영자가 빌더에서 지침을 바꾼다. |
| **Function/UX Effect** | 실데이터 회차 1회(17시대)에서 후보 → 신호 → 5종목 리포트(섹션 6/6) → 판단 5건(진입 1·보류 4, 사유 기록) → 보유·성과 반영까지 한 번에 끝났다. 테스트 보유 종목은 손절가 도달 시 청산되고 저널·원칙 후보 4개가 생겼다. 권한 있는 사용자는 '시장 분석' 메뉴 8탭에서 결과를 보고, 운영자는 스위치 하나로 자동 분석을 끈다(꺼진 회차는 LLM 0회). |
| **Core Value** | 에이전트가 리서치 업무(신호 확인 → 리포트 → 판단 → 사후 복기)를 끝까지 수행하고, 리포트 수치 973개 중 근거 없는 수치는 0개였다. 판단과 결과가 근거·비용(종목당 약 $0.21)과 함께 남는다. |

---

## 1.4 Success Criteria Final Status

| # | Criteria | Status | Evidence |
|---|---------|:------:|----------|
| SC-1 | 마감 후 회차 1회에서 신호 종목 → 리포트 → 판단 → 계좌 반영(상한 초과분은 미분석) | ✅ Met | 설계서 §7.8 E1 — 회차 #4: 분석 5, over_cap 24, duplicate 3, 진입 1(HC홈센타 8점), 보류 4 |
| SC-2 | 스위치 off → 다음 회차 건너뜀, LLM 0회 | ✅ Met | E2 — 회차 #3 `skipped(DISABLED)`, 구간 ai_run 0 |
| SC-3 | 표본 리포트 수치가 도구 결과와 일치(불일치 0), 없는 항목은 공란 | ✅ Met | E3(리포트 5건 973 수치): 근거 없는 수치 0, 계산식 4/44 소오차 → Act-2 G1(재무 증감 코드 계산) → **재실측 회차 #7 리포트 #12: 수치 222 = 근거 원문 182 + 코드 계산값과 일치하는 증감 39 + 대략 구간 1, 계산식 13 오차 0** |
| SC-4 | 보유 종목 손절·목표 도달 → 청산·거래·성과·저널 | ✅ Met | E4 — `[E2E]` 보유 stop 청산 -3.85%, 매도 판단, 성과 스냅샷, 저널 1, 원칙 후보 4 |
| SC-5 | 활성 원칙이 다음 매수 판단 입력에 들어감 | ✅ Met | E5 — 판단 3건 `principles_used=[4]` |
| SC-6 | 권한 없음 → 메뉴 없음·API 403 | ✅ Met | E6 — 403 `MA_FORBIDDEN`, 메뉴 `can_view` 조건 |
| SC-7 | 빌더에서 섹션 지침 변경 → 다음 분석 반영(코드 수정 없음) | ✅ Met | E7 — 리포트 5건 기술 섹션 모두 표식 문장 포함 |
| SC-8 | `market_analysis` 의존 방향 테스트 통과 | ✅ Met | `tests/contracts/test_market_analysis_isolation.py` I1~I6, 전체 회귀에서 통과 |

**Success Rate**: 8/8 met (100%) — SC-3 은 Act-2 후 재실측으로 충족

## 1.5 Decision Record Summary

| Source | Decision | Followed? | Outcome |
|--------|----------|:---------:|---------|
| [Plan] D1 | 리포트 + 가상 계좌만, KIS 주문 없음 | ✅ | 주문 도구는 허용 목록 밖, 기본 에이전트 미부착(테스트) |
| [Plan] D2·D8 | sangplusbot 안 새 메뉴, 독립 모듈 `market_analysis` + `ma_` 테이블 | ✅ | 포트로만 플랫폼과 연결, 격리 계약 테스트 I1~I6 통과 |
| [Plan] D3 | 순서는 코드, 내용은 빌더 에이전트 | ✅ | E7 — 지침만 바꿔 다음 분석에 반영 |
| [Plan] D4 | KIS + DART + 뉴스 + 웹 리서치 | ✅ | mcp-dart-server·mcp-perplexity-server 신설, KIS `get_index_history`·`group` 추가 |
| [Plan] D5 | 권한 부여자만 열람 + 면책 | ✅ | `MARKET_ANALYSIS_VIEW/MANAGE`, 모든 탭 면책 띠 |
| [Plan] D6 | 신호 종목 전부 분석 + on/off + 상한 | ✅ | 상한 초과는 `over_cap` 으로 남김, 스위치 off 는 LLM 0 |
| [Plan] D7 | 저널·원칙 1차 포함 | ✅ | 청산 → 저널 → 원칙 후보(기본 비활성, DD9) → 켜면 판단 입력 |
| [Design] 설계안 C | 실용 균형 — 포트 4개 + 코어 opt-in 1개(`reference_context`) | ✅ | 코어 변경은 opt-in 필드와 권한 코드뿐. HTTP 로는 못 넣게 막음(C1) |
| [Design] DD | 진입·청산은 결정론, LLM 숫자는 입력일 뿐 | ✅ | 게이트가 판단 시점 시세로 손익비·손절폭 재계산 |
| [Design] §1.1-5 | 근거 없는 숫자 금지 | ✅ (보강) | 근거 없는 수치 0. 계산값도 코드가 만들도록 보강(Act-2 G1) |

---

## 2. Related Documents

| Phase | Document | Status |
|-------|----------|--------|
| Plan | [stock-analysis-agents.plan.md](../01-plan/features/stock-analysis-agents.plan.md) | ✅ |
| Design | [stock-analysis-agents.design.md](../02-design/features/stock-analysis-agents.design.md) v1.3 | ✅ (§7.1~§7.9 구현·실측·Check 기록) |
| Check | [stock-analysis-agents.analysis.md](../03-analysis/stock-analysis-agents.analysis.md) | ✅ (중간 §1~10, 최종 §11, Act-2 §12) |
| Act | 현재 문서 | ✅ |

---

## 3. Completed Items

### 3.1 Functional Requirements

| ID | Requirement | Status | Notes |
|----|-------------|--------|-------|
| FR-01 | 자동 분석 스위치, 꺼지면 건너뜀 | ✅ | E2 |
| FR-02 | 회차·하루·동시 상한, 초과는 미분석 기록 | ✅ | `over_cap` |
| FR-03 | 회차 시각 설정, 장중 미확정 표시 | ✅ | `provisional` |
| FR-04 | 후보 → scan → 신호 종목, 같은 날 1회, 보유는 매도 판단으로 | ✅ | `duplicate`, 주식류만(ETF·ETN·스팩 제외, §7.7) |
| FR-05 | prefetch → 6섹션 → 전략 → 요약 | ✅ | |
| FR-06 | 역할 ↔ 빌더 에이전트 매핑, 기본 에이전트 생성 | ✅ | `POST /bootstrap-agents` |
| FR-07 | 리포트 본문·근거·신호·시점·확정 여부·토큰 저장, 근거 없는 수치 금지 | ✅ | E3 근거 없는 수치 0 |
| FR-08 | 매수 판단 구조화 + 결정론 게이트 | ✅ | |
| FR-09 | 10슬롯 가상 계좌, KIS 시세 기록, 실현 수익만 누적 | ✅ | |
| FR-10 | 보유 결정론 청산 + 매도 판단 | ✅ | E4 |
| FR-11 | 시장 체제 결정론 계산·저장 | ✅ | KOSPI 80봉 |
| FR-12 | 저널·원칙 후보·활성 원칙 주입·토글 | ✅ | E5 |
| FR-13 | 화면 8탭 | ✅ | 보유 탭 현재가·평가 수익률(사용자 결정) |
| FR-14 | 면책 문구 | ✅ | |
| FR-15 | VIEW/MANAGE 권한 | ✅ | E6 |
| FR-16 | DART MCP 서버 | ✅ | find_corp·get_financials·list_disclosures |
| FR-17 | 회차·종목 실행 기록, 실행 현황 화면 | ✅ | 실패 사유 `KIS_UNAVAILABLE`·`SCAN_FAILED` 구분 |

### 3.2 Non-Functional Requirements

| Item | Target | Achieved | Status |
|------|--------|----------|--------|
| 분리 가능성 | 포트만 사용, AST 테스트 | 격리 계약 I1~I6 통과 | ✅ |
| 비용 | 종목당 기록, 회차 실측 | 종목당 약 6만 토큰·약 $0.21(gpt-5.1), 회차 3·일 50 기본이면 일 최대 약 $10.5 | ✅ |
| 정확성 | 수치 = 도구 결과 | 근거 없는 수치 0, 증감 계산 오차 4/44 → 코드 계산 후 0/13 | ✅ |
| 안정성 | 종목 실패가 회차를 멈추지 않음 | 종목·섹션 단위 실패 격리, KIS 치명 오류는 회차 failed | ✅ |
| 동시성 | 겹치면 뒤 회차 건너뜀 | `skipped(BUSY)`, 재시작 시 running 회수 | ✅ |
| 보안 | 주문 도구 권한 없음 | 허용 목록·미부착 테스트 | ✅ |

### 3.3 Deliverables

| Deliverable | Location | Status |
|-------------|----------|--------|
| DB | `idt/db/migration/V100`(테이블 13)·`V101`(권한) — 로컬 적용 | ✅ |
| 백엔드 모듈 | `idt/src/{domain,application,infrastructure}/market_analysis/`, `api/market_analysis_di.py`, `api/routes/market_analysis_router.py`(라우트 18) | ✅ |
| 프론트 | `idt_front/src/pages/MarketAnalysisPage/*`(8탭), types·services·hooks·utils, 사이드바 메뉴 | ✅ |
| agent_mcp | KIS `get_index_history`·`group`, mcp-dart-server, mcp-perplexity-server (별도 저장소, 미커밋) | ✅ |
| 테스트 | 시장 분석 백엔드 342, 프론트 시장 분석 28, 격리 계약 | ✅ |
| 문서 | Plan, Design v1.3, Analysis, 이 보고서 | ✅ |

---

## 4. Incomplete Items

### 4.1 Carried Over

| Item | Reason | Priority |
|------|--------|----------|
| G3 리포트 머리 사실에 신호 값 표시 | Minor, 기록만(사용자 결정) | Low |
| G4 탭·상세를 URL 로 | Minor | Low |
| G5 U5 체제 경계값 테스트 | Minor | Low |
| G6 판단 파서 NaN·Infinity | Minor | Medium |
| G7 server_finder 예외를 값으로 | Minor | Low |
| G8 failed 재시도를 하루 상한에 포함 | Minor (비용 상한 관련) | Medium |
| G9 PUT /settings enabled 기본값 | Minor (꺼지는 쪽이라 안전) | Low |
| 거래량 순위가 ETF 위주(30 중 주식 6) | KIS 순위 제외 조건 스펙 미확인 | Medium |
| 수급 거래대금 단위 명시 | "-55억 단위 추정" 같은 추정 표현 1건 | Low |
| DART·Perplexity 단독 실왕복 기록 | E1 섹션 6/6 done 으로 간접 확인만 | Low |
| 배포 | 운영 DB 에 V100·V101, MCP 서버 3종 등록·키 | 배포 시 |

### 4.2 Cancelled/On Hold

| Item | Reason | Alternative |
|------|--------|-------------|
| 실제 주문 | D1 범위 밖 | 가상 계좌 |
| 해외 시장 | 국내만 | — |

---

## 5. Quality Metrics

### 5.1 Final Analysis Results

| Metric | Target | Final | Change |
|--------|--------|-------|--------|
| Design Match Rate | 90% | 94.6% (실측 포함), 정적 96.2% | 중간 94.3% → |
| Critical Gap | 0 | 0 | 중간 C1 해결 |
| 백엔드 전체 회귀 | 기준선 61 실패 유지 | 61 failed / 13,803 passed (같은 파일, 수정 영역 0) | ✅ |
| 프론트 전체 회귀 | 기준선 10 실패 유지 | 10 failed / 2,249 passed (같은 5 파일) | ✅ |
| 보안 | 주문 도구 차단 | 허용 목록·미부착 | ✅ |

### 5.2 Resolved Issues

| Issue | Resolution | Result |
|-------|------------|--------|
| C1 `reference_context` 가 HTTP 로 들어옴 | `RunAgentHttpRequest` 로 본문에서 버림 | ✅ |
| I1 KIS 장애인데 회차 done 0건 | `failed(KIS_UNAVAILABLE)` | ✅ |
| I2 리포트가 running 으로 남음 | 실패 확정·참고 자료 상한·재시작 회수 | ✅ |
| 스캔 전부 실패가 "신호 0건" 으로 보임 | `failed(SCAN_FAILED)` | ✅ |
| ETF·ETN 이 후보에 섞임 | KIS `group` + `EquityPolicy` | ✅ (30 중 ETF 22·ETN 2 제외) |
| 화면 저장 결과 문구가 사라짐 | mutation 을 부모로 | ✅ (실화면 확인) |
| **코어** 단가 PATCH 가 저장 안 됨 | `LlmModelRepository.update()` 단가 3필드 | ✅ |
| **코어** 스냅샷 모델명(gpt-5.1-2025-11-13) 매핑 실패 → 비용 0 | `ModelNameResolver` 날짜 꼬리 대체 | ✅ (재실측: 실행 모두 비용 기록) |
| **코어** MCP 설명 상한 2,000 | 10,000 | ✅ KIS 원문 2,534자 등록 |
| G1 재무 증감 LLM 계산 오차 | 코드 계산 블록 | ✅ (재실측 오차 0) |
| G2 건너뜀 사유 원래 코드 노출 | 라벨 키 = 서버 값 | ✅ |

---

## 6. Lessons Learned & Retrospective

### 6.1 What Went Well (Keep)

- **순서는 코드, 내용은 에이전트**: 지침만 바꿔 다음 분석에 반영(E7)되고, 진입·청산은 결정론이라 재현된다.
- **실측이 결함을 찾는다**: 단위 테스트가 모두 통과한 상태에서 실화면·실회차가 ETF 혼입, 스캔 전부 실패 은폐, 문구 사라짐, 코어 비용 0(결함 2건 중첩)을 드러냈다.
- **수치 대조를 자동화**: 973개 수치를 근거·계산·구간으로 분류하고 계산식을 다시 계산해, "근거 없는 수치 0"과 "계산 오차 4"를 분리해 볼 수 있었다.

### 6.2 What Needs Improvement (Problem)

- **목 데이터가 서버 값과 달라 테스트가 결함을 가렸다**(G2 소문자 `'holiday'`). 목은 서버 enum 값에서 가져와야 한다.
- **API 200 응답만 보고 저장됐다고 믿었다**(단가 PATCH). 쓰기 확인은 DB 를 다시 읽어야 한다.
- **LLM 에게 산술을 맡겼다**: 근거 블록에 원값만 주면 증감률을 직접 계산하다 틀린다.
- 오래 걸리는 대기(18:10)와 짧은 JWT 만료가 겹쳐 대기 스크립트가 한 번 멈췄다.

### 6.3 What to Try Next (Try)

- 파생 수치(증감·비율·이평 괴리)는 처음부터 근거 블록에서 코드로 계산해 넘긴다.
- 프론트 목의 enum 값은 서버 스키마와 같은 상수에서 만든다(계약 테스트 후보).
- 쓰기 API 실측은 "응답 → DB 재조회" 2단계로 확인한다.

---

## 7. Process Improvement Suggestions

### 7.1 PDCA Process

| Phase | Current | Suggestion |
|-------|---------|------------|
| Do | module 마다 단위 테스트 통과로 마감 | 화면·외부 연동 모듈은 실데이터 1회 확인을 마감 조건에 포함 |
| Check | 설계서 절 번호가 구현 중 바뀜 | 구현 결과 절(§7.x)을 계속 쌓되 Check 때 원래 절에 안내를 다는 방식 유지(§7.9) |

### 7.2 Tools/Environment

| Area | Suggestion |
|------|------------|
| 실측 스크립트 | 토큰 재발급을 대기 스크립트 안에서 처리 |
| 비용 | 모델 등록 시 스냅샷명 별칭을 함께 확인 |

---

## 8. Next Steps

### 8.1 Immediate

- [x] 작은 회차로 SC-3 재실측(회차 #7, 오차 0) + gpt-5.1 비용 기록 확인(실행 9건 모두 단가 적용, 리포트 1건 $0.214)
- [ ] 커밋·PR (idt·idt_front, worktree `../wt/stock-analysis-agents`). agent_mcp 변경은 별도 처리
- [ ] `/bkit:pdca archive stock-analysis-agents`
- [ ] 배포 시 운영 DB V100·V101, MCP 서버 3종(KIS 재빌드·DART·Perplexity) 등록

### 8.2 Next PDCA Cycle 후보

| Item | Priority |
|------|----------|
| Minor G6·G8 (파서 안전성, 하루 비용 상한) | Medium |
| 거래량 순위 주식 비중 개선(KIS 제외 조건) | Medium |
| G3·G4 화면 보강 | Low |

---

## 9. Changelog

### v1.0.0 (2026-11-26)

**Added:**
- 시장 분석 모듈(`market_analysis`): 회차 스케줄러·후보 수집·신호 스캔·6섹션 리포트·매수/매도 판단·10슬롯 가상 계좌·저널·원칙
- `/api/v1/market-analysis/*` 18개, 화면 '시장 분석' 8탭
- agent_mcp: KIS `get_index_history`·`group`, mcp-dart-server, mcp-perplexity-server

**Changed:**
- `RunAgentRequest.reference_context`(내부 호출자 opt-in), HTTP 본문은 `RunAgentHttpRequest` 로 차단
- MCP 설명 상한 2,000 → 10,000

**Fixed:**
- LLM 단가 PATCH 미저장, 스냅샷 모델명 매핑 실패로 비용 0

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-11-26 | Completion report | 배상규 |
