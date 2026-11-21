"""RunSourcesService ↔ citation_enricher 이음매 S9 (answer-citation-verification §9.2).

- 미주입이면 기존 결과와 같다(payload 에 citation 키 없음)
- 실행 묶음당 load 1회, 실행마다 apply
- load·apply 실패는 인용 없이 기존 칩(답변·재진입을 막지 않는다)
"""

import dataclasses
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.application.agent_run.run_sources import RunSourcesService

from tests.application.agent_run.test_run_sources_service import (
    RUN_B,
    RUN_ID,
    _retrieval,
)


def _service(enricher=None):
    runs = MagicMock()
    runs.find_retrievals_by_runs = AsyncMock(
        return_value={
            RUN_ID.value: [_retrieval()],
            RUN_B.value: [_retrieval(RUN_B, "doc-2")],
        }
    )
    runs.find_tool_calls_by_runs = AsyncMock(return_value={})
    documents = MagicMock()
    documents.find_filenames = AsyncMock(return_value={})
    tools = MagicMock()
    tools.list_active = AsyncMock(return_value=[])
    logger = MagicMock()
    kwargs = {} if enricher is None else {"citation_enricher": enricher}
    return RunSourcesService(
        runs, documents, tools, logger, max_items=6, **kwargs
    ), logger


@pytest.mark.asyncio
async def test_without_enricher_no_citation_key():
    service, _ = _service()
    (item,) = (await service.build_for_runs([RUN_ID], "req"))[RUN_ID.value]
    assert "citation" not in item.to_payload()


@pytest.mark.asyncio
async def test_load_once_and_apply_per_run():
    enricher = MagicMock()
    enricher.load = AsyncMock(return_value={RUN_ID.value: "stored-a"})
    enricher.apply = MagicMock(
        side_effect=lambda items, stored, evidence: [
            dataclasses.replace(
                i, citation={"status": "verified", "entries": [], "s": stored}
            )
            for i in items
        ]
    )
    service, _ = _service(enricher)
    built = await service.build_for_runs([RUN_ID, RUN_B], "req")
    enricher.load.assert_awaited_once_with([RUN_ID.value, RUN_B.value], "req")
    assert built[RUN_ID.value][0].to_payload()["citation"]["s"] == "stored-a"
    assert built[RUN_B.value][0].citation["s"] is None


@pytest.mark.asyncio
async def test_load_failure_keeps_chips_without_citation():
    enricher = MagicMock()
    enricher.load = AsyncMock(side_effect=RuntimeError("db"))
    service, logger = _service(enricher)
    (item,) = (await service.build_for_runs([RUN_ID], "req"))[RUN_ID.value]
    assert item.citation is None
    logger.warning.assert_called()


@pytest.mark.asyncio
async def test_apply_failure_keeps_chips_without_citation():
    enricher = MagicMock()
    enricher.load = AsyncMock(return_value={})
    enricher.apply = MagicMock(side_effect=RuntimeError("bad"))
    service, logger = _service(enricher)
    (item,) = (await service.build_for_runs([RUN_ID], "req"))[RUN_ID.value]
    assert item.citation is None
    logger.warning.assert_called()
