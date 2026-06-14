# Gap Analysis: fix-anthropic-prefill-error

> 분석일: 2026-06-11
> 분석 대상: Design ↔ Implementation/Tests
> Match Rate: **100%**

## 1. 분석 개요

| 항목 | 내용 |
|------|------|
| Design | `docs/02-design/features/fix-anthropic-prefill-error.design.md` |
| Plan(참고) | `docs/01-plan/features/fix-anthropic-prefill-error.plan.md` |
| 구현 | `message_normalization.py`(신규), `supervisor_nodes.py`, `workflow_compiler.py`, `claude_client.py` |
| 테스트 | `test_message_normalization.py`, `test_supervisor_nodes.py`, `test_workflow_compiler.py`, `test_claude_client.py` |
| 검증 방식 | 정적 코드 비교 + 테스트 실행(Do 단계에서 agent_builder 337 passed, llm+general_chat 168 passed 확인) |

## 2. 항목별 일치 표

| # | 검증 항목 | 설계 위치 | 구현 위치 | 결과 |
|---|-----------|-----------|-----------|:----:|
| 1 | `ensure_user_tail` 시그니처 `(messages, instruction=DEFAULT_CONTINUATION)` | §2-1 | `message_normalization.py:22-25` | 일치 |
| 1 | `DEFAULT_CONTINUATION` 상수 | §2-1 | `message_normalization.py:10` (문구 동일) | 일치 |
| 1 | dict/LangChain 양쪽 role 추출 (`_tail_role`) | §2-1 | `message_normalization.py:15-19` (`dict→role`, `객체→type`) | 일치 |
| 1 | 비파괴(원본 무변형, 새 리스트 반환) | §2-1 | `[*messages, ...]` 신규 리스트 | 일치 |
| 1 | 빈 배열 처리(D5): instruction truthy면 `[HumanMessage]`, 아니면 그대로 | §2-1, D5 | 구현 일치 | 일치 |
| 2 | supervisor: system 선두 + `ensure_user_tail` | §2-2 | `supervisor_nodes.py:183-186` | 일치 |
| 2 | `SUPERVISOR_TAIL_INSTRUCTION` 상수(문구 동일) | §2-2 | `supervisor_nodes.py:107-109` | 일치 |
| 2 | `decision_prompt` 텍스트 본문 무변경 (위치/role만 변경) | §2-2, §2-7 | 본문 유지, system으로만 이동 | 일치 |
| 3 | `_wrap_worker`: `ensure_user_tail` 적용 + 워커 지시 문구 | §2-3 | `workflow_compiler.py:726-736` | 일치 |
| 4 | `_analyze_context`: 검색 필터 후 `ensure_user_tail` | §2-4 | `workflow_compiler.py:700-703` (system 선두 + conversation) | 일치 |
| 5 | `final_answer_node`: `conversation_messages`에 `ensure_user_tail` | §2-5 | `workflow_compiler.py:547-556` | 일치 |
| 6 | `_build_messages`: warning 로그 + continuation HumanMessage append (D3) | §2-6, D3 | `claude_client.py:63-71` | 일치 |
| 7 | GeneralChatUseCase / 프롬프트 본문 / 대화 메모리 정책 무변경 | §2-7 | 변경 파일에 미포함, 프롬프트 본문 유지 | 일치 |
| 8 | 테스트 TC-01~14 존재 | §3 | 아래 표 참조 | 일치 |
| 9 | 레이어 규칙: domain에 LangChain 의존 추가 없음 | §2-7, CLAUDE.md | 변경 4파일 모두 application/infrastructure 레이어 | 일치 |

### 2-1. 테스트 매핑 (TC-01~14)

| TC | 설계 | 실제 테스트 | 결과 |
|----|------|-------------|:----:|
| TC-01 user-last no-op | §3-1 | `test_message_normalization.py::test_tc01` | 있음 |
| TC-02 AI-last append + 원본 보존 | §3-1 | `test_tc02` | 있음 |
| TC-03 연속 AI → Human 1개 | §3-1 | `test_tc03` | 있음 |
| TC-04 tool-last no-op | §3-1 | `test_tc04` | 있음 |
| TC-05 dict assistant-last append | §3-1 | `test_tc05` (+`tc05b` dict user-last no-op 추가) | 있음 |
| TC-06 빈 배열+instruction | §3-1 | `test_tc06` (+`tc06b` 빈 instruction 추가) | 있음 |
| TC-07 원본 불변 | §3-1 | `test_tc07` | 있음 |
| TC-08 1차 판단 system 선두/user-last | §3-2 | `test_supervisor_nodes.py::test_tc08` | 있음 |
| TC-09 2차 판단 not assistant-last | §3-2 | `test_tc09` | 있음 |
| TC-10 `_wrap_worker` user-last | §3-3 | `test_workflow_compiler.py::test_tc10` | 있음 |
| TC-11 `_analyze_context` user-last | §3-3 | `test_tc11` | 있음 |
| TC-12 `final_answer` no-op 회귀 | §3-3 | `test_tc12` (+`tc12b` assistant-last 교정 추가) | 있음 |
| TC-13 `_build_messages` assistant-last append+warning | §3-4 | `test_claude_client.py::test_tc13` | 있음 |
| TC-14 user-last 가드 미발동 | §3-4 | `test_tc14` | 있음 |

설계 TC 14건 전부 구현됨. 추가로 `tc05b`/`tc06b`/`tc12b` 3건이 보강되어 커버리지 상회(설계 초과는 Gap 아님).

## 3. Gap 목록

발견된 불일치 없음.

참고(비-Gap, 정보성):
- (Info) 설계 §2-1 주석에서 언급한 "`search_pipeline._message_role` public 승격 재사용" 옵션은 채택하지 않고 `_tail_role`를 로컬 정의 — 설계가 "구현 시 선택"으로 명시했으므로 정상 범위.
- (Info) TC-02 설계 예시는 `AIMessage(name="w0")`, 구현 테스트는 `name="worker_0"` — 명칭만 다르고 검증 의미 동일.
- (Info) 설계 §4 구현 순서 7항의 "수동 스모크(Anthropic 2-스텝 실행) 400 미발생 확인"은 자동 검증 불가 항목. 코드 레벨로는 4+1 지점 모두 user-last 불변식이 보장되나, 실 Anthropic 호출 스모크는 별도 수동 확인 필요(권장 조치 참조).

## 4. Match Rate

| 카테고리 | 점수 | 상태 |
|----------|:----:|:----:|
| 설계 일치 (§2-1~2-7) | 100% | OK |
| 테스트 설계 (§3, TC-01~14) | 100% | OK |
| 레이어 규칙 준수 | 100% | OK |
| **종합** | **100%** | OK |

## 5. 권장 조치

즉시 조치 필요 항목 없음. 후속 권장:
1. (선택) 설계 §4-7 수동 스모크: Anthropic provider(claude-sonnet-4-6)로 supervisor 워커 1회 경유 후 2차 판단까지 실행하여 400 prefill 미발생 실측.
2. (완료) 테스트 실행 검증 — Do 단계에서 agent_builder 337 passed / llm+general_chat 168 passed, 2 skipped 확인.
3. (기록) Out of Scope로 명시된 Opus 4.7+/Fable 5의 `temperature` 400 이슈는 후속 과제로 유지(본 분석 범위 아님).
