# Gap Analysis: fix-chat-reasoning-object-render

> 분석일: 2026-06-08
> 분석 대상: Plan ↔ Implementation/Tests
> Match Rate: **100%**

---

## 1. 분석 개요

| 항목 | 내용 |
|------|------|
| Plan | `docs/01-plan/features/fix-chat-reasoning-object-render.plan.md` |
| Implementation (BE) | `src/domain/llm/message_content.py` (신규), `src/application/agent_builder/run_agent_use_case.py` (`_map_chat_stream`), `src/application/general_chat/use_case.py` (`_map_token`) |
| Implementation (FE) | `idt_front/src/hooks/useChatStream.ts:95`, `idt_front/src/hooks/useAgentRunStream.ts:131` |
| Tests (BE) | `tests/domain/llm/test_message_content.py`, `test_run_agent_use_case_stream.py::TestStreamTokenEvents` (신규 2), `tests/application/general_chat/test_use_case.py::TestChatTokenContentNormalization` (신규 2) |
| Tests (FE) | `useChatStream.test.ts` (신규 1), `useAgentRunStream.test.ts` (신규 1) |
| Test Result | BE: 10/10 (helper), +2 agent stream, +2 general chat 모두 PASS / FE: useChatStream 13/13, useAgentRunStream 14/14 PASS, `tsc --noEmit` 무에러 |

## 2. 카테고리별 점수

| Category | Score | Status |
|----------|:-----:|:------:|
| Plan §3 Scope Coverage (5 items) | 100% | ✅ PASS |
| Plan §4 Solution Semantic Match | 100% | ✅ PASS |
| Plan §5 Test Cases Coverage | 100% | ✅ PASS |
| Plan §6 Out-of-Scope / 호환성 보존 | 100% | ✅ PASS |
| **Overall Match Rate** | **100%** | **✅ PASS** |

## 3. Plan §3 수정 범위 커버리지

| # | Plan Item | Expected | Actual | Status |
|---|-----------|----------|--------|:------:|
| 1 | `coerce_message_text(content) -> str` 헬퍼 (str 통과 / list 평탄화 / 그 외 "") | 공용 util 신규 | `src/domain/llm/message_content.py` 신규 — 동일 시그니처·동작 | ✅ Minor Deviation (위치) |
| 2 | `run_agent_use_case._map_chat_stream`에 헬퍼 적용 + 빈 문자열이면 None | 매핑 수정 | `run_agent_use_case.py` `_map_chat_stream` 적용, `if not chunk_text: return None` 보존 | ✅ |
| 3 | `general_chat/use_case._map_token`에 헬퍼 적용 | 매핑 수정 | `use_case.py` `_map_token` 적용, 스킵 가드 보존 | ✅ |
| 4 | `useChatStream.ts` / `useAgentRunStream.ts` string 가드 | 2차 안전망 | 두 hook `chat_token`/`agent_token`에 `typeof chunk === 'string' ? chunk : ''` 가드 | ✅ |
| 5 | 백엔드/프론트 회귀 테스트 | 신규 테스트 | BE 6개 + FE 2개 신규 추가, 전부 PASS | ✅ |

**Minor deviation (개선)**: Plan §3은 헬퍼 위치를 "`src/application/agent_builder/_text.py` 또는 기존 공용 util"로 제시했으나, 실제로는 `src/domain/llm/message_content.py`(domain 순수 함수)에 배치. 두 application use_case가 공유하므로 application 하위 특정 모듈보다 domain 공용이 응집도·재사용 측면에서 더 적절하며, 외부 의존 없는 순수 함수라 레이어 규칙 위반 없음. Plan 의도(공용 헬퍼) 자체는 충족.

## 4. Plan §4 솔루션 의미적 일치도

| 요소 | Plan §4 (예시) | 실제 구현 | 동등성 |
|------|---------------|-----------|:------:|
| str 통과 | `if isinstance(content, str): return content` | 동일 | ✅ |
| list 평탄화 | str 요소 + dict의 `"text"` join | 동일 (`isinstance(block, str)` / `isinstance(block, dict)` + `block.get("text")` str 검사) | ✅ |
| 비-텍스트 block 무시 | tool_use 등 제외 | `text`가 str일 때만 append → 무시 | ✅ |
| 그 외 타입 | `return ""` | 동일 (None/숫자 → "") | ✅ |
| BE 적용부 빈문자 스킵 | `if not chunk_text: return None` | 양쪽 매핑 모두 기존 가드 보존 | ✅ |
| FE 가드 | `typeof chunk === 'string' ? chunk : ''` | 두 hook 동일 | ✅ |
| FE 타입 계약 | `chunk: string` 유지, 가드만 추가 | `types/websocket.ts` 무변경, 가드만 추가 | ✅ |

## 5. Plan §5 테스트 케이스 커버리지

| Plan 테스트 | 의미 | 실제 테스트 | 상태 |
|------------|------|------------|:----:|
| 5-1 | content 정규화 단위(str/block list/non-text/None) | `test_message_content.py` 10개 (passthrough/empty/flatten/ignore-non-text/mixed/no-text-key/non-str-text/none/unexpected/empty-list) | ✅ 초과 달성 |
| 5-2 | 매핑 회귀(list→str, text 없으면 스킵) — agent | `TestStreamTokenEvents::test_content_block_list_is_flattened_to_str`, `..._without_text_is_skipped` | ✅ |
| 5-2 | 매핑 회귀 — general chat | `TestChatTokenContentNormalization::test_content_block_list_flattened`, `..._without_text_skipped` | ✅ |
| 5-3 | 프론트 토큰 결합 회귀(`[object Object]` 미발생) | `useChatStream.test.ts` + `useAgentRunStream.test.ts` 각 1개 (`not.toContain('[object Object]')`) | ✅ |

## 6. Plan §6 영향 범위 / 호환성 보존

| 항목 | Plan 기대 | 실제 | 상태 |
|------|-----------|------|:----:|
| 정상 str chunk 경로 | 변경 없음 | 헬퍼가 str 통과, 기존 토큰 테스트 영향 없음 | ✅ |
| 빈 문자열 스킵 로직 | 보존 | `if not chunk_text: return None` 양쪽 유지 | ✅ |
| 레이어 규칙 | 위반 없음 | domain 순수 함수, import 정상 로드 확인 | ✅ |
| FE 타입 계약 | `chunk: string` 유지 | 무변경 + tsc 무에러 | ✅ |

## 7. Gap / 후속 항목

| 구분 | 내용 | 처리 |
|------|------|------|
| Gap | 없음 (모든 Plan 범위·테스트 충족) | — |
| 후속(Plan §8) | WS payload 스키마에서 `chunk: str` pydantic 강제 검증 추가 | 별도 이슈 |
| 후속(Plan §8) | non-text block(tool_use 등) 토큰 표시 제외 — 추론 가시화 필요 시 STEP_REASONING 경로로 별도 노출 | 별도 검토 |
| 수동 검증 | 실제 list-content 모델(예: Anthropic block)로 `/chatpage` dev 서버 수동 확인 | 권장 (자동 테스트로 동등 검증됨) |

## 8. 결론

- **Match Rate 100%** — Plan §3 범위 5개 항목, §4 솔루션 의미, §5 테스트, §6 호환성 모두 충족.
- 단일 Minor deviation(헬퍼 위치 domain 배치)은 Gap이 아니라 레이어 규칙 부합·재사용성 향상의 개선.
- 근본 수정(백엔드 정규화) + 2차 안전망(프론트 가드) 이중화로 재발 방지까지 확보.
- 다음 단계: `/pdca report fix-chat-reasoning-object-render` (완료 보고서). 코드 정리 필요 시 `/simplify` 선행 가능.
