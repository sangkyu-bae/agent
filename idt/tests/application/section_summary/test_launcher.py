"""SectionSummaryLauncher 테스트 (Design D11, FR-09)."""
import asyncio

import pytest

from src.application.section_summary.launcher import SectionSummaryLauncher
from src.application.section_summary.schemas import (
    SectionSummaryLaunchInput,
    SectionSummaryRetryNotAllowedError,
)

from tests.application.section_summary.conftest import FakeJobStore, FakeLogger


class _RecordingRunner:
    def __init__(self, gate: asyncio.Event | None = None):
        self.runs: list[str] = []
        self._gate = gate

    async def run(self, job_id, request_id):
        self.runs.append(job_id)
        if self._gate is not None:
            await self._gate.wait()


def _launch_input() -> SectionSummaryLaunchInput:
    return SectionSummaryLaunchInput(
        document_id="doc-1",
        kb_id="kb-1",
        collection_name="col",
        profile_id="prof-1",
        llm_model_id="model-1",
        embedding_model_name="text-embedding-3-small",
    )


@pytest.mark.asyncio
async def test_launch_creates_job_and_runs_task():
    job_store = FakeJobStore()
    runner = _RecordingRunner()
    launcher = SectionSummaryLauncher(job_store, runner, FakeLogger())

    info = await launcher.launch(_launch_input(), "req-1")

    assert info is not None
    assert info.status == "pending"
    created = job_store.created[0]
    assert created.document_id == "doc-1"
    assert created.llm_model_id == "model-1"
    assert created.embedding_provider == "openai"

    await asyncio.sleep(0)
    assert runner.runs == [info.job_id]


@pytest.mark.asyncio
async def test_launch_failure_returns_none_without_raising():
    """잡 생성 실패가 업로드 흐름으로 전파되지 않는다 (FR-09)."""
    job_store = FakeJobStore()
    job_store.create_error = RuntimeError("db down")
    launcher = SectionSummaryLauncher(
        job_store, _RecordingRunner(), FakeLogger()
    )

    info = await launcher.launch(_launch_input(), "req-1")

    assert info is None


@pytest.mark.asyncio
async def test_provider_resolver_used_and_fallback_on_error():
    async def resolver(model_name, request_id):
        return "custom-provider"

    job_store = FakeJobStore()
    launcher = SectionSummaryLauncher(
        job_store,
        _RecordingRunner(),
        FakeLogger(),
        embedding_provider_resolver=resolver,
    )
    await launcher.launch(_launch_input(), "req-1")
    assert job_store.created[0].embedding_provider == "custom-provider"

    async def broken(model_name, request_id):
        raise RuntimeError("no repo")

    job_store2 = FakeJobStore()
    launcher2 = SectionSummaryLauncher(
        job_store2,
        _RecordingRunner(),
        FakeLogger(),
        embedding_provider_resolver=broken,
    )
    await launcher2.launch(_launch_input(), "req-1")
    assert job_store2.created[0].embedding_provider == "openai"


@pytest.mark.asyncio
async def test_retry_rejected_while_job_is_running():
    gate = asyncio.Event()
    runner = _RecordingRunner(gate)
    launcher = SectionSummaryLauncher(FakeJobStore(), runner, FakeLogger())

    info = await launcher.launch(_launch_input(), "req-1")
    await asyncio.sleep(0)  # task 시작

    with pytest.raises(SectionSummaryRetryNotAllowedError):
        await launcher.retry(info.job_id, "req-2")

    gate.set()
    await asyncio.sleep(0)
    await asyncio.sleep(0)  # task 종료 대기

    await launcher.retry(info.job_id, "req-3")
    await asyncio.sleep(0)
    assert runner.runs.count(info.job_id) == 2
