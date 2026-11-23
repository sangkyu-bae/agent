"""answer_citation_di — 스위치·조립 실패 (answer-citation-verification §10.1, FR-15)."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from src.api.answer_citation_di import build_answer_citation, citation_enricher_for
from src.application.answer_citation.enricher import CitationEnricher
from src.application.answer_citation.labeler import CitationLabeler
from src.application.answer_citation.service import CitationService


def _settings(enabled: bool, ttl=1800.0, max_runs=1000):
    return SimpleNamespace(
        answer_citation_enabled=enabled,
        answer_citation_registry_ttl_seconds=ttl,
        answer_citation_registry_max_runs=max_runs,
    )


def test_disabled_builds_nothing():
    assert build_answer_citation(_settings(False), MagicMock(), MagicMock()) is None


def test_enabled_builds_parts_sharing_one_registry():
    parts = build_answer_citation(_settings(True), MagicMock(), MagicMock())
    assert isinstance(parts.labeler, CitationLabeler)
    assert isinstance(parts.service, CitationService)
    assert parts.labeler._registry is parts.service._registry


def test_assembly_failure_disables_feature_with_warning():
    logger = MagicMock()
    assert (
        build_answer_citation(_settings(True, ttl="bad"), MagicMock(), logger) is None
    )
    logger.warning.assert_called_once()


def test_enricher_only_when_parts_exist():
    assert citation_enricher_for(None, MagicMock(), MagicMock()) is None
    parts = build_answer_citation(_settings(True), MagicMock(), MagicMock())
    assert isinstance(
        citation_enricher_for(parts, MagicMock(), MagicMock()), CitationEnricher
    )
