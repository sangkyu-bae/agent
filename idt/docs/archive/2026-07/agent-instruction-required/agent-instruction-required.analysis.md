# agent-instruction-required Gap Analysis

> **Date**: 2026-07-06
> **Design**: [agent-instruction-required.design.md](../02-design/features/agent-instruction-required.design.md)
> **Phase**: Check (PDCA)
> **Analyzer**: gap-detector

---

## Overall Scores

| Category | Score | Status |
|----------|:-----:|:------:|
| Design Match | 100% | ✅ |
| Architecture Compliance | 100% | ✅ |
| Convention Compliance | 100% | ✅ |
| **Match Rate** | **99%** | ✅ |

10개 기능 요구사항(FR-01~FR-10) 전부 코드에서 구현 확인. 90% 임계 초과.

---

## FR별 검증 결과

| FR | 요구사항 | 상태 | 근거 |
|----|----------|:----:|------|
| FR-01 | create 빈 system_prompt → 422 | ✅ | `create_agent_use_case.py` Step 3 `validate_system_prompt(request.system_prompt or "")` + `policies.py` 빈 값 ValueError |
| FR-02 | PromptGenerator 자동생성 fallback 제거 | ✅ | use case Step 3 생성 분기·`_resolve_prompt_tool_meta`·PromptGenerator import 부재 |
| FR-03 | tool 미지정 시 0-worker 생성 성공 | ✅ | `else: WorkflowSkeleton(workers=[], flow_hint="")` + `validate_tool_count` 하한 제거 |
| FR-04 | update 빈 문자열 → 422, None 통과 | ✅ | `UpdateAgentPolicy.validate_update`: `if system_prompt is not None: validate_system_prompt(...)` |
| FR-05 | interview 3종 + 유스케이스/스토어/스키마 삭제 | ✅ | 파일 5개 부재, router/schemas/main.py `interview` grep 0건 |
| FR-06 | prompt_generator/tool_selector 삭제 + DI 정리 | ✅ | 파일 부재, main.py 관련 심볼 grep 0건 |
| FR-07 | 프론트 빈 지침 저장 차단 + 인라인 에러 | ✅ | `AgentBuilderPage` handleSave 차단 + `LeftConfigPanel` `role="alert"` |
| FR-08 | placeholder 자동생성 문구 제거 (통일) | ✅ | 단일 placeholder, `isEditMode` 분기·"자동 생성" grep 0건 |
| FR-09 | create 요청에 system_prompt 포함 (2→1 call) | ✅ | create 본문에 `system_prompt`, onSuccess는 스케줄만·update 미호출, 타입 필드 추가 |
| FR-10 | 도구 0개 에이전트 실행 정상 동작 | ✅ | `if worker_map:` 조건부 quality_gate 등록 + final_answer 무조건 등록. supervisor FINISH-answer 경로(설계 §1.3) |

---

## Gap 목록

### 🔴 Missing — 없음

### 🟡 Minor (실코드 무영향)

| 항목 | 위치 | 설명 | 조치 |
|------|------|------|------|
| 레거시 문자열 잔존 | `application/agent_composer/composer.py` 도크스트링 | 삭제 안내 주석에 `ToolSelector/PromptGenerator` 단어 잔존 (의도된 안내) | 유지 무방 |
| 폐기 설계 문서 | `src/claude/task/task-custom-agent-builder.md` | 구 설계 문서에 삭제 대상 클래스 언급 (Plan §1.3에서 "대체됨" 명시) | Optional 아카이빙 |

Plan DoD "grep 0건"은 위 2곳(주석/문서)으로 형식상 미달이나 **실행 코드 아님**.

### 🔵 Verification Gap (해소 완료)

| 항목 | 설계 근거 | 상태 |
|------|-----------|------|
| 0-worker `ainvoke` 실행 테스트 | 설계 §8.1 "compile(workers=[]) 성공 + ainvoke 시 supervisor FINISH-answer로 종료" | ✅ Check 단계에서 추가 (`test_workflow_compiler.py::test_zero_worker_graph_invokes_and_finishes`) |

Do 단계에서는 0-worker **컴파일/노드 구조** 테스트만 존재했고, 설계가 요구한 **런타임 ainvoke** 테스트가 누락되어 있었다. Check 단계에서 supervisor가 FINISH+answer로 직접 응답하는 실행 경로를 검증하는 통합 테스트를 추가하여 갭을 닫았다.

---

## 테스트 현황

| 영역 | 결과 |
|------|------|
| 백엔드 domain (policies/multi_agent_policies) | 통과 |
| 백엔드 application (create/mcp/prompt/doc_template/update) | 112 passed |
| 백엔드 workflow_compiler (0-worker compile + ainvoke) | 통과 |
| 백엔드 router | 신규 통과 + 5 사전 실패(ListTools 도구수·RunAgent auth DI, 무관) |
| 프론트 type-check | 클린 |
| 프론트 lint | 변경 파일 신규 에러 0건 |
| 프론트 agent-builder 컴포넌트 | 18파일 134 passed |

교차 실행 teardown 에러는 Windows 이벤트 루프 플레이키니스로, 격리 실행 시 전부 통과.

---

## 결론

**Match Rate 99% — 10/10 FR 구현 완료, 신규 회귀 0건.** 90% 임계 초과로 `/pdca report agent-instruction-required` 진행 가능.

권장 후속(선택): `task-custom-agent-builder.md` 아카이빙으로 grep 노이즈 제거.
