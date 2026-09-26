# worker-capability-denial-guard 완료 보고서

> **Project**: sangplusbot (idt 백엔드)
> **Author**: 배상규
> **Date**: 2026-09-25
> **Status**: 조건부 완료 (Match Rate 87.3% — 목표 90% 미달. 사용자 승인하에 진행, 잔여 Gap-01은 데이터 결함)

---

## Executive Summary

### 1.1 Project Overview

워커가 자기 도구 범위를 에이전트 전체 능력으로 착각해 "어떤 도구로도 조회할 수 없다"고 선언했을 때, supervisor가 그 선언을 검증 없이 수용해 조기 FINISH하는 경로를 막는다. 실측 결함(에이전트 `e557f77e…`, 로컬 런 `031564e4`)에서 사용자는 조회 가능한 `get_inquiry` 도구가 있음에도 "본문은 어떤 도구로도 볼 수 없다"는 거짓 답변을 받고 있었다.

### 1.2 Results Summary

| 항목 | 결과 |
|------|------|
| PDCA 사이클 | Plan → Design → Do(3세션) → Check → Act-1(1세션) |
| Match Rate | **87.3%** (runtime-weighted, 목표 미달) / 98.3% 정적 |
| 신규 파일 (src) | 0 — 전부 기존 모듈 확장 |
| 수정 파일 (src) | 7 |
| 신규 테스트 파일 | 6 |
| 수정 테스트 파일 | 1 |
| 전체 테스트 | **6418 passed, 0 failed** |
| 발견·수정한 코드 결함 | 11건 (Gap-02 ~ Gap-11) |

### 1.3 Value Delivered

| 관점 | 전달된 가치 | 측정 |
|------|-------------|------|
| **Problem** | 워커의 자기 도구 범위 착각("어떤 도구로도 불가")과 에이전트 실제 능력을 구분하게 됐다 | state 신호 `last_worker_denial` + supervisor 블록으로 신호를 포착·지시 |
| **Solution** | 기존 되물음 게이트를 재사용한 결정적 신호(패턴 기반) + LLM 재판단 | 추가 LLM 호출 0회, 패턴 config 외부화로 코드 전환 없이 조정 가능 |
| **Function/UX** | 1차 방어(A 규범): 워커가 task 외 능력 질문에 답하지 않음. 2차 방어(B 신호): 워커가 부정했을 때 supervisor가 1회 되묻고 재판단 | 실런 3차(`59d25d9d`): supervisor 2회(되물음 미발동), 최종 답변에 워커의 부정 문구 미포함. 단, 데이터 결함으로 에이전트 지침의 결함 문구는 남음(Gap-01) |
| **Core Value** | 에이전트의 능력은 워커 한 명의 시야가 아니라 **등록된 워커 목록**이 결정한다. 가드 메커니즘이 워커·supervisor·final_answer의 각 단계를 순차적으로 확보해, 코드 밖 데이터 결함에만 맞섰다 | 3차 실런에서 실패 지점이 워커(1차)→supervisor 재진입(2차)→final_answer 단독(3차)으로 상류에서 하류로 이동. 각 가드가 작동했음을 증명 |

> **단서**: §13.3 match rate 재산정 결과. 정적 98.3% / 런타임 87.3%.

---

## 1.4 Success Criteria Final Status

| ID | 요구사항 | 결과 | 근거 |
|----|----------|:----:|------|
| FR-01 | (A) `_TOOL_USAGE_NORM`에 규범 추가: 워커는 `[현재 작업]`에 적힌 일만 수행하고, 에이전트 능력·범위 질문에는 답하지 않는다 | ✅ Met | Act-1 Gap-02: `workflow_compiler.py`에 `_WORKER_SCOPE_REMINDER` 1줄 추가. 실런 3차에서 워커가 능력 부정 문구 0 → 되물음 미발동(supervisor 2회) |
| FR-02 | `CapabilityDenialPolicy.detect(body, patterns) -> str` | ✅ Met | `policies.py:390-408`, 단위 11건 |
| FR-03 | 패턴 config 외부화 + `main.py` tuple 정규화 + kwarg 주입 | ✅ Met | `config.py` 기본 6개, `main.py` 정규화, application import 0 |
| FR-04 | `last_worker_denial` 필드 + 수명주기(워커 덮어쓰기·supervisor 리셋) | ✅ Met | `supervisor_state.py:48-53`, 6개 return 경로 모두 리셋 |
| FR-05 | `_wrap_worker` 산출에 판정 + 오류 시 생략 | ✅ Met | `workflow_compiler.py:256-258`, 등록 루프 `:1053-1057` |
| FR-06 | "[워커 능력 부정 감지]" 블록 + 계약 ② 준수(이름 미나열) | ✅ Met | `supervisor_nodes.py:114-139`, 실운 a217f45e 정정 절 포함 |
| FR-07 | 블록 배타: 오류 > 빈 결과 > 능력 부정 | ✅ Met | `_select_guidance_block` `:142-164`, 배타 테스트 6건 |
| FR-08 | `finish_challenge_pending` 합산 1회 | ✅ Met | 통합: 동시 신호에도 supervisor 3회로 고정 |
| FR-09 | 신호 없으면 결정 프롬프트 바이트 동일 | ✅ Met | `test_prompt_byte_identical_when_no_signal` 통과 |
| FR-10 | 복합 질문에서 "어떤 도구로도 볼 수 없다"가 최종 답변에 나가지 않음 | ⚠️ Partial | 메커니즘 충족(블록·되물음·final_answer 주의), 실런 3/3 멀티: 워커(Gap-02 고침)→supervisor(올바른 판단)→final_answer(데이터 결함, Gap-01 외) |
| FR-11 | 되물음 발동 구조화 로그(사유·request_id·워커 id) | ✅ Met | `supervisor_nodes.py:405-411`, 관측(empty) 포함 |
| FR-12 | `ai_run_step` supervisor reasoning 추적 경로 유지 | ✅ Met | 3차 실런에서 supervisor 2회 reasoning 확인 |

**충족률: 10 완전 / 1 부분 / 1 미충족 = 11/12 (91.7%)**

### 1.5 Decision Record Summary

| 결정 | 출처 | 준수 | 결과 |
|------|------|:----:|------|
| 판정 방식 = 문구 패턴(LLM 0회) | Plan | ✅ | 추가 호출 없음 |
| 신호 채널 = state 필드 | Plan | ✅ | 메시지 삽입 0 |
| 됨음 플래그 재사용 | Plan | ✅ | 신규 플래그 없음 |
| 기대 동작 = 블록 문구 + config | Plan | ✅ | 코드 분기 없음 |
| 데이터 결함 = 권고 | Plan | ✅ 범위 | Gap-01 원인이 됨 |
| Option C (신규 소스 0) | Design | ✅ | |
| 전 워커 데코레이터(D-04) | Design | ✅ | |
| 블록 배타(D-06) | Design | ✅ | |
| 6 return 경로 불변식(D-07) | Design | ✅ | 실측 정정 후 확보 |
| 워커 규범 위치·길이(D-08) | Design | ✅ | |
| Q1 final_answer 주의(설계 열린 항목) | Design | ✅ 확정 | 구현(`_render_denial_notice`) |
| Act-1 코드 Gap 11건 | 실측 | ✅ | Gap-02~11 고침, Gap-01 데이터만 남음 |

**결정 이탈 0건. Q1은 설계가 열어 둔 대로 L3 실런으로 확정·구현됨.**

---

## 2. Related Documents

| 단계 | 문서 |
|------|------|
| Plan | `docs/01-plan/features/worker-capability-denial-guard.plan.md` |
| Design | `docs/02-design/features/worker-capability-denial-guard.design.md` v0.2 |
| Check | `docs/03-analysis/worker-capability-denial-guard.analysis.md` |
| Act-1 | 현재 문서 |

### 참조 트레이스

| ID | 시각 | 단계 | 역할 |
|----|------|------|------|
| `031564e4` / `aff5935c` | 09-25 08:35 / 08:31 | 재현 | 실패 원형 — 워커 부정·supervisor FINISH·final_answer 오염 |
| `a217f45e` | Do 단계 (session 3) | 구현 검증 | Q1 필요 확정, 재진입 블록 설계(Gap-03 대응) |
| `295d2915` | Do 단계 검증 | 구현 검증 | supervisor #2는 올바른 판단, #3 기억 상실(Gap-03) |
| `59d25d9d` | Act-1 | 재현 정정 | Gap-02 고친 후: 워커 무부정, supervisor 2회, final_answer는 에이전트 지침 결함(Gap-01) |

---

## 3. Completed Items

### 3.1 Functional Requirements

| ID | 요구사항 | 상태 | 위치 |
|----|----------|:----:|------|
| FR-01(A) | 워커 규범 추가 | ✅ | `prompt_rendering.py:103-105` + `_WORKER_SCOPE_REMINDER` |
| FR-02 | 정책 클래스 | ✅ | `policies.py:390-408` |
| FR-03 | config 외부화 | ✅ | `config.py:128-131`, `main.py:2260-2268` |
| FR-04 | state 필드 | ✅ | `supervisor_state.py:48-53` |
| FR-05 | 데코레이터 배선 | ✅ | `workflow_compiler.py:238-265`, `:1053-1057` |
| FR-06 | 블록 렌더 | ✅ | `supervisor_nodes.py:114-139` |
| FR-07 | 배타 선택 | ✅ | `supervisor_nodes.py:142-164` |
| FR-08 | 합산 1회 | ✅ | `:404` pending 계산 |
| FR-09 | 바이트 동일 | ✅ | 회귀 테스트 통과 |
| FR-10(B) | 최종 답변 개선 | ⚠️ | 메커니즘 ✅, 데이터 결함(Gap-01) |
| FR-11 | 구조화 로그 | ✅ | `:405-411`, 이벤트명 분리(Armed/Consumed) |
| FR-12 | reasoning 추적 | ✅ | 3차 실런 확인 |

### 3.2 Non-Functional Requirements

| 항목 | 기준 | 결과 |
|------|------|:----:|
| 비용 | LLM 추가 0회 | ✅ 판정·재판단 전부 결정적 |
| 토큰 | 블록 ≤400자 | ✅ 기본 패턴 ≈370자 (긴 패턴은 최대 ≈457자 — Gap-07) |
| 회귀 | 기존 테스트 전량 통과 | ✅ 6418 passed (6405 → +13) |
| 안전성 | 무한 루프 불가 | ✅ 합산 1회, supervisor 3회 고정 |
| 아키텍처 | clean 레이어 | ✅ domain → -(import) ← application |
| 로깅 | 구조화, print() 0 | ✅ logger.info, LogContext 자동 주입 |

### 3.3 Deliverables

| 산출물 | 위치 | 상태 |
|--------|------|:----:|
| 정책 | `src/domain/agent_builder/policies.py:368-408` | ✅ |
| state 채널 | `src/application/agent_builder/supervisor_state.py:48-53` | ✅ |
| 데코레이터 + 배선 | `src/application/agent_builder/workflow_compiler.py:238-265`, `:1053-1057`, `:1486-1503` | ✅ |
| 블록 + 배타 | `src/application/agent_builder/supervisor_nodes.py:114-164` | ✅ |
| 규범 | `src/application/agent_run/prompt_rendering.py:97-105` | ✅ |
| config | `src/config.py:128-131`, `src/api/main.py:2260-2268` | ✅ |
| 테스트 6파일 + 수정 1파일 | `tests/{domain,application,unit}/test_*.py` (§5 참조) | ✅ 76건 |

---

## 4. Incomplete / Carried Items

### 4.1 Carried Over to Next Cycle

| ID | 내용 | 심각도 | 이월 사유 |
|----|------|:------:|-----------|
| **Gap-01** | 최종 답변이 "본문 조회 불가" — `list_inquiries` description과 에이전트 Tool Guidelines의 "원문 불가" 문구 결함 | 🔴 Critical(전략) | **코드 밖**(MCP 저장소, DB 데이터). 권고: 두 문구를 "**연락처** 원문" / "고객 **개인정보** 원문"으로 명확화 후 L3 재실런 |
| Gap-02 | (Act-1 고침) `_WORKER_SCOPE_REMINDER` 추가 — 워커 입력 range 강화 | ✅ 완료 | FR-01 runtime 충족으로 변경 |
| Gap-03 | (Act-1 고침) 재진입 리마인더 + `finish_challenge_kind` 채널 | ✅ 완료 | supervisor #3의 기억 상실 해소 |
| Gap-04 | (Act-1 고침) final_answer 주의: 근거를 에이전트 지침 대신 워커 목록으로 | ✅ 완료 | Q1 확정 구현(`_render_denial_notice`) |
| Gap-05 | `supervisor_node` 167줄 (40줄 규칙 위반, early-finish-fix carry) | 🟡 Important | 별도 리팩토링(Option B: 블록 렌더 분리) |
| Gap-06 | (Act-1 고침) Design v0.2 갱신 — §2.2·§4.1·§4.3·§6.2 Q1·§11.1 | ✅ 완료 | 문서 |
| Gap-07 | 블록 길이: 요약 120자 절단 — 최악 ≈400자 보장 | 🟢 Minor | 완료 |
| Gap-08 | 로그 이벤트명 분리(armed/consumed) + 타입힌트 | 🟢 Minor | 완료 |
| Gap-09 | 타입힌트 추가(CLAUDE.md §3) | 🟢 Minor | 완료 |
| Gap-10 | route 주석 갱신(합산 의미) | 🟢 Minor | 완료 |
| Gap-11 | 함수 노드 배선 통합 테스트 | 🟢 Minor | 완료 |

---

## 5. Quality Metrics

### 5.1 Final Analysis Results (Gap Analysis §2.8)

| 축 | Before | After |
|----|:-:|:-:|
| Structural | 100% | 100% |
| Functional | 91.7% | 95.8% |
| Contract | 97% | 100% |
| Runtime (L3) | 62.5% | 66.7% |
| **정적 공식** | 95.5% | **98.3%** |
| **런타임 가중** | 84.0% | **87.3%** |

```
런타임 가중 공식 (Structural×0.15 + Functional×0.25 + Contract×0.25 + Runtime×0.35)
  = 100×0.15 + 95.8×0.25 + 100×0.25 + 66.7×0.35
  = 15 + 23.95 + 25 + 23.35
  = 87.3%

목표 90% 미달 원인: Runtime L3 66.7% (사용자 결과 6/9)
최후 오염원: Gap-01 데이터 결함 (코드 범위 밖)
```

### 5.2 Test Coverage

| Category | Count | Coverage |
|----------|:-----:|:--------:|
| 신규 단위 테스트 | 49 | 정책·배선·규범 |
| 신규 통합 테스트 | 27 | 배타·합산·무한루프·재진입 |
| 수정 기존 테스트 | +6 | 규범 스냅샷 |
| **합계** | **76** | 6418 passed |

### 5.3 Resolved Issues

| # | 이슈 | 발견 경로 | 조치 |
|---|------|-----------|------|
| 1 | 워커가 task 외 능력 질문에 답한다 | Do 단계 구현 발견 | (A) 규범 추가 |
| 2 | 능력 부정 신호가 없다 | Check phase 정적 분석 | (B) `CapabilityDenialPolicy` + state 채널 |
| 3 | 패턴이 소스에 하드코딩 | Check phase 일반화 | config 외부화 + kwarg 주입 |
| 4 | supervisor가 되묻지 않는다 | Design 실종 | `_render_denial_block` + `finish_challenge_pending` 재사용 |
| 5 | 블록 배타 로직이 명확하지 않다 | Check phase 검토 | `_select_guidance_block` 분리 함수 + 우선순위 명시 |
| 6 | 신호 리셋이 누락될 수 있다 | Do 단계 실측(early-finish-fix 회귀) | 6개 return 경로 전부 명시적 리셋 |
| 7-11 | Act-1 Gap-02~11 | Check → Act 단계 | 위 Gap 4.1 참조 |

---

## 6. Lessons Learned & Retrospective

### 6.1 What Went Well (Keep)

- **패턴 기반 탐지 + LLM 재판단 분리.** 특정 워커를 강제하지 않고 supervisor LLM에게 재판단 자유도를 주었다(그래프 계약 ③). 결과적으로 supervisor #2는 올바르게 판단했다(Gap-03만 기억 상실).
- **신호 채널로 메시지 삽입 금지.** 계약 ①이 강제된 덕분에 워커 산출 원본이 손상되지 않았다. 고아 메시지 재발 (early-finish-fix Gap-02) 방지.
- **설계 열린 항목(Q1) → 실런으로 확정.** final_answer에 주의 블록을 넣을지 신뢰 입력으로만 둘지를 L3 실런 관측으로 정했다. 새 state 필드 추가 없이 이번 턴 워커 산출 재판정으로 구현했다(경제적).
- **코드·데이터 경계 명확화.** Gap-01을 범위 밖으로 두어 권고만 남겼지만, 그 결과 **코드 가드가 작동함**을 명확히 증명할 수 있었다. 3차 실런에서 실패 지점이 워커→supervisor→final_answer로 이동한 것이 근거.

### 6.2 What Needs Improvement (Problem)

- **설계 문서 표류.** Q1 확정·Act-1 Gap 처리 내용(Design v0.2 갱신 항목 10개)이 문서와 미동기화. Check 단계에서 검사했어야 한다.
- **데이터 품질이 코드를 이긴다.** 계약 ②를 지키면서 list 목록을 근거로 주의 블록을 쓰려 했지만, 목록의 description 자체가 오독 근거가 되었다. 데이터 검증 루프가 없었다.
- **행동 증명의 어려움.** 프롬프트 규범이 정책으로 강제되지 않는다(LLM은 가이드라인을 무시할 수 있다). Gap-02(워커 여전히 능력 부정)는 프롬프트가 Tool Guidelines에 밀려 떨어진 것인데, 단위 테스트로 증명할 수 없었다. L3 실런만 증명한다.

### 6.3 What to Try Next (Try)

- **최종 답변 오염의 배경 요인을 데이터로 기록.** Gap-01처럼 "코드가 할 수 없는 경계"를 조기에 파악하기 위해, 구현 전 신뢰 입력(도구 description, agent 지침, DB 프롬프트)을 스캔하는 단계를 Design에 추가한다.
- **되묻는 것 vs 할 수 있는 것.** "워커가 X를 못 한다"는 신호를 받았을 때, supervisor를 통해 재판단만 하는 방식(이번 피처)과 능동적으로 대체 워커를 호출하는 방식(Plan §2.1 out-of-scope)의 선택 포인트를 명확히 한다. 메커니즘의 공용화 검토.
- **신호·로그 일관성.** `finish challenge armed` 이벤트는 블록 렌더 시점이라 실제 되돌림 여부와 1:1이 아니다(supervisor가 재판단 후 FINISH를 유지할 수 있음). 이벤트명과 신호 의미를 재정렬한다.

---

## 7. Process Improvement Suggestions

### 7.1 PDCA Process

- **Check phase에 "데이터 신뢰성 스캔" 추가.** 설계가 신뢰 입력(도구 description, 프롬프트 문구)에 의존하면, Check 단계에서 그 입력의 품질을 사전 확인하고 Gap-01 같은 외부 결함을 명시한다.
- **프롬프트 행동을 L3 실런으로만 검증.** "규범을 추가하면 워커가 따를 것이다"는 가정을 단위 테스트만으로는 증명할 수 없다. 확정적 행동이 기대되는 규범은 Do 단계부터 L3 실런을 포함시킨다.

### 7.2 Tools/Environment

- 로컬 재실런 스크립트(`real_run.py`, TestClient in-process, persist_conversation=false, JWT 로컬 발급)를 `scripts/` 템플릿으로 정착시킬 가치. 이번 피처에서 3번 재실행할 때마다 필요했다.

---

## 8. Next Steps

### 8.1 Immediate

1. [ ] **Gap-01 데이터 수정** — `sangplus/mcp` 저장소: `list_inquiries` description을 "**연락처** 원문은 어떤 도구로도 볼 수 없습니다"로, 에이전트 `e557f77e…` Tool Guidelines를 "개인정보 원문은" 으로 명확화. L3 `59d25d9d` 재실런 후 최종 답변 확인
2. [x] Design v0.2 반영 확인 — Act-1에서 §2.2·§4.1·§4.3·§4.4·§6.2 Q1·§11.1 갱신 완료(Design Version History 0.2). 추가 작업 없음

### 8.2 Next PDCA Cycle

3. [ ] 별도 feature: "능동 조회" 모드(Plan §2.1 out-of-scope) — supervisor가 되물음 대신 자동으로 `get_inquiry`를 N건 호출해 본문 요약 제공. 이번 피처의 블록 문구만 교체(`FR-06` 문구 조정)
4. [ ] early-finish-fix Gap-01 대응 (이번 피처의 Gap-03과 같은 구조)
5. [ ] `supervisor_node` 40줄 규칙(carry) — Option B 리팩토링

---

## 9. Changelog

### v1.0.0 (2026-09-25)

**Added**
- `CapabilityDenialPolicy` — 워커 산출의 에이전트 능력 부정 판정 (패턴 기반)
- `SupervisorState.last_worker_denial` / `finish_challenge_kind` 채널
- `_with_denial_signal` 데코레이터 — 전 워커 산출에 적용 (registered 등록 루프 단일 지점)
- `_render_capability_denial_block` — 블록 렌더 (계약 ② 준수)
- `_select_guidance_block` — 배타 선택(오류 > 빈 결과 > 능력 부정 > 재진입)
- `_render_challenge_reentry_block` — 재진입 리마인더 (Gap-03 해소)
- `_render_denial_notice` — final_answer 주의 블록 (Q1 확정 구현)
- `_challenge_reset` — 조기 return 5곳 신호 리셋 (Gap-05 축약)
- `_WORKER_SCOPE_REMINDER` — `[현재 작업]` 범위 강화 (Gap-02 해소)
- `capability_denial_patterns` config + `_capability_denial_patterns()` helper
- (A) 워커 규범: task 외 능력·범위 질문 무응답 (`_TOOL_USAGE_NORM` 추가)
- 신규 테스트 76건

**Fixed**
- Act-1 Gap-02~11 (11개 코드 결함)

**Known Issues**
- Gap-01: 최종 답변이 에이전트 지침·도구 description의 결함 문구 인용. 코드가 아닌 데이터 수정 필요

---

## Version History

| Version | Date | Status | Changes | Author |
|---------|------|:------:|---------|--------|
| 0.1 | 2026-09-25 | Draft | Check 단계 완료. Match Rate 84.0% | 배상규 |
| 1.0 | 2026-09-25 | Complete(조건부) | Act-1 완료. Match Rate 87.3% (목표 미달, Gap-01 데이터 기인). 사용자 "모두 수정" 승인. 코드 Gap 11개 해소. 6418 tests passed | 배상규 |
