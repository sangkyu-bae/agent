"""CompositeActionExecutor — 집행기 디스패치.

Design Ref: approval-gate-phase2-mcp-executor §2.1, §6.1.

Phase 1 은 `supports()` 가 항상 True 인 Mock 을 폴백으로 뒀고, 그 결과
집행기가 없는 도구도 "executed" 로 기록됐다. 여기서는 받을 집행기가 없으면
실패를 돌려준다 — executed 로 가는 길이 없어야 한다 (Plan SC-2).
"""
from collections.abc import Sequence

from src.domain.approval.execution_policy import (
    ExecutionFailureKind,
    ExecutionFailurePolicy,
)
from src.domain.approval.interfaces import ActionExecutorInterface, ExecutionResult
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class CompositeActionExecutor(ActionExecutorInterface):
    """등록 순서대로 `supports()` 첫 매치에 위임한다."""

    def __init__(
        self,
        *,
        executors: Sequence[ActionExecutorInterface],
        logger: LoggerInterface,
    ) -> None:
        self._executors = tuple(executors)
        self._logger = logger

    def supports(self, tool_id: str) -> bool:
        return self._find(tool_id) is not None

    async def execute(
        self,
        *,
        tool_id: str,
        tool_args: dict,
        request_id: str,
        idempotency_key: str | None = None,
        subject_user_id: str | None = None,
    ) -> ExecutionResult:
        executor = self._find(tool_id)
        if executor is None:
            self._logger.warning(
                "no action executor for tool", request_id=request_id, tool_id=tool_id
            )
            return self._failure("blocked", f"지원 집행기 없음: {tool_id}")
        try:
            return await executor.execute(
                tool_id=tool_id, tool_args=tool_args, request_id=request_id,
                idempotency_key=idempotency_key, subject_user_id=subject_user_id,
            )
        except Exception as e:
            # 집행기는 예외를 던지지 않는 계약이다. 어겼다면 집행 도중이었을
            # 수 있으므로 불명으로 기록한다. str(e) 는 문구에 넣지 않는다 (D-11).
            self._logger.error(
                "action executor raised", exception=e,
                request_id=request_id, tool_id=tool_id,
            )
            return self._failure("unknown", f"집행기 오류 ({type(e).__name__})")

    def _find(self, tool_id: str) -> ActionExecutorInterface | None:
        for executor in self._executors:
            if executor.supports(tool_id):
                return executor
        return None

    @staticmethod
    def _failure(kind: ExecutionFailureKind, reason: str) -> ExecutionResult:
        return ExecutionResult(
            ok=False, output="",
            error_message=ExecutionFailurePolicy.render(kind, reason),
        )
