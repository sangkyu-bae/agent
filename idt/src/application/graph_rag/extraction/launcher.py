"""GraphExtractionLauncher — 잡 생성 + 인프로세스 태스크 실행.

Design Ref: graph-rag-foundation §7.2 D8 — SectionSummaryLauncher 선례.
앱 수명 싱글턴. 태스크 참조를 보관해 GC 를 막고, 같은 문서의 중복 실행을 막는다.
재기동하면 진행 중 잡은 끊긴다 → start_graph_rag 에서 failed(interrupted) 처리.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Protocol

from src.domain.graph_rag.extraction import (
    ExtractionJob,
    JobMode,
    JobStatus,
    TriggerSource,
)
from src.domain.graph_rag.interfaces import ExtractionJobStorePort
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class _Runner(Protocol):
    async def run(self, job_id: str, request_id: str) -> None: ...


class GraphExtractionLauncher:
    def __init__(
        self, jobs: ExtractionJobStorePort, runner: _Runner, logger: LoggerInterface
    ) -> None:
        self._jobs = jobs
        self._runner = runner
        self._logger = logger
        self._tasks: set[asyncio.Task] = set()
        self._running_docs: set[str] = set()

    def is_running(self, document_id: str) -> bool:
        return document_id in self._running_docs

    async def launch(
        self,
        *,
        document_id: str,
        kb_id: str | None,
        collection_name: str,
        mode: JobMode,
        trigger: TriggerSource,
        requested_by: str | None,
        request_id: str,
    ) -> ExtractionJob:
        job = await self._jobs.create(
            ExtractionJob(
                id=str(uuid.uuid4()),
                document_id=document_id,
                kb_id=kb_id,
                collection_name=collection_name,
                status=JobStatus.PENDING,
                mode=mode,
                trigger_source=trigger,
                requested_by=requested_by,
            ),
            request_id,
        )
        self._running_docs.add(document_id)
        task = asyncio.create_task(self._run_guarded(job, request_id))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return job

    async def _run_guarded(self, job: ExtractionJob, request_id: str) -> None:
        try:
            await self._runner.run(job.id, request_id)
        except Exception as e:  # noqa: BLE001 — 러너가 이미 기록, 여기는 최후 방어
            self._logger.error(
                "graph extraction task crashed",
                exception=e,
                request_id=request_id,
                job_id=job.id,
            )
        finally:
            self._running_docs.discard(job.document_id)
