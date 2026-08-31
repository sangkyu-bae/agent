"""MultimodalExtractionUseCase — 추출 → 필터 → 상한 → 동시 비전 호출 → 결과 조립.

Design Ref: multimodal-extractor §2.2 (데이터 흐름), §4.2 (인프로세스 포트),
§6.3 (degraded/예외 경계)
- Plan FR-09: Semaphore(concurrency), 건당 timeout,
  429/timeout 만 1회 재시도(지수 백오프)
- Plan FR-10: 설정 오류(비활성·모델 미선택/없음/비전 미지원·API 키 env 없음)는 예외 전파
- Plan FR-16: run() 은 저장 모듈이 주입받아 호출한다.
  건별 비전 실패로는 절대 예외를 내지 않는다.
- Plan FR-08: elapsed_ms/status/model_id 등 서버 계산 필드는 여기서만 채운다
  (LLM 필드 금지).
"""

import asyncio
import os
import time
import uuid
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from src.application.multimodal.registries import (
    ExtractorRegistry,
    VisionAdapterRegistry,
)
from src.domain.llm.interfaces import LLMFactoryInterface
from src.domain.llm_model.entity import LlmModel
from src.domain.llm_model.interfaces import LlmModelRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.multimodal.errors import (
    MultimodalDisabledError,
    MultimodalNotConfiguredError,
)
from src.domain.multimodal.interfaces import (
    DescribeOptions,
    DescribeOutcome,
    MultimodalSettingRepository,
    VisionDescriberPort,
)
from src.domain.multimodal.policies import LimitPolicy, NoiseFilterPolicy
from src.domain.multimodal.schemas import DescriptionDraft
from src.domain.multimodal.value_objects import (
    ChartReading,
    DataPoint,
    ElementStatus,
    ElementType,
    ExtractionResult,
    ImageCandidate,
    MultimodalElement,
    MultimodalSettings,
)

if TYPE_CHECKING:
    from src.domain.pdf_analyzer.schemas import AnalysisResult

_TRANSIENT_STATUS = {408, 429, 500, 502, 503, 504}


class MultimodalExtractionUseCase:
    def __init__(
        self,
        extractors: ExtractorRegistry,
        adapters: VisionAdapterRegistry,
        settings_repo: MultimodalSettingRepository,
        llm_model_repo: LlmModelRepositoryInterface,
        llm_factory: LLMFactoryInterface,
        logger: LoggerInterface,
        retry_backoff_sec: float = 2.0,
        callbacks: list[Any] | None = None,
    ) -> None:
        self._extractors = extractors
        self._adapters = adapters
        self._settings_repo = settings_repo
        self._llm_model_repo = llm_model_repo
        self._llm_factory = llm_factory
        self._logger = logger
        self._retry_backoff_sec = retry_backoff_sec
        self._callbacks = callbacks
        # 테스트 훅: 어댑터 생성 직후 호출(동작 주입). 운영 경로에서는 None.
        self._on_adapter_built: Callable[[VisionDescriberPort], None] | None = None
        self._timeout_override_sec: float | None = None

    # ── public ────────────────────────────────────────────────────────────────

    async def run(
        self,
        file_bytes: bytes,
        filename: str,
        request_id: str,
        analysis: "AnalysisResult | None" = None,
    ) -> ExtractionResult:
        extractor = self._extractors.resolve(filename)  # UnsupportedFormatError 우선
        settings = await self._settings_repo.get(request_id)
        if not settings.enabled:
            raise MultimodalDisabledError("multimodal extraction is disabled")
        llm_model = await self.resolve_vision_model(settings, request_id)

        t0 = time.perf_counter()
        candidates = extractor.extract(file_bytes, filename, analysis)
        extract_ms = _ms(t0)
        filtered = NoiseFilterPolicy.apply(candidates, settings)
        limited = LimitPolicy.apply(filtered.kept, settings)

        t1 = time.perf_counter()
        described = await self._describe_all(
            limited.to_call, settings, llm_model, request_id
        )
        describe_ms = _ms(t1)

        skipped = [
            _skipped_element(s.candidate, s.reason, llm_model.id)
            for s in limited.skipped
        ]
        elements = tuple(described + skipped)
        result = ExtractionResult(
            elements=elements,
            total_candidates=len(candidates),
            dropped_by_filter=len(filtered.dropped),
            skipped_by_limit=len(limited.skipped),
            succeeded=sum(e.status is ElementStatus.SUCCEEDED for e in elements),
            failed=sum(e.status is ElementStatus.FAILED for e in elements),
            vision_model_id=llm_model.id,
            provider=llm_model.provider,
            model_name=llm_model.model_name,
            timings_ms=(("extract", extract_ms), ("describe", describe_ms)),
            dropped=tuple(filtered.dropped),
        )
        self._logger.info(
            "multimodal.run done",
            request_id=request_id,
            filename=filename,
            total=result.total_candidates,
            dropped=result.dropped_by_filter,
            skipped=result.skipped_by_limit,
            succeeded=result.succeeded,
            failed=result.failed,
            provider=llm_model.provider,
            model=llm_model.model_name,
            extract_ms=extract_ms,
            describe_ms=describe_ms,
        )
        return result

    async def resolve_vision_model(
        self, settings: MultimodalSettings, request_id: str
    ) -> LlmModel:
        """설정의 소프트 참조를 검증해 LlmModel 로 푼다.

        실패는 전부 MultimodalNotConfiguredError.
        """
        if not settings.vision_model_id:
            raise MultimodalNotConfiguredError("vision_model_id is not set")
        model = await self._llm_model_repo.find_by_id(
            settings.vision_model_id, request_id
        )
        if model is None:
            raise MultimodalNotConfiguredError(
                f"vision model '{settings.vision_model_id}' not found"
            )
        if not model.is_active or not model.supports_vision:
            raise MultimodalNotConfiguredError(
                f"vision model '{model.model_name}' is inactive or not vision-capable"
            )
        if not model.base_url and not os.environ.get(model.api_key_env):
            raise MultimodalNotConfiguredError(
                f"api key env '{model.api_key_env}' is not set for {model.provider}"
            )
        return model

    def build_adapter(self, llm_model: LlmModel) -> VisionDescriberPort:
        adapter = self._adapters.build(
            llm_model.provider,
            llm_factory=self._llm_factory,
            llm_model=llm_model,
            logger=self._logger,
            callbacks=self._callbacks,
        )
        if self._on_adapter_built is not None:
            self._on_adapter_built(adapter)
        return adapter

    # ── internal ──────────────────────────────────────────────────────────────

    async def _describe_all(
        self,
        to_call: list[ImageCandidate],
        settings: MultimodalSettings,
        llm_model: LlmModel,
        request_id: str,
    ) -> list[MultimodalElement]:
        if not to_call:
            return []
        adapter = self.build_adapter(llm_model)
        options = DescribeOptions(settings.output_language, settings.detail_level)
        timeout = self._timeout_override_sec or float(settings.timeout_sec)
        sem = asyncio.Semaphore(settings.concurrency)

        async def one(c: ImageCandidate) -> MultimodalElement:
            async with sem:
                return await self._describe_one(
                    adapter, c, options, timeout, llm_model, request_id
                )

        return list(await asyncio.gather(*(one(c) for c in to_call)))

    async def _describe_one(
        self,
        adapter: VisionDescriberPort,
        c: ImageCandidate,
        options: DescribeOptions,
        timeout: float,
        llm_model: LlmModel,
        request_id: str,
    ) -> MultimodalElement:
        t0 = time.perf_counter()
        try:
            outcome = await self._call_with_retry(adapter, c, options, timeout)
        except Exception as e:  # noqa: BLE001 — 건별 degraded (Design §6.3)
            self._logger.warning(
                "vision.describe failed",
                request_id=request_id,
                page=c.page,
                sha256=c.sha256[:12],
                provider=llm_model.provider,
                exception=e,
            )
            return _failed_element(c, _reason(e), llm_model.id, _ms(t0))
        elapsed = _ms(t0)
        self._logger.info(
            "vision.describe ok",
            request_id=request_id,
            page=c.page,
            provider=llm_model.provider,
            model=llm_model.model_name,
            mode=outcome.output_mode,
            elapsed_ms=elapsed,
            usage=outcome.usage,
        )
        return _succeeded_element(c, outcome, llm_model.id, elapsed, self._logger)

    async def _call_with_retry(
        self,
        adapter: VisionDescriberPort,
        c: ImageCandidate,
        options: DescribeOptions,
        timeout: float,
    ) -> DescribeOutcome:
        try:
            return await asyncio.wait_for(
                adapter.describe(c, c.hint_type, options), timeout
            )
        except Exception as e:  # noqa: BLE001
            if not _is_transient(e):
                raise
            await asyncio.sleep(self._retry_backoff_sec)
        return await asyncio.wait_for(
            adapter.describe(c, c.hint_type, options), timeout
        )


# ── helpers (순수 함수) ──────────────────────────────────────────────────────────


def _ms(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)


def _is_transient(e: Exception) -> bool:
    if isinstance(e, (asyncio.TimeoutError, TimeoutError)):
        return True
    status = getattr(e, "status_code", None) or getattr(e, "status", None)
    return isinstance(status, int) and status in _TRANSIENT_STATUS


def _reason(e: Exception) -> str:
    if isinstance(e, (asyncio.TimeoutError, TimeoutError)):
        return "timeout (1 retry)"
    return f"{type(e).__name__}: {e}"[:500]


def _base_fields(c: ImageCandidate, model_id: str | None) -> dict[str, Any]:
    return dict(
        element_id=uuid.uuid4().hex,
        page=c.page,
        bbox=c.bbox,
        image_bytes=c.image_bytes,
        mime=c.mime,
        width=c.width,
        height=c.height,
        sha256=c.sha256,
        model_id=model_id,
    )


def _skipped_element(
    c: ImageCandidate, reason: str, model_id: str
) -> MultimodalElement:
    return MultimodalElement(
        **_base_fields(c, model_id),
        element_type=c.hint_type,
        status=ElementStatus.SKIPPED,
        reason=reason,
        description=None,
        keywords=(),
        markdown_table=None,
        chart=None,
        page_text=None,
        elapsed_ms=None,
        degraded_output_mode=False,
    )


def _failed_element(
    c: ImageCandidate, reason: str, model_id: str, elapsed_ms: int
) -> MultimodalElement:
    return MultimodalElement(
        **_base_fields(c, model_id),
        element_type=c.hint_type,
        status=ElementStatus.FAILED,
        reason=reason,
        description=None,
        keywords=(),
        markdown_table=None,
        chart=None,
        page_text=None,
        elapsed_ms=elapsed_ms,
        degraded_output_mode=False,
    )


def _succeeded_element(
    c: ImageCandidate,
    outcome: DescribeOutcome,
    model_id: str,
    elapsed_ms: int,
    logger: LoggerInterface,
) -> MultimodalElement:
    draft = outcome.draft
    detected = ElementType(draft.detected_type)
    if detected is not c.hint_type:
        logger.info(
            "vision.describe reclassified",
            page=c.page,
            hint=c.hint_type.value,
            detected=detected.value,
        )
    return MultimodalElement(
        **_base_fields(c, model_id),
        element_type=detected,
        status=ElementStatus.SUCCEEDED,
        reason=None,
        description=draft.description,
        keywords=tuple(draft.keywords),
        markdown_table=draft.markdown_table,
        chart=_chart_of(draft),
        page_text=draft.page_text,
        elapsed_ms=elapsed_ms,
        degraded_output_mode=outcome.degraded_output_mode,
    )


def _chart_of(draft: DescriptionDraft) -> ChartReading | None:
    if draft.chart is None:
        return None
    ch = draft.chart
    return ChartReading(
        chart_type=ch.chart_type,
        x_axis=ch.x_axis,
        y_axis=ch.y_axis,
        series=tuple(ch.series),
        data_points=tuple(DataPoint(p.label, p.value) for p in ch.data_points),
        trend=ch.trend,
    )
