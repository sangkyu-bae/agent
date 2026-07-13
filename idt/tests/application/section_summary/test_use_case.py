"""SummarizeSectionsUseCase(러너) 테스트 (Design §6.2, D3/D6/D10/D17)."""
from types import SimpleNamespace

import pytest

from src.domain.section_summary.policy import SectionSummaryJobPolicy
from src.application.section_summary.use_case import SummarizeSectionsUseCase

from tests.application.section_summary.conftest import (
    FakeJobStore,
    FakeSectionSource,
    FakeSummarizer,
    FakeWriter,
    make_card,
    make_job,
)


def _runner(
    job_store,
    source,
    writer,
    fakes,
    summarizer,
    llm_model_repo=None,
    max_sections=500,
    document_summary_step=None,
):
    from tests.application.section_summary.conftest import FakeLlmModelRepo

    return SummarizeSectionsUseCase(
        job_store=job_store,
        section_source=source,
        writer=writer,
        llm_model_repo=llm_model_repo or FakeLlmModelRepo(),
        llm_factory=fakes.llm_factory,
        embedding_factory=fakes.embedding_factory,
        policy=SectionSummaryJobPolicy(),
        logger=fakes.logger,
        concurrency=2,
        max_sections=max_sections,
        summarizer_builder=lambda llm: summarizer,
        document_summary_step=document_summary_step,
    )


@pytest.mark.asyncio
async def test_happy_path_completes_job(fakes):
    job_store = FakeJobStore({"job-1": make_job()})
    source = FakeSectionSource([make_card("p1", 0), make_card("p2", 1)])
    writer = FakeWriter()
    summarizer = FakeSummarizer()

    await _runner(job_store, source, writer, fakes, summarizer).run(
        "job-1", "req-1"
    )

    assert job_store.start_calls == [("job-1", 2, 0)]
    assert ("job-1", "processing", None) in job_store.status_calls
    assert job_store.status_calls[-1] == ("job-1", "completed", None)
    assert sorted(job_store.increments) == [("job-1", 1, 0), ("job-1", 1, 0)]
    assert len(writer.records) == 2
    record = writer.records[0]
    assert record.document_id == "doc-1"
    assert record.kb_id == "kb-1"
    assert record.summary_text == "a\nb\nc"


@pytest.mark.asyncio
async def test_partial_failure_isolated_and_job_failed(fakes):
    job_store = FakeJobStore({"job-1": make_job()})
    source = FakeSectionSource([make_card("p1", 0), make_card("p2", 1)])
    writer = FakeWriter()
    summarizer = FakeSummarizer(failing_refs={"p2"})

    await _runner(job_store, source, writer, fakes, summarizer).run(
        "job-1", "req-1"
    )

    assert len(writer.records) == 1
    assert ("job-1", 0, 1) in job_store.increments
    final = job_store.status_calls[-1]
    assert final[1] == "failed"
    assert "1 section(s) failed" in final[2]


@pytest.mark.asyncio
async def test_retry_skips_done_sections(fakes):
    """기완료 섹션은 LLM 재호출 없이 스킵 (D6 멱등)."""
    job_store = FakeJobStore({"job-1": make_job(status="failed")})
    source = FakeSectionSource(
        [make_card("p1", 0), make_card("p2", 1)], done_refs={"p1"}
    )
    writer = FakeWriter()
    summarizer = FakeSummarizer()

    await _runner(job_store, source, writer, fakes, summarizer).run(
        "job-1", "req-1"
    )

    assert summarizer.summarized_refs == ["p2"]
    assert job_store.start_calls == [("job-1", 2, 1)]
    assert job_store.status_calls[-1] == ("job-1", "completed", None)


@pytest.mark.asyncio
async def test_all_done_completes_without_llm(fakes):
    job_store = FakeJobStore({"job-1": make_job(status="failed")})
    source = FakeSectionSource([make_card("p1", 0)], done_refs={"p1"})
    summarizer = FakeSummarizer()

    await _runner(job_store, source, FakeWriter(), fakes, summarizer).run(
        "job-1", "req-1"
    )

    assert summarizer.summarized_refs == []
    assert job_store.status_calls[-1] == ("job-1", "completed", None)


@pytest.mark.asyncio
async def test_max_sections_cap_fails_job(fakes):
    job_store = FakeJobStore({"job-1": make_job()})
    source = FakeSectionSource([make_card(f"p{i}", i) for i in range(3)])
    summarizer = FakeSummarizer()

    await _runner(
        job_store, source, FakeWriter(), fakes, summarizer, max_sections=2
    ).run("job-1", "req-1")

    assert summarizer.summarized_refs == []
    final = job_store.status_calls[-1]
    assert final[1] == "failed"
    assert "exceed cap" in final[2]


@pytest.mark.asyncio
async def test_inactive_model_fails_job(fakes):
    from tests.application.section_summary.conftest import FakeLlmModelRepo

    job_store = FakeJobStore({"job-1": make_job()})
    repo = FakeLlmModelRepo(SimpleNamespace(id="model-1", is_active=False))

    await _runner(
        job_store,
        FakeSectionSource([make_card("p1")]),
        FakeWriter(),
        fakes,
        FakeSummarizer(),
        llm_model_repo=repo,
    ).run("job-1", "req-1")

    final = job_store.status_calls[-1]
    assert final[1] == "failed"
    assert "unavailable" in final[2]


@pytest.mark.asyncio
async def test_document_summary_chained_after_sections(fakes):
    """섹션 전량 성공 → 문서 요약 단계 실행 → completed (document-summary-routing D1)."""
    from tests.application.section_summary.conftest import (
        FakeDocumentSummaryStep,
    )

    job_store = FakeJobStore({"job-1": make_job()})
    step = FakeDocumentSummaryStep()

    await _runner(
        job_store,
        FakeSectionSource([make_card("p1", 0)]),
        FakeWriter(),
        fakes,
        FakeSummarizer(),
        document_summary_step=step,
    ).run("job-1", "req-1")

    assert step.run_jobs == ["job-1"]
    assert job_store.status_calls[-1] == ("job-1", "completed", None)


@pytest.mark.asyncio
async def test_document_summary_failure_fails_job(fakes):
    from tests.application.section_summary.conftest import (
        FakeDocumentSummaryStep,
    )

    job_store = FakeJobStore({"job-1": make_job()})
    step = FakeDocumentSummaryStep(error=RuntimeError("boom"))

    await _runner(
        job_store,
        FakeSectionSource([make_card("p1", 0)]),
        FakeWriter(),
        fakes,
        FakeSummarizer(),
        document_summary_step=step,
    ).run("job-1", "req-1")

    final = job_store.status_calls[-1]
    assert final[1] == "failed"
    assert final[2].startswith("document summary failed:")


@pytest.mark.asyncio
async def test_document_summary_not_run_when_sections_failed(fakes):
    from tests.application.section_summary.conftest import (
        FakeDocumentSummaryStep,
    )

    job_store = FakeJobStore({"job-1": make_job()})
    step = FakeDocumentSummaryStep()

    await _runner(
        job_store,
        FakeSectionSource([make_card("p1", 0)]),
        FakeWriter(),
        fakes,
        FakeSummarizer(failing_refs={"p1"}),
        document_summary_step=step,
    ).run("job-1", "req-1")

    assert step.run_jobs == []
    assert job_store.status_calls[-1][1] == "failed"


@pytest.mark.asyncio
async def test_retry_regenerates_document_summary_without_section_llm(fakes):
    """재시도: 전 섹션 done → 섹션 LLM 0회 + 문서 요약만 재생성 (D4)."""
    from tests.application.section_summary.conftest import (
        FakeDocumentSummaryStep,
    )

    job_store = FakeJobStore({"job-1": make_job(status="failed")})
    step = FakeDocumentSummaryStep()
    summarizer = FakeSummarizer()

    await _runner(
        job_store,
        FakeSectionSource([make_card("p1", 0)], done_refs={"p1"}),
        FakeWriter(),
        fakes,
        summarizer,
        document_summary_step=step,
    ).run("job-1", "req-1")

    assert summarizer.summarized_refs == []
    assert step.run_jobs == ["job-1"]
    assert job_store.status_calls[-1] == ("job-1", "completed", None)


@pytest.mark.asyncio
async def test_completed_job_is_not_rerun(fakes):
    job_store = FakeJobStore({"job-1": make_job(status="completed")})

    await _runner(
        job_store,
        FakeSectionSource([make_card("p1")]),
        FakeWriter(),
        fakes,
        FakeSummarizer(),
    ).run("job-1", "req-1")

    assert job_store.status_calls == []
