# supervisor-early-finish-fix Gap Analysis

> **Project**: sangplusbot (idt 백엔드)
> **Author**: 배상규
> **Date**: 2026-09-17
> **Design Doc**: [supervisor-early-finish-fix.design.md](../02-design/features/supervisor-early-finish-fix.design.md)
> **Planning Doc**: [supervisor-early-finish-fix.plan.md](../01-plan/features/supervisor-early-finish-fix.plan.md)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 빈 결과를 데이터 부재로 오판해 남은 워커를 시도하지 않고 종료한다 |
| **WHO** | P2 — KB 운영자/에이전트 소유자 |
| **RISK** | 빈 결과 오탐으로 정상 "0건"까지 되물어 지연·토큰 증가 |
| **SUCCESS** | 되물음 1회 발생 + 신호 없을 때 프롬프트 바이트 동일 |
| **SCOPE** | D(워커 규범) + C(빈 결과 신호·블록·1회 되물음) |

---

## Strategic Alignment Check

### 핵심 문제가 해결되었는가 — ❌ 아니다

**메커니즘은 동작하지만 사용자 목표는 달성되지 않았다.**

프로덕션 트레이스 `01a0ae68`(2026-09-17 08:07, 구현 후 실행)에서 사용자가 실제로 받은 최종 답변:

> "저축은행별 금리 데이터(표 행 자체)가 전혀 제공되지 않은 상태입니다. …어느 쪽도 지금 페이지의 정보만으로는 만들어서 드릴 수 없습니다."

되물음이 발동했음에도 supervisor는 `browser_open → snapshot → click → extract` 경로로 가지 않았다. 2번째 FINISH 근거:

> "동일 URL을 다시 스크래핑하거나 **브라우저 조작 도구를 사용해도**, 현재 페이지 상태가 데이터 부재인 이상 추가로 얻을 수 있는 정보가 없다."

즉 LLM은 브라우저 워커의 존재를 인지했고, 블록도 봤고, 되물음 기회도 받았지만 **"데이터 부재"라는 자기 확신을 꺾지 않았다.** Plan의 WHY("남은 워커를 시도하지 않고 종료")가 그대로 재현됐다.

→ **Critical 전략 미정렬.** 구조적 일치율과 무관하게 이 항목만으로 iterate가 필요하다.

### Success Criteria Status

| ID | 요구사항 | 상태 | 근거 |
|----|----------|:----:|------|
| FR-01 | (D) 워커의 에이전트 전체 능력 부정 금지 | ⚠️ Partial | 구현·테스트 완료. 그러나 초안 문구가 **런타임에서 역효과**(Gap-02). 수정판 D-v2는 **런타임 미검증** |
| FR-02 | `EmptyResultPolicy` 구조적+패턴 판정 | ✅ Met | `policies.py` / 단위 11건 |
| FR-03 | 패턴 설정값 외부화 | ✅ Met | `config.py` + `main.py:_empty_result_patterns()` |
| FR-04 | state 신호 필드, 워커가 세팅·supervisor가 리셋 | ✅ Met | 프로덕션 트레이스에서 블록 3회 렌더로 역산 확인 |
| FR-05 | "[수집 결과 확인 필요]" 블록 렌더 | ✅ Met | 트레이스 supervisor #4·#5·#6에 블록 존재, #7에는 부재(리셋) |
| FR-06 | 미해소 FINISH를 1회 되돌림 | ✅ Met | 트레이스 #6→#7이 되물음, 2번째 FINISH 통과 |
| FR-07 | 1회 상한 결정적 보장 + 한도 가드 우선 | ✅ Met | 무한 루프 버그 발견·수정(아래 §2.4), 회귀 테스트 2건 |
| FR-08 | 신호 없으면 프롬프트 바이트 동일 | ✅ Met | `test_prompt_byte_identical_when_no_signal` |
| FR-09 | 되물음 발동을 구조화 로그로 기록 | ❌ Not Met | 구현 누락 — 신규 코드에 되물음 관련 `logger.info` 없음 |

**충족률**: 완전 7 / 부분 1 / 미충족 1 = **7.5 / 9 (83%)**

### Decision Record Verification

| 결정 | 출처 | 준수 | 비고 |
|------|------|:----:|------|
| D+C 먼저, A는 별도 피처 | Plan | ✅ | A는 Plan만 작성, 미착수 |
| 1회 되물음 (결정적 차단 아님) | Plan Q2 | ✅ | 런타임 확인 |
| 구조적 신호 1차 + 패턴은 설정값 | Plan Q3 | ✅ | 단, 실효 탐지는 패턴이 담당(설계 §3.2에 기록된 한계) |
| 위키 절차만 추적 (A 범위) | Plan Q4 | ✅ | 본 피처 범위 밖 |
| Option C — state 신호 + route 되돌림 | Design | ✅ | 그래프 노드 추가 없음 |
| 4개 팩토리를 단일 데코레이터로 (D-06) | Design | ✅ | `_wrap_step` 안쪽 배치 |
| 3경로 전부 배선 | 사용자 선택 | ✅ | 데코레이터로 4팩토리 커버 + wiki 제외(Q-01 확정) |

**결정 이탈 없음.**

---

## 1. Analysis Overview

### 1.1 Analysis Purpose

Design 문서와 구현의 일치 여부, Plan Success Criteria 충족도, 그리고 **실제 프로덕션 런에서 의도한 효과가 났는지**를 검증한다.

### 1.2 Analysis Scope

- 정적: Design §4.1 변경 함수 목록 ↔ 구현
- 동적: **프로덕션 LangSmith 트레이스 3건 대조** (합성 L1~L3 테스트가 아니라 실제 런)

| 트레이스 | 시각 | 코드 상태 | 역할 |
|---|---|---|---|
| `01a08b28` | 09-10 | 변경 전 | 정상 대조군 (browser 플로우 성공) |
| `01a0a82b` | 09-16 | 변경 전 | 결함 재현 (조기 FINISH) |
| `01a0ae68` | 09-17 | **D-v1 + C 적용 후** | 본 분석의 주 근거 |

> 주의: `01a0ae68`은 D 규범 **초안(v1)** 이 배포된 상태의 런이다. Gap-02 수정 후의 D-v2는 아직 어떤 런에서도 실행되지 않았다.

---

## 2. Gap Analysis

### 2.1 Gap 목록

| ID | 심각도 | 내용 |
|----|:------:|------|
| **Gap-01** | 🔴 Critical | 되물음이 발동해도 supervisor가 브라우저 조작 경로로 전환하지 않는다 — 사용자 목표 미달성 |
| **Gap-02** | 🔴 Critical | (D-v1) 워커 규범이 도구 결과 전달을 차단했다. 수정됐으나 **런타임 미검증** |
| **Gap-03** | 🟡 Important | 빈 결과 탐지 대상이 워커의 **답변**이지 도구 **원본**이 아니다 |
| **Gap-04** | 🟡 Important | FR-09 구조화 로그 미구현 — 되물음 발동을 운영에서 관측할 수 없다 |
| **Gap-05** | 🟢 Minor | 동일 워커가 인자만 바꿔 3회 연속 호출됨 (본 피처 범위 밖, 별도 이슈) |
| **Gap-06** | 🔴 Critical | `token_limit` 가드 경로에 **잔여 무한 루프** — 독립 검증에서 발견, 즉시 수정 |
| **Gap-07** | 🟢 Minor | 기본 패턴에 상위 문자열 포함 → 과탐 여지. 수정됨 |
| **Gap-08** | 🟡 Important | `supervisor_node` 145줄 — 40줄 규칙 위반(사전 존재). 이번 피처가 약 15줄 가중 |

### 2.1.1 독립 검증 (gap-detector)

설계 §4.1의 7개 항목은 **전부 구현·배선 확인**됐다. 추가로 다음이 발견됐다.

- **Gap-06 (Critical)** — 아래 §2.7
- **FR-09 미구현 확정** — `supervisor_nodes.py`·`workflow_compiler.py` 어디에도 되물음 관련 로그 호출 0건. `_with_empty_signal`은 logger를 받지도 않는다
- `EmptyResultPolicy.detect`가 설계의 `@staticmethod` 대신 `@classmethod`, 인자 타입 힌트 없음 — 동작 동일하나 CLAUDE.md §3 "명시적 타입 사용" 흠
- sub-agent 그래프(depth>0)에도 신호 데코레이터는 걸리지만 `route_to_worker`가 pending을 읽지 않아 되물음은 발생하지 않는다 — **무해하나 설계 미규정**

### 2.2 Gap-01 — 되물음이 설득에 실패한다 (Critical)

**증상**: 블록이 렌더되고 되물음도 일어났으나 supervisor가 같은 결론을 반복.

**원인 가설 2가지**:

1. **블록 문구가 너무 약하다.** 현재 문구는 *"아직 시도하지 않은 방법이 남아 있다면 FINISH 대신 그 방법을 먼저 시도하세요"* — "남아 있다면"이라는 조건의 참/거짓 판단을 LLM에게 통째로 맡긴다. LLM은 "브라우저를 써도 소용없다"고 스스로 판단해 조건을 거짓으로 만들었다.
2. **계약 ②(목록 프레이밍 금지)와의 긴장.** 워커 이름을 명시하면 LLM이 행동할 가능성이 높지만, 위키 계약이 화이트리스트 나열을 금지한다. 설계 시 이 긴장을 인지했으나 **조건부 서술만으로 충분한지 검증하지 않았다.**

**설계 문서와의 관계**: Design §4.3이 "오탐 시 LLM이 곧바로 FINISH를 재선택할 여지를 남긴다"를 *장점*으로 기술했는데, 실제로는 **정탐일 때도 재선택해버리는** 부작용이 됐다. 설계 판단 오류.

### 2.3 Gap-02 — D-v1 규범의 전달 차단 (Critical, 수정됨)

트레이스 `01a0ae68`에서 supervisor가 본 워커 산출물 4건이 전부 `"이 워커의 범위 밖입니다."` 단일 문장이었다. `wiki_read`·`scrape_url` 모두 도구는 성공했으나 결과가 전달되지 않았고, supervisor는 이를 도구 실패로 오인했다(`"wiki_read 호출이 실패한 상태"`).

**원인**: `"'이 워커의 범위 밖'이라고만 밝히세요"`의 **"~라고만"** 절대 프레이밍이 기존 규범 `"데이터를 정재만 할뿐 어떠한 작업을 하지 마세요"`와 결합.

**조치**: 전달 의무를 선순위로 재작성, 회귀 테스트 2건 추가, Design §1.2에 D-08 실측 정정 기록.

**잔여 위험**: 프롬프트 변경의 효과는 단위 테스트로 증명 불가. **재현 런이 반드시 필요하다.**

### 2.4 Gap-07(해소) — 무한 루프 (Do 단계에서 발견·수정)

`supervisor_node`의 조기 return 2곳(LLM 결정 실패 fallback / 워커 미실행 draft answer)이 `finish_challenge_pending`을 확정하지 않아 `GraphRecursionError`가 발생했다(기존 테스트 3건 실패로 포착). 모든 return 경로가 플래그를 확정하도록 수정하고 회귀 테스트 2건으로 고정했다. Design §2.2에 불변식으로 기록.

> 설계가 "카운터 없이 구조적으로 보장된다"고 단언했으나 **happy path에만 성립**했다. 후속 피처 A가 같은 게이트를 확장할 때 이 불변식을 먼저 확인해야 한다.

### 2.7 Gap-06 — `token_limit` 가드의 잔여 무한 루프 (Critical, 수정됨)

§2.4에서 두 경로를 고쳤으나 **같은 유형의 세 번째 경로가 남아 있었다.**

```python
if state["token_usage"] >= state["token_limit"]:
    logger.warning("token_limit reached", ...)
    return {"next_worker": "__end__"}        # pending 미확정, limit_reached 미설정
```

`max_iterations` 가드와 달리 이 경로는 `limit_reached`를 **의도적으로 세우지 않는다** — agent-recursion-limit D5의 설계 결정이며 `test_agent_iteration_limit.py`가 고정하고 있다. 따라서:

```
pending=True + 토큰 한도 초과
  → route: __end__ + pending + not limit_reached → "supervisor"
  → supervisor: 같은 가드 → __end__ (pending 그대로)
  → 무한 루프
```

`iteration_count`도 이 경로에서는 증가하지 않아 `max_iterations` 가드가 막아주지 못한다. 도달 조건은 현실적이다 — 워커가 `token_usage`를 실제로 누적시키므로, 빈 결과를 낸 워커가 한도를 넘기면 즉시 성립한다.

**조치**: `token_limit`·`max_iterations`·`forced worker` 세 경로 모두 플래그를 명시적으로 확정하도록 수정. 회귀 테스트 2건 추가.

**교훈**: "모든 return 경로가 플래그를 확정한다"는 불변식을 §2.2에 적어놓고도 구현에서 3/6 경로만 지켰다. 불변식을 **테스트로 강제**하지 않으면 문서에 적는 것만으로는 지켜지지 않는다.

### 2.8 재검증 — D-v2 배포 후 프로덕션 런 3건 (2026-09-17)

Gap-02 수정(D-v2) 이후 같은 질문으로 3회 실행된 런을 대조했다.

| 런 | 시각 | 플로우 | 결과 |
|---|---|---|---|
| `01a0ae73` | 08:19 | wiki → scrape_url → **browser_open** → final | ⚠️ 부분 — 세션만 열고 snapshot/click 없이 종료 |
| `01a0ae79` | 08:26 | wiki → scrape_url → **되물음** → final | ❌ 실패 — "데이터 없음" 답변 |
| `01a0ae7c` | 08:30 | wiki → **browser_open → snapshot → click(e108) → extract** → final | ✅ **완전 성공** — 금리 표 9,826자 |

**Gap-02 해소 확정.** 3건 모두 워커가 도구 결과를 정상 전달했다. `"이 워커의 범위 밖입니다"` 단독 응답은 사라졌다.

- 08:30: *"도구로부터 추출한 … 저축은행별 금리 표 구조는 아래와 같습니다"*
- 08:26: *"툴에서 반환한 내용을 가감 없이 그대로 옮깁니다"*

**오탐 0건.** 성공한 08:30 런에서 빈 결과 블록은 한 번도 렌더되지 않았다 — Plan RISK "정상 0건 오탐"이 실측에서 발생하지 않았다.

**Gap-01은 여전히 열려 있다 — 재현율 1/3.** 실패한 08:26 런은 되물음까지 받고도 FINISH를 두 번 냈다:

> "추가로 **브라우저 도구를 열어도** 동일 페이지에서 기본 조건을 변경하지 말라는 위키 지침 때문에 유효한 표 데이터를 얻지 못한다."

LLM이 위키 문구 *"검색조건은 건드리지 말고 그대로 검색만 클릭"* 을 **"아무것도 조작하지 말라"** 로 오독해, 클릭 자체가 금지된 것으로 결론냈다. 되물음 블록은 이 자체 논증을 반박하지 못한다.

→ Gap-01의 원인이 좁혀졌다: 블록이 **"시도할 게 남았는지"만 묻고, LLM이 이미 세운 반대 논거를 건드리지 않는다.**

### 2.5 Runtime Verification Results

**검증 방식**: 합성 테스트가 아닌 프로덕션 트레이스 대조.

| 항목 | 결과 | 증거 |
|------|:----:|------|
| 빈 결과 블록 렌더 | ✅ | supervisor #4·#5·#6 system prompt에 `[수집 결과 확인 필요]` 존재 |
| 블록 1회성(소비 후 리셋) | ✅ | #7에는 블록 부재 |
| 되물음 1회 발동 | ✅ | #6 FINISH → supervisor 재진입(#7) |
| 무한 루프 없음 | ✅ | #7 FINISH가 통과해 `final_answer` 도달 |
| 한도 가드 우선 | ✅(단위) | 프로덕션에서 한도 도달 사례 없음 — 단위 테스트로만 확인 |
| **사용자 목표 달성** | ❌ | 최종 답변이 "데이터 없음" |
| **워커 결과 전달** | ❌(v1) | Gap-02. v2 미검증 |

### 2.6 Match Rate Summary

런타임 검증이 실행됐으므로 runtime 포함 공식을 적용한다.

| 축 | 점수 | 근거 |
|----|:----:|------|
점수는 **Gap-02/06/07 수정 + 재검증 런 3건 반영 후** 상태로 산정한다.

| 축 | 점수 | 근거 |
|----|:----:|------|
| Structural | 100% | Design §4.1의 7개 변경 지점 전부 구현·배선 확인(독립 검증) |
| Functional | 89% | FR 9건 중 완전 8 / 미충족 1(FR-09 로깅). FR-01은 D-v2로 런타임 확인 |
| Contract | 95% | pending 불변식 6/6 복원. `detect` staticmethod→classmethod·타입힌트 누락만 잔존 |
| Runtime | 75% | 메커니즘 5항목 + 오탐 0건 확인. 단 **사용자 목표 달성 1/3** |

```
Overall = 100×0.15 + 89×0.25 + 95×0.25 + 75×0.35
        = 15 + 22.25 + 23.75 + 26.25
        = 87.25%
```

**Match Rate: 87%** — 목표 90% 미달. **iterate 필요.**

미달 사유는 단 두 가지로 좁혀졌다: **Gap-01 재현율(1/3)** 과 **Gap-04 로깅 미구현**.

---

## 3. Code Quality Analysis

| 항목 | 결과 |
|------|------|
| 신규 함수 길이 | `_with_empty_signal` 6줄 / `_render_empty_result_block` 7줄 / `route_to_worker_or_final` 5줄 — 상한 40 준수 |
| if 중첩 | 최대 1단계 — 상한 2 준수 |
| `print()` 사용 | 없음 |
| Design Ref 주석 | 7곳 부착 |
| 보안 | 블록에 수집 원문 미포함(정책 생성 문구만) — 외부 콘텐츠의 지시문 승격 없음 |

---

## 5. Test Coverage

| 파일 | 테스트 수 | 대상 |
|------|:---------:|------|
| `tests/domain/agent_builder/test_empty_result_policy.py` | 11 | FR-02 |
| `tests/application/agent_builder/test_empty_signal_wiring.py` | 10 | FR-04 |
| `tests/application/agent_builder/test_supervisor_empty_block.py` | 14 | FR-05, FR-07, FR-08 |
| `tests/application/agent_builder/test_finish_challenge_route.py` | 8 | FR-06, FR-07 |
| `tests/application/agent_builder/test_empty_result_integration.py` | 6 | L3 통합, Q-01 배선 |
| `tests/application/agent_run/test_worker_context_block.py` | 17(+6) | FR-01 |

전체 스위트 `tests/application` + `tests/domain`: **5817 passed, 0 failed**

### 5.2 미커버 영역

- **FR-09 로깅** — 구현 자체가 없음
- **D-v2 규범의 런타임 효과** — 프롬프트 행동은 단위 테스트로 증명 불가
- **되물음 후 supervisor의 실제 행동 변화** — 통합 테스트는 스텁 LLM이라 설득력을 측정하지 못한다

---

## 6. Clean Architecture Compliance

| 항목 | 결과 |
|------|------|
| domain → 상위 레이어 참조 | 없음 (`EmptyResultPolicy`는 str만 수신) |
| 정책은 domain, 흐름 제어는 application | 준수 |
| config 직접 import (application/domain) | 없음 — `main.py` kwarg 주입 |
| infrastructure / interfaces 변경 | 없음 |

**Architecture Score: 100%**

---

## 9. Recommended Actions

### 9.1 Immediate (iterate 대상)

1. **[Gap-02] 재현 런 실행** — dev 서버 재시작 후 동일 질문. 워커가 도구 결과를 전달하는지 확인. 이것 없이는 다른 수정의 효과를 측정할 수 없다.
2. **[Gap-01] 블록 문구 강화** — "남아 있다면"이라는 LLM 자체 판단 조건을 제거. 계약 ②를 지키면서도 행동을 유도하는 표현 설계 필요. 예: 빈 결과의 **원인 가설**("조작 전 상태일 수 있다")을 단정적으로 제시하고, 판단이 아니라 확인을 요구.
3. **[Gap-04] FR-09 로깅 추가** — 되물음 발동 시 `logger.info`(사유·worker_id·request_id). 운영 관측 없이는 Gap-01의 개선 여부를 측정할 수 없다.

### 9.2 Short-term

4. **[Gap-03] 탐지 대상 재검토** — 워커 답변이 아닌 도구 원본에서 판정할 수 있는지. `_wrap_worker`는 `result_messages`(내부 트레이스)에 접근 가능하므로 `ToolErrorPolicy.summarize`와 같은 방식으로 tool 메시지에서 직접 판정하는 안을 검토.

### 9.3 Long-term (backlog)

5. 브라우저 도구군 단일 워커 번들링 — Gap-01의 구조적 해법. `scrape_url`과 `browser_*`가 별개 워커인 한 supervisor는 매 스텝 재판단해야 한다.
6. `wiki-procedure-completion`(A) 착수 — 위키 절차 완주 체크리스트.

---

## 10. Design Document Updates Needed

이미 반영 완료:

- §2.2 — pending 불변식 실측 정정 (모든 return 경로가 플래그 확정)
- §1.2 — D-08 절대 프레이밍 금지 실측 정정
- §11.1 — 테스트 파일 지목 정정

추가 필요:

- §4.3 — "오탐 시 재선택 여지"가 장점이 아니라 **Gap-01의 원인**이었음을 기록

---

## 11. Next Steps

1. [ ] dev 서버 재시작 후 재현 런 (Gap-02 검증)
2. [ ] `/pdca iterate supervisor-early-finish-fix` — Gap-01·Gap-04 수정
3. [ ] 재분석 후 90% 도달 시 `/pdca report`

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-09-17 | 최초 분석. Match Rate 80.5%, Critical 2건 | 배상규 |
