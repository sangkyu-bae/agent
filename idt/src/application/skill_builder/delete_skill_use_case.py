"""DeleteSkillUseCase: skill 소프트 삭제 (소유자 또는 admin)."""
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.skill_builder.interfaces import SkillRepositoryInterface
from src.domain.skill_builder.policies import SkillAccessInput, SkillVisibilityPolicy


class DeleteSkillUseCase:
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
        viewer_user_id: str,
        viewer_role: str,
        request_id: str,
    ) -> None:
        self._logger.info(
            "DeleteSkillUseCase start", request_id=request_id, skill_id=skill_id
        )
        skill = await self._repo.find_by_id(skill_id, request_id)
        if skill is None or skill.status == "deleted":
            raise ValueError("스킬을 찾을 수 없습니다.")

        ctx = SkillAccessInput(
            owner_id=skill.user_id,
            visibility=skill.visibility.value,
            department_id=skill.department_id,
            viewer_user_id=viewer_user_id,
            viewer_department_ids=[],
            viewer_role=viewer_role,
        )
        if not SkillVisibilityPolicy.can_delete(ctx):
            raise PermissionError("삭제 권한 없음")

        await self._repo.soft_delete(skill_id, request_id)
        self._logger.info("DeleteSkillUseCase done", request_id=request_id)
