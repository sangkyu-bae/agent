# prompt-guard Analysis Report

> **Analysis Type**: Gap Analysis (Design vs Implementation) + Runtime Verification
>
> **Feature**: prompt-guard
> **Project**: sangplusbot (idt 백엔드)
> **Analyst**: 배상규 (gap-detector 정적 분석 + 세션 검증)
> **Date**: 2026-10-12
> **Design Doc**: [prompt-guard.design.md](./prompt-guard.design.md)
> **Plan Doc**: [prompt-guard.plan.md](./prompt-guard.plan.md)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 사용자 채팅 입력이 에이전트 시스템 프롬프트를 덮어쓰거나 유출시키는 직접 프롬프트 인젹션을 현재 아무 계층도 막지 못한다 |
| **WHO** | 1차: 에이전트 소유자/KB 운영자(P2) — 자신이 설정한 지침의 보전. 2차: 일반 대화 사용자 — 예측 가능한 거절 안내. 3차: 운영자 — 차단 시도 추적 |
| **RISK** | 정상 요청의 오차단("앞 내용은 무시하고 다시 요약해줘" 같은 선의의 '무시' 표현) → 규칙은 좁게·애매 구간은 LLM 판정·log-only 모드로 선배포 |
| **SUCCESS** | 공격 코퍼스 탐지율 ≥ 95%, 선의 코퍼스 오차단 0건, 정상 요청 추가 LLM 호출 0회, 규칙 단계 p95 < 5ms, 회귀 `FAILED` 목록 diff 0 |
| **SCOPE** | 이번: 모듈(domain/application/infrastructure) + 두 경로 배선 + 전역 플래그 + 로그/스텝 기록. 제외: 간접 인젹션(문서·도구 결과), 출력 검사, 에이전트별 토글, 관리자 화면 |

---

## Strategic Alignment Check

### Plan Alignment (PRD 없음 — Plan Executive Summary 기준)

| Element | Expected | Status |
|---------|----------|:------:|
| Core Problem (WHY) | 두 채팅 경로의 사용자 입력이 검사 없이 LLM에 도달 | ✅ 두 경로 모두 LLM 호출 전 검사, 차단 시 그래프/에이전트 미생성 |
| Target User (WHO) | P2 소유자 지침 보전, 사용자 예측 가능 거절, 운영자 추적 | ✅ 고정 안내문 + ai_run 스텝 + 구조화 로그 |
| Value Proposition | 정상 요청 지연·비용 변화 0, 프론트·스키마 변경 0 | ✅ PASS 경로 LLM 호출 0(테스트), 마이그레이션·프론트 변경 0 |

### Success Criteria Status (Plan §4.1 DoD)

| # | Criteria | Status | Evidence |
|---|----------|:------:|----------|
| SC-1 | FR-01~FR-15 구현·테스트 통과(TDD) | ✅ | 93 tests passed (`tests/{domain,application,infrastructure}/prompt_guard`, wiring 2, DI 1) |
| SC-2 | 공격 코퍼스 ≥ 60 탐지율 ≥ 95%, 선의 ≥ 50 오차단 0 | ✅ | attacks 76건 PASS 0·규칙 BLOCK ≥ 80%, 나머지 REVIEW→판정기(스모크 3/3); benign 53건 BLOCK 0 (`test_rules.py`) |
| SC-3 | 두 경로 배선: 그래프 미생성·안내문 저장·이벤트 시퀀스·`tools_used=[]` | ✅ | `test_prompt_guard_wiring.py` 양쪽 #8/#12 + Design §8.6 실런 |
| SC-4 | `prompt_guard_enabled=false` 시 기존 테스트 무변경 통과 | ✅ | `test_none_guard_keeps_existing_behavior` ×2, `test_disabled_returns_none`; agent_builder·general_chat 스위트 1229건 통과 |
| SC-5 | 판정기 실 LLM 1회 스모크(양성·음성·메타공격) 기록 | ✅ | Design §8.4 Do 실측 3/3 (gpt-4o) |
| SC-6 | 로컬 서버 두 경로(REST + WS) 수동 재현 | ✅ | Design §8.6: chat REST·agent REST·agent WS 3경로 (1차 결함 1건 수정 후 재확인) |
| SC-7 | 회귀 `FAILED` 목록 master 기준과 동일 | ✅ | 53건, module-1→3→4 모두 동일 |
| SC-8 | Design 문서 작성(규칙·안내문·판정 프롬프트 확정) | ✅ | design.md v0.1 + §8.4/§8.6 실측 추가 |
| SC-9 (Quality) | 신규 모듈 커버리지 ≥ 80%, lint 0, 40줄·중첩 규칙 | ⚠️ | lint: 신규 파일 0(프로젝트 공통 UP042 3건 제외). 커버리지 수치 미측정(테스트 93건이 모든 공개 메서드를 호출) |

**Success Rate**: 8/9 met, 1 partial (커버리지 수치 미측정)

### Decision Record Verification

| Source | Decision | Followed? | Deviation |
|--------|----------|:---------:|-----------|
| [Plan] | 규칙 1차 + LLM 2차(REVIEW만) | ✅ | — |
| [Plan] | 차단 + 고정 안내문, 일반 답변 형태로 이력 저장 | ✅ | — |
| [Plan] | 판정 모델 = 레지스트리 is_default | ✅ | 판정기는 application 클래스 대신 도메인 포트 `UtilityLLMProviderPort`에 의존(더 엄격) |
| [Plan] | fail-open | ✅ | timeout 경고에 `exception=` 누락(Gap 4) |
| [Plan] | 두 경로 배선 + 전역 플래그 | ✅ | — |
| [Design] D1 | 역할 탈취 REVIEW, 탈옥 토큰 결합 시 BLOCK | ✅ | 단독 "DAN"은 `dan mode/모드`로 좁힘(선의 이름 충돌) |
| [Design] D2 | `guard_blocked` 참일 때만 | ✅ | — |
| [Design] D3 | 모드는 서비스 `enforced`로 수렴 | ✅ | — |
| [Design] D4 | 공급자 None → JudgeUnavailable → fail-open | ✅ | 이름 `JudgeUnavailableError`(코드베이스 관례) |
| [Design] D5 | 가드 위치(RUN_STARTED 직후 / 이력 조회 직후·차트 편집 전) | ✅ | — |
| [Design] OQ2 | 차단 턴 컨텍스트 제외 | ⚠️ | turn_index tie 시 정렬 순서 의존(Gap 1) |
| [Design] OQ5 | 스텝 요약에 원문 없음 | ✅ | 실런 output_summary 확인 |

---

## 1. Analysis Overview

### 1.1 Purpose
Design(§3·§4·§8·§9·§12)과 구현·테스트의 정합성을 정적 3축(구조·기능·계약)으로 측정하고, 런타임 증거(테스트 93건 + 인프로세스 실런 3경로)로 보강한다.

### 1.2 Scope
- Design: `docs/02-design/features/prompt-guard.design.md`
- 구현: `idt/src/{domain,application,infrastructure}/prompt_guard/`, `config.py`, `api/main.py`, `agent_builder/run_agent_use_case.py`, `general_chat/use_case.py`
- 테스트: 13 파일 + 코퍼스 3 + DI 1
- 방법: gap-detector 정적 분석 → 세션에서 Gap 1·4 코드 재확인 → 테스트 재실행

---

## 2. Gap Analysis

### 2.1 Structural (60/61 = 98.4%)

| 항목 | 상태 |
|------|------|
| 신규 src 11 파일, 수정 5 파일, 테스트·픽스처 13 파일 | ✅ 전부 존재 |
| §3 VO·정책·포트·상수 21 심볼 | ✅ (DEFAULT_RULES는 Design 14 + `ko.leak.02` 1 추가) |
| §4.3 config 5키·기본값 | ✅ `config.py:338-349` |
| §4.4 DI + 두 유스케이스 주입 | ✅ `main.py:865-905`, `:2666`, `:3181` |
| `.env.example` 5키 | ❌ bkit 쓰기 정책으로 미반영 (수동 추가 필요) |

### 2.2 Functional Depth (46.5/48 = 96.9%)

| Design 섹션 | 점수 | 비고 |
|-------------|:----:|------|
| §4.1 서비스 흐름·fail-open 4종·log_only·FR-12 로그 | 6/6 | REVIEW→benign도 info 로그(additive) |
| §4.2 판정기 strict 스키마·태그 격리·None→Unavailable·체인 캐시 | 6/6 | 시스템 프롬프트가 메타공격도 명시 |
| §4.4 DI 킬스위치·judge 토글·조립 실패 None·싱글톤 | 5/5 | — |
| §4.5 에이전트 배선 | 7.5/8 | OQ2 제외가 turn tie 정렬에 의존(Gap 1) |
| §4.6 일반 채팅 배선 | 6/6 | `_maybe_build_charts(history)`는 원본 사용 — 차단 턴에 스냅샷 없어 무해 |
| §4.7 이벤트 계약 | 2/2 | — |
| §3.2 규칙 카탈로그 | 2.5/3 | 패턴 확장 ~10건이 docstring·Design 표에 미기록(Gap 2) |
| §3.3 정책 + §6 오류표 | 11.5/12 | timeout 경고 `exception=` 누락(Gap 4) |

### 2.3 Contract — FR 역추적 (14.5/15 = 96.7%)

| FR | 구현 | 테스트 | 상태 |
|----|------|--------|:----:|
| FR-01 정규화 | policies.py:42-53 | test_normalization ×5, test_rules zero-width | ✅ |
| FR-02 BLOCK 규칙 | rules.py:32-114 | test_rules 대표 4 + 코퍼스 | ✅ |
| FR-03 REVIEW만 판정 | service.py:63-108 | test_service #1~3 | ✅ |
| FR-04 is_default·strict | llm_judge.py:25-77, main.py:894 | test_llm_judge 스키마 3 + 실 LLM 스모크 | ✅ |
| FR-05 `<user_input>` 격리 | prompts.py | test_llm_judge 프롬프트 2 + 스모크 #3 | ✅ |
| FR-06 fail-open | service.py:77-108 | timeout·exception·unavailable 3 | ✅ (timeout kwarg 결함은 Gap 4) |
| FR-07 차단 시퀀스 | run_agent 547-579, general_chat 371-396 | wiring #8/#12 | ✅ |
| FR-08 결정적 안내문 | policies.py:28-32 | wiring answer == NOTICE | ✅ |
| FR-09 사용자 메시지 저장 | run_agent :301, general_chat :374 | wiring roles/turn | ✅ |
| FR-10 킬스위치 None | main.py:869-883 | DI 4 + none_guard ×2 | ✅ |
| FR-11 log_only | policies.py:102, service.py:42-48 | policy·service·wiring 3 | ✅ |
| FR-12 구조화 로그 | service.py:126-156 | block 로그 키·스니펫 ≤200 | ⚠️ `judge_verdict`·`judge_latency_ms` 미단언(Gap 6) |
| FR-13 ai_run 스텝 | run_agent 495-521 | wiring #14 + 실런 | ✅ |
| FR-14 `source` 인자 | interfaces.py, schemas.py | protocol·source 테스트 | ✅ |
| FR-15 규칙 id·카테고리 | schemas.py:35-43, rules.py | id 형식·tier 테스트 | ✅ |

레이어 규칙(§9): domain stdlib+domain only ✅, application→infrastructure 미참조 ✅, 유스케이스는 `src.domain.prompt_guard`만 ✅ (AST 테스트 5건).

### 2.4 Runtime Verification (100%)

| 레벨 | 결과 |
|------|------|
| 단위·배선·DI·경계 테스트 | 93/93 passed (1 deselected = 실 LLM 마커) |
| 실 LLM 스모크 | 3/3 (Design §8.4) |
| L1 인프로세스 실런 | chat REST 공격·애매·정상, agent REST + run detail 스텝, agent WS 이벤트·이력 — 전부 기대값 일치 (Design §8.6; 1차 500 결함은 `charts: []`로 수정 후 재확인) |
| 전체 회귀 | FAILED 53건 = master 상시 실패 목록, diff 0 |

L2/L3(Playwright)은 프론트 변경 0이라 해당 없음.

### 2.5 Match Rate Summary

```
Structural : 98.4%  (60/61)
Functional : 96.9%  (46.5/48)
Contract   : 96.7%  (14.5/15)
Runtime    : 100%   (93 tests + smoke 3/3 + live 3 paths + FAILED diff 0)
──────────────────────────────────────────────
Overall    : 98.2%  = 98.4×0.15 + 96.9×0.25 + 96.7×0.25 + 100×0.35
```

---

## 3. Gap List

| # | Severity | Conf. | 위치 | 내용 | 수정안 |
|---|----------|:-----:|------|------|--------|
| G-1 | **Important** | 60%→**확인됨** | `policies.py:133`, `conversation_repository.py:83` | `exclude_blocked_turns`가 `turn_index`만으로 정렬. 에이전트 경로의 기존 결함(Design §8.6 발견 2)으로 user/assistant가 같은 turn을 가지면 DB 반환 순서에 따라 안내문이 user 앞에 올 수 있고, 그러면 공격문이 컨텍스트에 남는다 | 정렬 키를 `(turn_index, role==USER ? 0 : 1)`로 — tie 시 user 선행을 강제. 같은 turn의 assistant-먼저 입력 테스트 추가 |
| G-2 | Minor | 90% | `rules.py` docstring, Design §3.2 | `ko.leak.02` 와 패턴 확장 ~10건(원래·지침·filler, `of`·guidelines, `tell`, `(?:^\|\s)`, 니, `pretend that you`, 잊고, 지침·해제, `(previous\|prior) instructions`, `dan mode`)이 SoT 표에 없음 | Design §3.2 표에 ko.leak.02 추가 + docstring 확장 목록 |
| G-3 | Minor | 85% | `idt/.env.example` | PROMPT_GUARD 5키 없음 (bkit 정책) | 수동 추가 |
| G-4 | Minor | 70%→**확인됨** | `service.py:92-96` | timeout 경고에 `exception=` 없음(logging 규칙) | `except TimeoutError as e` + 전달 |
| G-5 | Minor | 80% | `agent_builder/test_prompt_guard_wiring.py` | Design 8.3 #11 후반("새 user turn_index는 원본 길이")을 에이전트 경로에서 미단언 | 차단 이력 + 스트림 실행 후 `save` turn 값 단언 |
| G-6 | Minor | 75% | `test_service.py` | FR-12 `judge_verdict`·`judge_latency_ms`·`mode` 키 미단언 | REVIEW→injection 로그 키 단언 추가 |
| G-7 | Minor | 70% | `main.py:2666, :3181` | 두 팩토리가 `get_prompt_guard()`를 주입하는지 테스트 없음(실런만) | AST/소스 테스트 1건 |
| G-8 | Minor | 60% | `test_module_boundaries.py:74` | 유스케이스 금지 접두에 `src.application.prompt_guard` 누락 | 접두 튜플 확장 |
| G-9 | Minor | 65% | `config.py:338-349` | 소비 지점이 블록 주석 1곳(파일만) — Plan §4.2는 키별 file:line | 키별 주석에 `main.py:_build_prompt_guard` 명기 |
| G-10 | Minor | 60% | `main.py:879`, `service.py:42` | `PROMPT_GUARD_MODE` 오타 → ValueError → 가드 전체 off(warning 1회) | 설계대로지만 위험. error 레벨 로그 또는 `block` 폴백 검토 |
| G-11 | Minor | 50% | `general_chat/use_case.py:161` | `prompt_guard=None` 타입 주석 없음 | `PromptGuardPort \| None` |

기록된 편차(gap 아님): D1, D2, rules.py 정정, `JudgeUnavailableError`, `charts: []`, 도메인 포트 의존, REVIEW→benign info 로그, `GUARD_MODES` 검증, `decide` keyword-only, 단독 "DAN" 비차단, 스모크 마커 `-m llm`.

---

## 4. Code Quality Notes

- 함수 40줄·if 중첩 2단계: 신규 함수 모두 준수(`_log`는 dict 리터럴 포함 31줄).
- 보안: 로그·스텝에 원문 전체 미기록 확인(실런 output_summary). 판정기 system에 메타공격 명시.
- 성능: 규칙 15개 사전 컴파일, PASS 경로 외부 호출 0. REVIEW 비율은 benign 코퍼스 53건 중 REVIEW 약 20%(무시·역할·ignore 류) — 판정기 호출 비용은 운영 로그로 관측 필요.

---

## 5. Recommendation

Match Rate 98.2% ≥ 90% → Report 진행 가능. 단 **G-1은 보안 의미가 있어 Report 전에 수정 권장**(5분 작업: 정렬 키 + 테스트 1건). G-4·G-5·G-6·G-8은 함께 처리하면 10분 내. G-2는 Design 표 갱신. G-3은 수동.

---

## 6. Act-1 결과 (2026-10-12, 사용자 결정: "지금 모두 수정")

| Gap | 처리 | 근거 |
|-----|------|------|
| G-1 | ✅ 수정 | `BlockedTurnPolicy.exclude_blocked_turns` 정렬 키 `(turn_index, user=0/assistant=1)` — tie 에서 user 선행. `test_same_turn_index_tie_still_drops_preceding_user` 추가 |
| G-2 | ✅ 문서 | Design §3.2 에 `ko.leak.02` 행 + 패턴 확장 목록(정정 블록); `rules.py` docstring 확장 목록 |
| G-3 | ⏭ 수동 | `.env.example` 은 bkit 쓰기 정책으로 세션에서 불가 — 사용자 수동 추가 |
| G-4 | ✅ 수정 | `except TimeoutError as e` → `_warn_judge(..., e)` |
| G-5 | ✅ 테스트 | `test_blocked_history_does_not_shift_saved_turn_index` (에이전트 경로, 원본 4건 → 저장 turn 5) |
| G-6 | ✅ 테스트 | `test_review_with_injection_verdict_blocks` 에 `judge_verdict`·`judge_latency_ms`·`mode`·`judge_error` 단언 |
| G-7 | ✅ 테스트 | `test_both_chat_use_cases_receive_prompt_guard_kwarg` — main.py AST 에서 두 생성 호출의 `prompt_guard=get_prompt_guard()` 확인 |
| G-8 | ✅ 테스트 | 경계 테스트 금지 접두에 `src.application.prompt_guard` 추가 |
| G-9 | ✅ 수정 | config 5키 각각에 소비 지점(`main.py get_prompt_guard / _build_prompt_guard`, 인자명) 주석 |
| G-10 | ⏭ 설계 유지 | mode 오타 → 가드 비활성 + warning 1회는 Design §4.4(탈착형 이음매) 그대로. config 주석에 운영 주의 명기. 후속에서 `block` 폴백 검토 가능 |
| G-11 | ✅ 수정 | `prompt_guard: PromptGuardPort \| None = None` + import |

**재측정**: prompt-guard 테스트 96건 통과(+3), 린트 신규 파일 0(UP042 공통 패턴 제외). 전체 회귀 FAILED 53건 — module-4 목록과 완전히 동일(diff 0).

Match Rate 재계산: Structural 98.4%(`.env.example` 1건 잔존) · Functional 100%(G-1·G-4 해소, 48/48) · Contract 100%(FR-12 단언 추가, 15/15) · Runtime 100% → **Overall 99.8%**

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-10-12 | 초안 — gap-detector 정적 분석 + 런타임 증거 통합, G-1·G-4 코드 재확인 | 배상규 |
