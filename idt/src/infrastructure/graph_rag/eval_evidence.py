"""general 전환 근거 검증 — module-2 자리표시 구현.

Design Ref: graph-rag-foundation §4.2 stage / §11.4 V7 — RAGAS 실행 테이블·완료 상태
확인은 module-7 에서 구현한다. 그 전까지는 근거를 인정하지 않아 general 전환은
강제 사유 경로로만 가능하다(기본은 닫힘).
"""

from __future__ import annotations

from src.domain.graph_rag.interfaces import EvalEvidenceVerifierPort
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class UnverifiedEvalEvidence(EvalEvidenceVerifierPort):
    def __init__(self, logger: LoggerInterface) -> None:
        self._logger = logger

    async def is_valid(
        self, baseline_run_id: str | None, graph_run_id: str | None, request_id: str
    ) -> bool:
        self._logger.info(
            "RAGAS evidence verification not implemented yet (module-7) — rejected",
            request_id=request_id,
            baseline_run_id=baseline_run_id,
            graph_run_id=graph_run_id,
        )
        return False
