"""ForkSkillUseCase: skill 전체 복제 (접근 가능 + 자기 소유 아님)."""
import uuid
from datetime import datetime

from src.application.skill_builder.schemas import SkillResponse, to_response
from src.domain.department.interfaces import DepartmentRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.skill_builder.interfaces import SkillRepositoryInterface
from src.domain.skill_builder.policies import (
    SkillAccessInput,
    SkillForkPolicy,
)


class ForkSkillUseCase:
    def __init__(
        self,
        repository: SkillRepositoryInterface,
        dept_repo: DepartmentRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._repo = repository
        self._dept_repo = dept_repo
        self._logger = logger

    async def execute(
        self,
        source_skill_id: str,
        user_id: str,
        custom_name: str | None,
        request_id: str,
    ) -> SkillResponse:
        self._logger.info(
            "ForkSkillUseCase start", request_id=request_id, source=source_skill_id
        )
        source = await self._repo.find_by_id(source_skill_id, request_id)
        if source is None:
            raise ValueError("스킬을 찾을 수 없습니다.")
        SkillForkPolicy.validate_source_status(source.status)

        viewer_dept_ids = await self._viewer_dept_ids(user_id, request_id)
        ctx = SkillAccessInput(
            owner_id=source.user_id,
            visibility=source.visibility.value,
            department_id=source.department_id,
            viewer_user_id=user_id,
            viewer_department_ids=viewer_dept_ids,
            viewer_role="user",
        )
        if source.user_id == user_id:
            raise ValueError("자신의 스킬은 포크할 수 없습니다.")
        if not SkillForkPolicy.can_fork(ctx):
            raise PermissionError("접근 권한 없음")

        now = datetime.utcnow()
        forked = source.fork_for(str(uuid.uuid4()), user_id, now)
        if custom_name:
            forked.name = custom_name
        saved = await self._repo.save(forked, request_id)
        self._logger.info(
            "ForkSkillUseCase done", request_id=request_id, id=saved.id
        )
        return to_response(saved)

    async def _viewer_dept_ids(self, user_id: str, request_id: str) -> list[str]:
        rows = await self._dept_repo.find_departments_by_user(
            int(user_id), request_id
        )
        return [r.department_id for r in rows]
