# Gap Analysis — fix-agent-builder-tool-selection

> 분석일: 2026-06-01
> 단계: PDCA Check
> 기준 문서: `docs/01-plan/features/fix-agent-builder-tool-selection.plan.md`
> **Match Rate: 100%** ✅ — Plan §4/§5/§8의 모든 코드 항목 구현, 기능적 Gap 없음

---

## 1. 종합 점수

| 카테고리 | 점수 | 상태 |
|----------|:----:|:----:|
| 설계 일치 (§4/§5/§8) | 100% | ✅ |
| API 계약 동기화 (CLAUDE.md §4-1) | 100% | ✅ |
| TDD 충족 (§7) | 100% | ✅ |
| **종합** | **100%** | ✅ |

의도된 범위 제외(MCP 생성-시 연결, §5-5)와 사전 존재 DI 이슈(`TestRunAgent`)는 산정에서 제외.

---

## 2. §4 수정 범위 (6/6 구현)

| # | 내용 | 구현 위치 | 상태 |
|---|------|-----------|:----:|
| 1 | `CreateAgentRequest.tool_ids: list[str] \| None` | `schemas.py:42` | ✅ |
| 2 | `execute()` 우선순위 분기 (tool_ids→configs→AI) | `create_agent_use_case.py:59-71` | ✅ |
| 3 | `_build_skeleton_from_tool_ids` (config 매칭 주입) | `create_agent_use_case.py:184-216` | ✅ |
| 4 | `CreateBuilderAgentRequest.tool_ids?: string[]` | `agentBuilder.ts:12` | ✅ |
| 5 | `handleSave` form.tools→tool_ids 전송 | `index.tsx:145-157` | ✅ |
| 6 | MCP 도구 생성-시 가드 | `index.tsx`(전송 제외) + FormView(UI 비활성) | ✅ |

> §6 가드는 **택1-A(비활성+툴팁)와 택1-B(전송 제외)를 둘 다** 적용 — Plan 요구보다 견고.

---

## 3. §5 수정 방향 일치

- §5-1~§5-4: Plan 제시 코드와 분기 순서·메서드 시그니처 1:1 일치.
- §5-3 미등록 도구 방어책: "라우터 422 **또는** 프론트 차단" 택1 중 **프론트 차단(§5-5)** 채택. `get_tool_meta`(`tool_registry.py:47-51`)가 `ValueError("Unknown tool_id")`를 던지고 백엔드 테스트가 검증. 라우터 422 미구현은 누락 아님(택1 충족).

---

## 4. §7 TDD (백엔드 6 + 프론트 3 전부 구현)

- 백엔드 `TestExplicitToolIdsSelection` (`test_create_agent_use_case.py`): 셀렉터 미호출 / 워커 구성 / prefix normalize / RAG config 매칭(+비매칭 None) / 빈 리스트 폴백 / MCP id ValueError — Plan 6케이스 전부 커버. **30 passed**.
- 프론트 (`AgentBuilderFormView.test.tsx`): tool_ids 전송 / 미선택 시 미전송 / MCP 비활성 — 3건 전부 구현. **7 passed**.

---

## 5. Gap 목록

**기능적 Gap 없음.** 잔여는 검증 권장 항목뿐:

| 우선순위 | 항목 |
|:--------:|------|
| 🟢 Low | DoD 검증 스킬 4종(`/verify-architecture`, `/verify-logging`, `/verify-tdd`, `/api-contract-sync`) 실행으로 최종 그린 확정 |
| 🟢 Low | "내부 도구 선택→생성 반영" end-to-end 수동 QA 1회 |

- **의도된 범위 제외(Gap 아님)**: MCP 생성-시 실제 연결 (Plan §5-5 후속 과제).
- **사전 존재 이슈(무관)**: `tests/api/test_agent_builder_router.py::TestRunAgent::*` 3건 — `get_assemble_auth_context_use_case` DI 미초기화. 이번 변경과 무관(격리 실행에서도 동일 실패).

---

## 6. 구현 품질 관찰

- `tool_ids=[]`(falsy)일 때 백엔드 `if request.tool_ids:`가 AI 폴백 — 프론트 `length>0 ? : undefined`와 이중 정합.
- MCP 가드가 UI 비활성 + 전송 필터 양쪽 적용 → UI 우회해도 MCP id 미유출.
- UseCase가 domain(`get_tool_meta`/`WorkflowSkeleton`)만 참조, 인프라 직접 참조 없음 — CLAUDE.md §6 위반 없음.

---

## 7. 결론 / 다음 단계

Match Rate **100%** (≥ 90%). 자동 개선(iterate) 불필요.
→ `/pdca report fix-agent-builder-tool-selection` 로 완료 보고서 진행 권장.
