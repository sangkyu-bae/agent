"""ApprovalGateSettingsUseCase: 에이전트별 승인 게이트 설정 조회·저장.

approval-gate Check G3 수정. Design §3.4 의 per-agent config 오버라이드는
MergePolicy 에 구현돼 있었지만 agent_middleware.config 를 쓸 입구가 없어,
execute_after·expires_hours·timezone 이 관리자 default 로 전역 적용됐다.
금리 에이전트만 00시에 집행하는 요구(Plan v0.2)가 성립하려면 이 입구가 필요하다.

"행 존재 = 적용" 규약(builtin-middleware)을 따른다: 저장하면 행이 생기고,
on/off 는 config.mode 로 가른다. 행을 지우지 않는 이유는 설정값(cron 등)을
끈 동안에도 보존해 다시 켤 때 되살리기 위해서다.
"""
from src.application.approval.errors import ApprovalForbiddenError
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.middleware.config_policy import MiddlewareConfigPolicy
from src.domain.middleware.entities import MiddlewareType

_GATE = MiddlewareType.APPROVAL_GATE


class GateUnavailableError(Exception):
    """관리자가 카탈로그에서 승인 게이트를 비활성화했다."""

    code = "APPROVAL_GATE_UNAVAILABLE"
    http_status = 409


class ApprovalGateSettingsUseCase:
    def __init__(
        self, agent_repo, catalog_repo, agent_middleware_repo,
        logger: LoggerInterface,
    ) -> None:
        self._agent_repo = agent_repo
        self._catalog_repo = catalog_repo
        self._mw_repo = agent_middleware_repo
        self._logger = logger

    async def get(self, agent_id: str, *, user_id: str, request_id: str) -> dict:
        await self._authorize(agent_id, user_id, request_id)
        entry = await self._catalog_entry(request_id)
        record = await self._record(agent_id, request_id)
        default = dict(entry.default_config) if entry else {}
        override = (record.config or {}) if record else {}
        is_enforced = bool(entry and entry.is_enforced)
        return {
            "available": bool(entry and entry.is_active),
            "enabled": is_enforced or record is not None,
            "is_enforced": is_enforced,
            "config": {**default, **override},
        }

    async def put(
        self, agent_id: str, *, user_id: str, config: dict, request_id: str
    ) -> dict:
        await self._authorize(agent_id, user_id, request_id)
        entry = await self._catalog_entry(request_id)
        if entry is None or not entry.is_active:
            raise GateUnavailableError("approval_gate is not active in catalog")
        # 저장 시점 방어 — 통과시키면 승인 버튼을 누른 사람이 원인 모를 오류를 본다.
        MiddlewareConfigPolicy.validate(_GATE, config)
        # FR-20: 강제된 게이트는 어차피 mode=off 를 무시한다. 그 값을 저장하게
        # 두면 화면에는 꺼진 것으로 보이는데 실제로는 켜져 있는 상태가 된다.
        if entry.is_enforced and config.get("mode") == "off":
            raise ValueError("approval_gate is enforced by admin; mode=off is not allowed")
        await self._mw_repo.upsert_config(
            agent_id=agent_id, middleware_type=_GATE.value,
            config=config, request_id=request_id,
        )
        self._logger.info(
            "approval gate settings saved", request_id=request_id,
            agent_id=agent_id, mode=config.get("mode", "always"),
            has_schedule=bool(config.get("execute_after")),
        )
        return await self.get(agent_id, user_id=user_id, request_id=request_id)

    async def _authorize(self, agent_id: str, user_id: str, request_id: str) -> None:
        agent = await self._agent_repo.find_by_id(agent_id, request_id)
        if agent is None or not user_id or agent.user_id != user_id:
            raise ApprovalForbiddenError(agent_id)

    async def _catalog_entry(self, request_id: str):
        catalog = await self._catalog_repo.list_all(request_id)
        return next((e for e in catalog if e.middleware_type is _GATE), None)

    async def _record(self, agent_id: str, request_id: str):
        records = await self._mw_repo.list_by_agent(agent_id, request_id)
        return next((r for r in records if r.middleware_type == _GATE.value), None)
