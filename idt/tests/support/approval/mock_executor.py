"""MockActionExecutor — 테스트 더블.

approval-gate Phase 1 에서는 프로덕션 폴백 집행기였다. `supports()` 가 항상
True 라 집행기 없는 도구까지 "executed" 로 기록하는 가짜 성공을 만들었고,
approval-gate-phase2 (D-06) 에서 src 밖으로 옮겼다. 프로덕션 배선에 다시
꽂지 않는다 — tests/application/approval/test_executor_wiring.py 가 막는다.

실제 부작용 없이 게이트·승인·예약·재개 흐름을 검증할 때만 쓴다.
"""
from src.domain.approval.interfaces import ActionExecutorInterface, ExecutionResult
from src.domain.logging.interfaces.logger_interface import LoggerInterface

# 집행 실패를 E2E 로 검증하기 위한 예약 도구 id — 실제 도구와 충돌하지 않도록
# 접두어를 붙인다.
FAILING_TOOL_ID = "mock:always_fail"


class MockActionExecutor(ActionExecutorInterface):
    """모든 도구를 받아 로그만 남기고 성공을 반환한다.

    `supports` 가 항상 True 다 — 테스트에서 어떤 tool_id 든 받기 위해서다.
    """

    def __init__(self, logger: LoggerInterface) -> None:
        self._logger = logger

    def supports(self, tool_id: str) -> bool:
        return True

    async def execute(
        self,
        *,
        tool_id: str,
        tool_args: dict,
        request_id: str,
        idempotency_key: str | None = None,
    ) -> ExecutionResult:
        if tool_id == FAILING_TOOL_ID:
            self._logger.warning(
                "MockActionExecutor forced failure",
                request_id=request_id,
                tool_id=tool_id,
            )
            return ExecutionResult(
                ok=False,
                output="",
                error_message="mock executor forced failure",
            )
        self._logger.info(
            "MockActionExecutor executed",
            request_id=request_id,
            tool_id=tool_id,
            arg_keys=sorted(tool_args),
        )
        return ExecutionResult(
            ok=True,
            output=f"[mock] {tool_id} 집행 완료 (실제 부작용 없음)",
        )
