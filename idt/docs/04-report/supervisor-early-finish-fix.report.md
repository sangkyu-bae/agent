# supervisor-early-finish-fix 완료 보고서

> **Project**: sangplusbot (idt 백엔드)
> **Author**: 배상규
> **Date**: 2026-09-17
> **Status**: 조건부 완료 (Match Rate 87% — 목표 90% 미달, 이월 항목 있음)

---

## Executive Summary

### 1.1 Project Overview

수집 워커가 빈 결과를 냈을 때 supervisor가 "데이터 자체가 없음"으로 단정하고 남은 수단을 시도하지 않은 채 종료하던 문제를 고쳤다. LangSmith 트레이스 `01a0a82b`에서 실증된 결함으로, 사용자는 실제로 조회 가능한 저축은행 금리 표 대신 "데이터가 없습니다" 답변을 받고 있었다.

### 1.2 Results Summary

| 항목 | 결과 |
|------|------|
| PDCA 사이클 | Plan → Design → Do(3세션) → Check |
| Match Rate | **87%** (Structural 100 / Functional 89 / Contract 95 / Runtime 75) |
| 신규 파일 (src) | 0 — 전부 기존 모듈 확장 |
| 수정 파일 (src) | 6 |
| 신규 테스트 파일 | 5 |
| 전체 테스트 | **5,819 passed, 0 failed** |
| 발견·수정한 잠재 결함 | 무한 루프 3경로, 워커 전달 차단 1건, 과탐 패턴 1건 |

### 1.3 Value Delivered

| 관점 | 전달된 가치 | 측정 |
|------|-------------|------|
| **Problem** | "못 찾았다"와 "아직 안 해봤다"를 시스템이 구분하게 됐다 | 빈 결과가 `last_worker_error`와 별개 신호로 state에 오름 |
| **Solution** | 되물음 1회 게이트가 프로덕션에서 실제 동작 | 트레이스 `01a0ae68` supervisor #6→#7 되돌림 확인 |
| **Function/UX** | 목표 플로우(`browser_open→snapshot→click→extract`)가 실행되어 사용자가 실제 금리 표 수신 | 트레이스 `01a0ae7c` — 답변 9,826자, BNK 3.80% 등 실데이터 |
| **Core Value** | 워커가 도구 결과를 삼키지 않고 전달하도록 규범 확립 | 재검증 3런 모두 도구 결과 전달 확인 |

> **단서**: 위 Function/UX 가치는 **재현율 1/3**이다. 완전 성공 1회, 부분 1회, 실패 1회. §4.1 참조.

---

## 1.4 Success Criteria Final Status

| ID | 요구사항 | 결과 | 근거 |
|----|----------|:----:|------|
| FR-01 | 워커의 에이전트 전체 능력 부정 금지 | ✅ Met | D-v2로 재작성 후 3런 모두 도구 결과 전달 확인 |
| FR-02 | `EmptyResultPolicy` 구조적+패턴 판정 | ✅ Met | 단위 11건 |
| FR-03 | 패턴 설정값 외부화 | ✅ Met | `config.py` + `main.py` 정규화 주입 |
| FR-04 | state 신호, 워커 세팅·supervisor 리셋 | ✅ Met | 프로덕션 블록 렌더 3회로 역산 |
| FR-05 | "[수집 결과 확인 필요]" 블록 | ✅ Met | 트레이스 supervisor #4·#5·#6 |
| FR-06 | 미해소 FINISH 1회 되돌림 | ✅ Met | #6→#7 되돌림, 2번째 FINISH 통과 |
| FR-07 | 1회 상한 보장 + 한도 가드 우선 | ✅ Met | 무한 루프 3경로 수정, 회귀 4건 |
| FR-08 | 신호 없으면 프롬프트 바이트 동일 | ✅ Met | 전용 테스트 |
| FR-09 | 되물음을 구조화 로그로 기록 | ❌ Not Met | **미구현 — 이월** |

**충족률: 8/9 (89%)**

### 비기능 요구사항

| 항목 | 기준 | 결과 |
|------|------|:----:|
| 비용 | 빈 결과 판정에 LLM 호출 0회 | ✅ 결정적 판정만 |
| 토큰 | 블록 400자 이내, 발동 시에만 | ✅ |
| 회귀 | 기존 테스트 전량 통과 | ✅ 5,819 |
| 안전성 | 되물음 무한 루프 불가 | ✅ (2회 실패 후 확보) |
| 아키텍처 | domain → 상위 참조 없음 | ✅ |

---

## 1.5 Decision Record Summary

| 결정 | 출처 | 준수 | 결과 |
|------|------|:----:|------|
| D+C 먼저, A는 별도 피처 | Plan Q1 | ✅ | 리스크 격리 성공 — A 미착수 상태에서도 D+C 검증 가능했다 |
| 1회 되물음 (결정적 차단 아님) | Plan Q2 | ✅ | 무한 루프를 구조적으로 막았고 프로덕션에서 정상 동작 |
| 구조적 1차 + 패턴은 설정값 | Plan Q3 | ✅ | 설계 시 기록한 대로 **실효 탐지는 패턴이 담당**. 구조적 신호는 보완재 |
| 위키 절차만 추적 | Plan Q4 | ✅ | 범위 유지 |
| Option C (state 신호 + route 되돌림) | Design | ✅ | 그래프 노드 추가 없이 달성. 되물음이 트레이스에 `supervisor` 2회로 드러나 진단 가능 |
| 4개 팩토리를 단일 데코레이터로 (D-06) | Design | ✅ | `_wrap_step`이 tracker 미배선 시 원본 반환하는 함정을 회피 |
| wiki 워커 판정 제외 (Q-01) | Do | ✅ | 짧은 위키 본문의 구조적 오탐을 사전 차단 |

**결정 이탈 0건.** 다만 설계 **판단 오류** 2건이 실행 중 드러났다(§6.2).

---

## 2. Related Documents

| 단계 | 문서 |
|------|------|
| Plan | `docs/01-plan/features/supervisor-early-finish-fix.plan.md` |
| Design | `docs/02-design/features/supervisor-early-finish-fix.design.md` |
| Analysis | `docs/03-analysis/supervisor-early-finish-fix.analysis.md` |
| 후속 Plan | `docs/01-plan/features/wiki-procedure-completion.plan.md` (미착수) |
| 참조 계약 | `docs/wiki/backend/patterns/supervisor-graph-contracts.md` |

**근거 트레이스**

| ID | 시각 | 역할 |
|----|------|------|
| `01a08b28` | 09-10 | 정상 대조군 (browser 플로우) |
| `01a0a82b` | 09-16 | 결함 재현 |
| `01a0ae68` | 09-17 08:07 | D-v1 회귀 발견 |
| `01a0ae73/79/7c` | 09-17 08:19~08:30 | D-v2 재검증 3런 |

---

## 3. Completed Items

### 3.3 Deliverables

| 산출물 | 위치 |
|--------|------|
| `EmptyResultPolicy` | `src/domain/agent_builder/policies.py` |
| `empty_result_patterns` 설정 | `src/config.py` |
| DI 정규화 헬퍼 | `src/api/main.py:_empty_result_patterns()` |
| state 2채널 | `src/application/agent_builder/supervisor_state.py` |
| 블록 렌더 + 플래그 수명주기 + 되물음 라우팅 | `src/application/agent_builder/supervisor_nodes.py` |
| 신호 데코레이터 + 배선 + `route_map` 자기순환 | `src/application/agent_builder/workflow_compiler.py` |
| 워커 규범 (D) | `src/application/agent_run/prompt_rendering.py` |
| 테스트 5파일 (49건) | `tests/domain/agent_builder/`, `tests/application/agent_builder/`, `tests/application/agent_run/` |

---

## 4. Incomplete Items

### 4.1 Carried Over to Next Cycle

| ID | 내용 | 심각도 | 이월 사유 |
|----|------|:------:|-----------|
| **Gap-01** | 되물음을 받고도 supervisor가 브라우저 경로로 가지 않는 경우가 있다 (재현율 1/3) | 🔴 Critical | 코드가 아닌 **LLM 설득력** 영역. 블록 문구 강화만으로 해결될지 불확실해 별도 검증 사이클 필요 |
| **Gap-04 (FR-09)** | 되물음 발동 구조화 로그 미구현 | 🟡 Important | Gap-01 개선 효과를 측정할 수단이므로 다음 사이클 1순위 |
| **Gap-03** | 빈 결과 탐지 대상이 워커 **답변**이지 도구 **원본**이 아니다 | 🟡 Important | 워커가 요약하며 신호 문구를 빼면 탐지 실패. `_wrap_worker`가 tool 메시지에 접근 가능하므로 `ToolErrorPolicy` 방식으로 전환 검토 |
| **Gap-08** | `supervisor_node` 145줄 (40줄 규칙 위반) | 🟡 Important | 사전 존재 위반이나 이번 피처가 약 15줄 가중. 별도 리팩토링 |
| **Gap-05** | 동일 워커가 인자만 바꿔 3회 연속 호출 | 🟢 Minor | 본 피처 범위 밖 |
| — | `detect` 타입 힌트 누락 (`classmethod`) | 🟢 Minor | CLAUDE.md §3 "명시적 타입" 흠 |

### Gap-01 상세 — 원인이 좁혀진 상태

실패 런(`01a0ae79`)의 supervisor 근거:

> "추가로 브라우저 도구를 열어도 동일 페이지에서 기본 조건을 변경하지 말라는 위키 지침 때문에 유효한 표 데이터를 얻지 못한다."

LLM이 위키 문구 *"검색조건은 건드리지 말고 그대로 검색만 클릭"* 을 **"아무것도 조작하지 말라"** 로 오독했다. 되물음 블록은 *"시도할 게 남았는지"* 만 묻기 때문에 LLM이 스스로 세운 반대 논거를 반박하지 못한다.

**진행 중인 실험**: 위키 문구를 `"검색 조건은 기본값 그대로 둔 채 검색 버튼을 클릭한 뒤, 클릭 후 나타난 표를 읽어서"` 로 교체 후 3회 재실행해 재현율을 측정하기로 했다. 결과에 따라 Gap-01의 코드 대응 범위를 정한다.

> 이 실험은 **우회책이지 해결책이 아니다.** 일반 사용자가 자연어로 쓰는 한 같은 오독이 재발하므로, 코드 레벨 대응(블록 강화 또는 후속 피처 A)은 유효하다.

---

## 5. Quality Metrics

### 5.1 Final Analysis Results

| 축 | 점수 |
|----|:----:|
| Structural | 100% |
| Functional | 89% |
| Contract | 95% |
| Runtime | 75% |
| **Overall** | **87%** |

### 5.2 Resolved Issues

| # | 문제 | 발견 경로 | 조치 |
|---|------|-----------|------|
| 1 | 워커가 "브라우저 기능 없음"을 단언해 컨텍스트 오염 | 트레이스 `01a0a82b` 분석 | (D) 규범 추가 |
| 2 | 빈 결과가 실패 신호로 잡히지 않음 | 트레이스 `01a0a82b` 분석 | `EmptyResultPolicy` + 신호 채널 + 블록 |
| 3 | **무한 루프** — LLM 실패 / draft answer 경로가 pending 미소진 | Do 단계 전체 회귀 (기존 테스트 3건 실패) | 두 경로 확정 + 회귀 2건 |
| 4 | **D-v1 규범이 워커의 도구 결과 전달을 차단** | 프로덕션 트레이스 `01a0ae68` | 전달 의무를 선순위로 재작성 + 회귀 2건 |
| 5 | **무한 루프 잔여 경로** — `token_limit` 가드 (`limit_reached` 미설정이라 route가 되돌림) | Check 단계 독립 검증 | 3경로 전부 확정 + 회귀 2건 |
| 6 | 기본 패턴에 상위 문자열 포함 → 과탐 여지 | Check 단계 독립 검증 | `"데이터가 없습니다"` 제거 |

---

## 6. Lessons Learned & Retrospective

### 6.1 What Went Well (Keep)

- **프로덕션 트레이스를 1차 근거로 삼은 것.** 설계·구현·검증 전 단계에서 LangSmith 트레이스를 API로 뽑아 대조했다. 합성 테스트로는 #4(전달 차단)와 Gap-01(설득 실패)을 절대 발견하지 못했을 것이다.
- **개발 위키의 계약 문서를 설계 입력으로 강제한 것.** `supervisor-graph-contracts.md`의 계약 ①②③이 설계를 직접 구속했고, 특히 계약 ①(메시지 대신 state 채널) 덕분에 고아 tool 메시지 400 재발을 사전에 피했다.
- **독립 검증(gap-detector)이 실질 가치를 냈다.** 내가 놓친 `token_limit` 무한 루프(Critical)를 잡았다. 자기 구현을 자기가 검증할 때의 맹점을 보여준다.
- **단일 데코레이터 배선(D-06).** 4개 워커 팩토리를 한 지점에서 덮어 수정 범위를 줄였고, `_wrap_step`의 조건부 반환 함정도 피했다.

### 6.2 What Needs Improvement (Problem)

- **설계가 "구조적으로 보장된다"고 단언했으나 happy path에만 성립했다.** `finish_challenge_pending` 1회 상한은 6개 return 경로 중 3개만 지키고 있었고, 무한 루프가 **두 번** 발생했다(Do 1회, Check 1회). 불변식을 문서에 적는 것만으로는 지켜지지 않는다.
- **프롬프트 변경의 위험을 과소평가했다.** `"...라고만 밝히세요"` 한 구절이 4개 워커 전부의 출력을 망가뜨렸다. 단위 테스트는 문구 존재만 확인할 뿐 LLM 행동을 증명하지 못한다. 위키 계약 ②("목록 프레이밍은 방어 지시를 이긴다")를 블록에는 적용하면서 **워커 규범에는 적용하지 못한 일관성 실패**다.
- **Gap-01을 설계 시점에 장점으로 오판했다.** Design §4.3에 "오탐 시 LLM이 곧바로 FINISH를 재선택할 여지를 남긴다"를 **장점**으로 적었는데, 실제로는 정탐일 때도 재선택하는 부작용이었다.
- **FR-09(로깅)를 끝까지 잊었다.** Plan에 명시했는데 3개 세션 내내 누락됐고 독립 검증에서야 확인됐다. 관측 수단이 없어 Gap-01의 재현율을 프로덕션에서 자동 집계할 수 없다.

### 6.3 What to Try Next (Try)

- **불변식은 테스트로 강제한다.** "모든 return 경로가 X를 확정한다" 같은 명제는 문서가 아니라 파라미터라이즈드 테스트(각 조기 return 경로별 케이스)로 고정한다.
- **프롬프트 변경은 회귀 런을 DoD에 포함한다.** 프롬프트 상수를 건드리는 변경은 단위 테스트 통과만으로 완료 처리하지 않고, 프로덕션 1회 실행 + 트레이스 확인까지를 Definition of Done에 넣는다.
- **절대 프레이밍 금지 규칙을 위키 계약에 승격한다.** 계약 ②(목록 프레이밍)와 같은 계열로 *"'A라고만 하라'류 지시는 다른 의무를 덮어쓴다"* 를 추가 후보로 둔다 (`/wiki update` 시 검토).
- **LLM 설득이 필요한 개선은 재현율로 측정한다.** 1회 성공을 성공으로 세지 않는다. 최소 3회 실행 후 n/3으로 기록한다.

---

## 7. Process Improvement Suggestions

### 7.1 PDCA Process

- **Check 단계에 "프로덕션 트레이스 대조"를 정식 축으로 둔다.** 현재 Runtime 축은 합성 L1~L3를 상정하는데, 이 피처에서는 실제 런 대조가 훨씬 강력했다. 트레이스가 있는 프로젝트는 이를 Runtime 근거로 명시한다.
- **독립 검증을 Check 기본 절차로 유지한다.** 구현자 자신의 분석만으로는 Critical 1건을 놓쳤다.

### 7.2 Tools/Environment

- LangSmith run API로 트레이스를 덤프·대조하는 스크립트가 반복적으로 유용했다. 재사용 가능한 형태로 `scripts/`에 정착시킬 가치가 있다 (현재는 스크래치패드).

---

## 8. Next Steps

### 8.1 Immediate

1. [ ] 위키 문구 교체 후 **3회 재실행** — Gap-01 재현율 측정
2. [ ] FR-09 로깅 구현 (되물음 발동 시 `logger.info`: 사유·worker_id·request_id)

### 8.2 Next PDCA Cycle

3. [ ] Gap-01 대응 — 블록이 LLM의 반대 논거를 직접 다루도록 재설계 (계약 ② 준수 하에)
4. [ ] Gap-03 — 탐지 대상을 워커 답변에서 도구 원본으로 전환 검토
5. [ ] `wiki-procedure-completion` (A) 착수 — Plan 작성 완료 상태. **본 피처의 되물음 게이트를 재사용하므로 §2.2 불변식(모든 return이 플래그 확정)을 먼저 확인할 것**
6. [ ] Gap-08 — `supervisor_node` 분해 리팩토링

---

## 9. Changelog

### v1.0.0 (2026-09-17)

**Added**
- `EmptyResultPolicy` — 수집 산출의 유효 데이터 부재 판정 (구조적 + 설정 패턴)
- `SupervisorState.last_worker_empty` / `finish_challenge_pending` 채널
- `_with_empty_signal` 데코레이터 — 4개 워커 팩토리 단일 배선
- `_render_empty_result_block` — 조건부 안내 블록 (계약 ② 준수)
- `route_to_worker_or_final` 되물음 분기 + `route_map` 자기순환
- `empty_result_patterns` 설정 + `main.py` DI 정규화
- 워커 규범: 도구 결과 전달 의무 + 에이전트 전체 능력 부정 금지

**Fixed**
- supervisor 조기 return 3경로(LLM 실패 / draft answer / token_limit)의 되물음 플래그 미소진으로 인한 무한 루프
- 워커 규범의 절대 프레이밍이 도구 결과 전달을 차단하던 문제

**Known Issues**
- 되물음 후 브라우저 경로 전환 재현율 1/3 (Gap-01)
- 되물음 발동 구조화 로그 미구현 (FR-09)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-09-17 | 최초 완료 보고. Match Rate 87%, 이월 6건 | 배상규 |
