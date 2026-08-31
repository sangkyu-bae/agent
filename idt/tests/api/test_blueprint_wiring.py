"""golden-sample-blueprint DI 배선 — 라우트 등록은 실요청으로 검증."""

from fastapi.testclient import TestClient
from src.api.blueprint_di import build_font_catalog, build_sample_extractor_registry


def test_registry_and_font_catalog_defaults():
    assert build_sample_extractor_registry().supported == ("pdf", "pptx")
    cat = build_font_catalog("", "NanumGothic")
    assert cat.installed() == () and cat.default_font() == "NanumGothic"


def test_app_registers_blueprint_routes_and_guards_auth():
    from src.api.main import create_app

    client = TestClient(create_app())
    # 미인증 → 401 (404 면 라우트 미등록, 500 이면 DI 미배선)
    assert client.get("/api/v1/admin/blueprints").status_code == 401
    assert client.get("/api/v1/admin/blueprints/fonts").status_code == 401
    assert client.get("/api/v1/blueprints/options").status_code == 401
    r = client.post(
        "/api/v1/admin/blueprints/extract",
        files={"file": ("a.pdf", b"%PDF", "application/pdf")},
    )
    assert r.status_code == 401
