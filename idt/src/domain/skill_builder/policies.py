"""SkillBuilderPolicy / SkillVisibilityPolicy / SkillForkPolicy: skill 도메인 규칙.

agent_builder의 visibility/fork 규칙과 동일한 정책을 skill 전용으로 둔다.
도메인 격리를 위해 agent_builder 모듈을 import 하지 않는다(두 도메인 간 결합 방지).
"""
from dataclasses import dataclass


class SkillBuilderPolicy:
    """skill 입력값 유효성 규칙."""

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
        if len(description) > cls.MAX_DESCRIPTION_LENGTH:
            raise ValueError(
                f"description은 {cls.MAX_DESCRIPTION_LENGTH}자를 초과할 수 없습니다."
            )

    @classmethod
    def validate_instruction(cls, instruction: str) -> None:
        if not instruction or not instruction.strip():
            raise ValueError("instruction은 비어 있을 수 없습니다.")
        if len(instruction) > cls.MAX_INSTRUCTION_LENGTH:
            raise ValueError(
                f"instruction은 {cls.MAX_INSTRUCTION_LENGTH}자를 초과할 수 없습니다."
            )

    @classmethod
    def validate_script(cls, script_type: str, script_content: str | None) -> None:
        if script_type not in cls.ALLOWED_SCRIPT_TYPES:
            raise ValueError(f"허용되지 않은 script_type: {script_type!r}")
        if script_content and len(script_content) > cls.MAX_SCRIPT_LENGTH:
            raise ValueError(
                f"script_content는 {cls.MAX_SCRIPT_LENGTH}자를 초과할 수 없습니다."
            )
        if script_type == "none" and script_content and script_content.strip():
            raise ValueError("script_type='none'이면 script_content를 비워야 합니다.")

    @classmethod
    def validate_visibility(cls, visibility: str, department_id: str | None) -> None:
        if visibility not in cls.ALLOWED_VISIBILITY:
            raise ValueError(f"허용되지 않은 visibility: {visibility!r}")
        if visibility == "department" and not department_id:
            raise ValueError("department visibility requires department_id")


@dataclass(frozen=True)
class SkillAccessInput:
    owner_id: str
    visibility: str
    department_id: str | None
    viewer_user_id: str
    viewer_department_ids: list[str]
    viewer_role: str


class SkillVisibilityPolicy:
    """skill 접근/수정/삭제 권한 규칙 (agent_builder.VisibilityPolicy와 동일)."""

    @staticmethod
    def can_access(ctx: SkillAccessInput) -> bool:
        if ctx.owner_id == ctx.viewer_user_id:
            return True
        if ctx.visibility == "public":
            return True
        if ctx.visibility == "department":
            return (
                ctx.department_id is not None
                and ctx.department_id in ctx.viewer_department_ids
            )
        return False

    @staticmethod
    def can_edit(ctx: SkillAccessInput) -> bool:
        return ctx.owner_id == ctx.viewer_user_id

    @staticmethod
    def can_delete(ctx: SkillAccessInput) -> bool:
        return ctx.owner_id == ctx.viewer_user_id or ctx.viewer_role == "admin"


class SkillForkPolicy:
    """포크 권한 규칙: 접근 가능 + 자기 소유 아님."""

    @staticmethod
    def can_fork(ctx: SkillAccessInput) -> bool:
        if ctx.owner_id == ctx.viewer_user_id:
            return False
        return SkillVisibilityPolicy.can_access(ctx)

    @staticmethod
    def validate_source_status(status: str) -> None:
        if status == "deleted":
            raise ValueError("삭제된 스킬은 포크할 수 없습니다.")
