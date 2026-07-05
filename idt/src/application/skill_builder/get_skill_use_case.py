"""GetSkillUseCase: skill 단건 조회 (가시성 접근 제어)."""
from src.application.skill_builder.schemas import SkillResponse, to_response
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.skill_builder.interfaces import SkillRepositoryInterface
from src.domain.skill_builder.policies import SkillAccessInput, SkillVisibilityPolicy


class GetSkillUseCase:
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
        request_id: str,
        viewer_user_id: str,
        viewer_role: str,
        viewer_department_ids: list[str] | None = None,
    ) -> SkillResponse | None:
        self._logger.info(
            "GetSkillUseCase start", request_id=request_id, skill_id=skill_id
        )
        skill = await self._repo.find_by_id(skill_id, request_id)
        if skill is None or skill.status == "deleted":
            return None

        ctx = SkillAccessInput(
            owner_id=skill.user_id,
            visibility=skill.visibility.value,
            department_id=skill.department_id,
            viewer_user_id=viewer_user_id,
            viewer_department_ids=viewer_department_ids or [],
            viewer_role=viewer_role,
        )
        if not SkillVisibilityPolicy.can_access(ctx):
            raise PermissionError("접근 권한 없음")
        return to_response(skill)
