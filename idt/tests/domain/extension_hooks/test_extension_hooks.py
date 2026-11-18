"""코어 확장 훅 레지스트리·VO 테스트 (graph-rag-foundation Design §3.1, module-1)."""
import pytest
from src.domain.extension_hooks import (
    DocumentDeletedEvent,
    DocumentDeletionHook,
    DocumentIngestedEvent,
    ExtensionHooks,
    FeatureExposurePort,
    PostIngestHook,
    SupplementalGrant,
    SupplementalQuery,
    SupplementalResult,
    SupplementalRetrievalSource,
)


class _Ingest(PostIngestHook):
    async def on_document_ingested(self, event, request_id):
        return None


class _Delete(DocumentDeletionHook):
    async def on_document_deleted(self, event, request_id):
        return None


class _Source(SupplementalRetrievalSource):
    async def retrieve(self, query):
        return SupplementalResult(label="graph", hits=[], weight=0.5)


class _Exposure(FeatureExposurePort):
    async def is_visible(self, feature, caller_is_admin):
        return caller_is_admin


def test_grant_for_role_admin_and_user():
    assert SupplementalGrant.for_role("admin").caller_is_admin is True
    assert SupplementalGrant.for_role("user").caller_is_admin is False
    assert SupplementalGrant.for_role("anonymous").caller_is_admin is False


def test_hooks_default_empty():
    hooks = ExtensionHooks()
    assert hooks.post_ingest is None
    assert hooks.deletion is None
    assert hooks.supplemental is None
    assert hooks.exposure is None


def test_register_fills_slots():
    hooks = ExtensionHooks()
    ingest, delete, source, exposure = _Ingest(), _Delete(), _Source(), _Exposure()
    hooks.register(
        post_ingest=ingest, deletion=delete, supplemental=source, exposure=exposure
    )
    assert hooks.post_ingest is ingest
    assert hooks.deletion is delete
    assert hooks.supplemental is source
    assert hooks.exposure is exposure


def test_register_same_slot_twice_raises():
    hooks = ExtensionHooks()
    hooks.register(supplemental=_Source())
    with pytest.raises(ValueError):
        hooks.register(supplemental=_Source())


def test_same_owner_reregister_replaces():
    # create_app() 이 한 프로세스에서 여러 번 불려도(테스트·리로드) 같은 모듈은 교체된다
    hooks = ExtensionHooks()
    first, second = _Exposure(), _Exposure()
    hooks.register(owner="graph_rag", exposure=first)
    hooks.register(owner="graph_rag", exposure=second)
    assert hooks.exposure is second


def test_different_owner_same_slot_raises():
    hooks = ExtensionHooks()
    hooks.register(owner="graph_rag", exposure=_Exposure())
    with pytest.raises(ValueError):
        hooks.register(owner="other_ext", exposure=_Exposure())


def test_register_partial_keeps_other_slots():
    hooks = ExtensionHooks()
    hooks.register(post_ingest=_Ingest())
    hooks.register(deletion=_Delete())
    assert hooks.post_ingest is not None
    assert hooks.deletion is not None
    assert hooks.supplemental is None


@pytest.mark.asyncio
async def test_is_visible_without_exposure_is_false():
    hooks = ExtensionHooks()
    assert await hooks.is_visible("graph_rag", caller_is_admin=True) is False


@pytest.mark.asyncio
async def test_is_visible_delegates_and_swallows_errors():
    class _Boom(FeatureExposurePort):
        async def is_visible(self, feature, caller_is_admin):
            raise RuntimeError("down")

    hooks = ExtensionHooks()
    hooks.register(exposure=_Exposure())
    assert await hooks.is_visible("graph_rag", caller_is_admin=True) is True
    assert await hooks.is_visible("graph_rag", caller_is_admin=False) is False

    broken = ExtensionHooks()
    broken.register(exposure=_Boom())
    # 노출 판단 실패는 닫힘(False)
    assert await broken.is_visible("graph_rag", caller_is_admin=True) is False


def test_events_and_query_are_frozen():
    e = DocumentIngestedEvent(
        document_id="d1", kb_id="kb1", collection_name="c", filename="a.pdf",
        user_id="u1", chunk_count=3, status="completed",
    )
    with pytest.raises(Exception):
        e.document_id = "x"  # type: ignore[misc]
    d = DocumentDeletedEvent(document_id="d1", kb_id=None, collection_name="c")
    assert d.kb_id is None
    q = SupplementalQuery(
        query="q", top_k=5, collection_name="c", es_index=None,
        hard_filter={"kb_id": "kb1"}, lenient_filter={"visibility": "public"},
        grant=SupplementalGrant(caller_is_admin=False), request_id="r",
    )
    with pytest.raises(TypeError):
        q.hard_filter["x"] = "y"  # type: ignore[index]
