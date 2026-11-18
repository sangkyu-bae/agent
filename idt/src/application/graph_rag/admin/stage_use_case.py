"""노출 단계 변경 + 이력 (Design §4.2 stage, Plan FR-23).

이력 INSERT 와 설정 UPDATE 는 같은 요청 세션(한 트랜잭션)에서 일어난다.
general 전환은 StageTransitionPolicy 가 RAGAS 근거 또는 강제 사유를 요구한다.
"""

from __future__ import annotations

import dataclasses
import uuid
from datetime import UTC, datetime

from src.domain.graph_rag.interfaces import (
    EvalEvidenceVerifierPort,
    GraphRagSettingsRepositoryPort,
    GraphSettingsReaderPort,
    StageChangeRepositoryPort,
)
from src.domain.graph_rag.policies import StageTransitionPolicy
from src.domain.graph_rag.value_objects import (
    GraphRagSettings,
    RolloutStage,
    StageChange,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class ChangeStageUseCase:
    def __init__(
        self,
        settings_repo: GraphRagSettingsRepositoryPort,
        change_repo: StageChangeRepositoryPort,
        verifier: EvalEvidenceVerifierPort,
        reader: GraphSettingsReaderPort,
        logger: LoggerInterface,
    ) -> None:
        self._settings_repo = settings_repo
        self._change_repo = change_repo
        self._verifier = verifier
        self._reader = reader
        self._logger = logger

    async def change(
        self,
        to_stage: RolloutStage,
        *,
        actor_id: str,
        request_id: str,
        eval_baseline_run_id: str | None = None,
        eval_graph_run_id: str | None = None,
        force_reason: str | None = None,
    ) -> GraphRagSettings:
        current = await self._settings_repo.get(request_id)
        if StageTransitionPolicy.is_noop(current.rollout_stage, to_stage):
            return current
        evidence_ok = await self._evidence_ok(
            to_stage, eval_baseline_run_id, eval_graph_run_id, request_id
        )
        StageTransitionPolicy.validate(
            current.rollout_stage,
            to_stage,
            eval_evidence_ok=evidence_ok,
            force_reason=force_reason,
        )
        await self._change_repo.add(
            StageChange(
                id=str(uuid.uuid4()),
                from_stage=current.rollout_stage,
                to_stage=to_stage,
                changed_by=actor_id,
                eval_baseline_run_id=eval_baseline_run_id,
                eval_graph_run_id=eval_graph_run_id,
                # 근거가 검증되면 사유는 남기지 않는다(강제 전환일 때만 기록).
                force_reason=None
                if evidence_ok
                else ((force_reason or "").strip() or None),
                created_at=datetime.now(UTC),
            ),
            request_id,
        )
        saved = await self._settings_repo.update(
            dataclasses.replace(current, rollout_stage=to_stage), request_id
        )
        self._reader.invalidate()
        return saved

    async def history(self, limit: int, request_id: str) -> list[StageChange]:
        return await self._change_repo.list_recent(limit, request_id)

    async def _evidence_ok(
        self,
        to_stage: RolloutStage,
        baseline: str | None,
        graph: str | None,
        request_id: str,
    ) -> bool:
        if to_stage is not RolloutStage.GENERAL or not (baseline and graph):
            return False
        return await self._verifier.is_valid(baseline, graph, request_id)
