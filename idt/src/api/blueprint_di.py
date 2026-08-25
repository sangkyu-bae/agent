"""golden-sample-blueprint DI 배선.

Design Ref: golden-sample-blueprint §2.1 / §9.1 / D3 (비전 설정 재사용) / D8
- 추출기 레지스트리·FontCatalog 는 앱 수명 싱글턴. UseCase 는 per-request 세션.
- VisionProvider 는 multimodal 의 `MultimodalExtractionUseCase.resolve_vision_model /
  build_adapter` 를 그대로 써 설정 검증·어댑터 생성을 복제하지 않는다.
- config 소비 지점은 여기 1곳 (blueprint_font_dir / blueprint_default_font).
- main.py 는 wire_blueprint() 호출 1회만 둔다 (탈착형 이음매).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from fastapi import Depends, FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.blueprint.admin_use_case import BlueprintAdminUseCase
from src.application.blueprint.extraction_use_case import (
    BlueprintExtractionUseCase,
    VisionSession,
)
from src.application.blueprint.registries import SampleExtractorRegistry
from src.application.multimodal.use_case import MultimodalExtractionUseCase
from src.domain.llm.interfaces import LLMFactoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface


def build_sample_extractor_registry() -> SampleExtractorRegistry:
    from src.infrastructure.blueprint.extractors.pdf_style_extractor import (
        PdfStyleExtractor,
    )
    from src.infrastructure.blueprint.extractors.pptx_style_extractor import (
        PptxStyleExtractor,
    )

    reg = SampleExtractorRegistry()
    reg.register(PdfStyleExtractor())
    reg.register(PptxStyleExtractor())
    return reg


def build_font_catalog(font_dir: str, default_font: str):
    from src.infrastructure.blueprint.fonts import FontCatalog

    return FontCatalog(
        font_dir=Path(font_dir) if font_dir else None, default=default_font
    )


class MultimodalVisionProvider:
    """VisionProviderPort — multimodal UseCase 의 모델 해석·어댑터 생성을 재사용."""

    def __init__(self, settings_repo, multimodal: MultimodalExtractionUseCase) -> None:
        self._settings_repo = settings_repo
        self._mm = multimodal

    async def resolve(self, request_id: str) -> VisionSession:
        from src.domain.multimodal.errors import MultimodalDisabledError
        from src.infrastructure.blueprint.llm.synthesizer import NarrativeSynthesizer
        from src.infrastructure.blueprint.vision.page_classifier import (
            VisionPageClassifier,
        )

        settings = await self._settings_repo.get(request_id)
        if not settings.enabled:
            raise MultimodalDisabledError("multimodal extraction is disabled")
        model = await self._mm.resolve_vision_model(settings, request_id)
        adapter = self._mm.build_adapter(model)
        return VisionSession(
            settings=settings,
            classifier=VisionPageClassifier(adapter),
            synthesizer=NarrativeSynthesizer(adapter),
        )


def _build_vision_provider_factory(
    get_session, llm_factory: LLMFactoryInterface, logger: LoggerInterface
):
    """세션 → MultimodalVisionProvider (multimodal 레지스트리는 앱 수명 싱글턴)."""
    from src.api.multimodal_di import (
        build_extractor_registry,
        build_vision_adapter_registry,
    )
    from src.infrastructure.llm_model.llm_model_repository import LlmModelRepository
    from src.infrastructure.multimodal.repository import MultimodalSettingRepository

    mm_extractors = build_extractor_registry()
    mm_adapters = build_vision_adapter_registry()

    def _provider(session: AsyncSession) -> MultimodalVisionProvider:
        settings_repo = MultimodalSettingRepository(session, logger)
        multimodal = MultimodalExtractionUseCase(
            extractors=mm_extractors,
            adapters=mm_adapters,
            settings_repo=settings_repo,
            llm_model_repo=LlmModelRepository(session, logger),
            llm_factory=llm_factory,
            logger=logger,
        )
        return MultimodalVisionProvider(settings_repo, multimodal)

    return _provider


def build_admin_use_case(
    session: AsyncSession,
    *,
    llm_factory: LLMFactoryInterface,
    logger: LoggerInterface,
    settings,
) -> BlueprintAdminUseCase:
    """세션 1개로 admin+extraction 을 조립 (CLI 재추출 스크립트용, style-fidelity §4.4).

    wire_blueprint 과 동일한 구성 — 레지스트리·폰트 카탈로그는 호출마다 새로 만든다.
    """
    from src.infrastructure.blueprint.repository import BlueprintRepository

    fonts = build_font_catalog(
        settings.blueprint_font_dir, settings.blueprint_default_font
    )
    extraction = BlueprintExtractionUseCase(
        extractors=build_sample_extractor_registry(),
        vision=_build_vision_provider_factory(None, llm_factory, logger)(session),
        fonts=fonts,
        logger=logger,
    )
    return BlueprintAdminUseCase(
        BlueprintRepository(session, logger), fonts, logger, extraction=extraction
    )


def wire_blueprint(
    app: FastAPI,
    *,
    get_session: Callable[..., AsyncSession],
    llm_factory: LLMFactoryInterface,
    logger: LoggerInterface,
    settings,
) -> None:
    """dependency_overrides 등록 + 라우터 include. create_app() 에서 1회 호출."""
    from src.api.routes.admin_blueprint_router import (
        get_blueprint_admin_use_case,
        get_blueprint_extraction_use_case,
        get_blueprint_thumbnailer,
        options_router,
        router,
    )
    from src.infrastructure.blueprint.repository import BlueprintRepository
    from src.infrastructure.multimodal.thumbnail import thumbnail_b64

    extractors = build_sample_extractor_registry()
    fonts = build_font_catalog(
        settings.blueprint_font_dir, settings.blueprint_default_font
    )
    vision_provider = _build_vision_provider_factory(get_session, llm_factory, logger)

    def _extraction_factory(
        session: AsyncSession = Depends(get_session),
    ) -> BlueprintExtractionUseCase:
        return BlueprintExtractionUseCase(
            extractors=extractors,
            vision=vision_provider(session),
            fonts=fonts,
            logger=logger,
        )

    def _admin_factory(
        session: AsyncSession = Depends(get_session),
    ) -> BlueprintAdminUseCase:
        return BlueprintAdminUseCase(
            BlueprintRepository(session, logger),
            fonts,
            logger,
            extraction=_extraction_factory(session),
        )

    app.dependency_overrides[get_blueprint_extraction_use_case] = _extraction_factory
    app.dependency_overrides[get_blueprint_admin_use_case] = _admin_factory
    app.dependency_overrides[get_blueprint_thumbnailer] = lambda: thumbnail_b64
    app.include_router(router)
    app.include_router(options_router)


def build_presentation_generation_use_case(
    *,
    conversion_adapter,
    attachment_store,
    logger: LoggerInterface,
    input_max_chars: int,
    concurrency: int = 4,
):
    """에이전트 런타임용 PresentationGenerationUseCase (WorkflowCompiler 주입).

    planner/writer 는 워커 LLM 을 받아 요청마다 생성된다 (팩토리).
    변환 어댑터·첨부 저장소는 문서생성기와 같은 인스턴스를 공유한다 (신규 생성 금지).
    """
    from src.application.blueprint.generation_use_case import (
        PresentationGenerationUseCase,
    )
    from src.infrastructure.blueprint.llm.slide_planner import SlidePlanner
    from src.infrastructure.blueprint.llm.slot_writer import SlotWriter
    from src.infrastructure.blueprint.renderer.pptx_renderer import PptxSlideRenderer

    return PresentationGenerationUseCase(
        planner_factory=lambda llm, cb: SlidePlanner(llm, logger, cb),
        writer_factory=lambda llm, cb: SlotWriter(llm, logger, cb),
        renderer=PptxSlideRenderer(),
        store=attachment_store,
        converter=conversion_adapter,
        logger=logger,
        concurrency=concurrency,
        input_max_chars=input_max_chars,
    )
