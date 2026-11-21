"""answer-citation-verification 조립 — 코어에 끼워 넣는 단일 지점 (Design §9.1, §10.1).

main.py 는 이 모듈의 접근자 3개만 부른다(answer_citation 패키지 import 는 여기뿐 —
tests/application/answer_citation/test_module_boundaries.py 가 강제한다).
  - answer_citation_labeler()  → ToolFactory(citation_labeler=)     검색 머리말 번호
  - answer_citation_service()  → WorkflowCompiler(citation_service=) 답변 지시·검증·저장
  - answer_citation_enricher(session, logger) → RunSourcesService(citation_enricher=) 칩
ANSWER_CITATION_ENABLED=false 이거나 조립에 실패하면 셋 다 None — 기존 동작 그대로.
기능을 뺄 때: main.py 의 import 1줄·주입 3곳과 이 파일, answer_citation 패키지를 지운다.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from src.application.answer_citation.enricher import CitationEnricher
from src.application.answer_citation.labeler import CitationLabeler
from src.application.answer_citation.registry import CitationRegistry
from src.application.answer_citation.service import CitationService
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.answer_citation.repository import (
    AnswerCitationRepository,
    SessionScopedAnswerCitationStore,
)
from src.infrastructure.logging import StructuredLogger


@dataclass(frozen=True)
class AnswerCitationParts:
    registry: CitationRegistry
    labeler: CitationLabeler
    service: CitationService


_parts: AnswerCitationParts | None = None
_built = False


def build_answer_citation(
    settings: Any, session_factory: Callable[[], Any], logger: LoggerInterface
) -> AnswerCitationParts | None:
    """설정 → 부품. 라벨러와 서비스는 같은 레지스트리를 공유한다(D-01)."""
    if not settings.answer_citation_enabled:
        return None
    try:
        registry = CitationRegistry(
            ttl_seconds=float(settings.answer_citation_registry_ttl_seconds),
            max_runs=int(settings.answer_citation_registry_max_runs),
        )
        store = SessionScopedAnswerCitationStore(session_factory, logger)
        return AnswerCitationParts(
            registry=registry,
            labeler=CitationLabeler(registry, logger),
            service=CitationService(registry, store, logger),
        )
    except Exception as e:  # noqa: BLE001 — 부가 기능 조립 실패가 기동을 막으면 안 된다
        logger.warning(
            "answer_citation assembly failed — feature disabled", exception=e
        )
        return None


def get_answer_citation() -> AnswerCitationParts | None:
    """앱 수명 1회 조립 — 요청마다 재시도하지 않는다(source_viewer_di 선례)."""
    global _parts, _built
    if not _built:
        from src.config import settings
        from src.infrastructure.persistence.database import get_session_factory

        _built = True
        _parts = build_answer_citation(
            settings, get_session_factory(), StructuredLogger("answer_citation")
        )
    return _parts


def answer_citation_labeler() -> CitationLabeler | None:
    parts = get_answer_citation()
    return parts.labeler if parts else None


def answer_citation_service() -> CitationService | None:
    parts = get_answer_citation()
    return parts.service if parts else None


def citation_enricher_for(
    parts: AnswerCitationParts | None, session: Any, logger: LoggerInterface
) -> CitationEnricher | None:
    """요청 세션의 저장소로 enricher 를 만든다(근거 칩 서비스와 같은 세션, DB-001)."""
    if parts is None:
        return None
    return CitationEnricher(AnswerCitationRepository(session, logger), logger)


def answer_citation_enricher(
    session: Any, logger: LoggerInterface
) -> CitationEnricher | None:
    return citation_enricher_for(get_answer_citation(), session, logger)
