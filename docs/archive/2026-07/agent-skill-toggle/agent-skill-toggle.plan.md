# agent-skill-toggle Plan Document

> **Feature**: agent-skill-toggle
> **Project**: sangplusbot (idt + idt_front)
> **Author**: 배상규
> **Date**: 2026-07-01
> **Status**: Plan
> **Type**: 풀스택 기능 개선 (Backend API 계약 + Frontend UI/UX)

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | Agent Builder에서 스킬 부착은 **에이전트 생성 후(edit 모드)에만** 가능하고(`AgentTestPanel.tsx:32` `enabled: isEdit`), UI도 드롭다운+"부착" 버튼 방식이라 등록 단계에서 스킬을 넣을 수 없다("스킬 클릭 못하게 막혀있음"). |
| **Solution** | 스킬을 **도구·서브에이전트와 동일한 등록-시점 선택 대상**으로 승격한다. `CreateAgentRequest`/`UpdateAgentRequest`에 `skill_ids`를 추가하고, UI는 스크린샷처럼 **온/오프 토글 리스트**(좌측 구성 섹션 + 우측 탭)로 전환하며, 토글은 `form` 로컬 상태만 바꾸고 **저장 버튼으로 일괄 반영**한다. |
| **Function/UX Effect** | 생성·수정 화면 모두에서 스킬 카드의 토글을 켜고 끄면 되고, 최대 3개 도달 시 나머지 토글이 비활성화되며 `n/3` 카운터가 표시된다. 저장 시 서버가 부착/해제 diff를 자동 동기화한다. |
| **Core Value** | "에이전트 만들 때 자연스럽게 스킬을 같이 고른다"는 일관된 멘탈 모델. 별도 후속 편집 없이 등록 한 번으로 스킬까지 구성 완료. |

---

## 1. 현황 (As-Is)

### 1-1. Backend (이미 구축된 자산)
| 영역 | 상태 | 근거 |
|------|------|------|
| Skill 부착/해제/조회 API | ✅ 존재 | `POST/DELETE/GET /api/v1/agents/{agent_id}/skills` (`agent_builder_router.py:620~683`) |
| 부착 검증 정책 (중복·최대 3개) | ✅ 존재 | `SkillAttachPolicy.MAX_ATTACHED=3` (`domain/agent_skill/policies.py:12`) |
| 스킬 접근권한 정책 (visibility) | ✅ 존재 | `SkillVisibilityPolicy.can_access` (`AttachSkillUseCase._ensure_skill_access`) |
| instruction → 프롬프트 주입 | ✅ 존재 | `SkillInjectionPolicy.merge` (실행 시 system_prompt 앞에 prepend) |

### 1-2. 핵심 제약 — 등록 시점에 스킬을 넣을 수 없음
- 부착 3종 API는 **모두 기존 `agent_id`를 요구**한다 → create 단계(에이전트 미존재)에서 호출 불가.
- `CreateAgentRequest`에는 `tool_ids`·`sub_agent_configs`는 있으나 **`skill_ids`가 없다**(`application/agent_builder/schemas.py:36`).
- `GetAgentResponse`에도 부착 스킬 정보가 없어(`schemas.py:83`) edit 폼을 프라임할 소스가 없다.

### 1-3. Frontend
| 영역 | 상태 | 근거 |
|------|------|------|
| 스킬 탭 활성 조건 | ⚠️ `enabled: isEdit` | `AgentTestPanel.tsx:32` — create 모드에서 비활성(막힘) |
| 스킬 패널 UI | ⚠️ 드롭다운+부착 버튼 | `AgentSkillPanel.tsx` — 토글 아님, edit 전용 |
| 부착/해제 방식 | ⚠️ 즉시 API 호출 | `useAttachSkill`/`useDetachSkill` mutate (staged 아님) |
| 폼 상태 | ❌ 스킬 필드 없음 | `AgentBuilderFormData` (`types/agentBuilder.ts:91`)에 `skills` 없음 |
| 도구/서브에이전트 등록-시점 선택 | ✅ 참고 패턴 | `form.tools` + `ToolPickerModal` + `handleToolToggle` (`AgentBuilderPage/index.tsx:188`) |

> **결론**: 백엔드 부착 로직·정책은 재사용하고, **(1) 계약에 `skill_ids` 추가 (2) create/update 시점 동기화 (3) 토글 UI 전환** 3가지만 신규로 만든다.

---

## 2. 목표 (To-Be) & 결정사항

사용자 확정 결정(2026-07-01):

| # | 결정 항목 | 선택 | 구현 함의 |
|---|-----------|------|-----------|
| D1 | 토글 UI 배치 | **좌측 섹션 + 우측 탭 둘 다** | 두 컴포넌트가 **동일한 `form.skills` 상태를 공유**(single source of truth) |
| D2 | 최대 부착 개수 | **3개 유지, 변경 용이하게** | 백엔드 `SkillAttachPolicy.MAX_ATTACHED` 단일 상수 + 프론트 `MAX_ATTACHED_SKILLS` 단일 상수, 값만 바꾸면 됨 |
| D3 | edit 모드 저장 시점 | **모두 저장 버튼으로 일괄** | 토글=로컬 상태만 변경, 저장 시 서버가 desired-set diff로 attach/detach 동기화 |

---

## 3. 설계 (Design 개요 — 상세는 design 단계에서 확정)

### 3-1. Backend

**(A) 계약 확장** — `application/agent_builder/schemas.py`
- `CreateAgentRequest`: `skill_ids: list[str] | None = None` 추가.
- `UpdateAgentRequest`: `skill_ids: list[str] | None = None` 추가.
  - 의미: `None` = 스킬 변경 안 함, `[]` = 전부 해제, `[...]` = **목표 상태(desired set)**. (서브에이전트 `sub_agent_configs` 관례와 동일)
- `GetAgentResponse`: `skill_ids: list[str] = []` 추가(부착 순서대로) → edit 폼 프라임용.

**(B) 부착 동기화 로직 추출/재사용** — 신규 `application/agent_skill/sync_agent_skills_use_case.py`
- `AttachSkillUseCase`에 흩어진 검증(스킬 접근권한 + 중복 + 최대개수)을 재사용해, **"agent_id + desired skill_ids" → 현재 링크와 diff → attach 누락분 / detach 초과분"** 을 수행하는 서비스로 캡슐화.
- `CreateAgentUseCase`: 에이전트 save 직후 `skill_ids`가 있으면 sync 호출(순서 = 리스트 순서 = sort_order).
- `UpdateAgentUseCase`: `request.skill_ids is not None`일 때 sync 호출.
- 정책 재사용: `SkillAttachPolicy.validate_attach`(개수/중복), `SkillVisibilityPolicy.can_access`(접근권한). **새 규칙 신설 없음**.
- DDD 준수: 두 도메인(agent_builder·skill_builder) 조합은 application 계층에서만(도메인 간 직접 import 금지 유지).

**(C) DI 배선** — `api/main.py`
- `CreateAgentUseCase`/`UpdateAgentUseCase`에 `agent_skill_repo`·`skill_repo`·`dept_repo` 주입(단일 세션 규칙 준수 — CLAUDE.md §6).

### 3-2. Frontend

**(A) 상태/계약**
- `AgentBuilderFormData`에 `skills: string[]` 추가, `DEFAULT_FORM.skills = []`.
- `CreateBuilderAgentRequest`/`UpdateBuilderAgentRequest`에 `skill_ids?: string[]`.
- `AgentDetail`(edit 프라임 소스)에 `skill_ids: string[]`.
- 신규 상수 `constants/agentSkill.ts` → `MAX_ATTACHED_SKILLS = 3` (백엔드와 동기화 주석).

**(B) 컨테이너 배선** — `AgentBuilderPage/index.tsx`
- `handleSkillToggle(skillId)`: 켜기(최대개수 미만일 때만) / 끄기 로컬 토글.
- edit 프라임: `editDetail.skill_ids` → `form.skills`.
- `handleSave`: create·update 요청 payload에 `skill_ids: form.skills`(빈 배열이면 create는 undefined, update는 `[]`로 명시 전송).

**(C) UI 컴포넌트**
- **우측 탭**(`AgentSkillPanel` 리팩터): 드롭다운+부착 → **토글 카드 리스트**(이름·설명·스위치). `useSkills`로 전체 후보 로드, `form.skills` 반영, `enabled`를 create·edit 모두 true로. 즉시 API 호출 제거(staged).
- **좌측 섹션**(신규 `SkillPickerModal` + `LeftConfigPanel` "스킬" `CollapsibleSection`): 도구함(`ToolPickerModal`) 패턴 복제 — 선택 요약 리스트 + "스킬" 버튼 → 모달 토글 리스트.
- 두 컴포넌트 모두 `form.skills` + `onSkillToggle` prop을 상위에서 주입받아 동기화.
- 최대개수 도달 시: 미선택 토글 `disabled`, `n/3` 카운터, 안내 문구.

### 3-3. API 계약 동기화 (CLAUDE.md §4-1 필수)
| Backend | Frontend |
|---------|----------|
| `CreateAgentRequest.skill_ids` | `CreateBuilderAgentRequest.skill_ids` |
| `UpdateAgentRequest.skill_ids` | `UpdateBuilderAgentRequest.skill_ids` |
| `GetAgentResponse.skill_ids` | `AgentDetail.skill_ids` |

---

## 4. 작업 범위 (파일 단위)

### Backend (idt/)
| 파일 | 변경 |
|------|------|
| `src/application/agent_builder/schemas.py` | Create/Update Request + GetAgentResponse에 `skill_ids` |
| `src/application/agent_skill/sync_agent_skills_use_case.py` | **신규** 동기화 서비스(diff attach/detach) |
| `src/application/agent_builder/create_agent_use_case.py` | save 직후 skill 동기화 호출 |
| `src/application/agent_builder/update_agent_use_case.py` | `skill_ids is not None` 시 동기화 호출 |
| `src/application/agent_builder/get_agent_use_case.py` | 부착 스킬 조회 → 응답에 `skill_ids` |
| `src/api/main.py` | Create/Update UseCase DI에 repo 주입 |
| `src/domain/agent_skill/policies.py` | (선택) `MAX_ATTACHED` 주석/노출만 — 값 변경 용이성 확인 |

### Frontend (idt_front/)
| 파일 | 변경 |
|------|------|
| `src/types/agentBuilder.ts` | form `skills`, req `skill_ids` |
| `src/types/agentStore.ts` | `AgentDetail.skill_ids` |
| `src/constants/agentSkill.ts` | **신규** `MAX_ATTACHED_SKILLS` |
| `src/pages/AgentBuilderPage/index.tsx` | `handleSkillToggle`, 프라임, save payload |
| `src/components/agent-builder/AgentSkillPanel.tsx` | 토글 리스트로 리팩터, staged |
| `src/components/agent-builder/AgentTestPanel.tsx` | 스킬 탭 create 모드도 활성 |
| `src/components/agent-builder/SkillPickerModal.tsx` | **신규** (ToolPickerModal 복제) |
| `src/components/agent-builder/LeftConfigPanel.tsx` | "스킬" 섹션 + 모달 배선 |
| `src/components/agent-builder/StudioLayout.tsx` | `onSkillToggle` prop 관통 |

---

## 5. TDD 계획 (테스트 먼저 — CLAUDE.md §4-4)

### Backend (pytest)
1. `CreateAgentUseCase`: `skill_ids` 부착됨 / 접근불가 스킬 거부 / 4개 요청 시 최대개수 초과 오류.
2. `UpdateAgentUseCase`: `skill_ids=None` 무변경 / `[]` 전체 해제 / 부분 diff(추가+제거 동시) / 순서 = sort_order.
3. `SyncAgentSkillsUseCase`: desired-set diff 단위 테스트(멱등 포함).
4. `GetAgentUseCase`: 응답 `skill_ids` 순서 검증.

### Frontend (Vitest + RTL + MSW)
1. 토글 켜기/끄기 → `form.skills` 반영, 저장 payload에 `skill_ids` 포함.
2. 최대 3개 도달 → 미선택 토글 `disabled` + 카운터.
3. create 모드에서 스킬 탭/섹션 활성 확인.
4. edit 프라임 → 기존 부착 스킬 토글 on 상태.
> 주의(메모리 참고): idt_front vitest는 Windows에서 `--pool=threads` 필요.

---

## 6. 리스크 / 영향 범위

| 리스크 | 대응 |
|--------|------|
| 기존 즉시 attach/detach API를 쓰던 곳이 있으면 회귀 | 3종 API는 **유지**(하위호환), 프론트 패널만 staged로 전환. 외부 호출자 없음 확인됨(`AgentSkillPanel`이 유일 사용처). |
| create 트랜잭션 중 부착 실패 시 부분 저장 | 에이전트 save와 skill sync의 실패 처리 정책을 design에서 확정(부착 실패=경고 vs 롤백). **Open Q1**. |
| edit에서 스킬만 바꿔도 프롬프트 재생성 여부 | 부착 instruction은 **실행 시** merge되므로 저장 시 프롬프트 불변 → 부작용 없음. |
| 최대개수 상수 2곳(프론트/백엔드) 불일치 | 백엔드가 진실원. 프론트 초과분은 서버가 409로 방어(정책 재사용). |

---

## 7. Open Questions (design 단계 전 확정 필요)

- **Q1.** create 시 스킬 부착이 일부 실패하면? (a) 에이전트는 저장하고 실패 스킬만 스킵+경고, (b) 전체 롤백. → 권장: (a) 부분 성공 + 응답에 skipped 표기.
- **Q2.** 우측 탭과 좌측 섹션이 완전 중복이면 우측 탭을 "요약 읽기 전용 + 좌측에서 편집"으로 둘지, 둘 다 편집 가능하게 둘지. → 권장: 둘 다 편집(동일 상태 공유라 비용 낮음).
- **Q3.** 스킬 후보 목록 scope: 현재 `useSkills({scope:'all'})`. 접근권한 없는 스킬도 목록에 보이면 저장 시 403 → 목록을 접근가능분으로 필터할지. → 권장: 백엔드 목록 API가 접근가능분만 반환하도록 확인/필터.

---

## 8. 다음 단계

```
/pdca design agent-skill-toggle
```
design에서 §3 설계 확정 + §7 Open Questions 해소 → `/pdca do`.
