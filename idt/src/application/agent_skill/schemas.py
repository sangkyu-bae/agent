"""agent_skill DTO + 매핑."""
from pydantic import BaseModel

from src.domain.skill_builder.schemas import SkillDefinition


class AttachSkillRequest(BaseModel):
    skill_id: str


class AttachedSkillItem(BaseModel):
    skill_id: str
    name: str
    description: str
    script_type: str
    sort_order: int
    has_script: bool


class AttachSkillResponse(AttachedSkillItem):
    pass


class ListAttachedSkillsResponse(BaseModel):
    agent_id: str
    skills: list[AttachedSkillItem]
    total: int
    max_attachable: int


def to_item(skill: SkillDefinition, sort_order: int) -> AttachedSkillItem:
    script_type = skill.script_type.value
    return AttachedSkillItem(
        skill_id=skill.id,
        name=skill.name,
        description=skill.description,
        script_type=script_type,
        sort_order=sort_order,
        has_script=script_type != "none",
    )
