# skill-agent-integration Design Document

> **Summary**: 에이전트에 Skill을 부착하는 `agent_skill` 조인 도메인을 신설하고, 실행 시 부착 Skill의 `instruction`을 에이전트 `system_prompt`에 병합(주입)한다. **Phase A(주입)만** — `script_content` 실행은 Out of Scope(별도 `skill-script-runtime`).
>
> **Project**: sangplusbot — idt (FastAPI + LangGraph RAG/Agent)
> **Version**: V034 migration baseline
> **Author**: 배상규
> **Date**: 2026-06-27
> **Status**: Draft
> **Planning Doc**: [skill-agent-integration.plan.md](../../01-plan/features/skill-agent-integration.plan.md)
> **Related**: [skill-builder.design.md](./skill-builder.design.md)(완료, Match Rate 97%), `agent_builder`(구현됨)

---

## 1. Overview

### 1.1 Design Goals

1. `skill-builder`가 저장한 `skill_definition` 데이터를 **에이전트 실행에 결합**한다. Phase A는 **instruction 주입**(텍스트 병합, 실행 없음)에 한정.
2. 부착 모델을 **별도 `agent_skill` 조인 테이블**(Plan D-1 옵션 B)로 두어 "주입 단위 skill"과 "실행 단위 worker(`agent_tool`)"의 관심사를 분리한다.
3. 주입 지점은 기존 **`include_user_context` / `render_user_context_block` prepend 선례**와 동형으로 설계해 회귀 위험을 최소화한다.
4. 부착 0개면 **기존 동작 완전 불변**(DoD). `script`를 가진 Skill을 부착해도 instruction만 주입되고 script는 무시된다.

### 1.2 Design Principles

- **Thin DDD 의존성 역전**: `agent_skill` domain은 외부 무참조. Repository는 Interface로 역전.
- **기존 패턴 차용**: 신규 추상화 금지. `skill_builder`(CRUD/Repository/Policy) + `agent_builder`(visibility/RBAC/sub_agent 부착) 재사용.
- **주입은 순수 프롬프트 변환**: 병합 규칙(순서·구분자·개수·총길이)은 domain Policy로 못박고, application(UseCase)이 흐름만 제어. WorkflowCompiler는 **무수정**(§2.4 D3).
- **저장 전용 안전성 계승**: `script_content`는 이번 phase에도 실행하지 않는다 → 코드 실행 위험 제로.
- **API 계약 동기화**: 백엔드 부착 스키마 ↔ 프론트 타입 동시 작성.

### 1.3 핵심 설계 결정 (Decision Log)

| ID | 결정 | 근거 |
|----|------|------|
| **D1** | 부착 모델 = **별도 `agent_skill` 조인 테이블** (Plan D-1 옵션 B 확정) | Phase A의 skill은 "실행 워커"가 아니라 "프롬프트 주입" — `agent_tool` 스키마/제약을 건드리지 않음 |
| **D2** | **Phase A(instruction 주입)만**. `script_content` 실행 제외 (Plan D-2 확정) | 샌드박스 런타임은 `skill-script-runtime`로 분리 → 본 phase 실행 위험 제로 |
| **D3** | instruction 병합 지점 = **`RunAgentUseCase`(application)** 에서 `supervisor_prompt`에 병합 후 compile 호출. **WorkflowCompiler 무수정** | 785줄 컴파일러 + 다수 테스트에 회귀 주입 방지. 병합은 compile 상류의 순수 프롬프트 변환. compile 내부 `render_user_context_block` prepend가 그대로 동작해 사용자 컨텍스트가 최외곽 유지 |
| **D4** | 주입 대상 = **최상위 실행 에이전트만**. 서브에이전트(`sub_agent` 워커)의 부착 skill은 Phase A 미주입 | 서브에이전트 주입은 컴파일러에 repo 결합을 강제 → 회귀·복잡도 상승. Phase A 한계로 명시, 후속 검토 |
| **D5** | 부착 권한 = **에이전트 수정 권한자**(소유자/admin) **그리고** 대상 skill **접근 가능**(visibility) | 두 도메인 정책을 UseCase가 조합. domain 간 직접 import 회피(결합 방지) |
| **D6** | 부착 정책 = **최대 3개 + 중복 차단 + 총 주입 길이 가드** | 프롬프트 비대화 방지(Plan §5.1, §8 리스크) |
| **D7** | `agent_skill` 행은 **hard delete**(detach), skill 자체는 `skill_definition.status` soft-delete 유지 | 부착은 단순 연결 — 이력 추적 불필요. skill 삭제 시 주입에서 자동 제외(status='active' 필터) |

---

## 2. Architecture

### 2.1 Component Diagram

```
┌────────────────────────────────────────────────────────────────┐
│  부착/해제 (관리 흐름)                                            │
│  AgentBuilder UI ─▶ agent_builder_router(/{agent_id}/skills)     │
│        ─▶ Attach/Detach/List UseCase ─▶ SkillAttachPolicy        │
│        ─▶ AgentSkillRepository (agent_skill CRUD)                │
│        ─▶ SkillRepository (대상 skill 접근/존재 확인, 재사용)     │
├────────────────────────────────────────────────────────────────┤
│  실행 주입 (런타임 흐름)                                          │
│  RunAgentUseCase._prepare_graph                                  │
│    ─▶ AgentSkillRepository.list_attached_skills(agent_id)        │
│         (agent_skill ⨝ skill_definition, status='active')       │
│    ─▶ SkillInjectionPolicy.merge(system_prompt, skills)         │
│    ─▶ WorkflowDefinition(supervisor_prompt=merged) ─▶ compile() │
│         compile 내부: render_user_context_block + supervisor    │
└────────────────────────────────────────────────────────────────┘
```

### 2.2 Data Flow — 부착(Attach)

```
POST /api/v1/agents/{agent_id}/skills  { skill_id }
  → router: get_current_user → use_case.execute(agent_id, skill_id, viewer, request_id)
  → AttachSkillUseCase:
      1) agent = agent_repo.find_by_id        (없으면 404)
      2) VisibilityPolicy.can_edit(agent, viewer)   → 아니면 PermissionError(403)
      3) skill = skill_repo.find_by_id         (없거나 deleted → 404)
      4) SkillVisibilityPolicy.can_access(skill, viewer) → 아니면 PermissionError(403)
      5) links = agent_skill_repo.list_links(agent_id)
      6) SkillAttachPolicy.validate_attach(existing=links, new_skill_id)  (중복/최대개수)
      7) agent_skill_repo.attach(AgentSkillLink(agent_id, skill_id, sort_order=len(links)))
  → 201 AttachSkillResponse(attached link + skill summary)
```

### 2.3 Data Flow — 실행 시 주입(Inject)

```
RunAgentUseCase.stream → _prepare_graph
  workflow = agent.to_workflow_definition()         # supervisor_prompt = agent.system_prompt
  skills = await agent_skill_repo.list_attached_skills(agent.id, request_id)  # active만, sort_order ASC
  merged = SkillInjectionPolicy.merge(workflow.supervisor_prompt, skills)
  workflow = replace(workflow, supervisor_prompt=merged)   # 부착 0개면 merged == 원본
  compiler.compile(workflow, ...)                   # 내부에서 user_context_block prepend (불변)
```

> 최종 system prompt 구성 순서(최외곽→최내곽):
> `[현재 사용자 정보 블록]` → `[부착 Skill 1..N instruction]` → `[에이전트 system_prompt]`
> 사용자 컨텍스트는 compile 내부에서 prepend되므로 항상 최외곽 유지(보안 컨텍스트 우선).

### 2.4 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `AgentSkillRepository` | `MySQLBaseRepository`, `get_session` | agent_skill CRUD + skill_definition JOIN |
| `Attach/Detach/List UseCase` | `AgentSkillRepositoryInterface`, `AgentDefinitionRepositoryInterface`, `SkillRepositoryInterface`, `DepartmentRepositoryInterface`, `LoggerInterface` | 흐름 제어 + 권한 조합 |
| `RunAgentUseCase` | `AgentSkillRepositoryInterface`(신규, optional) | 실행 시 부착 skill 로드 + 주입 |
| `SkillInjectionPolicy` | (순수) | 병합 순서·구분자·개수·총길이 규칙 |
| `SkillAttachPolicy` | (순수) | 중복·최대개수 검증 |

---

## 3. Data Model

### 3.1 Entity 정의 (`domain/agent_skill/schemas.py`)

```python
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class AgentSkillLink:
    """에이전트 ↔ Skill 부착(주입) 연결 단위. 실행 워커가 아닌 프롬프트 주입 단위."""

    agent_id: str
    skill_id: str
    sort_order: int = 0
    created_at: datetime | None = None   # 신규 부착 시 UseCase에서 채움
```

> 주입에 필요한 본문(`instruction`)은 `SkillDefinition`(skill_builder 도메인)에서 가져온다. `AgentSkillLink`는 **연결 메타**만 보유(중복 데이터 금지).

### 3.2 Entity Relationships

```
[AgentDefinition] 1 ──── N [AgentSkillLink] N ──── 1 [SkillDefinition]
        (agent_id, ON DELETE CASCADE)        (skill_id, ON DELETE CASCADE)
```

- 에이전트 삭제(hard) 시 부착행 CASCADE 제거. (에이전트는 soft-delete 운영이나 FK는 안전망으로 CASCADE.)
- skill hard-delete 시 부착행 CASCADE 제거. **단 운영상 skill은 soft-delete**(status='deleted')이므로, 실제로는 주입 쿼리의 `status='active'` 필터가 1차 차단한다.
- 동일 (agent_id, skill_id) 쌍은 **UNIQUE**로 중복 부착 금지(정책 + DB 이중 방어).

### 3.3 Database Schema — `db/migration/V034__create_agent_skill.sql`

V033이 최신 → **V034** 확정.

```sql
-- skill-agent-integration Plan §4 / Design §3.3:
-- 에이전트 ↔ Skill 부착(instruction 주입) 조인 테이블. 실행 워커(agent_tool)와 분리.
CREATE TABLE agent_skill (
    id          VARCHAR(36)  PRIMARY KEY,
    agent_id    VARCHAR(36)  NOT NULL,
    skill_id    VARCHAR(36)  NOT NULL,
    sort_order  INT          NOT NULL DEFAULT 0 COMMENT '주입 순서(작을수록 먼저)',
    created_at  DATETIME     NOT NULL,
    CONSTRAINT fk_agent_skill_agent FOREIGN KEY (agent_id)
        REFERENCES agent_definition(id) ON DELETE CASCADE,
    CONSTRAINT fk_agent_skill_skill FOREIGN KEY (skill_id)
        REFERENCES skill_definition(id) ON DELETE CASCADE,
    CONSTRAINT uq_agent_skill UNIQUE (agent_id, skill_id),
    INDEX ix_agent_skill_agent (agent_id),
    INDEX ix_agent_skill_skill (skill_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

> ⚠️ `agent_definition.id` / `skill_definition.id` 모두 `VARCHAR(36)` PK임을 전제(기존 V007/V033 확인됨). FK 타입 일치 필수.

### 3.4 ORM Model — `infrastructure/persistence/models/agent_skill/models.py`

```python
from datetime import datetime
from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from src.infrastructure.persistence.models.base import Base


class AgentSkillModel(Base):
    __tablename__ = "agent_skill"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    skill_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
```

> `id`는 부착행 식별/멱등 detach를 위한 surrogate key. 도메인 `AgentSkillLink`에는 노출하지 않고 Repository 내부에서만 생성(uuid).

---

## 4. API Specification (`/api/v1/agents/{agent_id}/skills`)

agent_builder_router에 부착 엔드포인트를 추가한다(별도 라우터 신설 안 함 — 에이전트 하위 리소스).

### 4.1 Endpoint List

| Method | Path | Description | Auth | UseCase | Success |
|--------|------|-------------|------|---------|---------|
| GET | `/api/v1/agents/{agent_id}/skills` | 부착된 Skill 목록 | Required | ListAttachedSkillsUseCase | 200 |
| POST | `/api/v1/agents/{agent_id}/skills` | Skill 부착 | Required | AttachSkillUseCase | 201 |
| DELETE | `/api/v1/agents/{agent_id}/skills/{skill_id}` | 부착 해제 | Required | DetachSkillUseCase | 204 |

> 라우트 등록 순서: `/{agent_id}/skills`는 `/{agent_id}` 단건 라우트보다 구체적이므로 경로 충돌 없음(기존 `/{agent_id}/tools` 패턴과 동일 위치).

### 4.2 Application DTO — `application/agent_skill/schemas.py`

```python
from pydantic import BaseModel


class AttachSkillRequest(BaseModel):
    skill_id: str


class AttachedSkillItem(BaseModel):
    skill_id: str
    name: str
    description: str
    script_type: str            # none|python|shell — UI에서 "script 미실행" 안내용
    sort_order: int
    has_script: bool            # script_type != 'none'

class AttachSkillResponse(AttachedSkillItem):
    pass


class ListAttachedSkillsResponse(BaseModel):
    agent_id: str
    skills: list[AttachedSkillItem]
    total: int
    max_attachable: int         # SkillAttachPolicy.MAX_ATTACHED (UI 제한 표시)
```

### 4.3 Detailed Specification

#### `POST /api/v1/agents/{agent_id}/skills`

**Request:**
```json
{ "skill_id": "9f2c-..." }
```

**Response (201):** `AttachSkillResponse`
```json
{
  "skill_id": "9f2c-...",
  "name": "환율 계산기",
  "description": "통화 간 환율을 계산하는 스킬",
  "script_type": "python",
  "sort_order": 0,
  "has_script": true
}
```

**Error:**
- `404` 에이전트 없음 / skill 없음(또는 deleted)
- `403` 에이전트 수정 권한 없음(비소유·비admin) / skill 접근 불가(visibility)
- `409` 이미 부착됨(중복) / 최대 부착 개수(3) 초과
- `401` 미인증

#### `DELETE /api/v1/agents/{agent_id}/skills/{skill_id}`

**Response (204):** 본문 없음. **멱등** — 부착돼 있지 않아도 204(반복 호출 안전).
**Error:** `404` 에이전트 없음, `403` 수정 권한 없음.

#### `GET /api/v1/agents/{agent_id}/skills`

**Response (200):** `ListAttachedSkillsResponse` — `sort_order` ASC. deleted skill은 제외(주입과 동일 필터).
**Error:** `404` 에이전트 없음, `403` 접근 불가.

---

## 5. UI/UX Design (idt_front — 에이전트 빌더)

### 5.1 Screen Layout — 에이전트 빌더 내 "Skill 부착" 섹션

기존 워커/도구 부착 UI 옆(또는 하단)에 Skill 부착 패널을 추가한다.

```
┌──────────────────────────────────────────────────────────┐
│  부착된 Skill (1/3)                      [+ Skill 부착]    │
├──────────────────────────────────────────────────────────┤
│  환율 계산기   [python]  ⚠ script 미실행      [해제]       │
│  ...                                                       │
├──────────────────────────────────────────────────────────┤
│  ℹ 부착한 Skill의 지시문(instruction)만 에이전트 프롬프트에│
│    합쳐집니다. script는 현재 실행되지 않습니다.            │
└──────────────────────────────────────────────────────────┘
        ▼ [+ Skill 부착] 클릭 → 선택 모달
┌──────────────────────────────────────────────────────────┐
│  Skill 선택  [검색____]                                    │
│  ○ 환율 계산기   (python)                                  │
│  ○ 문서 요약     (none)                                    │
│            [취소]  [부착]                                  │
└──────────────────────────────────────────────────────────┘
```

- 부착 가능 목록은 `POST /api/v1/skills/list`(skill-builder, RBAC 접근분)에서 가져오고, 이미 부착된 항목은 비활성/제외.
- 최대 3개 도달 시 `[+ Skill 부착]` 비활성 + 안내.

### 5.2 User Flow

```
에이전트 빌더 열기 → 부착 Skill 목록 로드(GET .../skills)
  → [+ Skill 부착] → 접근 가능 skill 목록 → 선택 → 부착(POST) → 목록 갱신
  → [해제] → DELETE → 목록 갱신
```

### 5.3 Component / 파일 List (idt_front)

| Component | Location | Responsibility |
|-----------|----------|----------------|
| `AgentSkillPanel`(또는 빌더 페이지 내 인라인) | Presentation | 부착 목록 + 부착/해제 + script 미실행 안내 |
| `hooks/useAgentSkills.ts` | Application | TanStack Query 훅(list/attach/detach + 캐시 무효화) |
| `services/agentSkillService.ts` | Infrastructure | axios 클라이언트(snake↔camel 매핑) |
| `types/agentSkill.ts` | Domain | 부착 API 계약 타입 |
| `constants/api.ts` | — | `AGENT_SKILLS(agentId)` 엔드포인트 상수 추가(수정) |
| `lib/queryKeys.ts` | — | `agentSkills(agentId)` 키 추가(수정) |

### 5.4 프론트 타입 (`types/agentSkill.ts`) — 백엔드 계약 미러

```typescript
export interface AttachedSkill {
  skillId: string;
  name: string;
  description: string;
  scriptType: 'none' | 'python' | 'shell';
  sortOrder: number;
  hasScript: boolean;
}

export interface ListAttachedSkillsResponse {
  agentId: string;
  skills: AttachedSkill[];
  total: number;
  maxAttachable: number;
}

export interface AttachSkillPayload {
  skillId: string;
}
```

> snake_case ↔ camelCase 매핑은 `agentSkillService.ts`에서(기존 service 관례).

---

## 6. Error Handling

### 6.1 라우터 예외 매핑 (agent_builder_router 동일 패턴)

| UseCase 예외 | HTTP | 조건 |
|--------------|------|------|
| `ValueError` ("찾을 수 없") | 404 | 에이전트/skill 미존재·deleted |
| `ValueError` ("이미 부착"/"최대") | 409 | 중복 부착 / 최대 개수 초과 |
| `PermissionError` | 403 | 에이전트 수정권한 없음 / skill 접근불가 |
| 미인증 | 401 | `get_current_user` 의존성 |

### 6.2 router 처리 패턴 (Attach 예)

```python
@router.post("/{agent_id}/skills", response_model=AttachSkillResponse,
             status_code=201)
async def attach_skill(agent_id: str, body: AttachSkillRequest,
                       current_user: User = Depends(get_current_user),
                       use_case=Depends(get_attach_skill_use_case)):
    request_id = str(uuid.uuid4())
    try:
        return await use_case.execute(
            agent_id, body.skill_id, request_id,
            viewer_user_id=str(current_user.id),
            viewer_role=("admin" if current_user.is_admin else "user"),
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        msg = str(e)
        if "찾을 수 없" in msg:
            raise HTTPException(status_code=404, detail=msg)
        if ("이미 부착" in msg) or ("최대" in msg):
            raise HTTPException(status_code=409, detail=msg)
        raise HTTPException(status_code=422, detail=msg)
```

---

## 7. Domain Policy — `domain/agent_skill/policies.py`

도메인 격리 원칙상 `agent_skill` 전용 얇은 정책을 둔다(agent/skill 도메인 직접 의존은 UseCase에서만 조합).

```python
from dataclasses import dataclass


class SkillAttachPolicy:
    MAX_ATTACHED = 3   # Plan §5.1: 프롬프트 비대화 방지

    @classmethod
    def validate_attach(cls, existing_skill_ids: list[str], new_skill_id: str) -> None:
        if new_skill_id in existing_skill_ids:
            raise ValueError("이미 부착된 스킬입니다.")
        if len(existing_skill_ids) >= cls.MAX_ATTACHED:
            raise ValueError(f"스킬은 최대 {cls.MAX_ATTACHED}개까지 부착할 수 있습니다.")


@dataclass(frozen=True)
class InjectableSkill:
    """주입에 필요한 최소 정보(skill_builder.SkillDefinition에서 추출)."""
    name: str
    instruction: str
    sort_order: int


class SkillInjectionPolicy:
    """부착 skill instruction → supervisor_prompt 병합 규칙(순수)."""

    MAX_TOTAL_INJECTED = 40_000   # 주입 총 길이 상한(가드). 초과분 skill은 제외.
    BLOCK_HEADER = "[부착된 스킬: {name}]"
    SEPARATOR = "\n\n---\n\n"

    @classmethod
    def merge(cls, base_prompt: str, skills: list[InjectableSkill]) -> str:
        """skills를 sort_order ASC로 base_prompt 앞에 prepend. 부착 0개면 base 그대로."""
        if not skills:
            return base_prompt
        ordered = sorted(skills, key=lambda s: s.sort_order)
        blocks: list[str] = []
        used = 0
        for s in ordered:
            body = s.instruction.strip()
            if not body:
                continue
            block = f"{cls.BLOCK_HEADER.format(name=s.name)}\n{body}"
            if used + len(block) > cls.MAX_TOTAL_INJECTED:
                break          # 길이 가드 — 이후 skill 제외(로그는 UseCase에서)
            blocks.append(block)
            used += len(block)
        if not blocks:
            return base_prompt
        return cls.SEPARATOR.join(blocks) + cls.SEPARATOR + base_prompt
```

> **권한 정책 재사용**: 에이전트 수정권한은 `agent_builder.VisibilityPolicy`(소유자/admin), skill 접근권한은 `skill_builder.SkillVisibilityPolicy.can_access`를 **UseCase가 호출**한다(두 정책 모듈을 agent_skill 도메인이 직접 import하지 않음 — 결합 방지).

---

## 8. Test Plan (TDD — Red→Green→Refactor)

> CLAUDE.md §4-4. 테스트 없이 구현 코드 먼저 작성 금지. idt pytest **격리 실행**, 프론트 `--pool=threads`, `npm install --legacy-peer-deps`. 사전 실패(tests/api 28·infra 30 / 프론트 8)는 신규 회귀로 오인 금지.

### 8.1 백엔드 (pytest)

| 테스트 파일 | 대상 케이스 |
|------------|------------|
| `tests/domain/agent_skill/test_policies.py` | `SkillAttachPolicy`(중복·최대개수), `SkillInjectionPolicy.merge`(부착 0개=불변 / 순서 sort_order / 구분자·헤더 / 빈 instruction 스킵 / 총길이 가드 초과 제외) |
| `tests/application/agent_skill/test_attach_detach_use_cases.py` | Attach(정상/에이전트없음404/skill없음·deleted404/수정권한없음403/skill접근불가403/중복409/최대초과409), Detach(정상/멱등/권한), List(sort_order·deleted 제외) |
| `tests/application/agent_builder/test_run_agent_skill_injection.py` | `RunAgentUseCase._prepare_graph`에서 부착 instruction이 `supervisor_prompt`에 병합되는지 / **부착 0개면 기존과 동일** / user_context 블록이 여전히 최외곽 prepend / script-skill은 instruction만 주입 |
| `tests/infrastructure/agent_skill/test_repository.py` | attach/detach(멱등)/list_links/list_attached_skills(JOIN, active만, sort_order), UNIQUE 중복 방어 |

> §8.1 핵심 회귀 가드: **부착 0개 → 기존 컴파일 결과 바이트 동일**(DoD). 주입은 `replace(workflow, supervisor_prompt=merged)`로만 영향.

### 8.2 프론트 (Vitest + RTL + MSW, `--pool=threads`)

| 테스트 파일 | 대상 |
|------------|------|
| `src/__tests__/mocks/handlers.ts` | `/api/v1/agents/:id/skills` MSW 핸들러(list/attach/detach) |
| `src/hooks/useAgentSkills.test.ts` | 목록/부착/해제 훅 + 캐시 무효화 |
| `AgentSkillPanel`(또는 빌더 페이지) 테스트 | 부착 목록 렌더, 최대 3개 도달 시 부착 버튼 비활성, "script 미실행" 안내 표시, 해제 동작 |

---

## 9. Clean Architecture / 레이어 배치

### 9.1 This Feature's Layer Assignment (백엔드)

| Component | Layer | Location |
|-----------|-------|----------|
| `AgentSkillLink` | Domain | `domain/agent_skill/schemas.py` |
| `AgentSkillRepositoryInterface` | Domain | `domain/agent_skill/interfaces.py` |
| `SkillAttachPolicy`, `SkillInjectionPolicy`, `InjectableSkill` | Domain | `domain/agent_skill/policies.py` |
| Attach/Detach/List UseCase + DTO | Application | `application/agent_skill/*` |
| `RunAgentUseCase` 주입 추가 | Application | `application/agent_builder/run_agent_use_case.py`(수정) |
| `AgentSkillModel` | Infrastructure | `infrastructure/persistence/models/agent_skill/models.py` |
| `AgentSkillRepository` | Infrastructure | `infrastructure/agent_skill/agent_skill_repository.py` |
| 부착 엔드포인트 | Interface | `api/routes/agent_builder_router.py`(수정) |
| DI 팩토리 | Composition Root | `api/main.py`(수정) |

### 9.2 Repository Interface — `domain/agent_skill/interfaces.py`

```python
from abc import ABC, abstractmethod
from src.domain.agent_skill.schemas import AgentSkillLink
from src.domain.skill_builder.schemas import SkillDefinition


class AgentSkillRepositoryInterface(ABC):
    @abstractmethod
    async def attach(self, link: AgentSkillLink, request_id: str) -> AgentSkillLink: ...
    @abstractmethod
    async def detach(self, agent_id: str, skill_id: str, request_id: str) -> None: ...
    @abstractmethod
    async def list_links(self, agent_id: str, request_id: str) -> list[AgentSkillLink]: ...
    @abstractmethod
    async def list_attached_skills(
        self, agent_id: str, request_id: str,
    ) -> list[SkillDefinition]: ...   # agent_skill ⨝ skill_definition, status='active', sort_order ASC
```

> `list_attached_skills`가 `SkillDefinition`(skill_builder 도메인 엔티티)을 반환하는 것은 의존성 규칙 위반이 아니다 — infrastructure가 두 도메인 엔티티를 조합 매핑하는 것은 허용(domain→domain 순수 타입 참조). 주입에 필요한 `instruction`을 한 쿼리로 확보해 **한 UseCase 내 동일 세션** 규칙을 지킨다.

### 9.3 Repository 구현 핵심 (`infrastructure/agent_skill/agent_skill_repository.py`)

- `MySQLBaseRepository[AgentSkillModel]` + `AgentSkillRepositoryInterface` 다중 상속(skill_repository.py 동형).
- `attach`: `AgentSkillModel(id=uuid, ...)` → `_base_save`(flush). **commit/rollback 금지**(세션 미들웨어).
- `detach`: `delete(AgentSkillModel).where(agent_id, skill_id)` 실행(없어도 무에러 — 멱등).
- `list_attached_skills`: `select(SkillDefinitionModel).join(AgentSkillModel, ...).where(agent_id, SkillDefinitionModel.status=='active').order_by(AgentSkillModel.sort_order)` → `skill_builder._to_entity` 재사용.
- 세션은 생성자 DI(`get_session`) — 팩토리에서 직접 `get_session_factory()()` 금지.

### 9.4 RunAgentUseCase 주입 변경 (최소 수정)

```python
# 생성자: optional 의존성 추가 (None이면 주입 비활성 → 기존 동작 100% 유지)
def __init__(self, ..., agent_skill_repo: AgentSkillRepositoryInterface | None = None):
    self._agent_skill_repo = agent_skill_repo

# _prepare_graph 내 workflow 빌드 직후:
workflow = agent.to_workflow_definition()
if self._agent_skill_repo is not None:
    skills = await self._agent_skill_repo.list_attached_skills(agent.id, request_id)
    if skills:
        injectables = [
            InjectableSkill(name=s.name, instruction=s.instruction, sort_order=i)
            for i, s in enumerate(skills)   # 이미 sort_order ASC 정렬된 결과
        ]
        merged = SkillInjectionPolicy.merge(workflow.supervisor_prompt, injectables)
        workflow = replace(workflow, supervisor_prompt=merged)  # dataclasses.replace
        self._logger.info("skill injection applied", request_id=request_id,
                          agent_id=agent.id, attached=len(skills))
```

> `WorkflowDefinition`은 `@dataclass`(frozen 아님)이나 불변 치환을 위해 `dataclasses.replace` 사용. **WorkflowCompiler·compile 시그니처 무변경**(D3) → 컴파일러 테스트 회귀 없음.

### 9.5 DI Factory (`api/main.py`)

```python
def create_agent_skill_factories():
    app_logger = get_app_logger()

    def _make_repo(session):
        return AgentSkillRepository(session=session, logger=app_logger)

    def _make_skill_repo(session):
        return SkillRepository(session=session, logger=app_logger)

    def _make_agent_repo(session):
        return AgentDefinitionRepository(session=session, logger=app_logger)  # 기존 팩토리 재사용

    def attach_factory(session: AsyncSession = Depends(get_session)):
        return AttachSkillUseCase(
            agent_skill_repo=_make_repo(session),
            agent_repo=_make_agent_repo(session),
            skill_repo=_make_skill_repo(session),
            dept_repo=DepartmentRepository(session=session, logger=app_logger),
            logger=app_logger,
        )
    # detach_factory / list_factory 동형 (동일 session 공유)
    ...
    return attach_factory, detach_factory, list_factory
```

- `RunAgentUseCase` DI 팩토리에 `agent_skill_repo=_make_repo(session)` 한 줄 추가(동일 세션).
- `app.dependency_overrides`로 `get_attach_skill_use_case` 등 3종 + 기존 run use case 오버라이드 교체.

### 9.6 의존성 규칙 체크

```
interface ──→ application ──→ domain ←── infrastructure
규칙: agent_skill domain은 외부 무참조. agent_skill domain은 agent/skill 도메인을 import하지 않는다.
      두 도메인 정책 조합(권한)은 application(UseCase)에서만 수행.
      infrastructure는 domain(agent_skill + skill_builder 순수 엔티티)만 참조.
```

---

## 10. Coding Convention 적용

| 항목 | 적용 |
|------|------|
| 네이밍 | 클래스 PascalCase, 함수 snake_case, 상수 UPPER_SNAKE |
| 함수 길이 | 40줄 이내 (UseCase.execute 권한검증/부착을 helper로 분할) |
| if 중첩 | 2단계 이내 |
| 타입 | dataclass(domain) / pydantic(DTO) / typing 명시 |
| 로깅 | `LoggerInterface` + `request_id` 전파, `print()` 금지 |
| config | 하드코딩 금지(MAX_ATTACHED·MAX_TOTAL_INJECTED는 Policy 상수) |
| 프론트 | 컴포넌트 PascalCase.tsx, 훅 camelCase.ts, 엔드포인트 `constants/api.ts` |

---

## 11. Security Considerations

- [x] **스크립트 미실행(계승)**: `script_content`는 주입·실행 모두 안 함 — instruction 텍스트만 병합. eval/exec/subprocess 없음.
- [x] **프롬프트 인젝션 표면 고지**: 부착 skill의 instruction이 system prompt에 들어가므로, **접근 가능한 skill만 부착 가능**(visibility 검증) + **에이전트 수정 권한자만 부착 가능**(소유자/admin)으로 이중 차단. 타인이 임의 skill을 주입할 수 없음.
- [x] **사용자 컨텍스트 우선순위**: `render_user_context_block`(권한·신원)이 항상 **최외곽** prepend 유지(주입 skill보다 우선) → skill instruction이 권한 안내를 덮어쓰지 못함.
- [x] **프롬프트 비대화 방지(DoS-lite)**: 최대 3개 + 총 40,000자 주입 가드.
- [x] **RBAC**: 부착/해제/조회 모두 `get_current_user` 강제 + 권한 정책.
- [ ] **감사 로깅**: 부착/해제 및 실행 주입 시 `request_id`·`agent_id`·`attached count` 로깅(관측). 상세 감사 추적은 후속.

---

## 12. Implementation Guide

### 12.1 Implementation Order (Plan §10 반영)

1. [ ] `db/migration/V034__create_agent_skill.sql`
2. [ ] domain: `schemas.py`(AgentSkillLink) → `interfaces.py` → `policies.py`(Attach/Injection) + **테스트 먼저**
3. [ ] infrastructure: `AgentSkillModel` → `AgentSkillRepository` + 테스트
4. [ ] application: DTO → Attach/Detach/List UseCase + 테스트
5. [ ] **RunAgentUseCase 주입** 추가(optional repo) + 주입/회귀 테스트(부착 0개 불변)
6. [ ] interface: agent_builder_router 부착 엔드포인트 3종 + main.py DI(+ run use case에 repo 1줄)
7. [ ] 백엔드 통합 검증(격리 실행)
8. [ ] 프론트: `types/agentSkill.ts` + `constants/api.ts` + `lib/queryKeys.ts`(계약 동기화)
9. [ ] `services/agentSkillService.ts` + `hooks/useAgentSkills.ts` + MSW + 테스트
10. [ ] 에이전트 빌더 Skill 부착 패널 + script 미실행 안내 + 테스트
11. [ ] 통합 확인: 부착 → 실행 시 프롬프트 반영(주입), 해제 → 미반영

### 12.2 Definition of Done (Plan §9)

- [ ] V034 적용 가능
- [ ] 부착/해제/목록 API 동작(접근권한·최대개수·중복 정책 적용)
- [ ] 부착 instruction이 실행 시 `system_prompt`에 병합됨 / **부착 0개면 기존 동작 불변**
- [ ] script-skill 부착 시 instruction만 주입, script 미실행(명시)
- [ ] 빌더 UI 부착/해제 + "script 미실행" 안내
- [ ] 백엔드/프론트 신규 테스트 통과(격리/threads)
- [ ] API 계약 동기화(백엔드 ↔ 프론트 타입)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-06-27 | Initial draft — Plan 기반 agent_skill 4계층 + 주입(D3) 상세 설계 | 배상규 |
