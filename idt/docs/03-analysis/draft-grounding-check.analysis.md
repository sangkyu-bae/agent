# draft-grounding-check Gap Analysis

> **Date**: 2026-09-30 | **Phase**: Check → Act-1 | **Match Rate**: 89.8% → **92.5%** (Act-1, runtime 공식)
> **Plan**: [plan](../01-plan/features/draft-grounding-check.plan.md) (v0.2) · **Design**: [design](../02-design/features/draft-grounding-check.design.md) (v0.3)
> 분석: bkit:gap-detector (정적) + 메인 세션 (전체 회귀·L3 실런 기록 근거, G-3·G-4 코드 재확인)
> Formula: Structural×0.15 + Functional×0.25 + Contract×0.25 + Runtime×0.35

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 초안·답변 LLM 이 근거 없는 사실(연락처 등)을 반복 생성 — 금융 고객 응대에 지어낸 정보가 섞일 위험. 값의 적절성은 질문마다 달라 고정 규칙으로는 판단 불가. |
| **WHO** | P2 — 에이전트 소유자·승인자, 채팅 사용자, 최종 수신 고객. |
| **RISK** | 판정기 LLM 비용·지연 → 근거 있는 런만·전역 토글. 판정기 오판 → 규칙 힌트 병행·high 만 재작성·fail-open. 판정 JSON 채팅 누출 → 내부 태그로 스트림 제외. |
| **SUCCESS** | L3 초안·채팅 답변에 근거 없는 연락처 0 / 근거에 있는 값 유지 / 판정 실패 시 정상 반환 / 루프 토큰 채팅 노출 0 / 리서치·엑셀 회귀 0. |
| **SCOPE** | 판정기 확장 → 공통 재작성 루프 → action 초안 적용 → final_answer 적용 → 스트리밍 보류 → 설정. |

---

## 1. Scores

| Axis | Score | Notes |
|------|:-----:|-------|
| Structural | 97% | 설계 §2.1/§11.1 파일 전부 존재, 테스트 4파일 + 스트림 테스트. 설계에 없는 로그 이벤트·필드(G-11) |
| Functional | 92% | 플레이스홀더 없음, D1–D7·G1–G9·I1–I7 테스트 존재. final_answer 코퍼스 순서(G-4), 차트 단독 활성(G-3), 재작성 AIMessage 메타 유실(G-5) |
| Contract | 90% | 포트·VO·GroundedGenerator·create_action_node·WorkflowCompiler 파라미터·설정 5종·INTERNAL_LLM_TAG·스키마 일치. `grounding skipped` reason 필드 없음(G-1), judge 실패 로그가 예외 전체(G-2) |
| Runtime | 85% | 전체 회귀 53 failed(상시 목록) / 10208 passed. 관련 스위트 1101 pass. L3(gpt-4o 판정기): 초안 5/6 승인 등록·근거 없는 번호 0(실패 1 = 기존 인자 조립), 채팅 WS 2/2·내부 태그/final_answer 토큰 0. 최종 확인 런은 OpenAI 429(크레딧 소진)로 중단 — D-13·D-14 보정은 기록된 판정 재생으로만 확인 |
| **Overall** | **89.8%** | 97×0.15 + 92×0.25 + 90×0.25 + 85×0.35 = 14.55 + 23.0 + 22.5 + 29.75 |

## 2. Success Criteria

| SC | Status | Evidence |
|----|:------:|----------|
| SC-1 L3 초안 ×3 근거 없는 연락처 0 | ✅ Met | gpt-4o 판정기 런 초안 5건 모두 phones=[] (l3g3·l3g4). 초안 생성 실패 1건은 인자 조립 `grounded=false`(승인자 선택 인자) — 기존 결함 |
| SC-2 L3 채팅 답변 근거 없는 연락처 0 | ✅ Met | WS 2/2 answer_phones=[] (l3g3) |
| SC-3 근거에 있는 값 유지(과검출 0) | ⚠️ Partial | 단위: test_grounding.py(D-13 원문 그대로 제외), test_grounded_generation.py. L3: 채팅 요약에서 제목·이름·300만원·크크크론 유지(gpt-4o). 위키 대표번호 시나리오 미수행. gpt-4o 도 값 없는 채널 안내("영업점 방문")를 high 로 잡는 경향 |
| SC-4 판정기 예외 시 원문 유지 | ✅ Met (unit) | test_grounded_generation.py G5, test_grounded_wiring.py. L3 미수행 |
| SC-5 판정 JSON·재작성 토큰 채팅 노출 0 | ✅ Met | run_agent_use_case.py `_map_chat_stream` 태그 필터 + test_grounding_internal_tag_is_not_streamed. L3 WS token_nodes=['model','supervisor'], JSON 0 |
| SC-6 리서치·엑셀 회귀 0, 상시 목록 외 실패 0 | ✅ Met | 전체 회귀 53 failed 모두 상시 목록(api stream 9·general_chat 7·main 1·main_logging 1·ws_auth 2·collection 4·es 1·pymupdf 21·parent_child 7) |

Success Rate: 5/6 Met, 1 Partial.

## 3. Design Decisions

| # | Status | Evidence |
|---|:------:|----------|
| D-01 LLM 판정 + 힌트 | ✅ | grounding_hints.py (차단 권한 없음), grounded_generation.py `_judge_safely` |
| D-02 초안+답변 | ✅ | action_pipeline.py `_compose_grounded`, workflow_compiler.py `_generate_final_answer` |
| D-03 상한 2/1 | ✅ | config.py, main.py 주입 |
| D-04 내부 태그 스트림 제외 | ✅ | action_pipeline.py·workflow_compiler.py·adapter.py 태그, run_agent_use_case.py 필터 |
| D-05 high 만 | ✅ | GroundingVerdict.high_claims |
| D-06 fail-open | ✅ | `_judge_safely` → None, adapter 재발생 |
| D-07 문장 제거·빈 결과 처리 | ✅ | `_strip`, action 빈 초안 → 작성 실패 |
| D-08 evaluate 불변·포트 | ✅ | use_case.py → HallucinationEvaluatorPort |
| D-09 비활성 조건 호출 0 | ⚠️ | 차트만 있는 런은 활성(G-3), 활성+근거 공백 시 첫 초안에 태그(G-9) |
| D-10 코퍼스 상한·순서 | ⚠️ | action 경로 최신 우선 OK, final_answer 는 오래된 워커 결과 먼저(G-4) |
| D-11 판정 전용 모델 | ✅ | config.py `grounding_judge_model`, main.py `get_grounding_judge_llm_provider` (실측 gpt-4o 해석) |
| D-12 태그 경계·품질 비판정 | ✅ | prompts.py |
| D-13 원문 그대로 주장 제외 | ✅ | GroundingVerdict.excluding_found_in, 재생 검증 양성 대조군 0/3 제외 |
| D-14 글 단위 경계·공백 흡수 | ✅ | grounding_edit.py |

## 4. Gaps

### Important
| ID | Location | Issue | Conf. |
|----|----------|-------|:-----:|
| G-2 | grounded_generation.py `_judge_safely`, adapter.py `judge` | 판정 실패를 예외 객체로 로깅 — 구조화 출력 파싱 오류면 메시지에 판정기 원출력(주장 span)이 실릴 수 있음. §6·§7 은 예외 타입만 허용 | 60 |
| G-4 | workflow_compiler.py `_answer_grounding_sources` | 워커 결과가 오래된 것부터 → 24000자 초과 시 최신 워커 산출이 먼저 잘림(D-10 역순) | 85 |

### Minor
| ID | Location | Issue | Conf. |
|----|----------|-------|:-----:|
| G-1 | grounded_generation.py `run` | `grounding skipped` 에 reason(disabled/no_sources/no_judge) 없음 | 95 |
| G-3 | workflow_compiler.py final_answer | 차트 블록만 있어도 루프 활성 — D-09 는 워커 산출 기준 | 70 |
| G-5 | workflow_compiler.py `_generate_final_answer` | 교체 시 새 AIMessage 로 usage·response_metadata 유실 | 80 |
| G-6 | workflow_compiler.py `_create_final_answer_node` | 40줄 초과(기존 위반, +8줄) | 90 |
| G-7 | action_pipeline.py `_compose_draft` | 작성 실패 `error=str(e)` — 스택 없음(기존) | 85 |
| G-8 | adapter.py `_resolve_judge_chain` | 공급자 None 시 레거시 폴백이 gpt-4o-mini | 75 |
| G-9 | action_pipeline.py `_compose_grounded` | 활성+근거 공백이면 판정 없이 첫 초안만 태그 | 70 |
| G-11 | design §5.4/§6/헤더 | `grounding_judge_model`·`literal_dropped`·추가 로그 2종 미기재, 헤더 v0.2 | 95 |
| G-12 | adapter.py + grounded_generation.py | 판정 실패 1건이 ERROR+WARNING 이중 로깅 | 90 |

### 설계 외 추가(의도)
- 재작성 호출 예외 시 현재 글에서 문장 제거(test_grounded_generation.py)
- span 이 원문에 없으면 원문 유지·stripped=False

### 범위 밖 (이월)
- 인자 조립 LLM 이 선택 인자(approver)를 필수로 보고 `grounded=false` — approval-gate-run-termination 이월 G1 계열
- SSE `/run/stream` 쿼리 토큰 인증 미배선(상시 실패 test_agent_builder_router_stream)
- L3 재확인(크레딧 충전 후): D-13·D-14 실런, SC-3 위키 번호, SC-4 판정기 장애 주입

## 5. Recommended Actions
1. G-4: `_answer_grounding_sources` 에서 근거 블록을 최신 워커 우선으로
2. G-2 + G-12: 판정 실패 로그를 `exception_type` 으로, adapter 쪽은 error 유지하되 메시지 원문 제외
3. G-1, G-3: skip reason 필드, final_answer 활성 판단을 워커 산출 존재로
4. G-11: 설계 §5.4·§6·헤더 갱신
5. 크레딧 충전 후 L3 재실행

## 6. Act-1 (2026-09-30)

사용자 결정: "지금 모두 수정". 테스트 먼저(Red 8건) → 구현 → Green.

| Gap | 조치 | 검증 |
|-----|------|------|
| G-4 | `_answer_grounding_sources(system_prompt, worker_outputs, conversation)` — 워커 산출 최신 우선 | test_grounded_wiring `test_코퍼스는_최신_워커_산출_우선` |
| G-3 | 활성 판단을 blocks → worker_outputs 로. 차트만 있으면 판정 0 | `test_차트만_있으면_판정하지_않는다` |
| G-2 | 판정 실패 로그 = `exception_type` + `stack`(프레임만), 메시지 미기록 | test_grounded_generation `test_판정_실패_로그는_타입과_스택만` (원출력 값 미노출 단언) |
| G-12 | 어댑터 `judge()` 로깅 제거(재발생만) → 실패 로그 1곳 | test_adapter `test_실패는_로깅_없이_재발생` |
| G-1 | `grounding skipped` reason = disabled / no_judge / no_sources | `test_skip_로그에_사유` ×3 |
| G-5 | 교체 답변은 `response.model_copy(content=...)` — usage·response_metadata 보존 | `test_교체된_답변도_응답_메타데이터를_보존한다` |
| G-11 | 설계 v0.3: 헤더, §4.3 실패 로깅, §5.3 코퍼스, §5.4 `grounding_judge_model`·주입, §6 로그 이벤트·필드 | 문서 |

유지(범위 밖·저빈도): G-6·G-7 기존 위반, G-8 레거시 폴백(등록 모델 0개일 때만), G-9 action 경로 근거 공백(대화가 항상 포함되어 사실상 미발생).

| Axis | Before | After |
|------|:------:|:-----:|
| Structural | 97 | 98 |
| Functional | 92 | 96 |
| Contract | 90 | 96 |
| Runtime | 85 | 85 (L3 재실런 불가 — OpenAI 크레딧 소진) |
| **Overall** | 89.8 | **92.5** (98×0.15 + 96×0.25 + 96×0.25 + 85×0.35 = 14.7 + 24.0 + 24.0 + 29.75) |

회귀: 관련 스위트 1108 pass. 전체 53 failed(상시 목록 동일) / 10218 passed.

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2026-09-30 | Check — 89.8% |
| 0.2 | 2026-09-30 | Act-1 — 92.5% |
