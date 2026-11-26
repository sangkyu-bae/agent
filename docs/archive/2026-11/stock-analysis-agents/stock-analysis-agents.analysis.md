# stock-analysis-agents Gap Analysis

> **Summary**: 최종 분석(module-1~10, §11) — Overall **94.6%**(실측 포함) / 정적 공식 96.2%, Critical 0 · Important 2 · Minor 8 · 문서 갱신 10. SC 7/8 충족, SC-3 부분. §1~§10 은 module-1~6 중간 점검(94.3%)과 Act-1 기록.
>
> **Author**: gap-detector (주요 갭은 주 세션에서 코드로 재확인)
> **Created**: 2026-11-26 (중간) · 2026-11-26 (최종 §11)
> **Status**: Draft
> **Design**: stock-analysis-agents.design.md (v1.2)
> **Plan**: stock-analysis-agents.plan.md (v0.1)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 신호(사실)와 판단 사이의 빈칸을 에이전트가 채우고, 판단의 성과를 추적·복기할 수 있게 한다 |
| **WHO** | 권한 부여자(리포트·계좌 열람), 운영자(자동 분석 on/off, 섹션 에이전트 지침·모델 관리) |
| **RISK** | "신호가 오면 전부 분석"의 LLM 비용 폭주 · 숫자 할루시네이션 · 사내 매매 의견 노출(준법) · AGPL 코드 유입 |
| **SUCCESS** | 장 마감 후 실행 1회에서 신호 종목 전부가 리포트·판단·계좌 반영까지 끝나고, 리포트 숫자가 도구 결과와 일치하며, 스위치를 끄면 다음 회차가 실행되지 않는다 |
| **SCOPE** | 국내(KRX)만. module-1 기반 → 2 데이터 소스 → 3 포트·코어 opt-in → 4 분석 파이프라인 → 5 회차 → 6 가상 계좌 → 7 저널·원칙 → 8 조회 API → 9 화면 → 10 실측 |

---

## 1. 범위

- 대상: module-1~6. 기준은 Design §2.2·2.3·3·4·6·7·10·13.2·14.2·16 과 구현 결과 절 §4.2·§7.1·§7.2·§7.3·§8.1(Do 단계 확정 결정 — 코드가 그와 어긋날 때만 Gap).
- 이미 확인(재실행 안 함): 모듈·계약 테스트 266 통과, ruff 통과, 전체 스위트는 기존 실패 61건 외 통과.
- **미확인**: agent_mcp 코드(`get_index_history`·mcp-dart-server·mcp-perplexity-server), `adapters/access.py`·`structured.py`·`agent_creator.py`·`default_prompts.py`·`models.py`(V100 일치는 `test_models_match_migration` 이 보장)·`repositories.py`·`application/market_analysis/access.py` 세부.
- 정적 공식: Overall = 0.2·Structural + 0.4·Functional + 0.4·Contract.

## 2. Plan Success Criteria

| SC | 상태 | 근거 |
|----|------|------|
| SC-1 회차 1회에 신호 종목 → 리포트 → 판단 → 계좌 반영 | ⚠️ Partial (코드 경로 완성, 실측은 module-10) | `round_runner.py` 후보·스캔·상한·분석, `judgement.py` 게이트 → 진입/관심. bootstrap API(module-8) 전까지 모든 회차 ROLE_UNMAPPED(§7.3 주의, 설계대로) |
| SC-2 스위치 OFF → 건너뜀, LLM 0회 | ✅ Met (정적) | `scheduler.py`, `test_scheduler.py::test_disabled_switch_records_skip_and_never_runs_u7` |
| SC-3 리포트 수치 50개 일치 | ⏸️ module-10 | 기반: 머리 사실 결정론 렌더 `report.py`, 근거 블록 `evidence.py`, 근거 저장 `report_repository.py` |
| SC-4 손절·목표 도달 → 청산·거래·성과·저널 | ⚠️ Partial | 청산·판단 기록 `positions.py`, 성과 `performance.py`, `test_position_manager.py::test_sc4_...`. 저널은 module-7(`on_closed` 자리만) |
| SC-5 활성 원칙 → 매수 판단 입력 | ⏸️ module-7 | 주입·기록 자리 `judgement.py`(`principles_used`), DI `principles=None` |
| SC-6 권한 없음 → 메뉴 없음·403 | ⚠️ Partial | `require_view`·`require_manage`, `/access`. 보호 라우트 module-8, 메뉴 module-9 |
| SC-7 빌더 지침 변경 반영 | ⚠️ Partial (구조 충족, 실측 E7 남음) | 역할 → 에이전트 id 매핑 실행 `pipeline.py` |
| SC-8 의존 방향 테스트 | ✅ Met | `tests/contracts/test_market_analysis_isolation.py` I1~I6 |

## 3. 구조 (Structural) — 100% (idt 기준)

| Design §16.1 항목 | 구현 | 상태 |
|---|---|---|
| domain `{entities,value_objects,policies}.py` | `value_objects`·`setting`·`access`·`runtime`·`tool_policy`·`report`·`round`·`account` 로 분할 | ✅ (분할만 다름 — 문서 갱신 권장) |
| application ports·pipeline·round_runner·candidates·judgement·positions·regime·performance·verdict_parser·evidence·bootstrap_agents·default_prompts | 전부 있음 (+ scheduler, access) | ✅ |
| infrastructure models·repositories·ticker | 있음 (+ report/round/account_repository 분리) | ✅ |
| adapters agent_runner·market_tools·access·structured | 있음 (+ agent_creator) | ✅ |
| `api/market_analysis_di.py`·`routes/market_analysis_router.py` | 있음 (라우터는 `/access` 만) | ✅ |
| 코어 수정: schemas(`reference_context`)·run_agent_use_case·PermissionCode 2·config 플래그 2·main 배선 | 있음 | ✅ |
| V100(13 테이블)·V101 | 있음 | ✅ |
| agent_mcp 3건 | 미확인 | — |
| journal(module-7), queries·commands·schemas(module-8), `interfaces/schemas/market_analysis/` | — | 범위 밖 |

placeholder·TODO 없음. `market_analysis_router.py` 의 `NotImplementedError` 는 DI 가 덮어쓰는 기본 의존성.

## 4. 기능 (Functional) — 92.9% (26/28)

### 4.1 §6 정책 (6/6, PrincipleSelectionPolicy 는 module-7)

| 정책 | 결과 |
|---|---|
| RegimePolicy | ✅ 5단계·60봉 미만 neutral+insufficient (`account.py`) |
| EntryGatePolicy ①~⑧ | ✅ 사유 누적, Decimal, P = 게이트 시점 get_quote |
| ExitPolicy | ✅ STOP 우선, adjust 조건 |
| RoundCapPolicy | ✅ duplicate/held/over_cap, 신호 수 → 거래량 → 종목코드 |
| RoundSchedulePolicy | ✅ KST, 30분 창, 15:30 이후 close, 주말, 휴장 |
| PerformancePolicy | ✅ 실현 수익률 × 비중 ÷ 슬롯, 승률 |

### 4.2 §10 실패 모델 (해당 9행 → 7.5/9)

| 상황 | 결과 |
|---|---|
| KIS 서버 비활성·KIS_AUTH_FAILED → 회차 failed | ❌ done(후보 0) → **I1** |
| KIS RATE_LIMITED·TIMEOUT(종목) → item failed | ✅ |
| DART·Tavily·Perplexity 실패 → 근거 is_error | ✅ |
| 섹션 실패 → partial, 매수 판단 진행 | ✅ |
| 전략·요약 실패 → skip(REPORT_INCOMPLETE) | ✅ |
| JSON 파싱 실패 → DD8 폴백 | ✅ |
| 재시작 → abandoned + item failed(ABANDONED) | ⚠️ running 리포트는 남음 → **I2** |
| 회차 겹침 → BUSY | ✅ |
| 역할 매핑 없음 | ✅ |

### 4.3 §13.2 Unit 시나리오 (해당 13개 → 12.5/13, U12 는 module-7)

U1·U2·U3(`test_account_policies.py`), U4(`test_exit_policy`, `test_position_manager.py::test_sc4_...`), U6(`test_round_policy.py::test_cap_policy_u6`), U7(`test_scheduler.py`), U8(`test_round_runner.py::test_holiday_skips_without_analysis_u8`), U9(`test_verdict_parser.py`, `test_buy_judgement.py`), U10(`test_pipeline.py`), U11·U14(`test_scheduler.py`, `test_round_repository.py`), U13(`test_tool_policy.py`, `test_market_tools.py`) ✅.
U5 ⚠️ — 5단계는 있으나 경계값(R20 = ±5% 정확히, C = MA20, MA20 = MA60) 없음 → M1.

## 5. 계약 (Contract) — 92.9% (13/14)

AgentRunnerPort · MarketToolPort · AccessPort(→ PermissionCodesReader + AccessPolicy, 이름만 다름) · StructuredExtractor · ReportStore·RoleAgentStore · RoundStore · HeldReader · PositionStore·DecisionStore·RegimeStore · AgentCreator · DB 컬럼↔V100↔models · `ma_round` UNIQUE · 권한 코드·설정 기본 행 · `GET /access` 응답 → ✅
`reference_context` 는 HTTP 로 들어올 수 없다(§4.1·§11) → ❌ **C1**

## 6. Gap 목록

### 🔴 Critical

**C1. `reference_context` 가 HTTP 로 들어오고 프롬프트 가드를 거치지 않는다 (확신도 95%, 주 세션 재확인)**
- 위치: `idt/src/api/routes/agent_builder_router.py:290-293` (`body: RunAgentRequest`), `idt/src/application/agent_builder/schemas.py:338`, 주입 `run_agent_use_case.py` `_prepare_graph`
- 내용: `POST /api/v1/agents/{id}/run` 에 `reference_context` 를 담아 보내면 "[참고 자료 — 호출자 제공 …]" 머리말을 달고 마지막 사용자 메시지 뒤에 붙는다. 프롬프트 가드는 `query` 만 보므로 가드 없는 주입 통로가 된다. 계약 테스트 `test_reference_context_callers.py` 는 라우터 소스의 문자열만 보므로 잡지 못한다.
- 제안: HTTP 라우트에서 `reference_context` 를 받지 않게 막고(전용 body 스키마 또는 None 강제), TestClient 로 POST 했을 때 use case 가 None 을 받는지 확인하는 계약 테스트 추가.
- 참고(기존 결함, 이번 변경과 무관): `persist_conversation`·`llm_model_id_override`·`temperature_override` 도 같은 경로로 노출.

### 🟡 Important

**I1. KIS 를 쓸 수 없어도 회차가 failed 가 아니라 done(0건)으로 끝난다 (확신도 90%)**
- 위치: `round_runner.py` (`kis_server_id` 존재만 검사), `regime.py` `_bars`(오류 → 빈 목록), `candidates.py`(오류 → 건너뜀)
- 내용: Design §10 "KIS 서버 비활성·KIS_AUTH_FAILED → 회차 failed". 지금은 장애와 "신호 없음"을 구분할 수 없다.
- 제안: 회차 ①의 KIS 응답이 `SERVER_UNAVAILABLE`·`KIS_AUTH_FAILED` 이거나 순위 조회가 전부 오류면 `failed(KIS_UNAVAILABLE)`. 테스트 추가.

**I2. 파이프라인 예외 시 `ma_report` 가 running 으로 영구히 남는다 (확신도 85%, 주 세션 재확인)**
- 위치: `pipeline.py` 리포트 생성 뒤 구간 예외 → `round_runner.py` 는 item 만 failed. `abandon_running` 은 리포트를 건드리지 않는다.
- 예외 경로: `adapters/agent_runner.py` 의 `_assemble` 와 `RunAgentRequest(...)` 생성이 try 밖 — 참고 자료가 40,000자를 넘으면 ValidationError(요약 단계의 전략 본문 길이 무제한), `save_section` 등 DB 오류.
- 제안: `pipeline.run` 의 리포트 생성 이후를 감싸 `finish_report(FAILED)` 보장, 요약 참고 자료의 전략 본문 자르기, agent_runner 의 try 범위 확대(실패를 값으로), `abandon_running` 이 그 회차 running 리포트도 failed 로.

### 🔵 Minor

| # | 위치 | 내용 | 제안 |
|---|---|---|---|
| M1 | `test_account_policies.py` | U5 경계값 테스트 없음 | 경계 테스트 추가 |
| M2 | `verdict_parser.py` `_price` | `NaN`·`Infinity` 가 InvalidOperation 으로 pydantic 밖에 새고 판단 행이 남지 않음 | `is_finite()` 검사, ValueError 로 변환 |
| M3 | `judgement.py` 진입 | enter 판단 저장 → 포지션 생성 → 연결이 원자적이지 않음 | 실패 시 판단을 skip(ENTRY_FAILED)으로 |
| M4 | `positions.py` `gather` | 한 포지션 예외가 manage 전체를 실패시키고 청산 건의 `on_closed` 가 빠짐 | `_one` 단위로 예외 가두기 |
| M5 | `adapters/market_tools.py` | `server_finder` DB 예외가 try 밖 | try 안으로, `SERVER_LOOKUP_FAILED` |
| M6 | `judgement.py` 진입 잠금 | 프로세스 단위 — module-8 `run-now` 때 재확인 | run-now 설계 때 확인 |
| M7 | `round_repository.py` `_ANALYZED` | failed 재시도가 하루 상한 밖에서 비용을 씀 | M8 실측 때 비용 확인 |
| M8 | Design §4·§16.1 | 포트 이름·파일 분할이 구현과 다름 | 설계 문서 갱신 |

## 7. 범위 밖 (계획됨 — Gap 아님)

- module-7 저널·원칙 (JournalWriter, PrincipleReader 구현, `on_closed` 연결, PrincipleSelectionPolicy, U12, SC-5)
- module-8 조회·설정 API (`/access` 외 라우트, bootstrap API, 설정 검증, 오류 코드, L1)
- module-9 화면 (탭, 면책 띠, 메뉴 노출, L2)
- module-10 실측 (E1~E8, SC-1·SC-3 실측, 비용·상한 재검토)
- agent_mcp 실왕복 (키 없음)

## 8. Match Rate

| 축 | 점수 |
|---|:---:|
| Structural | 100% |
| Functional | 92.9% |
| Contract | 92.9% |
| **Overall** | **94.3%** |

90% 이상이지만 C1 은 보안 계약 위반이므로 module-7 착수 전에 고친다. 권장 순서: C1 → I2 → I1 → Minor.

## 9. Runtime Verification Plan (참고)

| 층 | 항목 |
|---|---|
| L1 | `POST /api/v1/agents/{id}/run` 에 `reference_context` → 주입되지 않는지 · `GET /api/v1/market-analysis/access` 권한 없음 → `can_view:false` · 모듈 off → 404 |
| L3 | module-10 E1~E8 (서버는 사용자가 기동) |

## 10. Act-1 수정 결과 (2026-11-26, 사용자 결정: Critical+Important 수정, Minor 는 기록만)

| Gap | 수정 | 테스트 |
|---|---|---|
| C1 | `RunAgentHttpRequest`(schemas.py) — `reference_context` 를 OpenAPI 에서 빼고(`SkipJsonSchema`) 본문에 있어도 검증 전에 버린다. `POST /{agent_id}/run` 본문 타입을 이것으로 교체. 내부 호출자(시장 분석 어댑터)는 기존 `RunAgentRequest` 그대로 | `tests/api/test_run_agent_reference_context_http.py` (본문 값 무시 · OpenAPI 미노출) |
| I1 | `regime.MarketRegimeService` 가 KOSPI 조회의 `SERVER_UNAVAILABLE`·`KIS_AUTH_FAILED` 를 `MarketSnapshot.kis_error` 로 돌려주고, 회차는 `failed(KIS_UNAVAILABLE(코드))`. 일시 오류(KIS_TIMEOUT·RATE_LIMITED)는 기존대로 neutral 로 계속 | `test_round_runner.py::test_kis_unavailable_fails_round_instead_of_done_zero`, `::test_transient_index_error_does_not_fail_round` |
| I2 | ① `pipeline.run` 이 리포트 행 생성 뒤 예외를 잡아 `finish_report(FAILED)` 후 다시 던짐 ② 요약 참고 자료의 전략 본문 20,000자·전체 38,000자 상한 ③ `PlatformAgentRunner` 가 인증 조립 예외(`AUTH_CONTEXT_FAILED`)·참고 자료 초과(`CONTEXT_TOO_LONG`)·요청 검증 실패(`REQUEST_INVALID`)를 값으로 ④ `abandon_running` 이 그 회차의 running 리포트도 failed 로 | `test_pipeline.py::test_exception_after_report_created_marks_it_failed_and_reraises`, `::test_summary_context_is_bounded_even_for_huge_strategy`, `test_agent_runner.py::test_assembler_exception_becomes_failed_outcome`, `::test_reference_context_over_limit_fails_without_running`, `test_round_repository.py::test_abandon_running_also_fails_running_reports_of_that_round` |

Minor M1~M8 은 그대로 남긴다 — M4(보유 관리 예외 격리)·M3(진입 원자성)은 module-7 `on_closed` 연결 때 함께 보는 것을 권장.
수정 후 예상 Match Rate: Functional 28/28 중 27.5(U5 경계만 남음), Contract 14/14 → Overall ≈ 99%.

---

## 11. 최종 분석 (module-1~10, 2026-11-26)

정적 대조는 gap-detector, 런타임은 설계서 §7.8 실측(E1~E8)과 이번 회귀 실행. G2 는 주 세션에서 코드로 재확인했다.

### 11.1 점수

| 축 | 점수 | 근거 |
|---|:-:|---|
| Structural | 97% | §16.1·§7.6 파일, 라우트 18, V100(13 테이블)·V101, agent_mcp 3건 존재. 빠진 `application/market_analysis/schemas.py`·`src/interfaces/schemas/market_analysis/` 는 §14.1 이 "라우터 안 스키마"로 바꾼 문서 쪽 문제. 탭 URL 라우팅 없음 |
| Functional | 95% | §6 정책 7, §10 실패 모델 9/9, §9.4 체크리스트 24 충족·2 부분(G2·G3). 이전 Minor M1·M2·M5·M7 잔존 |
| Contract | 97% | 18/18 엔드포인트 설계·서버·클라이언트 일치(URL·메서드·파라미터·응답 모양·오류 형식). 값 계약 1건 불일치(G2) |
| Runtime | 94% | §7.8: E1·E2·E4~E7 통과, E3 부분, E8 측정 |

- 이전과 같은 정적 공식(0.2S+0.4F+0.4C): **96.2%** (중간 94.3%)
- 실측 포함 공식: **94.6%**

### 11.2 Plan Success Criteria

| SC | 상태 | 근거 |
|---|:-:|---|
| SC-1 신호 종목 → 리포트 → 판단 → 계좌 반영 | ✅ | E1 회차 #4: 리포트 5(섹션 6/6), 판단 5(진입 1·보류 4), 포지션·스냅샷 반영, over_cap·duplicate 기록 |
| SC-2 스위치 off → 건너뜀·LLM 0 | ✅ | E2 회차 #3 `skipped(DISABLED)`, 구간 ai_run 0 |
| SC-3 리포트 수치 = 도구 결과 | ⚠️ | E3 수치 973: 근거에 그대로 819 · 근거로 계산 146 · 대략 구간 8 · **근거 없는 수치 0**. 계산식 44 중 4 소오차(최대 0.22%p) |
| SC-4 손절·목표 → 청산·거래·성과·저널 | ✅ | E4 stop 청산 -3.85%, 매도 판단, 저널 1, 원칙 후보 4 |
| SC-5 활성 원칙 → 매수 판단 입력 | ✅ | E5 `principles_used=[4]` (판단 3건) |
| SC-6 권한 없음 → 메뉴 없음·403 | ✅ | E6 403 `MA_FORBIDDEN`, `AppSidebar.tsx` can_view 조건 |
| SC-7 빌더 지침 변경 → 다음 분석 반영 | ✅ | E7 리포트 5건 기술 섹션 모두 표식 포함 |
| SC-8 의존 방향 테스트 | ✅ | `tests/contracts/test_market_analysis_isolation.py` I1~I6 — 이번 회귀에서 통과 |

**7/8 충족 · 1 부분.**

### 11.3 회귀

| 대상 | 결과 | 기준선 |
|---|---|---|
| 시장 분석 백엔드(`-k market_analysis`) | 339 passed | — |
| 백엔드 전체 | 61 failed · 13,803 passed | 61 (master 55 + blueprint 6) — 같은 파일들, 수정 영역(llm_model·agent_run·mcp_registry·market_analysis) 실패 0 |
| 프론트 전체 | 10 failed · 2,249 passed (5 파일) | 10 (ChatPage·CreateCollectionModal·UpdateScopeModal×6·DatasetsTab·KnowledgeBaseDetailPage) — 동일 |

### 11.4 Gap 목록

**🟡 Important**

| # | 확신도 | 위치 | 설계 | 실제 |
|---|:-:|---|---|---|
| G1 | 95% | `application/market_analysis/evidence.py` | SC-3 불일치 0, Design §1.1-5 근거 없는 숫자 금지 | 재무 증감액·증감률을 에이전트가 계산 → 4/44 소오차. 근거 블록에서 결정론으로 미리 계산하면 0 |
| G2 | 100% (주 세션 확인) | `idt_front/src/types/marketAnalysis.ts:428-433` ↔ `idt/src/domain/market_analysis/round.py:24-28` | §9.4 건너뜀 사유 한글 표시 | 서버 값 `DISABLED·WEEKEND·HOLIDAY·BUSY`(대문자), 라벨 키 소문자 → 화면에 원래 코드가 그대로 보임. MSW 목(`marketAnalysisMocks.ts:264`)도 소문자 `'holiday'` 라 테스트가 가림 |

**🔵 Minor**

| # | 확신도 | 위치 | 내용 |
|---|:-:|---|---|
| G3 | 85% | `ReportDetail.tsx:47-64` | 머리 사실의 "신호 값"(`signals[].values`) 미표시 — 규칙명 배지만 |
| G4 | 95% | `index.tsx:41`, `App.tsx:91` | 탭·상세 선택이 URL 이 아니라 상태 — 새로고침·링크 공유 시 대시보드로 (§9.1·§15) |
| G5 | 90% | `test_account_policies.py:36-48` | U5 경계값 테스트 없음 (이전 M1) |
| G6 | 85% | `verdict_parser.py:25-34` | `"NaN"` 가 InvalidOperation 으로 새어 나감, `"Infinity"` 통과 (이전 M2) |
| G7 | 90% | `adapters/market_tools.py:79` | server_finder 예외가 try 밖 (이전 M5) |
| G8 | 80% | `domain/market_analysis/round.py:183-193` | failed 재시도가 하루 상한 계산 밖 (이전 M7) |
| G9 | 80% | `market_analysis_router.py:140` | PUT /settings 에 enabled 없으면 기본 False — 꺼지는 쪽이라 안전, 프론트는 항상 보냄 |
| G10 | 확인 필요 | agent_mcp dart·perplexity | 시그니처는 §8.1 과 일치. E1 섹션 6/6 done 으로 실왕복 간접 확인 |

### 11.5 문서만 고치면 되는 것 (코드가 진실)

| # | 설계서 위치 | 고칠 내용 |
|---|---|---|
| D1 | 머리말·Version History | Status·버전 표에 v1.1(§7.7)·v1.2(§7.8) |
| D2 | §3.3 | `run_trigger`, `run_as_user_id VARCHAR(100)`, `ma_decision.confidence`, `ma_journal.raw_answer`, position 시각·인덱스, regime.created_at |
| D3 | §4 포트 표 | 실제 포트 이름(AgentRunner·MarketTools·PermissionCodesReader+AccessPolicy·StructuredExtractor)과 Store 포트들, session_key 없음 |
| D4 | §16.1 파일 구조 | domain·application·infra 실제 파일 분할 |
| D5 | §16.3 module-8 | 라우터 15 → 18 |
| D6 | §5.1·§5.3 | run-now 202 `{round_id}`, 503 `MA_UNAVAILABLE`, PUT role-agents `{mapping}`, PATCH 응답, 목록 `{items,total,page,size}` |
| D7 | §5.2 dashboard 예시 | regime·equity·last_round 실제 모양 |
| D8 | §9.4 설정 | 실행자 ID 입력·MCP 목록/ID 입력 (§7.6) |
| D9 | §11 Security·Plan §4.1 | 체크박스 갱신 |
| D10 | §1.3 Q3 | 섹션 모델 → §7.1(플랫폼 기본 모델) 주석 |

### 11.6 실측 중 고친 코어 결함 (이 사이클에 포함, 설계서 §7.8)

| 결함 | 수정 | 테스트 |
|---|---|---|
| 단가 PATCH 가 DB 에 저장 안 됨 | `LlmModelRepository.update()` 단가 3필드 | `test_llm_model_repository.py::test_update_persists_pricing` |
| 스냅샷 모델명 매핑 실패 → 비용 0 | `ModelNameResolver` 날짜 꼬리 제거 대체 | `test_model_name_resolver.py::TestDatedSnapshotFallback` 4개 |
| MCP 설명 상한 2,000 | 10,000 | `test_policies.py` 3개 |

### 11.7 권장

1. G2 (작고 화면에 바로 보임) — 라벨 키 대문자 + 목을 서버 값으로
2. G1 — 재무 증감 결정론 계산으로 SC-3 을 0 으로
3. D1~D10 문서 일괄 갱신
4. G3~G9 는 기록 또는 후속 사이클

## 12. Act-2 결과 (2026-11-26, 사용자 결정: Important 2건 + 문서 갱신, Minor 기록만)

| Gap | 결과 | 테스트 |
|---|---|---|
| G1 | 재무 증감액·증감률을 `evidence.financial_changes()` 가 결정론 계산, 근거 블록 앞에 `[계산 dart_financials]` 로 싣고 직접 계산 금지 명시. 전기 0·흑자↔적자 전환은 "계산 안 함" | `test_evidence.py` +3 (실측 오차 사례 고정) |
| G2 | `ROUND_SKIP_LABELS` 키를 서버 값(대문자)으로, MSW 목도 서버 값으로 | `MarketAnalysisPage/index.test.tsx` |
| D1~D10 | 설계서 v1.3 — 오래된 절에 §7.9 안내, §7.9 에 실제 컬럼·포트·파일·API 모양, Security 체크, Q3, module-8 18개, 버전 표 1.1~1.3 | — |

시장 분석 백엔드 342 passed, 프론트 시장 분석 28 passed. G1 의 효과(SC-3 계산 오차 0)는 다음 회차 실측에서 확인한다 — 새 계산 블록은 다음 분석부터 섹션에 들어간다.

수정 후 예상: Functional 96%·Contract 100% → 정적 공식 ≈ 97.8%, 실측 포함 ≈ 95.9% (SC-3 은 다음 실측 전까지 ⚠️ 유지).

**재실측 (회차 #7, Act-2 반영 백엔드)**: 리포트 #12 수치 222 = 근거 원문 182 + 코드 계산값과 일치하는 증감 39 + 대략 구간 1, 계산식 13 오차 0 → SC-3 ✅. gpt-5.1 실행 9건 모두 단가 적용(리포트 1건 $0.214) → 스냅샷 모델명 수정 실호출 확인. 회차 #6 은 G1 수정 전 코드로 돈 백엔드라 증감률 7개가 틀렸다(재기동 누락) — 기록만.
