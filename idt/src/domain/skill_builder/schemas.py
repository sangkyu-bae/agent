"""도메인 스키마: SkillDefinition 엔티티 + SkillVisibility / SkillScriptType enum."""
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
    """재사용 Skill 정의 도메인 객체 (skill_definition 테이블 1 row).

    instruction(지시문) + script_content(실행 스크립트 텍스트, 저장 전용)를 보관한다.
    소유/visibility/fork 구조는 agent_definition과 동일하게 적용된다.
    """

    id: str
    user_id: str
    name: str
    description: str
    instruction: str
    trigger: str | None
    script_type: SkillScriptType
    script_content: str | None
    status: str  # 'active' | 'deleted'
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
        """status='deleted'로 소프트 삭제."""
        self.status = "deleted"

    def fork_for(
        self, new_id: str, user_id: str, now: datetime
    ) -> "SkillDefinition":
        """다른 사용자 소유의 새 skill로 전체 복제. fork 본은 항상 private."""
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
