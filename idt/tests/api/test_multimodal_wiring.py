"""multimodal-extractor DI 배선.

라우트 등록은 실요청으로 검증 (위키 router-map: app.routes 순회 금지).
"""

from fastapi.testclient import TestClient
from src.api.multimodal_di import (
    build_extractor_registry,
    build_vision_adapter_registry,
)


def test_registries_have_expected_keys():
    assert build_extractor_registry().supported() == ("pdf",)
    assert build_vision_adapter_registry().supported() == (
        "anthropic",
        "ollama",
        "openai",
        "openai_compatible",
    )


def test_app_registers_multimodal_routes_and_guards_auth():
    from src.api.main import create_app

    client = TestClient(create_app())
    # 미인증 → 401 (404 면 라우트 미등록, 500 이면 DI 미배선)
    assert client.get("/api/v1/admin/multimodal/settings").status_code == 401
    assert client.post("/api/v1/admin/multimodal/test").status_code == 401
    r = client.post(
        "/api/v1/preview/multimodal",
        files={"file": ("a.pdf", b"%PDF", "application/pdf")},
    )
    assert r.status_code == 401
