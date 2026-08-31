"""실 LLM 스모크 — Plan DoD "어댑터 3종 각각 실 LLM 1회 스모크 통과".

위키 structured-output-strict-schema: fake 로만 테스트한 LLM 모듈은 미완료
— 실 호출 1회가 DoD. 기본 pytest 에서는 제외(addopts -m 'not llm').
실행: `pytest -m llm tests/infrastructure/multimodal`
- OpenAI / Anthropic: 해당 API 키 env 없으면 skip
- OpenAI 호환 로컬: MM_SMOKE_LOCAL_BASE_URL + MM_SMOKE_LOCAL_MODEL 없으면 skip
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from hashlib import sha256
from unittest.mock import MagicMock

import pytest
from dotenv import load_dotenv
from src.application.multimodal.settings_use_case import sample_chart_png
from src.domain.llm_model.entity import LlmModel
from src.domain.multimodal.interfaces import DescribeOptions
from src.domain.multimodal.value_objects import BBox, ElementType, ImageCandidate
from src.infrastructure.llm.llm_factory import LLMFactory
from src.infrastructure.multimodal.vision.anthropic_vision_adapter import (
    AnthropicVisionAdapter,
)
from src.infrastructure.multimodal.vision.openai_compatible_vision_adapter import (
    OpenAICompatibleVisionAdapter,
)
from src.infrastructure.multimodal.vision.openai_vision_adapter import (
    OpenAIVisionAdapter,
)

load_dotenv()

pytestmark = pytest.mark.llm


def _model(
    provider: str, model_name: str, api_key_env: str, base_url: str | None = None
):
    now = datetime.now(UTC)
    return LlmModel(
        id=f"smoke-{provider}",
        provider=provider,
        model_name=model_name,
        display_name=model_name,
        description=None,
        api_key_env=api_key_env,
        max_tokens=None,
        is_active=True,
        is_default=False,
        created_at=now,
        updated_at=now,
        base_url=base_url,
        supports_vision=True,
    )


def _chart_candidate() -> ImageCandidate:
    data = sample_chart_png()
    return ImageCandidate(
        page=1,
        bbox=BBox(0, 0, 960, 640),
        image_bytes=data,
        mime="image/png",
        width=960,
        height=640,
        area_ratio=0.5,
        sha256=sha256(data).hexdigest(),
        hint_type=ElementType.CHART,
    )


def _assert_chart_outcome(outcome) -> None:
    d = outcome.draft
    assert d.detected_type == "chart", d
    assert d.description.strip(), "description 비어 있음"
    assert d.chart is not None and len(d.chart.data_points) >= 1, d
    labels = " ".join(p.label for p in d.chart.data_points)
    assert any(q in labels for q in ("1Q", "2Q", "3Q", "4Q")), labels


@pytest.mark.asyncio
@pytest.mark.skipif(not os.environ.get("OPENAI_API_KEY"), reason="OPENAI_API_KEY 없음")
async def test_openai_vision_smoke():
    adapter = OpenAIVisionAdapter(
        LLMFactory(), _model("openai", "gpt-4o", "OPENAI_API_KEY"), MagicMock()
    )
    out = await adapter.describe(
        _chart_candidate(), ElementType.CHART, DescribeOptions("ko", "brief")
    )
    _assert_chart_outcome(out)
    # OpenAI 는 strict(json_schema) 를 지원해야 한다 — 폴백이 나면 설계 전제가 틀린 것
    assert out.output_mode == "strict" and out.degraded_output_mode is False


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"), reason="ANTHROPIC_API_KEY 없음"
)
async def test_anthropic_vision_smoke():
    adapter = AnthropicVisionAdapter(
        LLMFactory(),
        _model("anthropic", "claude-sonnet-4-6", "ANTHROPIC_API_KEY"),
        MagicMock(),
    )
    out = await adapter.describe(
        _chart_candidate(), ElementType.CHART, DescribeOptions("ko", "brief")
    )
    _assert_chart_outcome(out)
    # Anthropic 은 strict 가 tool-call 기반이라 json 폴백이 날 수 있다 — 모드만 기록
    assert out.output_mode in ("strict", "json", "text")


@pytest.mark.asyncio
@pytest.mark.skipif(
    not (
        os.environ.get("MM_SMOKE_LOCAL_BASE_URL")
        and os.environ.get("MM_SMOKE_LOCAL_MODEL")
    ),
    reason="MM_SMOKE_LOCAL_BASE_URL / MM_SMOKE_LOCAL_MODEL 없음 (로컬 vLLM/Ollama)",
)
async def test_openai_compatible_local_vision_smoke():
    adapter = OpenAICompatibleVisionAdapter(
        LLMFactory(),
        _model(
            "openai",
            os.environ["MM_SMOKE_LOCAL_MODEL"],
            "MM_SMOKE_LOCAL_API_KEY",
            base_url=os.environ["MM_SMOKE_LOCAL_BASE_URL"],
        ),
        MagicMock(),
    )
    out = await adapter.describe(
        _chart_candidate(), ElementType.CHART, DescribeOptions("ko", "brief")
    )
    _assert_chart_outcome(out)
    assert out.output_mode in ("json", "text")  # strict 는 애초에 제외


@pytest.mark.asyncio
@pytest.mark.skipif(not os.environ.get("OPENAI_API_KEY"), reason="OPENAI_API_KEY 없음")
async def test_end_to_end_use_case_with_real_openai(monkeypatch):
    """합성 PDF → UseCase.run() 실 호출 (Design §8.1 Smoke). 비용 가드: 상한 2장."""
    from unittest.mock import AsyncMock

    import fitz
    from src.api.multimodal_di import (
        build_extractor_registry,
        build_vision_adapter_registry,
    )
    from src.application.multimodal.use_case import MultimodalExtractionUseCase
    from src.domain.multimodal.value_objects import ElementStatus, MultimodalSettings

    from tests.infrastructure.multimodal.test_pdf_extractor import _draw_table, _png

    doc = fitz.open()
    p1 = doc.new_page(width=595, height=842)
    p1.insert_image(fitz.Rect(72, 100, 472, 400), stream=sample_chart_png())
    p1.insert_image(fitz.Rect(500, 20, 548, 68), stream=_png(48, 48, (30, 30, 200)))
    p2 = doc.new_page(width=595, height=842)
    _draw_table(p2, fitz.Rect(72, 100, 500, 300))
    pdf = doc.tobytes()
    doc.close()

    settings = MultimodalSettings(
        id="s",
        enabled=True,
        vision_model_id="smoke-openai",
        max_images_per_doc=2,
        min_image_px=100,
        min_area_ratio=0.02,
        concurrency=2,
        timeout_sec=90,
        output_language="ko",
        detail_level="brief",
        updated_at=datetime.now(UTC),
    )
    settings_repo = MagicMock()
    settings_repo.get = AsyncMock(return_value=settings)
    llm_repo = MagicMock()
    llm_repo.find_by_id = AsyncMock(
        return_value=_model("openai", "gpt-4o", "OPENAI_API_KEY")
    )
    uc = MultimodalExtractionUseCase(
        extractors=build_extractor_registry(),
        adapters=build_vision_adapter_registry(),
        settings_repo=settings_repo,
        llm_model_repo=llm_repo,
        llm_factory=LLMFactory(),
        logger=MagicMock(),
    )
    result = await uc.run(pdf, "smoke.pdf", "smoke-req")

    assert result.total_candidates >= 2
    assert result.dropped_by_filter >= 1  # 48px 아이콘
    succeeded = [e for e in result.elements if e.status is ElementStatus.SUCCEEDED]
    assert succeeded, [(e.status, e.reason) for e in result.elements]
    chart = next((e for e in succeeded if e.element_type is ElementType.CHART), None)
    assert chart is not None and chart.description
    assert chart.model_id == "smoke-openai" and chart.elapsed_ms is not None
