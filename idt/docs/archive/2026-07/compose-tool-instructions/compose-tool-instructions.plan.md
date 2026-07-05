# Plan: compose-tool-instructions

> Agent Composer 도구별 지침 생성 + 초안 적용 시 도구 미세팅 버그 수정
> 작성일: 2026-07-05 | 상태: Plan | 범위: 풀스택 (idt + idt_front)

---

## Executive Summary

| 관점 | 요약 |
|------|------|
| **Problem** | 자연어 에이전트 조합(compose) 시 도구는 선택해주지만 ① 생성되는 지침(system_prompt)에 도구 활용 방법이 부실하고, ② 도구별 사용 지침을 구조화된 데이터로 받을 수 없으며, ③ 초안 [적용하기] 시 도구가 폼에 세팅되지 않는 버그가 있다. |
| **Solution** | composer LLM 출력에 도구별 `instruction` 필드를 추가하고, system_prompt에 [도구 지침] 섹션을 필수화하며, compose 응답 `workers[]`에 instruction을 노출한다. 적용 시 도구 미세팅 버그(MCP 도구 ID 형식 불일치 추정)를 조사·수정한다. |
| **Function UX Effect** | 초안 카드에서 도구별 사용 지침을 확인할 수 있고, [적용하기] 한 번으로 도구 선택 + 도구 지침이 포함된 시스템 프롬프트가 폼에 완전히 반영된다. |
| **Core Value** | "자연어 한 줄 → 실행 가능한 에이전트 초안"의 완성도 향상 — 조합된 에이전트가 도구를 언제/어떻게 쓸지 지침 수준에서 보장된다. |

---

## 1. 배경 / 문제

### 1-1. 현재 동작 (코드 확인 완료)

- `AgentComposer`(`src/application/agent_composer/composer.py`)는 LLM 1회 호출로
  `workers`(도구 선택) + `system_prompt`(에이전트 지침)를 생성한다.
- `_WorkerOutput`은 `tool_id / worker_id / description / sort_order`만 갖는다 —
  **도구별 사용 지침(instruction) 필드가 없다.**
- `_SYSTEM_PROMPT` 규칙상 system_prompt에 [역할]/[동작 원칙] 섹션은 요구하지만,
  각 도구를 **언제·어떻게 사용할지**에 대한 구체 지침 섹션은 강제하지 않는다
  → 실사용에서 generic한 프롬프트가 생성됨 (사용자 확인).
- 프론트 `handleApplyDraft`(`AgentBuilderPage/index.tsx:286`)는
  `draft.tool_ids` → `form.tools`, `draft.system_prompt` → `form.systemPrompt`로
  반영하는 코드가 존재하지만, **실제 화면에서는 도구가 세팅되지 않음** (사용자 확인 — 버그).

### 1-2. 도구 미세팅 버그 추정 원인 (Design 단계에서 확정)

- 백엔드 `_map_mcp_workers`(FR-05)는 MCP 도구를 `mcp:{srv}:{tool}` → `mcp_{server_id}`로
  변환해 `tool_ids`에 담는다.
- 프론트 도구함(`useToolCatalog`)의 도구 ID 형식과 불일치하면 ToolPicker 체크/표시가
  안 될 수 있다 (`form.tools`에는 들어가도 카탈로그 매칭 실패).
- 내부 도구만 선택된 경우에도 재현되는지, `catalogTools`의 ID 형식이 무엇인지
  Design 단계에서 재현 + 확정한다.

## 2. 목표

1. compose 응답에서 **도구별 사용 지침**을 구조화된 필드로 받는다.
2. 생성되는 **system_prompt에 [도구 지침] 섹션을 필수 포함** — 도구별 사용 시점/방법/주의사항.
3. 초안 [적용하기] 시 **도구 선택이 폼에 정상 반영**되도록 버그 수정.
4. 프론트 초안 카드에서 도구별 지침을 확인 가능.

## 3. 요구사항

### 백엔드 (idt)

| ID | 요구사항 | 비고 |
|----|----------|------|
| FR-01 | `_WorkerOutput`에 `instruction` 필드 추가 — LLM이 도구별 사용 지침 생성 (사용 시점, 입력 형태, 주의사항 2~4문장) | composer.py structured output |
| FR-02 | `_SYSTEM_PROMPT` 규칙 강화 — system_prompt에 `[도구 지침]` 섹션 필수, 각 워커의 instruction 내용이 반영되도록 지시 | 내용 부실 개선 |
| FR-03 | compose 응답 `workers[]`에 `instruction` 노출 — `WorkerInfo` 공용 스키마에 `instruction: str = ""` 추가(하위호환) 또는 compose 전용 DTO 분리 (Design에서 결정) | api-contract-sync 대상 |
| FR-04 | 서버 보정 경로에서 instruction 보존 — `_sanitize_workers`/`_map_mcp_workers` 병합 시 instruction도 병합(`"; "` 연결) | 기존 description 병합과 동일 규칙 |
| FR-05 | (조사) compose 응답 `tool_ids`의 MCP 도구 ID 형식이 프론트 도구함/저장 API와 정합한지 검증, 불일치 시 백엔드 또는 프론트에서 정합화 | 도구 미세팅 버그의 백엔드 측 원인 후보 |

### 프론트엔드 (idt_front)

| ID | 요구사항 | 비고 |
|----|----------|------|
| FR-06 | 타입 동기화 — `types/agentComposer.ts` workers에 `instruction` 추가 | api-contract-sync |
| FR-07 | 초안 카드(`ComposeDraftCard`)에 도구별 지침 표시 (도구 목록 항목 확장 또는 접기 영역) | |
| FR-08 | **[적용하기] 도구 미세팅 버그 수정** — 재현 → 원인 확정(ID 형식 불일치/상태 갱신 누락 등) → 수정 + 회귀 테스트 | 최우선 |
| FR-09 | [적용하기] 시 도구 지침이 포함된 system_prompt가 지침 필드에 반영됨을 확인 (백엔드가 병합해서 내려주므로 추가 병합 로직 불필요 예상) | |

## 4. Non-Goals

- 도구별 지침의 **저장 스키마 신설 없음** — 지침은 system_prompt에 병합되어 기존
  `POST /agents` 경로로 저장된다. workers[].instruction은 표시/편집 보조용.
- 에이전트 실행(WorkflowCompiler) 경로 변경 없음.
- 기존 단발성 compose 동작(coverage/none 처리, MCP 폴백) 변경 없음.

## 5. 영향 범위

| 영역 | 파일 |
|------|------|
| BE composer | `src/application/agent_composer/composer.py` |
| BE use case | `src/application/agent_composer/compose_agent_use_case.py` |
| BE 스키마 | `src/application/agent_composer/schemas.py`, `src/application/agent_builder/schemas.py`(WorkerInfo 확장 시), `src/domain/agent_builder/schemas.py`(WorkerDefinition) |
| BE 테스트 | `tests/application/agent_composer/*`, `tests/api/test_agent_composer_router.py` |
| FE 타입/서비스 | `src/types/agentComposer.ts` |
| FE UI | `components/agent-builder/fix/ComposeDraftCard.tsx`, `pages/AgentBuilderPage/index.tsx`(handleApplyDraft) |
| FE 테스트 | `ComposeDraftCard.test.tsx`, `FixAgentPanel.test.tsx`, `AgentBuilderStudio.test.tsx` |

## 6. 구현 순서 (개요)

1. **FR-08/FR-05 버그 조사·수정** (도구 미세팅) — 재현이 먼저, 원인 확정 후 수정
2. BE: FR-01 → FR-02 → FR-04 → FR-03 (TDD: 테스트 먼저)
3. FE: FR-06 → FR-07 → FR-09 (`/api-contract-sync` 체크리스트 적용)
4. 통합 확인: compose → 카드 표시 → 적용 → 저장 왕복

## 7. 리스크 / 주의

- `WorkerInfo`는 agent_builder 공용 스키마 — instruction 추가 시 기존 응답들에
  빈 필드가 노출됨 (기본값 `""`, 하위호환이지만 계약 문서 갱신 필요).
- LLM 출력 필드 증가로 structured output 실패율/토큰 증가 가능 — instruction
  길이 상한(예: 300자) 및 미생성 시 빈 문자열 허용.
- system_prompt 길이 상한(`MAX_SYSTEM_PROMPT_LENGTH`) 내에서 [도구 지침] 섹션이
  절단될 수 있음 — clamp 시 notes 안내 유지.
- 도구 미세팅 버그의 원인이 확정 전이므로, Design 단계에서 재현 결과에 따라
  FR-05/FR-08의 수정 위치(백/프론트)가 달라질 수 있다.

## 8. 완료 기준 (Check)

- [ ] compose 응답 workers[]에 도구별 instruction 포함 (테스트)
- [ ] 생성된 system_prompt에 [도구 지침] 섹션 존재 (프롬프트 규칙 + 테스트)
- [ ] 초안 [적용하기] 시 도구가 폼 도구함에 체크되어 표시됨 (버그 수정 + 회귀 테스트)
- [ ] 초안 카드에 도구별 지침 표시
- [ ] 백/프론트 전 관련 테스트 통과, api-contract-sync 완료
