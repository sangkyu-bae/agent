# stock-analysis-agents Planning Document

> **Summary**: mcp-kis-server 신호를 받아 여러 에이전트가 종목 분석 리포트를 쓰고, 매수·매도 판단을 가상 계좌에 기록하고, 청산 결과로 매매 원칙을 쌓는다. 결과는 sangplusbot 안의 전용 화면 묶음에서 보며, 나중에 별도 서비스로 떼어낼 수 있게 독립 모듈로 만든다.
>
> **Project**: sangplusbot (idt + idt_front) · 연동 agent_mcp
> **Author**: 배상규
> **Date**: 2026-11-26
> **Status**: Draft (v0.1)
> **참고 대상**: prism-insight (https://github.com/dragon1086/prism-insight, AGPL-3.0 + 상업 라이선스) · 실사이트 https://analysis.stocksimulation.kr/

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | mcp-kis-server는 시세·지표·신호를 사실로만 돌려주고 판단은 하지 않는다. 신호가 난 종목을 누가 분석하고, 사도 되는지 판단하고, 그 판단이 맞았는지 추적하는 부분이 없다. 결과를 모아 보는 화면도 없다. |
| **Solution** | 신호 수집 잡 → 종목별 다중 에이전트 분석(기술·수급·재무·기업·뉴스·시장 6섹션 + 전략 + 요약) → 매수 판단(점수 + 결정론 게이트) → 10슬롯 가상 계좌 → 보유 종목 매도 판단 → 청산 저널·원칙 축적의 순서를 코드 파이프라인으로 고정한다. 섹션별 에이전트의 지침·모델·도구는 Agent Builder에서 운영자가 바꾼다. |
| **Function/UX Effect** | 권한을 받은 사용자가 '시장 분석' 메뉴에서 대시보드(누적 수익률과 지수 비교), 보유 종목, 거래 내역, 관심종목(보류 사유 포함), 리포트 상세, 매매 원칙을 본다. 운영자는 자동 분석을 한 번에 켜고 끈다. |
| **Core Value** | 에이전트가 사람의 리서치 업무(신호 확인 → 리포트 → 판단 → 사후 복기)를 끝까지 수행하고, 판단과 결과가 모두 근거와 함께 남는다. |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 신호(사실)와 판단 사이의 빈칸을 에이전트가 채우고, 판단의 성과를 추적·복기할 수 있게 한다 |
| **WHO** | 권한 부여자(리포트·계좌 열람), 운영자(자동 분석 on/off, 섹션 에이전트 지침·모델 관리) |
| **RISK** | "신호가 오면 전부 분석"의 LLM 비용 폭주 · 숫자 할루시네이션 · 사내 매매 의견 노출(준법) · AGPL 코드 유입 |
| **SUCCESS** | 장 마감 후 실행 1회에서 신호 종목 전부가 리포트·판단·계좌 반영까지 끝나고, 리포트 숫자가 도구 결과와 일치하며, 스위치를 끄면 다음 회차가 실행되지 않는다 |
| **SCOPE** | 국내(KRX)만. M1 기반 → M2 데이터 소스 → M3 분석 파이프라인 → M4 신호 트리거 → M5 가상 계좌 → M6 저널·원칙 → M7 화면 → M8 실측 |

---

## 1. Overview

### 1.1 Purpose

신호 서버가 의도적으로 남겨 둔 "판단" 층을 sangplusbot에 만든다. 서버 문서(`agent_mcp/mcp-kis-server/docs/signal-comparison-prism-insight.md` §6)는 시장 체제 판정, 종목 점수, 최종 선발, 매수·매도를 **에이전트 몫**으로 정했다. 이번 기능이 그 몫을 맡는다.

### 1.2 Background

**조사로 확인한 사실 (2026-11-26)**

| 대상 | 확인 내용 |
|------|-----------|
| mcp-kis-server | 도구 15종(시세·적재 5, 지표·신호 2, 순위·수급·조건검색 4, 모의 주문·계좌 4). 신호 규칙 7종. 실전 조회 integration은 2026-11-24·25에 국내 30종목으로 확인했다. 장중 봉은 `provisional=true`로 표시되고, 국내 일봉은 18:00에 확정된다. 전 종목 일봉 적재 `collect_daily_snapshot`(18:05 이후 1회)이 등록 설명에 들어 있다. 판단은 하지 않는다 |
| prism-insight 파이프라인 | 트리거 배치 → 종목별 6섹션 리포트(기술·수급·재무·기업·뉴스·시장) → 투자전략 → 핵심 요약 → 매수 에이전트(1~10점, 체제별 최소 점수, 손익비, 손절 −5~−7%) → 10슬롯 계좌 → 매도 판단 → 저널·원칙 → 텔레그램 |
| 실사이트 데이터 (`dashboard_data.json`) | `summary`(포트폴리오·매매·AI 판단) · `holdings`(시나리오·목표가·손절가·손익비·시장 체제) · `trading_history` · `watchlist`(점수, 최소 점수, 결정, **보류 사유**, 밸류에이션, 섹터 전망) · `market_condition`(일자별 지수·체제) · `prism_performance`(누적 수익률) · `holding_decisions`(매도 판단, 확신도, 목표·손절 조정) · `trading_insights`(원칙, 저널, 직관, 트리거 신뢰도, 놓친 기회와 피한 손실) · `operating_costs` |
| sangplusbot 재사용 자산 | Agent Builder(에이전트 지침·모델·MCP 도구), `RunAgentUseCase`, 백그라운드 워커(30초 틱)·스케줄(cron 최소 10분, `skip_when_busy`), MCP 레지스트리·도구 권한, 실행 기록·토큰 비용, `PermissionCode` 권한 체계, 보안 에이전트 선례(MCP + 전용 에이전트 + 스케줄 + 전용 화면 + 켜고 끄기) |
| 플랫폼 제약 | supervisor 서브 에이전트는 최대 3개(`AgentBuilderPolicy.MAX_SUB_AGENTS`)라 6섹션을 한 supervisor에 담지 못한다 → 순서는 코드가 쥔다. 다음 마이그레이션 번호는 V100 |

**사용자 결정 (2026-11-26)**

| # | 항목 | 결정 |
|---|------|------|
| D1 | 1차 범위 | 리포트 + 가상 계좌(매수·매도 판단, 성과 추적). 한투 주문은 보내지 않는다 |
| D2 | 화면 위치 | sangplusbot 안의 새 메뉴. 단 나중에 별도 서비스로 떼어내기 쉬운 구조 |
| D3 | 에이전트 조립 | 코드 파이프라인(순서·병렬·저장) + 섹션 에이전트는 Agent Builder 에이전트(운영자가 지침·모델·도구 수정) |
| D4 | 데이터 소스 | KIS + DART 재무·공시 + 뉴스 검색 + 웹 리서치 |
| D5 | 열람 대상 | 새 권한을 받은 사용자만. 모든 화면에 면책 문구 |
| D6 | 분석 대상 | **신호가 난 종목은 전부 분석.** 자동 분석은 운영자가 켜고 끌 수 있어야 한다 |
| D7 | 저널·원칙 학습 | 1차에 포함 |
| D8 | 코드 구조 | 주식 전용 독립 모듈 + 플랫폼과는 인터페이스(포트)로만 연결. 코어에 주식 하드코딩 금지 |

### 1.3 Related Documents

- 신호 서버: `agent_mcp/mcp-kis-server/CLAUDE.md`, `docs/signal-guide.md`, `docs/signal-comparison-prism-insight.md`
- 신호 서버 설계: `agent_mcp/docs/02-design/features/mcp-kis-server.design.md`, `kis-daily-snapshot.design.md`
- 실측: `agent_mcp/docs/03-analysis/kis-signal-test-2026-11-25.report.md`
- 선례: `docs/archive/2026-11/firewall-agent/` (스케줄·켜고 끄기·전용 화면·건너뜀)
- 시나리오·원칙: `docs/USER-SCENARIOS.md`(사내 전용, "근거 없으면 공란"), `idt/docs/architecture/growing-agent-vision.md`(성장형 에이전트 — 저널·원칙은 이 방향의 도메인 사례)

---

## 2. Scope

### 2.1 In Scope

- [ ] **M1 기반**: 독립 모듈 골격(`market_analysis`), 테이블(V100~), 권한 코드 `MARKET_ANALYSIS_VIEW`·`MARKET_ANALYSIS_MANAGE`, 자동 분석 설정(on/off, 안전 상한, 회차 시각) API
- [ ] **M2 데이터 소스**: agent_mcp에 DART MCP 서버 신규(재무제표·공시 목록), 뉴스 검색·웹 리서치 도구 연결, mcp-kis-server 등록·도구 권한 확인
- [ ] **M3 분석 파이프라인**: prefetch(도구 결과를 한 번 받아 섹션에 나눠 줌) → 섹션 에이전트 6개 → 투자전략 → 요약 → 리포트 저장(섹션별 본문 + 사용한 도구 결과 근거)
- [ ] **M4 신호 트리거**: 회차마다 후보 수집(순위·조건검색·마감 후 전 종목) → `scan_signals` → 신호 종목 전부 분석 큐에 넣기. 같은 종목은 같은 거래일에 1회만. 자동 분석 스위치가 꺼져 있으면 회차를 건너뜀
- [ ] **M5 가상 계좌**: 매수 판단 에이전트(점수·목표가·손절가·기간·근거) + 결정론 게이트(체제별 최소 점수, 손익비 하한, 손절폭 상한, 슬롯 여유) → 진입 또는 관심종목(보류 사유). 보유 종목은 회차마다 목표·손절 도달 시 결정론 청산, 그 밖에는 매도 판단 에이전트(유지·매도·목표·손절 조정). 성과(실현 수익률, 승률, 평균 보유일, 누적 수익률과 KOSPI·KOSDAQ 비교)
- [ ] **M6 저널·원칙**: 청산마다 저널 에이전트(상황, 판단 평가, 교훈, 패턴 태그) → 원칙 후보(조건·행동·근거 거래 수·확신도) → 활성 원칙을 매수·매도 판단 입력에 넣음. 운영자가 원칙을 끄고 켬
- [ ] **M7 화면**: 대시보드 · 보유 종목 · 거래 내역 · 관심종목 · 리포트 목록/상세 · 인사이트(원칙·저널·신호 규칙별 성과) · 설정(스위치·상한·회차·섹션 에이전트 지정) · 실행 현황(회차별 대상 수·성공·실패·토큰 비용)
- [ ] **M8 실측**: 장 마감 후 실데이터 E2E 1회 + 비용 측정, 장중 회차 1회

### 2.2 Out of Scope

- 한투 주문(모의 포함) 전송 — `place_order` 도구는 이 기능의 에이전트에 권한을 주지 않는다
- 미국 시장 (`KIS_US_ENABLED` 꺼짐 유지)
- 외부 공개·대고객 노출, 텔레그램 같은 외부 방송 (USER-SCENARIOS 스코프 밖)
- 리포트 PDF·DOCX 내보내기, 메일·메신저 알림 → 다음 사이클 후보
- 별도 서비스 분리 자체 (구조만 대비)
- prism-insight 코드·프롬프트 복사 (AGPL). 구조와 아이디어만 참고한다
- 백테스트 엔진, 트리거 품질 가중치 자동 조정

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Module |
|----|-------------|----------|--------|
| FR-01 | 자동 분석 스위치(전체 on/off)를 운영자가 화면에서 바꾸고, 꺼져 있으면 신호 수집·분석·보유 관리 회차가 모두 실행되지 않고 "건너뜀"으로 기록된다 | High | M1·M4 |
| FR-02 | 비용 안전 장치: 회차당·하루당 최대 분석 종목 수, 동시 분석 수를 설정값으로 둔다. 상한을 넘은 종목은 버리지 않고 "상한 초과로 미분석"으로 남긴다 (D6 '전부 분석'을 기본으로 하되 상한은 사고 방지용) | High | M1·M4 |
| FR-03 | 회차 시각(장중 n회·마감 후 1회)을 설정으로 정한다. 장중 분석은 미확정 봉 기반임을 리포트에 표시한다 | High | M4 |
| FR-04 | 회차마다 후보 수집 → `scan_signals` → 신호가 하나라도 난 종목을 분석 대상으로 넣는다. 같은 종목은 같은 거래일에 1회만 분석하고, 보유 중인 종목은 매수 분석 대신 매도 판단으로 보낸다 | High | M4 |
| FR-05 | 종목 분석은 prefetch → 6섹션 → 전략 → 요약 순서로 코드가 실행한다. 섹션 사이에는 병렬 실행이 가능하다 | High | M3 |
| FR-06 | 섹션별 담당 에이전트는 Agent Builder 에이전트를 지정해 쓴다(설정 화면에서 역할 ↔ 에이전트 매핑). 지정이 없으면 모듈 기본 지침으로 생성한 에이전트를 쓴다 | High | M3·M7 |
| FR-07 | 리포트는 섹션별 본문, 사용한 도구 결과(근거), 신호 종류, 분석 시점, 봉 확정 여부, 섹션별 토큰을 저장한다. 근거가 없는 수치는 쓰지 않는다(공란 + "데이터 없음") | High | M3 |
| FR-08 | 매수 판단 에이전트는 점수(1~10)·목표가·손절가·투자 기간·근거를 구조화해 낸다. 진입 여부는 결정론 게이트가 정한다(체제별 최소 점수, 손익비 하한, 손절폭 상한, 남은 슬롯) | High | M5 |
| FR-09 | 가상 계좌는 10슬롯(설정)이며 진입·청산 가격은 판단 시점의 KIS 시세로 기록한다. 실현 수익만 누적한다 | High | M5 |
| FR-10 | 보유 종목은 회차마다 현재가를 확인해 목표가·손절가 도달 시 결정론으로 청산하고, 그 밖에는 매도 판단 에이전트가 유지·매도·목표 조정을 낸다 | High | M5 |
| FR-11 | 시장 체제(강세~강약세)는 지수 이평 기준의 결정론 규칙으로 계산해 일자별로 저장한다 | Medium | M5 |
| FR-12 | 청산마다 저널 에이전트가 저널을 쓰고, 원칙 후보를 만든다. 활성 원칙(상한 N개)은 매수·매도 판단 입력에 들어간다. 운영자는 원칙을 끄고 켤 수 있다 | Medium | M6 |
| FR-13 | 화면: 대시보드(KPI, 누적 수익률 vs KOSPI·KOSDAQ), 보유 종목, 거래 내역, 관심종목(보류 사유), 리포트 목록·상세, 인사이트, 설정, 실행 현황 | High | M7 |
| FR-14 | 모든 화면 상단에 면책 문구("투자 권유 아님, 가상 계좌 시뮬레이션")를 표시한다 | High | M7 |
| FR-15 | `MARKET_ANALYSIS_VIEW` 없는 사용자에게는 메뉴·API가 모두 막힌다. 설정·원칙 변경은 `MARKET_ANALYSIS_MANAGE` | High | M1 |
| FR-16 | DART MCP 서버: 기업 고유번호 조회, 주요 재무제표(분기·연간), 최근 공시 목록. 사실만 돌려준다 | High | M2 |
| FR-17 | 회차·종목 단위 실행 기록(대상, 성공·실패, 실패 사유, 토큰·비용)을 남기고 실행 현황 화면에 보인다 | Medium | M4·M7 |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 분리 가능성 | `market_analysis` 모듈은 플랫폼 내부 클래스를 직접 import하지 않고 포트(에이전트 실행, MCP 도구 호출, 인증·권한, 잡 실행)만 쓴다 | 의존 방향 AST 테스트 |
| 비용 | 종목당 LLM 호출·토큰을 기록하고, 마감 후 회차 1회 비용을 M8에서 실측해 Design 추정치와 비교 | 실행 기록 집계 |
| 정확성 | 리포트·판단에 나오는 가격·거래량·재무 수치가 도구 결과와 일치 | M8 표본 대조 (종목 5개 × 수치 10개) |
| 안정성 | 한 종목 분석 실패가 회차 전체를 멈추지 않는다. KIS `RATE_LIMITED`·`KIS_TIMEOUT`은 종목 단위 실패로 기록 | 실패 주입 테스트 |
| 동시성 | 회차가 겹치면 뒤 회차는 건너뛴다(`skip_when_busy` 방식) | 테스트 |
| 보안 | 이 모듈 에이전트에 모의 주문 도구(`place_order`·`cancel_order`) 권한 없음 | 도구 권한 테스트 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] SC-1: 장 마감 후 회차 1회에서 신호 종목 전부가 리포트 → 매수 판단 → 계좌 반영(진입 또는 관심종목)까지 끝난다 (상한 초과분은 "미분석"으로 남는다)
- [ ] SC-2: 자동 분석을 끄면 다음 회차가 "건너뜀"으로 기록되고 LLM 호출이 0회다
- [ ] SC-3: 표본 리포트 5건의 수치 50개가 도구 결과와 일치한다(불일치 0). 데이터가 없는 항목은 공란으로 남는다
- [ ] SC-4: 보유 종목이 손절가·목표가에 닿으면 다음 회차에 청산되고, 거래 내역·성과·저널이 생긴다
- [ ] SC-5: 활성 원칙이 다음 매수 판단 입력에 들어간 것이 실행 기록에서 확인된다
- [ ] SC-6: 권한 없는 사용자는 메뉴가 보이지 않고 API가 403을 돌려준다
- [ ] SC-7: 섹션 에이전트의 지침을 빌더에서 바꾸면 다음 분석에 반영된다(코드 수정 없음)
- [ ] SC-8: `market_analysis` 모듈의 의존 방향 테스트가 통과한다

### 4.2 Quality Criteria

- [ ] 백엔드 pytest, 프론트 Vitest·RTL·MSW — TDD
- [ ] 기존 회귀 실패 0 (master 상시 실패 목록 제외)
- [ ] ruff·tsc·eslint 통과
- [ ] Gap 분석 Match Rate 90% 이상

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| **"신호 종목 전부 분석"의 비용 폭주** — 11-25 실측에서 거래량 상위 30종목 중 신호 58건이 났다. 종목 20개 × 종목당 LLM 약 10회면 회차당 약 200회 | High | High | FR-02 상한(회차·하루·동시), 스위치(FR-01), 종목·회차 토큰 기록(FR-17), 섹션은 경량 모델·판단은 상위 모델 조합. 기본 상한값은 M8 실측으로 정함 |
| 숫자 할루시네이션 (가격·재무 수치를 지어냄) | High | Medium | prefetch 결과만 근거로 쓰게 하고, 리포트에 근거 블록 저장, 판단 게이트는 LLM 숫자가 아닌 시세로 다시 계산(손익비·손절폭) |
| 사내에 매매 의견 노출 (준법) | High | Medium | 권한 부여자만(D5), 면책 문구, 주문 미전송, 가상 계좌 명시. 운영 오픈 전 준법 확인은 사용자 몫으로 남긴다 |
| AGPL 코드 유입 | High | Low | 코드·프롬프트 복사 금지. 참고는 공개 문서의 구조 수준으로 하고, Design에 참고 출처를 표로 남긴다 |
| mcp-kis-server 실운영 미검증 (quant DB 연결, 전 종목 적재 실데이터) | Medium | High | M2에서 등록·조회 실측을 먼저 하고, 전 종목 적재가 안 되면 순위·조건검색 후보만으로 M4를 시작 |
| 장중 미확정 봉 기반 판단 | Medium | High | 리포트·판단에 `provisional` 표시, 결정론 청산은 현재가 기준, 장중 회차 진입 여부는 설정으로 |
| DART·뉴스 키·쿼터 부재 | Medium | Medium | 섹션 단위 실패 허용(해당 섹션 "데이터 없음"), 키 확보 여부를 M2 착수 전 확인 |
| 범위 과다 (M1~M8, 저널 포함) | Medium | High | 모듈 단위 세션 진행, M5까지 끝나면 중간 점검. 필요 시 M6·M7 일부를 후속 기능으로 분리 |
| 회차 겹침·워커 부하 (분석이 회차 간격보다 길다) | Medium | Medium | 회차 건너뜀, 종목 단위 잡 분할, 동시 실행 상한 |
| Smart App Control DLL 차단 (로컬) | Low | High | 서버 기동은 사용자가 하고, 실측 스크립트는 재시도 래퍼를 쓴다 (기존 메모 준수) |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `market_analysis` (domain·application·infrastructure·api) | 신규 모듈 | 전부 신규 |
| `ma_*` 테이블 (V100~) | DB | 신규: 설정, 회차·종목 실행, 리포트·섹션, 판단, 가상 계좌(포지션·거래), 관심종목, 시장 체제, 저널, 원칙, 섹션↔에이전트 매핑 |
| `PermissionCode` | Enum | `MARKET_ANALYSIS_VIEW`·`MARKET_ANALYSIS_MANAGE` 추가 |
| 백그라운드 잡 종류 | Config/Code | 분석 회차 잡 유형 추가 (기존 워커 재사용) |
| 사이드바·라우터 (idt_front) | UI | '시장 분석' 메뉴 1개, 권한 기반 노출 |
| MCP 레지스트리 | Data | mcp-kis-server(등록 확인), mcp-dart-server(신규), 뉴스·웹 도구 |
| agent_mcp `mcp-dart-server` | 신규 서버 | 신규 |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| `PermissionCode` | READ | `idt/src/domain/permission/value_objects.py`, `resolver.py`, 권한 관리 화면·라벨 | 값 추가만 — 라벨 맵·권한 관리 화면 목록 확인 필요 |
| 백그라운드 워커 | READ | `idt/src/application/background_job/` | 새 잡 유형 등록 — 기존 잡 처리 분기 확인 필요 |
| `RunAgentUseCase` | CALL | 웹훅·스케줄·백그라운드 호출자 | 새 호출자 추가 — 노출 범위 기능은 호출자 opt-in 플래그(기본 False) 규칙을 따름. 기존 호출자 영향 없음 |
| 사이드바 메뉴 | READ | idt_front 사이드바·라우터 | 권한 없는 사용자에게 변화 없음 |
| Agent Builder 에이전트 | READ | 섹션 매핑이 에이전트 id를 참조 | 에이전트 삭제 시 매핑 처리 필요 (Design에서 정함) |

### 6.3 Verification

- [ ] 권한 추가 후 기존 권한 관리 화면·API 회귀 통과
- [ ] 기존 백그라운드 잡(스케줄·알림 수신) 회귀 통과
- [ ] `RunAgentUseCase` 호출자 AST 계약 테스트 통과

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Selected |
|-------|:--------:|
| Starter | ☐ |
| Dynamic | ☐ |
| **Enterprise** (기존 idt 레이어 규칙: domain → application → infrastructure, DI) | ☑ |

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 조립 | Agent Builder supervisor / 코드 고정 / 코드 파이프라인 + 빌더 에이전트 | **코드 파이프라인 + 빌더 에이전트** (D3) | 6섹션 순서·병렬·저장은 코드가 보장하고, 지침·모델은 운영자가 바꾼다. supervisor 서브 에이전트 3개 제약을 피한다 |
| 파이프라인 엔진 | LangGraph / 순수 asyncio | LangGraph (Design에서 확정) | 기존 스택. 섹션 병렬·재시도 표현이 쉽다 |
| 판단 방식 | LLM 단독 / 결정론 단독 / LLM 점수 + 결정론 게이트 | **LLM 점수 + 결정론 게이트** | 진입·청산·손익비는 재현 가능해야 한다. "LLM 출력을 신뢰하지 않고 서버가 최종 결정" (기존 ComposePolicy 원칙과 같음) |
| 저장소 | quant DB / sangplusbot MySQL | **sangplusbot MySQL, `ma_` 접두** | 권한·화면·실행 기록이 여기 있다. 분리 시 `ma_*` 테이블만 옮긴다 |
| 모듈 경계 | 코어 범용화 / 독립 모듈 + 포트 | **독립 모듈 + 포트** (D8) | 분리 대비. 포트 4개: 에이전트 실행, MCP 도구 호출, 인증·권한, 잡 스케줄 |
| API | 기존 라우터에 섞기 / 전용 prefix | `/api/v1/market-analysis/*` | 분리 시 prefix 단위로 떼어낸다 |
| 프론트 | 기존 pages에 흩기 / 한 폴더 | 한 폴더(라우트·서비스·훅·타입 묶음) | 위치는 idt_front CLAUDE.md 규칙을 확인해 Design에서 정함 |
| 데이터 수집 | 섹션마다 도구 호출 / prefetch 후 배분 | **prefetch 우선, 섹션 에이전트는 보충 호출만** | KIS 계정 초당 한도·비용 절감, 근거 블록 일원화 |

### 7.3 흐름

```
[회차 잡] 워커(30초 틱)가 설정 시각에 실행 ── 스위치 OFF → 건너뜀 기록
  ① 시장 체제 계산(지수, 결정론) ─ 일 1회
  ② 보유 종목: 현재가 → 목표·손절 도달 시 청산 / 아니면 매도 판단 에이전트
  ③ 후보 수집: get_rankings · run_condition_search · (마감 후) 전 종목 DB
  ④ scan_signals → 신호 종목 전부 (당일 분석분·보유분 제외, 상한 적용)
  ⑤ 종목별 분석 잡 (동시 상한)
       prefetch(KIS·DART·뉴스·웹) → 섹션 6 → 전략 → 요약 → 리포트 저장
       → 매수 판단 에이전트(+ 활성 원칙) → 결정론 게이트 → 진입 | 관심종목(보류 사유)
  ⑥ 청산 발생 시 저널 에이전트 → 원칙 후보

[화면] /market-analysis/*  ← API /api/v1/market-analysis/*  ← ma_* 테이블
```

### 7.4 모듈 구조 미리보기

```
idt/src/domain/market_analysis/          엔티티·VO·정책(게이트, 체제, 슬롯, 상한)
idt/src/application/market_analysis/     회차·분석·판단·저널 유스케이스, 포트 정의
idt/src/infrastructure/market_analysis/  리포지토리, 포트 어댑터(플랫폼 연결은 여기만)
idt/src/api/routes/market_analysis*.py   /api/v1/market-analysis/*
idt/db/migration/V100__...               ma_* 테이블
idt_front/.../market-analysis/           화면 묶음 (위치는 Design)
agent_mcp/mcp-dart-server/               DART 재무·공시 MCP (신규)
```

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- [x] `CLAUDE.md` 3종 (`/`, `idt/`, `idt_front/`)과 `idt/docs/rules/`
- [x] TDD 원칙 (pytest / Vitest + RTL + MSW)
- [x] idt_front 상수 export 규칙(컴포넌트 파일 런타임 상수 export 금지, `as const`는 `src/types/*.ts`)
- [x] `RunAgentUseCase` 호출자 opt-in 게이팅 + AST 계약 테스트
- [x] agent_mcp MCP 서버 스캐폴딩 규칙 (`mcp-server-scaffold`), 응답·오류 형식 `"{CODE}: 설명"`

### 8.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| 모듈 경계 | 없음 | `market_analysis`가 import할 수 있는 플랫폼 패키지 목록(포트만) + AST 테스트 | High |
| 테이블 접두 | 없음 | `ma_` | High |
| 리포트 근거 형식 | 근거 칩(`_attach_sources`) 존재 | 섹션별 근거 블록 스키마 — 기존 근거 칩 재사용 여부 | Medium |
| 시각 | 응답 UTC `+00:00` 부착(PR #136) | 거래일은 KST 날짜, 시각은 UTC 저장 | Medium |

### 8.3 Environment Variables Needed

| Variable | Purpose | Scope | To Be Created |
|----------|---------|-------|:-------------:|
| `MARKET_ANALYSIS_ENABLED` | 모듈 자체 활성(라우터·잡 등록). 기본 false | idt | ☐ |
| `OPENDART_API_KEY` | DART 재무·공시 | mcp-dart-server | ☐ |
| `TAVILY_API_KEY` / `PERPLEXITY_API_KEY` | 뉴스·웹 리서치 (기존 키) | idt | 기존 |
| KIS 키·`KIS_HTS_ID` | mcp-kis-server (기존) | agent_mcp | 기존 |

자동 분석 on/off·상한·회차는 env가 아니라 DB 설정(화면에서 변경)으로 둔다.

---

## 9. Next Steps

1. [ ] 아래 미결 사항 확인
2. [ ] `/pdca design stock-analysis-agents` — 3가지 설계안 비교, 테이블·API·포트·화면 상세, 세션 가이드(M1~M8)
3. [ ] M2 착수 전 DART 키, 뉴스 도구(네이버 검색 MCP는 Plan 상태, Tavily 내장 여부) 확인

### 9.1 미결 사항 (Design에서 정하거나 사용자 확인)

| # | 항목 | 제안 기본값 |
|---|------|-------------|
| Q1 | 회차 시각 | 장중 10:00·14:00 + 마감 후 18:10 (마감 후 회차가 전 종목 적재 이후) |
| Q2 | 안전 상한 기본값 | 회차 20종목, 하루 50종목, 동시 3 — M8 실측 후 조정 |
| Q3 | 모델 | 섹션: 경량 모델 / 전략·매수·매도 판단: 상위 모델 (빌더에서 변경 가능) |
| Q4 | 장중 회차에서 진입 허용 여부 | 허용, 단 리포트·판단에 미확정 표시 |
| Q5 | 시장 체제용 지수 데이터 | KIS 지수 조회 가능 여부 확인. 안 되면 KODEX 200(069500) 등 ETF로 대체 |
| Q6 | 섹션 에이전트 기본 생성 | 모듈 활성화 시 기본 에이전트 8개(섹션 6 + 전략·요약)와 판단 3개(매수·매도·저널)를 생성해 매핑 |
| Q7 | 원칙 주입 상한 | 활성 원칙 최대 10개, 우선순위·확신도 순 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-11-26 | 최초 작성 — 신호 서버·prism-insight·실사이트 데이터 조사, 사용자 결정 D1~D8 반영 | 배상규 |
