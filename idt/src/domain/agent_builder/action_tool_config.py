"""ActionToolConfig: action 워커 설정 VO.

Design Ref: action-category-compose-node §3.1 / D-10.

DocumentGeneratorToolConfig 패턴(frozen dataclass + __post_init__ 검증 +
model_dump). WorkerDefinition.tool_config(dict)에 asdict 형태로 저장된다.

알 수 없는 키를 무시하는 이유: tool_config dict는 도구마다 다른 설정을 담는
공용 자리이고, 후속 사이클(fixed_args 등)에서 키가 늘어나도 기존 저장분이
깨지지 않아야 한다.
"""
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ActionToolConfig:
    """에이전트별 action 워커 설정.

    - draft_arg_key: 초안 원문을 넣을 도구 인자 키. 빈 문자열이면 런타임에
      ActionArgumentPolicy.DRAFT_KEY_CANDIDATES 순서로 inputSchema에 있는
      첫 키를 쓴다(관례 키 자동 탐색).
    """

    draft_arg_key: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.draft_arg_key, str):
            raise ValueError(
                f"draft_arg_key must be a string, got {type(self.draft_arg_key).__name__}"
            )

    @classmethod
    def from_tool_config(cls, tool_config: dict | None) -> "ActionToolConfig":
        """WorkerDefinition.tool_config → VO. None·빈 dict·null 값은 기본값."""
        cfg = tool_config or {}
        raw = cfg.get("draft_arg_key")
        return cls(draft_arg_key=str(raw) if raw is not None else "")

    def model_dump(self) -> dict:
        """WorkerDefinition.tool_config 저장용 dict."""
        return asdict(self)
