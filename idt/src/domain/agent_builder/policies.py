"""AgentBuilderPolicy, UpdateAgentPolicy: 에이전트 빌더 도메인 규칙."""


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


class UpdateAgentPolicy:
    @classmethod
    def validate_update(cls, status: str, system_prompt: str | None) -> None:
        if status != "active":
            raise ValueError("비활성화된 에이전트는 수정할 수 없습니다.")
        if system_prompt is not None:
            AgentBuilderPolicy.validate_system_prompt(system_prompt)
