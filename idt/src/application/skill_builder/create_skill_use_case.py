"""CreateSkillUseCase: skill 생성."""
import uuid
from datetime import datetime

from src.application.skill_builder.schemas import (
    CreateSkillRequest,
    SkillResponse,
    to_response,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.skill_builder.interfaces import SkillRepositoryInterface
from src.domain.skill_builder.policies import SkillBuilderPolicy
from src.domain.skill_builder.schemas import (
    SkillDefinition,
    SkillScriptType,
    SkillVisibility,
)


class CreateSkillUseCase:
    def __init__(
        self,
        repository: SkillRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._repo = repository
        self._logger = logger

    async def execute(
        self, request: CreateSkillRequest, request_id: str
    ) -> SkillResponse:
        self._logger.info(
            "CreateSkillUseCase start", request_id=request_id, name=request.name
        )
        SkillBuilderPolicy.validate_name(request.name)
        SkillBuilderPolicy.validate_description(request.description)
        SkillBuilderPolicy.validate_instruction(request.instruction)
        SkillBuilderPolicy.validate_script(request.script_type, request.script_content)
        SkillBuilderPolicy.validate_visibility(
            request.visibility, request.department_id
        )

        now = datetime.utcnow()
        skill = SkillDefinition(
            id=str(uuid.uuid4()),
            user_id=request.user_id,
            name=request.name,
            description=request.description,
            instruction=request.instruction,
            trigger=request.trigger,
            script_type=SkillScriptType(request.script_type),
            script_content=request.script_content,
            status="active",
            visibility=SkillVisibility(request.visibility),
            department_id=request.department_id,
            forked_from=None,
            forked_at=None,
            created_at=now,
            updated_at=now,
        )
        saved = await self._repo.save(skill, request_id)
        self._logger.info(
            "CreateSkillUseCase done", request_id=request_id, id=saved.id
        )
        return to_response(saved)
