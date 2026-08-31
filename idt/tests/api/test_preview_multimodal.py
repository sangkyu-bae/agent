"""POST /api/v1/preview/multimodal L1 — Design §4.2 / §8.2 #10~#13."""

from __future__ import annotations

from unittest.mock import AsyncMock

import fitz
from fastapi import FastAPI
from fastapi.testclient import TestClient
from src.api.routes.preview_router import (
    get_multimodal_extraction_use_case,
    get_multimodal_thumbnailer,
    router,
)
from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.multimodal.errors import (
    ExtractionError,
    MultimodalDisabledError,
    MultimodalNotConfiguredError,
    UnsupportedFormatError,
    UnsupportedVisionProviderError,
)
from src.domain.multimodal.value_objects import (
    BBox,
    ChartReading,
    DataPoint,
    ElementStatus,
    ElementType,
    ExtractionResult,
    MultimodalElement,
)
from src.infrastructure.multimodal.thumbnail import thumbnail_b64
from src.interfaces.dependencies.auth import get_current_user


def _user() -> User:
    return User(
        email="u@test.com",
        password_hash="h",
        role=UserRole.USER,
        status=UserStatus.APPROVED,
        id=1,
    )


def _png(w=400, h=300) -> bytes:
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, w, h), False)
    pix.clear_with(90)
    return pix.tobytes("png")


def _el(
    status=ElementStatus.SUCCEEDED, et=ElementType.CHART, **over
) -> MultimodalElement:
    base = dict(
        element_id="e1",
        page=12,
        bbox=BBox(72, 100, 520, 390),
        element_type=et,
        status=status,
        reason=None,
        description="분기별 한도",
        keywords=("한도",),
        markdown_table=None,
        chart=ChartReading(
            "bar", "분기", "억원", ("한도",), (DataPoint("1Q", "120"),), "증가"
        ),
        page_text=None,
        image_bytes=_png(),
        mime="image/png",
        width=400,
        height=300,
        sha256="a" * 64,
        model_id="m1",
        elapsed_ms=1980,
        degraded_output_mode=False,
    )
    base.update(over)
    return MultimodalElement(**base)


def _result(elements) -> ExtractionResult:
    return ExtractionResult(
        elements=tuple(elements),
        total_candidates=23,
        dropped_by_filter=9,
        skipped_by_limit=1,
        succeeded=1,
        failed=1,
        vision_model_id="m1",
        provider="openai",
        model_name="gpt-4o",
        timings_ms=(("extract", 812), ("describe", 15430)),
    )


def _client(uc: AsyncMock) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_multimodal_extraction_use_case] = lambda: uc
    app.dependency_overrides[get_multimodal_thumbnailer] = lambda: thumbnail_b64
    app.dependency_overrides[get_current_user] = lambda: _user()
    return TestClient(app)


URL = "/api/v1/preview/multimodal"
PDF = {"file": ("a.pdf", b"%PDF-1.4 fake", "application/pdf")}


def test_preview_serializes_result_with_thumbnail_and_without_bytes():
    uc = AsyncMock()
    uc.run.return_value = _result(
        [
            _el(),
            _el(
                status=ElementStatus.FAILED,
                et=ElementType.FIGURE,
                element_id="e2",
                reason="timeout (1 retry)",
                description=None,
                chart=None,
                keywords=(),
            ),
            _el(
                status=ElementStatus.SKIPPED,
                element_id="e3",
                reason="limit:max_images_per_doc=50",
                description=None,
                chart=None,
                keywords=(),
                elapsed_ms=None,
            ),
        ]
    )
    r = _client(uc).post(URL, files=PDF)
    assert r.status_code == 200
    b = r.json()
    assert b["provider"] == "openai" and b["total_candidates"] == 23
    assert b["timings_ms"] == {"extract": 812, "describe": 15430}
    assert "dropped" not in b  # debug=false
    e = b["elements"][0]
    assert "image_bytes" not in e and e["thumbnail_b64"]
    assert e["element_type"] == "chart" and e["status"] == "succeeded"
    assert e["chart"]["data_points"] == [{"label": "1Q", "value": "120"}]
    assert e["bbox"] == {"x0": 72, "y0": 100, "x1": 520, "y1": 390}
    assert b["elements"][1]["status"] == "failed" and b["elements"][1]["reason"]
    assert (
        b["elements"][2]["status"] == "skipped"
        and b["elements"][2]["elapsed_ms"] is None
    )
    # run() 호출 인자: bytes, filename, request_id, analysis=None
    args, kwargs = uc.run.call_args
    assert args[0] == b"%PDF-1.4 fake" and args[1] == "a.pdf"


def test_thumbnail_is_downscaled_png_under_256px():
    import base64

    uc = AsyncMock()
    uc.run.return_value = _result(
        [_el(image_bytes=_png(1200, 600), width=1200, height=600)]
    )
    e = _client(uc).post(URL, files=PDF).json()["elements"][0]
    raw = base64.b64decode(e["thumbnail_b64"])
    pix = fitz.Pixmap(raw)
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"
    assert max(pix.width, pix.height) <= 256
    assert e["width"] == 1200  # 원본 크기는 그대로 보고


def test_preview_debug_includes_dropped_summary():
    uc = AsyncMock()
    uc.run.return_value = _result([_el()])
    b = _client(uc).post(f"{URL}?debug=true", files=PDF).json()
    assert "dropped" in b and isinstance(b["dropped"], list)


def test_preview_unsupported_extension_415():
    uc = AsyncMock()
    uc.run.side_effect = UnsupportedFormatError("docx", ("pdf",))
    r = _client(uc).post(
        URL, files={"file": ("a.docx", b"x", "application/octet-stream")}
    )
    assert r.status_code == 415
    assert r.json()["detail"]["code"] == "UNSUPPORTED_FORMAT"
    assert "pdf" in r.json()["detail"]["message"]


def test_preview_disabled_409():
    uc = AsyncMock()
    uc.run.side_effect = MultimodalDisabledError("off")
    r = _client(uc).post(URL, files=PDF)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "MULTIMODAL_DISABLED"


def test_preview_not_configured_409():
    uc = AsyncMock()
    uc.run.side_effect = MultimodalNotConfiguredError("no model")
    r = _client(uc).post(URL, files=PDF)
    assert (
        r.status_code == 409
        and r.json()["detail"]["code"] == "MULTIMODAL_NOT_CONFIGURED"
    )


def test_preview_requires_auth():
    from fastapi import HTTPException

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_multimodal_extraction_use_case] = lambda: AsyncMock()
    app.dependency_overrides[get_multimodal_thumbnailer] = lambda: thumbnail_b64

    def _unauth():
        raise HTTPException(401, "no token")

    app.dependency_overrides[get_current_user] = _unauth
    assert TestClient(app).post(URL, files=PDF).status_code == 401


def test_preview_too_large_413():
    uc = AsyncMock()
    big = b"%PDF" + b"0" * (30 * 1024 * 1024 + 1)
    r = _client(uc).post(URL, files={"file": ("a.pdf", big, "application/pdf")})
    assert r.status_code == 413
    uc.run.assert_not_called()


def test_preview_corrupt_pdf_bytes_415():
    """Gap Critical: .pdf 확장자 + 비-PDF 바이트 → ExtractionError → 415 (Design §7)."""
    uc = AsyncMock()
    uc.run.side_effect = ExtractionError("cannot open pdf 'a.pdf': not a PDF")
    r = _client(uc).post(
        URL, files={"file": ("a.pdf", b"not a pdf at all", "application/pdf")}
    )
    assert r.status_code == 415
    assert r.json()["detail"]["code"] == "UNSUPPORTED_FORMAT"


def test_preview_unknown_provider_500_with_code():
    uc = AsyncMock()
    uc.run.side_effect = UnsupportedVisionProviderError("gemini", ("openai",))
    r = _client(uc).post(URL, files=PDF)
    assert r.status_code == 500
    assert r.json()["detail"]["code"] == "UNSUPPORTED_VISION_PROVIDER"
