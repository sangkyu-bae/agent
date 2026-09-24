# action-category-compose-node Completion Report

> **Summary**: `action` 카테고리 워커를 react에서 떼어내 "작성 1회 → 초안 → 인자 조립 → 도구 1회 호출" 함수 노드로 만들었다. 승인 초안·발송 본문·최종 답변이 같은 문자열이 되었고, "미분류 = action" 폴백을 "미분류 = None(react)"으로 정정했다. Match Rate 93%, Important 0, 미커밋.
>
> **Project**: sangplusbot (idt)
> **Date**: 2026-09-24
> **Author**: 배상규
> **Cycle**: Plan 2026-09-22 → Design 09-23 → Do 09-23~24 → Check/Act 09-24
> **Branch**: feature/approval-gate-tracing-observability

---

## Executive Summary

### 1.1 Project Overview

| 항목 | 내용 |
|------|------|
| 배경 | 메일·고객문의 회신처럼 부작용 도구를 쓰는 워커는 react가 본문을 도구 인자로 지어내고, 승인 게이트는 인자 키를 추측해 초안을 꺼내며, final_answer가 초안을 다시 썼다 |
| 목표 | 초안 작성 주체를 노드로 고정해 승인·발송·답변이 같은 문자열이 되게 한다. 코어에 메일 지식은 넣지 않는다 |
| 범위 | 백엔드(idt) 한정. module-1 계약 정정·도메인, module-2 초안 규약·노드, module-3 컴파일러 배선·final_answer, module-4 통합·재개 |

### 1.2 Results Summary

| 지표 | 값 |
|------|----|
| Match Rate | 93% (91% → iterate 1회 → 93%) |
| FR | 25/26 ✅, 1 ❔(FR-26 추적은 실런 필요) |
| SC | 5 ✅ / 3 ⚠️ / 0 ❌ |
| 테스트 | 신규 9파일 96케이스, 갱신 8파일. 관련 스위트 4,382 passed, 전체(api·infra 제외) 6,428 passed |
| 변경량 | 18 files, +492 / -64, 신규 파일 10 |
| 잔여 갭 | Critical 0 / Important 0 / Minor 11 |

### 1.3 Value Delivered

| 관점 | 계획 | 실제 |
|------|------|------|
| **Problem** | 초안이 인자에 묻혀 승인·발송·답변이 어긋날 수 있음 | 초안이 워커 산출 규약(`[w 초안]`/`[w 집행결과]`)으로 한 번 생성되고 세 지점이 같은 문자열임을 그래프 통합 테스트로 고정 |
| **Solution** | action 함수 노드 + 폴백 정정 + final_answer 보존 정책 | 전부 구현. run cap을 초안 규약까지 확장해 재개 런 이중 발송 차단(SC-8) |
| **UX** | 승인 화면 초안 = 발송 본문 = 답변 포함분, 실행 이력에 작성·집행 스텝 분리 | 노드 스텝 요약이 키·길이만 담고 값은 로그에 남지 않음. 실제 `ai_run_step` 적재는 실런 미수행으로 미확인 |
| **Core Value** | 특화는 데이터로, 코어는 "부작용 도구 1회 호출"만 앎 | 코어에 메일 지식 0건. 설정은 `tool_config.draft_arg_key` 한 항목, 미설정 시 관례 키 자동 탐색 |

## 1.4 Success Criteria Final Status

| SC | 상태 | 근거 |
|----|:--:|------|
| SC-1 명시 action = 함수 노드, 미분류 = react | ✅ | `test_workflow_compiler_action.py`, TC-W05 개정 |
| SC-2 게이트 시 도구 0회·draft == 초안·본문 키 == 초안 | ✅ | `test_action_pipeline.py::TestGatedPath`, 통합 1차 런 |
| SC-3 비게이트 시 정확히 1회·재시도 0 | ✅ | `TestDispatchPath`, 통합 |
| SC-4 final_answer 초안 원문 포함 | ⚠️ | 즉시·재개 모두 포함 확인. "바이트 동일" 비교 테스트는 없음(Minor) |
| SC-5 폴백 None | ✅ | TC-R03 개정, 등가 테스트 통과 |
| SC-6 서버 단위 참조 action 거부 | ⚠️ | 정책·카탈로그 UseCase 적용. 다른 경로는 API 부재로 미존재 |
| SC-7 실행 이력 요약에 값 없음 | ⚠️ | 요약·로그는 테스트로 고정. DB 적재는 실런 미수행 |
| SC-8 재개 런 재실행 0회 | ✅ | run cap 초안 규약 + 통합 테스트 |

**5/8 Met, 3 Partial(모두 실런·테스트 정밀도 문제, 기능 결함 아님)**

## 1.5 Decision Record Summary

| 결정 | 출처 | 준수 | 결과 |
|------|------|:--:|------|
| 명시 action만 새 노드, 폴백 None | Plan/D-01 | ✅ | 로컬 DB 명시 action 0건이라 데이터 회귀 없음. 레거시 테스트 9곳 기대값 갱신 |
| 본문 결정적 주입 + 나머지 보조 LLM | Plan/D-04·05 | ✅ | LLM이 본문 키를 채워도 초안이 이김(테스트 고정) |
| 에이전트 모델로 작성, 새 지침 필드 없음 | Plan | ✅ | supervisor 프롬프트 + 워커 설명으로 충분 |
| final_answer 재작성 금지 모드, 정책 객체 격리 | Plan/FR-18 | ✅ | `FinalAnswerDraftPolicy` 1곳. 지시는 user tail이 아닌 system prompt로 정정(v0.2) |
| 함수형 `action_pipeline.py`(Option C) | Design/D-02 | ✅ | 신규 파일 2개, 40줄 규칙 준수 |
| 게이트 판정 함수 공유 | D-03 | ✅ | `_should_gate_worker`를 미들웨어·노드가 공유 |
| 산출 1 AIMessage 2구획, uuid4 tool_call_id, compile 시 격리, fixed_args 제외 | D-06·08·09·10 | ✅ | — |
| run cap = collect ∪ action | D-11 | ✅(보강) | `_executed_worker_ids`가 초안 규약도 세도록 확장하지 않으면 무효였음 |
| 초안 전용 모드 제외, compose/dispatch 분리 | Plan | ✅ | 후속 확장 가능 |

---

## 2. Related Documents

| 문서 | 경로 | 버전 |
|------|------|------|
| Plan | `docs/01-plan/features/action-category-compose-node.plan.md` | 0.1 |
| Design | `docs/02-design/features/action-category-compose-node.design.md` | 0.2 |
| Analysis | `docs/03-analysis/action-category-compose-node.analysis.md` | 0.2 |
| 선행 | approval-gate, approval-gate-phase2-mcp-executor, mcp-tool-category-routing(archived) | — |

---

## 3. Completed Items

### 3.1 Functional Requirements

| 그룹 | FR | 상태 |
|------|----|------|
| A 카테고리 계약 | FR-01~04 | ✅ 폴백 None, `ToolMeta.category=None`, action 단일 도구 참조 강제, 테스트 갱신 |
| B 설정 | FR-05~07 | ✅ `ActionToolConfig` VO, compile 시 검증·격리, `RagToolConfigRequest.draft_arg_key`(iterate) |
| C 노드 | FR-08~16 | ✅ compose/assemble/dispatch, 초안 규약, 1회 호출, run cap, function_node 등록·empty_signal 제외 |
| D final_answer | FR-17~20 | ✅ 정책 블록·지시, 승인 대기 런 미경유, 초안 없는 런 불변 |
| E 승인 연동 | FR-21~23 | ✅ 신호 5키 동일, UseCase·집행기 무변경, 재개 outcome 우선 |
| F 관측·보안 | FR-24~26 | ✅ 24·25 / ❔ 26(실런 필요) |

### 3.2 Non-Functional Requirements

| 항목 | 결과 |
|------|------|
| 정확성(1회 호출) | 단위·통합 테스트로 고정 |
| 일관성(세 지점 동일 문자열) | 통합 테스트로 고정 |
| 무회귀 | 기존 스위트 통과, api/infra 실패 53건은 stash 대조로 기존 항목 확인 |
| 보안 | 값 로그 금지, 재시도 없음, fail-closed(신호 생성 실패·인자 조립 실패 시 미발송) |
| 아키텍처 | domain 신규 코드 stdlib만 import |

### 3.3 Deliverables

| 구분 | 파일 |
|------|------|
| 신규 src | `domain/agent_builder/action_tool_config.py`, `application/agent_builder/action_pipeline.py` |
| 수정 src | `domain/agent_builder/{policies,schemas}.py`, `domain/tool_catalog/policies.py`, `application/agent_builder/{search_pipeline,collect_pipeline,worker_run_cap_hooks,workflow_compiler,schemas}.py`, `infrastructure/agent_builder/tool_factory.py` |
| 프론트 | `idt_front/src/types/ragToolConfig.ts` 선택 필드 1개(API 계약 동기화) |
| 테스트 신규 | `test_action_tool_config`, `test_action_argument_policy`, `test_final_answer_draft_policy`, `test_draft_output_markers`, `test_action_pipeline`, `test_workflow_compiler_action`, `test_final_answer_draft_mode`, `test_action_graph_integration` |

---

## 4. Incomplete Items

### 4.1 Carried Over to Next Cycle

| 항목 | 사유 | 제안 |
|------|------|------|
| L3 실런 세 지점 대조(`ai_run_step`·`approval_request.draft`·`ai_tool_call`) | 로컬 MCP 5종에 본문 키를 받는 부작용 도구 없음 | 메일 MCP 등록 후 `category="action"` 지정만으로 검증 가능 |
| 프론트 `draft_arg_key` 입력 폼 + 카테고리 설명 문구("실행" → "작성→1회 호출") | Plan Out(백엔드 한정) | UI 사이클 |
| Minor 11건 | 문서 시그니처·블록 순서·로그 `tool_id`·상수명·바이트 동일 테스트·docstring 등 | 다음 리팩터 시 일괄 |
| 초안 전용(dispatch 없음) 모드 | Plan Out, compose 분리로 확장 지점 확보 | 필요 시 별도 사이클 |

### 4.2 Cancelled/On Hold

- `fixed_args`(고정 인자) — YAGNI로 제외(D-10), VO가 미지 키를 무시하므로 후속 추가 시 하위호환

---

## 5. Quality Metrics

### 5.1 Final Analysis Results

| 축 | 점수 |
|----|:--:|
| Structural | 92 |
| Functional | 92 |
| Contract | 90 |
| Runtime | 95 |
| **Overall** | **93%** |
| Architecture / Convention | 100 / 95 |

### 5.2 Resolved Issues (Iteration 1)

| 갭 | 조치 |
|----|------|
| GAP-I1 설정 경로 부재 | 요청 스키마 선택 필드 추가, RAG 파서가 타 도구 키 무시, 프론트 타입 동기화 |
| GAP-I2 오류 응답을 성공 처리 | `ToolErrorPolicy.ERROR_PREFIXES` 접두 판정 |
| GAP-I3 실패 문구 미절단 | 상한 절단 |
| GAP-I4·I5 | 검증 후 수용·하향(API 부재 / 재현 불가) |

---

## 6. Lessons Learned & Retrospective

### 6.1 Keep
- **Plan 전 냉정한 반론 → 코드 근거로 합의.** "MCP로 빼자"에서 시작해 "노드로 빼자"로 정리될 때까지 코드(final_answer D1 라우팅, react 인자 추출 휴리스틱)를 근거로 대화해 스코프가 한 번에 잡혔다.
- **선례 동형 설계.** collect 노드의 시그니처·실패 철학·산출 1건 계약을 그대로 따라 리뷰·테스트 패턴을 재사용했다.
- **정책 객체로 교체 지점 격리.** `FinalAnswerDraftPolicy`·`ActionArgumentPolicy`가 domain 순수 코드라 테스트가 빠르고 변경이 국소화된다.
- **갭 보고를 그대로 믿지 않고 검증.** gap-detector Important 5건 중 2건은 코드 확인으로 수용·하향됐다.

### 6.2 Problem
- **폴백 계약의 숨은 의미.** "action"이 사실상 미분류 버킷이었던 사실을 Plan 질문 단계에서야 발견했다. 카테고리 같은 열거값을 추가할 때는 기본값의 소비자를 먼저 grep해야 한다.
- **run cap이 검색 규약만 세던 것**을 Design이 놓쳤다. 재사용하는 기존 훅의 판정 기준을 설계 단계에서 읽었어야 한다.
- **user tail 지시가 항상 도달하지 않음**(마지막이 assistant일 때만 부착). 기존 헬퍼의 조건을 확인하지 않고 설계에 썼다.
- **셸 히어독 + 한글 + `\n` 이스케이프**가 실제 개행으로 바뀌어 구문 오류. 스크립트 파일로 우회.
- gap-detector 서브에이전트가 30턴 한도에 걸리고 Write가 막혀 보고서를 파일로 남기지 못했다.

### 6.3 Try
- 열거값·기본값을 바꾸는 Plan에는 "기본값 소비자 목록"을 Impact Analysis 필수 항목으로.
- 재사용 훅·헬퍼는 Design §2.3 Dependencies에 "판정 기준" 한 줄을 함께 적기.
- 서브에이전트에는 분석 범위를 파일 10개 이하로 쪼개 주거나, 결과를 메시지로 받는 것을 기본으로.

---

## 7. Process Improvement Suggestions

### 7.1 PDCA
- Design v0.2처럼 Do 중 발견을 Version History에 즉시 기록한 것이 Check에서 유효했다. 유지.
- Analysis에 "gap-detector 결과 검증" 절을 정식 단계로 두면 Important 오탐이 줄어든다.

### 7.2 Tools/Environment
- 로컬에 본문 키를 받는 더미 MCP(예: `echo_mail`)를 하나 등록해 두면 action 계열 L3를 항상 돌릴 수 있다.

---

## 8. Next Steps

### 8.1 Immediate
1. 커밋·PR: `feat(agent-builder): action 카테고리 작성→1회 호출 함수 노드 + 폴백 None 정정` (사용자 지시 시)
2. `/pdca archive action-category-compose-node --summary`

### 8.2 Next PDCA Cycle
- **UI**: 에이전트 빌더 `draft_arg_key` 폼 + 카테고리 설명 문구
- **실런 검증**: 메일 MCP 등록 → 세 지점 대조 → SC-4·6·7 ⚠️ 해소
- **Phase 3 후보**: 승인 화면 초안 편집(편집분이 발송 본문·최종 답변에도 반영되어야 하므로 이 사이클의 "같은 문자열" 규약 위에서 설계)

---

## 9. Changelog

### v1.0.0 (2026-09-24)
- feat: `action` 카테고리 함수 노드(`action_pipeline.py`) — compose → 초안 → 인자 조립(본문 결정적) → 게이트/1회 호출
- feat: `ActionToolConfig`, `ActionArgumentPolicy`, `FinalAnswerDraftPolicy` 도메인 추가
- feat: 초안 산출 규약 `format/is/split_draft_output`
- fix: 카테고리 폴백 `"action"` → `None`(미분류=react), `ToolMeta.category` 기본값 None
- fix: action도 단일 도구 참조만 허용(서버 단위 거부)
- feat: final_answer 초안 보존 모드(정책 객체)
- fix: `WorkerRunCapHooks`가 초안 규약도 실행으로 셈(재개 이중 발송 방지)
- feat: `RagToolConfigRequest.draft_arg_key`, RAG 파서 타 도구 키 무시, 프론트 타입 동기화
- fix: dispatch 오류 텍스트 응답 실패 판정, 실패 문구 절단
- refactor: collect 헬퍼 4개 공개 이름화

## Version History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-09-24 | 배상규 | 완료 보고서 |
