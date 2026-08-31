"""multimodal-extractor DI 배선.

Design Ref: multimodal-extractor §9.4 (DI는 main.py 경유) / §9.5 (레지스트리 키 규칙)
- 레지스트리 2개는 앱 수명 싱글턴(무거운 객체 아님 — 어댑터는 요청마다 build 됨,
  클라이언트 생성은 LLMFactory 가 담당). UseCase 는 per-request 세션
  (설정 repo · llm_model repo 단일 세션).
- 어댑터 등록: openai / anthropic / (ollama, openai_compatible → 동일 어댑터).
  gemini 미등록.
- main.py 가 4000줄을 넘어 비대하므로 배선을 이 모듈로 분리하고
  main.py 는 호출 1줄만 둔다.
"""

from collections.abc import Callable

from fastapi import Depends, FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.multimodal.registries import (
    ExtractorRegistry,
    VisionAdapterRegistry,
)
from src.application.multimodal.settings_use_case import MultimodalSettingsUseCase
from src.application.multimodal.use_case import MultimodalExtractionUseCase
from src.domain.llm.interfaces import LLMFactoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface


def build_extractor_registry() -> ExtractorRegistry:
    from src.infrastructure.multimodal.extractors.pdf_pymupdf_extractor import (
        PdfPyMuPdfExtractor,
    )

    reg = ExtractorRegistry()
    reg.register(PdfPyMuPdfExtractor())
    return reg


def build_vision_adapter_registry() -> VisionAdapterRegistry:
    from src.infrastructure.multimodal.vision.anthropic_vision_adapter import (
        AnthropicVisionAdapter,
    )
    from src.infrastructure.multimodal.vision.openai_compatible_vision_adapter import (
        OpenAICompatibleVisionAdapter,
    )
    from src.infrastructure.multimodal.vision.openai_vision_adapter import (
        OpenAIVisionAdapter,
    )

    reg = VisionAdapterRegistry()
    reg.register(OpenAIVisionAdapter)
    reg.register(AnthropicVisionAdapter)
    # Design §9.5: ollama 와 openai_compatible 는 같은 어댑터(OpenAI 포맷, strict 제외)
    reg.register(OpenAICompatibleVisionAdapter, keys=("ollama", "openai_compatible"))
    return reg


def wire_multimodal(
    app: FastAPI,
    *,
    get_session: Callable[..., AsyncSession],
    llm_factory: LLMFactoryInterface,
    logger: LoggerInterface,
) -> None:
    """dependency_overrides 등록 + 라우터 include. create_app() 에서 1회 호출."""
    from src.api.routes.admin_multimodal_router import (
        get_multimodal_settings_use_case,
    )
    from src.api.routes.admin_multimodal_router import router as admin_multimodal_router
    from src.api.routes.preview_router import (
        get_multimodal_extraction_use_case,
        get_multimodal_thumbnailer,
    )
    from src.infrastructure.llm_model.llm_model_repository import LlmModelRepository
    from src.infrastructure.multimodal.repository import MultimodalSettingRepository
    from src.infrastructure.multimodal.thumbnail import thumbnail_b64

    extractors = build_extractor_registry()
    adapters = build_vision_adapter_registry()

    def _extraction_factory(
        session: AsyncSession = Depends(get_session),
    ) -> MultimodalExtractionUseCase:
        return MultimodalExtractionUseCase(
            extractors=extractors,
            adapters=adapters,
            settings_repo=MultimodalSettingRepository(session, logger),
            llm_model_repo=LlmModelRepository(session, logger),
            llm_factory=llm_factory,
            logger=logger,
        )

    def _settings_factory(
        session: AsyncSession = Depends(get_session),
    ) -> MultimodalSettingsUseCase:
        return MultimodalSettingsUseCase(
            settings_repo=MultimodalSettingRepository(session, logger),
            llm_model_repo=LlmModelRepository(session, logger),
            adapters=adapters,
            llm_factory=llm_factory,
            logger=logger,
        )

    app.dependency_overrides[get_multimodal_extraction_use_case] = _extraction_factory
    app.dependency_overrides[get_multimodal_settings_use_case] = _settings_factory
    app.dependency_overrides[get_multimodal_thumbnailer] = lambda: thumbnail_b64
    app.include_router(admin_multimodal_router)
