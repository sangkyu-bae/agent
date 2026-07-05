# agent-subagent-management Design Document

> **Summary**: 서브에이전트 관리 모달을 신규 구현하고, 후보 노출/검증을 구독 기반 → 가시성 기반(`VisibilityPolicy.can_access`)으로 정렬하며, 수정(edit) 경로에 `sub_agent_configs`를 추가한다.
>
> **Project**: sangplusbot (idt + idt_front)
> **Version**: feature/mcp-server-registry
> **Author**: 배상규
> **Date**: 2026-06-30
> **Status**: Draft
> **Planning Doc**: [agent-subagent-management.plan.md](../../01-plan/features/agent-subagent-management.plan.md)

---

## 1. Overview

### 1.1 Design Goals

- "준비중" placeholder를 첨부 이미지(`docs/img/subagent.png`)의 2-pane 관리 모달로 교체
- 사용 가능 에이전트 = **본인 소유 + 전체공개 + 부서공개** (가시성 기반)
- 생성·수정 양쪽에서 서브에이전트 구성을 영속화
- 백엔드 신규 구현 최소화 — 기존 supervisor 런타임/모델/정책 재사용

### 1.2 Design Principles

- **재사용 우선**: `VisibilityPolicy.can_access`가 이미 "소유 OR 공개 OR (부서 AND 동일부서)" 규칙을 인코딩 → 후보 조회·검증 모두 이 정책에 위임 (구독 게이트 제거)
- **DRY**: create의 `_build_sub_agent_workers`를 공유 빌더로 추출하여 update에서 재사용
- **불변 보존**: 수정 시 도구(tool) 워커는 건드리지 않고 sub_agent 워커만 교체
- Thin DDD 레이어 의존성 준수 (라우터 무로직)

---

## 2. Architecture

### 2.1 Component Diagram

```
[SubAgentManagerModal]──useAvailableSubAgents──▶ GET /api/v1/agents/available-sub-agents
        │ (add/remove)                                   │
        ▼                                                ▼
  form.subAgents ──(map)──▶ sub_agent_configs    ListAvailableSubAgentsUseCase
        │                          │                  └─ VisibilityPolicy.can_access (소유+공개+부서)
        ▼                          ▼
  POST /agents (create)     PATCH /agents/{id} (update, 신규 sub_agent_configs)
        │                          │
        └────────┬─────────────────┘
                 ▼
        SubAgentWorkerBuilder (공유) → VisibilityPolicy.can_access 검증
                 ▼
        AgentDefinition.workers (tool + sub_agent) → builder_agent_tools 저장
```

### 2.2 Data Flow (수정 경로)

```
모달 추가/제거 → form.subAgents 갱신 → 저장 클릭
 → PATCH {sub_agent_configs} → UpdateAgentUseCase
 → SubAgentWorkerBuilder(가시성 검증, 순환/중첩/개수 검증)
 → AgentDefinition.replace_sub_agents() (tool 워커 보존)
 → repository.update (sub_agent 워커 row 동기화) → 200
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| ListAvailableSubAgentsUseCase | AgentDefinitionRepository, DepartmentRepository, VisibilityPolicy | 가시성 기반 후보 조회 |
| SubAgentWorkerBuilder (신규/추출) | AgentDefinitionRepository, VisibilityPolicy, NestingDepthPolicy, CircularReferencePolicy | create/update 공용 sub_agent 워커 빌드+검증 |
| UpdateAgentUseCase | SubAgentWorkerBuilder, AgentDefinition.replace_sub_agents | 수정 경로 sub_agent 반영 |
| SubAgentManagerModal | useAvailableSubAgents, useModels | 후보 표시/검색/필터 |

---

## 3. Data Model

### 3.1 변경 없음 (기존 재사용)

서브에이전트 관계는 기존 `builder_agent_tools`(`AgentToolModel`)의 `worker_type='sub_agent'`, `ref_agent_id`로 저장. **DB 스키마/마이그레이션 변경 없음.**

### 3.2 도메인 메서드 추가 — `AgentDefinition.replace_sub_agents`

```python
# idt/src/domain/agent_builder/schemas.py (AgentDefinition)
def replace_sub_agents(self, sub_workers: list[WorkerDefinition]) -> None:
    """tool 워커는 보존하고 sub_agent 워커만 교체. sort_order 재정렬."""
    tool_workers = [w for w in self.workers if w.worker_type == "tool"]
    for i, w in enumerate(sub_workers):
        w.sort_order = len(tool_workers) + i
    self.workers = tool_workers + sub_workers
```

---

## 4. API Specification

### 4.1 Endpoint List

| Method | Path | Description | 변경 |
|--------|------|-------------|------|
| GET | `/api/v1/agents/available-sub-agents` | 사용 가능 후보 목록 | 소스 정책 변경(DD-1) + 응답 필드 추가 |
| POST | `/api/v1/agents` | 생성 (이미 `sub_agent_configs` 지원) | 검증을 가시성 기반으로 변경 |
| PATCH | `/api/v1/agents/{agent_id}` | 수정 | `sub_agent_configs` 입력 추가(DD-2) |
| GET | `/api/v1/agents/{agent_id}` | 조회 (edit 로드용, 변경 없음) | `workers[]`에 sub_agent 포함됨 |

### 4.2 `GET /available-sub-agents` — 응답 (필드 추가, FR-08)

```python
# idt/src/application/agent_builder/schemas.py
class SubAgentCandidate(BaseModel):
    agent_id: str
    name: str
    description: str
    source_type: str        # "owned" | "public" | "department"  ← "subscribed" 대체
    tool_ids: list[str]
    has_sub_agents: bool = False
    llm_model_id: str | None = None   # 추가: 프론트가 provider:model_name 배지로 변환
    visibility: str | None = None     # 추가: 배지/필터 표시
```

> 모델 라벨은 프론트의 기존 `useModels` 목록으로 `llm_model_id → provider:model_name` 변환 (백엔드 JOIN 불필요).

### 4.3 `PATCH /agents/{agent_id}` — 요청 (DD-2)

```python
class UpdateAgentRequest(BaseModel):
    system_prompt: str | None = None
    name: str | None = None
    visibility: str | None = None
    department_id: str | None = None
    temperature: float | None = None
    sub_agent_configs: list[SubAgentConfigRequest] | None = None  # 추가
    # None  = 변경 안 함, []  = 모든 서브에이전트 제거
```

### 4.4 검증 정책 통일 (DD-1)

create/update 공용 `SubAgentWorkerBuilder`가 후보별로 다음을 호출:

```python
ctx = AccessCheckInput(
    agent_owner_id=sub_agent.user_id,
    agent_visibility=sub_agent.visibility,
    agent_department_id=sub_agent.department_id,
    viewer_user_id=parent_user_id,
    viewer_department_ids=parent_department_ids,
    viewer_role="user",
)
if not VisibilityPolicy.can_access(ctx):
    raise PermissionError(...)
```

추가 검증: `NestingDepthPolicy.validate_depth`, `CircularReferencePolicy.validate_no_cycle`(self 및 하위 그래프), `AgentBuilderPolicy.validate_worker_count`.

> `SubAgentAccessPolicy`(구독 기반)는 deprecated 처리 또는 내부적으로 `VisibilityPolicy.can_access`에 위임. 기존 호출부(create `_build_sub_agent_workers`)를 교체.

---

## 5. UI/UX Design

### 5.1 좌측 패널 섹션 (placeholder 교체)

```
┌ 서브에이전트 ──────────────[ 관리 ]┐
│ • 사내 문서 RAG 챗봇        [제거]  │   ← form.subAgents 있을 때
│ • 데이터 분석가             [제거]  │
└ (없으면) "서브에이전트가 없습니다" ┘
```

### 5.2 관리 모달 (`docs/img/subagent.png` 기준)

```
┌ 서브에이전트 관리                                    [×] ┐
│ 이 에이전트가 작업을 위임할 서브에이전트를 추가/제거합니다.│
│ ┌ 현재 서브에이전트 (N) ┐   ┌ 사용 가능한 에이전트 ──────┐│
│ │ [추가된 목록 / 빈상태] │   │ [🔍 에이전트 검색...]      ││
│ │   각 항목 [제거]       │   │ ┌ 카드 ──────────[추가]┐  ││
│ └───────────────────────┘   │ │ 이름 / 설명          │  ││
│                              │ │ provider:model 배지  │  ││
│                              │ └──────────────────────┘  ││
│                              │ ... (스크롤)               ││
│                              └────────────────────────────┘│
└───────────────────────────────────────────────────────────┘
```

- 우측 후보 필터(클라이언트): **현재 편집 중 agentId 제외**, **이미 추가된 ref_agent_id 제외**, 검색어(name/description) 매칭
- 최대 3개 도달 시 "추가" 버튼 disabled + 안내문("서브에이전트는 최대 3개")
- DRAFT 포함: 백엔드가 `status != 'deleted'` 전부 반환하므로 별도 처리 불필요

### 5.3 Component List

| Component | Location | Responsibility |
|-----------|----------|----------------|
| SubAgentManagerModal | `idt_front/src/components/agent-builder/SubAgentManagerModal.tsx` | 후보 조회·검색·필터·추가/제거 |
| LeftConfigPanel(수정) | `.../agent-builder/LeftConfigPanel.tsx` | 현재 서브에이전트 표시 + 모달 트리거 |
| useAvailableSubAgents | `idt_front/src/hooks/useAgentBuilder.ts` | TanStack Query (모달 open 시 enabled) |
| agentBuilderService.listAvailableSubAgents | `.../services/agentBuilderService.ts` | GET 호출 |

### 5.4 프론트 타입 (계약 동기화)

```typescript
// idt_front/src/types/agentBuilder.ts
export interface SubAgentCandidate {
  agent_id: string; name: string; description: string;
  source_type: 'owned' | 'public' | 'department';
  tool_ids: string[]; has_sub_agents: boolean;
  llm_model_id?: string; visibility?: string;
}
export interface SubAgentConfig { ref_agent_id: string; name: string; description: string; }

// AgentBuilderFormData 확장
subAgents: SubAgentConfig[];

// Create/Update Request 확장
sub_agent_configs?: { ref_agent_id: string; description: string }[];
```

`API_ENDPOINTS.AGENT_AVAILABLE_SUB_AGENTS = '/api/v1/agents/available-sub-agents'`

---

## 6. Error Handling

| Code | 상황 | 처리 |
|------|------|------|
| 400 | 최대 3개 초과 / 순환참조 / 중첩깊이 초과 | 백엔드 ValueError → 메시지 모달 상단 표시 (UI 사전 가드로 대부분 차단) |
| 403 | 접근 불가 에이전트를 sub_agent로 지정 (private-other) | PermissionError → 사용자 안내. UI는 애초에 후보에서 제외 |
| 404 | ref_agent_id 없음/삭제됨 | "서브 에이전트를 찾을 수 없습니다" |

---

## 7. Security Considerations

- [x] 가시성 검증을 `VisibilityPolicy.can_access`로 서버측 강제 (프론트 필터는 UX 보조일 뿐)
- [x] 수정 권한은 기존 `can_edit`(owner only) 유지
- [x] 순환참조/중첩깊이 서버측 검증 (클라이언트 우회 방지)
- [x] 입력 길이 제한 유지 (description ≤ 500)

---

## 8. Test Plan

### 8.1 Scope

| Type | Target | Tool |
|------|--------|------|
| Unit (BE) | ListAvailableSubAgents, SubAgentWorkerBuilder, Update use case, replace_sub_agents | pytest |
| Unit (FE) | service/hook, modal, payload mapping | Vitest + MSW |

### 8.2 Key Cases

**Backend**
- [ ] 후보 목록: 소유 + 공개(타인) + 부서(동일) 포함, private(타인)·deleted 제외
- [ ] create: 공개 에이전트(타인, 미구독)를 sub_agent로 지정 → 성공 (구독 게이트 제거 검증)
- [ ] update: `sub_agent_configs` 제공 시 sub_agent 워커 교체, tool 워커 보존
- [ ] update: `[]` → 전체 제거, `None` → 변경 없음
- [ ] 제약: 4개 지정 → 400, 자기참조/순환 → 400/검증 에러
- [ ] 접근 불가(private-other) 지정 → 403

**Frontend**
- [ ] useAvailableSubAgents 후보 로드 (MSW)
- [ ] 모달: 검색 필터, 현재 agentId·기존 선택 제외, 추가/제거 콜백
- [ ] 최대 3개 도달 시 추가 disabled
- [ ] create/update payload에 `sub_agent_configs` 포함, edit 로드 시 workers→subAgents 매핑
- [ ] LeftConfigPanel: 개수 표시 + 모달 오픈

> **테스트 환경 주의**: idt pytest는 Windows 이벤트 루프 teardown 산발 실패 → 신규 테스트 격리 실행으로 검증. idt_front vitest는 `--pool=threads` 사용.

---

## 9. Clean Architecture (레이어 배치)

| Component | Layer | Location |
|-----------|-------|----------|
| replace_sub_agents, VisibilityPolicy 사용 | Domain | `idt/src/domain/agent_builder/` |
| SubAgentWorkerBuilder, Update/List use case | Application | `idt/src/application/agent_builder/` |
| repository.update (worker 동기화) | Infrastructure | `idt/src/infrastructure/agent_builder/agent_definition_repository.py` |
| SubAgentManagerModal, LeftConfigPanel | Presentation(FE) | `idt_front/src/components/agent-builder/` |
| service / hook / types | Application·Domain(FE) | `idt_front/src/{services,hooks,types}/` |

> **⚠ 검증 포인트(구현 시 최우선 확인)**: 현재 `repository.update`가 `builder_agent_tools`(워커 row)를 동기화하는지 확인. 미동기화 시, sub_agent 워커 교체를 반영하도록 update에 worker 동기화 로직(기존 sub_agent row 삭제 후 신규 insert, tool row 보존)을 추가한다. 이 항목이 DD-2의 성패를 좌우한다.

---

## 10. Coding Convention Reference

- 함수 40줄/if 중첩 2단계 이내, 명시적 타입, logger 사용 (idt CLAUDE.md)
- 컴포넌트 PascalCase, 기존 모달 패턴(`ModelSettingsModal`/`UserRegisterModal`) 준수 — overlay `fixed inset-0 z-50 bg-black/50`, `role="dialog"`, ESC 닫기
- API 계약 동기화: 백엔드 스키마 변경 시 `idt_front/src/types/agentBuilder.ts` 동시 수정

---

## 11. Implementation Guide

### 11.1 Implementation Order (TDD)

**Backend (idt)**
1. [ ] (test→impl) `AgentDefinition.replace_sub_agents` 도메인 메서드
2. [ ] (test→impl) `SubAgentWorkerBuilder` 추출 + 가시성 기반 검증 (create `_build_sub_agent_workers` 교체)
3. [ ] (test→impl) `ListAvailableSubAgentsUseCase` 가시성 기반 재작성 + `SubAgentCandidate` 필드 추가
4. [ ] (test→impl) `UpdateAgentRequest.sub_agent_configs` + `UpdateAgentUseCase` 반영
5. [ ] (검증) `repository.update` 워커 동기화 — 필요 시 보강
6. [ ] 라우터 docstring/응답모델 정리

**Frontend (idt_front)**
7. [ ] 타입 확장 + `API_ENDPOINTS` 추가
8. [ ] (test→impl) service `listAvailableSubAgents` + hook `useAvailableSubAgents`
9. [ ] (test→impl) `SubAgentManagerModal`
10. [ ] `LeftConfigPanel` placeholder 교체 + 모달 연결
11. [ ] `AgentBuilderPage`: form.subAgents ↔ sub_agent_configs 매핑(create/update), edit 로드 매핑
12. [ ] 통합 확인: 생성·수정 후 재로딩 시 서브에이전트 유지

### 11.2 File Structure (영향)

```
idt/src/domain/agent_builder/schemas.py        (+replace_sub_agents)
idt/src/domain/agent_builder/policies.py        (SubAgentAccessPolicy→VisibilityPolicy 위임)
idt/src/application/agent_builder/
  ├ sub_agent_worker_builder.py                 (신규, create에서 추출)
  ├ list_available_sub_agents_use_case.py        (가시성 기반)
  ├ update_agent_use_case.py                     (+sub_agent_configs)
  ├ create_agent_use_case.py                     (빌더 사용)
  └ schemas.py                                   (UpdateAgentRequest, SubAgentCandidate)
idt/src/infrastructure/agent_builder/agent_definition_repository.py  (update 워커 동기화 확인/보강)

idt_front/src/components/agent-builder/SubAgentManagerModal.tsx  (신규)
idt_front/src/components/agent-builder/LeftConfigPanel.tsx
idt_front/src/{services/agentBuilderService.ts, hooks/useAgentBuilder.ts, types/agentBuilder.ts, constants/api.ts}
```

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-06-30 | Initial draft (코드 검증 기반, DD-1/DD-2 확정) | 배상규 |
