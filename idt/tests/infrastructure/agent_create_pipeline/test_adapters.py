"""CatalogCandidateReader / NullToolSelector 테스트 — Design §2.3 / §6.1.

포트 계약 2개를 못박는다:
- 후보 로더는 **예외를 던지지 않는다** — 실패는 빈 튜플 + warning.
- Null 셀렉터는 항상 fallback 이며 required 를 보존한다 (파이프라인이
  degraded 로 진행할 수 있는 형태).
"""
from datetime import datetime

from src.domain.tool_catalog.entity import ToolCatalogEntry
from src.domain.tool_selection.schemas import ToolSource
from src.infrastructure.agent_create_pipeline.adapters import (
    CatalogCandidateReader,
    NullToolSelector,
)


class FakeLogger:
    def __init__(self) -> None:
        self.warnings: list[str] = []

    def debug(self, message, **kwargs): ...
    def info(self, message, **kwargs): ...

    def warning(self, message, **kwargs):
        self.warnings.append(message)

    def error(self, message, exception=None, **kwargs): ...
    def critical(self, message, exception=None, **kwargs): ...


class FakeCatalogRepo:
    def __init__(self, entries=None, error: Exception | None = None) -> None:
        self.entries = entries or []
        self.error = error

    async def list_active(self, request_id: str):
        if self.error is not None:
            raise self.error
        return self.entries


def _entry(tool_id="internal:hybrid_search", source="internal",
           description="검색 도구") -> ToolCatalogEntry:
    now = datetime(2026, 8, 19)
    return ToolCatalogEntry(
        id="1", tool_id=tool_id, source=source, name="검색",
        description=description, mcp_server_id=None, requires_env=[],
        is_active=True, is_builtin=False, created_at=now, updated_at=now,
    )


# --- CatalogCandidateReader --------------------------------------------------


async def test_maps_catalog_entries_to_candidates_verbatim() -> None:
    """tool_id 는 카탈로그 표기 그대로 통과한다 (이중 네임스페이스 변환 금지)."""
    repo = FakeCatalogRepo([
        _entry("internal:hybrid_search", "internal"),
        _entry("mcp:srv1:web_search", "mcp"),
    ])
    reader = CatalogCandidateReader(repository=repo, logger=FakeLogger())

    candidates = await reader.list_active()

    assert [c.tool_id for c in candidates] == [
        "internal:hybrid_search", "mcp:srv1:web_search",
    ]
    assert candidates[0].source is ToolSource.INTERNAL
    assert candidates[1].source is ToolSource.MCP


async def test_none_description_becomes_empty_string() -> None:
    repo = FakeCatalogRepo([_entry(description=None)])
    reader = CatalogCandidateReader(repository=repo, logger=FakeLogger())
    candidates = await reader.list_active()
    assert candidates[0].description == ""


async def test_repository_failure_degrades_to_empty_with_warning() -> None:
    logger = FakeLogger()
    reader = CatalogCandidateReader(
        repository=FakeCatalogRepo(error=RuntimeError("db down")), logger=logger
    )

    candidates = await reader.list_active()

    assert candidates == ()
    assert len(logger.warnings) == 1


async def test_unknown_source_falls_back_to_internal() -> None:
    repo = FakeCatalogRepo([_entry(source="???")])
    reader = CatalogCandidateReader(repository=repo, logger=FakeLogger())
    candidates = await reader.list_active()
    assert candidates[0].source is ToolSource.INTERNAL


# --- NullToolSelector --------------------------------------------------------


async def test_null_selector_always_falls_back_preserving_required() -> None:
    selector = NullToolSelector()

    result = await selector.select(
        "질의", (), required_ids=("internal:a", "internal:b", "internal:a")
    )

    assert result.fallback is True
    assert result.selected_ids == ()
    assert result.final_ids == ("internal:a", "internal:b")
    assert result.reason
