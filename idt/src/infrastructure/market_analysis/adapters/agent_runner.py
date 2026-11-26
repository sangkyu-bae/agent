"""빌더 에이전트 1회 실행 어댑터 (application.ports.AgentRunner 구현).

Design Ref: stock-analysis-agents §4 ①, DD5 ·
O4(확인: persist_conversation=False 여도 ai_run 은 남는다).
백그라운드 워커 `_run_agent` 와 같은 방식이다
— 실행마다 새 세션, 실행자 auth_ctx 재조립.

- `session_id=None`: 이전 대화를 불러오지 않는다 (섹션마다 독립 실행)
- `persist_conversation=False`: 대화
이력을 남기지 않는다. 실행 기록(ai_run·토큰·비용)은 남는다
- `reference_context`: 코어 opt-in 필드. 이 파일이 유일한 호출자다 (tests/contracts)
- 실패는 예외가 아니라 `AgentRunOutcome(failed=True)` 로 돌려준다
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import Any

from pydantic import ValidationError

from src.application.agent_builder.schemas import RunAgentRequest
from src.domain.agent_run.value_objects import RunId
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.market_analysis.runtime import AgentRunOutcome
from src.infrastructure.persistence.repositories.agent_run_repository import (
    SqlAlchemyAgentRunRepository,
)

_QUERY_MAX = 2000  # RunAgentRequest.query 상한
_CONTEXT_MAX = 40_000  # RunAgentRequest.reference_context 상한

UsageReader = Callable[[str], Awaitable[tuple[int, Decimal]]]


def _failed(error: str) -> AgentRunOutcome:
    return AgentRunOutcome(answer="", run_id=None, failed=True, error=error)


class PlatformAgentRunner:
    def __init__(
        self,
        *,
        session_factory: Callable[[], Any],
        run_uc_builder: Callable[[Any], Any],
        auth_ctx_assembler: Callable[[str, str], Awaitable[Any]],
        logger: LoggerInterface,
        usage_reader: UsageReader | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._builder = run_uc_builder
        self._assemble = auth_ctx_assembler
        self._logger = logger
        self._usage_reader = usage_reader or self._read_usage

    async def run(
        self,
        *,
        agent_id: str,
        query: str,
        reference_context: str | None,
        run_as_user_id: str,
        request_id: str,
    ) -> AgentRunOutcome:
        if len(query) > _QUERY_MAX:
            return _failed("QUERY_TOO_LONG")
        if reference_context is not None and len(reference_context) > _CONTEXT_MAX:
            return _failed("CONTEXT_TOO_LONG")
        # 중간 점검 I2: 포트는 예외를 던지지 않는다 — 인증 조립 실패도 값으로 돌려준다
        try:
            ctx = await self._assemble(run_as_user_id, request_id)
        except Exception as e:  # noqa: BLE001
            self._logger.warning(
                "market_analysis auth context failed",
                exception=e,
                request_id=request_id,
            )
            return _failed(f"AUTH_CONTEXT_FAILED: {str(e)[:300]}")
        if ctx is None:
            return _failed("RUN_AS_USER_INVALID")
        try:
            request = RunAgentRequest(
                query=query,
                user_id=run_as_user_id,
                session_id=None,
                persist_conversation=False,
                reference_context=reference_context,
            )
        except ValidationError as e:
            return _failed(f"REQUEST_INVALID: {str(e)[:300]}")
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    response = await self._builder(session).execute(
                        agent_id,
                        request,
                        request_id,
                        viewer_user_id=run_as_user_id,
                        viewer_department_ids=list(
                            getattr(ctx, "department_ids", []) or []
                        ),
                        auth_ctx=ctx,
                    )
        except Exception as e:  # noqa: BLE001 — 섹션 1개 실패가 회차를 멈추면 안 된다
            self._logger.warning(
                "market_analysis agent run failed",
                exception=e,
                request_id=request_id,
                agent_id=agent_id,
            )
            return AgentRunOutcome(
                answer="", run_id=None, failed=True, error=f"RUN_FAILED: {str(e)[:300]}"
            )

        tokens, cost = 0, Decimal("0")
        if response.run_id:
            try:
                tokens, cost = await self._usage_reader(response.run_id)
            except Exception as e:  # noqa: BLE001 — 비용 조회 실패는 답변을 버리지 않는다
                self._logger.warning(
                    "market_analysis usage read failed",
                    exception=e,
                    request_id=request_id,
                    run_id=response.run_id,
                )
        return AgentRunOutcome(
            answer=response.answer or "",
            run_id=response.run_id,
            tokens=tokens,
            cost_usd=cost,
        )

    async def _read_usage(self, run_id: str) -> tuple[int, Decimal]:
        async with self._session_factory() as session:
            run = await SqlAlchemyAgentRunRepository(session).find_run(RunId(run_id))
        if run is None:
            return 0, Decimal("0")
        return run.token_usage.total_tokens, Decimal(str(run.cost_usd.total_usd))
