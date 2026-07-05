"""UpdateSkillUseCase: skill 부분 수정 (소유자만)."""
from datetime import datetime

from src.application.skill_builder.schemas import (
    SkillResponse,
    UpdateSkillRequest,
    to_response,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.skill_builder.interfaces import SkillRepositoryInterface
from src.domain.skill_builder.policies import SkillBuilderPolicy
from src.domain.skill_builder.schemas import SkillScriptType, SkillVisibility


class UpdateSkillUseCase:
    def __init__(
        self,
        repository: SkillRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._repo = repository
        self._logger = logger

    async def execute(
        self,
        skill_id: str,
        request: UpdateSkillRequest,
        request_id: str,
        viewer_user_id: str,
    ) -> SkillResponse:
        self._logger.info(
            "UpdateSkillUseCase start", request_id=request_id, skill_id=skill_id
        )
        skill = await self._repo.find_by_id(skill_id, request_id)
        if skill is None or skill.status == "deleted":
            raise ValueError("스킬을 찾을 수 없습니다.")
        if skill.user_id != viewer_user_id:
            raise PermissionError("수정 권한 없음")

        self._validate(request, skill.script_type.value, skill.department_id)
        skill.apply_update(
            name=request.name,
            description=request.description,
            instruction=request.instruction,
            trigger=request.trigger,
            script_type=SkillScriptType(request.script_type)
            if request.script_type is not None
            else None,
            script_content=request.script_content,
            visibility=SkillVisibility(request.visibility)
            if request.visibility is not None
            else None,
            department_id=request.department_id,
        )
        skill.updated_at = datetime.utcnow()
        updated = await self._repo.update(skill, request_id)
        self._logger.info("UpdateSkillUseCase done", request_id=request_id)
        return to_response(updated)

    @staticmethod
    def _validate(
        request: UpdateSkillRequest, cur_script_type: str, cur_department_id: str | None
    ) -> None:
        if request.name is not None:
            SkillBuilderPolicy.validate_name(request.name)
        if request.instruction is not None:
            SkillBuilderPolicy.validate_instruction(request.instruction)
        if request.script_type is not None or request.script_content is not None:
            SkillBuilderPolicy.validate_script(
                request.script_type or cur_script_type, request.script_content
            )
        if request.visibility is not None:
            SkillBuilderPolicy.validate_visibility(
                request.visibility, request.department_id or cur_department_id
            )
