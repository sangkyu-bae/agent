"""Skill Builder 요청/응답 DTO + 엔티티→응답 매핑 헬퍼."""
from pydantic import BaseModel, Field

from src.domain.skill_builder.policies import SkillAccessInput, SkillVisibilityPolicy
from src.domain.skill_builder.schemas import SkillDefinition


class CreateSkillRequest(BaseModel):
    user_id: str = ""  # router에서 current_user.id 주입
    name: str = Field(..., max_length=255)
    description: str = ""
    instruction: str
    trigger: str | None = None
    script_type: str = "none"
    script_content: str | None = None
    visibility: str = "private"
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
    scope: str = "all"  # mine|department|public|all
    search: str | None = None
    page: int = 1
    size: int = 20


class ForkSkillRequest(BaseModel):
    name: str | None = None


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


# 명세 일관성을 위한 alias
CreateSkillResponse = SkillResponse
GetSkillResponse = SkillResponse
UpdateSkillResponse = SkillResponse
ForkSkillResponse = SkillResponse


def to_response(s: SkillDefinition) -> SkillResponse:
    return SkillResponse(
        id=s.id,
        user_id=s.user_id,
        name=s.name,
        description=s.description,
        instruction=s.instruction,
        trigger=s.trigger,
        script_type=s.script_type.value,
        script_content=s.script_content,
        status=s.status,
        visibility=s.visibility.value,
        department_id=s.department_id,
        forked_from=s.forked_from,
        forked_at=s.forked_at.isoformat() if s.forked_at else None,
        created_at=s.created_at.isoformat(),
        updated_at=s.updated_at.isoformat(),
    )


def to_summary(
    s: SkillDefinition, viewer_user_id: str, viewer_role: str
) -> SkillSummary:
    ctx = SkillAccessInput(
        owner_id=s.user_id,
        visibility=s.visibility.value,
        department_id=s.department_id,
        viewer_user_id=viewer_user_id,
        viewer_department_ids=[],
        viewer_role=viewer_role,
    )
    return SkillSummary(
        id=s.id,
        name=s.name,
        description=s.description,
        script_type=s.script_type.value,
        visibility=s.visibility.value,
        owner_user_id=s.user_id,
        forked_from=s.forked_from,
        can_edit=SkillVisibilityPolicy.can_edit(ctx),
        can_delete=SkillVisibilityPolicy.can_delete(ctx),
        created_at=s.created_at.isoformat(),
    )
