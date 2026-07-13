"""section_summary application 테스트 공용 페이크."""
from types import SimpleNamespace

import pytest

from src.domain.section_summary.entities import (
    SectionCard,
    SectionSummaryJob,
    SectionSummaryResult,
)


class FakeLogger:
    def debug(self, *a, **k): ...
    def info(self, *a, **k): ...
    def warning(self, *a, **k): ...
    def error(self, *a, **k): ...
    def critical(self, *a, **k): ...


class FakeJobStore:
    def __init__(self, jobs: dict[str, SectionSummaryJob] | None = None):
        self.jobs = jobs or {}
        self.status_calls: list[tuple] = []
        self.start_calls: list[tuple] = []
        self.increments: list[tuple] = []
        self.created: list[SectionSummaryJob] = []
        self.create_error: Exception | None = None

    async def create(self, job, request_id):
        if self.create_error is not None:
            raise self.create_error
        self.jobs[job.id] = job
        self.created.append(job)
        return job

    async def find_by_id(self, job_id, request_id):
        return self.jobs.get(job_id)

    async def find_by_document(self, document_id, request_id):
        for job in self.jobs.values():
            if job.document_id == document_id:
                return job
        return None

    async def update_status(self, job_id, status, error, request_id):
        self.status_calls.append((job_id, status, error))
        job = self.jobs.get(job_id)
        if job is not None:
            job.status = status
            job.error = error

    async def start_progress(self, job_id, total, done, request_id):
        self.start_calls.append((job_id, total, done))

    async def increment_progress(self, job_id, done_delta, failed_delta, request_id):
        self.increments.append((job_id, done_delta, failed_delta))


class FakeSectionSource:
    def __init__(self, sections=None, done_refs=None):
        self.sections = sections or []
        self.done_refs = done_refs or set()

    async def list_sections(self, collection_name, document_id, request_id):
        return self.sections

    async def list_done_refs(self, collection_name, document_id, request_id):
        return self.done_refs


class FakeSummarizer:
    def __init__(self, failing_refs: set[str] | None = None):
        self.failing_refs = failing_refs or set()
        self.summarized_refs: list[str] = []

    async def summarize(self, card, request_id):
        self.summarized_refs.append(card.section_ref)
        if card.section_ref in self.failing_refs:
            raise RuntimeError(f"boom: {card.section_ref}")
        return SectionSummaryResult(
            keywords=["kw"], summary_lines=["a", "b", "c"]
        )


class FakeDocumentSummaryStep:
    """문서 요약 단계 페이크 (document-summary-routing D1/D2)."""

    def __init__(self, error: Exception | None = None):
        self.error = error
        self.run_jobs: list[str] = []

    async def run(self, job, request_id):
        self.run_jobs.append(job.id)
        if self.error is not None:
            raise self.error


class FakeWriter:
    def __init__(self):
        self.records = []

    async def write(self, record, request_id):
        self.records.append(record)


class FakeEmbedding:
    async def embed_text(self, text):
        return [0.1, 0.2]


class FakeEmbeddingFactory:
    def create_from_string(self, provider, model_name):
        return FakeEmbedding()


class FakeLlmModelRepo:
    def __init__(self, model=None):
        self.model = (
            model
            if model is not None
            else SimpleNamespace(id="model-1", is_active=True)
        )

    async def find_by_id(self, model_id, request_id):
        return self.model


class FakeLlmFactory:
    def create(self, llm_model, temperature=0.0):
        return object()


def make_job(**overrides) -> SectionSummaryJob:
    values = dict(
        id="job-1",
        document_id="doc-1",
        kb_id="kb-1",
        collection_name="col",
        chunking_profile_id="prof-1",
        llm_model_id="model-1",
        embedding_provider="openai",
        embedding_model="text-embedding-3-small",
        status="pending",
    )
    values.update(overrides)
    return SectionSummaryJob(**values)


def make_card(ref: str, index: int = 0) -> SectionCard:
    return SectionCard(
        section_ref=ref,
        title=f"제{index + 1}조",
        text=f"본문 {ref}",
        chunk_index=index,
        meta={"user_id": "7", "kb_name": "여신규정", "filename": "rule.pdf"},
    )


@pytest.fixture
def fakes():
    return SimpleNamespace(
        logger=FakeLogger(),
        embedding_factory=FakeEmbeddingFactory(),
        llm_factory=FakeLlmFactory(),
    )
