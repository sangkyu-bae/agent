# 완료 보고서 — fix-agent-builder-tool-selection

> 작성일: 2026-06-01
> 단계: PDCA 완료 (Plan → Do → Check → Report)
> Match Rate: **100%**

---

## 1. Executive Summary

### 1.1 프로젝트 개요

| 항목 | 내용 |
|------|------|
| Feature | fix-agent-builder-tool-selection |
| 유형 | 버그 수정 (풀스택) |
| 시작 | 2026-05-31 (Plan) |
| 완료 | 2026-06-01 (Report) |
| 기간 | 1일 |
| PDCA 경로 | Plan → Do → Check(100%) → Report (Design 생략: 소규모 버그) |

### 1.2 결과 요약

| 지표 | 값 |
|------|----|
| Match Rate | 100% |
| 변경 파일 | 6개 (소스 4 + 테스트 2) |
| 코드 변경 | +240 / -5 lines |
| 신규 테스트 | 9개 (백엔드 6 + 프론트 3) |
| 테스트 결과 | 백엔드 agent_builder 30 passed / 프론트 7 passed / tsc 0 error |
| Iteration | 0회 (1회차에 90% 초과) |

### 1.3 Value Delivered (4-관점)

| 관점 | 전달 가치 (실측) |
|------|------------------|
| **Problem** | `/agent-builder` 생성 시 선택한 도구가 서버로 전송되지 않아(요청 바디 누락 + 백엔드 수신 필드 부재) 사용자의 선택이 무시되던 버그 → **해결** |
| **Solution** | 프론트 `handleSave`에 `form.tools` → `tool_ids` 전송 추가, 백엔드 `CreateAgentRequest.tool_ids` 신규 + `_build_skeleton_from_tool_ids()` 분기(우선순위: tool_ids → tool_configs → AI 자동) |
| **Function/UX Effect** | 선택한 내부 도구가 그대로 에이전트에 반영. 미선택 시 기존 AI 자동 선택 유지(하위 호환). MCP 도구는 생성 단계에서 비활성화 + 안내 |
| **Core Value** | "선택한 대로 동작한다"는 예측 가능성 회복 — Agent Builder 통제권/신뢰성 확보 |

---

## 2. 근본 원인 → 해결 매핑

| 근본 원인 (Plan §2) | 해결 |
|---------------------|------|
| `form.tools` useState는 정상이나 `handleSave`가 페이로드에 미포함 | `index.tsx:145-157`에서 `tool_ids` 전송 |
| 백엔드 `CreateAgentRequest`에 `tool_ids` 필드 부재 | `schemas.py:42` 필드 추가 |
| 명시적 도구 선택 경로 부재 | `create_agent_use_case.py` 우선순위 분기 + `_build_skeleton_from_tool_ids` |
| MCP 도구 생성 단계 미지원(`get_tool_meta` ValueError) | UI 비활성 + 전송 제외 양방향 가드 |

---

## 3. 변경 내역

### 백엔드 (idt)
| 파일 | 변경 | 라인 |
|------|------|------|
| `src/application/agent_builder/schemas.py` | `CreateAgentRequest.tool_ids` 필드 | +2 |
| `src/application/agent_builder/create_agent_use_case.py` | 우선순위 분기 + `_build_skeleton_from_tool_ids()` | +41/-? |
| `tests/application/agent_builder/test_create_agent_use_case.py` | `TestExplicitToolIdsSelection` 6 케이스 | +97 |

### 프론트엔드 (idt_front)
| 파일 | 변경 | 라인 |
|------|------|------|
| `src/types/agentBuilder.ts` | `CreateBuilderAgentRequest.tool_ids?` | +1 |
| `src/pages/AgentBuilderPage/index.tsx` | `tool_ids` 전송 + MCP UI 가드 | +22 |
| `src/__tests__/components/AgentBuilderFormView.test.tsx` | 3 케이스 | +82 |

---

## 4. 테스트 결과

| 스위트 | 결과 |
|--------|------|
| `tests/application/agent_builder/` | 30 passed |
| `AgentBuilderFormView.test.tsx` | 7 passed |
| `tsc --noEmit` | 0 error |

**무관한 사전 실패**: `tests/api/test_agent_builder_router.py::TestRunAgent::*` 3건 — run-agent 엔드포인트의 `get_assemble_auth_context_use_case` DI 미초기화. 격리 실행에서도 동일하게 실패하는 기존 이슈로 이번 변경과 무관.

---

## 5. 배운 점 / 후속 과제

### 배운 점
- **API 계약 누락 패턴**: state는 정상이어도 ① 요청 매핑 ② 수신 필드 두 지점을 모두 봐야 함. "전송 안 됨" 증상은 useState가 아니라 페이로드 조립 단계에서 발생할 수 있다.
- `tool_ids=[]`(falsy) ↔ 프론트 `length>0 ? : undefined` 이중 정합으로 AI 폴백 안정화.

### 후속 과제 (의도된 범위 제외)
- **MCP 도구의 생성-시 실제 연결** (Plan §5-5): 현재 생성 플로우(`get_tool_meta`/`ToolSelector`)가 내부 도구 4종만 지원. MCP 워커 빌드 + 시스템 프롬프트 메타 처리를 별도 feature로 분리.
- 권장 검증: `/verify-architecture`, `/verify-logging`, `/verify-tdd`, `/api-contract-sync` 및 end-to-end 수동 QA 1회.

---

## 6. PDCA 산출물

| 단계 | 문서 |
|------|------|
| Plan | `docs/01-plan/features/fix-agent-builder-tool-selection.plan.md` |
| Check | `docs/03-analysis/fix-agent-builder-tool-selection.analysis.md` |
| Report | `docs/04-report/fix-agent-builder-tool-selection.report.md` (본 문서) |

> Design 단계는 소규모 버그 수정 특성상 생략(Plan이 구현 가이드 대체).
