"""검색 가드 — superseded 청크를 모든 검색에서 기본 제외한다.

Design Ref: document-revision §9.5 — 호출 지점이 아니라 저장소 검색 최하단에 건다.
필드가 없는 기존 청크는 must_not 에 걸리지 않으므로 active 로 통과한다(백필 불필요).
ES 절은 순수 dict 라 application 계층(HybridSearchUseCase)에서도 쓸 수 있도록
domain 에 둔다.
"""
from __future__ import annotations

REVISION_STATUS_FIELD = "revision_status"
SUPERSEDED_VALUE = "superseded"
ACTIVE_VALUE = "active"


def es_revision_guard_clause() -> dict:
    """ES bool.filter 에 넣는 절. 호출마다 새 dict 를 반환한다."""
    return {
        "bool": {
            "must_not": [{"term": {REVISION_STATUS_FIELD: SUPERSEDED_VALUE}}]
        }
    }
