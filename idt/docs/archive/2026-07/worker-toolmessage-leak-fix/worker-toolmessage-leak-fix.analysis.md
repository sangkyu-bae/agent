# Worker ToolMessage Leak Fix Gap Analysis

> **Match Rate: 100% (24/24)** — FR-06(E2E 수동 이월)은 분모 제외, Gap 0건
>
> **Project**: sangplusbot (idt 백엔드)
> **Analyzer**: gap-detector
> **Date**: 2026-07-29
> **Design Reference**: `docs/02-design/features/worker-toolmessage-leak-fix.design.md`

---

## 1. 판정 요약

| 구분 | 검증 항목 | Match | Gap |
|------|-----------|:-----:|:---:|
| Design 결정 (D1~D4·§4.3 기각·§7) | 16 | 16 | 0 |
| 테스트 설계 (§5.1 TC-01~06, §5.2 기존 갱신) | 8 | 8 | 0 |
| **합계** | **24** | **24** | **0** |

## 2. Design 결정 대조 (발췌)

| 항목 | 설계 기대 | 구현 실측 | 판정 |
|------|-----------|-----------|:----:|
| D1 최종 답변 재생성 1건 반환 | §2.2 content 추출 → `AIMessage(name=worker_id)` | `workflow_compiler.py:997-1018` | Match |
| D1 빈 결과 graceful | `content=""` | 초기화 + `if result_messages` 가드 | Match |
| `AIMessage` 모듈 상단 import | §2.2 | `workflow_compiler.py:4` | Match |
| D2 `_is_tool_message` dict/객체 양형 | §3.2 | `workflow_compiler.py:102-106` 문자 단위 일치 | Match |
| D2 conversation 필터 결합 | §3.2 | `workflow_compiler.py:612-615` | Match |
| D3 token_delta 공식 | `len//4 if str else 0` | `workflow_compiler.py:1010-1012` | Match |
| §4.3 기각 항목 무변경 (`_analyze_context`·`_is_worker_output`·supervisor_nodes) | 무변경 | 전부 무변경 실측 | Match |
| `search_pipeline.py`·`_wrap_sub_agent` 무변경 | §3.1/§7 | 무변경 | Match |

## 3. FR 충족표 (Plan §3.1)

| FR | 내용 | 근거 | 판정 |
|----|------|------|:----:|
| FR-01 | 워커 산출물 = 최종 AIMessage 1건 (트레이스 미유출) | 구현 + TC-01 | 충족 |
| FR-02 | 직답 워커 동일 규약 | TC-02·TC-04 | 충족 |
| FR-03 | final_answer LLM 입력 tool 역할 부재 | 필터 + TC-05/06 | 충족 |
| FR-04 | token_delta 신규 산출분 기준 | TC-03 | 충족 |
| FR-05 | 타 워커 노드 규약·동작 불변 | 코드 무변경 실측 | 충족 |
| FR-06 | 위키 워커 E2E 완주 | **수동 이월** (Qdrant/ES 기동 시 위키 질의로 확인) | 이월 |

## 4. Gap 목록

없음. 설계에 없는 구현 변경도 없음 — 이번 기능의 diff는
`workflow_compiler.py`(D1·D2·D3·import) + `test_worker_trace_leak.py`(신규) +
`test_workflow_compiler.py`(TC-18 갱신)로 한정.

## 5. 참고 사항 (Gap 아님 — 후속 정리 후보)

1. TC-01의 `assert not getattr(msg, "tool_calls", [])`는 재생성 AIMessage가 항상
   `tool_calls=[]`라 사실상 항진 단언 — 실질 방어는 `len(out) == 1` 단언이 담당.
2. `final_answer_node`의 응답 token_delta(682행)는 D3의 `isinstance(str)` 가드가 없어
   block-list content에서 기존 부정확성이 남음 — 사전 존재, 이번 범위 밖.
3. `test_worker_trace_leak.py`의 `_make_compiler()`가 `test_workflow_compiler.py`의
   동명 헬퍼(튜플 반환)와 시그니처가 다름 — 파일 간 혼동 여지만 있고 동작 문제 없음.
4. "content가 block list → token_delta 0" 분기는 구현되어 있으나 전용 테스트 없음
   (설계 TC 목록에도 없어 요구사항 아님).

## 6. 결론

Match Rate 100% ≥ 90% — Act 반복 불필요.
다음: `/pdca report worker-toolmessage-leak-fix`.
FR-06 E2E는 기존 E2E 이월 체크리스트(Qdrant/ES 기동 시 일괄 검증)에 합류.
