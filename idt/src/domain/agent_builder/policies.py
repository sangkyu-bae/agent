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
    MAX_SUB_AGENTS = 3
    MAX_WORKERS_TOTAL = 6
    MIN_WORKERS = 1
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
    def validate_worker_count(cls, workers: list) -> None:
        if len(workers) < cls.MIN_WORKERS:
            raise ValueError(f"최소 {cls.MIN_WORKERS}개 이상의 워커가 필요합니다.")
        if len(workers) > cls.MAX_WORKERS_TOTAL:
            raise ValueError(f"워커는 최대 {cls.MAX_WORKERS_TOTAL}개까지 선택할 수 있습니다.")

        tool_count = sum(1 for w in workers if w.worker_type == "tool")
        sub_agent_count = sum(1 for w in workers if w.worker_type == "sub_agent")

        if tool_count > cls.MAX_TOOLS:
            raise ValueError(f"도구는 최대 {cls.MAX_TOOLS}개까지 선택할 수 있습니다.")
        if sub_agent_count > cls.MAX_SUB_AGENTS:
            raise ValueError(f"서브 에이전트는 최대 {cls.MAX_SUB_AGENTS}개까지 선택할 수 있습니다.")

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


class QualityGatePolicy:
    """워커 응답 품질 검증 도메인 규칙."""

    MIN_RESPONSE_LENGTH = 10
    EMPTY_INDICATORS = ["모르겠습니다", "답변할 수 없습니다", "정보를 찾을 수 없"]

    @classmethod
    def check_response(cls, content: str) -> bool:
        if not content or len(content.strip()) < cls.MIN_RESPONSE_LENGTH:
            return False

        stripped = content.strip().lower()
        for indicator in cls.EMPTY_INDICATORS:
            if stripped.startswith(indicator):
                return False

        return True


class SearchPipelinePolicy:
    """search 노드 파이프라인 도메인 규칙 (search-node-query-pipeline).

    순수 규칙만 보관 — LLM/도구 호출 없음.
    """

    MAX_SEARCH_ATTEMPTS = 3            # 최초 1 + 재시도 2
    DEFAULT_COMPRESS_THRESHOLD = 4000  # 압축 발동 임계 길이(자)

    def __init__(self, compress_threshold: int | None = None) -> None:
        self.compress_threshold = (
            compress_threshold
            if compress_threshold and compress_threshold > 0
            else self.DEFAULT_COMPRESS_THRESHOLD
        )

    def is_last_attempt(self, attempt: int) -> bool:
        """attempt(1-base)가 마지막 시도인가 — True면 validate 생략 (Design D1)."""
        return attempt >= self.MAX_SEARCH_ATTEMPTS

    def needs_compression(self, text: str) -> bool:
        return len(text) > self.compress_threshold


class UpdateAgentPolicy:
    @classmethod
    def validate_update(cls, status: str, system_prompt: str | None) -> None:
        if status != "active":
            raise ValueError("비활성화된 에이전트는 수정할 수 없습니다.")
        if system_prompt is not None:
            AgentBuilderPolicy.validate_system_prompt(system_prompt)


# ── Multi-Agent Composition Policies ──────────────────────────


class CircularReferenceError(ValueError):
    """에이전트 참조 순환 발생."""

    def __init__(self, cycle_path: list[str]) -> None:
        self.cycle_path = cycle_path
        path_str = " → ".join(cycle_path)
        super().__init__(f"순환참조가 감지되었습니다: {path_str}")


class NestingDepthExceededError(ValueError):
    """중첩 깊이 초과."""

    def __init__(self, current_depth: int, max_depth: int) -> None:
        super().__init__(
            f"중첩 깊이 {current_depth}이(가) 최대 허용 깊이 {max_depth}을(를) 초과합니다"
        )


class CircularReferencePolicy:
    """에이전트 간 순환참조 방지 정책."""

    @staticmethod
    def validate_no_cycle(current_agent_id: str, visited: set[str]) -> None:
        if current_agent_id in visited:
            cycle = list(visited) + [current_agent_id]
            raise CircularReferenceError(cycle)


class NestingDepthPolicy:
    """에이전트 중첩 깊이 제한 정책."""

    MAX_NESTING_DEPTH = 2

    @classmethod
    def validate_depth(cls, current_depth: int) -> None:
        if current_depth > cls.MAX_NESTING_DEPTH:
            raise NestingDepthExceededError(current_depth, cls.MAX_NESTING_DEPTH)


class SubAgentAccessPolicy:
    """[DEPRECATED] 구독 기반 서브에이전트 사용 권한 정책.

    DD-1(agent-subagent-management) 이후 서브에이전트 접근은 가시성 기반
    `VisibilityPolicy.can_access`로 일원화되었다. 이 정책은 더 이상 호출되지 않으며
    (dead code), 하위 호환/회귀 테스트 보존 목적으로만 남겨 둔다. 신규 코드에서
    사용하지 말 것.
    """

    @staticmethod
    def can_use_as_sub_agent(
        parent_owner_id: str,
        sub_agent_owner_id: str,
        is_subscribed: bool,
    ) -> bool:
        if parent_owner_id == sub_agent_owner_id:
            return True
        return is_subscribed
