"""general 전환 근거 검증 — evaluation_run 2건을 읽어 EvalEvidencePolicy 적용.

Design Ref: graph-rag-foundation §4.2 stage / §11.4 V7(완료 상태 'completed',
실행 설정은 config JSON). module-2 의 자리표시(항상 거절)를 module-7 에서 대체했다.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.graph_rag.eval_evidence import EvalEvidencePolicy, EvalRunFacts
from src.domain.graph_rag.interfaces import EvalEvidenceVerifierPort
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.ragas.models import EvaluationRunModel


def _facts(row: EvaluationRunModel) -> EvalRunFacts:
    config = row.config or {}
    return EvalRunFacts(
        id=row.id,
        status=row.status,
        target_type=row.target_type,
        target_id=row.target_id,
        testset_id=config.get("testset_id"),
        allow_supplemental=bool(config.get("allow_supplemental", False)),
    )


class RagasEvalEvidence(EvalEvidenceVerifierPort):
    def __init__(self, session: AsyncSession, logger: LoggerInterface) -> None:
        self._session = session
        self._logger = logger

    async def is_valid(
        self, baseline_run_id: str | None, graph_run_id: str | None, request_id: str
    ) -> bool:
        ids = [i for i in (baseline_run_id, graph_run_id) if i]
        rows: dict[str, EvalRunFacts] = {}
        if ids:
            result = await self._session.execute(
                select(EvaluationRunModel).where(EvaluationRunModel.id.in_(ids))
            )
            rows = {r.id: _facts(r) for r in result.scalars().all()}
        reason = EvalEvidencePolicy.problem(
            rows.get(baseline_run_id or ""), rows.get(graph_run_id or "")
        )
        self._logger.info(
            "graph stage eval evidence checked",
            request_id=request_id,
            baseline_run_id=baseline_run_id,
            graph_run_id=graph_run_id,
            problem=reason,
        )
        return reason is None
