"""source-passage-viewer module-2 — 업로드 → original_sink 연결 (Design §2.2, §8.2 #11).

- 미주입(None)이면 기존 동작 그대로
- KB 업로드이고 인덱싱이 완전 실패하지 않았을 때만 1회 저장
- sink 가 예외를 던져도 업로드 결과는 그대로 (두 겹 흡수의 바깥 겹)
"""
from unittest.mock import AsyncMock, patch

import pytest

from tests.application.unified_upload.test_extra_metadata import (
    _build_use_case,
    _fake_chunk,
    _make_request,
    _run_upload,
)

_KB_META = {"kb_id": "kb-uuid", "kb_name": "여신 규정집"}


@pytest.mark.asyncio
async def test_without_sink_upload_is_unchanged():
    _, deps = _build_use_case()
    result, _ = await _run_upload(
        deps, _make_request(extra_metadata=_KB_META), [_fake_chunk()]
    )
    assert result.status == "completed"


@pytest.mark.asyncio
async def test_kb_upload_saves_original_once():
    _, deps = _build_use_case()
    sink = AsyncMock()
    deps["original_sink"] = sink
    request = _make_request(extra_metadata=_KB_META, file_bytes=b"%PDF bytes")
    result, _ = await _run_upload(deps, request, [_fake_chunk()])

    sink.save.assert_awaited_once_with(
        result.document_id, "test.pdf", b"%PDF bytes", "req-1"
    )


@pytest.mark.asyncio
async def test_non_kb_upload_does_not_save():
    _, deps = _build_use_case()
    sink = AsyncMock()
    deps["original_sink"] = sink
    await _run_upload(deps, _make_request(), [_fake_chunk()])
    sink.save.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_indexing_does_not_save():
    _, deps = _build_use_case()
    sink = AsyncMock()
    deps["original_sink"] = sink
    deps["es_repo"].bulk_index.side_effect = RuntimeError("es down")
    with patch(
        "src.application.unified_upload.use_case.UnifiedUploadUseCase._store_to_qdrant",
        new=AsyncMock(side_effect=RuntimeError("qdrant down")),
    ):
        result, _ = await _run_upload(
            deps, _make_request(extra_metadata=_KB_META), [_fake_chunk()]
        )
    assert result.status == "failed"
    sink.save.assert_not_awaited()


@pytest.mark.asyncio
async def test_sink_exception_does_not_break_upload():
    _, deps = _build_use_case()
    sink = AsyncMock()
    sink.save.side_effect = RuntimeError("boom")
    deps["original_sink"] = sink
    result, _ = await _run_upload(
        deps, _make_request(extra_metadata=_KB_META), [_fake_chunk()]
    )
    assert result.status == "completed"
    deps["logger"].warning.assert_called()
