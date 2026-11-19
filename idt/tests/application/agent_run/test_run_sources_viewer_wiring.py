"""source-passage-viewer module-3 — RunSourcesService ↔ viewer_enricher 연결 (§11.2 #2, §8.2 #9·10).

- enricher 미주입이면 기존 결과와 완전히 같다
- enricher 결과가 그대로 쓰인다(실시간·재진입 공통 경로)
- enricher 가 예외를 던지면 enrich 전 목록 + warning (두 겹 흡수의 바깥 겹)
"""
import dataclasses
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_run.run_sources import RunSourcesService
from tests.application.agent_run.test_run_sources_service import RUN_ID, _retrieval


def _service(enricher=None):
    runs = MagicMock()
    runs.find_retrievals_by_runs = AsyncMock(return_value={RUN_ID.value: [_retrieval()]})
    runs.find_tool_calls_by_runs = AsyncMock(return_value={})
    documents = MagicMock()
    documents.find_filenames = AsyncMock(return_value={})
    tools = MagicMock()
    tools.list_active = AsyncMock(return_value=[])
    logger = MagicMock()
    kwargs = {} if enricher is None else {"viewer_enricher": enricher}
    return RunSourcesService(runs, documents, tools, logger, max_items=6, **kwargs), logger


@pytest.mark.asyncio
async def test_without_enricher_items_have_no_viewer():
    service, _ = _service()
    (item,) = (await service.build_for_runs([RUN_ID], "req"))[RUN_ID.value]
    assert item.viewer is None
    assert "viewer" not in item.to_payload()


@pytest.mark.asyncio
async def test_enricher_output_is_used():
    async def enrich(items, evidence, request_id):
        assert evidence.retrievals and request_id == "req"
        return [dataclasses.replace(i, viewer={"document_id": "doc-1"}) for i in items]

    enricher = MagicMock()
    enricher.enrich = AsyncMock(side_effect=enrich)
    service, _ = _service(enricher)
    (item,) = (await service.build_for_runs([RUN_ID], "req"))[RUN_ID.value]
    assert item.to_payload()["viewer"] == {"document_id": "doc-1"}


@pytest.mark.asyncio
async def test_enricher_exception_keeps_original_items():
    enricher = MagicMock()
    enricher.enrich = AsyncMock(side_effect=RuntimeError("boom"))
    service, logger = _service(enricher)
    (item,) = (await service.build_for_runs([RUN_ID], "req"))[RUN_ID.value]
    assert item.key == "doc-1" and item.viewer is None
    logger.warning.assert_called()
