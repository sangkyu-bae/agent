"""GraphExtractionLauncher·GraphIngestHook·잡 관리 유스케이스 (Plan FR-04·FR-16)."""
from __future__ import annotations

import asyncio
import dataclasses
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from src.application.graph_rag.admin.jobs_use_case import (
    DocumentNotFoundError,
    ExtractionJobsUseCase,
    GraphJobBusyError,
    GraphModelMissingError,
    GraphUnsupportedDocumentError,
)
from src.application.graph_rag.extraction.launcher import GraphExtractionLauncher
from src.application.graph_rag.hooks import GraphIngestHook
from src.domain.extension_hooks import DocumentIngestedEvent
from src.domain.graph_rag.exceptions import (
    GraphBackendUnavailableError,
    GraphStageOffError,
)
from src.domain.graph_rag.extraction import JobMode, JobStatus, TriggerSource
from src.domain.graph_rag.value_objects import GraphRagSettings, RolloutStage

from tests.application.graph_rag.fakes import FakeReader
from tests.application.graph_rag.test_extraction_use_case import _Jobs, _job


class _Runner:
    def __init__(self):
        self.ran = []
        self.gate = asyncio.Event()

    async def run(self, job_id, request_id):
        self.ran.append(job_id)
        await self.gate.wait()


def _settings(**over):
    base = dataclasses.replace(
        GraphRagSettings.defaults(), rollout_stage=RolloutStage.ADMIN_ONLY,
        extraction_enabled=True, extraction_llm_model_id="m-1",
    )
    return dataclasses.replace(base, **over)


def _launcher(jobs=None, runner=None):
    jobs = jobs or _Jobs(None)
    runner = runner or _Runner()
    return GraphExtractionLauncher(jobs, runner, MagicMock()), jobs, runner


# ── launcher ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_launch_creates_job_and_runs_in_background():
    launcher, jobs, runner = _launcher()
    job = await launcher.launch(
        document_id="doc-1", kb_id="kb-1", collection_name="col",
        mode=JobMode.RESUME, trigger=TriggerSource.UPLOAD, requested_by="1",
        request_id="r",
    )
    assert job.status is JobStatus.PENDING and jobs.job is job
    await asyncio.sleep(0)
    assert runner.ran == [job.id]
    assert launcher.is_running("doc-1")
    runner.gate.set()
    await asyncio.sleep(0.01)
    assert not launcher.is_running("doc-1")


# ── ingest hook ─────────────────────────────────────────────────────────────

class _FakeLauncher:
    def __init__(self, raise_exc=None):
        self.calls = []
        self._raise = raise_exc

    async def launch(self, **kw):
        self.calls.append(kw)
        if self._raise:
            raise self._raise

    def is_running(self, document_id):
        return False


def _event(**over):
    base = dict(document_id="doc-1", kb_id="kb-1", collection_name="col",
                filename="rule.pdf", user_id="7", chunk_count=3, status="completed")
    base.update(over)
    return DocumentIngestedEvent(**base)


@pytest.mark.asyncio
async def test_hook_launches_upload_job_when_enabled():
    launcher = _FakeLauncher()
    await GraphIngestHook(launcher, FakeReader(_settings())).on_document_ingested(
        _event(), "r"
    )
    assert launcher.calls[0]["trigger"] is TriggerSource.UPLOAD
    assert launcher.calls[0]["mode"] is JobMode.RESUME


@pytest.mark.asyncio
@pytest.mark.parametrize("settings, event", [
    (_settings(rollout_stage=RolloutStage.OFF), _event()),
    (_settings(extraction_enabled=False), _event()),
    (_settings(extraction_llm_model_id=None), _event()),
    (_settings(), _event(status="failed")),
    (_settings(), _event(filename="rates.xlsx")),
    (_settings(), _event(chunk_count=0)),
])
async def test_hook_skips(settings, event):
    launcher = _FakeLauncher()
    await GraphIngestHook(launcher, FakeReader(settings)).on_document_ingested(event, "r")
    assert launcher.calls == []


# ── admin jobs use case ─────────────────────────────────────────────────────

class _Docs:
    def __init__(self, docs):
        self.docs = docs

    async def find_by_document_id(self, document_id, request_id):
        return self.docs.get(document_id)


def _jobs_uc(settings=None, *, active=None, store_ok=True, docs=None):
    jobs = _Jobs(_job())
    if active:
        async def _active(document_id, request_id):
            return active
        jobs.find_active = _active
    launcher = _FakeLauncher()
    docs = docs if docs is not None else {
        "doc-1": SimpleNamespace(document_id="doc-1", kb_id="kb-1",
                                 collection_name="col", filename="a.pdf"),
    }
    uc = ExtractionJobsUseCase(
        jobs=jobs, launcher=launcher, reader=FakeReader(settings or _settings()),
        documents=_Docs(docs), store_available=lambda: store_ok, logger=MagicMock(),
    )
    return uc, launcher


@pytest.mark.asyncio
async def test_trigger_admin_extract():
    uc, launcher = _jobs_uc()
    await uc.trigger("doc-1", JobMode.REBUILD, actor_id="99", request_id="r")
    kw = launcher.calls[0]
    assert kw["mode"] is JobMode.REBUILD and kw["trigger"] is TriggerSource.ADMIN
    assert kw["requested_by"] == "99" and kw["collection_name"] == "col"


@pytest.mark.asyncio
async def test_trigger_errors():
    with pytest.raises(GraphStageOffError):
        await _jobs_uc(_settings(rollout_stage=RolloutStage.OFF))[0].trigger(
            "doc-1", JobMode.RESUME, actor_id="1", request_id="r")
    with pytest.raises(GraphModelMissingError):
        await _jobs_uc(_settings(extraction_llm_model_id=None))[0].trigger(
            "doc-1", JobMode.RESUME, actor_id="1", request_id="r")
    with pytest.raises(GraphBackendUnavailableError):
        await _jobs_uc(store_ok=False)[0].trigger(
            "doc-1", JobMode.RESUME, actor_id="1", request_id="r")
    with pytest.raises(DocumentNotFoundError):
        await _jobs_uc(docs={})[0].trigger(
            "doc-1", JobMode.RESUME, actor_id="1", request_id="r")
    with pytest.raises(GraphJobBusyError):
        await _jobs_uc(active=_job())[0].trigger(
            "doc-1", JobMode.RESUME, actor_id="1", request_id="r")


@pytest.mark.asyncio
async def test_trigger_rejects_spreadsheet_documents():
    # 2026-11-17 실추출에서 엑셀이 '값=엔티티' 그래프를 만들어 수동 실행도 막는다
    docs = {"doc-x": SimpleNamespace(document_id="doc-x", kb_id="kb-1",
                                     collection_name="col", filename="거래처.xlsx")}
    uc, launcher = _jobs_uc(docs=docs)
    with pytest.raises(GraphUnsupportedDocumentError):
        await uc.trigger("doc-x", JobMode.REBUILD, actor_id="1", request_id="r")
    assert launcher.calls == []
