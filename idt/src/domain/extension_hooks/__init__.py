"""코어 확장 지점 (graph-rag-foundation module-1).

코어 모듈은 이 패키지만 import 한다. 확장 구현(graph_rag 등)은 import 하지 않는다
— tests/contracts/test_extension_boundaries.py 가 고정한다.
"""
from src.domain.extension_hooks.events import (
    DocumentDeletedEvent,
    DocumentIngestedEvent,
    SupplementalGrant,
    SupplementalQuery,
    SupplementalResult,
)
from src.domain.extension_hooks.ports import (
    DocumentDeletionHook,
    FeatureExposurePort,
    PostIngestHook,
    SupplementalRetrievalSource,
)
from src.domain.extension_hooks.registry import ExtensionHooks

GRAPH_RAG_FEATURE = "graph_rag"

__all__ = [
    "DocumentDeletedEvent",
    "DocumentDeletionHook",
    "DocumentIngestedEvent",
    "ExtensionHooks",
    "FeatureExposurePort",
    "GRAPH_RAG_FEATURE",
    "PostIngestHook",
    "SupplementalGrant",
    "SupplementalQuery",
    "SupplementalResult",
    "SupplementalRetrievalSource",
]
