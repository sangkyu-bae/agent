"""기본 에이전트 부트스트랩 — 매핑이 없는 역할만 빌더 에이전트를 만들어 매핑한다.

Design Ref: stock-analysis-agents §5.1(POST /bootstrap-agents), Plan Q6, D3.
- 이미 매핑된 역할은 건드리지 않는다(멱등). 운영자가 바꾼 에이전트를 덮어쓰지 않는다
- 도구는 설정된 MCP 서버의 허용목록 도구만 붙인다. 주문 도구는 붙이지 않는다
- 모델은 플랫폼 기본 모델(llm_model_id 없음) — 바꾸는 일은 빌더에서 한다 (module-4 결정)
- 역할별 실패는 결과로 돌려주고 매핑하지 않는다
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from src.application.market_analysis.default_prompts import (
    ROLE_NAMES,
    ROLE_PROMPTS,
    ROLE_TOKEN_LIMITS,
    ROLE_TOOLS,
)
from src.application.market_analysis.ports import (
    AgentCreator,
    RoleAgentStore,
    SettingReader,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.market_analysis.runtime import ToolSource
from src.domain.market_analysis.setting import MarketAnalysisSetting
from src.domain.market_analysis.tool_policy import ToolPolicy
from src.domain.market_analysis.value_objects import AgentRole

NAME_PREFIX = "[시장 분석] "
TAVILY_TOOL_ID = "tavily_search"


class BootstrapStatus(StrEnum):
    CREATED = "created"
    KEPT = "kept"
    FAILED = "failed"


@dataclass(frozen=True)
class BootstrapItem:
    role: AgentRole
    status: BootstrapStatus
    agent_id: str | None
    error: str | None = None


def tool_ids_for(role: AgentRole, setting: MarketAnalysisSetting) -> list[str]:
    servers = {
        ToolSource.KIS: setting.kis_server_id,
        ToolSource.DART: setting.dart_server_id,
        ToolSource.PERPLEXITY: setting.perplexity_server_id,
    }
    ids: list[str] = []
    for source, tool in ROLE_TOOLS[role]:
        if source is ToolSource.TAVILY:
            ids.append(TAVILY_TOOL_ID)
            continue
        server_id = servers.get(source)
        if not server_id:
            continue
        ToolPolicy.check(source, tool)
        ids.append(f"mcp:{server_id}:{tool}")
    return ids


class BootstrapAgentsUseCase:
    def __init__(
        self,
        *,
        roles: RoleAgentStore,
        creator: AgentCreator,
        settings: SettingReader,
        logger: LoggerInterface,
    ) -> None:
        self._roles = roles
        self._creator = creator
        self._settings = settings
        self._logger = logger

    async def execute(
        self, *, owner_user_id: str, request_id: str
    ) -> list[BootstrapItem]:
        if not owner_user_id:
            raise ValueError("owner_user_id is required")
        setting = await self._settings.get(request_id)
        mapped = await self._roles.get_all(request_id)
        items: list[BootstrapItem] = []
        for role in AgentRole:
            if mapped.get(role):
                items.append(BootstrapItem(role, BootstrapStatus.KEPT, mapped[role]))
                continue
            agent_id, error = await self._creator.create(
                name=f"{NAME_PREFIX}{ROLE_NAMES[role]}",
                system_prompt=ROLE_PROMPTS[role],
                tool_ids=tool_ids_for(role, setting),
                owner_user_id=owner_user_id,
                token_limit=ROLE_TOKEN_LIMITS[role],
                request_id=request_id,
            )
            if agent_id is None:
                self._logger.warning(
                    "market_analysis bootstrap failed",
                    request_id=request_id,
                    role=role.value,
                    error=error,
                )
                items.append(BootstrapItem(role, BootstrapStatus.FAILED, None, error))
                continue
            await self._roles.set(
                role=role,
                agent_id=agent_id,
                updated_by=owner_user_id,
                request_id=request_id,
            )
            items.append(BootstrapItem(role, BootstrapStatus.CREATED, agent_id))
        return items
