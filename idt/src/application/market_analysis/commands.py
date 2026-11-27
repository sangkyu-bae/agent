"""운영자 명령 — 설정 · 자동 분석 스위치 · 역할
매핑 · 지금 실행 (module-8, manage 권한).

Design Ref: stock-analysis-agents §5.1 · §5.2 · §5.3, Plan FR-01 · FR-02.
- 설정: 값 범위(SettingValidationPolicy)
→ 가리키는 서버·사용자가 쓸 수 있는지(플랫폼 조회)
  → 저장. 실패는 필드별 사유를 담은 InvalidSettingError(422 MA_INVALID_SETTING)
- 스위치를 켜려면 KIS 서버와 실행 사용자가 설정돼
있어야 한다 — 켜 두고 회차마다 failed 가
  나는 상태를 만들지 않는다
- 역할 매핑: 에이전트가 있고 삭제되지 않았는지 확인(422 MA_ROLE_AGENT_INVALID)
- 지금 실행: 스케줄러의 수동 회차(trigger=manual). 실행 중이면 RoundBusyError(409)
"""

from __future__ import annotations

from dataclasses import replace

from src.application.market_analysis.ports import (
    ReferenceChecker,
    RoleAgentStore,
    SettingReader,
    SettingWriter,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.market_analysis.setting import MarketAnalysisSetting
from src.domain.market_analysis.setting_validation import SettingValidationPolicy
from src.domain.market_analysis.value_objects import AgentRole, RoundKind

_SERVER_FIELDS = ("kis_server_id", "dart_server_id", "perplexity_server_id")


class InvalidSettingError(ValueError):
    def __init__(self, errors: dict[str, str]) -> None:
        super().__init__(", ".join(f"{k}: {v}" for k, v in errors.items()))
        self.errors = errors


class RoleAgentInvalidError(ValueError):
    def __init__(self, roles: list[str]) -> None:
        super().__init__(", ".join(roles))
        self.roles = roles


class RoundBusyError(RuntimeError):
    pass


def _needs_for_enabled(setting: MarketAnalysisSetting) -> dict[str, str]:
    errors: dict[str, str] = {}
    if setting.enabled and not setting.kis_server_id:
        errors["kis_server_id"] = "자동 분석을 켜려면 KIS 서버를 지정해야 합니다"
    if setting.enabled and not setting.run_as_user_id:
        errors["run_as_user_id"] = "자동 분석을 켜려면 실행 사용자를 지정해야 합니다"
    return errors


class UpdateSettingsUseCase:
    """설정 저장. 자동 분석 스위치는 바꾸지 않는다 — 스위치는 SetEnabledUseCase 만.
    오래 열어 둔 폼의 enabled 가 다른 곳에서 바꾼 스위치를 덮어쓰지 않게 한다 (G9)."""

    def __init__(
        self,
        *,
        reader: SettingReader,
        writer: SettingWriter,
        checker: ReferenceChecker,
        logger: LoggerInterface,
    ) -> None:
        self._reader = reader
        self._writer = writer
        self._checker = checker
        self._logger = logger

    async def execute(
        self, setting: MarketAnalysisSetting, *, updated_by: str, request_id: str
    ) -> MarketAnalysisSetting:
        current = await self._reader.get(request_id)
        setting = replace(setting, enabled=current.enabled)
        errors = SettingValidationPolicy.validate(setting)
        errors.update(_needs_for_enabled(setting))
        for field in _SERVER_FIELDS:
            server_id = getattr(setting, field)
            if server_id and field not in errors:
                if not await self._checker.mcp_server_active(server_id, request_id):
                    errors[field] = "등록된 활성 MCP 서버가 아닙니다"
        if setting.run_as_user_id and "run_as_user_id" not in errors:
            if not await self._checker.user_active(setting.run_as_user_id, request_id):
                errors["run_as_user_id"] = "활성 사용자가 아닙니다"
        if errors:
            raise InvalidSettingError(errors)
        await self._writer.save(setting, updated_by=updated_by, request_id=request_id)
        self._logger.info(
            "market_analysis settings updated",
            request_id=request_id,
            updated_by=updated_by,
            enabled=setting.enabled,
        )
        return setting


class SetEnabledUseCase:
    """자동 분석 스위치만 (Plan FR-01). 끄는 것은 항상 된다."""

    def __init__(
        self,
        *,
        reader: SettingReader,
        writer: SettingWriter,
        logger: LoggerInterface,
    ) -> None:
        self._reader = reader
        self._writer = writer
        self._logger = logger

    async def execute(
        self, enabled: bool, *, updated_by: str, request_id: str
    ) -> MarketAnalysisSetting:
        current = await self._reader.get(request_id)
        updated = replace(current, enabled=enabled)
        errors = _needs_for_enabled(updated)
        if errors:
            raise InvalidSettingError(errors)
        await self._writer.save(updated, updated_by=updated_by, request_id=request_id)
        self._logger.info(
            "market_analysis switch changed",
            request_id=request_id,
            updated_by=updated_by,
            enabled=enabled,
        )
        return updated


class SetRoleAgentsUseCase:
    def __init__(
        self,
        *,
        roles: RoleAgentStore,
        checker: ReferenceChecker,
        logger: LoggerInterface,
    ) -> None:
        self._roles = roles
        self._checker = checker
        self._logger = logger

    async def execute(
        self, mapping: dict[AgentRole, str], *, updated_by: str, request_id: str
    ) -> dict[AgentRole, str]:
        invalid = [
            role.value
            for role, agent_id in mapping.items()
            if not agent_id
            or not await self._checker.agent_usable(agent_id, request_id)
        ]
        if invalid:
            raise RoleAgentInvalidError(invalid)
        for role, agent_id in mapping.items():
            await self._roles.set(
                role=role,
                agent_id=agent_id,
                updated_by=updated_by,
                request_id=request_id,
            )
        return await self._roles.get_all(request_id)


class RunNowUseCase:
    """수동 회차 — 자동 스위치와 무관, 상한은 적용 (§5.1)."""

    def __init__(self, *, scheduler: object, logger: LoggerInterface) -> None:
        self._scheduler = scheduler
        self._logger = logger

    async def execute(
        self, kind: RoundKind, *, requested_by: str, request_id: str
    ) -> int:
        round_id = await self._scheduler.run_now(kind, request_id)  # type: ignore[attr-defined]
        if round_id is None:
            raise RoundBusyError()
        self._logger.info(
            "market_analysis manual round started",
            request_id=request_id,
            round_id=round_id,
            requested_by=requested_by,
        )
        return int(round_id)
