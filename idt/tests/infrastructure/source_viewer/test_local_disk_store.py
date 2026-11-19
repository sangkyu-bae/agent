"""source-passage-viewer module-1 — LocalDiskOriginalStore (Design §3.4, §7, §8.2 #5)."""
import pytest

from src.infrastructure.source_viewer.local_disk_store import LocalDiskOriginalStore

_DOC = "8f1c2d3e-0000-4000-8000-000000000001"


@pytest.mark.asyncio
async def test_save_exists_open_delete_roundtrip(tmp_path):
    store = LocalDiskOriginalStore(tmp_path)
    assert await store.exists(_DOC) is False
    assert await store.open(_DOC) is None

    await store.save(_DOC, b"%PDF-1.4 data")
    assert (tmp_path / "8f" / _DOC).read_bytes() == b"%PDF-1.4 data"
    assert await store.exists(_DOC) is True
    assert await store.open(_DOC) == b"%PDF-1.4 data"

    await store.delete(_DOC)
    assert await store.exists(_DOC) is False


@pytest.mark.asyncio
async def test_save_overwrites(tmp_path):
    store = LocalDiskOriginalStore(tmp_path)
    await store.save(_DOC, b"old")
    await store.save(_DOC, b"new")
    assert await store.open(_DOC) == b"new"


@pytest.mark.asyncio
async def test_save_leaves_no_temp_file(tmp_path):
    store = LocalDiskOriginalStore(tmp_path)
    await store.save(_DOC, b"x")
    assert sorted(p.name for p in (tmp_path / "8f").iterdir()) == [_DOC]


@pytest.mark.asyncio
async def test_delete_missing_is_noop(tmp_path):
    await LocalDiskOriginalStore(tmp_path).delete(_DOC)


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["../escape", "", "x" * 36])
async def test_invalid_document_id_rejected_on_every_operation(tmp_path, bad):
    store = LocalDiskOriginalStore(tmp_path)
    for op in (store.exists, store.open, store.delete):
        with pytest.raises(ValueError):
            await op(bad)
    with pytest.raises(ValueError):
        await store.save(bad, b"x")
    assert list(tmp_path.iterdir()) == []


def test_root_is_created(tmp_path):
    root = tmp_path / "nested" / "originals"
    LocalDiskOriginalStore(root)
    assert root.is_dir()
