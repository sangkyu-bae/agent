"""SummarizeSectionsUseCase — 섹션 요약 잡 러너 (card-section-summary Design §6.2).

흐름: 잡 로드/전이 검증 → 모델 확인 → 섹션 조회 → 기완료분 스킵(멱등) →
섹션별 LLM(동시성 제한)→임베딩→저장 → 진행 카운트 → 최종 상태.
DB 접근은 전부 JobStore(호출별 독립 짧은 세션)로 위임하고,
LLM/임베딩 호출은 트랜잭션 밖에서 수행한다 (D11/D12).
"""
import asyncio
from typing import Callable

from src.domain.llm.interfaces import LLMFactoryInterface
from src.domain.llm_model.interfaces import LlmModelRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.section_summary.entities import (
    JOB_STATUS_COMPLETED,
    JOB_STATUS_FAILED,
    JOB_STATUS_PROCESSING,
    SectionCard,
    SectionSummaryJob,
    SectionSummaryRecord,
    SectionSummaryResult,
    summary_id_for,
)
from src.domain.section_summary.interfaces import (
    DocumentSummaryStepInterface,
    SectionSourceInterface,
    SectionSummarizerInterface,
    SectionSummaryJobStoreInterface,
    SummaryWriterInterface,
)
from src.domain.section_summary.policy import SectionSummaryJobPolicy
from src.infrastructure.embeddings.embedding_factory import EmbeddingFactory
from src.infrastructure.section_summary.llm_summarizer import (
    LlmSectionSummarizer,
)


class SummarizeSectionsUseCase:
    def __init__(
        self,
        job_store: SectionSummaryJobStoreInterface,
        section_source: SectionSourceInterface,
        writer: SummaryWriterInterface,
        llm_model_repo: LlmModelRepositoryInterface,
        llm_factory: LLMFactoryInterface,
        embedding_factory: EmbeddingFactory,
        policy: SectionSummaryJobPolicy,
        logger: LoggerInterface,
        concurrency: int = 3,
        input_char_cap: int = 12000,
        max_sections: int = 500,
        summarizer_builder: Callable[..., SectionSummarizerInterface] | None = None,
        document_summary_step: DocumentSummaryStepInterface | None = None,
    ) -> None:
        self._job_store = job_store
        self._section_source = section_source
        self._writer = writer
        self._llm_model_repo = llm_model_repo
        self._llm_factory = llm_factory
        self._embedding_factory = embedding_factory
        self._policy = policy
        self._logger = logger
        self._concurrency = concurrency
        self._max_sections = max_sections
        self._summarizer_builder = summarizer_builder or (
            lambda llm: LlmSectionSummarizer(llm, logger, input_char_cap)
        )
        # None = 문서 요약 체이닝 비활성 — 기존 동작 불변 (document-summary-routing D1)
        self._document_summary_step = document_summary_step

    async def run(self, job_id: str, request_id: str) -> None:
        job = await self._job_store.find_by_id(job_id, request_id)
        if job is None:
            self._logger.error(
                "Section summary job not found",
                request_id=request_id,
                job_id=job_id,
            )
            return
        try:
            self._policy.validate_transition(job.status, JOB_STATUS_PROCESSING)
        except ValueError as e:
            self._logger.warning(
                "Section summary run skipped",
                request_id=request_id,
                job_id=job_id,
                error=str(e),
            )
            return
        await self._job_store.update_status(
            job_id, JOB_STATUS_PROCESSING, None, request_id
        )
        await self._run_processing(job, request_id)

    async def _run_processing(
        self, job: SectionSummaryJob, request_id: str
    ) -> None:
        try:
            failed = await self._execute(job, request_id)
        except Exception as e:
            self._logger.error(
                "Section summary job failed",
                exception=e,
                request_id=request_id,
                job_id=job.id,
                document_id=job.document_id,
            )
            await self._job_store.update_status(
                job.id, JOB_STATUS_FAILED, str(e)[:1000], request_id
            )
            return
        if failed != 0:
            await self._job_store.update_status(
                job.id,
                JOB_STATUS_FAILED,
                f"{failed} section(s) failed",
                request_id,
            )
            return
        if not await self._run_document_summary(job, request_id):
            return
        await self._job_store.update_status(
            job.id, JOB_STATUS_COMPLETED, None, request_id
        )

    async def _run_document_summary(
        self, job: SectionSummaryJob, request_id: str
    ) -> bool:
        """문서 요약 체이닝 (document-summary-routing D1/D3).

        completed = 섹션 전량 + 문서 요약 성공. step 미주입이면 기존 동작 불변.
        """
        if self._document_summary_step is None:
            return True
        try:
            await self._document_summary_step.run(job, request_id)
        except Exception as e:
            self._logger.error(
                "Document summary step failed",
                exception=e,
                request_id=request_id,
                job_id=job.id,
                document_id=job.document_id,
            )
            await self._job_store.update_status(
                job.id,
                JOB_STATUS_FAILED,
                f"document summary failed: {e}"[:1000],
                request_id,
            )
            return False
        return True

    async def _execute(self, job: SectionSummaryJob, request_id: str) -> int:
        """섹션 순회 실행. 반환값 = 실패 섹션 수."""
        model = await self._llm_model_repo.find_by_id(
            job.llm_model_id, request_id
        )
        if model is None or not model.is_active:
            raise ValueError(
                f"summary LLM model unavailable or inactive: {job.llm_model_id}"
            )
        sections = await self._section_source.list_sections(
            job.collection_name, job.document_id, request_id
        )
        if len(sections) > self._max_sections:
            raise ValueError(
                f"sections {len(sections)} exceed cap {self._max_sections}"
            )
        done_refs = await self._section_source.list_done_refs(
            job.collection_name, job.document_id, request_id
        )
        pending = [s for s in sections if s.section_ref not in done_refs]
        await self._job_store.start_progress(
            job.id, len(sections), len(sections) - len(pending), request_id
        )
        if not pending:
            return 0
        return await self._process_all(job, pending, model, request_id)

    async def _process_all(
        self, job: SectionSummaryJob, pending: list[SectionCard], model, request_id: str
    ) -> int:
        llm = self._llm_factory.create(model, 0.0)
        summarizer = self._summarizer_builder(llm)
        embedding = self._embedding_factory.create_from_string(
            provider=job.embedding_provider,
            model_name=job.embedding_model,
        )
        semaphore = asyncio.Semaphore(self._concurrency)
        lock = asyncio.Lock()
        results = await asyncio.gather(
            *[
                self._process_section(
                    job, card, summarizer, embedding, semaphore, lock, request_id
                )
                for card in pending
            ]
        )
        failed = sum(1 for ok in results if not ok)
        self._logger.info(
            "Section summary sections processed",
            request_id=request_id,
            job_id=job.id,
            document_id=job.document_id,
            chunking_profile_id=job.chunking_profile_id,
            llm_model_id=job.llm_model_id,
            processed=len(pending),
            failed=failed,
        )
        return failed

    async def _process_section(
        self,
        job: SectionSummaryJob,
        card: SectionCard,
        summarizer: SectionSummarizerInterface,
        embedding,
        semaphore: asyncio.Semaphore,
        lock: asyncio.Lock,
        request_id: str,
    ) -> bool:
        try:
            async with semaphore:
                raw = await summarizer.summarize(card, request_id)
                clean = self._policy.sanitize_output(
                    raw.keywords, raw.summary_lines
                )
                vector = await embedding.embed_text(
                    f"{card.title}\n{clean.summary_text}"
                )
                record = self._build_record(job, card, clean, vector)
                await self._writer.write(record, request_id)
        except Exception as e:
            self._logger.error(
                "Section summary failed for section",
                exception=e,
                request_id=request_id,
                job_id=job.id,
                section_ref=card.section_ref,
            )
            async with lock:
                await self._job_store.increment_progress(
                    job.id, 0, 1, request_id
                )
            return False
        async with lock:
            await self._job_store.increment_progress(job.id, 1, 0, request_id)
        return True

    @staticmethod
    def _build_record(
        job: SectionSummaryJob,
        card: SectionCard,
        result: SectionSummaryResult,
        vector: list[float],
    ) -> SectionSummaryRecord:
        return SectionSummaryRecord(
            summary_id=summary_id_for(card.section_ref),
            section_ref=card.section_ref,
            document_id=job.document_id,
            collection_name=job.collection_name,
            kb_id=job.kb_id,
            kb_name=card.meta.get("kb_name", ""),
            user_id=card.meta.get("user_id", ""),
            clause_title=card.title,
            chunk_index=card.chunk_index,
            keywords=result.keywords,
            summary_text=result.summary_text,
            vector=vector,
            filename=card.meta.get("filename", ""),
        )
