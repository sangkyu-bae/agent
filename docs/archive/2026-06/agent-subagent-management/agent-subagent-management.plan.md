# agent-subagent-management Planning Document

> **Summary**: /agent-builder 좌측 패널의 "서브에이전트(준비중)" placeholder를 실제 관리 모달로 교체하여, 본인 소유·전체공개·부서공개 에이전트를 서브에이전트로 추가/제거하고 저장한다.
>
> **Project**: sangplusbot (idt + idt_front)
> **Version**: feature/mcp-server-registry
> **Author**: 배상규
> **Date**: 2026-06-30
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 에이전트 빌더에 멀티-에이전트(supervisor) 백엔드는 이미 구현돼 있으나, 프론트의 서브에이전트 섹션이 "준비중" placeholder라 사용자가 서브에이전트를 구성할 방법이 없다. |
| **Solution** | placeholder를 2-pane 관리 모달로 교체하고, 사용 가능 에이전트 목록을 **본인 소유 + 전체공개 + 부서공개**(visibility 기반)로 제공하여 추가/제거한 결과를 create/update 페이로드(`sub_agent_configs`)로 저장한다. |
| **Function/UX Effect** | 사용자가 첨부 이미지처럼 모달에서 사용 가능 에이전트를 검색·추가하여 부모 에이전트가 작업을 위임할 서브에이전트를 직접 구성할 수 있다. |
| **Core Value** | 이미 존재하는 supervisor 런타임을 노출시키는 "마지막 1마일" UI로, 백엔드 재구현 없이 멀티-에이전트 조립 기능을 완성한다. |

---

## 1. Overview

### 1.1 Purpose

`/agent-builder` 스튜디오 좌측 패널의 **서브에이전트** 섹션은 현재 `PlaceholderSection`("서브에이전트가 없습니다", 준비중)으로 비활성 상태다. 이를 첨부 이미지(`docs/img/subagent.png`)처럼 **모달 기반 관리 UI**로 교체하여, 부모 에이전트가 작업을 위임할 서브에이전트를 추가/제거하고 영속화하는 것이 목표다.

### 1.2 Background

코드 검증 결과 **백엔드 멀티-에이전트 구성 기능은 대부분 이미 구현됨**을 확인했다(아래 §6.4). 따라서 본 작업은 백엔드를 새로 만드는 것이 아니라, ① 후보 목록의 노출 정책을 사용자 요구(공개/부서/소유)에 맞추고 ② 프론트 UI를 신규 구현하여 기존 백엔드와 연결하는 것이 핵심이다.

### 1.3 Related Documents

- 참조 이미지: `docs/img/subagent.png`
- 백엔드 라우터: `idt/src/api/routes/agent_builder_router.py`
- 도메인 정책: `idt/src/domain/agent_builder/policies.py`
- 프론트 좌측 패널: `idt_front/src/components/agent-builder/LeftConfigPanel.tsx`

---

## 2. Scope

### 2.1 In Scope

- [ ] (FE) `LeftConfigPanel` 서브에이전트 섹션의 `PlaceholderSection` → 실제 섹션(현재 서브에이전트 N개 + "관리" 버튼)으로 교체
- [ ] (FE) `SubAgentManagerModal` 신규 — 좌측 "현재 서브에이전트(N)" / 우측 "사용 가능한 에이전트"(검색 + 목록 + 추가) 2-pane
- [ ] (FE) 사용 가능 목록 조회 서비스/훅 + 타입 추가, form state(`subAgents`)와 create/update 페이로드(`sub_agent_configs`) 연결
- [ ] (FE) 목록 필터: **현재 편집 중인 에이전트 제외**, **이미 추가된 서브에이전트 제외**, **DRAFT 포함**
- [ ] (BE) `available-sub-agents` 후보 소스를 구독 기반 → **가시성 기반(소유 + 공개 + 부서)** 으로 변경 (DD-1)
- [ ] (BE) `SubAgentCandidate` 응답에 모델 정보(badge용)·가시성 필드 추가
- [ ] (BE) **수정(edit) 경로 지원**: `UpdateAgentRequest`에 `sub_agent_configs` 추가 + update use case 반영 (DD-2)
- [ ] (BE) `SubAgentAccessPolicy`를 가시성 기반 검증으로 확장 (DD-1 후속)
- [ ] (공통) API 계약 동기화 (`CLAUDE.md` §4-1)
- [ ] (공통) TDD: 백엔드 pytest / 프론트 Vitest+MSW

### 2.2 Out of Scope

- 서브에이전트 **런타임 위임 로직 변경** — supervisor(workflow_compiler/supervisor_state/nodes/hooks)는 이미 구현됨, 그대로 사용 (사용자 확인: "설정 저장 + 목록만")
- 좌측 "비주얼" 그래프 탭, 미들웨어 섹션 (별도 준비중)
- 구독(subscription) 모델 자체의 재설계 — 본 작업은 서브에이전트 후보 게이트에서 구독 의존을 제거할 뿐, 구독 기능(내 에이전트/핀)은 유지
- 도메인 제약(최대 3개, 중첩 깊이 2) 상수 변경

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | 서브에이전트 섹션이 현재 추가된 서브에이전트 개수/목록과 "서브에이전트 관리" 진입 버튼을 표시한다 | High | Pending |
| FR-02 | 관리 모달은 좌측 현재 서브에이전트(제거 가능), 우측 사용 가능 에이전트(검색·추가)의 2-pane 레이아웃이다 | High | Pending |
| FR-03 | 사용 가능 에이전트 = 본인 소유 + 전체공개(public) + 부서공개(department) 에이전트로 조회된다 | High | Pending |
| FR-04 | 사용 가능 목록에서 현재 편집 중인 에이전트와 이미 추가된 서브에이전트는 제외하고, DRAFT(미게시) 에이전트는 포함한다 | High | Pending |
| FR-05 | 추가/제거 결과가 form state에 반영되고, 생성/수정 저장 시 `sub_agent_configs`로 전송·영속화된다 | High | Pending |
| FR-06 | 수정(edit) 모드에서도 서브에이전트를 추가/제거할 수 있다 (UpdateAgentRequest 확장) | High | Pending |
| FR-07 | 최대 3개·순환참조·중첩 깊이 2 제약을 UI에서 사전 가드하고, 백엔드 검증 에러를 사용자에게 표면화한다 | Medium | Pending |
| FR-08 | 후보 카드에 모델 배지(예: `anthropic:claude-haiku-4-5`)와 설명, 가시성/출처를 표시한다 | Medium | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Architecture | Thin DDD 레이어 준수, 라우터에 비즈니스 로직 금지 | `/verify-architecture` |
| API 계약 | 백엔드 스키마 ↔ 프론트 타입 일치 | `/api-contract-sync` 체크리스트 |
| Accessibility | 모달 `role="dialog"`, ESC 닫기, 포커스 처리 (기존 모달 패턴 준수) | 수동 점검 |
| Test | 신규 모듈 TDD, 핵심 분기 커버 | pytest / vitest |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] FR-01~08 구현 완료
- [ ] 백엔드 pytest(가시성 필터/update sub_agent 경로/정책) 통과
- [ ] 프론트 Vitest(모달 동작/필터/페이로드) 통과
- [ ] 백엔드↔프론트 타입 동기화 완료
- [ ] 생성·수정 양 경로에서 서브에이전트 영속/재로딩 동작 확인

### 4.2 Quality Criteria

- [ ] 함수 40줄/if 중첩 2단계 이내 (idt 컨벤션)
- [ ] lint 무오류, 빌드 성공
- [ ] DDD 레이어 의존성 위반 없음

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 가시성 전환(DD-1)이 기존 구독 기반 동작/테스트와 충돌 | Medium | Medium | 구독 게이트 제거가 아닌 "가시성 OR 구독" 합집합으로 확장하는 대안 검토, 기존 테스트 회귀 확인 |
| 수정 경로에서 sub_agent 변경과 기존 워커(도구) immutable 정책 충돌 | High | Medium | DD-2 설계 단계에서 "도구는 불변, 서브에이전트만 교체" 동작 정의 후 update use case 구현 |
| 순환참조/중첩깊이 위반이 저장 시점에야 발견되어 UX 저하 | Medium | Medium | UI에서 현재 편집 에이전트/이미 추가 항목 제외로 1차 차단, 서버 에러 메시지 사용자 표면화 |
| `SubAgentCandidate` 필드 추가가 응답 계약을 깸 | Low | Low | 신규 필드는 optional/기본값으로 추가, 프론트 타입 동기화 |
| (회귀 주의) idt pytest Windows 이벤트 루프 teardown 산발 실패 | Low | Medium | 관련 테스트 격리 실행으로 검증 (기존 메모리 노트) |

---

## 6. Architecture Considerations

### 6.1 Project Level

Enterprise(백엔드 Thin DDD) + Dynamic(프론트 feature 모듈). 신규 레이어 도입 없음 — 기존 구조에 편승.

### 6.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 후보 노출 정책 (DD-1) | 구독 기반 유지 / **가시성 기반 전환** / 합집합 | **가시성 기반(소유+공개+부서)** *(설계 단계 확정)* | 사용자 요구가 명시적으로 공개·부서·소유. 기존 `VisibilityPolicy.can_access` 및 `scope=all`과 동일 의미 |
| 수정 시 서브에이전트 변경 (DD-2) | 불가(생성 시만) / **가능(Update 확장)** | **가능** *(권장)* | "관리" 모달은 편집 모드에서도 필요. 단 도구 불변 정책과의 상호작용은 설계에서 명확화 |
| 필터(제외 self/기존, draft 포함) | 백엔드 쿼리 파라미터 / **프론트 클라이언트 필터** | **프론트 필터** | 후보 수가 적고, 현재 편집 agentId·선택 목록은 프론트 컨텍스트. 백엔드 무변경 |
| 관계 저장 | **조인 테이블** (기존) | 기존 `builder_agent_tools(worker_type='sub_agent', ref_agent_id)` 재사용 | 사용자 확인: 조인 테이블. 이미 존재하므로 마이그레이션 불필요 |
| 모달 패턴 | 기존 `ModelSettingsModal`/`UserRegisterModal` 패턴 | 동일 패턴 | 일관성 |

### 6.3 영향 파일 (예상)

```
[Backend] idt/
  src/application/agent_builder/list_available_sub_agents_use_case.py  (가시성 기반 조회로 변경)
  src/application/agent_builder/schemas.py        (SubAgentCandidate 필드 추가, UpdateAgentRequest.sub_agent_configs)
  src/application/agent_builder/update_agent_use_case.py  (sub_agent 반영)
  src/domain/agent_builder/policies.py            (SubAgentAccessPolicy 가시성 확장)
  src/api/routes/agent_builder_router.py          (docstring/응답 모델 점검)
  tests/application/agent_builder/...             (TDD)

[Frontend] idt_front/
  src/components/agent-builder/LeftConfigPanel.tsx       (placeholder 교체)
  src/components/agent-builder/SubAgentManagerModal.tsx  (신규)
  src/types/agentBuilder.ts            (subAgents, sub_agent_configs, SubAgentCandidate)
  src/services/agentBuilderService.ts  (listAvailableSubAgents)
  src/hooks/useAgentBuilder.ts         (useAvailableSubAgents)
  src/constants/api.ts                 (AGENT_AVAILABLE_SUB_AGENTS)
  src/__tests__/... (Vitest + MSW)
```

### 6.4 검증된 기존 자산 (재사용 — 새로 만들지 말 것)

| 영역 | 상태 | 위치 |
|------|------|------|
| 서브에이전트 영속 모델 | ✅ 존재 | `AgentToolModel.worker_type`("tool"\|"sub_agent"), `ref_agent_id` |
| 생성 시 서브에이전트 입력 | ✅ 존재 | `CreateAgentRequest.sub_agent_configs: list[SubAgentConfigRequest]` |
| 조회 시 서브에이전트 노출 | ✅ 존재 | `GetAgentResponse.workers[].worker_type/ref_agent_id/ref_agent_name` |
| 후보 목록 엔드포인트 | ✅ 존재(정책 변경 필요) | `GET /api/v1/agents/available-sub-agents` |
| 도메인 정책 | ✅ 존재 | `AgentBuilderPolicy`(MAX_SUB_AGENTS=3), `CircularReferencePolicy`, `NestingDepthPolicy`(max 2), `SubAgentAccessPolicy` |
| supervisor 런타임 | ✅ 존재 | `workflow_compiler.py`, `supervisor_state.py`, `supervisor_nodes.py`, `supervisor_hooks.py` |
| 가시성 모델 | ✅ 존재 | `Visibility`(private/department/public), `VisibilityPolicy.can_access`, `list_agents` `scope=all` |

> **갭 요약**: ① 후보 소스가 구독 기반(요구는 가시성 기반) ② Update 경로에 sub_agent 입력 없음 ③ 후보 응답에 모델/가시성 정보 없음 ④ 프론트 UI 전부 미구현.

---

## 7. Convention Prerequisites

- [x] `CLAUDE.md`(루트/idt/idt_front) 컨벤션 존재 — Thin DDD, TDD, API 계약 동기화
- [x] 모달/폼 패턴 존재 (`ModelSettingsModal`, `UserRegisterModal`)
- 환경변수 추가 없음 (기존 인증/엔드포인트 재사용)

---

## 8. Next Steps

1. [ ] 설계 문서 작성 (`/pdca design agent-subagent-management`) — DD-1/DD-2 확정, Update 경로의 도구-불변 상호작용 정의, 모달 props/상태 설계
2. [ ] 백엔드 TDD: 가시성 필터 → 후보 응답 필드 → Update sub_agent 경로
3. [ ] 프론트 TDD: 서비스/훅 → 모달 → 패널 연결
4. [ ] API 계약 동기화 검증

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-06-30 | Initial draft (코드 검증 기반) | 배상규 |
