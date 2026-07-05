# skill-builder Design Document

> **Summary**: 재사용 가능한 Skill(지시문 + 실행 스크립트)을 저장·관리하는 `skill_definition` 도메인을 Thin DDD 4계층으로 신설한다 (백엔드 CRUD/Fork + 관리 UI). 스크립트는 **저장 전용**(실행 없음).
>
> **Project**: sangplusbot — idt (FastAPI + LangGraph RAG/Agent)
> **Version**: V033 migration baseline
> **Author**: 배상규
> **Date**: 2026-06-25
> **Status**: Draft
> **Planning Doc**: [skill-builder.plan.md](../../01-plan/features/skill-builder.plan.md)

---

## 1. Overview

### 1.1 Design Goals

1. `agent_builder` / `mcp_registry`와 **동일한 패턴**으로 `skill_definition` 도메인을 추가해 일관성·예측가능성을 확보한다.
2. Skill = **instruction(지시문) + script(실행 스크립트 텍스트)** 를 저장하는 엔티티로 정의하고, 수동 폼 기반 CRUD + Fork API와 관리 UI를 제공한다.
3. 에이전트와 동일한 **visibility(private/department/public) + RBAC + soft-delete + fork** 정책을 재사용한다.
4. 후속 `agent + skill` 연동을 대비해 `trigger` / `script_type` 컬럼을 미리 둔다 (이번 phase는 연동·실행 제외).

### 1.2 Design Principles

- **Thin DDD 의존성 역전**: domain은 외부(인프라/DB/LLM) 무참조. Repository는 Interface로 역전.
- **기존 패턴 차용**: 신규 추상화 도입 금지. mcp_registry(단순 CRUD) + agent_builder(visibility/fork/RBAC)를 조합.
- **저장 전용 안전성**: `script_content`는 텍스트로 저장만 하며 실행 런타임은 Out of Scope → 본 phase에 코드 실행 위험 없음.
- **API 계약 동기화**: 백엔드 스키마(`application/skill_builder/schemas.py`) ↔ 프론트 타입(`types/skill.ts`) 동시 작성.

### 1.3 핵심 설계 결정 (Decision Log)

| ID | 결정 | 근거 |
|----|------|------|
| **D1** | `mcp_registry`의 Fernet 암호화는 **도입하지 않음** | 비밀값 저장 요구 없음. `script_content`는 평문 TEXT |
| **D2** | soft-delete를 `status='active'\|'deleted'`로 (에이전트 방식) | mcp는 hard delete지만, fork/이력 추적을 위해 agent 방식 채택 |
| **D3** | `visibility`는 ENUM 컬럼 (agent_definition V007과 동일) | 기존 RBAC 인프라(부서 조회) 재사용 |
| **D4** | Repository는 `MySQLBaseRepository` 상속 + `_to_model/_to_entity` 매퍼 | mcp_server_repository.py와 동형 |
| **D5** | 라우터 메서드는 PUT(전체수정) 사용 (mcp 방식), agent의 PATCH 아님 | 단순 CRUD라 부분/전체 구분 불필요, mcp 패턴 일치 |
| **D6** | subscribe(구독) 제외, **fork만** 지원 | Plan Out of Scope. fork는 단순 전체 복제 |

---

## 2. Architecture

### 2.1 Layer 구조 (Thin DDD)

```
interfaces (api/routes/skill_builder_router.py)
    │  HTTPException 매핑만, 비즈니스 로직 없음
    ▼
application (application/skill_builder/*_use_case.py)
    │  흐름 제어 + Policy 호출 + 로깅(request_id)
    ▼
domain (domain/skill_builder/{schemas,interfaces,policies}.py)   ← 순수 규칙, 외부 무참조
    ▲
infrastructure (infrastructure/skill_builder/skill_repository.py + persistence ORM)
       Interface 구현, MySQLBaseRepository
```

### 2.2 Data Flow (Create 예시)

```
POST /api/v1/skills
  → router: get_current_user → body.user_id 주입 → use_case.execute(body, request_id)
  → CreateSkillUseCase: SkillBuilderPolicy.validate_* → VisibilityPolicy.clamp(미적용, agent와 달리 scope 없음)
  → SkillDefinition 엔티티 생성(uuid, now)
  → SkillRepository.save(entity) → _to_model → MySQLBaseRepository.save(flush) → _to_entity
  → to_response(entity) → 201 CreateSkillResponse
```

### 2.3 Dependencies (재사용 인프라)

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `SkillRepository` | `MySQLBaseRepository`, `get_session` | DB 영속화 (commit은 세션 미들웨어가 관리) |
| `ListSkillsUseCase(accessible)` | `DepartmentRepositoryInterface` | 뷰어 부서 ID 조회 → RBAC |
| `*UseCase` | `LoggerInterface` | 구조화 로깅 + request_id 전파 |
| router | `get_current_user` (`interfaces/dependencies/auth`) | 인증/소유자 식별 |

---

## 3. Data Model

### 3.1 Entity 정의 (`domain/skill_builder/schemas.py`)

`agent_builder/schemas.py`의 dataclass 스타일을 따른다.

```python
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class SkillVisibility(str, Enum):
    PRIVATE = "private"
    DEPARTMENT = "department"
    PUBLIC = "public"


class SkillScriptType(str, Enum):
    NONE = "none"
    PYTHON = "python"
    SHELL = "shell"


@dataclass
class SkillDefinition:
    id: str
    user_id: str
    name: str
    description: str
    instruction: str
    trigger: str | None
    script_type: SkillScriptType
    script_content: str | None
    status: str                       # 'active' | 'deleted'
    visibility: SkillVisibility
    department_id: str | None
    forked_from: str | None
    forked_at: datetime | None
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if self.visibility == SkillVisibility.DEPARTMENT and self.department_id is None:
            raise ValueError("department visibility requires department_id")

    def apply_update(
        self,
        name: str | None = None,
        description: str | None = None,
        instruction: str | None = None,
        trigger: str | None = None,
        script_type: SkillScriptType | None = None,
        script_content: str | None = None,
        visibility: SkillVisibility | None = None,
        department_id: str | None = None,
    ) -> None:
        """부분 수정. None이 아닌 필드만 갱신 후 불변식 재검증."""
        if name is not None:
            self.name = name
        if description is not None:
            self.description = description
        if instruction is not None:
            self.instruction = instruction
        if trigger is not None:
            self.trigger = trigger
        if script_type is not None:
            self.script_type = script_type
        if script_content is not None:
            self.script_content = script_content
        if visibility is not None:
            self.visibility = visibility
        if department_id is not None:
            self.department_id = department_id
        self.__post_init__()

    def soft_delete(self) -> None:
        self.status = "deleted"

    def fork_for(self, new_id: str, user_id: str, now: datetime) -> "SkillDefinition":
        """다른 사용자 소유의 새 skill로 전체 복제. fork 시 항상 private."""
        return SkillDefinition(
            id=new_id,
            user_id=user_id,
            name=self.name,
            description=self.description,
            instruction=self.instruction,
            trigger=self.trigger,
            script_type=self.script_type,
            script_content=self.script_content,
            status="active",
            visibility=SkillVisibility.PRIVATE,
            department_id=None,
            forked_from=self.id,
            forked_at=now,
            created_at=now,
            updated_at=now,
        )
```

### 3.2 Entity Relationships

```
[User] 1 ──── N [SkillDefinition]         (user_id, 소유)
[Department] 1 ── N [SkillDefinition]     (department_id, NULL 허용, ON DELETE SET NULL)
[SkillDefinition] ── forked_from(self FK 아님, 단순 id 추적) ──> [SkillDefinition]
```

> agent_definition과 동일하게 `forked_from`은 FK 제약 없이 원본 id만 보관(원본 삭제와 무관하게 이력 유지).

### 3.3 Database Schema — `db/migration/V033__create_skill_definition.sql`

V032가 최신 → **V033** 확정. agent_definition의 sharing 컬럼(V007) 구조를 차용한다.

```sql
-- skill-builder Plan §5.1 / Design §3.3: 재사용 Skill(지시문+스크립트) 저장 테이블.
-- agent_definition의 소유/visibility/fork 구조 차용. 비밀값 없음(평문 TEXT).
CREATE TABLE skill_definition (
    id             VARCHAR(36)  PRIMARY KEY,
    user_id        VARCHAR(100) NOT NULL,
    name           VARCHAR(255) NOT NULL,
    description    TEXT         NOT NULL,
    trigger_text   TEXT         NULL COMMENT '사용 시점 설명(후속 에이전트 매칭 대비)',
    instruction    TEXT         NOT NULL COMMENT '지시문 본문(SKILL.md 본문)',
    script_type    VARCHAR(20)  NOT NULL DEFAULT 'none' COMMENT 'none|python|shell',
    script_content TEXT         NULL COMMENT '실행 스크립트 원문(저장 전용, 실행 안 함)',
    status         VARCHAR(20)  NOT NULL DEFAULT 'active' COMMENT 'active|deleted (soft-delete)',
    visibility     ENUM('private','department','public') NOT NULL DEFAULT 'private',
    department_id  VARCHAR(36)  NULL,
    forked_from    VARCHAR(36)  NULL COMMENT 'Fork 원본 skill id',
    forked_at      DATETIME     NULL,
    created_at     DATETIME     NOT NULL,
    updated_at     DATETIME     NOT NULL,
    CONSTRAINT fk_skill_dept FOREIGN KEY (department_id) REFERENCES departments(id) ON DELETE SET NULL,
    INDEX ix_skill_user        (user_id),
    INDEX ix_skill_visibility  (visibility),
    INDEX ix_skill_dept_vis    (department_id, visibility),
    INDEX ix_skill_status      (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

> ⚠️ **`trigger`는 MySQL 예약어** → 컬럼명을 `trigger_text`로 사용. ORM/엔티티는 `trigger`로 노출하고 모델 매핑에서만 `trigger_text`로 연결한다(아래 §9.1).

### 3.4 ORM Model — `infrastructure/persistence/models/skill_builder/models.py`

```python
from datetime import datetime
from sqlalchemy import DateTime, Enum as SAEnum, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from src.infrastructure.persistence.models.base import Base


class SkillDefinitionModel(Base):
    __tablename__ = "skill_definition"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # 'trigger'는 예약어 → DB 컬럼은 trigger_text, 파이썬 속성은 trigger
    trigger: Mapped[str | None] = mapped_column("trigger_text", Text, nullable=True)
    instruction: Mapped[str] = mapped_column(Text, nullable=False)
    script_type: Mapped[str] = mapped_column(String(20), nullable=False, default="none")
    script_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    visibility: Mapped[str] = mapped_column(
        SAEnum("private", "department", "public", name="skill_visibility"),
        nullable=False, default="private", index=True,
    )
    department_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    forked_from: Mapped[str | None] = mapped_column(String(36), nullable=True)
    forked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
```

---

## 4. API Specification (`/api/v1/skills`)

### 4.1 Endpoint List

| Method | Path | Description | Auth | UseCase | Success |
|--------|------|-------------|------|---------|---------|
| POST | `/api/v1/skills` | Skill 생성 | Required | CreateSkillUseCase | 201 |
| GET | `/api/v1/skills/my` | 내 Skill 목록 | Required | ListSkillsUseCase.execute_my | 200 |
| POST | `/api/v1/skills/list` | 접근 가능 Skill 목록(RBAC) | Required | ListSkillsUseCase.execute_accessible | 200 |
| GET | `/api/v1/skills/{skill_id}` | 단건 조회 | Required | GetSkillUseCase | 200 |
| PUT | `/api/v1/skills/{skill_id}` | 수정 | Required | UpdateSkillUseCase | 200 |
| DELETE | `/api/v1/skills/{skill_id}` | soft-delete | Required | DeleteSkillUseCase | 204 |
| POST | `/api/v1/skills/{skill_id}/fork` | Fork(전체 복제) | Required | ForkSkillUseCase | 201 |

> 라우트 등록 순서 주의: `/my`, `/list`는 `/{skill_id}` **앞**에 선언해 path 충돌을 방지(agent_builder_router의 `/my`, `/tools` 선행 패턴 동일).

### 4.2 Application DTO — `application/skill_builder/schemas.py`

```python
from pydantic import BaseModel, Field


class CreateSkillRequest(BaseModel):
    user_id: str = ""                       # router에서 current_user.id 주입
    name: str = Field(..., max_length=255)
    description: str
    instruction: str
    trigger: str | None = None
    script_type: str = "none"               # none|python|shell
    script_content: str | None = None
    visibility: str = "private"             # private|department|public
    department_id: str | None = None


class UpdateSkillRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    instruction: str | None = None
    trigger: str | None = None
    script_type: str | None = None
    script_content: str | None = None
    visibility: str | None = None
    department_id: str | None = None


class ListSkillsRequest(BaseModel):
    scope: str = "all"                      # mine|department|public|all
    search: str | None = None
    page: int = 1
    size: int = 20


class ForkSkillRequest(BaseModel):
    name: str | None = None                 # 미지정 시 원본 이름 복제


class SkillResponse(BaseModel):
    id: str
    user_id: str
    name: str
    description: str
    instruction: str
    trigger: str | None
    script_type: str
    script_content: str | None
    status: str
    visibility: str
    department_id: str | None
    forked_from: str | None
    forked_at: str | None
    created_at: str
    updated_at: str


class SkillSummary(BaseModel):
    id: str
    name: str
    description: str
    script_type: str
    visibility: str
    owner_user_id: str
    forked_from: str | None
    can_edit: bool
    can_delete: bool
    created_at: str


class ListSkillsResponse(BaseModel):
    skills: list[SkillSummary]
    total: int
    page: int
    size: int


# alias로 명세 일관성 유지
CreateSkillResponse = SkillResponse
GetSkillResponse = SkillResponse
UpdateSkillResponse = SkillResponse
ForkSkillResponse = SkillResponse


def to_response(s) -> SkillResponse: ...    # 엔티티 → SkillResponse 매핑 (datetime → isoformat)
```

### 4.3 Detailed Specification

#### `POST /api/v1/skills`

**Request:**
```json
{
  "name": "환율 계산기",
  "description": "통화 간 환율을 계산하는 스킬",
  "instruction": "사용자가 환율 변환을 요청하면 다음 절차를 따른다 ...",
  "trigger": "환율, 통화 변환 요청 시",
  "script_type": "python",
  "script_content": "def convert(...): ...",
  "visibility": "private",
  "department_id": null
}
```

**Response (201):** `SkillResponse` (전체 필드 + `forked_from: null`)

**Error:**
- `422` 입력 검증 실패(빈 name/instruction, 잘못된 script_type/visibility, department visibility인데 department_id 없음)
- `401` 미인증

#### `POST /api/v1/skills/list` (RBAC)

**Request:** `ListSkillsRequest` (`scope`: mine/department/public/all)
**Response (200):** `ListSkillsResponse` — VisibilityPolicy로 접근 가능한 것만, `can_edit/can_delete` 계산 포함.

#### `POST /api/v1/skills/{skill_id}/fork`

**Response (201):** 새 소유자(`user_id`=호출자), `visibility=private`, `forked_from`=원본 id.
**Error:** `400` 자신의 skill / 삭제된 skill, `403` 접근 불가, `404` 원본 없음.

---

## 5. UI/UX Design (idt_front 관리 페이지)

### 5.1 Screen Layout — `pages/AdminSkillsPage`

```
┌──────────────────────────────────────────────┐
│  Skill 관리                  [+ 새 Skill 만들기] │
├──────────────────────────────────────────────┤
│  [검색____]  [scope: all▼]                      │
├──────────────────────────────────────────────┤
│  이름        | 타입   | 공개범위 | 작업          │
│  환율 계산기 | python | private | 수정 삭제 Fork │
│  ...                                           │
└──────────────────────────────────────────────┘
        ▼ (생성/수정 클릭 시 모달)
┌──────────────────────────────────────────────┐
│  SkillFormModal                                │
│  이름 [_______]                                 │
│  설명 [_______]                                 │
│  트리거 [_______]                               │
│  지시문(instruction) [텍스트area__________]      │
│  스크립트 타입 [none|python|shell ▼]             │
│  스크립트(script_content) [코드area_________]    │
│  공개범위 [private|department|public ▼]          │
│  (department 선택 시) 부서 [_____▼]              │
│            [취소]  [저장]                        │
└──────────────────────────────────────────────┘
```

> UI 안내문: "스크립트는 **저장만** 되며 현재 실행되지 않습니다." (Plan §10 리스크 대응)

### 5.2 User Flow

```
Admin 메뉴 → "Skill 관리" → 목록 조회(/list) → [새 Skill] 모달 → 저장(POST) → 목록 갱신
                                          └→ [수정] 모달 → PUT → 갱신
                                          └→ [삭제] 확인 → DELETE → 갱신
                                          └→ [Fork] → POST fork → 내 목록에 복제본
```

### 5.3 Component / 파일 List

> **구현 반영(2026-06-25)**: 목록 테이블·폼 모달을 `AdminMcpServersPage` 관례에 맞춰 **`AdminSkillsPage/index.tsx` 단일 파일에 인라인**으로 구현했다(`SkillFormModal`은 같은 파일 내부 컴포넌트). 별도 `SkillListTable.tsx`/`SkillFormModal.tsx` 분리는 도입하지 않는다 — mcp 페이지와 동일한 단일 파일 패턴으로 일관성 유지.

| Component | Location | Responsibility |
|-----------|----------|----------------|
| `AdminSkillsPage/index.tsx` | Presentation | 목록 테이블 + 검색 + 인라인 `SkillFormModal`(생성/수정 폼) + 삭제/Fork |
| `hooks/useSkills.ts` | Application | TanStack Query 훅(list/detail/create/update/delete/fork) |
| `services/skillService.ts` | Infrastructure | axios API 클라이언트 |
| `types/skill.ts` | Domain | API 계약 타입 |
| `constants/api.ts` | — | `SKILLS` 엔드포인트 상수(수정) |
| `constants/adminNav.ts` | — | "Skill 관리" 메뉴 추가(수정) |

### 5.4 프론트 타입 (`types/skill.ts`) — 백엔드 계약 미러

```typescript
export type SkillVisibility = 'private' | 'department' | 'public';
export type SkillScriptType = 'none' | 'python' | 'shell';

export interface Skill {
  id: string;
  userId: string;
  name: string;
  description: string;
  instruction: string;
  trigger: string | null;
  scriptType: SkillScriptType;
  scriptContent: string | null;
  status: string;
  visibility: SkillVisibility;
  departmentId: string | null;
  forkedFrom: string | null;
  forkedAt: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface SkillSummary {
  id: string;
  name: string;
  description: string;
  scriptType: SkillScriptType;
  visibility: SkillVisibility;
  ownerUserId: string;
  forkedFrom: string | null;
  canEdit: boolean;
  canDelete: boolean;
  createdAt: string;
}

export interface CreateSkillPayload {
  name: string;
  description: string;
  instruction: string;
  trigger?: string | null;
  scriptType: SkillScriptType;
  scriptContent?: string | null;
  visibility: SkillVisibility;
  departmentId?: string | null;
}
export type UpdateSkillPayload = Partial<CreateSkillPayload>;
export interface ListSkillsResponse {
  skills: SkillSummary[];
  total: number;
  page: number;
  size: number;
}
```

> 백엔드 snake_case ↔ 프론트 camelCase는 서비스 계층(`skillService.ts`)에서 매핑(기존 mcpServerService.ts 관례 따름).

---

## 6. Error Handling

### 6.1 라우터 예외 매핑 (mcp/agent 라우터 동일)

| UseCase 예외 | HTTP | 조건 |
|--------------|------|------|
| `ValueError` (검증 실패) | 422 | name/instruction 빈값, 잘못된 enum, department_id 누락 |
| `ValueError` ("찾을 수 없") | 404 | 대상 skill 미존재 |
| `ValueError` ("자신의"/"삭제된") | 400 | fork 자기소유/삭제본 |
| `PermissionError` | 403 | 소유자/admin 아님(수정·삭제·접근) |
| 미인증 | 401 | `get_current_user` 의존성 |

### 6.2 router 처리 패턴 (Update 예)

```python
@router.put("/{skill_id}", response_model=UpdateSkillResponse)
async def update_skill(skill_id, body, current_user=Depends(get_current_user),
                       use_case=Depends(get_update_skill_use_case)):
    request_id = str(uuid.uuid4())
    try:
        return await use_case.execute(skill_id, body, request_id,
                                      viewer_user_id=str(current_user.id))
    except PermissionError:
        raise HTTPException(status_code=403, detail="수정 권한 없음")
    except ValueError as e:
        msg = str(e)
        raise HTTPException(status_code=404 if "찾을 수 없" in msg else 422, detail=msg)
```

---

## 7. Domain Policy — `domain/skill_builder/policies.py`

agent_builder의 `VisibilityPolicy` / `AccessCheckInput` / `ForkPolicy`를 **재사용 가능하면 import**하되, 도메인 격리 원칙상 skill 전용 얇은 정책 모듈을 둔다(agent 모듈 직접 의존 회피 — 두 도메인 간 결합 방지).

```python
class SkillBuilderPolicy:
    MAX_NAME_LENGTH = 255
    MAX_DESCRIPTION_LENGTH = 2000
    MAX_INSTRUCTION_LENGTH = 20000
    MAX_SCRIPT_LENGTH = 50000
    ALLOWED_SCRIPT_TYPES = {"none", "python", "shell"}
    ALLOWED_VISIBILITY = {"private", "department", "public"}

    @classmethod
    def validate_name(cls, name: str) -> None:
        if not name or not name.strip():
            raise ValueError("name은 비어 있을 수 없습니다.")
        if len(name) > cls.MAX_NAME_LENGTH:
            raise ValueError(f"name은 {cls.MAX_NAME_LENGTH}자를 초과할 수 없습니다.")

    @classmethod
    def validate_description(cls, description: str) -> None:
        # 구현 반영: description은 NOT NULL이나 빈 문자열 허용, 길이 상한만 검증
        if len(description) > cls.MAX_DESCRIPTION_LENGTH:
            raise ValueError(f"description은 {cls.MAX_DESCRIPTION_LENGTH}자를 초과할 수 없습니다.")

    @classmethod
    def validate_instruction(cls, instruction: str) -> None:
        if not instruction or not instruction.strip():
            raise ValueError("instruction은 비어 있을 수 없습니다.")
        if len(instruction) > cls.MAX_INSTRUCTION_LENGTH:
            raise ValueError(f"instruction은 {cls.MAX_INSTRUCTION_LENGTH}자를 초과할 수 없습니다.")

    @classmethod
    def validate_script(cls, script_type: str, script_content: str | None) -> None:
        if script_type not in cls.ALLOWED_SCRIPT_TYPES:
            raise ValueError(f"허용되지 않은 script_type: {script_type!r}")
        if script_content and len(script_content) > cls.MAX_SCRIPT_LENGTH:
            raise ValueError(f"script_content는 {cls.MAX_SCRIPT_LENGTH}자를 초과할 수 없습니다.")
        if script_type == "none" and script_content and script_content.strip():
            raise ValueError("script_type='none'이면 script_content를 비워야 합니다.")

    @classmethod
    def validate_visibility(cls, visibility: str, department_id: str | None) -> None:
        if visibility not in cls.ALLOWED_VISIBILITY:
            raise ValueError(f"허용되지 않은 visibility: {visibility!r}")
        if visibility == "department" and not department_id:
            raise ValueError("department visibility requires department_id")


# 접근/수정/삭제/포크 권한: agent_builder.VisibilityPolicy와 동일 규칙을 skill용으로 복제
@dataclass(frozen=True)
class SkillAccessInput:
    owner_id: str
    visibility: str
    department_id: str | None
    viewer_user_id: str
    viewer_department_ids: list[str]
    viewer_role: str


class SkillVisibilityPolicy:
    @staticmethod
    def can_access(ctx: SkillAccessInput) -> bool: ...   # 소유 or public or (department & 부서일치)
    @staticmethod
    def can_edit(ctx: SkillAccessInput) -> bool:          # 소유자만
        return ctx.owner_id == ctx.viewer_user_id
    @staticmethod
    def can_delete(ctx: SkillAccessInput) -> bool:        # 소유자 or admin
        return ctx.owner_id == ctx.viewer_user_id or ctx.viewer_role == "admin"


class SkillForkPolicy:
    @staticmethod
    def can_fork(ctx: SkillAccessInput) -> bool:          # 접근가능 & 자기소유 아님
        if ctx.owner_id == ctx.viewer_user_id:
            return False
        return SkillVisibilityPolicy.can_access(ctx)
    @staticmethod
    def validate_source_status(status: str) -> None:
        if status == "deleted":
            raise ValueError("삭제된 스킬은 포크할 수 없습니다.")
```

---

## 8. Test Plan (TDD — Red→Green→Refactor)

> CLAUDE.md §4-4. 테스트 없이 구현 코드 먼저 작성 금지.

### 8.1 백엔드 (pytest)

> **구현 반영(2026-06-25)**: application 계층 UseCase 6종 테스트는 파일 난립을 피해 **`tests/application/skill_builder/test_skill_use_cases.py` 1파일로 통합**했다(케이스는 클래스별 분리, 커버리지 동등). 아래 표의 케이스는 모두 해당 파일에 포함된다.

| 테스트 파일 | 대상 케이스 |
|------------|------------|
| `tests/domain/skill_builder/test_policies.py` | validate_name/instruction/description/script(none+content 충돌)/visibility, can_edit/can_delete/can_fork |
| `tests/domain/skill_builder/test_schemas.py` | `__post_init__`(department 불변식), `apply_update` 부분수정, `soft_delete`, `fork_for`(private 강제, forked_from 세팅) |
| `tests/application/skill_builder/test_skill_use_cases.py` | Create(정상/빈 instruction/none+script 충돌/department 검증), Update(부분수정/비소유 Permission/미존재), List(my/accessible RBAC), Delete(soft-delete/권한), Fork(소유자·forked_from·private/자기소유/삭제본) |
| `tests/infrastructure/skill_builder/test_skill_repository.py` | save/find_by_id/soft_delete/list_by_user, model↔entity 매핑(trigger↔trigger_text) |

> ⚠️ idt pytest는 Windows 이벤트 루프 teardown으로 교차 실행 시 산발 실패 → 신규 테스트는 **격리 실행**으로 검증. 사전 실패(tests/api 28·infra 30)는 신규 회귀로 오인 금지.

### 8.2 프론트 (Vitest + RTL + MSW, `--pool=threads`)

| 테스트 파일 | 대상 |
|------------|------|
| `src/__tests__/mocks/handlers.ts` | `/api/v1/skills` MSW 핸들러(list/create/update/delete/fork) |
| `src/hooks/useSkills.test.ts` | 목록/생성/수정/삭제/fork 훅 + 캐시 무효화 |
| `src/pages/AdminSkillsPage/index.test.tsx` | 목록 렌더, 빈/에러 상태, 생성 모달 오픈 |
| `src/pages/AdminSkillsPage/components/SkillFormModal.test.tsx` | 필수값 검증, script_type=none일 때 script 비활성, 제출 payload |

---

## 9. Clean Architecture / 레이어 배치

### 9.1 This Feature's Layer Assignment (백엔드)

| Component | Layer | Location |
|-----------|-------|----------|
| `SkillDefinition`, `SkillVisibility`, `SkillScriptType` | Domain | `domain/skill_builder/schemas.py` |
| `SkillRepositoryInterface` | Domain | `domain/skill_builder/interfaces.py` |
| `SkillBuilderPolicy`, `SkillVisibilityPolicy`, `SkillForkPolicy` | Domain | `domain/skill_builder/policies.py` |
| Create/Get/List/Update/Delete/Fork UseCase + DTO | Application | `application/skill_builder/*` |
| `SkillDefinitionModel` | Infrastructure | `infrastructure/persistence/models/skill_builder/models.py` |
| `SkillRepository` | Infrastructure | `infrastructure/skill_builder/skill_repository.py` |
| `skill_builder_router` | Interface | `api/routes/skill_builder_router.py` |
| `create_skill_builder_factories()` | Composition Root | `api/main.py` |

### 9.2 Repository Interface — `domain/skill_builder/interfaces.py`

```python
from abc import ABC, abstractmethod
from src.domain.skill_builder.schemas import SkillDefinition


class SkillRepositoryInterface(ABC):
    @abstractmethod
    async def save(self, skill: SkillDefinition, request_id: str) -> SkillDefinition: ...
    @abstractmethod
    async def find_by_id(self, skill_id: str, request_id: str) -> SkillDefinition | None: ...
    @abstractmethod
    async def update(self, skill: SkillDefinition, request_id: str) -> SkillDefinition: ...
    @abstractmethod
    async def list_by_user(self, user_id: str, request_id: str) -> list[SkillDefinition]: ...
    @abstractmethod
    async def list_accessible(
        self, viewer_user_id: str, viewer_department_ids: list[str],
        scope: str, search: str | None, page: int, size: int, request_id: str,
    ) -> tuple[list[SkillDefinition], int]: ...
    @abstractmethod
    async def soft_delete(self, skill_id: str, request_id: str) -> None: ...
```

### 9.3 Repository 구현 핵심 (`infrastructure/skill_builder/skill_repository.py`)

- `MySQLBaseRepository[SkillDefinitionModel]` + `SkillRepositoryInterface` 다중 상속(mcp_server_repository.py 동형).
- 모듈 레벨 `_to_model(entity)` / `_to_entity(model)` 매퍼 (cipher 없음 — D1).
- `save`/`update` 모두 `_base_save`(flush)에 위임 — **commit/rollback 호출 금지**(세션 미들웨어 관리).
- `list_accessible`: `MySQLQueryCondition` 또는 명시적 select로 visibility/부서/status='active' 필터 + 총건수. scope 분기(mine/department/public/all).
- `soft_delete`: find → `status='deleted'` → save(flush).

### 9.4 DI Factory (`api/main.py`)

```python
def create_skill_builder_factories():
    """Return per-request DI factories for Skill Builder use cases."""
    app_logger = get_app_logger()

    def _make_repo(session: AsyncSession):
        return SkillRepository(session=session, logger=app_logger)

    def create_factory(session: AsyncSession = Depends(get_session)):
        return CreateSkillUseCase(repository=_make_repo(session), logger=app_logger)

    def get_factory(session: AsyncSession = Depends(get_session)):
        return GetSkillUseCase(repository=_make_repo(session), logger=app_logger)

    def list_factory(session: AsyncSession = Depends(get_session)):
        return ListSkillsUseCase(
            repository=_make_repo(session),
            dept_repo=DepartmentRepository(session=session, logger=app_logger),
            logger=app_logger,
        )

    def update_factory(session: AsyncSession = Depends(get_session)):
        return UpdateSkillUseCase(repository=_make_repo(session), logger=app_logger)

    def delete_factory(session: AsyncSession = Depends(get_session)):
        return DeleteSkillUseCase(repository=_make_repo(session), logger=app_logger)

    def fork_factory(session: AsyncSession = Depends(get_session)):
        return ForkSkillUseCase(
            repository=_make_repo(session),
            dept_repo=DepartmentRepository(session=session, logger=app_logger),
            logger=app_logger,
        )
    return create_factory, get_factory, list_factory, update_factory, delete_factory, fork_factory
```

`_register_routes`(또는 동등 override 블록)에서:

```python
(_skill_create_f, _skill_get_f, _skill_list_f,
 _skill_update_f, _skill_delete_f, _skill_fork_f) = create_skill_builder_factories()
app.dependency_overrides[get_create_skill_use_case] = _skill_create_f
app.dependency_overrides[get_get_skill_use_case]    = _skill_get_f
app.dependency_overrides[get_list_skills_use_case]  = _skill_list_f
app.dependency_overrides[get_update_skill_use_case] = _skill_update_f
app.dependency_overrides[get_delete_skill_use_case] = _skill_delete_f
app.dependency_overrides[get_fork_skill_use_case]   = _skill_fork_f
app.include_router(skill_builder_router)
```

### 9.5 의존성 규칙 체크

```
interface ──→ application ──→ domain ←── infrastructure
                    └──────────────→ infrastructure (DI로만)
규칙: domain은 외부 무참조. skill 도메인은 agent 도메인을 import하지 않는다(결합 방지).
```

---

## 10. Coding Convention 적용

| 항목 | 적용 |
|------|------|
| 네이밍 | 클래스 PascalCase, 함수 snake_case, 상수 UPPER_SNAKE |
| 함수 길이 | 40줄 이내 (UseCase.execute 분할) |
| if 중첩 | 2단계 이내 |
| 타입 | dataclass(domain) / pydantic(DTO) / typing 명시 |
| 로깅 | `LoggerInterface` + `request_id` 전파, `print()` 금지 |
| config | 하드코딩 금지(상수는 Policy 클래스 상수로) |
| 프론트 | 컴포넌트 PascalCase.tsx, 훅 camelCase.ts, 엔드포인트 상수 `constants/api.ts` |

---

## 11. Implementation Guide

### 11.1 구현 순서 (Plan §12 반영)

1. [ ] `db/migration/V033__create_skill_definition.sql`
2. [ ] domain: `schemas.py` → `interfaces.py` → `policies.py` (+ 테스트 먼저)
3. [ ] infrastructure: `SkillDefinitionModel` → `SkillRepository` (+ 테스트)
4. [ ] application: DTO → Create/Get/List/Update/Delete/Fork UseCase (+ 테스트)
5. [ ] interface: `skill_builder_router.py` + `main.py` DI 연결 + include_router
6. [ ] 백엔드 통합 검증 (격리 실행)
7. [ ] 프론트: `types/skill.ts` + `constants/api.ts` (계약 동기화)
8. [ ] `services/skillService.ts` + `hooks/useSkills.ts` + MSW + 테스트
9. [ ] `AdminSkillsPage`(목록/폼/삭제/Fork) + `adminNav` + 라우트 + 테스트
10. [ ] 브라우저 통합 확인 (dev 서버)

### 11.2 Definition of Done (Plan §11)

- [ ] V033 적용 가능 / `/api/v1/skills` CRUD+fork 동작
- [ ] visibility + RBAC 접근 제어 / soft-delete 동작
- [ ] 백엔드 신규 테스트 통과(격리) / 프론트 훅·컴포넌트 테스트 통과
- [ ] 프론트 타입이 백엔드 스키마와 일치(계약 동기화)
- [ ] `script_content`는 저장만 되고 실행되지 않음(전제 준수)

---

## 12. Security Considerations

- [x] **스크립트 미실행**: `script_content`는 TEXT 저장만 — eval/exec/subprocess 금지(런타임은 후속 phase 별도 설계).
- [x] **RBAC**: 수정/삭제는 소유자(or admin), 조회는 visibility 기반. 라우터에서 `get_current_user` 강제.
- [x] **입력 검증**: 길이 상한(name/instruction/script), enum 화이트리스트로 비정상 값 차단.
- [ ] XSS: 프론트에서 instruction/script_content 렌더 시 평문 textarea/`<pre>`로만 표시(HTML 미해석).
- [x] **비밀값 없음**: 암호화 컬럼 불필요(D1) — 자격증명 저장 요구 발생 시 후속 phase에서 mcp의 Fernet 패턴 도입.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-06-25 | Initial draft — Plan 기반 4계층 상세 설계 | 배상규 |
