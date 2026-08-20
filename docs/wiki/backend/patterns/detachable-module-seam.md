---
title: 탈착형 모듈 이음매 — None 킬스위치 + AST 경계 테스트
status: draft
source_type: conversation
source_refs:
  - idt/src/application/intent/node.py (analyzer=None → 노드 자체를 만들지 않음)
  - idt/src/infrastructure/tool_selection/adapters/langchain_filter.py (실패 시 입력 그대로 반환)
  - idt/src/application/general_chat/use_case.py (tool_filter=None 기본값 · 바인딩 직전 filter 호출)
  - idt/src/api/main.py:2440~2465 (킬스위치 off·조립 실패 시 None 반환)
  - idt/src/config.py:120~126 (tool_selector_enabled 기본 False)
  - idt/tests/infrastructure/tool_selection/test_module_boundaries.py (AST import 검사)
  - docs/archive/2026-08/intent-analyzer/intent-analyzer.report.md (§1.3 Core Value, D8·FR-09)
  - docs/archive/2026-08/tool-recommender/tool-recommender.report.md (§1.5 Decision Record, §6.1)
  - idt/tests/infrastructure/tool_selection/test_module_boundaries.py:101-159 (_DECLARED_CONSUMERS 확장 + duck typing 예외 원칙, ⚠️ 미커밋)
  - docs/archive/2026-08/agent-create-pipeline/agent-create-pipeline.report.md (§1.5 Plan D2, §6.1 "탈부착 계약 테스트가 실제로 작동")
confidence: 0.65
version: 4
created: 2026-08-14
updated: 2026-08-19
verified_at: 7c3ffdd
---

# 탈착형 모듈 이음매 — None 킬스위치 + AST 경계 테스트

> ⚠️ **근거 전량이 `12c69b4` 미커밋 상태다.** `git cat-file` 전수 확인 결과:
> `intent/node.py`·`langchain_filter.py`·`test_module_boundaries.py`·PDCA 보고서 3종은
> HEAD에 **존재하지 않고**, `main.py`·`config.py`·`general_chat/use_case.py`는 파일만
> 커밋돼 있을 뿐 **인용한 라인은 전부 미커밋 diff 안**에 있다.
> 따라서 `verified_at`을 이용한 표류 검사가 **작동하지 않는다** — 코드 커밋 후
> `verified_at` 재기록이 필요하다.
>
> **선례에 대한 정정(v2)**: v1은 `search_decision`·`chart_router`를 이 패턴의 선례로
> 적었으나, 커밋된 코드를 확인하니 **둘 다 None 킬스위치를 구현하지 않는다** —
> `create_chart_router_node`는 `classifier=None`이어도 **항상 노드를 반환**하고
> 애매구간을 보수적으로 처리하며, `search_decision`은 워크플로의 **필수 의존**이다.
> intent 모듈 docstring도 "선례를 따르되 **None 을 반환하는 점이 다르다**"라고 적고 있다.
> 즉 §1의 "팩토리가 None을 반환한다"는 확립된 관행이 아니라 **이번 사이클의 신규 제안**이다.

## 문제

"실험적 기능을 붙이되, 안 통하면 흔적 없이 뺄 수 있어야 한다"는 요구는 흔하다.
그런데 보통은 (1) 조건문이 기존 경로 곳곳에 흩뿌려지고, (2) 기존 모듈이 신규 모듈을
import 해버려 삭제가 불가능해지며, (3) 신규 모듈이 죽으면 기존 경로까지 같이 죽는다.

intent-analyzer와 tool-recommender 두 사이클이 **서로 독립적으로 같은 해법**에
도달했고, 둘 다 회귀 0건으로 끝났다. 다만 두 사이클 모두 **아직 실전 활성화 전**이다
(intent는 어느 그래프에도 미배선, tool-recommender는 킬스위치 기본 off) — 이 문서는
"검증된 관행"이 아니라 **두 사이클이 수렴한 유력한 제안**으로 읽어야 한다.

## 검증된 사실

### 1. 이음매는 "None을 반환하는 팩토리" 한 지점

- `create_intent_node(analyzer=None, ...)` → **`None`을 반환**한다
  (`application/intent/node.py:49-50`). 호출측은 그 None을 보고 `add_node` 자체를
  건너뛰므로 **노드가 그래프에 존재조차 하지 않는다**. `if enabled:` 분기가 그래프
  런타임에 남지 않는다는 점이 핵심.
- `main.py`의 `tool_filter` 빌더도 동일하다: 킬스위치 off면 `None`, **조립 중 예외가
  나도 `None`**(`main.py:2463-2465`, "선별은 부가 기능이다 — 조립 실패가 채팅을
  막아선 안 된다"). `GeneralChatUseCase.__init__(tool_filter=None)`이 기본값이라
  주입이 없으면 기능이 없던 상태와 완전히 동일하다.

### 2. 실패는 "입력을 그대로 돌려주기"로 흡수한다

`LangChainToolFilter.filter()`는 어떤 실패에도 도구를 잃지 않는다
(`langchain_filter.py:110-139`):

| 상황 | 동작 |
|------|------|
| 도구 ID를 **하나라도** 식별 실패/중복 | 선별 전체 포기 → 입력 그대로 |
| 셀렉터가 예외 (Port 계약상 도달 불가) | warning + 입력 그대로 |
| 선별 결과가 0건 | warning + 입력 그대로 |

**부분 식별 시 부분 선별을 하지 않는 것**이 설계의 핵심이다 — 일부만 식별되면
식별 실패한 도구가 조용히 사라져 회귀가 된다. "회귀를 만드느니 선별을 포기한다."

의도 분석 쪽 대응물은 `IntentResultPolicy.degraded()`로, LLM이 죽어도 예외를
전파하지 않고 `degraded=True`만 돌려 호출자가 기존 로직을 그대로 진행하게 한다.

### 3. LLM 출력은 도메인 정책이 "정규화"만 한다 (판정은 안 함)

> 🗑 **이 절의 결정은 폐기됐다 (v3).** 대체: [[llm-output-trust-boundary]].
> 아래의 "겸용 스키마 + 3층 방어"는 계산 필드가 3개로 늘면서 확장에 실패했고,
> 후속 사이클(prompt-composer)은 **LLM 스키마에 계산 필드를 아예 두지 않는**
> Draft/Result 분리로 바꿨다. 이력 보존을 위해 원문은 남긴다 — 새 모듈에는 적용하지 말 것.

`IntentResultPolicy.normalize()`는 순수 함수라 분기 100% 커버가 가능하다.
특히 **`raw.degraded`를 읽지 않는다** — LLM이 채울 수 있는 필드이므로 호출자가
넘긴 `degraded` 인자만 신뢰한다(3층 방어). LLM 출력의 어떤 필드를 신뢰하고 어떤
필드를 무시할지 정책에 명문화하면 "LLM이 스스로 성공/실패를 보고"하는 신뢰 구멍이 막힌다.

### 4. 탈착 계약은 사람 규율이 아니라 CI가 지킨다

`tests/infrastructure/tool_selection/test_module_boundaries.py`가 **AST로 import를
파싱**해 검사한다:
- `domain/tool_selection/**`는 표준 라이브러리와 자기 패키지 외 아무것도 import 하지 않는다
- domain → infrastructure 참조 0 (CLAUDE.md §6)

그리고 "외부 참조는 `main.py` 뿐"이 grep으로 실증된다. 실제로 `12c69b4` 워킹트리에서
`intent`/`tool_selection` 패키지를 참조하는 외부 파일은 `main.py`·`intent_router.py`·
`interfaces/schemas/intent.py` 뿐이다.

### 4b. 두 번째 소비자 등장 — 선언 목록 확장 프로세스가 실제로 작동했다 (v4 추가)

agent-create-pipeline이 tool_selection의 **두 번째 소비자**가 되자 §4의 AST 계약
테스트가 즉시 실패했고(전체 스위트에서 신규 실패 2건으로 적발), 의도된 절차대로
`_DECLARED_CONSUMERS`에 4개 파일이 **근거 주석과 함께** 등록됐다
(`test_module_boundaries.py:101-112`). "계약 테스트 실패 → 의식적 선언 갱신"이라는
확장 경로가 설계대로 돌아간 첫 실증이다.

이때 확립된 예외 원칙: **duck typing 규칙은 "떼어도 동작해야 하는" 소비자에게만
적용된다.** General Chat은 tool_selection이 부가 기능이므로 import 없이
`tool_filter` duck typing으로 결선하지만(디렉토리 삭제 = 기능 제거), 파이프라인은
도구 추천이 부가 기능이 아니라 **단계 자체**이므로 `ToolSelectorPort` + 도메인 VO를
정식 의존으로 선언했다(순수 domain 계약만 물어 프레임워크 격리는 유지). 대신
"디렉토리 삭제 시 고쳐야 할 지점이 이 4파일만큼 늘었다"를 선언 목록이 정확히
기록한다 — 탈부착 계약은 "아무도 못 물게"가 아니라 "무는 곳을 전수 열거"가 본질이다.

### 5. 킬스위치 기본값은 off, 그리고 "off = 이 기능이 없던 상태"

`tool_selector_enabled: bool = False`. 결선(module-4)까지 끝났는데도 기본 off로
두어, 배포와 활성화를 분리했다. 성장 루프 플래그 4종과 같은 관행이다
([[architecture-overview]] §3).

(v4 추가) 라우터 레벨의 등가물: agent-create-pipeline은 킬스위치
(`AGENT_PIPELINE_ENABLED`) off이거나 선행 협력자(prompt-composer) 미가동이면
**`include_router` 자체를 하지 않는다** — 노드가 그래프에 없는 것처럼 라우트가 앱에
없다(404). "off = 없던 상태"를 엔드포인트 단위로 적용한 세 번째 사례
([[router-map]] 등록 순서 주의 참조).

## 다음에 적용하는 법

1. **새 실험적 모듈은 팩토리가 `None`을 반환할 수 있게 설계한다.** 호출부는
   `if x is not None:` 한 줄. 기능 제거 = 디렉토리 삭제 + 그 한 줄 삭제.
2. **폴백은 "이 모듈이 없던 상태"로 정의한다.** 부분 성공(부분 선별, 부분 매핑)은
   조용한 회귀를 만드니 전부 포기하는 쪽을 기본값으로.
3. **경계 규칙은 테스트로 못박는다.** AST import 검사 테스트를 신규 패키지에
   복제하면 되며, 이는 "탈부착 가능"의 유일한 지속 가능한 증거다.
4. **DI 조립 실패도 폴백 경로**로 취급한다 — `main.py` 빌더를 try/except로 감싸고
   실패 시 `None` + `logger.warning(..., exception=e)`
   ([[structured-logger-warning-exception]]).
5. **배선 전에 모듈만 먼저 인도하는 것**은 회귀 0건의 직접 원인이다. 다만 이 경우
   "프롬프트가 실제로 통하는가"는 미검증으로 남으므로, 실호출 검증 1회를 Do 종료
   조건으로 명시할 것 (intent-analyzer는 이걸 체크리스트로 뒀다가 사이클 종료까지
   미실행으로 이월됐다).

## 관련 문서

- §3 대체 문서: `backend/patterns/llm-output-trust-boundary.md`
- AST 경계 검사의 확장형: `backend/patterns/ast-source-contract-tests.md`
- 조감도: `backend/architecture-overview.md`
- 계약 확장 관행: `conventions/additive-contract-extension.md`
- 로깅 규약: `backend/patterns/structured-logger-warning-exception.md`
