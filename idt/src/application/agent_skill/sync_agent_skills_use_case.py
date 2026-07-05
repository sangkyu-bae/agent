"""SyncAgentSkillsUseCase: 에이전트 부착 스킬을 desired-set으로 재조정(reconcile).

agent-skill-toggle: create/update 시점에 프론트가 보낸 skill_ids(목표 상태)를 받아
현재 링크와 비교해 detach/attach 한다. 검증(존재·접근권한·개수)을 먼저 수행하므로
하나라도 무효면 아무 것도 변경하지 않는다(all-or-nothing). 실제 트랜잭션 롤백은
세션 미들웨어가 담당한다(commit/rollback 직접 호출 금지).

권한 조합(에이전트 수정권한은 호출 UseCase에서, skill 접근권한은 여기서 SkillVisibilityPolicy로)
은 application 계층에서 처리한다 — 도메인 간 직접 import 회피.
"""
from datetime import datetime

from src.domain.agent_skill.interfaces import AgentSkillRepositoryInterface
from src.domain.agent_skill.policies import SkillAttachPolicy
from src.domain.agent_skill.schemas import AgentSkillLink
from src.domain.department.interfaces import DepartmentRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.skill_builder.interfaces import SkillRepositoryInterface
from src.domain.skill_builder.policies import (
    SkillAccessInput,
    SkillVisibilityPolicy,
)


class SyncAgentSkillsUseCase:
    def __init__(
        self,
        agent_skill_repo: AgentSkillRepositoryInterface,
        skill_repo: SkillRepositoryInterface,
        dept_repo: DepartmentRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._links = agent_skill_repo
        self._skills = skill_repo
        self._dept_repo = dept_repo
        self._logger = logger

    async def sync(
        self,
        agent_id: str,
        desired_skill_ids: list[str],
        request_id: str,
        *,
        viewer_user_id: str,
        viewer_role: str,
    ) -> list[str]:
        """desired_skill_ids(목표 상태)로 부착 링크를 재조정한다.

        반환: 최종 부착된 skill_id 목록(순서 = sort_order).
        """
        desired = self._dedupe_keep_order(desired_skill_ids)
        self._logger.info(
            "SyncAgentSkillsUseCase start",
            request_id=request_id, agent_id=agent_id, desired=desired,
        )

        # 1) 검증 (all-or-nothing: 무효 발견 시 변경 전 raise)
        SkillAttachPolicy.validate_count(desired)
        if desired:
            dept_ids = await self._viewer_dept_ids(viewer_user_id, request_id)
            for sid in desired:
                skill = await self._skills.find_by_id(sid, request_id)
                if skill is None or skill.status == "deleted":
                    raise ValueError(f"스킬을 찾을 수 없습니다: {sid}")
                ctx = SkillAccessInput(
                    owner_id=skill.user_id,
                    visibility=skill.visibility.value,
                    department_id=skill.department_id,
                    viewer_user_id=viewer_user_id,
                    viewer_department_ids=dept_ids,
                    viewer_role=viewer_role,
                )
                if not SkillVisibilityPolicy.can_access(ctx):
                    raise PermissionError(
                        f"이 스킬에 접근할 권한이 없습니다: {sid}"
                    )

        # 2) reconcile: 순서/구성이 동일하면 no-op
        current = [
            l.skill_id for l in await self._links.list_links(agent_id, request_id)
        ]
        if current == desired:
            self._logger.info(
                "SyncAgentSkillsUseCase noop",
                request_id=request_id, agent_id=agent_id,
            )
            return desired

        # max 3라 순서/구성 변경 시 전체 교체가 가장 단순·정확(sort_order 재부여)
        for sid in current:
            await self._links.detach(agent_id, sid, request_id)
        now = datetime.utcnow()
        for idx, sid in enumerate(desired):
            await self._links.attach(
                AgentSkillLink(
                    agent_id=agent_id,
                    skill_id=sid,
                    sort_order=idx,
                    created_at=now,
                ),
                request_id,
            )
        self._logger.info(
            "SyncAgentSkillsUseCase done",
            request_id=request_id, agent_id=agent_id, final=desired,
        )
        return desired

    @staticmethod
    def _dedupe_keep_order(skill_ids: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for sid in skill_ids:
            if sid not in seen:
                seen.add(sid)
                result.append(sid)
        return result

    async def _viewer_dept_ids(
        self, viewer_user_id: str, request_id: str
    ) -> list[str]:
        rows = await self._dept_repo.find_departments_by_user(
            int(viewer_user_id), request_id
        )
        return [r.department_id for r in rows]
