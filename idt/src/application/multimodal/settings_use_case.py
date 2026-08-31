"""MultimodalSettingsUseCase — 전역 설정 조회/전체 교체/연결 테스트.

Design Ref: multimodal-extractor §4.2 (GET/PUT settings, POST test) / Plan FR-13, FR-14
- PUT 은 전체 교체. 범위 검증은 도메인 VO(MultimodalSettings.__post_init__)가 단일 출처.
- vision_model_id 는 소프트 참조: 저장 시 존재·is_active·supports_vision 검증
  (chunking_profile._validate_summary_model 선례).
  GET 은 끊어진 참조를 warnings 로 알린다.
- 연결 테스트는 내장 샘플 차트(또는 업로드 1장)를 선택 모델로 1회 호출한다.
"""

import time
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from importlib import resources

from src.application.multimodal.registries import VisionAdapterRegistry
from src.domain.llm.interfaces import LLMFactoryInterface
from src.domain.llm_model.entity import LlmModel
from src.domain.llm_model.interfaces import LlmModelRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.multimodal.errors import MultimodalError, MultimodalNotConfiguredError
from src.domain.multimodal.interfaces import (
    DescribeOptions,
    MultimodalSettingRepository,
)
from src.domain.multimodal.schemas import DescriptionDraft
from src.domain.multimodal.value_objects import (
    BBox,
    ElementType,
    ImageCandidate,
    MultimodalSettings,
)


class VisionModelNotFoundError(MultimodalError):
    """PUT 에 존재하지 않는 모델 id (→ 404)."""


class VisionModelNotCapableError(MultimodalError):
    """PUT 에 비활성 또는 supports_vision=0 모델 (→ 409)."""


@dataclass(frozen=True)
class SettingsUpdate:
    enabled: bool
    vision_model_id: str | None
    max_images_per_doc: int
    min_image_px: int
    min_area_ratio: float
    concurrency: int
    timeout_sec: int
    output_language: str
    detail_level: str


@dataclass(frozen=True)
class SettingsView:
    settings: MultimodalSettings
    vision_model: LlmModel | None
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class ConnectionTestResult:
    ok: bool
    provider: str
    model_name: str
    elapsed_ms: int
    degraded_output_mode: bool
    draft: DescriptionDraft | None
    error: str | None


def sample_chart_png() -> bytes:
    """연결 테스트 기본 이미지.

    src/infrastructure/multimodal/assets/sample_chart.png
    """
    return (
        resources.files("src.infrastructure.multimodal.assets")
        .joinpath("sample_chart.png")
        .read_bytes()
    )


class MultimodalSettingsUseCase:
    TEST_ELEMENT_TYPE = ElementType.CHART

    def __init__(
        self,
        settings_repo: MultimodalSettingRepository,
        llm_model_repo: LlmModelRepositoryInterface,
        adapters: VisionAdapterRegistry,
        llm_factory: LLMFactoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._settings_repo = settings_repo
        self._llm_model_repo = llm_model_repo
        self._adapters = adapters
        self._llm_factory = llm_factory
        self._logger = logger

    async def get(self, request_id: str) -> SettingsView:
        settings = await self._settings_repo.get(request_id)
        return await self._view(settings, request_id)

    async def update(self, upd: SettingsUpdate, request_id: str) -> SettingsView:
        current = await self._settings_repo.get(request_id)
        if upd.vision_model_id is not None:
            await self._validate_model(upd.vision_model_id, request_id)
        new = MultimodalSettings(
            id=current.id,
            enabled=upd.enabled,
            vision_model_id=upd.vision_model_id,
            max_images_per_doc=upd.max_images_per_doc,
            min_image_px=upd.min_image_px,
            min_area_ratio=upd.min_area_ratio,
            concurrency=upd.concurrency,
            timeout_sec=upd.timeout_sec,
            output_language=upd.output_language,
            detail_level=upd.detail_level,
            updated_at=datetime.now(UTC),
        )  # ValueError(범위) 는 그대로 전파 → 라우터가 400
        saved = await self._settings_repo.update(new, request_id)
        self._logger.info(
            "multimodal settings updated",
            request_id=request_id,
            enabled=saved.enabled,
            vision_model_id=saved.vision_model_id,
        )
        return await self._view(saved, request_id)

    async def test_connection(
        self, image_bytes: bytes | None, mime: str, request_id: str
    ) -> ConnectionTestResult:
        settings = await self._settings_repo.get(request_id)
        model = await self._resolve_configured_model(settings, request_id)
        data = image_bytes or sample_chart_png()
        mime = mime if image_bytes else "image/png"
        candidate = ImageCandidate(
            page=1,
            bbox=BBox(0, 0, 0, 0),
            image_bytes=data,
            mime=mime,
            width=0,
            height=0,
            area_ratio=0.0,
            sha256=sha256(data).hexdigest(),
            hint_type=self.TEST_ELEMENT_TYPE,
        )
        adapter = self._adapters.build(
            model.provider,
            llm_factory=self._llm_factory,
            llm_model=model,
            logger=self._logger,
            callbacks=None,
        )
        options = DescribeOptions(settings.output_language, settings.detail_level)
        t0 = time.perf_counter()
        try:
            outcome = await adapter.describe(candidate, self.TEST_ELEMENT_TYPE, options)
        except Exception as e:  # noqa: BLE001 — 연결 테스트는 실패도 결과(ok=False)
            self._logger.warning(
                "multimodal connection test failed",
                request_id=request_id,
                provider=model.provider,
                model=model.model_name,
                exception=e,
            )
            return ConnectionTestResult(
                ok=False,
                provider=model.provider,
                model_name=model.model_name,
                elapsed_ms=_ms(t0),
                degraded_output_mode=False,
                draft=None,
                error=f"{type(e).__name__}: {e}"[:500],
            )
        return ConnectionTestResult(
            ok=True,
            provider=model.provider,
            model_name=model.model_name,
            elapsed_ms=_ms(t0),
            degraded_output_mode=outcome.degraded_output_mode,
            draft=outcome.draft,
            error=None,
        )

    # ── internal ──────────────────────────────────────────────────────────────

    async def _validate_model(self, model_id: str, request_id: str) -> LlmModel:
        model = await self._llm_model_repo.find_by_id(model_id, request_id)
        if model is None:
            raise VisionModelNotFoundError(f"llm model '{model_id}' not found")
        if not model.is_active or not model.supports_vision:
            raise VisionModelNotCapableError(
                f"llm model '{model.model_name}' is inactive or not vision-capable"
            )
        return model

    async def _resolve_configured_model(
        self, settings: MultimodalSettings, request_id: str
    ) -> LlmModel:
        if not settings.vision_model_id:
            raise MultimodalNotConfiguredError("vision_model_id is not set")
        try:
            return await self._validate_model(settings.vision_model_id, request_id)
        except MultimodalError as e:
            raise MultimodalNotConfiguredError(str(e)) from e

    async def _view(
        self, settings: MultimodalSettings, request_id: str
    ) -> SettingsView:
        if not settings.vision_model_id:
            return SettingsView(settings, None, ())
        model = await self._llm_model_repo.find_by_id(
            settings.vision_model_id, request_id
        )
        warnings: list[str] = []
        if model is None:
            warnings.append(f"selected model '{settings.vision_model_id}' not found")
        else:
            if not model.is_active:
                warnings.append("selected model inactive")
            if not model.supports_vision:
                warnings.append("selected model does not support vision")
        return SettingsView(settings, model, tuple(warnings))


def _ms(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)
