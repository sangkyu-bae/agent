"""Design §8.2 #10/#11 — 실 추출기 + 레지스트리 + fake 비전 어댑터를 라우터까지 관통.

UseCase 를 mock 하지 않는다: PdfPyMuPdfExtractor → NoiseFilter/Limit Policy →
MultimodalExtractionUseCase → preview_multimodal 직렬화(썸네일) 까지 한 번에 검증한다.
비전 호출만 fake (실 LLM 은 test_vision_smoke.py).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import fitz
from fastapi import FastAPI
from fastapi.testclient import TestClient
from src.api.multimodal_di import build_extractor_registry
from src.api.routes.preview_router import (
    get_multimodal_extraction_use_case,
    get_multimodal_thumbnailer,
    router,
)
from src.application.multimodal.registries import VisionAdapterRegistry
from src.application.multimodal.use_case import MultimodalExtractionUseCase
from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.llm_model.entity import LlmModel
from src.domain.multimodal.interfaces import DescribeOutcome
from src.domain.multimodal.schemas import DescriptionDraft
from src.domain.multimodal.value_objects import MultimodalSettings
from src.infrastructure.multimodal.thumbnail import thumbnail_b64
from src.interfaces.dependencies.auth import get_current_user

from tests.infrastructure.multimodal.test_pdf_extractor import _draw_table, _png

URL = "/api/v1/preview/multimodal"


def _user() -> User:
    return User(
        email="u@test.com",
        password_hash="h",
        role=UserRole.USER,
        status=UserStatus.APPROVED,
        id=1,
    )


def _pdf() -> bytes:
    """p1: 큰 그림 1 + 48px 아이콘 2 / p2: 표 1 → 후보 4, 필터 제외 2."""
    doc = fitz.open()
    big = _png(400, 300, (200, 30, 30))
    icon = _png(48, 48, (30, 30, 200))
    p1 = doc.new_page(width=595, height=842)
    p1.insert_text((72, 60), "figure page", fontsize=12)
    p1.insert_image(fitz.Rect(72, 100, 472, 400), stream=big)
    p1.insert_image(fitz.Rect(500, 20, 548, 68), stream=icon)
    p1.insert_image(fitz.Rect(500, 780, 548, 828), stream=icon)
    p2 = doc.new_page(width=595, height=842)
    _draw_table(p2, fitz.Rect(72, 100, 500, 300))
    data = doc.tobytes()
    doc.close()
    return data


class FakeVision:
    provider = "fake"
    fail_sha: set[str] = set()

    def __init__(self, llm_factory, llm_model, logger, callbacks=None):
        pass

    async def describe(self, image, element_type, options):
        await asyncio.sleep(0)
        if image.sha256 in FakeVision.fail_sha:
            raise TimeoutError("slow")
        return DescribeOutcome(
            draft=DescriptionDraft(
                detected_type=element_type.value,
                description=f"desc-{element_type.value}",
                keywords=["k"],
                markdown_table="| a | b |"
                if element_type.value == "table_image"
                else None,
                chart=None,
                page_text=None,
            ),
            degraded_output_mode=False,
            output_mode="strict",
            usage={"total_tokens": 7},
        )


def _settings(**over) -> MultimodalSettings:
    base = dict(
        id="s",
        enabled=True,
        vision_model_id="m1",
        max_images_per_doc=50,
        min_image_px=100,
        min_area_ratio=0.02,
        concurrency=2,
        timeout_sec=5,
        output_language="ko",
        detail_level="brief",
        updated_at=datetime.now(UTC),
    )
    base.update(over)
    return MultimodalSettings(**base)


def _client(settings: MultimodalSettings, monkeypatch) -> TestClient:
    monkeypatch.setenv("FAKE_KEY", "x")
    now = datetime.now(UTC)
    model = LlmModel(
        id="m1",
        provider="fake",
        model_name="fake-v",
        display_name="Fake",
        description=None,
        api_key_env="FAKE_KEY",
        max_tokens=None,
        is_active=True,
        is_default=False,
        created_at=now,
        updated_at=now,
        supports_vision=True,
    )
    settings_repo = MagicMock()
    settings_repo.get = AsyncMock(return_value=settings)
    llm_repo = MagicMock()
    llm_repo.find_by_id = AsyncMock(return_value=model)
    vreg = VisionAdapterRegistry()
    vreg.register(FakeVision)
    uc = MultimodalExtractionUseCase(
        extractors=build_extractor_registry(),
        adapters=vreg,
        settings_repo=settings_repo,
        llm_model_repo=llm_repo,
        llm_factory=MagicMock(),
        logger=MagicMock(),
        retry_backoff_sec=0.01,
    )
    uc._timeout_override_sec = 0.2
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_multimodal_extraction_use_case] = lambda: uc
    app.dependency_overrides[get_multimodal_thumbnailer] = lambda: thumbnail_b64
    app.dependency_overrides[get_current_user] = lambda: _user()
    return TestClient(app)


def test_l1_10_synthetic_pdf_through_real_extractor(monkeypatch):
    """§8.2 #10: succeeded=2(그림+표), dropped=2(아이콘), 썸네일 존재, bytes 미노출."""
    FakeVision.fail_sha = set()
    r = _client(_settings(), monkeypatch).post(
        URL, files={"file": ("sample.pdf", _pdf(), "application/pdf")}
    )
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["total_candidates"] == 4
    assert b["dropped_by_filter"] == 2
    assert b["skipped_by_limit"] == 0
    assert b["succeeded"] == 2 and b["failed"] == 0
    types = sorted(e["element_type"] for e in b["elements"])
    assert types == ["figure", "table_image"]
    for e in b["elements"]:
        assert "image_bytes" not in e
        assert e["thumbnail_b64"]
        assert e["status"] == "succeeded" and e["model_id"] == "m1"
    table = next(e for e in b["elements"] if e["element_type"] == "table_image")
    assert table["markdown_table"] == "| a | b |" and table["page"] == 2


def test_l1_11_one_timeout_is_degraded_not_fatal(monkeypatch):
    """§8.2 #11: 1건 타임아웃 → failed=1, 나머지 succeeded, 전체 200."""
    client = _client(_settings(), monkeypatch)
    # 먼저 sha 를 알아내기 위해 한 번 추출 (결정적 PNG 이므로 재현 가능)
    first = client.post(
        URL, files={"file": ("sample.pdf", _pdf(), "application/pdf")}
    ).json()
    figure_sha = next(
        e["sha256"] for e in first["elements"] if e["element_type"] == "figure"
    )
    FakeVision.fail_sha = {figure_sha}
    try:
        b = client.post(
            URL, files={"file": ("sample.pdf", _pdf(), "application/pdf")}
        ).json()
    finally:
        FakeVision.fail_sha = set()
    assert b["succeeded"] == 1 and b["failed"] == 1
    failed = next(e for e in b["elements"] if e["status"] == "failed")
    assert failed["element_type"] == "figure" and "timeout" in failed["reason"]


def test_limit_marks_overflow_skipped_end_to_end(monkeypatch):
    b = (
        _client(_settings(max_images_per_doc=1), monkeypatch)
        .post(URL, files={"file": ("sample.pdf", _pdf(), "application/pdf")})
        .json()
    )
    assert b["succeeded"] == 1 and b["skipped_by_limit"] == 1
    skipped = next(e for e in b["elements"] if e["status"] == "skipped")
    assert skipped["reason"] == "limit:max_images_per_doc=1"
    assert skipped["thumbnail_b64"]  # skipped 도 썸네일은 제공(육안 확인용)


def test_debug_lists_filtered_candidates_end_to_end(monkeypatch):
    b = (
        _client(_settings(), monkeypatch)
        .post(
            f"{URL}?debug=true",
            files={"file": ("sample.pdf", _pdf(), "application/pdf")},
        )
        .json()
    )
    # 두 아이콘 모두 px 필터에서 먼저 탈락
    # — 해시 중복은 "kept" 사이에서만 판정된다(policies.py)
    reasons = sorted(d["reason"] for d in b["dropped"])
    assert reasons == ["min_image_px", "min_image_px"]
    assert all(d["width"] == 48 for d in b["dropped"])
