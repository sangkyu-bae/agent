"""Qdrant 개정 가드 — superseded 청크를 벡터 질의·scroll 에서 기본 제외.

Design Ref: document-revision §9.5 G1·G2 — 필드 부재 청크는 must_not 에
걸리지 않아 통과한다.
"""
from __future__ import annotations

from qdrant_client import models

from src.domain.document_revision.search_guard import (
    REVISION_STATUS_FIELD,
    SUPERSEDED_VALUE,
)


def revision_guard_condition() -> models.FieldCondition:
    return models.FieldCondition(
        key=REVISION_STATUS_FIELD,
        match=models.MatchValue(value=SUPERSEDED_VALUE),
    )


def _is_guard(cond: object) -> bool:
    return (
        getattr(cond, "key", None) == REVISION_STATUS_FIELD
        and getattr(getattr(cond, "match", None), "value", None) == SUPERSEDED_VALUE
    )


def apply_revision_guard(query_filter: models.Filter | None) -> models.Filter:
    """기존 must/should/min_should 는 그대로 두고 must_not 에 가드를 더한다(멱등)."""
    if query_filter is None:
        return models.Filter(must_not=[revision_guard_condition()])
    must_not = list(query_filter.must_not or [])
    if not any(_is_guard(c) for c in must_not):
        must_not.append(revision_guard_condition())
    return models.Filter(
        must=query_filter.must,
        should=query_filter.should,
        min_should=query_filter.min_should,
        must_not=must_not,
    )
