"""SessionScopedToolAccessChecker — 세션이 없는 싱글턴용 단건 도구 권한 판정.

Design Ref: tool-access-control §0 F4 — 승인 집행(decide·예약 집행)은 compile 을 거치지
않고 CompositeActionExecutor 로 도구를 직접 실행한다. 집행기는 앱 싱글턴이라 요청 세션이
없으므로 판정마다 세션을 연다. 승인 대기 중 권한이 회수됐으면 집행하지 않는다.

예외를 던지지 않는다 — 판정 실패는 False(Fail-Closed). 집행 실패는 정상 흐름의
한 갈래(blocked → failed 전이)다.
"""
from collections.abc import Callable

from src.application.tool_access.resolver import ToolAccessResolver
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class SessionScopedToolAccessChecker:
    def __init__(
        self,
        session_factory,
        resolver_factory: Callable[[object], ToolAccessResolver],
        logger: LoggerInterface,
    ) -> None:
        self._session_factory = session_factory
        self._resolver_factory = resolver_factory
        self._logger = logger

    async def is_allowed(
        self, subject_user_id: str | None, tool_id: str, request_id: str
    ) -> bool:
        try:
            async with self._session_factory() as session:
                resolver = self._resolver_factory(session)
                access = await resolver.for_user_id(subject_user_id, request_id)
            allowed = access.allows_reference(tool_id)
        except Exception as e:
            self._logger.error(
                "tool access check failed — treated as denied",
                exception=e, request_id=request_id, tool_id=tool_id,
            )
            return False
        if not allowed:
            self._logger.warning(
                "tool access denied at execution",
                request_id=request_id, tool_id=tool_id,
                subject_user_id=subject_user_id,
            )
        return allowed
