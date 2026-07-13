"""SectionSummaryLauncher — 잡 생성 + 인프로세스 태스크 킥오프 (Design D11).

애플리케이션 싱글턴. 잡 INSERT는 JobStore(독립 짧은 세션)로 수행하고
asyncio.create_task로 러너를 백그라운드 실행한다. launch 실패는 warning 후
None 반환 — 업로드 결과에 절대 영향을 주지 않는다 (FR-09).
"""
import asyncio
import uuid
from typing import Awaitable, Callable

from src.application.section_summary.schemas import (
    SectionSummaryLaunchInfo,
    SectionSummaryLaunchInput,
    SectionSummaryRetryNotAllowedError,
)
from src.application.section_summary.use_case import SummarizeSectionsUseCase
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.section_summary.entities import (
    JOB_STATUS_PENDING,
    SectionSummaryJob,
)
from src.domain.section_summary.interfaces import (
    SectionSummaryJobStoreInterface,
)

_DEFAULT_EMBEDDING_PROVIDER = "openai"

# (embedding_model_name, request_id) -> provider | None
EmbeddingProviderResolver = Callable[[str, str], Awaitable[str | None]]


class SectionSummaryLauncher:
    def __init__(
        self,
        job_store: SectionSummaryJobStoreInterface,
        runner: SummarizeSectionsUseCase,
        logger: LoggerInterface,
        embedding_provider_resolver: EmbeddingProviderResolver | None = None,
    ) -> None:
        self._job_store = job_store
        self._runner = runner
        self._logger = logger
        self._resolve_provider_fn = embedding_provider_resolver
        # create_task 참조 보관(GC 방지) + 동일 잡 중복 실행 차단
        self._tasks: set[asyncio.Task] = set()
        self._active_jobs: set[str] = set()

    async def launch(
        self, launch_input: SectionSummaryLaunchInput, request_id: str
    ) -> SectionSummaryLaunchInfo | None:
        try:
            provider = await self._resolve_provider(
                launch_input.embedding_model_name, request_id
            )
            job = SectionSummaryJob(
                id=str(uuid.uuid4()),
                document_id=launch_input.document_id,
                kb_id=launch_input.kb_id,
                collection_name=launch_input.collection_name,
                chunking_profile_id=launch_input.profile_id,
                llm_model_id=launch_input.llm_model_id,
                embedding_provider=provider,
                embedding_model=launch_input.embedding_model_name,
                status=JOB_STATUS_PENDING,
            )
            saved = await self._job_store.create(job, request_id)
            self._spawn(saved.id, request_id)
            self._logger.info(
                "Section summary job launched",
                request_id=request_id,
                job_id=saved.id,
                document_id=launch_input.document_id,
                chunking_profile_id=launch_input.profile_id,
                llm_model_id=launch_input.llm_model_id,
            )
            return SectionSummaryLaunchInfo(
                job_id=saved.id, status=JOB_STATUS_PENDING
            )
        except Exception as e:
            self._logger.warning(
                "Section summary launch failed (upload unaffected)",
                request_id=request_id,
                document_id=launch_input.document_id,
                error=str(e),
            )
            return None

    async def retry(self, job_id: str, request_id: str) -> None:
        """재시도 킥오프 — 상태 전이는 러너가 검증·수행한다 (D4)."""
        if job_id in self._active_jobs:
            raise SectionSummaryRetryNotAllowedError(
                "section summary job is already running"
            )
        self._spawn(job_id, request_id)

    def _spawn(self, job_id: str, request_id: str) -> None:
        self._active_jobs.add(job_id)
        task = asyncio.create_task(self._run_guarded(job_id, request_id))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run_guarded(self, job_id: str, request_id: str) -> None:
        try:
            await self._runner.run(job_id, request_id)
        except Exception as e:
            self._logger.error(
                "Section summary task crashed",
                exception=e,
                request_id=request_id,
                job_id=job_id,
            )
        finally:
            self._active_jobs.discard(job_id)

    async def _resolve_provider(
        self, embedding_model_name: str, request_id: str
    ) -> str:
        if self._resolve_provider_fn is None:
            return _DEFAULT_EMBEDDING_PROVIDER
        try:
            provider = await self._resolve_provider_fn(
                embedding_model_name, request_id
            )
        except Exception as e:
            self._logger.warning(
                "Embedding provider resolution failed, defaulting",
                request_id=request_id,
                embedding_model=embedding_model_name,
                error=str(e),
            )
            return _DEFAULT_EMBEDDING_PROVIDER
        return provider or _DEFAULT_EMBEDDING_PROVIDER
