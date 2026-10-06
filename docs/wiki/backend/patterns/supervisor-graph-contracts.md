---
title: Supervisor 그래프 계약 — 워커 산출물 1건·목록 프레이밍 금지·강제 라우팅 범위·name 패턴·서브에이전트 입력
status: approved
source_type: conversation
source_refs:
  - idt/docs/archive/2026-07/worker-toolmessage-leak-fix/worker-toolmessage-leak-fix.report.md
  - idt/docs/archive/2026-07/data-inventory-requery/data-inventory-requery.report.md
  - 커밋 08d37cab (수퍼바이저 과차단 + 재질문 재검색 우회 수정)
  - 커밋 392d4637 (워커 트레이스 유출→고아 tool 400 방어)
  - idt/src/application/agent_builder/workflow_compiler.py (_wrap_worker, final_answer 필터, function_node_ids, _wrap_sub_agent)
  - 커밋 fe184dd (worker_id 공백 → OpenAI name 400, sanitize_llm_name) — v2
  - 커밋 49b2f41 (서브에이전트 입력 3블록 + function_node_ids 회귀 수정) — v2
  - idt/src/domain/agent_builder/rag_tool_config.py (sanitize_llm_name, clamp_llm_name) — v2
  - idt/src/domain/agent_builder/sub_agent_context_policy.py (find_origin_index, 4000자 상한) — v2
  - idt/src/application/agent_builder/sub_agent_context.py (TaskWithOriginStrategy, resolve_strategy, legacy_input) — v2
  - idt/tests/application/agent_builder/test_workflow_compiler_sub_agent.py (C0 TestSubAgentRuntimeNode) — v2
  - idt/docs/archive/2026-10/subagent-context-scope/subagent-context-scope.report.md — v2
confidence: 0.9
version: 2
created: 2026-08-03
updated: 2026-10-06
reviewer: 배상규
verified_at: ae12fc4
---

> v2 (2026-10-06): §4(LLM 노출 name 패턴)·§5(서브에이전트 입력·노드 등록 계약) 추가.
> 에이전트 갱신이므로 approved → draft 강등 (재승인 필요).

Supervisor 그래프(에이전트 실행 경로)를 수정할 때 지켜야 할, 실장애로 검증된 계약 3가지.

## 1. 워커 산출물은 AIMessage(name=worker_id) 정확히 1건

- **장애**: 도구를 호출하는 react 워커의 내부 트레이스(tool_calls AIMessage + ToolMessage +
  최종 AIMessage)가 supervisor state로 통째로 유출 → final_answer의 필터가 AIMessage만
  제거해 **ToolMessage가 고아로 잔류** → OpenAI 400
  (`role 'tool' must be a response to a preceding message with 'tool_calls'`)로 런 전체 실패.
- **계약**: `_wrap_worker`는 react 결과의 최종 content로 `AIMessage(name=worker_id)` 1건만
  재생성해 반환한다. search/analysis/sub_agent/document_extractor는 원래 준수 —
  새 워커 래퍼를 만들 때 이 규약부터 확인. 2차 방어로 final_answer의 conversation 필터가
  tool 타입 메시지도 제거하며, token_delta는 신규 산출분 기준으로 계산한다.
- 멀티턴에서는 state에 남은 고아 tool 메시지가 **후속 턴까지 오염**시키므로 1차 차단이 핵심.

## 2. 프롬프트에 "할 수 있는 것 목록"을 주지 마라 (목록 프레이밍은 방어 지시를 이긴다)

- **장애**: 수퍼바이저 프롬프트에 권한/기능 목록을 넣자 LLM이 목록 밖 요청을 전부
  거부(과차단)했다. "목록에 없어도 위임하라"류 방어 지시는 목록 프레이밍을 이기지 못한다.
- **수정**: 권한 목록 제거 + 위임 가드 + 결정 프롬프트의 2차 방어선 (커밋 08d37cab).
- **적용**: 라우팅/위임 프롬프트는 화이트리스트 나열 대신 "기본은 위임, 예외만 명시" 프레임으로.

## 3. 결정적 강제 라우팅은 "현재 턴 수집분"에만 반응

- **장애**: 이전 턴 검색결과 재주입분이 `is_search_result()`를 통과해 분석 워커 강제 라우팅을
  트리거 → 범위 확대 재질문("전체 사용자")에서 재검색 기회 자체가 사라져 오응답.
- **계약**: 재주입분(REINJECTED_MARKER)은 강제 라우팅 트리거에서 제외. 재사용 vs 재수집
  판단은 보유 데이터 인벤토리 블록([이번 턴 수집/이전 턴 보유] + 원 질문 + 출처)을 근거로
  **LLM이 수행**한다. 결정적 라우팅=확실한 신호 전용, 불확실 판단=LLM — 책임 분리.
- **교차 회귀 주의**: `is_search_result` 같은 규약은 첨부 라우팅·데이터 연속성·시각화가
  공유한다. 규약을 바꾸면 소비자 전수를 확인할 것 (한 기능의 수정이 다른 기능을 깬 선례).

## 4. AIMessage.name 은 OpenAI 패턴 `^[^\s<|\/>]+$` 를 지켜야 한다 (v2)

- **장애**: 서브에이전트 worker_id(`sub_agent_{에이전트이름}_{i}`)가 에이전트 이름의 공백을
  그대로 물어, §1 계약대로 만든 `AIMessage(name=worker_id)` 가 다음 supervisor 결정 호출에서
  OpenAI 400 → 런 조기 종료 (fe184dd). 단위 테스트는 LLM을 안 부르므로 못 잡았고 L3 실런에서만 드러났다.
- **계약**: LLM에 노출되는 이름은 `clamp_llm_name()` 을 반드시 통과시킨다 — 64자 상한(초과 시
  원본 해시 4자 접미) + `sanitize_llm_name()`(공백·`<|\/>` → `_`, 한글 보존).
  신규 id는 빌더에서 정규화하고, **이미 저장된 id는 재저장 없이 메시지 생성 단계에서 치환**한다
  (해시는 치환 전 원본 기준이라 결정적).
- 도구 이름(`^[a-zA-Z0-9_-]+$`, `sanitize_tool_name`)과 **패턴이 다르다** — 메시지 name은 한글 허용,
  tool name은 불허. 둘을 혼용하지 말 것.

## 5. 서브에이전트 워커 입력·노드 등록 계약 (v2)

**(a) 입력은 3블록 조립 — 부모 마지막 메시지 1건이 아니다.**
- 과거: 서브에이전트는 `state.messages[-1]` 만 받고 supervisor 지시(`worker_task`)를 읽지 않았다 →
  앞 워커 다음이면 그 산출물만, QG 재시도면 피드백 문장만 받았다.
- 현재: `TaskWithOriginStrategy` 가 `[원 질문]` + `[참고 자료 — 이번 턴 워커 산출, 최신 우선 채움·
  시간순 출력, 4000자 상한]` + `[현재 작업](+[재시도 사유])` 를 조립. 규칙은 domain
  `SubAgentContextPolicy` 소유. 실런에서 자식이 참고자료로 **재검색 0회** 요약(중복 수집 방지 실측).
- **턴 경계 함정**: 기존 `_current_turn_messages` 는 QG 피드백(role=user)을 턴 경계로 오인한다.
  서브에이전트 문맥은 `SubAgentContextPolicy.find_origin_index()`(QG 피드백·재주입분 건너뜀)를
  단일 정의로 쓴다 — 이번 턴 경계가 필요한 새 코드도 이 함수를 쓸지 먼저 검토할 것.
- 조립 실패 시 `legacy_input`(마지막 메시지)로 fail-safe. 연결별 `context_mode` 는
  `resolve_strategy()` 한 곳에서 확장한다(현재 항상 default — 컴파일러 수정 불필요).

**(b) 함수형 워커 노드는 `function_node_ids` 에 등록해야 한다.**
- 컴파일러는 `function_node_ids` 에 없는 워커를 `_wrap_worker`(react 래퍼, `.ainvoke` 호출)로 감싼다.
  sub_agent 분기가 이 집합에서 빠져 래퍼 함수에 `.ainvoke` → `AttributeError` 가
  3a25eb7(2026-06) 이후 4개월 잠복했다. 기존 테스트가 `_compile_sub_agent` 를 `AsyncMock` 으로
  대체해 실제 노드 실행을 한 번도 안 탔기 때문 ([거짓 초록 §6](../../conventions/false-green-quality-gates.md)).
- **적용**: 새 노드/워커 유형을 추가하면 `function_node_ids` 등록 여부를 확인하고, **컴파일된 그래프에서
  노드를 실제 실행하는 테스트**(C0 `TestSubAgentRuntimeNode` 형태)를 기본으로 둔다.

**(c) 서브에이전트·게이트 워커 직후는 조건부 간선**이다 — 자식 런의 승인 대기 신호를 부모가 미리 알 수
없으므로 항상 `route_after_gated_worker` 로 분기(신호 없으면 기존과 같은 quality_gate).
상세: [승인 게이트 런 계약](approval-gate-run-contract.md).
