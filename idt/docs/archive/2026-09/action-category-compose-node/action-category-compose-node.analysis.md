# action-category-compose-node Gap Analysis

> **Summary**: Design v0.2 대 구현의 정적 3축 대조(gap-detector) + 런타임 검증(단위·통합 388건). Match Rate **91%**. Critical 0, Important 3(검증 후 확정), Minor 11.
>
> **Project**: sangplusbot (idt)
> **Date**: 2026-09-24
> **Author**: 배상규
> **Plan**: `docs/01-plan/features/action-category-compose-node.plan.md` v0.1
> **Design**: `docs/02-design/features/action-category-compose-node.design.md` v0.2
> **Branch**: feature/approval-gate-tracing-observability (미커밋)

### Pipeline References (for verification)

- gap-detector 원시 보고(에이전트 세션 내 전달, 파일 저장은 도구 제한으로 실패 — 본 문서 §2·§5에 요지 반영)
- 런타임: `uv run python -m pytest` 기능 관련 15개 파일 388 passed; api/infrastructure 제외 전체 6,428 passed; api/infrastructure 실패 53건은 `git stash` 대조로 기존 항목 확인

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 부작용 도구의 본문을 react가 인자로 지어내고, 게이트는 추측하고, final_answer가 다시 쓴다 |
| **WHO** | P2 에이전트 소유자, 최종 사용자, 관리자 |
| **RISK** | final_answer 보존 불완전, 재개 이중 실행, 폴백 계약 변경 |
| **SUCCESS** | 도구 호출 정확히 1회(게이트 시 0회), 승인 draft == 발송 본문 == 답변 포함분, 미분류 회귀 0 |
| **SCOPE** | module-1~4 전부 구현. Out: 프론트 UI, 초안 전용 모드, 승인 화면 편집 |

---

## Strategic Alignment Check

### Plan Alignment

| 질문 | 판정 | 근거 |
|------|:--:|------|
| 핵심 문제(WHY)를 해결했는가 | ✅ | 초안이 노드에서 한 번 만들어지고 승인 `draft`·발송 인자 본문·final_answer 포함분이 같은 문자열임을 그래프 통합 테스트가 고정(`test_action_graph_integration.py`) |
| "일반화가 이긴다" 원칙 | ✅ | 코어에 메일 지식 0건. 특화는 프롬프트·워커 설명·`tool_config`(단, 설정 입력 경로는 GAP-I1) |
| 무회귀 | ✅ | 미분류 워커 react 유지(`test_workflow_compiler_category.py`), 초안 없는 final_answer 프롬프트 불변(정책 블록이 빈 문자열) |

### Success Criteria Status

| SC | 판정 | 근거 |
|----|:--:|------|
| SC-1 명시 action = 함수 노드, 미분류 = react | ✅ | `workflow_compiler.py` action 분기, `test_workflow_compiler_action.py`, TC-W05 개정 |
| SC-2 게이트 시 0회·draft == 초안·본문 키 == 초안 | ✅ | `test_action_pipeline.py::TestGatedPath`, 통합 테스트 1차 런 |
| SC-3 비게이트 시 정확히 1회·재시도 0 | ✅ | `test_action_pipeline.py::TestDispatchPath`, 통합 테스트 |
| SC-4 final_answer 초안 원문 포함, 초안 없는 런 불변 | ⚠️ | 포함은 즉시·재개 모두 확인. "바이트 동일" 비교 테스트는 없고 "초안 블록 없음" 검증으로 대체(GAP-M5) |
| SC-5 폴백 None | ✅ | `_resolve_category` + TC-R03 개정 |
| SC-6 서버 단위 참조 action 거부 | ⚠️ | 정책·카탈로그 갱신 UseCase에서 거부. `agent_tool.category`를 쓰는 API가 없어 다른 경로는 존재하지 않음(GAP-I4 → 수용) |
| SC-7 실행 이력 요약에 값 없음 | ⚠️ | 요약·로그 값 미노출은 테스트로 고정. `ai_run_step` 실제 적재는 L3 미수행으로 미확인 |
| SC-8 재개 런 재실행 0회 | ✅ | run cap 초안 규약 포함 + 통합 테스트 |

**5 ✅ / 3 ⚠️ / 0 ❌**

### Decision Record Verification

D-01~D-14 전부 준수(gap-detector §6 표). 편차 없음. D-11은 Do에서 "초안 규약도 실행으로 센다"로 보강(Design v0.2 ①).

---

## 1. Analysis Overview

### 1.1 Purpose
Design v0.2 대 구현의 구조·기능·계약 일치도와 Plan SC 충족을 확인하고, 잔여 갭의 심각도를 확정한다.

### 1.2 Scope
`src/domain/agent_builder/{action_tool_config,policies,schemas}.py`, `src/domain/tool_catalog/policies.py`, `src/application/agent_builder/{action_pipeline,search_pipeline,collect_pipeline,worker_run_cap_hooks,workflow_compiler}.py`, 신규 테스트 8개 파일 + 갱신 7개 파일.

---

## 2. Gap Analysis (Design vs Implementation)

### 2.1 API Endpoints
신규 엔드포인트 없음(설계와 일치). 단 Design §4.2가 예시한 `tool_config.draft_arg_key` 전달은 **현재 요청 스키마로 도달 불가**(§2.4 GAP-I1).

### 2.2 Data Model

| Design §3.1 | 구현 | 판정 |
|---|---|:--:|
| `ActionToolConfig` VO | `action_tool_config.py` 시그니처 일치 | ✅ |
| `ActionArgumentPolicy` 3메서드 | `policies.py` | ✅ |
| `FinalAnswerDraftPolicy.detect(sections)` | 구현은 `(sections, later_outputs=None)` — §3.1 본문 서술(D-07)과는 일치, 시그니처 블록과만 불일치 | Minor |
| `DraftContext` | 일치 | ✅ |
| DB 스키마 | 변경 없음 | ✅ |

### 2.3 Component Structure
§9.1 파일 7종 전부 존재. `_should_gate_worker`는 모듈 함수가 아닌 `WorkflowCompiler` staticmethod(테스트가 `compiler._should_gate_worker`로 접근). 동작 동일.

### 2.4 Functional Depth (FR-01~FR-26)

| 판정 | 건수 | 항목 |
|------|:--:|------|
| ✅ | 22 | FR-01~06, 08~19, 21~24 |
| ⚠️ | 2 | FR-20(바이트 비교 테스트 부재), FR-25(dispatch 실패 문구 미절단) |
| ❌ | 1 | **FR-07** — `RagToolConfigRequest`가 고정 필드 pydantic이라 `draft_arg_key`가 저장 전에 소실 |
| ❔ | 1 | FR-26(추적·토큰 집계는 러너 tracer 위임, 실런 필요) |

§6.1 실패 분기 9건 중 8건 완전, #8(dispatch 오류 응답)은 예외만 처리하고 **오류 텍스트 응답(`Error executing tool…`)을 성공으로 기록**.

### 2.5 Page UI Checklist
해당 없음(백엔드 한정).

### 2.6 Contract Verification

| 계약 | 판정 | 근거 |
|------|:--:|------|
| §3.4 초안 산출 규약 | ✅ | `format/is/split_draft_output` 왕복 15케이스 |
| §6.2 승인 신호 = `_extract_approval_pending` 5키 동일 | ✅ | render→extract 왕복(`_build_signal`), `test_action_pipeline.py::test_signal_round_trips_through_policy` |
| D-03 게이트 판정 단일 함수 | ✅ | `test_workflow_compiler_action.py::TestShouldGateWorker` |
| §2.2 compose 블록 순서 | Minor | 설계 `datetime+worker+user`, 구현 `datetime+user+worker`(collect 선례 준수) |
| §6.3 로그 필드 | Minor | `tool_id` 누락 |

### 2.7 Runtime Verification Results

| 레벨 | 결과 |
|------|------|
| L0/L1 단위·컴파일러 배선 | 388 passed (기능 관련 15파일) |
| 그래프 통합(게이트→END→재개→final_answer, 즉시 집행) | 2 passed |
| L1 API | 신규 엔드포인트 없어 해당 없음. dev 서버(8000) 응답 확인만 |
| L3 실런 세 지점 대조 | **미수행** — 로컬 MCP 5종에 본문 키 도구 없음(Design v0.2 기록) |
| 회귀 | api/infrastructure 제외 6,428 passed. 53 failed는 stash 대조로 기존 항목 |

### 2.8 Match Rate Summary

| 축 | 점수 | 가중치 |
|----|:--:|:--:|
| Structural | 92 | 0.15 |
| Functional | 84 | 0.25 |
| Contract | 90 | 0.25 |
| Runtime | 95 (L3 미수행 감점) | 0.35 |
| **Overall** | **91%** | |

---

## 3. Code Quality Analysis

- 함수 40줄·if 중첩 2단계: 위반 없음(`_draft_context`의 if/elif 체인은 도구상 3으로 잡히나 중첩 아님)
- domain 외부 의존 0, print 0, placeholder/TODO 0
- 로그: 요약·`action_node executing`은 키·길이만. dispatch 예외는 `exception=e`로 스택 포함(LOG 규칙 준수) — Design §7의 "절단" 문구와는 어긋남(GAP-I3의 실질은 outcome 문자열 미절단)

---

## 5. Gap List (검증 후 확정)

### Important (3)

| ID | 갭 | conf. | 검증 | 조치 |
|----|----|:--:|------|------|
| GAP-I1 | **FR-07 설정 경로 부재** — `tool_configs: dict[str, RagToolConfigRequest]` 고정 필드, `worker_skeleton_builder`가 `model_dump()`로 저장 → `draft_arg_key` 소실. 관례 키 도구는 무설정 동작하나 비관례 키 도구는 설정 불가 | 95% | 코드 확인(`schemas.py:57-73`, `worker_skeleton_builder.py:77,115`) | iterate: `RagToolConfigRequest.draft_arg_key: str \| None = None` 추가(additive). 프론트 타입 동기화는 후속 UI 사이클에 위임(Plan Out) |
| GAP-I2 | **§6.1 #8 오류 응답 미판정** — `_dispatch_once`가 반환 텍스트를 검사하지 않아 `Error executing tool…`이 `ok=True`로 기록 | 90% | `action_pipeline.py:228-229`, `ToolErrorPolicy.ERROR_PREFIXES` 존재 | iterate: `ToolErrorPolicy.ERROR_PREFIXES` 접두 판정 → 실패 처리 |
| GAP-I3 | **FR-25 실패 outcome 미절단** — `집행 실패: {e}`가 상한 없이 워커 산출→final_answer 프롬프트로 전파 | 85% | `action_pipeline.py:225-227` | iterate: `_OUTCOME_MAX_CHARS` 절단 |

### 수용·하향 (2)

| ID | 갭 | 판정 |
|----|----|------|
| GAP-I4 | `assert_assignable` 호출 1곳 | **수용** — `agent_tool.category`를 쓰는 API가 없음(리포지토리 매핑만 존재). 경로가 생기면 그때 호출 |
| GAP-I5 | 다회 턴 초안 잔존 시 영구 스킵 | **재현 불가로 Minor 하향** — 턴 저장은 최종 답변 문자열만(`run_agent_use_case.py:1352`), 재주입은 search/excel 스냅샷 한정이며 재주입 본문은 헤더가 달라 `is_draft_output` 첫 줄 판정을 통과하지 못함 |

### Minor (9)

M1 detect 시그니처 문서 불일치 · M2 compose 블록 순서 · M3 로그 `tool_id` · M4 상수명 · M5 바이트 동일 테스트 부재 · M6 §11.1 "수정" 테스트 3종을 신규 파일로 대체 · M7 `test_workflow_compiler_category.py` docstring 잔존 · M8 collect `_invoke_once` 비공개 유지 · M9 `_render_outcome` 부재, run cap 테스트 중간 import

---

## 6. Clean Architecture Compliance
domain → application 역참조 0. `action_pipeline`은 application에서 domain 정책·LangChain 메시지·MCP 어댑터 계약만 사용. 점수 100.

## 7. Convention Compliance
네이밍(`create_action_node`, `*Policy`, `*ToolConfig`) 준수. Design Ref 주석 모듈·핵심 지점에 존재. import 순서 위반 1건(테스트 파일 중간 import, M9). 점수 95.

---

## 8. Overall Score

| 항목 | 점수 |
|------|:--:|
| Match Rate | **91%** |
| Architecture | 100 |
| Convention | 95 |
| Critical / Important / Minor | 0 / 3 / 11 |

---

## 9. Recommended Actions

### 9.1 Immediate (iterate 대상)
1. GAP-I1 `RagToolConfigRequest.draft_arg_key` 추가 + 저장 왕복 테스트
2. GAP-I2 dispatch 오류 텍스트 판정(`ToolErrorPolicy.ERROR_PREFIXES`) + 테스트
3. GAP-I3 실패 outcome 절단 + 테스트

### 9.2 Short-term
- M5 final_answer 바이트 동일 테스트, M7 docstring 정리, M3 `tool_id` 로그 필드

### 9.3 Long-term
- L3 실런 세 지점 대조(메일 MCP 등록 후), 프론트 `draft_arg_key` 입력 폼(별도 사이클)

## 10. Design Document Updates Needed
- §3.1 `detect` 시그니처에 `later_outputs` 반영
- §2.2 compose 블록 순서를 구현(collect 동형)에 맞춤
- §7 로그 문구: "예외는 스택 포함(LOG 규칙), outcome 문자열만 절단"으로 정정
- §10.3 상수명 실제 이름으로

## 11. Iteration 1 결과 (2026-09-24)

| 갭 | 조치 | 검증 |
|----|------|------|
| GAP-I1 | `RagToolConfigRequest.draft_arg_key: str \| None`(max 100) 추가. `ToolFactory._parse_rag_config`가 `RagToolConfig` 필드만 취해 타 도구 키를 무시. 프론트 `types/ragToolConfig.ts`에 선택 필드 동기화(입력 폼은 후속) | `test_worker_skeleton_builder.py` 왕복 2건, `test_tool_factory.py` 1건 |
| GAP-I2 | `_dispatch_once`가 `ToolErrorPolicy.ERROR_PREFIXES` 접두 응답을 실패로 기록 | `test_action_pipeline.py::TestDispatchErrorResponses::test_error_text_response_is_failure` |
| GAP-I3 | 실패 outcome을 `_OUTCOME_MAX_CHARS`로 절단 | `…::test_failure_outcome_is_truncated` |

재검증: 관련 스위트 4,382 passed. FR-07·FR-25 ✅, §6.1 #8 ✅로 전환.

| 축 | 점수 |
|----|:--:|
| Structural | 92 |
| Functional | 92 (FR ✅25 / ❔1) |
| Contract | 90 |
| Runtime | 95 |
| **Overall** | **93%** |

잔여: Minor 11건(§5) + FR-26 실런 미확인. `/pdca report action-category-compose-node`로 진행.

## Version History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 0.1 | 2026-09-24 | 배상규 | 초안. gap-detector 정적 3축 + 런타임 388건. Important 5건 중 2건 검증 후 수용·하향 |
| 0.2 | 2026-09-24 | 배상규 | Iteration 1: Important 3건 수정, Match Rate 91→93% |
