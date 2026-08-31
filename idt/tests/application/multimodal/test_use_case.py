"""MultimodalExtractionUseCase — Design §2.2/§4.2(인프로세스 포트)/§6.3, FR-09/10/16.

fake 추출기·fake 어댑터로: 설정 해석, 필터→상한→동시 호출,
타임아웃·재시도·건별 degraded,
설정 오류 예외, 결과 조립(Draft 복사 + 서버 계산 필드)을 검증한다.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.application.multimodal.registries import (
    ExtractorRegistry,
    VisionAdapterRegistry,
)
from src.application.multimodal.use_case import MultimodalExtractionUseCase
from src.domain.llm_model.entity import LlmModel
from src.domain.multimodal.errors import (
    MultimodalDisabledError,
    MultimodalNotConfiguredError,
    UnsupportedFormatError,
)
from src.domain.multimodal.interfaces import DescribeOutcome
from src.domain.multimodal.schemas import DescriptionDraft
from src.domain.multimodal.value_objects import (
    BBox,
    ElementStatus,
    ElementType,
    ImageCandidate,
    MultimodalSettings,
)

# ── fixtures ──────────────────────────────────────────────────────────────────


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
        updated_at=datetime(2026, 8, 21, tzinfo=UTC),
    )
    base.update(over)
    return MultimodalSettings(**base)


def _llm_model(**over) -> LlmModel:
    now = datetime.now(UTC)
    base = dict(
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
    base.update(over)
    return LlmModel(**base)


def _cand(i: int, w=300, h=300, hint=ElementType.FIGURE, page=1) -> ImageCandidate:
    return ImageCandidate(
        page=page,
        bbox=BBox(0, i, 10, i + 10),
        image_bytes=bytes([i]) * 8,
        mime="image/png",
        width=w,
        height=h,
        area_ratio=0.2,
        sha256=f"{i:064x}",
        hint_type=hint,
    )


def _draft(detected="figure", **over) -> DescriptionDraft:
    base = dict(
        detected_type=detected,
        description=f"desc-{detected}",
        keywords=["k"],
        markdown_table=None,
        chart=None,
        page_text=None,
    )
    base.update(over)
    return DescriptionDraft(**base)


class FakeExtractor:
    supported_extensions = frozenset({"pdf"})

    def __init__(self, cands):
        self._cands = cands
        self.calls = []

    def extract(self, file_bytes, filename, analysis):
        self.calls.append((filename, analysis))
        return list(self._cands)


class FakeAdapter:
    """describe 동작을 sha256 별로 지정.

    'ok' | Exception 인스턴스 | 'sleep:<sec>' | 콜러블
    """

    provider = "fake"
    instances: list[FakeAdapter] = []

    def __init__(self, llm_factory, llm_model, logger, callbacks=None):
        self.llm_model = llm_model
        self.behaviors: dict[str, object] = {}
        self.calls: list[str] = []
        self.active = 0
        self.max_active = 0
        FakeAdapter.instances.append(self)

    async def describe(self, image, element_type, options):
        self.calls.append(image.sha256)
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            b = self.behaviors.get(image.sha256, "ok")
            if callable(b):
                return await b(image, element_type, options)
            if isinstance(b, str) and b.startswith("sleep:"):
                await asyncio.sleep(float(b.split(":")[1]))
            elif isinstance(b, Exception):
                raise b
            await asyncio.sleep(0.01)
            return DescribeOutcome(
                draft=_draft(element_type.value),
                degraded_output_mode=False,
                output_mode="strict",
                usage={"total_tokens": 10},
            )
        finally:
            self.active -= 1


def _build(
    cands,
    settings=None,
    llm_model=None,
    env_key=True,
    monkeypatch=None,
) -> tuple[MultimodalExtractionUseCase, FakeExtractor]:
    FakeAdapter.instances.clear()
    settings = settings or _settings()
    settings_repo = MagicMock()
    settings_repo.get = AsyncMock(return_value=settings)
    llm_repo = MagicMock()
    llm_repo.find_by_id = AsyncMock(
        return_value=llm_model if llm_model is not None else _llm_model()
    )
    ex = FakeExtractor(cands)
    ereg = ExtractorRegistry()
    ereg.register(ex)
    vreg = VisionAdapterRegistry()
    vreg.register(FakeAdapter)
    if monkeypatch is not None:
        if env_key:
            monkeypatch.setenv("FAKE_KEY", "x")
        else:
            monkeypatch.delenv("FAKE_KEY", raising=False)
    uc = MultimodalExtractionUseCase(
        extractors=ereg,
        adapters=vreg,
        settings_repo=settings_repo,
        llm_model_repo=llm_repo,
        llm_factory=MagicMock(),
        logger=MagicMock(),
        retry_backoff_sec=0.01,
    )
    return uc, ex


# ── 정상 경로 ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_returns_elements_with_server_fields_and_draft_copy(monkeypatch):
    uc, ex = _build(
        [_cand(1), _cand(2, hint=ElementType.CHART)], monkeypatch=monkeypatch
    )
    res = await uc.run(b"pdf", "a.pdf", "req", analysis=None)
    assert res.total_candidates == 2 and res.succeeded == 2 and res.failed == 0
    assert (
        res.provider == "fake"
        and res.model_name == "fake-v"
        and res.vision_model_id == "m1"
    )
    e1 = next(e for e in res.elements if e.sha256 == f"{1:064x}")
    assert (
        e1.status is ElementStatus.SUCCEEDED and e1.element_type is ElementType.FIGURE
    )
    assert e1.description == "desc-figure" and e1.keywords == ("k",)
    assert (
        e1.image_bytes == bytes([1]) * 8
        and e1.page == 1
        and e1.bbox == BBox(0, 1, 10, 11)
    )
    assert e1.model_id == "m1" and e1.elapsed_ms is not None and e1.elapsed_ms >= 0
    assert e1.element_id and e1.degraded_output_mode is False
    assert dict(res.timings_ms).keys() >= {"extract", "describe"}
    assert ex.calls == [("a.pdf", None)]


@pytest.mark.asyncio
async def test_llm_detected_type_overrides_hint(monkeypatch):
    """LLM 재분류(detected_type) 채택 — hint 와 다르면 로그만 (Design §3.1)."""
    uc, _ = _build([_cand(1, hint=ElementType.FIGURE)], monkeypatch=monkeypatch)

    def prime(adapter):
        async def as_chart(image, et, opt):
            assert et is ElementType.FIGURE  # 프롬프트는 hint 기준
            chart = {
                "chart_type": "bar",
                "x_axis": "분기",
                "y_axis": "억원",
                "series": ["한도"],
                "data_points": [{"label": "1Q", "value": "120"}],
                "trend": "증가",
            }
            return DescribeOutcome(
                draft=_draft("chart", chart=chart),
                degraded_output_mode=False,
                output_mode="strict",
                usage=None,
            )

        adapter.behaviors[f"{1:064x}"] = as_chart

    uc._on_adapter_built = prime
    res = await uc.run(b"pdf", "a.pdf", "req")
    e = res.elements[0]
    assert e.element_type is ElementType.CHART
    assert e.chart is not None and e.chart.data_points[0].value == "120"
    assert e.chart.series == ("한도",)


@pytest.mark.asyncio
async def test_filter_and_limit_are_applied_and_reported(monkeypatch):
    cands = [_cand(1), _cand(2, w=40, h=40), _cand(3), _cand(4), _cand(1, page=2)]
    uc, _ = _build(
        cands, settings=_settings(max_images_per_doc=2), monkeypatch=monkeypatch
    )
    res = await uc.run(b"pdf", "a.pdf", "req")
    assert res.total_candidates == 5
    assert res.dropped_by_filter == 2  # 40px + duplicate sha
    assert res.skipped_by_limit == 1
    assert res.succeeded == 2
    skipped = [e for e in res.elements if e.status is ElementStatus.SKIPPED]
    assert len(skipped) == 1 and skipped[0].reason == "limit:max_images_per_doc=2"
    assert skipped[0].description is None and skipped[0].image_bytes is not None
    assert FakeAdapter.instances[0].calls.count(f"{4:064x}") == 0


@pytest.mark.asyncio
async def test_concurrency_is_bounded_by_settings(monkeypatch):
    cands = [_cand(i) for i in range(1, 7)]
    uc, _ = _build(cands, settings=_settings(concurrency=2), monkeypatch=monkeypatch)
    await uc.run(b"pdf", "a.pdf", "req")
    assert FakeAdapter.instances[0].max_active <= 2


# ── 건별 degraded ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_per_image_failure_is_recorded_not_raised(monkeypatch):
    uc, _ = _build([_cand(1), _cand(2)], monkeypatch=monkeypatch)

    def prime(adapter):
        adapter.behaviors[f"{2:064x}"] = RuntimeError("boom")

    uc._on_adapter_built = prime  # 테스트 훅: 어댑터 생성 직후 동작 주입
    res = await uc.run(b"pdf", "a.pdf", "req")
    assert res.succeeded == 1 and res.failed == 1
    failed = next(e for e in res.elements if e.status is ElementStatus.FAILED)
    assert "boom" in (failed.reason or "") and failed.description is None
    assert failed.model_id == "m1"


@pytest.mark.asyncio
async def test_timeout_per_image_then_retry_once(monkeypatch):
    uc, _ = _build(
        [_cand(1)], settings=_settings(timeout_sec=5), monkeypatch=monkeypatch
    )
    uc._timeout_override_sec = 0.05  # 테스트용 짧은 타임아웃(설정 하한 5s 우회)

    def prime(adapter):
        adapter.behaviors[f"{1:064x}"] = "sleep:1"

    uc._on_adapter_built = prime
    res = await uc.run(b"pdf", "a.pdf", "req")
    assert res.failed == 1
    assert FakeAdapter.instances[0].calls.count(f"{1:064x}") == 2  # 1회 + 재시도 1회
    assert "timeout" in res.elements[0].reason


@pytest.mark.asyncio
async def test_rate_limit_retries_once_then_succeeds(monkeypatch):
    uc, _ = _build([_cand(1)], monkeypatch=monkeypatch)

    class RateLimitError(Exception):
        status_code = 429

    def prime(adapter):
        n = {"c": 0}

        async def flaky(image, et, opt):
            n["c"] += 1
            if n["c"] == 1:
                raise RateLimitError("429")
            return DescribeOutcome(
                draft=_draft(),
                degraded_output_mode=True,
                output_mode="json",
                usage=None,
            )

        adapter.behaviors[f"{1:064x}"] = flaky

    uc._on_adapter_built = prime
    res = await uc.run(b"pdf", "a.pdf", "req")
    assert res.succeeded == 1
    assert res.elements[0].degraded_output_mode is True


@pytest.mark.asyncio
async def test_non_transient_error_is_not_retried(monkeypatch):
    uc, _ = _build([_cand(1)], monkeypatch=monkeypatch)

    def prime(adapter):
        adapter.behaviors[f"{1:064x}"] = ValueError("bad schema")

    uc._on_adapter_built = prime
    res = await uc.run(b"pdf", "a.pdf", "req")
    assert res.failed == 1 and FakeAdapter.instances[0].calls == [f"{1:064x}"]


@pytest.mark.asyncio
async def test_all_failures_still_return_result(monkeypatch):
    uc, _ = _build([_cand(1), _cand(2)], monkeypatch=monkeypatch)

    def prime(adapter):
        for i in (1, 2):
            adapter.behaviors[f"{i:064x}"] = RuntimeError("x")

    uc._on_adapter_built = prime
    res = await uc.run(b"pdf", "a.pdf", "req")
    assert res.failed == 2 and res.succeeded == 0 and len(res.elements) == 2


# ── 설정 오류 = 예외 (FR-10) ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_disabled_raises(monkeypatch):
    uc, _ = _build(
        [_cand(1)], settings=_settings(enabled=False), monkeypatch=monkeypatch
    )
    with pytest.raises(MultimodalDisabledError):
        await uc.run(b"pdf", "a.pdf", "req")


@pytest.mark.asyncio
async def test_no_model_selected_raises(monkeypatch):
    uc, _ = _build(
        [_cand(1)], settings=_settings(vision_model_id=None), monkeypatch=monkeypatch
    )
    with pytest.raises(MultimodalNotConfiguredError):
        await uc.run(b"pdf", "a.pdf", "req")


@pytest.mark.asyncio
async def test_model_missing_inactive_or_not_vision_raises(monkeypatch):
    for m in (None, _llm_model(is_active=False), _llm_model(supports_vision=False)):
        uc, _ = _build([_cand(1)], llm_model=m, monkeypatch=monkeypatch)
        if m is None:
            uc._llm_model_repo.find_by_id = AsyncMock(return_value=None)
        with pytest.raises(MultimodalNotConfiguredError):
            await uc.run(b"pdf", "a.pdf", "req")


@pytest.mark.asyncio
async def test_missing_api_key_env_raises_unless_base_url(monkeypatch):
    uc, _ = _build([_cand(1)], env_key=False, monkeypatch=monkeypatch)
    with pytest.raises(MultimodalNotConfiguredError):
        await uc.run(b"pdf", "a.pdf", "req")
    # base_url(self-host) 이면 키 없어도 통과 (LLMFactory EMPTY 관례)
    uc2, _ = _build(
        [_cand(1)],
        llm_model=_llm_model(base_url="http://vllm:8000/v1"),
        env_key=False,
        monkeypatch=monkeypatch,
    )
    res = await uc2.run(b"pdf", "a.pdf", "req")
    assert res.succeeded == 1


@pytest.mark.asyncio
async def test_unsupported_extension_raises_before_model_resolution(monkeypatch):
    uc, _ = _build([_cand(1)], monkeypatch=monkeypatch)
    with pytest.raises(UnsupportedFormatError):
        await uc.run(b"x", "a.docx", "req")


@pytest.mark.asyncio
async def test_no_candidates_returns_empty_result_without_building_adapter(monkeypatch):
    uc, _ = _build([], monkeypatch=monkeypatch)
    res = await uc.run(b"pdf", "a.pdf", "req")
    assert res.elements == () and res.total_candidates == 0
    assert FakeAdapter.instances == []


# ── 설정 검증 헬퍼 (SettingsUseCase 와 공유) ──────────────────────────────────


@pytest.mark.asyncio
async def test_resolve_vision_model_is_reusable(monkeypatch):
    uc, _ = _build([], monkeypatch=monkeypatch)
    m = await uc.resolve_vision_model(_settings(), "req")
    assert m.id == "m1"
