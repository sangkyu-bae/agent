"""AgentBuilderPolicy, UpdateAgentPolicy, VisibilityPolicy: 에이전트 빌더 도메인 규칙."""
from dataclasses import dataclass
from enum import Enum


class Visibility(str, Enum):
    PRIVATE = "private"
    DEPARTMENT = "department"
    PUBLIC = "public"


SCOPE_TO_VISIBILITY: dict[str, str] = {
    "PERSONAL": "private",
    "DEPARTMENT": "department",
    "PUBLIC": "public",
}

VISIBILITY_RANK: dict[str, int] = {
    "private": 0,
    "department": 1,
    "public": 2,
}


@dataclass(frozen=True)
class AccessCheckInput:
    agent_owner_id: str
    agent_visibility: str
    agent_department_id: str | None
    viewer_user_id: str
    viewer_department_ids: list[str]
    viewer_role: str


class VisibilityPolicy:
    @staticmethod
    def can_access(ctx: AccessCheckInput) -> bool:
        if ctx.agent_owner_id == ctx.viewer_user_id:
            return True
        if ctx.agent_visibility == Visibility.PUBLIC:
            return True
        if ctx.agent_visibility == Visibility.DEPARTMENT:
            return (
                ctx.agent_department_id is not None
                and ctx.agent_department_id in ctx.viewer_department_ids
            )
        return False

    @staticmethod
    def can_edit(ctx: AccessCheckInput) -> bool:
        return ctx.agent_owner_id == ctx.viewer_user_id

    @staticmethod
    def can_delete(ctx: AccessCheckInput) -> bool:
        return (
            ctx.agent_owner_id == ctx.viewer_user_id
            or ctx.viewer_role == "admin"
        )

    @staticmethod
    def max_visibility_for_scopes(scopes: list[str]) -> str:
        if not scopes:
            raise ValueError("scopes must not be empty")
        ranks: list[int] = []
        for scope in scopes:
            vis = SCOPE_TO_VISIBILITY.get(scope)
            if vis is None:
                raise ValueError(f"Unknown scope: {scope}")
            ranks.append(VISIBILITY_RANK[vis])
        min_rank = min(ranks)
        for vis, rank in VISIBILITY_RANK.items():
            if rank == min_rank:
                return vis
        raise ValueError("Unreachable")

    @staticmethod
    def clamp_visibility(requested: str, scopes: list[str]) -> str:
        if not scopes:
            return requested
        max_vis = VisibilityPolicy.max_visibility_for_scopes(scopes)
        if VISIBILITY_RANK[requested] > VISIBILITY_RANK[max_vis]:
            return max_vis
        return requested


class AgentBuilderPolicy:
    MAX_TOOLS = 5
    MIN_TOOLS = 1
    MAX_NAME_LENGTH = 200
    MAX_SYSTEM_PROMPT_LENGTH = 4000
    MAX_USER_REQUEST_LENGTH = 1000

    @classmethod
    def validate_tool_count(cls, count: int) -> None:
        if count < cls.MIN_TOOLS:
            raise ValueError(f"최소 {cls.MIN_TOOLS}개 이상의 도구가 필요합니다.")
        if count > cls.MAX_TOOLS:
            raise ValueError(f"도구는 최대 {cls.MAX_TOOLS}개까지 선택할 수 있습니다.")

    @classmethod
    def validate_system_prompt(cls, prompt: str) -> None:
        if len(prompt) > cls.MAX_SYSTEM_PROMPT_LENGTH:
            raise ValueError(
                f"system_prompt는 {cls.MAX_SYSTEM_PROMPT_LENGTH}자를 초과할 수 없습니다."
            )

    @classmethod
    def validate_name(cls, name: str) -> None:
        if not name or not name.strip():
            raise ValueError("name은 비어 있을 수 없습니다.")
        if len(name) > cls.MAX_NAME_LENGTH:
            raise ValueError(f"name은 {cls.MAX_NAME_LENGTH}자를 초과할 수 없습니다.")


class ForkPolicy:
    @staticmethod
    def can_fork(ctx: AccessCheckInput) -> bool:
        """포크 가능 여부: 접근 가능 + 자신의 에이전트가 아닌 경우."""
        if ctx.agent_owner_id == ctx.viewer_user_id:
            return False
        return VisibilityPolicy.can_access(ctx)

    @staticmethod
    def validate_source_status(status: str) -> None:
        """삭제된 에이전트는 포크 불가."""
        if status == "deleted":
            raise ValueError("삭제된 에이전트는 포크할 수 없습니다.")


class UpdateAgentPolicy:
    @classmethod
    def validate_update(cls, status: str, system_prompt: str | None) -> None:
        if status != "active":
            raise ValueError("비활성화된 에이전트는 수정할 수 없습니다.")
        if system_prompt is not None:
            AgentBuilderPolicy.validate_system_prompt(system_prompt)
